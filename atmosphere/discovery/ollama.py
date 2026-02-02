"""
Ollama backend integration.

Provides direct access to Ollama for LLM inference and embeddings.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class OllamaConfig:
    """Ollama backend configuration."""
    host: str = "localhost"
    port: int = 11434
    timeout: float = 120.0
    default_model: str = "llama3.2"
    embedding_model: str = "nomic-embed-text"
    
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class OllamaBackend:
    """
    Ollama backend for LLM inference and embeddings.
    
    Usage:
        ollama = OllamaBackend()
        
        # Generate text
        response = await ollama.generate("What is 2+2?")
        
        # Generate embeddings
        embedding = await ollama.embed("Hello world")
        
        # Chat completion
        messages = [{"role": "user", "content": "Hello!"}]
        response = await ollama.chat(messages)
    """
    
    def __init__(self, config: Optional[OllamaConfig] = None):
        self.config = config or OllamaConfig()
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            )
        return self._session
    
    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def health_check(self) -> bool:
        """Check if Ollama is available."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.config.base_url}/api/tags") as resp:
                return resp.status == 200
        except Exception:
            return False
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models."""
        session = await self._get_session()
        async with session.get(f"{self.config.base_url}/api/tags") as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to list models: {resp.status}")
            data = await resp.json()
            return data.get("models", [])
    
    async def has_model(self, model: str) -> bool:
        """Check if a model is available."""
        models = await self.list_models()
        return any(model in m.get("name", "") for m in models)
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Generate text completion.
        
        Args:
            prompt: The input prompt
            model: Model to use (defaults to config.default_model)
            system: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text
        """
        session = await self._get_session()
        model = model or self.config.default_model
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }
        
        if system:
            payload["system"] = system
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        
        payload["options"].update(kwargs)
        
        async with session.post(
            f"{self.config.base_url}/api/generate",
            json=payload
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise RuntimeError(f"Generation failed: {error}")
            
            data = await resp.json()
            return data.get("response", "")
    
    async def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Generate text with streaming."""
        session = await self._get_session()
        model = model or self.config.default_model
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": kwargs
        }
        
        async with session.post(
            f"{self.config.base_url}/api/generate",
            json=payload
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise RuntimeError(f"Generation failed: {error}")
            
            async for line in resp.content:
                if line:
                    import json
                    data = json.loads(line)
                    if "response" in data:
                        yield data["response"]
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Chat completion (OpenAI-compatible format).
        
        Args:
            messages: List of {"role": "user/assistant/system", "content": "..."}
            model: Model to use
            temperature: Sampling temperature
            
        Returns:
            Chat completion response
        """
        session = await self._get_session()
        model = model or self.config.default_model
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                **kwargs
            }
        }
        
        async with session.post(
            f"{self.config.base_url}/api/chat",
            json=payload
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise RuntimeError(f"Chat failed: {error}")
            
            data = await resp.json()
            return {
                "message": data.get("message", {}),
                "model": model,
                "done": data.get("done", True)
            }
    
    async def embed(
        self,
        text: str,
        model: Optional[str] = None
    ) -> List[float]:
        """
        Generate text embedding.
        
        Args:
            text: Text to embed
            model: Embedding model (defaults to nomic-embed-text)
            
        Returns:
            Embedding vector as list of floats
        """
        session = await self._get_session()
        model = model or self.config.embedding_model
        
        payload = {
            "model": model,
            "prompt": text
        }
        
        async with session.post(
            f"{self.config.base_url}/api/embeddings",
            json=payload
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise RuntimeError(f"Embedding failed: {error}")
            
            data = await resp.json()
            return data.get("embedding", [])
    
    async def embed_batch(
        self,
        texts: List[str],
        model: Optional[str] = None
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        # Ollama doesn't have native batch, parallelize
        tasks = [self.embed(text, model) for text in texts]
        return await asyncio.gather(*tasks)
