"""Capability registration model."""

from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict


class CapabilityType(str, Enum):
    """Capability type enum."""
    APP_QUERY = "app/query"        # Read data from an app
    APP_ACTION = "app/action"      # Trigger actions (approve, resolve, etc.)
    APP_STREAM = "app/stream"      # Subscribe to real-time events
    APP_CHAT = "app/chat"          # Natural language interface to an app


@dataclass
class EndpointSpec:
    """Specification for an API endpoint."""
    method: str                     # HTTP method (GET, POST, PUT, DELETE)
    path: str                       # Endpoint path
    description: str                # Human-readable description
    params: Optional[Dict] = None   # Optional parameter schema
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "method": self.method,
            "path": self.path,
            "description": self.description,
            "params": self.params or {}
        }


@dataclass
class ToolParam:
    """Parameter specification for a tool."""
    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None

    def to_dict(self) -> Dict:
        d = {"name": self.name, "type": self.type, "description": self.description, "required": self.required}
        if self.default is not None:
            d["default"] = self.default
        if self.enum is not None:
            d["enum"] = self.enum
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> "ToolParam":
        return cls(
            name=data["name"],
            type=data.get("type", "string"),
            description=data.get("description", ""),
            required=data.get("required", True),
            default=data.get("default"),
            enum=data.get("enum"),
        )


@dataclass
class ToolSpec:
    """
    Tool/function specification — the primary abstraction for app capabilities.
    
    Each tool maps to an underlying HTTP endpoint but presents a clean
    function-calling interface (like OpenAI function calling).
    """
    name: str                        # e.g., "scan_anomalies"
    description: str                 # What it does (for LLM/human consumption)
    parameters: List[ToolParam]      # Input params
    returns: str                     # Description of return value
    endpoint: EndpointSpec           # The underlying HTTP endpoint
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "returns": self.returns,
            "endpoint": self.endpoint.to_dict(),
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ToolSpec":
        ep_data = data.get("endpoint", {})
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            parameters=[ToolParam.from_dict(p) for p in data.get("parameters", [])],
            returns=data.get("returns", ""),
            endpoint=EndpointSpec(
                method=ep_data.get("method", "GET"),
                path=ep_data.get("path", ""),
                description=ep_data.get("description", ""),
                params=ep_data.get("params"),
            ),
            tags=data.get("tags", []),
        )

    def to_openai_function(self) -> Dict:
        """Convert to OpenAI function-calling format."""
        properties = {}
        required = []
        for p in self.parameters:
            prop: Dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


@dataclass
class Capability:
    """
    Application capability registration.
    
    Describes what an application can do and how to access it.
    """
    id: str                                    # Unique capability ID (e.g., "app/horizon/anomaly")
    type: CapabilityType                       # Capability type
    description: str                            # Human-readable description
    keywords: List[str]                        # Keywords for semantic routing
    endpoints: Dict[str, Dict]                 # Endpoint name -> spec
    tools: Dict[str, ToolSpec] = field(default_factory=dict)  # Tool name -> spec
    push_events: List[str] = field(default_factory=list)  # Events this capability can emit
    metadata: Optional[Dict] = None            # Additional metadata
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for transmission."""
        d = {
            "id": self.id,
            "type": self.type.value if isinstance(self.type, CapabilityType) else self.type,
            "description": self.description,
            "keywords": self.keywords,
            "endpoints": self.endpoints,
            "push_events": self.push_events,
            "metadata": self.metadata or {}
        }
        if self.tools:
            d["tools"] = {name: tool.to_dict() for name, tool in self.tools.items()}
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Capability":
        """Create from dictionary."""
        tools = {}
        for name, tdata in data.get("tools", {}).items():
            if isinstance(tdata, dict):
                tdata.setdefault("name", name)
                tools[name] = ToolSpec.from_dict(tdata)
        return cls(
            id=data["id"],
            type=CapabilityType(data["type"]),
            description=data["description"],
            keywords=data["keywords"],
            endpoints=data["endpoints"],
            tools=tools,
            push_events=data.get("push_events", []),
            metadata=data.get("metadata")
        )
