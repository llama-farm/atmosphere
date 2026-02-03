"""
Capabilities for Atmosphere nodes.

Bidirectional capability system:
- TOOLS (pull): External systems invoke capability functions
- TRIGGERS (push): Capabilities emit events that route to handlers

Built-in capability types:
- llm: Language model inference (chat, reasoning, code)
- vision: Image/video analysis and generation
- audio: Speech-to-text, TTS, voice cloning
- sensors: Camera, motion, temperature
- agents: Security, research, assistant
- iot: HVAC, lights, locks
- storage: Vector, document, file
- compute: GPU, sandbox

Legacy support:
- Capability, CapabilityHandler, CapabilityRegistry from base.py
"""

# Legacy base classes (for backwards compatibility)
from .base import (
    Capability as LegacyCapability,
    CapabilityHandler,
    CapabilityRegistry as LegacyCapabilityRegistry,
)
from .llm import LLMCapability
from .vision import VisionCapability

# Enhanced capability system with Tools + Triggers
from .registry import (
    # Core types
    CapabilityType,
    Tool,
    Trigger,
    Capability,
    # Registry
    CapabilityRegistry,
    GossipMessage,
    get_registry,
    reset_registry,
)

# Tool executor
from .executor import (
    ToolExecutor,
    ExecutionResult,
    ExecutionOptions,
    ExecutionStatus,
    ExecutionError,
    ToolNotFoundError,
    CapabilityNotFoundError,
    CapabilityOfflineError,
    ValidationError,
    TimeoutError,
    call_tool,
)

# Example capabilities
from .examples import (
    ALL_EXAMPLES,
    # Sensors
    CAMERA_CAPABILITY,
    MOTION_SENSOR_CAPABILITY,
    # Audio
    VOICE_CAPABILITY,
    TRANSCRIBE_CAPABILITY,
    VOICE_CLONE_CAPABILITY,
    # Vision
    IMAGE_GEN_CAPABILITY,
    VISION_ANALYZE_CAPABILITY,
    OCR_CAPABILITY,
    # LLM
    LLM_CHAT_CAPABILITY,
    LLM_REASONING_CAPABILITY,
    LLM_CODE_CAPABILITY,
    # Agents
    SECURITY_AGENT_CAPABILITY,
    RESEARCH_AGENT_CAPABILITY,
    # IoT
    HVAC_CAPABILITY,
    LIGHT_CAPABILITY,
    LOCK_CAPABILITY,
    # Helpers
    get_example_by_type,
    get_example_by_id,
)

__all__ = [
    # Legacy
    "LegacyCapability",
    "CapabilityHandler",
    "LegacyCapabilityRegistry",
    "LLMCapability",
    "VisionCapability",
    # Core types
    "CapabilityType",
    "Tool",
    "Trigger",
    "Capability",
    # Registry
    "CapabilityRegistry",
    "GossipMessage",
    "get_registry",
    "reset_registry",
    # Executor
    "ToolExecutor",
    "ExecutionResult",
    "ExecutionOptions",
    "ExecutionStatus",
    "ExecutionError",
    "ToolNotFoundError",
    "CapabilityNotFoundError",
    "CapabilityOfflineError",
    "ValidationError",
    "TimeoutError",
    "call_tool",
    # Examples
    "ALL_EXAMPLES",
    "CAMERA_CAPABILITY",
    "MOTION_SENSOR_CAPABILITY",
    "VOICE_CAPABILITY",
    "TRANSCRIBE_CAPABILITY",
    "VOICE_CLONE_CAPABILITY",
    "IMAGE_GEN_CAPABILITY",
    "VISION_ANALYZE_CAPABILITY",
    "OCR_CAPABILITY",
    "LLM_CHAT_CAPABILITY",
    "LLM_REASONING_CAPABILITY",
    "LLM_CODE_CAPABILITY",
    "SECURITY_AGENT_CAPABILITY",
    "RESEARCH_AGENT_CAPABILITY",
    "HVAC_CAPABILITY",
    "LIGHT_CAPABILITY",
    "LOCK_CAPABILITY",
    "get_example_by_type",
    "get_example_by_id",
]
