# Atmosphere: The Internet of Intent

## Complete Architecture Specification

**Version:** 1.0  
**Status:** Draft  
**Last Updated:** 2025-02-02  
**Document Type:** Master Architecture Specification

---

## Document Overview

This document is the definitive specification for Atmosphere—a distributed intelligence mesh that routes work to capability rather than packets to addresses. It consolidates all design work into a single, comprehensive reference.

### Related Documents

| Document | Purpose |
|----------|---------|
| `ARCHITECTURE.md` | Core routing concepts |
| `design/AGENT_LAYER.md` | Agent system details |
| `design/TOOL_SYSTEM.md` | Tool definitions and invocation |
| `design/INTEGRATIONS.md` | LlamaFarm, Ollama, Matter adapters |
| `design/SCENARIOS.md` | Real-world validation scenarios |

---

# Part I: The Vision

## 1.1 What is Atmosphere?

Atmosphere is the **Internet of Intent**—a distributed mesh network that fundamentally changes how compute happens. Instead of routing packets to addresses, Atmosphere routes **work** to **capability**.

### The Old World (Packet Routing)

```
User: "Summarize these 12 documents"
    ↓
Application: requests.post("http://api.openai.com/v1/chat")
    ↓
DNS: api.openai.com → 104.18.7.192
    ↓
TCP: Send bytes to 104.18.7.192:443
    ↓
Cloud: Process on some server in us-east-1
    ↓
Response: Wait 8 seconds, hope it doesn't time out
```

### The New World (Intent Routing)

```
User: "Summarize these 12 documents"
    ↓
Atmosphere: embed("summarize documents") → [0.23, -0.45, ...]
    ↓
Mesh: Find nodes with matching capability embedding
    ↓
Route: Best node is 2 hops away, has 70B LLM, GPU idle
    ↓
Execute: Work runs where it makes sense
    ↓
Response: 3.5 seconds, parallel across 4 nodes
```

**The fundamental shift**: From "where is the server?" to "who can do this work?"

## 1.2 The Paradigm Shift

### Packets → Intents

Traditional networks move **data** from point A to point B. Atmosphere moves **work** to wherever it can best be accomplished.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         THE PARADIGM SHIFT                                  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   TRADITIONAL INTERNET          │         ATMOSPHERE                       │
│   ──────────────────────        │         ──────────────────               │
│                                 │                                          │
│   Packet: bytes                 │         Intent: semantic meaning         │
│   Address: IP/hostname          │         Target: capability embedding     │
│   Routing: shortest path        │         Routing: best capability match   │
│   Topology: hierarchical        │         Topology: mesh (gossip)          │
│   State: centralized DNS        │         State: distributed gradients     │
│   Trust: certificate chains     │         Trust: cryptographic identity    │
│   Failure: single point         │         Failure: graceful degradation    │
│                                 │                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

### Addresses → Capabilities

You don't need to know *where* something is. You need to know *what* it can do.

```python
# Old way: You must know the address
response = requests.post("http://192.168.1.50:8080/inference", json={"image": img})

# New way: You describe what you need
response = await mesh.route("detect objects in this image", image=img)
# Atmosphere finds the best node with vision capability
```

### Static → Dynamic

Traditional services are configured and deployed. Atmosphere capabilities emerge and dissolve as nodes join and leave the mesh.

```
T=0:     Mac Mini joins mesh
         Advertises: [llm:7b, embeddings, tts]
         
T=5min:  Dell workstation joins
         Advertises: [llm:70b, vision, gpu_compute]
         
T=10min: Work arrives: "analyze this video"
         Routes to: Dell (has vision + GPU)
         
T=15min: Dell goes offline (maintenance)
         Routes to: Cloud fallback (degraded but works)
         
T=20min: Dell returns
         Routes to: Dell again (better than cloud)
```

## 1.3 The Four Principles

### Principle 1: Semantic Routing

Don't route to addresses. Route to meaning.

Every intent and every capability is an embedding vector. Routing is cosine similarity at scale.

```python
# Intent embedding (what you want)
intent_vec = embed("summarize financial reports and identify risks")
# → [0.23, -0.45, 0.12, 0.67, ...]

# Capability embedding (what's available)
node_cap_vec = embed("I can analyze financial documents, generate summaries, and assess risk factors")
# → [0.21, -0.43, 0.15, 0.64, ...]

# Routing decision
similarity = cosine_similarity(intent_vec, node_cap_vec)
# → 0.94 (excellent match)
```

**Why it matters**: No configuration files. No service discovery APIs. Capabilities find each other through meaning.

### Principle 2: Edge-First

Work runs as close to the data as possible.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           EDGE-FIRST PRINCIPLE                              │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   Data Source        Local Processing         Cloud (if needed)            │
│   ───────────        ────────────────         ─────────────────            │
│                                                                            │
│   [Camera]           [Jetson Nano]            [GPU Cloud]                  │
│      │                    │                        │                       │
│      └─── 1ms ───────────►│                        │                       │
│           Video stream    │── detect faces         │                       │
│                          │── count people         │                       │
│                          │                        │                       │
│                          ├─── 100ms ─────────────►│                       │
│                          │    Only if face        │── identify unknown    │
│                          │    not recognized      │── advanced analysis   │
│                          │                        │                       │
│                                                                            │
│   Result: 90% of work happens in 1ms at edge                              │
│           10% escalates to cloud when needed                              │
└────────────────────────────────────────────────────────────────────────────┘
```

**Why it matters**:
- **Latency**: 1ms edge vs 100ms cloud
- **Bandwidth**: Process video locally, send only results
- **Privacy**: Sensitive data never leaves local network
- **Resilience**: Works when internet is down

### Principle 3: Graceful Degradation

The mesh handles failure automatically. No single point of failure.

| Event | Response |
|-------|----------|
| Node goes offline | Route to next-best node |
| Node overloaded | Queue or route elsewhere |
| Rate limited | Back off, try alternatives |
| Network partition | Continue locally, sync later |
| Cloud unreachable | Local-only mode, reduced capability |

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      FAILURE HANDLING EXAMPLE                             │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Normal:  Intent → Node A (optimal) → Response                          │
│                                                                          │
│   Node A fails:                                                          │
│            Intent → [X] Node A                                           │
│                   → Node B (second best) → Response                      │
│                                                                          │
│   Both fail:                                                             │
│            Intent → [X] Node A                                           │
│                   → [X] Node B                                           │
│                   → Local LLM (degraded) → Response + warning           │
│                                                                          │
│   All fail:                                                              │
│            Intent → [X] All nodes                                        │
│                   → "I can't complete this right now, but I saved       │
│                      your request and will process when available"      │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Principle 4: Super Scale

O(log N) everywhere. From 10 nodes to 10 billion.

| N (nodes) | Gossip rounds to propagate | Route lookup |
|-----------|---------------------------|--------------|
| 100 | 7 | O(1) gradient table |
| 10,000 | 14 | O(1) gradient table |
| 1,000,000 | 20 | O(1) gradient table |
| 1,000,000,000 | 30 | O(1) gradient table |

No central registry. No bottleneck. Nodes discover each other via gossip protocol.

**How it works**:
- Each node tells a few neighbors about capability changes
- Those neighbors tell their neighbors
- Information propagates exponentially: reaches all nodes in O(log N) rounds
- Route lookups are constant time via local gradient tables

---

# Part II: Core Protocol

## 2.1 Protocol Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WORK LAYER                                      │
│                                                                             │
│   "Summarize these docs"  →  [Decompose]  →  Work Units  →  [Route]        │
│                                                                             │
│   Work units are the atomic pieces that get distributed across nodes       │
├─────────────────────────────────────────────────────────────────────────────┤
│                              AGENT LAYER                                     │
│                                                                             │
│   Stateful entities that perceive, decide, and act                         │
│   - Reactive (ESP32) → Deliberative → Orchestrator → Cognitive (LLM)       │
│   - Spawn children, delegate work, report results                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                              ROUTING LAYER                                   │
│                                                                             │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│   │ Intent Embedder │→ │ Gradient Table  │→ │ Load Balancer   │            │
│   │ (384-dim vector)│  │ (capability→hop)│  │ (availability)  │            │
│   └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                             │
│   Semantic matching + routing decisions happen here                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                              MESH LAYER                                      │
│                                                                             │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│   │ Gossip Protocol │  │ State Sync      │  │ Failure Detect  │            │
│   │ (propagation)   │  │ (CRDT merge)    │  │ (heartbeats)    │            │
│   └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                             │
│   Nodes discover each other, share state, detect failures                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                              IDENTITY LAYER                                  │
│                                                                             │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│   │ Rownd Local     │  │ Token Verify    │  │ Revocation      │            │
│   │ (Ed25519 keys)  │  │ (offline!)      │  │ (gossip-based)  │            │
│   └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                             │
│   Zero-trust auth. Verify without calling home. Works in bunkers.          │
├─────────────────────────────────────────────────────────────────────────────┤
│                              TRANSPORT LAYER                                 │
│                                                                             │
│   Whatever moves bytes: TCP, UDP, QUIC, LoRa, BLE, WiFi, Carrier Pigeon   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2.2 Message Types

### Intent Message

The fundamental unit of work in Atmosphere.

```json
{
  "type": "intent",
  "id": "intent-7f3a2b1c",
  "created_at": "2024-01-15T14:32:05.865Z",
  "origin_node": "factory-edge-01",
  "intent": "investigate equipment anomaly",
  "embedding": [0.23, -0.45, 0.12, 0.67, ...],
  "context": {
    "machine_id": "machine-03",
    "anomaly_type": "vibration",
    "severity": "high"
  },
  "constraints": {
    "max_latency_ms": 1000,
    "require_visual": true,
    "local_only": false
  },
  "signature": "ed25519:def456..."
}
```

### Capability Announcement

How nodes advertise what they can do.

```json
{
  "type": "capability_announce",
  "node_id": "node-abc123",
  "timestamp": "2024-01-15T12:00:00Z",
  "capabilities": [
    {
      "type": "vision",
      "description": "Image analysis with GPU acceleration",
      "embedding": [0.34, -0.21, ...],
      "tools": ["analyze_image", "detect_faces", "ocr"],
      "constraints": {
        "gpu": true,
        "max_image_mb": 50
      }
    },
    {
      "type": "llm",
      "description": "70B parameter language model inference",
      "embedding": [0.56, -0.32, ...],
      "models": ["llama3-70b", "mixtral-8x7b"],
      "constraints": {
        "context_window": 8192,
        "tokens_per_second": 45
      }
    }
  ],
  "resources": {
    "cpu_load": 0.35,
    "memory_used_gb": 12.4,
    "gpu_utilization": 0.20
  },
  "signature": "ed25519:abc123..."
}
```

### Agent Message

Communication between agents.

```json
{
  "type": "agent_message",
  "id": "msg-uuid-123",
  "from_agent": "anomaly-agent-01",
  "to_agent": "vision-agent-02",
  "via_node": "factory-ml-01",
  "message_type": "intent",
  "payload": {
    "intent": "analyze_image",
    "args": {
      "image_uri": "atmosphere://nvr-01/frames/frame-001",
      "analysis_types": ["thermal_anomaly", "motion_blur"]
    }
  },
  "ttl_hops": 3,
  "priority": 8,
  "timestamp": 1705326000000,
  "signature": "ed25519:..."
}
```

### Tool Request/Response

```json
{
  "type": "tool_invoke",
  "id": "req-uuid-123",
  "tool": "notify",
  "version": ">=1.0.0",
  "params": {
    "recipient": "rob@email.com",
    "message": "Server CPU at 95%!",
    "urgency": "high"
  },
  "context": {
    "agent_id": "monitor-agent-1",
    "session_id": "sess-456",
    "trace_id": "trace-789"
  },
  "routing": {
    "prefer_nodes": [],
    "exclude_nodes": [],
    "hop_budget": 3,
    "timeout_ms": 30000
  },
  "auth": {
    "token": "eyJ...",
    "capabilities_proof": "..."
  },
  "signature": "ed25519:..."
}
```

## 2.3 Gossip Protocol

Information propagates through the mesh via epidemic gossip.

### How It Works

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         GOSSIP PROPAGATION                                  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   Round 0:    Node A has new capability                                    │
│               ●                                                            │
│                                                                            │
│   Round 1:    A tells B and C                                              │
│               ● ──► ●                                                      │
│               └──► ●                                                       │
│                                                                            │
│   Round 2:    B tells D, E; C tells F, G                                   │
│               ● ──► ● ──► ●                                                │
│               │     └──► ●                                                 │
│               └──► ● ──► ●                                                 │
│                    └──► ●                                                  │
│                                                                            │
│   Round 3:    8 nodes know → 16 nodes know                                 │
│   Round 4:    16 nodes know → 32 nodes know                                │
│   ...                                                                      │
│   Round 20:   1,000,000 nodes know                                         │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### Gossip Message Types

| Type | Purpose | Frequency |
|------|---------|-----------|
| `capability_announce` | New/changed capabilities | On change + every 30s |
| `heartbeat` | Node is alive | Every 5s |
| `revocation` | Token/key revoked | Immediate + persist |
| `gradient_update` | Routing table changes | On change |

### Anti-Entropy

Nodes periodically compare state digests to ensure consistency:

```python
async def anti_entropy_round(self):
    """Periodic full state sync with random peer."""
    peer = random.choice(self.known_peers)
    
    # Exchange state digests
    my_digest = self.compute_state_digest()
    peer_digest = await peer.get_state_digest()
    
    # Find differences
    missing_local = peer_digest - my_digest
    missing_remote = my_digest - peer_digest
    
    # Exchange missing items
    if missing_local:
        items = await peer.get_items(missing_local)
        self.merge_items(items)
    
    if missing_remote:
        await peer.send_items(self.get_items(missing_remote))
```

## 2.4 Gradient Tables

How does a node know where to route without asking a central server?

**Gradient tables.** Each node maintains a local routing table mapping capability clusters to next-hop peers.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                    GRADIENT TABLE (on each node)                            │
├────────────────────────────────────────────────────────────────────────────┤
│ Capability Cluster  │ Best Peer     │ Hops │ Score │ Last Updated          │
├─────────────────────┼───────────────┼──────┼───────┼───────────────────────┤
│ vision/detection    │ jetson-01     │ 2    │ 0.91  │ 2s ago                │
│ vision/detection    │ cloud-gpu-01  │ 5    │ 0.94  │ 5s ago                │
│ llm/70b             │ dell-gpu      │ 1    │ 0.96  │ 1s ago                │
│ llm/7b              │ local         │ 0    │ 0.88  │ now                   │
│ embeddings          │ local         │ 0    │ 0.92  │ now                   │
│ embeddings          │ mac-studio    │ 2    │ 0.90  │ 3s ago                │
│ rag/search          │ home-server   │ 1    │ 0.85  │ 2s ago                │
│ audio/transcribe    │ cloud-whisper │ 4    │ 0.93  │ 10s ago               │
└────────────────────────────────────────────────────────────────────────────┘
```

### Gradient Update Algorithm

```python
def update_gradient(self, capability: str, peer: str, hops: int, score: float):
    """Update gradient table with new routing information."""
    key = capability
    
    # Get current entries for this capability
    entries = self.gradient_table.get(key, [])
    
    # Update or add entry
    updated = False
    for entry in entries:
        if entry.peer == peer:
            entry.hops = hops
            entry.score = score
            entry.last_updated = now()
            updated = True
            break
    
    if not updated:
        entries.append(GradientEntry(
            capability=capability,
            peer=peer,
            hops=hops,
            score=score,
            last_updated=now()
        ))
    
    # Sort by score (descending)
    entries.sort(key=lambda e: e.score, reverse=True)
    
    # Keep top N entries per capability
    self.gradient_table[key] = entries[:MAX_ENTRIES_PER_CAP]
    
    # Decay stale entries
    self._decay_stale_entries()
```

## 2.5 Routing Algorithm

The core algorithm that decides where work runs.

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
            score *= 0.5    # Penalize but don't exclude
        if node.queue_depth > 10:
            score *= 0.7
        available.append((node, score))
    
    # 3. LOCALITY BONUS
    # Prefer nearby nodes (lower latency)
    for i, (node, score) in enumerate(available):
        latency_ms = get_latency(local_node, node)
        if latency_ms < 10:
            available[i] = (node, score * 1.3)   # Local bonus
        elif latency_ms < 50:
            available[i] = (node, score * 1.1)   # Same-site bonus
        elif latency_ms > 200:
            available[i] = (node, score * 0.8)   # Distance penalty
    
    # 4. CONSTRAINT CHECK
    # Apply any hard constraints from the work unit
    if work_unit.constraints.get("local_only"):
        available = [(n, s) for n, s in available if n.is_local]
    if work_unit.constraints.get("gpu_required"):
        available = [(n, s) for n, s in available if n.has_gpu]
    if work_unit.constraints.get("max_latency_ms"):
        max_lat = work_unit.constraints["max_latency_ms"]
        available = [(n, s) for n, s in available 
                     if get_latency(local_node, n) < max_lat]
    
    # 5. SELECT BEST
    available.sort(key=lambda x: x[1], reverse=True)
    return available[0][0]
```

### Parallel Work Distribution

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

Total: 3 seconds
Sequential: 12 * 500ms + 300ms + 2500ms = 8.8 seconds
Speedup: 2.9x (scales better with more nodes)
```

---

# Part III: Distributed Registries

## 3.1 Overview

Atmosphere maintains three distributed registries that synchronize across the mesh via gossip:

1. **Capability Registry** — What nodes can do
2. **Agent Registry** — What agents exist and their state
3. **Tool Registry** — What actions can be performed

All registries use the same pattern: **base definitions + diffs**, synchronized via gossip.

## 3.2 Capability Registry

### Structure

```python
@dataclass
class CapabilityEntry:
    """A capability provided by a node."""
    capability_id: str           # Unique: "{node}:{type}:{subtype}"
    node_id: str                 # Which node provides it
    type: str                    # Category: llm, vision, embeddings, etc.
    name: str                    # Human-readable name
    description: str             # For semantic matching
    embedding: np.ndarray        # 384-dim embedding of description
    
    # Details
    models: List[str]            # Available models (if applicable)
    tools: List[str]             # Tools this capability provides
    constraints: Dict[str, Any]  # GPU required, max input size, etc.
    
    # Freshness
    version: int                 # Increments on update
    timestamp: datetime          # When last updated
    signature: bytes             # Ed25519 signature by node
```

### Gossip Sync

Capabilities propagate through gossip with delta updates:

```python
class CapabilityGossip:
    """Gossip message for capability changes."""
    
    def on_capability_change(self, capability: CapabilityEntry):
        """Called when a local capability changes."""
        # Create gossip message
        msg = {
            "type": "capability_update",
            "node_id": self.node_id,
            "capability": capability.to_dict(),
            "timestamp": now(),
            "signature": self.sign(capability)
        }
        
        # Send to random subset of peers
        peers = random.sample(self.known_peers, min(3, len(self.known_peers)))
        for peer in peers:
            await peer.send(msg)
    
    def on_gossip_receive(self, msg: dict):
        """Called when gossip message received."""
        cap = CapabilityEntry.from_dict(msg["capability"])
        
        # Verify signature
        if not self.verify_signature(msg):
            return  # Reject invalid
        
        # Check if newer than what we have
        existing = self.capability_registry.get(cap.capability_id)
        if existing and existing.version >= cap.version:
            return  # Already have newer or same
        
        # Store and re-gossip
        self.capability_registry[cap.capability_id] = cap
        self._forward_gossip(msg)
```

## 3.3 Agent Registry

### Agent Registration

When an agent starts, it registers with the mesh:

```python
@dataclass
class AgentRegistration:
    agent_id: str                         # Unique identifier
    agent_type: str                       # Type template (e.g., "anomaly_investigator")
    node_id: str                          # Host node
    parent_id: Optional[str]              # Parent agent (None for root)
    
    # Capabilities
    capabilities: List[str]               # What can this agent do?
    intents: List[str]                    # What intents does it handle?
    intent_embeddings: List[np.ndarray]   # For semantic matching
    
    # State
    state: AgentState                     # created | running | suspended | terminated
    resource_profile: ResourceProfile     # Cost/performance hints
    
    # Metadata
    version: int
    timestamp: datetime
    signature: bytes
```

### Agent Discovery Mechanisms

**Option A: Treat agents as capabilities (recommended for MVP)**

Agents register their intents as capabilities. Existing semantic routing finds them:

```python
# Register agent type as capability
router.register_capability(
    label="agent:anomaly_investigator",
    description="Agent that investigates sensor anomalies",
    handler="spawn_anomaly_investigator"
)

# Intent routing finds it automatically
result = await router.route("investigate this vibration anomaly")
# result.capability = "agent:anomaly_investigator"
```

**Option B: Gossip-based discovery (for scale)**

```python
async def on_gossip_receive(registrations: List[AgentRegistration]):
    for reg in registrations:
        if reg.timestamp > local_registry.get(reg.agent_id).timestamp:
            local_registry[reg.agent_id] = reg
            await gossip_to_peers(reg)
```

## 3.4 Tool Registry

### Tool Registration

Each node maintains a local tool registry:

```python
class ToolRegistry:
    """Registry of available tools on this node."""
    
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self.handlers: Dict[str, Callable] = {}
    
    def register(self, tool: ToolDefinition, handler: Callable):
        """Register a tool with its handler."""
        key = f"{tool.namespace}:{tool.name}"
        self.tools[key] = tool
        self.handlers[key] = handler
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name (with or without namespace)."""
        if ":" in name:
            return self.tools.get(name)
        # Search all namespaces
        for key, tool in self.tools.items():
            if key.endswith(f":{name}"):
                return tool
        return None
```

### Tool Definition Schema

```json
{
  "$schema": "https://atmosphere.dev/schemas/tool/v1",
  "tool": {
    "name": "notify",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Send notification to a person, device, or channel",
    
    "parameters": {
      "type": "object",
      "required": ["recipient", "message"],
      "properties": {
        "recipient": {
          "type": "string",
          "description": "Email, phone, @handle, or channel ID"
        },
        "message": {
          "type": "string",
          "maxLength": 4096
        },
        "urgency": {
          "type": "string",
          "enum": ["low", "medium", "high", "critical"],
          "default": "medium"
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "delivered": { "type": "boolean" },
        "delivery_id": { "type": "string" }
      }
    },
    
    "requires": {
      "capabilities": ["notification"],
      "permissions": ["notify:send"]
    },
    
    "execution": {
      "timeout_ms": 30000,
      "retries": 2
    }
  }
}
```

## 3.5 How Gossip Syncs Registries

All registries follow the same sync pattern:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                       REGISTRY GOSSIP SYNC                                  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   1. LOCAL CHANGE                                                          │
│      Node A updates its capability                                         │
│      → Increments version number                                           │
│      → Signs with node key                                                 │
│                                                                            │
│   2. GOSSIP PUSH                                                           │
│      Node A sends to 3 random peers                                        │
│      → "I have capability X version 5"                                     │
│                                                                            │
│   3. GOSSIP PULL (on receive)                                              │
│      Node B receives gossip                                                │
│      → Check: do I have version >= 5?                                      │
│      → No: store new version, forward to my peers                          │
│      → Yes: ignore (already have)                                          │
│                                                                            │
│   4. ANTI-ENTROPY (periodic)                                               │
│      Every 60s, compare digests with random peer                           │
│      → Exchange any missing entries                                        │
│      → Ensures eventual consistency                                        │
│                                                                            │
│   Result: All nodes converge to same state within O(log N) rounds          │
└────────────────────────────────────────────────────────────────────────────┘
```

---

# Part IV: Agents

## 4.1 What IS an Agent?

An **agent** is a stateful entity that:
1. **Receives intents** or events
2. **Makes decisions** about how to fulfill them
3. **Takes actions** (which may include spawning sub-agents)
4. **Reports results** to its parent or originator

Unlike a **capability** (stateless function), an agent has:
- **Lifecycle** — Exists over time, can be idle or active
- **Context** — Maintains state between invocations
- **Autonomy** — Makes decisions, not just executes
- **Delegation** — Can spawn child agents

## 4.2 The Agent Spectrum

Agents exist on a spectrum from minimal to maximal:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          THE AGENT SPECTRUM                                  │
├────────────────┬───────────────────┬───────────────────┬────────────────────┤
│    REACTIVE    │    DELIBERATIVE   │    ORCHESTRATOR   │     COGNITIVE      │
│   (Minimal)    │    (Standard)     │    (Complex)      │      (Full)        │
├────────────────┼───────────────────┼───────────────────┼────────────────────┤
│ ESP32          │ Raspberry Pi      │ Edge Server       │ Cloud/GPU          │
│ ~50 KB RAM     │ ~512 MB RAM       │ ~4 GB RAM         │ ~16+ GB RAM        │
├────────────────┼───────────────────┼───────────────────┼────────────────────┤
│ Event→Action   │ Event→Plan→Action │ Orchestrate       │ Reason, Learn      │
│ No state       │ Simple state      │ Complex state     │ Full context       │
│ No planning    │ Rule-based        │ Goal-driven       │ LLM-powered        │
│ No delegation  │ Fixed delegation  │ Dynamic spawn     │ Meta-reasoning     │
└────────────────┴───────────────────┴───────────────────┴────────────────────┘
```

### Reactive Agent (ESP32/Embedded)

The smallest possible agent. Runs on microcontrollers.

```c
// ~2KB code, ~500B RAM
typedef struct {
    uint8_t id[16];
    uint8_t type;
    uint8_t state;
    void (*handler)(uint8_t* msg, uint16_t len);
} MinimalAgent;

void vibration_handler(uint8_t* payload, uint16_t len) {
    float vibration = *(float*)payload;
    if (vibration > THRESHOLD) {
        mesh_emit("anomaly_detected", &vibration, sizeof(float));
    }
}
```

### Deliberative Agent (Standard Python)

Has state and can follow multi-step plans.

```python
@dataclass
class Agent:
    id: str
    type: str
    node_id: str
    state: AgentState = AgentState.CREATED
    context: Dict[str, Any] = field(default_factory=dict)
    
    async def handle_intent(self, intent: str, args: dict) -> Any:
        """Override in subclasses."""
        raise NotImplementedError
    
    async def spawn_child(self, agent_type: str, intent: str = None) -> str:
        """Spawn a child agent and return its ID."""
        return await agent_manager.spawn(
            agent_type=agent_type,
            parent_id=self.id,
            initial_intent=intent
        )
    
    async def emit_intent(self, intent: str, args: dict) -> Any:
        """Emit an intent to the mesh and await result."""
        return await mesh.route_and_execute(intent, args)
```

### Cognitive Agent (LLM-Powered)

Full reasoning capabilities with tool use.

```python
class CognitiveAgent(Agent):
    """Agent with LLM-powered reasoning."""
    
    def __init__(self, *args, model: str = "llama3.2", **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model
        self.conversation_history = []
    
    async def handle_intent(self, intent: str, args: dict) -> Any:
        """Use LLM to reason about and execute the intent."""
        
        # Reasoning loop
        for i in range(10):  # Max iterations
            response = await self._call_llm(intent, args)
            tool_call = self._parse_tool_call(response)
            
            if tool_call:
                result = await self._execute_tool(tool_call)
                self.conversation_history.append({
                    "role": "tool",
                    "content": str(result)
                })
            else:
                # No tool call = final answer
                return self._extract_answer(response)
```

## 4.3 Agent Lifecycle

```
                    ┌──────────────────────────────────┐
                    │                                  │
                    │         ┌──────────┐             │
         spawn()    │    ┌───→│ RUNNING  │←───┐       │ resume()
            │       │    │    └────┬─────┘    │       │
            ▼       │    │         │          │       │
       ┌────────┐   │    │         │suspend() │       │
       │CREATED │───┘    │         ▼          │       │
       └────────┘        │    ┌──────────┐    │       │
                         │    │SUSPENDED │────┘       │
                         │    └────┬─────┘            │
                         │         │                  │
                         │         │terminate()       │
                         │         │                  │
                         │         ▼                  │
                         │   ┌────────────┐           │
                         └──→│ TERMINATED │←──────────┘
                             └────────────┘
                                   │
                                   │ cleanup
                                   ▼
                               [garbage collected]
```

### Spawning an Agent

```python
async def spawn_agent(
    agent_type: str,
    parent_id: Optional[str] = None,
    initial_intent: Optional[str] = None,
    target_node: Optional[str] = None,
    config: Optional[Dict] = None
) -> str:
    """
    Create and start a new agent.
    
    1. Generate agent ID
    2. Find or negotiate hosting node
    3. Instantiate agent from type registry
    4. Send initial intent (if provided)
    5. Return agent ID for tracking
    """
```

### Agent Termination

Agents terminate when:
1. **Task complete** — Agent calls `self.terminate(result)`
2. **Parent terminates** — Cascade to children
3. **Timeout** — Exceeded max lifetime
4. **Resource limit** — Memory/children exceeded
5. **Explicit kill** — Control message from admin

## 4.4 Agent Communication

### Intra-Node (Same Node)

Direct queue access, microsecond latency:

```python
async def send_local(message: AgentMessage):
    target_agent = agent_registry.get(message.to_agent)
    await target_agent.inbox.put(message)
```

### Cross-Node (Different Nodes)

Serialize, sign, route through mesh:

```python
async def send_remote(message: AgentMessage, target_node: str):
    wire_format = serialize(message)
    wire_format.signature = node.identity.sign(wire_format.payload)
    return await router.route_message(wire_format, target_node)
```

### Delegation Pattern

Parent agent delegating to children:

```python
class OrchestratorAgent(Agent):
    async def handle_intent(self, intent: str, args: dict):
        if intent == "investigate_anomaly":
            # Spawn parallel children
            collector_id = await self.spawn_child(
                "data_collector",
                initial_intent="collect_sensor_data"
            )
            context_id = await self.spawn_child(
                "context_gatherer",
                initial_intent="gather_environmental_context"
            )
            
            # Wait for both
            data = await self.await_child(collector_id)
            context = await self.await_child(context_id)
            
            # Continue with analysis
            return await self.analyze(data, context)
```

## 4.5 Agent Message Format (Wire Protocol)

```
Agent Message Binary Format (for constrained devices):

 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Version    |     Type      |    Priority   |   TTL Hops    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         Message ID                            |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        From Agent ID                          |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         To Agent ID                           |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Payload Length        |          Reserved             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         Payload Data                          |
|                              ...                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Signature (64 bytes)                       |
|                              ...                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

Total: 28 bytes header + payload + 64 byte signature
```

---

# Part V: Tools

## 5.1 What IS a Tool?

Tools are the **actions** that agents can perform. While capabilities describe what a node *can do*, tools are the specific *functions* agents invoke.

```
Capability: "I have GPU compute power"
Tool: analyze_image(image, task) -> detected_objects[]

Capability: "I can send notifications"  
Tool: notify(recipient, message, urgency) -> delivery_status
```

### Tools vs Capabilities

| Aspect | Capability | Tool |
|--------|------------|------|
| Abstraction | Resource/ability | Specific action |
| Example | `vision` | `detect_faces(image)` |
| Discovery | Advertised via gossip | Registered with capabilities |
| Matching | Semantic similarity | Exact name + parameters |
| Runtime | Always present | May be dynamically loaded |

## 5.2 Tool Categories

### Sensing Tools

```yaml
category: sensing
tools:
  - query_sensor          # Read sensor values
  - get_camera_frame      # Capture camera image
  - read_temperature      # Get temperature reading
  - get_location          # Get device GPS location
```

### Acting Tools

```yaml
category: acting
tools:
  - control_device        # Send command to device
  - set_thermostat        # Set temperature
  - turn_on_light         # Control lights
  - unlock_door           # Control locks
```

### Communicating Tools

```yaml
category: communicating
tools:
  - notify                # Send notification
  - send_email            # Send email
  - post_slack            # Post to Slack
  - send_sms              # Send SMS
```

### Querying Tools

```yaml
category: querying
tools:
  - search_web            # Search the internet
  - query_database        # Query a database
  - rag_search            # Search vector store
  - fetch_url             # Fetch web content
```

### Computing Tools

```yaml
category: computing
tools:
  - run_model             # ML inference
  - analyze_image         # Vision analysis
  - transcribe_audio      # Speech to text
  - generate_embedding    # Create embeddings
  - llm_complete          # LLM text generation
```

### Managing Tools

```yaml
category: managing
tools:
  - spawn_agent           # Create new agent
  - kill_agent            # Terminate agent
  - store_data            # Key-value storage
  - get_data              # Retrieve stored data
```

## 5.3 Core Tool Definitions

### notify

```json
{
  "name": "notify",
  "namespace": "core",
  "description": "Send notification to person, device, or channel",
  "parameters": {
    "recipient": "string (email, phone, @handle, #channel)",
    "message": "string (max 4096 chars)",
    "urgency": "enum [low, medium, high, critical]"
  },
  "returns": { "delivered": "boolean", "delivery_id": "string" },
  "requires": { "capabilities": ["notification"], "permissions": ["notify:send"] }
}
```

### analyze_image

```json
{
  "name": "analyze_image",
  "namespace": "core",
  "description": "Analyze image using vision model",
  "parameters": {
    "image": "string (URL or base64)",
    "task": "enum [detect_objects, classify, segment, ocr, describe]",
    "prompt": "string (optional custom prompt)"
  },
  "returns": { "result": "any", "confidence": "number", "model_used": "string" },
  "requires": { "capabilities": ["vision"], "gpu_preferred": true }
}
```

### llm_complete

```json
{
  "name": "llm_complete",
  "namespace": "core",
  "description": "Generate text using LLM",
  "parameters": {
    "prompt": "string",
    "system": "string (optional)",
    "max_tokens": "integer (default 1024)",
    "temperature": "number (0-2, default 0.7)"
  },
  "returns": { "text": "string", "tokens_used": "object" },
  "requires": { "capabilities": ["llm"] }
}
```

### spawn_agent

```json
{
  "name": "spawn_agent",
  "namespace": "core",
  "description": "Create a new agent instance",
  "parameters": {
    "agent_type": "string",
    "name": "string (optional)",
    "config": "object",
    "permissions": "array[string]",
    "ttl_seconds": "integer (optional)"
  },
  "returns": { "agent_id": "string", "status": "string" },
  "requires": { "capabilities": ["agent_runtime"], "permissions": ["agent:spawn"] }
}
```

## 5.4 Tool Invocation Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Agent     │────▶│   Router     │────▶│ Target Node │
│             │     │              │     │             │
│ invoke()    │     │ find_node()  │     │ execute()   │
└─────────────┘     └──────────────┘     └─────────────┘
      │                    │                    │
      │  ToolRequest       │  RoutedRequest     │
      │─────────────────▶  │─────────────────▶  │
      │                    │                    │
      │                    │   ToolResponse     │
      │◀────────────────────────────────────────│
```

### Routing Algorithm for Tools

```python
async def route_tool_invocation(request: ToolRequest) -> ToolResponse:
    # 1. Find tool definition
    tool = registry.get(request.tool)
    if not tool:
        raise ToolNotFoundError(request.tool)
    
    # 2. Validate parameters
    validate_params(tool.parameters, request.params)
    
    # 3. Check permissions
    if not auth.has_permissions(request.auth, tool.requires.permissions):
        raise PermissionDeniedError()
    
    # 4. Find capable nodes
    nodes = await mesh.find_nodes_with_capability(tool.requires.capabilities)
    
    # 5. Score and rank
    scored = []
    for node in nodes:
        score = 1.0
        score *= 0.95 ** node.hops  # Hop penalty
        if node.is_local:
            score *= 1.2  # Local bonus
        scored.append((node, score))
    
    scored.sort(key=lambda x: -x[1])
    
    # 6. Execute on best node
    for node, score in scored:
        try:
            return await node.execute_tool(request)
        except NodeUnavailableError:
            continue
    
    raise NoCapableNodeError(tool.name)
```

## 5.5 Permission Model

### Permission Structure

```
[namespace]:[action]:[resource]

Examples:
  notify:send              # Can send notifications
  device:control:*         # Can control any device
  device:control:light-1   # Can control specific light
  agent:spawn              # Can spawn agents
  storage:read:config/*    # Can read config keys
```

### Permission Checking

```python
def has_permission(token: AgentToken, required: str) -> bool:
    """Check if token grants required permission."""
    for perm in token.permissions:
        if matches(perm, required):
            return True
    return False

def matches(granted: str, required: str) -> bool:
    """Check if granted permission covers required."""
    granted_parts = granted.split(":")
    required_parts = required.split(":")
    
    for g, r in zip(granted_parts, required_parts):
        if g == "*":
            return True
        if g != r:
            return False
    
    return len(granted_parts) >= len(required_parts)
```

### Dangerous Tool Protection

Tools marked as dangerous require additional safeguards:

```json
{
  "name": "delete_all_data",
  "dangerous": true,
  "requires": {
    "permissions": ["admin:destroy"],
    "confirmation": true,
    "multi_party": 2
  }
}
```

---

# Part VI: The Learning Edge

## 6.1 Escalation Flow

When edge devices can't handle something, work escalates up:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           ESCALATION FLOW                                   │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   [Sensor]                                                                 │
│      │                                                                     │
│      ▼                                                                     │
│   [ESP32] ──── Can handle? ────► YES ──► Process locally, done            │
│      │                                                                     │
│      NO                                                                    │
│      │                                                                     │
│      ▼                                                                     │
│   [Jetson] ──── Can handle? ────► YES ──► Process at edge, done           │
│      │                                                                     │
│      NO                                                                    │
│      │                                                                     │
│      ▼                                                                     │
│   [Home Server] ── Can handle? ─► YES ──► Process locally, done           │
│      │                                                                     │
│      NO                                                                    │
│      │                                                                     │
│      ▼                                                                     │
│   [Cloud] ──── Process, return result                                     │
│      │                                                                     │
│      └──── Also: Log for training                                         │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## 6.2 Training Loop

Edge escalations become training data:

```python
class LearningEdge:
    """Collect escalation data for model improvement."""
    
    async def on_escalation(self, 
        input_data: Any,
        edge_result: Optional[Any],
        cloud_result: Any,
        edge_node: str
    ):
        """Record escalation for future training."""
        
        # Store the training example
        example = {
            "input": input_data,
            "edge_attempt": edge_result,
            "correct_output": cloud_result,
            "edge_node": edge_node,
            "timestamp": now()
        }
        
        await self.training_store.append(example)
        
        # Check if we have enough to train
        if await self.training_store.count() > TRAINING_THRESHOLD:
            await self.trigger_training()
    
    async def trigger_training(self):
        """Train smaller model on collected examples."""
        
        # Export training data
        examples = await self.training_store.export()
        
        # Fine-tune edge model
        new_model = await self.train(
            base_model="llama3.2-3b",
            examples=examples,
            target="edge-specialized-v2"
        )
        
        # Deploy to edge nodes
        for node in self.edge_nodes:
            await node.deploy_model(new_model)
        
        # Clear training store
        await self.training_store.clear()
```

## 6.3 Model Deployment

Atmosphere supports pushing updated models to edge nodes:

```python
class ModelDeployment:
    """Deploy models to edge nodes."""
    
    async def deploy_to_node(self, node_id: str, model: Model):
        """Deploy a model to a specific node."""
        
        # Check node capacity
        node = self.mesh.get_node(node_id)
        if model.size_gb > node.available_storage_gb:
            raise InsufficientStorage()
        
        # Stream model to node
        async with node.open_transfer() as transfer:
            for chunk in model.chunks():
                await transfer.send(chunk)
        
        # Verify integrity
        if not await node.verify_model(model.checksum):
            raise CorruptedTransfer()
        
        # Hot-swap: load new model
        await node.load_model(model.name)
        
        # Update capability registry
        await node.announce_capability_update()
```

## 6.4 LlamaFarm Integration

LlamaFarm is the primary AI backend for Atmosphere:

```python
class LlamaFarmAdapter(AtmosphereAdapter):
    """Adapter for LlamaFarm AI runtime."""
    
    @property
    def adapter_id(self) -> str:
        return "llamafarm"
    
    async def discover(self) -> bool:
        """Find LlamaFarm server."""
        urls = [
            self.config.get("url"),
            os.environ.get("LLAMAFARM_URL"),
            "http://localhost:14345",
            "http://localhost:8000"
        ]
        
        for url in filter(None, urls):
            if await self._check_url(url):
                self._url = url
                return True
        return False
    
    async def connect(self) -> bool:
        """Connect and enumerate capabilities."""
        # Get projects (RAG, agents)
        projects = await self._get("/v1/projects")
        
        # Get models
        models = await self._get("/v1/models")
        
        # Build capabilities
        self._build_capabilities(projects, models)
        return True
    
    def _build_capabilities(self, projects, models):
        """Map LlamaFarm features to Atmosphere capabilities."""
        
        if models:
            self._capabilities.append(Capability(
                id="llamafarm:llm",
                type="llm",
                description="LLM inference via LlamaFarm",
                models=[m["id"] for m in models]
            ))
        
        for project in projects:
            if project["type"] == "rag":
                self._capabilities.append(Capability(
                    id=f"llamafarm:rag:{project['id']}",
                    type="rag",
                    description=f"RAG from {project['name']}"
                ))
```

---

# Part VII: Security & Identity

## 7.1 Zero-Trust Model

Atmosphere uses zero-trust authentication that works **offline**.

### The Problem

Traditional auth needs a server:
```
Client → "Is this token valid?" → Auth Server → "Yes/No"
```

This fails when:
- Internet is down
- Auth server unreachable
- Operating in isolated environment

### The Atmosphere Solution

Tokens are **self-verifying**:

```python
token = {
    "node_id": "abc123",
    "capabilities": ["vision", "llm"],
    "issued_at": 1706900000,
    "expires_at": 1706986400,  # 24h later
    "signature": "ed25519_sig_of_above_fields"
}

def verify_token(token, mesh_public_key):
    """Verify token WITHOUT network call."""
    
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

**Key insight**: The mesh public key is distributed once. Every node can then verify every token forever (until expiry) without network calls.

## 7.2 Rownd Local Integration

[Rownd Local](https://rownd.io) provides the cryptographic identity layer:

```python
class RowndLocalIdentity:
    """Identity management via Rownd Local."""
    
    def __init__(self):
        self._keypair = None
        self._mesh_key = None
    
    async def initialize(self):
        """Generate or load Ed25519 keypair."""
        if os.path.exists(KEY_PATH):
            self._keypair = load_keypair(KEY_PATH)
        else:
            self._keypair = generate_keypair()
            save_keypair(self._keypair, KEY_PATH)
    
    def sign(self, message: bytes) -> bytes:
        """Sign a message with node's private key."""
        return ed25519_sign(self._keypair.private_key, message)
    
    def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool:
        """Verify a signature."""
        return ed25519_verify(public_key, message, signature)
    
    def create_token(self, capabilities: List[str], ttl_hours: int = 24) -> dict:
        """Create a self-verifying token."""
        token = {
            "node_id": self.node_id,
            "capabilities": capabilities,
            "issued_at": int(time.time()),
            "expires_at": int(time.time()) + ttl_hours * 3600
        }
        token["signature"] = base64_encode(self.sign(json.dumps(token)))
        return token
```

## 7.3 Federation

Multiple meshes can federate:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              FEDERATION                                     │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   Mesh A (Company A)              Mesh B (Company B)                       │
│   ┌────────────────┐              ┌────────────────┐                       │
│   │  Node A1       │              │  Node B1       │                       │
│   │  Node A2       │              │  Node B2       │                       │
│   │  Node A3       │              │  Node B3       │                       │
│   └───────┬────────┘              └───────┬────────┘                       │
│           │                               │                                │
│           └───────────┬───────────────────┘                                │
│                       │                                                    │
│                       ▼                                                    │
│              ┌────────────────┐                                            │
│              │ Federation     │                                            │
│              │ Gateway        │                                            │
│              │                │                                            │
│              │ - Trust anchor │                                            │
│              │ - Route broker │                                            │
│              │ - Policy point │                                            │
│              └────────────────┘                                            │
│                                                                            │
│   Rules:                                                                   │
│   - A can use B's vision capability (contract)                            │
│   - B cannot access A's internal RAG                                       │
│   - Both contribute to shared embedding pool                               │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## 7.4 Revocation via Gossip

Compromised keys/tokens are revoked via gossip:

```python
class RevocationGossip:
    """Propagate revocations across the mesh."""
    
    def revoke(self, node_id: str, reason: str):
        """Revoke a node's credentials."""
        
        revocation = {
            "type": "revocation",
            "target": node_id,
            "reason": reason,
            "revoked_at": now(),
            "revoked_by": self.node_id,
            "signature": self.sign(...)
        }
        
        # Store locally
        self.revocation_cache[node_id] = revocation
        
        # Gossip immediately
        for peer in self.all_peers:  # Not random - broadcast
            await peer.send(revocation)
    
    def on_revocation_received(self, revocation: dict):
        """Handle incoming revocation."""
        
        # Verify signature (must be from authority)
        if not self.verify_authority(revocation):
            return
        
        # Store
        self.revocation_cache[revocation["target"]] = revocation
        
        # Forward to all peers
        for peer in self.known_peers:
            await peer.send(revocation)
```

---

# Part VIII: Integrations

## 8.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ATMOSPHERE NODE                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                         INTENT ROUTER                                  │ │
│  │   Intent → Embed → Match Capabilities → Route (local/remote)          │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                      │                                      │
│                                      ▼                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                      ADAPTER REGISTRY                                  │ │
│  │   • Manages adapter lifecycle                                         │ │
│  │   • Aggregates capabilities from all adapters                         │ │
│  │   • Dispatches tool calls to appropriate adapter                      │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│          │              │              │              │              │      │
│          ▼              ▼              ▼              ▼              ▼      │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│   │LlamaFarm │   │  Ollama  │   │  Matter  │   │Cloud APIs│   │  Custom  │ │
│   │ Adapter  │   │ Adapter  │   │ Adapter  │   │ Adapter  │   │ Adapters │ │
│   └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘ │
└────────┼──────────────┼──────────────┼──────────────┼──────────────┼───────┘
         │              │              │              │              │
         ▼              ▼              ▼              ▼              ▼
    ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
    │LlamaFarm│   │ Ollama  │   │ Thread  │   │ OpenAI  │   │  Your   │
    │  :8000  │   │ :11434  │   │ Border  │   │  API    │   │ System  │
    └─────────┘   └─────────┘   │ Router  │   └─────────┘   └─────────┘
                                └─────────┘
```

## 8.2 Adapter Interface

All integrations implement this interface:

```python
class AtmosphereAdapter(ABC):
    """Base class for all Atmosphere integrations."""
    
    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier (e.g., 'llamafarm', 'ollama')."""
        pass
    
    @abstractmethod
    async def discover(self) -> bool:
        """Check if backend is available."""
        pass
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection, enumerate capabilities."""
        pass
    
    def get_capabilities(self) -> List[Capability]:
        """Return capabilities this adapter provides."""
        return self._capabilities
    
    def get_tools(self) -> List[Tool]:
        """Return tools this adapter exposes."""
        return self._tools
    
    @abstractmethod
    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Execute a tool call."""
        pass
    
    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Check backend health."""
        pass
```

## 8.3 LlamaFarm Adapter

```python
class LlamaFarmAdapter(AtmosphereAdapter):
    """
    LlamaFarm provides:
    - Multi-model LLM inference
    - Embeddings generation
    - RAG (projects with vector stores)
    - Vision analysis
    - Agent execution
    """
    
    DEFAULT_URLS = ["http://localhost:14345", "http://localhost:8000"]
    
    @property
    def adapter_id(self) -> str:
        return "llamafarm"
    
    async def discover(self) -> bool:
        for url in self._get_urls_to_try():
            if await self._check_url(url):
                self._url = url
                return True
        return False
    
    async def connect(self) -> bool:
        # Get projects (RAG, agents)
        self._projects = await self._get("/v1/projects")
        
        # Get models
        self._models = await self._get("/v1/models")
        
        # Build capabilities
        if self._models:
            self._capabilities.append(Capability(
                id="llamafarm:llm",
                type="llm",
                models=[m["id"] for m in self._models]
            ))
        
        for project in self._projects:
            if project["type"] == "rag":
                self._capabilities.append(Capability(
                    id=f"llamafarm:rag:{project['id']}",
                    type="rag"
                ))
        
        return True
    
    async def execute_tool(self, tool_name: str, params: dict) -> ToolResult:
        if tool_name == "llamafarm_chat":
            return await self._chat(params)
        elif tool_name == "llamafarm_embed":
            return await self._embed(params)
        elif tool_name.startswith("llamafarm_rag_"):
            return await self._rag_query(tool_name, params)
```

## 8.4 Ollama Adapter

```python
class OllamaAdapter(AtmosphereAdapter):
    """
    Ollama provides:
    - LLM inference (generate, chat)
    - Embeddings (with embedding models)
    - Vision (with multimodal models)
    """
    
    DEFAULT_URL = "http://localhost:11434"
    
    # Model name patterns for capability detection
    EMBEDDING_PATTERNS = ["embed", "nomic", "bge", "e5"]
    VISION_PATTERNS = ["vision", "llava", "bakllava", "moondream"]
    
    @property
    def adapter_id(self) -> str:
        return "ollama"
    
    async def discover(self) -> bool:
        url = os.environ.get("OLLAMA_HOST", self.DEFAULT_URL)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/api/tags") as resp:
                    if resp.status == 200:
                        self._url = url
                        return True
        except:
            pass
        return False
    
    async def connect(self) -> bool:
        # Get models
        resp = await self._get("/api/tags")
        self._models = resp.get("models", [])
        
        # Categorize by capability
        for model in self._models:
            name = model["name"].lower()
            
            if any(p in name for p in self.EMBEDDING_PATTERNS):
                self._add_capability("embeddings", model["name"])
            elif any(p in name for p in self.VISION_PATTERNS):
                self._add_capability("vision", model["name"])
            else:
                self._add_capability("llm", model["name"])
        
        return True
```

## 8.5 Matter Adapter

```python
class MatterAdapter(AtmosphereAdapter):
    """
    Matter provides:
    - Device discovery via mDNS
    - Cluster-based control (OnOff, LevelControl, etc.)
    - Thread mesh connectivity
    """
    
    # Matter cluster to capability mapping
    CLUSTER_CAPABILITIES = {
        "OnOff": "switch",
        "LevelControl": "dimmer",
        "ColorControl": "light",
        "Thermostat": "climate",
        "DoorLock": "lock"
    }
    
    @property
    def adapter_id(self) -> str:
        return "matter"
    
    async def discover(self) -> bool:
        # Look for Matter controller
        # - Home Assistant with Matter integration
        # - Local chip-tool server
        # - Configured controller URL
        pass
    
    async def connect(self) -> bool:
        # Enumerate devices
        devices = await self._get_devices()
        
        for device in devices:
            # Generate tools for each device/cluster combination
            for cluster in device.clusters:
                if cluster in self.CLUSTER_CAPABILITIES:
                    self._add_device_tools(device, cluster)
        
        return True
    
    def _add_device_tools(self, device, cluster):
        """Generate Atmosphere tools from Matter device clusters."""
        
        if cluster == "OnOff":
            self._tools.append(Tool(
                name=f"matter_{device.name}_on",
                description=f"Turn on {device.friendly_name}",
                handler=lambda: self._command(device, "OnOff", "On")
            ))
            self._tools.append(Tool(
                name=f"matter_{device.name}_off",
                description=f"Turn off {device.friendly_name}",
                handler=lambda: self._command(device, "OnOff", "Off")
            ))
```

## 8.6 Custom Adapters

Creating a custom adapter:

```python
class MyCustomAdapter(AtmosphereAdapter):
    """Template for custom adapter."""
    
    @property
    def adapter_id(self) -> str:
        return "my_custom"
    
    @property
    def adapter_name(self) -> str:
        return "My Custom Integration"
    
    async def discover(self) -> bool:
        # Check if your backend is available
        return await self._check_backend()
    
    async def connect(self) -> bool:
        # Connect and enumerate capabilities
        self._capabilities = [
            Capability(
                id="my_custom:feature1",
                type="custom_type",
                description="Description for semantic matching"
            )
        ]
        
        self._tools = [
            Tool(
                name="my_custom_action",
                description="Do something custom",
                parameters={"input": "string"},
                capability_id="my_custom:feature1"
            )
        ]
        
        return True
    
    async def execute_tool(self, tool_name: str, params: dict) -> ToolResult:
        # Implement your tool execution
        result = await self._call_backend(tool_name, params)
        return ToolResult(success=True, data=result)
    
    async def health_check(self) -> HealthStatus:
        healthy = await self._ping_backend()
        return HealthStatus(
            healthy=healthy,
            state=AdapterState.CONNECTED if healthy else AdapterState.DISCONNECTED
        )
```

---

# Part IX: Bandwidth Optimization

## 9.1 Data Locality Principle

The most important optimization: **don't move data unnecessarily**.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                       DATA LOCALITY PRINCIPLE                               │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   BAD: Move data to computation                                            │
│   ────────────────────────────────                                         │
│   [Camera] ──── 100 MB video ────► [Cloud] ──── process ────► [result]    │
│                                                                            │
│   GOOD: Move computation to data                                           │
│   ──────────────────────────────                                           │
│   [Camera] ──► [Edge: has model] ──── process ────► [1 KB result]         │
│                                                                            │
│   Bandwidth saved: 99.99%                                                  │
│   Latency reduced: 90%                                                     │
│   Privacy preserved: 100%                                                  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## 9.2 Reference vs Copy

When work requires large data, prefer references over copies:

```python
# BAD: Copy data
result = await mesh.route(
    "analyze this video",
    video=load_entire_video()  # 500 MB transferred
)

# GOOD: Pass reference
result = await mesh.route(
    "analyze this video",
    video_uri="atmosphere://camera-01/recordings/2024-01-15T14:00"
    # Node fetches directly from camera (same network)
)
```

### URI Scheme

```
atmosphere://{node_id}/{path}[?params]

Examples:
  atmosphere://nvr-01/frames/frame-001
  atmosphere://home-server/documents/report.pdf?version=2
  atmosphere://factory-edge-01/sensors/vibration-03/history?last=1h
```

## 9.3 Pre-Positioned Agents

For recurring tasks, position agents close to data sources:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                      PRE-POSITIONED AGENTS                                  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   Instead of:                                                              │
│   [Sensor] ──► [Cloud] ──► "Is this anomaly?" ──► [Response]              │
│                            (100ms+ latency)                                │
│                                                                            │
│   Do this:                                                                 │
│   [Sensor] ──► [Edge Agent] ──► "Anomaly!" ──► [Cloud for follow-up]      │
│               (pre-positioned)  (1ms latency)                              │
│                                                                            │
│   The agent lives at the edge:                                             │
│   - Processes locally                                                      │
│   - Only escalates when needed                                             │
│   - Maintains context between events                                       │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## 9.4 Diff-Based Invocation

For iterative work, send deltas not full state:

```python
# Session-based invocation
session = await mesh.create_session("analyze_document", document=doc)

# First query: full context needed
result1 = await session.query("summarize this document")

# Second query: only delta (question + reference to context)
result2 = await session.query("what about the financial section?")
# Node already has document, just processes new question

# Third query: another delta
result3 = await session.query("compare to Q3 results")
# Minimal data transfer, context preserved
```

### Context Compression

```python
class ContextManager:
    """Manage context across invocations to minimize transfer."""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.contexts: Dict[str, Context] = {}
    
    async def with_context(self, context_id: str, new_data: Any):
        """Add to existing context or create new."""
        
        if context_id in self.contexts:
            # Send only the delta
            ctx = self.contexts[context_id]
            delta = compute_delta(ctx.data, new_data)
            await self._send_delta(context_id, delta)
        else:
            # First time: send full context
            await self._send_full(context_id, new_data)
            self.contexts[context_id] = Context(data=new_data)
    
    def compute_delta(self, old: Any, new: Any) -> Any:
        """Compute minimal diff between states."""
        # For text: line-level diff
        # For JSON: structural diff
        # For binary: xdelta
        pass
```

## 9.5 Bandwidth Budgets

Nodes can declare bandwidth constraints:

```json
{
  "node_id": "jetson-01",
  "bandwidth_constraints": {
    "uplink_mbps": 10,
    "downlink_mbps": 50,
    "monthly_quota_gb": 100,
    "current_usage_gb": 45
  }
}
```

The router factors this into decisions:

```python
def route_with_bandwidth(work: WorkUnit, nodes: List[Node]) -> Node:
    """Route considering bandwidth constraints."""
    
    candidates = []
    for node in nodes:
        # Skip nodes that would exceed quota
        estimated_transfer = estimate_transfer(work)
        if node.remaining_quota_gb < estimated_transfer:
            continue
        
        # Penalize slow connections
        score = compute_base_score(node, work)
        if node.uplink_mbps < 10:
            score *= 0.7
        
        candidates.append((node, score))
    
    return max(candidates, key=lambda x: x[1])[0]
```

---

# Part X: Implementation Status & MVP

## 10.1 What's Built

| Component | Status | Notes |
|-----------|--------|-------|
| **Semantic routing** | ✅ Working | 100% accuracy, 14.5ms latency |
| **Gradient tables** | ✅ Working | Local lookup, gossip updates |
| **Gossip protocol** | ✅ Working | O(log N) propagation |
| **Zero-trust auth** | ✅ Working | Offline verification via Ed25519 |
| **Parallel dispatch** | 🟡 Basic | Needs production hardening |
| **Failure recovery** | 🟡 Basic | Needs more testing |
| **Agent framework** | 🟡 Design complete | Implementation needed |
| **Tool system** | 🟡 Design complete | Implementation needed |
| **LlamaFarm adapter** | 🟡 Designed | Implementation needed |
| **Ollama adapter** | 🟡 Designed | Implementation needed |
| **Matter adapter** | 🟡 Designed | Implementation needed |
| **Visual designer** | ✅ Working | Shows topology |

## 10.2 MVP Requirements

### Core (Week 1-2)

- [ ] Agent base class and lifecycle
- [ ] Simple agent registry (in-memory)
- [ ] Agent-as-capability wrapper
- [ ] Basic spawn/terminate
- [ ] Local-only agent communication

### Distribution (Week 3-4)

- [ ] Cross-node agent spawning
- [ ] Cross-node messaging
- [ ] Agent discovery via existing routing
- [ ] Resource limits enforcement

### Tools (Week 5-6)

- [ ] Tool registry
- [ ] Core tool implementations (notify, llm_complete, analyze_image)
- [ ] Permission checking
- [ ] Tool routing

### Adapters (Week 7-8)

- [ ] LlamaFarm adapter (full)
- [ ] Ollama adapter (full)
- [ ] Matter adapter (basic)
- [ ] Adapter health monitoring

### Production (Week 9-10)

- [ ] Load testing (1000+ concurrent intents)
- [ ] Multi-node demo (Mac + Dell + Jetson)
- [ ] Documentation (API reference, tutorials)
- [ ] Performance optimization

## 10.3 Validation Scenarios

The architecture has been validated against four real-world scenarios:

### Scenario 1: Smart Factory Anomaly Response
- Vibration sensor → threshold watcher → anomaly classification → visual confirmation → prediction → notification
- Validates: Multi-hop routing, parallel processing, edge-first, graceful degradation

### Scenario 2: Personal Assistant Query
- Voice input → RAG search → LLM synthesis → TTS output
- Validates: Privacy (local-first), semantic routing, multi-source context

### Scenario 3: Multi-Device Home Automation
- Price spike → energy optimization → Matter device control → battery management
- Validates: Cross-protocol, real-time decisions, coordinated actions

### Scenario 4: Security Incident Response
- Motion detection → face recognition → threat assessment → human-in-the-loop escalation
- Validates: Latency-critical, permission system, automatic vs approved actions

See `design/SCENARIOS.md` for detailed timing diagrams and message flows.

## 10.4 Roadmap

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              ROADMAP                                        │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   Q1 2025: Foundation                                                      │
│   ├── ✅ Semantic routing (done)                                          │
│   ├── ✅ Gossip protocol (done)                                           │
│   ├── ✅ Zero-trust auth (done)                                           │
│   ├── 🔲 Agent framework                                                  │
│   └── 🔲 Tool system                                                      │
│                                                                            │
│   Q2 2025: Integrations                                                    │
│   ├── 🔲 LlamaFarm adapter                                                │
│   ├── 🔲 Ollama adapter                                                   │
│   ├── 🔲 Matter adapter                                                   │
│   └── 🔲 Multi-node demo                                                  │
│                                                                            │
│   Q3 2025: Scale                                                           │
│   ├── 🔲 Load testing (10K+ nodes simulated)                              │
│   ├── 🔲 Production hardening                                             │
│   ├── 🔲 Monitoring & observability                                       │
│   └── 🔲 Beta with early adopters                                         │
│                                                                            │
│   Q4 2025: Ecosystem                                                       │
│   ├── 🔲 SDK release (Python, TypeScript, Rust)                           │
│   ├── 🔲 Plugin marketplace                                               │
│   ├── 🔲 Documentation & tutorials                                        │
│   └── 🔲 Public launch                                                    │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

# Appendices

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Intent** | A semantic description of work to be done |
| **Capability** | A resource or ability a node provides |
| **Agent** | A stateful entity that perceives, decides, and acts |
| **Tool** | A specific action an agent can invoke |
| **Gradient Table** | Local routing table mapping capabilities to peers |
| **Gossip** | Epidemic protocol for information propagation |
| **Mesh** | The network of Atmosphere nodes |
| **Work Unit** | Atomic piece of computation |
| **Embedding** | Vector representation of text for semantic matching |

## Appendix B: Configuration Reference

```yaml
# atmosphere.yaml
node:
  id: auto  # Generate UUID or specify
  name: "my-node"

mesh:
  bootstrap_peers:
    - "192.168.1.100:8080"
    - "peer.example.com:8080"
  gossip_interval_ms: 5000
  heartbeat_interval_ms: 1000

identity:
  key_path: ~/.atmosphere/identity.key
  mesh_public_key: "ed25519:abc123..."

adapters:
  llamafarm:
    enabled: true
    url: http://localhost:14345
  ollama:
    enabled: true
    url: http://localhost:11434
  matter:
    enabled: false
    controller_url: null

routing:
  embedding_model: all-MiniLM-L6-v2
  similarity_threshold: 0.7
  local_preference: 1.2
  hop_penalty: 0.95

resources:
  max_agents: 100
  max_memory_gb: 4
  max_concurrent_intents: 50
```

## Appendix C: API Quick Reference

### Route an Intent

```python
result = await mesh.route(
    intent="summarize this document",
    context={"document": doc_content},
    constraints={"max_latency_ms": 5000}
)
```

### Spawn an Agent

```python
agent_id = await mesh.spawn_agent(
    agent_type="research_agent",
    config={"model": "llama3-70b"},
    initial_intent="research competitor pricing"
)

result = await mesh.await_agent(agent_id, timeout_ms=60000)
```

### Invoke a Tool

```python
result = await mesh.invoke_tool(
    tool="notify",
    params={
        "recipient": "user@example.com",
        "message": "Task complete!",
        "urgency": "low"
    }
)
```

### Register a Capability

```python
@mesh.capability(
    type="custom",
    description="My custom processing capability"
)
async def my_handler(input_data: dict) -> dict:
    # Process and return
    return {"result": processed_data}
```

---

## Appendix D: Architecture Decision Records

### ADR-001: Semantic Routing over Service Discovery

**Decision**: Use embedding-based semantic routing instead of traditional service discovery.

**Rationale**:
- No configuration needed: capabilities find each other through meaning
- Natural handling of fuzzy requests
- Graceful degradation: partial matches still work
- Scale: O(log N) gossip vs O(N) registry queries

### ADR-002: Gossip over Consensus

**Decision**: Use epidemic gossip for state propagation instead of consensus protocols.

**Rationale**:
- Eventually consistent is sufficient for our use case
- No leader election, no coordination overhead
- Works through partitions
- O(log N) propagation regardless of network topology

### ADR-003: Self-Verifying Tokens

**Decision**: Tokens contain all information needed for verification, signed by issuer.

**Rationale**:
- Works offline (critical for edge deployment)
- No central auth server bottleneck
- Revocation handled via gossip
- Simple to implement with Ed25519

### ADR-004: Agents as First-Class Citizens

**Decision**: Agents are stateful entities with lifecycle, not just request handlers.

**Rationale**:
- Enables multi-step reasoning
- Supports parent-child delegation
- Allows context preservation across invocations
- Matches real-world task patterns

---

*This document is the complete specification for Atmosphere.*

*For implementation details, see the source code.*  
*For tutorials, see the documentation website.*  
*For questions, open an issue on GitHub.*

---

**Document Version:** 1.0  
**Last Updated:** 2025-02-02  
**Authors:** Atmosphere Team
