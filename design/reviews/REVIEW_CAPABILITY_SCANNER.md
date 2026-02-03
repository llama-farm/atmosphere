# Design Review: CAPABILITY_SCANNER.md

**Reviewer:** Fight Agent (Critic)  
**Date:** 2026-02-02  
**Rating:** 🟡 NEEDS WORK - Solid foundation but has significant gaps

---

## Summary

The Capability Scanner design is **well-structured and comprehensive** for the happy path. Detection methods for GPUs, models, and hardware are reasonable. However, the design has **critical gaps in error handling, security, and real-world edge cases** that will cause failures in production environments.

---

## Technical Soundness

### ✅ What Works

- [x] Architecture diagram clearly separates concerns (scanners → tester → registry)
- [x] GPU detection for Metal/CUDA/ROCm covers the major platforms
- [x] Model detection (Ollama, HuggingFace, GGUF) is pragmatic
- [x] "Test, don't assume" philosophy is correct
- [x] CLI integration design is clean and user-friendly

### ❌ Critical Issues

#### 1. **No Permission Handling - Scanner Will Crash**

The design shows:

```python
def detect_cameras_macos() -> List[CameraDevice]:
    result = subprocess.run(
        ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True,
        ...
    )
```

**Challenge:** On macOS Sonoma+, accessing camera list requires explicit permission. Without TCC (Transparency, Consent, and Control) approval:
- `ffmpeg` will prompt the user
- Or be denied and return empty/error
- Or the app needs to be pre-approved

**The same applies to:**
- Microphone access
- Screen recording (for screen capture detection)
- Location services (if ever added)

**The design completely ignores permissions.** No mention of:
- Checking if permission is granted before attempting
- Gracefully degrading if permission denied
- Guiding user through permission granting

#### 2. **subprocess Calls Are a Security Risk**

```python
result = subprocess.run(
    ["find", str(search_path), "-name", "*.gguf", "-type", "f", "-maxdepth", str(max_depth)],
    ...
)
```

**Challenge:** If `search_path` comes from user config (e.g., `GGUF_SEARCH_PATHS`), this is command injection waiting to happen:

```yaml
# Evil config
gguf_search_paths:
  - "/home/user; rm -rf /"
```

**Mitigation needed:**
- Validate/sanitize all paths
- Use `pathlib` instead of string concatenation
- Consider using Python's `os.walk()` instead of subprocess find

#### 3. **GPU Test Can Cause Visible Artifacts**

```python
def _test_metal_inference(self) -> bool:
    device = torch.device("mps")
    x = torch.randn(10, 10, device=device)
    y = torch.mm(x, x)
    return y.shape == (10, 10)
```

**Challenge:** Creating a tensor on MPS can:
- Cause GPU context creation (slow, visible)
- Trigger macOS "app is using graphics" notifications
- Compete with other GPU apps
- On some systems, cause brief screen flicker

**Recommendation:** Document that GPU test has side effects, or provide `--skip-gpu-test` flag.

#### 4. **Camera Test Captures a Real Frame**

```python
def test_camera(index: int = 0) -> bool:
    cap = cv2.VideoCapture(index)
    ret, frame = cap.read()
    cap.release()
    return ret and frame is not None
```

**Challenge:** This **actually captures a frame from the camera**.
- On laptops, the camera LED turns on
- Users will wonder "why is my camera turning on during setup?"
- Privacy concern: frame is captured (and discarded, but still)

**This is acknowledged nowhere in the design.** Users should be warned, or camera testing should be opt-in.

#### 5. **Microphone Test Records Audio**

Same issue as camera:

```python
def test_microphone(index: int = 0) -> bool:
    stream = p.open(format=pyaudio.paInt16, ...)
    data = stream.read(1024, ...)
```

**Challenge:** This records ~64ms of audio. Without user consent, this is a privacy violation in some jurisdictions (EU, California).

#### 6. **Service Detection Hits Real Endpoints**

```python
async def verify_service(service: DetectedService) -> DetectedService:
    for endpoint in ["/health", "/healthz", "/api/tags", "/"]:
        response = await client.get(f"{service.endpoint}{endpoint}")
```

**Challenge:** This makes HTTP requests to services. What if:
- The service has auth and returns 401 (detected as working?)
- The service has rate limiting and blocks the scanner
- The service is a honeypot logging all requests
- The `/` endpoint is expensive (full page render)

**Recommendation:** Make verification opt-in, or use HEAD requests, or only check port connectivity by default.

---

## Completeness

### ❌ Missing Critical Pieces

#### 1. **No Caching Strategy**

The scanner "completes in < 5 seconds" but has no caching:

**Challenge:** 
- Every `atmosphere scan` rescans everything
- Every node startup rescans
- No incremental updates ("model X was added since last scan")

**Recommendation:**
- Cache scan results with TTL
- Watch for file system changes (new GGUF files)
- Diff against previous scan

#### 2. **No Scan Scope Configuration**

The design assumes scanning everything:
- All directories for GGUF
- All cameras
- All ports

**Challenge:** User might want:
- "Only scan /models directory, not ~/Downloads"
- "Don't probe my database ports (6379, 5432)"
- "Skip camera detection entirely"

**No configuration shown for narrowing scope.**

#### 3. **No Progress Reporting**

CLI shows:
```python
with Progress(SpinnerColumn(), ...):
    task = progress.add_task("Scanning GPUs...", total=None)
```

**Challenge:** `total=None` means indeterminate progress. User has no idea:
- How long this will take
- What percentage is complete
- What is currently being scanned

For a 5-second scan this is fine. But if model testing takes 30 seconds, users will think it's hung.

#### 4. **No Partial Failure Handling**

What if:
- GPU scan works but camera scan fails?
- Ollama is found but unreachable?
- One of 10 models fails to test?

**Design doesn't show:**
- Continuing after partial failure
- Reporting which parts succeeded/failed
- Allowing retry of failed components

#### 5. **No Concurrent Scanning**

```python
# Sequential scanning
results["gpu"] = asyncio.run(scan_gpus(test=test))
results["models"] = asyncio.run(scan_models(host=host, test=test))
results["hardware"] = asyncio.run(scan_hardware(test=test))
```

**Challenge:** These are independent! Why not parallel?

```python
results = await asyncio.gather(
    scan_gpus(test=test),
    scan_models(host=host, test=test),
    scan_hardware(test=test),
)
```

Would cut scan time significantly.

---

## Cross-Platform

### ⚠️ macOS Specifics

- `system_profiler` commands are macOS-only
- AVFoundation is macOS-only
- launchd detection is macOS-only
- TCC permissions are macOS-specific

### ⚠️ Linux Specifics

- `/proc/cpuinfo` parsing is Linux-only
- `v4l2-ctl` is Linux-only
- `arecord` is Linux-only (ALSA)
- systemd detection is Linux-only

### ❌ Windows Completely Missing

- No WMI queries for hardware
- No DXGI for GPU detection
- No Windows audio device enumeration
- No Windows service detection

**Yet the design says:**
> "Cross-Platform - macOS and Linux first, Windows later"

"Later" needs a timeline, or this is tech debt that never ships.

### ❌ Container Environment Not Considered

What happens when scanner runs in Docker?
- No cameras
- No microphones
- No GPU (unless nvidia-docker)
- No systemd
- Fake `/proc` filesystem

**The scanner should detect container environment and adjust expectations.**

---

## Specific Challenges

### "Fast - Full scan completes in < 5 seconds"

**Challenge:** This claim is untested. Let's break it down:

| Component | Time Estimate |
|-----------|---------------|
| GPU detection | 0.5s |
| Metal/CUDA test | 1-2s (tensor creation is slow) |
| Ollama API call | 0.5-2s (depends on network) |
| Model test (single token) | 5-30s per model! |
| Camera detection | 0.5s |
| Camera test (frame capture) | 1-2s |
| Microphone detection | 0.3s |
| Port probing (10 ports) | 1s with 1s timeout each? Or parallel? |

**If testing is enabled, scan is 30+ seconds, not 5.**

### "Safe - Read-only detection, no side effects"

**This is FALSE.**

Side effects documented above:
- Camera LED turns on
- Audio is captured
- HTTP requests to services
- GPU context created

### "Accurate - Actually test capabilities, don't just check for existence"

**Challenge:** Testing introduces the side effects above. The design needs to:
1. Default to existence-only detection
2. Make testing opt-in with explicit `--test` flag
3. Warn users what testing does

The CLI shows `--test` flag, but the warnings are missing.

### NPU Detection is Shallow

```python
def detect_apple_neural_engine() -> Optional[dict]:
    # ANE is available on A11+ chips and all Apple Silicon Macs
    if "Apple" in chip:
        return {"available": True, ...}
```

**Challenge:** This doesn't detect ANE, it detects Apple Silicon. ANE availability != ANE usability for ML workloads. CoreML models must be specifically compiled for ANE.

**Recommendation:** Either test ANE with a real CoreML model or document as "Apple Silicon detected (ANE assumed available)".

### Ollama Model Testing is Expensive

```python
def test_ollama_model(model_name: str, ...):
    response = client.post(
        f"http://{host}:{port}/api/generate",
        json={"model": model_name, "prompt": "Hi", "options": {"num_predict": 1}}
    )
```

**Challenge:** Generating even 1 token:
- Loads model into memory (10-60 seconds for large models!)
- Uses GPU VRAM
- Can OOM if model is too large

**If user has 26 Ollama models, testing all of them:**
- Takes 5-30 minutes
- Uses all their VRAM
- Might crash from OOM

**Recommendation:** Test only if model is already loaded, or test a sample, or make testing explicit per-model.

---

## JSON Schema Issues

The output schema shows:
```json
{
  "gpu": {
    "metal": { ... },
    "metal_tested": { "type": "boolean" }
  }
}
```

**Challenge:** `metal_tested` is outside `metal` object. Inconsistent nesting. Should be:
```json
{
  "gpu": {
    "metal": {
      "name": "...",
      "tested": true
    }
  }
}
```

---

## Recommendations

### Critical (Must Fix)

1. **Add permission checking before hardware access**
   - macOS TCC status check
   - Graceful degradation if denied
   - Guide user through approval

2. **Make testing opt-in and warn about side effects**
   - Camera LED will activate
   - Audio will be captured
   - Model loading may take minutes

3. **Fix security issues**
   - Validate search paths
   - Don't use subprocess with user input
   - Rate limit service probing

4. **Add container environment detection**
   - Detect Docker/K8s
   - Adjust expectations (no hardware)
   - Skip irrelevant scans

### High Priority

1. **Add caching**
   - Cache results for 1 hour
   - Incremental updates
   - Manual refresh option

2. **Parallel scanning**
   - Independent scans should run concurrently
   - Cut total time by 2-3x

3. **Scope configuration**
   - Allow disabling categories
   - Allow custom search paths
   - Allow port exclusions

### Nice to Have

1. **Progress reporting**
   - Per-component progress
   - Time estimates
   - Current operation visibility

2. **Windows support timeline**
   - Define what "later" means
   - Or explicitly mark as unsupported

---

## Verdict

🟡 **NEEDS WORK**

The scanner design is **solid conceptually** but has:
- **Security issues** with subprocess and unvalidated paths
- **Privacy issues** with camera/mic testing
- **Permission handling completely absent**
- **Unrealistic performance claims** (5 seconds with testing is impossible)
- **Missing container awareness**

**Blocker?** Yes - the permission handling gap will cause the scanner to fail/crash on macOS. Must be addressed before implementation.

---

*The scanner is the foundation for capability discovery. Getting this right matters. Fix the permission and security issues, make testing opt-in with clear warnings, and this becomes a solid component.*
