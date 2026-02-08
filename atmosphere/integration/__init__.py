"""
Integration modules for external capability sources.

Discovers and registers capabilities from various backends:
- LlamaFarm projects
- Ollama models
- OpenAI API
- etc.
"""

from .llamafarm import discover_llamafarm_capabilities

__all__ = ["discover_llamafarm_capabilities"]
