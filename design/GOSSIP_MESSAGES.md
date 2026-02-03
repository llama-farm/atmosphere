# Gossip Protocol Messages

> **Capability discovery and routing table propagation via epidemic gossip.**

---

## Overview

Atmosphere uses gossip protocol to propagate capability information across the mesh. This achieves:
- **O(log N) convergence** - All nodes see updates within ~20 gossip rounds for 1M nodes
- **No central registry** - Fully decentralized discovery
- **Partition tolerance** - Works even when the mesh is split

---

## Message Types

### CAPABILITY_AVAILABLE

Announces a new capability joining the mesh.

```yaml
type: CAPABILITY_AVAILABLE
sender_id: "rob-mac-001"
timestamp: 1770076800.123
capability:
  id: "front-door-camera"
  node_id: "home-server"
  type: "sensor/camera"
  tools:
    - name: "get_frame"
      description: "Capture current camera frame"
      parameters:
        resolution:
          type: string
          enum: [full, 720p, thumbnail]
      returns:
        type: image/jpeg
    - name: "get_history"
      description: "Get motion events"
      parameters:
        since: { type: duration, default: "1h" }
      returns:
        type: array
  triggers:
    - event: "motion_detected"
      description: "Motion detected in frame"
      intent_template: "motion detected at {location}"
      route_hint: "security/*"
      priority: "normal"
      throttle: "30s"
    - event: "person_detected"
      description: "Human detected"
      intent_template: "person detected at {location}"
      route_hint: "security/*"
      priority: "high"
      throttle: "10s"
  metadata:
    location: "front door"
    hardware: "Reolink RLC-810A"
  status: "online"
  version: "1.0.0"
```

**Propagation:** Exponential fanout with deduplication by capability_id + timestamp.

---

### CAPABILITY_HEARTBEAT

Periodic liveness signal for registered capabilities.

```yaml
type: CAPABILITY_HEARTBEAT
sender_id: "home-server"
timestamp: 1770076830.456
capability_ids:
  - "front-door-camera"
  - "backyard-camera"
  - "whisper-service"
status: "online"  # online | busy | degraded
load: 0.45        # 0.0 - 1.0
queue_depth: 3    # pending requests
```

**Frequency:** Every 30 seconds.  
**Timeout:** Capability marked stale after 90s (3 missed heartbeats).

---

### CAPABILITY_REMOVED

Graceful deregistration of a capability.

```yaml
type: CAPABILITY_REMOVED
sender_id: "home-server"
timestamp: 1770076900.789
capability_id: "front-door-camera"
reason: "shutdown"  # shutdown | maintenance | replaced | revoked
replacement_id: null  # optional: new capability taking over
```

---

### CAPABILITY_UPDATE

Updates capability metadata without full re-registration.

```yaml
type: CAPABILITY_UPDATE
sender_id: "home-server"
timestamp: 1770076950.123
capability_id: "front-door-camera"
changes:
  status: "busy"
  metadata:
    maintenance_mode: true
    estimated_return: "2026-02-02T20:00:00Z"
version: "1.0.1"  # bumped version
```

---

### TRIGGER_EVENT

A capability has fired a trigger (PUSH direction).

```yaml
type: TRIGGER_EVENT
sender_id: "home-server"
timestamp: 1770077000.456
source_capability_id: "front-door-camera"
event: "person_detected"
intent:
  type: "trigger/sensor/camera/person_detected"
  text: "person detected at front door"
  priority: "high"
payload:
  timestamp: 1770077000.123
  confidence: 0.94
  count: 1
  frame: "<base64-encoded-jpeg>"
  location: "front door"
route_hint: "security/*"
```

**Note:** Trigger events route to handlers, not broadcast to all nodes. The mesh router decides where to send based on route_hint or semantic matching.

---

### ROUTE_UPDATE

Updates routing table entries (gradient table sync).

```yaml
type: ROUTE_UPDATE
sender_id: "rob-mac-001"
timestamp: 1770077050.789
routes:
  - capability_type: "vision/detect"
    best_node: "jetson-01"
    hops: 2
    score: 0.91
    latency_ms: 12
  - capability_type: "llm/chat"
    best_node: "dell-gpu"
    hops: 1
    score: 0.96
    latency_ms: 45
  - capability_type: "audio/transcribe"
    best_node: "cloud-whisper"
    hops: 4
    score: 0.93
    latency_ms: 120
ttl: 300  # route validity in seconds
```

**Propagation:** Merged into local gradient table with distance-vector updates.

---

### MODEL_DEPLOYED

A model has been deployed to a node (for organic deployment).

```yaml
type: MODEL_DEPLOYED
sender_id: "dell-gpu"
timestamp: 1770077100.123
model:
  id: "wildlife-classifier-v3"
  path: "unsloth/wildlife-yolo:Q4_K_M"
  size_bytes: 2147483648
  quantization: "Q4_K_M"
capabilities_added:
  - type: "vision/classify"
    domain: "wildlife"
    accuracy: 0.94
node_id: "dell-gpu"
deployment_method: "pull"  # push | pull | gossip | organic
```

---

### NODE_JOIN

A new node joins the mesh.

```yaml
type: NODE_JOIN
sender_id: "new-node-001"
timestamp: 1770077150.456
node:
  id: "new-node-001"
  address: "192.168.1.50:11450"
  public_key: "<ed25519-public-key>"
  capabilities: []  # will send CAPABILITY_AVAILABLE separately
resources:
  memory_gb: 32
  gpu: "RTX 4090"
  cpu_cores: 16
seed_peers:
  - "rob-mac:11450"
  - "dell-gpu:11450"
```

---

### NODE_LEAVE

A node is leaving the mesh gracefully.

```yaml
type: NODE_LEAVE
sender_id: "old-node-001"
timestamp: 1770077200.789
node_id: "old-node-001"
reason: "shutdown"  # shutdown | maintenance | migration
migrate_to: null    # optional: node taking over workloads
capabilities_affected:
  - "camera-1"
  - "whisper-local"
```

---

### TOKEN_REVOKED

Revocation notice propagated via gossip.

```yaml
type: TOKEN_REVOKED
sender_id: "mesh-admin"
timestamp: 1770077250.123
revoked_token_id: "tok_abc123"
revoked_node_id: "compromised-node"
reason: "security_incident"
effective_immediately: true
```

**Security:** Signed by mesh admin key, verified by all nodes.

---

## Gossip Protocol Details

### Fanout

Each node forwards messages to **3 random peers** per gossip round.

```
Round 0: Node A has message
Round 1: A → B, C, D (3 nodes know)
Round 2: B,C,D each → 3 peers (up to 12 nodes know)
Round 3: up to 36 nodes know
...
Round k: O(3^k) nodes know → log₃(N) rounds to reach N nodes
```

### Deduplication

Messages are deduplicated by `(type, key, timestamp)`:
- CAPABILITY_AVAILABLE: key = capability_id
- CAPABILITY_HEARTBEAT: key = sender_id
- TRIGGER_EVENT: key = source_capability_id + event + timestamp
- ROUTE_UPDATE: key = sender_id
- MODEL_DEPLOYED: key = model_id + node_id

Messages with older timestamps are dropped.

### TTL

Messages have implicit TTL based on type:
- CAPABILITY_AVAILABLE: 5 minutes (until heartbeat confirms)
- CAPABILITY_HEARTBEAT: 90 seconds
- TRIGGER_EVENT: 30 seconds (route or drop)
- ROUTE_UPDATE: 5 minutes
- Others: 2 minutes

### Consistency

Gossip provides **eventual consistency**. For strong consistency requirements, use direct RPC to the capability node.

---

## Implementation

```python
from atmosphere.capabilities.registry import GossipMessage

# Create messages
msg = GossipMessage.available(capability, node_id)
msg = GossipMessage.heartbeat(capability_ids, node_id)
msg = GossipMessage.unavailable(capability_id, node_id, reason)

# Process incoming
await registry.process_gossip(message)
```

---

*Document Version: 1.0*  
*Date: 2026-02-02*
