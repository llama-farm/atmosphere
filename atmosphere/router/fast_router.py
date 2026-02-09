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
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
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
    hash_embedding: Optional[np.ndarray] = None  # Hash-based embedding for fallback
    keywords: Set[str] = field(default_factory=set)  # Extracted keywords for fallback
    
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
            "embedding": self.embedding.tolist() if self.embedding is not None else None,
            "keywords": list(self.keywords) if self.keywords else [],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectEntry":
        embedding = None
        if data.get("embedding"):
            embedding = np.array(data["embedding"], dtype=np.float32)
        keywords = set(data.get("keywords", []))
        return cls(
            namespace=data["namespace"],
            name=data["name"],
            domain=data.get("domain", "general"),
            capabilities=data.get("capabilities", ["chat"]),
            topics=data.get("topics", []),
            description=data.get("description", ""),
            models=data.get("models", ["default"]),
            nodes=data.get("nodes", []),
            embedding=embedding,
            keywords=keywords,
        )


class MatchTier(Enum):
    """Which cascade tier produced the match."""
    EXPLICIT = "explicit"      # Exact model path or name match
    EMBEDDING = "embedding"    # Neural embedding similarity
    HASH = "hash"              # Hash-based embedding similarity  
    KEYWORD = "keyword"        # Keyword overlap
    FALLBACK = "fallback"      # Default project


@dataclass
class RouteResult:
    """Result of a routing decision."""
    project: Optional[ProjectEntry]
    score: float
    reason: str
    latency_ms: float = 0.0
    fallback: bool = False
    tier: MatchTier = MatchTier.FALLBACK  # Which cascade tier matched
    
    @property
    def success(self) -> bool:
        return self.project is not None


class KeywordMatcher:
    """
    Keyword extractor and matcher for fallback routing.
    """
    
    STOPWORDS = frozenset([
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
        "been", "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "shall", "can",
        "this", "that", "these", "those", "i", "you", "he", "she", "it", "we",
        "they", "what", "which", "who", "whom", "how", "when", "where", "why",
        "all", "each", "every", "both", "few", "more", "most", "other", "some",
        "such", "no", "not", "only", "same", "so", "than", "too", "very", "just",
    ])
    
    @classmethod
    def extract(cls, text: str, max_keywords: int = 20) -> Set[str]:
        """Extract keywords from text."""
        if not text:
            return set()
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        keywords = [w for w in words if w not in cls.STOPWORDS]
        counts = Counter(keywords)
        return set(kw for kw, _ in counts.most_common(max_keywords))
    
    @classmethod
    def _simple_stem(cls, word: str) -> str:
        """Very simple stemming: strip common English suffixes."""
        for suffix in ('ing', 'tion', 'sion', 'ment', 'ness', 'ies', 'ous', 'ive', 'able', 'ible', 'ally', 'ful', 'less', 'ize', 'ise', 'ly', 'er', 'ed', 'es', 's'):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                return word[:-len(suffix)]
        return word
    
    @classmethod
    def match_score(cls, query_kw: Set[str], target_kw: Set[str]) -> float:
        """
        Query-coverage keyword match score with simple stemming.
        
        Measures what fraction of query keywords appear in the target,
        using both exact and stem-based matching.
        """
        if not query_kw or not target_kw:
            return 0.0
        
        # Build stem index for target
        target_stems = {cls._simple_stem(w) for w in target_kw}
        target_with_stems = target_kw | target_stems
        
        # Count matches (exact + stem)
        matches = 0
        for qw in query_kw:
            if qw in target_kw:
                matches += 1.0
            elif cls._simple_stem(qw) in target_stems:
                matches += 0.85  # Slightly lower confidence for stem match
        
        query_coverage = matches / len(query_kw)
        # Small Jaccard component for tie-breaking
        exact_intersection = len(query_kw & target_kw)
        jaccard = exact_intersection / len(query_kw | target_kw) if (query_kw | target_kw) else 0
        return 0.8 * query_coverage + 0.2 * jaccard


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
    
    @property
    def using_neural(self) -> bool:
        """Whether neural embeddings are available."""
        return self._model is not None
    
    def embed(self, text: str) -> np.ndarray:
        """Embed a single text. Fast, synchronous."""
        if self._model is not None:
            return self._model.encode(text, normalize_embeddings=True)
        else:
            return self._hash_embed(text)
    
    def embed_hash(self, text: str) -> np.ndarray:
        """Always use hash embedding (for fallback tier)."""
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
        # Note: Keys must match domain values returned by APIDiscovery
        self._domain_keywords: Dict[str, List[str]] = {
            "camelids": ["llama", "alpaca", "camelid", "fiber", "husbandry", "breeding", "shearing", "llamas", "alpacas"],
            "animals/camelids": ["llama", "alpaca", "camelid", "fiber", "husbandry", "breeding", "shearing", "llamas", "alpacas"],  # Legacy alias
            "fishing": ["fish", "fishing", "tackle", "lure", "bass", "trout", "rod", "reel", "bait"],
            "healthcare": ["medical", "health", "doctor", "patient", "diagnosis", "treatment", "clinical", "symptom"],
            "legal": ["legal", "law", "attorney", "contract", "court", "liability", "lawsuit"],
            "finance": ["finance", "money", "investment", "trading", "stock", "portfolio", "market"],
            "coding": ["code", "programming", "software", "developer", "api", "function", "debug", "python"],
            "infrastructure": ["config", "discovery", "deploy", "server", "devops", "kubernetes", "sre", "ops"]
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
            # ONLY discover projects from the 'discoverable' namespace
            discovered = await discovery.discover_namespace("discoverable")
            
            for disc_proj in discovered:
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
            
            # Set default - prefer atmosphere-universal or projects with "universal" in name
            if "discoverable/atmosphere-universal" in self.projects:
                self._default_project = self.projects["discoverable/atmosphere-universal"]
            else:
                # Find first project with "universal" or "atmosphere" in name
                for path, entry in self.projects.items():
                    if "universal" in entry.name.lower() or "atmosphere" in entry.name.lower():
                        self._default_project = entry
                        break
                else:
                    if self.projects:
                        self._default_project = list(self.projects.values())[0]
            
            logger.info(f"Loaded {len(self.projects)} projects from 'discoverable' namespace via API")
            print(f"[FAST_ROUTER] Default project set to: {self._default_project.model_path if self._default_project else 'None'}", flush=True)
            print(f"[FAST_ROUTER] Available projects: {list(self.projects.keys())}", flush=True)
            
        except Exception as e:
            logger.error(f"Failed to load from API: {e}")
            # In 'discoverable-only' mode, we don't fall back to local registry
            # as that might contain private projects.
            self.projects = {}
    
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
        
        # Set default - prefer atmosphere-universal or projects with "universal" in name
        if "discoverable/atmosphere-universal" in self.projects:
            self._default_project = self.projects["discoverable/atmosphere-universal"]
        else:
            # Find first project with "universal" or "atmosphere" in name
            for path, entry in self.projects.items():
                if "universal" in entry.name.lower() or "atmosphere" in entry.name.lower():
                    self._default_project = entry
                    break
            else:
                # Fallback chain
                if "default/default-project" in self.projects:
                    self._default_project = self.projects["default/default-project"]
                elif self._domain_index.get("general"):
                    path = self._domain_index["general"][0]
                    self._default_project = self.projects[path]
                elif self.projects:
                    self._default_project = list(self.projects.values())[0]
    
    def _compute_embeddings(self) -> None:
        """Compute embeddings and extract keywords for all projects."""
        logger.info("Computing project embeddings and keywords...")
        
        for path, project in self.projects.items():
            # Build text to embed: combine domain, topics, description
            text_parts = [
                project.domain,
                " ".join(project.topics),
                project.description[:500] if project.description else "",
                project.name.replace("-", " ").replace("_", " ")
            ]
            text = " ".join(text_parts)
            
            # Primary embedding (neural or hash depending on availability)
            project.embedding = self._embedder.embed(text)
            
            # Hash embedding (always computed for fallback tier)
            project.hash_embedding = self._embedder.embed_hash(text)
            
            # Extract keywords for keyword fallback tier
            project.keywords = KeywordMatcher.extract(text)
    
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
            
            # Load optional hash embeddings and keywords if present
            cache_hash_embeddings = data.get("hash_embeddings", None)
            cache_keywords = data.get("keywords", None)
            
            # Apply cached embeddings
            for i, path in enumerate(cache_paths):
                if path in self.projects:
                    self.projects[path].embedding = cache_embeddings[i]
                    # Also load hash embeddings if cached
                    if cache_hash_embeddings is not None:
                        self.projects[path].hash_embedding = cache_hash_embeddings[i]
                    # Also load keywords if cached
                    if cache_keywords is not None:
                        kw = cache_keywords[i]
                        self.projects[path].keywords = set(kw) if isinstance(kw, (list, np.ndarray)) else set()
            
            # If hash embeddings or keywords weren't cached, recompute them
            needs_recompute = cache_hash_embeddings is None or cache_keywords is None
            if needs_recompute:
                logger.info("Cache missing hash embeddings or keywords, computing...")
                self._compute_hash_and_keywords()
                self._save_embedding_cache()  # Save updated cache
            
            return True
        except Exception as e:
            logger.warning(f"Failed to load embedding cache: {e}")
            return False
    
    def _compute_hash_and_keywords(self) -> None:
        """Compute only hash embeddings and keywords (when primary embeddings from cache)."""
        for path, project in self.projects.items():
            # Build text to embed: combine domain, topics, description
            text_parts = [
                project.domain,
                " ".join(project.topics),
                project.description[:500] if project.description else "",
                project.name.replace("-", " ").replace("_", " ")
            ]
            text = " ".join(text_parts)
            
            # Hash embedding (always computed for fallback tier)
            if project.hash_embedding is None:
                project.hash_embedding = self._embedder.embed_hash(text)
            
            # Extract keywords for keyword fallback tier
            if not project.keywords:
                project.keywords = KeywordMatcher.extract(text)
    
    def _save_embedding_cache(self) -> None:
        """Save embeddings, hash embeddings, and keywords to cache."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            paths = list(self.projects.keys())
            embeddings = np.array([
                self.projects[p].embedding for p in paths
            ], dtype=np.float32)
            
            # Also save hash embeddings
            hash_embeddings = np.array([
                self.projects[p].hash_embedding if self.projects[p].hash_embedding is not None 
                else np.zeros(self._embedder.dimension, dtype=np.float32)
                for p in paths
            ], dtype=np.float32)
            
            # Save keywords as list of lists (numpy can't directly store sets)
            keywords = np.array([
                list(self.projects[p].keywords) if self.projects[p].keywords else []
                for p in paths
            ], dtype=object)
            
            np.savez(
                self.cache_path, 
                paths=np.array(paths), 
                embeddings=embeddings,
                hash_embeddings=hash_embeddings,
                keywords=keywords
            )
            logger.info(f"Saved embedding cache to {self.cache_path}")
        except Exception as e:
            logger.warning(f"Failed to save embedding cache: {e}")
    
    def route(self, model: str, messages: Optional[List[Dict]] = None) -> RouteResult:
        """
        Route a request using cascade. FAST - no LLM calls.
        
        Cascade order:
        1. EXPLICIT: Exact model path or project name match
        2. EMBEDDING: Neural/hash embedding similarity
        3. HASH: Hash-based fallback (if neural available)
        4. KEYWORD: Pure keyword matching
        5. FALLBACK: Default project
        
        Args:
            model: Model identifier or "auto"/"default" for semantic routing
            messages: Chat messages for content-based routing
        
        Returns:
            RouteResult with selected project and cascade tier
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
                latency_ms=elapsed,
                tier=MatchTier.EXPLICIT,
            )
        
        # 2. Check project name only
        for path, project in self.projects.items():
            if project.name == model:
                elapsed = (time.perf_counter() - start) * 1000
                return RouteResult(
                    project=project,
                    score=0.95,
                    reason=f"Project name match ({project.namespace})",
                    latency_ms=elapsed,
                    tier=MatchTier.EXPLICIT,
                )
        
        # 3. Content-based cascade routing
        if messages and model in ("auto", "default", ""):
            return self._route_by_content(messages, start)
        
        # 4. Fallback
        elapsed = (time.perf_counter() - start) * 1000
        return RouteResult(
            project=self._default_project,
            score=0.0,
            reason=f"Fallback (no match for: {model})",
            latency_ms=elapsed,
            fallback=True,
            tier=MatchTier.FALLBACK,
        )
    
    def _route_by_content(self, messages: List[Dict], start: float) -> RouteResult:
        """
        Fast content-based routing using 3-tier cascade.
        
        Cascade:
        1. EMBEDDING: Neural/hash embedding similarity (threshold: 0.5)
        2. HASH: Explicit hash-based similarity if neural used (threshold: 0.35)
        3. KEYWORD: Pure keyword matching (threshold: 0.2)
        4. FALLBACK: Default project with domain boost
        """
        # Thresholds for cascade tiers (lowered for hash-based embeddings)
        EMBEDDING_THRESHOLD = 0.15  # Hash embeddings produce lower similarities
        HASH_THRESHOLD = 0.10
        KEYWORD_THRESHOLD = 0.05
        
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
                fallback=True,
                tier=MatchTier.FALLBACK,
            )
        
        # Pre-compute all content features
        prompt_embedding = self._embedder.embed(content)
        prompt_hash_embedding = self._embedder.embed_hash(content)
        prompt_keywords = KeywordMatcher.extract(content)
        
        # Quick keyword domain detection for boosting
        domain_scores: Dict[str, float] = {}
        for domain, keywords in self._domain_keywords.items():
            score = sum(1.0 for kw in keywords if kw in content)
            if score > 0:
                domain_scores[domain] = score
        
        # === COMBINED SCORING: Embedding + Keyword ===
        # Instead of pure cascade, compute all scores and combine them.
        # This prevents low-confidence hash matches from overriding keyword matches.
        
        combined_scores: Dict[str, Dict] = {}
        
        # Tier 1: Embedding/Hash similarity
        if self._embedding_matrix is not None and len(self._embedding_matrix) > 0:
            similarities = self._embedding_matrix @ prompt_embedding
            for i, path in enumerate(self._project_paths):
                project = self.projects[path]
                emb_score = float(similarities[i])
                # Domain boost
                if project.domain in domain_scores:
                    emb_score += domain_scores[project.domain] * 0.1
                combined_scores[path] = {
                    "embedding": emb_score,
                    "keyword": 0.0,
                    "project": project,
                }
        
        # Tier 2: Hash match (if neural used in tier 1)
        if self._embedder.using_neural:
            for path, project in self.projects.items():
                if project.hash_embedding is not None:
                    score = float(np.dot(prompt_hash_embedding, project.hash_embedding))
                    if project.domain in domain_scores:
                        score += domain_scores[project.domain] * 0.1
                    if path not in combined_scores:
                        combined_scores[path] = {"embedding": 0.0, "keyword": 0.0, "project": project}
                    # Use hash as embedding fallback (take max)
                    combined_scores[path]["embedding"] = max(combined_scores[path]["embedding"], score)
        
        # Tier 3: Keyword match
        for path, project in self.projects.items():
            score = KeywordMatcher.match_score(prompt_keywords, project.keywords)
            if project.domain in domain_scores:
                score += domain_scores[project.domain] * 0.15
            if path not in combined_scores:
                combined_scores[path] = {"embedding": 0.0, "keyword": 0.0, "project": project}
            combined_scores[path]["keyword"] = score
        
        # Combine: weight keyword matching more heavily since hash embeddings are noisy
        # High-confidence embedding (>0.5) gets full weight; low-confidence blends with keywords
        best_combined_score = 0.0
        best_combined_project = None
        best_tier = MatchTier.FALLBACK
        best_reason = ""
        
        for path, scores in combined_scores.items():
            emb = scores["embedding"]
            kw = scores["keyword"]
            project = scores["project"]
            
            # If embedding is high-confidence, trust it
            if emb >= 0.5:
                total = emb
                tier = MatchTier.EMBEDDING if self._embedder.using_neural else MatchTier.HASH
                reason = f"{'Embedding' if self._embedder.using_neural else 'Hash'} match ({project.domain})"
            # Otherwise, blend embedding and keyword scores
            else:
                # Keywords get more weight when embedding is uncertain
                total = 0.4 * emb + 0.6 * kw
                if kw > emb:
                    tier = MatchTier.KEYWORD
                    reason = f"Keyword match ({project.domain})"
                else:
                    tier = MatchTier.HASH
                    reason = f"Hash+keyword blend ({project.domain})"
            
            if total > best_combined_score:
                best_combined_score = total
                best_combined_project = project
                best_tier = tier
                best_reason = reason
        
        if best_combined_project and best_combined_score >= KEYWORD_THRESHOLD:
            elapsed = (time.perf_counter() - start) * 1000
            return RouteResult(
                project=best_combined_project,
                score=min(best_combined_score, 1.0),
                reason=best_reason,
                latency_ms=elapsed,
                fallback=False,
                tier=best_tier,
            )
        
        # === TIER 4: Final Fallback ===
        # Use best from any tier, or domain-boosted default
        best_project = self._default_project
        best_reason = "Default fallback"
        
        # If we had domain matches, prefer a project from that domain
        if domain_scores:
            top_domain = max(domain_scores, key=domain_scores.get)
            if top_domain in self._domain_index:
                domain_path = self._domain_index[top_domain][0]
                best_project = self.projects[domain_path]
                best_reason = f"Domain fallback ({top_domain})"
        
        elapsed = (time.perf_counter() - start) * 1000
        return RouteResult(
            project=best_project,
            score=0.0,
            reason=best_reason,
            latency_ms=elapsed,
            fallback=True,
            tier=MatchTier.FALLBACK,
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
            
            # Build text for embeddings and keywords
            text = f"{entry.domain} {' '.join(entry.topics)} {entry.description}"
            
            # Compute embedding if not provided
            if entry.embedding is None and self._embedder:
                entry.embedding = self._embedder.embed(text)
            
            # Always compute hash embedding for fallback tier
            if entry.hash_embedding is None and self._embedder:
                entry.hash_embedding = self._embedder.embed_hash(text)
            
            # Extract keywords if not provided
            if not entry.keywords:
                entry.keywords = KeywordMatcher.extract(text)
            
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

    def test_cascade(self, content: str) -> Dict[str, Any]:
        """
        Test all cascade tiers for a given content.
        
        Useful for debugging and understanding routing decisions.
        
        Returns dict with results from each tier.
        """
        if not self._initialized:
            self.initialize()
        
        # Thresholds
        EMBEDDING_THRESHOLD = 0.5
        HASH_THRESHOLD = 0.35
        KEYWORD_THRESHOLD = 0.2
        
        content = content.lower()
        
        # Compute all features
        prompt_embedding = self._embedder.embed(content)
        prompt_hash_embedding = self._embedder.embed_hash(content)
        prompt_keywords = KeywordMatcher.extract(content)
        
        # Domain detection
        domain_scores: Dict[str, float] = {}
        for domain, keywords in self._domain_keywords.items():
            score = sum(1.0 for kw in keywords if kw in content)
            if score > 0:
                domain_scores[domain] = score
        
        results = {
            "content": content[:100] + "..." if len(content) > 100 else content,
            "keywords": list(prompt_keywords),
            "domain_boosts": domain_scores,
            "neural_available": self._embedder.using_neural,
            "tiers": {},
        }
        
        # Tier 1: Embedding
        if self._embedding_matrix is not None and len(self._embedding_matrix) > 0:
            similarities = self._embedding_matrix @ prompt_embedding
            boosted = similarities.copy()
            for i, path in enumerate(self._project_paths):
                if self.projects[path].domain in domain_scores:
                    boosted[i] += domain_scores[self.projects[path].domain] * 0.1
            
            best_idx = np.argmax(boosted)
            best_score = float(boosted[best_idx])
            best_project = self.projects[self._project_paths[best_idx]]
            
            results["tiers"]["embedding"] = {
                "score": best_score,
                "threshold": EMBEDDING_THRESHOLD,
                "passed": best_score >= EMBEDDING_THRESHOLD,
                "project": best_project.model_path,
                "domain": best_project.domain,
            }
        
        # Tier 2: Hash (separate computation)
        best_hash = {"score": 0.0, "project": None, "domain": None}
        for path, project in self.projects.items():
            if project.hash_embedding is not None:
                score = float(np.dot(prompt_hash_embedding, project.hash_embedding))
                if project.domain in domain_scores:
                    score += domain_scores[project.domain] * 0.1
                if score > best_hash["score"]:
                    best_hash = {"score": score, "project": path, "domain": project.domain}
        
        results["tiers"]["hash"] = {
            "score": best_hash["score"],
            "threshold": HASH_THRESHOLD,
            "passed": best_hash["score"] >= HASH_THRESHOLD,
            "project": best_hash["project"],
            "domain": best_hash["domain"],
        }
        
        # Tier 3: Keyword
        best_kw = {"score": 0.0, "project": None, "domain": None}
        for path, project in self.projects.items():
            score = KeywordMatcher.match_score(prompt_keywords, project.keywords)
            if project.domain in domain_scores:
                score += domain_scores[project.domain] * 0.15
            if score > best_kw["score"]:
                best_kw = {"score": score, "project": path, "domain": project.domain}
        
        results["tiers"]["keyword"] = {
            "score": best_kw["score"],
            "threshold": KEYWORD_THRESHOLD,
            "passed": best_kw["score"] >= KEYWORD_THRESHOLD,
            "project": best_kw["project"],
            "domain": best_kw["domain"],
        }
        
        # Final route result
        messages = [{"role": "user", "content": content}]
        final = self.route("auto", messages)
        results["final"] = {
            "tier": final.tier.value,
            "score": final.score,
            "project": final.project.model_path if final.project else None,
            "domain": final.project.domain if final.project else None,
            "reason": final.reason,
            "fallback": final.fallback,
        }
        
        return results


# ============ Singleton ============

_router: Optional[FastProjectRouter] = None


def get_fast_router() -> FastProjectRouter:
    """Get or create the singleton fast router, preferring API discovery."""
    global _router
    if _router is None:
        _router = FastProjectRouter()
        
        # Try sync API load first (preferred - gets live LlamaFarm projects)
        try:
            import httpx
            
            # Initialize embedder first
            _router._embedder = FastEmbedder()
            _router._embedder.initialize()
            
            resp = httpx.get(f"{LLAMAFARM_BASE}/v1/projects/discoverable", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                projects = data.get("projects", [])
                
                for proj in projects:
                    cfg = proj.get("config", {})
                    runtime = cfg.get("runtime", {})
                    models_cfg = runtime.get("models", [])
                    
                    # Get description from config or first model
                    description = cfg.get("description", "")
                    if not description and models_cfg:
                        description = models_cfg[0].get("description", "")
                    
                    entry = ProjectEntry(
                        namespace=proj.get("namespace", "discoverable"),
                        name=proj.get("name", "unknown"),
                        domain=cfg.get("domain", "general"),
                        capabilities=["chat", "llm"],
                        topics=[],
                        description=description,
                        models=[m.get("model", "default") for m in models_cfg] or ["default"],
                        nodes=[_router.node_id]
                    )
                    _router.projects[entry.model_path] = entry
                
                # Set default - prefer atmosphere-universal
                if "discoverable/atmosphere-universal" in _router.projects:
                    _router._default_project = _router.projects["discoverable/atmosphere-universal"]
                else:
                    for path, entry in _router.projects.items():
                        if "universal" in entry.name.lower() or "atmosphere" in entry.name.lower():
                            _router._default_project = entry
                            break
                    else:
                        if _router.projects:
                            _router._default_project = list(_router.projects.values())[0]
                
                # Compute embeddings for semantic routing
                _router._compute_embeddings()
                _router._build_embedding_matrix()
                
                _router._initialized = True
                print(f"[FAST_ROUTER] Loaded {len(_router.projects)} projects from API", flush=True)
                print(f"[FAST_ROUTER] Default: {_router._default_project.model_path if _router._default_project else 'None'}", flush=True)
                print(f"[FAST_ROUTER] Embedding matrix: {_router._embedding_matrix.shape if _router._embedding_matrix is not None else 'None'}", flush=True)
            else:
                raise Exception(f"API returned {resp.status_code}")
        except Exception as e:
            print(f"[FAST_ROUTER] API load failed ({e}), falling back to file registry", flush=True)
            _router.initialize()
    
    return _router
