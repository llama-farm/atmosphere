"""
Matter device models and data structures.

Defines the core data types for Matter device representation.
"""

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Dict, Any, List, Optional


class MatterDeviceType(IntEnum):
    """
    Matter device type IDs from the Matter specification.
    
    See: Matter Application Cluster Specification, Section 7.4
    """
    # Lighting
    ON_OFF_LIGHT = 0x0100
    DIMMABLE_LIGHT = 0x0101
    COLOR_TEMP_LIGHT = 0x010C
    EXTENDED_COLOR_LIGHT = 0x010D
    
    # Plugs & Outlets
    ON_OFF_PLUG = 0x010A
    DIMMABLE_PLUG = 0x010B
    
    # Switches
    ON_OFF_SWITCH = 0x0103
    DIMMER_SWITCH = 0x0104
    COLOR_DIMMER_SWITCH = 0x0105
    
    # Sensors
    CONTACT_SENSOR = 0x0015
    OCCUPANCY_SENSOR = 0x0107
    LIGHT_SENSOR = 0x0106
    TEMPERATURE_SENSOR = 0x0302
    HUMIDITY_SENSOR = 0x0307
    PRESSURE_SENSOR = 0x0305
    FLOW_SENSOR = 0x0306
    
    # Security
    DOOR_LOCK = 0x000A
    DOOR_LOCK_CONTROLLER = 0x000B
    
    # HVAC
    THERMOSTAT = 0x0301
    FAN = 0x002B
    AIR_PURIFIER = 0x002D
    AIR_QUALITY_SENSOR = 0x002C
    
    # Covers
    WINDOW_COVERING = 0x0202
    WINDOW_COVERING_CONTROLLER = 0x0203
    
    # Appliances
    ROBOT_VACUUM = 0x0074
    DISHWASHER = 0x0075
    LAUNDRY_WASHER = 0x0073
    REFRIGERATOR = 0x0070
    ROOM_AIR_CONDITIONER = 0x0072
    
    # Media
    BASIC_VIDEO_PLAYER = 0x0028
    CASTING_VIDEO_PLAYER = 0x0023
    SPEAKER = 0x0022
    CONTENT_APP = 0x0024
    
    # Bridges
    BRIDGE = 0x000E
    AGGREGATOR = 0x000F


class ClusterType(IntEnum):
    """Matter cluster IDs."""
    # General
    IDENTIFY = 0x0003
    GROUPS = 0x0004
    SCENES = 0x0005
    
    # On/Off & Level
    ON_OFF = 0x0006
    LEVEL_CONTROL = 0x0008
    
    # Color
    COLOR_CONTROL = 0x0300
    
    # Locks
    DOOR_LOCK = 0x0101
    
    # HVAC
    THERMOSTAT = 0x0201
    FAN_CONTROL = 0x0202
    
    # Covers
    WINDOW_COVERING = 0x0102
    
    # Measurement
    TEMPERATURE_MEASUREMENT = 0x0402
    RELATIVE_HUMIDITY_MEASUREMENT = 0x0405
    OCCUPANCY_SENSING = 0x0406
    BOOLEAN_STATE = 0x0045
    ILLUMINANCE_MEASUREMENT = 0x0400
    PRESSURE_MEASUREMENT = 0x0403
    
    # Energy
    ELECTRICAL_MEASUREMENT = 0x0B04
    POWER_SOURCE = 0x002F


class DeviceStatus(str, Enum):
    """Device online status."""
    ONLINE = "online"
    OFFLINE = "offline"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


@dataclass
class MatterCluster:
    """A Matter cluster on an endpoint."""
    cluster_id: ClusterType
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    supported_commands: List[str] = field(default_factory=list)


@dataclass
class MatterEndpoint:
    """A Matter endpoint on a device."""
    endpoint_id: int
    device_type: MatterDeviceType
    clusters: List[MatterCluster] = field(default_factory=list)
    
    def get_cluster(self, cluster_id: ClusterType) -> Optional[MatterCluster]:
        """Get a cluster by ID."""
        for cluster in self.clusters:
            if cluster.cluster_id == cluster_id:
                return cluster
        return None
    
    def has_cluster(self, cluster_id: ClusterType) -> bool:
        """Check if endpoint has a cluster."""
        return self.get_cluster(cluster_id) is not None


@dataclass
class MatterDevice:
    """
    Represents a commissioned Matter device.
    
    A device has one or more endpoints, each with device types and clusters.
    """
    node_id: int
    vendor_id: int
    product_id: int
    vendor_name: str
    product_name: str
    serial_number: Optional[str]
    firmware_version: str
    endpoints: List[MatterEndpoint] = field(default_factory=list)
    label: Optional[str] = None  # User-assigned friendly name
    location: Optional[str] = None  # Room/area
    status: DeviceStatus = DeviceStatus.UNKNOWN
    last_seen: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def unique_id(self) -> str:
        """Generate unique ID for the device."""
        return f"matter_{self.node_id}"
    
    @property
    def display_name(self) -> str:
        """Get display name (label or product name)."""
        return self.label or self.product_name or f"Matter Device {self.node_id}"
    
    @property
    def primary_endpoint(self) -> Optional[MatterEndpoint]:
        """Get primary (non-root) endpoint."""
        for ep in self.endpoints:
            if ep.endpoint_id > 0:  # Endpoint 0 is root
                return ep
        return None
    
    @property
    def primary_device_type(self) -> Optional[MatterDeviceType]:
        """Get primary device type."""
        ep = self.primary_endpoint
        return ep.device_type if ep else None
    
    def get_endpoint(self, endpoint_id: int) -> Optional[MatterEndpoint]:
        """Get an endpoint by ID."""
        for ep in self.endpoints:
            if ep.endpoint_id == endpoint_id:
                return ep
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "node_id": self.node_id,
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "vendor_name": self.vendor_name,
            "product_name": self.product_name,
            "serial_number": self.serial_number,
            "firmware_version": self.firmware_version,
            "label": self.label,
            "location": self.location,
            "status": self.status.value,
            "last_seen": self.last_seen,
            "metadata": self.metadata,
            "endpoints": [
                {
                    "endpoint_id": ep.endpoint_id,
                    "device_type": ep.device_type.value,
                    "clusters": [
                        {
                            "cluster_id": c.cluster_id.value,
                            "name": c.name,
                            "attributes": c.attributes,
                            "supported_commands": c.supported_commands,
                        }
                        for c in ep.clusters
                    ],
                }
                for ep in self.endpoints
            ],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MatterDevice":
        """Deserialize from dictionary."""
        endpoints = []
        for ep_data in data.get("endpoints", []):
            clusters = []
            for c_data in ep_data.get("clusters", []):
                clusters.append(MatterCluster(
                    cluster_id=ClusterType(c_data["cluster_id"]),
                    name=c_data["name"],
                    attributes=c_data.get("attributes", {}),
                    supported_commands=c_data.get("supported_commands", []),
                ))
            endpoints.append(MatterEndpoint(
                endpoint_id=ep_data["endpoint_id"],
                device_type=MatterDeviceType(ep_data["device_type"]),
                clusters=clusters,
            ))
        
        return cls(
            node_id=data["node_id"],
            vendor_id=data["vendor_id"],
            product_id=data["product_id"],
            vendor_name=data["vendor_name"],
            product_name=data["product_name"],
            serial_number=data.get("serial_number"),
            firmware_version=data["firmware_version"],
            endpoints=endpoints,
            label=data.get("label"),
            location=data.get("location"),
            status=DeviceStatus(data.get("status", "unknown")),
            last_seen=data.get("last_seen", 0.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CommissionableDevice:
    """
    A device discovered via mDNS that can be commissioned.
    
    Not yet part of our Matter fabric.
    """
    discriminator: int
    vendor_id: int
    product_id: int
    device_type: Optional[MatterDeviceType]
    instance_name: str
    host: str
    port: int
    txt_records: Dict[str, str] = field(default_factory=dict)
    
    @property
    def pairing_hint(self) -> Optional[str]:
        """Get pairing hint from TXT records."""
        return self.txt_records.get("PH")
    
    @property
    def pairing_instruction(self) -> Optional[str]:
        """Get pairing instruction from TXT records."""
        return self.txt_records.get("PI")


@dataclass
class MatterCommand:
    """A command to execute on a Matter device."""
    node_id: int
    endpoint_id: int
    cluster_id: ClusterType
    command: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MatterCommandResult:
    """Result of a Matter command execution."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[int] = None
