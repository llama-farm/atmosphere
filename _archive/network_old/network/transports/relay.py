"""
Relay Transport - WebSocket connection via cloud relay server.

Characteristics:
- Higher latency (~100-500ms depending on location)
- Works anywhere with internet
- NAT traversal built-in
- Fallback when LAN not available
- Requires relay server infrastructure
"""

import asyncio
import json
import logging
import time
from typing import Optional, Callable, Dict, Any

import aiohttp

from ..resilient_transport import Transport, TransportType, TransportState

log = logging.getLogger(__name__)


class RelayTransport(Transport):
    """
    Cloud relay WebSocket transport.
    
    Connects to a relay server which forwards messages between peers.
    Used when direct LAN connection is not possible (different networks,
    NAT traversal issues, etc).
    
    Protocol:
    - Client sends: {"type": "join", "node_id": "...", "mesh_id": "...", "token": "..."}
    - Server sends: {"type": "joined", "peer_id": "..."}
    - Server sends: {"type": "peers", "peers": [...]}
    - Client sends: {"type": "broadcast", "payload": {...}}
    - Server sends: {"type": "message", "from": "...", "payload": {...}}
    """
    
    def __init__(self, node_id: str, mesh_id: str, token: Optional[str] = None):
        super().__init__(TransportType.RELAY)
        self.node_id = node_id
        self.mesh_id = mesh_id
        self.token = token
        
        # Relay has medium-high latency, low battery cost
        self.metrics.battery_cost = 0.2
        self.metrics.bandwidth_kbps = 10000.0  # 10 Mbps typical
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._relay_url: Optional[str] = None
        
        # Ping tracking
        self._ping_id: int = 0
        self._ping_start: float = 0
        self._ping_event: Optional[asyncio.Event] = None
        
        # Peer tracking (from relay)
        self.relay_peers: Dict[str, Dict[str, Any]] = {}
        
        # Event handlers
        self._on_peers_updated: Optional[Callable[[Dict], None]] = None
        self._on_peer_joined: Optional[Callable[[str], None]] = None
        self._on_peer_left: Optional[Callable[[str], None]] = None
    
    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return (
            self._ws is not None 
            and not self._ws.closed 
            and self.metrics.state == TransportState.CONNECTED
        )
    
    async def connect(self, address: str) -> bool:
        """
        Connect to relay server.
        
        Address format: "wss://relay.example.com/relay/{mesh_id}"
        """
        self._relay_url = address
        
        try:
            if self._session is None:
                self._session = aiohttp.ClientSession()
            
            self.metrics.state = TransportState.CONNECTING
            
            log.info(f"🔌 Relay connecting to {address} (node={self.node_id}, mesh={self.mesh_id})")
            print(f"[RELAY] Connecting to {address}")
            
            self._ws = await self._session.ws_connect(
                address,
                heartbeat=20.0,  # Keep connection alive
                timeout=aiohttp.ClientTimeout(total=15.0)
            )
            
            # Send join message
            join_msg = {
                "type": "join",
                "node_id": self.node_id,
                "mesh_id": self.mesh_id,
            }
            if self.token:
                join_msg["token"] = self.token
            
            await self._ws.send_json(join_msg)
            
            # Wait for joined confirmation
            try:
                msg = await asyncio.wait_for(self._ws.receive(), timeout=10.0)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("type") == "joined":
                        log.info(f"Joined relay as {data.get('peer_id')}")
                    elif data.get("type") == "error":
                        log.error(f"Relay join error: {data.get('message')}")
                        self.metrics.state = TransportState.FAILED
                        return False
            except asyncio.TimeoutError:
                log.error("Timeout waiting for join confirmation")
                self.metrics.state = TransportState.FAILED
                return False
            
            self.metrics.state = TransportState.CONNECTED
            print(f"[RELAY] ✅ State=CONNECTED, starting receive loop", flush=True)
            
            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            return True
            
        except Exception as e:
            log.error(f"Relay connect failed: {e}")
            self.metrics.state = TransportState.FAILED
            return False
    
    async def disconnect(self):
        """Disconnect from relay."""
        self.metrics.state = TransportState.DISCONNECTED
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        
        if self._ws and not self._ws.closed:
            await self._ws.close()
            self._ws = None
        
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        
        self.relay_peers.clear()
    
    async def send(self, message: bytes) -> bool:
        """Broadcast message to all peers via relay."""
        if not self._ws or self._ws.closed:
            self.metrics.state = TransportState.FAILED
            return False
        
        try:
            # Wrap in relay broadcast format
            await self._ws.send_json({
                "type": "broadcast",
                "payload": message.decode('utf-8') if isinstance(message, bytes) else message
            })
            return True
        except Exception as e:
            log.warning(f"Relay send failed: {e}")
            self.metrics.state = TransportState.FAILED
            return False
    
    async def send_to_peer(self, peer_id: str, message: bytes) -> bool:
        """Send direct message to specific peer via relay."""
        if not self._ws or self._ws.closed:
            self.metrics.state = TransportState.FAILED
            return False
        
        try:
            await self._ws.send_json({
                "type": "message",
                "to": peer_id,
                "payload": message.decode('utf-8') if isinstance(message, bytes) else message
            })
            return True
        except Exception as e:
            log.warning(f"Relay send_to_peer failed: {e}")
            return False
    
    async def ping(self) -> float:
        """Ping relay server and return latency in ms."""
        if not self._ws or self._ws.closed:
            raise ConnectionError("Not connected")
        
        self._ping_id += 1
        self._ping_event = asyncio.Event()
        self._ping_start = time.monotonic()
        
        try:
            # Send ping message
            await self._ws.send_json({
                "type": "ping",
                "id": self._ping_id
            })
            
            # Wait for pong
            await asyncio.wait_for(self._ping_event.wait(), timeout=5.0)
            
            latency_ms = (time.monotonic() - self._ping_start) * 1000
            return latency_ms
            
        except asyncio.TimeoutError:
            raise ConnectionError("Ping timeout")
        finally:
            self._ping_event = None
    
    async def _receive_loop(self):
        """Background task to receive relay messages."""
        print("[RELAY] 📭 Receive loop started", flush=True)
        try:
            async for msg in self._ws:
                print(f"[RELAY] 📬 Got ws msg type={msg.type}", flush=True)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_relay_message(msg.data)
                    
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    log.error(f"Relay WebSocket error: {self._ws.exception()}")
                    break
                    
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    break
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Relay receive loop error: {e}")
        finally:
            if self.metrics.state == TransportState.CONNECTED:
                self.metrics.state = TransportState.FAILED
                # Trigger auto-reconnect
                asyncio.create_task(self._auto_reconnect())
    
    async def _handle_relay_message(self, data: str):
        """Handle incoming relay protocol message."""
        try:
            msg = json.loads(data)
            msg_type = msg.get("type")
            log.debug(f"Relay message type: {msg_type}")
            
            if msg_type == "pong":
                # Response to our ping
                if self._ping_event:
                    self._ping_event.set()
                    
            elif msg_type == "peers":
                # Peer list update
                peers = msg.get("peers", [])
                self.relay_peers = {p["node_id"]: p for p in peers if "node_id" in p}
                log.debug(f"Relay peers updated: {len(self.relay_peers)} peers")
                if self._on_peers_updated:
                    self._on_peers_updated(self.relay_peers)
                    
            elif msg_type == "peer_joined":
                peer_id = msg.get("peer_id")
                peer_info = msg.get("peer_info", {})
                self.relay_peers[peer_id] = peer_info
                log.info(f"Peer joined via relay: {peer_id}")
                if self._on_peer_joined:
                    self._on_peer_joined(peer_id)
                    
            elif msg_type == "peer_left":
                peer_id = msg.get("peer_id")
                self.relay_peers.pop(peer_id, None)
                log.info(f"Peer left relay: {peer_id}")
                if self._on_peer_left:
                    self._on_peer_left(peer_id)
                    
            elif msg_type == "message":
                # Message from another peer
                from_peer = msg.get("from")
                payload = msg.get("payload")
                log.info(f"📨 Relay message from {from_peer}: {str(payload)[:100]}")
                print(f"[RELAY-MSG] From {from_peer}: {str(payload)[:100]}", flush=True)
                if payload and self._message_handler:
                    # Convert to bytes
                    if isinstance(payload, str):
                        self._message_handler(payload.encode('utf-8'))
                    elif isinstance(payload, dict):
                        self._message_handler(json.dumps(payload).encode('utf-8'))
                    else:
                        self._message_handler(bytes(payload))
                else:
                    log.warning(f"No message handler for relay message from {from_peer}")
                        
            elif msg_type == "error":
                log.error(f"Relay error: {msg.get('message')}")
                
        except json.JSONDecodeError:
            log.warning(f"Invalid JSON from relay: {data[:100]}")
        except Exception as e:
            log.error(f"Error handling relay message: {e}")
    
    async def _auto_reconnect(self):
        """Automatically reconnect after disconnect."""
        if not self._relay_url:
            return
        
        # Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
        delays = [1, 2, 4, 8, 16, 30]
        attempt = 0
        
        while self.metrics.state == TransportState.FAILED:
            delay = delays[min(attempt, len(delays) - 1)]
            log.info(f"Relay auto-reconnect in {delay}s (attempt {attempt + 1})...")
            await asyncio.sleep(delay)
            
            if self.metrics.state != TransportState.FAILED:
                break  # Already reconnected or stopped
            
            try:
                # Reset for reconnect
                if self._ws and not self._ws.closed:
                    await self._ws.close()
                self._ws = None
                
                success = await self.connect(self._relay_url)
                if success:
                    log.info("Relay auto-reconnect successful!")
                    return
            except Exception as e:
                log.warning(f"Relay reconnect attempt {attempt + 1} failed: {e}")
            
            attempt += 1
            self.metrics.reconnect_attempts = attempt
    
    # Event handler setters
    def on_peers_updated(self, handler: Callable[[Dict], None]):
        self._on_peers_updated = handler
    
    def on_peer_joined(self, handler: Callable[[str], None]):
        self._on_peer_joined = handler
    
    def on_peer_left(self, handler: Callable[[str], None]):
        self._on_peer_left = handler


def create_relay_transport_factory(node_id: str, mesh_id: str, token: Optional[str] = None):
    """Factory function for creating relay transports."""
    def factory() -> RelayTransport:
        return RelayTransport(node_id, mesh_id, token)
    return factory
