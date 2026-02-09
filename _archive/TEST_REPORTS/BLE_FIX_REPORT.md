# BLE UUID Mismatch Fix Report

**Date:** 2025-01-28
**Status:** ✅ FIXED

## Problem Summary

The Mac Python implementation and Android Kotlin implementation were using completely incompatible BLE configurations, preventing device discovery and communication.

## Issues Found & Fixed

### 1. Service & Characteristic UUIDs (Lines 26-32)

**BEFORE (Mac):**
```python
MESH_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
TX_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"
RX_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef2"
INFO_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef3"
```

**AFTER (Mac - matching Android):**
```python
MESH_SERVICE_UUID = "A7A05F30-0001-4000-8000-00805F9B34FB"
TX_CHAR_UUID = "A7A05F30-0002-4000-8000-00805F9B34FB"
RX_CHAR_UUID = "A7A05F30-0003-4000-8000-00805F9B34FB"
INFO_CHAR_UUID = "A7A05F30-0004-4000-8000-00805F9B34FB"
MESH_ID_CHAR_UUID = "A7A05F30-0005-4000-8000-00805F9B34FB"  # NEW
CCCD_UUID = "00002902-0000-1000-8000-00805F9B34FB"          # NEW
```

---

### 2. MessageType Values (Lines 35-46)

**BEFORE (Mac):**
```python
class MessageType(IntEnum):
    HELLO = 0x01
    DATA = 0x02      # WRONG!
    ACK = 0x03
    FORWARD = 0x04
    QUERY = 0x05
    RESPONSE = 0x06
```

**AFTER (Mac - matching Android):**
```python
class MessageType(IntEnum):
    # Discovery
    HELLO = 0x01
    HELLO_ACK = 0x02
    GOODBYE = 0x03
    
    # Routing
    ROUTE_REQ = 0x10
    ROUTE_REP = 0x11
    
    # Data
    DATA = 0x20       # FIXED!
    DATA_ACK = 0x21
    
    # Mesh management
    MESH_INFO = 0x30
    CAPABILITY = 0x31
```

---

### 3. Message Header Format (Lines 49-120)

**BEFORE (Mac) - 38-byte big-endian:**
```python
struct.pack(">B16s16sBI", msg_type, msg_id, source, ttl, payload_len)
# = 1 + 16 + 16 + 1 + 4 = 38 bytes, BIG-endian
```

**AFTER (Mac - matching Android) - 8-byte little-endian:**
```python
struct.pack("<BBBBHBB", version, msg_type, ttl, flags, seq, frag_index, frag_total)
# = 1 + 1 + 1 + 1 + 2 + 1 + 1 = 8 bytes, LITTLE-endian
```

**New MessageHeader class added matching Android exactly:**
```python
@dataclass
class MessageHeader:
    version: int = 1
    msg_type: MessageType = MessageType.DATA
    ttl: int = 5
    flags: int = 0
    seq: int = 0           # Sequence number for dedup
    frag_index: int = 0    # Fragment index
    frag_total: int = 1    # Total fragments
```

---

### 4. MessageFlags Added (Line ~115)

**NEW (matching Android):**
```python
class MessageFlags:
    ENCRYPTED = 0x01
    BROADCAST = 0x02
    PRIORITY = 0x04
    RELIABLE = 0x08
```

---

### 5. BleMessage Class Restructured (Lines 118-155)

**BEFORE:**
- Used `msg_id` (16-byte string) for deduplication
- Used `source` field in header
- Different serialization format

**AFTER:**
- Uses `source_id:seq` combination for deduplication (matching Android)
- Header and payload separated cleanly
- Compatible serialization with Android's `BleMessage.toBytes()`

---

### 6. BleMeshTransport Updates (Lines 170+)

- Added `_seq_counter` for sequence numbers
- Added `_next_seq()` method
- Updated `send()` and `broadcast()` to create proper MessageHeader
- Updated `_broadcast_message()` to use `source_id:seq` for dedup
- Updated `_handle_received_message()` to parse new format
- Added `_send_hello_ack()` method for proper handshake
- Updated `_forward_message()` to properly decrement TTL
- Fixed characteristic direction (TX for sending, RX for receiving)

---

### 7. Hello Message Format (Lines ~280)

**BEFORE:**
```python
hello = BleMessage(msg_id=..., msg_type=HELLO, source=..., payload=json)
```

**AFTER (matching Android's `encodeNodeInfo()`):**
```python
hello_payload = json.dumps({
    "id": self.node_id,
    "name": self.node_name,
    "platform": "macOS",
    "mesh_id": self.mesh_id,
    "capabilities": self.capabilities,
    "version": "1.0"
}).encode('utf-8')
```

---

## Files Modified

| File | Changes |
|------|---------|
| `atmosphere/mesh/ble_mesh.py` | UUID fix, message format, message types |

## Files NOT Modified (Reference Only)

| File | Status |
|------|--------|
| `BleTransport.kt` (Android) | Reference implementation - no changes needed |

---

## Verification Steps

1. **UUID Match:**
   ```bash
   grep -E "(MESH_SERVICE|TX_CHAR|RX_CHAR|INFO_CHAR)_UUID" atmosphere/mesh/ble_mesh.py
   ```
   Should show `A7A05F30-...` pattern

2. **MessageType Match:**
   ```bash
   grep "DATA = 0x" atmosphere/mesh/ble_mesh.py
   ```
   Should show `DATA = 0x20`

3. **Header Size:**
   The pack format `<BBBBHBB` produces exactly 8 bytes (matching Android)

---

## Protocol Compatibility Summary

| Feature | Mac (Before) | Mac (After) | Android |
|---------|--------------|-------------|---------|
| Service UUID | `12345678...` | `A7A05F30...` | `A7A05F30...` ✅ |
| Header Size | 38 bytes | 8 bytes | 8 bytes ✅ |
| Byte Order | Big-endian | Little-endian | Little-endian ✅ |
| DATA type | 0x02 | 0x20 | 0x20 ✅ |
| Dedup Key | msg_id | source:seq | source:seq ✅ |
| Hello Format | Custom | JSON | JSON ✅ |

---

## Next Steps

1. Run BLE transport tests on Mac
2. Test discovery between Mac and Android devices
3. Verify message exchange works bidirectionally
4. Test multi-hop forwarding
