"""Capability registration model."""

from enum import Enum
from typing import Dict, List, Optional
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
    push_events: List[str] = field(default_factory=list)  # Events this capability can emit
    metadata: Optional[Dict] = None            # Additional metadata
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for transmission."""
        return {
            "id": self.id,
            "type": self.type.value if isinstance(self.type, CapabilityType) else self.type,
            "description": self.description,
            "keywords": self.keywords,
            "endpoints": self.endpoints,
            "push_events": self.push_events,
            "metadata": self.metadata or {}
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Capability":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            type=CapabilityType(data["type"]),
            description=data["description"],
            keywords=data["keywords"],
            endpoints=data["endpoints"],
            push_events=data.get("push_events", []),
            metadata=data.get("metadata")
        )
