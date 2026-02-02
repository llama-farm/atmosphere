"""
Capabilities for Atmosphere nodes.

Built-in capability types:
- llm: Language model inference
- embeddings: Text embeddings  
- vision: Image/video analysis
- audio: Speech-to-text, TTS
- code: Code execution sandbox
- rag: Retrieval-augmented generation
- agents: Agentic task execution
"""

from .base import Capability, CapabilityHandler, CapabilityRegistry
from .llm import LLMCapability
from .vision import VisionCapability

__all__ = [
    "Capability",
    "CapabilityHandler",
    "CapabilityRegistry",
    "LLMCapability",
    "VisionCapability",
]
