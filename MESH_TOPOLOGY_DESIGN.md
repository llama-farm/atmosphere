# Mesh Topology Design: 10+ Devices, Multi-Transport, Delegated Auth

## The Scenario

```
┌─────────────────────────────────────────────────────────────┐
│                    HOME MESH (mesh_id: 0b82...)             │
│                                                              │
│  🖥️ Mac (Founder)          📱 Phone (LAN+BLE+Relay)        │
│  ├─ LAN (mDNS)             ├─ LAN (mDNS)                   │
│  ├─ BLE (GATT server)      ├─ BLE (GATT server+client)     │
│  ├─ Relay (WebSocket)      └─ Relay (WebSocket)             │
│  └─ LlamaFarm (12 models)                                   │
│                                                              │
│  🔲 Raspberry Pi (LAN)     📱 Tablet (BLE only, no WiFi)   │
│  └─ LAN only               └─ BLE only                      │
│                                                              │
│  💻 Laptop (LAN+Relay)     🔌 ESP32 Sensor (BLE only)      │
│  ├─ LAN                    └─ BLE only                      │
│  └─ Relay                                                    │
│                                                              │
│  📱 Remote Phone (Relay)   🔲 IoT Hub (LAN+BLE)            │
│  └─ Relay only             ├─ LAN                           │
│                             └─ BLE                           │
│                                                              │
│  💻 Remote Server (Relay)  📱 Friend's Phone (BLE→Relay)   │
│  └─ Relay only             ├─ BLE                           │
│                             └─ Relay                         │
└─────────────────────────────────────────────────────────────┘
```

## 1. Joining the Mesh

### Three Pairing Methods

#### Method A: QR Code (existing, works today)
```
Founder (or Delegate) → Generate Invite → QR Code → New Device Scans
```
- Founder calls `POST /api/mesh/invite` → gets signed token + endpoints
- Token encoded as `atmosphere://join?invite={base64_json}`
- QR code contains: mesh_id, mesh_name, token (signed), endpoints (local, relay, BLE)
- New device scans → parses → tries endpoints in priority order → sends `join` with token
- **Works over any transport** that can reach any existing mesh node

#### Method B: BLE Proximity + PIN Confirmation (NEW)
```
Existing Node advertising → New Device discovers → PIN exchange → Token issued
```
1. Every mesh node advertises BLE service UUID `A7A05F30-0001-...`
2. New device (not yet in mesh) scans, finds nearby Atmosphere nodes
3. New device sends `pair_request` via BLE GATT write:
   ```json
   {"type": "pair_request", "node_id": "new_device_id", "public_key": "ed25519_pub_b64"}
   ```
4. Existing node generates 6-digit PIN, displays it on screen
5. Both devices derive shared secret: `HKDF(ECDH(new_pub, existing_priv), "atmosphere-pair")`
6. New device enters PIN → sends `pair_confirm` with `HMAC(pin, shared_secret)`
7. Existing node verifies HMAC → if valid:
   - If node is **founder**: signs new token directly
   - If node is **delegate** with `can_invite`: signs sub-token (see Delegation below)
   - If node has **no invite authority**: forwards request to founder via mesh
8. Token sent back to new device via BLE
9. New device is now in the mesh — starts gossip, discovers other transports

#### Method C: LAN Discovery + PIN (NEW)
```
mDNS discovery → WebSocket connect → PIN exchange → Token issued
```
Same as Method B but over WiFi. mDNS finds `_atmosphere._tcp.local.` → WebSocket handshake → PIN flow.

### Why PIN?
- **BLE has no inherent authentication** — anyone in range could try to join
- PIN ensures physical proximity + human intent
- 6 digits = 1M combinations, brute-force protected by rate limiting (3 attempts, then 60s cooldown)
- Alternative: "confirm on both devices" (show same 4-word phrase, tap OK on both)

## 2. Delegation: Non-Founders Adding Devices

### The Authority Chain

```
Founder (root key)
├── issues Token A (capabilities: [participant, llm, can_invite])
│   └── Device A uses Token A to issue Sub-Token A1
│       └── Device X joins with Sub-Token A1
│           (capabilities: [participant, llm] — can_invite NOT inherited)
├── issues Token B (capabilities: [participant, sensor])
│   └── Device B CANNOT issue tokens (no can_invite)
└── issues Token C (capabilities: [participant, can_invite, can_delegate_invite])
    └── Device C can issue tokens WITH can_invite
        └── Device D gets can_invite too → can itself invite
```

### Rules
1. **Founder** can issue any token with any capabilities
2. **Delegate** (has `can_invite`) can issue tokens, BUT:
   - Cannot grant capabilities they don't have themselves
   - Cannot grant `can_invite` UNLESS they have `can_delegate_invite`
   - Sub-tokens include a **delegation chain**: `[founder_sig, delegate_sig]`
3. **Verification**: Any node can verify by walking the chain:
   - Check sub-token sig against delegate's public key
   - Check delegate's token sig against founder's public key (stored in mesh config)
   - All signatures valid + capabilities subset = ACCEPT

### Token Structure (Extended)

```json
{
  "mesh_id": "0b82206b236bd66c",
  "node_id": null,
  "issued_at": 1770525000,
  "expires_at": 1770611400,
  "capabilities": ["participant", "llm"],
  "issuer_id": "69ff1fa7cc80d0e0",
  "nonce": "a1b2c3d4e5f6...",
  "signature": "base64...",
  "delegation_chain": [
    {
      "issuer_id": "69ff1fa7cc80d0e0",
      "issuer_capabilities": ["participant", "llm", "can_invite"],
      "signature": "base64..."
    }
  ]
}
```

### Key Insight: Offline Delegation
If the founder is **offline**, a delegate can still issue tokens. The new device joins with the delegate's sub-token. When the founder comes back online, it can **audit** all sub-tokens via gossip. This is critical for field deployments.

## 3. Transport Bridging: The Hard Part

### The Problem
Device 6 (BLE only) needs to reach Device 7 (Relay only). They share no transport.

### Solution: Every Node is a Bridge

```
ESP32 (BLE) ──BLE──▶ Phone (BLE+Relay) ──Relay──▶ Remote Server (Relay)
                              │
                        ──LAN──▶ Mac (LAN+BLE+Relay) ──BLE──▶ Tablet (BLE)
```

**Rule**: When a node receives a message on ANY transport, it forwards to ALL other transports (with dedup + TTL).

### Message Flow

```python
def handle_incoming_message(msg, source_transport):
    # 1. Dedup check (nonce-based LRU cache)
    if msg.nonce in seen_messages:
        return  # Already processed
    seen_messages.add(msg.nonce)
    
    # 2. Process locally (gossip, inference, etc.)
    process_message(msg)
    
    # 3. If TTL > 0, forward to OTHER transports
    if msg.ttl > 0:
        msg.ttl -= 1
        msg.hops += 1
        for transport in active_transports:
            if transport != source_transport:
                transport.broadcast(msg)
```

### Deduplication
- Every message has a `nonce` (16-byte random, set by originator)
- Each node keeps an LRU cache of 1000 recent nonces
- If nonce seen before → drop (prevents broadcast storms)
- TTL starts at 5 (covers meshes up to 5 hops diameter)

### Transport Priority for Direct Sends
When sending TO a specific node (not broadcast):
1. **LAN** (if we know their IP via mDNS) — ~1ms
2. **BLE** (if in range, connected via GATT) — ~50ms
3. **Relay** (always works if both online) — ~100ms+

### Gossip Propagation Across Transports
Gossip announcements travel the same way:
1. Mac announces 12 capabilities on LAN + Relay + BLE
2. Phone receives via LAN, forwards to BLE peers (Tablet, ESP32)
3. Remote Server receives via Relay, forwards to... nothing (no other transports)
4. **Result**: Every device in the mesh has the full capability table, regardless of transport

## 4. The 10-Device Gossip Scenario

```
T=0s:  Mac (founder) starts. 12 capabilities. Advertises on LAN + BLE + Relay.
T=1s:  Phone joins via QR code (Relay). Gets 12 caps. Starts LAN + BLE.
T=2s:  Phone discovers Mac on LAN (mDNS). Switches to LAN. Faster!
T=3s:  Laptop joins via LAN (mDNS + PIN). Gets 12 caps from Mac directly.
T=5s:  Tablet (no WiFi) joins via BLE proximity + PIN with Phone.
       Phone is delegate (has can_invite). Issues sub-token.
       Phone forwards 12 caps to Tablet via BLE.
T=8s:  ESP32 joins via BLE proximity + PIN with Mac.
       Mac signs token directly (founder).
       ESP32 gets 12 caps. Announces its sensor capability.
T=9s:  ESP32's sensor cap propagates: BLE→Mac→LAN→Phone→BLE→Tablet
       AND: BLE→Mac→Relay→Remote Server, Remote Phone
T=10s: Everyone has 13 capabilities (12 LLM + 1 sensor).
T=12s: RPi joins via LAN. Gets 13 caps from Mac. Adds its own (camera).
T=13s: 14 capabilities everywhere. Full mesh convergence.
T=15s: Remote Server joins via Relay. Gets 14 caps.
       Adds 2 GPU capabilities. Propagates back through relay.
T=16s: 16 capabilities mesh-wide.
```

**Convergence time**: ~5-10 seconds for gossip to reach all nodes, regardless of transport topology.

## 5. Implementation Plan

### Phase 1: Transport Bridging (TONIGHT)
**Files to modify:**
- `atmosphere/api/server.py` — Bridge BLE↔Relay↔LAN messages
- `AtmosphereService.kt` — Bridge BLE↔WebSocket messages
- Both need: dedup cache, TTL handling, multi-transport forward

### Phase 2: BLE Proximity Pairing (TONIGHT)
**New files:**
- `atmosphere/pairing/ble_pair.py` — Mac-side BLE pairing handler (PIN generation, token issuance)
- `BlePairingManager.kt` — Android BLE pairing (discovery, PIN entry, token receipt)
- UI: PIN display dialog, PIN entry screen

### Phase 3: Delegation Chain (TONIGHT)
**Modify:**
- `atmosphere/auth/tokens.py` — Add `delegation_chain` field, sub-token issuance, chain verification
- `AtmosphereService.kt` — Store own token, use it for sub-token issuance when `can_invite`

### Phase 4: LAN PIN Pairing
**Modify:**
- `atmosphere/api/routes.py` — `/api/mesh/pair` WebSocket endpoint (PIN exchange)
- `JoinMeshScreen.kt` — Add "Join via LAN" option with PIN entry

## 6. Security Considerations

- **PIN brute-force**: 3 attempts, then 60s cooldown, then 5min, then lockout
- **Token replay**: Nonce prevents replay. Tokens are one-use for joining.
- **Compromised delegate**: Founder can revoke via gossip `token_revocation` message
- **MITM on BLE**: PIN confirmation prevents — attacker would need physical access
- **Relay trust**: Relay sees encrypted payloads only. Cannot forge tokens (no founder key).
- **Gossip flooding**: TTL + dedup + rate limiting prevents amplification attacks

---

*This design supports the full vision: third-party apps → local Atmosphere → semantic route → right model, across ANY combination of transports, with cryptographic trust at every hop.*
