"""
Embedding engine for semantic routing.

Generates embeddings using available backends (Ollama, LlamaFarm, etc.)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from ..discovery.ollama import OllamaBackend, OllamaConfig

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingConfig:
    """Configuration for embedding engine."""
    model: str = "nomic-ai/nomic-embed-text-v1.5"  # LlamaFarm model
    dimension: int = 768
    # LlamaFarm Universal endpoint (preferred)
    llamafarm_host: str = "localhost"
    llamafarm_port: int = 11540
    # Ollama fallback
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    timeout: float = 30.0
    cache_size: int = 1000
    use_llamafarm: bool = True  # Prefer LlamaFarm over Ollama


class EmbeddingEngine:
    """
    Main embedding engine with automatic backend selection.
    
    Usage:
        engine = EmbeddingEngine()
        await engine.initialize()
        
        vec = await engine.embed("analyze this image for objects")
        similarity = engine.cosine_similarity(vec1, vec2)
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self._backend: Optional[OllamaBackend] = None
        self._initialized = False
        self._cache: Dict[str, np.ndarray] = {}

    async def initialize(self) -> None:
        """Initialize the embedding engine."""
        if self._initialized:
            return

        # Try LlamaFarm Universal first (preferred)
        if self.config.use_llamafarm:
            llamafarm_url = f"http://{self.config.llamafarm_host}:{self.config.llamafarm_port}"
            if await self._check_llamafarm(llamafarm_url):
                self._llamafarm_url = llamafarm_url
                self._use_llamafarm = True
                self._initialized = True
                logger.info(f"Using LlamaFarm Universal backend with {self.config.model}")
                return

        # Fallback to Ollama
        ollama_config = OllamaConfig(
            host=self.config.ollama_host,
            port=self.config.ollama_port,
            timeout=self.config.timeout,
            embedding_model="nomic-embed-text"  # Ollama model name
        )
        
        ollama = OllamaBackend(ollama_config)
        
        if await ollama.health_check():
            if await ollama.has_model("nomic-embed-text"):
                self._backend = ollama
                self._use_llamafarm = False
                self._initialized = True
                logger.info(f"Using Ollama backend with nomic-embed-text")
                return
            else:
                logger.warning(f"Model nomic-embed-text not found in Ollama")

        raise RuntimeError(
            "No embedding backend available.\n"
            "  LlamaFarm Universal not responding on port 11540\n"
            "  Ollama nomic-embed-text not available\n"
            "Either start LlamaFarm or run: ollama pull nomic-embed-text"
        )
    
    async def _check_llamafarm(self, url: str) -> bool:
        """Check if LlamaFarm Universal endpoint is available."""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                # Quick health check
                async with session.get(f"{url}/v1/models", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        logger.debug(f"LlamaFarm Universal available at {url}")
                        return True
        except Exception as e:
            logger.debug(f"LlamaFarm not available: {e}")
        return False
    
    async def _embed_llamafarm(self, text: str) -> List[float]:
        """Generate embedding using LlamaFarm Universal endpoint."""
        import aiohttp
        import json
        
        url = f"{self._llamafarm_url}/v1/embeddings"
        payload = {
            "model": self.config.model,
            "input": text
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"LlamaFarm embedding failed: {error_text}")
                
                data = await resp.json()
                # OpenAI-compatible response format
                return data["data"][0]["embedding"]

    async def close(self) -> None:
        """Close the embedding engine."""
        if self._backend:
            await self._backend.close()
        self._initialized = False

    def _normalize(self, vec: np.ndarray) -> np.ndarray:
        """L2 normalize a vector."""
        norm = np.linalg.norm(vec)
        if norm == 0:
            return vec
        return vec / norm

    async def embed(self, text: str, normalize: bool = True) -> np.ndarray:
        """
        Generate embedding for text using LlamaFarm or Ollama.
        
        Args:
            text: Input text to embed
            normalize: Whether to L2 normalize the result
            
        Returns:
            Embedding vector as numpy array
        """
        if not self._initialized:
            await self.initialize()

        # Check cache
        cache_key = text[:200]
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        # Use LlamaFarm or Ollama
        if getattr(self, '_use_llamafarm', False):
            embedding = await self._embed_llamafarm(text)
        else:
            embedding = await self._backend.embed(text)
        vec = np.array(embedding, dtype=np.float32)

        if normalize:
            vec = self._normalize(vec)

        # Update cache
        if len(self._cache) >= self.config.cache_size:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[cache_key] = vec.copy()

        return vec

    async def embed_batch(
        self,
        texts: List[str],
        normalize: bool = True
    ) -> np.ndarray:
        """
        Generate embeddings for multiple texts.
        
        Returns:
            Array of shape (N, dimension) with embeddings
        """
        if not self._initialized:
            await self.initialize()

        # Use LlamaFarm or Ollama
        if getattr(self, '_use_llamafarm', False):
            embeddings = await self._embed_batch_llamafarm(texts)
        else:
            embeddings = await self._backend.embed_batch(texts)
        
        vecs = np.array(embeddings, dtype=np.float32)

        if normalize:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1
            vecs = vecs / norms

        return vecs
    
    async def _embed_batch_llamafarm(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts using LlamaFarm."""
        import aiohttp
        
        url = f"{self._llamafarm_url}/v1/embeddings"
        payload = {
            "model": self.config.model,
            "input": texts
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout * 2)  # Longer for batch
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"LlamaFarm batch embedding failed: {error_text}")
                
                data = await resp.json()
                # OpenAI-compatible response format - sort by index
                sorted_data = sorted(data["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in sorted_data]

    @staticmethod
    def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Compute cosine similarity between two vectors.
        
        Assumes vectors are already normalized.
        """
        return float(np.dot(vec1, vec2))

    @staticmethod
    def cosine_similarity_unnormalized(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity for unnormalized vectors."""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (norm1 * norm2))

    @staticmethod
    def batch_cosine_similarity(
        query: np.ndarray,
        candidates: np.ndarray
    ) -> np.ndarray:
        """Compute similarity between query and multiple candidates."""
        return candidates @ query

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return self.config.dimension

    @property
    def backend_name(self) -> str:
        """Return current backend name."""
        if getattr(self, '_use_llamafarm', False):
            return "llamafarm"
        if self._backend:
            return "ollama"
        return "none"


# ============================================================================
# Singleton & Convenience Functions
# ============================================================================

_default_engine: Optional[EmbeddingEngine] = None


def get_embedding_engine() -> EmbeddingEngine:
    """Get or create the default embedding engine singleton."""
    global _default_engine
    if _default_engine is None:
        _default_engine = EmbeddingEngine()
    return _default_engine


async def get_embedding(text: str, normalize: bool = True) -> np.ndarray:
    """
    Convenience function to get embedding for text.
    
    Uses the singleton EmbeddingEngine with automatic initialization.
    
    Args:
        text: Input text to embed
        normalize: Whether to L2 normalize the result
        
    Returns:
        Embedding vector as numpy array
    """
    engine = get_embedding_engine()
    return await engine.embed(text, normalize=normalize)


async def get_embeddings(texts: List[str], normalize: bool = True) -> np.ndarray:
    """
    Convenience function to get embeddings for multiple texts.
    
    Args:
        texts: List of input texts
        normalize: Whether to L2 normalize results
        
    Returns:
        Array of shape (N, dimension) with embeddings
    """
    engine = get_embedding_engine()
    return await engine.embed_batch(texts, normalize=normalize)


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Compute cosine similarity between two normalized vectors."""
    return EmbeddingEngine.cosine_similarity(vec1, vec2)
