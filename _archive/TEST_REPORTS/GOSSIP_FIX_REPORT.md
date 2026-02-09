# Gossip Protocol Fix Report

**Date:** 2025-01-31  
**Status:** ✅ FIXED  
**Files Modified:**
- `atmosphere/api/server.py`
- `atmosphere/core/gossip.py`

---

## Problem Summary

The gossip protocol was completely broken due to a **message format mismatch** between the sender (GossipManager) and receiver (server.py).

### What GossipManager Sends:
```json
{
  "type": "broadcast",
  "payload": {
    "type": "capability.announce",
    "node_id": "abc123",
    "capabilities": [...],
    "ttl": 10
  }
}
```

### What Server Expected:
```json
{
  "type": "message",
  "payload": {
    "type": "gossip",
    "data": "<base64-encoded>"
  }
}
```

**Result:** All gossip messages were being silently ignored. Capabilities never propagated.

---

## Fixes Applied

### Fix 1: Message Format Handling (CRITICAL)

**File:** `atmosphere/api/server.py` - `_process_relay_message` method

**Change:** Updated the message handler to correctly process `capability.announce` payloads:

```python
# Before (BROKEN):
if payload_type == "gossip" and self.gossip:
    import base64
    gossip_data = base64.b64decode(payload.get("data", ""))
    await self.gossip.handle_announcement(gossip_data, from_node)

# After (FIXED):
if payload_type == "capability.announce" and self.gossip:
    await self.gossip.handle_announcement(from_node, payload)

# Also added legacy support for backwards compatibility
elif payload_type == "gossip" and self.gossip:
    # ... legacy base64 handling ...
```

### Fix 2: Nonce Deduplication

**File:** `atmosphere/core/gossip.py` - `GossipMessage` dataclass and `GossipManager`

**Changes:**
1. Added `nonce` field to `GossipMessage` with auto-generation:
```python
nonce: str = ""  # Added for deduplication

def __post_init__(self):
    if not self.nonce:
        self.nonce = uuid.uuid4().hex[:16]
```

2. Added nonce cache to `GossipManager`:
```python
# Nonce cache for deduplication (nonce -> timestamp)
self._seen_nonces: Dict[str, float] = {}
self._nonce_cache_ttl = 300  # 5 minutes
```

3. Added `_check_nonce()` method with automatic cleanup:
```python
def _check_nonce(self, nonce: str) -> bool:
    """Check if nonce is new. Returns True if new, False if seen."""
    now = time.time()
    
    # Cleanup expired nonces
    expired = [n for n, t in self._seen_nonces.items() 
               if now - t > self._nonce_cache_ttl]
    for n in expired:
        del self._seen_nonces[n]
    
    # Check and mark
    if nonce in self._seen_nonces:
        return False
    self._seen_nonces[nonce] = now
    return True
```

### Fix 3: Multi-Hop Forwarding

**File:** `atmosphere/core/gossip.py` - `handle_announcement` method

**Change:** Added forwarding logic for announcements with TTL > 1:

```python
# Forward if TTL > 1 (multi-hop propagation)
if msg.ttl > 1 and self.send_to_relay:
    forwarded_msg = GossipMessage(
        type=msg.type,
        node_id=msg.node_id,  # Keep original source
        timestamp=msg.timestamp,
        capabilities=msg.capabilities,
        ttl=msg.ttl - 1,  # Decrement TTL
        nonce=msg.nonce,  # Keep same nonce for deduplication
        signature=msg.signature,
    )
    await self.send_to_relay({
        "type": "broadcast",
        "payload": forwarded_msg.to_dict(),
    })
```

---

## How It Works Now

### Message Flow (Fixed):

```
┌──────────────────────────────────────────────────────────────────┐
│ Node A: GossipManager.broadcast_capabilities()                    │
│   ↓                                                              │
│ Creates GossipMessage(type="capability.announce", nonce="xyz")    │
│   ↓                                                              │
│ Sends: {"type": "broadcast", "payload": {...}}                    │
└──────────────────────────────────────────────────────────────────┘
                              ↓
                         Relay Server
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ Node B: _process_relay_message()                                  │
│   ↓                                                              │
│ Receives: {"type": "message", "from": "A", "payload": {...}}      │
│   ↓                                                              │
│ Checks: payload_type == "capability.announce" ✓                   │
│   ↓                                                              │
│ Calls: gossip.handle_announcement(from_node, payload)             │
│   ↓                                                              │
│ Checks nonce (not seen) ✓                                         │
│   ↓                                                              │
│ Updates gradient table ✓                                          │
│   ↓                                                              │
│ Forwards if TTL > 1 ✓                                             │
└──────────────────────────────────────────────────────────────────┘
                              ↓
                         Relay Server
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ Node C: Receives forwarded announcement                           │
│   ↓                                                              │
│ Checks nonce (not seen) ✓                                         │
│   ↓                                                              │
│ Learns about Node A's capabilities (hops=2)                       │
└──────────────────────────────────────────────────────────────────┘
```

### Nonce Deduplication Prevents:
- Same node receiving announcement from multiple paths
- Forwarding loops in the mesh
- Duplicate processing wasting CPU

### Multi-Hop Enables:
- A → B → C capability discovery (A and C don't need direct connection)
- True mesh topology (not just hub-and-spoke)
- TTL prevents infinite propagation

---

## Testing Recommendations

### Test 1: Basic Gossip Propagation
1. Start two nodes (A and B) connected to same relay
2. Verify A's capabilities appear in B's gradient table
3. Verify B's capabilities appear in A's gradient table

### Test 2: Nonce Deduplication
1. Send same announcement twice (same nonce)
2. Verify second one is dropped (check debug logs)

### Test 3: Multi-Hop Propagation
1. Start three nodes: A, B, C
2. Configure so only A↔B and B↔C are directly connected
3. Verify A's capabilities reach C (via B) with hops=2

### Test 4: TTL Expiry
1. Send announcement with TTL=1
2. Verify it's NOT forwarded

---

## Remaining Considerations

### Not Changed (Intentional):
- **Did not switch to GossipProtocol** - GossipManager is simpler and now works correctly. GossipProtocol has additional features (endpoint registry, UI events) but is more complex. The fix to GossipManager is minimal and less risky.

### Future Improvements:
1. **Endpoint propagation** - GossipProtocol sends endpoint info (local IPs) which enables LAN discovery. GossipManager doesn't. Consider adding this later.
2. **Node cost factors** - GossipProtocol calculates dynamic routing cost based on battery/CPU. Could add to GossipManager.
3. **IHAVE/IWANT** - Neither implementation fully uses this for intelligent gossip pull. Future optimization.

---

## Summary

| Issue | Status | Fix |
|-------|--------|-----|
| Message format mismatch | ✅ Fixed | Handle `capability.announce` type |
| No nonce deduplication | ✅ Fixed | Added nonce field + cache |
| No multi-hop forwarding | ✅ Fixed | Forward if TTL > 1 |
| Blocking locks | ⚠️ Known | GradientTable uses threading.RLock (documented in review) |

The gossip protocol should now work correctly for capability propagation across the mesh.
