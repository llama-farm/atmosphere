# Relay Connection Fix

## Problem Identified

The `MeshConnectionManager._connect_relay()` method passes `self.config.relay_url` directly to `RelayTransport.connect()`, but the RelayTransport expects a full URL with the mesh_id path appended.

### Current Code (Broken)
```python
# In mesh_connection.py, line ~165
success = await self._relay.connect(self.config.relay_url)
```

This passes: `wss://atmosphere-relay-production.up.railway.app`

### What RelayTransport Expects
```python
# In transports/relay.py
async def connect(self, address: str) -> bool:
    """
    Connect to relay server.
    
    Address format: "wss://relay.example.com/relay/{mesh_id}"
    """
```

It expects: `wss://atmosphere-relay-production.up.railway.app/relay/0b82206b236bd66c`

## The Fix

### Option 1: Fix in mesh_connection.py (Recommended)

Change line ~165 in `atmosphere/network/mesh_connection.py`:

```python
# Before:
success = await self._relay.connect(self.config.relay_url)

# After:
relay_full_url = f"{self.config.relay_url}/relay/{self.config.mesh_id}"
success = await self._relay.connect(relay_full_url)
```

### Option 2: Fix in RelayTransport

Modify `RelayTransport.connect()` to automatically append the path:

```python
async def connect(self, address: str) -> bool:
    # Auto-append /relay/{mesh_id} if not present
    if "/relay/" not in address:
        address = f"{address}/relay/{self.mesh_id}"
    
    self._relay_url = address
    # ... rest of method
```

## Testing the Fix

After applying the fix, restart the server and check:

```bash
# Should show connections: 1
curl https://atmosphere-relay-production.up.railway.app/health
```

Expected output:
```json
{
  "status": "ok",
  "meshes": 1,
  "connections": 1,   # ← Should be 1 or more
  "registered_meshes": 1,
  "uptime_seconds": 1500.0
}
```

## Implementation

I recommend **Option 1** because:
1. Clearer intent - shows exactly what URL is being used
2. RelayTransport's docstring explicitly shows the expected format
3. Less magic/implicit behavior
4. Easier to debug

## Additional Improvements

Also add logging to help debug future issues:

```python
async def _connect_relay(self):
    """Connect to relay server and maintain connection."""
    while self._running:
        if not self._relay_connected:
            try:
                self._relay = RelayTransport(
                    self.config.node_id,
                    self.config.mesh_id,
                    self.config.relay_token
                )
                
                # Build full relay URL
                relay_full_url = f"{self.config.relay_url}/relay/{self.config.mesh_id}"
                log.info(f"Attempting to connect to relay: {relay_full_url}")
                
                # ... rest of method
                
                success = await self._relay.connect(relay_full_url)
                if success:
                    self._relay_connected = True
                    log.info(f"✅ Connected to relay server: {relay_full_url}")
                else:
                    log.warning(f"❌ Failed to connect to relay: {relay_full_url}, will retry...")
                    
            except Exception as e:
                log.error(f"❌ Relay connection error: {e}", exc_info=True)
```

This provides clear visibility into what's happening with the relay connection.
