# Atmosphere Sprint Tasks - Parallel Execution

## Work Streams (Can Run in Parallel)

### Stream A: Android llama.cpp + On-Device LLM
**Complexity:** HIGH | **Est:** 4-6 hours
- Integrate llama.cpp Android library
- Download Qwen3-1.7B-Q4_K_M model (~1GB)
- Create UniversalRuntime wrapper
- Simple SQLite RAG store
- Expose model as mesh capability

### Stream B: Mac LlamaFarm Projects
**Complexity:** MEDIUM | **Est:** 2-3 hours
- Query LlamaFarm `/api/projects?namespace=discoverable`
- Expose projects as capabilities
- Update UI to show projects
- Project-based routing

### Stream C: BLE Transport (Mac + Android)
**Complexity:** HIGH | **Est:** 4-6 hours
- Mac: bleak-based BLE GATT server
- Android: BLE peripheral + central
- Shared service UUID and protocol
- Discovery and small message relay

### Stream D: Gossip + Cost (Android)
**Complexity:** MEDIUM | **Est:** 3-4 hours
- CostCollector for Android
- Battery, CPU, thermal, network monitoring
- Gossip message broadcasting
- Cost factor updates every 30s

### Stream E: Semantic Router Polish
**Complexity:** MEDIUM | **Est:** 2-3 hours
- Pre-computed capability embeddings
- Intent matching with cosine similarity
- Cost-aware ranking
- Cross-node execution

### Stream F: Testing UI (Both platforms)
**Complexity:** MEDIUM | **Est:** 3-4 hours
- Node list with capabilities
- Test buttons for each capability
- Inter-node inference testing
- Results display

### Stream G: Camera + Voice (Android)
**Complexity:** MEDIUM | **Est:** 2-3 hours
- Camera capability (snapshot on request)
- Voice STT/TTS capability
- Permission handling
- Mesh exposure

### Stream H: Full API Verification
**Complexity:** LOW | **Est:** 2 hours
- Test all endpoints
- Fix any broken routes
- Document API completely
- Create test suite

---

## Recommended Parallel Assignment

| Agent | Streams | Focus |
|-------|---------|-------|
| Main | Coordination, Stream B, E | Mac-side, routing |
| Sub-Agent 1 | Stream A | Android llama.cpp (critical path) |
| Sub-Agent 2 | Stream C | BLE transport (both platforms) |
| Sub-Agent 3 | Stream D, G | Android cost + capabilities |
| Sub-Agent 4 | Stream F, H | UI + testing |

---

## Critical Path

```
Stream A (Android LLM)
    │
    ▼
Stream D (Android Cost) ──────┐
    │                         │
    ▼                         ▼
Stream G (Camera/Voice)   Stream F (Testing UI)
    │                         │
    └──────────┬──────────────┘
               │
               ▼
         Integration Test
```

BLE (Stream C) and Mac Projects (Stream B) can run independently.

---

## Immediate First Actions

1. **Check llama.cpp Android options** - AAR available? Build required?
2. **Check LlamaFarm API** - Does `/api/projects` endpoint exist?
3. **Verify BLE permissions** - Mac and Android ready?
4. **Start parallel work streams**
