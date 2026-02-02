"""
WebSocket support for real-time mesh events.
"""

import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time events."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.debug(f"WebSocket connected, total: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.debug(f"WebSocket disconnected, total: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return
        
        data = json.dumps(message)
        
        async with self._lock:
            dead_connections = set()
            
            for connection in self.active_connections:
                try:
                    await connection.send_text(data)
                except Exception:
                    dead_connections.add(connection)
            
            self.active_connections -= dead_connections
    
    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        """Send a message to a specific client."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to send message: {e}")


# Global connection manager
manager = ConnectionManager()


async def mesh_events_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time mesh events.
    
    Events include:
    - peer_joined: A new peer was discovered
    - peer_left: A peer disconnected
    - capability_added: A new capability became available
    - capability_removed: A capability became unavailable
    - route_changed: Routing table updated
    """
    await manager.connect(websocket)
    
    # Send initial status
    from .server import get_server
    server = get_server()
    
    if server:
        await manager.send_personal(websocket, {
            "type": "connected",
            "node_id": server.node.node_id if server.node else None,
            "capabilities": list(server.router.local_capabilities.keys()) if server.router else []
        })
    
    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle client messages
            if message.get("type") == "ping":
                await manager.send_personal(websocket, {"type": "pong"})
            
            elif message.get("type") == "subscribe":
                # Subscribe to specific event types
                pass
            
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(websocket)


# Event emitters for use by other components

async def emit_peer_joined(peer_info: dict) -> None:
    """Emit a peer_joined event."""
    await manager.broadcast({
        "type": "peer_joined",
        "peer": peer_info
    })


async def emit_peer_left(node_id: str) -> None:
    """Emit a peer_left event."""
    await manager.broadcast({
        "type": "peer_left",
        "node_id": node_id
    })


async def emit_capability_added(capability: dict) -> None:
    """Emit a capability_added event."""
    await manager.broadcast({
        "type": "capability_added",
        "capability": capability
    })


async def emit_route_changed(update: dict) -> None:
    """Emit a route_changed event."""
    await manager.broadcast({
        "type": "route_changed",
        "update": update
    })
