# Token Architecture - Design & Fixes

## Current Issue (2026-02-06)

The token replay protection is fragile:
1. Signed tokens have a nonce baked into the signature
2. Can't change nonce without invalidating signature
3. Relay tracks used nonces globally
4. Same device reconnecting with same token gets rejected

## Root Cause

The invite token conflates two concerns:
1. **Identity** - "I'm allowed to join this mesh" (long-lived)
2. **Session Auth** - "This is a fresh connection attempt" (per-connection)

## Current Fix (Relay-side)

Track nonces by `(nonce, node_id)` tuple instead of just `nonce`:
- Same node reconnecting with same nonce → ALLOWED
- Different node using same nonce → REJECTED (replay attack)

This is implemented in `relay/server.py` but wasn't deployed until 2026-02-06.

## Long-term Fix: Two-Layer Auth

### Layer 1: Invite Token (Long-lived)
```json
{
  "mesh_id": "...",
  "mesh_public_key": "...",
  "capabilities": ["participant", "llm"],
  "issuer_id": "founder_node_id",
  "expires_at": 1770476382,
  "signature": "..."  // Signs the above, NO nonce
}
```

### Layer 2: Session Auth (Per-connection)
```json
{
  "type": "join",
  "invite_token": { ... },  // Layer 1
  "session": {
    "node_id": "my_node_id",
    "nonce": "fresh_random_uuid",  // Generated each attempt
    "timestamp": 1770390000,
    "signature": "..."  // Node signs (nonce + timestamp) with its key
  }
}
```

### Benefits
- Invite tokens can be reused safely (no embedded nonce)
- Each connection attempt has a fresh nonce
- Node identity verified separately from invite validity
- Relay only needs to track session nonces (short TTL)

## Migration Path

1. ✅ Deploy relay fix (allow same node_id reconnection)
2. Add session auth layer to client
3. Update relay to accept both old and new formats
4. Deprecate old format after clients update

## Related Files
- `relay/server.py` - Token verification
- `atmosphere/auth/tokens.py` - Token creation/verification
- `atmosphere-android/.../MeshConnection.kt` - Client auth
