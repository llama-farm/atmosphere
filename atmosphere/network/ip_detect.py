"""
Dynamic IP detection for mesh networking.

Detects all usable local IPs and provides utilities for
endpoint management across dynamic network conditions.
"""

import socket
import subprocess
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set
import time

logger = logging.getLogger(__name__)


@dataclass
class NetworkInterface:
    """Information about a network interface."""
    name: str
    ip: str
    is_private: bool
    priority: int  # Lower is better (1=ethernet, 2=wifi, 3=other)
    
    
def is_private_ip(ip: str) -> bool:
    """Check if IP is in private range."""
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    try:
        first = int(parts[0])
        second = int(parts[1])
        # 10.x.x.x
        if first == 10:
            return True
        # 172.16.x.x - 172.31.x.x
        if first == 172 and 16 <= second <= 31:
            return True
        # 192.168.x.x
        if first == 192 and second == 168:
            return True
        return False
    except ValueError:
        return False


def get_local_ips() -> List[NetworkInterface]:
    """
    Get all local IPs with interface info.
    Returns sorted by priority (best first).
    """
    interfaces = []
    
    try:
        # Method 1: Use socket to get all addresses
        hostname = socket.gethostname()
        try:
            # This gets all IPs associated with hostname
            for ip in socket.gethostbyname_ex(hostname)[2]:
                if ip != '127.0.0.1':
                    interfaces.append(NetworkInterface(
                        name='socket',
                        ip=ip,
                        is_private=is_private_ip(ip),
                        priority=2
                    ))
        except socket.gaierror:
            pass
        
        # Method 2: Connect to external to find route IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            # Connect to Google DNS (doesn't actually send anything)
            s.connect(('8.8.8.8', 80))
            route_ip = s.getsockname()[0]
            s.close()
            
            if route_ip != '127.0.0.1':
                # This is the primary outbound interface - highest priority
                existing = [i for i in interfaces if i.ip == route_ip]
                if not existing:
                    interfaces.append(NetworkInterface(
                        name='route',
                        ip=route_ip,
                        is_private=is_private_ip(route_ip),
                        priority=1  # Best - this is the actual route
                    ))
                else:
                    existing[0].priority = 1
        except Exception:
            pass
        
        # Method 3: Parse ifconfig/ip output for more interfaces
        try:
            import platform
            if platform.system() == 'Darwin':
                # macOS
                output = subprocess.check_output(['ifconfig'], text=True, stderr=subprocess.DEVNULL)
                current_iface = None
                for line in output.split('\n'):
                    if line and not line.startswith('\t') and ':' in line:
                        current_iface = line.split(':')[0]
                    elif 'inet ' in line and '127.0.0.1' not in line:
                        parts = line.strip().split()
                        ip_idx = parts.index('inet') + 1
                        if ip_idx < len(parts):
                            ip = parts[ip_idx]
                            existing = [i for i in interfaces if i.ip == ip]
                            if not existing:
                                # Prioritize en0 (wifi/ethernet) over others
                                priority = 2 if current_iface and current_iface.startswith('en') else 3
                                interfaces.append(NetworkInterface(
                                    name=current_iface or 'unknown',
                                    ip=ip,
                                    is_private=is_private_ip(ip),
                                    priority=priority
                                ))
            else:
                # Linux
                output = subprocess.check_output(['ip', 'addr'], text=True, stderr=subprocess.DEVNULL)
                current_iface = None
                for line in output.split('\n'):
                    if ': ' in line and '@' not in line.split(':')[0]:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            current_iface = parts[1].strip().split('@')[0]
                    elif 'inet ' in line and '127.0.0.1' not in line:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            ip = parts[1].split('/')[0]
                            existing = [i for i in interfaces if i.ip == ip]
                            if not existing:
                                priority = 2 if current_iface and (current_iface.startswith('eth') or current_iface.startswith('en')) else 3
                                interfaces.append(NetworkInterface(
                                    name=current_iface or 'unknown',
                                    ip=ip,
                                    is_private=is_private_ip(ip),
                                    priority=priority
                                ))
        except Exception as e:
            logger.debug(f"ifconfig/ip parsing failed: {e}")
    
    except Exception as e:
        logger.error(f"IP detection failed: {e}")
    
    # Sort by priority (lower is better) and filter private IPs first
    interfaces.sort(key=lambda x: (not x.is_private, x.priority))
    
    return interfaces


def get_best_local_ip() -> Optional[str]:
    """Get the best local IP for mesh communication."""
    interfaces = get_local_ips()
    if interfaces:
        return interfaces[0].ip
    return None


def get_all_local_ips() -> List[str]:
    """Get all usable local IPs."""
    return list(set(i.ip for i in get_local_ips()))


@dataclass
class EndpointInfo:
    """Endpoint information for a node."""
    node_id: str
    local_ips: List[str] = field(default_factory=list)
    local_port: int = 11451
    relay_url: Optional[str] = None
    last_updated: float = field(default_factory=time.time)
    
    def get_local_endpoints(self) -> List[str]:
        """Get all local WebSocket endpoints."""
        return [f"ws://{ip}:{self.local_port}" for ip in self.local_ips]
    
    def get_all_endpoints(self) -> List[str]:
        """Get all endpoints (local first, then relay)."""
        endpoints = self.get_local_endpoints()
        if self.relay_url:
            endpoints.append(self.relay_url)
        return endpoints
    
    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "local_ips": self.local_ips,
            "local_port": self.local_port,
            "relay_url": self.relay_url,
            "last_updated": self.last_updated
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "EndpointInfo":
        return cls(
            node_id=data["node_id"],
            local_ips=data.get("local_ips", []),
            local_port=data.get("local_port", 11451),
            relay_url=data.get("relay_url"),
            last_updated=data.get("last_updated", time.time())
        )


class EndpointRegistry:
    """
    Registry of known endpoints for mesh nodes.
    
    Tracks both local and relay endpoints, handles updates
    from gossip, and provides connection ordering.
    """
    
    def __init__(self, my_node_id: str, my_port: int = 11451, relay_base: Optional[str] = None, mesh_id: Optional[str] = None):
        self.my_node_id = my_node_id
        self.my_port = my_port
        self.relay_base = relay_base
        self.mesh_id = mesh_id
        self._endpoints: dict[str, EndpointInfo] = {}
        self._my_ips: List[str] = []
        self._last_ip_check: float = 0
        self._ip_check_interval: float = 30.0  # Re-check IPs every 30 seconds
    
    def refresh_my_ips(self) -> bool:
        """
        Refresh local IP addresses.
        Returns True if IPs changed.
        """
        now = time.time()
        if now - self._last_ip_check < self._ip_check_interval:
            return False
        
        self._last_ip_check = now
        old_ips = set(self._my_ips)
        self._my_ips = get_all_local_ips()
        new_ips = set(self._my_ips)
        
        if old_ips != new_ips:
            logger.info(f"Local IPs changed: {old_ips} -> {new_ips}")
            return True
        return False
    
    def get_my_endpoint_info(self) -> EndpointInfo:
        """Get current endpoint info for this node."""
        self.refresh_my_ips()
        relay_url = None
        if self.relay_base and self.mesh_id:
            relay_url = f"{self.relay_base}/relay/{self.mesh_id}"
        
        return EndpointInfo(
            node_id=self.my_node_id,
            local_ips=self._my_ips.copy(),
            local_port=self.my_port,
            relay_url=relay_url
        )
    
    def update_peer(self, endpoint_info: EndpointInfo) -> bool:
        """
        Update endpoint info for a peer.
        Returns True if this is new/changed info.
        """
        if endpoint_info.node_id == self.my_node_id:
            return False  # Don't store our own
        
        existing = self._endpoints.get(endpoint_info.node_id)
        if existing:
            # Check if anything changed
            if (set(existing.local_ips) == set(endpoint_info.local_ips) and
                existing.local_port == endpoint_info.local_port and
                existing.relay_url == endpoint_info.relay_url):
                # Just update timestamp
                existing.last_updated = time.time()
                return False
        
        endpoint_info.last_updated = time.time()
        self._endpoints[endpoint_info.node_id] = endpoint_info
        logger.info(f"Updated endpoints for {endpoint_info.node_id}: {endpoint_info.local_ips}")
        return True
    
    def get_peer_endpoints(self, node_id: str) -> Optional[EndpointInfo]:
        """Get endpoint info for a peer."""
        return self._endpoints.get(node_id)
    
    def get_all_peers(self) -> List[EndpointInfo]:
        """Get all known peer endpoints."""
        return list(self._endpoints.values())
    
    def remove_peer(self, node_id: str) -> None:
        """Remove a peer from the registry."""
        self._endpoints.pop(node_id, None)
    
    def get_connection_order(self, node_id: str) -> List[str]:
        """
        Get ordered list of endpoints to try for a peer.
        Local first, then relay.
        """
        info = self._endpoints.get(node_id)
        if not info:
            return []
        return info.get_all_endpoints()
    
    def export_for_gossip(self) -> dict:
        """Export endpoint info for inclusion in gossip announcements."""
        return self.get_my_endpoint_info().to_dict()
    
    def import_from_gossip(self, data: dict) -> bool:
        """Import endpoint info from a gossip announcement."""
        try:
            info = EndpointInfo.from_dict(data)
            return self.update_peer(info)
        except Exception as e:
            logger.warning(f"Failed to import endpoint info: {e}")
            return False


# Convenience singleton for common use
_default_registry: Optional[EndpointRegistry] = None


def get_endpoint_registry() -> Optional[EndpointRegistry]:
    """Get the default endpoint registry."""
    return _default_registry


def init_endpoint_registry(node_id: str, port: int = 11451, relay_base: Optional[str] = None, mesh_id: Optional[str] = None) -> EndpointRegistry:
    """Initialize the default endpoint registry."""
    global _default_registry
    _default_registry = EndpointRegistry(node_id, port, relay_base, mesh_id)
    _default_registry.refresh_my_ips()
    return _default_registry
