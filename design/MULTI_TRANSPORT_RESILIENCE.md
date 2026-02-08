# Multi-Transport Resilience Architecture

## The Problem

Traditional mesh networks use a single transport at a time:
- If WiFi drops, you disconnect
- If relay server goes down, you're offline
- Failover requires reconnection (latency)

This doesn't work for mission-critical applications where you need **absolute resilience**.

## The Solution: Connect ALL, Use BEST, Failover INSTANT

```
┌─────────────────────────────────────────────────────────────────┐
│                    RESILIENT MESH NODE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              MESSAGE ROUTER                              │   │
│  │  • Scores all active transports in real-time            │   │
│  │  • Routes via BEST (lowest latency + highest reliability)│   │
│  │  • Instant failover (no reconnection needed)            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│         ┌──────────────────┼──────────────────┐                │
│         ▼                  ▼                  ▼                │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐           │
│  │   LAN/TCP  │    │   RELAY    │    │  BLE MESH  │  ...      │
│  │  ~2-5ms    │    │  ~100ms    │    │  ~50-80ms  │           │
│  │  ████████  │    │  ████████  │    │  ████████  │           │
│  │  CONNECTED │    │  CONNECTED │    │  STANDBY   │           │
│  └────────────┘    └────────────┘    └────────────┘           │
│         │                  │                  │                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              HEALTH MONITOR (Background)                 │   │
│  │  • Pings every transport every 10s                      │   │
│  │  • Tracks: latency, packet loss, battery cost           │   │
│  │  • Auto-reconnects failed transports                    │   │
│  │  • Promotes/demotes based on real metrics               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Transport Types

| Transport | Latency | Battery | Bandwidth | Use Case |
|-----------|---------|---------|-----------|----------|
| **LAN/mDNS** | 1-5ms | Low | 100+ Mbps | Same network, best choice |
| **WiFi Direct** | 5-20ms | Medium | 50+ Mbps | Nearby, no infrastructure |
| **BLE Mesh** | 50-100ms | Very Low | 1 Mbps | Offline, short range |
| **Matter/Thread** | 30-80ms | Low | 5 Mbps | Smart home integration |
| **Cloud Relay** | 100-500ms | Low | 10+ Mbps | Anywhere, NAT traversal |

## Transport Scoring

Each transport is scored in real-time based on:

```
score = 0.4 * latency_score + 0.4 * reliability_score + 0.2 * battery_score

latency_score = max(0, 1 - (latency_ms / 500))  // 0ms=1.0, 500ms=0.0
reliability_score = 1 - packet_loss_ratio       // 0% loss=1.0, 100%=0.0
battery_score = 1 - battery_cost                // Low cost=high score

// Penalty for recent failures (decays over 30 seconds)
if (recent_failure && consecutive_failures > 0):
    score -= 0.2 * (1 - seconds_since_failure / 30)
```

## Connection Lifecycle

### 1. Peer Discovery
When a peer is discovered (via mDNS, relay, QR scan):
- Collect all known addresses (LAN IP, relay URL, BLE address, etc.)
- Initiate connections to ALL simultaneously (not sequentially)

### 2. Parallel Connection
```python
async def connect_peer(peer_id, peer_info):
    tasks = []
    
    if peer_info.lan_address:
        tasks.append(connect_lan(peer_id, peer_info.lan_address))
    if peer_info.relay_url:
        tasks.append(connect_relay(peer_id, peer_info.relay_url))
    if peer_info.ble_address:
        tasks.append(connect_ble(peer_id, peer_info.ble_address))
    
    # Connect ALL in parallel - don't wait for one to fail
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful = sum(1 for r in results if r is True)
    
    log.info(f"Connected to {peer_id} via {successful}/{len(tasks)} transports")
```

### 3. Message Routing
```python
async def send(peer_id, message):
    # Get transports sorted by score (best first)
    transports = get_transports_by_score(peer_id)
    
    for transport in transports:
        if not transport.is_healthy:
            continue
        
        try:
            await transport.send(message)
            transport.metrics.record_success()
            return True
        except TransportError:
            transport.metrics.record_failure()
            # Continue to next transport (INSTANT failover)
            continue
    
    raise AllTransportsFailedError()
```

### 4. Health Monitoring
Background task runs every 10 seconds:

```python
async def health_monitor():
    while running:
        for peer_id, transports in all_transports.items():
            for transport in transports:
                try:
                    # Ping and measure actual latency
                    latency = await transport.ping(timeout=5.0)
                    transport.metrics.record_latency(latency)
                except TimeoutError:
                    transport.metrics.record_failure()
                    if transport.metrics.consecutive_failures >= 3:
                        # Mark as failed, schedule reconnect
                        transport.state = FAILED
                        schedule_reconnect(peer_id, transport.type)
        
        await asyncio.sleep(10)
```

### 5. Auto-Reconnection
Failed transports are automatically reconnected in background:

```python
async def reconnect(peer_id, transport_type):
    await asyncio.sleep(5)  # Delay before retry
    
    address = get_stored_address(peer_id, transport_type)
    success = await connect_transport(peer_id, transport_type, address)
    
    if success:
        stats.reconnects += 1
        log.info(f"Reconnected to {peer_id} via {transport_type}")
```

## API Endpoint: `/api/mesh/transports`

Get real-time transport status:

```json
{
  "node_id": "node-abc123",
  "transport_types": ["lan", "relay", "ble", "wifi_direct", "matter"],
  "enabled": {
    "lan": true,
    "relay": true,
    "ble": false,
    "wifi_direct": false,
    "matter": false
  },
  "global_stats": {
    "messages_sent": 1234,
    "messages_received": 5678,
    "failovers": 12,
    "reconnects": 5
  },
  "relay": {
    "connected": true,
    "url": "wss://atmosphere-relay-production.up.railway.app",
    "peer_count": 3
  },
  "peers": {
    "peer-xyz789": {
      "reachable": true,
      "transports": {
        "lan": {
          "state": "connected",
          "latency_ms": 2.3,
          "packet_loss": 0.0,
          "score": 0.95,
          "consecutive_failures": 0
        },
        "relay": {
          "state": "connected",
          "latency_ms": 145.7,
          "packet_loss": 0.01,
          "score": 0.58,
          "consecutive_failures": 0
        }
      },
      "best_transport": "lan"
    }
  }
}
```

## Failure Scenarios

### Scenario 1: WiFi Drops
- **Before**: Disconnect, wait for reconnect, lose messages
- **After**: Relay already connected, instant failover, zero message loss

### Scenario 2: Relay Server Restart
- **Before**: All remote nodes offline until relay recovers
- **After**: LAN peers unaffected, relay auto-reconnects in background

### Scenario 3: Network Congestion
- **Before**: High latency, dropped packets, poor UX
- **After**: Health monitor detects, routes via less congested transport

### Scenario 4: Mobile Device Moving
- **Before**: Constant reconnections as WiFi/cellular changes
- **After**: Multiple transports adapt seamlessly, best one auto-selected

## Implementation Files

### Python (Mac/Server)
- `atmosphere/network/resilient_transport.py` - Core manager + metrics
- `atmosphere/network/transports/lan.py` - LAN WebSocket transport
- `atmosphere/network/transports/relay.py` - Relay WebSocket transport
- `atmosphere/network/mesh_connection.py` - High-level mesh orchestration

### Kotlin (Android)
- `network/ResilientTransportManager.kt` - Core manager + metrics
- `network/WebSocketTransport.kt` - WebSocket transport (LAN + Relay)

## Future Transports

### BLE Mesh (Planned)
- Range: ~100m
- Bandwidth: ~1 Mbps
- Battery: Very low
- Use case: Offline mesh in buildings/events

### WiFi Direct (Planned)
- Range: ~200m
- Bandwidth: ~50 Mbps
- Battery: Medium
- Use case: P2P without infrastructure

### Matter/Thread (Planned)
- Range: ~30m per hop, mesh extends
- Bandwidth: ~5 Mbps
- Battery: Low
- Use case: Smart home device integration

## Design Principles

1. **Connect ALL available transports** - Don't wait for failures
2. **Route via BEST** - Based on real-time metrics, not static priority
3. **Failover INSTANT** - Already connected, no reconnection delay
4. **Health monitor continuously** - Detect problems before they affect users
5. **Reconnect automatically** - Self-healing network
6. **Battery aware** - Factor in power cost for mobile devices
7. **Audit everything** - Stats for debugging and optimization
