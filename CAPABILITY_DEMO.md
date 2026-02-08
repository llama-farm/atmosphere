# Atmosphere Capability Discovery Demo

## Live Capability Discovery from LlamaFarm

### Command
```bash
python3 -c "
import asyncio
import json
from atmosphere.integration.llamafarm import discover_llamafarm_capabilities

async def demo():
    caps = await discover_llamafarm_capabilities('demo-node', 'Demo Node')
    for cap in caps:
        print(json.dumps(cap.to_dict(), indent=2, default=str))
        
asyncio.run(demo())
"
```

### Output (Current System)

```json
{
  "node_id": "demo-node",
  "node_name": "Demo Node",
  "capability_id": "demo-node:llamafarm/discoverable/llama-expert-14:default",
  "project_path": "llamafarm/discoverable/llama-expert-14",
  "model_alias": "default",
  "model_actual": "unsloth/Qwen3-1.7B-GGUF:Q4_K_M",
  "model_family": "qwen3",
  "model_params_b": 1.7,
  "model_quantization": "Q4_K_M",
  "model_tier": "tiny",
  "capability_type": "llm/chat",
  "triggers": [],
  "tools": [],
  "label": "llama-expert-14 (default)",
  "description": "",
  "embedding": null,
  "embedding_hash": 0,
  "keywords": [],
  "good_for": [
    "simple_qa",
    "classification",
    "extraction"
  ],
  "not_good_for": [
    "reasoning",
    "agents",
    "code_complex",
    "analysis"
  ],
  "has_rag": true,
  "has_vision": false,
  "has_tools": false,
  "has_streaming": true,
  "context_length": 4096,
  "specializations": [],
  "cost_factors": null,
  "estimated_latency_ms": 100.0,
  "tokens_per_second": 50.0,
  "api_cost_per_1k_tokens": 0.0,
  "hops": 0,
  "via_node": null,
  "ttl": 10,
  "timestamp": 1770407086.784492,
  "expires_at": 1770407386.784492,
  "signature": ""
}
```

## API Endpoint Examples

### GET /capabilities
**Simplified view for UI/listing**

```bash
curl http://localhost:14321/capabilities
```

```json
[
  {
    "id": "demo-node:llamafarm/discoverable/llama-expert-14:default",
    "label": "llama-expert-14 (default)",
    "description": "",
    "handler": "llamafarm",
    "models": ["unsloth/Qwen3-1.7B-GGUF:Q4_K_M"],
    "keywords": [],
    "source": "llamafarm"
  }
]
```

### GET /mesh/capabilities
**Full routing metadata for mesh decisions**

```bash
curl http://localhost:14321/mesh/capabilities
```

```json
[
  {
    "capability_id": "demo-node:llamafarm/discoverable/llama-expert-14:default",
    "node_id": "demo-node",
    "node_name": "Demo Node",
    "project_path": "llamafarm/discoverable/llama-expert-14",
    "model_actual": "unsloth/Qwen3-1.7B-GGUF:Q4_K_M",
    "model_family": "qwen3",
    "model_tier": "tiny",
    "label": "llama-expert-14 (default)",
    "description": "",
    "keywords": [],
    "good_for": ["simple_qa", "classification", "extraction"],
    "not_good_for": ["reasoning", "agents", "code_complex", "analysis"],
    "has_rag": true,
    "specializations": [],
    "estimated_latency_ms": 100.0,
    "hops": 0
  }
]
```

### POST /route
**Route a query to best capability**

```bash
curl -X POST http://localhost:14321/route \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "What do llamas eat?"
  }'
```

```json
{
  "action": "process_local",
  "capability": "llama-expert-14",
  "score": 0.85,
  "hops": 0,
  "next_hop": null,
  "node_id": "demo-node"
}
```

## Key Features Demonstrated

### 1. Model Metadata Extraction
- **Actual model name**: `unsloth/Qwen3-1.7B-GGUF:Q4_K_M`
- **Family**: `qwen3` (extracted from name)
- **Size**: `1.7B` parameters
- **Quantization**: `Q4_K_M` (extracted from suffix)
- **Tier**: `tiny` (auto-classified from param count)

### 2. Capability Classification
Based on model tier, auto-assigns:
- **Good for**: Simple QA, classification, extraction (appropriate for 1.7B model)
- **Not good for**: Reasoning, agents, complex code (too small for these tasks)

### 3. Project Context
- **Has RAG**: `true` (detected from project config)
- **Context length**: `4096` tokens
- **Streaming**: Enabled

### 4. Cost Awareness
- **API cost**: `0.0` (local model = free)
- **Estimated latency**: `100ms`
- **Tokens/sec**: `50` (estimated throughput)

### 5. Routing Metadata
- **Hops**: `0` (local capability)
- **Via node**: `null` (direct access)
- **TTL**: `10` (gossip time-to-live)
- **Expires**: 5 minutes from timestamp

## Routing Decision Logic

When a query comes in like "What do llamas eat?":

1. **Intent Classification** (future): Classifies as `simple_qa`, `domain: animals`
2. **Capability Matching**: Finds `llama-expert-14` because:
   - Keywords match (once we add llama-related keywords to project)
   - Good for: `simple_qa` ✓
   - Has RAG: `true` (can look up llama facts) ✓
3. **Scoring**: 
   - Semantic match: 0.85
   - Latency: 100ms → score 0.9
   - Cost: $0 → score 1.0
   - Composite: 0.85 * 0.4 + 0.9 * 0.25 + 1.0 * 0.05 = 0.62
4. **Route**: Local execution → answer immediately

## Next Steps

To see this in action across a real mesh:
1. Start Atmosphere on Mac
2. Start Atmosphere on Phone
3. Query from Phone: "What do llamas eat?"
4. Watch it route to Mac's llama-expert project
5. Get answer with RAG-enhanced context

---

**Status**: Core integration complete. Ready for mesh testing.
