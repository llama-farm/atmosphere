"""
STUN client for NAT discovery and public endpoint detection.

Implements RFC 5389 (STUN) for discovering:
- Public IP address
- Public port mapping
- NAT type (basic detection)
"""

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Public STUN servers (UDP, port 3478 or 19302)
STUN_SERVERS = [
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun2.l.google.com", 19302),
    ("stun.cloudflare.com", 3478),
    ("stun.stunprotocol.org", 3478),
]

# STUN message types
STUN_BINDING_REQUEST = 0x0001
STUN_BINDING_RESPONSE = 0x0101
STUN_MAGIC_COOKIE = 0x2112A442

# STUN attribute types
ATTR_MAPPED_ADDRESS = 0x0001
ATTR_XOR_MAPPED_ADDRESS = 0x0020


@dataclass
class PublicEndpoint:
    """Public endpoint information discovered via STUN."""
    ip: str
    port: int
    source: str  # "stun:<server>", "manual", "upnp", etc.
    nat_type: Optional[str] = None  # "full_cone", "restricted", "symmetric", etc.
    
    def __str__(self) -> str:
        return f"{self.ip}:{self.port}"
    
    @property
    def is_public(self) -> bool:
        """Check if IP is public (not private/local)."""
        try:
            import ipaddress
            ip = ipaddress.ip_address(self.ip)
            return ip.is_global
        except ValueError:
            return False
    
    def to_dict(self) -> dict:
        return {
            "ip": self.ip,
            "port": self.port,
            "source": self.source,
            "nat_type": self.nat_type,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PublicEndpoint":
        return cls(**data)


def _build_stun_request() -> Tuple[bytes, bytes]:
    """Build a STUN binding request."""
    import os
    
    # Transaction ID (96 bits)
    transaction_id = os.urandom(12)
    
    # STUN header: type (2) + length (2) + magic cookie (4) + transaction ID (12)
    header = struct.pack(
        ">HHI",
        STUN_BINDING_REQUEST,
        0,  # Length (no attributes)
        STUN_MAGIC_COOKIE,
    ) + transaction_id
    
    return header, transaction_id


def _parse_stun_response(data: bytes, transaction_id: bytes) -> Optional[Tuple[str, int]]:
    """Parse STUN binding response to extract mapped address."""
    if len(data) < 20:
        return None
    
    # Parse header
    msg_type, msg_len, magic = struct.unpack(">HHI", data[:8])
    resp_transaction_id = data[8:20]
    
    # Verify response
    if msg_type != STUN_BINDING_RESPONSE:
        return None
    if magic != STUN_MAGIC_COOKIE:
        return None
    if resp_transaction_id != transaction_id:
        return None
    
    # Parse attributes
    offset = 20
    while offset < 20 + msg_len:
        if offset + 4 > len(data):
            break
        
        attr_type, attr_len = struct.unpack(">HH", data[offset:offset+4])
        offset += 4
        
        if offset + attr_len > len(data):
            break
        
        attr_data = data[offset:offset+attr_len]
        
        # XOR-MAPPED-ADDRESS (preferred)
        if attr_type == ATTR_XOR_MAPPED_ADDRESS and attr_len >= 8:
            family = attr_data[1]
            if family == 0x01:  # IPv4
                xor_port = struct.unpack(">H", attr_data[2:4])[0]
                xor_ip = struct.unpack(">I", attr_data[4:8])[0]
                
                # XOR with magic cookie
                port = xor_port ^ (STUN_MAGIC_COOKIE >> 16)
                ip_int = xor_ip ^ STUN_MAGIC_COOKIE
                ip = socket.inet_ntoa(struct.pack(">I", ip_int))
                
                return ip, port
        
        # MAPPED-ADDRESS (fallback)
        elif attr_type == ATTR_MAPPED_ADDRESS and attr_len >= 8:
            family = attr_data[1]
            if family == 0x01:  # IPv4
                port = struct.unpack(">H", attr_data[2:4])[0]
                ip = socket.inet_ntoa(attr_data[4:8])
                return ip, port
        
        # Align to 4 bytes
        offset += attr_len + ((4 - attr_len % 4) % 4)
    
    return None


async def discover_public_ip(
    local_port: int = 0,
    timeout: float = 3.0,
) -> Optional[PublicEndpoint]:
    """
    Discover public IP address using STUN.
    
    Args:
        local_port: Local port to bind (0 for random)
        timeout: Timeout per server in seconds
        
    Returns:
        PublicEndpoint if discovered, None otherwise
    """
    loop = asyncio.get_event_loop()
    
    for server, port in STUN_SERVERS:
        try:
            # Resolve STUN server
            try:
                server_addr = socket.gethostbyname(server)
            except socket.gaierror:
                logger.debug(f"Could not resolve STUN server: {server}")
                continue
            
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
            
            if local_port:
                sock.bind(("0.0.0.0", local_port))
            
            try:
                # Build and send request
                request, transaction_id = _build_stun_request()
                await loop.sock_sendto(sock, request, (server_addr, port))
                
                # Wait for response
                try:
                    data = await asyncio.wait_for(
                        loop.sock_recv(sock, 1024),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    logger.debug(f"STUN server {server} timeout")
                    continue
                
                # Parse response
                result = _parse_stun_response(data, transaction_id)
                if result:
                    ip, mapped_port = result
                    logger.info(f"STUN discovery: {ip}:{mapped_port} (via {server})")
                    return PublicEndpoint(
                        ip=ip,
                        port=mapped_port,
                        source=f"stun:{server}",
                    )
                
            finally:
                sock.close()
                
        except Exception as e:
            logger.debug(f"STUN server {server} failed: {e}")
            continue
    
    logger.warning("All STUN servers failed")
    return None


async def get_local_ip() -> str:
    """Get the local IP address used for outbound connections."""
    try:
        # Connect to a public IP (doesn't actually send data)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


@dataclass
class NetworkInfo:
    """Complete network information for a node."""
    local_ip: str
    local_port: int
    public_endpoint: Optional[PublicEndpoint]
    is_behind_nat: bool
    nat_type: Optional[str]
    
    @property
    def best_endpoint(self) -> str:
        """Get the best endpoint for sharing."""
        if self.public_endpoint and self.public_endpoint.is_public:
            return str(self.public_endpoint)
        return f"{self.local_ip}:{self.local_port}"
    
    @property
    def is_publicly_reachable(self) -> bool:
        """Check if we're likely reachable from the internet."""
        if not self.public_endpoint:
            return False
        # If public IP matches and port matches, probably reachable
        # (full cone NAT or no NAT)
        return self.public_endpoint.is_public


async def gather_network_info(local_port: int) -> NetworkInfo:
    """Gather complete network information for this node."""
    
    # Get local IP
    local_ip = await get_local_ip()
    
    # Try STUN discovery
    public_endpoint = await discover_public_ip(local_port=local_port)
    
    # Determine if behind NAT
    is_behind_nat = True
    if public_endpoint:
        is_behind_nat = public_endpoint.ip != local_ip
    
    return NetworkInfo(
        local_ip=local_ip,
        local_port=local_port,
        public_endpoint=public_endpoint,
        is_behind_nat=is_behind_nat,
        nat_type=public_endpoint.nat_type if public_endpoint else None,
    )
