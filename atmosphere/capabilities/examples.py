"""
Example Capability Definitions for Atmosphere.

Pre-built capability templates for common multimodal use cases.
Use these as starting points or register them directly.
"""

from .registry import Capability, CapabilityType, Tool, Trigger


# =============================================================================
# SENSOR CAPABILITIES
# =============================================================================

CAMERA_CAPABILITY = Capability(
    id="front-door-camera",
    node_id="home-node",
    type=CapabilityType.SENSOR_CAMERA,
    tools=[
        Tool(
            name="get_frame",
            description="Capture current frame from camera",
            parameters={},
            returns={"type": "image", "format": "jpeg"},
        ),
        Tool(
            name="get_history",
            description="Get recent motion events",
            parameters={
                "hours": {"type": "number", "default": 24},
                "limit": {"type": "number", "default": 100},
            },
            returns={"type": "array", "items": "motion_event"},
        ),
        Tool(
            name="get_clip",
            description="Get video clip around timestamp",
            parameters={
                "timestamp": {"type": "number", "required": True},
                "before_sec": {"type": "number", "default": 10},
                "after_sec": {"type": "number", "default": 10},
            },
            returns={"type": "video", "format": "mp4"},
        ),
        Tool(
            name="set_mode",
            description="Set camera mode (on/off/motion-only)",
            parameters={
                "mode": {"type": "string", "enum": ["on", "off", "motion-only"]},
            },
        ),
    ],
    triggers=[
        Trigger(
            event="motion_detected",
            description="Motion detected in camera frame",
            intent_template="motion at {location}",
            payload_schema={"location": "string", "confidence": "number"},
            priority="normal",
            throttle="30s",
        ),
        Trigger(
            event="person_detected",
            description="Person detected in camera frame",
            intent_template="person at {location}",
            payload_schema={
                "location": "string",
                "confidence": "number",
                "count": "number",
            },
            route_hint="agent/security",
            priority="high",
        ),
        Trigger(
            event="package_detected",
            description="Package arrived at door",
            intent_template="package at {location}",
            payload_schema={"location": "string", "timestamp": "number"},
            priority="high",
        ),
        Trigger(
            event="vehicle_detected",
            description="Vehicle detected",
            intent_template="vehicle {action} at {location}",
            payload_schema={
                "location": "string",
                "action": "string",  # arrived, departed
                "vehicle_type": "string",
            },
        ),
    ],
    metadata={
        "resolution": "1080p",
        "night_vision": True,
        "location": "front_door",
    },
)


MOTION_SENSOR_CAPABILITY = Capability(
    id="living-room-motion",
    node_id="home-node",
    type=CapabilityType.SENSOR_MOTION,
    tools=[
        Tool(
            name="get_status",
            description="Get current motion status",
            returns={"motion_detected": "boolean", "last_motion": "timestamp"},
        ),
        Tool(
            name="get_history",
            description="Get motion history",
            parameters={"hours": {"type": "number", "default": 24}},
            returns={"type": "array", "items": "motion_event"},
        ),
        Tool(
            name="set_sensitivity",
            description="Set motion sensitivity (1-10)",
            parameters={"level": {"type": "number", "min": 1, "max": 10}},
        ),
    ],
    triggers=[
        Trigger(
            event="motion_start",
            description="Motion started",
            intent_template="motion started in {room}",
            throttle="10s",
        ),
        Trigger(
            event="motion_end",
            description="Motion ended",
            intent_template="motion ended in {room}",
        ),
        Trigger(
            event="occupancy_change",
            description="Room occupancy changed",
            intent_template="{room} is now {status}",
            payload_schema={"room": "string", "status": "string"},
        ),
    ],
    metadata={"room": "living_room"},
)


# =============================================================================
# AUDIO CAPABILITIES
# =============================================================================

VOICE_CAPABILITY = Capability(
    id="voice-service",
    node_id="cloud-node",
    type=CapabilityType.AUDIO_GENERATE,
    tools=[
        Tool(
            name="speak",
            description="Convert text to speech",
            parameters={
                "text": {"type": "string", "required": True},
                "voice": {"type": "string", "default": "default"},
                "speed": {"type": "number", "default": 1.0},
                "output_format": {"type": "string", "default": "mp3"},
            },
            returns={"type": "audio", "format": "mp3"},
            timeout_ms=60000,
        ),
        Tool(
            name="list_voices",
            description="List available voices",
            returns={"type": "array", "items": "voice_info"},
        ),
        Tool(
            name="speak_ssml",
            description="Speak with SSML markup",
            parameters={
                "ssml": {"type": "string", "required": True},
                "voice": {"type": "string", "default": "default"},
            },
            returns={"type": "audio", "format": "mp3"},
        ),
    ],
    triggers=[
        Trigger(
            event="speech_complete",
            description="TTS finished generating",
            intent_template="speech complete: {text_preview}",
            payload_schema={
                "text_preview": "string",
                "duration_ms": "number",
                "voice": "string",
            },
        ),
    ],
    metadata={
        "provider": "elevenlabs",
        "languages": ["en", "es", "fr", "de", "ja"],
    },
)


TRANSCRIBE_CAPABILITY = Capability(
    id="whisper-service",
    node_id="cloud-node",
    type=CapabilityType.AUDIO_TRANSCRIBE,
    tools=[
        Tool(
            name="transcribe",
            description="Transcribe audio to text",
            parameters={
                "audio": {"type": "bytes", "required": True},
                "language": {"type": "string", "default": "auto"},
                "format": {"type": "string", "default": "text"},
            },
            returns={"text": "string", "language": "string", "confidence": "number"},
            timeout_ms=120000,
        ),
        Tool(
            name="transcribe_url",
            description="Transcribe audio from URL",
            parameters={
                "url": {"type": "string", "required": True},
                "language": {"type": "string", "default": "auto"},
            },
            returns={"text": "string", "language": "string"},
        ),
        Tool(
            name="transcribe_stream",
            description="Start streaming transcription",
            parameters={
                "stream_url": {"type": "string", "required": True},
                "language": {"type": "string", "default": "auto"},
            },
            returns={"session_id": "string"},
        ),
    ],
    triggers=[
        Trigger(
            event="transcription_complete",
            description="Transcription ready",
            intent_template="transcribed: {preview}",
            payload_schema={
                "preview": "string",
                "full_text": "string",
                "language": "string",
                "duration_ms": "number",
            },
        ),
        Trigger(
            event="keyword_detected",
            description="Hotword/keyword detected in audio",
            intent_template="keyword '{keyword}' detected",
            payload_schema={
                "keyword": "string",
                "confidence": "number",
                "timestamp_ms": "number",
            },
            route_hint="agent/*",
            priority="high",
        ),
        Trigger(
            event="speaker_change",
            description="Speaker changed in audio",
            intent_template="speaker changed to {speaker_id}",
            payload_schema={"speaker_id": "string", "timestamp_ms": "number"},
        ),
    ],
    metadata={
        "model": "whisper-large-v3",
        "languages": "multilingual",
        "realtime": True,
    },
)


VOICE_CLONE_CAPABILITY = Capability(
    id="voice-clone-service",
    node_id="cloud-node",
    type=CapabilityType.AUDIO_CLONE,
    tools=[
        Tool(
            name="clone",
            description="Clone a voice from sample audio",
            parameters={
                "samples": {"type": "array", "items": "bytes", "required": True},
                "name": {"type": "string", "required": True},
            },
            returns={"voice_id": "string"},
            timeout_ms=300000,
        ),
        Tool(
            name="speak_cloned",
            description="Generate speech with cloned voice",
            parameters={
                "text": {"type": "string", "required": True},
                "voice_id": {"type": "string", "required": True},
            },
            returns={"type": "audio", "format": "mp3"},
        ),
    ],
    triggers=[
        Trigger(
            event="clone_ready",
            description="Voice clone ready",
            intent_template="voice clone '{name}' ready",
            payload_schema={"voice_id": "string", "name": "string"},
        ),
    ],
    metadata={"provider": "elevenlabs"},
)


# =============================================================================
# VISION CAPABILITIES
# =============================================================================

IMAGE_GEN_CAPABILITY = Capability(
    id="image-generator",
    node_id="cloud-node",
    type=CapabilityType.VISION_GENERATE,
    tools=[
        Tool(
            name="generate",
            description="Generate image from prompt",
            parameters={
                "prompt": {"type": "string", "required": True},
                "size": {"type": "string", "default": "1024x1024"},
                "style": {"type": "string", "default": "natural"},
                "quality": {"type": "string", "default": "standard"},
            },
            returns={"type": "image", "format": "png"},
            timeout_ms=120000,
        ),
        Tool(
            name="edit",
            description="Edit existing image with prompt",
            parameters={
                "image": {"type": "bytes", "required": True},
                "prompt": {"type": "string", "required": True},
                "mask": {"type": "bytes"},
            },
            returns={"type": "image", "format": "png"},
            timeout_ms=120000,
        ),
        Tool(
            name="variation",
            description="Generate variations of an image",
            parameters={
                "image": {"type": "bytes", "required": True},
                "count": {"type": "number", "default": 4},
            },
            returns={"type": "array", "items": "image"},
        ),
    ],
    triggers=[
        Trigger(
            event="generation_complete",
            description="Image generation complete",
            intent_template="image generated: {prompt_preview}",
            payload_schema={
                "prompt_preview": "string",
                "image_url": "string",
                "generation_time_ms": "number",
            },
        ),
    ],
    metadata={
        "model": "dall-e-3",
        "max_resolution": "1024x1024",
    },
)


VISION_ANALYZE_CAPABILITY = Capability(
    id="vision-analyzer",
    node_id="cloud-node",
    type=CapabilityType.VISION_CLASSIFY,
    tools=[
        Tool(
            name="classify",
            description="Classify image contents",
            parameters={
                "image": {"type": "bytes", "required": True},
                "categories": {"type": "array", "items": "string"},
            },
            returns={"labels": "array", "confidences": "array"},
        ),
        Tool(
            name="describe",
            description="Generate description of image",
            parameters={
                "image": {"type": "bytes", "required": True},
                "detail": {"type": "string", "default": "medium"},
            },
            returns={"description": "string"},
        ),
        Tool(
            name="detect_objects",
            description="Detect objects in image",
            parameters={"image": {"type": "bytes", "required": True}},
            returns={"objects": "array"},
        ),
    ],
    triggers=[],
    metadata={"model": "gpt-4-vision"},
)


OCR_CAPABILITY = Capability(
    id="ocr-service",
    node_id="cloud-node",
    type=CapabilityType.VISION_OCR,
    tools=[
        Tool(
            name="extract_text",
            description="Extract text from image",
            parameters={
                "image": {"type": "bytes", "required": True},
                "language": {"type": "string", "default": "auto"},
            },
            returns={"text": "string", "blocks": "array"},
        ),
        Tool(
            name="extract_structured",
            description="Extract structured data (forms, tables)",
            parameters={
                "image": {"type": "bytes", "required": True},
                "type": {"type": "string", "enum": ["form", "table", "receipt"]},
            },
            returns={"data": "object"},
        ),
    ],
    triggers=[],
    metadata={"provider": "tesseract"},
)


# =============================================================================
# LLM CAPABILITIES
# =============================================================================

LLM_CHAT_CAPABILITY = Capability(
    id="llm-chat",
    node_id="cloud-node",
    type=CapabilityType.LLM_CHAT,
    tools=[
        Tool(
            name="chat",
            description="Send chat message to LLM",
            parameters={
                "messages": {"type": "array", "required": True},
                "model": {"type": "string", "default": "gpt-4"},
                "temperature": {"type": "number", "default": 0.7},
                "max_tokens": {"type": "number", "default": 4096},
            },
            returns={"content": "string", "usage": "object"},
            timeout_ms=60000,
        ),
        Tool(
            name="complete",
            description="Text completion",
            parameters={
                "prompt": {"type": "string", "required": True},
                "model": {"type": "string", "default": "gpt-4"},
            },
            returns={"completion": "string"},
        ),
    ],
    triggers=[
        Trigger(
            event="response_ready",
            description="LLM response ready (for async)",
            intent_template="response ready for {request_id}",
        ),
    ],
    metadata={
        "models": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
        "provider": "openai",
    },
)


LLM_REASONING_CAPABILITY = Capability(
    id="llm-reasoning",
    node_id="cloud-node",
    type=CapabilityType.LLM_REASONING,
    tools=[
        Tool(
            name="reason",
            description="Deep reasoning with extended thinking",
            parameters={
                "problem": {"type": "string", "required": True},
                "context": {"type": "string"},
                "thinking_budget": {"type": "number", "default": 10000},
            },
            returns={
                "answer": "string",
                "reasoning": "string",
                "confidence": "number",
            },
            timeout_ms=300000,
        ),
    ],
    triggers=[],
    metadata={
        "models": ["claude-3-opus", "o1-preview"],
    },
)


LLM_CODE_CAPABILITY = Capability(
    id="llm-code",
    node_id="cloud-node",
    type=CapabilityType.LLM_CODE,
    tools=[
        Tool(
            name="generate_code",
            description="Generate code from description",
            parameters={
                "description": {"type": "string", "required": True},
                "language": {"type": "string", "default": "python"},
                "context": {"type": "string"},
            },
            returns={"code": "string", "explanation": "string"},
        ),
        Tool(
            name="review_code",
            description="Review and suggest improvements",
            parameters={
                "code": {"type": "string", "required": True},
                "language": {"type": "string", "default": "python"},
            },
            returns={"issues": "array", "suggestions": "array"},
        ),
        Tool(
            name="explain_code",
            description="Explain what code does",
            parameters={"code": {"type": "string", "required": True}},
            returns={"explanation": "string"},
        ),
    ],
    triggers=[],
    metadata={
        "languages": ["python", "javascript", "typescript", "rust", "go"],
    },
)


# =============================================================================
# AGENT CAPABILITIES
# =============================================================================

SECURITY_AGENT_CAPABILITY = Capability(
    id="security-agent",
    node_id="home-node",
    type=CapabilityType.AGENT_SECURITY,
    tools=[
        Tool(
            name="get_status",
            description="Get security system status",
            returns={"armed": "boolean", "mode": "string", "alerts": "array"},
        ),
        Tool(
            name="arm",
            description="Arm the security system",
            parameters={"mode": {"type": "string", "enum": ["home", "away", "night"]}},
        ),
        Tool(
            name="disarm",
            description="Disarm the security system",
            parameters={"code": {"type": "string", "required": True}},
        ),
        Tool(
            name="trigger_alert",
            description="Manually trigger an alert",
            parameters={
                "type": {"type": "string", "required": True},
                "message": {"type": "string"},
            },
        ),
    ],
    triggers=[
        Trigger(
            event="alert",
            description="Security alert triggered",
            intent_template="SECURITY ALERT: {type} - {message}",
            payload_schema={
                "type": "string",
                "message": "string",
                "source": "string",
            },
            priority="critical",
        ),
        Trigger(
            event="armed",
            description="System armed",
            intent_template="security armed in {mode} mode",
        ),
        Trigger(
            event="disarmed",
            description="System disarmed",
            intent_template="security disarmed",
        ),
    ],
    metadata={"zones": 8, "panel": "home-assistant"},
)


RESEARCH_AGENT_CAPABILITY = Capability(
    id="research-agent",
    node_id="cloud-node",
    type=CapabilityType.AGENT_RESEARCH,
    tools=[
        Tool(
            name="research",
            description="Research a topic",
            parameters={
                "topic": {"type": "string", "required": True},
                "depth": {"type": "string", "default": "medium"},
                "sources": {"type": "array", "items": "string"},
            },
            returns={"summary": "string", "sources": "array", "facts": "array"},
            timeout_ms=300000,
        ),
        Tool(
            name="summarize_url",
            description="Summarize content from URL",
            parameters={"url": {"type": "string", "required": True}},
            returns={"summary": "string", "key_points": "array"},
        ),
    ],
    triggers=[
        Trigger(
            event="research_complete",
            description="Research task complete",
            intent_template="research complete: {topic_preview}",
        ),
    ],
    metadata={},
)


# =============================================================================
# IOT CAPABILITIES
# =============================================================================

HVAC_CAPABILITY = Capability(
    id="hvac-controller",
    node_id="home-node",
    type=CapabilityType.IOT_HVAC,
    tools=[
        Tool(
            name="get_status",
            description="Get current HVAC status",
            returns={
                "current_temp": "number",
                "target_temp": "number",
                "mode": "string",
                "running": "boolean",
            },
        ),
        Tool(
            name="set_temperature",
            description="Set target temperature",
            parameters={
                "temp": {"type": "number", "required": True},
                "unit": {"type": "string", "default": "fahrenheit"},
            },
        ),
        Tool(
            name="set_mode",
            description="Set HVAC mode",
            parameters={
                "mode": {"type": "string", "enum": ["heat", "cool", "auto", "off"]}
            },
        ),
    ],
    triggers=[
        Trigger(
            event="temp_reached",
            description="Target temperature reached",
            intent_template="temperature reached {temp}°",
        ),
        Trigger(
            event="temp_alert",
            description="Temperature out of range",
            intent_template="temperature alert: {current}° (target: {target}°)",
            priority="high",
        ),
    ],
    metadata={"brand": "nest", "zones": 2},
)


LIGHT_CAPABILITY = Capability(
    id="living-room-light",
    node_id="home-node",
    type=CapabilityType.IOT_LIGHT,
    tools=[
        Tool(
            name="get_status",
            description="Get light status",
            returns={"on": "boolean", "brightness": "number", "color": "string"},
        ),
        Tool(
            name="set_state",
            description="Set light on/off",
            parameters={"on": {"type": "boolean", "required": True}},
        ),
        Tool(
            name="set_brightness",
            description="Set brightness (0-100)",
            parameters={"brightness": {"type": "number", "required": True}},
        ),
        Tool(
            name="set_color",
            description="Set light color",
            parameters={
                "color": {"type": "string", "required": True}
            },  # hex or name
        ),
        Tool(
            name="set_scene",
            description="Activate a scene",
            parameters={
                "scene": {
                    "type": "string",
                    "enum": ["relax", "focus", "energize", "movie"],
                }
            },
        ),
    ],
    triggers=[
        Trigger(
            event="state_change",
            description="Light state changed",
            intent_template="light {action}",
        ),
    ],
    metadata={"brand": "hue", "color_capable": True},
)


LOCK_CAPABILITY = Capability(
    id="front-door-lock",
    node_id="home-node",
    type=CapabilityType.IOT_LOCK,
    tools=[
        Tool(
            name="get_status",
            description="Get lock status",
            returns={"locked": "boolean", "last_action": "object"},
        ),
        Tool(
            name="lock",
            description="Lock the door",
        ),
        Tool(
            name="unlock",
            description="Unlock the door (requires auth)",
            parameters={"code": {"type": "string"}},
            requires_auth=True,
        ),
    ],
    triggers=[
        Trigger(
            event="locked",
            description="Door locked",
            intent_template="door locked",
        ),
        Trigger(
            event="unlocked",
            description="Door unlocked",
            intent_template="door unlocked by {method}",
            route_hint="agent/security",
        ),
        Trigger(
            event="tamper",
            description="Tamper detected",
            intent_template="TAMPER ALERT on door lock",
            priority="critical",
            route_hint="agent/security",
        ),
    ],
    metadata={"brand": "august", "auto_lock": True},
)


# =============================================================================
# ALL EXAMPLES
# =============================================================================

ALL_EXAMPLES = [
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
]


def get_example_by_type(cap_type: CapabilityType) -> list[Capability]:
    """Get all examples of a specific type."""
    return [c for c in ALL_EXAMPLES if c.type == cap_type]


def get_example_by_id(capability_id: str) -> Capability | None:
    """Get an example by ID."""
    for c in ALL_EXAMPLES:
        if c.id == capability_id:
            return c
    return None
