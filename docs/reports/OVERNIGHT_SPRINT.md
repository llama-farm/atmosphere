# Atmosphere Overnight Sprint - Due 8am Feb 4, 2026

## Goal
Complete working mesh with:
1. ✅ Mac ↔ Android connectivity via relay (DONE - basic connection working)
2. 🔄 Peer visibility in both UIs
3. 🔄 Gossip protocol broadcasting capabilities
4. 🔄 Semantic routing to correct node AND model
5. 🔄 LlamaFarm project integration (prompts, RAG, etc.)
6. 🔄 Android inference via relay to Mac LlamaFarm

## Current State
- ✅ Relay deployed at `wss://atmosphere-relay-production.up.railway.app`
- ✅ Mac connects to relay, receives messages
- ✅ Android can scan QR and join mesh
- ✅ Mac has 1 capability registered: `llamafarm/discoverable/llama-expert-14`
- ❌ Peer visibility not showing in UI (both sides)
- ❌ Gossip not propagating capabilities
- ❌ Android LLM requests not routing through relay
- ❌ Semantic routing doesn't select optimal model

## Architecture

```
┌─────────────┐     Relay     ┌─────────────┐
│   Android   │◄────────────►│     Mac     │
│  (phone)    │    WebSocket  │  (server)   │
│             │               │             │
│ Capabilities│               │ Capabilities│
│ - camera    │               │ - LlamaFarm │
│ - mic       │               │   projects  │
│ - location  │               │ - 112 total │
└─────────────┘               └─────────────┘
```

## Critical Files

### Mac (Python)
- `atmosphere/api/server.py` - Main server, relay connection
- `atmosphere/api/routes.py` - API endpoints
- `atmosphere/router/semantic.py` - Semantic routing
- `atmosphere/router/fast_router.py` - Fast LlamaFarm project router
- `atmosphere/mesh/gossip.py` - Gossip protocol
- `atmosphere/network/relay.py` - Relay client
- `relay/server.py` - Relay server (Railway)

### Android (Kotlin)
- `AtmosphereViewModel.kt` - Main state management
- `MeshConnection.kt` - WebSocket to relay
- `SemanticRouter.kt` - Local routing
- `DefaultCapabilities.kt` - Device capabilities
- `MeshScreen.kt` - Main UI
- `TransportSettingsScreen.kt` - Transport status

## Sprint Tasks

### Phase 1: Mesh Visibility (2 hours)
1. Fix Mac `_relay_peers` tracking - peers from relay
2. Update mesh status API to include relay peers
3. Fix gossip to broadcast capabilities to relay
4. Android: Update UI to show peers from relay
5. Android: Fix TransportSettingsScreen status

### Phase 2: Gossip Protocol (2 hours)
1. Mac: Send capability announcements via relay
2. Relay: Forward gossip messages to mesh
3. Android: Receive and process gossip
4. Both: Maintain capability registry from gossip

### Phase 3: Semantic Routing (2 hours)
1. Review FastProjectRouter - 112 LlamaFarm projects
2. Implement intent→project matching
3. Route to specific project endpoint
4. Handle project prompts, RAG, etc.
5. Return structured responses

### Phase 4: Inference Flow (2 hours)
1. Android: Send LLM requests via relay
2. Relay: Forward to appropriate node
3. Mac: Execute via LlamaFarm project
4. Return response through relay
5. Android: Display response

### Phase 5: Testing & Polish (2 hours)
1. End-to-end test: Android→Mac LLM
2. Test capability visibility both ways
3. Test gossip propagation
4. Test semantic routing accuracy
5. Build release APK
6. Document any remaining issues

## Key Endpoints

### LlamaFarm
- `POST /v1/projects/{namespace}/{project}/chat/completions` - Chat with project
- `GET /v1/projects` - List all projects
- `GET /v1/projects?discoverable=true` - Discoverable projects

### Atmosphere Mac
- `GET /api/mesh/status` - Mesh state
- `GET /api/capabilities` - Local capabilities  
- `POST /api/route` - Route intent
- `POST /api/chat/completions` - OpenAI-compatible chat
- `WS /api/ws` - WebSocket for updates

### Relay
- `WS /relay/{mesh_id}` - Mesh WebSocket
- Messages: `join`, `peer_joined`, `peers`, `broadcast`, `chat_request`

## Success Criteria
By 8am:
1. Scan QR → Android joins mesh → visible on Mac UI
2. Mac capabilities visible on Android
3. Type message on Android → routes to Mac LlamaFarm → response displayed
4. All transports show correct status
5. No crashes, clean builds

## Notes
- Use LlamaFarm `universal` provider, NOT Ollama
- FastProjectRouter has embeddings for 112 projects
- Android native inference blocked (needs libllama-android.so)
- Focus on relay path for now
