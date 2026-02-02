"""
Backend discovery for Atmosphere.

Scans the local system for AI backends:
- Ollama
- LlamaFarm
- vLLM
- Custom backends
"""

from .scanner import Scanner, BackendInfo, scan_backends
from .ollama import OllamaBackend
from .llamafarm import LlamaFarmBackend

__all__ = [
    "Scanner",
    "BackendInfo",
    "scan_backends",
    "OllamaBackend",
    "LlamaFarmBackend",
]
