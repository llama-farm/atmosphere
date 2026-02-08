"""
Concrete transport implementations for Atmosphere mesh.

Each transport handles connection to peers via a specific method:
- LAN: Direct WebSocket connection on local network
- Relay: WebSocket via cloud relay server
- BLE: Bluetooth Low Energy (future)
- WiFi Direct: P2P WiFi (future)
- Matter: Smart home protocol (future)
"""

from .lan import LanTransport
from .relay import RelayTransport
from .base import BaseWebSocketTransport

__all__ = [
    "LanTransport",
    "RelayTransport",
    "BaseWebSocketTransport",
]
