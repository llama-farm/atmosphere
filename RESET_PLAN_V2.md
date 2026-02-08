# Atmosphere Reset Plan v2

## The Vision (From README - DO NOT LOSE THIS)

> **The Internet of Intent — Route Intelligence, Not Packets**
> 
> Traditional networks route packets to addresses.  
> Atmosphere routes **work** to **capability**.

A request comes in → mesh instantly knows:
1. **What** (intent classification)
2. **Which device** (gradient table lookup)
3. **Which project** on that device
4. **Which MODEL** (not just project - the actual model like `unsloth/Qwen3-1.7B`)
5. **At what cost** (battery, CPU, latency, $$)
6. **With what capability type** (llm, vision, agent, sensor, etc.)

---

## Critical Aspects We MUST Preserve

### 1. Bidirectional Capabilities (Triggers + Tools)
```
Every capability is BOTH:
- TRIGGER (push): "motion detected", "transcription complete"
- TOOL (pull): get_frame(), chat(), transcribe()

Example: Camera
├─ TRIGGERS: motion, person, package, vehicle
└─ TOOLS: get_frame(), get_clip(), get_history()
```

### 2. Capability Types (Expandable)
```
| Category       | Type              | Examples                    |
|----------------|-------------------|-----------------------------|
| Vision         | sensor/camera     | motion, get_frame           |
| Voice          | audio/generate    | speak, list_voices          |
| Transcription  | audio/transcribe  | transcribe, keyword trigger |
| Image Gen      | vision/generate   | generate, edit              |
| LLM            | llm/chat          | chat, complete, embed       |
| IoT            | iot/*             | get_value, set_value        |
| Agent          | agent/*           | invoke, task_complete       |
```

### 3. Cost Model (Already Built - USE IT)
```python
NodeCostFactors:
  - on_battery: bool
  - battery_percent: float
  - plugged_in: bool
  - cpu_load: float (0-1+)
  - gpu_load: float (0-100%)
  - memory_percent: float
  - memory_available_gb: float
  - bandwidth_mbps: float
  - is_metered: bool
  - latency_ms: float
  - api_model: str (for cloud API cost lookup)

API Costs (per 1M tokens):
  - gpt-4o: $2.50 / $10.00
  - claude-3-5-sonnet: $3.00 / $15.00
  - gemini-1.5-flash: $0.075 / $0.30
  - local models: $0.00
```

### 4. Security (Ed25519 + Shamir)
```
- Each node has Ed25519 keypair
- Hardware fingerprint binding
- Mesh uses Shamir secret sharing for mesh key
- Offline token verification
- Capability claims signed by owner
```

### 5. Platform SDK (Apps Connect to Us)
```
Mac App / Mobile App are PLATFORMS:
┌─────────────────────────────────────────┐
│  External App (e.g., Notes app)         │
│     ↓                                   │
│  "Summarize this document"              │
│     ↓                                   │
│  Atmosphere SDK / Local API             │
│     ↓                                   │
│  Mesh Router decides:                   │
│  ├─ Local model? (fast, free)           │
│  ├─ Remote device? (GPU server)         │
│  └─ Cloud API? (expensive, capable)     │
└─────────────────────────────────────────┘
```

---

## The Capability Table (THE CORE)

This is what gets gossiped. Every node broadcasts this periodically.

```python
@dataclass
class CapabilityAnnouncement:
    """What a node can do - gossiped to mesh."""
    
    # Identity
    node_id: str                    # "abc123..."
    node_name: str                  # "rob-macbook"
    
    # Capability Identity
    capability_id: str              # "llamafarm/discoverable/llama-expert-14"
    capability_type: str            # "llm/chat", "sensor/camera", "agent/security"
    
    # Semantic Matching (3-tier cascade)
    label: str                      # "Llama & Alpaca Expert"
    description: str                # "Expert on llamas, alpacas, camelid care..."
    embedding: List[float]          # 384-dim vector (optional, for capable devices)
    embedding_hash: str             # 32-bit SimHash (works everywhere)
    keywords: List[str]             # ["llama", "alpaca", "camelid", "fiber"]
    
    # THE MODEL (critical!)
    model_name: str                 # "unsloth/Qwen3-1.7B-GGUF:Q4_K_M"
    model_size: str                 # "tiny", "small", "medium", "large"
    context_length: int             # 4096, 8192, 32768
    
    # Capabilities
    has_rag: bool                   # Uses retrieval-augmented generation
    has_vision: bool                # Can process images
    has_tools: bool                 # Function calling support
    specializations: List[str]      # ["animal-care", "breeding", "fiber-arts"]
    
    # Triggers (push) & Tools (pull)
    triggers: List[str]             # Events this can emit
    tools: List[str]                # Functions this can be called with
    
    # Cost Factors
    cost_factors: NodeCostFactors   # Battery, CPU, GPU, etc.
    estimated_latency_ms: float     # How long requests take
    api_cost_per_1k: float          # $ cost (0 for local)
    
    # Routing
    hops: int                       # 0 = local, 1+ = via other nodes
    via_node: Optional[str]         # If hops > 0, who forwarded this
    ttl: int                        # Time to live for gossip
    
    # Security
    signature: str                  # Ed25519 signature of this announcement
    timestamp: float                # When announced
```

---

## Blast Radius Consensus (30+ Things on Mesh)

When many nodes are adding/editing capabilities:

### Rule 1: Owner Authority
- Only the **owner node** can update its own capabilities
- Signature verification prevents spoofing
- Other nodes can only forward, not modify

### Rule 2: Timestamp Wins
- Newer announcements override older ones
- Clock skew tolerance: 5 seconds
- Nodes reject future timestamps > 5s ahead

### Rule 3: TTL Decay
- Each hop decrements TTL
- TTL=0 → don't forward
- Prevents infinite propagation

### Rule 4: Conflict Resolution
```
If two announcements for same capability_id:
1. Higher timestamp wins
2. If timestamps equal (within 1s): higher node_id wins (deterministic)
3. Log conflict for debugging
```

### Rule 5: Capability Expiry
- Capabilities expire after 5 minutes without refresh
- Node must re-announce to stay in mesh
- Graceful degradation when nodes disappear

---

## Cascading Semantic Router

### The 3-Tier Cascade (Works on ANY Device)

```
INPUT: "How do I shear my alpaca?"

TIER 1: Embedding Match (if device has embeddings)
├─ Compute intent embedding
├─ Dot product with all capability embeddings
├─ Score > 0.65? → Use this match
└─ Best match: llama-expert (0.87)

TIER 2: Hash Match (fast, works everywhere)
├─ Compute SimHash of intent
├─ XOR distance to capability hashes
├─ Score > 0.40? → Use this match
└─ Works on Raspberry Pi, phones, etc.

TIER 3: Keyword Match (always works)
├─ Extract keywords: ["shear", "alpaca"]
├─ Jaccard similarity with capability keywords
├─ Score > 0.30? → Use this match
└─ Zero dependencies, always available
```

### Composite Scoring

```python
def compute_composite_score(match: CapabilityMatch) -> float:
    """
    Combine all factors into final routing score.
    """
    weights = {
        'semantic': 0.35,      # How well intent matches capability
        'latency': 0.20,       # Lower latency = better
        'cost': 0.15,          # Lower cost = better
        'capability': 0.15,    # RAG, specialization bonuses
        'availability': 0.10,  # Is node available/healthy?
        'hops': 0.05,          # Prefer direct routes
    }
    
    # Semantic score (from cascade)
    semantic = match.semantic_score  # 0-1
    
    # Latency score (inverse normalized)
    latency = 1 - min(match.latency_ms / 2000, 1)  # 2s = worst
    
    # Cost score
    if match.api_cost_per_1k > 0:
        cost = 1 - min(match.api_cost_per_1k / 0.01, 1)  # $0.01/1k = worst
    else:
        cost = 1.0  # Local = best
    
    # Capability score
    capability = 0.5
    if match.has_rag and intent.requires_knowledge:
        capability += 0.2
    if any(s in intent.domain for s in match.specializations):
        capability += 0.2
    if match.model_size >= intent.min_model_size:
        capability += 0.1
    
    # Availability (from cost factors)
    availability = 1.0
    if match.cost_factors.on_battery and match.cost_factors.battery_percent < 20:
        availability *= 0.5  # Deprioritize dying battery
    if match.cost_factors.cpu_load > 0.9:
        availability *= 0.7  # Deprioritize overloaded
    
    # Hops penalty
    hops = 0.95 ** match.hops
    
    # Weighted sum
    score = (
        weights['semantic'] * semantic +
        weights['latency'] * latency +
        weights['cost'] * cost +
        weights['capability'] * capability +
        weights['availability'] * availability +
        weights['hops'] * hops
    )
    
    return score
```

### Routing Decision Log (Debuggable!)

```
🎯 ROUTE: "How do I shear my alpaca?"
├─ Intent: QA, domain=animals, complexity=SIMPLE
├─ Candidates:
│   ├─ llama-expert@mac (score=0.92)
│   │   ├─ semantic: 0.87 (embedding match)
│   │   ├─ latency: 50ms → 0.97
│   │   ├─ cost: local → 1.00
│   │   ├─ capability: has_rag, specialization=camelid → 0.90
│   │   ├─ availability: battery=80%, cpu=10% → 1.00
│   │   └─ hops: 0 → 1.00
│   └─ gpt-4o@cloud (score=0.71)
│       ├─ semantic: 0.95 (better match)
│       ├─ latency: 800ms → 0.60
│       ├─ cost: $0.01/1k → 0.00
│       └─ ...
└─ Selected: llama-expert@mac
    Model: unsloth/Qwen3-1.7B-GGUF:Q4_K_M
    Reason: Best composite score (local, fast, specialized)
```

---

## What We Delete

```
❌ atmosphere/network/resilient_transport.py (complex, fragile)
❌ atmosphere/network/mesh_connection.py (per-peer nonsense)
❌ atmosphere/network/transports/*.py (premature optimization)
❌ Per-peer transport management
❌ ConnectionTrain complexity on Android
```

---

## What We Keep

```
✅ atmosphere/cost/ (cost model - EXCELLENT)
✅ atmosphere/auth/ (Ed25519 identity)
✅ atmosphere/mesh/node.py (identity, Shamir)
✅ atmosphere/router/intent_classifier.py (crown jewel)
✅ atmosphere/router/semantic.py (needs refactor to use gradient table)
✅ atmosphere/router/gradient.py (needs capability expansion)
✅ atmosphere/mesh/gossip.py (needs capability schema update)
```

---

## Implementation Plan

### Phase 1: Capability Schema (Day 1)
- [ ] Define `CapabilityAnnouncement` dataclass
- [ ] Include model name, type, triggers, tools
- [ ] Include cost factors
- [ ] Add signature field for security

### Phase 2: Gossip Protocol Update (Day 2)
- [ ] Update gossip to use new schema
- [ ] Implement TTL and timestamp conflict resolution
- [ ] Add capability expiry (5 min)
- [ ] Test: Two nodes see each other's capabilities

### Phase 3: Gradient Table (Day 3)
- [ ] Refactor to store full CapabilityAnnouncement
- [ ] Index by capability_id, embedding_hash, keywords
- [ ] Fast lookup for all 3 cascade tiers
- [ ] Include model name in route result

### Phase 4: Semantic Router Refactor (Day 4)
- [ ] Query gradient table for ALL capabilities (local + remote)
- [ ] Implement 3-tier cascade
- [ ] Implement composite scoring with cost factors
- [ ] Add detailed routing log

### Phase 5: Simple Transport (Day 5)
- [ ] Single relay WebSocket (that's it)
- [ ] JSON messages with routing info
- [ ] No per-peer complexity
- [ ] Test: Route request from phone to Mac

### Phase 6: Android Port (Day 6-7)
- [ ] Port capability schema
- [ ] Port hash-based matching
- [ ] Port gossip protocol
- [ ] SDK API for external apps

---

## Success Metrics

1. **Routing works**: Phone → Mac → llama-expert in <200ms
2. **Debuggable**: Every route decision explains itself
3. **Cost-aware**: Prefers local over cloud, healthy over dying
4. **Expandable**: Can add camera, agent without protocol change
5. **Secure**: Spoofed capabilities rejected
6. **Simple**: One file for transport, complexity in routing

---

## Questions to Resolve

1. **SimHash parameters**: 32-bit? 64-bit? Which hash function?
2. **Gossip interval**: 30s default, configurable?
3. **Embedding model**: MiniLM-384? Smaller for mobile?
4. **Capability expiry**: 5 min? Configurable?
5. **Max capabilities per node**: Limit for DoS prevention?

---

*The goal: Any device, any request → routed to the right place, right model, right cost, in 100ms. Every time.*
