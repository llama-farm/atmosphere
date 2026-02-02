# LlamaFarm + Atmosphere: Architecture Diagrams

**Visual companion to LLAMAFARM_INTEGRATION.md**

---

## 1. System Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                USER LAYER                                    │
│                                                                              │
│  User: "Analyze this contract"                                              │
│  CLI / Web UI / API / Agent                                                 │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ATMOSPHERE LAYER                                    │
│                        (Orchestration & Routing)                             │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ Intent Router   │  │ Semantic Match  │  │ Load Balancer   │             │
│  │                 │  │                 │  │                 │             │
│  │ Embed: "analyze │→ │ Score caps:     │→ │ Select best:    │             │
│  │ contract legal" │  │ - RAG: 0.93 ✓   │  │ Node B (70B)    │             │
│  │                 │  │ - LLM: 0.87     │  │ Load: 30%       │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────┐               │
│  │                    GRADIENT TABLE                         │               │
│  │  (Local routing cache, updated via gossip)               │               │
│  │                                                           │               │
│  │  Capability           Node        Hops  Score  Updated   │               │
│  │  llamafarm:rag:legal  node-b      2     0.93   1s ago    │               │
│  │  llamafarm:llm:70b    node-b      2     0.91   1s ago    │               │
│  │  llamafarm:llm:7b     local       0     0.88   now       │               │
│  │  ollama:llm:qwen      node-c      3     0.85   5s ago    │               │
│  └──────────────────────────────────────────────────────────┘               │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ADAPTER LAYER                                     │
│                         (Backend Integration)                                │
│                                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                    │
│  │ LlamaFarm    │   │ Ollama       │   │ Matter       │                    │
│  │ Adapter      │   │ Adapter      │   │ Adapter      │                    │
│  │              │   │              │   │              │                    │
│  │ - Discovery  │   │ - Discovery  │   │ - Discovery  │                    │
│  │ - Enumerate  │   │ - Enumerate  │   │ - Enumerate  │                    │
│  │ - Execute    │   │ - Execute    │   │ - Execute    │                    │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘                    │
└─────────┼──────────────────┼──────────────────┼──────────────────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKEND LAYER                                        │
│                      (Actual Execution)                                      │
│                                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                    │
│  │ LlamaFarm    │   │ Ollama       │   │ Thread       │                    │
│  │ Core         │   │ Server       │   │ Border       │                    │
│  │              │   │              │   │ Router       │                    │
│  │ :14345       │   │ :11434       │   │              │                    │
│  │              │   │              │   │              │                    │
│  │ • Projects   │   │ • Models     │   │ • Devices    │                    │
│  │ • Models     │   │ • Simple API │   │ • Matter     │                    │
│  │ • RAG        │   │              │   │              │                    │
│  └──────────────┘   └──────────────┘   └──────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Operation Modes

### Standalone Mode

```
┌────────────────────────────────────────┐
│           Mac Studio                   │
│                                        │
│  ┌──────────────────────────────────┐  │
│  │        LlamaFarm Core            │  │
│  │                                  │  │
│  │  • Models: Llama 3.2, Flux      │  │
│  │  • Projects: RAG-Docs           │  │
│  │  • API: http://localhost:14345  │  │
│  │                                  │  │
│  │  No mesh, no networking         │  │
│  └──────────────────────────────────┘  │
│                                        │
│  User → Local API → LlamaFarm          │
│                                        │
└────────────────────────────────────────┘

Use Case: Privacy-critical, single machine
```

### Provider Mode

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Dell GPU Server                                  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                    Atmosphere Node                              │     │
│  │                                                                 │     │
│  │  Mode: provider                                                 │     │
│  │  Discoverable: true                                             │     │
│  │                                                                 │     │
│  │  ┌────────────────────────────────────────────────────────┐    │     │
│  │  │  Gossip: BROADCAST capabilities                        │    │     │
│  │  │  - llamafarm:llm:70b                                   │    │     │
│  │  │  - llamafarm:llm:405b                                  │    │     │
│  │  │  - llamafarm:embeddings:bge-large                      │    │     │
│  │  │                                                         │    │     │
│  │  │  Listen: ACCEPT work from mesh                         │    │     │
│  │  │  Route: NEVER (don't consume from mesh)               │    │     │
│  │  └────────────────────────────────────────────────────────┘    │     │
│  │                         │                                       │     │
│  │                         ▼                                       │     │
│  │  ┌────────────────────────────────────────────────────────┐    │     │
│  │  │              LlamaFarm Core                             │    │     │
│  │  │                                                         │    │     │
│  │  │  • 4x RTX 4090 GPUs                                    │    │     │
│  │  │  • 128GB VRAM                                          │    │     │
│  │  │  • Models: 70B, 405B, embeddings                      │    │     │
│  │  │  • Max concurrent: 8                                   │    │     │
│  │  └────────────────────────────────────────────────────────┘    │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
│  Provides: Heavy computation for entire mesh                            │
│  Never consumes: Focused on serving                                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

Use Case: Dedicated inference server
```

### Participant Mode (Most Common)

```
┌──────────────────────────────────┐      ┌──────────────────────────────────┐
│        Mac Studio                │      │       Dell Server                │
│                                  │      │                                  │
│  ┌────────────────────────────┐  │      │  ┌────────────────────────────┐  │
│  │   Atmosphere Node          │  │      │  │   Atmosphere Node          │  │
│  │                            │  │      │  │                            │  │
│  │  Mode: participant         │◄─┼──────┼─►│  Mode: participant         │  │
│  │                            │  │      │  │                            │  │
│  │  • Broadcast capabilities  │  │gossip│  │  • Broadcast capabilities  │  │
│  │  • Accept work from mesh   │  │      │  │  • Accept work from mesh   │  │
│  │  • Route to mesh when      │  │      │  │  • Route to mesh when      │  │
│  │    local can't handle      │  │      │  │    local can't handle      │  │
│  │                            │  │      │  │                            │  │
│  └──────────┬─────────────────┘  │      │  └──────────┬─────────────────┘  │
│             │                    │      │             │                    │
│             ▼                    │      │             ▼                    │
│  ┌────────────────────────────┐  │      │  ┌────────────────────────────┐  │
│  │     LlamaFarm Core         │  │      │  │     LlamaFarm Core         │  │
│  │                            │  │      │  │                            │  │
│  │  • 7B models (fast)        │  │      │  │  • 70B models (powerful)   │  │
│  │  • Embeddings              │  │      │  │  • Vision                  │  │
│  │  • RAG-Docs                │  │      │  │  • RAG-Legal               │  │
│  └────────────────────────────┘  │      │  └────────────────────────────┘  │
│                                  │      │                                  │
└──────────────────────────────────┘      └──────────────────────────────────┘

           │                                          │
           │  Task: "Analyze contract (70B)"          │
           │                                          │
           └──────────────────route──────────────────►│
                            (2 hops)                  │
                                                      │
                                         Execute + return result

Use Case: Developer workstation + GPU server
```

### Headless Mode

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Kubernetes Pod (Docker)                             │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                    Atmosphere Node                              │     │
│  │                                                                 │     │
│  │  Mode: headless                                                 │     │
│  │  Discoverable: true                                             │     │
│  │                                                                 │     │
│  │  UI: DISABLED                                                   │     │
│  │  Direct API: DISABLED (mesh-only)                              │     │
│  │  Logging: ERROR level only                                      │     │
│  │  Resources: Optimized for throughput                            │     │
│  │                                                                 │     │
│  └────────────────────────────┬───────────────────────────────────┘     │
│                               │                                         │
│                               ▼                                         │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │              LlamaFarm Core (Headless)                          │     │
│  │                                                                 │     │
│  │  Project: rag-production (only this exposed)                   │     │
│  │  Max concurrent: 20                                             │     │
│  │  Auto-restart: Yes                                              │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

Kubernetes HPA:
- Scale up if mesh load > 70%
- Scale down if mesh load < 20%
- Min replicas: 1
- Max replicas: 10

Use Case: Production inference in cloud/k8s
```

---

## 3. Capability Registration Flow

```
T=0s: LlamaFarm Starts
│
│  ┌────────────────────────────────────────────────────────┐
│  │              LlamaFarm Core Init                       │
│  │                                                        │
│  │  1. Load config from ~/.llamafarm/config.yaml        │
│  │  2. Parse atmosphere section                          │
│  │  3. Start HTTP server (:14345)                        │
│  │  4. Load models                                        │
│  │  5. Start projects (RAG, agents)                      │
│  │  6. Health endpoint ready: /health                    │
│  └────────────────────────────────────────────────────────┘
│
│
T=1s: Atmosphere Starts
│
│  ┌────────────────────────────────────────────────────────┐
│  │              Atmosphere Node Init                      │
│  │                                                        │
│  │  1. Load node identity                                │
│  │  2. Start gossip protocol                             │
│  │  3. Start adapter discovery                           │
│  └────────────────────────────────────────────────────────┘
│           │
│           ▼
│  ┌────────────────────────────────────────────────────────┐
│  │         Backend Discovery (automatic)                  │
│  │                                                        │
│  │  Scanning:                                             │
│  │  • http://localhost:14345 (LlamaFarm)  → ✓ Found      │
│  │  • http://localhost:11434 (Ollama)     → ✗ Not found  │
│  │  • http://localhost:8000 (vLLM)        → ✗ Not found  │
│  └────────────────────────────────────────────────────────┘
│           │
│           ▼
T=2s: Adapter Connection
│
│  ┌────────────────────────────────────────────────────────┐
│  │      LlamaFarm Adapter.connect()                       │
│  │                                                        │
│  │  GET http://localhost:14345/health                    │
│  │  → 200 OK                                              │
│  │                                                        │
│  │  GET http://localhost:14345/v1/models                 │
│  │  → {data: [{id: "llama3.2-7b"}, {id: "flux-dev"}]}   │
│  │                                                        │
│  │  GET http://localhost:14345/v1/projects               │
│  │  → {data: [{id: "rag-docs", type: "rag"}]}           │
│  └────────────────────────────────────────────────────────┘
│           │
│           ▼
│  ┌────────────────────────────────────────────────────────┐
│  │      Build Capabilities                                │
│  │                                                        │
│  │  Capability 1:                                         │
│  │    id: llamafarm:llm:llama3.2-7b                      │
│  │    type: llm                                           │
│  │    description: "Efficient LLM for text generation"   │
│  │    embedding: [0.23, -0.41, ...] (384-dim)            │
│  │                                                        │
│  │  Capability 2:                                         │
│  │    id: llamafarm:vision:flux-dev                      │
│  │    type: vision                                        │
│  │    description: "Image generation with Flux"          │
│  │    embedding: [0.56, 0.78, ...]                       │
│  │                                                        │
│  │  Capability 3:                                         │
│  │    id: llamafarm:rag:docs                             │
│  │    type: rag                                           │
│  │    description: "Documentation knowledge base"        │
│  │    embedding: [-0.12, 0.34, ...]                      │
│  └────────────────────────────────────────────────────────┘
│           │
│           ▼
T=3s: Capability Announcement
│
│  ┌────────────────────────────────────────────────────────┐
│  │      Gossip: Capability Broadcast                      │
│  │                                                        │
│  │  Message Type: capability_announcement                │
│  │  From: node-mac-studio-abc123                         │
│  │  Timestamp: 1706900003                                │
│  │                                                        │
│  │  Capabilities: [3 total]                              │
│  │  Resources:                                            │
│  │    load: 0.1 (idle)                                   │
│  │    queue_depth: 0                                     │
│  │    vram_available: 32GB                               │
│  │                                                        │
│  │  Signature: ed25519_sig...                            │
│  └────────────────────────────────────────────────────────┘
│           │
│           │  Gossip fanout = 3
│           │
│           ├─────────────────► Peer 1 (1 hop)
│           │                   │
│           │                   └──► Peer 4 (2 hops)
│           │
│           ├─────────────────► Peer 2 (1 hop)
│           │                   │
│           │                   └──► Peer 5 (2 hops)
│           │
│           └─────────────────► Peer 3 (1 hop)
│                               │
│                               └──► Peer 6 (2 hops)
│
T=3s+10ms: All peers updated
│
│  ┌────────────────────────────────────────────────────────┐
│  │      Gradient Table Updated (on all nodes)             │
│  │                                                        │
│  │  Node: mac-studio                                      │
│  │  Capabilities added:                                   │
│  │    - llamafarm:llm:llama3.2-7b                        │
│  │    - llamafarm:vision:flux-dev                        │
│  │    - llamafarm:rag:docs                               │
│  │                                                        │
│  │  Ready to route intents!                              │
│  └────────────────────────────────────────────────────────┘
│
│
✓ Integration Complete (3s total)
```

---

## 4. Intent Routing Example

```
User: "Summarize this 20-page legal contract"

┌────────────────────────────────────────────────────────────────────────┐
│ T=0ms: Intent Received (Node A - Mac Studio)                           │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  User Input: "Summarize this 20-page legal contract"         │      │
│  │  Document: 20 pages, 15,000 words                            │      │
│  │  Context: Legal domain, high accuracy required               │      │
│  └──────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=10ms: Intent Embedding                                               │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  Embed intent:                                                │      │
│  │  "summarize legal contract document analysis reasoning"      │      │
│  │                                                               │      │
│  │  Result: [0.234, -0.123, 0.456, ..., 0.789]  (384 dims)     │      │
│  └──────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=12ms: Semantic Matching (Query Gradient Table)                       │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  Comparing to all capabilities:                               │      │
│  │                                                               │      │
│  │  Candidate 1: llamafarm:llm:llama3.2-7b (local, 0 hops)     │      │
│  │    Similarity: 0.87                                          │      │
│  │    Penalty: none (local)                                     │      │
│  │    Boost: none (small model)                                 │      │
│  │    Load: 0.1 (idle) → 1.1x boost                            │      │
│  │    Final: 0.87 * 1.1 = 0.96                                 │      │
│  │                                                               │      │
│  │  Candidate 2: llamafarm:llm:llama3.2-70b (Node B, 2 hops)   │      │
│  │    Similarity: 0.91                                          │      │
│  │    Penalty: 0.95^2 = 0.90 (2 hops)                          │      │
│  │    Boost: 1.2x (large model for complex reasoning)          │      │
│  │    Load: 0.3 (light) → 1.05x boost                          │      │
│  │    Final: 0.91 * 0.90 * 1.2 * 1.05 = 1.03  ✓ BEST          │      │
│  │                                                               │      │
│  │  Candidate 3: llamafarm:rag:legal (Node B, 2 hops)          │      │
│  │    Similarity: 0.93                                          │      │
│  │    Penalty: 0.95^2 = 0.90                                    │      │
│  │    Note: RAG for retrieval, not summarization               │      │
│  │    Final: 0.93 * 0.90 = 0.84                                │      │
│  │                                                               │      │
│  │  Decision: Route to llamafarm:llm:llama3.2-70b on Node B    │      │
│  └──────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=15ms: Routing Decision                                               │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  Route:                                                       │      │
│  │    From: Node A (mac-studio)                                 │      │
│  │    To:   Node B (dell-server)                                │      │
│  │    Via:  Direct connection                                   │      │
│  │    Hops: 2                                                    │      │
│  │                                                               │      │
│  │  Capability: llamafarm:llm:llama3.2-70b                      │      │
│  │  Estimated latency: 50ms routing + 5000ms inference          │      │
│  └──────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            │  Forward request
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=20ms: Request Forwarding                                             │
│                                                                         │
│  Node A ─────────────────────────────────► Node B                      │
│                                                                         │
│  POST http://node-b:14345/v1/chat/completions                          │
│  {                                                                      │
│    "model": "llama3.2-70b",                                            │
│    "messages": [                                                        │
│      {                                                                  │
│        "role": "user",                                                  │
│        "content": "Summarize this contract:\n\n[20 pages...]"         │
│      }                                                                  │
│    ],                                                                   │
│    "temperature": 0.3,  // Low temp for factual summary               │
│    "max_tokens": 2048                                                  │
│  }                                                                      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=70ms: Execution on Node B                                            │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  LlamaFarm Core (Node B)                                     │      │
│  │                                                               │      │
│  │  1. Receive request                                          │      │
│  │  2. Check if model loaded (llama3.2-70b)                    │      │
│  │     → Loaded, proceed                                        │      │
│  │  3. Tokenize input (15,000 words → ~20,000 tokens)          │      │
│  │  4. Run inference (70B model)                                │      │
│  │     - Batch size: 1                                          │      │
│  │     - Context: 20,000 in + 2,048 out                        │      │
│  │     - Speed: ~15 tokens/sec                                  │      │
│  │     - Time: ~5000ms                                          │      │
│  │  5. Generate summary (2,048 tokens)                          │      │
│  │  6. Return result                                            │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                         │
│  GPU Utilization: 40% → 95% (during inference)                         │
│  VRAM: 40GB (70B Q4 quantization)                                      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            │  ~5000ms inference
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=5070ms: Result Returns to Node A                                     │
│                                                                         │
│  Node B ─────────────────────────────────► Node A                      │
│                                                                         │
│  Response:                                                              │
│  {                                                                      │
│    "choices": [{                                                        │
│      "message": {                                                       │
│        "role": "assistant",                                             │
│        "content": "This contract is a software licensing agreement..."  │
│      }                                                                  │
│    }],                                                                  │
│    "usage": {                                                           │
│      "prompt_tokens": 20000,                                           │
│      "completion_tokens": 2048,                                         │
│      "total_tokens": 22048                                             │
│    }                                                                    │
│  }                                                                      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=5100ms: Result Delivered to User                                     │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  Summary (2,048 tokens):                                     │      │
│  │                                                               │      │
│  │  This contract is a software licensing agreement between     │      │
│  │  [Party A] and [Party B]. Key terms include:                │      │
│  │                                                               │      │
│  │  1. License Grant: Non-exclusive, worldwide...              │      │
│  │  2. Payment Terms: $X upon signing, $Y annually...          │      │
│  │  3. Termination Clause: Either party may...                 │      │
│  │  ...                                                          │      │
│  │                                                               │      │
│  │  Notable considerations:                                      │      │
│  │  - Indemnification is limited to...                          │      │
│  │  - Liability cap of...                                        │      │
│  │  - Intellectual property rights remain with...              │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                         │
│  Total Time: 5.1 seconds                                                │
│  Cost: $0 (local execution)                                             │
│  Quality: High (70B model)                                              │
└────────────────────────────────────────────────────────────────────────┘

Performance Breakdown:
- Intent embedding: 10ms
- Semantic matching: 2ms
- Routing decision: 3ms
- Request forwarding: 5ms (network)
- Model inference: 5000ms (70B generation)
- Response return: 30ms (network)
- Total: 5050ms (~5 seconds)

Compare to alternatives:
- Local 7B model: 1s (fast but lower quality summary)
- Cloud API (GPT-4): 2s (fast but costs ~$0.50 for 22k tokens)
- No mesh (manual): User has to know where 70B is running

Mesh advantage: Best quality + Zero cost + Automatic routing
```

---

## 5. Multi-Node Work Distribution

```
Task: "Analyze these 10 documents and create a comparison report"

┌────────────────────────────────────────────────────────────────────────┐
│ T=0ms: Intent Decomposition                                            │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  Planner (LLM meta-step):                                    │      │
│  │                                                               │      │
│  │  Plan:                                                        │      │
│  │  1. Embed all 10 documents (parallel)                        │      │
│  │  2. Summarize each document (parallel)                       │      │
│  │  3. Extract key points (parallel)                            │      │
│  │  4. Compare summaries (sequential)                           │      │
│  │  5. Generate report (sequential)                             │      │
│  │                                                               │      │
│  │  Work units: 30 total (10 embed + 10 summarize + 10 extract │      │
│  │                         + 1 compare + 1 report)              │      │
│  └──────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=1ms: Parallel Group 1 - Embeddings (10 tasks)                        │
│                                                                         │
│  Route each embed task to best node:                                   │
│                                                                         │
│  embed-0 → Node A (local, idle)                                        │
│  embed-1 → Node B (1 hop, idle)                                        │
│  embed-2 → Node C (2 hops, idle)                                       │
│  embed-3 → Node A (still has capacity)                                 │
│  embed-4 → Node B (still has capacity)                                 │
│  embed-5 → Node D (just discovered, 3 hops, idle)                      │
│  embed-6 → Node A                                                      │
│  embed-7 → Node B                                                      │
│  embed-8 → Node C                                                      │
│  embed-9 → Node A                                                      │
│                                                                         │
│  Dispatch all in parallel (asyncio.gather):                            │
│                                                                         │
│  Node A: [embed-0, embed-3, embed-6, embed-9]  (4 tasks)              │
│  Node B: [embed-1, embed-4, embed-7]           (3 tasks)              │
│  Node C: [embed-2, embed-8]                    (2 tasks)              │
│  Node D: [embed-5]                             (1 task)               │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=150ms: All Embeddings Complete                                       │
│                                                                         │
│  Results:                                                               │
│  embed-0 → [0.12, -0.34, ...]  ✓ (Node A, 80ms)                       │
│  embed-1 → [0.56, 0.78, ...]   ✓ (Node B, 100ms)                      │
│  embed-2 → [-0.23, 0.45, ...]  ✓ (Node C, 120ms)                      │
│  embed-3 → [0.67, -0.12, ...]  ✓ (Node A, 85ms)                       │
│  embed-4 → [0.34, 0.56, ...]   ✓ (Node B, 110ms)                      │
│  embed-5 → [0.89, -0.67, ...]  ✓ (Node D, 150ms)  ← slowest           │
│  embed-6 → [0.23, 0.12, ...]   ✓ (Node A, 90ms)                       │
│  embed-7 → [-0.45, 0.78, ...]  ✓ (Node B, 115ms)                      │
│  embed-8 → [0.12, -0.56, ...]  ✓ (Node C, 130ms)                      │
│  embed-9 → [0.78, 0.34, ...]   ✓ (Node A, 95ms)                       │
│                                                                         │
│  Bottleneck: Node D (3 hops, slower network)                           │
│  Speedup: 150ms vs 10*50ms = 500ms sequential → 3.3x faster            │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=151ms: Parallel Group 2 - Summarization (10 tasks)                   │
│                                                                         │
│  Route to nodes with LLM capability:                                   │
│                                                                         │
│  summarize-0 → Node B (70B model, light load)                          │
│  summarize-1 → Node B                                                  │
│  summarize-2 → Node A (7B model, local)                                │
│  summarize-3 → Node B                                                  │
│  summarize-4 → Node C (32B model)                                      │
│  summarize-5 → Node B                                                  │
│  summarize-6 → Node A                                                  │
│  summarize-7 → Node C                                                  │
│  summarize-8 → Node A                                                  │
│  summarize-9 → Node B                                                  │
│                                                                         │
│  Node A (7B):  3 tasks → ~1.5s each                                    │
│  Node B (70B): 5 tasks → ~3s each                                      │
│  Node C (32B): 2 tasks → ~2s each                                      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=4000ms: Summarization Complete                                       │
│                                                                         │
│  Node B finished all 5 summaries: ~3.5s (batched for efficiency)       │
│  Node A finished all 3 summaries: ~1.8s                                │
│  Node C finished all 2 summaries: ~2.2s                                │
│                                                                         │
│  Bottleneck: Node B (70B slower but higher quality)                    │
│  Speedup: 4s vs 10*3s = 30s sequential → 7.5x faster                   │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=4001ms: Parallel Group 3 - Key Point Extraction (10 tasks)           │
│                                                                         │
│  Similar distribution, ~2s total                                        │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=6000ms: Sequential - Comparison                                      │
│                                                                         │
│  Single task (requires all previous results):                          │
│  compare → Node B (70B, good at reasoning)                             │
│                                                                         │
│  Input: All 10 summaries + key points                                  │
│  Prompt: "Compare these summaries and identify patterns..."            │
│  Time: ~3s                                                              │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=9000ms: Sequential - Report Generation                               │
│                                                                         │
│  report → Node B (70B)                                                 │
│                                                                         │
│  Input: Comparison results                                             │
│  Prompt: "Generate executive summary report..."                        │
│  Time: ~2s                                                              │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=11000ms: Complete!                                                    │
│                                                                         │
│  Total time: 11 seconds                                                 │
│  Sequential would be: ~40 seconds                                       │
│  Speedup: 3.6x                                                          │
│                                                                         │
│  Work distribution:                                                     │
│  - Node A: 7 tasks (3 summarize, 4 embed, etc.)                        │
│  - Node B: 13 tasks (5 summarize, 3 embed, compare, report)            │
│  - Node C: 4 tasks                                                      │
│  - Node D: 1 task                                                       │
│                                                                         │
│  Cost: $0 (all local)                                                   │
│  Quality: High (70B for critical steps)                                │
└────────────────────────────────────────────────────────────────────────┘

Key Benefits:
1. Automatic parallelization (no manual coordination)
2. Load-aware distribution (busy nodes get fewer tasks)
3. Capability-aware routing (70B for reasoning, 7B for simple tasks)
4. Resilient (if Node C fails, tasks automatically reroute)
5. Cost-effective (all local, no cloud costs)
```

---

## 6. Model Migration Flow

```
Scenario: Private medical records on Node A, but 70B model is on Node B

┌────────────────────────────────────────────────────────────────────────┐
│ User on Node A: "Analyze these patient records" (HIPAA-sensitive)      │
│                                                                         │
│  Constraint: data_must_stay_local = True                               │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=0ms: Routing Decision                                                │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  Best capability: llamafarm:llm:llama3.2-70b                 │      │
│  │  Location: Node B                                             │      │
│  │  Constraint violation: Data can't leave Node A!              │      │
│  │                                                               │      │
│  │  Options:                                                     │      │
│  │  1. Use local 7B (lower quality)                            │      │
│  │  2. Migrate 70B to Node A ✓ CHOSEN                          │      │
│  │  3. Fail request (unacceptable)                              │      │
│  └──────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=1ms: Resource Check on Node A                                        │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  Model requirements (70B Q4):                                │      │
│  │    - VRAM: 40GB                                              │      │
│  │    - RAM: 60GB                                               │      │
│  │    - Disk: 80GB                                              │      │
│  │                                                               │      │
│  │  Node A resources:                                            │      │
│  │    - VRAM: 32GB ✗ INSUFFICIENT                               │      │
│  │    - RAM: 128GB ✓ OK                                         │      │
│  │    - Disk: 500GB ✓ OK                                        │      │
│  │                                                               │      │
│  │  Fallback plan: CPU inference (slow but acceptable)         │      │
│  │  Estimated time: 10x slower (30s instead of 3s)             │      │
│  │  User accepts: Privacy > Speed                               │      │
│  └──────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=2ms: Initiate Model Migration                                        │
│                                                                         │
│  Node A ─────RPC: get_model_metadata────► Node B                       │
│                                           │                             │
│                                           ▼                             │
│                                    ┌────────────────┐                   │
│                                    │ Model: 70B Q4  │                   │
│                                    │ Size: 80GB     │                   │
│                                    │ Chunks: 1,250  │                   │
│                                    │ (64MB each)    │                   │
│                                    └────────────────┘                   │
│                                           │                             │
│  Node A ◄────metadata────────────────────┘                             │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=10ms: Stream Model Chunks                                            │
│                                                                         │
│  Node A ◄═══════════════════════════════► Node B                       │
│                                                                         │
│  Streaming 1,250 chunks in parallel (BitTorrent-style):                │
│                                                                         │
│  Chunk 0000 (64MB) ████████████████████ 100% (Node B → Node A)         │
│  Chunk 0001 (64MB) ████████████████████ 100%                           │
│  Chunk 0002 (64MB) ████████████████████ 100%                           │
│  ...                                                                    │
│  Chunk 1249 (32MB) ████████████████████ 100%                           │
│                                                                         │
│  Progress:                                                              │
│  T=10ms:    0.1% (100MB / 80GB)                                        │
│  T=5000ms:  20% (16GB / 80GB)                                          │
│  T=15000ms: 60% (48GB / 80GB)                                          │
│  T=25000ms: 100% ✓ Complete                                            │
│                                                                         │
│  Transfer rate: ~3.2GB/s (10GbE network)                               │
│  Total time: 25 seconds                                                 │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=25000ms: Load Model on Node A                                        │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  LlamaFarm (Node A):                                         │      │
│  │  llamafarm load llama3.2-70b --device cpu                    │      │
│  │                                                               │      │
│  │  Loading into RAM (no VRAM):                                 │      │
│  │  [████████████████████████████████] 100%                     │      │
│  │                                                               │      │
│  │  Time: 5s                                                     │      │
│  │  Memory: 60GB RAM used                                        │      │
│  └──────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=30000ms: Execute Locally on Node A                                   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │  Prompt: "Analyze these patient records..."                  │      │
│  │  Medical data: [10MB sensitive records]                      │      │
│  │                                                               │      │
│  │  Processing:                                                  │      │
│  │  - Device: CPU (48 cores)                                    │      │
│  │  - Speed: ~2 tokens/sec (slow but acceptable)               │      │
│  │  - Time: ~30s for 60 token response                          │      │
│  │  - Privacy: ✓ Data never left Node A                        │      │
│  └──────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ T=60000ms: Complete                                                     │
│                                                                         │
│  Result delivered to user                                               │
│                                                                         │
│  Total time: 60 seconds                                                 │
│  Breakdown:                                                             │
│    - Migration: 25s (one-time)                                          │
│    - Loading: 5s                                                        │
│    - Inference: 30s (CPU)                                               │
│                                                                         │
│  Future requests: No migration needed (model cached on Node A)          │
│  Next request time: 30s (just inference)                                │
│                                                                         │
│  Privacy maintained: ✓✓✓ (HIPAA compliant)                             │
│  Data never left Node A                                                 │
│  Model came to the data, not vice versa                                │
└────────────────────────────────────────────────────────────────────────┘

Alternative scenario (if Node A had VRAM):
- Migration: 25s
- Loading: 5s (to GPU)
- Inference: 3s (GPU)
- Total: 33s (first time), 3s (subsequent)

Key insight: Temporary performance hit for permanent privacy guarantee
```

---

These diagrams illustrate the revolutionary architecture where **Atmosphere orchestrates** and **LlamaFarm executes**, creating a distributed AI mesh that's privacy-preserving, cost-optimized, and automatically scalable.
