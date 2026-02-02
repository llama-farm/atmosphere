"""
Base classes for capability system.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


@dataclass
class Capability:
    """
    Represents a capability that a node can provide.
    
    Capabilities are matched to intents using semantic similarity.
    """
    id: str
    label: str
    description: str
    handler: str
    models: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "handler": self.handler,
            "models": self.models,
            "constraints": self.constraints
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Capability":
        return cls(**data)


class CapabilityHandler(ABC):
    """
    Base class for capability handlers.
    
    Implement this to create custom capability handlers.
    """
    
    @property
    @abstractmethod
    def capability_type(self) -> str:
        """Return the capability type (e.g., 'llm', 'vision')."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description for semantic matching."""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the capability with the given arguments."""
        pass
    
    async def health_check(self) -> bool:
        """Check if the capability is available."""
        return True
    
    def to_capability(self, node_id: str) -> Capability:
        """Convert to a Capability object."""
        return Capability(
            id=f"{node_id}:{self.capability_type}",
            label=self.capability_type,
            description=self.description,
            handler=self.__class__.__name__
        )


class CapabilityRegistry:
    """
    Registry for capability handlers.
    
    Usage:
        registry = CapabilityRegistry()
        registry.register(LLMCapability())
        
        handler = registry.get("llm")
        result = await handler.execute(prompt="Hello!")
    """
    
    def __init__(self):
        self._handlers: Dict[str, CapabilityHandler] = {}
        self._factories: Dict[str, Type[CapabilityHandler]] = {}
    
    def register(self, handler: CapabilityHandler) -> None:
        """Register a capability handler."""
        self._handlers[handler.capability_type] = handler
        logger.info(f"Registered capability: {handler.capability_type}")
    
    def register_factory(
        self,
        capability_type: str,
        factory: Type[CapabilityHandler]
    ) -> None:
        """Register a factory for lazy initialization."""
        self._factories[capability_type] = factory
    
    def get(self, capability_type: str) -> Optional[CapabilityHandler]:
        """Get a capability handler by type."""
        if capability_type in self._handlers:
            return self._handlers[capability_type]
        
        # Try lazy initialization
        if capability_type in self._factories:
            handler = self._factories[capability_type]()
            self._handlers[capability_type] = handler
            return handler
        
        return None
    
    def list_capabilities(self) -> List[str]:
        """List all registered capability types."""
        return list(self._handlers.keys()) + list(self._factories.keys())
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all registered capabilities."""
        results = {}
        for name, handler in self._handlers.items():
            try:
                results[name] = await handler.health_check()
            except Exception:
                results[name] = False
        return results


# Global registry
_registry = CapabilityRegistry()


def get_registry() -> CapabilityRegistry:
    """Get the global capability registry."""
    return _registry


def register_capability(handler: CapabilityHandler) -> None:
    """Register a capability handler globally."""
    _registry.register(handler)
