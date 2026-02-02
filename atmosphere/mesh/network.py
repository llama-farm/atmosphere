"""
Network utilities for internet-scale mesh.

NOTE: This module has been moved to atmosphere.network
This file provides backward compatibility.
"""

# Re-export everything from the new location
from ..network.stun import (
    PublicEndpoint,
    discover_public_ip,
    get_local_ip,
    NetworkInfo,
    gather_network_info,
    STUN_SERVERS,
)

from ..network.relay import (
    RelayInfo,
    DEFAULT_RELAYS,
    find_best_relay,
)

__all__ = [
    "PublicEndpoint",
    "discover_public_ip",
    "get_local_ip",
    "NetworkInfo",
    "gather_network_info",
    "STUN_SERVERS",
    "RelayInfo",
    "DEFAULT_RELAYS",
    "find_best_relay",
]
