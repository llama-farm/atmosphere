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
    
    async def list_projects(self) -> List[Dict[str, Any]]:
        """List available projects."""
        session = await self._get_session()
        async with session.get(f"{self.config.base_url}/v1/projects") as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data.get("data", [])
    
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
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate chat completion.
        
        Uses OpenAI-compatible API format.
        """
        session = await self._get_session()
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        payload.update(kwargs)
        
        async with session.post(
            f"{self.config.base_url}/v1/chat/completions",
            json=payload
        ) as resp:
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
        Import capabilities from LlamaFarm projects.
        
        Returns a mapping of capability type to list of capability IDs.
        """
        capabilities = {
            "llm": [],
            "embeddings": [],
            "vision": [],
            "rag": [],
            "agents": []
        }
        
        try:
            projects = await self.list_projects()
            for project in projects:
                project_id = project.get("id", "")
                project_type = project.get("type", "")
                
                if project_type in capabilities:
                    capabilities[project_type].append(project_id)
        except Exception as e:
            logger.warning(f"Failed to import LlamaFarm capabilities: {e}")
        
        return capabilities
