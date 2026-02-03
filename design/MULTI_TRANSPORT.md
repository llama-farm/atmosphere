# Atmosphere Multi-Transport Layer

**Version:** 1.0.0  
**Status:** Implementation  
**Date:** 2026-02-03

## Overview

Atmosphere uses **5 independent transport methods** with automatic fallback and continuous optimization. All transports are enabled by default with owner opt-out.

```
┌─────────────────────────────────────────────────────────────────┐
│                     TRANSPORT PRIORITY                          │
├─────────────────────────────────────────────────────────────────┤
│  1. Local Network (LAN)     - Fastest, lowest latency          │
│  2. WiFi Direct (P2P)       - No router needed                 │
│  3. BLE Mesh                - Works offline, low power         │
│  4. Matter                  - Smart home devices               │
│  5. Relay Server            - Always works, fallback           │
└─────────────────────────────────────────────────────────────────┘
```

## Architecture

```
                                  ┌─────────────────────┐
                                  │   TransportManager  │
                                  │  (Orchestrator)     │
                                  └──────────┬──────────┘
                                             │
             ┌───────────────────────────────┼───────────────────────────────┐
             │              │                │               │               │
     ┌───────▼───────┐ ┌────▼─────┐ ┌───────▼───────┐ ┌─────▼─────┐ ┌──────▼──────┐
     │  LANTransport │ │WiFiDirect│ │  BLETransport │ │  Matter   │ │   Relay     │
     │  (WebSocket)  │ │Transport │ │   (Mesh)      │ │ Transport │ │  Transport  │
     └───────────────┘ └──────────┘ └───────────────┘ └───────────┘ └─────────────┘
             │              │                │               │               │
             └──────────────┴────────────────┴───────────────┴───────────────┘
                                             │
                                    ┌────────▼────────┐
                                    │   ConnectionPool │
                                    │  (Per-Peer)     │
                                    └─────────────────┘
```

## Transport Specifications

### 1. Local Network (LAN WebSocket)
- **Priority:** 1 (highest)
- **Latency:** <5ms
- **Bandwidth:** ~1Gbps
- **Discovery:** mDNS/Bonjour
- **Port:** 11450 (gossip), 11451 (API)
- **Security:** Mesh token verification
- **Works:** Same WiFi network

```json
{
  "type": "lan",
  "enabled": true,
  "discovery": "mdns",
  "port": 11450,
  "tls": false
}
```

### 2. WiFi Direct (P2P)
- **Priority:** 2
- **Latency:** <10ms  
- **Bandwidth:** ~250Mbps
- **Discovery:** WiFi Direct service discovery
- **Platform:** Android native, Mac (limited)
- **Security:** WPA2 + mesh token
- **Works:** No router needed, ~200m range

```json
{
  "type": "wifi_direct",
  "enabled": true,
  "group_name": "atmosphere_{mesh_id}",
  "auto_accept": false
}
```

### 3. BLE Mesh
- **Priority:** 3
- **Latency:** 50-100ms
- **Bandwidth:** ~1Mbps
- **Discovery:** BLE advertising
- **Topology:** True mesh (multi-hop)
- **Security:** Mesh token in encrypted payload
- **Works:** Offline, low power, ~30m per hop

```json
{
  "type": "ble_mesh",
  "enabled": true,
  "advertising": true,
  "scanning": true,
  "max_hops": 3,
  "ttl": 5
}
```

### 4. Matter
- **Priority:** 4
- **Latency:** 20-50ms
- **Bandwidth:** Varies by device
- **Discovery:** Matter commissioning
- **Devices:** Thread, WiFi, Ethernet
- **Security:** Matter certificates
- **Works:** Smart home devices as capabilities

```json
{
  "type": "matter",
  "enabled": true,
  "fabric_id": null,
  "auto_commission": false
}
```

### 5. Relay Server
- **Priority:** 5 (fallback)
- **Latency:** 50-200ms (depends on server location)
- **Bandwidth:** ~100Mbps
- **Discovery:** Static URL
- **Security:** Mesh tokens (see below)
- **Works:** Always, NAT traversal

```json
{
  "type": "relay",
  "enabled": true,
  "url": "wss://atmosphere-relay-production.up.railway.app",
  "fallback_urls": [
    "wss://relay-us-west.atmosphere.dev",
    "wss://relay-eu.atmosphere.dev"
  ]
}
```

## Relay Security (CRITICAL)

### Problem
Current relay accepts anyone with mesh_id. A random attacker could:
1. Guess mesh_ids (only 16 hex chars)
2. Join arbitrary meshes
3. Intercept traffic

### Solution: Mesh Tokens

Every mesh has a **signing key** held by founders. Joining requires a **signed token**.

```python
# Token structure
{
    "mesh_id": "0b82206b236bd66c",
    "node_id": "69ff1fa7cc80d0e0",
    "issued_at": 1738540800,
    "expires_at": 1738627200,  # 24h default
    "capabilities": ["chat", "llm"],
    "signature": "base64..."  # Ed25519 signature from mesh founder
}
```

### Token Issuance Flow
```
┌─────────────┐     QR Code / Deep Link      ┌─────────────┐
│   Founder   │ ──────────────────────────── │  New Node   │
│  (Mac/Phone)│     Contains signed token     │  (Android)  │
└─────────────┘                               └─────────────┘
                                                    │
                                                    ▼
                                          ┌─────────────────┐
                                          │  Relay Server   │
                                          │ Verifies token  │
                                          │ before allowing │
                                          │ mesh access     │
                                          └─────────────────┘
```

### Relay Verification
```python
# Server-side verification
async def verify_join_token(token: str, mesh_id: str) -> bool:
    """
    Verify a join token against the mesh's public key.
    
    The relay caches mesh public keys from founders.
    """
    try:
        data = decode_token(token)
        
        # Check expiration
        if data["expires_at"] < time.time():
            return False
        
        # Check mesh_id matches
        if data["mesh_id"] != mesh_id:
            return False
        
        # Verify signature against cached mesh public key
        mesh_pubkey = get_mesh_public_key(mesh_id)
        if not mesh_pubkey:
            # First founder registers the mesh
            return False
            
        return verify_signature(
            mesh_pubkey,
            data["signature"],
            canonical_token_bytes(data)
        )
    except Exception:
        return False
```

### Founder Registration
When a founder first connects, they register the mesh:
```json
{
    "type": "register_mesh",
    "mesh_id": "0b82206b236bd66c",
    "mesh_public_key": "base64...",
    "founder_proof": "base64...",  // Signed by founder's key
    "name": "home-mesh"
}
```

## Connection Pool

Each peer maintains a **ConnectionPool** with multiple active transports:

```python
class ConnectionPool:
    """Manages multiple transport connections to a single peer."""
    
    def __init__(self, peer_id: str):
        self.peer_id = peer_id
        self.connections: Dict[str, Transport] = {}  # type -> transport
        self.metrics: Dict[str, TransportMetrics] = {}
        self.preferred: Optional[str] = None
    
    async def send(self, message: bytes) -> bool:
        """Send via best available transport."""
        # Try preferred first
        if self.preferred and self.preferred in self.connections:
            try:
                await self.connections[self.preferred].send(message)
                return True
            except TransportError:
                pass
        
        # Fallback chain
        for transport_type in TRANSPORT_PRIORITY:
            if transport_type in self.connections:
                try:
                    await self.connections[transport_type].send(message)
                    self.preferred = transport_type
                    return True
                except TransportError:
                    continue
        
        return False
    
    def update_metrics(self, transport_type: str, latency_ms: float, success: bool):
        """Update transport metrics for optimization."""
        metrics = self.metrics.setdefault(transport_type, TransportMetrics())
        metrics.add_sample(latency_ms, success)
        self._recalculate_preferred()
```

## Continuous Optimization

The TransportManager continuously:

1. **Probes** all transports every 30s
2. **Measures** latency, packet loss, bandwidth
3. **Ranks** transports by composite score
4. **Switches** when better option available

```python
def calculate_transport_score(metrics: TransportMetrics) -> float:
    """
    Score a transport (higher = better).
    
    Factors:
    - Latency (40%)
    - Reliability (30%)
    - Bandwidth (20%)
    - Power cost (10%)
    """
    latency_score = max(0, 100 - metrics.avg_latency_ms)
    reliability_score = metrics.success_rate * 100
    bandwidth_score = min(100, metrics.bandwidth_mbps)
    power_score = 100 - (metrics.power_mw / 10)
    
    return (
        latency_score * 0.4 +
        reliability_score * 0.3 +
        bandwidth_score * 0.2 +
        power_score * 0.1
    )
```

## Configuration

### ~/.atmosphere/config.json
```json
{
  "transports": {
    "lan": {
      "enabled": true,
      "port": 11450,
      "mdns": true
    },
    "wifi_direct": {
      "enabled": true,
      "auto_accept": false
    },
    "ble_mesh": {
      "enabled": true,
      "advertising": true,
      "scanning": true,
      "max_hops": 3
    },
    "matter": {
      "enabled": true,
      "auto_commission": false
    },
    "relay": {
      "enabled": true,
      "url": "wss://atmosphere-relay-production.up.railway.app"
    }
  },
  "optimization": {
    "probe_interval_ms": 30000,
    "switch_threshold": 20,
    "prefer_local": true
  }
}
```

### UI Options
The mesh settings screen shows:
- Toggle for each transport (all ON by default)
- Current active transport per peer
- Latency/quality indicators
- "Prefer local only" mode (disables relay)

## Implementation Priority

1. **Relay Security** (Critical) - Add token verification
2. **LAN WebSocket** (Done) - Already working
3. **Relay** (Done) - Add security layer
4. **BLE Mesh** (Android) - Most complex
5. **WiFi Direct** (Android) - Platform-specific
6. **Matter** (Later) - Requires chip SDK

## Message Format

All transports use the same message format:
```python
@dataclass
class MeshMessage:
    """Universal message format across all transports."""
    type: str  # "gossip", "direct", "broadcast", "llm_request", etc.
    from_node: str
    to_node: Optional[str]  # None = broadcast
    payload: bytes
    ttl: int = 5
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    signature: str = ""  # Ed25519 signature
    
    def to_bytes(self) -> bytes:
        return msgpack.packb(asdict(self))
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "MeshMessage":
        return cls(**msgpack.unpackb(data))
```

## Error Handling

```python
class TransportError(Exception):
    """Base transport error."""
    pass

class ConnectionLost(TransportError):
    """Connection to peer lost."""
    pass

class TransportUnavailable(TransportError):
    """Transport not available on this device."""
    pass

class AuthenticationFailed(TransportError):
    """Token verification failed."""
    pass
```

## Security Summary

| Transport | Authentication | Encryption | Notes |
|-----------|---------------|------------|-------|
| LAN WS | Mesh token | TLS optional | Same network = trust |
| WiFi Direct | WPA2 + token | WPA2 | Group password |
| BLE Mesh | Token in payload | AES-128 | BLE encryption |
| Matter | Certificates | CASE | Full PKI |
| Relay | Mesh token | TLS | Server verifies |

## Next Steps

1. Implement `TransportManager` class
2. Add token verification to relay
3. Update QR code to include signed token
4. Add transport selection UI
5. Implement BLE transport (Android)
6. Implement WiFi Direct transport (Android)
