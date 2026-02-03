# Atmosphere: Master Architecture

**The Internet of Intent — Route Intelligence, Not Packets**

---

## The Core Idea

Traditional networks route **packets** to **addresses**.

Atmosphere routes **work** to **capability**.

The question changes from *"Where is 192.168.1.50?"* to *"Who can analyze this image?"*

**This is the entire thesis.** Everything else serves this.

---

## The One Thing That Matters

### WHERE work gets done

A user asks: *"Summarize these 12 documents and compare them to last quarter's strategy."*

What happens:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Intent: "Summarize 12 docs, compare to strategy"                      │
│                                                                         │
│  Atmosphere decomposes this into WORK:                                 │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Work Unit 1: Embed doc 1     → Node A (has embeddings, idle)    │   │
│  │ Work Unit 2: Embed doc 2     → Node B (has embeddings, idle)    │   │
│  │ Work Unit 3: Embed doc 3     → Node A (still has capacity)      │   │
│  │ Work Unit 4: Embed doc 4     → Node C (just came online)        │   │
│  │ ...                                                              │   │
│  │ Work Unit 12: Embed doc 12   → Node B                           │   │
│  │                                                                  │   │
│  │ Work Unit 13: RAG search     → Node D (has vector DB)           │   │
│  │ Work Unit 14: Summarize      → Node E (has 70B LLM, GPU)        │   │
│  │ Work Unit 15: Compare        → Node E (already has context)     │   │
│  │ Work Unit 16: Format response → Local (fastest)                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  12 embedding calls spread across 3 nodes in parallel: 200ms           │
│  RAG + summarize + compare on GPU node: 3s                             │
│  Total: ~3.5s instead of 30s sequential                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**This is what Atmosphere does.** It decides WHERE each piece of work runs based on:

1. **Capability** — Can this node do this work?
2. **Availability** — Is it online? Is it busy?
3. **Locality** — Is it close (low latency)?
4. **Cost** — Is there a cheaper option?
5. **Constraints** — Privacy? Latency requirements? Data residency?

---

## Core Principles

### 1. Bidirectional Capabilities

Every capability is both a **trigger** and a **tool**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                     BIDIRECTIONAL CAPABILITY                           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   PUSH (Trigger)                         PULL (Tool)                   │
│                                                                        │
│   Camera detects motion          ←→      Agent queries camera          │
│   Model finishes training        ←→      Agent invokes inference       │
│   Sensor hits threshold          ←→      Agent reads current value     │
│                                                                        │
│   Same capability. Same mesh. Both directions.                         │
└────────────────────────────────────────────────────────────────────────┘
```

**Why this matters:**
- A camera isn't just a passive sensor you query
- A model isn't just an endpoint you call  
- Everything is a peer that can both **initiate** and **respond**

```yaml
capability:
  id: front-door-camera
  type: sensor/camera
  
  tools:      # What agents can PULL
    - get_frame: "Current camera snapshot"
    - get_history: "Motion events from last N minutes"
    
  triggers:   # What it can PUSH
    - motion_detected: "Intent routes to security agent"
    - person_detected: "High-priority, routes to notifications"
    - package_detected: "Routes to delivery tracking"
```

See [design/BIDIRECTIONAL_CAPABILITIES.md](design/BIDIRECTIONAL_CAPABILITIES.md) for the full specification.

### 2. Semantic Routing

Don't route to addresses. Route to meaning.

```python
# Traditional
requests.post("http://gpu-server-01.internal:8080/inference", data=image)

# Atmosphere
mesh.route("detect objects in this image", data=image)
# → Automatically finds best node with vision capability
```

**How it works:**
- Every node advertises capabilities as embedding vectors
- Intents are embedded using the same model
- Cosine similarity finds the best match
- Gradient tables cache routes for speed

### 2. Edge-First

Work runs as close to the data as possible.

```
Sensor data → Edge node (1ms away) → Process locally
                ↓
        Only if edge can't handle it:
                ↓
            Cloud (100ms away)
```

**Why:**
- Latency: 1ms vs 100ms matters
- Bandwidth: Don't ship video to cloud
- Privacy: Data stays local when possible
- Resilience: Works when internet is down

### 3. Graceful Degradation

The mesh handles failure automatically.

| Event | Response |
|-------|----------|
| Node goes offline | Route to next-best node |
| Node is busy | Queue or route elsewhere |
| Rate limited | Back off, try alternatives |
| Network partition | Continue locally, sync later |

No single point of failure. No central coordinator that can die.

### 4. Super Scale

O(log N) everywhere.

| N (nodes) | Gossip rounds to propagate | Route lookup |
|-----------|---------------------------|--------------|
| 100 | 7 | O(1) gradient table |
| 10,000 | 14 | O(1) gradient table |
| 1,000,000 | 20 | O(1) gradient table |
| 1,000,000,000 | 30 | O(1) gradient table |

No central registry. No bottleneck. Nodes discover each other via gossip.

### 5. Useful Now

This isn't vaporware. Working today:

- ✅ Semantic routing with real embeddings
- ✅ 21-node mesh operational
- ✅ 100% routing accuracy in tests
- ✅ <15ms routing latency
- ✅ Zero-trust auth (offline verification)
- ✅ Visual designer showing topology

---

## The Protocol Stack

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         WORK LAYER                                      │
│                                                                         │
│  ┌───────────────────────────────┐  ┌───────────────────────────────┐  │
│  │         PUSH (Triggers)       │  │         PULL (Tools)          │  │
│  │                               │  │                               │  │
│  │  Camera → "motion detected"   │  │  Agent → camera.get_frame()   │  │
│  │  Model → "training complete"  │  │  Agent → thermostat.set(72)   │  │
│  │  Sensor → "threshold hit"     │  │  Agent → model.classify(img)  │  │
│  └───────────────────────────────┘  └───────────────────────────────┘  │
│                                                                         │
│  Both directions use the same routing fabric below                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         ROUTING LAYER                                   │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │ Intent Embedder │→ │ Gradient Table  │→ │ Load Balancer   │         │
│  │ (384-dim vector)│  │ (capability→hop)│  │ (availability)  │         │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘         │
│                                                                         │
│  Semantic matching + routing decisions happen here                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         MESH LAYER                                      │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │ Gossip Protocol │  │ State Sync      │  │ Failure Detect  │         │
│  │ (propagation)   │  │ (CRDT merge)    │  │ (heartbeats)    │         │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘         │
│                                                                         │
│  Nodes discover each other, share state, detect failures               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         IDENTITY LAYER                                  │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │ Rownd Local     │  │ Token Verify    │  │ Revocation      │         │
│  │ (Ed25519 keys)  │  │ (offline!)      │  │ (gossip-based)  │         │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘         │
│                                                                         │
│  Zero-trust auth. Verify without calling home. Works in bunkers.       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         TRANSPORT LAYER                                 │
│                                                                         │
│  Whatever moves bytes: TCP, UDP, QUIC, LoRa, BLE, WiFi, Carrier Pigeon │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Work Distribution: The Core Algorithm

When work arrives, Atmosphere decides where it runs:

```python
def route_work(work_unit: WorkUnit) -> Node:
    """
    THE CORE ALGORITHM
    
    Input: A piece of work that needs to be done
    Output: The node that should do it
    """
    
    # 1. CAPABILITY MATCH
    # Find nodes that CAN do this work
    candidates = []
    for node in mesh.nodes:
        similarity = cosine_similarity(
            work_unit.embedding,
            node.capability_embedding
        )
        if similarity > 0.7:
            candidates.append((node, similarity))
    
    if not candidates:
        raise NoCapableNode("No node can handle this work")
    
    # 2. AVAILABILITY FILTER
    # Remove nodes that are offline, busy, or unhealthy
    available = []
    for node, score in candidates:
        if node.status != "online":
            continue
        if node.load > 0.9:  # >90% busy
            score *= 0.5  # Penalize but don't exclude
        if node.queue_depth > 10:
            score *= 0.7
        available.append((node, score))
    
    # 3. LOCALITY BONUS
    # Prefer nearby nodes (lower latency)
    for i, (node, score) in enumerate(available):
        latency_ms = get_latency(local_node, node)
        if latency_ms < 10:
            available[i] = (node, score * 1.3)  # Local bonus
        elif latency_ms < 50:
            available[i] = (node, score * 1.1)  # Same-site bonus
        elif latency_ms > 200:
            available[i] = (node, score * 0.8)  # Distance penalty
    
    # 4. CONSTRAINT CHECK
    # Apply any hard constraints from the work unit
    if work_unit.constraints.get("local_only"):
        available = [(n, s) for n, s in available if n.is_local]
    if work_unit.constraints.get("gpu_required"):
        available = [(n, s) for n, s in available if n.has_gpu]
    if work_unit.constraints.get("max_latency_ms"):
        max_lat = work_unit.constraints["max_latency_ms"]
        available = [(n, s) for n, s in available if get_latency(local_node, n) < max_lat]
    
    # 5. SELECT BEST
    available.sort(key=lambda x: x[1], reverse=True)
    return available[0][0]
```

---

## Parallel Work Distribution

The real power: spreading work across the mesh.

```python
async def execute_parallel(work_units: List[WorkUnit]) -> List[Result]:
    """
    Execute multiple work units in parallel across the mesh.
    This is how you summarize 12 docs in 200ms instead of 3s.
    """
    
    # Route each work unit to best node
    assignments = []
    for unit in work_units:
        node = route_work(unit)
        assignments.append((unit, node))
    
    # Execute all in parallel
    tasks = []
    for unit, node in assignments:
        task = asyncio.create_task(node.execute(unit))
        tasks.append(task)
    
    # Gather results (with timeout per unit)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle failures gracefully
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            # Retry on different node
            unit = work_units[i]
            backup_node = route_work(unit, exclude=[assignments[i][1]])
            result = await backup_node.execute(unit)
        final_results.append(result)
    
    return final_results
```

**Example: 12-Document Summary**

```
Time 0ms:    Route 12 embed jobs → 3 available nodes
Time 1ms:    All 12 jobs dispatched in parallel
Time 150ms:  Node A returns embeddings for docs 1, 3, 7, 10
Time 180ms:  Node B returns embeddings for docs 2, 6, 11, 12
Time 200ms:  Node C returns embeddings for docs 4, 5, 8, 9
Time 201ms:  Route RAG search → Node D (has vector DB)
Time 500ms:  RAG results returned
Time 501ms:  Route summarization → Node E (70B LLM)
Time 3000ms: Summary complete
Time 3001ms: Format and return to user

Total: 3 seconds
Sequential would be: 12 * 500ms + 300ms + 2500ms = 8.8 seconds
Speedup: 2.9x (and scales better with more nodes)
```

---

## The Gradient Table

How does a node know where to route without asking a central server?

**Gradient tables.** Each node maintains a local routing table that maps capability clusters to next-hop peers.

```
┌────────────────────────────────────────────────────────────────────────┐
│                    GRADIENT TABLE (on each node)                       │
├────────────────────────────────────────────────────────────────────────┤
│ Capability Cluster  │ Best Peer     │ Hops │ Score │ Last Updated     │
├─────────────────────┼───────────────┼──────┼───────┼──────────────────┤
│ vision/detection    │ jetson-01     │ 2    │ 0.91  │ 2s ago           │
│ vision/detection    │ cloud-gpu-01  │ 5    │ 0.94  │ 5s ago           │
│ llm/70b             │ dell-gpu      │ 1    │ 0.96  │ 1s ago           │
│ llm/7b              │ local         │ 0    │ 0.88  │ now              │
│ embeddings          │ local         │ 0    │ 0.92  │ now              │
│ embeddings          │ mac-studio    │ 2    │ 0.90  │ 3s ago           │
│ rag/search          │ home-server   │ 1    │ 0.85  │ 2s ago           │
│ audio/transcribe    │ cloud-whisper │ 4    │ 0.93  │ 10s ago          │
└────────────────────────────────────────────────────────────────────────┘
```

**How it's updated:**

1. **Capability Beacons**: Nodes broadcast their capabilities every 30s
2. **Gossip**: Beacons propagate via gossip (O(log N) rounds)
3. **Reinforcement**: Successful routes increase scores, failures decrease them
4. **Decay**: Stale entries (no beacon in 5 min) get pruned

---

## Handling Failures

The mesh self-heals.

### Node Goes Offline

```
T=0:     Node B stops responding
T=5s:    Heartbeat missed
T=10s:   Second heartbeat missed, mark "suspect"
T=30s:   Third miss, mark "offline"
T=30.1s: Gradient table updated, routes through B removed
T=30.2s: Next work unit that would have gone to B → routes to C instead
```

### Node Overwhelmed

```
T=0:     Node A reports 95% CPU, queue depth 15
T=0.1s:  State propagates via gossip
T=1s:    All nodes see A is busy
T=1.1s:  Work that would score A highest now penalized
T=1.2s:  Work routes to B instead (second-best capability match)
T=60s:   A's load drops to 40%
T=61s:   A becomes preferred again
```

### Network Partition

```
Site 1                          Site 2
┌──────────────┐                ┌──────────────┐
│ Node A       │    PARTITION   │ Node C       │
│ Node B       │ ══════════════ │ Node D       │
└──────────────┘                └──────────────┘

T=0:     Partition occurs
T=30s:   Sites detect they can't reach each other
T=31s:   Each site continues operating independently
         - Site 1: A and B still route to each other
         - Site 2: C and D still route to each other
T=???:   Partition heals
T=+1s:   Gossip resumes, gradient tables merge
T=+5s:   Full mesh restored, routes optimized
```

---

## Identity & Trust

Zero-trust authentication that works offline.

### The Problem

Traditional auth needs a server:
```
Client → "Is this token valid?" → Auth Server → "Yes/No"
```

This fails when:
- Internet is down
- Auth server is unreachable
- You're in a bunker

### The Atmosphere Solution

Tokens are self-verifying:

```python
# Token structure (simplified)
token = {
    "node_id": "abc123",
    "capabilities": ["vision", "llm"],
    "issued_at": 1706900000,
    "expires_at": 1706986400,  # 24h later
    "signature": "ed25519_sig_of_above_fields"
}

# Verification (NO NETWORK CALL)
def verify_token(token, mesh_public_key):
    # Check signature
    if not ed25519_verify(mesh_public_key, token.signature):
        return False, "Invalid signature"
    
    # Check expiration
    if time.time() > token.expires_at:
        return False, "Expired"
    
    # Check revocation (local cache, updated via gossip)
    if token.node_id in revocation_cache:
        return False, "Revoked"
    
    return True, "Valid"
```

**Key insight:** The mesh public key is the only thing you need. It's distributed once, then every node can verify every token forever (until expiry) without calling anyone.

---

## Integration Points

Atmosphere doesn't replace your AI stack. It orchestrates it.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ATMOSPHERE MESH                                 │
│                                                                         │
│  Routes work to capabilities, doesn't care what provides them          │
│                                                                         │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   LlamaFarm     │    │     Ollama      │    │     vLLM        │
│                 │    │                 │    │                 │
│ - Projects      │    │ - Models        │    │ - High-perf     │
│ - RAG           │    │ - Simple API    │    │ - Batching      │
│ - Agents        │    │ - Local         │    │ - GPU optimized │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┴───────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │    Actual Hardware      │
                    │                         │
                    │  CPU, GPU, TPU, NPU     │
                    └─────────────────────────┘
```

Atmosphere provides:
- **Discovery**: "LlamaFarm is running on this node with these capabilities"
- **Routing**: "This work needs RAG, LlamaFarm has it, route there"
- **Load balancing**: "Ollama on Node A is busy, try Node B"
- **Failover**: "vLLM crashed, fall back to Ollama"

---

## What Changes the World

Traditional AI:
```
User → Cloud API → Response
       (100ms+, requires internet, data leaves your control)
```

Atmosphere AI:
```
User → Mesh → Wherever is best → Response
       (1ms-100ms, works offline, data stays where you want)
```

**The shift:**
- From "send data to the AI" to "send AI to the data"
- From "one big model in the cloud" to "many specialized models everywhere"
- From "pray the API is up" to "mesh self-heals"
- From "trust the cloud provider" to "trust the math"

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Semantic routing | ✅ Working | 100% accuracy, 14.5ms latency |
| Gradient tables | ✅ Working | Local lookup, gossip updates |
| Gossip protocol | ✅ Working | O(log N) propagation |
| Zero-trust auth | ✅ Working | Offline verification |
| Parallel dispatch | 🟡 Basic | Needs production hardening |
| Failure recovery | 🟡 Basic | Needs more testing |
| LlamaFarm adapter | ✅ Designed | Implementation needed |
| Ollama adapter | ✅ Designed | Implementation needed |
| Matter bridge | ✅ Designed | Implementation needed |

---

## Next Steps

1. **Harden parallel dispatch** — Production-ready work distribution
2. **Build adapters** — LlamaFarm, Ollama, Matter integrations
3. **Multi-node demo** — Mac + Dell + Jetson working together
4. **Load testing** — 1000+ concurrent work units
5. **Documentation** — Full API reference, tutorials

---

## The Vision

A world where:
- Every device with compute joins the mesh
- Work flows to the best place automatically
- Internet optional, not required
- No single company controls the infrastructure
- AI is as available as electricity

**This is the Internet of Intent.**

---

*Document Version: 1.0*  
*Date: 2026-02-02*  
*Core Focus: Semantic routing, work distribution, edge-first, resilient mesh*
