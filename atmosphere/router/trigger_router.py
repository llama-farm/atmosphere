"""
Trigger Router for Atmosphere.

Handles the PUSH side of capabilities - routing events from triggers
to appropriate handlers through the intent system.

Key features:
- Throttle checking (don't fire too often)
- Route hint resolution (e.g., "security/*" finds security agents)
- Semantic routing fallback when no hint provided
- Priority-based routing
"""

import asyncio
import logging
import time
import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum

from ..capabilities.registry import (
    CapabilityRegistry,
    Capability,
    Trigger,
    CapabilityType,
    get_registry,
)

logger = logging.getLogger(__name__)


class TriggerPriority(Enum):
    """Priority levels for triggers."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3
    
    @classmethod
    def from_string(cls, s: str) -> "TriggerPriority":
        return {
            "low": cls.LOW,
            "normal": cls.NORMAL,
            "high": cls.HIGH,
            "critical": cls.CRITICAL,
        }.get(s.lower(), cls.NORMAL)


@dataclass
class Intent:
    """
    An intent created from a trigger event.
    
    Intents are the universal language of Atmosphere - they represent
    what needs to happen, not how to do it.
    """
    id: str
    source_capability: str
    source_trigger: str
    intent_text: str  # Formatted from trigger template
    payload: Dict[str, Any]
    priority: TriggerPriority
    created_at: float = field(default_factory=time.time)
    route_hint: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_capability": self.source_capability,
            "source_trigger": self.source_trigger,
            "intent_text": self.intent_text,
            "payload": self.payload,
            "priority": self.priority.name,
            "created_at": self.created_at,
            "route_hint": self.route_hint,
        }


@dataclass
class TriggerResult:
    """Result of firing a trigger."""
    success: bool
    intent: Optional[Intent] = None
    routed_to: List[str] = field(default_factory=list)
    throttled: bool = False
    error: Optional[str] = None


class ThrottleTracker:
    """Tracks throttle state for triggers."""
    
    def __init__(self):
        self._last_fired: Dict[str, float] = {}  # key -> timestamp
    
    def should_throttle(self, key: str, throttle_ms: Optional[int]) -> bool:
        """Check if a trigger should be throttled."""
        if throttle_ms is None:
            return False
        
        last = self._last_fired.get(key, 0)
        elapsed_ms = (time.time() - last) * 1000
        
        return elapsed_ms < throttle_ms
    
    def record_fire(self, key: str) -> None:
        """Record that a trigger was fired."""
        self._last_fired[key] = time.time()
    
    def clear(self, key: Optional[str] = None) -> None:
        """Clear throttle state."""
        if key:
            self._last_fired.pop(key, None)
        else:
            self._last_fired.clear()


# Type for intent handlers
IntentHandler = Callable[[Intent], Any]


class TriggerRouter:
    """
    Routes trigger events to appropriate handlers.
    
    When a capability fires a trigger:
    1. Check throttle (skip if fired too recently)
    2. Create intent from trigger template + payload
    3. Resolve route hint to find handlers
    4. If no hint, use semantic routing
    5. Dispatch intent to handlers
    """
    
    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        semantic_router: Optional[Any] = None  # SemanticRouter if available
    ):
        self.registry = registry or get_registry()
        self.semantic_router = semantic_router
        self.throttle = ThrottleTracker()
        
        # Handler registrations
        self._handlers: Dict[str, List[IntentHandler]] = {}  # pattern -> handlers
        self._global_handlers: List[IntentHandler] = []  # receive all intents
        self._priority_queues: Dict[TriggerPriority, asyncio.Queue] = {
            p: asyncio.Queue() for p in TriggerPriority
        }
        
        # Intent counter for IDs
        self._intent_counter = 0
        self._lock = asyncio.Lock()
    
    async def fire_trigger(
        self,
        capability_id: str,
        event: str,
        payload: Dict[str, Any]
    ) -> TriggerResult:
        """
        Fire a trigger event from a capability.
        
        Args:
            capability_id: The capability firing the trigger
            event: The trigger event name
            payload: Event payload data
        
        Returns:
            TriggerResult with routing information
        """
        # Get capability and trigger
        capability = self.registry.get(capability_id)
        if not capability:
            return TriggerResult(
                success=False,
                error=f"Capability not found: {capability_id}"
            )
        
        trigger = capability.get_trigger(event)
        if not trigger:
            return TriggerResult(
                success=False,
                error=f"Trigger not found: {event} in {capability_id}"
            )
        
        # Check throttle
        throttle_key = f"{capability_id}:{event}"
        throttle_ms = trigger.parse_throttle_ms()
        
        if self.throttle.should_throttle(throttle_key, throttle_ms):
            logger.debug(f"Throttled trigger: {throttle_key}")
            return TriggerResult(success=True, throttled=True)
        
        # Create intent
        intent = await self._create_intent(capability, trigger, payload)
        
        # Record fire for throttle
        self.throttle.record_fire(throttle_key)
        
        # Route intent
        routed_to = await self._route_intent(intent, trigger)
        
        return TriggerResult(
            success=True,
            intent=intent,
            routed_to=routed_to,
        )
    
    async def _create_intent(
        self,
        capability: Capability,
        trigger: Trigger,
        payload: Dict[str, Any]
    ) -> Intent:
        """Create an intent from a trigger."""
        async with self._lock:
            self._intent_counter += 1
            intent_id = f"intent-{self._intent_counter}-{int(time.time() * 1000)}"
        
        intent_text = trigger.format_intent(payload)
        priority = TriggerPriority.from_string(trigger.priority)
        
        return Intent(
            id=intent_id,
            source_capability=capability.id,
            source_trigger=trigger.event,
            intent_text=intent_text,
            payload=payload,
            priority=priority,
            route_hint=trigger.route_hint,
        )
    
    async def _route_intent(
        self,
        intent: Intent,
        trigger: Trigger
    ) -> List[str]:
        """Route an intent to appropriate handlers."""
        routed_to = []
        
        # Try route hint first
        if trigger.route_hint:
            handlers = await self._resolve_route_hint(trigger.route_hint)
            for handler_id, handler in handlers:
                try:
                    await self._dispatch_to_handler(intent, handler)
                    routed_to.append(handler_id)
                except Exception as e:
                    logger.error(f"Handler {handler_id} failed: {e}")
        
        # If no hint or no handlers found, try semantic routing
        if not routed_to and self.semantic_router:
            semantic_handlers = await self._semantic_route(intent)
            for handler_id, handler in semantic_handlers:
                try:
                    await self._dispatch_to_handler(intent, handler)
                    routed_to.append(handler_id)
                except Exception as e:
                    logger.error(f"Semantic handler {handler_id} failed: {e}")
        
        # Pattern-based handlers
        for pattern, handlers in self._handlers.items():
            if self._matches_pattern(intent, pattern):
                for handler in handlers:
                    try:
                        await self._dispatch_to_handler(intent, handler)
                        routed_to.append(f"pattern:{pattern}")
                    except Exception as e:
                        logger.error(f"Pattern handler failed: {e}")
        
        # Global handlers always receive
        for handler in self._global_handlers:
            try:
                await self._dispatch_to_handler(intent, handler)
                routed_to.append("global")
            except Exception as e:
                logger.error(f"Global handler failed: {e}")
        
        # Queue for async processing
        await self._priority_queues[intent.priority].put(intent)
        
        if not routed_to:
            logger.warning(f"No handlers found for intent: {intent.intent_text}")
        
        return routed_to
    
    async def _resolve_route_hint(
        self,
        hint: str
    ) -> List[tuple[str, IntentHandler]]:
        """
        Resolve a route hint to actual handlers.
        
        Examples:
        - "security/*" → finds all security agent capabilities
        - "agent/security" → specific type
        - "capability:camera-1" → specific capability
        """
        handlers = []
        
        # Check if it's a specific capability reference
        if hint.startswith("capability:"):
            cap_id = hint.replace("capability:", "")
            capability = self.registry.get(cap_id)
            if capability:
                # Look for a registered intent handler for this capability
                handler = self._handlers.get(f"capability:{cap_id}")
                if handler:
                    handlers.extend([(cap_id, h) for h in handler])
            return handlers
        
        # Pattern match against capability types
        matching_caps = self.registry.find_by_route_hint(hint, healthy_only=True)
        
        for cap in matching_caps:
            # Check if capability has registered handlers
            cap_handlers = self._handlers.get(f"capability:{cap.id}", [])
            handlers.extend([(cap.id, h) for h in cap_handlers])
            
            # Also check type-based handlers
            type_handlers = self._handlers.get(f"type:{cap.type.value}", [])
            handlers.extend([(cap.id, h) for h in type_handlers])
        
        return handlers
    
    async def _semantic_route(
        self,
        intent: Intent
    ) -> List[tuple[str, IntentHandler]]:
        """Use semantic routing to find handlers."""
        if not self.semantic_router:
            return []
        
        try:
            # Use the semantic router to find matching capabilities
            matches = await self.semantic_router.route(intent.intent_text)
            
            handlers = []
            for match in matches:
                cap_id = match.get("capability_id") or match.get("id")
                if cap_id:
                    cap_handlers = self._handlers.get(f"capability:{cap_id}", [])
                    handlers.extend([(cap_id, h) for h in cap_handlers])
            
            return handlers
        except Exception as e:
            logger.error(f"Semantic routing failed: {e}")
            return []
    
    def _matches_pattern(self, intent: Intent, pattern: str) -> bool:
        """Check if an intent matches a handler pattern."""
        # Event pattern: "event:motion_detected"
        if pattern.startswith("event:"):
            event_pattern = pattern.replace("event:", "")
            return fnmatch.fnmatch(intent.source_trigger, event_pattern)
        
        # Priority pattern: "priority:critical"
        if pattern.startswith("priority:"):
            priority_str = pattern.replace("priority:", "")
            return intent.priority.name.lower() == priority_str.lower()
        
        # Intent text pattern (regex)
        if pattern.startswith("regex:"):
            regex = pattern.replace("regex:", "")
            return bool(re.search(regex, intent.intent_text, re.IGNORECASE))
        
        # Glob pattern on intent text
        return fnmatch.fnmatch(intent.intent_text.lower(), pattern.lower())
    
    async def _dispatch_to_handler(
        self,
        intent: Intent,
        handler: IntentHandler
    ) -> Any:
        """Dispatch an intent to a handler."""
        if asyncio.iscoroutinefunction(handler):
            return await handler(intent)
        else:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, handler, intent)
    
    def register_handler(
        self,
        pattern: str,
        handler: IntentHandler
    ) -> None:
        """
        Register a handler for a pattern.
        
        Patterns:
        - "capability:camera-1" → specific capability
        - "type:agent/security" → capability type
        - "event:motion_detected" → event name
        - "priority:critical" → priority level
        - "regex:motion at.*" → regex on intent text
        - "motion at *" → glob on intent text
        """
        if pattern not in self._handlers:
            self._handlers[pattern] = []
        self._handlers[pattern].append(handler)
        logger.info(f"Registered trigger handler for pattern: {pattern}")
    
    def register_global_handler(self, handler: IntentHandler) -> None:
        """Register a handler that receives all intents."""
        self._global_handlers.append(handler)
    
    def unregister_handler(self, pattern: str, handler: IntentHandler) -> bool:
        """Unregister a handler."""
        if pattern in self._handlers:
            try:
                self._handlers[pattern].remove(handler)
                return True
            except ValueError:
                pass
        return False
    
    async def get_queued_intents(
        self,
        priority: Optional[TriggerPriority] = None,
        limit: int = 100
    ) -> List[Intent]:
        """Get queued intents, optionally filtered by priority."""
        intents = []
        
        if priority:
            queue = self._priority_queues[priority]
            while not queue.empty() and len(intents) < limit:
                intents.append(await queue.get())
        else:
            # Get from all queues, highest priority first
            for p in reversed(TriggerPriority):
                queue = self._priority_queues[p]
                while not queue.empty() and len(intents) < limit:
                    intents.append(await queue.get())
        
        return intents
    
    async def process_queue(
        self,
        handler: IntentHandler,
        priority: Optional[TriggerPriority] = None,
        continuous: bool = False
    ) -> None:
        """
        Process queued intents with a handler.
        
        Args:
            handler: Function to call for each intent
            priority: Only process this priority (None = all)
            continuous: Keep running (True) or process once (False)
        """
        while True:
            if priority:
                queue = self._priority_queues[priority]
                intent = await queue.get()
                await self._dispatch_to_handler(intent, handler)
            else:
                # Process highest priority first
                for p in reversed(TriggerPriority):
                    queue = self._priority_queues[p]
                    if not queue.empty():
                        intent = await queue.get()
                        await self._dispatch_to_handler(intent, handler)
                        break
                else:
                    # All queues empty
                    if not continuous:
                        break
                    await asyncio.sleep(0.1)
            
            if not continuous:
                break
    
    def stats(self) -> Dict[str, Any]:
        """Get router statistics."""
        return {
            "registered_patterns": len(self._handlers),
            "global_handlers": len(self._global_handlers),
            "queued_intents": {
                p.name: self._priority_queues[p].qsize()
                for p in TriggerPriority
            },
            "throttle_entries": len(self.throttle._last_fired),
        }


# Global router instance
_global_router: Optional[TriggerRouter] = None


def get_trigger_router(
    registry: Optional[CapabilityRegistry] = None,
    semantic_router: Optional[Any] = None
) -> TriggerRouter:
    """Get the global trigger router."""
    global _global_router
    if _global_router is None:
        _global_router = TriggerRouter(registry, semantic_router)
    return _global_router


def reset_trigger_router() -> None:
    """Reset the global router (for testing)."""
    global _global_router
    _global_router = None


# Convenience function
async def fire_trigger(
    capability_id: str,
    event: str,
    payload: Dict[str, Any]
) -> TriggerResult:
    """Convenience function to fire a trigger."""
    router = get_trigger_router()
    return await router.fire_trigger(capability_id, event, payload)
