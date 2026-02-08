"""
Simple Relay Transport - ONE WebSocket connection that just works.

No per-peer complexity, no transport cycling, no magic.
Just a WebSocket to the relay server with automatic reconnection.
"""

import asyncio
import json
import logging
from typing import Callable, Optional, Any, Dict, List
from dataclasses import dataclass
import time

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    websockets = None
    WebSocketClientProtocol = None

logger = logging.getLogger(__name__)


@dataclass
class RelayMessage:
    """Message structure for relay communication."""
    target_node: str
    source_node: str
    payload: Dict[str, Any]
    message_id: Optional[str] = None
    timestamp: Optional[float] = None


class RelayConnection:
    """
    Simple WebSocket connection to Atmosphere relay server.
    
    Features:
    - Auto-reconnect with exponential backoff
    - Message routing through relay
    - Callback-based message handling
    - Founder registration with mesh key
    - No per-peer complexity
    """
    
    def __init__(
        self,
        node_id: str,
        mesh_id: str,
        token: str,
        relay_url: str = "wss://atmosphere-relay-production.up.railway.app",
        on_message: Optional[Callable[[RelayMessage], None]] = None,
        max_reconnect_delay: float = 60.0,
        # Founder registration fields
        is_founder: bool = False,
        mesh_public_key: Optional[str] = None,
        founder_proof: Optional[str] = None,
        node_public_key: Optional[str] = None,
        mesh_name: Optional[str] = None,
    ):
        """
        Initialize relay connection.
        
        Args:
            node_id: This node's unique identifier
            mesh_id: Mesh ID to join
            token: Authentication token for the mesh
            relay_url: WebSocket URL of relay server (without /relay/ path)
            on_message: Callback for incoming messages
            max_reconnect_delay: Maximum delay between reconnection attempts (seconds)
        """
        if websockets is None:
            raise ImportError("websockets package required. Install with: pip install websockets")
        
        self.node_id = node_id
        self.mesh_id = mesh_id
        self.token = token
        self.relay_url = relay_url.rstrip('/')
        self.on_message = on_message
        self.max_reconnect_delay = max_reconnect_delay
        
        # Founder registration fields
        self.is_founder = is_founder
        self.mesh_public_key = mesh_public_key
        self.founder_proof = founder_proof
        self.node_public_key = node_public_key
        self.mesh_name = mesh_name or mesh_id[:8]
        
        # Capabilities to announce
        self._capabilities: List[str] = []
        
        self._ws: Optional[WebSocketClientProtocol] = None
        self._connected = False
        self._reconnect_delay = 1.0
        self._running = False
        self._connect_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        
        logger.info(f"RelayConnection initialized for node {node_id} (founder={is_founder})")
    
    def set_capabilities(self, capabilities: List[str]) -> None:
        """Set capabilities to announce during registration."""
        self._capabilities = capabilities
        logger.info(f"Set {len(capabilities)} capabilities for relay announcement")
    
    async def connect(self) -> None:
        """Start the connection (and auto-reconnection) loop."""
        if self._running:
            logger.warning("Connection already running")
            return
        
        self._running = True
        self._connect_task = asyncio.create_task(self._connection_loop())
        logger.info("Connection loop started")
    
    async def disconnect(self) -> None:
        """Stop the connection and clean up."""
        logger.info("Disconnecting...")
        self._running = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._connect_task:
            self._connect_task.cancel()
            try:
                await self._connect_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        self._connected = False
        logger.info("Disconnected")
    
    async def _connection_loop(self) -> None:
        """Main connection loop with exponential backoff."""
        while self._running:
            try:
                # Build WebSocket URL with mesh path
                ws_url = f"{self.relay_url}/relay/{self.mesh_id}"
                print(f"[RELAY] Connecting to: {ws_url}", flush=True)
                logger.info(f"Connecting to relay at {ws_url}...")
                
                async with websockets.connect(ws_url) as ws:
                    print(f"[RELAY] WebSocket connected!", flush=True)
                    self._ws = ws
                    self._connected = True
                    self._reconnect_delay = 1.0  # Reset backoff on successful connection
                    
                    logger.info("✓ Connected to relay")
                    
                    # Send registration message
                    print(f"[RELAY] Registering node {self.node_id}...", flush=True)
                    await self._register()
                    print(f"[RELAY] Registration sent", flush=True)
                    
                    # Start receiving messages
                    print(f"[RELAY] Starting receive loop...", flush=True)
                    self._receive_task = asyncio.create_task(self._receive_loop())
                    
                    # Wait for disconnection
                    await self._receive_task
                    
            except Exception as e:
                self._connected = False
                print(f"[RELAY] Connection failed: {e}", flush=True)
                logger.warning(f"Connection failed: {e}")
                
                if self._running:
                    # Exponential backoff
                    delay = min(self._reconnect_delay, self.max_reconnect_delay)
                    logger.info(f"Reconnecting in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                    self._reconnect_delay *= 2
    
    async def _register(self) -> None:
        """Register this node with the relay."""
        
        # Announce capabilities - if founder, definitely include "llm" since we have LlamaFarm
        caps_to_announce = self._capabilities if self._capabilities else []
        if self.is_founder and "llm" not in caps_to_announce:
            caps_to_announce = caps_to_announce + ["llm", "llamafarm", "chat"]
        
        if self.is_founder and self.mesh_public_key and self.founder_proof:
            # FOUNDER: Send register_mesh to establish the mesh on the relay
            register_msg = {
                "type": "register_mesh",
                "mesh_id": self.mesh_id,
                "mesh_public_key": self.mesh_public_key,
                "founder_proof": self.founder_proof,
                "node_id": self.node_id,
                "node_public_key": self.node_public_key or "",
                "name": self.mesh_name,
                "display_name": self.mesh_name,
                "capabilities": caps_to_announce,
                "timestamp": time.time()
            }
            print(f"[RELAY] 🔑 Sending FOUNDER registration: mesh={self.mesh_id}, node={self.node_id}, caps={caps_to_announce}", flush=True)
            logger.info(f"Registering mesh {self.mesh_id} as founder {self.node_id} with {len(caps_to_announce)} capabilities")
        else:
            # MEMBER: Send join with token
            register_msg = {
                "type": "join",
                "node_id": self.node_id,
                "token": self.token if isinstance(self.token, dict) else {},
                "name": self.mesh_name,
                "capabilities": caps_to_announce,
                "timestamp": time.time()
            }
            print(f"[RELAY] Sending JOIN: node_id={self.node_id}, mesh={self.mesh_id}", flush=True)
            logger.info(f"Joining mesh {self.mesh_id} as member {self.node_id}")
        
        await self._ws.send(json.dumps(register_msg))
        print(f"[RELAY] Registration sent successfully", flush=True)
        logger.debug(f"Sent registration for node {self.node_id} in mesh {self.mesh_id}")
    
    async def _receive_loop(self) -> None:
        """Receive and process messages from relay."""
        try:
            async for raw_message in self._ws:
                try:
                    print(f"[RELAY] Received message: {raw_message[:200]}", flush=True)
                    data = json.loads(raw_message)
                    
                    # Handle different message types
                    msg_type = data.get("type")
                    print(f"[RELAY] Message type: {msg_type}", flush=True)
                    
                    if msg_type == "message":
                        # Route to callback
                        msg = RelayMessage(
                            target_node=data.get("target_node", ""),
                            source_node=data.get("source_node", ""),
                            payload=data.get("payload", {}),
                            message_id=data.get("message_id"),
                            timestamp=data.get("timestamp")
                        )
                        
                        if self.on_message:
                            try:
                                if asyncio.iscoroutinefunction(self.on_message):
                                    await self.on_message(msg)
                                else:
                                    self.on_message(msg)
                            except Exception as e:
                                logger.error(f"Error in message callback: {e}", exc_info=True)
                    
                    elif msg_type == "ping":
                        # Respond to ping
                        await self._ws.send(json.dumps({"type": "pong"}))
                    
                    elif msg_type == "registered":
                        logger.info(f"✓ Registered with relay as {self.node_id}")
                    
                    elif msg_type == "mesh_registered":
                        success = data.get("success", False)
                        if success:
                            print(f"[RELAY] ✅ Mesh registered successfully!", flush=True)
                            logger.info(f"✓ Mesh {self.mesh_id} registered with relay")
                        else:
                            error = data.get("message", "Unknown error")
                            print(f"[RELAY] ❌ Mesh registration failed: {error}", flush=True)
                            logger.error(f"Mesh registration failed: {error}")
                    
                    elif msg_type == "error":
                        code = data.get("code", "UNKNOWN")
                        message = data.get("message", "No message")
                        print(f"[RELAY] ❌ Error: {code} - {message}", flush=True)
                        logger.error(f"Relay error: {code} - {message}")
                    
                    else:
                        # Pass other relay messages (joined, peers, etc.) to callback
                        logger.debug(f"Received {msg_type} message: {data}")
                        if self.on_message:
                            try:
                                # Wrap in RelayMessage format (payload = full message)
                                msg = RelayMessage(
                                    target_node=self.node_id,
                                    source_node="relay",
                                    payload=data,
                                    message_id=data.get("message_id"),
                                    timestamp=data.get("timestamp", time.time())
                                )
                                if asyncio.iscoroutinefunction(self.on_message):
                                    await self.on_message(msg)
                                else:
                                    self.on_message(msg)
                            except Exception as e:
                                logger.error(f"Error in callback for {msg_type}: {e}", exc_info=True)
                        
                except json.JSONDecodeError:
                    logger.warning(f"Received invalid JSON: {raw_message}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection closed")
            self._connected = False
        except Exception as e:
            logger.error(f"Error in receive loop: {e}", exc_info=True)
            self._connected = False
    
    async def send(self, target_node_id: str, payload: Dict[str, Any], message_id: Optional[str] = None) -> bool:
        """
        Send a message to another node through the relay.
        
        Args:
            target_node_id: ID of the target node
            payload: Message payload (must be JSON-serializable)
            message_id: Optional message ID for tracking
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self._connected or not self._ws:
            logger.warning("Cannot send: not connected to relay")
            return False
        
        try:
            message = {
                "type": "message",
                "target_node": target_node_id,
                "source_node": self.node_id,
                "payload": payload,
                "message_id": message_id,
                "timestamp": time.time()
            }
            
            await self._ws.send(json.dumps(message))
            logger.debug(f"Sent message to {target_node_id}: {message_id or 'no-id'}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending message: {e}", exc_info=True)
            return False
    
    @property
    def connected(self) -> bool:
        """Check if currently connected to relay."""
        return self._connected and self._ws is not None
    
    @property
    def ws(self) -> Optional[WebSocketClientProtocol]:
        """
        Access to underlying WebSocket for backward compatibility.
        Prefer using .connected property and .send() method instead.
        """
        return self._ws
    
    def __repr__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        return f"RelayConnection(node={self.node_id}, status={status})"


# Convenience function for simple usage
async def create_relay_connection(
    node_id: str,
    mesh_id: str,
    token: str,
    on_message: Optional[Callable[[RelayMessage], None]] = None,
    relay_url: str = "wss://atmosphere-relay-production.up.railway.app"
) -> RelayConnection:
    """
    Create and connect to relay in one step.
    
    Example:
        async def handle_message(msg: RelayMessage):
            print(f"Received from {msg.source_node}: {msg.payload}")
        
        relay = await create_relay_connection(
            "my-node", 
            "my-mesh", 
            "my-token",
            handle_message
        )
        await relay.send("other-node", {"hello": "world"})
    """
    conn = RelayConnection(node_id, mesh_id, token, relay_url, on_message)
    await conn.connect()
    
    # Wait a moment for connection to establish
    for _ in range(10):
        if conn.connected:
            break
        await asyncio.sleep(0.1)
    
    return conn
