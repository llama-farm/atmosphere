# Owner Approval Design

## Overview

**Philosophy: Discovery is automatic, exposure is opt-in.**

When Atmosphere scans a device, it discovers everything: models, hardware capabilities, sensors, and tools. But discovering something doesn't mean sharing it. The owner—the human who controls the node—must explicitly approve what gets exposed to the mesh.

This is fundamentally a **consent-first** architecture:
- **Privacy by default**: Cameras, microphones, personal data stay private
- **Resource protection**: Prevent mesh abuse of expensive hardware (GPUs)
- **Access control**: Choose which meshes can see which capabilities
- **Revocable**: Change your mind anytime, instant effect

### Why This Matters

Without owner approval:
- Someone joins your mesh and suddenly has access to your webcam
- A rogue agent burns 100% of your GPU on crypto mining
- Your private Ollama models are exposed to strangers
- You can't differentiate between home mesh and work mesh

With owner approval:
- You explicitly choose: "Yes, share my Ollama models, but not the webcam"
- You set limits: "GPU available, but max 80% VRAM"
- You control access: "Only these mesh IDs can use my node"
- You can revoke instantly: "Actually, turn off microphone sharing"

---

## User Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        OWNER APPROVAL FLOW                      │
└─────────────────────────────────────────────────────────────────┘

1. SCAN
   ┌─────────────────┐
   │ atmosphere scan │
   └────────┬────────┘
            │
            ▼
   ┌─────────────────────────────────────────┐
   │ Scanner discovers:                       │
   │ • 26 Ollama models                       │
   │ • NVIDIA RTX 4090 (24GB VRAM)           │
   │ • USB Webcam (Logitech C920)            │
   │ • Microphone (Blue Yeti)                 │
   │ • LlamaFarm (14 projects)               │
   └────────┬────────────────────────────────┘
            │
            ▼
2. APPROVE
   ┌─────────────────────┐
   │ atmosphere approve  │
   │  --web (GUI)        │
   │  --cli (headless)   │
   └────────┬────────────┘
            │
   ┌────────┴────────┐
   │   Web Browser   │        ┌─────────────────┐
   │    OR           │───────▶│ Approval UI     │
   │   Terminal      │        └────────┬────────┘
   └─────────────────┘                 │
                                       ▼
3. SELECT                     ┌─────────────────┐
   Owner chooses:             │ User selects:   │
   • Which models to share    │ ✓ llama3.2      │
   • Hardware limits          │ ✓ qwen3:1.7b    │
   • Privacy settings         │ ✗ codellama:34b │
   • Access control           │ ✓ GPU (80%)     │
                              │ ✗ Webcam        │
                              └────────┬────────┘
                                       │
                                       ▼
4. SAVE                       ┌─────────────────────────┐
                              │ ~/.atmosphere/config.yaml│
                              │ (owner-controlled)       │
                              └────────┬────────────────┘
                                       │
                                       ▼
5. JOIN                       ┌─────────────────────────┐
   ┌─────────────────┐        │ Node joins mesh with    │
   │ atmosphere join │───────▶│ ONLY approved           │
   │ --token <...>   │        │ capabilities            │
   └─────────────────┘        └─────────────────────────┘
```

### State Machine

```
┌──────────┐     scan      ┌────────────┐    approve    ┌──────────┐
│          │──────────────▶│            │──────────────▶│          │
│  EMPTY   │               │ DISCOVERED │               │ APPROVED │
│          │◀──────────────│            │◀──────────────│          │
└──────────┘     clear     └────────────┘    revoke     └──────────┘
                                 │
                                 │ timeout (no action)
                                 ▼
                           ┌────────────┐
                           │  PENDING   │ (Caps discovered but not reviewed)
                           └────────────┘
```

---

## UI Mockups

### Web UI (React)

#### Main Approval Panel

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ☰ Atmosphere                                       🔴 Not Connected     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 🛡️  OWNER APPROVAL                                              │   │
│  │                                                                  │   │
│  │  Decide what this node shares with the mesh                      │   │
│  │                                                                  │   │
│  │  Scanned: 2024-02-02 19:45:32 • 47 capabilities discovered       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 🧠 LANGUAGE MODELS                                     26 total   │  │
│  │ ─────────────────────────────────────────────────────────────────│  │
│  │                                                                   │  │
│  │  ┌ Ollama Models ─────────────────────────────────────────────┐  │  │
│  │  │                                                            │  │  │
│  │  │  ☑ Select All Ollama    ○ None    ○ Popular Only          │  │  │
│  │  │                                                            │  │  │
│  │  │  ┌──────────────────────────────────────────────────────┐ │  │  │
│  │  │  │ ☑ llama3.2:latest          7B  │ ⭐ Popular          │ │  │  │
│  │  │  │ ☑ llama3.1:8b              8B  │ ⭐ Popular          │ │  │  │
│  │  │  │ ☑ qwen3:1.7b             1.7B  │ Fast                │ │  │  │
│  │  │  │ ☐ codellama:34b           34B  │ ⚠️ Large (20GB)     │ │  │  │
│  │  │  │ ☑ mistral:7b               7B  │                     │ │  │  │
│  │  │  │ ☐ mixtral:8x7b            47B  │ ⚠️ Large (26GB)     │ │  │  │
│  │  │  │ ☑ phi3:mini              3.8B  │ Fast                │ │  │  │
│  │  │  │ ☐ deepseek-coder:33b      33B  │ ⚠️ Large (18GB)     │ │  │  │
│  │  │  │     ... 18 more (click to expand)                    │ │  │  │
│  │  │  └──────────────────────────────────────────────────────┘ │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │                                                                   │  │
│  │  ┌ LlamaFarm Projects ────────────────────────────────────────┐  │  │
│  │  │                                                            │  │  │
│  │  │  ☑ anomaly-detector (3 models)                             │  │  │
│  │  │  ☑ code-assistant (5 models)                               │  │  │
│  │  │  ☐ private-research (2 models)  🔒 Marked private          │  │  │
│  │  │                                                            │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 🖥️ HARDWARE                                         4 devices    │  │
│  │ ─────────────────────────────────────────────────────────────────│  │
│  │                                                                   │  │
│  │  ┌ GPU: NVIDIA RTX 4090 ───────────────────────────────────────┐ │  │
│  │  │                                                              │ │  │
│  │  │  ☑ Share GPU for inference                                  │ │  │
│  │  │                                                              │ │  │
│  │  │  Max VRAM Usage:                                             │ │  │
│  │  │  ├────────────────────────────────┬───────┤                 │ │  │
│  │  │  0%            50%          80%   │  100%                   │ │  │
│  │  │                              ▲                               │ │  │
│  │  │                         [ 80% ]                              │ │  │
│  │  │                                                              │ │  │
│  │  │  Max Concurrent Jobs: [ 3 ▼ ]                                │ │  │
│  │  │                                                              │ │  │
│  │  └──────────────────────────────────────────────────────────────┘ │  │
│  │                                                                   │  │
│  │  ┌ CPU: Apple M3 Max ──────────────────────────────────────────┐ │  │
│  │  │  ☑ Share CPU for inference                                  │ │  │
│  │  │  Max Cores: [ 8 of 12 ▼ ]                                   │ │  │
│  │  └──────────────────────────────────────────────────────────────┘ │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 🔴 PRIVACY-SENSITIVE                               ⚠️ Careful    │  │
│  │ ─────────────────────────────────────────────────────────────────│  │
│  │                                                                   │  │
│  │  ┌ Camera: Logitech C920 HD Pro ─────────────────────────────┐   │  │
│  │  │                                                           │   │  │
│  │  │  ☐ Share camera access                                    │   │  │
│  │  │                                                           │   │  │
│  │  │  ⚠️  Warning: Enables remote frame capture                │   │  │
│  │  │     Consider: Only enable for trusted meshes              │   │  │
│  │  │                                                           │   │  │
│  │  │  If enabled:                                              │   │  │
│  │  │    ○ Still frames only (1 FPS max)                        │   │  │
│  │  │    ○ Full video stream                                    │   │  │
│  │  │                                                           │   │  │
│  │  └───────────────────────────────────────────────────────────┘   │  │
│  │                                                                   │  │
│  │  ┌ Microphone: Blue Yeti ────────────────────────────────────┐   │  │
│  │  │                                                           │   │  │
│  │  │  ○ Disabled (no audio access)                             │   │  │
│  │  │  ◉ Transcription only (audio → text, no raw audio)        │   │  │
│  │  │  ○ Full audio access                                      │   │  │
│  │  │                                                           │   │  │
│  │  │  🔒 Transcription uses local Whisper, audio never leaves  │   │  │
│  │  │                                                           │   │  │
│  │  └───────────────────────────────────────────────────────────┘   │  │
│  │                                                                   │  │
│  │  ┌ Screen Capture ───────────────────────────────────────────┐   │  │
│  │  │                                                           │   │  │
│  │  │  ☐ Allow screen sharing                                   │   │  │
│  │  │                                                           │   │  │
│  │  │  ⚠️  This exposes your desktop to mesh agents             │   │  │
│  │  │                                                           │   │  │
│  │  └───────────────────────────────────────────────────────────┘   │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 🔐 ACCESS CONTROL                                                │  │
│  │ ─────────────────────────────────────────────────────────────────│  │
│  │                                                                   │  │
│  │  Mesh Access:                                                     │  │
│  │    ◉ Allow all meshes I join                                     │  │
│  │    ○ Only specific meshes:                                       │  │
│  │                                                                   │  │
│  │      ☑ home-mesh-abc123        (3 nodes)                         │  │
│  │      ☑ work-mesh-def456        (12 nodes)                        │  │
│  │      ☐ public-test-mesh        (47 nodes) ⚠️ Public              │  │
│  │                                                                   │  │
│  │  Authentication:                                                  │  │
│  │    ☑ Require auth for capability access                          │  │
│  │    ☐ Allow anonymous queries                                     │  │
│  │                                                                   │  │
│  │  Rate Limiting:                                                   │  │
│  │    Max requests/minute: [ 60 ▼ ]                                 │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                                                                   │  │
│  │   [ Cancel ]            [ Save Draft ]        [ Apply & Join → ] │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Compact Summary View (Post-Approval)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 🛡️ Exposure Summary                                    [ Edit ✏️ ]     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ✅ Sharing                         │  🚫 Private                       │
│  ─────────────────────────────────  │  ─────────────────────────────   │
│  🧠 18 Ollama models                │  🧠 8 Ollama models               │
│  📂 2 LlamaFarm projects            │  📂 1 LlamaFarm project           │
│  🖥️ GPU (80% VRAM limit)            │  📷 Webcam                        │
│  🔊 Microphone (transcription)      │  🖥️ Screen capture                │
│  💻 CPU (8 cores)                   │                                   │
│                                                                         │
│  📊 Limits: 60 req/min • 3 concurrent GPU jobs                         │
│  🔐 Access: 2 meshes • Auth required                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### CLI UI (for Headless Servers)

Using `inquirer`-style interactive prompts:

```bash
$ atmosphere approve

┌─────────────────────────────────────────────────────────────────┐
│                     🛡️  OWNER APPROVAL                          │
│                                                                 │
│  Node: robs-macbook-m3                                          │
│  Scanned: 2024-02-02 19:45:32                                   │
│  Discovered: 47 capabilities                                    │
└─────────────────────────────────────────────────────────────────┘

? Select capabilities to expose (use arrow keys, space to toggle):

  ── 🧠 Language Models ──────────────────────────────────────────

  ◉ Ollama Models (26 available)
  │ ├─ ◉ llama3.2:latest          7B  ⭐ 
  │ ├─ ◉ llama3.1:8b              8B  ⭐
  │ ├─ ◉ qwen3:1.7b             1.7B  
  │ ├─ ◯ codellama:34b           34B  ⚠️  Large
  │ ├─ ◉ mistral:7b               7B
  │ ├─ ◯ mixtral:8x7b            47B  ⚠️  Large
  │ └─ ... 20 more (press → to expand)
  
  ◉ LlamaFarm Projects (3 available)
  │ ├─ ◉ anomaly-detector         3 models
  │ ├─ ◉ code-assistant           5 models
  │ └─ ◯ private-research         2 models  🔒

  ── 🖥️ Hardware ─────────────────────────────────────────────────

  ◉ GPU: NVIDIA RTX 4090
  │ └─ Max VRAM: [████████░░] 80%
  
  ◉ CPU: Apple M3 Max
  │ └─ Max Cores: [8 of 12]

  ── 🔴 Privacy-Sensitive ────────────────────────────────────────

  ◯ Camera: Logitech C920         ⚠️  Enables remote capture
  ◉ Microphone: Blue Yeti
  │ └─ Mode: (•) Transcription only  ( ) Full audio  ( ) Disabled
  ◯ Screen Capture                ⚠️  Exposes desktop

  ── 🔐 Access Control ───────────────────────────────────────────

  ◉ Require authentication
  ◯ Allow anonymous queries
  
  Rate limit: [60] requests/minute
  Max concurrent: [5] jobs

─────────────────────────────────────────────────────────────────

  [↑↓] Navigate  [Space] Toggle  [→] Expand  [Enter] Continue
```

#### CLI Progress Indicators

```bash
$ atmosphere approve --quick

Scanning... ████████████████████████████████ 100%

Found 47 capabilities:
  • 26 Ollama models
  • 3 LlamaFarm projects  
  • 2 hardware devices
  • 2 sensors

Apply recommended settings? (models + GPU, no cameras) [Y/n]: y

✓ Config saved to ~/.atmosphere/config.yaml
✓ 31 capabilities will be exposed
✓ 16 capabilities kept private

To join a mesh: atmosphere join --token <TOKEN>
To edit settings: atmosphere approve
```

#### Non-Interactive Mode

```bash
# Approve everything except cameras
$ atmosphere approve --all --except camera,screen

# Approve only specific items
$ atmosphere approve \
  --models "llama3.2,mistral:7b,qwen3:*" \
  --gpu --gpu-max-vram 80 \
  --no-camera \
  --microphone transcription

# Export/import configs
$ atmosphere approve --export > my-config.yaml
$ atmosphere approve --import my-config.yaml

# Show current config
$ atmosphere approve --show
```

---

## Data Model

### Config File Schema

Location: `~/.atmosphere/config.yaml`

```yaml
# Atmosphere Node Configuration
# Generated: 2024-02-02T19:45:32Z
# Node: robs-macbook-m3

version: 1

# What this node exposes to the mesh
expose:
  # Language models
  models:
    ollama:
      enabled: true
      # Explicit allow list (if empty, all discovered models exposed)
      allow:
        - llama3.2:latest
        - llama3.1:8b
        - qwen3:1.7b
        - mistral:7b
        - phi3:mini
      # Explicit deny list (takes precedence over allow)
      deny:
        - codellama:34b      # Too large
        - mixtral:8x7b       # Too large
      # Wildcard patterns
      patterns:
        allow:
          - "qwen*"          # All qwen models
          - "*:7b"           # All 7B models
        deny:
          - "*:70b"          # No 70B models
          - "*uncensored*"   # No uncensored variants
    
    llamafarm:
      enabled: true
      projects:
        allow:
          - anomaly-detector
          - code-assistant
        deny:
          - private-research

  # Hardware resources
  hardware:
    gpu:
      enabled: true
      device: "NVIDIA RTX 4090"
      limits:
        max_vram_percent: 80
        max_vram_gb: 19.2  # Calculated from percent
        max_concurrent_jobs: 3
        priority: medium    # low, medium, high (affects scheduling)
    
    cpu:
      enabled: true
      device: "Apple M3 Max"
      limits:
        max_cores: 8
        max_percent: 70
        max_concurrent_jobs: 5

  # Sensors (privacy-sensitive)
  sensors:
    camera:
      enabled: false
      # If enabled, these settings apply:
      settings:
        mode: stills        # stills | video
        max_fps: 1
        max_resolution: 720p
        require_notification: true  # Flash LED when capturing
    
    microphone:
      enabled: true
      mode: transcription   # disabled | transcription | full
      settings:
        transcription_model: whisper-small
        language: auto
        # If mode is 'transcription', raw audio never leaves node
    
    screen:
      enabled: false
      # If enabled:
      settings:
        max_fps: 1
        require_notification: true
        exclude_windows:
          - "1Password"
          - "*Private*"

  # Other tools/capabilities
  tools:
    enabled: true
    allow:
      - web_search
      - file_read
      - code_execute
    deny:
      - shell_execute    # Too dangerous
      - system_admin

# Access control
access:
  # Which meshes can access this node's capabilities
  meshes:
    mode: allowlist     # allowlist | denylist | all
    allow:
      - mesh-id-abc123  # Home mesh
      - mesh-id-def456  # Work mesh
    deny:
      - mesh-id-public  # Public test mesh
  
  # Authentication requirements
  auth:
    require: true
    methods:
      - token           # Bearer tokens
      - mtls            # Mutual TLS
    allow_anonymous: false
  
  # Rate limiting
  rate_limits:
    global:
      requests_per_minute: 60
      requests_per_hour: 1000
    per_mesh:
      requests_per_minute: 30
    per_capability:
      llm:
        requests_per_minute: 20
        max_tokens_per_request: 4096
      camera:
        requests_per_minute: 1

# Node metadata
node:
  name: "Rob's MacBook"
  description: "Primary development machine"
  location: "Home Office"
  tags:
    - personal
    - development
    - high-performance

# Audit settings
audit:
  log_all_requests: true
  log_path: ~/.atmosphere/audit.log
  retain_days: 30
```

### TypeScript Types

```typescript
// Core approval types
interface ApprovalConfig {
  version: number;
  expose: ExposureConfig;
  access: AccessConfig;
  node: NodeMetadata;
  audit: AuditConfig;
}

interface ExposureConfig {
  models: ModelExposure;
  hardware: HardwareExposure;
  sensors: SensorExposure;
  tools: ToolExposure;
}

interface ModelExposure {
  ollama: {
    enabled: boolean;
    allow: string[];
    deny: string[];
    patterns: {
      allow: string[];
      deny: string[];
    };
  };
  llamafarm: {
    enabled: boolean;
    projects: {
      allow: string[];
      deny: string[];
    };
  };
}

interface HardwareExposure {
  gpu: {
    enabled: boolean;
    device: string;
    limits: {
      max_vram_percent: number;
      max_vram_gb: number;
      max_concurrent_jobs: number;
      priority: 'low' | 'medium' | 'high';
    };
  };
  cpu: {
    enabled: boolean;
    device: string;
    limits: {
      max_cores: number;
      max_percent: number;
      max_concurrent_jobs: number;
    };
  };
}

interface SensorExposure {
  camera: {
    enabled: boolean;
    settings: {
      mode: 'stills' | 'video';
      max_fps: number;
      max_resolution: string;
      require_notification: boolean;
    };
  };
  microphone: {
    enabled: boolean;
    mode: 'disabled' | 'transcription' | 'full';
    settings: {
      transcription_model: string;
      language: string;
    };
  };
  screen: {
    enabled: boolean;
    settings: {
      max_fps: number;
      require_notification: boolean;
      exclude_windows: string[];
    };
  };
}

interface AccessConfig {
  meshes: {
    mode: 'allowlist' | 'denylist' | 'all';
    allow: string[];
    deny: string[];
  };
  auth: {
    require: boolean;
    methods: ('token' | 'mtls')[];
    allow_anonymous: boolean;
  };
  rate_limits: RateLimitConfig;
}

// Scanner output (input to approval UI)
interface ScanResult {
  timestamp: string;
  node_id: string;
  capabilities: DiscoveredCapability[];
}

interface DiscoveredCapability {
  id: string;
  type: CapabilityType;
  name: string;
  description: string;
  metadata: Record<string, any>;
  privacy_level: 'safe' | 'moderate' | 'sensitive';
  resource_cost: 'low' | 'medium' | 'high';
  recommended: boolean;
}

type CapabilityType = 
  | 'model/ollama'
  | 'model/llamafarm'
  | 'hardware/gpu'
  | 'hardware/cpu'
  | 'sensor/camera'
  | 'sensor/microphone'
  | 'sensor/screen'
  | 'tool';
```

---

## React Components

### Component Hierarchy

```
ApprovalPanel
├── ApprovalHeader
│   ├── NodeInfo
│   └── ScanStatus
├── CapabilitySelector
│   ├── ModelSection
│   │   ├── OllamaModelList
│   │   │   └── ModelItem (×n)
│   │   └── LlamaFarmProjectList
│   │       └── ProjectItem (×n)
│   ├── HardwareSection
│   │   ├── GPUConfig
│   │   │   └── ResourceSlider
│   │   └── CPUConfig
│   │       └── ResourceSlider
│   └── SensorSection
│       ├── CameraConfig
│       ├── MicrophoneConfig
│       └── ScreenConfig
├── AccessControlPanel
│   ├── MeshSelector
│   ├── AuthConfig
│   └── RateLimitConfig
├── ExposureSummary
│   ├── SharedList
│   └── PrivateList
└── ApprovalActions
    ├── CancelButton
    ├── SaveDraftButton
    └── ApplyButton
```

### Component Skeletons

#### ApprovalPanel.jsx

```jsx
import React, { useState, useEffect } from 'react';
import { Shield, RefreshCw, Save, Check, X } from 'lucide-react';
import { CapabilitySelector } from './CapabilitySelector';
import { AccessControlPanel } from './AccessControlPanel';
import { ExposureSummary } from './ExposureSummary';
import './ApprovalPanel.css';

export const ApprovalPanel = ({ onApprove, onCancel }) => {
  const [scanResult, setScanResult] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    // Fetch scan results and existing config
    Promise.all([
      fetch('/v1/scan/latest').then(r => r.json()),
      fetch('/v1/config').then(r => r.json()),
    ])
      .then(([scan, existingConfig]) => {
        setScanResult(scan);
        setConfig(existingConfig || createDefaultConfig(scan));
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to load:', err);
        setLoading(false);
      });
  }, []);

  const handleConfigChange = (path, value) => {
    setConfig(prev => {
      const updated = { ...prev };
      setNestedValue(updated, path, value);
      return updated;
    });
    setDirty(true);
  };

  const handleSave = async (apply = false) => {
    setSaving(true);
    try {
      await fetch('/v1/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });

      if (apply) {
        await fetch('/v1/mesh/refresh', { method: 'POST' });
        onApprove?.(config);
      }

      setDirty(false);
    } catch (err) {
      console.error('Save failed:', err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="approval-panel loading">
        <div className="spinner" />
        <p>Loading scan results...</p>
      </div>
    );
  }

  return (
    <div className="approval-panel fade-in">
      <div className="approval-header">
        <div className="header-icon">
          <Shield size={32} />
        </div>
        <div className="header-content">
          <h1>Owner Approval</h1>
          <p>Decide what this node shares with the mesh</p>
        </div>
        <div className="header-meta">
          <span className="scan-time">
            Scanned: {new Date(scanResult.timestamp).toLocaleString()}
          </span>
          <span className="capability-count">
            {scanResult.capabilities.length} capabilities discovered
          </span>
        </div>
      </div>

      <div className="approval-content">
        <CapabilitySelector
          capabilities={scanResult.capabilities}
          config={config.expose}
          onChange={(expose) => handleConfigChange('expose', expose)}
        />

        <AccessControlPanel
          config={config.access}
          onChange={(access) => handleConfigChange('access', access)}
        />

        <ExposureSummary
          capabilities={scanResult.capabilities}
          config={config}
        />
      </div>

      <div className="approval-actions">
        <button 
          className="action-button cancel"
          onClick={onCancel}
        >
          <X size={18} />
          Cancel
        </button>
        
        <button 
          className="action-button save"
          onClick={() => handleSave(false)}
          disabled={!dirty || saving}
        >
          <Save size={18} />
          Save Draft
        </button>
        
        <button 
          className="action-button apply"
          onClick={() => handleSave(true)}
          disabled={saving}
        >
          {saving ? (
            <>
              <RefreshCw size={18} className="spin" />
              Applying...
            </>
          ) : (
            <>
              <Check size={18} />
              Apply & Join
            </>
          )}
        </button>
      </div>
    </div>
  );
};

// Helper to set nested values
function setNestedValue(obj, path, value) {
  const parts = path.split('.');
  let current = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    current = current[parts[i]] = current[parts[i]] || {};
  }
  current[parts[parts.length - 1]] = value;
}

// Create default config from scan results
function createDefaultConfig(scan) {
  return {
    version: 1,
    expose: {
      models: {
        ollama: { enabled: true, allow: [], deny: [] },
        llamafarm: { enabled: true, projects: { allow: [], deny: [] } },
      },
      hardware: {
        gpu: { enabled: true, limits: { max_vram_percent: 80 } },
        cpu: { enabled: true, limits: { max_cores: 8 } },
      },
      sensors: {
        camera: { enabled: false },
        microphone: { enabled: true, mode: 'transcription' },
        screen: { enabled: false },
      },
    },
    access: {
      meshes: { mode: 'all' },
      auth: { require: true },
      rate_limits: { global: { requests_per_minute: 60 } },
    },
  };
}

export default ApprovalPanel;
```

#### CapabilitySelector.jsx

```jsx
import React, { useState } from 'react';
import { 
  Brain, Cpu, Gpu, Camera, Mic, Monitor,
  ChevronDown, ChevronRight, CheckSquare, Square,
  AlertTriangle, Star, Lock
} from 'lucide-react';
import { ResourceSlider } from './ResourceSlider';
import './CapabilitySelector.css';

const CATEGORY_ICONS = {
  'model': Brain,
  'hardware': Cpu,
  'sensor': Camera,
};

const PRIVACY_BADGES = {
  safe: { color: '#10b981', label: 'Safe' },
  moderate: { color: '#f59e0b', label: 'Moderate' },
  sensitive: { color: '#ef4444', label: 'Sensitive' },
};

export const CapabilitySelector = ({ capabilities, config, onChange }) => {
  const [expanded, setExpanded] = useState({
    models: true,
    hardware: true,
    sensors: false,
  });

  // Group capabilities by category
  const grouped = capabilities.reduce((acc, cap) => {
    const category = cap.type.split('/')[0];
    acc[category] = acc[category] || [];
    acc[category].push(cap);
    return acc;
  }, {});

  const toggleSection = (section) => {
    setExpanded(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const handleModelToggle = (modelId, enabled) => {
    const current = config.models.ollama;
    const newAllow = enabled
      ? [...current.allow, modelId]
      : current.allow.filter(m => m !== modelId);
    const newDeny = enabled
      ? current.deny.filter(m => m !== modelId)
      : [...current.deny, modelId];
    
    onChange({
      ...config,
      models: {
        ...config.models,
        ollama: { ...current, allow: newAllow, deny: newDeny },
      },
    });
  };

  const isModelEnabled = (modelId) => {
    const { allow, deny } = config.models.ollama;
    if (deny.includes(modelId)) return false;
    if (allow.length === 0) return true; // Default allow all
    return allow.includes(modelId);
  };

  return (
    <div className="capability-selector">
      {/* Models Section */}
      <div className="selector-section">
        <div 
          className="section-header"
          onClick={() => toggleSection('models')}
        >
          <Brain size={24} />
          <h2>Language Models</h2>
          <span className="section-count">
            {grouped.model?.length || 0} total
          </span>
          {expanded.models ? <ChevronDown /> : <ChevronRight />}
        </div>

        {expanded.models && (
          <div className="section-content slide-in">
            {/* Ollama Models */}
            <div className="model-group">
              <div className="group-header">
                <span className="group-name">Ollama Models</span>
                <div className="group-actions">
                  <button onClick={() => handleSelectAll('ollama', true)}>
                    Select All
                  </button>
                  <button onClick={() => handleSelectAll('ollama', false)}>
                    None
                  </button>
                </div>
              </div>

              <div className="model-list">
                {grouped.model
                  ?.filter(m => m.type === 'model/ollama')
                  .map(model => (
                    <ModelItem
                      key={model.id}
                      model={model}
                      enabled={isModelEnabled(model.id)}
                      onToggle={(enabled) => handleModelToggle(model.id, enabled)}
                    />
                  ))}
              </div>
            </div>

            {/* LlamaFarm Projects */}
            <div className="model-group">
              <div className="group-header">
                <span className="group-name">LlamaFarm Projects</span>
              </div>

              <div className="project-list">
                {grouped.model
                  ?.filter(m => m.type === 'model/llamafarm')
                  .map(project => (
                    <ProjectItem
                      key={project.id}
                      project={project}
                      enabled={!config.models.llamafarm.projects.deny.includes(project.id)}
                      onToggle={(enabled) => handleProjectToggle(project.id, enabled)}
                    />
                  ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Hardware Section */}
      <div className="selector-section">
        <div 
          className="section-header"
          onClick={() => toggleSection('hardware')}
        >
          <Cpu size={24} />
          <h2>Hardware</h2>
          <span className="section-count">
            {grouped.hardware?.length || 0} devices
          </span>
          {expanded.hardware ? <ChevronDown /> : <ChevronRight />}
        </div>

        {expanded.hardware && (
          <div className="section-content slide-in">
            {grouped.hardware?.map(hw => (
              <HardwareConfig
                key={hw.id}
                hardware={hw}
                config={config.hardware[hw.id.split('/')[1]]}
                onChange={(hwConfig) => {
                  onChange({
                    ...config,
                    hardware: {
                      ...config.hardware,
                      [hw.id.split('/')[1]]: hwConfig,
                    },
                  });
                }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Sensors Section */}
      <div className="selector-section privacy-sensitive">
        <div 
          className="section-header"
          onClick={() => toggleSection('sensors')}
        >
          <Camera size={24} />
          <h2>Privacy-Sensitive</h2>
          <span className="privacy-warning">
            <AlertTriangle size={16} />
            Careful
          </span>
          {expanded.sensors ? <ChevronDown /> : <ChevronRight />}
        </div>

        {expanded.sensors && (
          <div className="section-content slide-in">
            {/* Camera */}
            <SensorConfig
              sensor={grouped.sensor?.find(s => s.type === 'sensor/camera')}
              config={config.sensors.camera}
              onChange={(sensorConfig) => {
                onChange({
                  ...config,
                  sensors: { ...config.sensors, camera: sensorConfig },
                });
              }}
            />

            {/* Microphone */}
            <MicrophoneConfig
              sensor={grouped.sensor?.find(s => s.type === 'sensor/microphone')}
              config={config.sensors.microphone}
              onChange={(sensorConfig) => {
                onChange({
                  ...config,
                  sensors: { ...config.sensors, microphone: sensorConfig },
                });
              }}
            />

            {/* Screen */}
            <SensorConfig
              sensor={grouped.sensor?.find(s => s.type === 'sensor/screen')}
              config={config.sensors.screen}
              onChange={(sensorConfig) => {
                onChange({
                  ...config,
                  sensors: { ...config.sensors, screen: sensorConfig },
                });
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
};

// Sub-components
const ModelItem = ({ model, enabled, onToggle }) => (
  <div className={`model-item ${enabled ? 'enabled' : 'disabled'}`}>
    <button 
      className="toggle-button"
      onClick={() => onToggle(!enabled)}
    >
      {enabled ? <CheckSquare size={18} /> : <Square size={18} />}
    </button>
    
    <div className="model-info">
      <span className="model-name">{model.name}</span>
      <span className="model-size">{model.metadata.size}</span>
    </div>
    
    <div className="model-badges">
      {model.recommended && (
        <span className="badge popular">
          <Star size={12} /> Popular
        </span>
      )}
      {model.resource_cost === 'high' && (
        <span className="badge warning">
          <AlertTriangle size={12} /> Large
        </span>
      )}
    </div>
  </div>
);

const HardwareConfig = ({ hardware, config, onChange }) => (
  <div className="hardware-config">
    <div className="hw-header">
      <input
        type="checkbox"
        checked={config?.enabled ?? true}
        onChange={(e) => onChange({ ...config, enabled: e.target.checked })}
      />
      <span className="hw-name">{hardware.name}</span>
      <span className="hw-device">{hardware.metadata.device}</span>
    </div>
    
    {config?.enabled && (
      <div className="hw-limits">
        <ResourceSlider
          label="Max VRAM"
          value={config.limits?.max_vram_percent ?? 80}
          min={10}
          max={100}
          unit="%"
          onChange={(val) => onChange({
            ...config,
            limits: { ...config.limits, max_vram_percent: val },
          })}
        />
        
        <div className="limit-row">
          <label>Max Concurrent Jobs:</label>
          <select
            value={config.limits?.max_concurrent_jobs ?? 3}
            onChange={(e) => onChange({
              ...config,
              limits: { ...config.limits, max_concurrent_jobs: Number(e.target.value) },
            })}
          >
            {[1, 2, 3, 5, 10].map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
      </div>
    )}
  </div>
);

const MicrophoneConfig = ({ sensor, config, onChange }) => (
  <div className="sensor-config microphone">
    <div className="sensor-header">
      <Mic size={20} />
      <span className="sensor-name">{sensor?.name || 'Microphone'}</span>
    </div>
    
    <div className="microphone-modes">
      <label className="mode-option">
        <input
          type="radio"
          name="mic-mode"
          checked={!config.enabled}
          onChange={() => onChange({ enabled: false })}
        />
        <span className="mode-label">Disabled</span>
        <span className="mode-desc">No audio access</span>
      </label>
      
      <label className="mode-option recommended">
        <input
          type="radio"
          name="mic-mode"
          checked={config.enabled && config.mode === 'transcription'}
          onChange={() => onChange({ enabled: true, mode: 'transcription' })}
        />
        <span className="mode-label">Transcription Only</span>
        <span className="mode-desc">
          <Lock size={12} />
          Audio → text locally, raw audio never leaves
        </span>
      </label>
      
      <label className="mode-option warning">
        <input
          type="radio"
          name="mic-mode"
          checked={config.enabled && config.mode === 'full'}
          onChange={() => onChange({ enabled: true, mode: 'full' })}
        />
        <span className="mode-label">Full Audio</span>
        <span className="mode-desc">
          <AlertTriangle size={12} />
          Raw audio can be streamed
        </span>
      </label>
    </div>
  </div>
);

export default CapabilitySelector;
```

#### ResourceSlider.jsx

```jsx
import React from 'react';
import './ResourceSlider.css';

export const ResourceSlider = ({ 
  label, 
  value, 
  min = 0, 
  max = 100, 
  step = 5,
  unit = '%',
  onChange,
  showTicks = true,
  color = '#3b82f6'
}) => {
  const percentage = ((value - min) / (max - min)) * 100;

  return (
    <div className="resource-slider">
      <div className="slider-header">
        <span className="slider-label">{label}</span>
        <span className="slider-value" style={{ color }}>
          {value}{unit}
        </span>
      </div>
      
      <div className="slider-track-container">
        <div className="slider-track">
          <div 
            className="slider-fill"
            style={{ 
              width: `${percentage}%`,
              background: `linear-gradient(90deg, ${color}44, ${color})`,
            }}
          />
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            className="slider-input"
          />
        </div>
        
        {showTicks && (
          <div className="slider-ticks">
            <span>{min}{unit}</span>
            <span>{Math.round((max - min) / 2)}{unit}</span>
            <span>{max}{unit}</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default ResourceSlider;
```

#### AccessControlPanel.jsx

```jsx
import React from 'react';
import { Shield, Globe, Key, Clock } from 'lucide-react';
import './AccessControlPanel.css';

export const AccessControlPanel = ({ config, onChange }) => {
  return (
    <div className="access-control-panel">
      <div className="panel-header">
        <Shield size={24} />
        <h2>Access Control</h2>
      </div>

      <div className="panel-content">
        {/* Mesh Access */}
        <div className="control-section">
          <div className="section-title">
            <Globe size={18} />
            <span>Mesh Access</span>
          </div>

          <div className="radio-group">
            <label className="radio-option">
              <input
                type="radio"
                name="mesh-mode"
                checked={config.meshes.mode === 'all'}
                onChange={() => onChange({
                  ...config,
                  meshes: { ...config.meshes, mode: 'all' },
                })}
              />
              <span>Allow all meshes I join</span>
            </label>
            
            <label className="radio-option">
              <input
                type="radio"
                name="mesh-mode"
                checked={config.meshes.mode === 'allowlist'}
                onChange={() => onChange({
                  ...config,
                  meshes: { ...config.meshes, mode: 'allowlist' },
                })}
              />
              <span>Only specific meshes</span>
            </label>
          </div>

          {config.meshes.mode === 'allowlist' && (
            <div className="mesh-list">
              {/* Mesh checkboxes would be populated from known meshes */}
              <div className="mesh-item">
                <input type="checkbox" id="mesh-1" />
                <label htmlFor="mesh-1">
                  <span className="mesh-name">home-mesh-abc123</span>
                  <span className="mesh-info">3 nodes</span>
                </label>
              </div>
            </div>
          )}
        </div>

        {/* Authentication */}
        <div className="control-section">
          <div className="section-title">
            <Key size={18} />
            <span>Authentication</span>
          </div>

          <label className="checkbox-option">
            <input
              type="checkbox"
              checked={config.auth.require}
              onChange={(e) => onChange({
                ...config,
                auth: { ...config.auth, require: e.target.checked },
              })}
            />
            <span>Require auth for capability access</span>
          </label>

          <label className="checkbox-option">
            <input
              type="checkbox"
              checked={config.auth.allow_anonymous}
              onChange={(e) => onChange({
                ...config,
                auth: { ...config.auth, allow_anonymous: e.target.checked },
              })}
            />
            <span>Allow anonymous queries</span>
          </label>
        </div>

        {/* Rate Limiting */}
        <div className="control-section">
          <div className="section-title">
            <Clock size={18} />
            <span>Rate Limiting</span>
          </div>

          <div className="rate-limit-row">
            <label>Max requests/minute:</label>
            <select
              value={config.rate_limits.global.requests_per_minute}
              onChange={(e) => onChange({
                ...config,
                rate_limits: {
                  ...config.rate_limits,
                  global: {
                    ...config.rate_limits.global,
                    requests_per_minute: Number(e.target.value),
                  },
                },
              })}
            >
              {[10, 30, 60, 100, 200].map(n => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AccessControlPanel;
```

#### ExposureSummary.jsx

```jsx
import React from 'react';
import { Check, X, Brain, Cpu, Camera, Mic, Monitor, Shield } from 'lucide-react';
import './ExposureSummary.css';

export const ExposureSummary = ({ capabilities, config }) => {
  // Calculate what's exposed vs private
  const exposed = [];
  const private_ = [];

  // Models
  const ollamaModels = capabilities.filter(c => c.type === 'model/ollama');
  const exposedModels = ollamaModels.filter(m => {
    if (config.expose.models.ollama.deny.includes(m.id)) return false;
    if (config.expose.models.ollama.allow.length === 0) return true;
    return config.expose.models.ollama.allow.includes(m.id);
  });
  const privateModels = ollamaModels.filter(m => !exposedModels.includes(m));

  if (exposedModels.length > 0) {
    exposed.push({ icon: Brain, label: `${exposedModels.length} Ollama models` });
  }
  if (privateModels.length > 0) {
    private_.push({ icon: Brain, label: `${privateModels.length} Ollama models` });
  }

  // Hardware
  if (config.expose.hardware.gpu?.enabled) {
    exposed.push({ 
      icon: Cpu, 
      label: `GPU (${config.expose.hardware.gpu.limits?.max_vram_percent || 80}% VRAM limit)` 
    });
  }

  // Sensors
  if (!config.expose.sensors.camera?.enabled) {
    private_.push({ icon: Camera, label: 'Webcam' });
  }
  if (config.expose.sensors.microphone?.enabled) {
    const mode = config.expose.sensors.microphone.mode;
    exposed.push({ 
      icon: Mic, 
      label: `Microphone (${mode})` 
    });
  }
  if (!config.expose.sensors.screen?.enabled) {
    private_.push({ icon: Monitor, label: 'Screen capture' });
  }

  return (
    <div className="exposure-summary">
      <div className="summary-header">
        <Shield size={20} />
        <h3>Exposure Summary</h3>
        <button className="edit-button">Edit ✏️</button>
      </div>

      <div className="summary-columns">
        <div className="summary-column exposed">
          <h4>
            <Check size={16} />
            Sharing
          </h4>
          <ul>
            {exposed.map((item, i) => (
              <li key={i}>
                <item.icon size={14} />
                <span>{item.label}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="summary-column private">
          <h4>
            <X size={16} />
            Private
          </h4>
          <ul>
            {private_.map((item, i) => (
              <li key={i}>
                <item.icon size={14} />
                <span>{item.label}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="summary-footer">
        <div className="summary-stat">
          📊 Limits: {config.access.rate_limits.global.requests_per_minute} req/min 
          • {config.expose.hardware.gpu?.limits?.max_concurrent_jobs || 3} concurrent GPU jobs
        </div>
        <div className="summary-stat">
          🔐 Access: {config.access.meshes.mode === 'all' ? 'All meshes' : `${config.access.meshes.allow?.length || 0} meshes`}
          • Auth {config.access.auth.require ? 'required' : 'optional'}
        </div>
      </div>
    </div>
  );
};

export default ExposureSummary;
```

---

## CLI Implementation

### Using Inquirer.js

```javascript
// cli/approve.js
import inquirer from 'inquirer';
import chalk from 'chalk';
import ora from 'ora';
import yaml from 'js-yaml';
import fs from 'fs/promises';
import path from 'path';

const CONFIG_PATH = path.join(process.env.HOME, '.atmosphere', 'config.yaml');

export async function runApprovalCLI(options = {}) {
  console.log(chalk.bold.cyan('\n🛡️  OWNER APPROVAL\n'));

  // Load scan results
  const spinner = ora('Loading scan results...').start();
  const scanResult = await loadScanResults();
  spinner.succeed(`Found ${scanResult.capabilities.length} capabilities`);

  // Load existing config or create default
  let config = await loadOrCreateConfig(scanResult);

  if (options.quick) {
    // Quick mode - apply recommended settings
    return await quickApprove(scanResult, config);
  }

  // Interactive mode
  const { section } = await inquirer.prompt([
    {
      type: 'list',
      name: 'section',
      message: 'What would you like to configure?',
      choices: [
        { name: '🧠 Language Models', value: 'models' },
        { name: '🖥️ Hardware', value: 'hardware' },
        { name: '🔴 Privacy-Sensitive', value: 'sensors' },
        { name: '🔐 Access Control', value: 'access' },
        { name: '📋 Review & Apply', value: 'review' },
        new inquirer.Separator(),
        { name: '💾 Save & Exit', value: 'save' },
        { name: '❌ Cancel', value: 'cancel' },
      ],
    },
  ]);

  switch (section) {
    case 'models':
      config = await configureModels(scanResult, config);
      break;
    case 'hardware':
      config = await configureHardware(scanResult, config);
      break;
    case 'sensors':
      config = await configureSensors(scanResult, config);
      break;
    case 'access':
      config = await configureAccess(config);
      break;
    case 'review':
      await reviewAndApply(scanResult, config);
      return;
    case 'save':
      await saveConfig(config);
      return;
    case 'cancel':
      console.log(chalk.yellow('\nCancelled. No changes made.\n'));
      return;
  }

  // Loop back
  return runApprovalCLI(options);
}

async function configureModels(scanResult, config) {
  const ollamaModels = scanResult.capabilities
    .filter(c => c.type === 'model/ollama')
    .map(m => ({
      name: `${m.name} (${m.metadata.size})${m.recommended ? ' ⭐' : ''}${m.resource_cost === 'high' ? ' ⚠️ Large' : ''}`,
      value: m.id,
      checked: !config.expose.models.ollama.deny.includes(m.id),
    }));

  const { selectedModels } = await inquirer.prompt([
    {
      type: 'checkbox',
      name: 'selectedModels',
      message: 'Select Ollama models to expose:',
      choices: ollamaModels,
      pageSize: 15,
    },
  ]);

  // Update config
  const allModelIds = ollamaModels.map(m => m.value);
  config.expose.models.ollama.allow = selectedModels;
  config.expose.models.ollama.deny = allModelIds.filter(id => !selectedModels.includes(id));

  console.log(chalk.green(`\n✓ ${selectedModels.length} models will be exposed\n`));

  return config;
}

async function configureHardware(scanResult, config) {
  const gpuCap = scanResult.capabilities.find(c => c.type === 'hardware/gpu');

  if (gpuCap) {
    const { gpuEnabled, maxVram, maxJobs } = await inquirer.prompt([
      {
        type: 'confirm',
        name: 'gpuEnabled',
        message: `Share GPU (${gpuCap.metadata.device})?`,
        default: config.expose.hardware.gpu?.enabled ?? true,
      },
      {
        type: 'list',
        name: 'maxVram',
        message: 'Maximum VRAM usage:',
        choices: [
          { name: '50%', value: 50 },
          { name: '70%', value: 70 },
          { name: '80% (recommended)', value: 80 },
          { name: '90%', value: 90 },
          { name: '100% (full)', value: 100 },
        ],
        default: 2, // 80%
        when: (answers) => answers.gpuEnabled,
      },
      {
        type: 'list',
        name: 'maxJobs',
        message: 'Maximum concurrent GPU jobs:',
        choices: [1, 2, 3, 5, 10],
        default: 2, // 3
        when: (answers) => answers.gpuEnabled,
      },
    ]);

    config.expose.hardware.gpu = {
      enabled: gpuEnabled,
      device: gpuCap.metadata.device,
      limits: gpuEnabled ? {
        max_vram_percent: maxVram,
        max_concurrent_jobs: maxJobs,
      } : undefined,
    };
  }

  return config;
}

async function configureSensors(scanResult, config) {
  console.log(chalk.yellow('\n⚠️  Privacy-Sensitive Settings\n'));

  const { cameraEnabled } = await inquirer.prompt([
    {
      type: 'confirm',
      name: 'cameraEnabled',
      message: chalk.red('Share camera access?') + ' (enables remote capture)',
      default: false,
    },
  ]);

  const { micMode } = await inquirer.prompt([
    {
      type: 'list',
      name: 'micMode',
      message: 'Microphone access:',
      choices: [
        { name: 'Disabled (no audio access)', value: 'disabled' },
        { 
          name: chalk.green('Transcription only') + ' (audio→text locally, raw audio never leaves)', 
          value: 'transcription' 
        },
        { 
          name: chalk.yellow('Full audio') + ' (raw audio can be streamed)', 
          value: 'full' 
        },
      ],
      default: 1, // transcription
    },
  ]);

  const { screenEnabled } = await inquirer.prompt([
    {
      type: 'confirm',
      name: 'screenEnabled',
      message: chalk.red('Allow screen sharing?') + ' (exposes desktop to mesh)',
      default: false,
    },
  ]);

  config.expose.sensors = {
    camera: { enabled: cameraEnabled },
    microphone: { 
      enabled: micMode !== 'disabled', 
      mode: micMode === 'disabled' ? undefined : micMode,
    },
    screen: { enabled: screenEnabled },
  };

  return config;
}

async function reviewAndApply(scanResult, config) {
  console.log(chalk.bold.cyan('\n📋 Configuration Summary\n'));

  // Count exposed items
  const exposedModels = config.expose.models.ollama.allow.length || 
    (scanResult.capabilities.filter(c => c.type === 'model/ollama').length - 
     config.expose.models.ollama.deny.length);

  console.log(chalk.green('✓ Sharing:'));
  console.log(`  • ${exposedModels} Ollama models`);
  if (config.expose.hardware.gpu?.enabled) {
    console.log(`  • GPU (${config.expose.hardware.gpu.limits?.max_vram_percent || 80}% VRAM limit)`);
  }
  if (config.expose.sensors.microphone?.enabled) {
    console.log(`  • Microphone (${config.expose.sensors.microphone.mode})`);
  }

  console.log(chalk.red('\n🚫 Private:'));
  const privateModels = config.expose.models.ollama.deny.length;
  if (privateModels > 0) console.log(`  • ${privateModels} Ollama models`);
  if (!config.expose.sensors.camera?.enabled) console.log('  • Webcam');
  if (!config.expose.sensors.screen?.enabled) console.log('  • Screen capture');

  const { confirm } = await inquirer.prompt([
    {
      type: 'confirm',
      name: 'confirm',
      message: 'Apply this configuration?',
      default: true,
    },
  ]);

  if (confirm) {
    const spinner = ora('Saving configuration...').start();
    await saveConfig(config);
    spinner.succeed('Configuration saved');

    console.log(chalk.green('\n✓ Config saved to ~/.atmosphere/config.yaml'));
    console.log(chalk.cyan('\nTo join a mesh: atmosphere join --token <TOKEN>\n'));
  }
}

async function saveConfig(config) {
  const configDir = path.dirname(CONFIG_PATH);
  await fs.mkdir(configDir, { recursive: true });
  await fs.writeFile(CONFIG_PATH, yaml.dump(config), 'utf8');
}

async function loadOrCreateConfig(scanResult) {
  try {
    const content = await fs.readFile(CONFIG_PATH, 'utf8');
    return yaml.load(content);
  } catch {
    // Return default config
    return {
      version: 1,
      expose: {
        models: {
          ollama: { enabled: true, allow: [], deny: [] },
          llamafarm: { enabled: true, projects: { allow: [], deny: [] } },
        },
        hardware: {
          gpu: { enabled: true, limits: { max_vram_percent: 80, max_concurrent_jobs: 3 } },
        },
        sensors: {
          camera: { enabled: false },
          microphone: { enabled: true, mode: 'transcription' },
          screen: { enabled: false },
        },
      },
      access: {
        meshes: { mode: 'all' },
        auth: { require: true },
        rate_limits: { global: { requests_per_minute: 60 } },
      },
    };
  }
}
```

---

## Integration Points

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        INTEGRATION ARCHITECTURE                          │
└─────────────────────────────────────────────────────────────────────────┘

                            ┌─────────────────┐
                            │  atmosphere     │
                            │    scan         │
                            └────────┬────────┘
                                     │
                                     ▼
                   ┌─────────────────────────────────┐
                   │          SCAN RESULTS           │
                   │                                 │
                   │  {                              │
                   │    capabilities: [...],        │
                   │    timestamp: "...",           │
                   │    node_id: "..."              │
                   │  }                              │
                   └─────────────┬───────────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              │                                     │
              ▼                                     ▼
    ┌─────────────────┐                  ┌─────────────────┐
    │  Web Approval   │                  │  CLI Approval   │
    │  (React UI)     │                  │  (Inquirer)     │
    └────────┬────────┘                  └────────┬────────┘
             │                                    │
             └──────────────┬─────────────────────┘
                            │
                            ▼
              ┌─────────────────────────────────┐
              │       OWNER CONFIG              │
              │  ~/.atmosphere/config.yaml      │
              │                                 │
              │  expose:                        │
              │    models: {...}                │
              │    hardware: {...}              │
              │    sensors: {...}               │
              │  access: {...}                  │
              └─────────────┬───────────────────┘
                            │
                            ▼
              ┌─────────────────────────────────┐
              │      CAPABILITY FILTER          │
              │                                 │
              │  Input: scan results + config   │
              │  Output: approved capabilities  │
              │                                 │
              │  - Apply allow/deny lists       │
              │  - Apply resource limits        │
              │  - Apply access control         │
              └─────────────┬───────────────────┘
                            │
                            ▼
              ┌─────────────────────────────────┐
              │        MESH REGISTRY            │
              │                                 │
              │  Register ONLY approved caps    │
              │  with configured limits         │
              │                                 │
              │  Gossip: "I have these caps"    │
              └─────────────────────────────────┘
```

### API Endpoints

```yaml
# Scanner API
GET /v1/scan/latest
  → Returns most recent scan results

POST /v1/scan/run
  → Triggers new scan
  → Returns scan results

# Config API
GET /v1/config
  → Returns current config

PUT /v1/config
  → Updates config
  → Body: ApprovalConfig

POST /v1/config/validate
  → Validates config without saving

# Approval UI
GET /v1/approve
  → Returns approval UI HTML (for web)

# Mesh Integration
POST /v1/mesh/refresh
  → Re-registers with mesh using current config
  → Called after config changes
```

### Config Persistence

```typescript
// Config watcher for hot-reload
import chokidar from 'chokidar';

const CONFIG_PATH = '~/.atmosphere/config.yaml';

export function watchConfig(onConfigChange: (config: ApprovalConfig) => void) {
  const watcher = chokidar.watch(CONFIG_PATH);
  
  watcher.on('change', async () => {
    const config = await loadConfig();
    const validated = await validateConfig(config);
    if (validated.valid) {
      onConfigChange(validated.config);
    } else {
      console.error('Invalid config:', validated.errors);
    }
  });

  return watcher;
}
```

---

## Implementation Plan

### Phase 1: Core Foundation (Week 1)
| Task | Effort | Priority |
|------|--------|----------|
| Define TypeScript types | 2h | P0 |
| Create config schema (YAML) | 2h | P0 |
| Config load/save utilities | 3h | P0 |
| Config validation | 3h | P0 |
| CLI `approve --show` command | 2h | P0 |

### Phase 2: CLI Implementation (Week 1-2)
| Task | Effort | Priority |
|------|--------|----------|
| Interactive model selection | 4h | P0 |
| Hardware configuration | 3h | P0 |
| Sensor configuration | 3h | P0 |
| Access control configuration | 3h | P1 |
| `approve --quick` mode | 2h | P1 |
| `approve --export/--import` | 2h | P2 |

### Phase 3: Web UI (Week 2-3)
| Task | Effort | Priority |
|------|--------|----------|
| ApprovalPanel component | 6h | P0 |
| CapabilitySelector component | 6h | P0 |
| ResourceSlider component | 2h | P0 |
| AccessControlPanel component | 4h | P1 |
| ExposureSummary component | 3h | P1 |
| CSS styling | 4h | P1 |
| WebSocket real-time updates | 3h | P2 |

### Phase 4: Integration (Week 3)
| Task | Effort | Priority |
|------|--------|----------|
| Scanner → Approval flow | 4h | P0 |
| Approval → Registry filter | 4h | P0 |
| Config hot-reload | 3h | P1 |
| API endpoints | 4h | P1 |
| End-to-end testing | 4h | P0 |

### Phase 5: Polish (Week 4)
| Task | Effort | Priority |
|------|--------|----------|
| Error handling | 3h | P1 |
| Help text and documentation | 3h | P1 |
| Keyboard shortcuts (CLI) | 2h | P2 |
| Accessibility (Web) | 3h | P2 |
| Performance optimization | 2h | P2 |

### Total Estimated Effort
- **Phase 1**: ~12 hours
- **Phase 2**: ~17 hours  
- **Phase 3**: ~28 hours
- **Phase 4**: ~19 hours
- **Phase 5**: ~13 hours
- **Total**: ~89 hours (~2-3 weeks for one developer)

---

## Design Considerations

### For Technical Users
- Full YAML config access
- Wildcard patterns for model selection
- CLI flags for automation
- Export/import for backup
- Verbose logging option

### For Non-Technical Users
- Clear visual hierarchy (safe → sensitive)
- Privacy warnings with explanations
- "Quick" mode with safe defaults
- Summary view shows impact
- Undo/revert capability

### Accessibility
- Keyboard navigation (CLI + Web)
- Screen reader support
- Color-blind friendly indicators
- High contrast mode option

### Security
- Config file permissions (600)
- No sensitive data in config (tokens stored separately)
- Audit logging of changes
- Validation before apply

---

## Future Enhancements

1. **Per-mesh configurations**: Different exposure rules for different meshes
2. **Time-based rules**: "Share GPU only 9am-5pm"
3. **Usage analytics**: "This model was requested 47 times today"
4. **Recommendation engine**: "Based on your usage, consider enabling..."
5. **Remote approval**: Approve changes via mobile notification
6. **Config templates**: "Development setup", "Production server", "Private workstation"
7. **Capability dependencies**: "Enabling vision requires camera access"
8. **Cost estimation**: "At current usage, this would cost ~$X/month"
