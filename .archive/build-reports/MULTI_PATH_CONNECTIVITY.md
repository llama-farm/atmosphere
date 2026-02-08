# Multi-Path Mesh Connectivity

Atmosphere supports multiple connection paths to ensure mesh connectivity across different network scenarios.

## Overview

When generating an invite token/QR code, the system now detects and includes multiple ways for remote devices to connect:

1. **Local Network (fastest)** - Direct connection via local IP (e.g., `ws://192.168.x.x:11451`)
2. **Public Internet** - Connection via public IP (e.g., `ws://73.45.x.x:11451`) - requires port forwarding
3. **Relay Server (fallback)** - Connection via relay when direct connection fails

## How It Works

### Token Generation (`/api/mesh/token`)

When generating an invite token, the Mac server:

1. Detects the **local IP** using standard socket connection
2. Uses **STUN** (RFC 5389) to discover the public IP by querying Google's STUN servers
3. Checks for configured **relay URLs** (via `ATMOSPHERE_RELAY_URL` environment variable)

The response includes:

```json
{
  "token": "ATM-XXXX...",
  "mesh_id": "abc123",
  "mesh_name": "Home Mesh",
  "endpoints": {
    "local": "ws://192.168.86.237:11451",
    "public": "ws://73.45.123.89:11451",
    "relay": "wss://relay.atmosphere.io/mesh/abc123"
  },
  "network_info": {
    "local_ip": "192.168.86.237",
    "public_ip": "73.45.123.89",
    "is_behind_nat": true,
    "stun_source": "stun:stun.l.google.com"
  },
  "endpoint": "ws://73.45.123.89:11451",  // Legacy single endpoint
  "qr_data": "atmosphere://join?token=ATM-XXX&mesh=Home&endpoints={...}"
}
```

### Android Connection

When scanning a QR code or entering an invite, the Android app:

1. Parses the multi-endpoint format from the `endpoints` query parameter
2. Tries endpoints **in order**: local → public → relay
3. Uses the first successful connection
4. Reports which connection method succeeded

```kotlin
// Example usage
val endpoints = MeshEndpoints(
    local = "ws://192.168.86.237:11451",
    public = "ws://73.45.123.89:11451",
    relay = null
)

val connection = MeshConnection.connectWithFallback(
    endpoints = endpoints,
    token = "ATM-XXX",
    onConnected = { type, meshName ->
        Log.i("Mesh", "Connected via $type to $meshName")
    },
    onProgress = { type, status ->
        Log.d("Mesh", "$type: $status")
    },
    onError = { error ->
        Log.e("Mesh", "All connections failed: $error")
    }
)
```

## Network Requirements

### Local Network
- ✅ Works automatically
- Both devices on same WiFi/LAN

### Public Internet  
- ⚠️ Requires port forwarding
- Router must forward port 11451 (TCP/WebSocket) to the Mac
- May not work with Carrier-Grade NAT (CGNAT)

### Relay Server
- ✅ Works through any NAT
- Requires a relay server deployment
- Higher latency than direct connections

## Setting Up Port Forwarding

1. Log into your router's admin panel (usually `192.168.1.1` or `192.168.0.1`)
2. Find "Port Forwarding" or "NAT" settings
3. Add a rule:
   - External Port: `11451`
   - Internal IP: Your Mac's local IP (shown in the UI)
   - Internal Port: `11451`
   - Protocol: TCP
4. Save and restart if needed

## Setting Up a Relay Server

You can run your own relay server:

```bash
# Install
pip install atmosphere

# Run relay
python -m atmosphere.network.relay --port 8080
```

Then set the environment variable before starting Atmosphere:

```bash
export ATMOSPHERE_RELAY_URL=wss://your-relay-server.com:8080
atmosphere serve
```

## Test Scenarios

| Scenario | Local | Public | Relay | Expected |
|----------|-------|--------|-------|----------|
| Same WiFi | ✅ | N/A | N/A | Connects via local |
| Phone on cell, Mac on home WiFi | ❌ | ✅ (if port forwarded) | ✅ | Connects via public or relay |
| Both behind NAT | ❌ | ❌ | ✅ | Connects via relay |

## Files Modified

- `atmosphere/api/routes.py` - Token generation with multi-path endpoints
- `atmosphere/network/stun.py` - STUN client for public IP discovery (existing)
- `atmosphere/network/relay.py` - Relay server/client (existing)
- `atmosphere-android/.../MeshConnection.kt` - Multi-endpoint fallback
- `atmosphere-android/.../JoinMeshScreen.kt` - Parse new QR format
- `atmosphere/ui/src/components/JoinPanel.jsx` - Show connectivity status
- `atmosphere/ui/src/components/JoinPanel.css` - Connectivity status styling

## QR Code Format

### New Format (v2)
```
atmosphere://join?token=ATM-XXX&mesh=NAME&endpoints={"local":"ws://...","public":"ws://...","relay":"wss://..."}
```

### Legacy Format (v1) - Still Supported
```
atmosphere://join?token=ATM-XXX&mesh=NAME&endpoint=ws://...
```

## Troubleshooting

### Public IP Not Detected
- Check if STUN servers are reachable
- Some corporate firewalls block UDP to STUN servers
- Verify with: `nc -u stun.l.google.com 19302`

### Port Forwarding Not Working
- Verify the rule is active in your router
- Check if your ISP uses CGNAT (you'll have a private IP like `100.x.x.x`)
- Try DMZ as a test (not recommended for production)

### Relay Connection Fails
- Verify relay server is running and accessible
- Check firewall allows outbound WebSocket connections
- Verify `ATMOSPHERE_RELAY_URL` is set correctly
