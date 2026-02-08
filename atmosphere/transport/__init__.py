"""
Atmosphere Transport Layer - Simplified

For now: Just relay transport.
Future: Add LAN discovery, BLE, etc. when core routing is solid.
"""

from .relay import RelayConnection, RelayMessage, create_relay_connection

__all__ = [
    "RelayConnection",
    "RelayMessage",
    "create_relay_connection",
]
