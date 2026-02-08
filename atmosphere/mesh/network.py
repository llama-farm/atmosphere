"""
Network utilities for internet-scale mesh.

NOTE: This module has been moved to atmosphere.network
This file provides backward compatibility.
"""

# Re-export from new locations
from ..network.ip_detect import (
    get_local_ips,
    get_best_local_ip,
    get_all_local_ips,
    EndpointInfo,
    EndpointRegistry,
)

# STUN support has been removed/refactored
# Stubs for backward compatibility
class PublicEndpoint:
    pass

def discover_public_ip(*args, **kwargs):
    return None

def gather_network_info(*args, **kwargs):
    return {
        "local_ips": get_all_local_ips(),
        "public_ip": None,
        "endpoints": []
    }

STUN_SERVERS = []

# Relay support
from ..transport.relay import (
    RelayConnection,
    # Add other relay exports if needed
)

__all__ = [
    "get_local_ips",
    "get_best_local_ip",
    "get_all_local_ips",
    "EndpointInfo",
    "EndpointRegistry",
    "PublicEndpoint",
    "discover_public_ip",
    "gather_network_info",
    "STUN_SERVERS",
]
