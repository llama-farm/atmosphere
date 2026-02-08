# Semantic Router v2: Intelligence Routing for Edge Mesh Networks

## Executive Summary

The Semantic Router is Atmosphere's **crown jewel** - it's not just about moving data, it's about moving **intelligence** to where it's needed. This proposal outlines a three-layer routing architecture that:

1. **Classifies intent locally** (~1ms) - No network round-trip for classification
2. **Matches capabilities from gossip cache** (~5ms) - Uses continuously-updated mesh state
3. **Routes to optimal node + model** - Right-sized intelligence for each request

**Core Principle**: A simple question shouldn't wake up a 70B model. A complex reasoning task shouldn't be handled by a tiny model. The router must understand the **cognitive load** of each request.

---

## The Problem

Current routing is naive:
- Every request goes to the same model
- No understanding of request complexity
- No consideration of model specialization
- No load balancing across mesh
- No cost optimization (small model = faster + cheaper)

**What we need:**
```
"What's 2+2?"           → tiny model, any node, <100ms
"Explain quantum physics" → large model, Mac node, ~2s
"Book me a flight"       → agent-capable, tools required
"Summarize this PDF"     → RAG-capable, document processing
```

---

## Architecture: Three Layers

```
┌─────────────────────────────────────────────────────────────┐
│                     REQUESTING NODE                          │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │   Layer 1   │→ │   Layer 2    │→ │      Layer 3        │ │
│  │  Classify   │  │    Match     │  │       Route         │ │
│  │   Intent    │  │ Capabilities │  │  Select Best Node   │ │
│  │   (~1ms)    │  │   (~5ms)     │  │      (~1ms)         │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
│         ↑                 ↑                    ↓             │
│    Local Rules      Gossip Cache         Execute Request     │
│    + Tiny Model     (mesh state)         to Selected Node    │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Intent Classification (On-Device)

**Goal**: Understand what the user is asking for BEFORE hitting the network.

### Classification Dimensions

```kotlin
data class IntentClassification(
    // Complexity (determines model size needed)
    val complexity: Complexity,  // TRIVIAL, SIMPLE, MODERATE, COMPLEX, EXPERT
    
    // Task type (determines capabilities needed)
    val taskType: TaskType,      // QA, CHAT, REASONING, RESEARCH, AGENTIC, CODE, CREATIVE
    
    // Domain (determines model specialization)
    val domain: Domain?,         // MEDICAL, LEGAL, TECHNICAL, FINANCIAL, GENERAL
    
    // Requirements
    val needsTools: Boolean,     // Requires function calling
    val needsRAG: Boolean,       // Requires document retrieval
    val needsVision: Boolean,    // Has image input
    val needsCode: Boolean,      // Code generation/execution
    
    // Expected characteristics
    val expectedLength: Length,  // SHORT, MEDIUM, LONG, UNLIMITED
    val confidenceScore: Float   // How confident are we in this classification
)
```

### Complexity Detection Rules

```
TRIVIAL (→ 0.5B-1B model):
  - Math: "2+2", "sqrt(16)"
  - Greetings: "hi", "hello"
  - Simple facts: "What color is the sky?"
  - Pattern: <10 words, no reasoning required

SIMPLE (→ 1B-3B model):
  - Single-step questions
  - Basic knowledge recall
  - Simple transformations
  - Pattern: Single concept, direct answer expected

MODERATE (→ 3B-7B model):
  - Multi-step reasoning
  - Explanations required
  - Comparisons
  - Pattern: "explain", "compare", "how does X work"

COMPLEX (→ 7B-14B model):
  - Analysis tasks
  - Creative writing
  - Code generation
  - Pattern: Multiple concepts, synthesis required

EXPERT (→ 14B+ model or agent):
  - Research tasks
  - Multi-document analysis
  - Complex agentic workflows
  - Pattern: "analyze", "research", "create a plan for"
```

### Implementation: Hybrid Classifier

```python
class IntentClassifier:
    """
    Hybrid approach:
    1. Fast rule-based pre-filter (regex, keywords)
    2. Tiny embedding model for semantic matching
    3. Confidence-weighted combination
    """
    
    def __init__(self):
        # Rule-based patterns (instant, ~0.1ms)
        self.trivial_patterns = [
            r'^\d+\s*[\+\-\*\/]\s*\d+',  # Math
            r'^(hi|hello|hey)\b',         # Greetings
            r'^what (is|are) \d+',        # Simple math
        ]
        
        # Keyword indicators
        self.complexity_keywords = {
            'trivial': ['hi', 'hello', 'what is'],
            'simple': ['who', 'when', 'where'],
            'moderate': ['explain', 'describe', 'how'],
            'complex': ['analyze', 'compare', 'design'],
            'expert': ['research', 'investigate', 'create a plan']
        }
        
        self.tool_keywords = ['book', 'schedule', 'send', 'search', 'find']
        self.rag_keywords = ['document', 'pdf', 'file', 'article', 'paper']
        
        # Tiny embedding model for semantic matching (optional, ~1ms)
        self.embedder = None  # Load lazily if needed
    
    def classify(self, message: str) -> IntentClassification:
        """Classify intent in <2ms."""
        
        # Phase 1: Rule-based (instant)
        for pattern in self.trivial_patterns:
            if re.match(pattern, message.lower()):
                return IntentClassification(
                    complexity=Complexity.TRIVIAL,
                    taskType=TaskType.QA,
                    confidenceScore=0.95
                )
        
        # Phase 2: Keyword analysis (~0.5ms)
        words = set(message.lower().split())
        complexity = self._detect_complexity(words)
        task_type = self._detect_task_type(words)
        needs_tools = bool(words & set(self.tool_keywords))
        needs_rag = bool(words & set(self.rag_keywords))
        
        # Phase 3: Semantic embedding (only if uncertain, ~1ms)
        if complexity == Complexity.MODERATE:
            # Use embeddings to refine
            complexity = self._semantic_refine(message, complexity)
        
        return IntentClassification(
            complexity=complexity,
            taskType=task_type,
            needsTools=needs_tools,
            needsRAG=needs_rag,
            confidenceScore=0.8
        )
```

---

## Layer 2: Capability Matching (Gossip-Powered)

**Goal**: Find nodes that CAN handle this request.

### Gossip Protocol: What Nodes Advertise

```kotlin
data class NodeCapabilities(
    val nodeId: String,
    val nodeName: String,
    val meshId: String,
    
    // Model inventory
    val models: List<ModelInfo>,
    
    // Capability flags
    val supportsTools: Boolean,
    val supportsRAG: Boolean,
    val supportsVision: Boolean,
    val supportsStreaming: Boolean,
    
    // Performance metrics (rolling average)
    val avgLatencyMs: Float,
    val currentLoad: Float,        // 0.0 - 1.0
    val availableMemoryMb: Int,
    
    // Network info
    val directEndpoint: String?,   // Local network address
    val relayEndpoint: String?,    // Relay URL
    val lastSeen: Long,            // Timestamp
    
    // Specializations
    val domains: List<String>,     // "medical", "legal", etc.
)

data class ModelInfo(
    val name: String,              // "llama-expert-14", "qwen3:1.7B"
    val provider: String,          // "llamafarm", "ollama"
    val sizeClass: SizeClass,      // TINY, SMALL, MEDIUM, LARGE, XLARGE
    val parameterCount: Long?,     // 1.7B, 7B, etc.
    val contextLength: Int,        // 4096, 8192, etc.
    val specialization: String?,   // "code", "medical", "chat"
    val costPerToken: Float,       // Relative cost metric
)

enum class SizeClass {
    TINY,    // <1B params
    SMALL,   // 1-3B params
    MEDIUM,  // 3-7B params
    LARGE,   // 7-14B params
    XLARGE   // 14B+ params
}
```

### Capability Matching Logic

```python
def match_capabilities(
    intent: IntentClassification,
    mesh_state: Dict[str, NodeCapabilities]
) -> List[NodeMatch]:
    """
    Find all nodes that can handle this intent.
    Returns sorted list of viable nodes.
    """
    matches = []
    
    for node_id, caps in mesh_state.items():
        # Filter: Must have required capabilities
        if intent.needsTools and not caps.supportsTools:
            continue
        if intent.needsRAG and not caps.supportsRAG:
            continue
        if intent.needsVision and not caps.supportsVision:
            continue
        
        # Filter: Must have appropriately-sized model
        required_size = complexity_to_size(intent.complexity)
        viable_models = [
            m for m in caps.models 
            if m.sizeClass >= required_size
        ]
        if not viable_models:
            continue
        
        # Filter: Check domain specialization (boost, not filter)
        domain_boost = 1.0
        if intent.domain and intent.domain in caps.domains:
            domain_boost = 1.5
        
        # Calculate fitness score
        best_model = select_best_model(viable_models, intent)
        fitness = calculate_fitness(caps, best_model, intent, domain_boost)
        
        matches.append(NodeMatch(
            nodeId=node_id,
            model=best_model,
            fitness=fitness,
            latencyEstimate=caps.avgLatencyMs,
            endpoint=caps.directEndpoint or caps.relayEndpoint
        ))
    
    return sorted(matches, key=lambda m: m.fitness, reverse=True)
```

---

## Layer 3: Optimal Routing (Cost-Aware Selection)

**Goal**: Pick the BEST node from viable candidates.

### Routing Score Formula

```python
def calculate_routing_score(match: NodeMatch, context: RoutingContext) -> float:
    """
    Multi-factor scoring for route selection.
    Higher = better.
    """
    score = 0.0
    
    # 1. Model fitness (40% weight)
    # Prefer right-sized model - not too big, not too small
    model_fit = model_fitness_score(match.model, context.intent)
    score += 0.40 * model_fit
    
    # 2. Latency (30% weight)  
    # Prefer local network over relay
    if match.isLocalNetwork:
        latency_score = 1.0
    elif match.latencyEstimate < 100:
        latency_score = 0.8
    elif match.latencyEstimate < 500:
        latency_score = 0.5
    else:
        latency_score = 0.2
    score += 0.30 * latency_score
    
    # 3. Load balancing (20% weight)
    # Prefer less-loaded nodes
    load_score = 1.0 - match.currentLoad
    score += 0.20 * load_score
    
    # 4. Specialization bonus (10% weight)
    # Boost for domain-specialized models
    if match.domainMatch:
        score += 0.10
    
    return score


def model_fitness_score(model: ModelInfo, intent: IntentClassification) -> float:
    """
    Score how well a model fits the intent.
    Penalize both over-sized and under-sized models.
    """
    required = complexity_to_size(intent.complexity)
    actual = model.sizeClass
    
    if actual == required:
        return 1.0  # Perfect fit
    elif actual == required + 1:
        return 0.8  # Slightly over-provisioned (ok)
    elif actual == required - 1:
        return 0.6  # Slightly under-provisioned (risky)
    elif actual > required:
        return 0.5  # Over-provisioned (wasteful)
    else:
        return 0.2  # Under-provisioned (likely to fail)
```

---

## Gossip Protocol: Continuous Updates

### What Gets Gossiped

```
Every 30 seconds (configurable):
├── Node heartbeat
│   ├── nodeId, meshId
│   ├── currentLoad (0.0-1.0)
│   ├── availableMemory
│   └── lastLatencyStats
│
Every 5 minutes (or on change):
├── Capability update
│   ├── Full model inventory
│   ├── Capability flags
│   └── Specialization domains
│
On-demand (query):
└── Full node profile request
```

### Gossip Message Types

```kotlin
sealed class GossipMessage {
    data class Heartbeat(
        val nodeId: String,
        val load: Float,
        val memory: Int,
        val latency: Float
    ) : GossipMessage()
    
    data class CapabilityUpdate(
        val nodeId: String,
        val capabilities: NodeCapabilities
    ) : GossipMessage()
    
    data class CostVector(
        val nodeId: String,
        val capabilities: Map<String, Float>  // capability -> cost
    ) : GossipMessage()
}
```

### Local Cache Management

```kotlin
class MeshStateCache {
    private val nodes = ConcurrentHashMap<String, NodeCapabilities>()
    private val lastUpdate = ConcurrentHashMap<String, Long>()
    
    // Configurable staleness threshold
    val staleThresholdMs = 60_000L  // 1 minute
    
    fun getViableNodes(intent: IntentClassification): List<NodeCapabilities> {
        val now = System.currentTimeMillis()
        return nodes.values.filter { node ->
            // Not stale
            (now - (lastUpdate[node.nodeId] ?: 0)) < staleThresholdMs &&
            // Matches requirements
            matchesIntent(node, intent)
        }
    }
    
    fun onGossipReceived(message: GossipMessage) {
        when (message) {
            is GossipMessage.Heartbeat -> {
                nodes[message.nodeId]?.let { existing ->
                    nodes[message.nodeId] = existing.copy(
                        currentLoad = message.load,
                        availableMemoryMb = message.memory
                    )
                }
                lastUpdate[message.nodeId] = System.currentTimeMillis()
            }
            is GossipMessage.CapabilityUpdate -> {
                nodes[message.nodeId] = message.capabilities
                lastUpdate[message.nodeId] = System.currentTimeMillis()
            }
        }
    }
}
```

---

## LlamaFarm Integration

### Project Metadata → Router Intelligence

LlamaFarm projects already contain rich metadata:

```yaml
# llamafarm.yaml
name: llama-expert-14
namespace: discoverable
description: "Expert on llamas and alpacas"
domain: agriculture
topics: [llama, alpaca, camelid, fiber]

runtime:
  models:
    - name: default
      provider: universal
      model: unsloth/Qwen3-1.7B-GGUF:Q4_K_M
      
prompts:
  - name: default
    content: |
      You are an expert on llamas...
```

**What the router extracts:**

```python
@dataclass
class ProjectRouterInfo:
    name: str                    # "llama-expert-14"
    namespace: str               # "discoverable"
    description: str             # For semantic matching
    domain: str                  # "agriculture"
    topics: List[str]            # ["llama", "alpaca"]
    model_size: SizeClass        # Inferred from model name
    has_system_prompt: bool      # True
    prompt_complexity: str       # "specialized" vs "general"
```

### Auto-Registration from LlamaFarm

```python
async def register_llamafarm_projects(router: SemanticRouter, llamafarm_url: str):
    """
    Pull projects from LlamaFarm and register as router capabilities.
    """
    projects = await fetch_discoverable_projects(llamafarm_url)
    
    for proj in projects:
        # Infer model size from model name
        model_size = infer_model_size(proj.runtime.model)
        
        # Build capability entry
        cap = Capability(
            id=f"llamafarm/{proj.namespace}/{proj.name}",
            name=proj.name,
            description=proj.description,
            nodeId=LOCAL_NODE_ID,
            type="llm",
            handler=f"llamafarm:{proj.namespace}/{proj.name}",
            keywords=proj.topics,
            cost=model_size_to_cost(model_size),
            metadata=json.dumps({
                "model": proj.runtime.model,
                "size_class": model_size.value,
                "domain": proj.domain,
                "has_tools": proj.has_tools,
            })
        )
        
        router.register_capability(cap)
```

---

## UI: The Crown Jewel Visibility

### What Users See

```
┌─────────────────────────────────────────────┐
│  🎯 Semantic Router                         │
├─────────────────────────────────────────────┤
│  Intent: "Explain quantum entanglement"     │
│                                             │
│  Classification:                            │
│  ├─ Complexity: COMPLEX (→ 7B+ model)       │
│  ├─ Task Type: REASONING                    │
│  ├─ Domain: PHYSICS                         │
│  └─ Confidence: 92%                         │
│                                             │
│  Route Selected:                            │
│  ├─ Node: rob-macbook (local)               │
│  ├─ Model: llama-expert-14 (Qwen3-1.7B)     │
│  ├─ Fitness Score: 87%                      │
│  └─ Expected Latency: ~150ms                │
│                                             │
│  Alternatives Considered:                   │
│  ├─ android-phone (relay): 72% fitness      │
│  └─ edge-device (offline): not viable       │
└─────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Intent Classification (This Week)
- [ ] Build rule-based classifier
- [ ] Add complexity detection keywords
- [ ] Integrate into Android SemanticRouter
- [ ] Show classification in UI

### Phase 2: Gossip-Powered Matching (Next Week)
- [ ] Define gossip message schema
- [ ] Implement local mesh state cache
- [ ] Broadcast capabilities on startup
- [ ] Handle capability updates

### Phase 3: Optimal Routing (Week 3)
- [ ] Implement routing score formula
- [ ] Add latency-aware selection
- [ ] Load balancing integration
- [ ] Model fitness scoring

### Phase 4: LlamaFarm Integration (Week 4)
- [ ] Auto-extract project metadata
- [ ] Map projects to capabilities
- [ ] Dynamic model size inference
- [ ] Domain specialization routing

---

## Success Metrics

1. **Classification Accuracy**: >90% correct complexity assessment
2. **Routing Latency**: <10ms total routing decision time
3. **Model Right-Sizing**: <20% over-provisioning rate
4. **User Visibility**: Every request shows routing decision
5. **Gossip Freshness**: Mesh state <30s stale

---

## Conclusion

The Semantic Router v2 transforms Atmosphere from a simple mesh relay into an **intelligent routing fabric**. It ensures:

- **Simple questions get fast answers** (tiny models, local nodes)
- **Complex questions get deep analysis** (large models, capable nodes)
- **Specialized questions reach specialists** (domain-tuned models)
- **The mesh stays balanced** (load-aware routing)
- **Users understand what's happening** (full visibility)

This is how we move **intelligence**, not just data.

---

*"The best router isn't the one that finds A path. It's the one that finds THE RIGHT path."*
