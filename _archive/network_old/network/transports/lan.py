"""
LAN Transport - Direct WebSocket connection on local network.

Characteristics:
- Lowest latency (~1-5ms)
- Highest bandwidth
- Requires same network
- No internet dependency
- Most reliable when available
"""

import logging
from ..resilient_transport import TransportType
from .base import BaseWebSocketTransport

log = logging.getLogger(__name__)


class LanTransport(BaseWebSocketTransport):
    """
    Direct LAN WebSocket transport.
    
    Connects directly to a peer's mesh endpoint on the local network.
    This is the fastest and most reliable transport when both nodes
    are on the same network.
    """
    
    def __init__(self):
        super().__init__(TransportType.LAN)
        # LAN has lowest battery cost
        self.metrics.battery_cost = 0.1
        # LAN typically has highest bandwidth
        self.metrics.bandwidth_kbps = 100000.0  # 100 Mbps typical
    
    async def connect(self, address: str) -> bool:
        """
        Connect to peer's mesh WebSocket endpoint.
        
        Address format: "ws://192.168.x.x:11451/mesh/ws"
        """
        # Ensure ws:// prefix
        if not address.startswith(("ws://", "wss://")):
            address = f"ws://{address}"
        
        # Ensure mesh WebSocket path
        if "/mesh/ws" not in address and not address.endswith("/ws"):
            if address.endswith("/"):
                address = f"{address}mesh/ws"
            else:
                address = f"{address}/mesh/ws"
        
        log.info(f"LAN connecting to {address}")
        return await super().connect(address)


def create_lan_transport() -> LanTransport:
    """Factory function for creating LAN transports."""
    return LanTransport()
