"""
LLM capability handler.
"""

import logging
from typing import Any, Dict, List, Optional

from .base import CapabilityHandler
from ..discovery.ollama import OllamaBackend, OllamaConfig

logger = logging.getLogger(__name__)


class LLMCapability(CapabilityHandler):
    """
    Language model capability for text generation.
    
    Supports:
    - Text completion
    - Chat completion
    - Code generation
    - Summarization
    - Analysis
    """
    
    def __init__(self, config: Optional[OllamaConfig] = None):
        self._config = config or OllamaConfig()
        self._backend: Optional[OllamaBackend] = None
    
    @property
    def capability_type(self) -> str:
        return "llm"
    
    @property
    def description(self) -> str:
        return (
            "Language model for text generation, completion, summarization, "
            "analysis, reasoning, code generation, and conversation"
        )
    
    async def _get_backend(self) -> OllamaBackend:
        if self._backend is None:
            self._backend = OllamaBackend(self._config)
        return self._backend
    
    async def health_check(self) -> bool:
        try:
            backend = await self._get_backend()
            return await backend.health_check()
        except Exception:
            return False
    
    async def execute(self, **kwargs) -> Any:
        """
        Execute LLM capability.
        
        Supported kwargs:
        - prompt: Text prompt for completion
        - messages: List of chat messages
        - model: Model to use
        - temperature: Sampling temperature
        - max_tokens: Maximum tokens to generate
        - system: System prompt
        """
        backend = await self._get_backend()
        
        # Determine mode
        if "messages" in kwargs:
            return await self._chat(backend, **kwargs)
        elif "prompt" in kwargs:
            return await self._generate(backend, **kwargs)
        else:
            raise ValueError("Either 'prompt' or 'messages' required")
    
    async def _generate(self, backend: OllamaBackend, **kwargs) -> str:
        """Generate text completion."""
        return await backend.generate(
            prompt=kwargs["prompt"],
            model=kwargs.get("model"),
            system=kwargs.get("system"),
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens")
        )
    
    async def _chat(self, backend: OllamaBackend, **kwargs) -> Dict[str, Any]:
        """Generate chat completion."""
        return await backend.chat(
            messages=kwargs["messages"],
            model=kwargs.get("model"),
            temperature=kwargs.get("temperature", 0.7)
        )
    
    async def close(self) -> None:
        if self._backend:
            await self._backend.close()
