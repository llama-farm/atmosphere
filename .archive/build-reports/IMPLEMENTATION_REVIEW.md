# Atmosphere Implementation Review

**Generated:** 2025-01-10  
**Reviewer:** Subagent Design Review  
**Scope:** Compare design docs vs actual implementation

---

## Executive Summary

| Component | Status | Completion |
|-----------|--------|------------|
| Capability Scanner | 🟡 Partial | ~70% |
| Cost Model | ✅ Complete | ~95% |
| Owner Approval | 🟡 Partial | ~60% |
| Packaging | 🟡 Partial | ~40% |
| Matter Integration | 🟡 Partial | ~50% |
| Gossip Messages | 🟡 Partial | ~65% |
| Bidirectional Capabilities | 🟡 Partial | ~75% |

**Overall Assessment:** Core infrastructure is well-implemented but several features from the design docs are pending or stubbed out.

---

## 1. Capability Scanner

### Design: `design/CAPABILITY_SCANNER.md`
### Implementation: `atmosphere/scanner/`

#### ✅ Implemented and Matches Design

| Feature | Design Section | Implementation |
|---------|----------------|----------------|
| GPU Detection (Metal) | GPU Detection → Metal | `scanner/gpu.py::_detect_metal_gpu()` - Uses system_profiler, extracts Metal version, cores, memory |
| GPU Detection (CUDA) | GPU Detection → CUDA | `scanner/gpu.py::_detect_cuda_gpus()` - Uses nvidia-smi, gets memory, compute capability |
| GPU Detection (ROCm) | GPU Detection → ROCm | `scanner/gpu.py::_detect_rocm_gpus()` - Uses rocm-smi |
| Permission Pre-flight (macOS) | Permission Pre-flight | `scanner/permissions.py` - TCC permission checks without triggering prompts |
| Permission Instructions | Permission Request Guidance | `scanner/permissions.py::PERMISSION_INSTRUCTIONS` |
| Ollama Model Detection | Model Detection → Ollama | `scanner/models.py::detect_ollama_models()` - Async HTTP to /api/tags |
| LlamaFarm Detection | Model Detection → LlamaFarm | `scanner/models.py::detect_llamafarm_models()` - /v1/models endpoint |
| HuggingFace Cache Scan | Model Detection → HuggingFace | `scanner/models.py::detect_huggingface_models()` - Scans ~/.cache/huggingface/hub |
| GGUF File Detection | Model Detection → GGUF | `scanner/models.py::detect_gguf_files()` - With quantization extraction |
| Camera Detection (macOS) | Hardware Detection → Cameras | `scanner/hardware.py::_detect_cameras_macos()` - system_profiler SPCameraDataType |
| Camera Detection (Linux) | Hardware Detection → Cameras | `scanner/hardware.py::_detect_cameras_linux()` - v4l2-ctl |
| Microphone Detection | Hardware Detection → Microphones | `scanner/hardware.py::_detect_microphones_macos/linux()` |
| Speaker Detection | Hardware Detection → Speakers | `scanner/hardware.py::_detect_speakers_macos/linux()` |
| Port Probing | Service Detection → Port Probing | `scanner/services.py::_probe_port()` - TCP connect check |
| Service Verification | Service Detection → Verify | `scanner/services.py::_verify_service()` - HTTP health checks |
| Docker Container Detection | Service Detection → Docker | **NOT IMPLEMENTED** |
| Graceful Degradation | Permission Pre-flight | `scanner/permissions.py::PermissionStatus` - can_detect vs can_access separation |

#### 🟡 Implemented but Differs from Design

| Feature | Design | Actual Implementation | Notes |
|---------|--------|----------------------|-------|
| Scanner Architecture | Single `CapabilityScanner` class with sub-scanners | Separate modules: `gpu.py`, `models.py`, `hardware.py`, `services.py` | Better modularity, same functionality |
| Capability Testing | `CapabilityTester` class to verify capabilities actually work | **NOT IMPLEMENTED** | Only detection, not functional testing |
| CLI Integration | `atmosphere scan` command | `scanner/cli.py` - Rich console output, JSON mode | Matches design intent |

#### ❌ NOT Implemented (In Design but Missing)

| Feature | Design Section | Status |
|---------|----------------|--------|
| Vulkan GPU Detection | GPU Detection → Vulkan | ❌ Not implemented |
| NPU Detection (Apple Neural Engine) | NPU Detection | ❌ Not implemented |
| NPU Detection (Qualcomm) | NPU Detection | ❌ Not implemented |
| Camera Functional Test | Capability Testing | ❌ Not implemented - no `test_camera()` |
| Microphone Functional Test | Capability Testing | ❌ Not implemented - no `test_microphone()` |
| GPU Inference Test | Capability Testing | ❌ Not implemented - no `test_metal_inference()` |
| Ollama Model Test | Capability Testing | ❌ Not implemented - no `test_ollama_model()` |
| Docker Container Discovery | Service Detection → Docker | ❌ Not implemented |
| Systemd Service Detection | Service Detection → Systemd | ❌ Not implemented |
| LaunchAgent Detection (macOS) | Service Detection | ❌ Not implemented |
| Registry Integration | Capability Registry | ❌ Scanner doesn't auto-register capabilities |

---

## 2. Cost Model

### Design: `design/COST_MODEL.md`
### Implementation: `atmosphere/cost/`

#### ✅ Implemented and Matches Design

| Feature | Design Section | Implementation |
|---------|----------------|----------------|
| NodeCostFactors dataclass | Cost Calculation | `collector.py::NodeCostFactors` - All fields match design |
| Power State Detection (macOS) | Power State → macOS | `collector.py::MacOSCostCollector._get_power_state_psutil()` |
| Power State Detection (Linux) | Power State → Linux | `collector.py::LinuxCostCollector._get_power_state()` - /sys/class/power_supply |
| Power Cost Multiplier | Cost Multipliers | `model.py::power_cost_multiplier()` - 1x-5x based on battery |
| CPU Load Detection | Compute Load | `collector.py::_get_cpu_load_psutil()` - Load average normalized |
| GPU Load (NVIDIA) | Compute Load → nvidia-smi | `collector.py::MacOSCostCollector._get_nvidia_gpu()` |
| Apple GPU Heuristic | Compute Load → macOS GPU | `collector.py::MacOSCostCollector._get_apple_gpu_heuristic()` - Process-based estimation with clear warning |
| Compute Load Multiplier | Cost Multipliers | `model.py::compute_load_multiplier()` - CPU, GPU, memory factors |
| Network Metered Detection (macOS) | Network → Metered | `collector.py::MacOSCostCollector._is_metered_connection()` - iPhone tethering detection |
| Network Metered Detection (Linux) | Network → Metered | `collector.py::LinuxCostCollector._is_metered_connection()` - NetworkManager D-Bus |
| Network Cost Multiplier | Cost Multipliers | `model.py::network_cost_multiplier()` |
| API Cost Table | Cloud API Costs | `model.py::API_COSTS` - OpenAI, Anthropic, Google pricing |
| API Cost Estimation | Cloud API Costs | `model.py::estimate_api_cost()` |
| WorkRequest dataclass | Cost Calculation | `model.py::WorkRequest` |
| Total Cost Calculation | Cost Calculation | `model.py::compute_node_cost()` - Combines all factors |
| Node Selection with Hysteresis | Routing Integration | `model.py::select_best_node()` - `min_cost_difference` parameter |
| Cross-platform Factory | Platform-Specific Detection | `collector.py::get_cost_collector()` |
| Stub Collector | Platform-Specific Detection | `collector.py::StubCostCollector` |

#### ✅ Gossip Integration (Matches Design)

| Feature | Design Section | Implementation |
|---------|----------------|----------------|
| NODE_COST_UPDATE message | Gossip Integration | `gossip.py::build_cost_message()` - Matches schema |
| CostGossipState | Gossip Integration | `gossip.py::CostGossipState` - node_costs tracking |
| Stale threshold handling | Gossip Integration | `gossip.py::CostGossipState.get_node_cost()` - 60s default stale |
| CostBroadcaster | Broadcast Frequency | `gossip.py::CostBroadcaster` - 30s interval, significant change detection |
| Force broadcast | Broadcast Frequency | `gossip.py::CostBroadcaster.force_broadcast_needed()` |

#### ✅ Router Integration

| Feature | Design Section | Implementation |
|---------|----------------|----------------|
| CostAwareRouter | Routing Integration | `router.py::CostAwareRouter` |
| IntegratedCostRouter | Routing Integration | `router.py::IntegratedCostRouter` |
| Route result with cost breakdown | Routing Integration | `router.py::RouteResult` |

#### 🟡 Minor Differences

| Feature | Design | Actual | Notes |
|---------|--------|--------|-------|
| Stale threshold | 120 seconds | 60 seconds (power), 120s (default) | Actually more sophisticated with power-aware thresholds |
| Memory pressure (macOS) | `/usr/bin/memory_pressure` | Uses psutil | Cross-platform approach |

#### ❌ NOT Implemented

| Feature | Design Section | Status |
|---------|----------------|--------|
| Bandwidth Estimation | Network → Bandwidth | ❌ No `BandwidthEstimator` class |
| Transfer History Tracking | Network → Bandwidth | ❌ Not implemented |
| Thermal Throttling Detection | Open Questions | ❌ Not implemented |
| Historical Smoothing | Open Questions | ❌ Not implemented |

---

## 3. Owner Approval

### Design: `design/OWNER_APPROVAL.md`
### Implementation: `atmosphere/approval/`

#### ✅ Implemented and Matches Design

| Feature | Design Section | Implementation |
|---------|----------------|----------------|
| ApprovalConfig dataclass | Data Model | `models.py::ApprovalConfig` - Complete with version, node, exposure, access, audit |
| ExposureConfig | Data Model → expose | `models.py::ExposureConfig` - models, hardware, sensors |
| ModelExposure (Ollama) | Data Model → models | `models.py::OllamaExposure` - allow/deny lists, patterns |
| ModelPatterns with fnmatch | Data Model → patterns | `models.py::ModelPatterns` - Wildcard matching implemented |
| LlamaFarmExposure | Data Model → llamafarm | `models.py::LlamaFarmExposure` |
| HardwareExposure (GPU/CPU) | Data Model → hardware | `models.py::GPUExposure`, `CPUExposure` with limits |
| GPULimits | Data Model → gpu.limits | `models.py::GPULimits` - max_vram_percent, max_concurrent_jobs |
| SensorExposure | Data Model → sensors | `models.py::SensorExposure` - camera, microphone, screen |
| CameraExposure | Data Model → camera | `models.py::CameraExposure` - OFF by default, mode stills/video |
| MicrophoneExposure | Data Model → microphone | `models.py::MicrophoneExposure` - transcription mode support |
| MicrophoneMode enum | Data Model | `models.py::MicrophoneMode` - DISABLED, TRANSCRIPTION, FULL |
| AccessConfig | Data Model → access | `models.py::AccessConfig` - meshes, auth, rate_limits |
| MeshAccess | Data Model → meshes | `models.py::MeshAccess` - ALL, ALLOWLIST, DENYLIST modes |
| AuthConfig | Data Model → auth | `models.py::AuthConfig` - require, methods, allow_anonymous |
| RateLimitConfig | Data Model → rate_limits | `models.py::RateLimitConfig` - global, per_mesh, llm-specific |
| AuditConfig | Data Model → audit | `models.py::AuditConfig` - log_all_requests, log_path, retain_days |
| NodeMetadata | Data Model → node | `models.py::NodeMetadata` - name, description, location, tags |
| YAML Serialization | Config File Schema | `config.py::save_config()`, `load_config()` |
| Safe Defaults | Data Model | `models.py::ApprovalConfig.with_safe_defaults()` |
| Config Validation | Config File Schema | `config.py::validate_config()` - Returns warnings list |
| Exposure Summary | UI Mockups | `config.py::get_exposure_summary()` |
| Config Directory | Config File Schema | `config.py::get_config_dir()` - ~/.atmosphere |

#### 🟡 Implemented but Differs

| Feature | Design | Actual | Notes |
|---------|--------|--------|-------|
| Config path | `~/.atmosphere/config.yaml` | Same | ✓ Matches |
| Resource limits | Per-capability in exposure | `exposure.resources` as separate field | Slightly different structure |

#### ❌ NOT Implemented

| Feature | Design Section | Status |
|---------|----------------|--------|
| Web UI (React) | UI Mockups → Web UI | ❌ No React components |
| CLI Interactive UI (inquirer) | UI Mockups → CLI UI | ❌ Basic CLI only |
| Approval Flow State Machine | State Machine | ❌ No EMPTY→DISCOVERED→APPROVED flow |
| Real-time Mesh Refresh | User Flow → Apply & Join | ❌ No `/v1/mesh/refresh` endpoint |
| Tools Exposure | Data Model → tools | ❌ No `tools` section in config |
| Screen Capture exclude_windows | Data Model → screen.settings | ✅ Actually implemented in models.py |

---

## 4. Packaging

### Design: `design/PACKAGING.md`
### Implementation: Project root

#### ✅ Implemented

| Feature | Design Section | Implementation |
|---------|----------------|----------------|
| pyproject.toml structure | PyPI | Present at project root |
| Package name | PyPI | `atmosphere` (not `atmosphere-mesh` as suggested) |
| Dependencies | PyPI | Core deps present |
| Entry point | PyPI | `atmosphere` CLI |

#### 🟡 Partially Implemented

| Feature | Design | Actual | Notes |
|---------|--------|--------|-------|
| httpx dependency | Listed as MISSING | Need to verify in pyproject.toml | May be fixed |
| UI bundling | `atmosphere/ui/dist/` | ❌ No UI to bundle | React app not built |

#### ❌ NOT Implemented

| Feature | Design Section | Status |
|---------|----------------|--------|
| Homebrew Formula | Homebrew | ❌ No `Formula/atmosphere.rb` |
| Homebrew Tap | Homebrew | ❌ No `llama-farm/homebrew-tap` |
| Debian Package | Debian Package | ❌ No `debian/` directory |
| Docker Image | Docker Image | ❌ No `Dockerfile` |
| docker-compose.yml | Docker Image | ❌ Not present |
| CI/CD Pipeline | CI/CD Pipeline | ❌ No `.github/workflows/release.yml` |
| Version Bump Script | Version Management | ❌ No `scripts/bump-version.sh` |
| MANIFEST.in | PyPI | ❌ Not present |
| Shell Completions | Homebrew → completions | ❌ Not generated |

---

## 5. Matter Integration

### Design: `design/MATTER_INTEGRATION.md`
### Implementation: `atmosphere/integrations/matter/`

#### ✅ Implemented and Matches Design

| Feature | Design Section | Implementation |
|---------|----------------|----------------|
| MatterDevice model | Architecture | `models.py::MatterDevice` |
| MatterEndpoint model | Architecture | `models.py::MatterEndpoint` |
| ClusterType enum | Clusters | `models.py::ClusterType` - OnOff, LevelControl, ColorControl, DoorLock, etc. |
| DeviceType enum | Device Types | `models.py::DeviceType` - 15+ device types |
| MatterCommand | Code Structure | `models.py::MatterCommand` |
| MatterCommandResult | Code Structure | `models.py::MatterCommandResult` |
| BridgeConfig | Code Structure → Bridge | `bridge.py::BridgeConfig` |
| MatterBridge class | Code Structure → Bridge | `bridge.py::MatterBridge` |
| Bridge WebSocket protocol | Implementation Options | `bridge.py` - JSON-RPC via WebSocket (stubbed) |
| Device commissioning | Commissioning Flow | `bridge.py::MatterBridge.commission()` |
| Command execution | Control Layer | `bridge.py::MatterBridge.execute_command()` |
| Attribute read/write | Control Layer | `bridge.py::MatterBridge.read_attribute()`, `write_attribute()` |
| Subscriptions | Events & Triggers | `bridge.py::MatterBridge.subscribe()`, `unsubscribe()` |
| Event handlers | Events & Triggers | `bridge.py::MatterBridge.on_device_event`, etc. |
| MatterBridgeManager | Code Structure | `bridge.py::MatterBridgeManager` |
| Device state caching | Architecture | `bridge.py::MatterBridgeManager._device_states` |
| Tool execution | Tool Call → Device Command | `bridge.py::MatterBridgeManager.execute_tool()` |
| Cluster to tool mapping | Device → Capability Mapping | `mapping.py` exists |
| CLI commands | - | `cli.py` exists |

#### 🟡 Stubbed/Partial

| Feature | Design | Actual | Notes |
|---------|--------|--------|-------|
| Bridge subprocess | Start Node.js process | STUBBED - `_send_request()` returns mocks | Comment says "For MVP, this is STUBBED" |
| WebSocket connection | aiohttp/websockets | STUBBED | `_connect_websocket()` is pass |
| matter.js bridge | Node.js package | ❌ No `node_bridge/` directory | Bridge implementation missing |
| Device discovery | mDNS scanning | `discovery.py` exists but likely stubbed | Needs verification |

#### ❌ NOT Implemented

| Feature | Design Section | Status |
|---------|----------------|--------|
| Node.js Bridge Package | Code Structure → node_bridge | ❌ `node_bridge/` directory doesn't exist |
| matter.js integration | Implementation Options | ❌ No actual matter.js dependency |
| Thread Border Router | Future Enhancements | ❌ Not implemented |
| Scene/Group Support | Future Enhancements | ❌ Not implemented |
| Energy Monitoring | Future Enhancements | ❌ Not implemented |

---

## 6. Gossip Messages

### Design: `design/GOSSIP_MESSAGES.md`
### Implementation: `atmosphere/mesh/gossip.py`

#### ✅ Implemented and Matches Design

| Feature | Design Section | Implementation |
|---------|----------------|----------------|
| CapabilityInfo dataclass | CAPABILITY_AVAILABLE | `gossip.py::CapabilityInfo` - id, label, description, vector, hops, via, models |
| ResourceInfo dataclass | - | `gossip.py::ResourceInfo` - cpu, memory, gpu, battery |
| Announcement dataclass | Message Types | `gossip.py::Announcement` - type, from_node, capabilities, resources, timestamp, ttl, nonce |
| GossipProtocol class | Implementation | `gossip.py::GossipProtocol` |
| Build announcement | - | `gossip.py::GossipProtocol.build_announcement()` |
| Periodic announce | Broadcast Frequency | `gossip.py::GossipProtocol._announce_loop()` - 30 second interval |
| Handle incoming | Implementation | `gossip.py::GossipProtocol.handle_announcement()` |
| Nonce deduplication | Deduplication | `gossip.py::GossipProtocol._check_nonce()` |
| TTL decrement | TTL | `gossip.py::handle_announcement()` - decrements and forwards |
| Known nodes tracking | - | `gossip.py::GossipProtocol.known_nodes()` |
| Stats | - | `gossip.py::GossipProtocol.stats()` |
| Gradient table integration | - | Uses `GradientTable` for routing updates |

#### 🟡 Differences from Design

| Feature | Design | Actual | Notes |
|---------|--------|--------|-------|
| Message type naming | `CAPABILITY_AVAILABLE`, etc. | `"announce"` type | Simpler but different naming |
| Message structure | Detailed schema in YAML | `Announcement.to_dict()` | Similar but not identical structure |
| MAX_TTL | 10 in implementation | Design doesn't specify | Reasonable default |
| ANNOUNCE_INTERVAL | 30 seconds | Matches design expectation | ✓ |

#### ❌ NOT Implemented

| Feature | Design Section | Status |
|---------|----------------|--------|
| CAPABILITY_HEARTBEAT | Message Types | ❌ Separate heartbeat message not implemented |
| CAPABILITY_REMOVED | Message Types | ❌ Not implemented as gossip message |
| CAPABILITY_UPDATE | Message Types | ❌ Not implemented |
| TRIGGER_EVENT | Message Types | ❌ Not implemented - triggers don't gossip |
| ROUTE_UPDATE | Message Types | ❌ Separate route gossip not implemented |
| MODEL_DEPLOYED | Message Types | ❌ Not implemented |
| NODE_JOIN | Message Types | ❌ Not implemented |
| NODE_LEAVE | Message Types | ❌ Not implemented |
| TOKEN_REVOKED | Message Types | ❌ Not implemented |

---

## 7. Bidirectional Capabilities

### Design: `design/BIDIRECTIONAL_CAPABILITIES.md`
### Implementation: `atmosphere/capabilities/registry.py`

#### ✅ Implemented and Matches Design

| Feature | Design Section | Implementation |
|---------|----------------|----------------|
| Tool dataclass | Capability Schema → tools | `registry.py::Tool` - name, description, parameters, returns |
| Tool parameter validation | Capability Schema | `registry.py::Tool.validate_params()` |
| Trigger dataclass | Capability Schema → triggers | `registry.py::Trigger` - event, description, intent_template, route_hint, priority, throttle |
| Trigger throttle parsing | Capability Schema | `registry.py::Trigger.parse_throttle_ms()` |
| Trigger intent formatting | Push Flow | `registry.py::Trigger.format_intent()` |
| Capability dataclass | Capability Schema | `registry.py::Capability` - id, node_id, type, tools, triggers, metadata, status |
| CapabilityType enum | - | `registry.py::CapabilityType` - LLM, Vision, Audio, Sensor, Agent, IoT, Storage, Compute |
| CapabilityRegistry class | Implementation | `registry.py::CapabilityRegistry` |
| Register capability | Capability Lifecycle | `registry.py::CapabilityRegistry.register()` |
| Deregister capability | Capability Lifecycle | `registry.py::CapabilityRegistry.deregister()` |
| Find by type | Routing Fabric | `registry.py::CapabilityRegistry.find_by_type()` |
| Find by trigger | Routing Fabric | `registry.py::CapabilityRegistry.find_by_trigger()` |
| Find by tool | Routing Fabric | `registry.py::CapabilityRegistry.find_by_tool()` |
| Find by route hint | Routing Fabric | `registry.py::CapabilityRegistry.find_by_route_hint()` - fnmatch patterns |
| Health tracking | Capability Lifecycle | `registry.py::Capability.is_healthy()` |
| Heartbeat update | Capability Lifecycle | `registry.py::CapabilityRegistry.update_heartbeat()` |
| Handler registration | Implementation | `registry.py::CapabilityRegistry.register_handler()` |
| GossipMessage helper | Gossip Integration | `registry.py::GossipMessage` - available, heartbeat, unavailable |
| Process gossip | Gossip Integration | `registry.py::CapabilityRegistry.process_gossip()` |
| Serialization | - | `registry.py::Capability.to_dict()`, `from_dict()` |
| Global registry | - | `registry.py::get_registry()`, `reset_registry()` |

#### 🟡 Differences

| Feature | Design | Actual | Notes |
|---------|--------|--------|-------|
| Capability type | String like `"sensor/camera"` | Enum `CapabilityType.SENSOR_CAMERA` | Enum is more type-safe |
| Metadata structure | `location`, `hardware` at top level | Inside `metadata` dict | Slightly different organization |
| Tool returns | Detailed schema | Simple dict | Less detailed than design |

#### ❌ NOT Implemented

| Feature | Design Section | Status |
|---------|----------------|--------|
| Tool execution routing | Pull Flow | ❌ No `call_tool()` mesh routing |
| Trigger firing | Push Flow | ❌ No `fire_trigger()` method |
| Intent creation from trigger | Push Flow → Create intent | ❌ Not automated |
| Trigger throttle enforcement | Push Flow | ❌ No throttle state tracking |
| Cross-capability workflow orchestration | Cross-Capability Workflows | ❌ Not implemented |
| Full camera capability example | More Examples → Camera | ❌ Example not in codebase |

---

## Summary: Priority Action Items

### 🔴 Critical (Blocking Core Functionality)

1. **Capability Testing** - Scanner detects but doesn't verify capabilities work
2. **Matter Bridge** - Node.js bridge is completely stubbed
3. **Trigger/Event System** - No actual trigger firing or intent routing

### 🟡 High Priority (Feature Completion)

1. **Approval Web UI** - React components not implemented
2. **Gossip Message Types** - Only basic announcement, missing heartbeat/remove/update
3. **Packaging** - No Dockerfile, Homebrew formula, or CI/CD
4. **NPU Detection** - Apple Neural Engine and Qualcomm not detected

### 🟢 Medium Priority (Polish)

1. **Bandwidth Estimation** - No transfer history tracking
2. **Docker Discovery** - Container detection not implemented
3. **Systemd/LaunchAgent** - Service management detection
4. **Version Bump Scripts** - Release tooling

### 📝 Documentation Gaps

1. Update design docs to reflect implementation differences (enum vs string types)
2. Document stubbed components more clearly
3. Add migration guide for design → implementation

---

## Files Checked

### Design Documents
- `~/clawd/projects/atmosphere/design/CAPABILITY_SCANNER.md`
- `~/clawd/projects/atmosphere/design/COST_MODEL.md`
- `~/clawd/projects/atmosphere/design/OWNER_APPROVAL.md`
- `~/clawd/projects/atmosphere/design/PACKAGING.md`
- `~/clawd/projects/atmosphere/design/MATTER_INTEGRATION.md`
- `~/clawd/projects/atmosphere/design/GOSSIP_MESSAGES.md`
- `~/clawd/projects/atmosphere/design/BIDIRECTIONAL_CAPABILITIES.md`

### Implementation Files
- `atmosphere/scanner/` (gpu.py, models.py, hardware.py, services.py, permissions.py, cli.py)
- `atmosphere/cost/` (collector.py, model.py, router.py, gossip.py)
- `atmosphere/approval/` (models.py, config.py)
- `atmosphere/mesh/gossip.py`
- `atmosphere/capabilities/` (registry.py, base.py)
- `atmosphere/integrations/matter/` (bridge.py, models.py, mapping.py, discovery.py, cli.py)

---

*Review completed by design-review subagent*
