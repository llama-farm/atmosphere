"""
Network utilities for internet-scale mesh.

This module provides:
- STUN client for public IP/port discovery
- NAT traversal with UDP hole punching
- Relay server for fallback connectivity
"""

from .stun import (
    PublicEndpoint,
    discover_public_ip,
    get_local_ip,
    NetworkInfo,
    gather_network_info,
)
from .nat import (
    NATTraversal,
    ConnectionAttempt,
    punch_hole,
    establish_p2p_connection,
)
from .relay import (
    RelayServer,
    RelayClient,
    RelayInfo,
    DEFAULT_RELAYS,
)

__all__ = [
    "PublicEndpoint",
    "discover_public_ip",
    "get_local_ip",
    "NetworkInfo",
    "gather_network_info",
    "NATTraversal",
    "ConnectionAttempt",
    "punch_hole",
    "establish_p2p_connection",
    "RelayServer",
    "RelayClient",
    "RelayInfo",
    "DEFAULT_RELAYS",
]
