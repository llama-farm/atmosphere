"""
LlamaFarm backend integration.

Provides access to LlamaFarm for advanced AI capabilities.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class LlamaFarmConfig:
    """LlamaFarm backend configuration."""
    host: str = "localhost"
    port: int = 14345  # LlamaFarm default port
    api_key: Optional[str] = None
    timeout: float = 120.0
    
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class LlamaFarmBackend:
    """
    LlamaFarm backend for advanced AI capabilities.
    
    Supports:
    - LLM inference
    - Embeddings
    - Vision
    - RAG
    - Agents
    """
    
    def __init__(self, config: Optional[LlamaFarmConfig] = None):
        self.config = config or LlamaFarmConfig()
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                headers=headers
            )
        return self._session
    
    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def health_check(self) -> bool:
        """Check if LlamaFarm is available."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.config.base_url}/health") as resp:
                return resp.status == 200
        except Exception:
            return False
    
    async def get_info(self) -> Dict[str, Any]:
        """Get LlamaFarm server info."""
        session = await self._get_session()
        async with session.get(f"{self.config.base_url}/info") as resp:
            if resp.status != 200:
                return {}
            return await resp.json()
    
    async def list_projects(self, namespace: str = "discoverable") -> List[Dict[str, Any]]:
        """
        List available projects in a namespace.
        
        Args:
            namespace: Namespace to list projects from (default: "discoverable")
            
        Returns:
            List of project dictionaries
        """
        session = await self._get_session()
        
        # LlamaFarm API: GET /v1/projects/{namespace}
        url = f"{self.config.base_url}/v1/projects/{namespace}"
        
        async with session.get(url) as resp:
            if resp.status != 200:
                logger.warning(f"Failed to list projects in namespace '{namespace}': {resp.status}")
                return []
            data = await resp.json()
            # Response format: {"total": N, "projects": [...]}
            return data.get("projects", [])
    
    async def list_discoverable_projects(self) -> List[Dict[str, Any]]:
        """
        List projects in the 'discoverable' namespace.
        
        These are projects that should be exposed to the mesh.
        """
        return await self.list_projects(namespace="discoverable")
    
    async def list_all_namespaces(self) -> List[str]:
        """
        List all available namespaces.
        
        Note: LlamaFarm doesn't have a namespace listing endpoint,
        so we check the filesystem or return known defaults.
        """
        # LlamaFarm stores projects at ~/.llamafarm/projects/{namespace}/{project}/
        from pathlib import Path
        import os
        
        projects_dir = Path(os.environ.get("LF_DATA_DIR", Path.home() / ".llamafarm")) / "projects"
        
        if not projects_dir.exists():
            return ["discoverable"]  # Default
        
        namespaces = []
        for item in projects_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                namespaces.append(item.name)
        
        return namespaces if namespaces else ["discoverable"]
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models."""
        session = await self._get_session()
        async with session.get(f"{self.config.base_url}/v1/models") as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data.get("data", [])
    
    async def generate(
        self,
        prompt: str,
        model: str = "default",
        **kwargs
    ) -> str:
        """
        Simple text generation.
        
        Args:
            prompt: Input text
            model: Model name
            **kwargs: Additional parameters
            
        Returns:
            Generated text
        """
        messages = [{"role": "user", "content": prompt}]
        result = await self.chat_completion(messages, model=model, **kwargs)
        return result["choices"][0]["message"]["content"]
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "default",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        namespace: str = "discoverable",
        project: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate chat completion.
        
        Uses LlamaFarm project-based API:
        /v1/projects/{namespace}/{project}/chat/completions
        """
        session = await self._get_session()
        
        # Use atmosphere-universal project (Universal Runtime)
        if not project:
            project = "atmosphere-universal"
        
        payload = {
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        # Filter out namespace/project from kwargs
        payload.update({k: v for k, v in kwargs.items() if k not in ("namespace", "project")})
        
        # Use project endpoint if we have one
        if project:
            url = f"{self.config.base_url}/v1/projects/{namespace}/{project}/chat/completions"
        else:
            url = f"{self.config.base_url}/v1/chat/completions"
        
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise RuntimeError(f"Chat completion failed: {error}")
            
            return await resp.json()
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """Alias for chat_completion for compatibility with executor."""
        result = await self.chat_completion(messages, model=model, **kwargs)
        return {
            "message": result["choices"][0]["message"],
            "model": result.get("model", model),
            "usage": result.get("usage", {})
        }
    
    async def embed(
        self,
        text: str,
        model: str = "default"
    ) -> List[float]:
        """Generate text embedding."""
        session = await self._get_session()
        
        payload = {
            "model": model,
            "input": text
        }
        
        async with session.post(
            f"{self.config.base_url}/v1/embeddings",
            json=payload
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise RuntimeError(f"Embedding failed: {error}")
            
            data = await resp.json()
            embeddings = data.get("data", [{}])
            return embeddings[0].get("embedding", []) if embeddings else []
    
    async def vision_analyze(
        self,
        image_url: str,
        prompt: str = "Describe this image",
        model: str = "default"
    ) -> Dict[str, Any]:
        """Analyze an image."""
        session = await self._get_session()
        
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        }]
        
        return await self.chat_completion(messages, model=model)
    
    async def rag_query(
        self,
        query: str,
        dataset: str = "default",
        top_k: int = 5
    ) -> Dict[str, Any]:
        """Query RAG dataset."""
        session = await self._get_session()
        
        payload = {
            "query": query,
            "dataset": dataset,
            "top_k": top_k
        }
        
        async with session.post(
            f"{self.config.base_url}/v1/rag/query",
            json=payload
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise RuntimeError(f"RAG query failed: {error}")
            
            return await resp.json()
    
    async def import_capabilities(self) -> Dict[str, List[str]]:
        """
        Import capabilities from LlamaFarm projects in the 'discoverable' namespace.
        
        Only projects explicitly in the "discoverable" namespace will be exposed to the mesh.
        Returns a mapping of capability type to list of capability IDs.
        
        LlamaFarm project response format:
        {
            "namespace": "discoverable",
            "name": "project-name",
            "config": { ... }
        }
        """
        capabilities = {
            "llm": [],
            "embeddings": [],
            "vision": [],
            "rag": [],
            "agents": []
        }
        
        try:
            # ONLY use discoverable namespace - these are capabilities meant for mesh exposure
            projects = await self.list_discoverable_projects()
            logger.info(f"Found {len(projects)} discoverable LlamaFarm projects")
            
            for project in projects:
                # Project format from LlamaFarm API
                project_name = project.get("name", "")
                namespace = project.get("namespace", "")
                config = project.get("config", {})
                
                # Determine capability type from project config
                # Default to "llm" if not specified
                project_type = config.get("type", "llm")
                
                # Build capability ID: namespace/project_name
                capability_id = f"{namespace}/{project_name}" if namespace else project_name
                
                if project_type in capabilities:
                    capabilities[project_type].append(capability_id)
                    logger.debug(f"Imported discoverable capability: {capability_id} ({project_type})")
                else:
                    # Unknown type, default to llm
                    capabilities["llm"].append(capability_id)
                    logger.debug(f"Imported discoverable capability: {capability_id} (default: llm)")
                    
        except Exception as e:
            logger.warning(f"Failed to import LlamaFarm capabilities: {e}")
        
        return capabilities
