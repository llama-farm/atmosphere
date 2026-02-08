# Atmosphere Execution Plan - 2026-02-03

## ✅ COMPLETED TODAY

### 1. Emails Sent
- **Michelle Bland (BusPatrol)** - Confirmed meeting move to 3:00 PM CST tomorrow
- **Matt Feldhaus (DAV PBC)** - Offered 3:30-4:30 PM CST chat today, Friday lunch option

### 2. Relay Server Deployed to Railway 🚀
- **URL:** `wss://atmosphere-relay-production.up.railway.app`
- **Health:** `https://atmosphere-relay-production.up.railway.app/health`
- **Stats:** `https://atmosphere-relay-production.up.railway.app/stats`
- **Project:** https://railway.com/project/13179799-c9dc-45b3-bae2-845e1906c09a
- **Features:**
  - WebSocket relay for NAT traversal
  - Mesh rooms (multiple isolated meshes)
  - Peer discovery (auto-notify on join/leave)
  - LLM request forwarding
  - Accepts both `join` and `register` messages (Android + generic compatibility)

### 3. Mac Mesh Updated
- **Relay URL configured:** `~/.atmosphere/config.json` now includes `relay_url`
- **Tokens include relay:** `POST /api/mesh/token` now returns:
  ```json
  "endpoints": {
    "local": "ws://192.168.86.237:11451",
    "relay": "wss://atmosphere-relay-production.up.railway.app/relay/0b82206b236bd66c"
  }
  ```

### 4. Research Completed (by sub-agents)
- **Offline mesh research** - BLE, WiFi Aware, WiFi Direct, Matter integration
- **Key finding:** iOS 19 will support WiFi Aware due to EU DMA

---

## 🔄 NEXT STEPS

### Immediate (Today)
1. **Install APK on phone** - `~/Desktop/atmosphere-debug.apk`
2. **Test end-to-end over cell data:**
   - Phone → Relay (wss://atmosphere-relay-production.up.railway.app) → Mac
   - Send LLM request from phone → Get response from Mac's Ollama

### This Week
3. **Mac auto-connect to relay** - Background WebSocket to relay server
4. **LLM forwarding** - Mac handles `llm_request` messages from relay
5. **Multi-path token display** - UI shows all endpoints (local/public/relay)

### Later
6. **TURN server** - Custom implementation if Railway has limitations
7. **BLE mesh** - Start POC from research docs
8. **Voice bridge** - Need Telnyx API key

---

## Architecture

```
┌─────────────────┐         ┌──────────────────────────────────┐         ┌─────────────────┐
│                 │         │                                  │         │                 │
│   Android App   │────────▶│   Railway Relay                  │◀────────│   Mac Mesh      │
│                 │  WSS    │   atmosphere-relay-production    │  WSS    │   rob-macbook   │
│   - Camera      │         │   .up.railway.app                │         │   - Ollama      │
│   - Location    │         │                                  │         │   - LlamaFarm   │
│   - On-device   │         │   - Mesh rooms                   │         │   - 146 models  │
│     LLM         │         │   - Peer discovery               │         │                 │
│                 │         │   - LLM forwarding               │         │                 │
└─────────────────┘         └──────────────────────────────────┘         └─────────────────┘
```

---

## Key URLs

| Resource | URL |
|----------|-----|
| Relay WebSocket | `wss://atmosphere-relay-production.up.railway.app/relay/{mesh_id}` |
| Relay Health | https://atmosphere-relay-production.up.railway.app/health |
| Railway Dashboard | https://railway.com/project/13179799-c9dc-45b3-bae2-845e1906c09a |
| Mac API | http://localhost:11451/api |
| Mac UI | http://localhost:3007 |
| APK | `~/Desktop/atmosphere-debug.apk` |
| Offline Research | `~/clawd/projects/atmosphere/research/offline-mesh/` |

---

## Test Commands

```bash
# Test relay health
curl https://atmosphere-relay-production.up.railway.app/health

# Test relay stats
curl https://atmosphere-relay-production.up.railway.app/stats

# Generate new token (includes relay)
curl -X POST http://localhost:11451/api/mesh/token

# Test WebSocket connection
python3 -c "
import asyncio, json, websockets
async def test():
    async with websockets.connect('wss://atmosphere-relay-production.up.railway.app/relay/0b82206b236bd66c') as ws:
        await ws.send(json.dumps({'type':'join','node_id':'test','capabilities':[]}))
        print(await ws.recv())
asyncio.run(test())
"
```
