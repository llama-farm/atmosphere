# Model Deployment System

> Organic distribution of trained models across the Atmosphere mesh

## Overview

The Model Deployment System enables trained ML models (anomaly detectors, classifiers, etc.) to be automatically distributed across mesh nodes. This is the key to the "edge learning loop" where:

1. Edge node sees anomaly it can't classify
2. Escalates to cloud/central for analysis
3. Central trains new detector
4. **New detector deploys back to edge nodes automatically**

## Model Package Format

```yaml
# model-manifest.yaml
name: network-anomaly-detector
version: 1.0.0
type: anomaly_detector  # anomaly_detector | classifier | embedder | router

trained_on: 2026-02-02T15:30:00Z
training_data_domain: network-traffic
training_node: central-01  # Where it was trained

# Model file info
file: model.joblib  # or .onnx, .safetensors, .pkl
format: sklearn     # sklearn | pytorch | onnx | tensorflow | mlx
size_bytes: 12345678
checksum_sha256: abc123...

# Python requirements
requirements:
  - scikit-learn>=1.0
  - numpy>=1.20
  - joblib>=1.0

# What this model can do
capabilities:
  - anomaly_detection
  - network_monitoring
  
# Model-specific config
config:
  contamination: 0.1
  threshold: -0.5
  feature_columns:
    - bytes_in
    - bytes_out
    - latency_ms

# Node requirements to run this model
node_requirements:
  min_memory_mb: 512
  min_cpu_cores: 1
  gpu_required: false
  architectures:
    - x86_64
    - arm64

# Deployment metadata
deployment:
  priority: normal  # critical | high | normal | low
  replicas: 0       # 0 = deploy everywhere capable
  regions: []       # Empty = all regions
  roles:            # Node roles that should have this
    - edge
    - gateway
```

## Deployment Strategies

### 1. Push (Admin-Initiated)
Admin explicitly pushes a model to specific nodes.

```bash
atmosphere model push network-detector node-abc
atmosphere model push network-detector --role edge  # All edge nodes
```

**Flow:**
```
Admin → Registry → Target Node(s)
         ↓
    Validate requirements
         ↓
    Transfer model file
         ↓
    Verify checksum
         ↓
    Load & confirm
```

### 2. Pull (Node-Initiated)
Node requests models matching its capabilities/role.

```bash
atmosphere model pull network-detector
atmosphere model pull --capabilities anomaly_detection
```

**Flow:**
```
Node → Query Registry → Find best source peer
                ↓
         Request transfer
                ↓
         Receive & verify
                ↓
         Register locally
```

### 3. Gossip (Peer Discovery)
Nodes advertise available models via gossip protocol.

**Messages:**
- `MODEL_AVAILABLE` - "I have model X version Y"
- `MODEL_REQUEST` - "I need model matching criteria Z"
- `MODEL_OFFER` - "I can send you model X"

**Flow:**
```
Node A gossips: MODEL_AVAILABLE(detector-v3)
        ↓
Node B hears, needs anomaly detection
        ↓
Node B: MODEL_REQUEST(capabilities=[anomaly])
        ↓
Node A: MODEL_OFFER(detector-v3, size=1MB)
        ↓
Node B accepts → Direct transfer A→B
```

### 4. Organic (Auto-Deployment)
New nodes automatically receive relevant models based on their role.

**When a new node joins:**
1. Node announces: capabilities, memory, GPU, role
2. Mesh identifies relevant models for that role
3. Nearest peer with models initiates transfer
4. Node confirms receipt and loads models

**Example:**
```
New edge node joins
        ↓
Mesh sees: role=edge, memory=4GB, no-GPU
        ↓
Identifies: anomaly-detector-v3, traffic-classifier-v2
        ↓
Gateway-01 (nearest with models) initiates push
        ↓
Edge node loads models, joins detection mesh
```

## Protocol Messages

### MODEL_AVAILABLE (Gossip)
```json
{
  "type": "model_available",
  "from_node": "gateway-01",
  "model": {
    "name": "network-anomaly-detector",
    "version": "1.0.0",
    "type": "anomaly_detector",
    "size_bytes": 12345678,
    "checksum": "sha256:abc123...",
    "capabilities": ["anomaly_detection"]
  },
  "timestamp": 1706886600,
  "ttl": 5
}
```

### MODEL_REQUEST (Direct/Gossip)
```json
{
  "type": "model_request",
  "from_node": "edge-05",
  "criteria": {
    "name": "network-anomaly-detector",
    "version": ">=1.0.0",
    "capabilities": ["anomaly_detection"],
    "max_size_bytes": 50000000
  },
  "urgency": "normal"
}
```

### MODEL_OFFER (Direct)
```json
{
  "type": "model_offer",
  "from_node": "gateway-01",
  "to_node": "edge-05",
  "model": {
    "name": "network-anomaly-detector",
    "version": "1.0.0"
  },
  "transfer_options": {
    "direct_tcp": "192.168.1.10:8765",
    "relay": "relay.atmosphere.local:8766"
  }
}
```

### MODEL_TRANSFER (Direct Stream)
```json
{
  "type": "model_transfer",
  "model_name": "network-anomaly-detector",
  "version": "1.0.0",
  "chunk_index": 0,
  "total_chunks": 10,
  "data_base64": "...",
  "checksum_chunk": "sha256:..."
}
```

## Node Capabilities for Model Selection

Nodes advertise their capabilities for model matching:

```yaml
node_capabilities:
  node_id: edge-05
  role: edge
  hardware:
    memory_mb: 4096
    cpu_cores: 4
    gpu: null
    architecture: arm64
  software:
    python_version: "3.11"
    installed_packages:
      - scikit-learn==1.4.0
      - numpy==1.26.0
      - torch==2.1.0
  interests:
    - anomaly_detection
    - network_monitoring
  constraints:
    max_model_size_mb: 100
    max_models: 10
```

## Model Registry

### Local Registry (per-node)
Stored at `~/.atmosphere/models/registry.yaml`:

```yaml
models:
  network-anomaly-detector:
    version: 1.0.0
    path: ~/.atmosphere/models/network-anomaly-detector-1.0.0.joblib
    loaded: true
    loaded_at: 2026-02-02T16:00:00Z
    source_node: gateway-01
    checksum: sha256:abc123...
    
  traffic-classifier:
    version: 2.1.0
    path: ~/.atmosphere/models/traffic-classifier-2.1.0.onnx
    loaded: false
    source_node: central-01
    checksum: sha256:def456...
```

### Mesh Registry (distributed)
Each node maintains knowledge of models across the mesh via gossip:

```yaml
mesh_models:
  network-anomaly-detector:
    versions:
      "1.0.0":
        nodes: [gateway-01, edge-01, edge-02]
        first_seen: 2026-02-01T00:00:00Z
      "0.9.0":
        nodes: [edge-03]
        deprecated: true
```

## Auto-Deployment Rules

Define rules for automatic model deployment:

```yaml
# ~/.atmosphere/config/deployment_rules.yaml
rules:
  - name: edge-anomaly-detectors
    trigger: node_join
    conditions:
      role: edge
      min_memory_mb: 512
    models:
      - name: network-anomaly-detector
        version: latest
      - name: traffic-classifier
        version: ">=2.0.0"
    
  - name: gateway-full-suite
    trigger: node_join
    conditions:
      role: gateway
    models:
      - name: "*"  # All available models
```

## CLI Commands

```bash
# List models
atmosphere model list                      # Local models
atmosphere model list --mesh               # All models in mesh
atmosphere model list --available          # Models I don't have

# Model info
atmosphere model info <name>               # Details about a model
atmosphere model info <name> --versions    # All versions
atmosphere model info <name> --nodes       # Which nodes have it

# Push/Pull
atmosphere model push <name> <node>        # Push to specific node
atmosphere model push <name> --role edge   # Push to all edge nodes
atmosphere model push <name> --all         # Push to all capable nodes
atmosphere model pull <name>               # Pull from mesh
atmosphere model pull --capabilities anom  # Pull by capability

# Deployment
atmosphere model deploy <name> --all       # Deploy everywhere
atmosphere model deploy <name> --rule file # Deploy per rule file
atmosphere model undeploy <name> <node>    # Remove from node

# Import from LlamaFarm
atmosphere model import <path>             # Import trained model
atmosphere model import --llamafarm        # Import from ~/.llamafarm/models

# Status
atmosphere model status                    # Deployment status
atmosphere model status <name>             # Specific model status
```

## Integration with LlamaFarm

Models trained by LlamaFarm at `~/.llamafarm/models/` can be imported:

```bash
# Import a specific model
atmosphere model import ~/.llamafarm/models/anomaly/network_detector.joblib \
  --name network-anomaly-detector \
  --type anomaly_detector \
  --capabilities anomaly_detection,network_monitoring

# Bulk import
atmosphere model import --llamafarm --type anomaly
```

Import process:
1. Read model file
2. Detect format (joblib, onnx, etc.)
3. Extract/generate manifest
4. Copy to `~/.atmosphere/models/`
5. Register in local registry
6. Announce via gossip (if configured)

## Security Considerations

### Model Signing
Models can be cryptographically signed:

```yaml
signature:
  signer: central-admin
  algorithm: ed25519
  signature: base64:...
  signed_at: 2026-02-02T15:30:00Z
```

### Transfer Verification
1. Checksum verification after transfer
2. Optional signature verification
3. Manifest validation
4. Dependency checking before load

### Access Control
```yaml
model_access:
  network-anomaly-detector:
    read: [edge, gateway, admin]
    write: [admin]
    deploy: [admin, gateway]
```

## Metrics

Track deployment health:

```yaml
deployment_metrics:
  total_models: 5
  total_deployments: 23  # Model instances across nodes
  pending_transfers: 2
  failed_transfers_24h: 0
  avg_transfer_time_ms: 1234
  
  by_model:
    network-anomaly-detector:
      nodes: 8
      version_distribution:
        "1.0.0": 6
        "0.9.0": 2
```

## Edge Learning Loop

Complete cycle:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  1. DETECT                                                  │
│     Edge node sees unclassified anomaly                     │
│                          │                                  │
│                          ▼                                  │
│  2. ESCALATE                                                │
│     Send sample to central for analysis                     │
│                          │                                  │
│                          ▼                                  │
│  3. TRAIN                                                   │
│     Central trains new detector model                       │
│                          │                                  │
│                          ▼                                  │
│  4. DEPLOY (This System!)                                   │
│     Model auto-distributes to edge nodes                    │
│                          │                                  │
│                          ▼                                  │
│  5. DETECT (Improved!)                                      │
│     Edge nodes now recognize this anomaly type              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

This creates a self-improving distributed detection network.
