# Atmosphere Full Stack Execution Plan

**Goal:** Both Mac and Android apps fully functional, sharing models across ALL connectivity modes (BLE, WiFi Direct, LAN, Internet relay), with semantic routing, cost model, gossip protocol, camera/voice, and complete UI exposure.

---

## 🎯 Success Criteria

| Requirement | Mac | Android |
|-------------|-----|---------|
| Expose local models to mesh | ✅ Ollama + LlamaFarm | ⬜ llama.cpp + Qwen3-1.7B |
| Call remote models | ⬜ | ⬜ |
| LlamaFarm projects (discoverable) | ⬜ | N/A |
| BLE mesh connectivity | ⬜ | ⬜ |
| WiFi Direct connectivity | ⬜ | ⬜ |
| LAN connectivity | ✅ | ⬜ |
| Internet relay connectivity | ✅ | ⬜ |
| Camera capability | N/A | ⬜ |
| Voice capability | ⬜ | ⬜ |
| Gossip protocol (peer discovery) | ✅ | ⬜ |
| Cost model (continuous updates) | ✅ | ⬜ |
| Semantic router | ⬜ | ⬜ |
| Inter-node inference testing | ⬜ | ⬜ |
| Full UI exposure | ⬜ | ⬜ |

---

## Phase 1: Android On-Device LLM (Day 1-2)

### 1.1 llama.cpp Integration

**Goal:** Run Qwen3-1.7B locally on Android with a minimal LlamaFarm-style wrapper.

```
┌─────────────────────────────────────────────────────────┐
│                    Android App                          │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────┐   │
│  │           UniversalRuntime (Kotlin)              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────┐  │   │
│  │  │ System      │  │ Project     │  │ Simple  │  │   │
│  │  │ Prompts     │  │ Router      │  │ RAG DB  │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────┘  │   │
│  └────────────────────────┬────────────────────────┘   │
│                           │                             │
│  ┌────────────────────────▼────────────────────────┐   │
│  │              llama.cpp (JNI)                     │   │
│  │         unsloth/Qwen3-1.7B-GGUF:Q4_K_M          │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Tasks:**
- [ ] Add llama.cpp Android library (llama.android AAR or build from source)
- [ ] Download Qwen3-1.7B-Q4_K_M to app assets or external storage (~1GB)
- [ ] Create `LocalInferenceService.kt` - JNI wrapper for llama.cpp
- [ ] Create `UniversalRuntime.kt`:
  - System prompt management
  - Project/persona selection
  - Simple SQLite RAG store (embeddings optional, keyword search first)
- [ ] Expose model via mesh as capability: `{"type": "llm", "model": "qwen3-1.7b", "local": true}`
- [ ] Test: On-device inference works, model info exposed to mesh

**Files to Create:**
```
app/src/main/kotlin/com/llamafarm/atmosphere/
├── inference/
│   ├── LocalInferenceService.kt    # llama.cpp JNI wrapper
│   ├── UniversalRuntime.kt         # System prompts, project routing
│   └── SimpleRagStore.kt           # SQLite keyword search
├── model/
│   └── ModelManager.kt             # Download, load, manage GGUF files
```

### 1.2 Model Download UI

- [ ] Settings screen to download/delete models
- [ ] Progress indicator for large model downloads
- [ ] Storage usage display
- [ ] Model selection (if multiple models available)

---

## Phase 2: Mac LlamaFarm Projects Exposure (Day 2)

### 2.1 Discoverable Projects API

**Goal:** Mac app exposes LlamaFarm projects in the "discoverable" namespace.

**Tasks:**
- [ ] Query LlamaFarm API: `GET /api/projects?namespace=discoverable`
- [ ] Expose projects as mesh capabilities with metadata
- [ ] Each project becomes a callable "tool" on the mesh
- [ ] UI shows available projects from connected nodes

**API Integration:**
```python
# In atmosphere/discovery/llamafarm.py
async def discover_projects():
    """Get discoverable LlamaFarm projects."""
    resp = await client.get("http://localhost:14345/api/projects", 
                           params={"namespace": "discoverable"})
    projects = resp.json()
    return [
        Capability(
            name=f"project:{p['name']}",
            type="project",
            description=p.get("description", ""),
            metadata={"project_id": p["id"], "system_prompt": p.get("system_prompt")}
        )
        for p in projects
    ]
```

### 2.2 Project Execution

- [ ] Route intent to project → execute with project's system prompt
- [ ] Return structured response
- [ ] Track project usage in cost model

---

## Phase 3: Full Connectivity Stack (Day 2-3)

### 3.1 Connectivity Modes

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Connectivity Stack                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Priority 1: BLE (Always available, low power)                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Discovery, small messages, capability announcements             │ │
│  │ Mac: bleak library | Android: Android BLE API                  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  Priority 2: WiFi Direct (High bandwidth, no infrastructure)        │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Large transfers, streaming inference                            │ │
│  │ Mac: Not supported | Android: WifiP2pManager                   │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  Priority 3: LAN (Same network, fastest)                            │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Full mesh operations when on same WiFi                         │ │
│  │ Both: WebSocket to ws://192.168.x.x:11451                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  Priority 4: Internet Relay (Always works, highest latency)         │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ NAT traversal, cross-network mesh                              │ │
│  │ Both: WebSocket to wss://atmosphere-relay-production...        │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 BLE Implementation

**Mac (Python + bleak):**
- [ ] Create `atmosphere/transport/ble_mac.py`
- [ ] GATT server with Atmosphere service UUID
- [ ] Advertise node capabilities
- [ ] Scan for nearby Atmosphere nodes
- [ ] Message relay over BLE characteristics

**Android (Kotlin):**
- [ ] Create `transport/BleTransport.kt`
- [ ] BLE peripheral (advertise) + central (scan) modes
- [ ] GATT service matching Mac
- [ ] Characteristic read/write for messages
- [ ] Background BLE scanning with filters

### 3.3 WiFi Direct (Android only)

- [ ] Create `transport/WifiDirectTransport.kt`
- [ ] Service discovery using WifiP2pManager
- [ ] Group formation (one device becomes GO)
- [ ] Socket connection over WiFi Direct
- [ ] Fallback to BLE if WiFi Direct unavailable

### 3.4 Transport Manager

**Unified transport selection:**
```kotlin
class TransportManager {
    private val transports = listOf(
        BleTransport(),           // Always available
        WifiDirectTransport(),    // Android only, high bandwidth
        LanTransport(),           // Same network
        RelayTransport()          // Internet fallback
    )
    
    suspend fun connect(peer: PeerInfo): Transport {
        // Try transports in order until one works
        for (transport in transports) {
            if (transport.canConnect(peer)) {
                try {
                    return transport.connect(peer)
                } catch (e: Exception) {
                    continue
                }
            }
        }
        throw NoTransportAvailableException()
    }
}
```

---

## Phase 4: Camera & Voice Capabilities (Day 3)

### 4.1 Camera (Android)

- [ ] `CameraCapability.kt` - expose camera as mesh capability
- [ ] Trigger: Motion detection pushes events to mesh
- [ ] Tool: Remote snapshot request → returns image
- [ ] Privacy: Require explicit approval for each remote access
- [ ] Compression: JPEG quality configurable

### 4.2 Voice (Both platforms)

**Mac:**
- [ ] `atmosphere/capabilities/voice_mac.py`
- [ ] Microphone access (with permission)
- [ ] Speech-to-text using Whisper (local or API)
- [ ] Text-to-speech using system voices

**Android:**
- [ ] `capabilities/VoiceCapability.kt`
- [ ] SpeechRecognizer for STT
- [ ] TextToSpeech for TTS
- [ ] Wake word detection (optional)

---

## Phase 5: Gossip Protocol & Cost Model (Day 3-4)

### 5.1 Gossip Protocol

**Current state:** Basic implementation exists
**Needed:**
- [ ] Periodic heartbeat (every 30s)
- [ ] Capability announcements on change
- [ ] Cost factor broadcasting
- [ ] Peer list synchronization
- [ ] Dead peer detection (timeout after 3 missed heartbeats)

**Message types:**
```json
{"type": "heartbeat", "node_id": "...", "seq": 123, "load": 0.4}
{"type": "capabilities", "node_id": "...", "caps": [...]}
{"type": "cost", "node_id": "...", "factors": {...}}
{"type": "peer_list", "peers": [...]}
```

### 5.2 Cost Model (Continuous Updates)

**Mac (already implemented, needs polish):**
- [ ] CPU/memory/GPU utilization polling (every 10s)
- [ ] Battery state (if laptop)
- [ ] Network bandwidth estimation
- [ ] Model load times cached
- [ ] Broadcast cost factors via gossip

**Android (new):**
- [ ] Create `cost/CostCollector.kt`
- [ ] Battery level + charging state
- [ ] CPU usage (via /proc/stat or ActivityManager)
- [ ] Memory pressure
- [ ] Thermal state (throttling detection)
- [ ] Network type (WiFi vs cellular) + signal strength
- [ ] Background service for continuous collection
- [ ] Broadcast to mesh every 30s

**Cost formula:**
```
cost = base_cost 
     * battery_multiplier      # 1.0 if charging, 1.5-3.0 on battery
     * load_multiplier         # 1.0-2.0 based on CPU/memory
     * network_multiplier      # 1.0 WiFi, 1.5-2.0 cellular
     * thermal_multiplier      # 1.0-2.0 if throttling
```

---

## Phase 6: Semantic Router (Day 4)

### 6.1 Intent Classification

**Goal:** Route natural language intents to the best capability across the mesh.

```
User: "Take a photo of the front door"
        │
        ▼
┌───────────────────────────────────────┐
│         Semantic Router               │
│  ┌─────────────────────────────────┐  │
│  │ 1. Extract intent embedding     │  │
│  │ 2. Match against capability     │  │
│  │    embeddings                    │  │
│  │ 3. Filter by availability       │  │
│  │ 4. Rank by cost                 │  │
│  │ 5. Route to best node           │  │
│  └─────────────────────────────────┘  │
└───────────────────────────────────────┘
        │
        ▼
Route to: android-pixel.camera (cost: 0.3)
```

**Tasks:**
- [ ] Pre-compute embeddings for all capability descriptions
- [ ] On intent: compute embedding, find top-k matches
- [ ] Filter: only capabilities currently available
- [ ] Rank: by (similarity * (1 / cost))
- [ ] Route: forward request to selected node
- [ ] Fallback: if no match, return "no capability found"

### 6.2 Cross-Node Execution

- [ ] Request serialization (JSON over WebSocket)
- [ ] Response streaming for LLM
- [ ] Timeout handling
- [ ] Retry with next-best node on failure

---

## Phase 7: Inter-Node Testing UI (Day 4-5)

### 7.1 Test Panel (Both platforms)

**Features:**
- [ ] List all connected nodes with status
- [ ] For each node, show available capabilities
- [ ] "Test" button for each capability
- [ ] Results display (latency, response, errors)
- [ ] Inference test: send prompt, show response + timing

**UI Mockup:**
```
┌─────────────────────────────────────────────────────────────┐
│  Mesh Testing                                                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Connected Nodes (2)                                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 🖥️ rob-macbook (local)                    Cost: 0.12   │ │
│  │   └─ llm: llama3.2, qwen3:8b, mistral:7b + 143 more   │ │
│  │   └─ embeddings: mxbai-embed-large                     │ │
│  │   └─ project: medical-assistant                        │ │
│  │   [Test LLM] [Test Embedding]                          │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 📱 rob-pixel (relay)                      Cost: 0.45   │ │
│  │   └─ llm: qwen3-1.7b (on-device)                       │ │
│  │   └─ camera: back, front                               │ │
│  │   └─ location: gps                                     │ │
│  │   [Test LLM] [Test Camera] [Test Location]             │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│  Quick Test                                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Prompt: [Hello, what can you do?              ] [Send] │ │
│  │ Target: [Auto (semantic routing)          ▼]           │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  Results                                                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ✅ Routed to: rob-pixel.llm (qwen3-1.7b)               │ │
│  │ ⏱️ Latency: 234ms (relay) + 1.2s (inference)          │ │
│  │ Response: "Hello! I'm Qwen, a helpful assistant..."    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Connectivity Test

- [ ] Show current transport (BLE/WiFi Direct/LAN/Relay)
- [ ] Ping test to each node
- [ ] Bandwidth estimation
- [ ] Transport switching test

---

## Phase 8: Full UI Polish (Day 5)

### 8.1 Mac UI (React)

**Screens:**
- [ ] Dashboard: Mesh overview, node count, message stats
- [ ] Nodes: List with capabilities, cost, last seen
- [ ] Capabilities: All capabilities across mesh, grouped by type
- [ ] Projects: LlamaFarm discoverable projects
- [ ] Router: Semantic routing test interface
- [ ] Settings: Relay URL, ports, BLE enable/disable
- [ ] Testing: Inter-node inference testing

### 8.2 Android UI (Jetpack Compose)

**Screens:**
- [ ] Home: Connection status, local model status
- [ ] Mesh: Connected nodes, capabilities
- [ ] Local Model: Download, load, test on-device inference
- [ ] Camera: Preview, remote access permissions
- [ ] Settings: Model selection, cost preferences, transports
- [ ] Testing: Cross-mesh inference testing

---

## Phase 9: API Verification (Day 5)

### 9.1 Mac API Endpoints

| Endpoint | Method | Status | Test |
|----------|--------|--------|------|
| `/api/health` | GET | ✅ | ⬜ |
| `/api/mesh/status` | GET | ✅ | ⬜ |
| `/api/mesh/token` | POST | ✅ | ⬜ |
| `/api/mesh/nodes` | GET | ✅ | ⬜ |
| `/api/capabilities` | GET | ✅ | ⬜ |
| `/api/capabilities/scan` | POST | ✅ | ⬜ |
| `/api/cost` | GET | ✅ | ⬜ |
| `/api/route` | POST | ⬜ | ⬜ |
| `/api/execute` | POST | ⬜ | ⬜ |
| `/api/projects` | GET | ⬜ | ⬜ |
| `/v1/chat/completions` | POST | ✅ | ⬜ |
| `/v1/models` | GET | ✅ | ⬜ |
| `/api/ws` | WebSocket | ✅ | ⬜ |

### 9.2 Test Suite

- [ ] Create `tests/test_full_stack.py`
- [ ] Automated tests for each endpoint
- [ ] Cross-node inference test
- [ ] Transport fallback test
- [ ] Cost model accuracy test

---

## Execution Timeline

| Day | Phase | Deliverables |
|-----|-------|--------------|
| 1 | Android llama.cpp | Local inference working, model exposed to mesh |
| 2 | LlamaFarm projects + LAN connectivity | Projects discoverable, Android connects over LAN |
| 2-3 | BLE + WiFi Direct | Offline mesh discovery and messaging |
| 3 | Camera + Voice | Capabilities exposed and callable |
| 3-4 | Gossip + Cost | Continuous updates, network-wide visibility |
| 4 | Semantic Router | Intent-based routing working |
| 4-5 | Testing UI | Inter-node testing functional |
| 5 | Polish + Verification | Full UI, all APIs tested |

---

## Resource Requirements

### Android
- **Storage:** ~1.5GB for Qwen3-1.7B model
- **RAM:** ~2GB for inference
- **Permissions:** Camera, Microphone, Bluetooth, WiFi, Location

### Mac
- **Services:** Ollama, LlamaFarm (optional)
- **Ports:** 11451 (API), 11450 (gossip), 3007 (UI)
- **BLE:** Requires macOS 10.15+ and Bluetooth enabled

### Network
- **Relay:** wss://atmosphere-relay-production.up.railway.app (Railway free tier)

---

## Files to Create/Modify

### Android (23 files)
```
app/src/main/kotlin/com/llamafarm/atmosphere/
├── inference/
│   ├── LocalInferenceService.kt      # NEW
│   ├── UniversalRuntime.kt           # NEW
│   └── SimpleRagStore.kt             # NEW
├── model/
│   └── ModelManager.kt               # NEW
├── transport/
│   ├── TransportManager.kt           # NEW
│   ├── BleTransport.kt               # NEW
│   ├── WifiDirectTransport.kt        # NEW
│   ├── LanTransport.kt               # MODIFY (exists)
│   └── RelayTransport.kt             # MODIFY (exists)
├── capabilities/
│   ├── CameraCapability.kt           # NEW
│   └── VoiceCapability.kt            # NEW
├── cost/
│   └── CostCollector.kt              # NEW
├── ui/screens/
│   ├── TestingScreen.kt              # NEW
│   ├── LocalModelScreen.kt           # NEW
│   └── SettingsScreen.kt             # MODIFY
└── viewmodel/
    └── AtmosphereViewModel.kt        # MODIFY
```

### Mac/Python (15 files)
```
atmosphere/
├── transport/
│   ├── __init__.py                   # NEW
│   ├── ble_mac.py                    # NEW
│   └── manager.py                    # NEW
├── capabilities/
│   └── voice_mac.py                  # NEW
├── discovery/
│   └── llamafarm.py                  # MODIFY (add projects)
├── router/
│   └── semantic.py                   # MODIFY (improve)
├── api/
│   └── routes.py                     # MODIFY (add endpoints)
└── ui/src/
    ├── components/
    │   ├── TestingPanel.jsx          # NEW
    │   └── ProjectsPanel.jsx         # NEW
    └── App.jsx                       # MODIFY
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| llama.cpp Android build issues | Use pre-built AAR from llama.cpp releases |
| Qwen3-1.7B too slow on phone | Test on device first, have smaller fallback (TinyLlama) |
| BLE throughput too low | Use BLE for discovery only, upgrade to WiFi for data |
| WiFi Direct not on Mac | Accept Mac limitation, use LAN/relay instead |
| Railway free tier limits | Monitor usage, have Fly.io backup |

---

## Success Metrics

1. **Android runs local LLM** - Response in <5s for short prompts
2. **Cross-mesh inference** - Mac can call Android's model and vice versa
3. **BLE discovery works** - Devices find each other without WiFi
4. **All transports work** - Automatic fallback through the stack
5. **Cost model accurate** - Battery/load reflected in routing decisions
6. **Semantic routing** - "Take a photo" routes to camera capability
7. **UI complete** - All features accessible, no hidden functionality
