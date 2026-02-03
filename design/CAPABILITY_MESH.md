# Capability Mesh Design

> **Route any intent to any capability across a distributed mesh.**

## Overview

Atmosphere is not just a text router for LLMs — it's a **capability mesh** that routes typed intents to the right capability on the right node. Whether it's a text query, an image to classify, an audio clip to transcribe, or a tool to execute, the mesh finds the best handler.

## The Problem

Traditional AI systems require you to know:
- Which model to call
- Where it's running
- What format it expects
- How to handle failures

**Atmosphere abstracts this away:** Express your intent, the mesh handles the rest.

---

## Core Concepts

### 0. Bidirectional Capabilities

**Every capability is both a trigger and a tool.** This is the foundational insight of the capability mesh.

| Direction | Mechanism | Example |
|-----------|-----------|---------|
| **PUSH** | Triggers | Camera detects motion → publishes intent to mesh |
| **PULL** | Tools | Agent calls `camera.get_history()` → gets data back |

Same capability. Same registration. Same routing fabric. Both directions.

See **[BIDIRECTIONAL_CAPABILITIES.md](BIDIRECTIONAL_CAPABILITIES.md)** for the complete specification including:
- Capability schema with tools and triggers
- Push and pull routing flows
- Cross-capability workflow examples
- Implementation patterns

### 1. Typed Intents

Every request is a typed intent with structured metadata:

```yaml
Intent:
  id: "int-abc123"
  type: "vision/classify"       # Capability needed
  domain: "wildlife"            # Domain hint for routing
  data:                         # Payload
    image: <base64 or URL>
    context: "backyard camera"
  preferences:
    latency: "low"              # low (<100ms), normal, high-quality
    accuracy: "high"            # best-effort, high, exact
    location: "prefer-local"    # local, any, specific-node
  cache:
    key: "backyard-frame-hash"  # For result caching
    ttl: 3600                   # Cache TTL in seconds
  callback:                     # Optional async response
    url: "http://sensor/callback"
    method: "POST"
```

### 2. Capability Types

| Category | Type | Description |
|----------|------|-------------|
| **LLM** | `llm/chat` | Conversational AI |
| | `llm/reasoning` | Complex multi-step reasoning |
| | `llm/code` | Code generation/analysis |
| | `llm/summarize` | Text summarization |
| **Vision** | `vision/classify` | Image classification |
| | `vision/detect` | Object detection |
| | `vision/ocr` | Text extraction from images |
| | `vision/segment` | Image segmentation |
| **Audio** | `audio/transcribe` | Speech to text |
| | `audio/generate` | Text to speech |
| | `audio/identify` | Sound/speaker identification |
| **Agent** | `agent/research` | Autonomous web research |
| | `agent/workflow` | Multi-step task execution |
| | `agent/monitor` | Continuous monitoring |
| **Tool** | `tool/camera` | Camera capture |
| | `tool/iot` | IoT device control |
| | `tool/api` | External API calls |
| | `tool/file` | File operations |
| **ML** | `ml/anomaly` | Anomaly detection |
| | `ml/classify` | Classification |
| | `ml/forecast` | Time series forecasting |
| | `ml/embed` | Embedding generation |

### 3. Node Capabilities

Each node advertises its capabilities via gossip:

```yaml
Node: rob-mac
Capabilities:
  # LLM capabilities with domain expertise
  - type: llm/chat
    projects:
      - name: llama-expert-14
        domain: camelids
        has_rag: true
      - name: fishing-assistant
        domain: fishing
        has_rag: true
  
  # Vision capabilities
  - type: vision/classify
    models:
      - name: wildlife-yolo
        domain: wildlife
        accuracy: 0.94
      - name: general-clip
        domain: general
        accuracy: 0.89
  
  - type: vision/ocr
    models: [doctr, tesseract]
  
  # Agents
  - type: agent/research
    id: research-agent
    triggers:
      - "research *"
      - "find out about *"
    tools: [web-search, summarize, rag-query]
  
  # Tools
  - type: tool/camera
    devices:
      - id: webcam-0
        location: office
      - id: security-cam-1
        location: front-door

Resources:
  memory_gb: 64
  gpu: "M1 Max"
  cpu_cores: 10
  
Network:
  latency_to_peers:
    matt-dell: 45ms
    edge-sensor-1: 12ms
    cloud-1: 120ms

Status: online
Load: 0.3
LastSeen: 2026-02-02T17:30:00Z
```

---

## Routing Architecture

### Multi-Tier Routing

```
┌─────────────────────────────────────────────────────────────────┐
│                        INTENT ROUTER                             │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  TIER 1: Cache (0.01ms)                                    │ │
│  │  • Exact intent hash match                                 │ │
│  │  • TTL: 60 seconds                                         │ │
│  └────────────────────────────────────────────────────────────┘ │
│                           │ miss                                 │
│                           ▼                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  TIER 2: Semantic Cache (0.1ms)                            │ │
│  │  • SimHash similarity match                                │ │
│  │  • TTL: 1 hour                                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                           │ miss                                 │
│                           ▼                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  TIER 3: Keyword/Type Match (0.5ms)                        │ │
│  │  • Capability type → candidate nodes                       │ │
│  │  • Domain keyword matching                                 │ │
│  │  • No embedding model required                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                           │ multiple candidates                  │
│                           ▼                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  TIER 4: Semantic Ranking (10ms)                           │ │
│  │  • Embedding similarity (if embedder available)            │ │
│  │  • Or: request peer to embed                               │ │
│  └────────────────────────────────────────────────────────────┘ │
│                           │                                      │
│                           ▼                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  TIER 5: Selection (0.1ms)                                 │ │
│  │  • Score by: accuracy, latency, load, preferences          │ │
│  │  • Return best node + capability                           │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Distributed Embeddings

The challenge: How do tiny edge devices match queries without an embedding model?

**Solution: Multi-Representation Gossip**

Each capability is gossiped with multiple representations:

```yaml
CapabilityRecord:
  id: "llama-expert-14@rob-mac"
  type: llm/chat
  domain: camelids
  
  representations:
    # Full embedding (384 dims) - for nodes with embedder
    embedding: [0.12, -0.34, 0.56, ...]
    
    # SimHash (64 bits) - for nodes without embedder
    simhash: "a7f3b2c1e9d8..."
    
    # Keywords - universal fallback
    keywords: ["llama", "alpaca", "camelid", "fiber", "breeding"]
    
    # Domain - coarse routing
    domain: "camelids"
```

**Node Routing Strategy:**

| Node Type | Has Embedder | Strategy |
|-----------|--------------|----------|
| Laptop/Server | ✅ | Full semantic (embeddings) |
| Phone/Tablet | ✅ | Full semantic (smaller model) |
| Edge Gateway | ❌ | SimHash + keywords |
| Tiny Sensor | ❌ | Keywords + domain only |
| Fallback | - | Ask peer to embed |

---

## The Deer Scenario: Complete Flow

A security camera sees movement. Here's how it flows through the mesh:

```
┌──────────────────────────────────────────────────────────────────┐
│                   EDGE SENSOR (Tiny Device)                       │
│                                                                   │
│  1. Motion detected → capture frame                              │
│  2. Local tiny classifier: "animal" (confidence: 0.6)            │
│  3. Can't identify species → escalate                            │
│                                                                   │
│  Creates Intent:                                                  │
│  {                                                                │
│    type: "vision/classify",                                       │
│    domain: "wildlife",                                            │
│    data: { image: <jpeg bytes> },                                │
│    preferences: { latency: "low", accuracy: "high" },            │
│    context: { camera: "backyard", time: "dusk" }                 │
│  }                                                                │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                   LOCAL ROUTING (On Sensor)                       │
│                                                                   │
│  1. Cache check: MISS                                            │
│  2. Keyword match: "vision/classify" + "wildlife"                │
│  3. Known peers with vision/classify:                            │
│     - rob-mac (latency: 12ms, has wildlife model)                │
│     - cloud-1 (latency: 120ms, general only)                     │
│  4. Select: rob-mac (domain match + low latency)                 │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                   ROB'S MAC (Capability Node)                     │
│                                                                   │
│  1. Receive intent + image                                        │
│  2. Load wildlife-yolo model (or use cached)                     │
│  3. Classify: "white-tailed deer" (confidence: 0.94)             │
│  4. Optional: Query wildlife-rag for behavior context            │
│  5. Return:                                                       │
│     {                                                             │
│       species: "white-tailed deer",                              │
│       confidence: 0.94,                                          │
│       behavior: "grazing",                                       │
│       context: "Common at dusk, likely feeding"                  │
│     }                                                             │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                   EDGE SENSOR (Response)                          │
│                                                                   │
│  1. Receive classification result                                 │
│  2. Cache: "similar frames → deer" (TTL: 1 hour)                 │
│  3. Take action: Log event, maybe notify owner                   │
│  4. If deer seen repeatedly → trigger training                   │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                   LEARNING LOOP (Async)                           │
│                                                                   │
│  1. Collect: {image, label: "deer", confidence: 0.94}            │
│  2. After N samples: Train edge-optimized deer detector          │
│  3. Package model: deer-detector-v1 (2MB, runs on sensor)        │
│  4. Deploy via mesh gossip                                        │
│  5. Next time: Sensor classifies locally, no escalation          │
└──────────────────────────────────────────────────────────────────┘
```

---

## Agent Discovery & Execution

### Agent Registry

Agents are capabilities that can execute multi-step tasks:

```yaml
Agents:
  - id: "research-agent@rob-mac"
    type: agent/research
    triggers:
      - pattern: "research *"
        priority: high
      - pattern: "find out about *"
        priority: normal
      - pattern: "what is the latest on *"
        priority: normal
    capabilities:
      - web-search
      - summarize
      - rag-query
    constraints:
      max_steps: 10
      max_tokens: 50000
      timeout: 300s
    node: rob-mac
    
  - id: "monitor-agent@edge-1"
    type: agent/monitor
    triggers:
      - pattern: "watch for *"
      - pattern: "alert me when *"
    capabilities:
      - vision/detect
      - notify
    constraints:
      continuous: true
      alert_threshold: 0.8
    node: edge-sensor-1
```

### Agent Invocation

```
User: "Research the latest advances in llama breeding techniques"
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  INTENT PARSER                                                   │
│                                                                  │
│  Match: "research *" → research-agent@rob-mac                   │
│  Extract: topic = "latest advances in llama breeding techniques"│
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  AGENT EXECUTION (rob-mac)                                       │
│                                                                  │
│  Step 1: web-search("llama breeding 2025 2026")                 │
│  Step 2: summarize(search_results)                               │
│  Step 3: rag-query("llama-expert-14", "breeding advances")      │
│  Step 4: synthesize(web_summary, rag_context)                   │
│  Step 5: return final_summary                                    │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  RESPONSE                                                        │
│                                                                  │
│  "Recent advances in llama breeding include..."                  │
│  (with citations from both web and RAG sources)                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tool Execution

### Tool Registry

Tools are atomic capabilities that perform specific actions:

```yaml
Tools:
  - id: "camera-front@edge-gateway"
    type: tool/camera
    device:
      id: front-door-cam
      location: front-door
      resolution: 1080p
    actions:
      - capture: Take a single frame
      - stream: Start video stream
      - night-mode: Toggle night vision
    node: edge-gateway
    
  - id: "door-lock@edge-gateway"
    type: tool/iot
    device:
      id: front-door-lock
      manufacturer: August
    actions:
      - lock: Lock the door
      - unlock: Unlock the door
      - status: Get lock status
    constraints:
      requires_auth: true
      auth_level: owner
    node: edge-gateway
```

### Tool Invocation Flow

```
User: "Take a photo of the front door"
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  INTENT PARSER                                                   │
│                                                                  │
│  Type: tool/camera                                               │
│  Action: capture                                                 │
│  Target: front-door                                              │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  ROUTER                                                          │
│                                                                  │
│  Lookup: tool/camera + front-door                               │
│  Match: camera-front@edge-gateway                               │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  EDGE GATEWAY                                                    │
│                                                                  │
│  POST /tools/camera/capture                                      │
│  { device: "front-door-cam" }                                   │
│                                                                  │
│  Response:                                                       │
│  { image: <base64>, timestamp: "2026-02-02T17:30:00Z" }         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Caching Strategy

### Multi-Level Cache

```python
class IntentCache:
    """
    Multi-level cache for routing decisions and results.
    
    L1: Exact match (same intent = same route)
    L2: Semantic match (similar intent = likely same route)
    L3: Result cache (same query = cached result)
    """
    
    def __init__(self):
        # L1: Route cache - exact intent hash
        self.route_cache = TTLCache(maxsize=100, ttl=60)
        
        # L2: Semantic route cache - SimHash
        self.semantic_cache = TTLCache(maxsize=1000, ttl=3600)
        
        # L3: Result cache - full responses
        self.result_cache = TTLCache(maxsize=500, ttl=3600)
    
    def get_route(self, intent: Intent) -> Optional[RouteResult]:
        # L1: Exact match
        l1_key = self._intent_hash(intent)
        if l1_key in self.route_cache:
            return self.route_cache[l1_key]
        
        # L2: Semantic match
        l2_key = self._simhash(intent)
        if l2_key in self.semantic_cache:
            return self.semantic_cache[l2_key]
        
        return None
    
    def get_result(self, intent: Intent) -> Optional[Any]:
        # Check if we have a cached result
        cache_key = intent.cache.key if intent.cache else None
        if cache_key and cache_key in self.result_cache:
            return self.result_cache[cache_key]
        return None
    
    def store(self, intent: Intent, route: RouteResult, result: Any = None):
        l1_key = self._intent_hash(intent)
        l2_key = self._simhash(intent)
        
        self.route_cache[l1_key] = route
        self.semantic_cache[l2_key] = route
        
        if result and intent.cache:
            ttl = intent.cache.ttl or 3600
            self.result_cache.set(intent.cache.key, result, ttl)
```

### Cache Invalidation

- **Route cache:** Invalidated when node capabilities change
- **Semantic cache:** Invalidated on significant capability updates
- **Result cache:** Respects TTL from intent, invalidated on data change

---

## Gossip Protocol Extensions

### New Message Types

```yaml
# Capability advertisement
CAPABILITY_UPDATE:
  type: capability_update
  node: rob-mac
  capabilities:
    - type: vision/classify
      models: [wildlife-yolo]
      representations:
        embedding: [...]
        simhash: "a7f3..."
        keywords: [wildlife, animal, deer]
  timestamp: 1234567890

# Agent registration
AGENT_REGISTER:
  type: agent_register
  agent:
    id: research-agent@rob-mac
    triggers: [...]
    capabilities: [...]
  node: rob-mac
  timestamp: 1234567890

# Tool availability
TOOL_AVAILABLE:
  type: tool_available
  tool:
    id: camera-front@edge-gateway
    type: tool/camera
    actions: [capture, stream]
  node: edge-gateway
  timestamp: 1234567890

# Model deployment
MODEL_DEPLOYED:
  type: model_deployed
  model:
    name: deer-detector-v1
    type: vision/classify
    size_bytes: 2000000
  node: edge-sensor-1
  source_node: rob-mac
  timestamp: 1234567890
```

---

## Implementation Phases

### Phase 1: Multi-Capability Routing ✅
- [x] Typed intent schema
- [x] Capability type registry
- [ ] Multi-tier routing (cache → keyword → semantic)

### Phase 2: Distributed Embeddings
- [ ] SimHash generation for capabilities
- [ ] Multi-representation gossip
- [ ] Embedding-free routing for edge devices

### Phase 3: Agent Framework
- [ ] Agent registry
- [ ] Trigger pattern matching
- [ ] Multi-step execution engine

### Phase 4: Tool Execution
- [ ] Tool registry
- [ ] Action dispatch
- [ ] Auth/permission model

### Phase 5: Learning Loop
- [ ] Sample collection
- [ ] Edge model training
- [ ] Mesh-wide deployment

---

## API Endpoints

### Intent Submission

```
POST /v1/intent
{
  "type": "vision/classify",
  "domain": "wildlife",
  "data": { "image": "<base64>" },
  "preferences": { "latency": "low" }
}

Response:
{
  "id": "int-abc123",
  "status": "completed",
  "result": {
    "species": "deer",
    "confidence": 0.94
  },
  "routed_to": "rob-mac",
  "latency_ms": 45
}
```

### Capability Discovery

```
GET /v1/capabilities
GET /v1/capabilities?type=vision/classify
GET /v1/capabilities?domain=wildlife

Response:
{
  "capabilities": [
    {
      "type": "vision/classify",
      "node": "rob-mac",
      "models": ["wildlife-yolo"],
      "domain": "wildlife",
      "latency_ms": 12
    }
  ]
}
```

### Agent Invocation

```
POST /v1/agent/invoke
{
  "query": "Research the latest on llama breeding",
  "agent": "research-agent"  // Optional, auto-matched if omitted
}

Response:
{
  "id": "agent-run-xyz",
  "status": "completed",
  "result": "Recent advances include...",
  "steps": [
    { "tool": "web-search", "duration_ms": 1200 },
    { "tool": "summarize", "duration_ms": 800 },
    { "tool": "rag-query", "duration_ms": 200 }
  ]
}
```

### Tool Execution

```
POST /v1/tool/execute
{
  "tool": "camera-front@edge-gateway",
  "action": "capture"
}

Response:
{
  "id": "tool-exec-123",
  "status": "completed",
  "result": {
    "image": "<base64>",
    "timestamp": "2026-02-02T17:30:00Z"
  }
}
```

---

## Summary

Atmosphere v2 is a **capability mesh** that:

1. **Routes typed intents** — not just text, but images, audio, tool calls, agent tasks
2. **Discovers capabilities** — LLMs, vision, audio, agents, tools, ML models
3. **Works everywhere** — full embeddings on laptops, SimHash on edge, keywords on tiny devices
4. **Learns and adapts** — escalate → train → deploy → handle locally
5. **Caches aggressively** — sub-millisecond routing for repeated patterns

**The vision:** Any device can express any intent, and the mesh finds the best way to fulfill it.
