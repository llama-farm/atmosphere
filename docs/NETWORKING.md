# Atmosphere Networking Guide

This guide explains how to set up Atmosphere for both local network (LAN) and internet-scale (WAN) mesh deployments.

## Quick Start

### Check Your Network

```bash
atmosphere network
```

This will show:
- Your local IP address
- Your public IP (via STUN discovery)
- Whether you're behind NAT
- Whether you're likely reachable from the internet

### Scenario 1: LAN Only (Same Network)

If all nodes are on the same local network:

```bash
# Node 1 (creator)
atmosphere init
atmosphere mesh create --name "my-mesh"
# Generates invite code automatically

# Node 2 (joiner)
atmosphere init
atmosphere mesh join '<invite_code>'
```

mDNS discovery will also help nodes find each other.

### Scenario 2: Internet (Different Networks)

For nodes in different locations (e.g., different cities):

**Prerequisite**: At least one node must be publicly reachable.

#### Option A: Port Forwarding (Recommended)

1. Forward port `11451` on your router to your machine
2. Create mesh with your public IP:

```bash
# Check your public IP
atmosphere network

# Create mesh with public endpoint
atmosphere mesh create --name "my-mesh" --endpoint "YOUR_PUBLIC_IP:11451"

# Or let it auto-detect (if port is already forwarded):
atmosphere mesh create --name "my-mesh"
```

3. Share the invite code via Slack/email/etc.

4. Remote user joins:
```bash
atmosphere init
atmosphere mesh join '<invite_code>'
```

#### Option B: Public Server (VPS)

Run one Atmosphere node on a VPS with a public IP:

```bash
# On VPS (has public IP)
atmosphere init
atmosphere serve --host 0.0.0.0 --port 11451

atmosphere mesh create --name "my-mesh"
# Invite code will use the VPS's public IP
```

Other nodes join via the VPS, which acts as the mesh backbone.

#### Option C: Manual Endpoint

If you know your public IP but STUN detection isn't working:

```bash
atmosphere mesh invite --endpoint "203.0.113.45:11451"
```

## Network Requirements

### Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 11451 | TCP | HTTP API (primary) |
| 11450 | TCP | Gossip protocol |

### Firewall Rules

For a publicly accessible node:

```bash
# Linux (ufw)
sudo ufw allow 11451/tcp
sudo ufw allow 11450/tcp

# macOS (built-in firewall)
# Allow in System Preferences > Security > Firewall > Options
```

### NAT Types

| NAT Type | Direct Connection | Notes |
|----------|-------------------|-------|
| No NAT (public IP) | ✅ Yes | Best case |
| Full Cone NAT | ✅ Yes | Port forwarding works |
| Restricted Cone | ⚠️ Maybe | May need relay |
| Symmetric NAT | ❌ No | Needs relay |

## Troubleshooting

### "Connection failed" when joining

1. Check that the founder's node is running: `atmosphere serve`
2. Verify the endpoint is reachable: `curl http://ENDPOINT:11451/health`
3. Check firewall settings
4. Try with explicit endpoint: `atmosphere mesh join --endpoint IP:PORT`

### "No public IP detected"

This means you're behind NAT without port forwarding. Options:

1. Set up port forwarding on your router
2. Use a VPS as the mesh founder
3. Wait for relay support (coming soon)

### Invite code expired

Invite codes expire after 24 hours by default. Generate a new one:

```bash
atmosphere mesh invite --hours 48
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     INTERNET                                 │
└─────────────────────────────────────────────────────────────┘
        │                           │
        ▼                           ▼
┌───────────────┐           ┌───────────────┐
│  Rob's Mac    │◀─────────▶│  Matt's PC    │
│  (Portland)   │   Direct  │  (Seattle)    │
│               │   TCP     │               │
│  Public IP:   │           │  Behind NAT   │
│  71.x.x.x     │           │  Connects to  │
│  Port: 11451  │           │  Rob's IP     │
└───────────────┘           └───────────────┘
```

## Coming Soon

- **Relay Servers**: For nodes that can't be directly reached
- **WebSocket Transport**: Better NAT traversal
- **UPnP/NAT-PMP**: Automatic port forwarding
- **Hole Punching**: P2P connections through NAT

## Security Notes

- All mesh communication is authenticated via Ed25519 signatures
- Invite codes are time-limited and single-use
- Nodes verify mesh membership on every connection
- Traffic between nodes can be encrypted (TLS) when using `https://` endpoints
