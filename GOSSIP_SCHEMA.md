# Gossip Protocol Schema

## Overview

The Atmosphere gossip protocol enables capability discovery and distribution across the mesh network. Each node periodically broadcasts its capabilities, and peers update their gradient tables for intelligent routing.

## Message Format

### GossipMessage Schema

All gossip messages follow this JSON schema:

```json
{
  "type": "capability.announce" | "capability.request" | "capability.response",
  "node_id": "abc123...",
  "timestamp": 1234567890.123,
  "capabilities": [...],
  "ttl": 10,
  "signature": "..."
}
```

**Fields:**
- `type` (string, required): Message type
  - `capability.announce`: Broadcast of capabilities to all peers
  - `capability.request`: Request capabilities from specific node
  - `capability.response`: Response to capability request
- `node_id` (string, required): Source node's Ed25519 public key hash
- `timestamp` (float, required): Unix timestamp when message was created
- `capabilities` (array, optional): List of CapabilityAnnouncement objects
- `ttl` (int, default: 10): Time-to-live for forwarding
- `signature` (string, optional): Ed25519 signature of message

### CapabilityAnnouncement Schema

Each capability in the `capabilities` array follows this structure:

```json
{
  // === IDENTITY ===
  "node_id": "abc123...",
  "node_name": "MacBook Pro",
  "capability_id": "abc123:llamafarm/llama-expert:default",
  
  // === PROJECT ROUTING ===
  "project_path": "llamafarm/discoverable/llama-expert-14",
  "model_alias": "default",
  
  // === MODEL METADATA ===
  "model_actual": "unsloth/Qwen3-1.7B-GGUF:Q4_K_M",
  "model_family": "qwen3",
  "model_params_b": 1.7,
  "model_quantization": "Q4_K_M",
  "model_tier": "tiny",
  
  // === CAPABILITY TYPE ===
  "capability_type": "llm/chat",
  "triggers": [],
  "tools": [],
  
  // === SEMANTIC MATCHING ===
  "label": "Llama Expert",
  "description": "Expert on llamas and alpacas",
  "embedding": [0.1, 0.2, ...],  // 384-dim vector (optional)
  "embedding_hash": 3141592653,   // 32-bit SHA256 hash
  "keywords": ["llama", "alpaca", "camelid"],
  
  // === INTELLIGENCE PROFILE ===
  "good_for": ["simple_qa", "classification"],
  "not_good_for": ["reasoning", "agents"],
  "has_rag": false,
  "has_vision": false,
  "has_tools": false,
  "has_streaming": true,
  "context_length": 4096,
  "specializations": ["animal-care"],
  
  // === COST FACTORS ===
  "cost_factors": {...},
  "estimated_latency_ms": 50.0,
  "tokens_per_second": 50.0,
  "api_cost_per_1k_tokens": 0.0,
  
  // === ROUTING METADATA ===
  "hops": 0,
  "via_node": null,
  "ttl": 10,
  "timestamp": 1234567890.123,
  "expires_at": 1234568190.123,
  
  // === SECURITY ===
  "signature": "..."
}
```

## Embedding Hash Algorithm

The `embedding_hash` field provides a lightweight 32-bit identifier for fast capability matching on resource-constrained devices.

**Algorithm:**
1. Serialize embedding vector to stable JSON: `json.dumps(embedding, sort_keys=True)`
2. Encode to UTF-8 bytes
3. Compute SHA256 hash
4. Extract first 32 bits (4 bytes) as unsigned integer
5. Store as `embedding_hash`

**Example (Python):**
```python
import hashlib
import json

def compute_embedding_hash(embedding: List[float]) -> int:
    embedding_bytes = json.dumps(embedding, sort_keys=True).encode('utf-8')
    sha256_hash = hashlib.sha256(embedding_bytes).digest()
    hash_32bit = int.from_bytes(sha256_hash[:4], byteorder='big', signed=False)
    return hash_32bit
```

**Properties:**
- 32-bit unsigned integer (0 to 4,294,967,295)
- Deterministic: same embedding → same hash
- Fast to compute and compare
- No similarity preservation (exact match only)
- Collision probability: ~1 in 4 billion

## Message Flow

### 1. Capability Announcement (Broadcast)

When a node starts or discovers new capabilities:

```
Node A → Relay → All Peers
{
  "type": "capability.announce",
  "node_id": "node-a",
  "timestamp": 1234567890.123,
  "capabilities": [
    { /* CapabilityAnnouncement */ },
    { /* CapabilityAnnouncement */ }
  ],
  "ttl": 10,
  "signature": "..."
}
```

**Frequency:** Every 30 seconds (configurable)
**Expiry:** 5 minutes (capabilities must be re-announced)

### 2. Gradient Table Update

When receiving an announcement from `node_id` via `relay_connection`:

1. Parse GossipMessage
2. For each capability:
   - Skip if expired
   - Increment `hops` by 1
   - Set `via_node = node_id`
   - Convert to GradientEntry
   - Update gradient table (if better route)

**Better route logic:**
- New capability → add
- Existing capability with more hops → ignore
- Existing capability with same/fewer hops → update timestamp

### 3. Capability Request/Response (Future)

For direct capability queries:

```
Request:
{
  "type": "capability.request",
  "node_id": "node-b",
  "timestamp": 1234567890.123,
  "capabilities": [],  // Empty = request all
  "ttl": 1,
  "signature": "..."
}

Response:
{
  "type": "capability.response",
  "node_id": "node-a",
  "timestamp": 1234567890.124,
  "capabilities": [/* ... */],
  "ttl": 1,
  "signature": "..."
}
```

## Routing Integration

### Gradient Table Storage

Each capability announcement updates the gradient table:

```python
GradientEntry(
    capability_id="node-a:llamafarm/llama-expert:default",
    capability_label="Llama Expert",
    capability_vector=np.array([0.1, 0.2, ...]),  # From embedding
    hops=1,
    next_hop="node-a",
    via_node="relay",
    estimated_latency_ms=50.0,
    last_updated=time.time(),
    confidence=0.95  # 0.95^hops
)
```

### 3-Tier Matching Cascade

Router uses capabilities for semantic matching:

1. **Tier 1: Embedding Match** (if device has embeddings)
   - Compute cosine similarity between intent and capability embeddings
   - Best for semantic accuracy
   
2. **Tier 2: Hash Match** (fast, works everywhere)
   - Compare `embedding_hash` for exact matches
   - Good for known capabilities
   
3. **Tier 3: Keyword Match** (fallback)
   - Match keywords from intent to capability keywords
   - Always works, even with zero dependencies

## Security

### Signatures (Future Enhancement)

Each message can be signed with node's Ed25519 private key:

```python
signature = ed25519.sign(
    private_key,
    json.dumps({
        "type": msg.type,
        "node_id": msg.node_id,
        "timestamp": msg.timestamp,
        "capabilities": msg.capabilities
    }, sort_keys=True)
)
```

Peers verify signatures to prevent:
- Capability spoofing
- Malicious announcements
- Route poisoning

## Configuration

```python
# gossip.py constants
GOSSIP_MSG_ANNOUNCE = "capability.announce"
GOSSIP_MSG_REQUEST = "capability.request"
GOSSIP_MSG_RESPONSE = "capability.response"

GOSSIP_INTERVAL_SEC = 30   # Broadcast every 30 seconds
GOSSIP_EXPIRY_SEC = 300    # Capabilities expire after 5 minutes
```

## Usage Example

### Broadcasting Capabilities

```python
from atmosphere.core.gossip import GossipManager
from atmosphere.core.capability import CapabilityAnnouncement
from atmosphere.router.gradient import GradientTable

# Initialize
gradient_table = GradientTable(node_id="node-a")
gossip = GossipManager(
    node_id="node-a",
    gradient_table=gradient_table,
    send_to_relay=relay.send_message
)

# Add local capability
capability = CapabilityAnnouncement(
    node_id="node-a",
    node_name="MacBook Pro",
    capability_id="node-a:llamafarm/llama-expert:default",
    project_path="llamafarm/discoverable/llama-expert",
    model_alias="default",
    model_actual="unsloth/Qwen3-1.7B-GGUF:Q4_K_M",
    # ... other fields
)

gossip.add_local_capability(capability)

# Start periodic broadcasts
await gossip.start()

# Later: handle announcement from peer
await gossip.handle_announcement(
    node_id="node-b",
    announcement={
        "type": "capability.announce",
        # ... message content
    }
)

# Query all known capabilities
all_caps = gossip.get_all_capabilities()
print(f"Known capabilities: {len(all_caps)}")

# Stop
await gossip.stop()
```

### Receiving Announcements

```python
# When relay receives a message
async def on_relay_message(message: dict):
    if message.get("type") == "mesh.broadcast":
        payload = message.get("payload", {})
        if payload.get("type") == "capability.announce":
            await gossip.handle_announcement(
                node_id=payload["node_id"],
                announcement=payload
            )
```

## Files Created

1. **atmosphere/core/capability.py**
   - `CapabilityAnnouncement` dataclass with all fields
   - Embedding hash computation (32-bit SHA256)
   - Model tier detection
   - LlamaFarm project integration

2. **atmosphere/core/gossip.py**
   - `GossipManager` class
   - `GossipMessage` dataclass
   - Broadcast/receive/update logic
   - Periodic gossip loop
   - Gradient table integration

3. **RESET_PLAN.md** (updated)
   - Phase 2 checkboxes marked complete

## Next Steps (Phase 3)

- [ ] Implement 3-tier cascade router in `atmosphere/router/semantic.py`
- [ ] Add composite scoring in `atmosphere/router/scorer.py`
- [ ] Implement constraint filtering in `atmosphere/router/constraints.py`
- [ ] Wire up gossip to relay connection
- [ ] Test Mac → Phone routing

---

**Phase 2 Complete!** ✅

The gossip protocol is now ready to distribute capabilities across the mesh and enable intelligent semantic routing.
