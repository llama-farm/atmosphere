# Atmosphere Transport Architecture

## Critical Review (2026-02-03)

### Transport Priority (Lower = Higher Priority)
1. **LAN** (Priority 1) - WebSocket on local network, ~1ms latency
2. **WiFi Direct** (Priority 2) - P2P without router, ~5ms latency  
3. **BLE Mesh** (Priority 3) - Works offline, multi-hop, ~50ms latency
4. **Matter** (Priority 4) - Smart home devices, ~100ms latency
5. **Relay** (Priority 5) - Cloud fallback, ~200ms latency

### Current State

#### Python (Mac) - `atmosphere/mesh/transport.py`
| Transport | Status | Lines | Notes |
|-----------|--------|-------|-------|
| LAN | ✅ Working | 150 | Full WebSocket client |
| WiFi Direct | ❌ Stub | 0 | Not implemented |
| BLE | ❌ Stub | 0 | Not implemented |
| Matter | ⚠️ Partial | 40602 | Full integration exists in `/integrations/matter/` |
| Relay | ✅ Working | 100 | Full WebSocket client |

#### Android (Kotlin) - Multiple files
| Transport | Status | Lines | Notes |
|-----------|--------|-------|-------|
| LAN | ✅ Working | 600 | MeshConnection.kt |
| WiFi Direct | ✅ Working | 726 | transport/WifiDirectTransport.kt |
| BLE Mesh | ✅ Working | 1137 | transport/BleTransport.kt |
| Matter | ❌ Stub | 0 | Config exists, no impl |
| Relay | ✅ Working | 200 | network/TransportManager.kt |

### Key Issues Fixed

1. **Connection Fallback** - Android now tries multiple endpoints with timeout
2. **Signed Tokens** - V2 tokens with Ed25519 signatures
3. **Transport Status** - UI shows all transport states
4. **Concurrent Transports** - TransportManagerV2 runs all transports simultaneously

### Concurrent Transport Design

All transports run simultaneously. When sending:
1. Try LAN first (fastest)
2. If LAN fails → WiFi Direct
3. If WiFi Direct fails → BLE
4. If BLE fails → Relay (always works)

For receiving: Accept messages from ANY connected transport.

### Matter Integration

The Python side has full Matter integration:
- `/integrations/matter/discovery.py` - mDNS discovery
- `/integrations/matter/bridge.py` - WebSocket to matter.js bridge
- `/integrations/matter/mapping.py` - Device to capability mapping

To enable Matter on Mac:
```bash
cd ~/clawd/projects/atmosphere
python -m atmosphere.integrations.matter.cli discover
```

### Best Practices

1. **Always have Relay enabled** - It's the ultimate fallback
2. **Prefer local transports** - Lower latency, no cloud dependency
3. **Handle disconnection gracefully** - Auto-reconnect with backoff
4. **Use heartbeats** - 25-second ping interval keeps connections alive
5. **Timeout quickly for fallback** - 5s connect timeout allows fast failover

### Transport Selection Algorithm

```python
def select_transport(peer_id, message):
    """Select best transport for sending to peer."""
    pool = get_connection_pool(peer_id)
    
    # Score each transport
    for transport in pool.transports:
        score = (
            (100 - transport.latency_ms) * 0.4 +  # Lower latency = higher score
            transport.success_rate * 100 * 0.3 +   # Reliability matters
            (6 - transport.priority) * 10 * 0.3    # Priority bonus
        )
        transport.current_score = score
    
    # Use highest scoring connected transport
    return max(pool.transports, key=lambda t: t.current_score if t.connected else -1)
```
