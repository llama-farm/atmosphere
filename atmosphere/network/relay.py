"""
Relay server for fallback connectivity.

When NAT traversal fails, traffic is relayed through a public server.
This is a simple WebSocket-based relay that forwards messages between peers.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional, Set

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)


@dataclass
class RelayInfo:
    """Information about a relay server."""
    url: str  # WebSocket URL (ws:// or wss://)
    region: str  # e.g., "us-east", "eu-west"
    latency_ms: Optional[int] = None
    capacity: Optional[int] = None  # Max connections
    
    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "region": self.region,
            "latency_ms": self.latency_ms,
            "capacity": self.capacity,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "RelayInfo":
        return cls(
            url=data["url"],
            region=data["region"],
            latency_ms=data.get("latency_ms"),
            capacity=data.get("capacity"),
        )


# Default community relay servers
# TODO: Set up actual community relays
DEFAULT_RELAYS = [
    # RelayInfo(url="wss://relay.atmosphere.dev/v1", region="us-east"),
]


class RelaySession:
    """A relay session between two peers."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.peer_a: Optional[web.WebSocketResponse] = None
        self.peer_b: Optional[web.WebSocketResponse] = None
        self.created_at = time.time()
        self.bytes_relayed = 0
    
    def add_peer(self, ws: web.WebSocketResponse) -> bool:
        """Add a peer to the session. Returns True if session is complete."""
        if self.peer_a is None:
            self.peer_a = ws
            return False
        elif self.peer_b is None:
            self.peer_b = ws
            return True
        return False
    
    def get_other_peer(self, ws: web.WebSocketResponse) -> Optional[web.WebSocketResponse]:
        """Get the other peer in this session."""
        if ws == self.peer_a:
            return self.peer_b
        elif ws == self.peer_b:
            return self.peer_a
        return None
    
    @property
    def is_complete(self) -> bool:
        """Check if both peers are connected."""
        return self.peer_a is not None and self.peer_b is not None


class RelayServer:
    """
    Simple relay server for fallback connectivity.
    
    Protocol:
    1. Client A connects with session_id
    2. Client B connects with same session_id
    3. Server relays all messages between A and B
    4. Either client can disconnect to end session
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.sessions: Dict[str, RelaySession] = {}
        self.app = web.Application()
        self.app.router.add_get("/relay/{session_id}", self.handle_relay)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/stats", self.handle_stats)
        self.runner: Optional[web.AppRunner] = None
    
    async def start(self) -> None:
        """Start the relay server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        
        logger.info(f"Relay server started on {self.host}:{self.port}")
    
    async def stop(self) -> None:
        """Stop the relay server."""
        if self.runner:
            await self.runner.cleanup()
        logger.info("Relay server stopped")
    
    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "ok",
            "sessions": len(self.sessions),
            "timestamp": time.time(),
        })
    
    async def handle_stats(self, request: web.Request) -> web.Response:
        """Stats endpoint."""
        total_bytes = sum(s.bytes_relayed for s in self.sessions.values())
        active_sessions = sum(1 for s in self.sessions.values() if s.is_complete)
        
        return web.json_response({
            "total_sessions": len(self.sessions),
            "active_sessions": active_sessions,
            "total_bytes_relayed": total_bytes,
        })
    
    async def handle_relay(self, request: web.Request) -> web.WebSocketResponse:
        """Handle a relay WebSocket connection."""
        session_id = request.match_info["session_id"]
        
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        
        # Get or create session
        if session_id not in self.sessions:
            self.sessions[session_id] = RelaySession(session_id)
        
        session = self.sessions[session_id]
        is_complete = session.add_peer(ws)
        
        if is_complete:
            logger.info(f"Relay session {session_id} complete, starting relay")
        else:
            logger.info(f"Waiting for second peer in session {session_id}")
        
        try:
            # Relay messages
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = msg.data
                    session.bytes_relayed += len(data)
                    
                    # Forward to other peer
                    other = session.get_other_peer(ws)
                    if other and not other.closed:
                        await other.send_str(data)
                
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    data = msg.data
                    session.bytes_relayed += len(data)
                    
                    # Forward to other peer
                    other = session.get_other_peer(ws)
                    if other and not other.closed:
                        await other.send_bytes(data)
                
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error in session {session_id}: {ws.exception()}")
        
        finally:
            # Clean up
            logger.info(f"Peer disconnected from session {session_id}")
            
            # Close other peer if still connected
            other = session.get_other_peer(ws)
            if other and not other.closed:
                await other.close()
            
            # Remove session
            if session_id in self.sessions:
                del self.sessions[session_id]
        
        return ws


class RelayClient:
    """
    Client for connecting to a relay server.
    
    Usage:
        client = RelayClient("ws://relay.example.com:8080", "session-123")
        await client.connect()
        await client.send(b"data")
        data = await client.receive()
    """
    
    def __init__(
        self,
        relay_url: str,
        session_id: Optional[str] = None,
    ):
        """
        Initialize relay client.
        
        Args:
            relay_url: WebSocket URL of relay server (without /relay path)
            session_id: Session ID (generated if not provided)
        """
        self.relay_url = relay_url.rstrip("/")
        self.session_id = session_id or self._generate_session_id()
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
    
    @staticmethod
    def _generate_session_id() -> str:
        """Generate a random session ID."""
        import secrets
        return secrets.token_urlsafe(16)
    
    async def connect(self, timeout: float = 10.0) -> bool:
        """
        Connect to the relay server.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if connected, False otherwise
        """
        try:
            self._session = aiohttp.ClientSession()
            url = f"{self.relay_url}/relay/{self.session_id}"
            
            self.ws = await asyncio.wait_for(
                self._session.ws_connect(url),
                timeout=timeout
            )
            
            logger.info(f"Connected to relay: {url}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to relay: {e}")
            if self._session:
                await self._session.close()
                self._session = None
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from relay server."""
        if self.ws and not self.ws.closed:
            await self.ws.close()
        
        if self._session:
            await self._session.close()
            self._session = None
    
    async def send(self, data: bytes) -> bool:
        """
        Send data through the relay.
        
        Args:
            data: Data to send
            
        Returns:
            True if sent, False if not connected
        """
        if not self.ws or self.ws.closed:
            return False
        
        try:
            await self.ws.send_bytes(data)
            return True
        except Exception as e:
            logger.error(f"Failed to send via relay: {e}")
            return False
    
    async def receive(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """
        Receive data from the relay.
        
        Args:
            timeout: Receive timeout in seconds (None = block forever)
            
        Returns:
            Received data, or None on error/timeout
        """
        if not self.ws or self.ws.closed:
            return None
        
        try:
            if timeout:
                msg = await asyncio.wait_for(self.ws.receive(), timeout=timeout)
            else:
                msg = await self.ws.receive()
            
            if msg.type == aiohttp.WSMsgType.BINARY:
                return msg.data
            elif msg.type == aiohttp.WSMsgType.TEXT:
                return msg.data.encode()
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                logger.warning("Relay connection closed")
                return None
            
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error(f"Failed to receive from relay: {e}")
            return None
        
        return None


async def find_best_relay(
    relays: Optional[list[RelayInfo]] = None
) -> Optional[RelayInfo]:
    """
    Find the best relay server by latency.
    
    Args:
        relays: List of relays to test (defaults to DEFAULT_RELAYS)
        
    Returns:
        Best relay, or None if none available
    """
    relays = relays or DEFAULT_RELAYS
    
    if not relays:
        logger.warning("No relay servers configured")
        return None
    
    # TODO: Implement latency testing
    # For now, just return the first one
    return relays[0] if relays else None


async def start_relay_server(host: str = "0.0.0.0", port: int = 8080) -> RelayServer:
    """
    Start a relay server.
    
    Args:
        host: Host to bind to
        port: Port to bind to
        
    Returns:
        Running RelayServer instance
    """
    server = RelayServer(host, port)
    await server.start()
    return server
