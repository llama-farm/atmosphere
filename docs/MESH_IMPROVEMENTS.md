# Atmosphere Mesh Networking - Improvements & Best Practices

## Research Summary

Based on analysis of open-source mesh implementations and Bluetooth SIG standards:

### Current State ✅
Our implementation already follows many best practices:
- **TTL-based flood routing** - Messages have hop limits (default 5)
- **Message caching/deduplication** - LRU cache prevents loops
- **Fragmentation/reassembly** - Handles messages > MTU
- **CBOR serialization** - Compact binary encoding
- **Dual-mode operation** - Both scanner (central) and advertiser (peripheral)
- **Cross-platform UUIDs** - Mac now matches Android

### Recommended Improvements

## 1. Managed Flooding Optimizations

### 1.1 Heartbeat Messages (Bluetooth SIG Pattern)
```python
class HeartbeatManager:
    """
    Periodic heartbeat messages for network health.
    - Indicates node is alive
    - Shares current TTL/hop count for path optimization
    - Helps detect topology changes
    """
    def __init__(self, interval_sec: int = 60):
        self.interval = interval_sec
        self.peer_hop_counts: Dict[str, int] = {}  # peer_id -> min_hops
    
    async def send_heartbeat(self, transport):
        """Send heartbeat with features bitmap and hop count."""
        # Receivers can learn optimal paths from heartbeat TTL delta
```

### 1.2 Relay Node Designation
Not all nodes need to relay. Low-power devices (phones) can disable relay:
```python
# Current: all nodes relay
# Improved: optional relay feature
class NodeFeatures(IntFlag):
    RELAY = 0x01      # Can relay messages
    PROXY = 0x02      # GATT proxy for non-mesh BLE devices  
    FRIEND = 0x04     # Can cache for low-power nodes
    LOW_POWER = 0x08  # Low-power mode (doesn't relay)
```

### 1.3 Trickle-Based Gossip (RFC 6206)
Instead of immediate rebroadcast, use probabilistic delay:
```python
class TrickleTimer:
    """
    Trickle algorithm for efficient flooding.
    - Suppresses redundant transmissions
    - Adapts to network density
    """
    def __init__(self, i_min=100, i_max=60000, k=3):
        self.i_min = i_min    # Min interval (ms)
        self.i_max = i_max    # Max interval (ms)
        self.k = k            # Redundancy constant
        self.i = i_min
        self.counter = 0
    
    def on_consistent(self):
        """Heard same message - increment counter."""
        self.counter += 1
    
    def on_inconsistent(self):
        """Heard different/new message - reset timer."""
        self.i = self.i_min
    
    def should_transmit(self) -> bool:
        """Transmit only if counter < k."""
        return self.counter < self.k
```

## 2. Routing Enhancements

### 2.1 AODV-Lite (On-Demand Distance Vector)
For larger meshes, add optional routing discovery:
```python
class RouteEntry:
    destination: str
    next_hop: str
    hop_count: int
    seq_num: int
    lifetime: float

class AodvRouter:
    """
    Lightweight AODV for directed messaging.
    - Discovers routes on-demand (not proactive)
    - Maintains routing table only for active destinations
    - Falls back to flooding if route unknown
    """
    routes: Dict[str, RouteEntry] = {}
    
    async def route_request(self, dest_id: str):
        """Broadcast RREQ, wait for RREP."""
        
    async def send_to(self, dest_id: str, data: bytes):
        """Send via route if known, else RREQ then send."""
```

### 2.2 Link Quality Metrics
Track RSSI and packet success rate for smarter routing:
```python
@dataclass
class LinkMetrics:
    rssi_avg: float = -80
    rssi_samples: List[int] = field(default_factory=list)
    packets_sent: int = 0
    packets_acked: int = 0
    
    @property
    def delivery_ratio(self) -> float:
        if self.packets_sent == 0:
            return 1.0
        return self.packets_acked / self.packets_sent
    
    @property
    def link_cost(self) -> float:
        """Lower is better. Combines RSSI and reliability."""
        rssi_factor = max(0, (self.rssi_avg + 100) / 60)  # 0-1
        return 1 / (rssi_factor * self.delivery_ratio + 0.01)
```

## 3. Security Enhancements

### 3.1 Network Key (Bluetooth Mesh Pattern)
All nodes in a mesh share a network key:
```python
class MeshSecurity:
    """
    Bluetooth Mesh-style security.
    - Network key (shared by all nodes) - obfuscates headers
    - Application key (per-app) - encrypts payloads
    - Device key (per-node) - for provisioning
    """
    def __init__(self, network_key: bytes):
        self.net_key = network_key
        self.privacy_key = self._derive_privacy_key(network_key)
    
    def obfuscate_header(self, header: bytes, iv_index: int) -> bytes:
        """Obfuscate header to prevent tracking."""
        
    def encrypt_payload(self, payload: bytes, app_key: bytes) -> bytes:
        """AES-CCM encrypt with 4-byte MIC."""
```

### 3.2 Replay Protection
```python
class ReplayProtection:
    """
    Per-source sequence number tracking.
    Reject messages with old sequence numbers.
    """
    min_seq: Dict[str, int] = {}  # source_id -> min acceptable seq
    
    def is_valid(self, source_id: str, seq: int) -> bool:
        min_seq = self.min_seq.get(source_id, 0)
        if seq <= min_seq:
            return False
        self.min_seq[source_id] = seq
        return True
```

## 4. Friendship (Low-Power Support)

For battery-powered devices (phones), implement friendship:
```python
class FriendNode:
    """
    Caches messages for low-power nodes (LPNs).
    LPN sleeps most of the time, wakes to poll friend.
    """
    def __init__(self, lpn_id: str, receive_window_ms: int):
        self.lpn_id = lpn_id
        self.message_cache: List[bytes] = []
        self.receive_window = receive_window_ms
    
    def cache_message(self, msg: bytes):
        """Store message for LPN."""
        self.message_cache.append(msg)
    
    def on_poll(self) -> List[bytes]:
        """LPN polling - return cached messages."""
        cached = self.message_cache
        self.message_cache = []
        return cached

class LowPowerNode:
    """
    Low-power node that relies on friend for messages.
    """
    friend_id: str = None
    poll_interval_ms: int = 30000  # Poll every 30s
    
    async def establish_friendship(self, friend_id: str):
        """Negotiate friendship with powered node."""
        
    async def poll_friend(self) -> List[bytes]:
        """Wake up, poll friend, process messages, sleep."""
```

## 5. Proxy Support (GATT Bridge)

Allow non-mesh BLE devices (older phones) to interact:
```python
class ProxyNode:
    """
    GATT proxy for non-mesh Bluetooth devices.
    Accepts connections, translates to/from mesh protocol.
    """
    # Already partially implemented via GATT server
    # Enhancement: full Proxy Protocol PDU support
```

## 6. Transport Priority Improvements

### Current Transport Hierarchy
```
1. LAN (lowest latency when available)
2. BLE Mesh (works offline)
3. Cloud Relay (always available)
```

### Improved Transport Selection
```python
class TransportSelector:
    """
    Smart transport selection based on:
    - Latency requirements
    - Power constraints
    - Message size
    - Reliability needs
    """
    def select_transport(
        self,
        message_size: int,
        priority: str,  # "realtime", "normal", "background"
        power_constrained: bool
    ) -> str:
        if priority == "realtime" and self.lan_available:
            return "lan"
        if power_constrained and self.ble_friend_available:
            return "ble_friendship"
        if message_size > 10000:  # Large messages
            return "lan" if self.lan_available else "relay"
        return "ble" if self.ble_available else "relay"
```

## Implementation Priority

### Phase 1 (This Week)
1. ✅ UUID alignment (done)
2. [ ] Basic heartbeat messages
3. [ ] Link quality tracking (RSSI)
4. [ ] Test BLE discovery end-to-end

### Phase 2 (Next Week)
1. [ ] Trickle-based gossip
2. [ ] Relay node designation
3. [ ] Network key encryption

### Phase 3 (Future)
1. [ ] AODV routing for large meshes
2. [ ] Friendship for low-power
3. [ ] Full proxy protocol

## Open Source References

- **Bluetooth Mesh SDK (Nordic)**: https://developer.nordicsemi.com/nRF_Connect_SDK/doc/latest/nrf/protocols/bt_mesh/index.html
- **Zephyr Bluetooth Mesh**: https://docs.zephyrproject.org/latest/connectivity/bluetooth/mesh.html
- **Android Bluetooth Mesh**: https://developer.android.com/guide/topics/connectivity/bluetooth/ble-mesh
- **BLEmesh Paper**: https://www.researchgate.net/publication/307632317
- **Trickle RFC**: https://datatracker.ietf.org/doc/html/rfc6206

## Metrics to Track

```python
@dataclass
class MeshMetrics:
    messages_sent: int = 0
    messages_received: int = 0
    messages_relayed: int = 0
    messages_dropped: int = 0  # TTL expired
    messages_deduplicated: int = 0  # Loop prevention
    avg_hop_count: float = 0
    peer_count: int = 0
    avg_rssi: float = 0
```

---

*Updated: 2026-02-04*
