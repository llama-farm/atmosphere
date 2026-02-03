# Capability Scanner Design

## Overview

The Capability Scanner is a core component of Atmosphere that automatically discovers what capabilities exist on a device and makes them available to the capability registry. Instead of requiring manual configuration, Atmosphere should "just know" what a node can do.

### Why It Matters

In the Internet of Intent, capabilities find work, and work finds capabilities. But before capabilities can be discovered by the mesh, they need to be discovered **locally**. A node joining the Atmosphere network should:

1. **Auto-detect** available hardware (GPU, camera, mic)
2. **Find** installed models (Ollama, HuggingFace, GGUF files)
3. **Discover** running services (Docker containers, APIs)
4. **Test** that capabilities actually work (not just exist)
5. **Register** working capabilities with the local registry
6. **Announce** capabilities to the mesh via gossip

The scanner bridges the gap between "what's installed" and "what capabilities are available."

### Design Goals

1. **Zero Configuration** - Works out of the box on macOS and Linux
2. **Fast** - Full scan completes in < 5 seconds
3. **Safe** - Read-only detection, no side effects
4. **Accurate** - Actually test capabilities, don't just check for existence
5. **Extensible** - Easy to add new detection methods
6. **Cross-Platform** - macOS and Linux first, Windows later

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Capability Scanner                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  GPU Scanner │  │Model Scanner │  │Hardware Scan │          │
│  │              │  │              │  │              │          │
│  │ • Metal      │  │ • Ollama     │  │ • Camera     │          │
│  │ • CUDA       │  │ • HuggingFace│  │ • Microphone │          │
│  │ • ROCm       │  │ • GGUF files │  │ • Speakers   │          │
│  │ • Vulkan     │  │ • LlamaFarm  │  │              │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│  ┌──────┴─────────────────┴─────────────────┴───────┐          │
│  │              Service Scanner                      │          │
│  │                                                   │          │
│  │  • Port probing (11434, 14345, 8000, etc.)       │          │
│  │  • Docker container discovery                     │          │
│  │  • Systemd unit detection (Linux)                │          │
│  │  • LaunchAgent detection (macOS)                 │          │
│  └──────────────────────┬────────────────────────────┘          │
│                         │                                       │
│  ┌──────────────────────┴────────────────────────────┐          │
│  │              Capability Tester                     │          │
│  │                                                   │          │
│  │  • GPU: Run inference test                        │          │
│  │  • Camera: Capture single frame                   │          │
│  │  • Model: Generate single token                   │          │
│  │  • Service: Health check endpoint                 │          │
│  └──────────────────────┬────────────────────────────┘          │
│                         │                                       │
│  ┌──────────────────────┴────────────────────────────┐          │
│  │              Capability Registry                   │          │
│  │                                                   │          │
│  │  • Register discovered capabilities               │          │
│  │  • Generate capability definitions                │          │
│  │  • Emit gossip messages                          │          │
│  └───────────────────────────────────────────────────┘          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Input | Output |
|-----------|-------|--------|
| GPU Scanner | System APIs | `ScanResult[GPU]` with device info, memory, compute units |
| Model Scanner | File system, HTTP APIs | `ScanResult[Model]` with model name, size, quantization |
| Hardware Scanner | OS APIs, ffmpeg | `ScanResult[Hardware]` with device list |
| Service Scanner | Network ports, process list | `ScanResult[Service]` with endpoints |
| Capability Tester | `ScanResult` | `TestedCapability` with pass/fail status |
| Registry | `TestedCapability` | `Capability` objects registered to mesh |

---

## Permission Pre-flight (macOS)

> **⚠️ CRITICAL:** On macOS, accessing hardware like cameras and microphones requires 
> TCC (Transparency, Consent, and Control) permissions. Attempting to access these 
> without permission will cause the app to **crash or hang**, not gracefully fail.

### TCC Permission Check

Before scanning hardware capabilities, check permissions first:

```python
import subprocess
import platform
from dataclasses import dataclass
from typing import Dict
import logging

logger = logging.getLogger(__name__)

@dataclass
class PermissionStatus:
    """Status of a TCC permission."""
    granted: bool
    can_request: bool
    note: str = ""

def check_macos_permissions() -> Dict[str, PermissionStatus]:
    """
    Check TCC permissions before attempting hardware access.
    
    IMPORTANT: This checks permission STATUS, not capability.
    A device may have a camera but the app lacks permission to use it.
    
    Returns dict of permission statuses for each hardware type.
    """
    if platform.system() != "Darwin":
        # Non-macOS: assume permissions are handled at runtime
        return {
            "camera": PermissionStatus(True, False),
            "microphone": PermissionStatus(True, False),
            "screen_recording": PermissionStatus(True, False),
            "accessibility": PermissionStatus(True, False),
        }
    
    return {
        "camera": _check_camera_permission(),
        "microphone": _check_microphone_permission(),
        "screen_recording": _check_screen_recording_permission(),
        "accessibility": _check_accessibility_permission(),
    }


def _check_camera_permission() -> PermissionStatus:
    """
    Check camera permission without triggering the permission dialog.
    
    Note: We can detect if cameras EXIST via system_profiler (no permission needed),
    but actually USING them requires TCC approval.
    """
    try:
        # system_profiler doesn't need camera permission - it just lists hardware
        result = subprocess.run(
            ["system_profiler", "SPCameraDataType", "-json"],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode != 0:
            return PermissionStatus(False, True, "system_profiler failed")
        
        # Camera hardware exists. Check if we can actually access it.
        # Unfortunately, there's no clean way to check TCC status without triggering
        # the permission dialog. We can check the TCC database directly (requires SIP off)
        # or just note that permission may be needed.
        
        return PermissionStatus(
            granted=True,  # We know hardware exists
            can_request=True,
            note="Camera hardware detected. TCC permission may be required for actual access."
        )
    except subprocess.TimeoutExpired:
        return PermissionStatus(False, True, "Timeout checking camera")
    except Exception as e:
        logger.warning(f"Camera permission check failed: {e}")
        return PermissionStatus(False, True, str(e))


def _check_microphone_permission() -> PermissionStatus:
    """Check microphone permission status."""
    try:
        # List audio input devices via system_profiler
        result = subprocess.run(
            ["system_profiler", "SPAudioDataType", "-json"],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode != 0:
            return PermissionStatus(False, True, "system_profiler failed")
        
        return PermissionStatus(
            granted=True,
            can_request=True,
            note="Audio hardware detected. TCC permission required for recording."
        )
    except Exception as e:
        logger.warning(f"Microphone permission check failed: {e}")
        return PermissionStatus(False, True, str(e))


def _check_screen_recording_permission() -> PermissionStatus:
    """
    Check screen recording permission.
    
    This is tricky - screen recording permission can only be tested by
    actually attempting to capture, which may trigger the permission dialog.
    """
    try:
        # CGWindowListCopyWindowInfo with kCGWindowListOptionOnScreenOnly
        # returns empty or limited results without screen recording permission.
        # But calling this from Python is complex. Use a simpler heuristic.
        
        # Check if screencapture works (it will prompt if no permission)
        # We don't actually run it to avoid the prompt
        
        return PermissionStatus(
            granted=False,  # Assume not granted until proven
            can_request=True,
            note="Screen recording permission must be granted in System Preferences > Privacy > Screen Recording"
        )
    except Exception as e:
        return PermissionStatus(False, True, str(e))


def _check_accessibility_permission() -> PermissionStatus:
    """Check accessibility permission (needed for some automation)."""
    try:
        # This AppleScript trick can check accessibility without triggering dialog
        result = subprocess.run(
            ["osascript", "-e", 
             'tell application "System Events" to return (exists process 1)'],
            capture_output=True, text=True, timeout=5
        )
        
        # If this runs without error, we likely have accessibility permission
        has_permission = result.returncode == 0
        
        return PermissionStatus(
            granted=has_permission,
            can_request=True,
            note="" if has_permission else "Enable in System Preferences > Privacy > Accessibility"
        )
    except Exception as e:
        return PermissionStatus(False, True, str(e))
```

### Graceful Degradation

The scanner MUST handle missing permissions gracefully:

```python
def scan_with_permissions() -> dict:
    """
    Scan capabilities with permission awareness.
    
    Never crashes due to missing permissions. Instead, reports what
    permissions are missing and what capabilities are unavailable.
    """
    results = {
        "timestamp": time.time(),
        "permissions": {},
        "capabilities": {},
        "warnings": [],
    }
    
    # Check permissions first
    perms = check_macos_permissions()
    results["permissions"] = {k: v.__dict__ for k, v in perms.items()}
    
    # GPU scanning (no permissions needed)
    try:
        results["capabilities"]["gpu"] = scan_gpus()
    except Exception as e:
        results["warnings"].append(f"GPU scan failed: {e}")
        results["capabilities"]["gpu"] = None
    
    # Camera scanning (permission required for actual access)
    if perms["camera"].granted:
        try:
            results["capabilities"]["cameras"] = detect_cameras()
        except PermissionError:
            results["warnings"].append(
                "Camera access denied. Grant permission in System Preferences > Privacy > Camera"
            )
            results["capabilities"]["cameras"] = []
        except Exception as e:
            results["warnings"].append(f"Camera detection failed: {e}")
            results["capabilities"]["cameras"] = []
    else:
        results["capabilities"]["cameras"] = []
        results["warnings"].append(
            f"Camera scan skipped: {perms['camera'].note}"
        )
    
    # Microphone scanning
    if perms["microphone"].granted:
        try:
            results["capabilities"]["microphones"] = detect_microphones()
        except PermissionError:
            results["warnings"].append(
                "Microphone access denied. Grant in System Preferences > Privacy > Microphone"
            )
            results["capabilities"]["microphones"] = []
        except Exception as e:
            results["warnings"].append(f"Microphone detection failed: {e}")
            results["capabilities"]["microphones"] = []
    else:
        results["capabilities"]["microphones"] = []
        results["warnings"].append(
            f"Microphone scan skipped: {perms['microphone'].note}"
        )
    
    # Screen capture (permission definitely required)
    if perms["screen_recording"].granted:
        try:
            results["capabilities"]["displays"] = detect_displays()
        except Exception as e:
            results["warnings"].append(f"Display detection failed: {e}")
            results["capabilities"]["displays"] = []
    else:
        results["capabilities"]["displays"] = []
        results["warnings"].append(
            "Screen recording not permitted. Enable in System Preferences > Privacy > Screen Recording"
        )
    
    return results
```

### Permission Request Guidance

When permissions are missing, provide actionable guidance:

```python
PERMISSION_INSTRUCTIONS = {
    "camera": """
To grant camera access:
1. Open System Preferences > Security & Privacy > Privacy > Camera
2. Click the lock to make changes
3. Check the box next to this application
4. Restart the application
    
Or run: tccutil reset Camera
""",
    "microphone": """
To grant microphone access:
1. Open System Preferences > Security & Privacy > Privacy > Microphone
2. Click the lock to make changes  
3. Check the box next to this application
4. Restart the application

Or run: tccutil reset Microphone
""",
    "screen_recording": """
To grant screen recording access:
1. Open System Preferences > Security & Privacy > Privacy > Screen Recording
2. Click the lock to make changes
3. Check the box next to this application
4. You may need to restart the application

Note: Screen recording permission cannot be granted via tccutil.
""",
    "accessibility": """
To grant accessibility access:
1. Open System Preferences > Security & Privacy > Privacy > Accessibility
2. Click the lock to make changes
3. Check the box next to this application
4. Restart may be required
"""
}

def print_permission_help(missing: list[str]) -> None:
    """Print help for missing permissions."""
    print("\n⚠️  Missing Permissions")
    print("=" * 40)
    for perm in missing:
        if perm in PERMISSION_INSTRUCTIONS:
            print(f"\n{perm.upper()}:")
            print(PERMISSION_INSTRUCTIONS[perm])
```

---

## Detection Methods

### GPU Detection

GPU detection is critical for Atmosphere since most AI workloads benefit from acceleration.

#### Metal (macOS)

Metal is Apple's GPU API, available on all modern Macs. Detection via `system_profiler`:

```python
import subprocess
import json
import re
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class MetalGPU:
    name: str
    vendor: str
    metal_version: str
    cores: int
    memory_gb: Optional[float] = None  # Unified memory on Apple Silicon

def detect_metal_gpu() -> Optional[MetalGPU]:
    """Detect Metal GPU on macOS."""
    try:
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return None
        
        data = json.loads(result.stdout)
        displays = data.get("SPDisplaysDataType", [])
        
        for gpu in displays:
            name = gpu.get("sppci_model", "Unknown")
            vendor = gpu.get("sppci_vendor", "Unknown")
            metal_support = gpu.get("spdisplays_metalversion", "")
            
            # Extract core count from name (e.g., "24" from "Apple M1 Max")
            cores = 0
            if "Total Number of Cores" in gpu:
                cores = int(gpu["Total Number of Cores"])
            
            if metal_support:
                return MetalGPU(
                    name=name,
                    vendor=vendor,
                    metal_version=metal_support,
                    cores=cores
                )
        
        return None
    except Exception as e:
        logger.warning(f"Metal detection failed: {e}")
        return None

def test_metal_available() -> bool:
    """Test if Metal/MPS is actually usable for ML workloads."""
    try:
        import torch
        return torch.backends.mps.is_available() and torch.backends.mps.is_built()
    except ImportError:
        # PyTorch not installed, try MLX
        try:
            import mlx.core as mx
            # MLX always uses Metal on macOS
            return True
        except ImportError:
            return False
```

#### CUDA (NVIDIA)

CUDA detection via `nvidia-smi` and PyTorch:

```python
@dataclass
class CudaGPU:
    name: str
    index: int
    memory_total_mb: int
    memory_free_mb: int
    cuda_version: str
    compute_capability: str

def detect_cuda_gpus() -> List[CudaGPU]:
    """Detect NVIDIA GPUs via nvidia-smi."""
    gpus = []
    
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free,compute_cap", 
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        # Get CUDA version
        version_result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        cuda_version = version_result.stdout.strip().split("\n")[0] if version_result.returncode == 0 else "unknown"
        
        for line in result.stdout.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                gpus.append(CudaGPU(
                    name=parts[1],
                    index=int(parts[0]),
                    memory_total_mb=int(parts[2]),
                    memory_free_mb=int(parts[3]),
                    compute_capability=parts[4],
                    cuda_version=cuda_version
                ))
        
        return gpus
    except FileNotFoundError:
        return []  # nvidia-smi not installed
    except Exception as e:
        logger.warning(f"CUDA detection failed: {e}")
        return []

def test_cuda_available() -> bool:
    """Test if CUDA is actually usable."""
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        # Actually try to use it
        device = torch.device("cuda")
        x = torch.tensor([1.0], device=device)
        return True
    except Exception:
        return False
```

#### ROCm (AMD)

ROCm detection for AMD GPUs on Linux:

```python
@dataclass
class ROCmGPU:
    name: str
    index: int
    memory_total_mb: int
    memory_free_mb: int

def detect_rocm_gpus() -> List[ROCmGPU]:
    """Detect AMD GPUs via rocm-smi."""
    gpus = []
    
    try:
        # Check if rocm-smi exists
        result = subprocess.run(
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        # Parse rocm-smi output
        # Format varies, this is a simplified parser
        current_gpu = {"index": 0}
        
        for line in result.stdout.split("\n"):
            if "GPU[" in line:
                match = re.search(r"GPU\[(\d+)\]", line)
                if match:
                    current_gpu["index"] = int(match.group(1))
            elif "Card series" in line:
                current_gpu["name"] = line.split(":")[-1].strip()
            elif "VRAM Total Memory" in line:
                mem = re.search(r"(\d+)", line)
                if mem:
                    current_gpu["memory_total_mb"] = int(mem.group(1))
            elif "VRAM Total Used Memory" in line:
                mem = re.search(r"(\d+)", line)
                if mem:
                    used = int(mem.group(1))
                    current_gpu["memory_free_mb"] = current_gpu.get("memory_total_mb", 0) - used
                    
                    if "name" in current_gpu:
                        gpus.append(ROCmGPU(**current_gpu))
                    current_gpu = {"index": current_gpu["index"] + 1}
        
        return gpus
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.warning(f"ROCm detection failed: {e}")
        return []
```

#### Vulkan (Cross-platform fallback)

Vulkan detection for non-Apple/NVIDIA/AMD systems:

```python
def detect_vulkan_devices() -> List[dict]:
    """Detect Vulkan-capable devices."""
    try:
        result = subprocess.run(
            ["vulkaninfo", "--summary"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        devices = []
        current_device = {}
        
        for line in result.stdout.split("\n"):
            if "deviceName" in line:
                current_device["name"] = line.split("=")[-1].strip()
            elif "deviceType" in line:
                current_device["type"] = line.split("=")[-1].strip()
            elif "apiVersion" in line:
                current_device["api_version"] = line.split("=")[-1].strip()
                if current_device.get("name"):
                    devices.append(current_device.copy())
                    current_device = {}
        
        return devices
    except FileNotFoundError:
        return []
```

---

### NPU Detection

Neural Processing Units are increasingly common, especially on Apple Silicon and Qualcomm chips.

#### Apple Neural Engine (ANE)

The ANE is detected implicitly through CoreML availability:

```python
def detect_apple_neural_engine() -> Optional[dict]:
    """Detect Apple Neural Engine via CoreML."""
    import platform
    
    if platform.system() != "Darwin":
        return None
    
    try:
        # Check if CoreML is available
        import coremltools
        
        # ANE is available on A11+ chips (iPhone 8+) and all Apple Silicon Macs
        # We can't directly query ANE, but we can infer from chip
        result = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        chip = result.stdout.strip()
        
        # Apple Silicon chips have ANE
        if "Apple" in chip:
            # Estimate ANE cores based on chip
            ane_cores = 16  # Default
            if "M1" in chip:
                ane_cores = 16
            elif "M2" in chip:
                ane_cores = 16
            elif "M3" in chip:
                ane_cores = 16
            elif "M4" in chip:
                ane_cores = 16  # May vary
            
            # Max/Ultra variants have more
            if "Max" in chip:
                ane_cores = 16
            elif "Ultra" in chip:
                ane_cores = 32
            
            return {
                "available": True,
                "chip": chip,
                "ane_cores": ane_cores,
                "framework": "CoreML"
            }
        
        return None
    except ImportError:
        return None
    except Exception as e:
        logger.warning(f"ANE detection failed: {e}")
        return None
```

#### Qualcomm NPU (Linux)

For Qualcomm-based devices (phones, some laptops):

```python
def detect_qualcomm_npu() -> Optional[dict]:
    """Detect Qualcomm Hexagon NPU."""
    try:
        # Check for Qualcomm AI Engine
        result = subprocess.run(
            ["qaic-util", "-q"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return {
                "available": True,
                "type": "Qualcomm Hexagon",
                "info": result.stdout.strip()
            }
        
        return None
    except FileNotFoundError:
        return None
```

---

### Model Detection

Finding locally available AI models is essential for capability registration.

#### Ollama Models

Ollama provides a REST API for model discovery:

```python
import httpx
from dataclasses import dataclass
from typing import List, Optional

@dataclass 
class OllamaModel:
    name: str
    size_bytes: int
    parameter_size: str
    quantization: str
    family: str
    modified_at: str

async def detect_ollama_models(
    host: str = "localhost",
    port: int = 11434,
    timeout: float = 5.0
) -> List[OllamaModel]:
    """Detect models available in Ollama."""
    models = []
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"http://{host}:{port}/api/tags")
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            
            for model in data.get("models", []):
                details = model.get("details", {})
                models.append(OllamaModel(
                    name=model["name"],
                    size_bytes=model.get("size", 0),
                    parameter_size=details.get("parameter_size", "unknown"),
                    quantization=details.get("quantization_level", "unknown"),
                    family=details.get("family", "unknown"),
                    modified_at=model.get("modified_at", "")
                ))
        
        return models
    except httpx.ConnectError:
        return []  # Ollama not running
    except Exception as e:
        logger.warning(f"Ollama detection failed: {e}")
        return []

def test_ollama_model(model_name: str, host: str = "localhost", port: int = 11434) -> bool:
    """Test if an Ollama model can actually generate."""
    import httpx
    
    try:
        # Use sync client for simplicity in test
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"http://{host}:{port}/api/generate",
                json={
                    "model": model_name,
                    "prompt": "Hi",
                    "stream": False,
                    "options": {"num_predict": 1}  # Single token
                }
            )
            return response.status_code == 200
    except Exception:
        return False
```

#### LlamaFarm Models

LlamaFarm provides project-based model management:

```python
@dataclass
class LlamaFarmProject:
    name: str
    models: List[str]
    status: str

async def detect_llamafarm_projects(
    host: str = "localhost",
    port: int = 14345
) -> List[LlamaFarmProject]:
    """Detect projects available in LlamaFarm."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"http://{host}:{port}/v1/projects")
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            projects = []
            
            for proj in data.get("projects", []):
                projects.append(LlamaFarmProject(
                    name=proj["name"],
                    models=proj.get("models", []),
                    status=proj.get("status", "unknown")
                ))
            
            return projects
    except httpx.ConnectError:
        return []
    except Exception as e:
        logger.warning(f"LlamaFarm detection failed: {e}")
        return []
```

#### HuggingFace Cache

Scan the local HuggingFace cache for downloaded models:

```python
from pathlib import Path

@dataclass
class HuggingFaceModel:
    repo_id: str
    revision: str
    size_bytes: int
    path: Path

def detect_huggingface_models(
    cache_dir: Optional[Path] = None
) -> List[HuggingFaceModel]:
    """Detect models in HuggingFace cache."""
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    
    if not cache_dir.exists():
        return []
    
    models = []
    
    for entry in cache_dir.iterdir():
        if not entry.is_dir():
            continue
        
        # Parse directory name: models--org--name or datasets--org--name
        name = entry.name
        
        if name.startswith("models--"):
            # Extract repo_id: models--org--name -> org/name
            parts = name.split("--")[1:]
            if len(parts) >= 2:
                repo_id = "/".join(parts)
            else:
                repo_id = parts[0] if parts else name
            
            # Find snapshots
            snapshots_dir = entry / "snapshots"
            if snapshots_dir.exists():
                for snapshot in snapshots_dir.iterdir():
                    if snapshot.is_dir():
                        # Calculate size
                        size = sum(
                            f.stat().st_size 
                            for f in snapshot.rglob("*") 
                            if f.is_file()
                        )
                        
                        models.append(HuggingFaceModel(
                            repo_id=repo_id,
                            revision=snapshot.name[:8],  # Short hash
                            size_bytes=size,
                            path=snapshot
                        ))
    
    return models
```

#### GGUF Files

Find standalone GGUF model files:

```python
def detect_gguf_files(
    search_paths: Optional[List[Path]] = None,
    max_depth: int = 3
) -> List[dict]:
    """Find GGUF model files on disk."""
    if search_paths is None:
        search_paths = [
            Path.home() / "Downloads",
            Path.home() / ".cache",
            Path.home() / "models",
            Path.home() / ".ollama" / "models",
        ]
    
    gguf_files = []
    
    for search_path in search_paths:
        if not search_path.exists():
            continue
        
        try:
            # Use find command for efficiency
            result = subprocess.run(
                ["find", str(search_path), "-name", "*.gguf", 
                 "-type", "f", "-maxdepth", str(max_depth)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            for line in result.stdout.strip().split("\n"):
                if line:
                    path = Path(line)
                    if path.exists():
                        # Parse model info from filename
                        name = path.stem
                        
                        # Common patterns: model-size-quant.gguf
                        quantization = "unknown"
                        for quant in ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16", "F32"]:
                            if quant in name.upper():
                                quantization = quant
                                break
                        
                        gguf_files.append({
                            "path": str(path),
                            "name": name,
                            "size_bytes": path.stat().st_size,
                            "quantization": quantization
                        })
        except Exception as e:
            logger.warning(f"GGUF search failed in {search_path}: {e}")
    
    return gguf_files
```

---

### Hardware Detection

#### Cameras

Camera detection varies significantly by platform:

```python
@dataclass
class CameraDevice:
    index: int
    name: str
    type: str  # "video", "screen"

def detect_cameras_macos() -> List[CameraDevice]:
    """Detect cameras on macOS using ffmpeg/AVFoundation."""
    cameras = []
    
    try:
        result = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # ffmpeg outputs device list to stderr
        output = result.stderr
        
        in_video = False
        for line in output.split("\n"):
            if "AVFoundation video devices:" in line:
                in_video = True
                continue
            elif "AVFoundation audio devices:" in line:
                in_video = False
                continue
            
            if in_video and "[" in line and "]" in line:
                # Parse: [AVFoundation indev @ 0x...] [0] FaceTime HD Camera
                match = re.search(r'\[(\d+)\]\s+(.+)$', line)
                if match:
                    index = int(match.group(1))
                    name = match.group(2).strip()
                    
                    device_type = "screen" if "screen" in name.lower() else "video"
                    
                    cameras.append(CameraDevice(
                        index=index,
                        name=name,
                        type=device_type
                    ))
        
        return cameras
    except FileNotFoundError:
        # ffmpeg not installed, try OpenCV
        return detect_cameras_opencv()
    except Exception as e:
        logger.warning(f"macOS camera detection failed: {e}")
        return []

def detect_cameras_linux() -> List[CameraDevice]:
    """Detect cameras on Linux using v4l2."""
    cameras = []
    
    try:
        # List video devices
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return detect_cameras_opencv()
        
        current_name = ""
        for line in result.stdout.split("\n"):
            line = line.strip()
            if line and not line.startswith("/"):
                current_name = line.rstrip(":")
            elif line.startswith("/dev/video"):
                index = int(line.replace("/dev/video", ""))
                cameras.append(CameraDevice(
                    index=index,
                    name=current_name,
                    type="video"
                ))
        
        return cameras
    except FileNotFoundError:
        return detect_cameras_opencv()

def detect_cameras_opencv() -> List[CameraDevice]:
    """Fallback camera detection using OpenCV."""
    cameras = []
    
    try:
        import cv2
        
        # Probe first 10 indices
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cameras.append(CameraDevice(
                    index=i,
                    name=f"Camera {i}",
                    type="video"
                ))
                cap.release()
    except ImportError:
        pass
    
    return cameras

def test_camera(index: int = 0) -> bool:
    """Test if a camera can capture frames."""
    try:
        import cv2
        
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            return False
        
        ret, frame = cap.read()
        cap.release()
        
        return ret and frame is not None
    except Exception:
        return False
```

#### Microphones

```python
@dataclass
class AudioDevice:
    index: int
    name: str
    type: str  # "input" or "output"
    channels: int

def detect_microphones_macos() -> List[AudioDevice]:
    """Detect microphones on macOS using ffmpeg."""
    mics = []
    
    try:
        result = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        output = result.stderr
        in_audio = False
        
        for line in output.split("\n"):
            if "AVFoundation audio devices:" in line:
                in_audio = True
                continue
            
            if in_audio and "[" in line and "]" in line:
                match = re.search(r'\[(\d+)\]\s+(.+)$', line)
                if match:
                    index = int(match.group(1))
                    name = match.group(2).strip()
                    
                    mics.append(AudioDevice(
                        index=index,
                        name=name,
                        type="input",
                        channels=2  # Assume stereo
                    ))
        
        return mics
    except Exception as e:
        logger.warning(f"Microphone detection failed: {e}")
        return []

def detect_microphones_linux() -> List[AudioDevice]:
    """Detect microphones on Linux using ALSA."""
    mics = []
    
    try:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        for line in result.stdout.split("\n"):
            if "card" in line.lower():
                # Parse: card 0: PCH [HDA Intel PCH], device 0: ALC...
                match = re.search(r'card (\d+):.*\[(.+?)\]', line)
                if match:
                    mics.append(AudioDevice(
                        index=int(match.group(1)),
                        name=match.group(2),
                        type="input",
                        channels=2
                    ))
        
        return mics
    except FileNotFoundError:
        return []

def test_microphone(index: int = 0) -> bool:
    """Test if microphone can capture audio."""
    try:
        import pyaudio
        
        p = pyaudio.PyAudio()
        
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=index,
                frames_per_buffer=1024
            )
            
            # Try to read a small chunk
            data = stream.read(1024, exception_on_overflow=False)
            stream.close()
            
            return len(data) > 0
        finally:
            p.terminate()
    except Exception:
        return False
```

#### Speakers

```python
def detect_speakers_macos() -> List[AudioDevice]:
    """Detect speakers on macOS."""
    speakers = []
    
    try:
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPAudioDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            audio_data = data.get("SPAudioDataType", [])
            
            for device in audio_data:
                for item in device.get("_items", []):
                    if "output" in item.get("coreaudio_device_transport", "").lower():
                        speakers.append(AudioDevice(
                            index=len(speakers),
                            name=item.get("_name", "Unknown"),
                            type="output",
                            channels=2
                        ))
        
        return speakers
    except Exception as e:
        logger.warning(f"Speaker detection failed: {e}")
        return []
```

---

### Service Detection

#### Port Probing

Check for known services on common ports:

```python
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

KNOWN_PORTS = {
    11434: ("ollama", "Ollama API"),
    14345: ("llamafarm", "LlamaFarm API"),
    8000: ("fastapi", "FastAPI/Generic HTTP"),
    8080: ("http", "HTTP Server"),
    5000: ("flask", "Flask/Generic HTTP"),
    6333: ("qdrant", "Qdrant Vector DB"),
    19530: ("milvus", "Milvus Vector DB"),
    8983: ("solr", "Apache Solr"),
    9200: ("elasticsearch", "Elasticsearch"),
    6379: ("redis", "Redis"),
    5432: ("postgres", "PostgreSQL"),
    27017: ("mongodb", "MongoDB"),
}

@dataclass
class DetectedService:
    port: int
    service_type: str
    name: str
    verified: bool = False
    endpoint: Optional[str] = None

def probe_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

def detect_services(
    host: str = "localhost",
    ports: Optional[List[int]] = None,
    timeout: float = 1.0
) -> List[DetectedService]:
    """Detect services running on known ports."""
    if ports is None:
        ports = list(KNOWN_PORTS.keys())
    
    services = []
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(probe_port, host, port, timeout): port
            for port in ports
        }
        
        for future in as_completed(futures):
            port = futures[future]
            try:
                is_open = future.result()
                if is_open:
                    service_type, name = KNOWN_PORTS.get(port, ("unknown", f"Port {port}"))
                    services.append(DetectedService(
                        port=port,
                        service_type=service_type,
                        name=name,
                        endpoint=f"http://{host}:{port}"
                    ))
            except Exception:
                pass
    
    return services

async def verify_service(service: DetectedService) -> DetectedService:
    """Verify a service is actually responding."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            # Try common health endpoints
            for endpoint in ["/health", "/healthz", "/api/tags", "/", "/v1/models"]:
                try:
                    response = await client.get(f"{service.endpoint}{endpoint}")
                    if response.status_code < 500:
                        service.verified = True
                        return service
                except Exception:
                    continue
    except Exception:
        pass
    
    return service
```

#### Docker Containers

```python
@dataclass
class DockerContainer:
    id: str
    name: str
    image: str
    ports: List[str]
    status: str

def detect_docker_containers() -> List[DockerContainer]:
    """Detect running Docker containers."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", 
             "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        containers = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 5:
                containers.append(DockerContainer(
                    id=parts[0],
                    name=parts[1],
                    image=parts[2],
                    ports=parts[3].split(", ") if parts[3] else [],
                    status=parts[4]
                ))
        
        return containers
    except FileNotFoundError:
        return []  # Docker not installed
    except Exception as e:
        logger.warning(f"Docker detection failed: {e}")
        return []
```

#### Systemd Services (Linux)

```python
def detect_systemd_services(patterns: List[str] = None) -> List[dict]:
    """Detect relevant systemd services on Linux."""
    if patterns is None:
        patterns = ["ollama", "docker", "podman", "qdrant", "redis"]
    
    try:
        result = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--state=running",
             "--no-pager", "--plain"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        services = []
        for line in result.stdout.split("\n"):
            for pattern in patterns:
                if pattern in line.lower():
                    parts = line.split()
                    if parts:
                        services.append({
                            "name": parts[0],
                            "status": "running",
                            "pattern_match": pattern
                        })
        
        return services
    except FileNotFoundError:
        return []  # Not using systemd
```

---

### Capability Testing

The key insight: **existence ≠ functionality**. Just because something is installed doesn't mean it works.

```python
from enum import Enum
from typing import Callable, Any

class TestStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"

@dataclass
class TestResult:
    name: str
    status: TestStatus
    duration_ms: float
    message: Optional[str] = None
    details: Optional[dict] = None

class CapabilityTester:
    """Run actual tests against detected capabilities."""
    
    def __init__(self):
        self.tests: Dict[str, Callable] = {}
        self._register_default_tests()
    
    def _register_default_tests(self):
        """Register built-in capability tests."""
        self.tests["metal_inference"] = self._test_metal_inference
        self.tests["cuda_inference"] = self._test_cuda_inference
        self.tests["ollama_generate"] = self._test_ollama_generate
        self.tests["camera_capture"] = self._test_camera_capture
        self.tests["microphone_record"] = self._test_microphone_record
    
    async def run_test(self, test_name: str, **kwargs) -> TestResult:
        """Run a single test."""
        if test_name not in self.tests:
            return TestResult(
                name=test_name,
                status=TestStatus.SKIPPED,
                duration_ms=0,
                message=f"Unknown test: {test_name}"
            )
        
        import time
        start = time.perf_counter()
        
        try:
            test_fn = self.tests[test_name]
            result = await test_fn(**kwargs) if asyncio.iscoroutinefunction(test_fn) else test_fn(**kwargs)
            duration = (time.perf_counter() - start) * 1000
            
            if result:
                return TestResult(
                    name=test_name,
                    status=TestStatus.PASSED,
                    duration_ms=duration
                )
            else:
                return TestResult(
                    name=test_name,
                    status=TestStatus.FAILED,
                    duration_ms=duration,
                    message="Test returned False"
                )
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return TestResult(
                name=test_name,
                status=TestStatus.ERROR,
                duration_ms=duration,
                message=str(e)
            )
    
    def _test_metal_inference(self) -> bool:
        """Test Metal/MPS can run inference."""
        try:
            import torch
            if not torch.backends.mps.is_available():
                return False
            
            # Small inference test
            device = torch.device("mps")
            x = torch.randn(10, 10, device=device)
            y = torch.mm(x, x)
            return y.shape == (10, 10)
        except Exception:
            return False
    
    def _test_cuda_inference(self) -> bool:
        """Test CUDA can run inference."""
        try:
            import torch
            if not torch.cuda.is_available():
                return False
            
            device = torch.device("cuda")
            x = torch.randn(10, 10, device=device)
            y = torch.mm(x, x)
            return y.shape == (10, 10)
        except Exception:
            return False
    
    async def _test_ollama_generate(
        self, 
        model: str = None,
        host: str = "localhost",
        port: int = 11434
    ) -> bool:
        """Test Ollama can generate text."""
        try:
            # Find a small model if none specified
            if model is None:
                models = await detect_ollama_models(host, port)
                if not models:
                    return False
                # Pick smallest model
                model = min(models, key=lambda m: m.size_bytes).name
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"http://{host}:{port}/api/generate",
                    json={
                        "model": model,
                        "prompt": "1+1=",
                        "stream": False,
                        "options": {"num_predict": 5}
                    }
                )
                return response.status_code == 200
        except Exception:
            return False
    
    def _test_camera_capture(self, index: int = 0) -> bool:
        """Test camera can capture a frame."""
        return test_camera(index)
    
    def _test_microphone_record(self, index: int = 0) -> bool:
        """Test microphone can record audio."""
        return test_microphone(index)
```

---

## System Information

Basic system info is needed for capability metadata:

```python
@dataclass
class SystemInfo:
    os: str
    os_version: str
    arch: str
    cpu_brand: str
    cpu_cores: int
    cpu_threads: int
    ram_total_gb: float
    ram_available_gb: float
    disk_total_gb: float
    disk_available_gb: float

def detect_system_info() -> SystemInfo:
    """Detect basic system information."""
    import platform
    import psutil
    
    # CPU info
    cpu_brand = "Unknown"
    try:
        if platform.system() == "Darwin":
            result = subprocess.run(
                ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                cpu_brand = result.stdout.strip()
        else:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        cpu_brand = line.split(":")[1].strip()
                        break
    except Exception:
        pass
    
    # Memory
    mem = psutil.virtual_memory()
    
    # Disk
    disk = psutil.disk_usage("/")
    
    return SystemInfo(
        os=platform.system(),
        os_version=platform.release(),
        arch=platform.machine(),
        cpu_brand=cpu_brand,
        cpu_cores=psutil.cpu_count(logical=False) or 1,
        cpu_threads=psutil.cpu_count(logical=True) or 1,
        ram_total_gb=mem.total / (1024**3),
        ram_available_gb=mem.available / (1024**3),
        disk_total_gb=disk.total / (1024**3),
        disk_available_gb=disk.free / (1024**3)
    )
```

---

## CLI Integration

The scanner should be accessible via the `atmosphere` CLI:

```bash
# Full scan
atmosphere scan

# Category-specific scans
atmosphere scan --gpu
atmosphere scan --models
atmosphere scan --hardware
atmosphere scan --services

# With capability testing
atmosphere scan --test

# Output format
atmosphere scan --json
atmosphere scan --yaml

# Verbose output
atmosphere scan -v
atmosphere scan -vv  # Debug level

# Save results
atmosphere scan --output scan-results.json

# Specific host (for remote scanning)
atmosphere scan --host 192.168.1.100
```

### Implementation

```python
# atmosphere/cli/scan.py

import click
import asyncio
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

@click.command()
@click.option("--gpu", is_flag=True, help="Scan GPUs only")
@click.option("--models", is_flag=True, help="Scan models only")
@click.option("--hardware", is_flag=True, help="Scan hardware only")
@click.option("--services", is_flag=True, help="Scan services only")
@click.option("--test", is_flag=True, help="Run capability tests")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--yaml", "output_yaml", is_flag=True, help="Output as YAML")
@click.option("--output", "-o", type=click.Path(), help="Save results to file")
@click.option("--host", default="localhost", help="Host to scan")
@click.option("-v", "--verbose", count=True, help="Increase verbosity")
def scan(gpu, models, hardware, services, test, output_json, output_yaml, output, host, verbose):
    """Scan for local capabilities."""
    
    # If no specific category, scan all
    scan_all = not (gpu or models or hardware or services)
    
    results = {}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        
        # System info (always included)
        task = progress.add_task("Scanning system...", total=None)
        results["system"] = asyncio.run(scan_system())
        progress.remove_task(task)
        
        if scan_all or gpu:
            task = progress.add_task("Scanning GPUs...", total=None)
            results["gpu"] = asyncio.run(scan_gpus(test=test))
            progress.remove_task(task)
        
        if scan_all or models:
            task = progress.add_task("Scanning models...", total=None)
            results["models"] = asyncio.run(scan_models(host=host, test=test))
            progress.remove_task(task)
        
        if scan_all or hardware:
            task = progress.add_task("Scanning hardware...", total=None)
            results["hardware"] = asyncio.run(scan_hardware(test=test))
            progress.remove_task(task)
        
        if scan_all or services:
            task = progress.add_task("Scanning services...", total=None)
            results["services"] = asyncio.run(scan_services(host=host))
            progress.remove_task(task)
    
    # Output results
    if output_json:
        import json
        output_str = json.dumps(results, indent=2, default=str)
        if output:
            Path(output).write_text(output_str)
        else:
            console.print(output_str)
    elif output_yaml:
        import yaml
        output_str = yaml.dump(results, default_flow_style=False)
        if output:
            Path(output).write_text(output_str)
        else:
            console.print(output_str)
    else:
        # Pretty print
        display_results(results, verbose)
        if output:
            import json
            Path(output).write_text(json.dumps(results, indent=2, default=str))

def display_results(results: dict, verbose: int = 0):
    """Display scan results in a nice format."""
    
    # System info
    sys_info = results.get("system", {})
    console.print(f"\n[bold]System:[/bold] {sys_info.get('os', 'Unknown')} {sys_info.get('os_version', '')}")
    console.print(f"  CPU: {sys_info.get('cpu_brand', 'Unknown')} ({sys_info.get('cpu_cores', '?')} cores)")
    console.print(f"  RAM: {sys_info.get('ram_available_gb', 0):.1f} / {sys_info.get('ram_total_gb', 0):.1f} GB available")
    
    # GPUs
    if "gpu" in results:
        console.print("\n[bold]GPUs:[/bold]")
        gpu_data = results["gpu"]
        if gpu_data.get("metal"):
            m = gpu_data["metal"]
            status = "✅" if gpu_data.get("metal_tested") else "⚠️"
            console.print(f"  {status} {m['name']} (Metal {m['metal_version']}, {m['cores']} cores)")
        if gpu_data.get("cuda"):
            for g in gpu_data["cuda"]:
                status = "✅" if gpu_data.get("cuda_tested") else "⚠️"
                console.print(f"  {status} {g['name']} (CUDA, {g['memory_total_mb']}MB)")
        if not gpu_data.get("metal") and not gpu_data.get("cuda"):
            console.print("  [dim]No GPU acceleration detected[/dim]")
    
    # Models
    if "models" in results:
        console.print("\n[bold]Models:[/bold]")
        model_data = results["models"]
        
        if model_data.get("ollama"):
            console.print(f"  [cyan]Ollama[/cyan] ({len(model_data['ollama'])} models)")
            for m in model_data["ollama"][:5]:  # Show first 5
                size_gb = m["size_bytes"] / (1024**3)
                console.print(f"    • {m['name']} ({size_gb:.1f}GB, {m['quantization']})")
            if len(model_data["ollama"]) > 5:
                console.print(f"    [dim]... and {len(model_data['ollama']) - 5} more[/dim]")
        
        if model_data.get("huggingface"):
            console.print(f"  [cyan]HuggingFace[/cyan] ({len(model_data['huggingface'])} models)")
            for m in model_data["huggingface"][:3]:
                console.print(f"    • {m['repo_id']}")
    
    # Hardware
    if "hardware" in results:
        console.print("\n[bold]Hardware:[/bold]")
        hw = results["hardware"]
        
        if hw.get("cameras"):
            console.print(f"  [cyan]Cameras[/cyan]")
            for cam in hw["cameras"]:
                status = "✅" if cam.get("tested") else "📷"
                console.print(f"    {status} {cam['name']}")
        
        if hw.get("microphones"):
            console.print(f"  [cyan]Microphones[/cyan]")
            for mic in hw["microphones"]:
                console.print(f"    🎤 {mic['name']}")
    
    # Services
    if "services" in results:
        console.print("\n[bold]Services:[/bold]")
        for svc in results.get("services", []):
            status = "✅" if svc.get("verified") else "🔌"
            console.print(f"  {status} {svc['name']} (:{svc['port']})")
    
    console.print()
```

---

## Output Format

### JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CapabilityScanResult",
  "type": "object",
  "properties": {
    "scan_id": {
      "type": "string",
      "description": "Unique scan identifier"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "duration_ms": {
      "type": "number"
    },
    "system": {
      "type": "object",
      "properties": {
        "os": { "type": "string" },
        "os_version": { "type": "string" },
        "arch": { "type": "string" },
        "cpu_brand": { "type": "string" },
        "cpu_cores": { "type": "integer" },
        "cpu_threads": { "type": "integer" },
        "ram_total_gb": { "type": "number" },
        "ram_available_gb": { "type": "number" },
        "disk_total_gb": { "type": "number" },
        "disk_available_gb": { "type": "number" }
      }
    },
    "gpu": {
      "type": "object",
      "properties": {
        "metal": {
          "type": "object",
          "properties": {
            "name": { "type": "string" },
            "vendor": { "type": "string" },
            "metal_version": { "type": "string" },
            "cores": { "type": "integer" }
          }
        },
        "metal_tested": { "type": "boolean" },
        "cuda": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string" },
              "index": { "type": "integer" },
              "memory_total_mb": { "type": "integer" },
              "memory_free_mb": { "type": "integer" },
              "cuda_version": { "type": "string" },
              "compute_capability": { "type": "string" }
            }
          }
        },
        "cuda_tested": { "type": "boolean" },
        "rocm": { "type": "array" },
        "vulkan": { "type": "array" }
      }
    },
    "npu": {
      "type": "object",
      "properties": {
        "apple_ane": {
          "type": "object",
          "properties": {
            "available": { "type": "boolean" },
            "chip": { "type": "string" },
            "ane_cores": { "type": "integer" }
          }
        }
      }
    },
    "models": {
      "type": "object",
      "properties": {
        "ollama": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string" },
              "size_bytes": { "type": "integer" },
              "parameter_size": { "type": "string" },
              "quantization": { "type": "string" },
              "family": { "type": "string" }
            }
          }
        },
        "ollama_tested": { "type": "boolean" },
        "llamafarm": { "type": "array" },
        "huggingface": { "type": "array" },
        "gguf_files": { "type": "array" }
      }
    },
    "hardware": {
      "type": "object",
      "properties": {
        "cameras": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "index": { "type": "integer" },
              "name": { "type": "string" },
              "type": { "type": "string" },
              "tested": { "type": "boolean" }
            }
          }
        },
        "microphones": { "type": "array" },
        "speakers": { "type": "array" }
      }
    },
    "services": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "port": { "type": "integer" },
          "service_type": { "type": "string" },
          "name": { "type": "string" },
          "verified": { "type": "boolean" },
          "endpoint": { "type": "string" }
        }
      }
    },
    "test_results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "status": { "enum": ["passed", "failed", "skipped", "error"] },
          "duration_ms": { "type": "number" },
          "message": { "type": "string" }
        }
      }
    }
  }
}
```

### Example Output

```json
{
  "scan_id": "scan-abc123",
  "timestamp": "2025-01-15T10:30:00Z",
  "duration_ms": 3450,
  "system": {
    "os": "Darwin",
    "os_version": "25.2.0",
    "arch": "arm64",
    "cpu_brand": "Apple M1 Max",
    "cpu_cores": 10,
    "cpu_threads": 10,
    "ram_total_gb": 64.0,
    "ram_available_gb": 48.2,
    "disk_total_gb": 926.0,
    "disk_available_gb": 450.0
  },
  "gpu": {
    "metal": {
      "name": "Apple M1 Max",
      "vendor": "Apple",
      "metal_version": "Metal 4",
      "cores": 24
    },
    "metal_tested": true
  },
  "npu": {
    "apple_ane": {
      "available": true,
      "chip": "Apple M1 Max",
      "ane_cores": 16
    }
  },
  "models": {
    "ollama": [
      {
        "name": "qwen3:8b",
        "size_bytes": 5225388164,
        "parameter_size": "8.2B",
        "quantization": "Q4_K_M",
        "family": "qwen3"
      },
      {
        "name": "llama3.2:latest",
        "size_bytes": 2019393189,
        "parameter_size": "3.2B",
        "quantization": "Q4_K_M",
        "family": "llama"
      }
    ],
    "ollama_tested": true,
    "huggingface": [
      {
        "repo_id": "BAAI/bge-reranker-v2-m3",
        "revision": "abc12345",
        "size_bytes": 1234567890
      }
    ]
  },
  "hardware": {
    "cameras": [
      {
        "index": 0,
        "name": "FaceTime HD Camera",
        "type": "video",
        "tested": true
      }
    ],
    "microphones": [
      {
        "index": 0,
        "name": "MacBook Pro Microphone",
        "type": "input",
        "channels": 2
      }
    ]
  },
  "services": [
    {
      "port": 11434,
      "service_type": "ollama",
      "name": "Ollama API",
      "verified": true,
      "endpoint": "http://localhost:11434"
    },
    {
      "port": 14345,
      "service_type": "llamafarm",
      "name": "LlamaFarm API",
      "verified": true,
      "endpoint": "http://localhost:14345"
    }
  ],
  "test_results": [
    {"name": "metal_inference", "status": "passed", "duration_ms": 245},
    {"name": "ollama_generate", "status": "passed", "duration_ms": 1200},
    {"name": "camera_capture", "status": "passed", "duration_ms": 89}
  ]
}
```

---

## Implementation Plan

### Phase 1: Core Scanner (2-3 days)

1. **Create module structure**
   - `atmosphere/scanner/__init__.py`
   - `atmosphere/scanner/gpu.py`
   - `atmosphere/scanner/models.py`
   - `atmosphere/scanner/hardware.py`
   - `atmosphere/scanner/services.py`
   - `atmosphere/scanner/tester.py`
   - `atmosphere/scanner/main.py`

2. **Implement GPU detection** (0.5 day)
   - Metal detection for macOS
   - CUDA detection for NVIDIA
   - Basic testing

3. **Implement model detection** (0.5 day)
   - Ollama API integration
   - HuggingFace cache scanning
   - GGUF file finder

4. **Implement system info** (0.25 day)
   - CPU, RAM, disk detection
   - Cross-platform support

### Phase 2: Hardware & Services (2 days)

5. **Implement hardware detection** (0.5 day)
   - Camera detection (macOS + Linux)
   - Microphone detection
   - Speaker detection

6. **Implement service detection** (0.5 day)
   - Port probing
   - Docker container discovery
   - Service verification

7. **Implement capability tester** (1 day)
   - Test framework
   - GPU inference tests
   - Model generation tests
   - Hardware capture tests

### Phase 3: CLI & Integration (1-2 days)

8. **Implement CLI** (0.5 day)
   - `atmosphere scan` command
   - Output formatting (JSON, YAML, pretty)
   - Progress display

9. **Registry integration** (0.5 day)
   - Convert scan results to Capability objects
   - Auto-register discovered capabilities
   - Gossip message generation

10. **Testing & polish** (0.5-1 day)
    - Unit tests for each scanner
    - Integration tests
    - Documentation

### Total Effort: ~5-7 days

---

## Open Questions

### Decisions Needed

1. **Scan frequency**: Should scanning happen at startup only, or periodically? 
   - Recommendation: Startup + on-demand via CLI + optional periodic refresh

2. **Capability naming**: How should auto-discovered capabilities be named?
   - Recommendation: `{node_id}:{type}:{index}` e.g., `macbook:metal:0`, `macbook:ollama:qwen3-8b`

3. **Model testing scope**: Should we test ALL models or just one per service?
   - Recommendation: Test smallest model only (fast), with `--test-all` flag for thorough testing

4. **Hardware access permissions**: How to handle permission prompts (camera, mic)?
   - Recommendation: Skip test if permission denied, note in results

5. **Remote scanning**: Should the scanner work over SSH to other nodes?
   - Recommendation: Phase 2 feature, focus on local first

6. **Caching**: Should scan results be cached?
   - Recommendation: Yes, with TTL (e.g., 5 minutes) and force-refresh option

### Future Considerations

- **Windows support**: Different APIs for GPU, hardware detection
- **Container awareness**: Detect if running inside Docker/Podman
- **GPU memory tracking**: Real-time VRAM usage for load balancing
- **Network capabilities**: Bandwidth testing for distributed inference
- **Power awareness**: Battery state, thermal throttling detection

---

## References

- [PyTorch MPS Backend](https://pytorch.org/docs/stable/notes/mps.html)
- [NVIDIA SMI Documentation](https://developer.nvidia.com/nvidia-system-management-interface)
- [ROCm SMI Documentation](https://rocm.docs.amd.com/projects/rocm_smi_lib/en/latest/)
- [Ollama API Reference](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [AVFoundation Device Discovery](https://developer.apple.com/documentation/avfoundation/capture_setup)
- [V4L2 API](https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/v4l2.html)
