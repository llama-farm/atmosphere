# Matter Integration

Atmosphere integration for Matter/Thread smart home devices.

## Overview

This module provides:
- **Device Discovery**: mDNS-based discovery of Matter devices
- **Device Mapping**: Automatic conversion of Matter devices to Atmosphere capabilities
- **Command Execution**: Tool calls translated to Matter cluster commands
- **Event Handling**: Matter attribute changes converted to Atmosphere triggers
- **CLI Management**: Commands for device discovery, commissioning, and control

## Current Status: MVP

The MVP implementation includes:
- ✅ Complete device type → capability mapping
- ✅ Full tool and trigger definitions
- ✅ Device registry with persistence
- ✅ Mock device support for testing
- ✅ CLI structure
- ⚠️ **Stubbed**: Real Matter protocol (requires matter.js bridge)
- ⚠️ **Stubbed**: mDNS discovery
- ⚠️ **Stubbed**: Device commissioning

## Quick Start

### List Devices

```bash
atmosphere matter list
```

### Add Mock Device (for testing)

```bash
atmosphere matter add-mock --type dimmable_light --name "Living Room" --location "Living Room"
```

### View Device Status

```bash
atmosphere matter status 1
# or
atmosphere matter status "Living Room"
```

### Show Supported Device Types

```bash
atmosphere matter capabilities
```

## Supported Device Types

| Category | Device Type | Tools | Triggers |
|----------|-------------|-------|----------|
| **Lighting** | ON_OFF_LIGHT | on, off, toggle | state_changed |
| | DIMMABLE_LIGHT | +set_brightness | +brightness_changed |
| | COLOR_TEMP_LIGHT | +set_color_temp | |
| | EXTENDED_COLOR_LIGHT | +set_color | |
| **Plugs** | ON_OFF_PLUG | on, off, toggle | state_changed |
| | DIMMABLE_PLUG | +set_brightness | |
| **Security** | DOOR_LOCK | lock, unlock, get_state | locked, unlocked, tamper |
| | CONTACT_SENSOR | get_state | opened, closed |
| | OCCUPANCY_SENSOR | get_state | motion_detected, motion_cleared |
| **Climate** | THERMOSTAT | set_temp, set_mode, get_state | mode_changed, target_reached |
| | TEMPERATURE_SENSOR | get_reading | threshold_exceeded |
| | FAN | on, off, set_speed | state_changed |
| **Covers** | WINDOW_COVERING | open, close, set_position, stop | position_changed |
| **Appliances** | ROBOT_VACUUM | start, stop, return_home | cleaning_complete, error |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       ATMOSPHERE (Python)                            │
│                                                                      │
│   ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐   │
│   │   CLI Commands  │  │  Device Mapper  │  │   Discovery      │   │
│   └────────┬────────┘  └────────┬────────┘  └────────┬─────────┘   │
│            │                    │                     │             │
│            ▼                    ▼                     ▼             │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │                     Matter Bridge Client                      │  │
│   │                     (WebSocket/JSON-RPC)                      │  │
│   └──────────────────────────────┬───────────────────────────────┘  │
│                                  │                                   │
└──────────────────────────────────┼───────────────────────────────────┘
                                   │ WebSocket
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     matter.js Bridge (Node.js)                        │
│                     [NOT YET IMPLEMENTED]                             │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                   ┌───────────────┼───────────────┐
                   ▼               ▼               ▼
            ┌──────────┐    ┌──────────┐    ┌──────────┐
            │  Light   │    │   Lock   │    │ Thermo-  │
            │ (Wi-Fi)  │    │ (Thread) │    │  stat    │
            └──────────┘    └──────────┘    └──────────┘
```

## Next Steps for Full Implementation

### 1. Create matter.js Node.js Bridge

```bash
mkdir -p node_bridge
cd node_bridge
npm init -y
npm install @matter/main @matter/nodejs ws
```

Create `src/index.ts`:
```typescript
import { MatterServer } from "@matter/main";
import { WebSocketServer } from "ws";

// Start Matter controller
const controller = await MatterServer.create();

// Start WebSocket server for Python communication
const wss = new WebSocketServer({ port: 5580 });

wss.on("connection", (ws) => {
  ws.on("message", async (data) => {
    const request = JSON.parse(data.toString());
    // Handle JSON-RPC requests
    // ... execute Matter commands
    // ... return results
  });
});
```

### 2. Implement Real mDNS Discovery

```python
# discovery.py - Replace stub with real zeroconf
from zeroconf import ServiceBrowser, Zeroconf

class MatterServiceListener:
    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name)
        # Parse Matter TXT records
        # Add to commissionable devices
```

### 3. WebSocket Connection

```python
# bridge.py - Replace stub with real WebSocket
import aiohttp

async def _connect_websocket(self):
    session = aiohttp.ClientSession()
    self._ws = await session.ws_connect(f"ws://localhost:{self.config.port}/rpc")
    self._reader_task = asyncio.create_task(self._read_messages())
```

### 4. Thread Border Router (Future)

For Thread device support:
- Requires Thread-capable hardware (USB dongle or built-in)
- Consider integrating with OpenThread Border Router (OTBR)

## Testing

### With Mock Devices

```bash
# Add various mock devices
atmosphere matter add-mock --type dimmable_light --name "Kitchen Light" --location "Kitchen"
atmosphere matter add-mock --type door_lock --name "Front Door" --location "Entry"
atmosphere matter add-mock --type thermostat --name "Main Thermostat" --location "Living Room"

# List them
atmosphere matter list

# View capabilities
atmosphere matter status "Kitchen Light"
```

### With matter.js Virtual Devices

Once the bridge is implemented:
```bash
# Start a virtual light for testing
npx @matter/examples light --name "Test Light" --port 5541
```

### With Google Matter Virtual Device (MVD)

Download MVD from Google Home Developer Console for testing without hardware.

## Security Considerations

- **PIN codes** are never logged
- **Fabric credentials** should be encrypted at rest
- **Unlock commands** require confirmation (marked `security_sensitive`)
- Bridge communication is localhost-only (consider Unix socket for production)

## Files

- `models.py` - Data models (MatterDevice, MatterEndpoint, etc.)
- `mapping.py` - Device → Capability mapping tables
- `discovery.py` - Device discovery and commissioning
- `bridge.py` - WebSocket client for matter.js bridge
- `cli.py` - CLI commands
- `__init__.py` - Package exports

## References

- [Matter Specification](https://csa-iot.org/developer-resource/specifications-download-request/)
- [matter.js GitHub](https://github.com/matter-js/matter.js)
- [Atmosphere Design Doc](../../design/MATTER_INTEGRATION.md)
