"""
Atmosphere Multi-Transport Layer

Manages 5 independent transport methods with automatic fallback and continuous optimization:
1. Local Network (LAN WebSocket) - Fastest
2. WiFi Direct (P2P) - No router needed
3. BLE Mesh - Works offline
4. Matter - Smart home devices
5. Relay Server - Always works (fallback)
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import aiohttp
from zeroconf import ServiceBrowser, Zeroconf

logger = logging.getLogger(__name__)


# ============================================================================
# Transport Types & Configuration
# ============================================================================

class TransportType(Enum):
    """Transport types in priority order."""
    LAN = "lan"
    WIFI_DIRECT = "wifi_direct"
    BLE_MESH = "ble_mesh"
    MATTER = "matter"
    RELAY = "relay"


TRANSPORT_PRIORITY = [
    TransportType.LAN,
    TransportType.WIFI_DIRECT,
    TransportType.BLE_MESH,
    TransportType.MATTER,
    TransportType.RELAY,
]


@dataclass
class TransportConfig:
    """Configuration for transports."""
    lan: dict = field(default_factory=lambda: {
        "enabled": True,
        "port": 11450,
        "mdns": True,
    })
    wifi_direct: dict = field(default_factory=lambda: {
        "enabled": True,
        "auto_accept": False,
    })
    ble_mesh: dict = field(default_factory=lambda: {
        "enabled": True,
        "advertising": True,
        "scanning": True,
        "max_hops": 3,
    })
    matter: dict = field(default_factory=lambda: {
        "enabled": True,
        "auto_commission": False,
    })
    relay: dict = field(default_factory=lambda: {
        "enabled": True,
        "url": "wss://atmosphere-relay-production.up.railway.app",
        "fallback_urls": [],
    })
    optimization: dict = field(default_factory=lambda: {
        "probe_interval_ms": 30000,
        "switch_threshold": 20,
        "prefer_local": True,
    })
    
    def is_enabled(self, transport_type: TransportType) -> bool:
        config = getattr(self, transport_type.value, {})
        return config.get("enabled", True)
    
    def get_config(self, transport_type: TransportType) -> dict:
        return getattr(self, transport_type.value, {})


@dataclass
class TransportMetrics:
    """Metrics for a transport connection."""
    samples: List[float] = field(default_factory=list)
    successes: int = 0
    failures: int = 0
    last_latency_ms: float = 0
    last_updated: float = field(default_factory=time.time)
    
    @property
    def avg_latency_ms(self) -> float:
        if not self.samples:
            return float('inf')
        return sum(self.samples[-10:]) / len(self.samples[-10:])
    
    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        if total == 0:
            return 1.0
        return self.successes / total
    
    def add_sample(self, latency_ms: float, success: bool):
        self.samples.append(latency_ms)
        if len(self.samples) > 100:
            self.samples = self.samples[-100:]
        self.last_latency_ms = latency_ms
        self.last_updated = time.time()
        if success:
            self.successes += 1
        else:
            self.failures += 1
    
    def score(self) -> float:
        """Calculate transport score (higher = better)."""
        latency_score = max(0, 100 - self.avg_latency_ms)
        reliability_score = self.success_rate * 100
        return latency_score * 0.6 + reliability_score * 0.4


# ============================================================================
# Abstract Transport Base
# ============================================================================

class Transport(ABC):
    """Abstract base for all transports."""
    
    def __init__(self, transport_type: TransportType, config: dict):
        self.type = transport_type
        self.config = config
        self.connected = False
        self.metrics = TransportMetrics()
        self._message_handler: Optional[Callable] = None
    
    @abstractmethod
    async def connect(self, peer_id: str, endpoint: str) -> bool:
        """Connect to a peer."""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from peer."""
        pass
    
    @abstractmethod
    async def send(self, message: bytes) -> bool:
        """Send message to peer."""
        pass
    
    def on_message(self, handler: Callable[[bytes], None]):
        """Set message handler."""
        self._message_handler = handler
    
    async def probe(self) -> float:
        """Probe connection, return latency in ms."""
        start = time.time()
        try:
            await self.send(b'{"type":"ping"}')
            latency = (time.time() - start) * 1000
            self.metrics.add_sample(latency, True)
            return latency
        except Exception:
            self.metrics.add_sample(float('inf'), False)
            return float('inf')


# ============================================================================
# LAN WebSocket Transport
# ============================================================================

class LANTransport(Transport):
    """Local network WebSocket transport."""
    
    def __init__(self, config: dict):
        super().__init__(TransportType.LAN, config)
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._receive_task: Optional[asyncio.Task] = None
    
    async def connect(self, peer_id: str, endpoint: str) -> bool:
        """Connect to peer via WebSocket."""
        try:
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(
                endpoint,
                timeout=aiohttp.ClientTimeout(total=10)
            )
            self.connected = True
            
            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            logger.info(f"LAN connected to {peer_id} at {endpoint}")
            return True
        except Exception as e:
            logger.warning(f"LAN connect failed to {endpoint}: {e}")
            return False
    
    async def disconnect(self):
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
        
        self.connected = False
    
    async def send(self, message: bytes) -> bool:
        if not self._ws or self._ws.closed:
            return False
        try:
            await self._ws.send_bytes(message)
            return True
        except Exception as e:
            logger.warning(f"LAN send failed: {e}")
            return False
    
    async def _receive_loop(self):
        """Receive messages from WebSocket."""
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    if self._message_handler:
                        self._message_handler(msg.data)
                elif msg.type == aiohttp.WSMsgType.TEXT:
                    if self._message_handler:
                        self._message_handler(msg.data.encode())
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break
        except Exception as e:
            logger.warning(f"LAN receive error: {e}")
        finally:
            self.connected = False


# ============================================================================
# Relay Transport
# ============================================================================

class RelayTransport(Transport):
    """Cloud relay transport for NAT traversal."""
    
    def __init__(self, config: dict):
        super().__init__(TransportType.RELAY, config)
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._mesh_id: Optional[str] = None
        self._node_id: Optional[str] = None
    
    async def connect(
        self, 
        mesh_id: str, 
        node_id: str,
        token: Optional[dict] = None,
        is_founder: bool = False,
        mesh_public_key: Optional[str] = None,
        founder_proof: Optional[str] = None,
        capabilities: List[str] = None,
    ) -> bool:
        """
        Connect to relay server.
        
        For founders: provide mesh_public_key and founder_proof
        For members: provide token
        """
        self._mesh_id = mesh_id
        self._node_id = node_id
        
        url = self.config.get("url", "wss://atmosphere-relay-production.up.railway.app")
        endpoint = f"{url}/relay/{mesh_id}"
        
        try:
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(endpoint, timeout=aiohttp.ClientTimeout(total=30))
            
            # Send registration/join message
            if is_founder and mesh_public_key and founder_proof:
                await self._ws.send_json({
                    "type": "register_mesh",
                    "mesh_id": mesh_id,
                    "node_id": node_id,
                    "mesh_public_key": mesh_public_key,
                    "founder_proof": founder_proof,
                    "name": self.config.get("mesh_name", mesh_id[:8]),
                    "display_name": self.config.get("node_name", node_id[:8]),
                    "capabilities": capabilities or [],
                })
                
                # Wait for confirmation
                response = await asyncio.wait_for(self._ws.receive_json(), timeout=10)
                if response.get("type") == "error":
                    logger.error(f"Relay registration failed: {response.get('message')}")
                    await self._ws.close()
                    return False
            else:
                await self._ws.send_json({
                    "type": "join",
                    "mesh_id": mesh_id,
                    "node_id": node_id,
                    "token": token,
                    "capabilities": capabilities or [],
                })
                
                # Wait for peers list or error
                response = await asyncio.wait_for(self._ws.receive_json(), timeout=10)
                if response.get("type") == "error":
                    logger.error(f"Relay join failed: {response.get('message')}")
                    await self._ws.close()
                    return False
            
            self.connected = True
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            logger.info(f"Relay connected to mesh {mesh_id}")
            return True
            
        except Exception as e:
            logger.warning(f"Relay connect failed: {e}")
            return False
    
    async def disconnect(self):
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
        
        self.connected = False
    
    async def send(self, message: bytes) -> bool:
        if not self._ws or self._ws.closed:
            return False
        try:
            # Parse and wrap in relay format
            data = json.loads(message)
            await self._ws.send_json({
                "type": "broadcast",
                "payload": data,
            })
            return True
        except Exception as e:
            logger.warning(f"Relay send failed: {e}")
            return False
    
    async def send_direct(self, target_node: str, message: bytes) -> bool:
        """Send directly to a specific peer."""
        if not self._ws or self._ws.closed:
            return False
        try:
            data = json.loads(message)
            await self._ws.send_json({
                "type": "direct",
                "target": target_node,
                "payload": data,
            })
            return True
        except Exception as e:
            logger.warning(f"Relay direct send failed: {e}")
            return False
    
    async def _receive_loop(self):
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    # Handle relay protocol messages
                    if data.get("type") == "message" and self._message_handler:
                        payload = data.get("payload", {})
                        self._message_handler(json.dumps(payload).encode())
                    elif data.get("type") == "peer_joined":
                        logger.info(f"Peer joined: {data.get('node_id')}")
                    elif data.get("type") == "peer_left":
                        logger.info(f"Peer left: {data.get('node_id')}")
                    elif data.get("type") == "pong":
                        pass
                        
        except Exception as e:
            logger.warning(f"Relay receive error: {e}")
        finally:
            self.connected = False


# ============================================================================
# BLE Mesh Transport (Stub - requires platform-specific implementation)
# ============================================================================

class BLEMeshTransport(Transport):
    """BLE Mesh transport for offline networking."""
    
    def __init__(self, config: dict):
        super().__init__(TransportType.BLE_MESH, config)
        self._available = False
        self._check_availability()
    
    def _check_availability(self):
        """Check if BLE is available on this platform."""
        # BLE mesh requires platform-specific implementation
        # On Mac: CoreBluetooth
        # On Android: Android BLE stack
        # On Linux: BlueZ
        import platform
        self._available = platform.system() in ("Darwin", "Linux")
    
    async def connect(self, peer_id: str, endpoint: str) -> bool:
        if not self._available:
            return False
        # TODO: Implement BLE mesh discovery and connection
        logger.warning("BLE mesh not yet implemented")
        return False
    
    async def disconnect(self):
        pass
    
    async def send(self, message: bytes) -> bool:
        return False


# ============================================================================
# WiFi Direct Transport (Stub)
# ============================================================================

class WiFiDirectTransport(Transport):
    """WiFi Direct P2P transport."""
    
    def __init__(self, config: dict):
        super().__init__(TransportType.WIFI_DIRECT, config)
    
    async def connect(self, peer_id: str, endpoint: str) -> bool:
        # WiFi Direct requires Android/platform-specific implementation
        logger.warning("WiFi Direct not yet implemented")
        return False
    
    async def disconnect(self):
        pass
    
    async def send(self, message: bytes) -> bool:
        return False


# ============================================================================
# Matter Transport (Stub)
# ============================================================================

class MatterTransport(Transport):
    """Matter/Thread transport for smart home devices."""
    
    def __init__(self, config: dict):
        super().__init__(TransportType.MATTER, config)
    
    async def connect(self, peer_id: str, endpoint: str) -> bool:
        # Matter requires chip-tool SDK integration
        logger.warning("Matter not yet implemented")
        return False
    
    async def disconnect(self):
        pass
    
    async def send(self, message: bytes) -> bool:
        return False


# ============================================================================
# Connection Pool (Per-Peer)
# ============================================================================

@dataclass
class ConnectionPool:
    """
    Manages multiple transport connections to a single peer.
    
    Handles automatic fallback and transport switching.
    """
    peer_id: str
    transports: Dict[TransportType, Transport] = field(default_factory=dict)
    preferred: Optional[TransportType] = None
    
    async def send(self, message: bytes) -> bool:
        """Send via best available transport."""
        # Try preferred first
        if self.preferred and self.preferred in self.transports:
            transport = self.transports[self.preferred]
            if transport.connected:
                try:
                    if await transport.send(message):
                        return True
                except Exception:
                    pass
        
        # Fallback chain by priority
        for transport_type in TRANSPORT_PRIORITY:
            if transport_type in self.transports:
                transport = self.transports[transport_type]
                if transport.connected:
                    try:
                        if await transport.send(message):
                            self.preferred = transport_type
                            return True
                    except Exception:
                        continue
        
        return False
    
    def add_transport(self, transport: Transport):
        """Add a transport connection."""
        self.transports[transport.type] = transport
        if self.preferred is None:
            self.preferred = transport.type
    
    def get_best_transport(self) -> Optional[Transport]:
        """Get the best connected transport."""
        best_score = -1
        best_transport = None
        
        for transport in self.transports.values():
            if transport.connected:
                score = transport.metrics.score()
                if score > best_score:
                    best_score = score
                    best_transport = transport
        
        return best_transport
    
    async def disconnect_all(self):
        """Disconnect all transports."""
        for transport in self.transports.values():
            await transport.disconnect()
        self.transports.clear()
        self.preferred = None


# ============================================================================
# Transport Manager (Orchestrator)
# ============================================================================

class TransportManager:
    """
    Orchestrates all transports for a node.
    
    Responsibilities:
    - Discover peers on all transports
    - Maintain connections to mesh members
    - Optimize transport selection
    - Handle automatic failover
    """
    
    def __init__(self, config: TransportConfig, node_id: str, mesh_id: str):
        self.config = config
        self.node_id = node_id
        self.mesh_id = mesh_id
        
        self._pools: Dict[str, ConnectionPool] = {}  # peer_id -> pool
        self._message_handler: Optional[Callable] = None
        self._running = False
        self._probe_task: Optional[asyncio.Task] = None
        self._discovery_task: Optional[asyncio.Task] = None
        
        # Transport instances
        self._lan_server = None
        self._relay: Optional[RelayTransport] = None
        self._zeroconf: Optional[Zeroconf] = None
    
    def on_message(self, handler: Callable[[str, bytes], None]):
        """Set handler for incoming messages: handler(from_peer_id, message)."""
        self._message_handler = handler
    
    async def start(
        self,
        is_founder: bool = False,
        mesh_public_key: Optional[str] = None,
        founder_proof: Optional[str] = None,
        token: Optional[dict] = None,
        capabilities: List[str] = None,
    ):
        """
        Start transport manager.
        
        For founders: provide mesh_public_key and founder_proof
        For members: provide token
        """
        self._running = True
        
        # Start relay connection (always enabled by default)
        if self.config.is_enabled(TransportType.RELAY):
            await self._start_relay(
                is_founder=is_founder,
                mesh_public_key=mesh_public_key,
                founder_proof=founder_proof,
                token=token,
                capabilities=capabilities,
            )
        
        # Start LAN discovery
        if self.config.is_enabled(TransportType.LAN):
            await self._start_lan_discovery()
        
        # Start probe task for optimization
        self._probe_task = asyncio.create_task(self._probe_loop())
        
        logger.info(f"TransportManager started for mesh {self.mesh_id}")
    
    async def stop(self):
        """Stop all transports."""
        self._running = False
        
        if self._probe_task:
            self._probe_task.cancel()
            try:
                await self._probe_task
            except asyncio.CancelledError:
                pass
        
        if self._discovery_task:
            self._discovery_task.cancel()
        
        # Disconnect all peer pools
        for pool in self._pools.values():
            await pool.disconnect_all()
        self._pools.clear()
        
        # Stop relay
        if self._relay:
            await self._relay.disconnect()
        
        # Stop zeroconf
        if self._zeroconf:
            self._zeroconf.close()
        
        logger.info("TransportManager stopped")
    
    async def send(self, peer_id: str, message: bytes) -> bool:
        """Send message to a specific peer."""
        if peer_id not in self._pools:
            return False
        return await self._pools[peer_id].send(message)
    
    async def broadcast(self, message: bytes) -> int:
        """Broadcast to all connected peers. Returns count sent."""
        sent = 0
        for pool in self._pools.values():
            if await pool.send(message):
                sent += 1
        return sent
    
    def get_connected_peers(self) -> List[str]:
        """Get list of connected peer IDs."""
        return [
            peer_id for peer_id, pool in self._pools.items()
            if pool.get_best_transport() is not None
        ]
    
    def get_transport_status(self) -> dict:
        """Get status of all transports."""
        status = {}
        for transport_type in TransportType:
            config = self.config.get_config(transport_type)
            status[transport_type.value] = {
                "enabled": config.get("enabled", True),
                "connected_peers": 0,
            }
        
        # Count peers per transport
        for pool in self._pools.values():
            for transport in pool.transports.values():
                if transport.connected:
                    status[transport.type.value]["connected_peers"] += 1
        
        return status
    
    async def _start_relay(
        self,
        is_founder: bool,
        mesh_public_key: Optional[str],
        founder_proof: Optional[str],
        token: Optional[dict],
        capabilities: List[str],
    ):
        """Start relay transport."""
        config = self.config.get_config(TransportType.RELAY)
        self._relay = RelayTransport(config)
        
        def handle_relay_message(data: bytes):
            if self._message_handler:
                # Extract from_peer from message
                try:
                    msg = json.loads(data)
                    from_peer = msg.get("from", "unknown")
                    self._message_handler(from_peer, data)
                except:
                    pass
        
        self._relay.on_message(handle_relay_message)
        
        success = await self._relay.connect(
            mesh_id=self.mesh_id,
            node_id=self.node_id,
            is_founder=is_founder,
            mesh_public_key=mesh_public_key,
            founder_proof=founder_proof,
            token=token,
            capabilities=capabilities,
        )
        
        if success:
            logger.info("Relay transport connected")
        else:
            logger.warning("Relay transport failed to connect")
    
    async def _start_lan_discovery(self):
        """Start mDNS discovery for LAN peers."""
        try:
            self._zeroconf = Zeroconf()
            
            class AtmosphereListener:
                def __init__(self, manager: TransportManager):
                    self.manager = manager
                
                def add_service(self, zc, type_, name):
                    info = zc.get_service_info(type_, name)
                    if info:
                        asyncio.create_task(self.manager._handle_discovered_peer(info))
                
                def remove_service(self, zc, type_, name):
                    pass
                
                def update_service(self, zc, type_, name):
                    pass
            
            ServiceBrowser(
                self._zeroconf,
                "_atmosphere._tcp.local.",
                AtmosphereListener(self)
            )
            
            logger.info("LAN mDNS discovery started")
        except Exception as e:
            logger.warning(f"mDNS discovery failed: {e}")
    
    async def _handle_discovered_peer(self, service_info):
        """Handle a discovered LAN peer."""
        try:
            peer_id = service_info.properties.get(b"node_id", b"").decode()
            mesh_id = service_info.properties.get(b"mesh_id", b"").decode()
            
            if not peer_id or mesh_id != self.mesh_id or peer_id == self.node_id:
                return
            
            # Get address
            addresses = service_info.parsed_addresses()
            if not addresses:
                return
            
            endpoint = f"ws://{addresses[0]}:{service_info.port}/ws"
            
            # Connect via LAN
            config = self.config.get_config(TransportType.LAN)
            transport = LANTransport(config)
            
            def handle_message(data: bytes):
                if self._message_handler:
                    self._message_handler(peer_id, data)
            
            transport.on_message(handle_message)
            
            if await transport.connect(peer_id, endpoint):
                if peer_id not in self._pools:
                    self._pools[peer_id] = ConnectionPool(peer_id=peer_id)
                self._pools[peer_id].add_transport(transport)
                logger.info(f"LAN connected to peer {peer_id}")
                
        except Exception as e:
            logger.warning(f"Failed to connect to discovered peer: {e}")
    
    async def _probe_loop(self):
        """Periodically probe connections for optimization."""
        interval = self.config.optimization.get("probe_interval_ms", 30000) / 1000
        
        while self._running:
            try:
                await asyncio.sleep(interval)
                
                for pool in self._pools.values():
                    for transport in pool.transports.values():
                        if transport.connected:
                            await transport.probe()
                    
                    # Update preferred transport based on metrics
                    best = pool.get_best_transport()
                    if best and best.type != pool.preferred:
                        logger.info(f"Switching {pool.peer_id} from {pool.preferred} to {best.type}")
                        pool.preferred = best.type
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Probe error: {e}")
