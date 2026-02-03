# Atmosphere Relay Server

A lightweight WebSocket relay server for Atmosphere mesh networking when direct P2P connections aren't possible.

## Why a Relay?

When both devices are behind NAT (common scenario: Mac at home, Android on cellular), direct connections fail. The relay provides a rendezvous point where both devices connect **outbound** — no port forwarding needed.

```
┌─────────────┐      ┌─────────────────┐      ┌─────────────┐
│   Android   │─────▶│  Relay Server   │◀─────│     Mac     │
│  (cell data)│      │ (cloud/VPS)     │      │ (behind NAT)│
└─────────────┘      └─────────────────┘      └─────────────┘
```

## Quick Start

### Local Testing

```bash
# With Docker
docker compose up

# Or directly with Python
pip install -r requirements.txt
python server.py
```

### Verify It's Running

```bash
curl http://localhost:8765/health
# {"status": "ok", "meshes": 0, "connections": 0}
```

## Protocol

### 1. Connect & Register

```javascript
const ws = new WebSocket("ws://localhost:8765/relay/my-mesh-id");

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: "register",
    node_id: "my-unique-node-id",
    token: "mesh-auth-token",
    capabilities: ["llm", "chat"],
    name: "My Device"
  }));
};
```

### 2. Receive Peer List

```javascript
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  if (msg.type === "peers") {
    console.log("Current peers:", msg.peers);
  }
  
  if (msg.type === "peer_joined") {
    console.log("New peer:", msg.node_id, msg.capabilities);
  }
  
  if (msg.type === "peer_left") {
    console.log("Peer left:", msg.node_id);
  }
};
```

### 3. Send Messages

```javascript
// Broadcast to all peers
ws.send(JSON.stringify({
  type: "broadcast",
  payload: { message: "Hello everyone!" }
}));

// Direct message to specific peer
ws.send(JSON.stringify({
  type: "direct",
  target: "other-node-id",
  payload: { message: "Hello specific peer!" }
}));

// LLM request (routed to capable peer)
ws.send(JSON.stringify({
  type: "llm_request",
  request_id: "req-123",
  prompt: "What is the meaning of life?",
  model: "llama3.2"
}));
```

### 4. Receive Messages

```javascript
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  switch (msg.type) {
    case "message":
      console.log(`From ${msg.from}:`, msg.payload);
      break;
      
    case "llm_request":
      // You have LLM capability - process and respond
      const response = await processLLM(msg.prompt);
      ws.send(JSON.stringify({
        type: "llm_response",
        target: msg.from,
        request_id: msg.request_id,
        response: response
      }));
      break;
      
    case "llm_response":
      console.log(`LLM response for ${msg.request_id}:`, msg.response);
      break;
  }
};
```

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Server info |
| `GET /health` | Health check (for load balancers) |
| `GET /stats` | Detailed statistics |
| `WS /relay/{mesh_id}` | WebSocket relay endpoint |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8765` | Server port |
| `HOST` | `0.0.0.0` | Bind address |
| `LOG_LEVEL` | `info` | Logging verbosity |

## Deployment

See [RELAY_DEPLOYMENT.md](./RELAY_DEPLOYMENT.md) for detailed deployment instructions including:
- Railway.app (free tier)
- Fly.io (global edge)
- DigitalOcean ($5/mo)
- Self-hosted with nginx + SSL

## Integration with Atmosphere

### Mac (Atmosphere Server)

The relay URL is configured via environment variable:

```bash
export ATMOSPHERE_RELAY_URL="wss://relay.yourdomain.com"
atmosphere serve
```

The `/api/mesh/token` endpoint will include the relay URL:

```json
{
  "token": "ATM-ABC123...",
  "endpoints": {
    "local": "ws://192.168.1.100:11451",
    "public": "ws://73.x.x.x:11451",
    "relay": "wss://relay.yourdomain.com/relay/mesh-id"
  }
}
```

### Android (Atmosphere App)

The Android app tries endpoints in order:
1. **Local** - Same network, fastest
2. **Public** - Direct internet, requires port forwarding
3. **Relay** - Always works, slight latency

```kotlin
// In MeshConnection.kt
fun connect(endpoints: Endpoints) {
    // Try local first
    if (tryConnect(endpoints.local)) return
    
    // Try public if available
    if (endpoints.public != null && tryConnect(endpoints.public)) return
    
    // Fall back to relay
    connectViaRelay(endpoints.relay)
}
```

## Message Types

### Client → Server

| Type | Fields | Description |
|------|--------|-------------|
| `register` | `node_id`, `token`, `capabilities`, `name` | Initial registration |
| `broadcast` | `payload` | Send to all peers |
| `direct` | `target`, `payload` | Send to specific peer |
| `llm_request` | `request_id`, `prompt`, `model` | Request LLM completion |
| `llm_response` | `target`, `request_id`, `response` | LLM response |
| `ping` | - | Keepalive |
| `capabilities_update` | `capabilities` | Update capabilities |

### Server → Client

| Type | Fields | Description |
|------|--------|-------------|
| `peers` | `peers[]` | Initial peer list |
| `peer_joined` | `node_id`, `name`, `capabilities` | New peer notification |
| `peer_left` | `node_id` | Peer disconnect notification |
| `message` | `from`, `payload` | Message from another peer |
| `llm_request` | `from`, `request_id`, `prompt`, `model` | LLM request to process |
| `llm_response` | `from`, `request_id`, `response` | LLM response |
| `pong` | `timestamp` | Keepalive response |
| `error` | `message` | Error notification |

## Files

```
relay/
├── server.py           # FastAPI WebSocket relay server
├── Dockerfile          # Container build
├── docker-compose.yml  # Local development
├── requirements.txt    # Python dependencies
├── RELAY_DEPLOYMENT.md # Deployment guide
└── README.md           # This file
```

## Testing

### Manual Test with wscat

```bash
# Terminal 1: Start server
python server.py

# Terminal 2: First client (Mac)
wscat -c ws://localhost:8765/relay/test-mesh
> {"type":"register","node_id":"mac-1","capabilities":["llm"]}

# Terminal 3: Second client (Android)
wscat -c ws://localhost:8765/relay/test-mesh
> {"type":"register","node_id":"android-1","capabilities":[]}
> {"type":"llm_request","request_id":"1","prompt":"Hello!"}

# Back to Terminal 2 - you should see the llm_request
> {"type":"llm_response","target":"android-1","request_id":"1","response":"Hi there!"}

# Terminal 3 should receive the response
```

### Check Stats

```bash
curl http://localhost:8765/stats
```

## License

MIT - Part of the Atmosphere project
