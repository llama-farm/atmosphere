"""
BLE Mesh Transport for macOS.

Uses CoreBluetooth via PyObjC for Bluetooth Low Energy communication.
Implements a simple mesh protocol with multi-hop message forwarding.

Features:
- GATT server for receiving connections
- Central mode for discovering and connecting to peers
- Message fragmentation for large payloads
- Multi-hop forwarding (configurable TTL)
"""

import asyncio
import hashlib
import json
import logging
import struct
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# BLE UUIDs (MUST match Android BleTransport.kt exactly!)
# Base: A7A05F30-xxxx-4000-8000-00805F9B34FB (Atmosphere prefix)
MESH_SERVICE_UUID = "A7A05F30-0001-4000-8000-00805F9B34FB"
TX_CHAR_UUID = "A7A05F30-0002-4000-8000-00805F9B34FB"
RX_CHAR_UUID = "A7A05F30-0003-4000-8000-00805F9B34FB"
INFO_CHAR_UUID = "A7A05F30-0004-4000-8000-00805F9B34FB"
MESH_ID_CHAR_UUID = "A7A05F30-0005-4000-8000-00805F9B34FB"
CCCD_UUID = "00002902-0000-1000-8000-00805F9B34FB"


class MessageType(IntEnum):
    """Message types for BLE mesh protocol (MUST match Android BleTransport.kt!)."""
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


@dataclass
class MessageHeader:
    """
    8-byte message header (MUST match Android MessageHeader exactly!).
    
    Format (little-endian):
        - version: u8 (always 1)
        - msg_type: u8 (MessageType value)
        - ttl: u8 (hop count)
        - flags: u8 (ENCRYPTED=0x01, BROADCAST=0x02, PRIORITY=0x04, RELIABLE=0x08)
        - seq: u16 (sequence number)
        - frag_index: u8 (fragment index, 0 for single messages)
        - frag_total: u8 (total fragments, 1 for single messages)
    """
    version: int = 1
    msg_type: MessageType = MessageType.DATA
    ttl: int = 5
    flags: int = 0
    seq: int = 0
    frag_index: int = 0
    frag_total: int = 1
    
    def pack(self) -> bytes:
        """Pack header to 8 bytes (little-endian)."""
        return struct.pack(
            "<BBBBHBB",
            self.version,
            self.msg_type.value,
            self.ttl,
            self.flags,
            self.seq,
            self.frag_index,
            self.frag_total
        )
    
    @classmethod
    def unpack(cls, data: bytes) -> "MessageHeader":
        """Unpack 8-byte header."""
        if len(data) < 8:
            raise ValueError(f"Header too short: {len(data)} bytes")
        
        version, msg_type, ttl, flags, seq, frag_index, frag_total = struct.unpack(
            "<BBBBHBB", data[:8]
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


# Message flags (matching Android MessageFlags)
class MessageFlags:
    ENCRYPTED = 0x01
    BROADCAST = 0x02
    PRIORITY = 0x04
    RELIABLE = 0x08


@dataclass
class BleMessage:
    """BLE mesh message (compatible with Android BleMessage)."""
    header: MessageHeader
    payload: bytes
    source_id: str = ""
    timestamp: float = field(default_factory=time.time)
    
    def to_bytes(self) -> bytes:
        """Serialize message to bytes (8-byte header + payload)."""
        return self.header.pack() + self.payload
    
    @classmethod
    def from_bytes(cls, data: bytes, source_id: str = "") -> Optional["BleMessage"]:
        """Deserialize message from bytes."""
        if len(data) < 8:  # Minimum header size
            return None
        
        try:
            header = MessageHeader.unpack(data)
            payload = data[8:]
            
            return cls(
                header=header,
                payload=payload,
                source_id=source_id
            )
        except Exception as e:
            logger.error(f"Failed to parse BLE message: {e}")
            return None
    
    # Convenience properties for backwards compatibility
    @property
    def msg_type(self) -> MessageType:
        return self.header.msg_type
    
    @property
    def ttl(self) -> int:
        return self.header.ttl
    
    @property
    def seq(self) -> int:
        return self.header.seq


@dataclass
class BlePeer:
    """Discovered BLE peer."""
    peer_id: str
    name: str
    rssi: int = 0
    connected: bool = False
    last_seen: float = field(default_factory=time.time)
    capabilities: List[str] = field(default_factory=list)


class LruCache:
    """Simple LRU cache for deduplication."""
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()
    
    def __contains__(self, key: str) -> bool:
        return key in self._cache
    
    def add(self, key: str):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            self._cache[key] = True
            if len(self._cache) > self.max_size:
                self._cache.popitem(last=False)


class BleMeshTransport:
    """
    BLE Mesh transport using CoreBluetooth (macOS) or bleak (cross-platform).
    
    Falls back to bleak library if PyObjC/CoreBluetooth not available.
    
    Protocol compatible with Android BleTransport.kt:
    - Same service/characteristic UUIDs
    - Same 8-byte little-endian message header format
    - Same message type values
    """
    
    def __init__(
        self,
        node_id: str,
        node_name: str,
        mesh_id: str,
        capabilities: List[str] = None,
        max_hops: int = 5
    ):
        self.node_id = node_id
        self.node_name = node_name
        self.mesh_id = mesh_id
        self.capabilities = capabilities or []
        self.max_hops = max_hops
        
        self._running = False
        self._peers: Dict[str, BlePeer] = {}
        self._seen_messages = LruCache(1000)
        self._message_handler: Optional[Callable] = None
        self._seq_counter = 0  # Sequence counter for messages
        
        # Platform detection
        self._use_bleak = True
        try:
            import objc
            from Foundation import CBUUID, CBCentralManager, CBPeripheralManager
            self._use_bleak = False
            logger.info("Using CoreBluetooth for BLE")
        except ImportError:
            logger.info("Using bleak for BLE")
    
    def _next_seq(self) -> int:
        """Get next sequence number (wraps at 65535)."""
        self._seq_counter = (self._seq_counter + 1) & 0xFFFF
        return self._seq_counter
    
    @property
    def connected(self) -> bool:
        return any(p.connected for p in self._peers.values())
    
    @property
    def peers(self) -> List[BlePeer]:
        return list(self._peers.values())
    
    def on_message(self, handler: Callable[[str, bytes], None]):
        """Set message handler: handler(from_peer_id, message)."""
        self._message_handler = handler
    
    async def start(self, advertise: bool = True, scan: bool = True) -> bool:
        """Start BLE mesh transport."""
        if self._running:
            return True
        
        self._running = True
        
        if self._use_bleak:
            return await self._start_bleak(advertise, scan)
        else:
            return await self._start_corebluetooth(advertise, scan)
    
    async def stop(self):
        """Stop BLE mesh transport."""
        self._running = False
        
        if self._use_bleak:
            await self._stop_bleak()
        else:
            await self._stop_corebluetooth()
        
        self._peers.clear()
        logger.info("BLE mesh transport stopped")
    
    async def send(self, message: bytes, target: Optional[str] = None) -> bool:
        """Send message via BLE mesh."""
        header = MessageHeader(
            version=1,
            msg_type=MessageType.DATA,
            ttl=self.max_hops,
            flags=0,
            seq=self._next_seq(),
            frag_index=0,
            frag_total=1
        )
        msg = BleMessage(header=header, payload=message, source_id=self.node_id)
        
        return await self._broadcast_message(msg, target)
    
    async def broadcast(self, message: bytes) -> int:
        """Broadcast to all connected peers."""
        header = MessageHeader(
            version=1,
            msg_type=MessageType.DATA,
            ttl=self.max_hops,
            flags=MessageFlags.BROADCAST,
            seq=self._next_seq(),
            frag_index=0,
            frag_total=1
        )
        msg = BleMessage(header=header, payload=message, source_id=self.node_id)
        
        sent = 0
        for peer_id in self._peers:
            if await self._broadcast_message(msg, peer_id):
                sent += 1
        return sent
    
    async def _broadcast_message(self, msg: BleMessage, target: Optional[str] = None) -> bool:
        """Internal message broadcast."""
        # Mark as seen to prevent loops (use source_id:seq as unique key)
        msg_key = f"{msg.source_id}:{msg.header.seq}"
        self._seen_messages.add(msg_key)
        
        if self._use_bleak:
            return await self._send_bleak(msg, target)
        else:
            return await self._send_corebluetooth(msg, target)
    
    def _handle_received_message(self, data: bytes, from_device: str):
        """Handle received BLE message."""
        msg = BleMessage.from_bytes(data, source_id=from_device)
        if not msg:
            return
        
        # Check if already seen (dedup using source:seq as key)
        msg_key = f"{from_device}:{msg.header.seq}"
        if msg_key in self._seen_messages:
            return
        
        self._seen_messages.add(msg_key)
        
        # Handle different message types
        if msg.msg_type == MessageType.HELLO:
            self._handle_hello(msg, from_device)
        elif msg.msg_type == MessageType.DATA:
            # Deliver to application
            if self._message_handler:
                try:
                    self._message_handler(from_device, msg.payload)
                except Exception as e:
                    logger.error(f"Message handler error: {e}")
            
            # Forward if TTL > 1 (multi-hop)
            if msg.ttl > 1:
                asyncio.create_task(self._forward_message(msg, from_device))
    
    def _handle_hello(self, msg: BleMessage, from_device: str):
        """Handle HELLO message (peer announcement)."""
        try:
            # Android sends JSON-encoded node info in hello payload
            info = json.loads(msg.payload.decode('utf-8'))
            peer_id = info.get("id", from_device)
            
            self._peers[peer_id] = BlePeer(
                peer_id=peer_id,
                name=info.get("name", peer_id[:8]),
                connected=True,
                capabilities=info.get("capabilities", [])
            )
            
            logger.info(f"BLE peer hello: {peer_id} ({info.get('name', 'unknown')})")
            
            # Send HELLO_ACK back
            asyncio.create_task(self._send_hello_ack(from_device))
        except Exception as e:
            logger.error(f"Failed to parse hello: {e}")
    
    async def _send_hello_ack(self, target: str):
        """Send HELLO_ACK response."""
        info_payload = json.dumps({
            "id": self.node_id,
            "name": self.node_name,
            "platform": "macOS",
            "capabilities": self.capabilities,
            "version": "1.0",
            "mesh_id": self.mesh_id
        }).encode('utf-8')
        
        header = MessageHeader(
            version=1,
            msg_type=MessageType.HELLO_ACK,
            ttl=1,
            flags=0,
            seq=self._next_seq(),
            frag_index=0,
            frag_total=1
        )
        msg = BleMessage(header=header, payload=info_payload, source_id=self.node_id)
        await self._broadcast_message(msg, target)
    
    async def _forward_message(self, msg: BleMessage, exclude_device: str = None):
        """Forward message to other peers (multi-hop)."""
        if not self._running:
            return
        
        # Create new header with decremented TTL
        new_header = MessageHeader(
            version=msg.header.version,
            msg_type=msg.header.msg_type,
            ttl=msg.header.ttl - 1,
            flags=msg.header.flags,
            seq=msg.header.seq,  # Keep same seq for dedup
            frag_index=msg.header.frag_index,
            frag_total=msg.header.frag_total
        )
        
        forward_msg = BleMessage(
            header=new_header,
            payload=msg.payload,
            source_id=msg.source_id
        )
        
        # Forward to all peers except the one we received from
        for peer_id in self._peers:
            if peer_id != exclude_device:
                await self._broadcast_message(forward_msg, peer_id)
    
    # ========================================================================
    # Bleak Implementation (Cross-platform)
    # ========================================================================
    
    async def _start_bleak(self, advertise: bool, scan: bool) -> bool:
        """Start BLE using bleak library."""
        try:
            from bleak import BleakClient, BleakScanner
            
            if scan:
                asyncio.create_task(self._bleak_scan_loop())
            
            if advertise:
                # Bleak doesn't support peripheral mode well
                # We use scanning + connecting as "advertising"
                logger.info("BLE advertising not fully supported via bleak")
            
            logger.info("BLE mesh started (bleak)")
            return True
            
        except ImportError:
            logger.error("bleak not installed: pip install bleak")
            return False
        except Exception as e:
            logger.error(f"Failed to start bleak: {e}")
            return False
    
    async def _stop_bleak(self):
        """Stop bleak BLE."""
        pass  # Scanner stops when _running = False
    
    async def _send_bleak(self, msg: BleMessage, target: Optional[str]) -> bool:
        """Send message via bleak."""
        try:
            from bleak import BleakClient
            
            data = msg.to_bytes()
            sent = False
            
            for peer_id, peer in self._peers.items():
                if target and peer_id != target:
                    continue
                
                if hasattr(peer, '_bleak_client') and peer._bleak_client:
                    try:
                        await peer._bleak_client.write_gatt_char(
                            RX_CHAR_UUID,
                            data,
                            response=False
                        )
                        sent = True
                    except Exception as e:
                        logger.debug(f"Failed to send to {peer_id}: {e}")
            
            return sent
            
        except Exception as e:
            logger.error(f"Bleak send error: {e}")
            return False
    
    async def _bleak_scan_loop(self):
        """Scan for BLE peers using bleak."""
        try:
            from bleak import BleakScanner, BleakClient
            
            while self._running:
                try:
                    devices = await BleakScanner.discover(timeout=5.0)
                    
                    for device in devices:
                        # Check if device advertises our service
                        if device.name and "Atmosphere" in device.name:
                            await self._bleak_connect(device)
                    
                except Exception as e:
                    logger.debug(f"Scan error: {e}")
                
                await asyncio.sleep(10)  # Scan every 10 seconds
                
        except Exception as e:
            logger.error(f"Scan loop error: {e}")
    
    async def _bleak_connect(self, device):
        """Connect to a discovered device."""
        try:
            from bleak import BleakClient
            
            client = BleakClient(device)
            await client.connect()
            
            # Check if has our service
            services = await client.get_services()
            has_mesh_service = any(
                str(s.uuid).lower() == MESH_SERVICE_UUID.lower()
                for s in services
            )
            
            if has_mesh_service:
                peer_id = device.address.replace(":", "")[-12:]
                
                self._peers[peer_id] = BlePeer(
                    peer_id=peer_id,
                    name=device.name or peer_id,
                    rssi=device.rssi or 0,
                    connected=True
                )
                self._peers[peer_id]._bleak_client = client
                
                # Start notification handler on RX characteristic (we receive on RX)
                await client.start_notify(
                    RX_CHAR_UUID,
                    lambda s, d: self._handle_received_message(d, peer_id)
                )
                
                # Read INFO characteristic to get peer info
                try:
                    info_data = await client.read_gatt_char(INFO_CHAR_UUID)
                    if info_data:
                        info = json.loads(info_data.decode('utf-8'))
                        self._peers[peer_id].name = info.get("name", peer_id)
                        self._peers[peer_id].capabilities = info.get("capabilities", [])
                        logger.info(f"Peer info: {info.get('name')} caps={info.get('capabilities')}")
                except Exception as e:
                    logger.debug(f"Could not read INFO char: {e}")
                
                # Send HELLO message (JSON payload matching Android format)
                hello_payload = json.dumps({
                    "id": self.node_id,
                    "name": self.node_name,
                    "platform": "macOS",
                    "mesh_id": self.mesh_id,
                    "capabilities": self.capabilities,
                    "version": "1.0"
                }).encode('utf-8')
                
                hello_header = MessageHeader(
                    version=1,
                    msg_type=MessageType.HELLO,
                    ttl=1,
                    flags=0,
                    seq=self._next_seq(),
                    frag_index=0,
                    frag_total=1
                )
                hello = BleMessage(header=hello_header, payload=hello_payload, source_id=self.node_id)
                
                # Write to TX characteristic (we send to their TX)
                await client.write_gatt_char(TX_CHAR_UUID, hello.to_bytes())
                
                logger.info(f"Connected to BLE peer: {peer_id}")
            else:
                await client.disconnect()
                
        except Exception as e:
            logger.debug(f"Connect error: {e}")
    
    # ========================================================================
    # CoreBluetooth Implementation (macOS native)
    # ========================================================================
    
    async def _start_corebluetooth(self, advertise: bool, scan: bool) -> bool:
        """Start BLE using CoreBluetooth."""
        logger.warning("CoreBluetooth implementation not yet complete, falling back to bleak")
        self._use_bleak = True
        return await self._start_bleak(advertise, scan)
    
    async def _stop_corebluetooth(self):
        """Stop CoreBluetooth BLE."""
        pass
    
    async def _send_corebluetooth(self, msg: BleMessage, target: Optional[str]) -> bool:
        """Send message via CoreBluetooth."""
        return False


# Factory function for transport.py integration
def create_ble_mesh_transport(config: dict) -> BleMeshTransport:
    """Create BLE mesh transport from config."""
    return BleMeshTransport(
        node_id=config.get("node_id", ""),
        node_name=config.get("node_name", "Atmosphere"),
        mesh_id=config.get("mesh_id", ""),
        capabilities=config.get("capabilities", []),
        max_hops=config.get("max_hops", 5)
    )
