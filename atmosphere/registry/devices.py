"""
Device Registry - Tracks all devices that have ever connected to the mesh.

Persists device information including:
- Immutable device ID (fingerprint)
- Device name and type
- Capabilities
- Connection history
- Trust/permission settings
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class DeviceStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class TrustLevel(Enum):
    TRUSTED = "trusted"      # Full access
    LIMITED = "limited"      # Limited capabilities
    BLOCKED = "blocked"      # No access
    PENDING = "pending"      # Awaiting approval


@dataclass
class DeviceInfo:
    """Information about a known device."""
    device_id: str                          # Immutable fingerprint
    name: str = "Unknown Device"
    device_type: str = "unknown"            # android, ios, macos, windows, linux
    
    # Connection info
    first_seen: float = 0                   # Unix timestamp
    last_seen: float = 0                    # Unix timestamp
    last_endpoint: str = ""                 # Last known endpoint (local/relay)
    connection_count: int = 0               # Total connections
    
    # Capabilities
    capabilities: List[str] = field(default_factory=list)
    
    # Trust settings
    trust_level: str = "trusted"            # TrustLevel value
    allowed_capabilities: List[str] = field(default_factory=list)  # Empty = all
    blocked_capabilities: List[str] = field(default_factory=list)
    
    # Metadata
    model: str = ""                         # Device model (e.g., "Pixel 7")
    os_version: str = ""                    # OS version
    app_version: str = ""                   # Atmosphere app version
    
    # Runtime state (not persisted)
    status: str = "offline"                 # DeviceStatus value
    current_cost: float = 1.0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "DeviceInfo":
        # Filter out unknown fields and handle status separately
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


class DeviceRegistry:
    """
    Persistent registry of all known devices.
    
    Stored in ~/.atmosphere/devices.json
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path.home() / ".atmosphere"
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.data_dir / "devices.json"
        
        self._devices: Dict[str, DeviceInfo] = {}
        self._load()
    
    def _load(self):
        """Load registry from disk."""
        if self.registry_file.exists():
            try:
                with open(self.registry_file) as f:
                    data = json.load(f)
                    for device_id, device_data in data.get("devices", {}).items():
                        self._devices[device_id] = DeviceInfo.from_dict(device_data)
                logger.info(f"Loaded {len(self._devices)} devices from registry")
            except Exception as e:
                logger.error(f"Failed to load device registry: {e}")
    
    def _save(self):
        """Save registry to disk."""
        try:
            data = {
                "version": 1,
                "updated": time.time(),
                "devices": {
                    device_id: device.to_dict() 
                    for device_id, device in self._devices.items()
                }
            }
            with open(self.registry_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self._devices)} devices to registry")
        except Exception as e:
            logger.error(f"Failed to save device registry: {e}")
    
    def register_device(
        self,
        device_id: str,
        name: str = None,
        device_type: str = None,
        capabilities: List[str] = None,
        endpoint: str = None,
        model: str = None,
        **kwargs
    ) -> DeviceInfo:
        """
        Register or update a device.
        
        Called when a device connects to the mesh.
        """
        now = time.time()
        
        if device_id in self._devices:
            # Update existing device
            device = self._devices[device_id]
            device.last_seen = now
            device.connection_count += 1
            device.status = DeviceStatus.ONLINE.value
            
            if name:
                device.name = name
            if device_type:
                device.device_type = device_type
            if capabilities:
                device.capabilities = capabilities
            if endpoint:
                device.last_endpoint = endpoint
            if model:
                device.model = model
            
            logger.info(f"Device reconnected: {device.name} ({device_id[:8]}...)")
        else:
            # New device
            device = DeviceInfo(
                device_id=device_id,
                name=name or "Unknown Device",
                device_type=device_type or "unknown",
                first_seen=now,
                last_seen=now,
                last_endpoint=endpoint or "",
                connection_count=1,
                capabilities=capabilities or [],
                status=DeviceStatus.ONLINE.value,
                model=model or "",
            )
            self._devices[device_id] = device
            logger.info(f"New device registered: {device.name} ({device_id[:8]}...)")
        
        self._save()
        return device
    
    def mark_offline(self, device_id: str):
        """Mark a device as offline."""
        if device_id in self._devices:
            self._devices[device_id].status = DeviceStatus.OFFLINE.value
            self._save()
    
    def mark_online(self, device_id: str, cost: float = 1.0):
        """Mark a device as online."""
        if device_id in self._devices:
            self._devices[device_id].status = DeviceStatus.ONLINE.value
            self._devices[device_id].current_cost = cost
            self._devices[device_id].last_seen = time.time()
            self._save()
    
    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """Get device info by ID."""
        return self._devices.get(device_id)
    
    def get_all_devices(self) -> List[DeviceInfo]:
        """Get all known devices."""
        return list(self._devices.values())
    
    def get_online_devices(self) -> List[DeviceInfo]:
        """Get currently online devices."""
        return [d for d in self._devices.values() if d.status == DeviceStatus.ONLINE.value]
    
    def get_offline_devices(self) -> List[DeviceInfo]:
        """Get offline devices."""
        return [d for d in self._devices.values() if d.status == DeviceStatus.OFFLINE.value]
    
    def set_trust_level(self, device_id: str, trust_level: TrustLevel):
        """Set trust level for a device."""
        if device_id in self._devices:
            self._devices[device_id].trust_level = trust_level.value
            self._save()
    
    def block_device(self, device_id: str):
        """Block a device from connecting."""
        self.set_trust_level(device_id, TrustLevel.BLOCKED)
    
    def unblock_device(self, device_id: str):
        """Unblock a device."""
        self.set_trust_level(device_id, TrustLevel.TRUSTED)
    
    def remove_device(self, device_id: str):
        """Remove a device from the registry."""
        if device_id in self._devices:
            del self._devices[device_id]
            self._save()
    
    def update_cost(self, device_id: str, cost: float):
        """Update a device's current cost."""
        if device_id in self._devices:
            self._devices[device_id].current_cost = cost


# Global registry instance
_registry: Optional[DeviceRegistry] = None


def get_device_registry() -> DeviceRegistry:
    """Get the global device registry instance."""
    global _registry
    if _registry is None:
        _registry = DeviceRegistry()
    return _registry
