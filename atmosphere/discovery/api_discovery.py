"""
API-based Project Discovery for Atmosphere

Discovers LlamaFarm projects using the API, not filesystem scanning.
This works across the network - each node can discover projects on remote nodes.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx

logger = logging.getLogger(__name__)

# Cache settings
CACHE_TTL_SECONDS = 300  # 5 minutes
CACHE_PATH = Path.home() / ".atmosphere" / "cache" / "projects.json"


@dataclass
class DiscoveredProject:
    """A project discovered via API."""
    namespace: str
    name: str
    provider: str
    models: List[str]
    domain: str = "general"
    capabilities: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    description: str = ""
    node: str = "local"  # Which node this is on
    
    @property
    def model_path(self) -> str:
        return f"{self.namespace}/{self.name}"
    
    def to_dict(self) -> dict:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "provider": self.provider,
            "models": self.models,
            "domain": self.domain,
            "capabilities": self.capabilities,
            "topics": self.topics,
            "description": self.description,
            "node": self.node,
        }


class APIDiscovery:
    """
    Discovers LlamaFarm projects via API.
    
    Usage:
        discovery = APIDiscovery("http://localhost:14345")
        projects = await discovery.discover()
    """
    
    def __init__(
        self,
        llamafarm_url: str = "http://localhost:14345",
        node_id: str = "local",
        cache_ttl: int = CACHE_TTL_SECONDS
    ):
        self.llamafarm_url = llamafarm_url.rstrip("/")
        self.node_id = node_id
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, DiscoveredProject] = {}
        self._cache_time: float = 0
        self._namespaces: Set[str] = set()
    
    async def discover(self, force_refresh: bool = False) -> List[DiscoveredProject]:
        """
        Discover all projects from the LlamaFarm API.
        
        Uses cache if valid, otherwise fetches fresh.
        """
        if not force_refresh and self._is_cache_valid():
            logger.debug("Using cached project discovery")
            return list(self._cache.values())
        
        logger.info(f"Discovering projects from {self.llamafarm_url}")
        
        projects = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First, discover namespaces
            namespaces = await self._discover_namespaces(client)
            
            # Then, discover projects in each namespace
            for ns in namespaces:
                ns_projects = await self._discover_namespace_projects(client, ns)
                projects.extend(ns_projects)
        
        # Update cache
        self._cache = {p.model_path: p for p in projects}
        self._cache_time = time.time()
        
        # Save to disk cache
        self._save_cache()
        
        logger.info(f"Discovered {len(projects)} projects in {len(namespaces)} namespaces")
        return projects
    
    async def _discover_namespaces(self, client: httpx.AsyncClient) -> List[str]:
        """Discover available namespaces."""
        # Known namespaces to check
        known = ["default", "atmosphere", "edge", "examples", "llamafarm"]
        found = []
        
        for ns in known:
            try:
                response = await client.get(f"{self.llamafarm_url}/v1/projects/{ns}")
                if response.status_code == 200:
                    found.append(ns)
            except Exception:
                pass
        
        self._namespaces = set(found)
        return found
    
    async def _discover_namespace_projects(
        self, client: httpx.AsyncClient, namespace: str
    ) -> List[DiscoveredProject]:
        """Discover all projects in a namespace."""
        projects = []
        
        try:
            response = await client.get(f"{self.llamafarm_url}/v1/projects/{namespace}")
            if response.status_code != 200:
                return projects
            
            data = response.json()
            
            for proj in data.get("projects", []):
                discovered = self._parse_project(proj)
                if discovered:
                    projects.append(discovered)
        
        except Exception as e:
            logger.error(f"Error discovering namespace {namespace}: {e}")
        
        return projects
    
    def _parse_project(self, proj_data: dict) -> Optional[DiscoveredProject]:
        """Parse project data from API response."""
        try:
            config = proj_data.get("config", {})
            namespace = proj_data.get("namespace", "default")
            name = proj_data.get("name", "unknown")
            
            # Skip invalid projects
            if proj_data.get("validation_error"):
                return None
            
            # Extract models
            runtime = config.get("runtime", {})
            models_config = runtime.get("models", [])
            models = [m.get("name", "default") for m in models_config if isinstance(m, dict)]
            
            # Get provider
            provider = "unknown"
            if models_config and isinstance(models_config[0], dict):
                provider = models_config[0].get("provider", "universal")
            
            # Detect domain from prompts
            domain = "general"
            capabilities = ["chat"]
            topics = []
            description = ""
            
            prompts = config.get("prompts", [])
            if prompts and isinstance(prompts[0], dict):
                messages = prompts[0].get("messages", [])
                for msg in messages:
                    if msg.get("role") == "system":
                        content = msg.get("content", "").lower()
                        domain, topics = self._extract_domain_and_topics(content)
                        description = self._extract_description(msg.get("content", ""))
                        break
            
            # Detect capabilities
            if config.get("rag", {}).get("databases"):
                capabilities.append("rag")
            if any(m.get("tools") for m in models_config if isinstance(m, dict)):
                capabilities.append("tools")
            if any(m.get("instructor_mode") for m in models_config if isinstance(m, dict)):
                capabilities.append("structured")
            
            return DiscoveredProject(
                namespace=namespace,
                name=name,
                provider=provider,
                models=models or ["default"],
                domain=domain,
                capabilities=capabilities,
                topics=topics,
                description=description,
                node=self.node_id,
            )
        
        except Exception as e:
            logger.warning(f"Failed to parse project: {e}")
            return None
    
    def _extract_domain_and_topics(self, content: str) -> tuple:
        """Extract domain and topics from system prompt."""
        domain = "general"
        topics = []
        
        # Domain detection
        domain_keywords = {
            "camelids": ["llama", "alpaca", "camelid", "fiber"],
            "fishing": ["fishing", "fish", "bass", "regulations"],
            "healthcare": ["medical", "health", "patient", "clinical"],
            "legal": ["legal", "law", "attorney", "court"],
            "finance": ["finance", "money", "investment", "trading"],
            "coding": ["code", "programming", "developer", "software"],
            "infrastructure": ["sre", "ops", "infrastructure", "deploy"],
        }
        
        for domain_name, keywords in domain_keywords.items():
            for kw in keywords:
                if kw in content:
                    domain = domain_name
                    topics.extend([k for k in keywords if k in content])
                    break
            if domain != "general":
                break
        
        return domain, list(set(topics))
    
    def _extract_description(self, content: str) -> str:
        """Extract first sentence as description."""
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                # First non-empty, non-header line
                if len(line) > 100:
                    return line[:100] + "..."
                return line
        return ""
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._cache:
            return False
        return (time.time() - self._cache_time) < self.cache_ttl
    
    def _save_cache(self):
        """Save cache to disk."""
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "timestamp": datetime.now().isoformat(),
                "node": self.node_id,
                "projects": [p.to_dict() for p in self._cache.values()]
            }
            with open(CACHE_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def _load_cache(self) -> bool:
        """Load cache from disk."""
        try:
            if not CACHE_PATH.exists():
                return False
            
            with open(CACHE_PATH) as f:
                data = json.load(f)
            
            # Check if cache is too old
            ts = datetime.fromisoformat(data.get("timestamp", "2000-01-01"))
            if (datetime.now() - ts).total_seconds() > self.cache_ttl:
                return False
            
            # Load projects
            for p in data.get("projects", []):
                proj = DiscoveredProject(
                    namespace=p["namespace"],
                    name=p["name"],
                    provider=p.get("provider", "universal"),
                    models=p.get("models", ["default"]),
                    domain=p.get("domain", "general"),
                    capabilities=p.get("capabilities", ["chat"]),
                    topics=p.get("topics", []),
                    description=p.get("description", ""),
                    node=p.get("node", "local"),
                )
                self._cache[proj.model_path] = proj
            
            self._cache_time = ts.timestamp()
            return True
        
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return False
    
    def get_project(self, model_path: str) -> Optional[DiscoveredProject]:
        """Get a specific project by model path."""
        return self._cache.get(model_path)
    
    def get_projects_by_domain(self, domain: str) -> List[DiscoveredProject]:
        """Get projects matching a domain."""
        return [p for p in self._cache.values() if p.domain == domain]
    
    def get_projects_by_capability(self, capability: str) -> List[DiscoveredProject]:
        """Get projects with a specific capability."""
        return [p for p in self._cache.values() if capability in p.capabilities]


# Global instance
_discovery: Optional[APIDiscovery] = None


def get_discovery(llamafarm_url: str = "http://localhost:14345") -> APIDiscovery:
    """Get or create the global discovery instance."""
    global _discovery
    if _discovery is None:
        _discovery = APIDiscovery(llamafarm_url)
    return _discovery


async def discover_projects() -> List[DiscoveredProject]:
    """Convenience function to discover projects."""
    discovery = get_discovery()
    return await discovery.discover()
