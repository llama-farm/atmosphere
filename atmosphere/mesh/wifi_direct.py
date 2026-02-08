"""
WiFi Direct (P2P) Transport for macOS/Linux.

Uses platform-specific APIs:
- macOS: MultipeerConnectivity via PyObjC
- Linux: wpa_supplicant P2P

This enables direct device-to-device communication without a router.
"""

import asyncio
import json
import logging
import platform
import socket
import struct
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class WifiDirectState(Enum):
    IDLE = "idle"
    ADVERTISING = "advertising"
    BROWSING = "browsing"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


@dataclass
class WifiDirectPeer:
    """Discovered WiFi Direct peer."""
    peer_id: str
    name: str
    address: Optional[str] = None
    port: int = 11450
    capabilities: List[str] = field(default_factory=list)
    signal_strength: int = 0
    last_seen: float = 0


class WifiDirectTransport:
    """
    WiFi Direct transport for direct P2P connections.
    
    On macOS, uses Bonjour for discovery and direct TCP for messaging.
    On Linux, would use wpa_supplicant P2P (not yet implemented).
    """
    
    SERVICE_TYPE = "_atmosphere._tcp"
    
    def __init__(
        self,
        node_id: str,
        node_name: str,
        mesh_id: str,
        port: int = 11450,
        capabilities: List[str] = None
    ):
        self.node_id = node_id
        self.node_name = node_name
        self.mesh_id = mesh_id
        self.port = port
        self.capabilities = capabilities or []
        
        self._state = WifiDirectState.IDLE
        self._peers: Dict[str, WifiDirectPeer] = {}
        self._connections: Dict[str, asyncio.StreamWriter] = {}
        self._server: Optional[asyncio.Server] = None
        self._message_handler: Optional[Callable] = None
        self._running = False
        
        # Platform detection
        self._platform = platform.system().lower()
        
    @property
    def state(self) -> WifiDirectState:
        return self._state
    
    @property
    def peers(self) -> List[WifiDirectPeer]:
        return list(self._peers.values())
    
    @property
    def connected(self) -> bool:
        return len(self._connections) > 0
    
    def on_message(self, handler: Callable[[str, bytes], None]):
        """Set message handler: handler(from_peer_id, message)."""
        self._message_handler = handler
    
    async def start(self, advertise: bool = True, browse: bool = True) -> bool:
        """Start WiFi Direct transport."""
        if self._running:
            return True
            
        self._running = True
        
        try:
            # Start TCP server for incoming connections
            self._server = await asyncio.start_server(
                self._handle_client,
                host='0.0.0.0',
                port=self.port
            )
            
            # Get actual port if 0 was specified
            if self.port == 0:
                self.port = self._server.sockets[0].getsockname()[1]
            
            logger.info(f"WiFi Direct server started on port {self.port}")
            
            # Start mDNS advertising (using zeroconf)
            if advertise:
                await self._start_advertising()
            
            # Start peer discovery
            if browse:
                asyncio.create_task(self._discovery_loop())
            
            self._state = WifiDirectState.ADVERTISING if advertise else WifiDirectState.BROWSING
            return True
            
        except Exception as e:
            logger.error(f"Failed to start WiFi Direct: {e}")
            self._state = WifiDirectState.FAILED
            return False
    
    async def stop(self):
        """Stop WiFi Direct transport."""
        self._running = False
        
        # Close all connections
        for writer in self._connections.values():
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass
        self._connections.clear()
        
        # Stop server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        
        # Stop advertising
        await self._stop_advertising()
        
        self._state = WifiDirectState.IDLE
        logger.info("WiFi Direct transport stopped")
    
    async def connect_to_peer(self, peer_id: str) -> bool:
        """Connect to a discovered peer."""
        peer = self._peers.get(peer_id)
        if not peer or not peer.address:
            logger.warning(f"Peer {peer_id} not found or no address")
            return False
        
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(peer.address, peer.port),
                timeout=10.0
            )
            
            # Send handshake
            handshake = json.dumps({
                "type": "handshake",
                "node_id": self.node_id,
                "name": self.node_name,
                "mesh_id": self.mesh_id,
                "capabilities": self.capabilities
            }).encode()
            
            writer.write(struct.pack(">I", len(handshake)))
            writer.write(handshake)
            await writer.drain()
            
            self._connections[peer_id] = writer
            
            # Start reading from this connection
            asyncio.create_task(self._read_loop(peer_id, reader))
            
            logger.info(f"Connected to peer {peer_id} at {peer.address}:{peer.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to peer {peer_id}: {e}")
            return False
    
    async def send(self, peer_id: str, message: bytes) -> bool:
        """Send message to a specific peer."""
        writer = self._connections.get(peer_id)
        if not writer:
            return False
        
        try:
            # Length-prefixed message
            writer.write(struct.pack(">I", len(message)))
            writer.write(message)
            await writer.drain()
            return True
        except Exception as e:
            logger.error(f"Failed to send to {peer_id}: {e}")
            del self._connections[peer_id]
            return False
    
    async def broadcast(self, message: bytes) -> int:
        """Broadcast to all connected peers."""
        sent = 0
        for peer_id in list(self._connections.keys()):
            if await self.send(peer_id, message):
                sent += 1
        return sent
    
    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ):
        """Handle incoming client connection."""
        peer_id = None
        
        try:
            # Read handshake
            length_bytes = await asyncio.wait_for(reader.read(4), timeout=10.0)
            if len(length_bytes) < 4:
                return
            
            length = struct.unpack(">I", length_bytes)[0]
            data = await asyncio.wait_for(reader.read(length), timeout=10.0)
            
            handshake = json.loads(data)
            peer_id = handshake.get("node_id")
            
            if not peer_id:
                logger.warning("Invalid handshake: missing node_id")
                return
            
            # Store connection
            self._connections[peer_id] = writer
            
            # Update peer info
            addr = writer.get_extra_info('peername')
            self._peers[peer_id] = WifiDirectPeer(
                peer_id=peer_id,
                name=handshake.get("name", peer_id[:8]),
                address=addr[0] if addr else None,
                capabilities=handshake.get("capabilities", [])
            )
            
            logger.info(f"Peer {peer_id} connected from {addr}")
            
            # Read messages
            await self._read_loop(peer_id, reader)
            
        except Exception as e:
            logger.error(f"Client handler error: {e}")
        finally:
            if peer_id and peer_id in self._connections:
                del self._connections[peer_id]
            writer.close()
    
    async def _read_loop(self, peer_id: str, reader: asyncio.StreamReader):
        """Read messages from a peer."""
        try:
            while self._running:
                # Read length
                length_bytes = await reader.read(4)
                if len(length_bytes) < 4:
                    break
                
                length = struct.unpack(">I", length_bytes)[0]
                if length > 10 * 1024 * 1024:  # 10MB limit
                    logger.warning(f"Message too large from {peer_id}: {length}")
                    break
                
                # Read message
                data = await reader.read(length)
                if len(data) < length:
                    break
                
                # Deliver to handler
                if self._message_handler:
                    try:
                        self._message_handler(peer_id, data)
                    except Exception as e:
                        logger.error(f"Message handler error: {e}")
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Read loop ended for {peer_id}: {e}")
        finally:
            if peer_id in self._connections:
                del self._connections[peer_id]
    
    async def _start_advertising(self):
        """Start mDNS advertising."""
        try:
            from zeroconf import Zeroconf, ServiceInfo
            
            self._zeroconf = Zeroconf()
            
            # Get local IP
            local_ip = self._get_local_ip()
            
            info = ServiceInfo(
                f"{self.SERVICE_TYPE}.local.",
                f"{self.node_name}.{self.SERVICE_TYPE}.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    "node_id": self.node_id,
                    "mesh_id": self.mesh_id,
                    "caps": ",".join(self.capabilities[:5]),  # Limit size
                }
            )
            
            self._zeroconf.register_service(info)
            self._service_info = info
            logger.info(f"Advertising WiFi Direct service at {local_ip}:{self.port}")
            
        except ImportError:
            logger.warning("zeroconf not installed, advertising disabled")
        except Exception as e:
            logger.error(f"Failed to start advertising: {e}")
    
    async def _stop_advertising(self):
        """Stop mDNS advertising."""
        if hasattr(self, '_zeroconf') and self._zeroconf:
            try:
                if hasattr(self, '_service_info'):
                    self._zeroconf.unregister_service(self._service_info)
                self._zeroconf.close()
            except:
                pass
            self._zeroconf = None
    
    async def _discovery_loop(self):
        """Discover peers via mDNS."""
        try:
            from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
            
            class Listener(ServiceListener):
                def __init__(self, transport):
                    self.transport = transport
                
                def add_service(self, zc, type_, name):
                    info = zc.get_service_info(type_, name)
                    if info:
                        node_id = info.properties.get(b"node_id", b"").decode()
                        mesh_id = info.properties.get(b"mesh_id", b"").decode()
                        
                        # Only add peers from same mesh
                        if mesh_id == self.transport.mesh_id and node_id != self.transport.node_id:
                            addr = socket.inet_ntoa(info.addresses[0]) if info.addresses else None
                            
                            self.transport._peers[node_id] = WifiDirectPeer(
                                peer_id=node_id,
                                name=name.split(".")[0],
                                address=addr,
                                port=info.port,
                                capabilities=info.properties.get(b"caps", b"").decode().split(",")
                            )
                            logger.info(f"Discovered peer: {node_id} at {addr}:{info.port}")
                
                def remove_service(self, zc, type_, name):
                    # Find and remove peer by name
                    for peer_id, peer in list(self.transport._peers.items()):
                        if peer.name in name:
                            del self.transport._peers[peer_id]
                            logger.info(f"Peer removed: {peer_id}")
                            break
                
                def update_service(self, zc, type_, name):
                    self.add_service(zc, type_, name)
            
            zc = Zeroconf()
            listener = Listener(self)
            browser = ServiceBrowser(zc, f"{self.SERVICE_TYPE}.local.", listener)
            
            try:
                while self._running:
                    await asyncio.sleep(1)
            finally:
                browser.cancel()
                zc.close()
                
        except ImportError:
            logger.warning("zeroconf not installed, discovery disabled")
        except Exception as e:
            logger.error(f"Discovery error: {e}")
    
    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"


# Factory function for transport.py integration
def create_wifi_direct_transport(config: dict) -> WifiDirectTransport:
    """Create WiFi Direct transport from config."""
    return WifiDirectTransport(
        node_id=config.get("node_id", ""),
        node_name=config.get("node_name", "Atmosphere"),
        mesh_id=config.get("mesh_id", ""),
        port=config.get("port", 11450),
        capabilities=config.get("capabilities", [])
    )
