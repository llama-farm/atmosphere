"""
Atmosphere Matter Integration.

Provides integration with Matter/Thread smart home devices,
exposing them as Atmosphere capabilities in the mesh.

Architecture:
    Matter Device → Discovery → Mapping → Capability → Mesh

Key Components:
- models: Data models for Matter devices, endpoints, clusters
- discovery: mDNS discovery and device commissioning
- mapping: Device → Capability mapping with tools and triggers
- bridge: WebSocket client for matter.js Node.js bridge
- cli: CLI commands for device management

Example Usage:
    from atmosphere.integrations.matter import (
        MatterDiscovery,
        DeviceMapper,
        MatterBridge,
    )
    
    # Discover and map devices
    discovery = MatterDiscovery()
    await discovery.start()
    
    devices = discovery.get_all_devices()
    
    mapper = DeviceMapper()
    for device in devices:
        capabilities = mapper.device_to_capabilities(device)
        for cap in capabilities:
            await registry.register(cap)

See also:
- ~/clawd/projects/atmosphere/design/MATTER_INTEGRATION.md
- ~/clawd/projects/atmosphere/design/reviews/REVIEW_MATTER_INTEGRATION.md
"""

from .models import (
    # Enums
    MatterDeviceType,
    ClusterType,
    DeviceStatus,
    
    # Device models
    MatterDevice,
    MatterEndpoint,
    MatterCluster,
    CommissionableDevice,
    MatterCommand,
    MatterCommandResult,
)

from .discovery import (
    MatterDiscovery,
    DiscoveryConfig,
    CommissioningError,
    discover_matter_devices,
)

from .mapping import (
    # Mapping types
    CapabilityMapping,
    ToolDefinition,
    TriggerDefinition,
    
    # Mapping tables
    MATTER_TO_ATMOSPHERE,
    TOOL_DEFINITIONS,
    TRIGGER_DEFINITIONS,
    
    # Mapper class
    DeviceMapper,
    
    # Utilities
    get_tool_metadata,
)

from .bridge import (
    MatterBridge,
    MatterBridgeManager,
    BridgeConfig,
    BridgeState,
    JsonRpcError,
)

from .cli import (
    matter as matter_cli,
    register_cli,
)


__all__ = [
    # Models - Enums
    "MatterDeviceType",
    "ClusterType",
    "DeviceStatus",
    
    # Models - Classes
    "MatterDevice",
    "MatterEndpoint",
    "MatterCluster",
    "CommissionableDevice",
    "MatterCommand",
    "MatterCommandResult",
    
    # Discovery
    "MatterDiscovery",
    "DiscoveryConfig",
    "CommissioningError",
    "discover_matter_devices",
    
    # Mapping
    "CapabilityMapping",
    "ToolDefinition",
    "TriggerDefinition",
    "MATTER_TO_ATMOSPHERE",
    "TOOL_DEFINITIONS",
    "TRIGGER_DEFINITIONS",
    "DeviceMapper",
    "get_tool_metadata",
    
    # Bridge
    "MatterBridge",
    "MatterBridgeManager",
    "BridgeConfig",
    "BridgeState",
    "JsonRpcError",
    
    # CLI
    "matter_cli",
    "register_cli",
]


__version__ = "0.1.0"
