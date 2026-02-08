# Atmosphere Reset Plan - FINAL

## The Vision

> **The Internet of Intent — Route Intelligence, Not Packets**
>
> Edge devices don't just REQUEST intelligence — they ORCHESTRATE it.
> A Raspberry Pi can route a complex task across a mesh of GPUs, phones, and cloud APIs.

---

## Core Principle: Edge as Orchestrator

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ANY EDGE DEVICE (Phone, Pi, Watch, Laptop)                             │
│                                                                          │
│  Can:                                                                    │
│  ├─ Receive requests (from local apps, SDK, triggers)                   │
│  ├─ Classify intent (complexity, type, requirements)                    │
│  ├─ Decompose into capability chain                                     │
│  ├─ Route each step to best capability in mesh                          │
│  ├─ Chain results (output → next input)                                 │
│  ├─ Execute local capabilities (camera, sensors, tiny models)           │
│  └─ All with HASH-BASED routing (no embeddings required!)               │
│                                                                          │
│  Doesn't need:                                                           │
│  ├─ Powerful CPU (routing is O(1) hash lookup)                          │
│  ├─ Embeddings model (hash + keywords work everywhere)                  │
│  └─ Central server (gossip gives full mesh visibility)                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Capability Announcement Schema

What every node gossips to the mesh:

```python
@dataclass
class CapabilityAnnouncement:
    """Complete capability description for mesh routing."""
    
    # === IDENTITY ===
    node_id: str                    # "abc123" (Ed25519 public key hash)
    node_name: str                  # "rob-macbook"
    capability_id: str              # Unique: "{node_id}:{project_path}:{model_alias}"
    
    # === PROJECT ROUTING ===
    project_path: str               # "llamafarm/discoverable/llama-expert-14"
    model_alias: str                # "default" - what API calls use
    
    # === MODEL METADATA ===
    model_actual: str               # "unsloth/Qwen3-1.7B-GGUF:Q4_K_M"
    model_family: str               # "qwen3", "llama3", "mistral", "whisper"
    model_params_b: float           # 1.7, 7.0, 70.0 (billions)
    model_quantization: str         # "Q4_K_M", "fp16", "int8"
    model_tier: str                 # "tiny|small|medium|large|xl"
    
    # === CAPABILITY TYPE ===
    capability_type: str            # "llm/chat", "audio/transcribe", "sensor/camera"
    triggers: List[str]             # ["motion_detected", "transcription_complete"]
    tools: List[str]                # ["chat", "get_frame", "transcribe"]
    
    # === SEMANTIC MATCHING (3-tier cascade) ===
    label: str                      # "Llama & Alpaca Expert"
    description: str                # "Expert on llamas, alpacas..."
    embedding: Optional[List[float]] # 384-dim (optional, for capable devices)
    embedding_hash: int             # 64-bit SimHash (works everywhere)
    keywords: List[str]             # ["llama", "alpaca", "camelid"]
    
    # === INTELLIGENCE PROFILE ===
    good_for: List[str]             # ["simple_qa", "classification", "extraction"]
    not_good_for: List[str]         # ["complex_reasoning", "multi_step_agents"]
    has_rag: bool                   # Retrieval-augmented generation
    has_vision: bool                # Can process images
    has_tools: bool                 # Function/tool calling
    has_streaming: bool             # Streaming responses
    context_length: int             # 4096, 32768, 128000
    specializations: List[str]      # ["camelid-care", "code", "medical"]
    
    # === COST FACTORS ===
    cost_factors: NodeCostFactors   # Battery, CPU, GPU, memory
    estimated_latency_ms: float     # Typical response time
    tokens_per_second: float        # Inference speed
    api_cost_per_1k_tokens: float   # $ (0 for local)
    
    # === ROUTING METADATA ===
    hops: int                       # 0 = local, 1+ = forwarded
    via_node: Optional[str]         # Who forwarded this
    ttl: int                        # Time to live
    timestamp: float                # Unix timestamp
    expires_at: float               # When this expires (timestamp + 300s)
    
    # === SECURITY ===
    signature: str                  # Ed25519 signature of announcement
```

---

## Model Tier System

```
┌──────────┬───────────┬─────────────────────────────────────────────────┐
│ Tier     │ Params    │ Best For                                        │
├──────────┼───────────┼─────────────────────────────────────────────────┤
│ tiny     │ < 2B      │ Classification, extraction, simple QA           │
│          │           │ Embeddings, fast inference, edge devices        │
├──────────┼───────────┼─────────────────────────────────────────────────┤
│ small    │ 2-4B      │ Basic chat, summarization (short)               │
│          │           │ Single-step tasks, phone inference              │
├──────────┼───────────┼─────────────────────────────────────────────────┤
│ medium   │ 7-14B     │ General chat, summarization, simple agents      │
│          │           │ RAG, code assistance, reliable tool use         │
├──────────┼───────────┼─────────────────────────────────────────────────┤
│ large    │ 30-34B    │ Complex reasoning, multi-step agents            │
│          │           │ Long documents, nuanced tasks                   │
├──────────┼───────────┼─────────────────────────────────────────────────┤
│ xl       │ 70B+      │ Best quality, complex analysis                  │
│          │           │ When accuracy > speed/cost                      │
└──────────┴───────────┴─────────────────────────────────────────────────┘
```

---

## Intent → Capability Chain Decomposition

```python
def decompose_intent(intent: str) -> List[CapabilityStep]:
    """
    Break complex intent into executable capability chain.
    
    Example: "Summarize this meeting and notify the team"
    
    Returns:
    [
        CapabilityStep(
            type="audio/transcribe",
            min_tier="tiny",
            input_from="user",
            output_key="transcript"
        ),
        CapabilityStep(
            type="llm/summarize",
            min_tier="medium",  # Summarization needs comprehension
            input_from="transcript",
            output_key="summary"
        ),
        CapabilityStep(
            type="action/notify",
            min_tier=None,  # Not inference
            input_from="summary",
            output_key="result"
        )
    ]
    """
```

---

## Composite Routing Score

```python
def compute_route_score(
    capability: CapabilityAnnouncement,
    intent: IntentClassification,
    step: CapabilityStep,
) -> float:
    """
    Score a capability for routing. Higher = better.
    
    All factors normalized to 0-1.
    """
    
    # === SEMANTIC MATCH (30%) ===
    # How well does capability match what we need?
    semantic = compute_semantic_match(intent, capability)  # 3-tier cascade
    
    # === MODEL TIER FIT (25%) ===
    # Is the model appropriately sized for the task?
    tier_fit = compute_tier_fit(
        required_tier=step.min_tier,
        actual_tier=capability.model_tier,
        intent_complexity=intent.complexity
    )
    # Over-powered: 0.7 (wasteful but works)
    # Under-powered: 0.2-0.5 (risky)
    # Right-sized: 1.0
    
    # === LATENCY (15%) ===
    latency = 1 - min(capability.estimated_latency_ms / 2000, 1)
    
    # === COST (15%) ===
    if capability.api_cost_per_1k_tokens > 0:
        cost = 1 - min(capability.api_cost_per_1k_tokens / 0.01, 1)
    else:
        cost = 1.0  # Local = free = best
    
    # === AVAILABILITY (10%) ===
    avail = compute_availability(capability.cost_factors)
    # Low battery, high CPU load, metered network → lower score
    
    # === LOCALITY (5%) ===
    locality = 0.95 ** capability.hops
    
    # === WEIGHTED SUM ===
    score = (
        0.30 * semantic +
        0.25 * tier_fit +
        0.15 * latency +
        0.15 * cost +
        0.10 * avail +
        0.05 * locality
    )
    
    # === BONUSES ===
    if capability.has_rag and intent.requires_knowledge:
        score += 0.05
    if any(s in intent.domain_hints for s in capability.specializations):
        score += 0.05
        
    return min(score, 1.0)
```

---

## Blast Radius Consensus

When 30+ nodes are gossiping capabilities:

```
RULE 1: Owner Authority
├─ Only owner node can CREATE/UPDATE its capabilities
├─ Other nodes can only FORWARD
└─ Signature verification prevents spoofing

RULE 2: Timestamp Ordering
├─ Newer timestamp always wins
├─ Clock skew tolerance: 5 seconds
└─ Future timestamps > 5s ahead are rejected

RULE 3: TTL Decay
├─ Each forward decrements TTL
├─ TTL=0 → stop forwarding
└─ Prevents infinite propagation

RULE 4: Automatic Expiry
├─ Capabilities expire after 5 minutes
├─ Nodes must re-announce to stay visible
└─ Dead nodes disappear gracefully

RULE 5: Conflict Resolution
├─ Same capability_id, different timestamps → newer wins
├─ Same timestamp (within 1s) → higher node_id wins (deterministic)
└─ Log all conflicts for debugging
```

---

## Security Model

```
IDENTITY:
├─ Each node has Ed25519 keypair
├─ node_id = hash(public_key)
├─ Hardware fingerprint binding (optional)
└─ Mesh uses Shamir secret sharing for shared key

CAPABILITY CLAIMS:
├─ Every CapabilityAnnouncement is signed
├─ signature = sign(serialize(announcement), private_key)
├─ Receivers verify before accepting
└─ Invalid signatures are dropped + logged

MESH MEMBERSHIP:
├─ Join requires token from existing member
├─ Token includes mesh_id, inviter signature
├─ Revocation via gossip (signed revocation message)
└─ Offline verification (no central auth server)
```

---

## Platform SDK

Mac App and Mobile App expose APIs to OTHER apps:

```
┌─────────────────────────────────────────────────────────────────┐
│  EXTERNAL APP (Notes, Mail, Custom App)                         │
│       ↓                                                          │
│  Atmosphere SDK (local socket/HTTP)                              │
│       ↓                                                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  ATMOSPHERE PLATFORM                                         │ │
│  │                                                               │ │
│  │  1. Receive request                                          │ │
│  │  2. Classify intent                                          │ │
│  │  3. Check local capabilities                                 │ │
│  │  4. Check mesh capabilities (gradient table)                 │ │
│  │  5. Route to best option:                                    │ │
│  │     ├─ Local model (fastest, free)                           │ │
│  │     ├─ Nearby device (low latency)                           │ │
│  │     ├─ Remote device (GPU server)                            │ │
│  │     └─ Cloud API (expensive, capable)                        │ │
│  │  6. Return result to app                                     │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## What We DELETE

### Mac (Python)
```
❌ atmosphere/network/resilient_transport.py
❌ atmosphere/network/mesh_connection.py
❌ atmosphere/network/transports/relay.py
❌ atmosphere/network/transports/lan.py
❌ atmosphere/network/transports/ble.py
❌ atmosphere/network/transports/__init__.py
❌ Per-peer transport complexity
```

### Android (Kotlin)
```
❌ network/MeshConnection.kt (complex WebSocket mess)
❌ network/ConnectionTrain.kt (transport cycling)
❌ network/ResilientTransportManager.kt
❌ network/TransportManager.kt
❌ network/WebSocketTransport.kt
❌ network/BleTransport.kt (keep for later, but not now)
❌ data/SavedMesh.kt endpoint complexity
```

---

## What We KEEP

### Mac
```
✅ atmosphere/cost/ (cost model - excellent)
✅ atmosphere/auth/ (Ed25519 identity)
✅ atmosphere/mesh/node.py (identity)
✅ atmosphere/router/intent_classifier.py
✅ atmosphere/router/semantic.py (refactor to use gradient table)
✅ atmosphere/router/gradient.py (expand for full capability)
✅ atmosphere/mesh/gossip.py (update schema)
✅ atmosphere/api/server.py (update routes)
```

### Android
```
✅ viewmodel/AtmosphereViewModel.kt (refactor)
✅ service/AtmosphereService.kt (simplify)
✅ ui/ (all screens)
✅ data/SavedMesh.kt (simplify - just mesh identity)
```

---

## Implementation Phases

### Phase 1: Capability Schema (Day 1)
**Mac:**
- [ ] Create `atmosphere/core/capability.py` with full schema
- [ ] Include model tier, good_for, not_good_for
- [ ] Add signature generation/verification
- [ ] Unit tests for serialization

**Android:**
- [ ] Create `core/Capability.kt` matching schema
- [ ] Add JSON serialization
- [ ] Unit tests

### Phase 2: Simple Transport (Day 2)
**Mac:**
- [ ] Create `atmosphere/transport/relay.py` - ONE file, simple WS
- [ ] Connect, send JSON, receive JSON, that's it
- [ ] No per-peer management
- [ ] Delete old network/ folder

**Android:**
- [ ] Create `transport/RelayConnection.kt` - simple WS
- [ ] Delete network/ folder entirely
- [ ] Test: Connect to relay, send/receive

### Phase 3: Gossip Protocol (Day 3)
**Mac:**
- [ ] Update gossip to use new CapabilityAnnouncement
- [ ] Implement broadcast on connect + periodic
- [ ] Implement receive + gradient table update
- [ ] TTL, timestamp, expiry logic

**Android:**
- [ ] Port gossip protocol
- [ ] Receive capabilities into local table
- [ ] Broadcast local capabilities

### Phase 4: Gradient Table (Day 4)
**Mac:**
- [ ] Refactor gradient table for full capability
- [ ] Index by: capability_id, embedding_hash, keywords, type
- [ ] Fast lookup for all 3 cascade tiers
- [ ] Include model_alias in route results

**Android:**
- [ ] Port gradient table
- [ ] Hash-based lookup (no embeddings)
- [ ] Keyword fallback

### Phase 5: Semantic Router (Day 5)
**Mac:**
- [ ] Implement 3-tier cascade
- [ ] Implement composite scoring with all factors
- [ ] Add model tier fit scoring
- [ ] Intent decomposition (capability chaining)
- [ ] Detailed routing log

**Android:**
- [ ] Port 2-tier cascade (hash + keyword, no embeddings)
- [ ] Composite scoring
- [ ] Basic intent classification

### Phase 6: Integration (Day 6)
**Mac:**
- [ ] Wire to LlamaFarm project discovery
- [ ] Auto-register with full model metadata
- [ ] API endpoints for routing
- [ ] WebSocket for capability updates

**Android:**
- [ ] Wire to local model (if any)
- [ ] Route requests through mesh
- [ ] UI: Show mesh capabilities
- [ ] UI: Test routing

### Phase 7: Testing & Polish (Day 7)
- [ ] Phone → Mac routing works
- [ ] Mac → Phone routing works
- [ ] Capability chaining works
- [ ] Cost factors influence routing
- [ ] Model tier influences routing
- [ ] Logging shows WHY routes were chosen

---

## Success Metrics

1. **Phone routes "summarize this" to Mac's 7B model** (not tiny model)
2. **Simple QA routes to tiny model** (not wasting 70B)
3. **Every route decision is logged with scores**
4. **New node's capabilities visible in <5 seconds**
5. **Works with no central server**
6. **Edge device can orchestrate multi-step tasks**

---

## File Structure (New)

### Mac
```
atmosphere/
├── core/
│   ├── capability.py      # CapabilityAnnouncement schema
│   ├── intent.py          # IntentClassification
│   └── chain.py           # Capability chaining/decomposition
├── router/
│   ├── semantic.py        # 3-tier cascade + composite scoring
│   ├── gradient.py        # Gradient table (routing table)
│   └── scorer.py          # Score computation
├── mesh/
│   ├── gossip.py          # Gossip protocol
│   ├── node.py            # Node identity
│   └── consensus.py       # Conflict resolution
├── transport/
│   └── relay.py           # Simple relay client (ONE FILE)
├── cost/
│   ├── model.py           # Cost computation
│   └── collector.py       # System metrics
└── api/
    └── server.py          # FastAPI
```

### Android
```
com.llamafarm.atmosphere/
├── core/
│   ├── Capability.kt      # Schema
│   ├── Intent.kt          # Classification
│   └── Chain.kt           # Decomposition
├── router/
│   ├── SemanticRouter.kt  # 2-tier cascade
│   ├── GradientTable.kt   # Routing table
│   └── Scorer.kt          # Scoring
├── mesh/
│   ├── Gossip.kt          # Protocol
│   └── Node.kt            # Identity
├── transport/
│   └── RelayConnection.kt # Simple WS
└── service/
    └── AtmosphereService.kt
```

---

*START EXECUTION: Phase 1*
