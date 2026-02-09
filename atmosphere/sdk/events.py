"""Event emission and subscription."""

import logging
from typing import Dict, Any, Callable, List
from datetime import datetime

logger = logging.getLogger(__name__)


class EventEmitter:
    """
    Event emitter for push events.
    
    Allows apps to push real-time events to mesh subscribers.
    """
    
    def __init__(self, send_func: Callable):
        """
        Initialize event emitter.
        
        Args:
            send_func: Function to send events to mesh (typically from AtmosphereApp)
        """
        self._send = send_func
        self._listeners: Dict[str, List[Callable]] = {}
    
    async def emit(self, event: str, data: Dict[str, Any]) -> None:
        """
        Emit an event to mesh subscribers.
        
        Args:
            event: Event name (e.g., "anomaly.new")
            data: Event payload
        """
        message = {
            "type": "push_event",
            "event": event,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.debug(f"Emitting event: {event}")
        await self._send(message)
        
        # Also notify local listeners
        await self._notify_local(event, data)
    
    def on(self, event: str, handler: Callable) -> None:
        """
        Register a local event listener.
        
        Args:
            event: Event pattern (supports wildcards: "anomaly.*")
            handler: Async function to call when event occurs
        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(handler)
        logger.debug(f"Registered listener for: {event}")
    
    async def _notify_local(self, event: str, data: Dict[str, Any]) -> None:
        """Notify local listeners about an event."""
        for pattern, handlers in self._listeners.items():
            if self._match_pattern(event, pattern):
                for handler in handlers:
                    try:
                        await handler(event, data)
                    except Exception as e:
                        logger.error(f"Error in event handler for {event}: {e}")
    
    def _match_pattern(self, event: str, pattern: str) -> bool:
        """Check if event matches pattern (supports wildcards)."""
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event.startswith(prefix)
        return event == pattern
