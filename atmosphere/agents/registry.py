"""
Agent Registry for Atmosphere.

Manages agent lifecycle, discovery, and gossip synchronization.
Agents register here and become discoverable across the mesh.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type, TYPE_CHECKING

from .base import Agent, AgentSpec, AgentState, AgentMessage, MessageType

if TYPE_CHECKING:
    from ..mesh.gossip import GossipProtocol
    from ..router.semantic import SemanticRouter

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    """
    Information about an agent for registry/gossip.
    
    This is the lightweight representation that gets synced
    across the mesh - not the full agent state.
    """
    id: str
    agent_type: str
    node_id: str
    state: str
    description: str
    triggers: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    hops: int = 0
    via_node: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "node_id": self.node_id,
            "state": self.state,
            "description": self.description,
            "triggers": self.triggers,
            "capabilities": self.capabilities,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "hops": self.hops,
            "via_node": self.via_node,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentInfo":
        return cls(
            id=data["id"],
            agent_type=data["agent_type"],
            node_id=data["node_id"],
            state=data.get("state", "unknown"),
            description=data.get("description", ""),
            triggers=data.get("triggers", []),
            capabilities=data.get("capabilities", []),
            parent_id=data.get("parent_id"),
            created_at=data.get("created_at", time.time()),
            last_seen=data.get("last_seen", time.time()),
            hops=data.get("hops", 0),
            via_node=data.get("via_node"),
        )
    
    @classmethod
    def from_agent(cls, agent: Agent, node_id: str) -> "AgentInfo":
        """Create AgentInfo from a running agent."""
        triggers = []
        capabilities = []
        
        if agent.spec:
            triggers = [t.get("name", "") for t in agent.spec.triggers]
            capabilities = agent.spec.tools_required + agent.spec.tools_optional
        
        return cls(
            id=agent.id,
            agent_type=agent.agent_type,
            node_id=node_id,
            state=agent.state.value,
            description=agent.description,
            triggers=triggers,
            capabilities=capabilities,
            parent_id=agent.parent_id,
            created_at=agent.created_at,
            last_seen=time.time(),
            hops=0,
        )


@dataclass
class AgentTypeInfo:
    """
    Information about an agent type (spec) available in the mesh.
    
    These are the "templates" that can be instantiated as agents.
    """
    id: str
    version: str
    description: str
    triggers: List[Dict[str, Any]]
    tools_required: List[str]
    node_id: str  # Where this type is available
    last_seen: float = field(default_factory=time.time)
    hops: int = 0
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "version": self.version,
            "description": self.description,
            "triggers": self.triggers,
            "tools_required": self.tools_required,
            "node_id": self.node_id,
            "last_seen": self.last_seen,
            "hops": self.hops,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentTypeInfo":
        return cls(**data)
    
    @classmethod
    def from_spec(cls, spec: AgentSpec, node_id: str) -> "AgentTypeInfo":
        return cls(
            id=spec.id,
            version=spec.version,
            description=spec.description,
            triggers=spec.triggers,
            tools_required=spec.tools_required,
            node_id=node_id,
        )


class AgentRegistry:
    """
    Registry for agents and agent types.
    
    Responsibilities:
    - Track local running agents
    - Track remote agents (via gossip)
    - Track available agent types (specs)
    - Route messages between agents
    - Spawn new agents
    
    Usage:
        registry = AgentRegistry(node_id="my-node")
        
        # Register a local agent
        await registry.register(my_agent)
        
        # Find agents that can handle an intent
        agents = registry.find_for_intent("analyze_image")
        
        # Spawn a new agent
        agent_id = await registry.spawn("vision_monitor")
    """
    
    def __init__(
        self,
        node_id: str,
        gossip: Optional["GossipProtocol"] = None,
        router: Optional["SemanticRouter"] = None,
    ):
        self.node_id = node_id
        self.gossip = gossip
        self.router = router
        
        # Local agents (running on this node)
        self._local_agents: Dict[str, Agent] = {}
        
        # Remote agent info (from gossip)
        self._remote_agents: Dict[str, AgentInfo] = {}
        
        # Agent type factories (for spawning)
        self._factories: Dict[str, Type[Agent]] = {}
        
        # Agent specs (loaded from YAML)
        self._specs: Dict[str, AgentSpec] = {}
        
        # Available agent types (local + remote)
        self._agent_types: Dict[str, AgentTypeInfo] = {}
        
        # Message routing
        self._message_handlers: Dict[str, Callable] = {}
        
        # Sleeping agents (suspended, can be woken)
        self._sleeping_agents: Dict[str, Dict[str, Any]] = {}
    
    # === Agent Lifecycle ===
    
    async def register(self, agent: Agent) -> None:
        """Register a local agent with the registry."""
        agent.registry = self
        self._local_agents[agent.id] = agent
        
        # Create info for gossip
        info = AgentInfo.from_agent(agent, self.node_id)
        
        logger.info(f"Registered agent: {agent.id} ({agent.agent_type})")
        
        # Announce via gossip if available
        if self.gossip:
            await self._announce_agent(info)
    
    async def unregister(self, agent_id: str) -> None:
        """Unregister an agent."""
        if agent_id in self._local_agents:
            agent = self._local_agents.pop(agent_id)
            logger.info(f"Unregistered agent: {agent_id}")
            
            # Announce removal via gossip
            if self.gossip:
                await self._announce_agent_removed(agent_id)
    
    async def spawn(
        self,
        agent_type: str,
        parent_id: Optional[str] = None,
        initial_intent: Optional[str] = None,
        args: Optional[Dict[str, Any]] = None,
        target_node: Optional[str] = None,
        **config
    ) -> str:
        """
        Spawn a new agent.
        
        Args:
            agent_type: Type of agent to spawn
            parent_id: Parent agent ID (if spawned by another agent)
            initial_intent: Intent to send after spawning
            args: Arguments for initial intent
            target_node: Node to spawn on (None = local)
            **config: Additional configuration
            
        Returns:
            The new agent's ID
        """
        # If target node specified and not local, delegate to that node
        if target_node and target_node != self.node_id:
            return await self._spawn_remote(
                agent_type, parent_id, initial_intent, args, target_node
            )
        
        # Local spawn
        agent_id = config.get("agent_id") or uuid.uuid4().hex[:16]
        
        # Try factory first
        if agent_type in self._factories:
            factory = self._factories[agent_type]
            agent = factory(
                agent_id=agent_id,
                node_id=self.node_id,
                parent_id=parent_id,
                registry=self,
                **config
            )
        # Then try spec
        elif agent_type in self._specs:
            spec = self._specs[agent_type]
            agent = self._create_from_spec(spec, agent_id, parent_id, **config)
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        # Register and start
        await self.register(agent)
        await agent.start()
        
        # Send initial intent if specified
        if initial_intent:
            message = AgentMessage.intent(
                from_agent=parent_id or "system",
                to_agent=agent_id,
                intent=initial_intent,
                args=args or {},
            )
            await agent.receive(message)
        
        return agent_id
    
    async def _spawn_remote(
        self,
        agent_type: str,
        parent_id: Optional[str],
        initial_intent: Optional[str],
        args: Optional[Dict[str, Any]],
        target_node: str,
    ) -> str:
        """Spawn an agent on a remote node."""
        # This would use the mesh to send a spawn request
        # For now, raise not implemented
        raise NotImplementedError("Remote spawn not yet implemented")
    
    def _create_from_spec(
        self,
        spec: AgentSpec,
        agent_id: str,
        parent_id: Optional[str],
        **config
    ) -> Agent:
        """Create an agent from a spec."""
        from .loader import SpecAgent
        
        return SpecAgent(
            agent_id=agent_id,
            spec=spec,
            node_id=self.node_id,
            parent_id=parent_id,
            registry=self,
            **config
        )
    
    async def terminate(self, agent_id: str, reason: str = "terminated") -> bool:
        """Terminate an agent."""
        if agent_id in self._local_agents:
            agent = self._local_agents[agent_id]
            await agent.stop(reason)
            await self.unregister(agent_id)
            return True
        return False
    
    # === Sleep/Wake ===
    
    async def sleep(self, agent_id: str) -> bool:
        """Put an agent to sleep (suspend with state saved)."""
        if agent_id not in self._local_agents:
            return False
        
        agent = self._local_agents[agent_id]
        state = await agent.suspend()
        
        # Store sleeping state
        self._sleeping_agents[agent_id] = {
            "state": state,
            "spec": agent.spec,
            "slept_at": time.time(),
        }
        
        # Remove from active but keep info
        self._local_agents.pop(agent_id)
        
        logger.info(f"Agent {agent_id} is now sleeping")
        return True
    
    async def wake(self, agent_id: str) -> bool:
        """Wake a sleeping agent."""
        if agent_id not in self._sleeping_agents:
            return False
        
        sleep_data = self._sleeping_agents.pop(agent_id)
        state = sleep_data["state"]
        spec = sleep_data["spec"]
        
        # Recreate agent
        if spec:
            agent = self._create_from_spec(
                spec,
                agent_id=agent_id,
                parent_id=state.get("parent_id"),
            )
        else:
            # Can't wake without spec
            logger.error(f"Cannot wake agent {agent_id}: no spec")
            return False
        
        # Restore context and resume
        agent.context = state.get("context", {})
        agent.children = state.get("children", {})
        agent.state = AgentState.SUSPENDED
        
        await self.register(agent)
        await agent.resume(state)
        
        logger.info(f"Agent {agent_id} woke up")
        return True
    
    async def wake_for_intent(self, intent: str) -> Optional[str]:
        """
        Wake any sleeping agent that can handle an intent.
        
        Returns the woken agent's ID, or None if none found.
        """
        for agent_id, sleep_data in list(self._sleeping_agents.items()):
            spec = sleep_data.get("spec")
            if spec:
                # Check if any trigger matches the intent
                for trigger in spec.triggers:
                    trigger_name = trigger.get("name", "")
                    if trigger_name == intent or intent in trigger.get("description", ""):
                        await self.wake(agent_id)
                        return agent_id
        return None
    
    # === Discovery ===
    
    def get(self, agent_id: str) -> Optional[Agent]:
        """Get a local agent by ID."""
        return self._local_agents.get(agent_id)
    
    def get_info(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent info (local or remote)."""
        if agent_id in self._local_agents:
            return AgentInfo.from_agent(
                self._local_agents[agent_id],
                self.node_id
            )
        return self._remote_agents.get(agent_id)
    
    def list_local(self) -> List[Agent]:
        """List all local agents."""
        return list(self._local_agents.values())
    
    def list_all(self) -> List[AgentInfo]:
        """List all known agents (local + remote)."""
        result = []
        
        # Local agents
        for agent in self._local_agents.values():
            result.append(AgentInfo.from_agent(agent, self.node_id))
        
        # Remote agents
        result.extend(self._remote_agents.values())
        
        return result
    
    def list_sleeping(self) -> List[str]:
        """List sleeping agent IDs."""
        return list(self._sleeping_agents.keys())
    
    def find_for_intent(self, intent: str) -> List[AgentInfo]:
        """Find agents that can handle an intent."""
        matches = []
        
        # Check local agents
        for agent in self._local_agents.values():
            if self._can_handle_intent(agent, intent):
                matches.append(AgentInfo.from_agent(agent, self.node_id))
        
        # Check remote agents
        for info in self._remote_agents.values():
            if intent in info.triggers or self._intent_matches_description(intent, info.description):
                matches.append(info)
        
        # Sort by hops (prefer local)
        matches.sort(key=lambda x: x.hops)
        
        return matches
    
    def _can_handle_intent(self, agent: Agent, intent: str) -> bool:
        """Check if an agent can handle an intent."""
        if agent.spec:
            for trigger in agent.spec.triggers:
                if trigger.get("name") == intent:
                    return True
        
        # Check if intent matches description (simple substring for now)
        return self._intent_matches_description(intent, agent.description)
    
    def _intent_matches_description(self, intent: str, description: str) -> bool:
        """Simple intent matching against description."""
        intent_lower = intent.lower().replace("_", " ")
        description_lower = description.lower()
        
        # Direct substring match
        if intent_lower in description_lower:
            return True
        
        # Check if all intent words appear in description
        intent_words = intent_lower.split()
        if all(word in description_lower for word in intent_words):
            return True
        
        # Check word stems (simple: first 4 chars)
        intent_stems = [w[:4] for w in intent_words if len(w) >= 4]
        if intent_stems and all(stem in description_lower for stem in intent_stems):
            return True
        
        return False
    
    # === Type Registration ===
    
    def register_factory(self, agent_type: str, factory: Type[Agent]) -> None:
        """Register an agent factory for a type."""
        self._factories[agent_type] = factory
        logger.info(f"Registered agent factory: {agent_type}")
    
    def register_spec(self, spec: AgentSpec) -> None:
        """Register an agent spec."""
        self._specs[spec.id] = spec
        
        # Also track as available type
        self._agent_types[spec.id] = AgentTypeInfo.from_spec(spec, self.node_id)
        
        logger.info(f"Registered agent spec: {spec.id}")
    
    def get_spec(self, agent_type: str) -> Optional[AgentSpec]:
        """Get an agent spec by type."""
        return self._specs.get(agent_type)
    
    def list_types(self) -> List[str]:
        """List available agent types."""
        return list(set(self._factories.keys()) | set(self._specs.keys()))
    
    # === Message Routing ===
    
    async def route_message(self, message: AgentMessage) -> None:
        """Route a message to its destination."""
        to_agent = message.to_agent
        
        # Broadcast
        if to_agent == "*":
            await self._broadcast_message(message)
            return
        
        # Local agent
        if to_agent in self._local_agents:
            await self._local_agents[to_agent].receive(message)
            return
        
        # Remote agent - need to forward through mesh
        if to_agent in self._remote_agents:
            info = self._remote_agents[to_agent]
            await self._forward_to_node(message, info.node_id)
            return
        
        # Check sleeping agents - might need to wake
        if to_agent in self._sleeping_agents:
            await self.wake(to_agent)
            if to_agent in self._local_agents:
                await self._local_agents[to_agent].receive(message)
                return
        
        logger.warning(f"Cannot route message to unknown agent: {to_agent}")
    
    async def _broadcast_message(self, message: AgentMessage) -> None:
        """Broadcast a message to potential handlers."""
        # For intents, find matching agents
        if message.type == MessageType.INTENT:
            intent = message.payload.get("intent", "")
            
            # Try to wake a sleeping agent first
            woken = await self.wake_for_intent(intent)
            if woken:
                await self._local_agents[woken].receive(message)
                return
            
            # Find active agents
            matches = self.find_for_intent(intent)
            if matches:
                # Route to best match (lowest hops)
                best = matches[0]
                if best.node_id == self.node_id:
                    agent = self._local_agents.get(best.id)
                    if agent:
                        await agent.receive(message)
                        return
                else:
                    await self._forward_to_node(message, best.node_id)
                    return
        
        # Fallback: send to all local agents
        for agent in self._local_agents.values():
            await agent.receive(message)
    
    async def _forward_to_node(self, message: AgentMessage, node_id: str) -> None:
        """Forward a message to another node."""
        # This would use the mesh transport
        # For now, log and skip
        logger.warning(f"Would forward message to node {node_id}")
    
    # === Gossip Integration ===
    
    async def _announce_agent(self, info: AgentInfo) -> None:
        """Announce an agent via gossip."""
        if not self.gossip:
            return
        
        # Add to gossip as capability announcement
        # The gossip protocol needs extension for agents
        logger.debug(f"Would announce agent {info.id} via gossip")
    
    async def _announce_agent_removed(self, agent_id: str) -> None:
        """Announce agent removal via gossip."""
        if not self.gossip:
            return
        logger.debug(f"Would announce agent {agent_id} removal via gossip")
    
    def handle_gossip_agent(self, data: dict) -> None:
        """Handle agent info from gossip."""
        info = AgentInfo.from_dict(data)
        
        # Don't overwrite local agents
        if info.node_id == self.node_id:
            return
        
        # Update or add remote agent
        existing = self._remote_agents.get(info.id)
        if existing is None or info.last_seen > existing.last_seen:
            info.hops = data.get("hops", 0) + 1
            info.via_node = data.get("via_node")
            self._remote_agents[info.id] = info
    
    def handle_gossip_agent_type(self, data: dict) -> None:
        """Handle agent type info from gossip."""
        type_info = AgentTypeInfo.from_dict(data)
        
        # Don't overwrite local types
        if type_info.node_id == self.node_id:
            return
        
        existing = self._agent_types.get(type_info.id)
        if existing is None or type_info.last_seen > existing.last_seen:
            type_info.hops = data.get("hops", 0) + 1
            self._agent_types[type_info.id] = type_info
    
    def export_for_gossip(self) -> List[dict]:
        """Export agent info for gossip announcements."""
        result = []
        
        # Local agents
        for agent in self._local_agents.values():
            info = AgentInfo.from_agent(agent, self.node_id)
            result.append(info.to_dict())
        
        # Agent types
        for type_info in self._agent_types.values():
            if type_info.node_id == self.node_id:
                result.append({
                    "type": "agent_type",
                    **type_info.to_dict()
                })
        
        return result
    
    # === Persistence ===
    
    def save(self, path: Path) -> None:
        """Save registry state to disk."""
        data = {
            "node_id": self.node_id,
            "specs": {k: v.to_dict() for k, v in self._specs.items()},
            "sleeping_agents": self._sleeping_agents,
            "agent_types": {k: v.to_dict() for k, v in self._agent_types.items()},
        }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: Path, node_id: str) -> "AgentRegistry":
        """Load registry state from disk."""
        registry = cls(node_id=node_id)
        
        if not path.exists():
            return registry
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        # Load specs
        for spec_data in data.get("specs", {}).values():
            spec = AgentSpec.from_dict(spec_data)
            registry.register_spec(spec)
        
        # Load sleeping agents
        registry._sleeping_agents = data.get("sleeping_agents", {})
        
        return registry
    
    def stats(self) -> dict:
        """Get registry statistics."""
        return {
            "local_agents": len(self._local_agents),
            "remote_agents": len(self._remote_agents),
            "sleeping_agents": len(self._sleeping_agents),
            "agent_types": len(self._agent_types),
            "specs": len(self._specs),
            "factories": len(self._factories),
        }


# Global registry
_registry: Optional[AgentRegistry] = None


def get_registry() -> Optional[AgentRegistry]:
    """Get the global agent registry."""
    return _registry


def set_registry(registry: AgentRegistry) -> None:
    """Set the global agent registry."""
    global _registry
    _registry = registry


def reset_registry() -> None:
    """Reset the global agent registry."""
    global _registry
    _registry = None
