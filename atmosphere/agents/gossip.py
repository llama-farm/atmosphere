"""
Gossip integration for the Agent Registry.

Extends the gossip protocol to propagate agent information across the mesh.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..mesh.gossip import GossipProtocol
    from .registry import AgentRegistry, AgentInfo, AgentTypeInfo

logger = logging.getLogger(__name__)


@dataclass
class AgentAnnouncement:
    """Announcement of agents from a node."""
    type: str = "agent_announce"
    from_node: str = ""
    agents: List[Dict[str, Any]] = field(default_factory=list)
    agent_types: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    ttl: int = 10
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "from_node": self.from_node,
            "agents": self.agents,
            "agent_types": self.agent_types,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentAnnouncement":
        return cls(
            type=data.get("type", "agent_announce"),
            from_node=data.get("from_node", ""),
            agents=data.get("agents", []),
            agent_types=data.get("agent_types", []),
            timestamp=data.get("timestamp", time.time()),
            ttl=data.get("ttl", 10),
        )


class AgentGossip:
    """
    Gossip extension for agent propagation.
    
    This class bridges the agent registry with the gossip protocol,
    announcing local agents and processing announcements from peers.
    """
    
    def __init__(
        self,
        node_id: str,
        registry: "AgentRegistry",
        gossip: Optional["GossipProtocol"] = None,
    ):
        self.node_id = node_id
        self.registry = registry
        self.gossip = gossip
        
        # Hook into registry if gossip is available
        if gossip:
            self._setup_gossip_hooks()
    
    def _setup_gossip_hooks(self) -> None:
        """Set up hooks into the gossip protocol."""
        # The gossip protocol would need to be extended to support
        # custom message types. For now, we'll build announcements
        # that can be included in the existing capability announcements.
        pass
    
    def build_announcement(self) -> AgentAnnouncement:
        """Build an agent announcement for gossip."""
        agents = []
        agent_types = []
        
        # Add local running agents
        for agent in self.registry.list_local():
            from .registry import AgentInfo
            info = AgentInfo.from_agent(agent, self.node_id)
            agents.append(info.to_dict())
        
        # Add available agent types
        for type_id in self.registry.list_types():
            spec = self.registry.get_spec(type_id)
            if spec:
                agent_types.append({
                    "id": spec.id,
                    "version": spec.version,
                    "description": spec.description,
                    "triggers": [t.get("name", "") for t in spec.triggers],
                    "node_id": self.node_id,
                })
        
        return AgentAnnouncement(
            from_node=self.node_id,
            agents=agents,
            agent_types=agent_types,
        )
    
    def handle_announcement(self, data: dict) -> None:
        """Handle an agent announcement from a peer."""
        announcement = AgentAnnouncement.from_dict(data)
        
        # Skip our own announcements
        if announcement.from_node == self.node_id:
            return
        
        # Process agents
        for agent_data in announcement.agents:
            agent_data["hops"] = agent_data.get("hops", 0) + 1
            agent_data["via_node"] = announcement.from_node
            self.registry.handle_gossip_agent(agent_data)
        
        # Process agent types
        for type_data in announcement.agent_types:
            type_data["hops"] = type_data.get("hops", 0) + 1
            self.registry.handle_gossip_agent_type(type_data)
    
    def export_for_capability_announcement(self) -> List[Dict[str, Any]]:
        """
        Export agent info in a format that can be included with
        capability announcements.
        
        This allows agents to piggyback on the existing gossip
        infrastructure without requiring protocol changes.
        """
        result = []
        
        # Agents as "capabilities" with special type
        for agent in self.registry.list_local():
            from .registry import AgentInfo
            info = AgentInfo.from_agent(agent, self.node_id)
            
            result.append({
                "type": "agent",
                "agent_id": info.id,
                "agent_type": info.agent_type,
                "description": info.description,
                "triggers": info.triggers,
                "state": info.state,
            })
        
        return result


def integrate_with_gossip(
    registry: "AgentRegistry",
    gossip: "GossipProtocol",
    node_id: str,
) -> AgentGossip:
    """
    Integrate an agent registry with the gossip protocol.
    
    Returns an AgentGossip instance that handles propagation.
    """
    agent_gossip = AgentGossip(node_id, registry, gossip)
    
    # Store reference in registry
    registry._agent_gossip = agent_gossip
    
    return agent_gossip
