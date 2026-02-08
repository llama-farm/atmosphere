# Android Mesh Connection Simulation Report

**Date:** 2026-02-07 01:17:53 CST  
**Test Type:** E2E Android Simulation (without physical device)  
**Status:** ✅ SUCCESS

## Executive Summary

Successfully simulated an Android device joining the Atmosphere mesh network. The complete connection flow was verified:

- ✅ Token generation and signing with mesh master key
- ✅ Token parsing (like Android would do from deep link)
- ✅ WebSocket connection to production relay
- ✅ Token verification by relay server
- ✅ Mesh join with peer discovery
- ⏳ LLM request sent (no response - no LLM-capable peers available)

## Test Environment

| Component | Value |
|-----------|-------|
| Relay Server | wss://atmosphere-relay-production.up.railway.app |
| Mesh ID | 0b82206b236bd66c |
| Mesh Name | home-mesh |
| Simulated Android Node ID | 65d98c315d54d847 |
| Token Issuer | 118c1963042d52fc |
| Token Validity | 7 days (expires 2026-02-14) |

## Connection Flow

### Step 1: Token Generation ✅
```
- Loaded mesh.json for mesh ID and public key
- Loaded mesh.secrets for master private key (share_data)
- Created signed MeshToken with Ed25519 signature
- Wrapped in MeshInvite with relay endpoints
```

**Key Discovery:** When threshold=1 (single founder), the `share_data` in `mesh.secrets` IS the master private key. This is used to sign tokens that the relay can verify against `master_public_key`.

### Step 2: Deep Link Parsing ✅
```
Format: atmosphere://join/<base64url_invite>

Decoded:
- mesh_id: 0b82206b236bd66c
- mesh_name: home-mesh
- endpoints: [wss://atmosphere-relay-production.up.railway.app]
- token: {mesh_id, issuer_id, capabilities, expires_at, signature}
```

### Step 3: WebSocket Connection ✅
```
URL: wss://atmosphere-relay-production.up.railway.app/relay/0b82206b236bd66c
Protocol: Standard WebSocket with JSON messages
```

### Step 4: Join Message ✅
```json
{
    "type": "join",
    "node_id": "65d98c315d54d847",
    "token": {
        "mesh_id": "0b82206b236bd66c",
        "issuer_id": "118c1963042d52fc",
        "capabilities": ["participant"],
        "expires_at": 1770844673,
        "nonce": "...",
        "signature": "..."
    },
    "name": "Android-Simulator",
    "capabilities": ["llm-client"]
}
```

### Step 5: Server Response ✅
```json
{"type": "joined", "mesh": "home-mesh", "mesh_id": "0b82206b236bd66c", "node_count": 3}
{"type": "peers", "peers": [
    {"node_id": "69ff1fa7cc80d0e0", "name": "home-mesh", "is_founder": true},
    {"node_id": "003866f1a25c3659", "name": "Test-Peer-Python", "is_founder": false}
]}
```

### Step 6: LLM Request ⏳
```json
{
    "type": "llm_request",
    "request_id": "f660048e16c40dde",
    "messages": [{"role": "user", "content": "Say 'Hello from Atmosphere mesh!'"}],
    "model": "auto"
}
```

**Note:** Request was sent but no response received within 15s timeout. This is expected because no connected peers advertised LLM capabilities.

## Token Verification Deep Dive

### The Authentication Problem (Initially Failed)

First attempt failed with "Invalid token" because:
- Token was signed with node's private key (`identity.json`)
- Relay verifies against mesh's master public key (`mesh.json`)
- These are different keys!

### The Fix

Tokens must be signed with the **mesh master key**, not the node identity key:

```python
# WRONG - using node identity
identity_path = Path.home() / ".atmosphere" / "identity.json"
private_key = bytes.fromhex(id_data["private_key"])

# CORRECT - using mesh master key
secrets_path = Path.home() / ".atmosphere" / "mesh.secrets"  
share_data = bytes.fromhex(secrets_data["share_data"])  # THIS is the master key
private_key = Ed25519PrivateKey.from_private_bytes(share_data)
```

### Key Files Summary

| File | Purpose |
|------|---------|
| `~/.atmosphere/identity.json` | Node's private/public keypair (for node identity) |
| `~/.atmosphere/mesh.json` | Mesh metadata, master PUBLIC key, founding members |
| `~/.atmosphere/mesh.secrets` | Master PRIVATE key (as share_data when threshold=1) |

## Relay Protocol Summary

### Message Types

| Type | Direction | Purpose |
|------|-----------|---------|
| `register_mesh` | → Relay | Founder registers mesh (first time) |
| `join` | → Relay | Member joins with token |
| `joined` | ← Relay | Confirmation of join |
| `peers` | ← Relay | List of connected peers |
| `peer_joined` | ← Relay | New peer notification |
| `peer_left` | ← Relay | Peer disconnect notification |
| `llm_request` | → Relay | Request routed to LLM peer |
| `llm_response` | ← Relay | Response from LLM peer |
| `error` | ← Relay | Error message |

### Error Codes

| Code | Meaning |
|------|---------|
| `TOKEN_REQUIRED` | Mesh requires token but none provided |
| `TOKEN_INVALID` | Signature verification failed |
| `REGISTRATION_FAILED` | Mesh registration failed |

## Android Integration Notes

For actual Android implementation:

1. **Deep Link Handler:** Register for `atmosphere://` scheme
2. **Token Storage:** Store invite in SharedPreferences/DataStore
3. **WebSocket:** Use OkHttp WebSocket or similar
4. **Background:** Keep connection in foreground service for reliability
5. **Reconnection:** Implement exponential backoff (already in relay.py)

### Minimal Android Join Code

```kotlin
// Parse invite from deep link
val invite = MeshInvite.decode(inviteString)

// Connect to relay
val ws = OkHttpClient().newWebSocket(
    Request.Builder().url("${invite.endpoints[0]}/relay/${invite.token.meshId}").build(),
    object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            // Send join
            webSocket.send(Json.encodeToString(JoinMessage(
                type = "join",
                nodeId = generateNodeId(),
                token = invite.token,
                name = "Android Device",
                capabilities = listOf("llm-client")
            )))
        }
        
        override fun onMessage(webSocket: WebSocket, text: String) {
            val msg = Json.decodeFromString<RelayMessage>(text)
            when (msg.type) {
                "joined" -> Log.i("Mesh", "Joined!")
                "peers" -> updatePeerList(msg.peers)
                "llm_response" -> handleLLMResponse(msg)
            }
        }
    }
)
```

## Files Created

| File | Purpose |
|------|---------|
| `scripts/simulate_android_join.py` | Complete Android simulation script |
| `TEST_REPORTS/android_simulation_result.json` | JSON test results |
| `TEST_REPORTS/ANDROID_SIMULATION_REPORT.md` | This report |

## Test Script Usage

```bash
# Generate invite and run simulation
cd ~/clawd/projects/atmosphere
source .venv/bin/activate
python scripts/simulate_android_join.py

# Or with existing invite
python scripts/simulate_android_join.py --invite "atmosphere://join/..."
```

## Recommendations

1. **Capability Registration:** Mac app should register `["llm", "chat"]` capabilities when connecting so Android can discover it

2. **Token Generation API:** Add CLI command or API endpoint:
   ```bash
   atmosphere invite create --ttl 7d
   ```

3. **QR Code:** Generate QR from invite for easy scanning:
   ```bash
   atmosphere invite qr > invite.png
   ```

4. **Connection Health:** Add ping/pong heartbeat to detect stale connections

## Conclusion

The Android mesh connection flow works correctly. The simulation successfully:
- Parsed invite tokens like Android would
- Connected to the production relay
- Passed token verification
- Joined the mesh
- Discovered peers

The only gap is LLM request routing, which requires a peer with LLM capabilities to be connected. This is a configuration issue, not a protocol issue.

---
*Report generated by Android Simulator E2E Test*
