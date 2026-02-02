"""
Base agent implementation for Atmosphere.

Agents are stateful entities with lifecycle management, message handling,
and the ability to spawn children and invoke tools.
"""

import asyncio
import inspect
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .registry import AgentRegistry

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent lifecycle states."""
    CREATED = "created"
    RUNNING = "running"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class MessageType(Enum):
    """Types of agent messages."""
    INTENT = "intent"
    RESULT = "result"
    EVENT = "event"
    CONTROL = "control"


@dataclass
class AgentMessage:
    """Message envelope for agent communication."""
    id: str
    type: MessageType
    from_agent: str
    to_agent: str
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    ttl_hops: int = 10
    priority: int = 5  # 0-9, higher = more urgent
    via_node: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "ttl_hops": self.ttl_hops,
            "priority": self.priority,
            "via_node": self.via_node,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentMessage":
        return cls(
            id=data["id"],
            type=MessageType(data["type"]),
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            payload=data["payload"],
            timestamp=data.get("timestamp", time.time()),
            ttl_hops=data.get("ttl_hops", 10),
            priority=data.get("priority", 5),
            via_node=data.get("via_node"),
        )
    
    @classmethod
    def intent(
        cls,
        from_agent: str,
        to_agent: str,
        intent: str,
        args: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> "AgentMessage":
        """Create an intent message."""
        return cls(
            id=uuid.uuid4().hex[:16],
            type=MessageType.INTENT,
            from_agent=from_agent,
            to_agent=to_agent,
            payload={"intent": intent, "args": args or {}},
            **kwargs
        )
    
    @classmethod
    def result(
        cls,
        from_agent: str,
        to_agent: str,
        request_id: str,
        status: str,
        data: Any = None,
        error: Optional[str] = None,
        **kwargs
    ) -> "AgentMessage":
        """Create a result message."""
        return cls(
            id=uuid.uuid4().hex[:16],
            type=MessageType.RESULT,
            from_agent=from_agent,
            to_agent=to_agent,
            payload={
                "request_id": request_id,
                "status": status,
                "data": data,
                "error": error,
            },
            **kwargs
        )


@dataclass
class AgentSpec:
    """
    Agent specification - the template for creating agents.
    
    This is what gets gossiped around the mesh. Actual running
    agents are instances created from specs.
    """
    id: str
    type: str
    version: str
    description: str
    triggers: List[Dict[str, Any]] = field(default_factory=list)
    tools_required: List[str] = field(default_factory=list)
    tools_optional: List[str] = field(default_factory=list)
    default_params: Dict[str, Any] = field(default_factory=dict)
    instructions: str = ""
    resource_profile: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "version": self.version,
            "description": self.description,
            "triggers": self.triggers,
            "tools_required": self.tools_required,
            "tools_optional": self.tools_optional,
            "default_params": self.default_params,
            "instructions": self.instructions,
            "resource_profile": self.resource_profile,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentSpec":
        return cls(
            id=data["id"],
            type=data.get("type", "reactive"),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            triggers=data.get("triggers", []),
            tools_required=data.get("tools_required", []),
            tools_optional=data.get("tools_optional", []),
            default_params=data.get("default_params", {}),
            instructions=data.get("instructions", ""),
            resource_profile=data.get("resource_profile", {}),
        )


class Agent(ABC):
    """
    Base class for Atmosphere agents.
    
    Agents are stateful entities that:
    - Receive intents or events
    - Make decisions about how to fulfill them
    - Take actions (invoke tools, spawn children, emit intents)
    - Report results
    
    Subclass this to create custom agents. Override:
    - handle_intent() for processing incoming intents
    - on_start() / on_stop() for lifecycle hooks
    """
    
    def __init__(
        self,
        agent_id: Optional[str] = None,
        spec: Optional[AgentSpec] = None,
        node_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        registry: Optional["AgentRegistry"] = None,
    ):
        self.id = agent_id or uuid.uuid4().hex[:16]
        self.spec = spec
        self.node_id = node_id or "local"
        self.parent_id = parent_id
        self.registry = registry
        
        # Lifecycle
        self.state = AgentState.CREATED
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.stopped_at: Optional[float] = None
        
        # State
        self.context: Dict[str, Any] = {}
        self.children: Dict[str, str] = {}  # child_id -> state
        self._pending_results: Dict[str, asyncio.Future] = {}
        
        # Communication
        self._inbox: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Metrics
        self._messages_received = 0
        self._messages_sent = 0
        self._intents_handled = 0
        self._errors = 0
    
    @property
    def agent_type(self) -> str:
        """Return the agent type from spec or class name."""
        if self.spec:
            return self.spec.type
        return self.__class__.__name__.lower().replace("agent", "")
    
    @property
    def description(self) -> str:
        """Return agent description for semantic matching."""
        if self.spec:
            return self.spec.description
        return self.__doc__ or ""
    
    @property
    def is_running(self) -> bool:
        return self.state == AgentState.RUNNING
    
    @property
    def is_sleeping(self) -> bool:
        return self.state == AgentState.SUSPENDED
    
    # === Lifecycle ===
    
    async def start(self) -> None:
        """Start the agent's main loop."""
        if self.state == AgentState.RUNNING:
            return
        
        self.state = AgentState.RUNNING
        self.started_at = time.time()
        self._running = True
        
        logger.info(f"Agent {self.id} starting ({self.agent_type})")
        
        try:
            await self.on_start()
            self._task = asyncio.create_task(self._run_loop())
        except Exception as e:
            logger.error(f"Agent {self.id} failed to start: {e}")
            self.state = AgentState.TERMINATED
            self._running = False
            raise
    
    async def stop(self, reason: str = "stopped") -> None:
        """Stop the agent gracefully."""
        if self.state == AgentState.TERMINATED:
            return
        
        logger.info(f"Agent {self.id} stopping: {reason}")
        
        self._running = False
        self.state = AgentState.TERMINATED
        self.stopped_at = time.time()
        
        # Cancel the run loop
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        await self.on_stop()
    
    async def suspend(self) -> Dict[str, Any]:
        """
        Suspend the agent, returning serialized state.
        
        The agent can be resumed later with resume().
        Returns the state needed to restore the agent.
        """
        if self.state != AgentState.RUNNING:
            raise RuntimeError(f"Cannot suspend agent in state {self.state}")
        
        logger.info(f"Agent {self.id} suspending")
        
        self._running = False
        self.state = AgentState.SUSPENDED
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        # Serialize state for potential migration
        state = {
            "id": self.id,
            "spec": self.spec.to_dict() if self.spec else None,
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "context": self.context,
            "children": self.children,
            "created_at": self.created_at,
            "started_at": self.started_at,
        }
        
        return state
    
    async def resume(self, state: Optional[Dict[str, Any]] = None) -> None:
        """Resume a suspended agent, optionally restoring state."""
        if self.state != AgentState.SUSPENDED:
            raise RuntimeError(f"Cannot resume agent in state {self.state}")
        
        if state:
            self.context = state.get("context", self.context)
            self.children = state.get("children", self.children)
        
        logger.info(f"Agent {self.id} resuming")
        
        self.state = AgentState.RUNNING
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
    
    async def _run_loop(self) -> None:
        """Main agent loop - process messages from inbox."""
        while self._running:
            try:
                # Wait for message with timeout (for heartbeat)
                try:
                    message = await asyncio.wait_for(
                        self._inbox.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # Heartbeat interval - can add periodic tasks here
                    continue
                
                self._messages_received += 1
                await self._handle_message(message)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._errors += 1
                logger.error(f"Agent {self.id} error in run loop: {e}")
                await self.on_error(e)
    
    async def _handle_message(self, message: AgentMessage) -> None:
        """Route message to appropriate handler."""
        try:
            if message.type == MessageType.INTENT:
                self._intents_handled += 1
                result = await self.handle_intent(
                    message.payload["intent"],
                    message.payload.get("args", {})
                )
                # Send result back
                response = AgentMessage.result(
                    from_agent=self.id,
                    to_agent=message.from_agent,
                    request_id=message.id,
                    status="success",
                    data=result,
                )
                await self._send_message(response)
                
            elif message.type == MessageType.RESULT:
                # Result from a child or tool invocation
                request_id = message.payload.get("request_id")
                if request_id in self._pending_results:
                    future = self._pending_results.pop(request_id)
                    if message.payload.get("status") == "success":
                        future.set_result(message.payload.get("data"))
                    else:
                        future.set_exception(
                            RuntimeError(message.payload.get("error", "Unknown error"))
                        )
                
            elif message.type == MessageType.EVENT:
                await self.on_event(
                    message.payload.get("event", "unknown"),
                    message.payload.get("data", {})
                )
                
            elif message.type == MessageType.CONTROL:
                await self._handle_control(message.payload.get("command", ""))
                
        except Exception as e:
            self._errors += 1
            logger.error(f"Agent {self.id} error handling message: {e}")
            
            # Send error result if this was an intent
            if message.type == MessageType.INTENT:
                response = AgentMessage.result(
                    from_agent=self.id,
                    to_agent=message.from_agent,
                    request_id=message.id,
                    status="error",
                    error=str(e),
                )
                await self._send_message(response)
    
    async def _handle_control(self, command: str) -> None:
        """Handle control commands."""
        if command == "suspend":
            await self.suspend()
        elif command == "terminate":
            await self.stop("terminated by control message")
        elif command == "ping":
            logger.debug(f"Agent {self.id} received ping")
    
    async def _send_message(self, message: AgentMessage) -> None:
        """Send a message to another agent."""
        self._messages_sent += 1
        
        if self.registry:
            await self.registry.route_message(message)
        else:
            logger.warning(f"Agent {self.id} has no registry, cannot send message")
    
    # === Public API ===
    
    async def receive(self, message: AgentMessage) -> None:
        """Receive a message into the agent's inbox."""
        await self._inbox.put(message)
    
    async def invoke(self, intent: str, args: Optional[Dict[str, Any]] = None) -> Any:
        """
        Invoke an intent and wait for the result.
        
        This routes through the mesh to find the best handler.
        """
        message = AgentMessage.intent(
            from_agent=self.id,
            to_agent="*",  # Broadcast - let mesh route
            intent=intent,
            args=args or {},
        )
        
        # Create future for result
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_results[message.id] = future
        
        await self._send_message(message)
        
        # Wait for result (with timeout)
        try:
            return await asyncio.wait_for(future, timeout=60.0)
        except asyncio.TimeoutError:
            self._pending_results.pop(message.id, None)
            raise TimeoutError(f"Intent '{intent}' timed out")
    
    async def spawn_child(
        self,
        agent_type: str,
        initial_intent: Optional[str] = None,
        args: Optional[Dict[str, Any]] = None,
        **config
    ) -> str:
        """
        Spawn a child agent.
        
        Returns the child's agent ID.
        """
        if not self.registry:
            raise RuntimeError("Cannot spawn child without registry")
        
        child_id = await self.registry.spawn(
            agent_type=agent_type,
            parent_id=self.id,
            initial_intent=initial_intent,
            args=args,
            **config
        )
        
        self.children[child_id] = "running"
        return child_id
    
    async def emit_event(self, event: str, data: Dict[str, Any]) -> None:
        """Emit an event to the mesh (fire-and-forget)."""
        message = AgentMessage(
            id=uuid.uuid4().hex[:16],
            type=MessageType.EVENT,
            from_agent=self.id,
            to_agent="*",
            payload={"event": event, "data": data},
        )
        await self._send_message(message)
    
    # === Override these in subclasses ===
    
    async def on_start(self) -> None:
        """Called when the agent starts. Override for initialization."""
        pass
    
    async def on_stop(self) -> None:
        """Called when the agent stops. Override for cleanup."""
        pass
    
    async def on_error(self, error: Exception) -> None:
        """Called on unhandled errors. Override for custom error handling."""
        pass
    
    async def on_event(self, event: str, data: Dict[str, Any]) -> None:
        """Called when an event is received. Override to handle events."""
        pass
    
    @abstractmethod
    async def handle_intent(self, intent: str, args: Dict[str, Any]) -> Any:
        """
        Handle an incoming intent.
        
        This is the main entry point for agent logic. Override this
        to implement your agent's behavior.
        
        Args:
            intent: The intent string (e.g., "analyze_image", "send_notification")
            args: Arguments for the intent
            
        Returns:
            The result of handling the intent
        """
        raise NotImplementedError
    
    # === Serialization ===
    
    def to_dict(self) -> dict:
        """Serialize agent state for gossip/storage."""
        return {
            "id": self.id,
            "type": self.agent_type,
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "state": self.state.value,
            "spec": self.spec.to_dict() if self.spec else None,
            "context": self.context,
            "children": self.children,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "metrics": {
                "messages_received": self._messages_received,
                "messages_sent": self._messages_sent,
                "intents_handled": self._intents_handled,
                "errors": self._errors,
            },
        }
    
    def stats(self) -> dict:
        """Get agent statistics."""
        return {
            "id": self.id,
            "type": self.agent_type,
            "state": self.state.value,
            "uptime_sec": time.time() - self.started_at if self.started_at else 0,
            "messages_received": self._messages_received,
            "messages_sent": self._messages_sent,
            "intents_handled": self._intents_handled,
            "errors": self._errors,
            "children": len(self.children),
            "inbox_size": self._inbox.qsize(),
        }


class ReactiveAgent(Agent):
    """
    A simple reactive agent that responds to intents with rule-based logic.
    
    This is the lightest-weight agent type - suitable for simple
    event → action patterns without complex state.
    """
    
    def __init__(self, rules: Optional[Dict[str, Callable]] = None, **kwargs):
        super().__init__(**kwargs)
        self.rules = rules or {}
    
    def add_rule(self, intent: str, handler: Callable) -> None:
        """Add a rule for handling an intent."""
        self.rules[intent] = handler
    
    async def handle_intent(self, intent: str, args: Dict[str, Any]) -> Any:
        """Handle intent using registered rules."""
        if intent in self.rules:
            handler = self.rules[intent]
            if inspect.iscoroutinefunction(handler):
                return await handler(args)
            return handler(args)
        
        raise ValueError(f"No rule registered for intent: {intent}")


class DelegatingAgent(Agent):
    """
    An agent that delegates work to child agents or tools.
    
    This is the base for orchestrator-style agents that coordinate
    multiple sub-tasks.
    """
    
    async def delegate(
        self,
        intent: str,
        args: Optional[Dict[str, Any]] = None,
        agent_type: Optional[str] = None,
    ) -> Any:
        """
        Delegate an intent to another agent or tool.
        
        If agent_type is specified, spawns that type of agent.
        Otherwise, routes through the mesh.
        """
        if agent_type:
            # Spawn a specific agent type
            child_id = await self.spawn_child(
                agent_type=agent_type,
                initial_intent=intent,
                args=args,
            )
            # Wait for result
            return await self._wait_for_child(child_id)
        else:
            # Route through mesh
            return await self.invoke(intent, args)
    
    async def _wait_for_child(self, child_id: str, timeout: float = 60.0) -> Any:
        """Wait for a child agent to complete."""
        # This would be implemented with the registry
        raise NotImplementedError("Child waiting requires registry integration")
    
    @abstractmethod
    async def handle_intent(self, intent: str, args: Dict[str, Any]) -> Any:
        raise NotImplementedError
