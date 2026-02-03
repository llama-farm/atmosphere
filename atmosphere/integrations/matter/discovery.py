"""
Matter Device Discovery.

Provides mDNS-based discovery of commissionable Matter devices
and enumeration of already-commissioned devices.

Note: For MVP, actual Matter commissioning is stubbed.
Real commissioning requires matter.js or chip-tool integration.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Awaitable
from pathlib import Path
import json

from .models import (
    MatterDevice,
    MatterEndpoint,
    MatterCluster,
    MatterDeviceType,
    ClusterType,
    DeviceStatus,
    CommissionableDevice,
)

logger = logging.getLogger(__name__)


# Storage path for device registry
DEFAULT_STORAGE_PATH = Path.home() / ".atmosphere" / "matter"


@dataclass
class DiscoveryConfig:
    """Configuration for Matter discovery."""
    
    # mDNS discovery timeout
    discovery_timeout_seconds: float = 30.0
    
    # Whether to auto-discover on startup
    auto_discover: bool = True
    
    # Storage path for device registry
    storage_path: Path = DEFAULT_STORAGE_PATH
    
    # Callback when device goes online/offline
    on_device_status_change: Optional[Callable[[MatterDevice, DeviceStatus], Awaitable[None]]] = None
    
    # Callback when new device is discovered
    on_device_discovered: Optional[Callable[[CommissionableDevice], Awaitable[None]]] = None


class MatterDiscovery:
    """
    Discovers and manages Matter devices.
    
    For MVP, this is largely stubbed. The structure is in place for
    integrating with matter.js bridge for real discovery.
    
    Discovery types:
    1. mDNS discovery of commissionable devices (_matterc._udp.local)
    2. Enumeration of already-commissioned devices from storage
    3. Real-time status monitoring via subscriptions
    """
    
    def __init__(self, config: Optional[DiscoveryConfig] = None):
        self.config = config or DiscoveryConfig()
        self._devices: Dict[int, MatterDevice] = {}  # node_id → device
        self._commissionable: Dict[str, CommissionableDevice] = {}  # discriminator → device
        self._discovery_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Ensure storage directory exists
        self.config.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Load persisted devices
        self._load_devices()
    
    def _load_devices(self) -> None:
        """Load devices from persistent storage."""
        devices_file = self.config.storage_path / "devices.json"
        
        if devices_file.exists():
            try:
                with open(devices_file, "r") as f:
                    data = json.load(f)
                
                for device_data in data.get("devices", []):
                    device = MatterDevice.from_dict(device_data)
                    device.status = DeviceStatus.UNKNOWN  # Will be updated on connect
                    self._devices[device.node_id] = device
                
                logger.info(f"Loaded {len(self._devices)} devices from storage")
            except Exception as e:
                logger.error(f"Failed to load devices: {e}")
    
    def _save_devices(self) -> None:
        """Save devices to persistent storage."""
        devices_file = self.config.storage_path / "devices.json"
        
        try:
            data = {
                "version": 1,
                "updated": time.time(),
                "devices": [d.to_dict() for d in self._devices.values()],
            }
            
            with open(devices_file, "w") as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved {len(self._devices)} devices to storage")
        except Exception as e:
            logger.error(f"Failed to save devices: {e}")
    
    async def start(self) -> None:
        """Start the discovery service."""
        if self._running:
            return
        
        self._running = True
        logger.info("Starting Matter discovery service")
        
        if self.config.auto_discover:
            self._discovery_task = asyncio.create_task(self._background_discovery())
    
    async def stop(self) -> None:
        """Stop the discovery service."""
        self._running = False
        
        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass
            self._discovery_task = None
        
        self._save_devices()
        logger.info("Stopped Matter discovery service")
    
    async def _background_discovery(self) -> None:
        """Background task for periodic discovery."""
        while self._running:
            try:
                # Discover commissionable devices
                await self.discover_commissionable()
                
                # Check status of known devices
                await self._check_device_status()
                
                # Wait before next discovery cycle
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Discovery error: {e}")
                await asyncio.sleep(10)
    
    async def discover_commissionable(
        self,
        timeout: Optional[float] = None,
    ) -> List[CommissionableDevice]:
        """
        Discover commissionable Matter devices via mDNS.
        
        Commissionable devices advertise via:
        - _matterc._udp.local (commissioning mode)
        - _matterd._udp.local (commissioned but open for additional fabrics)
        
        Note: For MVP, this is STUBBED. Real implementation requires:
        - zeroconf library for mDNS
        - Or integration with matter.js bridge
        
        Args:
            timeout: Discovery timeout in seconds
        
        Returns:
            List of discovered commissionable devices
        """
        timeout = timeout or self.config.discovery_timeout_seconds
        
        # STUB: In real implementation, this would use zeroconf or matter.js
        # For now, return empty list
        logger.info(f"Scanning for commissionable Matter devices (timeout={timeout}s)...")
        
        # Simulated delay for discovery
        await asyncio.sleep(min(timeout, 2.0))
        
        discovered = list(self._commissionable.values())
        logger.info(f"Discovery complete: found {len(discovered)} commissionable devices")
        
        return discovered
    
    async def _check_device_status(self) -> None:
        """Check online status of known devices."""
        for device in self._devices.values():
            old_status = device.status
            
            # STUB: In real implementation, this would ping the device
            # via matter.js bridge
            
            # For now, mark devices as unknown after 5 minutes
            if time.time() - device.last_seen > 300:
                device.status = DeviceStatus.UNKNOWN
            
            if old_status != device.status:
                if self.config.on_device_status_change:
                    await self.config.on_device_status_change(device, device.status)
    
    async def commission_device(
        self,
        setup_code: str,
        label: Optional[str] = None,
        location: Optional[str] = None,
    ) -> MatterDevice:
        """
        Commission a new Matter device.
        
        The setup code can be:
        - QR code payload: MT:Y.K9042C00KA0648G00
        - Manual pairing code: 749-701-1233-65521327694
        
        Note: For MVP, this is STUBBED. Real commissioning requires
        matter.js bridge integration.
        
        Args:
            setup_code: QR payload or manual pairing code
            label: Optional friendly name
            location: Optional room/area
        
        Returns:
            The newly commissioned device
        
        Raises:
            CommissioningError: If commissioning fails
        """
        logger.info(f"Commissioning device with code: {setup_code[:10]}...")
        
        # STUB: Generate fake device for testing
        # In real implementation, this would:
        # 1. Parse setup code
        # 2. Establish PASE session
        # 3. Verify device attestation
        # 4. Issue operational credentials
        # 5. Configure ACLs
        
        # For now, create a mock device
        node_id = len(self._devices) + 1
        
        device = MatterDevice(
            node_id=node_id,
            vendor_id=0x1234,
            product_id=0x0001,
            vendor_name="Test Vendor",
            product_name="Test Light",
            serial_number=f"SN{node_id:08d}",
            firmware_version="1.0.0",
            label=label,
            location=location,
            status=DeviceStatus.ONLINE,
            last_seen=time.time(),
            endpoints=[
                MatterEndpoint(
                    endpoint_id=1,
                    device_type=MatterDeviceType.DIMMABLE_LIGHT,
                    clusters=[
                        MatterCluster(
                            cluster_id=ClusterType.ON_OFF,
                            name="OnOff",
                            attributes={"onOff": False},
                            supported_commands=["On", "Off", "Toggle"],
                        ),
                        MatterCluster(
                            cluster_id=ClusterType.LEVEL_CONTROL,
                            name="LevelControl",
                            attributes={"currentLevel": 254, "minLevel": 1, "maxLevel": 254},
                            supported_commands=["MoveToLevel", "Move", "Step", "Stop"],
                        ),
                    ],
                ),
            ],
        )
        
        # Store the device
        self._devices[device.node_id] = device
        self._save_devices()
        
        logger.info(f"Commissioned device: {device.display_name} (node_id={device.node_id})")
        
        return device
    
    async def decommission_device(self, node_id: int) -> bool:
        """
        Remove a device from our Matter fabric.
        
        Note: For MVP, this is STUBBED.
        
        Args:
            node_id: The device's node ID
        
        Returns:
            True if successful
        """
        if node_id not in self._devices:
            return False
        
        device = self._devices.pop(node_id)
        self._save_devices()
        
        logger.info(f"Decommissioned device: {device.display_name}")
        return True
    
    def get_device(self, node_id: int) -> Optional[MatterDevice]:
        """Get a device by node ID."""
        return self._devices.get(node_id)
    
    def get_device_by_label(self, label: str) -> Optional[MatterDevice]:
        """Get a device by its friendly label."""
        for device in self._devices.values():
            if device.label and device.label.lower() == label.lower():
                return device
        return None
    
    def get_all_devices(self) -> List[MatterDevice]:
        """Get all known devices."""
        return list(self._devices.values())
    
    def get_online_devices(self) -> List[MatterDevice]:
        """Get all online devices."""
        return [d for d in self._devices.values() if d.status == DeviceStatus.ONLINE]
    
    async def update_device_label(
        self,
        node_id: int,
        label: str,
        location: Optional[str] = None,
    ) -> Optional[MatterDevice]:
        """Update a device's friendly name and location."""
        device = self._devices.get(node_id)
        if not device:
            return None
        
        device.label = label
        if location is not None:
            device.location = location
        
        self._save_devices()
        return device
    
    def update_device_status(
        self,
        node_id: int,
        status: DeviceStatus,
    ) -> None:
        """Update a device's online status (called by bridge)."""
        device = self._devices.get(node_id)
        if device:
            device.status = status
            device.last_seen = time.time()
    
    def add_mock_device(
        self,
        device_type: MatterDeviceType,
        label: str,
        location: Optional[str] = None,
    ) -> MatterDevice:
        """
        Add a mock device for testing.
        
        This bypasses commissioning and adds a fake device directly.
        Useful for development and testing without real hardware.
        """
        from .models import ClusterType
        
        node_id = len(self._devices) + 1
        
        # Build clusters based on device type
        clusters = []
        
        if device_type in (
            MatterDeviceType.ON_OFF_LIGHT,
            MatterDeviceType.DIMMABLE_LIGHT,
            MatterDeviceType.COLOR_TEMP_LIGHT,
            MatterDeviceType.EXTENDED_COLOR_LIGHT,
            MatterDeviceType.ON_OFF_PLUG,
        ):
            clusters.append(MatterCluster(
                cluster_id=ClusterType.ON_OFF,
                name="OnOff",
                attributes={"onOff": False},
                supported_commands=["On", "Off", "Toggle"],
            ))
        
        if device_type in (
            MatterDeviceType.DIMMABLE_LIGHT,
            MatterDeviceType.COLOR_TEMP_LIGHT,
            MatterDeviceType.EXTENDED_COLOR_LIGHT,
            MatterDeviceType.DIMMABLE_PLUG,
        ):
            clusters.append(MatterCluster(
                cluster_id=ClusterType.LEVEL_CONTROL,
                name="LevelControl",
                attributes={"currentLevel": 254},
                supported_commands=["MoveToLevel", "Move", "Step", "Stop"],
            ))
        
        if device_type in (
            MatterDeviceType.COLOR_TEMP_LIGHT,
            MatterDeviceType.EXTENDED_COLOR_LIGHT,
        ):
            clusters.append(MatterCluster(
                cluster_id=ClusterType.COLOR_CONTROL,
                name="ColorControl",
                attributes={"colorTemperatureMireds": 370, "currentHue": 0, "currentSaturation": 0},
                supported_commands=["MoveToColorTemperature", "MoveToHueAndSaturation", "MoveToColor"],
            ))
        
        if device_type == MatterDeviceType.DOOR_LOCK:
            clusters.append(MatterCluster(
                cluster_id=ClusterType.DOOR_LOCK,
                name="DoorLock",
                attributes={"lockState": 1, "doorState": 1},  # Locked, Closed
                supported_commands=["LockDoor", "UnlockDoor"],
            ))
        
        if device_type == MatterDeviceType.THERMOSTAT:
            clusters.append(MatterCluster(
                cluster_id=ClusterType.THERMOSTAT,
                name="Thermostat",
                attributes={
                    "localTemperature": 2200,  # 22.00°C
                    "occupiedCoolingSetpoint": 2400,
                    "occupiedHeatingSetpoint": 2000,
                    "systemMode": 1,  # Auto
                },
                supported_commands=["SetpointRaiseLower"],
            ))
        
        if device_type == MatterDeviceType.TEMPERATURE_SENSOR:
            clusters.append(MatterCluster(
                cluster_id=ClusterType.TEMPERATURE_MEASUREMENT,
                name="TemperatureMeasurement",
                attributes={"measuredValue": 2200},  # 22.00°C
                supported_commands=[],
            ))
        
        if device_type == MatterDeviceType.OCCUPANCY_SENSOR:
            clusters.append(MatterCluster(
                cluster_id=ClusterType.OCCUPANCY_SENSING,
                name="OccupancySensing",
                attributes={"occupancy": 0},
                supported_commands=[],
            ))
        
        if device_type == MatterDeviceType.CONTACT_SENSOR:
            clusters.append(MatterCluster(
                cluster_id=ClusterType.BOOLEAN_STATE,
                name="BooleanState",
                attributes={"stateValue": False},  # Closed
                supported_commands=[],
            ))
        
        device = MatterDevice(
            node_id=node_id,
            vendor_id=0xFFFF,
            product_id=0x0001,
            vendor_name="Mock Vendor",
            product_name=f"Mock {device_type.name}",
            serial_number=f"MOCK{node_id:08d}",
            firmware_version="0.0.1-mock",
            label=label,
            location=location,
            status=DeviceStatus.ONLINE,
            last_seen=time.time(),
            endpoints=[
                MatterEndpoint(
                    endpoint_id=1,
                    device_type=device_type,
                    clusters=clusters,
                ),
            ],
        )
        
        self._devices[device.node_id] = device
        self._save_devices()
        
        logger.info(f"Added mock device: {device.display_name} ({device_type.name})")
        
        return device


class CommissioningError(Exception):
    """Raised when device commissioning fails."""
    pass


# Convenience function for quick discovery
async def discover_matter_devices(timeout: float = 30.0) -> List[MatterDevice]:
    """
    Quick discovery of already-commissioned Matter devices.
    
    For full control, use the MatterDiscovery class.
    """
    discovery = MatterDiscovery()
    return discovery.get_all_devices()
