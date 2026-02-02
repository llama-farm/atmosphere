"""
Adapters for external AI backends.

Provides execution layer interfaces to LlamaFarm, Ollama, and other backends.
"""

from .llamafarm import LlamaFarmExecutor

__all__ = ["LlamaFarmExecutor"]
