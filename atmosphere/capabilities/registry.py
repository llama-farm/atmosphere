"""
Enhanced Capability Registry with bidirectional Tools + Triggers.

Every capability is bidirectional:
- TOOL (pull): External systems can invoke capability functions
- TRIGGER (push): Capability can emit events that route to handlers
"""

import asyncio
import logging
import time
import re
import fnmatch
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Set
from enum import Enum

logger = logging.getLogger(__name__)


class CapabilityType(Enum):
    """Categorized capability types for the Internet of Intent."""
    
    # LLM
    LLM_CHAT = "llm/chat"
    LLM_REASONING = "llm/reasoning"
    LLM_CODE = "llm/code"
    
    # Vision
    VISION_CLASSIFY = "vision/classify"
    VISION_DETECT = "vision/detect"
    VISION_OCR = "vision/ocr"
    VISION_GENERATE = "vision/generate"  # Image generation
    
    # Audio/Voice
    AUDIO_TRANSCRIBE = "audio/transcribe"  # Speech to text
    AUDIO_GENERATE = "audio/generate"      # Text to speech / voice
    AUDIO_CLONE = "audio/clone"            # Voice cloning
    
    # Sensors
    SENSOR_CAMERA = "sensor/camera"
    SENSOR_MOTION = "sensor/motion"
    SENSOR_TEMPERATURE = "sensor/temperature"
    
    # Agents
    AGENT_SECURITY = "agent/security"
    AGENT_RESEARCH = "agent/research"
    AGENT_ASSISTANT = "agent/assistant"
    
    # IoT
    IOT_HVAC = "iot/hvac"
    IOT_LIGHT = "iot/light"
    IOT_LOCK = "iot/lock"
    IOT_SWITCH = "iot/switch"
    
    # Storage
    STORAGE_VECTOR = "storage/vector"
    STORAGE_DOCUMENT = "storage/document"
    STORAGE_FILE = "storage/file"
    
    # Compute
    COMPUTE_GPU = "compute/gpu"
    COMPUTE_SANDBOX = "compute/sandbox"


@dataclass
class Tool:
    """
    A callable function exposed by a capability.
    
    Tools are the PULL side - external systems invoke them.
    """
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    returns: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30000
    requires_auth: bool = False
    
    def validate_params(self, params: Dict[str, Any]) -> List[str]:
        """Validate parameters against schema. Returns list of errors."""
        errors = []
        for param_name, param_spec in self.parameters.items():
            if isinstance(param_spec, dict):
                required = param_spec.get("required", False)
                param_type = param_spec.get("type", "any")
            else:
                required = False
                param_type = param_spec
            
            if required and param_name not in params:
                errors.append(f"Missing required parameter: {param_name}")
            elif param_name in params:
                value = params[param_name]
                if param_type == "string" and not isinstance(value, str):
                    errors.append(f"Parameter {param_name} must be string")
                elif param_type == "number" and not isinstance(value, (int, float)):
                    errors.append(f"Parameter {param_name} must be number")
                elif param_type == "boolean" and not isinstance(value, bool):
                    errors.append(f"Parameter {param_name} must be boolean")
        return errors


@dataclass
class Trigger:
    """
    An event that a capability can emit.
    
    Triggers are the PUSH side - capability fires events that route to handlers.
    """
    event: str
    description: str
    intent_template: str  # Template for creating intent, e.g., "motion at {location}"
    payload_schema: Dict[str, Any] = field(default_factory=dict)
    route_hint: Optional[str] = None  # e.g., "security/*" to route to security agents
    priority: str = "normal"  # low, normal, high, critical
    throttle: Optional[str] = None  # "30s", "5m", etc.
    
    def format_intent(self, payload: Dict[str, Any]) -> str:
        """Format the intent template with payload values."""
        try:
            return self.intent_template.format(**payload)
        except KeyError as e:
            logger.warning(f"Missing key in intent template: {e}")
            return self.intent_template
    
    def parse_throttle_ms(self) -> Optional[int]:
        """Parse throttle string to milliseconds."""
        if not self.throttle:
            return None
        
        match = re.match(r'^(\d+)(s|m|h)$', self.throttle)
        if not match:
            return None
        
        value, unit = int(match.group(1)), match.group(2)
        multipliers = {'s': 1000, 'm': 60000, 'h': 3600000}
        return value * multipliers.get(unit, 1000)


@dataclass
class Capability:
    """
    A bidirectional capability that can be both invoked (tools) and emit events (triggers).
    
    This is the core unit of the Internet of Intent - capabilities find work,
    work finds capabilities.
    """
    id: str
    node_id: str
    type: CapabilityType
    tools: List[Tool] = field(default_factory=list)
    triggers: List[Trigger] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "online"  # online, offline, degraded, busy
    last_heartbeat: float = 0.0
    version: str = "1.0.0"
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None
    
    def get_trigger(self, event: str) -> Optional[Trigger]:
        """Get a trigger by event name."""
        for trigger in self.triggers:
            if trigger.event == event:
                return trigger
        return None
    
    def is_healthy(self, timeout_sec: float = 60.0) -> bool:
        """Check if capability is healthy based on heartbeat."""
        if self.status == "offline":
            return False
        return (time.time() - self.last_heartbeat) < timeout_sec
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for gossip/storage."""
        return {
            "id": self.id,
            "node_id": self.node_id,
            "type": self.type.value,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                    "returns": t.returns,
                }
                for t in self.tools
            ],
            "triggers": [
                {
                    "event": t.event,
                    "description": t.description,
                    "intent_template": t.intent_template,
                    "route_hint": t.route_hint,
                    "priority": t.priority,
                    "throttle": t.throttle,
                }
                for t in self.triggers
            ],
            "metadata": self.metadata,
            "status": self.status,
            "last_heartbeat": self.last_heartbeat,
            "version": self.version,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Capability":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            node_id=data["node_id"],
            type=CapabilityType(data["type"]),
            tools=[Tool(**t) for t in data.get("tools", [])],
            triggers=[Trigger(**t) for t in data.get("triggers", [])],
            metadata=data.get("metadata", {}),
            status=data.get("status", "online"),
            last_heartbeat=data.get("last_heartbeat", 0.0),
            version=data.get("version", "1.0.0"),
        )


class GossipMessage:
    """Gossip protocol messages for capability discovery."""
    
    CAPABILITY_AVAILABLE = "CAPABILITY_AVAILABLE"
    CAPABILITY_HEARTBEAT = "CAPABILITY_HEARTBEAT"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    CAPABILITY_UPDATE = "CAPABILITY_UPDATE"
    
    @staticmethod
    def available(capability: Capability, sender_id: str) -> Dict[str, Any]:
        """Create a CAPABILITY_AVAILABLE gossip message."""
        return {
            "type": GossipMessage.CAPABILITY_AVAILABLE,
            "sender_id": sender_id,
            "timestamp": time.time(),
            "capability": capability.to_dict(),
        }
    
    @staticmethod
    def heartbeat(capability_ids: List[str], sender_id: str) -> Dict[str, Any]:
        """Create a CAPABILITY_HEARTBEAT gossip message."""
        return {
            "type": GossipMessage.CAPABILITY_HEARTBEAT,
            "sender_id": sender_id,
            "timestamp": time.time(),
            "capability_ids": capability_ids,
        }
    
    @staticmethod
    def unavailable(capability_id: str, sender_id: str, reason: str = "") -> Dict[str, Any]:
        """Create a CAPABILITY_UNAVAILABLE gossip message."""
        return {
            "type": GossipMessage.CAPABILITY_UNAVAILABLE,
            "sender_id": sender_id,
            "timestamp": time.time(),
            "capability_id": capability_id,
            "reason": reason,
        }


class CapabilityRegistry:
    """
    Registry for discovering and managing capabilities.
    
    Features:
    - Register/deregister capabilities
    - Query by type, trigger event, or tool name
    - Health tracking via heartbeats
    - Gossip message generation for mesh propagation
    """
    
    def __init__(self, node_id: str = "local"):
        self.node_id = node_id
        self._capabilities: Dict[str, Capability] = {}
        self._by_type: Dict[CapabilityType, Set[str]] = {}
        self._by_trigger: Dict[str, Set[str]] = {}  # event -> capability_ids
        self._by_tool: Dict[str, Set[str]] = {}  # tool_name -> capability_ids
        self._handlers: Dict[str, Callable] = {}  # capability_id:tool_name -> handler
        self._lock = asyncio.Lock()
    
    async def register(self, capability: Capability) -> None:
        """Register a capability."""
        async with self._lock:
            self._capabilities[capability.id] = capability
            capability.last_heartbeat = time.time()
            
            # Index by type
            if capability.type not in self._by_type:
                self._by_type[capability.type] = set()
            self._by_type[capability.type].add(capability.id)
            
            # Index by triggers
            for trigger in capability.triggers:
                if trigger.event not in self._by_trigger:
                    self._by_trigger[trigger.event] = set()
                self._by_trigger[trigger.event].add(capability.id)
            
            # Index by tools
            for tool in capability.tools:
                if tool.name not in self._by_tool:
                    self._by_tool[tool.name] = set()
                self._by_tool[tool.name].add(capability.id)
            
            logger.info(f"Registered capability: {capability.id} ({capability.type.value})")
    
    async def deregister(self, capability_id: str) -> Optional[Capability]:
        """Deregister a capability. Returns the removed capability."""
        async with self._lock:
            if capability_id not in self._capabilities:
                return None
            
            capability = self._capabilities.pop(capability_id)
            
            # Remove from type index
            if capability.type in self._by_type:
                self._by_type[capability.type].discard(capability_id)
            
            # Remove from trigger index
            for trigger in capability.triggers:
                if trigger.event in self._by_trigger:
                    self._by_trigger[trigger.event].discard(capability_id)
            
            # Remove from tool index
            for tool in capability.tools:
                if tool.name in self._by_tool:
                    self._by_tool[tool.name].discard(capability_id)
            
            # Remove handlers
            for tool in capability.tools:
                handler_key = f"{capability_id}:{tool.name}"
                self._handlers.pop(handler_key, None)
            
            logger.info(f"Deregistered capability: {capability_id}")
            return capability
    
    async def update_heartbeat(self, capability_id: str) -> bool:
        """Update heartbeat timestamp for a capability."""
        if capability_id in self._capabilities:
            self._capabilities[capability_id].last_heartbeat = time.time()
            return True
        return False
    
    def get(self, capability_id: str) -> Optional[Capability]:
        """Get a capability by ID."""
        return self._capabilities.get(capability_id)
    
    def find_by_type(
        self, 
        cap_type: CapabilityType, 
        healthy_only: bool = True
    ) -> List[Capability]:
        """Find capabilities by type."""
        cap_ids = self._by_type.get(cap_type, set())
        capabilities = [self._capabilities[cid] for cid in cap_ids if cid in self._capabilities]
        
        if healthy_only:
            capabilities = [c for c in capabilities if c.is_healthy()]
        
        return capabilities
    
    def find_by_trigger(
        self, 
        event: str, 
        healthy_only: bool = True
    ) -> List[Capability]:
        """Find capabilities that emit a specific trigger event."""
        cap_ids = self._by_trigger.get(event, set())
        capabilities = [self._capabilities[cid] for cid in cap_ids if cid in self._capabilities]
        
        if healthy_only:
            capabilities = [c for c in capabilities if c.is_healthy()]
        
        return capabilities
    
    def find_by_tool(
        self, 
        tool_name: str, 
        healthy_only: bool = True
    ) -> List[Capability]:
        """Find capabilities that have a specific tool."""
        cap_ids = self._by_tool.get(tool_name, set())
        capabilities = [self._capabilities[cid] for cid in cap_ids if cid in self._capabilities]
        
        if healthy_only:
            capabilities = [c for c in capabilities if c.is_healthy()]
        
        return capabilities
    
    def find_by_route_hint(
        self, 
        hint: str, 
        healthy_only: bool = True
    ) -> List[Capability]:
        """
        Find capabilities matching a route hint pattern.
        
        Examples:
        - "security/*" matches AGENT_SECURITY type
        - "llm/*" matches all LLM types
        - "*" matches everything
        """
        results = []
        for cap in self._capabilities.values():
            if healthy_only and not cap.is_healthy():
                continue
            
            type_str = cap.type.value
            if fnmatch.fnmatch(type_str, hint):
                results.append(cap)
        
        return results
    
    def register_handler(
        self, 
        capability_id: str, 
        tool_name: str, 
        handler: Callable
    ) -> None:
        """Register a handler function for a capability's tool."""
        key = f"{capability_id}:{tool_name}"
        self._handlers[key] = handler
    
    def get_handler(
        self, 
        capability_id: str, 
        tool_name: str
    ) -> Optional[Callable]:
        """Get the handler for a capability's tool."""
        key = f"{capability_id}:{tool_name}"
        return self._handlers.get(key)
    
    def list_all(self) -> List[Capability]:
        """List all registered capabilities."""
        return list(self._capabilities.values())
    
    def list_healthy(self) -> List[Capability]:
        """List all healthy capabilities."""
        return [c for c in self._capabilities.values() if c.is_healthy()]
    
    def generate_available_message(self, capability: Capability) -> Dict[str, Any]:
        """Generate a gossip message for capability availability."""
        return GossipMessage.available(capability, self.node_id)
    
    def generate_heartbeat_message(self) -> Dict[str, Any]:
        """Generate a heartbeat gossip message for all local capabilities."""
        local_caps = [c.id for c in self._capabilities.values() if c.node_id == self.node_id]
        return GossipMessage.heartbeat(local_caps, self.node_id)
    
    def generate_unavailable_message(
        self, 
        capability_id: str, 
        reason: str = ""
    ) -> Dict[str, Any]:
        """Generate a gossip message for capability unavailability."""
        return GossipMessage.unavailable(capability_id, self.node_id, reason)
    
    async def process_gossip(self, message: Dict[str, Any]) -> None:
        """Process an incoming gossip message."""
        msg_type = message.get("type")
        
        if msg_type == GossipMessage.CAPABILITY_AVAILABLE:
            cap_data = message.get("capability", {})
            capability = Capability.from_dict(cap_data)
            await self.register(capability)
        
        elif msg_type == GossipMessage.CAPABILITY_HEARTBEAT:
            for cap_id in message.get("capability_ids", []):
                await self.update_heartbeat(cap_id)
        
        elif msg_type == GossipMessage.CAPABILITY_UNAVAILABLE:
            cap_id = message.get("capability_id")
            if cap_id:
                await self.deregister(cap_id)
    
    def stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "total_capabilities": len(self._capabilities),
            "healthy_capabilities": len(self.list_healthy()),
            "by_type": {t.value: len(ids) for t, ids in self._by_type.items()},
            "unique_triggers": len(self._by_trigger),
            "unique_tools": len(self._by_tool),
            "registered_handlers": len(self._handlers),
        }


# Global registry instance
_global_registry: Optional[CapabilityRegistry] = None


def get_registry(node_id: str = "local") -> CapabilityRegistry:
    """Get the global capability registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = CapabilityRegistry(node_id)
    return _global_registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _global_registry
    _global_registry = None
