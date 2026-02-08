"""
Resilient Multi-Transport Manager for Atmosphere Mesh.

Design Philosophy:
- Connect ALL available transports simultaneously
- Route messages via BEST transport (lowest latency, highest reliability)
- Instant failover when primary fails (no reconnection delay)
- Continuous health monitoring keeps connections warm
- Graceful degradation as transports fail/recover

Transport Priority (dynamic, based on real-time metrics):
1. LAN/mDNS - ~1-5ms latency, lowest battery cost
2. WiFi Direct - ~5-20ms, peer-to-peer, no infrastructure  
3. BLE Mesh - ~50-100ms, works offline, limited bandwidth
4. Matter/Thread - ~30-80ms, smart home integration
5. Cloud Relay - ~100-500ms, works anywhere, highest latency
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import json

log = logging.getLogger(__name__)


class TransportType(Enum):
    """Available transport types, ordered by typical preference."""
    LAN = "lan"           # Direct TCP/WebSocket on local network
    WIFI_DIRECT = "wifi_direct"  # P2P WiFi connection
    BLE = "ble"           # Bluetooth Low Energy mesh
    MATTER = "matter"     # Matter/Thread smart home protocol
    RELAY = "relay"       # Cloud relay (fallback)


class TransportState(Enum):
    """Connection state for a transport."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"      # Failed, will retry
    UNAVAILABLE = "unavailable"  # Not possible (e.g., no BLE hardware)


@dataclass
class TransportMetrics:
    """Real-time metrics for a transport connection."""
    transport_type: TransportType
    state: TransportState = TransportState.DISCONNECTED
    
    # Latency tracking (rolling average)
    latency_ms: float = float('inf')
    latency_samples: List[float] = field(default_factory=list)
    max_latency_samples: int = 10
    
    # Reliability tracking
    packets_sent: int = 0
    packets_failed: int = 0
    consecutive_failures: int = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    
    # Cost factors
    battery_cost: float = 0.1  # 0.0-1.0, higher = more drain
    bandwidth_kbps: float = 1000.0  # Estimated bandwidth
    
    # Connection info
    connected_at: Optional[datetime] = None
    reconnect_attempts: int = 0
    
    def record_latency(self, latency_ms: float):
        """Record a latency sample and update rolling average."""
        self.latency_samples.append(latency_ms)
        if len(self.latency_samples) > self.max_latency_samples:
            self.latency_samples.pop(0)
        self.latency_ms = sum(self.latency_samples) / len(self.latency_samples)
        self.last_success = datetime.now()
        self.consecutive_failures = 0
    
    def record_failure(self):
        """Record a send/ping failure."""
        self.packets_failed += 1
        self.consecutive_failures += 1
        self.last_failure = datetime.now()
    
    def record_success(self):
        """Record a successful send."""
        self.packets_sent += 1
        self.last_success = datetime.now()
        self.consecutive_failures = 0
    
    @property
    def packet_loss(self) -> float:
        """Calculate packet loss ratio (0.0-1.0)."""
        total = self.packets_sent + self.packets_failed
        if total == 0:
            return 0.0
        return self.packets_failed / total
    
    @property
    def is_healthy(self) -> bool:
        """Check if transport is healthy enough to use."""
        if self.state != TransportState.CONNECTED:
            return False
        if self.consecutive_failures >= 3:
            return False
        return True
    
    def score(self) -> float:
        """
        Calculate transport score. Higher = better.
        
        Used for selecting best transport:
        - 40% weight on latency (lower is better)
        - 40% weight on reliability (less packet loss is better)
        - 20% weight on battery cost (lower drain is better)
        """
        if not self.is_healthy:
            return 0.0
        
        # Normalize latency: 0ms = 1.0, 500ms+ = 0.0
        latency_score = max(0.0, 1.0 - (self.latency_ms / 500.0))
        
        # Reliability: 0% loss = 1.0, 100% loss = 0.0
        reliability_score = 1.0 - self.packet_loss
        
        # Battery: 0.0 cost = 1.0 score, 1.0 cost = 0.0 score
        battery_score = 1.0 - self.battery_cost
        
        # Penalize recent failures even if technically "healthy"
        recency_penalty = 0.0
        if self.last_failure and self.consecutive_failures > 0:
            since_failure = (datetime.now() - self.last_failure).total_seconds()
            if since_failure < 30:  # Penalty decays over 30 seconds
                recency_penalty = 0.2 * (1.0 - since_failure / 30.0)
        
        return (
            latency_score * 0.4 +
            reliability_score * 0.4 +
            battery_score * 0.2 -
            recency_penalty
        )


class Transport(ABC):
    """Abstract base class for mesh transports."""
    
    def __init__(self, transport_type: TransportType):
        self.transport_type = transport_type
        self.metrics = TransportMetrics(transport_type=transport_type)
        self._message_handler: Optional[Callable[[bytes], None]] = None
    
    @abstractmethod
    async def connect(self, address: str) -> bool:
        """Connect to peer at address. Returns True on success."""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from peer."""
        pass
    
    @abstractmethod
    async def send(self, message: bytes) -> bool:
        """Send message to peer. Returns True on success."""
        pass
    
    @abstractmethod
    async def ping(self) -> float:
        """Ping peer and return latency in ms."""
        pass
    
    @property
    def is_connected(self) -> bool:
        return self.metrics.state == TransportState.CONNECTED
    
    def set_message_handler(self, handler: Callable[[bytes], None]):
        """Set handler for incoming messages."""
        self._message_handler = handler
    
    def on_message(self, message: bytes):
        """Called when message received from peer."""
        if self._message_handler:
            self._message_handler(message)


@dataclass
class PeerConnection:
    """All transport connections to a single peer."""
    peer_id: str
    transports: Dict[TransportType, Transport] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    
    # Known addresses for this peer
    lan_address: Optional[str] = None
    relay_url: Optional[str] = None
    ble_address: Optional[str] = None
    wifi_direct_address: Optional[str] = None
    matter_address: Optional[str] = None
    
    def get_best_transport(self) -> Optional[Transport]:
        """Get best available transport by score."""
        healthy = [t for t in self.transports.values() if t.metrics.is_healthy]
        if not healthy:
            return None
        return max(healthy, key=lambda t: t.metrics.score())
    
    def get_transports_by_score(self) -> List[Transport]:
        """Get all transports sorted by score (best first)."""
        return sorted(
            self.transports.values(),
            key=lambda t: t.metrics.score(),
            reverse=True
        )
    
    @property
    def connected_count(self) -> int:
        """Number of currently connected transports."""
        return sum(1 for t in self.transports.values() if t.is_connected)
    
    @property
    def is_reachable(self) -> bool:
        """Check if peer is reachable via any transport."""
        return any(t.metrics.is_healthy for t in self.transports.values())


class ResilientTransportManager:
    """
    Manages multiple simultaneous transport connections for mesh resilience.
    
    Key behaviors:
    1. Connect ALL available transports to each peer simultaneously
    2. Route messages via best transport (scored by latency + reliability)
    3. Instant failover when primary fails (already connected to alternatives)
    4. Continuous health monitoring keeps connections warm
    5. Auto-reconnect failed transports in background
    """
    
    def __init__(
        self,
        node_id: str,
        transport_factories: Optional[Dict[TransportType, Callable[[], Transport]]] = None,
        health_check_interval: float = 10.0,
        reconnect_delay: float = 5.0,
        max_reconnect_attempts: int = 10,
    ):
        self.node_id = node_id
        self.transport_factories = transport_factories or {}
        self.health_check_interval = health_check_interval
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        
        # Peer connections
        self.peers: Dict[str, PeerConnection] = {}
        
        # Background tasks
        self._health_monitor_task: Optional[asyncio.Task] = None
        self._reconnect_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        
        # Event handlers
        self._on_peer_connected: Optional[Callable[[str], None]] = None
        self._on_peer_disconnected: Optional[Callable[[str], None]] = None
        self._on_message: Optional[Callable[[str, bytes], None]] = None
        
        # Stats
        self.stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "failovers": 0,
            "reconnects": 0,
        }
    
    async def start(self):
        """Start the transport manager and health monitor."""
        if self._running:
            return
        
        self._running = True
        self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
        log.info(f"ResilientTransportManager started for node {self.node_id}")
    
    async def stop(self):
        """Stop the transport manager and disconnect all peers."""
        self._running = False
        
        # Cancel health monitor
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass
        
        # Cancel reconnect tasks
        for task in self._reconnect_tasks.values():
            task.cancel()
        
        # Disconnect all peers
        for peer in self.peers.values():
            for transport in peer.transports.values():
                await transport.disconnect()
        
        self.peers.clear()
        log.info("ResilientTransportManager stopped")
    
    async def connect_peer(self, peer_id: str, peer_info: Dict[str, Any]) -> PeerConnection:
        """
        Connect to a peer via ALL available transports simultaneously.
        
        peer_info should contain available addresses:
        - lan_address: IP:port for direct connection
        - relay_url: WebSocket URL for relay
        - ble_address: Bluetooth address
        - wifi_direct_address: WiFi Direct address
        - matter_address: Matter device address
        """
        if peer_id in self.peers:
            peer = self.peers[peer_id]
            # Update known addresses
            peer.lan_address = peer_info.get("lan_address", peer.lan_address)
            peer.relay_url = peer_info.get("relay_url", peer.relay_url)
            peer.ble_address = peer_info.get("ble_address", peer.ble_address)
        else:
            peer = PeerConnection(
                peer_id=peer_id,
                lan_address=peer_info.get("lan_address"),
                relay_url=peer_info.get("relay_url"),
                ble_address=peer_info.get("ble_address"),
                wifi_direct_address=peer_info.get("wifi_direct_address"),
                matter_address=peer_info.get("matter_address"),
            )
            self.peers[peer_id] = peer
        
        # Connect via ALL available transports in parallel
        connect_tasks = []
        
        if peer.lan_address and TransportType.LAN in self.transport_factories:
            connect_tasks.append(
                self._connect_transport(peer, TransportType.LAN, peer.lan_address)
            )
        
        if peer.relay_url and TransportType.RELAY in self.transport_factories:
            connect_tasks.append(
                self._connect_transport(peer, TransportType.RELAY, peer.relay_url)
            )
        
        if peer.ble_address and TransportType.BLE in self.transport_factories:
            connect_tasks.append(
                self._connect_transport(peer, TransportType.BLE, peer.ble_address)
            )
        
        if peer.wifi_direct_address and TransportType.WIFI_DIRECT in self.transport_factories:
            connect_tasks.append(
                self._connect_transport(peer, TransportType.WIFI_DIRECT, peer.wifi_direct_address)
            )
        
        if peer.matter_address and TransportType.MATTER in self.transport_factories:
            connect_tasks.append(
                self._connect_transport(peer, TransportType.MATTER, peer.matter_address)
            )
        
        # Connect all in parallel, don't fail if some fail
        if connect_tasks:
            results = await asyncio.gather(*connect_tasks, return_exceptions=True)
            successful = sum(1 for r in results if r is True)
            log.info(f"Connected to peer {peer_id} via {successful}/{len(connect_tasks)} transports")
        
        # Notify if at least one connection succeeded
        if peer.is_reachable and self._on_peer_connected:
            self._on_peer_connected(peer_id)
        
        return peer
    
    async def _connect_transport(
        self, 
        peer: PeerConnection, 
        transport_type: TransportType, 
        address: str
    ) -> bool:
        """Connect a single transport to a peer."""
        try:
            # Skip if already connected
            if transport_type in peer.transports and peer.transports[transport_type].is_connected:
                return True
            
            # Create transport
            factory = self.transport_factories.get(transport_type)
            if not factory:
                return False
            
            transport = factory()
            transport.metrics.state = TransportState.CONNECTING
            
            # Set message handler
            transport.set_message_handler(
                lambda msg, pid=peer.peer_id: self._handle_message(pid, msg)
            )
            
            # Connect
            success = await transport.connect(address)
            
            if success:
                transport.metrics.state = TransportState.CONNECTED
                transport.metrics.connected_at = datetime.now()
                transport.metrics.reconnect_attempts = 0
                peer.transports[transport_type] = transport
                log.debug(f"Connected to {peer.peer_id} via {transport_type.value}")
                return True
            else:
                transport.metrics.state = TransportState.FAILED
                return False
                
        except Exception as e:
            log.warning(f"Failed to connect to {peer.peer_id} via {transport_type.value}: {e}")
            return False
    
    async def disconnect_peer(self, peer_id: str):
        """Disconnect all transports to a peer."""
        if peer_id not in self.peers:
            return
        
        peer = self.peers[peer_id]
        for transport in peer.transports.values():
            await transport.disconnect()
        
        del self.peers[peer_id]
        
        if self._on_peer_disconnected:
            self._on_peer_disconnected(peer_id)
    
    async def send(self, peer_id: str, message: bytes) -> bool:
        """
        Send message to peer via best available transport.
        Automatically fails over to next best if primary fails.
        """
        if peer_id not in self.peers:
            log.warning(f"Cannot send to unknown peer: {peer_id}")
            return False
        
        peer = self.peers[peer_id]
        transports = peer.get_transports_by_score()
        
        if not transports:
            log.warning(f"No transports available for peer: {peer_id}")
            return False
        
        primary_failed = False
        for i, transport in enumerate(transports):
            if not transport.metrics.is_healthy:
                continue
            
            try:
                success = await transport.send(message)
                if success:
                    transport.metrics.record_success()
                    self.stats["messages_sent"] += 1
                    
                    if primary_failed:
                        self.stats["failovers"] += 1
                        log.info(f"Failover successful: {peer_id} via {transport.transport_type.value}")
                    
                    return True
                else:
                    transport.metrics.record_failure()
                    primary_failed = True
                    
            except Exception as e:
                log.warning(f"Send failed via {transport.transport_type.value}: {e}")
                transport.metrics.record_failure()
                primary_failed = True
        
        log.error(f"All transports failed for peer: {peer_id}")
        return False
    
    async def broadcast(self, message: bytes, exclude: Optional[Set[str]] = None) -> int:
        """Broadcast message to all connected peers. Returns number of peers reached."""
        exclude = exclude or set()
        tasks = [
            self.send(peer_id, message)
            for peer_id in self.peers
            if peer_id not in exclude and self.peers[peer_id].is_reachable
        ]
        
        if not tasks:
            return 0
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return sum(1 for r in results if r is True)
    
    def _handle_message(self, peer_id: str, message: bytes):
        """Handle incoming message from a peer."""
        self.stats["messages_received"] += 1
        
        if peer_id in self.peers:
            self.peers[peer_id].last_seen = datetime.now()
        
        if self._on_message:
            self._on_message(peer_id, message)
    
    async def _health_monitor_loop(self):
        """
        Background task that continuously monitors all transport connections.
        
        - Pings each transport to measure real latency
        - Marks failed transports
        - Triggers reconnection for failed transports
        """
        while self._running:
            try:
                await self._health_check_all()
            except Exception as e:
                log.error(f"Health monitor error: {e}")
            
            await asyncio.sleep(self.health_check_interval)
    
    async def _health_check_all(self):
        """Ping all transports and update metrics."""
        for peer_id, peer in list(self.peers.items()):
            for transport_type, transport in list(peer.transports.items()):
                try:
                    if transport.metrics.state == TransportState.CONNECTED:
                        # Ping and measure latency
                        latency = await asyncio.wait_for(
                            transport.ping(),
                            timeout=5.0
                        )
                        transport.metrics.record_latency(latency)
                        
                    elif transport.metrics.state == TransportState.FAILED:
                        # Attempt reconnection
                        self._schedule_reconnect(peer, transport_type)
                        
                except asyncio.TimeoutError:
                    log.warning(f"Ping timeout: {peer_id} via {transport_type.value}")
                    transport.metrics.record_failure()
                    if transport.metrics.consecutive_failures >= 3:
                        transport.metrics.state = TransportState.FAILED
                        self._schedule_reconnect(peer, transport_type)
                        
                except Exception as e:
                    log.warning(f"Health check failed: {peer_id} via {transport_type.value}: {e}")
                    transport.metrics.record_failure()
    
    def _schedule_reconnect(self, peer: PeerConnection, transport_type: TransportType):
        """Schedule a reconnection attempt for a failed transport."""
        key = f"{peer.peer_id}:{transport_type.value}"
        
        if key in self._reconnect_tasks and not self._reconnect_tasks[key].done():
            return  # Already reconnecting
        
        if peer.transports.get(transport_type):
            if peer.transports[transport_type].metrics.reconnect_attempts >= self.max_reconnect_attempts:
                log.warning(f"Max reconnect attempts reached: {key}")
                return
        
        self._reconnect_tasks[key] = asyncio.create_task(
            self._reconnect(peer, transport_type)
        )
    
    async def _reconnect(self, peer: PeerConnection, transport_type: TransportType):
        """Attempt to reconnect a failed transport."""
        await asyncio.sleep(self.reconnect_delay)
        
        address = None
        if transport_type == TransportType.LAN:
            address = peer.lan_address
        elif transport_type == TransportType.RELAY:
            address = peer.relay_url
        elif transport_type == TransportType.BLE:
            address = peer.ble_address
        elif transport_type == TransportType.WIFI_DIRECT:
            address = peer.wifi_direct_address
        elif transport_type == TransportType.MATTER:
            address = peer.matter_address
        
        if not address:
            return
        
        if transport_type in peer.transports:
            peer.transports[transport_type].metrics.reconnect_attempts += 1
        
        success = await self._connect_transport(peer, transport_type, address)
        if success:
            self.stats["reconnects"] += 1
            log.info(f"Reconnected to {peer.peer_id} via {transport_type.value}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of all peer connections."""
        status = {
            "node_id": self.node_id,
            "peers": {},
            "stats": self.stats,
        }
        
        for peer_id, peer in self.peers.items():
            peer_status = {
                "reachable": peer.is_reachable,
                "connected_transports": peer.connected_count,
                "last_seen": peer.last_seen.isoformat() if peer.last_seen else None,
                "transports": {},
            }
            
            for transport_type, transport in peer.transports.items():
                m = transport.metrics
                peer_status["transports"][transport_type.value] = {
                    "state": m.state.value,
                    "latency_ms": round(m.latency_ms, 1) if m.latency_ms != float('inf') else None,
                    "packet_loss": round(m.packet_loss * 100, 1),
                    "score": round(m.score(), 3),
                    "consecutive_failures": m.consecutive_failures,
                }
            
            status["peers"][peer_id] = peer_status
        
        return status
    
    # Event handler setters
    def on_peer_connected(self, handler: Callable[[str], None]):
        self._on_peer_connected = handler
    
    def on_peer_disconnected(self, handler: Callable[[str], None]):
        self._on_peer_disconnected = handler
    
    def on_message(self, handler: Callable[[str, bytes], None]):
        self._on_message = handler
