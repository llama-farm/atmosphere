# Internet-Scale Mesh Networking

Atmosphere now supports mesh networking across the internet, not just local networks.

## Overview

The internet networking stack consists of three layers:

1. **STUN Client** - Discovers your public IP and port via STUN servers
2. **NAT Traversal** - Establishes direct P2P connections via UDP hole punching
3. **Relay Server** - Provides fallback connectivity when P2P fails

## Quick Start

### 1. Check Your Network

```bash
atmosphere network
```

This shows:
- Local IP and port
- Public IP and port (via STUN)
- NAT status
- Internet reachability

### 2. Create a Mesh with Internet Support

```bash
atmosphere init my-mesh
atmosphere serve --port 7777
```

In another terminal on the same machine:

```bash
atmosphere join
```

This generates a join code with your public endpoint included.

### 3. Join from a Remote Machine

On a different network (e.g., Rob in Portland, Matt in Seattle):

```bash
# Matt's machine (Seattle)
atmosphere join <join-code-from-rob>
```

The join process:
1. Attempts direct P2P connection via hole punching
2. Falls back to relay if P2P fails
3. Establishes mesh connectivity either way

## Architecture

### STUN (Public IP Discovery)

STUN (Session Traversal Utilities for NAT) discovers your public IP and port:

```python
from atmosphere.network import discover_public_ip

endpoint = await discover_public_ip()
print(f"Public IP: {endpoint.ip}:{endpoint.port}")
```

**STUN Servers Used:**
- `stun.l.google.com:19302`
- `stun1.l.google.com:19302`
- `stun2.l.google.com:19302`
- `stun.cloudflare.com:3478`
- `stun.stunprotocol.org:3478`

**Caching:** Results are cached for the session. STUN is lightweight but you don't need to call it constantly.

### NAT Traversal (UDP Hole Punching)

NAT traversal establishes direct P2P connections:

```python
from atmosphere.network import NATTraversal

traversal = NATTraversal(local_port=7777)
await traversal.start()

# Attempt connection to peer
attempt = await traversal.punch_hole(
    peer_id="peer-123",
    remote_host="203.0.113.10",
    remote_port=7777,
    timeout=10.0,
)

if attempt.is_direct:
    print("✓ Direct P2P connection established!")
else:
    print("✗ P2P failed, need relay")

await traversal.stop()
```

**How it works:**
1. Both peers discover their public endpoints (STUN)
2. Peers exchange endpoints via a signaling channel
3. Both peers simultaneously send UDP packets to each other
4. NAT creates bidirectional port mappings
5. Packets flow directly between peers

**Success Rate:**
- **Full Cone NAT:** ~95% success
- **Restricted NAT:** ~70% success  
- **Symmetric NAT:** ~20% success (needs relay)

### Relay Server (Fallback)

When P2P fails, traffic is relayed through a public server:

```python
from atmosphere.network import RelayServer, RelayClient

# On a public server
server = RelayServer(host="0.0.0.0", port=8080)
await server.start()

# On clients
client_a = RelayClient("ws://relay.example.com:8080", "session-123")
client_b = RelayClient("ws://relay.example.com:8080", "session-123")

await client_a.connect()
await client_b.connect()

# Messages are relayed
await client_a.send(b"hello")
msg = await client_b.receive()  # b"hello"
```

**Protocol:** WebSocket-based relay. Simple, efficient, works everywhere.

**Running Your Own Relay:**
```bash
# On a public server
atmosphere relay --host 0.0.0.0 --port 8080
```

**Health Check:**
```bash
curl http://relay.example.com:8080/health
# {"status": "ok", "sessions": 3, "timestamp": 1234567890}
```

## Join Tokens

Join tokens now include internet connectivity information:

```json
{
  "mesh_id": "mesh-abc123",
  "mesh_name": "my-mesh",
  "endpoint": "192.168.1.100:7777",
  "public_endpoint": "203.0.113.10:7777",
  "relay_urls": ["ws://relay.atmosphere.dev:8080"],
  "created_at": 1234567890,
  "expires_at": 1234654290
}
```

**Fields:**
- `endpoint` - Local endpoint (for LAN joins)
- `public_endpoint` - Public IP:port (for internet joins)
- `relay_urls` - Fallback relay servers

**Joining Logic:**
1. Try direct connection to `public_endpoint` (if provided)
2. Attempt UDP hole punching
3. Fall back to relay (if provided)
4. Try local `endpoint` as last resort (LAN fallback)

## Testing Internet Connectivity

### Scenario: Two Machines on Different Networks

**Rob's Machine (Portland):**
```bash
cd ~/atmosphere
atmosphere init rob-mesh
atmosphere serve --port 7777
```

Get the join code:
```bash
atmosphere join
# Outputs: MESH-ABCD-1234-EFGH
# Full code: eyJtZXNoX2lkIjoiLi4uIn0=
```

**Matt's Machine (Seattle):**
```bash
git clone https://github.com/atmosphere/atmosphere.git
cd atmosphere
pip install -e .

atmosphere join eyJtZXNoX2lkIjoiLi4uIn0=
```

**Expected Output:**
```
Joining mesh via public endpoint: 203.0.113.10:7777
Attempting direct P2P connection...
✓ P2P connection established!
✓ Joined mesh: rob-mesh
```

Or if P2P fails:
```
Attempting direct P2P connection...
✗ P2P failed, trying relay...
✓ Connected via relay: ws://relay.atmosphere.dev:8080
✓ Joined mesh: rob-mesh
```

### Verify Connection

Both machines:
```bash
atmosphere peers
```

Should show each other as connected.

## NAT Types and Success Rates

| NAT Type | P2P Success | Relay Needed |
|----------|-------------|--------------|
| No NAT (public IP) | 100% | Never |
| Full Cone NAT | 95% | Rare |
| Restricted Cone NAT | 70% | Sometimes |
| Port Restricted NAT | 50% | Often |
| Symmetric NAT | 20% | Almost always |

**Check your NAT type:**
```bash
atmosphere network
# Shows: NAT Type: full_cone
```

## Community Relay Servers

**Default Relays:**
- `wss://relay-us-east.atmosphere.dev` (US East)
- `wss://relay-us-west.atmosphere.dev` (US West)
- `wss://relay-eu.atmosphere.dev` (Europe)

**Custom Relay:**
```bash
atmosphere init my-mesh --relay ws://my-relay.example.com:8080
```

**Security Note:** Relays can see your traffic. For sensitive data:
1. Use TLS relays (`wss://`)
2. Run your own relay
3. Enable end-to-end encryption (coming soon)

## Troubleshooting

### "STUN discovery failed"

**Causes:**
- No internet connection
- Firewall blocking UDP port 3478/19302
- Behind restrictive corporate network

**Solutions:**
- Check internet connection
- Try manual public IP: `atmosphere init --public-ip <your-ip>`
- Use relay-only mode (no P2P)

### "P2P connection failed"

**Causes:**
- Symmetric NAT on both sides
- Firewall blocking UDP
- ISP blocking P2P

**Solutions:**
- Use relay fallback (automatic)
- Configure port forwarding on router
- Use VPN/Tailscale/ZeroTier

### "Relay connection failed"

**Causes:**
- Relay server down
- Firewall blocking WebSocket
- Network issues

**Solutions:**
- Try different relay server
- Check relay health: `curl http://relay:8080/health`
- Run your own relay

## Performance

### Bandwidth

**Direct P2P:**
- Latency: ~10-50ms (internet RTT)
- Bandwidth: Limited by your upload speed
- Overhead: Minimal (~2%)

**Relay:**
- Latency: +20-50ms (relay hop)
- Bandwidth: Limited by relay server
- Overhead: ~5% (WebSocket framing)

### Resource Usage

**STUN Client:**
- CPU: Negligible
- Memory: <1 MB
- Network: One-time ~1 KB

**NAT Traversal:**
- CPU: Low (event-driven)
- Memory: ~5 MB
- Network: ~1 KB/s keep-alive

**Relay Client:**
- CPU: Low (WebSocket)
- Memory: ~2 MB per connection
- Network: Varies with traffic

## Implementation Details

### STUN Protocol (RFC 5389)

```python
# STUN message format:
# 0                   1                   2                   3
# 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |0 0|     STUN Message Type     |         Message Length        |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                         Magic Cookie                          |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                                                               |
# |                     Transaction ID (96 bits)                  |
# |                                                               |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

STUN_BINDING_REQUEST = 0x0001
STUN_BINDING_RESPONSE = 0x0101
STUN_MAGIC_COOKIE = 0x2112A442
```

### UDP Hole Punching

```
Step 1: Both peers discover public endpoints
  Alice -> STUN -> 203.0.113.10:7777
  Bob   -> STUN -> 198.51.100.20:8888

Step 2: Exchange endpoints (via signaling)
  Alice tells Bob: "I'm at 203.0.113.10:7777"
  Bob tells Alice: "I'm at 198.51.100.20:8888"

Step 3: Simultaneously send packets
  Alice -> 198.51.100.20:8888 (creates NAT mapping)
  Bob   -> 203.0.113.10:7777 (creates NAT mapping)

Step 4: NAT allows bidirectional flow
  Alice <-> NAT_A <-> Internet <-> NAT_B <-> Bob
```

### Relay Protocol

```
Client A connects -> /relay/{session_id}
Client B connects -> /relay/{session_id}

Server: "Both clients connected, starting relay"

A sends: {"data": "hello"}
Server forwards to B

B sends: {"data": "world"}  
Server forwards to A

Either client disconnects -> session ends
```

## API Reference

See `atmosphere/network/` for full implementation:

- `stun.py` - STUN client
- `nat.py` - NAT traversal
- `relay.py` - Relay server and client

## Future Enhancements

- [ ] IPv6 support
- [ ] ICE (Interactive Connectivity Establishment)
- [ ] TURN (Traversal Using Relays around NAT)
- [ ] End-to-end encryption
- [ ] Multi-relay fallback
- [ ] Bandwidth optimization
- [ ] NAT type detection improvements
- [ ] Connection quality metrics

## Credits

Based on:
- RFC 5389 (STUN)
- RFC 5766 (TURN)
- RFC 8445 (ICE)
- WebRTC data channels
