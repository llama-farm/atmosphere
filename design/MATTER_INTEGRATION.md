# Matter Integration Design

**Version:** 1.0  
**Status:** Draft  
**Last Updated:** 2025-02-03

## Overview

Matter is the universal smart home protocol developed by the Connectivity Standards Alliance (CSA). By integrating Matter, Atmosphere gains access to every Matter-compatible smart device through a single, standardized interface—no per-brand adapter work required.

### Why Matter?

| Before Matter | With Matter |
|---------------|-------------|
| Each brand needs custom integration | One protocol covers all devices |
| Proprietary APIs, changing endpoints | Stable, spec-defined clusters |
| Cloud-dependent, latency-prone | Fully local, encrypted, fast |
| Vendor lock-in | Multi-admin, multi-ecosystem |
| Custom discovery per device type | Standard commissioning flow |

**The Value Proposition:** Adding Matter support to Atmosphere means every Matter-certified light, lock, thermostat, sensor, and appliance becomes a mesh capability automatically. As the Matter ecosystem grows (expected to be 100M+ devices by 2027), Atmosphere's reach grows with it.

---

## Matter Basics

### What is Matter?

Matter is:
- **Local-first**: Device-to-device communication, no cloud required
- **Secure**: End-to-end encryption, device attestation
- **Multi-admin**: Devices can be controlled by multiple ecosystems simultaneously
- **Standard**: Defined by CSA with participation from Apple, Google, Amazon, Samsung, etc.

### Protocol Stack

```
┌─────────────────────────────────────────────────┐
│                 Application Layer                │
│     (Device Types, Clusters, Attributes)        │
├─────────────────────────────────────────────────┤
│               Interaction Model                  │
│    (Read/Write/Subscribe/Invoke Commands)       │
├─────────────────────────────────────────────────┤
│                 Security Layer                   │
│    (CASE/PASE, Certificates, Encryption)        │
├─────────────────────────────────────────────────┤
│                Transport Layer                   │
│           (IPv6: Wi-Fi, Thread, Ethernet)       │
└─────────────────────────────────────────────────┘
```

### Commissioning Flow

Commissioning is how a new device joins a Matter fabric:

```
┌──────────────┐                              ┌──────────────┐
│    Device    │                              │  Controller  │
│  (New Light) │                              │ (Atmosphere) │
└──────┬───────┘                              └──────┬───────┘
       │                                              │
       │◄─── 1. Scan QR Code / Manual Code ──────────│
       │     (Contains setup PIN + discriminator)    │
       │                                              │
       │──── 2. PASE (Passcode Auth) ───────────────►│
       │     (Establish secure channel with PIN)     │
       │                                              │
       │◄─── 3. Attestation Check ──────────────────│
       │     (Verify device is genuine Matter)       │
       │                                              │
       │──── 4. NOC (Operational Creds) ───────────►│
       │     (Device gets fabric certificate)        │
       │                                              │
       │◄─── 5. ACL (Access Control) ───────────────│
       │     (Configure who can control device)      │
       │                                              │
       │──── 6. CASE (Certificate Auth) ───────────►│
       │     (Future sessions use certificates)      │
       │                                              │
       ▼                                              ▼
   [Commissioned]                             [Device Paired]
```

**Commissioning Data:**
- **QR Code**: `MT:Y.K9042C00KA0648G00` → Contains vendor ID, product ID, discriminator, PIN
- **Manual Code**: `749-701-1233-65521327694` → Fallback for no camera

### Device Types

Matter defines standard device types that determine what a device can do:

| Device Type | ID | Primary Clusters | Description |
|-------------|------|------------------|-------------|
| On/Off Light | 0x0100 | OnOff | Simple on/off control |
| Dimmable Light | 0x0101 | OnOff, LevelControl | Brightness control |
| Color Temperature Light | 0x010C | OnOff, LevelControl, ColorControl | Warm/cool white |
| Extended Color Light | 0x010D | OnOff, LevelControl, ColorControl | Full RGB/HSV |
| On/Off Plug-in Unit | 0x010A | OnOff | Smart plug |
| Dimmable Plug-in Unit | 0x010B | OnOff, LevelControl | Dimmable outlet |
| Door Lock | 0x000A | DoorLock | Lock/unlock, PIN codes |
| Thermostat | 0x0301 | Thermostat | HVAC control |
| Temperature Sensor | 0x0302 | TemperatureMeasurement | Temperature reading |
| Humidity Sensor | 0x0307 | RelativeHumidityMeasurement | Humidity reading |
| Occupancy Sensor | 0x0107 | OccupancySensing | Motion detection |
| Contact Sensor | 0x0015 | BooleanState | Door/window open/close |
| Window Covering | 0x0202 | WindowCovering | Blinds, shades |
| Fan | 0x002B | FanControl | Fan speed control |
| Air Purifier | 0x002D | FanControl, HepaFilterMonitoring | Air quality |
| Robot Vacuum | 0x0074 | RvcRunMode, RvcOperationalState | Vacuum control |

### Clusters (The Building Blocks)

Clusters are sets of related attributes and commands:

```
┌──────────────────────────────────────────────────────────────────┐
│                        OnOff Cluster (0x0006)                    │
├──────────────────────────────────────────────────────────────────┤
│  Attributes:                                                     │
│    • OnOff (bool) - Current state                               │
│    • GlobalSceneControl (bool)                                  │
│    • OnTime (uint16) - Auto-off timer                           │
│    • OffWaitTime (uint16) - Delay before off                    │
├──────────────────────────────────────────────────────────────────┤
│  Commands:                                                       │
│    • Off() - Turn off                                           │
│    • On() - Turn on                                             │
│    • Toggle() - Flip state                                      │
│    • OnWithTimedOff(on_time, off_wait_time)                     │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     LevelControl Cluster (0x0008)                │
├──────────────────────────────────────────────────────────────────┤
│  Attributes:                                                     │
│    • CurrentLevel (uint8) - 0-254                               │
│    • MinLevel, MaxLevel (uint8)                                 │
│    • OnOffTransitionTime (uint16)                               │
├──────────────────────────────────────────────────────────────────┤
│  Commands:                                                       │
│    • MoveToLevel(level, transition_time)                        │
│    • Move(mode, rate) - Continuous dimming                      │
│    • Step(mode, step_size, transition_time)                     │
│    • Stop() - Stop level change                                 │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     ColorControl Cluster (0x0300)                │
├──────────────────────────────────────────────────────────────────┤
│  Attributes:                                                     │
│    • CurrentHue, CurrentSaturation (uint8)                      │
│    • CurrentX, CurrentY (uint16) - CIE xy                       │
│    • ColorTemperatureMireds (uint16) - 147-500 (6800K-2000K)   │
│    • ColorMode (enum) - HS, XY, or ColorTemp                    │
├──────────────────────────────────────────────────────────────────┤
│  Commands:                                                       │
│    • MoveToHue(hue, direction, transition_time)                 │
│    • MoveToSaturation(saturation, transition_time)              │
│    • MoveToHueAndSaturation(hue, sat, time)                     │
│    • MoveToColorTemperature(mireds, transition_time)            │
│    • MoveToColor(x, y, transition_time) - CIE xy               │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                       DoorLock Cluster (0x0101)                  │
├──────────────────────────────────────────────────────────────────┤
│  Attributes:                                                     │
│    • LockState (enum) - NotFullyLocked, Locked, Unlocked        │
│    • LockType (enum) - Deadbolt, Latch, etc.                    │
│    • ActuatorEnabled (bool)                                      │
│    • DoorState (enum) - Open, Closed, etc.                      │
├──────────────────────────────────────────────────────────────────┤
│  Commands:                                                       │
│    • LockDoor(pin_code?)                                        │
│    • UnlockDoor(pin_code?)                                      │
│    • SetCredential(type, index, data)                           │
│    • ClearCredential(type, index)                               │
├──────────────────────────────────────────────────────────────────┤
│  Events:                                                         │
│    • DoorLockAlarm - Tamper, forced entry, etc.                 │
│    • LockOperation - Lock/unlock with user info                 │
│    • DoorStateChange - Door opened/closed                       │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                      Thermostat Cluster (0x0201)                 │
├──────────────────────────────────────────────────────────────────┤
│  Attributes:                                                     │
│    • LocalTemperature (int16) - Current temp in 0.01°C         │
│    • OccupiedCoolingSetpoint (int16)                            │
│    • OccupiedHeatingSetpoint (int16)                            │
│    • SystemMode (enum) - Off, Heat, Cool, Auto                  │
│    • RunningState (bitmap) - Heat, Cool, Fan stages             │
├──────────────────────────────────────────────────────────────────┤
│  Commands:                                                       │
│    • SetpointRaiseLower(mode, amount)                           │
│    • SetWeeklySchedule(days, transitions)                       │
│    • ClearWeeklySchedule()                                      │
└──────────────────────────────────────────────────────────────────┘
```

### Subscriptions (Real-time Updates)

Matter supports subscribing to attribute changes:

```python
# Subscribe to light state changes
subscription = await device.subscribe(
    attributes=[
        (endpoint=1, cluster=OnOff, attribute="OnOff"),
        (endpoint=1, cluster=LevelControl, attribute="CurrentLevel"),
    ],
    min_interval_seconds=1,
    max_interval_seconds=60,
)

# Callback fires on changes
def on_update(path, old_value, new_value):
    print(f"{path} changed: {old_value} → {new_value}")
```

---

## Architecture

### High-Level Integration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             ATMOSPHERE NODE                                  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         INTENT ROUTER                                │   │
│  │                                                                      │   │
│  │   "turn on kitchen lights" → Match → Route to Matter Adapter        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       MATTER ADAPTER                                 │   │
│  │                                                                      │   │
│  │   • Registers device capabilities to mesh                           │   │
│  │   • Maps tool calls to Matter commands                              │   │
│  │   • Converts Matter events to mesh triggers                         │   │
│  │                                                                      │   │
│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐    │   │
│  │   │  Discovery  │  │   Mapping   │  │  Event/Subscription Mgr │    │   │
│  │   │   Engine    │  │   Engine    │  │                         │    │   │
│  │   └─────────────┘  └─────────────┘  └─────────────────────────┘    │   │
│  │                           │                                          │   │
│  │                           ▼                                          │   │
│  │   ┌─────────────────────────────────────────────────────────────┐   │   │
│  │   │                    MATTER CONTROLLER                         │   │   │
│  │   │                    (matter.js wrapper)                       │   │   │
│  │   └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
└──────────────────────────────────────┼──────────────────────────────────────┘
                                       │
                   ┌───────────────────┼───────────────────┐
                   │                   │                   │
                   ▼                   ▼                   ▼
            ┌──────────┐        ┌──────────┐        ┌──────────┐
            │  Light   │        │   Lock   │        │ Thermo-  │
            │ (Wi-Fi)  │        │ (Thread) │        │  stat    │
            └──────────┘        └──────────┘        └──────────┘
```

### Detailed Flow: Tool Call → Device Command

```
Agent                    Atmosphere                Matter Adapter          Device
  │                          │                          │                     │
  │── "lock front door" ────►│                          │                     │
  │                          │                          │                     │
  │                          │── route to capability ──►│                     │
  │                          │   (iot/lock/front_door)  │                     │
  │                          │                          │                     │
  │                          │                          │── DoorLock.Lock() ─►│
  │                          │                          │   (node 5, ep 1)    │
  │                          │                          │                     │
  │                          │                          │◄─── success ────────│
  │                          │                          │                     │
  │                          │◄─── ToolResult ─────────│                     │
  │                          │   {success: true}        │                     │
  │                          │                          │                     │
  │◄─── "Front door locked" ─│                          │                     │
  │                          │                          │                     │
```

### Detailed Flow: Device Event → Mesh Trigger

```
Device               Matter Adapter              Atmosphere              Agent
  │                       │                          │                     │
  │── Motion detected ───►│                          │                     │
  │   (OccupancySensing)  │                          │                     │
  │                       │                          │                     │
  │                       │── emit trigger ─────────►│                     │
  │                       │   {type: "motion",       │                     │
  │                       │    device: "hallway",    │                     │
  │                       │    value: true}          │                     │
  │                       │                          │                     │
  │                       │                          │── wake agent? ─────►│
  │                       │                          │   (if configured)   │
  │                       │                          │                     │
  │                       │                          │◄─ "turn on lights" ─│
  │                       │                          │                     │
```

---

## Device → Capability Mapping

### Mapping Strategy

Each Matter device becomes one or more Atmosphere capabilities:

```python
# Mapping rule
def matter_device_to_capabilities(device: MatterDevice) -> List[Capability]:
    capabilities = []
    
    # Base capability from device type
    base_cap = Capability(
        id=f"matter:{device.node_id}:{device.device_type.name.lower()}",
        type=DEVICE_TYPE_TO_CAPABILITY[device.device_type],
        name=device.label or f"Matter {device.device_type.name}",
        description=f"{device.vendor_name} {device.product_name}",
    )
    capabilities.append(base_cap)
    
    # Additional capabilities from clusters
    for endpoint in device.endpoints:
        for cluster in endpoint.clusters:
            if cluster.id in CLUSTER_TO_CAPABILITY:
                cap = CLUSTER_TO_CAPABILITY[cluster.id](device, endpoint, cluster)
                capabilities.append(cap)
    
    return capabilities
```

### Complete Mapping Table

| Matter Device Type | Atmosphere Capability | Triggers | Tools |
|-------------------|----------------------|----------|-------|
| **Lighting** ||||
| On/Off Light | `iot/light` | - | `on`, `off`, `toggle` |
| Dimmable Light | `iot/light` | - | `on`, `off`, `set_brightness` |
| Color Temp Light | `iot/light` | - | `on`, `off`, `set_brightness`, `set_color_temp` |
| Extended Color Light | `iot/light` | - | `on`, `off`, `set_brightness`, `set_color`, `set_color_temp` |
| **Plugs & Outlets** ||||
| On/Off Plug | `iot/outlet` | - | `on`, `off`, `toggle` |
| Dimmable Plug | `iot/outlet` | - | `on`, `off`, `set_level` |
| **Security** ||||
| Door Lock | `iot/lock` | `locked`, `unlocked`, `door_opened`, `door_closed`, `tamper` | `lock`, `unlock`, `get_state` |
| Contact Sensor | `sensor/contact` | `opened`, `closed` | `get_state` |
| Occupancy Sensor | `sensor/motion` | `motion_detected`, `motion_cleared` | `get_state` |
| **Climate** ||||
| Thermostat | `iot/hvac` | `temp_reached`, `mode_changed` | `set_temperature`, `get_temperature`, `set_mode`, `get_mode` |
| Temperature Sensor | `sensor/temperature` | `threshold_crossed` | `get_reading` |
| Humidity Sensor | `sensor/humidity` | `threshold_crossed` | `get_reading` |
| Fan | `iot/fan` | - | `on`, `off`, `set_speed`, `set_direction` |
| Air Purifier | `iot/air_purifier` | `filter_change_needed` | `on`, `off`, `set_speed`, `get_air_quality` |
| **Covers** ||||
| Window Covering | `iot/blinds` | `opened`, `closed`, `position_changed` | `open`, `close`, `set_position`, `stop` |
| **Appliances** ||||
| Robot Vacuum | `iot/vacuum` | `cleaning_complete`, `error`, `stuck` | `start`, `stop`, `pause`, `return_home`, `get_status` |
| Dishwasher | `iot/dishwasher` | `cycle_complete`, `error` | `start`, `pause`, `get_status` |
| Laundry Washer | `iot/washer` | `cycle_complete`, `error` | `start`, `pause`, `get_status` |

### Tool Schema Examples

```python
# Light control tools
LIGHT_TOOLS = [
    Tool(
        name="light_on",
        description="Turn on a light",
        parameters={
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "Device identifier or name"},
                "brightness": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Brightness percentage (optional)"},
                "transition_ms": {"type": "integer", "description": "Transition time in milliseconds (optional)"},
            },
            "required": ["device_id"]
        },
        capability_id="iot/light",
    ),
    Tool(
        name="light_set_color",
        description="Set light color using RGB, HSV, or color temperature",
        parameters={
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "color": {
                    "oneOf": [
                        {"type": "object", "properties": {"r": {"type": "integer"}, "g": {"type": "integer"}, "b": {"type": "integer"}}},
                        {"type": "object", "properties": {"h": {"type": "integer"}, "s": {"type": "integer"}, "v": {"type": "integer"}}},
                        {"type": "object", "properties": {"kelvin": {"type": "integer", "minimum": 2000, "maximum": 6500}}},
                        {"type": "string", "description": "Color name like 'warm white', 'red', 'ocean blue'"}
                    ]
                },
                "transition_ms": {"type": "integer"},
            },
            "required": ["device_id", "color"]
        },
        capability_id="iot/light",
    ),
]

# Lock control tools
LOCK_TOOLS = [
    Tool(
        name="lock_door",
        description="Lock a door",
        parameters={
            "type": "object", 
            "properties": {
                "device_id": {"type": "string"},
                "pin_code": {"type": "string", "description": "Optional PIN for audit trail"},
            },
            "required": ["device_id"]
        },
        capability_id="iot/lock",
    ),
    Tool(
        name="unlock_door",
        description="Unlock a door - requires explicit confirmation for security",
        parameters={
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "pin_code": {"type": "string", "description": "PIN code (may be required by device)"},
            },
            "required": ["device_id"]
        },
        capability_id="iot/lock",
        metadata={"requires_confirmation": True, "security_sensitive": True},
    ),
]

# Thermostat tools
HVAC_TOOLS = [
    Tool(
        name="set_temperature",
        description="Set thermostat target temperature",
        parameters={
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "temperature": {"type": "number", "description": "Target temperature"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"], "default": "fahrenheit"},
                "mode": {"type": "string", "enum": ["heat", "cool", "auto"], "description": "HVAC mode (optional)"},
            },
            "required": ["device_id", "temperature"]
        },
        capability_id="iot/hvac",
    ),
]
```

---

## Implementation Options

### Option 1: matter.js (TypeScript/JavaScript) ⭐ RECOMMENDED

**Overview:**
A complete TypeScript implementation of the Matter protocol, actively maintained and well-documented.

**Pros:**
- ✅ Complete Matter stack in pure TypeScript (no native dependencies for core)
- ✅ Officially certified software component
- ✅ Excellent documentation and examples
- ✅ Active development, tracks latest Matter spec (currently 1.4)
- ✅ Tested with all major ecosystems (Apple, Google, Amazon, Samsung, Home Assistant)
- ✅ Supports both controller and device roles
- ✅ BLE commissioning support via `@matter/nodejs-ble`
- ✅ Shell CLI for testing (`@matter/nodejs-shell`)
- ✅ Node.js 20+ support

**Cons:**
- ⚠️ Requires Node.js (not pure Python)
- ⚠️ Larger memory footprint than native implementations

**Integration Approach:**

```
┌─────────────────────────────────────────────────────────────────────┐
│                       ATMOSPHERE (Python)                            │
│                                                                      │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │                     Matter Adapter                            │  │
│   │                     (Python wrapper)                          │  │
│   │                                                               │  │
│   │   • Manages matter.js subprocess                              │  │
│   │   • Communicates via WebSocket/JSON-RPC                       │  │
│   │   • Translates capabilities to/from mesh                      │  │
│   └───────────────────────────┬──────────────────────────────────┘  │
│                               │ WebSocket                            │
└───────────────────────────────┼──────────────────────────────────────┘
                                │
┌───────────────────────────────┼──────────────────────────────────────┐
│                               ▼                                       │
│   ┌──────────────────────────────────────────────────────────────┐   │
│   │              matter.js Controller Bridge                      │   │
│   │              (Node.js subprocess)                             │   │
│   │                                                               │   │
│   │   • WebSocket server for Python communication                 │   │
│   │   • Matter commissioning & control                            │   │
│   │   • Event forwarding                                          │   │
│   └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
│                        NODE.JS PROCESS                                │
└───────────────────────────────────────────────────────────────────────┘
```

### Option 2: python-matter-server (Home Assistant)

**Overview:**
The official Matter controller used by Home Assistant, wrapping the CHIP SDK.

**Pros:**
- ✅ Officially CSA-certified controller
- ✅ Python-native client library
- ✅ Production-tested in Home Assistant
- ✅ WebSocket API for communication

**Cons:**
- ⚠️ **Maintenance mode** — being rewritten on matter.js
- ⚠️ Heavy native dependencies (CHIP SDK)
- ⚠️ Complex build process
- ⚠️ x86/ARM binary dependencies

**Why Not Recommended:**
The project maintainers have explicitly stated they're rewriting on top of matter.js. Investing in python-matter-server would mean technical debt.

### Option 3: chip-tool (Reference Implementation)

**Overview:**
The official C++ reference implementation from the Matter SDK.

**Pros:**
- ✅ Most complete/accurate implementation
- ✅ Direct from CSA

**Cons:**
- ❌ C++, not practical for Atmosphere integration
- ❌ CLI-only, no library interface
- ❌ Very complex build environment
- ❌ Intended for testing, not production apps

**Why Not Recommended:**
Not designed for embedding. Would require significant wrapper work and C++ expertise.

### Recommendation: matter.js

**Choose matter.js because:**

1. **Best long-term investment** — Even Home Assistant is moving to it
2. **Clean architecture** — TypeScript provides type safety and good tooling
3. **Easy integration** — WebSocket/JSON-RPC bridge is straightforward
4. **Active community** — Regular updates, responsive maintainers
5. **Proven compatibility** — Tested with all major ecosystems

**Implementation Cost:**
- Build Node.js bridge process: 2-3 days
- Python adapter wrapper: 1-2 days  
- Device mapping layer: 2-3 days
- Testing & hardening: 2-3 days
- **Total: ~2 weeks**

---

## Code Structure

```
atmosphere/integrations/matter/
├── __init__.py                 # Package exports
├── adapter.py                  # MatterAdapter (AtmosphereAdapter implementation)
├── bridge/
│   ├── __init__.py
│   ├── client.py               # WebSocket client for Node.js bridge
│   ├── protocol.py             # JSON-RPC message definitions
│   └── manager.py              # Bridge process lifecycle management
├── discovery/
│   ├── __init__.py
│   ├── scanner.py              # Device discovery via mDNS
│   └── commissioning.py        # Commissioning flow handling
├── mapping/
│   ├── __init__.py
│   ├── devices.py              # Device type → capability mapping
│   ├── clusters.py             # Cluster → tool mapping
│   └── events.py               # Matter events → mesh triggers
├── controller/
│   ├── __init__.py
│   ├── commands.py             # High-level device control commands
│   ├── subscriptions.py        # Attribute subscription management
│   └── state.py                # Device state tracking
└── node_bridge/                # Node.js bridge (separate npm package)
    ├── package.json
    ├── tsconfig.json
    ├── src/
    │   ├── index.ts            # Entry point
    │   ├── server.ts           # WebSocket server
    │   ├── controller.ts       # Matter controller wrapper
    │   ├── commissioning.ts    # Commissioning handlers
    │   └── handlers.ts         # RPC method handlers
    └── dist/                   # Compiled JavaScript
```

### Key Classes

```python
# atmosphere/integrations/matter/adapter.py

from atmosphere.adapters.base import AtmosphereAdapter, Capability, Tool, ToolResult
from .bridge.client import MatterBridgeClient
from .mapping.devices import DeviceMapper

class MatterAdapter(AtmosphereAdapter):
    """
    Matter smart home integration for Atmosphere.
    
    Manages a matter.js Node.js subprocess and translates between
    Matter devices and Atmosphere capabilities.
    """
    
    adapter_id = "matter"
    adapter_name = "Matter Smart Home"
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._bridge = MatterBridgeClient(
            port=config.get("bridge_port", 5580),
            storage_path=config.get("storage_path", "~/.atmosphere/matter"),
        )
        self._mapper = DeviceMapper()
        self._devices: Dict[int, MatterDevice] = {}  # node_id → device
        self._subscriptions: Dict[str, Subscription] = {}
    
    async def discover(self) -> bool:
        """Check if Matter bridge is available or can be started."""
        return await self._bridge.ping() or await self._bridge.start()
    
    async def connect(self) -> bool:
        """Connect to bridge and enumerate commissioned devices."""
        if not await self._bridge.connect():
            return False
        
        # Get all commissioned devices
        devices = await self._bridge.get_devices()
        
        for device in devices:
            self._devices[device.node_id] = device
            
            # Map to capabilities
            caps = self._mapper.device_to_capabilities(device)
            self._capabilities.extend(caps)
            
            # Map to tools
            tools = self._mapper.device_to_tools(device)
            self._tools.extend(tools)
            
            # Subscribe to state changes
            await self._setup_subscriptions(device)
        
        self._state = AdapterState.CONNECTED
        return True
    
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> ToolResult:
        """Execute a Matter device command."""
        try:
            # Resolve device from params
            device = self._resolve_device(params.get("device_id"))
            if not device:
                return ToolResult(success=False, error="Device not found")
            
            # Map tool to Matter command
            command = self._mapper.tool_to_command(tool_name, device, params)
            
            # Execute via bridge
            result = await self._bridge.execute_command(command)
            
            return ToolResult(
                success=result.success,
                data=result.data,
                error=result.error,
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def commission_device(self, setup_code: str, name: str = None) -> MatterDevice:
        """
        Commission a new Matter device.
        
        Args:
            setup_code: QR code payload or manual pairing code
            name: Optional friendly name for the device
        
        Returns:
            Commissioned device info
        """
        device = await self._bridge.commission(setup_code, name=name)
        
        # Add to local tracking
        self._devices[device.node_id] = device
        
        # Register capabilities
        caps = self._mapper.device_to_capabilities(device)
        self._capabilities.extend(caps)
        
        # Publish to mesh
        await self._publish_capabilities(caps)
        
        return device
```

### Bridge Protocol (JSON-RPC)

```typescript
// node_bridge/src/protocol.ts

interface RpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: any;
}

interface RpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: any;
  error?: { code: number; message: string; data?: any };
}

// Methods
const METHODS = {
  // Lifecycle
  "ping": () => "pong",
  "shutdown": () => void,
  
  // Discovery & Commissioning
  "discover": () => DiscoveredDevice[],
  "commission": (params: {code: string, name?: string}) => CommissionedDevice,
  "getDevices": () => Device[],
  "getDevice": (params: {nodeId: number}) => Device,
  
  // Control
  "executeCommand": (params: {nodeId: number, endpoint: number, cluster: string, command: string, args?: any}) => CommandResult,
  "readAttribute": (params: {nodeId: number, endpoint: number, cluster: string, attribute: string}) => any,
  "writeAttribute": (params: {nodeId: number, endpoint: number, cluster: string, attribute: string, value: any}) => void,
  
  // Subscriptions
  "subscribe": (params: {nodeId: number, paths: AttributePath[]}) => string, // subscription ID
  "unsubscribe": (params: {subscriptionId: string}) => void,
};

// Events (server → client)
interface RpcEvent {
  jsonrpc: "2.0";
  method: "event";
  params: {
    type: "attributeChange" | "deviceEvent" | "deviceOnline" | "deviceOffline";
    nodeId: number;
    data: any;
  };
}
```

---

## Implementation Plan

### Phase 1: Foundation (Week 1)

| Task | Description | Effort |
|------|-------------|--------|
| 1.1 | Set up matter.js Node.js project with dependencies | 0.5 days |
| 1.2 | Implement WebSocket server with JSON-RPC | 1 day |
| 1.3 | Basic controller initialization | 0.5 days |
| 1.4 | Python bridge client | 1 day |
| 1.5 | Process lifecycle management | 0.5 days |
| 1.6 | Basic adapter skeleton | 0.5 days |

**Deliverable:** Can start/stop bridge, verify connectivity

### Phase 2: Device Management (Week 1-2)

| Task | Description | Effort |
|------|-------------|--------|
| 2.1 | Commissioning flow (QR code + manual) | 1 day |
| 2.2 | Device enumeration | 0.5 days |
| 2.3 | Device state tracking | 0.5 days |
| 2.4 | Device → Capability mapping | 1 day |
| 2.5 | Friendly names / device registry | 0.5 days |

**Deliverable:** Can commission devices and see them as capabilities

### Phase 3: Control Layer (Week 2)

| Task | Description | Effort |
|------|-------------|--------|
| 3.1 | OnOff cluster commands | 0.5 days |
| 3.2 | LevelControl commands | 0.5 days |
| 3.3 | ColorControl commands | 0.5 days |
| 3.4 | DoorLock commands | 0.5 days |
| 3.5 | Thermostat commands | 0.5 days |
| 3.6 | Tool schema generation | 0.5 days |
| 3.7 | Tool execution routing | 0.5 days |

**Deliverable:** Can control lights, locks, thermostats via tools

### Phase 4: Events & Triggers (Week 2)

| Task | Description | Effort |
|------|-------------|--------|
| 4.1 | Attribute subscription system | 1 day |
| 4.2 | Event → Trigger mapping | 0.5 days |
| 4.3 | Motion sensor triggers | 0.5 days |
| 4.4 | Contact sensor triggers | 0.5 days |
| 4.5 | Lock event triggers | 0.5 days |

**Deliverable:** Device events flow into mesh as triggers

### Phase 5: Polish & Testing (Week 2)

| Task | Description | Effort |
|------|-------------|--------|
| 5.1 | Error handling & recovery | 0.5 days |
| 5.2 | Connection resilience | 0.5 days |
| 5.3 | Unit tests | 1 day |
| 5.4 | Integration tests with virtual devices | 1 day |
| 5.5 | Documentation | 0.5 days |

**Deliverable:** Production-ready Matter adapter

### Total Effort: ~2 weeks

---

## Security Considerations

### Device Authentication
- Matter uses PKI with per-device certificates
- Devices are attested during commissioning (verified genuine)
- All communication is encrypted (AES-CCM)

### Sensitive Operations
```python
# Mark unlock as security-sensitive
Tool(
    name="unlock_door",
    metadata={
        "requires_confirmation": True,
        "security_sensitive": True,
        "audit_log": True,
    }
)
```

### Secrets Management
- Fabric credentials stored in encrypted storage
- PIN codes never logged
- Operational certificates rotatable

### Multi-Admin
- Atmosphere becomes one admin among potentially many
- Respect existing ACLs
- Don't override user-set restrictions

---

## Testing Strategy

### Virtual Devices (matter.js)
```bash
# Start a virtual light for testing
npx @matter/examples light --name "Test Light" --port 5541
```

### Matter Virtual Device (MVD)
Google provides MVD for testing without hardware:
- Download from Google Home Developer Console
- Supports common device types
- Can simulate events

### Integration Tests
```python
@pytest.mark.asyncio
async def test_light_on_off():
    adapter = MatterAdapter()
    await adapter.connect()
    
    # Find test light
    lights = [c for c in adapter.capabilities if c.type == "iot/light"]
    assert len(lights) > 0
    
    # Turn on
    result = await adapter.execute_tool("light_on", {"device_id": lights[0].id})
    assert result.success
    
    # Verify state
    state = await adapter.execute_tool("light_get_state", {"device_id": lights[0].id})
    assert state.data["on"] == True
```

---

## Future Enhancements

### Thread Border Router Integration
If Atmosphere node has Thread radio:
- Become a Thread border router
- Direct Thread device commissioning
- Lower latency for Thread devices

### Scene/Group Support
- Matter supports scenes (preset configurations)
- Groups for multi-device control
- Expose as high-level capabilities

### Energy Monitoring
- Matter 1.3+ adds energy metering clusters
- Track device power consumption
- Enable energy optimization workflows

### Camera Support
- Matter 1.5 adds camera device types
- Video streaming integration
- Motion detection triggers

---

## Appendix: Cluster Reference

### Commonly Used Clusters

| Cluster | ID | Purpose |
|---------|-----|---------|
| Identify | 0x0003 | Locate device (blink, beep) |
| Groups | 0x0004 | Group membership |
| Scenes | 0x0005 | Scene storage |
| OnOff | 0x0006 | On/off control |
| LevelControl | 0x0008 | Brightness/level |
| ColorControl | 0x0300 | Color management |
| DoorLock | 0x0101 | Lock control |
| WindowCovering | 0x0102 | Blinds/shades |
| Thermostat | 0x0201 | HVAC control |
| FanControl | 0x0202 | Fan speed |
| TemperatureMeasurement | 0x0402 | Temperature sensor |
| RelativeHumidityMeasurement | 0x0405 | Humidity sensor |
| OccupancySensing | 0x0406 | Motion detection |
| BooleanState | 0x0045 | Binary sensor (contact) |

### Full Cluster List
See: [Matter Cluster Specification](https://github.com/project-chip/connectedhomeip/tree/master/src/app/clusters)

---

## References

- [Matter Specification](https://csa-iot.org/developer-resource/specifications-download-request/) (CSA members)
- [matter.js GitHub](https://github.com/matter-js/matter.js)
- [Google Matter Developer Guide](https://developers.home.google.com/matter)
- [Apple HomeKit & Matter](https://developer.apple.com/documentation/homekit)
- [Matter SDK (connectedhomeip)](https://github.com/project-chip/connectedhomeip)
