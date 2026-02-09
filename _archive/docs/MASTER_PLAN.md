# Atmosphere Master Plan

> **One API to route intelligence anywhere.**

---

## 🎯 Vision

Atmosphere exposes a **single unified API** that:
1. Accepts requests in standard formats (OpenAI, etc.)
2. Routes to the right capability on the right node
3. Abstracts away where/how execution happens

**Simple case:** "Hey, run this prompt" → routes to best available LLM  
**Complex case:** Blob of data + metadata → agents figure out what operations to run

---

## 📐 Architecture Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                              │
│   Any OpenAI-compatible client, curl, SDK, custom app           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API LAYER (Atmosphere)                      │
│                                                                  │
│  OpenAI-Compatible:           Specialized:                       │
│  ├─ POST /v1/chat/completions ├─ POST /v1/ml/anomaly            │
│  ├─ POST /v1/completions      ├─ POST /v1/ml/classify           │
│  ├─ POST /v1/embeddings       ├─ POST /v1/ml/cluster            │
│  ├─ GET  /v1/models           ├─ POST /v1/ml/forecast           │
│  └─ POST /v1/images/generate  └─ POST /v1/execute (blob mode)   │
│                                                                  │
│  Meta:                        Discovery:                         │
│  ├─ GET  /v1/capabilities     ├─ GET  /v1/mesh/nodes            │
│  ├─ GET  /v1/health           ├─ GET  /v1/mesh/topology         │
│  └─ WS   /v1/stream           └─ POST /v1/mesh/join             │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ROUTER LAYER                               │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │   Intent     │  │  Capability  │  │   Node Selection     │   │
│  │   Parser     │  │   Matcher    │  │   (load, latency,    │   │
│  │              │  │              │  │    specialization)   │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│                                                                  │
│  Simple: model specified → route to node with that model        │
│  Smart:  no model specified → pick best for the task            │
│  Blob:   raw data + metadata → agents decompose & orchestrate   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     EXECUTION LAYER                              │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  LlamaFarm  │  │   Ollama    │  │   Remote    │              │
│  │  (local)    │  │   (local)   │  │   Nodes     │              │
│  │             │  │             │  │             │              │
│  │ • 53 LLMs   │  │ • 26 models │  │ • Matt's    │              │
│  │ • 802 anom  │  │             │  │   Dell      │              │
│  │ • 190 class │  │             │  │ • Cloud     │              │
│  │ • 7 routers │  │             │  │   workers   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔌 API Specification

### Tier 1: OpenAI-Compatible (drop-in replacement)

These endpoints match OpenAI's API exactly. Any client that works with OpenAI works with Atmosphere.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Chat with any LLM |
| `/v1/completions` | POST | Text completion |
| `/v1/embeddings` | POST | Generate embeddings |
| `/v1/models` | GET | List available models |
| `/v1/images/generations` | POST | Generate images |

**Key difference:** `model` field can be:
- Specific: `"llama3.2:latest"` → routes to node with that model
- Capability: `"best-code"` → routes to best coding model available
- Omitted: Router picks based on prompt analysis

### Tier 2: Specialized ML Endpoints

For operations that don't fit the OpenAI mold.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/ml/anomaly` | POST | Anomaly detection (detect/fit/score) |
| `/v1/ml/classify` | POST | Classification (predict/fit) |
| `/v1/ml/cluster` | POST | Clustering operations |
| `/v1/ml/forecast` | POST | Time series forecasting |
| `/v1/ml/embed` | POST | Custom embeddings (non-OpenAI format) |

### Tier 3: Blob Mode (Complex Orchestration)

For when you don't know exactly what you need — just throw data at it.

```
POST /v1/execute
{
  "data": <any blob>,
  "metadata": {
    "source": "sensor-array-7",
    "type": "timeseries",
    "columns": ["timestamp", "temp", "pressure", "vibration"],
    "goal": "find anomalies and predict failures"
  },
  "hints": ["urgent", "high-precision"],
  "callback": "https://my-app.com/webhook"
}
```

**Router behavior:**
1. Parse metadata to understand data structure
2. Analyze goal to determine required operations
3. Decompose into sub-tasks (anomaly detection → classification → alerting)
4. Route each sub-task to appropriate capability
5. Orchestrate results, return or callback

### Tier 4: Mesh & Discovery

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/mesh/nodes` | GET | List all nodes in mesh |
| `/v1/mesh/topology` | GET | Network topology graph |
| `/v1/mesh/join` | POST | Join this node to mesh |
| `/v1/mesh/capabilities` | GET | Aggregate capabilities across mesh |
| `/v1/mesh/route` | POST | Dry-run: show where a request would route |

---

## 🧠 Router Intelligence

### Level 1: Direct Routing
```
Request: model="llama3.2:latest"
Action: Find node with llama3.2:latest, route there
```

### Level 2: Capability Routing
```
Request: model="best-code" or no model + code-like prompt
Action: 
  1. Identify this is a coding task
  2. Find nodes with coding-optimized models
  3. Select best based on load/latency/specialization
  4. Route there
```

### Level 3: Semantic Routing
```
Request: "analyze this data for patterns"
Action:
  1. Parse intent → "pattern analysis"
  2. Match to capabilities → [anomaly, clustering, classification]
  3. Select most appropriate
  4. Route
```

### Level 4: Orchestrated Routing (Blob Mode)
```
Request: blob + metadata + goal
Action:
  1. Understand data structure
  2. Decompose goal into operations
  3. Build execution graph
  4. Dispatch to multiple nodes in parallel/sequence
  5. Aggregate results
  6. Return or callback
```

---

## 📋 Implementation Phases

### Phase 1: OpenAI-Compatible Core ✅ (partially done)
- [x] Basic server running
- [x] `/v1/models` endpoint
- [ ] `/v1/chat/completions` (full OpenAI spec)
- [ ] `/v1/completions`
- [ ] `/v1/embeddings`
- [ ] Model aliasing (abstract → concrete)

### Phase 2: ML Endpoints ✅ (done)
- [x] `/v1/ml/anomaly`
- [x] `/v1/ml/classify`
- [x] Intent routing for ML operations
- [ ] `/v1/ml/cluster`
- [ ] `/v1/ml/forecast`

### Phase 3: Smart Router
- [ ] Capability-based model selection
- [ ] Load balancing across nodes
- [ ] Latency-aware routing
- [ ] Specialization scoring

### Phase 4: Blob Mode
- [ ] Metadata parser
- [ ] Goal decomposition
- [ ] Execution graph builder
- [ ] Multi-node orchestration
- [ ] Result aggregation

### Phase 5: Mesh Networking
- [ ] mDNS discovery (fix async issue)
- [ ] STUN/NAT traversal
- [ ] Multi-machine routing
- [ ] Capability gossip

### Phase 6: Production Hardening
- [ ] Authentication (Rownd-local)
- [ ] Rate limiting
- [ ] Caching layer
- [ ] Metrics/observability
- [ ] WebSocket streaming

---

## 🎯 Success Criteria

### MVP (Week 1)
- [ ] Any OpenAI client can point to Atmosphere and get responses
- [ ] `curl -X POST localhost:11451/v1/chat/completions` works
- [ ] Requests route to LlamaFarm/Ollama automatically
- [ ] UI shows routing decisions in real-time

### Full Product (Month 1)
- [ ] Multi-node mesh working (Rob ↔ Matt)
- [ ] Blob mode functional
- [ ] Smart routing picks best model for task
- [ ] <100ms routing overhead

### Scale (Month 3)
- [ ] 100+ nodes in mesh
- [ ] Edge deployment tested
- [ ] Learning loop: edge → cloud → retrain → redeploy

---

## 📁 File Structure

```
atmosphere/
├── api/
│   ├── server.py           # FastAPI app
│   ├── routes.py           # All route definitions
│   ├── openai/             # OpenAI-compatible endpoints
│   │   ├── chat.py         # /v1/chat/completions
│   │   ├── completions.py  # /v1/completions
│   │   ├── embeddings.py   # /v1/embeddings
│   │   └── models.py       # /v1/models
│   ├── ml/                 # Specialized ML endpoints
│   │   ├── anomaly.py
│   │   ├── classify.py
│   │   └── cluster.py
│   └── mesh/               # Mesh endpoints
│       ├── nodes.py
│       └── topology.py
├── router/
│   ├── intent.py           # Intent parsing
│   ├── capability.py       # Capability matching
│   ├── selector.py         # Node selection
│   └── orchestrator.py     # Blob mode orchestration
├── adapters/
│   ├── llamafarm.py        # LlamaFarm adapter
│   ├── ollama.py           # Ollama adapter
│   └── remote.py           # Remote node adapter
├── mesh/
│   ├── discovery.py        # mDNS/gossip
│   ├── gossip.py           # State sync
│   └── network.py          # STUN/NAT
└── ui/                     # React dashboard
```

---

## 🚀 Next Actions

1. **Implement `/v1/chat/completions`** with full OpenAI spec
2. **Fix the model routing** so it picks from available nodes
3. **Add model aliasing** (`best-code` → actual model)
4. **Test with real OpenAI client** (Python SDK, etc.)

---

*Last updated: 2026-02-02*
