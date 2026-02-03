# Atmosphere: Roadmap to Production

> **From demo to deployable — what's left to build**

---

## Executive Summary

Atmosphere has solid foundations:
- ✅ Bidirectional capabilities (triggers + tools)
- ✅ Semantic routing with embeddings
- ✅ Gossip protocol design
- ✅ Zero-trust auth tokens
- ✅ LlamaFarm/Ollama discovery
- ✅ Working demos and UI

**What's missing for production:**
1. End-to-end workflow (discovery → approval → mesh join)
2. Packaging (pip/brew install, one command)
3. Dynamic cost model (battery, bandwidth, compute)
4. Mobile (Android app)
5. Matter integration (IoT)
6. Auto-capability detection
7. Owner control panel

---

## Part 1: End-to-End Workflow Gaps

### Current State
```
Today:
  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
  │   Install   │ ──? │   Discover  │ ──? │   Mesh      │
  │   (manual)  │     │   (partial) │     │   (demo)    │
  └─────────────┘     └─────────────┘     └─────────────┘
```

### Target State
```
Goal:
  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
  │  Install    │ ──▶ │  Discover   │ ──▶ │  Approve    │ ──▶ │  Live on    │
  │  (1 cmd)    │     │  (auto)     │     │  (owner UI) │     │  Mesh       │
  └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
        │                   │                   │                   │
        ▼                   ▼                   ▼                   ▼
   pip install         Scans local         Owner picks          Gossip
   atmosphere          hardware,           what to expose       announces,
                       models, APIs                             routes work
```

### Missing Pieces

#### 1.1 Local Capability Scanner
**Status:** ❌ Not implemented

Needs to detect:
```python
class CapabilityScanner:
    """Scans local system for available capabilities."""
    
    def scan_all(self) -> List[DiscoveredCapability]:
        return [
            *self.scan_hardware(),      # GPU, NPU, camera, mic
            *self.scan_models(),        # Ollama, LlamaFarm, HuggingFace
            *self.scan_services(),      # Running APIs, Docker containers
            *self.scan_system(),        # CPU, RAM, storage
        ]
    
    def scan_hardware(self):
        # GPU detection (CUDA, ROCm, Metal, Vulkan)
        # NPU detection (Apple Neural Engine, Qualcomm, Intel)
        # Camera detection (USB, built-in, IP cameras)
        # Microphone detection
        # Speaker detection
        pass
    
    def scan_models(self):
        # Ollama: ollama list
        # LlamaFarm: /v1/projects
        # HuggingFace cache: ~/.cache/huggingface/
        # GGUF files: find ~ -name "*.gguf"
        # Transformers: test imports, check VRAM
        pass
    
    def scan_services(self):
        # Check common ports (11434, 14345, 8000)
        # Docker: docker ps
        # systemd services
        pass
```

#### 1.2 Capability Approval UI
**Status:** ❌ Not implemented

Owner decides what to expose:
```
┌─────────────────────────────────────────────────────────────────┐
│  🔍 DISCOVERED CAPABILITIES                      [Scan Again]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ☑️  GPU: NVIDIA RTX 4090 (24GB)                               │
│      └─ Expose for: [✓] Inference [✓] Training [ ] Image Gen  │
│                                                                 │
│  ☑️  Ollama Models (26 models)                                 │
│      └─ [✓] llama3.2:latest                                    │
│      └─ [✓] qwen3:1.7b                                         │
│      └─ [ ] codellama:34b (disabled - too large)               │
│                                                                 │
│  ☐  Webcam: Logitech C920                                      │
│      └─ Not exposing (privacy)                                 │
│                                                                 │
│  ☑️  Microphone: Blue Yeti                                     │
│      └─ Expose for: [✓] Transcription [ ] Always-on           │
│                                                                 │
│  ☑️  LlamaFarm Projects (103 projects)                         │
│      └─ [Select which to expose...]                            │
│                                                                 │
│  [ ] Matter Devices (15 found)                                 │
│      └─ Requires Matter hub integration                        │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  [Cancel]                            [Save & Join Mesh]        │
└─────────────────────────────────────────────────────────────────┘
```

#### 1.3 Mesh Join Flow
**Status:** 🟡 Auth tokens exist, join flow partial

Complete flow:
```
1. User runs: atmosphere join <invite-token>
2. App validates token offline
3. App scans local capabilities
4. Owner approval UI shows discoveries
5. Owner selects what to expose
6. App registers with mesh
7. Gossip announces capabilities
8. Ready to receive work
```

---

## Part 2: Packaging

### Target: One-Command Install

#### macOS
```bash
# Homebrew (preferred)
brew install llama-farm/tap/atmosphere

# Or pip
pip install atmosphere-mesh

# Run
atmosphere start
```

#### Linux
```bash
# Debian/Ubuntu
curl -fsSL https://get.atmosphere.dev | bash
# or
sudo apt install atmosphere

# Fedora/RHEL
sudo dnf install atmosphere

# Run
atmosphere start
```

#### Package Contents
```
atmosphere/
├── bin/
│   └── atmosphere          # CLI binary
├── lib/
│   ├── atmosphere/         # Python package
│   └── ui/                 # React app (embedded)
├── share/
│   └── atmosphere/
│       ├── models/         # Default small models
│       └── config/         # Default configs
└── etc/
    └── atmosphere/
        └── default.yaml    # System config
```

### CLI Commands
```bash
atmosphere start              # Start node
atmosphere stop               # Stop node
atmosphere status             # Show status
atmosphere scan               # Scan for capabilities
atmosphere approve            # Open approval UI
atmosphere join <token>       # Join mesh with token
atmosphere invite             # Generate invite token
atmosphere mesh               # Show mesh topology
atmosphere route <intent>     # Test routing
atmosphere cost               # Show current cost factors
atmosphere config             # Edit config
atmosphere logs               # View logs
atmosphere ui                 # Open web UI
```

### Packaging Tasks
| Task | Effort | Priority |
|------|--------|----------|
| PyPI package (`pip install atmosphere-mesh`) | 1 day | P0 |
| Homebrew formula | 4 hours | P1 |
| Debian package | 1 day | P1 |
| AppImage for Linux | 4 hours | P2 |
| Docker image | 4 hours | P1 |
| Windows installer | 2 days | P3 |

---

## Part 3: Dynamic Cost Model

### Why Cost Matters

The mesh needs to route work to the **best** node, not just any capable node. "Best" means:
- Lowest latency for time-sensitive work
- Lowest cost for bulk work
- Highest quality for precision work

### Cost Factors

```python
@dataclass
class NodeCost:
    """Dynamic cost model for a node."""
    
    # Power state
    on_battery: bool = False
    battery_percent: float = 100.0
    
    # Compute availability
    cpu_load: float = 0.0          # 0.0 - 1.0
    gpu_load: float = 0.0          # 0.0 - 1.0
    memory_pressure: float = 0.0   # 0.0 - 1.0
    
    # Network
    bandwidth_mbps: float = 1000.0
    latency_ms: float = 1.0
    is_metered: bool = False       # Cell connection
    
    # Cloud API costs (real $$$)
    api_costs: Dict[str, float] = field(default_factory=dict)
    # e.g., {"openai/gpt-4": 0.03, "anthropic/claude": 0.015}
    
    def compute_cost(self, work_type: str) -> float:
        """Calculate cost score for this work type."""
        base_cost = 1.0
        
        # Battery penalty (2x cost when on battery)
        if self.on_battery:
            base_cost *= 2.0
            if self.battery_percent < 20:
                base_cost *= 5.0  # Critical battery
        
        # Load penalty
        if work_type in ["inference", "training"]:
            base_cost *= (1 + self.gpu_load * 2)
        else:
            base_cost *= (1 + self.cpu_load)
        
        # Memory pressure
        base_cost *= (1 + self.memory_pressure)
        
        # Network penalty for metered connections
        if self.is_metered:
            base_cost *= 3.0
        
        # Add actual API cost if applicable
        if work_type in self.api_costs:
            base_cost += self.api_costs[work_type] * 100  # Scale to match
        
        return base_cost
```

### Cost Broadcast

Nodes broadcast cost updates via gossip:
```yaml
type: NODE_COST_UPDATE
node_id: rob-mac
timestamp: 1770080000
cost_factors:
  on_battery: false
  battery_percent: 100
  cpu_load: 0.3
  gpu_load: 0.1
  memory_pressure: 0.2
  bandwidth_mbps: 1000
  is_metered: false
  overall_cost: 1.2  # Pre-computed
ttl: 60  # Refresh every 60s
```

### Routing with Cost

```python
def select_best_node(intent: Intent, candidates: List[Node]) -> Node:
    """Select best node considering capability AND cost."""
    
    scored = []
    for node in candidates:
        # Capability score (0-1, from semantic matching)
        capability_score = match_capability(intent, node)
        
        # Cost score (lower is better)
        cost_score = node.cost.compute_cost(intent.work_type)
        
        # Combined score (capability matters more)
        # High capability + low cost = high score
        combined = (capability_score * 0.7) - (cost_score * 0.3)
        scored.append((node, combined))
    
    return max(scored, key=lambda x: x[1])[0]
```

### Cost Implementation Tasks
| Task | Effort | Priority |
|------|--------|----------|
| Power state detection (macOS/Linux) | 4 hours | P1 |
| GPU/CPU load monitoring | 4 hours | P1 |
| Network bandwidth/type detection | 4 hours | P2 |
| Cost gossip messages | 2 hours | P1 |
| Routing with cost | 4 hours | P1 |
| Cloud API cost tracking | 1 day | P2 |

---

## Part 4: Android App

### Vision

A lightweight Android app that:
1. Joins a mesh with an invite token
2. Contributes phone capabilities (camera, mic, location, sensors)
3. Can run small models on-device (Llama.cpp)
4. Routes work to more capable nodes when needed

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     ANDROID APP                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   Camera    │  │    Mic      │  │   Sensors   │            │
│  │  Capability │  │ Capability  │  │ (GPS, etc)  │            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         │                │                │                    │
│         └────────────────┼────────────────┘                    │
│                          ▼                                      │
│                 ┌─────────────────┐                            │
│                 │   Atmosphere    │                            │
│                 │   Core (Rust)   │                            │
│                 └────────┬────────┘                            │
│                          │                                      │
│         ┌────────────────┼────────────────┐                    │
│         ▼                ▼                ▼                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   Llama.cpp │  │   Whisper   │  │   WebSocket │            │
│  │  (on-device)│  │  (on-device)│  │   (mesh)    │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Android Capabilities

| Capability | Type | Triggers | Tools |
|------------|------|----------|-------|
| Camera | sensor/camera | photo_taken, qr_scanned | take_photo, scan_qr |
| Microphone | audio/capture | recording_complete | start_recording, stop |
| Location | sensor/location | location_changed, geofence | get_location |
| Sensors | sensor/motion | shake_detected, orientation | get_accel, get_gyro |
| On-device LLM | llm/chat | - | chat (small models) |
| On-device STT | audio/transcribe | transcription_done | transcribe |

### Tech Stack

```
Android App:
├── Kotlin (main app)
├── Jetpack Compose (UI)
├── llama.cpp (JNI wrapper) - On-device inference
├── whisper.cpp (JNI wrapper) - On-device transcription
├── OkHttp/Ktor - WebSocket for mesh
└── Rust Core (via JNI) - Atmosphere protocol
```

### MVP Features

1. **Join Mesh**
   - Scan QR code or paste invite token
   - Connect via WebSocket relay
   
2. **Camera Capability**
   - Take photo on request (tool)
   - Fire trigger when photo taken
   
3. **Location Capability**
   - Get current location (tool)
   - Geofence triggers
   
4. **Basic Inference**
   - Run TinyLlama or Phi-3-mini on device
   - Route larger requests to mesh

### Android Tasks
| Task | Effort | Priority |
|------|--------|----------|
| Android project setup (Kotlin + Compose) | 1 day | P1 |
| Atmosphere core (Rust → JNI) | 3 days | P1 |
| WebSocket mesh connection | 1 day | P1 |
| Camera capability | 1 day | P2 |
| Location capability | 4 hours | P2 |
| llama.cpp integration | 2 days | P2 |
| QR code invite scanning | 4 hours | P2 |
| UI (join, status, capabilities) | 2 days | P2 |

---

## Part 5: Matter Integration

### Why Matter?

Matter is the universal smart home protocol. Integrating with Matter means:
- Every Matter device becomes a mesh capability
- Lights, locks, thermostats, sensors become tools/triggers
- No per-brand integration needed

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    MATTER BRIDGE                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │  Matter     │     │  Atmosphere │     │   Mesh      │       │
│  │  Controller │ ──▶ │   Bridge    │ ──▶ │   Router    │       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│        │                   │                                    │
│        ▼                   ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Matter Devices                        │   │
│  │  💡 Lights    🔒 Locks    🌡️ Thermostats    🚪 Sensors  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Matter → Atmosphere Mapping

| Matter Device | Capability Type | Triggers | Tools |
|---------------|-----------------|----------|-------|
| Light | iot/light | - | on, off, set_brightness, set_color |
| Lock | iot/lock | locked, unlocked, tamper | lock, unlock, get_status |
| Thermostat | iot/hvac | temp_reached, mode_changed | set_temp, get_temp, set_mode |
| Contact Sensor | sensor/contact | opened, closed | get_status |
| Motion Sensor | sensor/motion | motion_detected | get_status |
| Temperature Sensor | sensor/temperature | threshold_crossed | get_reading |

### Implementation

```python
class MatterBridge:
    """Bridges Matter devices to Atmosphere capabilities."""
    
    def __init__(self, controller_url: str):
        self.controller = MatterController(controller_url)
        self.registry = get_registry()
    
    async def discover_and_register(self):
        """Discover Matter devices and register as capabilities."""
        devices = await self.controller.discover()
        
        for device in devices:
            capability = self.device_to_capability(device)
            await self.registry.register(capability)
    
    def device_to_capability(self, device: MatterDevice) -> Capability:
        """Convert Matter device to Atmosphere capability."""
        
        # Map Matter clusters to tools/triggers
        tools = []
        triggers = []
        
        if device.has_cluster("OnOff"):
            tools.extend([
                Tool("on", "Turn on"),
                Tool("off", "Turn off"),
                Tool("toggle", "Toggle state"),
            ])
            
        if device.has_cluster("LevelControl"):
            tools.append(Tool("set_level", "Set brightness 0-100"))
            
        if device.has_cluster("DoorLock"):
            tools.extend([
                Tool("lock", "Lock door"),
                Tool("unlock", "Unlock door"),
            ])
            triggers.extend([
                Trigger("locked", "Door was locked"),
                Trigger("unlocked", "Door was unlocked"),
                Trigger("tamper", "Tamper detected", priority="critical"),
            ])
        
        return Capability(
            id=f"matter/{device.id}",
            type=self.get_capability_type(device),
            node_id=self.node_id,
            tools=tools,
            triggers=triggers,
            metadata={
                "matter_id": device.id,
                "manufacturer": device.manufacturer,
                "model": device.model,
                "location": device.location,
            }
        )
```

### Matter Tasks
| Task | Effort | Priority |
|------|--------|----------|
| Matter SDK integration (chip-tool or matter.js) | 2 days | P2 |
| Device discovery | 1 day | P2 |
| Device → Capability mapping | 1 day | P2 |
| Tool execution (device commands) | 1 day | P2 |
| Trigger subscription (device events) | 1 day | P2 |
| Matter bridge daemon | 1 day | P2 |

---

## Part 6: Auto-Capability Detection

### Goal

App should automatically detect what this device CAN do:

```
$ atmosphere scan

🔍 Scanning system capabilities...

Hardware:
  ✅ GPU: NVIDIA RTX 4090 (24GB VRAM)
     └─ Can run: 70B models (Q4), image generation, training
  ✅ NPU: Apple Neural Engine (16 cores)
     └─ Can run: CoreML models, on-device whisper
  ✅ Camera: Logitech C920
     └─ Can provide: 1080p video, snapshots
  ✅ Microphone: Blue Yeti
     └─ Can provide: audio capture, voice commands

Models:
  ✅ Ollama: 26 models installed
     └─ llama3.2:latest, qwen3:1.7b, codellama:7b, ...
  ✅ LlamaFarm: 103 projects
     └─ default/llama-expert-14, default/fishing-assistant, ...
  ✅ HuggingFace Cache: 15 models
     └─ bert-base-uncased, whisper-small, clip-vit-base, ...

Services:
  ✅ Ollama API (localhost:11434)
  ✅ LlamaFarm API (localhost:14345)
  ⚠️  No image generation service detected

Capability Tests:
  ✅ Can run transformers (tested: bert-base)
  ✅ Can run whisper (tested: tiny model)
  ❌ Cannot run SDXL (insufficient VRAM)
  ✅ Can capture camera (tested: snapshot)
  ✅ Can capture audio (tested: 1s recording)

Recommended capabilities to expose:
  - llm/chat (via Ollama + LlamaFarm)
  - audio/transcribe (via Whisper)
  - sensor/camera (via Logitech)
  - vision/classify (via CLIP)
```

### Detection Methods

```python
class CapabilityDetector:
    """Detects what this system can do."""
    
    async def detect_gpu(self) -> Optional[GPUInfo]:
        """Detect GPU capabilities."""
        # Try CUDA
        try:
            import torch
            if torch.cuda.is_available():
                return GPUInfo(
                    type="cuda",
                    name=torch.cuda.get_device_name(),
                    vram_gb=torch.cuda.get_device_properties(0).total_memory / 1e9,
                    compute_capability=torch.cuda.get_device_capability(),
                )
        except ImportError:
            pass
        
        # Try Metal (macOS)
        try:
            import torch
            if torch.backends.mps.is_available():
                return GPUInfo(type="mps", name="Apple Silicon", vram_gb=None)
        except:
            pass
        
        return None
    
    async def detect_models(self) -> List[ModelInfo]:
        """Detect available models."""
        models = []
        
        # Ollama
        try:
            r = await httpx.get("http://localhost:11434/api/tags")
            for m in r.json().get("models", []):
                models.append(ModelInfo(
                    source="ollama",
                    name=m["name"],
                    size_gb=m.get("size", 0) / 1e9,
                ))
        except:
            pass
        
        # LlamaFarm
        try:
            r = await httpx.get("http://localhost:14345/v1/projects")
            for p in r.json().get("projects", []):
                models.append(ModelInfo(
                    source="llamafarm",
                    name=f"{p['namespace']}/{p['name']}",
                ))
        except:
            pass
        
        # HuggingFace cache
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        if hf_cache.exists():
            for model_dir in hf_cache.glob("models--*"):
                name = model_dir.name.replace("models--", "").replace("--", "/")
                models.append(ModelInfo(source="huggingface", name=name))
        
        return models
    
    async def test_capability(self, cap_type: str) -> bool:
        """Actually test if a capability works."""
        
        if cap_type == "transformers":
            try:
                from transformers import pipeline
                classifier = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
                result = classifier("test")
                return True
            except:
                return False
        
        if cap_type == "whisper":
            try:
                import whisper
                model = whisper.load_model("tiny")
                return True
            except:
                return False
        
        if cap_type == "camera":
            try:
                import cv2
                cap = cv2.VideoCapture(0)
                ret, frame = cap.read()
                cap.release()
                return ret
            except:
                return False
        
        return False
```

### Detection Tasks
| Task | Effort | Priority |
|------|--------|----------|
| GPU detection (CUDA/ROCm/Metal/Vulkan) | 4 hours | P1 |
| Model detection (Ollama/LlamaFarm/HF) | 4 hours | P1 |
| Hardware detection (camera/mic/sensors) | 4 hours | P1 |
| Capability testing framework | 1 day | P1 |
| CLI `atmosphere scan` command | 4 hours | P1 |
| Service detection (ports, Docker) | 4 hours | P2 |

---

## Part 7: Owner Control

### Philosophy

The mesh discovers capabilities automatically, but the **owner decides** what to expose. Privacy and control are paramount.

### Control Levels

```yaml
# ~/.atmosphere/config.yaml

# What to expose to the mesh
expose:
  # Models
  models:
    ollama: 
      - llama3.2:*        # All llama3.2 variants
      - qwen3:1.7b
      # - codellama:*     # Disabled - proprietary code
    llamafarm:
      - default/public-*  # Only public projects
      # - default/private-*  # Never expose
  
  # Hardware
  hardware:
    gpu: true            # Allow GPU inference
    camera: false        # Privacy - don't expose
    microphone: whisper_only  # Only for transcription
  
  # Services
  services:
    ollama: true
    llamafarm: true
    # openai_api: false  # Don't proxy my API key
  
  # Limits
  limits:
    max_concurrent: 5
    max_vram_percent: 80
    off_battery_only: false
    
# Who can use this node
access:
  mesh_ids:
    - "mesh-family-*"    # Any family mesh
    - "mesh-work-abc123" # Specific work mesh
  require_auth: true
  
# Cost settings
cost:
  on_battery_multiplier: 3.0
  metered_connection_multiplier: 5.0
  peak_hours: "09:00-17:00"
  peak_multiplier: 1.5
```

### UI for Owner Control

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚙️  OWNER SETTINGS                                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  WHAT TO EXPOSE                                                │
│  ─────────────                                                 │
│  ☑️  Ollama Models                                             │
│      [✓] llama3.2:latest                                       │
│      [✓] qwen3:1.7b                                            │
│      [ ] codellama:34b (excluded)                              │
│                                                                 │
│  ☑️  LlamaFarm Projects                                        │
│      [Select specific projects...] (12/103 selected)           │
│                                                                 │
│  [ ] Camera (privacy concern)                                  │
│  [✓] Microphone → Transcription only                           │
│  [✓] GPU → Up to 80% VRAM                                      │
│                                                                 │
│  LIMITS                                                        │
│  ──────                                                        │
│  Max concurrent requests: [5      ]                            │
│  [ ] Only when plugged in                                      │
│  [✓] Reduce priority on battery                                │
│                                                                 │
│  ACCESS CONTROL                                                │
│  ──────────────                                                │
│  Allowed meshes:                                               │
│    [+] Add mesh ID...                                          │
│    • mesh-family-abc123 (Family)                              │
│    • mesh-work-xyz789 (Work) [Remove]                         │
│                                                                 │
│  [✓] Require authentication                                    │
│  [✓] Log all requests                                          │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  [Reset to Defaults]                        [Save Changes]     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 8: Priority Implementation Order

### Phase 1: Core Experience (2 weeks)

| Task | Effort | Owner |
|------|--------|-------|
| Local capability scanner | 2 days | - |
| Owner approval UI | 2 days | - |
| CLI packaging (PyPI) | 1 day | - |
| `atmosphere scan` command | 4 hours | - |
| `atmosphere approve` command | 4 hours | - |
| Cost model (battery/load) | 1 day | - |
| Cost-aware routing | 4 hours | - |
| Homebrew formula | 4 hours | - |

### Phase 2: Mobile & IoT (2 weeks)

| Task | Effort | Owner |
|------|--------|-------|
| Android project setup | 1 day | - |
| Atmosphere Rust core | 3 days | - |
| Android camera capability | 1 day | - |
| Android location capability | 4 hours | - |
| Matter SDK integration | 2 days | - |
| Matter device discovery | 1 day | - |
| Matter → Capability mapping | 1 day | - |

### Phase 3: Polish (1 week)

| Task | Effort | Owner |
|------|--------|-------|
| llama.cpp on Android | 2 days | - |
| Full owner control UI | 2 days | - |
| Debian/RPM packages | 1 day | - |
| Docker image | 4 hours | - |
| Documentation | 2 days | - |

---

## Summary: What's Not Done

| Area | Status | Critical? |
|------|--------|-----------|
| Local capability scanner | ❌ Not started | Yes |
| Owner approval UI | ❌ Not started | Yes |
| Packaging (pip/brew) | ❌ Not started | Yes |
| Dynamic cost model | ❌ Not started | Yes |
| Android app | ❌ Not started | Medium |
| Matter integration | ❌ Not started | Medium |
| Auto-capability testing | ❌ Not started | Yes |
| Mesh join flow (complete) | 🟡 Partial | Yes |
| LlamaFarm deep integration | 🟡 Partial | Medium |
| Agent system | 🟡 Basic | Medium |
| End-to-end workflow | 🟡 Demo only | Yes |

### The 80/20

If I had to pick the **5 most critical things**:

1. **Capability Scanner** - Can't have a mesh without knowing what's available
2. **Owner Approval UI** - Privacy and control are non-negotiable
3. **pip install** - Must be trivial to install
4. **Cost Model** - Battery/bandwidth awareness for real-world use
5. **Android App** - Phones are everywhere, huge force multiplier

---

*Document Version: 1.0*  
*Date: 2026-02-02*
