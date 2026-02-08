# Atmosphere Network Module

Internet-scale mesh networking components.

## Overview

This module provides the networking stack for Atmosphere to work across the internet, not just local networks.

### Components

1. **`stun.py`** - STUN client for NAT discovery
2. **`nat.py`** - NAT traversal and UDP hole punching
3. **`relay.py`** - WebSocket relay server for fallback connectivity

## Quick Reference

### Discover Public Endpoint

```python
from atmosphere.network import discover_public_ip

endpoint = await discover_public_ip()
print(f"Public: {endpoint.ip}:{endpoint.port}")
```

### NAT Traversal (P2P)

```python
from atmosphere.network import NATTraversal

traversal = NATTraversal(local_port=7777)
await traversal.start()

attempt = await traversal.punch_hole(
    peer_id="peer-123",
    remote_host="203.0.113.10",
    remote_port=7777,
)

if attempt.is_direct:
    print("✓ P2P connection established")
    await traversal.send_to_peer("peer-123", b"hello")

await traversal.stop()
```

### Relay Server

```python
from atmosphere.network import RelayServer

server = RelayServer(host="0.0.0.0", port=8080)
await server.start()
# Server runs, relays traffic between clients
await server.stop()
```

### Relay Client

```python
from atmosphere.network import RelayClient

client = RelayClient("ws://relay.example.com:8080", "session-id")
await client.connect()

await client.send(b"data")
received = await client.receive()

await client.disconnect()
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Internet Mesh Stack                       │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Relay Fallback                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  WebSocket Relay (relay.py)                          │   │
│  │  - Fallback when P2P fails                           │   │
│  │  - Public relay servers                              │   │
│  │  - Session-based forwarding                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                             ↑                                │
│  Layer 2: NAT Traversal                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  UDP Hole Punching (nat.py)                          │   │
│  │  - Direct P2P connections                            │   │
│  │  - Simultaneous packet exchange                      │   │
│  │  - Connection state management                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                             ↑                                │
│  Layer 1: Discovery                                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  STUN Client (stun.py)                               │   │
│  │  - Public IP discovery                               │   │
│  │  - NAT mapping detection                             │   │
│  │  - Multiple STUN servers                             │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Connection Flow

```
1. Node A and Node B both discover their public endpoints via STUN
   A: STUN → 203.0.113.10:7777
   B: STUN → 198.51.100.20:8888

2. Nodes exchange endpoints (via join code or signaling)
   A → B: "I'm at 203.0.113.10:7777"
   B → A: "I'm at 198.51.100.20:8888"

3. Both nodes attempt UDP hole punching
   A → 198.51.100.20:8888 (punch)
   B → 203.0.113.10:7777 (punch)
   
4. Success paths:
   
   ✓ P2P Success:
     NAT allows bidirectional flow
     Direct connection established
     
   ✗ P2P Failure:
     Symmetric NAT or firewall blocks
     Fall back to relay server
     
     A → Relay ← B
     Traffic proxied through relay
```

## NAT Types

| Type | P2P Success Rate | Notes |
|------|------------------|-------|
| No NAT | 100% | Direct public IP |
| Full Cone | 95% | Best for P2P |
| Restricted Cone | 70% | Usually works |
| Port Restricted | 50% | Hit or miss |
| Symmetric | 20% | Usually needs relay |

## Performance

### STUN Discovery
- **Latency:** ~100-500ms (one-time)
- **Bandwidth:** ~1 KB
- **CPU:** Negligible
- **Caching:** Yes (per session)

### NAT Traversal
- **Latency:** 10-50ms (internet RTT)
- **Bandwidth:** Unlimited (your connection)
- **CPU:** Low (event-driven)
- **Overhead:** ~2%

### Relay
- **Latency:** +20-50ms (relay hop)
- **Bandwidth:** Limited by relay server
- **CPU:** Low (WebSocket)
- **Overhead:** ~5%

## Configuration

### STUN Servers

Modify `STUN_SERVERS` in `stun.py`:

```python
STUN_SERVERS = [
    ("stun.l.google.com", 19302),
    ("stun.cloudflare.com", 3478),
    ("your-stun.example.com", 3478),
]
```

### Relay Servers

Modify `DEFAULT_RELAYS` in `relay.py`:

```python
DEFAULT_RELAYS = [
    RelayInfo(url="wss://relay-us.example.com:8080", region="us-east"),
    RelayInfo(url="wss://relay-eu.example.com:8080", region="eu-west"),
]
```

## Security Considerations

### STUN
- Uses public STUN servers (Google, Cloudflare)
- Only reveals your public IP (already visible)
- No sensitive data transmitted

### NAT Traversal
- Direct P2P connection (no intermediary)
- Potential for traffic sniffing on untrusted networks
- Use TLS/encryption for sensitive data

### Relay
- Traffic visible to relay server
- Use `wss://` (WebSocket Secure) for encryption
- Run your own relay for sensitive applications
- Future: end-to-end encryption

## Testing

### Unit Tests

```bash
cd ~/clawd/projects/atmosphere
pytest tests/test_internet_network.py
```

### Integration Test

```bash
# Terminal 1: Start relay server
python -c "
import asyncio
from atmosphere.network import RelayServer

async def main():
    server = RelayServer(host='127.0.0.1', port=8080)
    await server.start()
    await asyncio.sleep(3600)

asyncio.run(main())
"

# Terminal 2: Test client
python -c "
import asyncio
from atmosphere.network import RelayClient

async def main():
    client = RelayClient('ws://127.0.0.1:8080', 'test-123')
    if await client.connect():
        print('✓ Connected')
        await client.send(b'hello')
    await client.disconnect()

asyncio.run(main())
"
```

### Smoke Test

```bash
python tests/test_internet_network.py
```

## Troubleshooting

### STUN Discovery Fails

**Symptoms:**
- `discover_public_ip()` returns `None`
- Network info shows no public endpoint

**Causes:**
- No internet connection
- Firewall blocking UDP ports 3478, 19302
- Corporate network blocking STUN

**Solutions:**
- Check internet: `ping 8.8.8.8`
- Try different STUN server
- Use manual public IP
- Contact network admin

### P2P Connection Fails

**Symptoms:**
- `punch_hole()` times out
- Connection state stays `PUNCHING`

**Causes:**
- Symmetric NAT on both sides
- Firewall blocking UDP
- ISP restrictions

**Solutions:**
- Use relay fallback (automatic)
- Check NAT type: `atmosphere network`
- Configure port forwarding
- Use VPN/Tailscale

### Relay Connection Fails

**Symptoms:**
- `RelayClient.connect()` returns `False`
- WebSocket connection refused

**Causes:**
- Relay server down
- Firewall blocking WebSocket
- Network issues

**Solutions:**
- Check relay health: `curl http://relay:8080/health`
- Try different relay
- Run local relay for testing
- Check firewall rules

## Development

### Adding Features

To add new network features:

1. **STUN features** → Edit `stun.py`
2. **P2P features** → Edit `nat.py`
3. **Relay features** → Edit `relay.py`

Export new functions in `__init__.py`.

### Code Style

- Use async/await for I/O
- Type hints on public APIs
- Docstrings for all functions
- Log at appropriate levels

### Testing Checklist

- [ ] Unit tests pass
- [ ] Smoke test passes
- [ ] Integration test with real servers
- [ ] Documentation updated
- [ ] Example code tested

## References

- RFC 5389: STUN
- RFC 5766: TURN  
- RFC 8445: ICE
- WebRTC Data Channels

## Future Work

- [ ] IPv6 support
- [ ] ICE (full implementation)
- [ ] TURN protocol
- [ ] End-to-end encryption
- [ ] Connection quality metrics
- [ ] Bandwidth optimization
- [ ] Multi-relay fallback
- [ ] NAT type detection improvements
