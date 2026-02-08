# Atmosphere Reset Plan

## The Vision (What Actually Matters)

**Core Value Proposition:** Get intelligence to where it needs to be, instantly.

A request comes in → the mesh instantly knows:
1. **What kind of request** (intent classification)
2. **Which device** has the right capability
3. **Which project** on that device
4. **Which model** within that project
5. **At what cost** (latency, compute, battery, $)

This happens in milliseconds, on ANY device (phone, laptop, Raspberry Pi, server).

---

## What We're Deleting (Building on Sand)

```
❌ atmosphere/network/resilient_transport.py
❌ atmosphere/network/mesh_connection.py
❌ atmosphere/network/transports/relay.py
❌ atmosphere/network/transports/lan.py
❌ atmosphere/network/transports/ble.py
❌ Per-peer transport management
❌ ConnectionTrain complexity
❌ Transport cycling/reconnection logic
```

Keep simple relay client for now - ONE connection, works everywhere.

---

## What We're Building (The Core)

### Layer 0: Intent Classification (THE CROWN JEWEL)
```
Input: "What do llamas eat?"
Output: {
  complexity: TRIVIAL,
  task_type: QA,
  domain_hints: ["animals", "llama"],
  recommended_model_size: "tiny",
  requires_rag: false,
  latency_sensitive: true
}
```
- Already have this, needs refinement
- Fast, runs on ANY device (no embeddings needed)
- Keyword extraction + heuristics

### Layer 1: Capability Gossip Protocol
```
Every node periodically broadcasts:
{
  node_id: "abc123",
  capabilities: [
    {
      id: "llamafarm/llama-expert",
      label: "Llama & Alpaca Expert",
      embedding_hash: "a1b2c3d4",  // 32-bit hash of embedding
      embedding: [0.1, 0.2, ...],   // Full vector (optional, for capable devices)
      keywords: ["llama", "alpaca", "camelid"],
      model_size: "tiny",
      has_rag: true,
      specializations: ["animal-care", "breeding"],
      estimated_latency_ms: 50,
      cost_per_1k_tokens: 0.0,  // Local = free
    }
  ],
  device_info: {
    type: "laptop",
    on_battery: true,
    battery_percent: 80,
    available: true
  }
}
```

### Layer 2: Gradient Table (Routing Table)
```
Each node maintains:
{
  "llamafarm/llama-expert@node-abc": {
    embedding_hash: "a1b2c3d4",
    embedding: [...],  // Cached from gossip
    keywords: [...],
    hops: 1,
    via_node: "node-xyz",
    latency_ms: 150,
    last_seen: 1234567890,
    score_factors: {
      semantic_match: 0.85,
      latency_score: 0.9,
      cost_score: 1.0,
      availability: 1.0
    }
  }
}
```

### Layer 3: Cascading Semantic Router
```
Route Decision Flow:

1. CLASSIFY INTENT
   └─→ Get complexity, domain, requirements

2. MATCH CAPABILITIES (3-tier cascade)
   ├─→ Tier 1: Embedding match (if device has embeddings)
   ├─→ Tier 2: Hash match (fast, works everywhere)
   └─→ Tier 3: Keyword match (fallback, always works)

3. SCORE CANDIDATES
   For each matching capability:
   ├─→ semantic_score (0.4 weight)
   ├─→ latency_score (0.25 weight)
   ├─→ capability_score (0.2 weight) - RAG, specialization bonuses
   ├─→ hop_score (0.1 weight) - prefer direct
   └─→ cost_score (0.05 weight)

4. APPLY CONSTRAINTS
   ├─→ max_latency_ms
   ├─→ prefer_local
   ├─→ require_rag
   └─→ model_size_min/max

5. SELECT BEST
   └─→ Route to highest composite score
```

### Layer 4: Simple Transport (Just Works)
```
For now: Single WebSocket to relay
- Every device connects to relay
- Messages are JSON with routing info
- Relay forwards based on target_node

Future (when core is solid):
- Add LAN discovery (mDNS)
- Add BLE for nearby
- Add direct WebRTC
```

---

## Implementation Plan

### Phase 1: Clean Slate (Day 1) ✅
- [x] Archive current network/* code → `archive/network_old/`
- [x] Create simple RelayConnection class (one WS, that's it) → `atmosphere/transport/relay.py`
- [x] Verify basic send/receive works → Structure tests passing, ready for integration

### Phase 2: Gossip Protocol (Day 2)
- [x] Define CapabilityAnnouncement schema
- [x] Implement broadcast on connect
- [x] Implement receive + gradient table update
- [x] Add embedding hash for lightweight matching

### Phase 3: Semantic Router (Day 3-4) ✅
- [x] Refactor to use gradient table for ALL capabilities (local + remote) → `atmosphere/router/semantic.py`
- [x] Implement 3-tier cascade (embedding → hash → keyword) → `atmosphere/router/matcher.py`
- [x] Implement composite scoring with all factors → `atmosphere/router/scorer.py`
- [x] Add constraint filtering → `atmosphere/router/constraints.py`
- [x] Logging: Show WHY a route was chosen → Detailed logging in all components

### Phase 4: Integration (Day 5) ✅
- [x] Wire up to LlamaFarm project discovery
- [x] Auto-register capabilities from projects
- [x] Created `atmosphere/integration/llamafarm.py` with `discover_llamafarm_capabilities()`
- [x] Updated API routes to expose `/capabilities` and `/mesh/capabilities` endpoints
- [x] Created comprehensive test suite in `tests/test_routing.py`
- [x] Test: Mac → Phone routing (mock tests in `tests/test_mesh_integration.py`)
- [x] Test: Phone → Mac routing (mock tests in `tests/test_mesh_integration.py`)
- [x] Test: Intent classification accuracy (`tests/test_intent_accuracy.py` - 13 tests passing)

### Phase 5: Android Sync (Day 6)
- [x] Port gossip protocol to Android (GossipManager.kt)
- [x] Port hash-based matching to Android (HashMatcher.kt)
- [x] Updated SemanticRouter with hash-first cascade
- [x] Created RoutingDecision with full explanations
- [x] Integrated MeshConnection with gossip protocol
- [ ] Test full mesh routing

---

## Key Design Principles

1. **Hash-first matching** - Every device can route, no embeddings required
2. **Embeddings are optional** - Use when available for better accuracy
3. **Keywords as fallback** - Always works, even with zero deps
4. **Gossip is the source of truth** - No separate peer management
5. **Simple transport** - One relay connection, upgrade later
6. **Logging everything** - "Routed to X because: semantic=0.8, latency=50ms, has_rag=true"

---

## Success Metrics

- [ ] Phone can route "llama question" to Mac's llama-expert in <100ms
- [ ] Mac can route "summarize this" to appropriate model
- [ ] Routing decision explains itself (debuggable)
- [ ] Works offline between nearby devices (future)
- [ ] New device joins mesh → capabilities visible in <5s

---

## File Structure (New)

```
atmosphere/
├── core/
│   ├── intent.py          # Intent classification
│   ├── capability.py      # Capability schema
│   ├── gossip.py          # Gossip protocol
│   └── gradient.py        # Gradient/routing table
├── router/
│   ├── semantic.py        # 3-tier cascade router
│   ├── scorer.py          # Composite scoring
│   └── constraints.py     # Constraint filtering
├── transport/
│   └── relay.py           # Simple relay client (that's it for now)
└── api/
    └── server.py          # FastAPI server
```

---

## Questions to Resolve

1. **Embedding format**: 384-dim (MiniLM) or smaller?
2. **Hash algorithm**: SimHash? MinHash? Custom?
3. **Gossip interval**: 30s? Configurable?
4. **Relay protocol**: Keep current or simplify further?

---

*The goal: A request enters the mesh, and within 100ms, it's at the right place, being handled by the right model. Every time.*
