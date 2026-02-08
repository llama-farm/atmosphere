"""
Mesh Connection Manager - Orchestrates resilient multi-transport mesh connectivity.

This is the high-level manager that:
1. Discovers peers via multiple methods (mDNS, relay, manual)
2. Connects to each peer via ALL available transports
3. Routes messages through best transport with instant failover
4. Maintains continuous health monitoring
5. Handles mesh-level events (peer join/leave, gossip, etc.)
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from .resilient_transport import (
    ResilientTransportManager,
    TransportType,
    PeerConnection,
)
from .transports.lan import create_lan_transport
from .transports.relay import RelayTransport, create_relay_transport_factory

log = logging.getLogger(__name__)


@dataclass
class MeshConfig:
    """Configuration for mesh connectivity."""
    node_id: str
    mesh_id: str
    
    # Local server info
    local_host: str = "0.0.0.0"
    local_port: int = 11451
    
    # Relay configuration
    relay_url: Optional[str] = None
    relay_token: Optional[str] = None
    
    # Discovery
    enable_mdns: bool = True
    enable_relay_discovery: bool = True
    
    # Health monitoring
    health_check_interval: float = 10.0
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10
    
    # Transports to enable
    enable_lan: bool = True
    enable_relay: bool = True
    enable_ble: bool = False  # Future
    enable_wifi_direct: bool = False  # Future
    enable_matter: bool = False  # Future


class MeshConnectionManager:
    """
    High-level mesh connection manager.
    
    Orchestrates discovery and resilient connectivity across all transport types.
    Ensures maximum availability by maintaining multiple simultaneous connections
    to each peer.
    """
    
    def __init__(self, config: MeshConfig):
        self.config = config
        self._running = False
        
        # Build transport factories based on config
        factories = {}
        
        if config.enable_lan:
            factories[TransportType.LAN] = create_lan_transport
        
        # NOTE: Don't add RELAY to per-peer transport factories.
        # Relay is multiplexed - one shared connection handles ALL peers.
        # Per-peer transports are only for direct connections (LAN, BLE, etc).
        # The shared self._relay handles relay messaging.
        
        # Create resilient transport manager
        self.transport_manager = ResilientTransportManager(
            node_id=config.node_id,
            transport_factories=factories,
            health_check_interval=config.health_check_interval,
            reconnect_delay=config.reconnect_delay,
            max_reconnect_attempts=config.max_reconnect_attempts,
        )
        
        # Relay connection (separate from per-peer transports)
        self._relay: Optional[RelayTransport] = None
        self._relay_connected = False
        
        # Discovered peers (from all sources)
        self.discovered_peers: Dict[str, Dict[str, Any]] = {}
        
        # Event handlers
        self._on_peer_discovered: Optional[Callable[[str, Dict], None]] = None
        self._on_peer_connected: Optional[Callable[[str], None]] = None
        self._on_peer_disconnected: Optional[Callable[[str], None]] = None
        self._on_message: Optional[Callable[[str, bytes], None]] = None
        
        # Background tasks
        self._tasks: List[asyncio.Task] = []
    
    async def start(self):
        """Start the mesh connection manager."""
        if self._running:
            return
        
        self._running = True
        log.info(f"Starting MeshConnectionManager for node {self.config.node_id}")
        
        # Start transport manager
        await self.transport_manager.start()
        
        # Set up transport manager callbacks
        self.transport_manager.on_peer_connected(self._handle_peer_connected)
        self.transport_manager.on_peer_disconnected(self._handle_peer_disconnected)
        self.transport_manager.on_message(self._handle_message)
        
        # Connect to relay if configured
        if self.config.enable_relay and self.config.relay_url:
            self._tasks.append(
                asyncio.create_task(self._connect_relay())
            )
        
        # Start peer discovery
        if self.config.enable_mdns:
            self._tasks.append(
                asyncio.create_task(self._mdns_discovery_loop())
            )
        
        log.info(f"MeshConnectionManager started (relay_url={self.config.relay_url}, relay_enabled={self.config.enable_relay})")
        print(f"[MESH] MeshConnectionManager started - relay={self.config.relay_url}, enabled={self.config.enable_relay}", flush=True)
    
    async def stop(self):
        """Stop the mesh connection manager."""
        self._running = False
        
        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        
        # Disconnect relay
        if self._relay:
            await self._relay.disconnect()
            self._relay = None
        
        # Stop transport manager
        await self.transport_manager.stop()
        
        log.info("MeshConnectionManager stopped")
    
    async def _connect_relay(self):
        """Connect to relay server and maintain connection. Never gives up."""
        print(f"[MESH] _connect_relay task started", flush=True)
        reconnect_attempt = 0
        reconnect_delays = [1, 2, 4, 8, 16, 30]  # Exponential backoff, max 30s
        
        while self._running:
            if not self._relay_connected:
                try:
                    # Clean up old relay if exists
                    if self._relay:
                        try:
                            await self._relay.disconnect()
                        except:
                            pass
                    
                    self._relay = RelayTransport(
                        self.config.node_id,
                        self.config.mesh_id,
                        self.config.relay_token
                    )
                    
                    # Set up relay callbacks
                    self._relay.on_peers_updated(self._handle_relay_peers)
                    self._relay.on_peer_joined(self._handle_relay_peer_joined)
                    self._relay.on_peer_left(self._handle_relay_peer_left)
                    self._relay.set_message_handler(
                        lambda msg: self._handle_message("relay", msg)
                    )
                    
                    # Build full relay URL with mesh path
                    relay_full_url = f"{self.config.relay_url}/relay/{self.config.mesh_id}"
                    log.info(f"Attempting to connect to relay: {relay_full_url} (attempt {reconnect_attempt + 1})")
                    
                    success = await self._relay.connect(relay_full_url)
                    print(f"[RELAY-CONNECT] Result: {success}", flush=True)
                    if success:
                        self._relay_connected = True
                        reconnect_attempt = 0  # Reset on success
                        log.info(f"✅ Connected to relay server: {relay_full_url}")
                        print(f"[RELAY] ✅ Connected to {relay_full_url}", flush=True)
                    else:
                        reconnect_attempt += 1
                        delay = reconnect_delays[min(reconnect_attempt - 1, len(reconnect_delays) - 1)]
                        log.warning(f"❌ Failed to connect to relay: {relay_full_url}, retry in {delay}s...")
                        await asyncio.sleep(delay)
                        continue
                        
                except Exception as e:
                    reconnect_attempt += 1
                    delay = reconnect_delays[min(reconnect_attempt - 1, len(reconnect_delays) - 1)]
                    log.error(f"❌ Relay connection error: {e}, retry in {delay}s", exc_info=True)
                    await asyncio.sleep(delay)
                    continue
            
            # Check connection periodically (every 5s for faster detection)
            await asyncio.sleep(5.0)
            
            # Check if relay is still connected
            if self._relay:
                if not self._relay.is_connected:
                    log.warning("Relay connection lost, triggering reconnect...")
                    self._relay_connected = False
                    reconnect_attempt = 0  # Fresh start for new disconnect
    
    async def _mdns_discovery_loop(self):
        """Background task for mDNS peer discovery."""
        # Import here to avoid circular imports
        try:
            from zeroconf import ServiceBrowser, Zeroconf
            from zeroconf.asyncio import AsyncZeroconf
        except ImportError:
            log.warning("zeroconf not installed, mDNS discovery disabled")
            return
        
        # mDNS discovery implementation would go here
        # For now, we rely on relay and manual discovery
        while self._running:
            await asyncio.sleep(30.0)
    
    def _handle_relay_peers(self, peers: Dict[str, Dict]):
        """Handle peer list update from relay."""
        for peer_id, peer_info in peers.items():
            if peer_id == self.config.node_id:
                continue  # Skip self
            
            self._discover_peer(peer_id, {
                "source": "relay",
                "relay_url": self.config.relay_url,
                **peer_info
            })
    
    def _handle_relay_peer_joined(self, peer_id: str):
        """Handle new peer joining via relay."""
        if peer_id == self.config.node_id:
            return
        
        self._discover_peer(peer_id, {
            "source": "relay",
            "relay_url": self.config.relay_url,
        })
    
    def _handle_relay_peer_left(self, peer_id: str):
        """Handle peer leaving relay."""
        if peer_id in self.discovered_peers:
            # Don't remove entirely - might still be reachable via other transports
            self.discovered_peers[peer_id]["relay_available"] = False
    
    def _discover_peer(self, peer_id: str, peer_info: Dict[str, Any]):
        """Handle peer discovery from any source."""
        is_new = peer_id not in self.discovered_peers
        
        if is_new:
            self.discovered_peers[peer_id] = {
                "peer_id": peer_id,
                "discovered_at": datetime.now().isoformat(),
            }
        
        # Merge new info
        self.discovered_peers[peer_id].update(peer_info)
        self.discovered_peers[peer_id]["last_seen"] = datetime.now().isoformat()
        
        # Notify handler
        if self._on_peer_discovered:
            self._on_peer_discovered(peer_id, self.discovered_peers[peer_id])
        
        # Initiate connection via all available transports
        if is_new:
            asyncio.create_task(self._connect_to_peer(peer_id))
    
    async def _connect_to_peer(self, peer_id: str):
        """Connect to a discovered peer via all available transports."""
        if peer_id not in self.discovered_peers:
            return
        
        peer_info = self.discovered_peers[peer_id]
        
        # Build connection info from discovered data
        connect_info = {}
        
        # LAN address
        if "lan_address" in peer_info:
            connect_info["lan_address"] = peer_info["lan_address"]
        elif "host" in peer_info and "port" in peer_info:
            connect_info["lan_address"] = f"ws://{peer_info['host']}:{peer_info['port']}/mesh/ws"
        
        # Relay URL (must include mesh path for per-peer transport)
        if "relay_url" in peer_info:
            base_url = peer_info["relay_url"].rstrip("/")
            # Build full relay URL with mesh path
            connect_info["relay_url"] = f"{base_url}/relay/{self.config.mesh_id}"
        
        # BLE address
        if "ble_address" in peer_info:
            connect_info["ble_address"] = peer_info["ble_address"]
        
        if not connect_info:
            log.warning(f"No connection info for peer {peer_id}")
            return
        
        # Connect via transport manager (handles multi-transport)
        await self.transport_manager.connect_peer(peer_id, connect_info)
    
    def _handle_peer_connected(self, peer_id: str):
        """Handle peer connection event."""
        log.info(f"Peer connected: {peer_id}")
        if self._on_peer_connected:
            self._on_peer_connected(peer_id)
    
    def _handle_peer_disconnected(self, peer_id: str):
        """Handle peer disconnection event."""
        log.info(f"Peer disconnected: {peer_id}")
        if self._on_peer_disconnected:
            self._on_peer_disconnected(peer_id)
    
    def _handle_message(self, peer_id: str, message: bytes):
        """Handle incoming message from any peer."""
        if self._on_message:
            self._on_message(peer_id, message)
    
    async def send(self, peer_id: str, message: bytes) -> bool:
        """Send message to a specific peer (via best available transport)."""
        # Try direct transports first (LAN, BLE)
        if peer_id in self.transport_manager.peers:
            if self.transport_manager.peers[peer_id].is_reachable:
                return await self.transport_manager.send(peer_id, message)
        
        # Fallback to shared relay for relay-discovered peers
        if self._relay and self._relay.is_connected:
            peer_info = self.discovered_peers.get(peer_id, {})
            if peer_info.get("source") == "relay":
                try:
                    # Use relay's "direct" message type for targeted send
                    import json
                    relay_msg = {
                        "type": "direct",
                        "target": peer_id,
                        "payload": message.decode() if isinstance(message, bytes) else message,
                    }
                    await self._relay.send(json.dumps(relay_msg).encode())
                    return True
                except Exception as e:
                    log.warning(f"Relay send to {peer_id} failed: {e}")
        
        return False
    
    async def broadcast(self, message: bytes, exclude: Optional[Set[str]] = None) -> int:
        """Broadcast message to all connected peers."""
        count = await self.transport_manager.broadcast(message, exclude)
        
        # Also broadcast via relay if connected
        if self._relay and self._relay.is_connected:
            try:
                await self._relay.send(message)
            except Exception as e:
                log.warning(f"Relay broadcast failed: {e}")
        
        return count
    
    async def add_peer(self, peer_id: str, peer_info: Dict[str, Any]):
        """Manually add a peer (e.g., from QR code scan)."""
        self._discover_peer(peer_id, peer_info)
    
    def _is_peer_reachable(self, pid: str, info: Dict[str, Any]) -> bool:
        """Check if peer is reachable via any transport."""
        # Check direct transports (LAN, BLE, etc)
        if pid in self.transport_manager.peers:
            if self.transport_manager.peers[pid].is_reachable:
                return True
        # Check shared relay (for relay-discovered peers)
        if self._relay_connected and info.get("source") == "relay":
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """Get current mesh connection status."""
        return {
            "node_id": self.config.node_id,
            "mesh_id": self.config.mesh_id,
            "relay_connected": self._relay_connected,
            "relay_url": self.config.relay_url,
            "discovered_peers": len(self.discovered_peers),
            "connected_peers": sum(
                1 for pid, info in self.discovered_peers.items()
                if self._is_peer_reachable(pid, info)
            ),
            "transports": self.transport_manager.get_status(),
            "peers": {
                pid: {
                    "discovered": info,
                    "connected": (
                        self.transport_manager.peers.get(pid).connected_count
                        if pid in self.transport_manager.peers else (1 if self._relay_connected and info.get("source") == "relay" else 0)
                    ),
                    "reachable": self._is_peer_reachable(pid, info),
                }
                for pid, info in self.discovered_peers.items()
            },
        }
    
    # Event handler setters
    def on_peer_discovered(self, handler: Callable[[str, Dict], None]):
        self._on_peer_discovered = handler
    
    def on_peer_connected(self, handler: Callable[[str], None]):
        self._on_peer_connected = handler
    
    def on_peer_disconnected(self, handler: Callable[[str], None]):
        self._on_peer_disconnected = handler
    
    def on_message(self, handler: Callable[[str, bytes], None]):
        self._on_message = handler
