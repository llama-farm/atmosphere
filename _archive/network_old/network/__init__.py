"""
Network utilities for internet-scale mesh.

This module provides:
- STUN client for public IP/port discovery
- NAT traversal with UDP hole punching
- Relay server for fallback connectivity
- Resilient multi-transport mesh connectivity
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
from .resilient_transport import (
    ResilientTransportManager,
    TransportType,
    TransportState,
    TransportMetrics,
    Transport,
    PeerConnection,
)
from .mesh_connection import (
    MeshConnectionManager,
    MeshConfig,
)

__all__ = [
    # STUN/NAT
    "PublicEndpoint",
    "discover_public_ip",
    "get_local_ip",
    "NetworkInfo",
    "gather_network_info",
    "NATTraversal",
    "ConnectionAttempt",
    "punch_hole",
    "establish_p2p_connection",
    # Relay
    "RelayServer",
    "RelayClient",
    "RelayInfo",
    "DEFAULT_RELAYS",
    # Resilient Transport
    "ResilientTransportManager",
    "TransportType",
    "TransportState",
    "TransportMetrics",
    "Transport",
    "PeerConnection",
    "MeshConnectionManager",
    "MeshConfig",
]
