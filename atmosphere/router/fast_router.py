"""
Fast Distributed Project Router

Routes requests to LlamaFarm projects using pre-computed embeddings.
Designed for sub-millisecond routing decisions.

Key features:
- Pre-computed embeddings for all project metadata
- Local numpy-based vector index (no external deps)
- Gossip protocol integration for distributed sync
- No LLM calls during routing
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os

import numpy as np

logger = logging.getLogger(__name__)

# Registry paths
REGISTRY_PATH = Path.home() / ".llamafarm" / "atmosphere" / "projects" / "index.json"
EMBEDDING_CACHE_PATH = Path.home() / ".llamafarm" / "atmosphere" / "embeddings.npz"

# LlamaFarm API
LLAMAFARM_BASE = "http://localhost:14345"

# Embedding settings
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 dimension
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class ProjectEntry:
    """A project in the routing table."""
    namespace: str
    name: str
    domain: str
    capabilities: List[str]
    topics: List[str]
    description: str
    models: List[str]
    nodes: List[str]  # Which nodes have this project
    embedding: Optional[np.ndarray] = None  # Pre-computed embedding
    
    @property
    def model_path(self) -> str:
        return f"{self.namespace}/{self.name}"
    
    @property
    def has_rag(self) -> bool:
        return "rag" in self.capabilities
    
    @property
    def has_tools(self) -> bool:
        return "tools" in self.capabilities
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "domain": self.domain,
            "capabilities": self.capabilities,
            "topics": self.topics,
            "description": self.description,
            "models": self.models,
            "nodes": self.nodes,
            "embedding": self.embedding.tolist() if self.embedding is not None else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectEntry":
        embedding = None
        if data.get("embedding"):
            embedding = np.array(data["embedding"], dtype=np.float32)
        return cls(
            namespace=data["namespace"],
            name=data["name"],
            domain=data.get("domain", "general"),
            capabilities=data.get("capabilities", ["chat"]),
            topics=data.get("topics", []),
            description=data.get("description", ""),
            models=data.get("models", ["default"]),
            nodes=data.get("nodes", []),
            embedding=embedding
        )


@dataclass
class RouteResult:
    """Result of a routing decision."""
    project: Optional[ProjectEntry]
    score: float
    reason: str
    latency_ms: float = 0.0
    fallback: bool = False
    
    @property
    def success(self) -> bool:
        return self.project is not None


class FastEmbedder:
    """
    Fast local embedding using sentence-transformers.
    
    Falls back to TF-IDF-like hashing if sentence-transformers unavailable.
    """
    
    def __init__(self, dimension: int = EMBEDDING_DIM):
        self.dimension = dimension
        self._model = None
        self._use_fallback = False
        
    def initialize(self) -> None:
        """Initialize the embedding model."""
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Using sentence-transformers for embeddings")
        except ImportError:
            logger.warning("sentence-transformers not available, using hash-based fallback")
            self._use_fallback = True
    
    def embed(self, text: str) -> np.ndarray:
        """Embed a single text. Fast, synchronous."""
        if self._model is not None:
            return self._model.encode(text, normalize_embeddings=True)
        else:
            return self._hash_embed(text)
    
    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Embed multiple texts. Returns (N, dim) array."""
        if self._model is not None:
            return self._model.encode(texts, normalize_embeddings=True)
        else:
            return np.array([self._hash_embed(t) for t in texts], dtype=np.float32)
    
    def _hash_embed(self, text: str) -> np.ndarray:
        """
        Hash-based embedding fallback.
        Uses character n-grams hashed to vector positions.
        Fast but less semantic than neural embeddings.
        """
        vec = np.zeros(self.dimension, dtype=np.float32)
        text = text.lower()
        
        # Character trigrams
        for i in range(len(text) - 2):
            ngram = text[i:i+3]
            h = int(hashlib.md5(ngram.encode()).hexdigest(), 16)
            pos = h % self.dimension
            vec[pos] += 1.0
        
        # Word unigrams with higher weight
        for word in text.split():
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            pos = h % self.dimension
            vec[pos] += 2.0
        
        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        
        return vec


class FastProjectRouter:
    """
    Fast distributed project router.
    
    - Pre-computes embeddings at startup
    - Routes in sub-millisecond time using numpy
    - Syncs with other nodes via gossip
    """
    
    def __init__(
        self,
        node_id: str = None,
        registry_path: Optional[Path] = None,
        cache_path: Optional[Path] = None
    ):
        self.node_id = node_id or os.uname().nodename
        self.registry_path = registry_path or REGISTRY_PATH
        self.cache_path = cache_path or EMBEDDING_CACHE_PATH
        
        # Routing table: model_path -> ProjectEntry
        self.projects: Dict[str, ProjectEntry] = {}
        
        # Pre-computed embedding matrix for fast similarity
        self._project_paths: List[str] = []  # Ordered list of paths
        self._embedding_matrix: Optional[np.ndarray] = None  # (N, dim) matrix
        
        # Indexes for fast lookup
        self._domain_index: Dict[str, List[str]] = {}  # domain -> [paths]
        self._topic_index: Dict[str, List[str]] = {}   # topic -> [paths]
        self._capability_index: Dict[str, List[str]] = {}  # cap -> [paths]
        
        # Keyword boost vectors (pre-computed)
        self._domain_keywords: Dict[str, List[str]] = {
            "animals/camelids": ["llama", "alpaca", "camelid", "fiber", "husbandry", "breeding", "shearing"],
            "fishing": ["fish", "fishing", "tackle", "lure", "bass", "trout", "rod", "reel", "bait"],
            "healthcare": ["medical", "health", "doctor", "patient", "diagnosis", "treatment", "clinical", "symptom"],
            "legal": ["legal", "law", "attorney", "contract", "court", "liability", "lawsuit"],
            "finance": ["finance", "money", "investment", "trading", "stock", "portfolio", "market"],
            "coding": ["code", "programming", "software", "developer", "api", "function", "debug", "python"],
            "infrastructure": ["config", "discovery", "deploy", "server", "devops", "kubernetes"]
        }
        
        self._embedder: Optional[FastEmbedder] = None
        self._default_project: Optional[ProjectEntry] = None
        self._initialized = False
        
        # Gossip integration
        self._pending_updates: List[Dict] = []
        self._last_sync = 0.0
    
    def initialize(self) -> None:
        """Initialize router - load registry, compute embeddings."""
        if self._initialized:
            return
        
        start = time.perf_counter()
        
        # Initialize embedder
        self._embedder = FastEmbedder()
        self._embedder.initialize()
        
        # Load registry
        self._load_registry()
        
        # Load or compute embeddings
        if self._try_load_embedding_cache():
            logger.info("Loaded embeddings from cache")
        else:
            self._compute_embeddings()
            self._save_embedding_cache()
        
        # Build matrix for fast similarity
        self._build_embedding_matrix()
        
        elapsed = (time.perf_counter() - start) * 1000
        self._initialized = True
        logger.info(f"FastProjectRouter initialized in {elapsed:.1f}ms with {len(self.projects)} projects")
    
    async def initialize_from_api(self, llamafarm_url: str = LLAMAFARM_BASE) -> None:
        """
        Initialize router from LlamaFarm API instead of filesystem.
        
        This is the preferred method for distributed scenarios.
        """
        if self._initialized:
            return
        
        start = time.perf_counter()
        
        # Initialize embedder
        self._embedder = FastEmbedder()
        self._embedder.initialize()
        
        # Load from API
        await self._load_from_api(llamafarm_url)
        
        # Load or compute embeddings
        if self._try_load_embedding_cache():
            logger.info("Loaded embeddings from cache")
        else:
            self._compute_embeddings()
            self._save_embedding_cache()
        
        # Build matrix for fast similarity
        self._build_embedding_matrix()
        
        elapsed = (time.perf_counter() - start) * 1000
        self._initialized = True
        logger.info(f"FastProjectRouter initialized from API in {elapsed:.1f}ms with {len(self.projects)} projects")
    
    async def _load_from_api(self, llamafarm_url: str) -> None:
        """Load project registry from LlamaFarm API."""
        from ..discovery.api_discovery import APIDiscovery
        
        try:
            discovery = APIDiscovery(llamafarm_url, node_id=self.node_id)
            discovered = await discovery.discover()
            
            for disc_proj in discovered:
                # Skip test projects
                if disc_proj.namespace.startswith("test-"):
                    continue
                
                entry = ProjectEntry(
                    namespace=disc_proj.namespace,
                    name=disc_proj.name,
                    domain=disc_proj.domain,
                    capabilities=disc_proj.capabilities,
                    topics=disc_proj.topics,
                    description=disc_proj.description,
                    models=disc_proj.models,
                    nodes=[disc_proj.node]
                )
                
                self.projects[entry.model_path] = entry
                
                # Build indexes
                if entry.domain not in self._domain_index:
                    self._domain_index[entry.domain] = []
                self._domain_index[entry.domain].append(entry.model_path)
                
                for topic in entry.topics:
                    topic_lower = topic.lower()
                    if topic_lower not in self._topic_index:
                        self._topic_index[topic_lower] = []
                    self._topic_index[topic_lower].append(entry.model_path)
                
                for cap in entry.capabilities:
                    if cap not in self._capability_index:
                        self._capability_index[cap] = []
                    self._capability_index[cap].append(entry.model_path)
            
            # Set default
            if "default/default-project" in self.projects:
                self._default_project = self.projects["default/default-project"]
            elif self._domain_index.get("general"):
                path = self._domain_index["general"][0]
                self._default_project = self.projects[path]
            elif self.projects:
                self._default_project = list(self.projects.values())[0]
            
            logger.info(f"Loaded {len(self.projects)} projects from API")
            
        except Exception as e:
            logger.error(f"Failed to load from API: {e}, falling back to registry")
            self._load_registry()
    
    def _load_registry(self) -> None:
        """Load project registry from disk."""
        if not self.registry_path.exists():
            logger.warning(f"Registry not found: {self.registry_path}")
            return
        
        with open(self.registry_path) as f:
            index = json.load(f)
        
        projects_dir = self.registry_path.parent
        
        for proj_info in index.get("projects", []):
            proj_path = projects_dir / proj_info["path"]
            if not proj_path.exists():
                continue
            
            with open(proj_path) as f:
                proj_data = json.load(f)
            
            # Skip test projects
            ns = proj_data.get("namespace", "default")
            if ns.startswith("test-"):
                continue
            
            entry = ProjectEntry(
                namespace=ns,
                name=proj_data.get("name", "unknown"),
                domain=proj_data.get("domain", "general"),
                capabilities=proj_data.get("capabilities", ["chat"]),
                topics=proj_data.get("topics", []),
                description=proj_data.get("description", ""),
                models=proj_data.get("models", ["default"]),
                nodes=proj_data.get("nodes", [self.node_id])
            )
            
            self.projects[entry.model_path] = entry
            
            # Build indexes
            if entry.domain not in self._domain_index:
                self._domain_index[entry.domain] = []
            self._domain_index[entry.domain].append(entry.model_path)
            
            for topic in entry.topics:
                topic_lower = topic.lower()
                if topic_lower not in self._topic_index:
                    self._topic_index[topic_lower] = []
                self._topic_index[topic_lower].append(entry.model_path)
            
            for cap in entry.capabilities:
                if cap not in self._capability_index:
                    self._capability_index[cap] = []
                self._capability_index[cap].append(entry.model_path)
        
        # Set default
        if "default/default-project" in self.projects:
            self._default_project = self.projects["default/default-project"]
        elif self._domain_index.get("general"):
            path = self._domain_index["general"][0]
            self._default_project = self.projects[path]
        elif self.projects:
            self._default_project = list(self.projects.values())[0]
    
    def _compute_embeddings(self) -> None:
        """Compute embeddings for all projects."""
        logger.info("Computing project embeddings...")
        
        for path, project in self.projects.items():
            # Build text to embed: combine domain, topics, description
            text_parts = [
                project.domain,
                " ".join(project.topics),
                project.description[:500] if project.description else "",
                project.name.replace("-", " ").replace("_", " ")
            ]
            text = " ".join(text_parts)
            
            project.embedding = self._embedder.embed(text)
    
    def _build_embedding_matrix(self) -> None:
        """Build numpy matrix for fast batch similarity."""
        self._project_paths = list(self.projects.keys())
        
        embeddings = []
        for path in self._project_paths:
            project = self.projects[path]
            if project.embedding is not None:
                embeddings.append(project.embedding)
            else:
                embeddings.append(np.zeros(self._embedder.dimension, dtype=np.float32))
        
        if embeddings:
            self._embedding_matrix = np.vstack(embeddings)
        else:
            self._embedding_matrix = np.zeros((0, self._embedder.dimension), dtype=np.float32)
    
    def _try_load_embedding_cache(self) -> bool:
        """Try to load pre-computed embeddings from cache."""
        if not self.cache_path.exists():
            return False
        
        try:
            data = np.load(self.cache_path, allow_pickle=True)
            cache_paths = data["paths"].tolist()
            cache_embeddings = data["embeddings"]
            
            # Check if cache matches current projects
            current_paths = set(self.projects.keys())
            cache_paths_set = set(cache_paths)
            
            if current_paths != cache_paths_set:
                logger.info("Cache outdated, will recompute embeddings")
                return False
            
            # Apply cached embeddings
            for i, path in enumerate(cache_paths):
                if path in self.projects:
                    self.projects[path].embedding = cache_embeddings[i]
            
            return True
        except Exception as e:
            logger.warning(f"Failed to load embedding cache: {e}")
            return False
    
    def _save_embedding_cache(self) -> None:
        """Save embeddings to cache."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            paths = list(self.projects.keys())
            embeddings = np.array([
                self.projects[p].embedding for p in paths
            ], dtype=np.float32)
            
            np.savez(self.cache_path, paths=np.array(paths), embeddings=embeddings)
            logger.info(f"Saved embedding cache to {self.cache_path}")
        except Exception as e:
            logger.warning(f"Failed to save embedding cache: {e}")
    
    def route(self, model: str, messages: Optional[List[Dict]] = None) -> RouteResult:
        """
        Route a request. FAST - no LLM calls.
        
        Args:
            model: Model identifier or "auto"/"default" for semantic routing
            messages: Chat messages for content-based routing
        
        Returns:
            RouteResult with selected project
        """
        if not self._initialized:
            self.initialize()
        
        start = time.perf_counter()
        
        # 1. Check explicit model path
        if "/" in model and model in self.projects:
            elapsed = (time.perf_counter() - start) * 1000
            return RouteResult(
                project=self.projects[model],
                score=1.0,
                reason="Explicit model path",
                latency_ms=elapsed
            )
        
        # 2. Check project name only
        for path, project in self.projects.items():
            if project.name == model:
                elapsed = (time.perf_counter() - start) * 1000
                return RouteResult(
                    project=project,
                    score=0.95,
                    reason=f"Project name match ({project.namespace})",
                    latency_ms=elapsed
                )
        
        # 3. Content-based semantic routing
        if messages and model in ("auto", "default", ""):
            return self._route_by_content(messages, start)
        
        # 4. Fallback
        elapsed = (time.perf_counter() - start) * 1000
        return RouteResult(
            project=self._default_project,
            score=0.0,
            reason=f"Fallback (no match for: {model})",
            latency_ms=elapsed,
            fallback=True
        )
    
    def _route_by_content(self, messages: List[Dict], start: float) -> RouteResult:
        """
        Fast content-based routing using pre-computed embeddings.
        
        1. Extract user message
        2. Quick keyword check for domain boost
        3. Embed prompt
        4. Cosine similarity against all projects
        5. Return best match
        """
        # Extract last user message
        content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "").lower()
                break
        
        if not content:
            elapsed = (time.perf_counter() - start) * 1000
            return RouteResult(
                project=self._default_project,
                score=0.0,
                reason="No user content",
                latency_ms=elapsed,
                fallback=True
            )
        
        # Quick keyword domain detection (very fast)
        domain_scores: Dict[str, float] = {}
        for domain, keywords in self._domain_keywords.items():
            score = sum(1.0 for kw in keywords if kw in content)
            if score > 0:
                domain_scores[domain] = score
        
        # Embed the prompt
        prompt_embedding = self._embedder.embed(content)
        
        # Compute similarity against all projects (fast matrix multiply)
        if self._embedding_matrix is not None and len(self._embedding_matrix) > 0:
            similarities = self._embedding_matrix @ prompt_embedding
        else:
            similarities = np.array([])
        
        # Boost scores for keyword-matched domains
        boosted_scores = similarities.copy()
        for i, path in enumerate(self._project_paths):
            project = self.projects[path]
            if project.domain in domain_scores:
                boosted_scores[i] += domain_scores[project.domain] * 0.1
        
        # Find best match
        if len(boosted_scores) > 0:
            best_idx = np.argmax(boosted_scores)
            best_score = float(boosted_scores[best_idx])
            best_path = self._project_paths[best_idx]
            best_project = self.projects[best_path]
            
            # Determine reason
            if best_project.domain in domain_scores:
                reason = f"Domain match ({best_project.domain}) + semantic"
            else:
                reason = "Semantic similarity"
            
            elapsed = (time.perf_counter() - start) * 1000
            return RouteResult(
                project=best_project,
                score=min(best_score, 1.0),
                reason=reason,
                latency_ms=elapsed,
                fallback=best_score < 0.3
            )
        
        elapsed = (time.perf_counter() - start) * 1000
        return RouteResult(
            project=self._default_project,
            score=0.0,
            reason="No matches",
            latency_ms=elapsed,
            fallback=True
        )
    
    # ============ Gossip Integration ============
    
    def handle_route_update(self, update: Dict) -> None:
        """
        Handle a ROUTE_UPDATE from gossip.
        
        Update format:
        {
            "type": "route_update",
            "action": "add" | "update" | "remove",
            "project": { ... ProjectEntry data ... },
            "from_node": "node-id",
            "timestamp": 1234567890.123
        }
        """
        action = update.get("action")
        project_data = update.get("project", {})
        from_node = update.get("from_node")
        
        if action == "remove":
            path = f"{project_data.get('namespace')}/{project_data.get('name')}"
            if path in self.projects:
                del self.projects[path]
                self._rebuild_indexes()
                logger.info(f"Removed project {path} via gossip from {from_node}")
        
        elif action in ("add", "update"):
            entry = ProjectEntry.from_dict(project_data)
            
            # Compute embedding if not provided
            if entry.embedding is None and self._embedder:
                text = f"{entry.domain} {' '.join(entry.topics)} {entry.description}"
                entry.embedding = self._embedder.embed(text)
            
            # Update or add
            existing = self.projects.get(entry.model_path)
            if existing:
                # Merge nodes list
                all_nodes = set(existing.nodes) | set(entry.nodes)
                entry.nodes = list(all_nodes)
            
            self.projects[entry.model_path] = entry
            self._rebuild_indexes()
            logger.info(f"Updated project {entry.model_path} via gossip from {from_node}")
    
    def build_route_update(self, project: ProjectEntry, action: str = "update") -> Dict:
        """Build a ROUTE_UPDATE message for gossip."""
        return {
            "type": "route_update",
            "action": action,
            "project": project.to_dict(),
            "from_node": self.node_id,
            "timestamp": time.time()
        }
    
    def _rebuild_indexes(self) -> None:
        """Rebuild all indexes after an update."""
        self._domain_index.clear()
        self._topic_index.clear()
        self._capability_index.clear()
        
        for path, project in self.projects.items():
            if project.domain not in self._domain_index:
                self._domain_index[project.domain] = []
            self._domain_index[project.domain].append(path)
            
            for topic in project.topics:
                topic_lower = topic.lower()
                if topic_lower not in self._topic_index:
                    self._topic_index[topic_lower] = []
                self._topic_index[topic_lower].append(path)
            
            for cap in project.capabilities:
                if cap not in self._capability_index:
                    self._capability_index[cap] = []
                self._capability_index[cap].append(path)
        
        self._build_embedding_matrix()
    
    # ============ Query Methods ============
    
    def get_project(self, model_path: str) -> Optional[ProjectEntry]:
        """Get a project by model path."""
        if not self._initialized:
            self.initialize()
        return self.projects.get(model_path)
    
    def list_projects(
        self,
        domain: Optional[str] = None,
        capability: Optional[str] = None
    ) -> List[ProjectEntry]:
        """List projects with optional filters."""
        if not self._initialized:
            self.initialize()
        
        projects = list(self.projects.values())
        
        if domain:
            projects = [p for p in projects if p.domain == domain]
        if capability:
            projects = [p for p in projects if capability in p.capabilities]
        
        return projects
    
    def get_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        if not self._initialized:
            self.initialize()
        
        return {
            "total_projects": len(self.projects),
            "domains": {d: len(ps) for d, ps in self._domain_index.items()},
            "capabilities": {c: len(ps) for c, ps in self._capability_index.items()},
            "topics_count": len(self._topic_index),
            "embedding_dim": self._embedder.dimension if self._embedder else 0,
            "default_project": self._default_project.model_path if self._default_project else None,
            "node_id": self.node_id
        }
    
    def get_llamafarm_url(self, project: ProjectEntry, endpoint: str = "chat/completions") -> str:
        """Get the LlamaFarm API URL for a project."""
        return f"{LLAMAFARM_BASE}/v1/projects/{project.namespace}/{project.name}/{endpoint}"


# ============ Singleton ============

_router: Optional[FastProjectRouter] = None


def get_fast_router() -> FastProjectRouter:
    """Get or create the singleton fast router."""
    global _router
    if _router is None:
        _router = FastProjectRouter()
        _router.initialize()
    return _router
