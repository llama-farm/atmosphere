# Atmosphere Relay Server - LIVE 🚀

**Deployed:** 2026-02-03 13:22 CST
**Platform:** Railway.app
**Status:** ✅ OPERATIONAL

## Endpoints

| Endpoint | URL |
|----------|-----|
| **WebSocket** | `wss://atmosphere-relay-production.up.railway.app/relay/{mesh_id}` |
| **Health** | `https://atmosphere-relay-production.up.railway.app/health` |
| **Stats** | `https://atmosphere-relay-production.up.railway.app/stats` |

## Quick Test

```bash
# Health check
curl https://atmosphere-relay-production.up.railway.app/health

# Stats
curl https://atmosphere-relay-production.up.railway.app/stats
```

## Connection Flow

### Mac (mesh host):
```bash
# 1. Start local mesh
atmosphere serve

# 2. Connect to relay (auto-registers mesh)
wscat -c "wss://atmosphere-relay-production.up.railway.app/relay/home-mesh"
```

### Android (mesh client):
1. Scan QR code or enter mesh token
2. App connects to relay WebSocket
3. Messages relay through cloud to Mac
4. LLM requests forwarded to Mac's Ollama/LlamaFarm

## Architecture

```
┌─────────────────┐        ┌─────────────────────────────────┐        ┌─────────────────┐
│                 │        │                                 │        │                 │
│   Android App   │───────▶│   Railway Relay Server          │◀───────│   Mac Mesh      │
│  (cell data)    │  WSS   │  wss://atmosphere-relay-...     │  WSS   │  (home network) │
│                 │        │                                 │        │                 │
└─────────────────┘        └─────────────────────────────────┘        └─────────────────┘
         │                              │                                      │
         │                              │                                      │
         ▼                              ▼                                      ▼
    On-device LLM              Message Relay                          Ollama/LlamaFarm
    Camera, Mic, GPS           Peer Discovery                         146+ models
                               LLM Request Routing
```

## Message Protocol

### Join mesh:
```json
{"type": "join", "node_id": "rob-pixel", "capabilities": ["camera", "location", "llm"]}
```

### Send LLM request:
```json
{
  "type": "llm_request",
  "id": "req-123",
  "model": "llama3.2",
  "prompt": "Hello world"
}
```

### Receive LLM response:
```json
{
  "type": "llm_response",
  "id": "req-123",
  "content": "Hello! How can I help you today?"
}
```

## Next Steps

1. **Update Android app** to use relay URL
2. **Test end-to-end**: Phone on cell → Relay → Mac mesh
3. **Add relay URL to mesh tokens** (multi-path connectivity)
4. **Monitor Railway metrics** for production readiness

## Railway Dashboard

- **Project:** https://railway.com/project/13179799-c9dc-45b3-bae2-845e1906c09a
- **Logs:** `railway logs` (from relay directory)
- **Redeploy:** `railway up` (from relay directory)

## Cost

Railway free tier includes:
- 500 hours/month execution
- 100 GB bandwidth
- Automatic SSL
- Auto-sleep after 10 min inactivity (wakes on request)
