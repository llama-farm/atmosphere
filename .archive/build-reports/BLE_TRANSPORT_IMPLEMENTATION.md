# BLE Transport Implementation

## Overview

This document describes the BLE (Bluetooth Low Energy) transport layer implementation for Atmosphere mesh networking. The implementation enables offline peer discovery and messaging between Mac and Android devices.

## Files Created

### Mac (Python + bleak)

1. **`atmosphere/transport/__init__.py`** - Package initialization
2. **`atmosphere/transport/ble_mac.py`** - Main BLE transport implementation
3. **`scripts/test_ble.py`** - Test script for BLE transport

### Android (Kotlin)

1. **`app/src/main/kotlin/com/llamafarm/atmosphere/transport/BleTransport.kt`** - BLE transport implementation
2. **`app/src/main/kotlin/com/llamafarm/atmosphere/service/BleService.kt`** - Foreground service for BLE mesh
3. **`app/src/main/AndroidManifest.xml`** - Updated with BLE permissions

## Protocol

### Service UUID
```
Atmosphere Mesh Service: A7M0MESH-0001-0000-0000-000000000001
```

### Characteristics
| Name | UUID | Properties | Purpose |
|------|------|------------|---------|
| TX | A7M0MESH-0001-0001-0000-000000000001 | Write, Notify | Send messages |
| RX | A7M0MESH-0001-0002-0000-000000000001 | Read, Notify | Receive messages |
| INFO | A7M0MESH-0001-0003-0000-000000000001 | Read | Node capabilities |

### Message Header (8 bytes)
```
┌────┬────┬────┬────┬────────┬────────┬────────┐
│ V  │ T  │TTL │ F  │ SEQ    │ FRAG   │ TOTAL  │
│ 1  │ 1  │ 1  │ 1  │ 2      │ 1      │ 1      │
└────┴────┴────┴────┴────────┴────────┴────────┘
V:     Version (1)
T:     Message type
TTL:   Time-to-live (hops remaining)
F:     Flags
SEQ:   Sequence number
FRAG:  Fragment index
TOTAL: Total fragments
```

### Message Types
| Type | Value | Purpose |
|------|-------|---------|
| HELLO | 0x01 | Node announcement |
| HELLO_ACK | 0x02 | Response to HELLO |
| GOODBYE | 0x03 | Node leaving |
| ROUTE_REQ | 0x10 | Route discovery |
| ROUTE_REP | 0x11 | Route reply |
| DATA | 0x20 | Application data |
| DATA_ACK | 0x21 | Delivery confirmation |
| MESH_INFO | 0x30 | Mesh topology info |
| CAPABILITY | 0x31 | Node capability advertisement |

## Features

### Implemented
- ✅ BLE GATT server (peripheral mode)
- ✅ BLE scanning and connection (central mode)
- ✅ Message fragmentation/reassembly (up to 64KB messages)
- ✅ Flood-based mesh routing with TTL
- ✅ Loop prevention with LRU seen-message cache
- ✅ Node info exchange via INFO characteristic
- ✅ CBOR encoding (with JSON fallback)
- ✅ Cross-platform compatibility (Mac ↔ Android)

### Not Yet Implemented
- ⏳ Message encryption
- ⏳ Smart gossip routing (currently pure flood)
- ⏳ RSSI-based routing optimization
- ⏳ iOS support

## Dependencies

### Mac (Python)
```bash
pip install bleak       # Required: BLE client (scanning/connecting)
pip install bless       # Optional: GATT server (advertising)
pip install cbor2       # Optional: CBOR encoding (JSON fallback available)
```

### Android (Kotlin)
- No additional dependencies (uses Android Bluetooth APIs)
- Requires Android 5.0+ (API 21+)
- Recommended: Android 12+ (API 31+) for new BLE permissions model

## Usage

### Mac
```bash
# Run test script
cd ~/clawd/projects/atmosphere
python scripts/test_ble.py --name "My-Mac-Node"

# Or use in code
from atmosphere.transport.ble_mac import BleTransport

transport = BleTransport(node_name="My-Node")
transport.on_message = lambda msg: print(f"Got: {msg.payload}")
await transport.start()
await transport.send(b"Hello mesh!")
```

### Android
```kotlin
// In your Activity or Service
val bleTransport = BleTransport(
    context = this,
    nodeName = "My-Android-Node",
    capabilities = listOf("relay", "android")
)

bleTransport.onMessage = { message ->
    Log.d("BLE", "Received: ${message.payload.size} bytes")
}

bleTransport.start()
bleTransport.send(payload = "Hello".toByteArray())
```

## Testing

### Basic Discovery Test

1. Start Mac transport:
   ```bash
   python scripts/test_ble.py --name "Mac-Test"
   ```

2. Start Android app with BLE enabled

3. Both devices should discover each other within 5-10 seconds

### Message Exchange Test

1. Start both devices
2. On Mac, modify test script to send a message:
   ```python
   await transport.send(b"Test message from Mac")
   ```
3. Android should receive and log the message

## Known Limitations

1. **Range**: BLE typically works within 10-30 meters
2. **Bandwidth**: ~50-200 KB/s effective throughput
3. **MTU**: Messages > 244 bytes require fragmentation
4. **Connections**: Practical limit of ~5 simultaneous BLE connections
5. **iOS Background**: iOS has restrictions on BLE background operation

## Troubleshooting

### Mac: "bleak not available"
```bash
pip install bleak
```

### Mac: "bless not available" (GATT server disabled)
```bash
pip install bless
```
Note: Mac can still discover and connect to Android devices without bless.

### Android: "Missing Bluetooth permissions"
Ensure your app requests runtime permissions:
```kotlin
val permissions = BleTransport.getRequiredPermissions()
ActivityCompat.requestPermissions(activity, permissions, REQUEST_CODE)
```

### Devices not discovering each other
1. Ensure Bluetooth is enabled on both devices
2. Check that both are advertising the same service UUID
3. On Android, ensure location permission is granted (required for BLE scanning on older devices)
4. Try moving devices closer together

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      BleTransport                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │  Central Mode   │    │ Peripheral Mode │                │
│  │                 │    │                 │                │
│  │ • BLE Scanner   │    │ • GATT Server   │                │
│  │ • GATT Client   │    │ • Advertiser    │                │
│  │ • Connect       │    │ • Accept        │                │
│  └────────┬────────┘    └────────┬────────┘                │
│           │                       │                         │
│           └───────────┬───────────┘                         │
│                       │                                     │
│  ┌────────────────────┴────────────────────┐               │
│  │            MessageFragmenter            │               │
│  │  • Fragment large messages              │               │
│  │  • Reassemble incoming fragments        │               │
│  └────────────────────┬────────────────────┘               │
│                       │                                     │
│  ┌────────────────────┴────────────────────┐               │
│  │              MeshRouter                  │               │
│  │  • Loop prevention (seen cache)          │               │
│  │  • TTL management                        │               │
│  │  • Flood forwarding                      │               │
│  └──────────────────────────────────────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```
