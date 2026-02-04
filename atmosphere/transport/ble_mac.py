"""
BLE Transport for Atmosphere Mesh (Mac/Python with bleak).

Provides BLE GATT server/client for offline mesh discovery and messaging.
Compatible with Android Atmosphere nodes.
"""

import asyncio
import struct
import hashlib
import time
import platform
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Callable, Any
from collections import OrderedDict
import logging
import uuid
try:
    import cbor2
    CBOR_AVAILABLE = True
except ImportError:
    CBOR_AVAILABLE = False
    import json

try:
    from bleak import BleakClient, BleakScanner
    from bleak.backends.characteristic import BleakGATTCharacteristic
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False

# On macOS, we can use bleak-server or bless for GATT server
try:
    from bless import BlessServer, BlessGATTCharacteristic, GATTCharacteristicProperties, GATTAttributePermissions
    BLESS_AVAILABLE = True
except ImportError:
    BLESS_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================================
# UUIDs (MUST match Android implementation exactly!)
# ============================================================================

# These UUIDs are aligned with Android's BleTransport.kt
MESH_SERVICE_UUID = "A7A05F30-0001-4000-8000-00805F9B34FB"
TX_CHAR_UUID = "A7A05F30-0002-4000-8000-00805F9B34FB"
RX_CHAR_UUID = "A7A05F30-0003-4000-8000-00805F9B34FB"
INFO_CHAR_UUID = "A7A05F30-0004-4000-8000-00805F9B34FB"
MESH_ID_CHAR_UUID = "A7A05F30-0005-4000-8000-00805F9B34FB"
CCCD_UUID = "00002902-0000-1000-8000-00805F9B34FB"

# Manufacturer ID for service data (Atmosphere = 0xA7F0)
ATMOSPHERE_MANUFACTURER_ID = 0xA7F0

# Default configuration
DEFAULT_TTL = 5
MAX_FRAGMENT_SIZE = 236  # 244 MTU - 8 byte header
MAX_MESSAGE_SIZE = 64 * 1024  # 64KB max message size
REASSEMBLY_TIMEOUT = 30.0  # seconds
SEEN_MESSAGE_CACHE_SIZE = 1000


# ============================================================================
# Message Protocol
# ============================================================================

class MessageType(IntEnum):
    """BLE Mesh message types."""
    # Discovery
    HELLO = 0x01
    HELLO_ACK = 0x02
    GOODBYE = 0x03
    
    # Routing
    ROUTE_REQ = 0x10
    ROUTE_REP = 0x11
    
    # Data
    DATA = 0x20
    DATA_ACK = 0x21
    
    # Mesh management
    MESH_INFO = 0x30
    CAPABILITY = 0x31


class MessageFlags(IntEnum):
    """Message flag bits."""
    ENCRYPTED = 0x01
    BROADCAST = 0x02
    PRIORITY = 0x04
    RELIABLE = 0x08


@dataclass
class MessageHeader:
    """8-byte message header."""
    version: int = 1
    msg_type: MessageType = MessageType.DATA
    ttl: int = DEFAULT_TTL
    flags: int = 0
    seq: int = 0
    frag_index: int = 0
    frag_total: int = 1
    
    def pack(self) -> bytes:
        """Pack header to bytes."""
        return struct.pack(
            'BBBBHBB',
            self.version,
            self.msg_type,
            self.ttl,
            self.flags,
            self.seq & 0xFFFF,
            self.frag_index,
            self.frag_total
        )
    
    @classmethod
    def unpack(cls, data: bytes) -> 'MessageHeader':
        """Unpack header from bytes."""
        if len(data) < 8:
            raise ValueError(f"Header too short: {len(data)} bytes")
        
        version, msg_type, ttl, flags, seq, frag_index, frag_total = struct.unpack(
            'BBBBHBB', data[:8]
        )
        
        return cls(
            version=version,
            msg_type=MessageType(msg_type),
            ttl=ttl,
            flags=flags,
            seq=seq,
            frag_index=frag_index,
            frag_total=frag_total
        )


@dataclass
class BleMessage:
    """Complete BLE mesh message."""
    header: MessageHeader
    payload: bytes
    source_id: str = ""  # Set by transport
    
    @property
    def data(self) -> bytes:
        """Get full message bytes (header + payload)."""
        return self.header.pack() + self.payload
    
    @classmethod
    def from_bytes(cls, data: bytes, source_id: str = "") -> 'BleMessage':
        """Parse message from bytes."""
        header = MessageHeader.unpack(data)
        payload = data[8:]
        return cls(header=header, payload=payload, source_id=source_id)
    
    def decode_cbor(self) -> Any:
        """Decode CBOR payload (or JSON fallback)."""
        if CBOR_AVAILABLE:
            return cbor2.loads(self.payload)
        else:
            return json.loads(self.payload.decode('utf-8'))


@dataclass
class NodeInfo:
    """Information about an Atmosphere node."""
    node_id: str
    name: str = ""
    capabilities: List[str] = field(default_factory=list)
    platform: str = ""
    version: str = "1.0"
    rssi: int = 0
    last_seen: float = 0


# ============================================================================
# LRU Cache for seen messages (loop prevention)
# ============================================================================

class LRUCache:
    """Simple LRU cache for message deduplication."""
    
    def __init__(self, maxsize: int = SEEN_MESSAGE_CACHE_SIZE):
        self.maxsize = maxsize
        self.cache: OrderedDict = OrderedDict()
    
    def __contains__(self, key) -> bool:
        if key in self.cache:
            self.cache.move_to_end(key)
            return True
        return False
    
    def add(self, key, value=None):
        """Add key to cache."""
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            self.cache[key] = value or time.time()
            while len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)


# ============================================================================
# Message Fragmentation
# ============================================================================

class MessageFragmenter:
    """Handles message fragmentation and reassembly."""
    
    def __init__(self, mtu: int = MAX_FRAGMENT_SIZE):
        self.mtu = mtu
        self.pending_reassembly: Dict[tuple, Dict[int, bytes]] = {}
        self.reassembly_timestamps: Dict[tuple, float] = {}
        self._seq_counter = 0
    
    def _next_seq(self) -> int:
        """Get next sequence number."""
        self._seq_counter = (self._seq_counter + 1) & 0xFFFF
        return self._seq_counter
    
    def fragment(
        self,
        payload: bytes,
        msg_type: MessageType = MessageType.DATA,
        ttl: int = DEFAULT_TTL,
        flags: int = 0
    ) -> List[bytes]:
        """Fragment a message into BLE-sized chunks."""
        if len(payload) > MAX_MESSAGE_SIZE:
            raise ValueError(f"Message too large: {len(payload)} > {MAX_MESSAGE_SIZE}")
        
        seq = self._next_seq()
        total_frags = (len(payload) + self.mtu - 1) // self.mtu
        if total_frags == 0:
            total_frags = 1
        
        fragments = []
        for i in range(total_frags):
            start = i * self.mtu
            end = min(start + self.mtu, len(payload))
            
            header = MessageHeader(
                version=1,
                msg_type=msg_type,
                ttl=ttl,
                flags=flags,
                seq=seq,
                frag_index=i,
                frag_total=total_frags
            )
            
            fragments.append(header.pack() + payload[start:end])
        
        return fragments
    
    def reassemble(
        self,
        data: bytes,
        source_id: str
    ) -> Optional[BleMessage]:
        """
        Process incoming fragment and return complete message if ready.
        Returns None if more fragments are needed.
        """
        header = MessageHeader.unpack(data)
        payload = data[8:]
        
        # Single-fragment message
        if header.frag_total == 1:
            return BleMessage(header=header, payload=payload, source_id=source_id)
        
        # Multi-fragment message
        key = (source_id, header.seq)
        now = time.time()
        
        # Clean up old reassembly attempts
        self._cleanup_stale_reassembly()
        
        # Initialize or update reassembly state
        if key not in self.pending_reassembly:
            self.pending_reassembly[key] = {}
            self.reassembly_timestamps[key] = now
        
        self.pending_reassembly[key][header.frag_index] = payload
        
        # Check if we have all fragments
        if len(self.pending_reassembly[key]) == header.frag_total:
            # Reassemble in order
            fragments = self.pending_reassembly.pop(key)
            self.reassembly_timestamps.pop(key, None)
            
            sorted_frags = sorted(fragments.items())
            complete_payload = b''.join(frag for _, frag in sorted_frags)
            
            return BleMessage(
                header=MessageHeader(
                    version=header.version,
                    msg_type=header.msg_type,
                    ttl=header.ttl,
                    flags=header.flags,
                    seq=header.seq,
                    frag_index=0,
                    frag_total=1
                ),
                payload=complete_payload,
                source_id=source_id
            )
        
        return None
    
    def _cleanup_stale_reassembly(self):
        """Remove timed-out reassembly attempts."""
        now = time.time()
        stale_keys = [
            key for key, ts in self.reassembly_timestamps.items()
            if now - ts > REASSEMBLY_TIMEOUT
        ]
        for key in stale_keys:
            self.pending_reassembly.pop(key, None)
            self.reassembly_timestamps.pop(key, None)


# ============================================================================
# Link Quality Metrics
# ============================================================================

@dataclass
class LinkMetrics:
    """Track link quality for smarter routing decisions."""
    rssi_samples: List[int] = field(default_factory=list)
    packets_sent: int = 0
    packets_acked: int = 0
    last_heartbeat: float = 0
    hop_count: int = 1  # Hops to reach this peer
    
    MAX_SAMPLES = 10
    
    def add_rssi(self, rssi: int):
        """Add RSSI sample (keep last N)."""
        self.rssi_samples.append(rssi)
        if len(self.rssi_samples) > self.MAX_SAMPLES:
            self.rssi_samples.pop(0)
    
    @property
    def rssi_avg(self) -> float:
        """Average RSSI."""
        if not self.rssi_samples:
            return -100.0
        return sum(self.rssi_samples) / len(self.rssi_samples)
    
    @property
    def delivery_ratio(self) -> float:
        """Packet delivery ratio (0-1)."""
        if self.packets_sent == 0:
            return 1.0
        return self.packets_acked / self.packets_sent
    
    @property
    def link_cost(self) -> float:
        """Link cost for routing (lower is better)."""
        # Normalize RSSI to 0-1 (assuming -100 to -40 dBm range)
        rssi_factor = max(0, min(1, (self.rssi_avg + 100) / 60))
        reliability = self.delivery_ratio
        # Cost = 1 / quality, with hop count factor
        quality = rssi_factor * reliability + 0.01
        return self.hop_count / quality


@dataclass  
class MeshMetrics:
    """Global mesh metrics for monitoring."""
    messages_sent: int = 0
    messages_received: int = 0
    messages_relayed: int = 0
    messages_dropped_ttl: int = 0
    messages_deduplicated: int = 0
    heartbeats_sent: int = 0
    heartbeats_received: int = 0
    
    def to_dict(self) -> dict:
        return {
            "sent": self.messages_sent,
            "received": self.messages_received,
            "relayed": self.messages_relayed,
            "dropped_ttl": self.messages_dropped_ttl,
            "deduplicated": self.messages_deduplicated,
            "heartbeats_sent": self.heartbeats_sent,
            "heartbeats_received": self.heartbeats_received
        }


# ============================================================================
# Mesh Router
# ============================================================================

class MeshRouter:
    """
    Handles mesh routing with flood-based forwarding.
    
    Features:
    - TTL-based flooding with loop prevention
    - Link quality tracking (RSSI, delivery ratio)
    - Heartbeat support for topology awareness
    - Message deduplication via LRU cache
    """
    
    def __init__(self):
        self.seen_messages = LRUCache(SEEN_MESSAGE_CACHE_SIZE)
        self.peers: Dict[str, NodeInfo] = {}
        self.link_metrics: Dict[str, LinkMetrics] = {}
        self.message_handlers: List[Callable[[BleMessage], None]] = []
        self.node_id = str(uuid.uuid4())[:8]  # Short local ID
        self.metrics = MeshMetrics()
        self._seq_counter = 0
    
    def next_seq(self) -> int:
        """Get next sequence number."""
        self._seq_counter = (self._seq_counter + 1) & 0xFFFF
        return self._seq_counter
    
    def add_handler(self, handler: Callable[[BleMessage], None]):
        """Add message handler callback."""
        self.message_handlers.append(handler)
    
    def should_process(self, source_id: str, seq: int) -> bool:
        """Check if message should be processed (loop prevention)."""
        msg_id = (source_id, seq)
        if msg_id in self.seen_messages:
            self.metrics.messages_deduplicated += 1
            return False
        self.seen_messages.add(msg_id)
        return True
    
    def update_peer(self, peer_id: str, rssi: int = 0, info: Optional[NodeInfo] = None):
        """Update peer information and link metrics."""
        now = time.time()
        
        # Update NodeInfo
        if info:
            info.last_seen = now
            info.rssi = rssi
            self.peers[peer_id] = info
        elif peer_id in self.peers:
            self.peers[peer_id].last_seen = now
            self.peers[peer_id].rssi = rssi
        else:
            self.peers[peer_id] = NodeInfo(
                node_id=peer_id,
                rssi=rssi,
                last_seen=now
            )
        
        # Update link metrics
        if peer_id not in self.link_metrics:
            self.link_metrics[peer_id] = LinkMetrics()
        self.link_metrics[peer_id].add_rssi(rssi)
    
    def record_packet_sent(self, peer_id: str):
        """Record packet sent to peer."""
        if peer_id not in self.link_metrics:
            self.link_metrics[peer_id] = LinkMetrics()
        self.link_metrics[peer_id].packets_sent += 1
    
    def record_packet_ack(self, peer_id: str):
        """Record packet acknowledgment from peer."""
        if peer_id in self.link_metrics:
            self.link_metrics[peer_id].packets_acked += 1
    
    def get_link_cost(self, peer_id: str) -> float:
        """Get link cost to peer (lower is better)."""
        if peer_id in self.link_metrics:
            return self.link_metrics[peer_id].link_cost
        return float('inf')
    
    def get_best_peers(self, limit: int = 5) -> List[str]:
        """Get peers sorted by link quality (best first)."""
        peers_with_cost = [
            (peer_id, self.get_link_cost(peer_id))
            for peer_id in self.peers.keys()
        ]
        peers_with_cost.sort(key=lambda x: x[1])
        return [p[0] for p in peers_with_cost[:limit]]
    
    def remove_peer(self, peer_id: str):
        """Remove peer from registry."""
        self.peers.pop(peer_id, None)
        self.link_metrics.pop(peer_id, None)
    
    def deliver_message(self, message: BleMessage):
        """Deliver message to local handlers."""
        self.metrics.messages_received += 1
        for handler in self.message_handlers:
            try:
                handler(message)
            except Exception as e:
                logger.error(f"Message handler error: {e}")
    
    def decrement_ttl(self, data: bytes) -> Optional[bytes]:
        """Decrement TTL in message, return None if expired."""
        header = MessageHeader.unpack(data)
        if header.ttl <= 1:
            self.metrics.messages_dropped_ttl += 1
            return None
        
        new_header = MessageHeader(
            version=header.version,
            msg_type=header.msg_type,
            ttl=header.ttl - 1,
            flags=header.flags,
            seq=header.seq,
            frag_index=header.frag_index,
            frag_total=header.frag_total
        )
        
        self.metrics.messages_relayed += 1
        return new_header.pack() + data[8:]
    
    def create_heartbeat(self) -> bytes:
        """Create heartbeat message."""
        payload = {
            "id": self.node_id,
            "ts": int(time.time()),
            "peers": len(self.peers),
            "metrics": self.metrics.to_dict()
        }
        if CBOR_AVAILABLE:
            payload_bytes = cbor2.dumps(payload)
        else:
            payload_bytes = json.dumps(payload).encode('utf-8')
        
        header = MessageHeader(
            msg_type=MessageType.HELLO,
            ttl=DEFAULT_TTL,
            seq=self.next_seq()
        )
        self.metrics.heartbeats_sent += 1
        return header.pack() + payload_bytes
    
    def handle_heartbeat(self, source_id: str, payload: bytes, ttl_remaining: int):
        """Process incoming heartbeat."""
        try:
            if CBOR_AVAILABLE:
                data = cbor2.loads(payload)
            else:
                data = json.loads(payload.decode('utf-8'))
            
            # Calculate hop count from TTL
            hops = DEFAULT_TTL - ttl_remaining
            
            if source_id in self.link_metrics:
                self.link_metrics[source_id].hop_count = hops
                self.link_metrics[source_id].last_heartbeat = time.time()
            
            self.metrics.heartbeats_received += 1
            logger.debug(f"Heartbeat from {source_id}: {hops} hops, {data.get('peers', 0)} peers")
            
        except Exception as e:
            logger.warning(f"Failed to parse heartbeat: {e}")


# ============================================================================
# BLE Transport (Central + Peripheral)
# ============================================================================

class BleTransport:
    """
    BLE Transport for Atmosphere mesh.
    
    Operates in both central (scanner/client) and peripheral (advertiser/server) modes
    for full mesh connectivity.
    """
    
    def __init__(
        self,
        node_name: str = None,
        capabilities: List[str] = None
    ):
        if not BLEAK_AVAILABLE:
            raise ImportError("bleak is required: pip install bleak")
        
        self.node_name = node_name or f"Atmosphere-{platform.node()[:8]}"
        self.capabilities = capabilities or ["relay"]
        self.node_id = str(uuid.uuid4())[:12]
        
        self.router = MeshRouter()
        self.fragmenter = MessageFragmenter()
        
        # Connected peers (BleakClient instances)
        self.connected_clients: Dict[str, BleakClient] = {}
        
        # GATT server (if bless available)
        self.gatt_server: Optional[Any] = None
        
        # Callbacks
        self.on_message: Optional[Callable[[BleMessage], None]] = None
        self.on_peer_discovered: Optional[Callable[[NodeInfo], None]] = None
        self.on_peer_lost: Optional[Callable[[str], None]] = None
        
        # State
        self._running = False
        self._scan_task: Optional[asyncio.Task] = None
        self._server_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._heartbeat_interval = 30.0  # seconds
        
        # Local info for INFO characteristic
        self._node_info = {
            "id": self.node_id,
            "name": self.node_name,
            "platform": platform.system(),
            "capabilities": self.capabilities,
            "version": "1.0"
        }
        
        # Message buffer for RX characteristic
        self._rx_buffer: asyncio.Queue = asyncio.Queue()
    
    @property
    def node_info(self) -> NodeInfo:
        """Get local node info."""
        return NodeInfo(
            node_id=self.node_id,
            name=self.node_name,
            capabilities=self.capabilities,
            platform=platform.system(),
            version="1.0"
        )
    
    async def start(self):
        """Start BLE transport (scanning and advertising)."""
        if self._running:
            return
        
        self._running = True
        logger.info(f"Starting BLE transport: {self.node_name} ({self.node_id})")
        
        # Start scanning for peers
        self._scan_task = asyncio.create_task(self._scan_loop())
        
        # Start GATT server if available
        if BLESS_AVAILABLE:
            self._server_task = asyncio.create_task(self._run_gatt_server())
        else:
            logger.warning("bless not available - GATT server disabled. Install with: pip install bless")
        
        # Start heartbeat loop
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def stop(self):
        """Stop BLE transport."""
        self._running = False
        
        # Cancel tasks
        for task in [self._scan_task, self._server_task, self._heartbeat_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Disconnect all clients
        for address, client in list(self.connected_clients.items()):
            try:
                await client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting {address}: {e}")
        
        self.connected_clients.clear()
        
        # Stop GATT server
        if self.gatt_server:
            await self.gatt_server.stop()
            self.gatt_server = None
        
        logger.info("BLE transport stopped")
    
    # ========================================================================
    # Central Mode (Scanner/Client)
    # ========================================================================
    
    async def _scan_loop(self):
        """Continuously scan for Atmosphere nodes."""
        logger.info("Starting BLE scan loop")
        
        while self._running:
            try:
                # Scan for devices advertising our service
                devices = await BleakScanner.discover(
                    timeout=5.0,
                    return_adv=True
                )
                
                for device, adv_data in devices.values():
                    # Check for our service UUID in advertisement
                    service_uuids = adv_data.service_uuids or []
                    if any(MESH_SERVICE_UUID.lower() in uuid.lower() for uuid in service_uuids):
                        await self._handle_discovered_device(device, adv_data)
                
                # Cleanup stale connections
                await self._cleanup_stale_peers()
                
            except Exception as e:
                logger.error(f"Scan error: {e}")
            
            await asyncio.sleep(2.0)
    
    async def _heartbeat_loop(self):
        """Periodically send heartbeat messages."""
        logger.info(f"Starting heartbeat loop (interval: {self._heartbeat_interval}s)")
        
        while self._running:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                if self.connected_clients:
                    heartbeat = self.router.create_heartbeat()
                    await self.broadcast(heartbeat)
                    logger.debug(f"Sent heartbeat to {len(self.connected_clients)} peers")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _handle_discovered_device(self, device, adv_data):
        """Handle discovered Atmosphere device."""
        address = device.address
        rssi = adv_data.rssi if adv_data.rssi else -100
        
        # Already connected?
        if address in self.connected_clients:
            self.router.update_peer(address, rssi=rssi)
            return
        
        logger.info(f"Discovered Atmosphere node: {device.name or address} (RSSI: {rssi})")
        
        try:
            # Connect and discover services
            client = BleakClient(device)
            await client.connect()
            
            if client.is_connected:
                self.connected_clients[address] = client
                
                # Read node info
                info = await self._read_node_info(client)
                if info:
                    self.router.update_peer(address, rssi=rssi, info=info)
                    if self.on_peer_discovered:
                        self.on_peer_discovered(info)
                
                # Subscribe to RX notifications
                await self._subscribe_to_notifications(client)
                
                logger.info(f"Connected to: {address}")
        
        except Exception as e:
            logger.error(f"Failed to connect to {address}: {e}")
    
    async def _read_node_info(self, client: BleakClient) -> Optional[NodeInfo]:
        """Read node info from INFO characteristic."""
        try:
            data = await client.read_gatt_char(INFO_CHAR_UUID)
            if data:
                if CBOR_AVAILABLE:
                    info_dict = cbor2.loads(data)
                else:
                    info_dict = json.loads(data.decode('utf-8'))
                return NodeInfo(
                    node_id=info_dict.get("id", "unknown"),
                    name=info_dict.get("name", ""),
                    capabilities=info_dict.get("capabilities", []),
                    platform=info_dict.get("platform", ""),
                    version=info_dict.get("version", "1.0"),
                    last_seen=time.time()
                )
        except Exception as e:
            logger.warning(f"Failed to read node info: {e}")
        return None
    
    async def _subscribe_to_notifications(self, client: BleakClient):
        """Subscribe to RX characteristic notifications."""
        def notification_handler(sender: BleakGATTCharacteristic, data: bytearray):
            asyncio.create_task(self._handle_incoming_data(bytes(data), client.address))
        
        try:
            await client.start_notify(RX_CHAR_UUID, notification_handler)
        except Exception as e:
            logger.warning(f"Failed to subscribe to notifications: {e}")
    
    async def _handle_incoming_data(self, data: bytes, source_address: str):
        """Handle incoming data from a peer."""
        try:
            # Try to reassemble
            message = self.fragmenter.reassemble(data, source_address)
            
            if message:
                # Check for duplicates
                if not self.router.should_process(source_address, message.header.seq):
                    return
                
                # Deliver locally
                self.router.deliver_message(message)
                if self.on_message:
                    self.on_message(message)
                
                # Forward if TTL > 0 (flood routing)
                if message.header.ttl > 1:
                    await self._forward_message(data, source_address)
        
        except Exception as e:
            logger.error(f"Error handling incoming data: {e}")
    
    async def _forward_message(self, data: bytes, source_address: str):
        """Forward message to other peers (flood routing)."""
        forwarded_data = self.router.decrement_ttl(data)
        if not forwarded_data:
            return
        
        for address, client in list(self.connected_clients.items()):
            if address == source_address:
                continue
            
            try:
                if client.is_connected:
                    await client.write_gatt_char(TX_CHAR_UUID, forwarded_data)
            except Exception as e:
                logger.warning(f"Failed to forward to {address}: {e}")
    
    async def _cleanup_stale_peers(self):
        """Remove disconnected peers."""
        stale = []
        for address, client in self.connected_clients.items():
            if not client.is_connected:
                stale.append(address)
        
        for address in stale:
            self.connected_clients.pop(address, None)
            self.router.remove_peer(address)
            if self.on_peer_lost:
                self.on_peer_lost(address)
    
    # ========================================================================
    # Peripheral Mode (GATT Server)
    # ========================================================================
    
    async def _run_gatt_server(self):
        """Run GATT server for peripheral mode."""
        logger.info("Starting GATT server")
        
        try:
            self.gatt_server = BlessServer(name=self.node_name)
            
            # Add service
            await self.gatt_server.add_new_service(MESH_SERVICE_UUID)
            
            # TX characteristic (Write from client perspective)
            await self.gatt_server.add_new_characteristic(
                MESH_SERVICE_UUID,
                TX_CHAR_UUID,
                GATTCharacteristicProperties.write | GATTCharacteristicProperties.notify,
                None,  # Initial value
                GATTAttributePermissions.writeable
            )
            
            # RX characteristic (Read/Notify from client perspective)
            await self.gatt_server.add_new_characteristic(
                MESH_SERVICE_UUID,
                RX_CHAR_UUID,
                GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify,
                None,
                GATTAttributePermissions.readable
            )
            
            # INFO characteristic
            if CBOR_AVAILABLE:
                info_data = cbor2.dumps(self._node_info)
            else:
                info_data = json.dumps(self._node_info).encode('utf-8')
            await self.gatt_server.add_new_characteristic(
                MESH_SERVICE_UUID,
                INFO_CHAR_UUID,
                GATTCharacteristicProperties.read,
                info_data,
                GATTAttributePermissions.readable
            )
            
            # Set write handler
            self.gatt_server.write_request_func = self._handle_gatt_write
            
            # Start advertising
            await self.gatt_server.start()
            logger.info(f"GATT server started, advertising as: {self.node_name}")
            
            # Keep server running
            while self._running:
                await asyncio.sleep(1.0)
        
        except Exception as e:
            logger.error(f"GATT server error: {e}")
    
    def _handle_gatt_write(self, characteristic, value: bytes):
        """Handle GATT write requests."""
        if characteristic.uuid.lower() == TX_CHAR_UUID.lower():
            asyncio.create_task(self._handle_incoming_data(value, "gatt-client"))
        return True
    
    # ========================================================================
    # Sending Messages
    # ========================================================================
    
    async def send(
        self,
        payload: bytes,
        msg_type: MessageType = MessageType.DATA,
        ttl: int = DEFAULT_TTL,
        target: Optional[str] = None
    ) -> bool:
        """
        Send a message to the mesh.
        
        Args:
            payload: Message payload (will be fragmented if needed)
            msg_type: Message type
            ttl: Time-to-live (hop count)
            target: Specific peer address, or None for broadcast
        
        Returns:
            True if sent to at least one peer
        """
        fragments = self.fragmenter.fragment(payload, msg_type, ttl)
        sent = False
        
        for address, client in list(self.connected_clients.items()):
            if target and address != target:
                continue
            
            try:
                if client.is_connected:
                    for fragment in fragments:
                        await client.write_gatt_char(TX_CHAR_UUID, fragment)
                    sent = True
            except Exception as e:
                logger.warning(f"Failed to send to {address}: {e}")
        
        # Also notify via GATT server if available
        if self.gatt_server and not target:
            try:
                for fragment in fragments:
                    self.gatt_server.update_value(MESH_SERVICE_UUID, RX_CHAR_UUID, fragment)
            except Exception as e:
                logger.warning(f"Failed to notify via GATT server: {e}")
        
        return sent
    
    async def send_cbor(
        self,
        data: Any,
        msg_type: MessageType = MessageType.DATA,
        ttl: int = DEFAULT_TTL
    ) -> bool:
        """Send CBOR-encoded data to the mesh."""
        if CBOR_AVAILABLE:
            payload = cbor2.dumps(data)
        else:
            payload = json.dumps(data).encode('utf-8')
        return await self.send(payload, msg_type, ttl)
    
    async def broadcast(self, data: bytes) -> bool:
        """Broadcast raw message to all connected peers."""
        return await self.send(data, target=None)
    
    async def broadcast_hello(self):
        """Broadcast a HELLO message to discover peers."""
        hello_data = {
            "id": self.node_id,
            "name": self.node_name,
            "capabilities": self.capabilities,
            "platform": platform.system()
        }
        return await self.send_cbor(hello_data, MessageType.HELLO)
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def get_peers(self) -> List[NodeInfo]:
        """Get list of connected peers."""
        return list(self.router.peers.values())
    
    def get_peer_count(self) -> int:
        """Get number of connected peers."""
        return len(self.connected_clients)
    
    def is_running(self) -> bool:
        """Check if transport is running."""
        return self._running
    
    def get_metrics(self) -> dict:
        """Get mesh metrics for monitoring."""
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "running": self._running,
            "connected_peers": len(self.connected_clients),
            "known_peers": len(self.router.peers),
            "mesh_metrics": self.router.metrics.to_dict(),
            "link_metrics": {
                peer_id: {
                    "rssi_avg": m.rssi_avg,
                    "delivery_ratio": m.delivery_ratio,
                    "hop_count": m.hop_count,
                    "link_cost": m.link_cost
                }
                for peer_id, m in self.router.link_metrics.items()
            }
        }
    
    def get_best_route(self, destination: str) -> Optional[str]:
        """Get best next-hop for destination (if known)."""
        # Currently simple: direct if connected, else best link quality peer
        if destination in self.connected_clients:
            return destination
        best_peers = self.router.get_best_peers(limit=1)
        return best_peers[0] if best_peers else None


# ============================================================================
# Security Utilities
# ============================================================================

def derive_mesh_key(invite_token: str) -> bytes:
    """Derive mesh encryption key from invite token."""
    return hashlib.pbkdf2_hmac(
        'sha256',
        invite_token.encode(),
        b'atmosphere-mesh-key',
        100000,
        dklen=32
    )


# ============================================================================
# CLI for testing
# ============================================================================

async def main():
    """Test BLE transport."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Atmosphere BLE Transport Test")
    parser.add_argument("--name", default=None, help="Node name")
    parser.add_argument("--scan-only", action="store_true", help="Only scan, don't advertise")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    transport = BleTransport(node_name=args.name)
    
    def on_message(msg: BleMessage):
        print(f"📨 Received from {msg.source_id}: {msg.payload[:50]}...")
    
    def on_peer(info: NodeInfo):
        print(f"🔵 Peer discovered: {info.name} ({info.node_id})")
    
    def on_lost(peer_id: str):
        print(f"🔴 Peer lost: {peer_id}")
    
    transport.on_message = on_message
    transport.on_peer_discovered = on_peer
    transport.on_peer_lost = on_lost
    
    try:
        await transport.start()
        
        print(f"\n🌐 BLE Transport running: {transport.node_name}")
        print(f"   Node ID: {transport.node_id}")
        print(f"   Service UUID: {MESH_SERVICE_UUID}")
        print("\nPress Ctrl+C to stop\n")
        
        # Periodic hello broadcasts
        while True:
            await asyncio.sleep(10)
            peers = transport.get_peers()
            print(f"📊 Connected peers: {len(peers)}")
            for peer in peers:
                print(f"   - {peer.name} ({peer.node_id})")
            
            # Send hello
            await transport.broadcast_hello()
    
    except KeyboardInterrupt:
        print("\n⏹️ Stopping...")
    
    finally:
        await transport.stop()


if __name__ == "__main__":
    asyncio.run(main())
