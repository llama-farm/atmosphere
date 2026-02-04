# Atmosphere Mesh Design Document

## The Vision: Internet of Intent

**"Any device, anywhere, can understand and execute user intent."**

The mesh is the foundation. Without reliable, resilient connectivity that works
**every single time**, the Internet of Intent fails. This document defines the
complete mesh architecture.

---

## Table of Contents

1. [Core Principles](#core-principles)
2. [Transport Hierarchy](#transport-hierarchy)
3. [Connection Train](#connection-train)
4. [Mesh Persistence](#mesh-persistence)
5. [BLE Proximity Pairing](#ble-proximity-pairing)
6. [Heartbeat Protocol](#heartbeat-protocol)
7. [Failover & Recovery](#failover--recovery)
8. [Context Preservation](#context-preservation)
9. [Open Source Patterns](#open-source-patterns)
10. [Implementation Plan](#implementation-plan)

---

## Core Principles

### 1. Always Connected
The mesh must maintain connectivity through any means available:
- Local BLE when in proximity
- LAN when on same network
- Cloud relay when all else fails
- **Never show "disconnected" if any path exists**

### 2. Graceful Degradation
When optimal transport fails:
- Automatically try next transport
- Maintain session context across transport switches
- User should not notice transport changes

### 3. Persistence First
- **Every mesh relationship is saved**
- App remembers all meshes it has joined
- Auto-reconnect on app launch/resume
- Manual "forget" required to remove

### 4. Zero Configuration
- BLE pairing with simple code confirmation
- No QR codes required (optional convenience)
- No manual IP entry
- Just get close and tap "pair"

---

## Transport Hierarchy

### Priority Order (Best → Fallback)

```
┌─────────────────────────────────────────────────────────────┐
│  1. BLE MESH (0-30m)                                        │
│     • Works offline                                         │
│     • ~100ms latency                                        │
│     • Battery efficient                                     │
│     • Best for: Proximity, offline, low-power               │
├─────────────────────────────────────────────────────────────┤
│  2. LAN DIRECT (Same network)                               │
│     • Lowest latency (~10ms)                                │
│     • Highest bandwidth                                     │
│     • No internet required                                  │
│     • Best for: Same WiFi, home/office                      │
├─────────────────────────────────────────────────────────────┤
│  3. LAN MDNS (Discovery)                                    │
│     • Auto-discovery on local network                       │
│     • Falls back to direct if known IP works                │
│     • Best for: Dynamic IPs, new networks                   │
├─────────────────────────────────────────────────────────────┤
│  4. CLOUD RELAY (Always available)                          │
│     • Works across any network                              │
│     • ~50-200ms latency                                     │
│     • Requires internet                                     │
│     • Best for: Different networks, roaming                 │
└─────────────────────────────────────────────────────────────┘
```

### Transport Capabilities

| Transport | Latency | Bandwidth | Offline | Range | Battery |
|-----------|---------|-----------|---------|-------|---------|
| BLE Mesh | ~100ms | 1 Mbps | ✅ | 30m | Low |
| LAN Direct | ~10ms | 1 Gbps | ✅ | Network | N/A |
| LAN mDNS | ~15ms | 1 Gbps | ✅ | Network | N/A |
| Cloud Relay | ~100ms | 100 Mbps | ❌ | Global | Med |

---

## Connection Train

### The Train Metaphor
Think of transports as train cars - the app tries to board the fastest train
first, and falls back to slower trains only when necessary.

### Algorithm

```python
class ConnectionTrain:
    """
    Continuously probe all transports, use the best available.
    """
    
    def __init__(self):
        self.transports = {
            'ble': BleTransport(),      # Priority 1
            'lan': LanTransport(),      # Priority 2  
            'relay': RelayTransport()   # Priority 3 (always on)
        }
        self.active_transport = None
        self.transport_status = {}  # transport -> (connected, latency, last_check)
    
    async def run(self):
        """Main connection loop - runs forever."""
        while True:
            # Probe all transports in parallel
            results = await asyncio.gather(
                self.probe_ble(),
                self.probe_lan(),
                self.probe_relay(),
                return_exceptions=True
            )
            
            # Select best available
            best = self.select_best_transport()
            
            if best != self.active_transport:
                await self.switch_transport(best)
            
            await asyncio.sleep(PROBE_INTERVAL)  # 5-10 seconds
    
    def select_best_transport(self) -> str:
        """Select best transport by priority and availability."""
        for transport in ['ble', 'lan', 'relay']:
            status = self.transport_status.get(transport)
            if status and status.connected:
                return transport
        return 'relay'  # Fallback
    
    async def switch_transport(self, new_transport: str):
        """Switch to new transport, preserving context."""
        old = self.active_transport
        
        # Notify peer of transport switch
        await self.send_transport_switch_notice(old, new_transport)
        
        # Switch
        self.active_transport = new_transport
        
        logger.info(f"🚂 Transport switch: {old} → {new_transport}")
```

### Probe Strategy

```python
PROBE_INTERVALS = {
    'ble': 5,       # Check BLE every 5s when not connected
    'lan': 10,      # Check LAN every 10s
    'relay': 30,    # Relay is always-on, just health check
}

# When transport is active, probe less frequently
ACTIVE_PROBE_MULTIPLIER = 6  # 30s for BLE, 60s for LAN, etc.
```

### State Machine

```
                    ┌──────────────┐
                    │  SEARCHING   │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌─────────┐
        │   BLE   │  │   LAN   │  │  RELAY  │
        │ PROBING │  │ PROBING │  │ PROBING │
        └────┬────┘  └────┬────┘  └────┬────┘
             │            │            │
             ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌─────────┐
        │   BLE   │  │   LAN   │  │  RELAY  │
        │ ACTIVE  │◄─┤ ACTIVE  │◄─┤ ACTIVE  │
        └─────────┘  └─────────┘  └─────────┘
             │            │            │
             └────────────┴────────────┘
                          │
                    ┌─────▼─────┐
                    │  HEALTHY  │
                    └───────────┘
```

---

## Mesh Persistence

### What Gets Saved

```kotlin
data class SavedMesh(
    val meshId: String,           // Unique mesh identifier
    val meshName: String,         // Human-readable name
    val founderId: String,        // Founder node ID
    val founderName: String,      // "Rob's Mac"
    
    // Credentials
    val relayToken: String,       // Token for relay auth
    val meshKey: ByteArray?,      // Encryption key (if any)
    
    // Endpoints (all known ways to reach founder)
    val endpoints: List<Endpoint>,
    
    // State
    val joinedAt: Long,           // Timestamp
    val lastConnected: Long,      // Last successful connection
    val autoReconnect: Boolean,   // Auto-reconnect enabled
)

data class Endpoint(
    val type: String,             // "ble", "lan", "relay"
    val address: String,          // MAC addr, IP:port, or relay URL
    val lastSeen: Long,           // When this endpoint last worked
    val latencyMs: Int?,          // Last measured latency
)
```

### Storage Location

**Android:**
```kotlin
// DataStore (encrypted preferences)
val meshesKey = stringPreferencesKey("saved_meshes")

// Store as JSON array
[
  {
    "meshId": "0b82206b236bd66c",
    "meshName": "Atmosphere",
    "endpoints": [
      {"type": "relay", "address": "wss://relay.atmosphere.dev"},
      {"type": "lan", "address": "192.168.1.100:11451"},
      {"type": "ble", "address": "BC:D0:74:01:65:FB"}
    ],
    ...
  }
]
```

**Mac:**
```python
# ~/.atmosphere/meshes.json
{
  "meshes": [...],
  "active_mesh": "0b82206b236bd66c"
}
```

### UI Display

```
┌─────────────────────────────────────────┐
│  My Meshes                              │
├─────────────────────────────────────────┤
│  🟢 Atmosphere (Rob's Mac)              │
│      Connected via LAN • 12ms           │
│      [Disconnect]                       │
├─────────────────────────────────────────┤
│  🔴 Office Mesh (Work Mac)              │
│      Last seen: 2 days ago              │
│      [Reconnect] [Forget]               │
├─────────────────────────────────────────┤
│  ⚪ Home Mesh (Home Server)             │
│      Last seen: 1 hour ago              │
│      Auto-reconnecting...               │
└─────────────────────────────────────────┘
```

### Auto-Reconnect Logic

```kotlin
fun onAppResume() {
    val savedMeshes = loadSavedMeshes()
    
    for (mesh in savedMeshes.filter { it.autoReconnect }) {
        if (!isConnectedTo(mesh)) {
            // Try endpoints in order of last success
            val sortedEndpoints = mesh.endpoints
                .sortedByDescending { it.lastSeen }
            
            for (endpoint in sortedEndpoints) {
                if (tryConnect(endpoint)) {
                    break
                }
            }
        }
    }
}
```

---

## BLE Proximity Pairing

### Flow

```
┌──────────────────┐          ┌──────────────────┐
│     ANDROID      │          │       MAC        │
│                  │          │                  │
│  Sees "Mac" in   │          │  Advertising...  │
│  nearby devices  │          │                  │
│                  │          │                  │
│  [Tap to Pair]   │          │                  │
│        │         │          │                  │
│        ▼         │          │                  │
│  ─────────────────────────────────────────────│
│  │         PAIR_REQUEST (pubkey)         │    │
│  ─────────────────────────────────────────────│
│                  │          │        │        │
│                  │          │        ▼        │
│                  │          │  Accept pairing │
│  ─────────────────────────────────────────────│
│  │         PAIR_ACCEPT (pubkey)          │    │
│  ─────────────────────────────────────────────│
│        │         │          │        │        │
│        ▼         │          │        ▼        │
│  ┌──────────┐    │          │   ┌──────────┐  │
│  │  4 7 2   │    │  ECDH    │   │  4 7 2   │  │
│  │  8 3 1   │◄───┼──────────┼───│  8 3 1   │  │
│  └──────────┘    │  shared  │   └──────────┘  │
│  "Confirm code   │  secret  │   "Confirm code │
│   matches?"      │          │    matches?"    │
│        │         │          │        │        │
│  [Confirm]       │          │   [Confirm]     │
│        │         │          │        │        │
│  ─────────────────────────────────────────────│
│  │         CODE_CONFIRMED                │    │
│  ─────────────────────────────────────────────│
│        │         │          │        │        │
│  ─────────────────────────────────────────────│
│  │         CREDENTIALS                   │    │
│  │  • relay_token                        │    │
│  │  • mesh_id                            │    │
│  │  • local_ips                          │    │
│  │  • capabilities                       │    │
│  ─────────────────────────────────────────────│
│        │         │          │        │        │
│        ▼         │          │        ▼        │
│  ✅ PAIRED!      │          │   ✅ PAIRED!    │
│  Save mesh       │          │   Save peer     │
└──────────────────┘          └──────────────────┘
```

### Security

- **ECDH Key Exchange**: X25519 for shared secret
- **Code Derivation**: `SHA256(shared_secret + "atmosphere-pair")[:6]`
- **No PIN transmission**: Code derived independently on both sides
- **MITM Protection**: User verifies codes match visually

### Implementation

```python
# Already implemented in atmosphere/transport/ble_pairing.py
# Key classes:
# - BlePairingManager
# - PairingSession
# - PairingCredentials
```

---

## Heartbeat Protocol

### Multi-Channel Heartbeats

Every active transport sends heartbeats independently:

```python
class HeartbeatManager:
    """
    Send heartbeats across ALL active transports.
    This ensures we detect transport failures quickly.
    """
    
    HEARTBEAT_INTERVALS = {
        'ble': 30,      # BLE: every 30s
        'lan': 15,      # LAN: every 15s  
        'relay': 60,    # Relay: every 60s (server handles keepalive)
    }
    
    async def heartbeat_loop(self, transport: str):
        interval = self.HEARTBEAT_INTERVALS[transport]
        
        while self.running:
            heartbeat = self.build_heartbeat(transport)
            
            try:
                await self.transports[transport].send(heartbeat)
                self.last_sent[transport] = time.time()
            except Exception as e:
                self.mark_transport_unhealthy(transport)
            
            await asyncio.sleep(interval)
```

### Heartbeat Content

```json
{
  "type": "heartbeat",
  "node_id": "69ff1fa7cc80d0e0",
  "timestamp": 1707080400,
  "transport": "ble",
  "metrics": {
    "peers": 2,
    "messages_sent": 150,
    "messages_received": 148,
    "uptime_seconds": 3600
  },
  "capabilities": ["relay", "llm", "embeddings"],
  "endpoints": [
    {"type": "lan", "address": "192.168.1.100:11451"},
    {"type": "ble", "address": "BC:D0:74:01:65:FB"}
  ]
}
```

### Heartbeat Timeout Detection

```python
HEARTBEAT_TIMEOUTS = {
    'ble': 90,       # 3 missed heartbeats
    'lan': 45,       # 3 missed heartbeats
    'relay': 180,    # 3 missed heartbeats
}

def check_heartbeat_health(self, transport: str) -> bool:
    last_received = self.last_received.get(transport, 0)
    timeout = self.HEARTBEAT_TIMEOUTS[transport]
    
    if time.time() - last_received > timeout:
        logger.warning(f"❌ Heartbeat timeout on {transport}")
        return False
    return True
```

---

## Failover & Recovery

### Automatic Failover

```python
async def on_transport_failure(self, failed_transport: str):
    """Handle transport failure - switch to next best."""
    
    # Mark failed
    self.transport_status[failed_transport].connected = False
    
    # Find next best
    for transport in ['ble', 'lan', 'relay']:
        if transport != failed_transport:
            status = self.transport_status.get(transport)
            if status and status.connected:
                await self.switch_transport(transport)
                return
    
    # All failed - enter reconnection mode
    await self.enter_reconnection_mode()

async def enter_reconnection_mode(self):
    """Aggressive reconnection when all transports fail."""
    
    self.state = ConnectionState.RECONNECTING
    
    # Try all transports with exponential backoff
    backoff = 1
    max_backoff = 60
    
    while self.state == ConnectionState.RECONNECTING:
        for transport in ['relay', 'lan', 'ble']:  # Reverse order for speed
            if await self.try_connect(transport):
                self.state = ConnectionState.CONNECTED
                return
        
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)
```

### Session Continuity

When switching transports, preserve:
- Active conversations
- Pending requests
- Queue of unsent messages

```python
class SessionManager:
    """Maintains session across transport switches."""
    
    def __init__(self):
        self.pending_messages = asyncio.Queue()
        self.active_requests = {}  # request_id -> (request, callback)
    
    async def on_transport_switch(self, old: str, new: str):
        # Replay pending messages on new transport
        while not self.pending_messages.empty():
            msg = self.pending_messages.get_nowait()
            await self.send_via(new, msg)
        
        # Re-request active requests
        for req_id, (request, callback) in self.active_requests.items():
            await self.resend_request(new, request, callback)
```

---

## Context Preservation

### What Context to Preserve

1. **Mesh memberships**: All meshes the device has joined
2. **Peer information**: Known peers with their capabilities
3. **Endpoint cache**: All known ways to reach each peer
4. **Conversation state**: Active chat sessions
5. **Routing tables**: Learned routes through mesh

### Sync Across Transports

When a new transport connects, sync context:

```python
async def on_transport_connected(self, transport: str):
    """Sync context when new transport comes online."""
    
    # Request peer's current state
    state = await self.request_peer_state(transport)
    
    # Merge with local state
    self.merge_peer_info(state.peers)
    self.merge_endpoints(state.endpoints)
    
    # Share our state
    await self.send_local_state(transport)
```

---

## Open Source Patterns

### 1. libp2p GossipSub
**What it does**: Efficient pub/sub with topic-based routing
**Pattern to copy**:
- Mesh formation with D_lo/D_hi peer targets
- Heartbeat with IHAVE/IWANT metadata
- Peer scoring for reliability

### 2. Matrix Protocol
**What it does**: Decentralized messaging with eventual consistency
**Pattern to copy**:
- Event DAG for message ordering
- Federation model for server discovery
- Room state management

### 3. Bluetooth Mesh (SIG)
**What it does**: Standard BLE mesh networking
**Pattern to copy**:
- Managed flooding with TTL
- Friendship for low-power devices
- Proxy nodes for non-mesh devices

### 4. Apple Multipeer Connectivity
**What it does**: Automatic device discovery and connection
**Pattern to copy**:
- Seamless transport switching (WiFi/BLE)
- Invitation-based pairing
- Session management

### 5. WebRTC
**What it does**: Peer-to-peer communication
**Pattern to copy**:
- ICE for connection establishment
- STUN/TURN for NAT traversal
- Trickle ICE for fast connection

---

## Implementation Plan

### Phase 1: Mesh Persistence (This Week)
**Goal**: Mobile app remembers and auto-reconnects to meshes

- [ ] Create `SavedMesh` data class
- [ ] Implement mesh storage in DataStore
- [ ] Add "My Meshes" section to Join screen
- [ ] Show saved meshes with status (connected/disconnected)
- [ ] Implement auto-reconnect on app resume
- [ ] Add "Forget Mesh" option

### Phase 2: Connection Train (Next Week)
**Goal**: Automatic transport selection and failover

- [ ] Create `ConnectionTrain` class
- [ ] Implement parallel transport probing
- [ ] Add transport priority logic
- [ ] Implement seamless transport switching
- [ ] Add transport status to UI
- [ ] Test failover scenarios

### Phase 3: BLE Pairing UI (Week 3)
**Goal**: Simple proximity pairing without QR codes

- [ ] Add "Nearby Devices" discovery UI
- [ ] Implement pairing request flow
- [ ] Add 6-digit code display screen
- [ ] Wire up `BlePairingManager`
- [ ] Test Mac ↔ Android pairing
- [ ] Save paired device as mesh

### Phase 4: Cross-Channel Heartbeats (Week 4)
**Goal**: Reliable health monitoring across all transports

- [ ] Implement `HeartbeatManager`
- [ ] Add per-transport heartbeat loops
- [ ] Implement timeout detection
- [ ] Add heartbeat status to UI
- [ ] Test heartbeat across BLE/LAN/Relay

### Phase 5: Hardening (Week 5)
**Goal**: Rock-solid reliability

- [ ] Add comprehensive error handling
- [ ] Implement exponential backoff
- [ ] Add connection quality metrics
- [ ] Stress test with network disruptions
- [ ] Profile battery usage
- [ ] Document edge cases

---

## Success Metrics

1. **Connection Success Rate**: >99.9%
2. **Failover Time**: <3 seconds
3. **Auto-Reconnect Success**: >95%
4. **Heartbeat Reliability**: <0.1% missed
5. **Battery Impact**: <5% per hour active use

---

## File Structure

```
atmosphere/
├── mesh/
│   ├── connection_train.py      # Transport management
│   ├── heartbeat.py             # Heartbeat protocol
│   ├── persistence.py           # Mesh storage
│   └── session.py               # Session continuity
├── transport/
│   ├── ble_mac.py               # BLE transport (Mac)
│   ├── ble_pairing.py           # Pairing protocol
│   ├── lan.py                   # LAN direct
│   └── relay.py                 # Cloud relay

atmosphere-android/
├── mesh/
│   ├── ConnectionTrain.kt       # Transport management
│   ├── HeartbeatManager.kt      # Heartbeat protocol
│   └── MeshPersistence.kt       # Mesh storage
├── transport/
│   ├── BleTransport.kt          # BLE transport
│   └── LanTransport.kt          # LAN direct
├── data/
│   └── SavedMesh.kt             # Data models
└── ui/screens/
    ├── MyMeshesScreen.kt        # Saved meshes list
    └── BleParingScreen.kt       # Pairing flow
```

---

*Document Version: 1.0*
*Last Updated: 2026-02-04*
*Author: Clawd*
