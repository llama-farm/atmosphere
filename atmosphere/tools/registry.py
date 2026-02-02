"""
Tool Registry for Atmosphere.

Manages tool discovery, registration, and gossip synchronization.
Tools register here and become invocable across the mesh.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type, TYPE_CHECKING

from .base import Tool, ToolSpec, ToolResult, ToolContext, ToolError, ToolNotFoundError

if TYPE_CHECKING:
    from ..mesh.gossip import GossipProtocol

logger = logging.getLogger(__name__)


@dataclass
class ToolInfo:
    """
    Information about a tool for registry/gossip.
    
    This is the lightweight representation that gets synced
    across the mesh - not the full implementation.
    """
    name: str
    namespace: str
    version: str
    description: str
    node_id: str
    
    # Parameters summary
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    
    # Requirements
    capabilities_required: List[str] = field(default_factory=list)
    permissions_required: List[str] = field(default_factory=list)
    
    # Metadata
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    
    # Gossip info
    last_seen: float = field(default_factory=time.time)
    hops: int = 0
    via_node: Optional[str] = None
    
    @property
    def full_name(self) -> str:
        return f"{self.namespace}:{self.name}"
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "version": self.version,
            "description": self.description,
            "node_id": self.node_id,
            "parameters": self.parameters,
            "capabilities_required": self.capabilities_required,
            "permissions_required": self.permissions_required,
            "category": self.category,
            "tags": self.tags,
            "last_seen": self.last_seen,
            "hops": self.hops,
            "via_node": self.via_node,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ToolInfo":
        return cls(
            name=data["name"],
            namespace=data.get("namespace", "core"),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            node_id=data["node_id"],
            parameters=data.get("parameters", []),
            capabilities_required=data.get("capabilities_required", []),
            permissions_required=data.get("permissions_required", []),
            category=data.get("category", "general"),
            tags=data.get("tags", []),
            last_seen=data.get("last_seen", time.time()),
            hops=data.get("hops", 0),
            via_node=data.get("via_node"),
        )
    
    @classmethod
    def from_tool(cls, tool: Tool, node_id: str) -> "ToolInfo":
        """Create ToolInfo from a Tool instance."""
        return cls(
            name=tool.spec.name,
            namespace=tool.spec.namespace,
            version=tool.spec.version,
            description=tool.spec.description,
            node_id=node_id,
            parameters=[
                {"name": p.name, "type": p.type, "required": p.required}
                for p in tool.spec.parameters
            ],
            capabilities_required=tool.spec.capabilities_required,
            permissions_required=tool.spec.permissions_required,
            category=tool.spec.category,
            tags=tool.spec.tags,
        )


class ToolRegistry:
    """
    Registry for tools.
    
    Responsibilities:
    - Track local tools
    - Track remote tools (via gossip)
    - Route tool invocations
    - Handle remote execution
    
    Usage:
        registry = ToolRegistry(node_id="my-node")
        
        # Register a local tool
        registry.register(MyTool())
        
        # Find tools by name
        tool = registry.get("notify")
        
        # Execute a tool
        result = await registry.execute("notify", {"message": "Hello"})
    """
    
    def __init__(
        self,
        node_id: str,
        gossip: Optional["GossipProtocol"] = None,
    ):
        self.node_id = node_id
        self.gossip = gossip
        
        # Local tools (implementations on this node)
        self._local_tools: Dict[str, Tool] = {}
        
        # Remote tool info (from gossip)
        self._remote_tools: Dict[str, ToolInfo] = {}
        
        # Tool factories for lazy instantiation
        self._factories: Dict[str, Type[Tool]] = {}
    
    # === Registration ===
    
    def register(self, tool: Tool) -> None:
        """Register a local tool."""
        tool.registry = self
        key = tool.full_name
        self._local_tools[key] = tool
        
        logger.info(f"Registered tool: {key}")
        
        # Announce via gossip
        if self.gossip:
            self._announce_tool(tool)
    
    def register_class(self, tool_class: Type[Tool]) -> None:
        """Register a tool class for lazy instantiation."""
        spec = tool_class.spec
        key = f"{spec.namespace}:{spec.name}"
        self._factories[key] = tool_class
        logger.info(f"Registered tool factory: {key}")
    
    def unregister(self, tool_name: str) -> None:
        """Unregister a tool."""
        # Try full name first
        if tool_name in self._local_tools:
            del self._local_tools[tool_name]
            logger.info(f"Unregistered tool: {tool_name}")
            return
        
        # Try short name
        for key in list(self._local_tools.keys()):
            if key.endswith(f":{tool_name}"):
                del self._local_tools[key]
                logger.info(f"Unregistered tool: {key}")
                return
    
    # === Lookup ===
    
    def get(self, name: str) -> Optional[Tool]:
        """Get a local tool by name."""
        # Try exact match
        if name in self._local_tools:
            return self._local_tools[name]
        
        # Try without namespace
        for key, tool in self._local_tools.items():
            if key.endswith(f":{name}") or tool.name == name:
                return tool
        
        # Try factory
        for key, factory in self._factories.items():
            if key.endswith(f":{name}") or key == name:
                tool = factory(registry=self)
                self._local_tools[key] = tool
                return tool
        
        return None
    
    def get_info(self, name: str) -> Optional[ToolInfo]:
        """Get tool info (local or remote)."""
        # Check local first
        tool = self.get(name)
        if tool:
            return ToolInfo.from_tool(tool, self.node_id)
        
        # Check remote
        if name in self._remote_tools:
            return self._remote_tools[name]
        
        # Try without namespace
        for key, info in self._remote_tools.items():
            if key.endswith(f":{name}") or info.name == name:
                return info
        
        return None
    
    def list_local(self) -> List[Tool]:
        """List all local tools."""
        return list(self._local_tools.values())
    
    def list_all(self) -> List[ToolInfo]:
        """List all known tools (local + remote)."""
        result = []
        
        # Local tools
        for tool in self._local_tools.values():
            result.append(ToolInfo.from_tool(tool, self.node_id))
        
        # Remote tools
        result.extend(self._remote_tools.values())
        
        return result
    
    def list_names(self) -> List[str]:
        """List all tool names."""
        names = set()
        
        for tool in self._local_tools.values():
            names.add(tool.full_name)
        
        for info in self._remote_tools.values():
            names.add(info.full_name)
        
        return sorted(names)
    
    def find_by_capability(self, capability: str) -> List[ToolInfo]:
        """Find tools that require a specific capability."""
        result = []
        
        for tool in self._local_tools.values():
            if capability in tool.spec.capabilities_required:
                result.append(ToolInfo.from_tool(tool, self.node_id))
        
        for info in self._remote_tools.values():
            if capability in info.capabilities_required:
                result.append(info)
        
        return result
    
    def find_by_category(self, category: str) -> List[ToolInfo]:
        """Find tools in a category."""
        result = []
        
        for tool in self._local_tools.values():
            if tool.spec.category == category:
                result.append(ToolInfo.from_tool(tool, self.node_id))
        
        for info in self._remote_tools.values():
            if info.category == category:
                result.append(info)
        
        return result
    
    # === Execution ===
    
    async def execute(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        """
        Execute a tool by name.
        
        If the tool is local, executes directly.
        If remote, forwards to the appropriate node.
        """
        context = context or ToolContext(node_id=self.node_id)
        
        # Try local first
        tool = self.get(tool_name)
        if tool:
            return await tool.run(params, context)
        
        # Check if available remotely
        info = self.get_info(tool_name)
        if info and info.node_id != self.node_id:
            return await self._execute_remote(info, params, context)
        
        return ToolResult.fail(
            f"Tool not found: {tool_name}",
            code="TOOL_NOT_FOUND"
        )
    
    async def _execute_remote(
        self,
        info: ToolInfo,
        params: Dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute a tool on a remote node."""
        # This would use the mesh to forward the request
        # For now, return not implemented
        return ToolResult.fail(
            f"Remote tool execution not yet implemented: {info.full_name} on {info.node_id}",
            code="NOT_IMPLEMENTED"
        )
    
    # === Gossip ===
    
    def _announce_tool(self, tool: Tool) -> None:
        """Announce a tool via gossip."""
        if not self.gossip:
            return
        
        info = ToolInfo.from_tool(tool, self.node_id)
        logger.debug(f"Would announce tool {info.full_name} via gossip")
    
    def handle_gossip_tool(self, data: dict) -> None:
        """Handle tool info from gossip."""
        info = ToolInfo.from_dict(data)
        
        # Don't overwrite local tools
        if info.node_id == self.node_id:
            return
        
        # Update or add remote tool
        key = info.full_name
        existing = self._remote_tools.get(key)
        
        if existing is None or info.last_seen > existing.last_seen:
            info.hops = data.get("hops", 0) + 1
            info.via_node = data.get("via_node")
            self._remote_tools[key] = info
    
    def export_for_gossip(self) -> List[dict]:
        """Export tool info for gossip announcements."""
        result = []
        
        for tool in self._local_tools.values():
            info = ToolInfo.from_tool(tool, self.node_id)
            result.append(info.to_dict())
        
        return result
    
    # === Persistence ===
    
    def save(self, path: Path) -> None:
        """Save registry state to disk."""
        data = {
            "node_id": self.node_id,
            "tools": [
                ToolInfo.from_tool(t, self.node_id).to_dict()
                for t in self._local_tools.values()
            ],
        }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: Path, node_id: str) -> "ToolRegistry":
        """Load registry state from disk."""
        registry = cls(node_id=node_id)
        
        if not path.exists():
            return registry
        
        # Note: We can't restore actual tool implementations from disk
        # Only the info. Tools need to be re-registered.
        
        return registry
    
    def stats(self) -> dict:
        """Get registry statistics."""
        return {
            "local_tools": len(self._local_tools),
            "remote_tools": len(self._remote_tools),
            "factories": len(self._factories),
        }


# Global registry
_registry: Optional[ToolRegistry] = None


def get_registry() -> Optional[ToolRegistry]:
    """Get the global tool registry."""
    return _registry


def set_registry(registry: ToolRegistry) -> None:
    """Set the global tool registry."""
    global _registry
    _registry = registry


def reset_registry() -> None:
    """Reset the global tool registry."""
    global _registry
    _registry = None
