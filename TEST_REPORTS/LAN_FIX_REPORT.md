# LAN Transport Fix Report

**Date:** 2026-02-07
**Status:** ✅ Fixed

## Problem Summary

The LAN transport was **client-only** - it could discover peers via mDNS and connect to them, but there was no WebSocket server to accept incoming connections.

### Before Fix
```
Node A                          Node B
  │                               │
  ├─ mDNS advertise (port 11450) ─┤
  │                               │
  ├─ mDNS discovers Node B ───────┤
  │                               │
  └─ ws://nodeB:11450/ws ────────X (No server!)
```

### After Fix
```
Node A                          Node B
  │                               │
  ├─ Start LANServer (11450) ─────┼─ Start LANServer (11450)
  │                               │
  ├─ mDNS advertise ──────────────┼─ mDNS advertise
  │                               │
  ├─ mDNS discovers Node B ───────┤
  │                               │
  └─ ws://nodeB:11450/ws ─────────┼─► LANServer accepts ✓
                                  │
                                  ├─ mDNS discovers Node A
                                  │
                                  └─ ws://nodeA:11450/ws ───► LANServer accepts ✓
```

## Changes Made

### File: `atmosphere/mesh/transport.py`

#### 1. Added `LANServer` Class (lines ~252-430)
```python
class LANServer:
    """
    WebSocket server for accepting incoming LAN connections.
    
    This is the missing piece - peers discover us via mDNS but need
    a server to connect to. This provides that server.
    """
```

Features:
- Starts aiohttp web server on configurable port
- `/ws` endpoint for WebSocket connections
- `/` endpoint for health check / info
- Handshake protocol for peer identification
- Tracks connected peers by node_id
- Bidirectional message passing
- Proper cleanup on shutdown

#### 2. Updated `LANTransport` Class
Added handshake on connect:
```python
async def connect(self, peer_id: str, endpoint: str) -> bool:
    # ... connect ...
    # Send handshake to identify ourselves
    if self._node_id:
        await self._ws.send_json({
            "type": "handshake",
            "node_id": self._node_id,
            "mesh_id": self._mesh_id or "",
        })
        # Wait for acknowledgment
        ack = await asyncio.wait_for(self._ws.receive_json(), timeout=5)
```

#### 3. Updated `TransportManager._start_lan_discovery()`
Now starts the WebSocket server before mDNS advertising:
```python
async def _start_lan_discovery(self):
    """Start LAN transport: WebSocket server + mDNS discovery."""
    
    # Start the WebSocket server first - THIS IS CRITICAL
    self._lan_server = LANServer(
        node_id=self.node_id,
        mesh_id=self.mesh_id,
        port=port,
    )
    # ... setup handlers ...
    await self._lan_server.start()
    
    # Then start mDNS discovery
    self._zeroconf = Zeroconf()
    # ...
```

#### 4. Updated `send()` and `broadcast()` Methods
Now handle both outgoing (pool) and incoming (server) connections:
```python
async def send(self, peer_id: str, message: bytes) -> bool:
    # Try connection pool first (outgoing connections)
    if peer_id in self._pools:
        if await self._pools[peer_id].send(message):
            return True
    
    # Try LAN server (incoming connections)
    if self._lan_server and peer_id in self._lan_server.connected_peers:
        if await self._lan_server.send(peer_id, message):
            return True
    
    return False
```

#### 5. Updated `get_connected_peers()`
Now includes peers from both directions:
```python
def get_connected_peers(self) -> List[str]:
    peers = set()
    # Outgoing connections
    for peer_id, pool in self._pools.items():
        if pool.get_best_transport() is not None:
            peers.add(peer_id)
    # Incoming connections via LAN server
    if self._lan_server:
        peers.update(self._lan_server.connected_peers)
    return list(peers)
```

## Test Results

### Simple LAN Test (`test_lan_simple.py`)
```
✅ Server started on port 11461
✅ WebSocket connected
✅ Handshake successful
✅ Client appears in connected_peers
✅ Server received message from client
✅ Client received message from server
✅ LANTransport connected with handshake
✅ Server received via transport
✅ All tests passed!
```

### Integration Notes

- mDNS discovery between two processes on the same machine may not work (zeroconf limitation)
- For full mesh testing, use separate machines or Docker containers
- The WebSocket server uses aiohttp which is already a project dependency

## How It Works Now

1. **Node starts** → `TransportManager.start()` called
2. **LAN enabled** → `_start_lan_discovery()` runs
3. **Server starts** → `LANServer` listens on port 11450
4. **mDNS advertises** → Broadcasts `_atmosphere._tcp.local.` with node info
5. **Peer discovered** → mDNS finds other node
6. **Connect** → `LANTransport` connects to peer's `ws://ip:port/ws`
7. **Handshake** → Client sends node_id/mesh_id, server acknowledges
8. **Messages flow** → Bidirectional via WebSocket

## Port Configuration

Default: `11450` (configurable via `TransportConfig.lan["port"]`)

## Future Improvements

1. **Connection deduplication** - If A connects to B and B connects to A, we have duplicate connections
2. **Reconnection logic** - Auto-reconnect on disconnect
3. **TLS support** - For encrypted LAN connections
4. **Connection pooling** - Track server connections in ConnectionPool for unified metrics

## Files Modified

- `atmosphere/mesh/transport.py` - Main changes
  
## Files Added (for testing)

- `test_lan_simple.py` - Simple server/client test
- `test_lan_transport.py` - Full integration test suite
- `TEST_REPORTS/LAN_FIX_REPORT.md` - This report
