# Offline Distribution Protocol

How to get llamafarm.yaml, models, and agents to devices without internet.

## The Problem

Many edge devices will be:
- In air-gapped environments (factories, military, etc.)
- Behind firewalls with no outbound access
- In locations with unreliable connectivity

They still need:
- Model weights (potentially gigabytes)
- LlamaFarm configuration
- Agent definitions
- Knowledge/RAG data
- Tool definitions

## Solution: Distribution Packages

### Package Format

A distribution package is a self-contained archive:

```
production-inspection-v1.3.atmo/
├── manifest.yaml           # What's in this package
├── config/
│   ├── mission.yaml        # Mission configuration
│   └── llamafarm.yaml      # LlamaFarm project config
├── models/
│   ├── tinyyolo-defects-1.3.onnx
│   ├── yolov8s-defects-2.1.tensorrt
│   └── isolation-forest-line-1.0.pkl
├── agents/
│   ├── vision_agent-1.2.yaml
│   ├── anomaly_agent-1.0.yaml
│   └── learning_agent-1.1.yaml
├── tools/
│   └── core_tools.yaml
├── knowledge/
│   ├── defect-catalog.chunks.jsonl
│   └── sop-inspection.chunks.jsonl
└── checksums.sha256        # Integrity verification
```

### Manifest Structure

```yaml
# manifest.yaml
package:
  id: production-inspection
  version: "1.3"
  created: 2024-02-02T12:00:00Z
  created_by: training-server-01
  
  # What hardware tiers this package supports
  tiers: [tier_1, tier_2, tier_3]
  
  # Size by tier (helps device decide if it has space)
  size_by_tier:
    tier_1: 50MB
    tier_2: 250MB
    tier_3: 5GB

contents:
  config:
    - path: config/mission.yaml
      hash: sha256:abc123...
    - path: config/llamafarm.yaml
      hash: sha256:def456...
  
  models:
    - path: models/tinyyolo-defects-1.3.onnx
      id: tinyyolo-defects
      version: "1.3"
      size_mb: 6
      tiers: [tier_1, tier_2, tier_3]
      hash: sha256:...
      
    - path: models/yolov8s-defects-2.1.tensorrt
      id: yolov8s-defects
      version: "2.1"
      size_mb: 22
      tiers: [tier_2, tier_3]
      hash: sha256:...
      
    - path: models/llama3-8b-inspection.gguf
      id: llama3-8b-inspection
      version: "1.0"
      size_mb: 4500
      tiers: [tier_3]
      hash: sha256:...
  
  agents:
    - path: agents/vision_agent-1.2.yaml
      id: vision_agent
      version: "1.2"
      hash: sha256:...
    # ... etc
  
  knowledge:
    - path: knowledge/defect-catalog.chunks.jsonl
      domain: defect-catalog
      chunks: 1523
      hash: sha256:...

signatures:
  # Package signed by mesh authority
  mesh_signature: ed25519:...
  # Optional: signed by specific founder
  founder_signature: ed25519:...
```

## Distribution Methods

### Method 1: Mesh Transfer

If the device is on the mesh but behind firewall:

```
┌─────────────────┐          ┌─────────────────┐
│  Internet Node  │          │  Air-gapped     │
│  (has package)  │◄────────►│  Edge Node      │
│                 │  Mesh    │  (needs package)│
└─────────────────┘          └─────────────────┘

1. Edge node requests package via mesh
2. Internet node has package cached
3. Transfer via mesh protocol (may be slow)
4. Verify checksums and signatures
5. Install
```

### Method 2: USB/Physical Media

For truly air-gapped environments:

```bash
# On internet-connected machine
atmosphere package export production-inspection --version 1.3 --tier tier_1
# Creates: production-inspection-v1.3-tier1.atmo (50MB)

# Copy to USB drive
cp production-inspection-v1.3-tier1.atmo /media/usb/

# On air-gapped device
atmosphere package import /media/usb/production-inspection-v1.3-tier1.atmo
# Verifies signatures, installs contents
```

### Method 3: Local Network Sync

For devices on same LAN but no internet:

```
┌─────────────────┐          ┌─────────────────┐
│  Gateway Node   │          │  Edge Node      │
│  (has package)  │◄────────►│  (needs package)│
│                 │   LAN    │                 │
└─────────────────┘          └─────────────────┘

1. Gateway advertises available packages via mDNS
2. Edge discovers gateway
3. Requests package
4. High-speed LAN transfer
5. Verify and install
```

## Installation Process

```python
async def install_package(package_path: str, node: Node):
    """Install a distribution package on a node."""
    
    # 1. Load and verify manifest
    manifest = load_manifest(package_path)
    if not verify_signature(manifest, mesh_public_key):
        raise SecurityError("Invalid package signature")
    
    # 2. Determine tier
    tier = determine_tier(node.hardware)
    
    # 3. Check space requirements
    required_space = manifest.size_by_tier[tier]
    if node.available_space < required_space:
        raise SpaceError(f"Need {required_space}, have {node.available_space}")
    
    # 4. Extract and verify contents for this tier
    for item in manifest.contents.models:
        if tier in item.tiers:
            extract_and_verify(package_path, item)
    
    for item in manifest.contents.agents:
        extract_and_verify(package_path, item)
    
    # ... etc for other content types
    
    # 5. Install into runtime
    install_models(extracted_models)
    install_agents(extracted_agents)
    install_knowledge(extracted_knowledge)
    
    # 6. Apply configuration
    apply_llamafarm_config(manifest.config)
    
    # 7. Register with mesh
    announce_capabilities(node, manifest)
    
    # 8. Start services
    start_agents(installed_agents)
    
    return InstallResult(success=True, tier=tier, installed=manifest.contents)
```

## Delta Updates

For updates, only ship what changed:

```yaml
# delta manifest
delta:
  base_version: "1.2"
  target_version: "1.3"
  
  changes:
    models:
      updated:
        - id: tinyyolo-defects
          from_version: "1.2"
          to_version: "1.3"
          delta_path: models/tinyyolo-defects-1.2-to-1.3.delta
          delta_size_mb: 2  # vs 6MB full model
      added: []
      removed: []
    
    agents:
      updated:
        - id: vision_agent
          from_version: "1.1"
          to_version: "1.2"
    
    knowledge:
      chunks_added: 47
      chunks_removed: 12
      chunks_updated: 89
```

## Security Considerations

1. **Package Signing**: All packages signed by mesh authority
2. **Hash Verification**: Every file has SHA256 hash in manifest
3. **Chain of Custody**: Manifest records who created/transferred package
4. **Tamper Detection**: If any hash fails, reject entire package
5. **Version Control**: Can't install older version without explicit override

## CLI Commands

```bash
# Create a package for distribution
atmosphere package create \
  --mission production-inspection \
  --version 1.3 \
  --output ./packages/

# Create tier-specific packages (smaller)
atmosphere package create \
  --mission production-inspection \
  --version 1.3 \
  --tier tier_1 \
  --output ./packages/

# Export for USB transfer
atmosphere package export production-inspection-1.3 \
  --format archive \
  --output /media/usb/

# Import on air-gapped device
atmosphere package import /media/usb/production-inspection-v1.3.atmo

# Check for updates
atmosphere package check-updates

# Sync from gateway
atmosphere package sync --from gateway-01
```
