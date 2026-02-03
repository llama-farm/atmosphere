"""
Transport layer for Atmosphere mesh networking.

This module provides various transport backends:
- BLE: Bluetooth Low Energy mesh for offline connectivity
- WiFi: Direct WiFi communication (future)
"""

from .ble_mac import (
    BleTransport,
    BleMessage,
    MessageType,
    MESH_SERVICE_UUID,
    TX_CHAR_UUID,
    RX_CHAR_UUID,
    INFO_CHAR_UUID,
)

__all__ = [
    "BleTransport",
    "BleMessage",
    "MessageType",
    "MESH_SERVICE_UUID",
    "TX_CHAR_UUID",
    "RX_CHAR_UUID",
    "INFO_CHAR_UUID",
]
