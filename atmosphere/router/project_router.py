"""
LlamaFarm Project Router

Routes requests to the appropriate LlamaFarm project based on:
1. Explicit model path (e.g., "default/llama-expert-14")
2. Domain matching (e.g., "llama" → animals/camelids projects)
3. Capability matching (e.g., needs RAG → RAG-enabled projects)
4. Topic/keyword matching

Uses API-based discovery for finding projects across the mesh.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Registry path (fallback for file-based loading)
REGISTRY_PATH = Path.home() / ".llamafarm" / "atmosphere" / "projects" / "index.json"

# LlamaFarm API base
LLAMAFARM_BASE = "http://localhost:14345"


@dataclass
class Project:
    """A discovered LlamaFarm project."""
    namespace: str
    name: str
    domain: str
    capabilities: List[str]
    topics: List[str] = field(default_factory=list)
    description: str = ""
    models: List[str] = field(default_factory=list)
    complexity: str = "simple"
    nodes: List[str] = field(default_factory=list)
    
    @property
    def model_path(self) -> str:
        """Full model path for OpenAI-compatible routing."""
        return f"{self.namespace}/{self.name}"
    
    @property
    def has_rag(self) -> bool:
        return "rag" in self.capabilities
    
    @property
    def has_tools(self) -> bool:
        return "tools" in self.capabilities


@dataclass
class RouteDecision:
    """Result of routing decision."""
    project: Optional[Project]
    score: float
    reason: str
    fallback: bool = False
    
    @property
    def success(self) -> bool:
        return self.project is not None


class ProjectRouter:
    """
    Routes requests to LlamaFarm projects.
    
    Usage:
        router = ProjectRouter()
        router.load_registry()
        
        # Explicit routing
        decision = router.route("default/llama-expert-14", messages)
        
        # Implicit routing (semantic)
        decision = router.route_by_content(messages)
    """
    
    def __init__(self, registry_path: Optional[Path] = None):
        self.registry_path = registry_path or REGISTRY_PATH
        self.projects: Dict[str, Project] = {}  # model_path -> Project
        self.domain_index: Dict[str, List[Project]] = {}  # domain -> Projects
        self.topic_index: Dict[str, List[Project]] = {}  # topic -> Projects
        self.capability_index: Dict[str, List[Project]] = {}  # capability -> Projects
        self._loaded = False
        self._default_project: Optional[Project] = None
    
    def load_registry(self) -> bool:
        """Load the project registry from disk."""
        if not self.registry_path.exists():
            logger.warning(f"Registry not found: {self.registry_path}")
            return False
        
        try:
            with open(self.registry_path) as f:
                index = json.load(f)
            
            projects_dir = self.registry_path.parent
            
            for proj_info in index.get("projects", []):
                # Load full project metadata
                proj_path = projects_dir / proj_info["path"]
                if not proj_path.exists():
                    continue
                
                with open(proj_path) as f:
                    proj_data = json.load(f)
                
                project = Project(
                    namespace=proj_data.get("namespace", "default"),
                    name=proj_data.get("name", "unknown"),
                    domain=proj_data.get("domain", "general"),
                    capabilities=proj_data.get("capabilities", ["chat"]),
                    topics=proj_data.get("topics", []),
                    description=proj_data.get("description", ""),
                    models=proj_data.get("models", ["default"]),
                    complexity=proj_data.get("complexity", "simple"),
                    nodes=proj_data.get("nodes", [])
                )
                
                # Skip test projects
                if project.namespace.startswith("test-"):
                    continue
                
                # Index by model path
                self.projects[project.model_path] = project
                
                # Index by domain
                if project.domain not in self.domain_index:
                    self.domain_index[project.domain] = []
                self.domain_index[project.domain].append(project)
                
                # Index by topics
                for topic in project.topics:
                    topic_lower = topic.lower()
                    if topic_lower not in self.topic_index:
                        self.topic_index[topic_lower] = []
                    self.topic_index[topic_lower].append(project)
                
                # Index by capabilities
                for cap in project.capabilities:
                    if cap not in self.capability_index:
                        self.capability_index[cap] = []
                    self.capability_index[cap].append(project)
            
            # Set default project (prefer default/default-project or first general project)
            if "default/default-project" in self.projects:
                self._default_project = self.projects["default/default-project"]
            elif self.domain_index.get("general"):
                self._default_project = self.domain_index["general"][0]
            elif self.projects:
                self._default_project = list(self.projects.values())[0]
            
            self._loaded = True
            logger.info(f"Loaded {len(self.projects)} projects from registry")
            logger.info(f"Domains: {list(self.domain_index.keys())}")
            logger.info(f"Topics: {list(self.topic_index.keys())[:10]}...")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load registry: {e}")
            return False
    
    async def load_from_api(self, llamafarm_url: str = LLAMAFARM_BASE) -> bool:
        """
        Load projects from LlamaFarm API instead of filesystem.
        
        This is the preferred method for distributed/networked scenarios.
        """
        from ..discovery.api_discovery import APIDiscovery
        
        try:
            discovery = APIDiscovery(llamafarm_url)
            discovered = await discovery.discover()
            
            # Clear existing indices
            self.projects.clear()
            self.domain_index.clear()
            self.topic_index.clear()
            self.capability_index.clear()
            
            for disc_proj in discovered:
                # Skip test projects
                if disc_proj.namespace.startswith("test-"):
                    continue
                
                project = Project(
                    namespace=disc_proj.namespace,
                    name=disc_proj.name,
                    domain=disc_proj.domain,
                    capabilities=disc_proj.capabilities,
                    topics=disc_proj.topics,
                    description=disc_proj.description,
                    models=disc_proj.models,
                    complexity="rag-enabled" if "rag" in disc_proj.capabilities else "simple",
                    nodes=[disc_proj.node]
                )
                
                # Index by model path
                self.projects[project.model_path] = project
                
                # Index by domain
                if project.domain not in self.domain_index:
                    self.domain_index[project.domain] = []
                self.domain_index[project.domain].append(project)
                
                # Index by topics
                for topic in project.topics:
                    topic_lower = topic.lower()
                    if topic_lower not in self.topic_index:
                        self.topic_index[topic_lower] = []
                    self.topic_index[topic_lower].append(project)
                
                # Index by capabilities
                for cap in project.capabilities:
                    if cap not in self.capability_index:
                        self.capability_index[cap] = []
                    self.capability_index[cap].append(project)
            
            # Set default project
            if "default/default-project" in self.projects:
                self._default_project = self.projects["default/default-project"]
            elif self.domain_index.get("general"):
                self._default_project = self.domain_index["general"][0]
            elif self.projects:
                self._default_project = list(self.projects.values())[0]
            
            self._loaded = True
            logger.info(f"Loaded {len(self.projects)} projects from API")
            logger.info(f"Domains: {list(self.domain_index.keys())}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load from API: {e}")
            # Fall back to file-based loading
            return self.load_registry()
    
    def route(self, model: str, messages: Optional[List[Dict]] = None) -> RouteDecision:
        """
        Route a request by model path.
        
        Args:
            model: Model identifier (e.g., "default/llama-expert-14", "llama-expert-14", "default")
            messages: Optional messages for content-based fallback
            
        Returns:
            RouteDecision with the selected project
        """
        if not self._loaded:
            self.load_registry()
        
        # Check for explicit model path (namespace/name)
        if "/" in model:
            if model in self.projects:
                return RouteDecision(
                    project=self.projects[model],
                    score=1.0,
                    reason="Explicit model path match"
                )
        
        # Check for project name only (search all namespaces)
        for path, project in self.projects.items():
            if project.name == model:
                return RouteDecision(
                    project=project,
                    score=0.9,
                    reason=f"Project name match ({project.namespace})"
                )
        
        # If messages provided, try content-based routing
        if messages:
            return self.route_by_content(messages)
        
        # Fall back to default
        return self._get_fallback(f"No match for model: {model}")
    
    def route_by_content(self, messages: List[Dict]) -> RouteDecision:
        """
        Route based on message content (semantic routing).
        
        Analyzes the last user message for:
        - Domain keywords
        - Topic keywords
        - Required capabilities
        """
        if not self._loaded:
            self.load_registry()
        
        # Extract content to analyze
        content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "").lower()
                break
        
        if not content:
            return self._get_fallback("No user content to analyze")
        
        scores: List[Tuple[Project, float, str]] = []
        
        # Score by topic matching
        for topic, projects in self.topic_index.items():
            if topic in content:
                for project in projects:
                    scores.append((project, 0.8, f"Topic match: {topic}"))
        
        # Score by domain keywords
        domain_keywords = {
            "animals/camelids": ["llama", "alpaca", "camelid", "fiber", "husbandry", "breeding"],
            "fishing": ["fish", "fishing", "tackle", "lure", "bass", "trout", "rod", "reel"],
            "healthcare": ["medical", "health", "doctor", "patient", "diagnosis", "treatment", "clinical"],
            "legal": ["legal", "law", "attorney", "contract", "court", "liability"],
            "finance": ["finance", "money", "investment", "trading", "stock", "portfolio"],
            "coding": ["code", "programming", "software", "developer", "api", "function", "debug"],
            "infrastructure": ["config", "discovery", "parsing", "deploy", "server"]
        }
        
        for domain, keywords in domain_keywords.items():
            for keyword in keywords:
                if keyword in content:
                    for project in self.domain_index.get(domain, []):
                        scores.append((project, 0.7, f"Domain keyword: {keyword}"))
        
        # Check for capability requirements
        needs_rag = any(word in content for word in ["document", "search", "knowledge", "retrieve", "find in"])
        needs_tools = any(word in content for word in ["calculate", "run", "execute", "tool", "action"])
        
        if needs_rag:
            for project in self.capability_index.get("rag", []):
                scores.append((project, 0.6, "Requires RAG capability"))
        
        if needs_tools:
            for project in self.capability_index.get("tools", []):
                scores.append((project, 0.6, "Requires tools capability"))
        
        # Aggregate scores per project
        project_scores: Dict[str, Tuple[float, List[str]]] = {}
        for project, score, reason in scores:
            path = project.model_path
            if path not in project_scores:
                project_scores[path] = (0.0, [])
            current_score, reasons = project_scores[path]
            project_scores[path] = (current_score + score, reasons + [reason])
        
        # Find best match
        if project_scores:
            best_path = max(project_scores.keys(), key=lambda p: project_scores[p][0])
            best_score, reasons = project_scores[best_path]
            return RouteDecision(
                project=self.projects[best_path],
                score=min(best_score, 1.0),  # Cap at 1.0
                reason="; ".join(set(reasons))
            )
        
        return self._get_fallback("No content match found")
    
    def _get_fallback(self, reason: str) -> RouteDecision:
        """Return the default project as fallback."""
        return RouteDecision(
            project=self._default_project,
            score=0.0,
            reason=reason,
            fallback=True
        )
    
    def get_project(self, model_path: str) -> Optional[Project]:
        """Get a project by model path."""
        if not self._loaded:
            self.load_registry()
        return self.projects.get(model_path)
    
    def list_projects(self, domain: Optional[str] = None, capability: Optional[str] = None) -> List[Project]:
        """List projects, optionally filtered."""
        if not self._loaded:
            self.load_registry()
        
        projects = list(self.projects.values())
        
        if domain:
            projects = [p for p in projects if p.domain == domain]
        
        if capability:
            projects = [p for p in projects if capability in p.capabilities]
        
        return projects
    
    def get_llamafarm_url(self, project: Project, endpoint: str = "chat/completions") -> str:
        """Get the LlamaFarm API URL for a project."""
        return f"{LLAMAFARM_BASE}/v1/projects/{project.namespace}/{project.name}/{endpoint}"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        if not self._loaded:
            self.load_registry()
        
        return {
            "total_projects": len(self.projects),
            "domains": {d: len(ps) for d, ps in self.domain_index.items()},
            "capabilities": {c: len(ps) for c, ps in self.capability_index.items()},
            "topics_count": len(self.topic_index),
            "default_project": self._default_project.model_path if self._default_project else None
        }


# Singleton instance
_router: Optional[ProjectRouter] = None


def get_project_router() -> ProjectRouter:
    """Get or create the singleton router instance."""
    global _router
    if _router is None:
        _router = ProjectRouter()
        _router.load_registry()
    return _router
