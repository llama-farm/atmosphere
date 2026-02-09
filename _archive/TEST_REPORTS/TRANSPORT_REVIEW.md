# Atmosphere Transport Layer Review

**Date:** 2025-02-07  
**Reviewer:** Transport Tester Subagent  

---

## Executive Summary

| Transport | Status | Cross-Platform | Notes |
|-----------|--------|----------------|-------|
| **Relay** | ✅ Working | ✅ Yes | Production-ready, token security works |
| **LAN/mDNS** | ⚠️ Partial | ✅ Yes | mDNS discovery works, needs WebSocket server |
| **BLE Mesh** | ❌ Broken | ❌ No | **CRITICAL: UUID mismatch Mac↔Android** |

---

## 1. Relay Transport

### Status: ✅ WORKING

**Production URL:** `wss://atmosphere-relay-production.up.railway.app`

### Test Results

#### Health Endpoint
```json
{
  "status": "ok",
  "meshes": 1,
  "connections": 1,
  "registered_meshes": 1,
  "uptime_seconds": 57203
}
```

#### Connection Flow (Verified)
```
┌─────────────────┐                    ┌─────────────────┐
│   Founder Node  │                    │  Relay Server   │
└────────┬────────┘                    └────────┬────────┘
         │                                      │
         │ WS connect /relay/{mesh_id}          │
         │─────────────────────────────────────▶│
         │                                      │
         │ {"type":"register_mesh",             │
         │  "mesh_id":...,                      │
         │  "mesh_public_key":...,              │
         │  "node_public_key":...,              │
         │  "founder_proof":...}                │
         │─────────────────────────────────────▶│
         │                                      │
         │ {"type":"mesh_registered",           │
         │  "success":true}                     │
         │◀─────────────────────────────────────│
         │                                      │
         │ {"type":"joined",...}                │
         │◀─────────────────────────────────────│
         │                                      │
         │ {"type":"peers","peers":[]}          │
         │◀─────────────────────────────────────│
         │                                      │
```

#### Member Join with Token (Verified)
```
┌─────────────────┐                    ┌─────────────────┐
│   Member Node   │                    │  Relay Server   │
└────────┬────────┘                    └────────┬────────┘
         │                                      │
         │ WS connect /relay/{mesh_id}          │
         │─────────────────────────────────────▶│
         │                                      │
         │ {"type":"join",                      │
         │  "node_id":...,                      │
         │  "token":{signed by mesh key}}       │
         │─────────────────────────────────────▶│
         │                                      │
         │ {"type":"joined",...}                │
         │◀─────────────────────────────────────│
         │                                      │
         │ {"type":"peers",[founder_info]}      │
         │◀─────────────────────────────────────│
```

### Tested Features
- [x] Health endpoint
- [x] WebSocket connection
- [x] Founder mesh registration (with Ed25519 signatures)
- [x] Member join with token verification
- [x] Ping/pong keepalive (~0.1ms latency)
- [x] Peer notifications (peer_joined/peer_left)
- [x] Backward compat: join unregistered mesh allowed

### Code Location
- **Server:** `relay/server.py` (FastAPI + WebSocket)
- **Client:** `atmosphere/transport/relay.py`

### Issues Found
1. **Minor:** After member join, founder receives empty `peers` list before `peer_joined` notification
2. **Minor:** Ping response comes as separate `pong` message, not inline with `peers`

---

## 2. LAN/mDNS Transport

### Status: ⚠️ PARTIAL

### Components
1. **Discovery:** `atmosphere/mesh/discovery.py` - Uses `zeroconf` library
2. **Transport:** `atmosphere/mesh/transport.py` - LANTransport class

### mDNS Configuration
```python
SERVICE_TYPE = "_atmosphere._tcp.local."
SERVICE_NAME_PREFIX = "atmosphere-"
```

### Advertised Properties
```python
properties = {
    b"node_id": node_id.encode(),
    b"mesh_id": mesh_id.encode(),
    b"capabilities": ",".join(capabilities).encode(),
}
```

### Connection Flow
```
┌─────────────────┐                    ┌─────────────────┐
│   Mac Node A    │                    │   Mac Node B    │
└────────┬────────┘                    └────────┬────────┘
         │                                      │
         │ mDNS: advertise _atmosphere._tcp     │
         │◀════════════════════════════════════▶│ mDNS: browse
         │                                      │
         │ ServiceInfo discovered               │
         │  - node_id, mesh_id, caps            │
         │  - host:port                         │
         │◀─────────────────────────────────────│
         │                                      │
         │ WS connect ws://{host}:{port}/ws     │
         │◀─────────────────────────────────────│
         │                                      │
```

### Issues Found

1. **Missing WebSocket Server**
   - `LANTransport` is a WebSocket CLIENT only
   - No corresponding server in `transport.py` to accept connections
   - Discovery works, but no endpoint to connect to

2. **Port Configuration**
   - Default port 11450 configured but no server binds it

### Recommendations
- Add `LANServer` class that runs aiohttp/FastAPI WS server on mDNS-advertised port
- Or use existing mesh node WebSocket server

---

## 3. BLE Mesh Transport

### Status: ❌ BROKEN (Cross-Platform)

### Critical Bug: UUID Mismatch

**Mac/Python UUIDs** (`atmosphere/mesh/ble_mesh.py`):
```python
MESH_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
TX_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"
RX_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef2"
INFO_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef3"
```

**Android UUIDs** (`transport/BleTransport.kt`):
```kotlin
val MESH_SERVICE_UUID = UUID.fromString("A7A05F30-0001-4000-8000-00805F9B34FB")
val TX_CHAR_UUID = UUID.fromString("A7A05F30-0002-4000-8000-00805F9B34FB")
val RX_CHAR_UUID = UUID.fromString("A7A05F30-0003-4000-8000-00805F9B34FB")
val INFO_CHAR_UUID = UUID.fromString("A7A05F30-0004-4000-8000-00805F9B34FB")
val MESH_ID_CHAR_UUID = UUID.fromString("A7A05F30-0005-4000-8000-00805F9B34FB")
```

**Result:** Mac and Android devices will **never discover each other** via BLE because they advertise completely different service UUIDs.

### Message Format Mismatch

**Mac uses binary struct** (`ble_mesh.py`):
```python
def to_bytes(self) -> bytes:
    header = struct.pack(
        ">B16s16sBI",  # type, msg_id, source, ttl, payload_len
        self.msg_type,
        self.msg_id.encode()[:16].ljust(16, b'\x00'),
        self.source.encode()[:16].ljust(16, b'\x00'),
        self.ttl,
        len(self.payload)
    )
    return header + self.payload
```

**Android uses JSON** (`BleMeshManager.kt`):
```kotlin
fun toBytes(): ByteArray {
    val json = JSONObject().apply {
        put("id", messageId)
        put("from", fromNodeId)
        put("to", toNodeId)
        put("mesh", meshId)
        put("ttl", ttl)
        put("payload", Base64.encode(encryptedPayload))
        // ...
    }
    return json.toString().toByteArray()
}
```

**Result:** Even if UUIDs matched, messages would be unparseable.

### Android-Specific Features (Missing on Mac)
- `MESH_ID_CHAR_UUID` (5th characteristic) - Mac only has 4
- Encrypted message format with nonce/signature
- Manufacturer data advertising

### Mac Implementation Issues
1. CoreBluetooth implementation incomplete (falls back to bleak)
2. No GATT server mode (can only scan, not advertise)
3. Bleak doesn't support peripheral mode on macOS

### Fix Required

```python
# ble_mesh.py - Align with Android
MESH_SERVICE_UUID = "A7A05F30-0001-4000-8000-00805F9B34FB"
TX_CHAR_UUID = "A7A05F30-0002-4000-8000-00805F9B34FB"
RX_CHAR_UUID = "A7A05F30-0003-4000-8000-00805F9B34FB"
INFO_CHAR_UUID = "A7A05F30-0004-4000-8000-00805F9B34FB"
MESH_ID_CHAR_UUID = "A7A05F30-0005-4000-8000-00805F9B34FB"  # Add this
```

And use JSON format for messages to match Android.

---

## Transport Priority & Fallback

Current configuration (`transport.py`):
```python
TRANSPORT_PRIORITY = [
    TransportType.LAN,        # 1st - Fastest
    TransportType.WIFI_DIRECT,
    TransportType.BLE_MESH,
    TransportType.MATTER,
    TransportType.RELAY,      # Last - Always works
]
```

The fallback logic is correct - relay is always available as the ultimate fallback.

---

## Recommendations

### Immediate (P0)
1. **Fix BLE UUIDs** - Align Mac with Android UUIDs
2. **Fix BLE message format** - Use JSON on both platforms
3. **Add MESH_ID characteristic** to Mac implementation

### Short-term (P1)
1. **Add LAN WebSocket server** - Currently discovery works but no server to connect to
2. **Complete CoreBluetooth implementation** - Bleak can't do peripheral mode on Mac

### Medium-term (P2)
1. **WiFi Direct** - Currently stub only
2. **Matter** - Currently stub only
3. **End-to-end encryption** - Android has it, Mac doesn't

---

## Test Commands Used

```bash
# Health check
curl https://atmosphere-relay-production.up.railway.app/health

# WebSocket test (Python)
python3 -c "
import asyncio, websockets, json

async def test():
    async with websockets.connect('wss://atmosphere-relay-production.up.railway.app/relay/test') as ws:
        await ws.send(json.dumps({'type':'join','node_id':'test'}))
        print(await ws.recv())

asyncio.run(test())
"
```

---

## Files Reviewed

| File | Purpose |
|------|---------|
| `relay/server.py` | WebSocket relay server (FastAPI) |
| `atmosphere/transport/relay.py` | Relay client |
| `atmosphere/mesh/transport.py` | Multi-transport manager |
| `atmosphere/mesh/discovery.py` | mDNS/Zeroconf discovery |
| `atmosphere/mesh/ble_mesh.py` | Mac BLE implementation |
| `atmosphere-android/.../BleTransport.kt` | Android BLE transport |
| `atmosphere-android/.../BleMeshManager.kt` | Android BLE mesh manager |

---

**End of Report**
