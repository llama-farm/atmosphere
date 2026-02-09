# End-to-End Vision Model Dissemination Wiring

**Status**: ✅ Complete  
**Date**: 2026-02-08  
**Task**: Wire together the full model dissemination pipeline across Android, Mac, and Python platforms

---

## Overview

This document describes the complete vision model dissemination pipeline that enables LlamaFarm-trained models to be discovered and downloaded by Android and Mac mesh clients.

## Architecture

```
┌─────────────────┐
│   LlamaFarm     │
│  (localhost:    │
│    11540)       │
│                 │
│ - Train models  │
│ - Create pkgs   │
│ - Serve API     │
└────────┬────────┘
         │
         │ HTTP API
         │
         v
┌─────────────────────────────────────────────┐
│  Python ModelBridge (Atmosphere)            │
│  - Scans LlamaFarm models via API           │
│  - Builds model catalog                     │
│  - Serves models via HTTP (port 14345)      │
│  - Gossips catalog to mesh periodically     │
└────────┬────────────────────────────────────┘
         │
         │ WebSocket + BLE Mesh
         │
    ┌────┴────┐
    │         │
    v         v
┌───────┐  ┌──────┐
│ Mac   │  │Android
│ App   │  │  App │
│       │  │      │
│Catalog│  │Catalog
│Service│  │Manager
└───────┘  └──────┘
    │         │
    v         v
Download    Download
 Model       Model
```

## Components Wired

### 1. Python Model Bridge (`atmosphere/model_bridge.py`)

**Updates Made**:
- ✅ Query LlamaFarm vision API (`GET /v1/vision/models`)
- ✅ Query model packages (`GET /v1/vision/federation/packages`)
- ✅ Build comprehensive model catalog with metadata
- ✅ Serve models via HTTP with Range support (chunked transfer)
- ✅ Gossip `model_catalog` messages periodically
- ✅ Connect to Atmosphere mesh WebSocket

**Key Features**:
- Scans both HuggingFace cache and LlamaFarm-trained models
- Computes SHA-256 checksums for integrity verification
- Supports HTTP Range requests for resumable downloads
- Announces model availability every 5 minutes

**Message Format**:
```json
{
  "type": "model_catalog",
  "node_id": "llamafarm-node",
  "node_name": "LlamaFarm",
  "timestamp": 1234567890,
  "models": [
    {
      "model_id": "yolov8n_custom_20240208",
      "name": "Custom YOLOv8n",
      "type": "vision",
      "format": "pt",
      "size_bytes": 6000000,
      "sha256": "abc123...",
      "version": "1.0.0",
      "capabilities": ["object_detection"],
      "classes": ["person", "car", "dog"],
      "class_count": 3,
      "source": "llamafarm_training",
      "source_ref": "local"
    }
  ],
  "transfer_endpoints": {
    "http": "http://192.168.1.100:14345",
    "websocket": true
  },
  "ttl_seconds": 300
}
```

### 2. Android GossipManager (`GossipManager.kt`)

**Updates Made**:
- ✅ Added `handleModelCatalog()` method to process `model_catalog` messages
- ✅ Added `modelCatalogUpdates` SharedFlow for routing to ModelCatalog
- ✅ Detects message type and routes accordingly
- ✅ Triggers model update checks when new versions are discovered

**Integration Points**:
```kotlin
// Listen for model catalog updates
gossipManager.modelCatalogUpdates.collect { (catalogJson, sourceNodeId) ->
    modelCatalog.processCatalogMessage(sourceNodeId, nodeName, catalogJson)
    checkForModelUpdates()
}
```

### 3. Android MeshCapabilityHandler (`MeshCapabilityHandler.kt`)

**Updates Made**:
- ✅ Added `ModelCatalog` integration
- ✅ Added `VisionModelManager` integration
- ✅ Added `setGossipManager()` to wire model catalog flow
- ✅ Added `checkForModelUpdates()` to auto-queue downloads
- ✅ Added `isNewerVersion()` for semantic version comparison
- ✅ Updated `announceCapabilities()` to include loaded vision models

**Key Features**:
- Automatically detects new model versions from gossip
- Selects best peer for download (prefers HTTP, considers latency)
- Registers vision model capabilities in mesh announcements
- Integrates with existing ModelTransferService for downloads

**Vision Model Announcements**:
```json
{
  "type": "capability_announce",
  "node_id": "android_device_123",
  "capabilities": [...],
  "vision_models": [
    {
      "model_id": "yolov8n_custom_20240208",
      "version": "1.0.0",
      "loaded": true
    }
  ]
}
```

### 4. Mac ModelCatalogService (`ModelCatalogService.swift`)

**Updates Made**:
- ✅ Updated `performSync()` to query both models and packages endpoints
- ✅ Builds package map to enrich model metadata
- ✅ Periodically gossips catalog to BLE mesh
- ✅ Handles incoming catalog messages from peers
- ✅ Manages model transfer requests

**Sync Flow**:
1. Query `GET /v1/vision/models` → list active models
2. Query `GET /v1/vision/federation/packages` → get package metadata
3. Merge data → build enriched catalog
4. Broadcast catalog via BLE mesh + relay
5. Repeat every 5 minutes

### 5. Integration Test (`test_e2e_vision.py`)

**Test Coverage**:
- ✅ LlamaFarm health check
- ✅ List vision models
- ✅ List model packages
- ✅ Run vision detection
- ✅ Test escalation flow
- ✅ Simulate gossip message
- ✅ Create model package
- ✅ Test ModelBridge HTTP server
- ✅ Verify complete pipeline

**Usage**:
```bash
cd /Users/robthelen/clawd/projects/atmosphere
python3 test_e2e_vision.py
```

## Data Flow

### Model Training → Dissemination

1. **LlamaFarm trains a new vision model**
   - User escalates uncertain detections
   - Replay buffer accumulates training samples
   - Training completes → new model saved

2. **Package Creation**
   ```bash
   POST /v1/vision/federation/packages
   {
     "model_id": "yolov8n_custom_20240208"
   }
   ```
   - Creates `.tar.gz` package with model + metadata
   - Returns package info (path, size, checksum)

3. **Python ModelBridge Discovers**
   - Periodic scan (every 5 min)
   - Queries `/v1/vision/models` and `/v1/vision/federation/packages`
   - Updates catalog with new model

4. **Gossip Broadcast**
   - ModelBridge sends `model_catalog` message
   - Propagates to all mesh nodes via WebSocket/BLE
   - TTL: 5 minutes, re-gossiped periodically

5. **Android/Mac Receive Gossip**
   - GossipManager receives message
   - Routes to ModelCatalog
   - ModelCatalog merges peer info

6. **Version Check & Download**
   - MeshCapabilityHandler checks local vs. remote versions
   - If new version available → queue download
   - Selects best peer (HTTP preferred, lowest latency)
   - ModelTransferService chunks download (or HTTP range requests)

7. **Import & Activation**
   - VisionModelManager imports package
   - Verifies checksum
   - Loads model for inference
   - Announces capability to mesh

## API Endpoints

### LlamaFarm Vision API (port 11540)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/vision/models` | List active vision models |
| POST | `/v1/vision/detect` | Run object detection |
| POST | `/v1/vision/classify` | Run image classification |
| POST | `/v1/vision/train` | Start training job |
| GET | `/v1/vision/federation/packages` | List model packages |
| POST | `/v1/vision/federation/packages` | Create package from model |
| POST | `/v1/vision/federation/packages/import` | Import package |
| POST | `/v1/vision/federation/escalate` | Escalate for consensus |

### Python ModelBridge HTTP (port 14345)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/models` | List all available models |
| GET | `/v1/models/{model_id}` | Get model info |
| GET | `/v1/models/download/{model_id}` | Download model (supports Range) |
| GET | `/health` | Health check |

## Gossip Message Types

### `model_catalog`
Announces available models from a node.

**Fields**:
- `node_id`: Source node identifier
- `node_name`: Human-readable node name
- `timestamp`: Unix timestamp (ms)
- `models`: Array of model info objects
- `transfer_endpoints`: HTTP/WebSocket endpoints
- `ttl_seconds`: Time-to-live (300s default)

### `model_request`
Requests a model from a peer.

**Fields**:
- `model_id`: Model to request
- `requesting_node`: Requester node ID

### `model_transfer`
Chunked model data transfer.

**Fields**:
- `model_id`: Model being transferred
- `chunk_index`: Current chunk number
- `total_chunks`: Total chunks in transfer
- `data`: Base64-encoded chunk data
- `checksum`: SHA-256 of chunk

## Configuration

### Environment Variables

```bash
# Python ModelBridge
ATMOSPHERE_NODE_ID=llamafarm-primary
ATMOSPHERE_NODE_NAME=LlamaFarm
LLAMAFARM_MODELS_DIR=~/.llamafarm/models
HUGGINGFACE_CACHE_DIR=~/.cache/huggingface/hub
MODEL_BRIDGE_HTTP_PORT=14345
GOSSIP_INTERVAL_SEC=300

# Android
ATMOSPHERE_NODE_ID=android_device_123
MODEL_CATALOG_SYNC_INTERVAL_MS=300000

# Mac
LLAMAFARM_URL=http://localhost:11540
MODEL_SYNC_INTERVAL_SEC=300
```

## Testing

### Prerequisites
- LlamaFarm running on `localhost:11540`
- At least one vision model loaded
- Python Atmosphere mesh server running (optional)

### Run Tests
```bash
cd /Users/robthelen/clawd/projects/atmosphere
python3 test_e2e_vision.py
```

### Expected Output
```
╔═══════════════════════════════════════════╗
║  Vision Model Dissemination E2E Test     ║
╚═══════════════════════════════════════════╝

▶ Test 1: Check LlamaFarm Health
✓ LlamaFarm is healthy: ok
  Available models: 2
  - yolov8n: detection
  - yolov8x: detection

▶ Test 2: List Vision Models
✓ Found 2 vision models
  - yolov8n: detection (loaded=true, device=cpu)
  - yolov8x: detection (loaded=false, device=cpu)

...

╔═══════════════════════════════════════════╗
║  Test Summary                             ║
╚═══════════════════════════════════════════╝

✓ Health Check
✓ List Models
✓ List Packages
✓ Vision Detection
✓ Escalation Flow
✓ Gossip Simulation
✓ Package Creation
✓ ModelBridge HTTP
✓ Pipeline Integration

Result: 9/9 tests passed
✓ All tests passed!
```

## Monitoring & Debugging

### Python ModelBridge Logs
```bash
# Start with debug logging
python3 -m atmosphere.model_bridge --log-level DEBUG
```

### Android Logs
```bash
adb logcat | grep -E "(GossipManager|ModelCatalog|MeshCapabilityHandler)"
```

### Mac Logs
```bash
# View in Xcode Console or:
log stream --predicate 'subsystem == "com.llamafarm.atmosphere"' --level debug
```

### Verify Gossip Flow
```bash
# Listen to mesh WebSocket
wscat -c ws://localhost:8765

# Should see periodic model_catalog messages
{"type":"model_catalog","node_id":"llamafarm-primary",...}
```

## Troubleshooting

### Models Not Appearing in Catalog
1. Check LlamaFarm API: `curl http://localhost:11540/v1/vision/models`
2. Check packages: `curl http://localhost:11540/v1/vision/federation/packages`
3. Verify ModelBridge is running and scanning
4. Check gossip interval (default 5 min)

### Download Fails
1. Verify HTTP endpoint is reachable
2. Check firewall rules (port 14345)
3. Verify checksum matches
4. Check available disk space

### Gossip Not Propagating
1. Verify WebSocket connection to mesh server
2. Check TTL and nonce cache
3. Verify nodes are in same mesh network
4. Check BLE pairing (for Mac/Android direct mesh)

## Future Enhancements

### Planned
- [ ] Automatic model version rollback on failure
- [ ] P2P model transfer (peer-to-peer, no central server)
- [ ] Delta updates (only transfer changed weights)
- [ ] Model compression before transfer
- [ ] Bandwidth-aware download scheduling
- [ ] Peer reputation tracking

### Potential
- [ ] Multi-part download with parallel chunks
- [ ] Torrent-style model dissemination
- [ ] Model version conflict resolution
- [ ] Automatic model pruning (remove old versions)

## Related Files

### Python
- `/Users/robthelen/clawd/projects/atmosphere/atmosphere/model_bridge.py`
- `/Users/robthelen/clawd/projects/atmosphere/atmosphere/mesh/gossip.py`
- `/Users/robthelen/clawd/projects/atmosphere/test_e2e_vision.py`

### Android
- `atmosphere-android/app/src/main/kotlin/com/llamafarm/atmosphere/core/GossipManager.kt`
- `atmosphere-android/app/src/main/kotlin/com/llamafarm/atmosphere/mesh/ModelCatalog.kt`
- `atmosphere-android/app/src/main/kotlin/com/llamafarm/atmosphere/mesh/ModelTransferService.kt`
- `atmosphere-android/app/src/main/kotlin/com/llamafarm/atmosphere/capabilities/MeshCapabilityHandler.kt`

### Mac
- `AtmosphereMac/LlamaFarmBridge.swift`
- `AtmosphereMac/ModelCatalogService.swift`
- `AtmosphereMac/BLEMeshManager.swift`

## Summary

✅ **Complete Pipeline Wired**

The vision model dissemination pipeline is now fully integrated across all three platforms:

1. **Python** - Scans LlamaFarm, serves models, gossips catalog
2. **Android** - Receives gossip, manages catalog, auto-downloads updates
3. **Mac** - Queries LlamaFarm, gossips to BLE mesh, handles transfers

**Key Achievement**: When LlamaFarm trains a new model, it automatically becomes available to all mesh clients within 5 minutes via gossip propagation.

**Testing**: Run `python3 test_e2e_vision.py` to verify the complete flow.

---

**Author**: Subagent (e2e-vision-wiring)  
**Date**: 2026-02-08  
**Status**: ✅ Complete
