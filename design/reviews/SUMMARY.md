# Design Review Summary

**Reviewer:** Fight Agent  
**Date:** 2026-02-02  
**Total Docs Reviewed:** 6

---

## Overview Table

| Design | Rating | Key Issues | Blocker? |
|--------|--------|------------|----------|
| **PACKAGING.md** | 🟡 NEEDS WORK | Quick fixes not done, Windows missing, Debian deps unverified | No |
| **COST_MODEL.md** | 🟡 NEEDS WORK | Apple GPU detection fictional, stale thresholds too long, no oscillation prevention | Yes (GPU detection) |
| **CAPABILITY_SCANNER.md** | 🟢 APPROVED | ANE hardcoding, 5s scan target unrealistic, permission detection missing | No |
| **OWNER_APPROVAL.md** | 🟢 APPROVED | Pattern matching undocumented, revocation timing unclear | No |
| **MATTER_INTEGRATION.md** | 🟢 APPROVED | Node.js dependency, bridge lifecycle, no rate limiting | No |
| **ANDROID_APP.md** | 🟡 NEEDS WORK | **Effort massively underestimated**, iOS missing, battery/permissions incomplete | Yes (effort) |

---

## Ratings Breakdown

### 🟢 APPROVED (3 docs)

1. **CAPABILITY_SCANNER.md** - Solid architecture with minor fixable issues
2. **OWNER_APPROVAL.md** - Best design in the batch, excellent privacy-first thinking
3. **MATTER_INTEGRATION.md** - Well-researched, correct technology choices

### 🟡 NEEDS WORK (3 docs)

1. **PACKAGING.md** - Fundamentals are there but execution details missing
2. **COST_MODEL.md** - Great concept, broken implementation for Apple Silicon
3. **ANDROID_APP.md** - Right architecture, wildly unrealistic scope

---

## Critical Issues Across All Designs

### 1. **Effort Estimation is Consistently Optimistic**

Every design underestimates effort:
- Packaging: Claims 8-15 hours → Realistic 20-30 hours
- Cost Model: Claims 11-17 days → Realistic 18-25 days
- Capability Scanner: No estimate → Realistic 11-18 days
- Android App: No clear estimate → Realistic 11-15 WEEKS

**Pattern:** Designs are written as if everything works first try. They don't account for:
- Debugging edge cases
- Testing on multiple platforms/devices
- Integration issues between components
- Real-world user feedback cycles

### 2. **Windows Support is Ignored**

| Design | Windows Coverage |
|--------|-----------------|
| Packaging | "Deferred" (no details) |
| Cost Model | Completely missing |
| Capability Scanner | Completely missing |
| Owner Approval | N/A (platform agnostic) |
| Matter Integration | Works via Node.js |
| Android App | N/A |

**This is a pattern.** If Windows is not supported, SAY SO EXPLICITLY. Don't leave it ambiguous.

### 3. **Security Considerations Are Surface-Level**

Each design mentions security but lacks depth:
- File permissions not enforced
- Credential storage not specified (Android Keystore? macOS Keychain?)
- Audit logging mentioned but not designed
- PIN/secret handling not sanitized from logs

### 4. **Platform-Specific Code is Duplicated**

Multiple designs implement:
- Battery detection
- CPU/GPU monitoring
- Network state detection

Each does it slightly differently. There should be a shared `atmosphere.platform` module.

### 5. **Testing Strategy is Underspecified**

Most designs mention tests but don't specify:
- What devices/platforms to test on
- What CI/CD infrastructure is needed
- What performance benchmarks to hit
- What coverage targets exist

---

## Dependencies Between Designs

```
CAPABILITY_SCANNER.md ──────────►  OWNER_APPROVAL.md
        │                                 │
        │ (discovers capabilities)        │ (approves exposure)
        │                                 │
        ▼                                 ▼
   COST_MODEL.md ◄─────────────── PACKAGING.md
        │                                 │
        │ (routing decisions)             │ (distribution)
        │                                 │
        ▼                                 ▼
ANDROID_APP.md ◄──────────────── MATTER_INTEGRATION.md
        │                                 │
        │ (mobile capabilities)           │ (IoT devices)
        │                                 │
        └─────────────► ATMOSPHERE MESH ◄─┘
```

**Implementation Order Recommendation:**

1. **PACKAGING.md** - Get pip install working first
2. **CAPABILITY_SCANNER.md** - Need discovery before approval
3. **OWNER_APPROVAL.md** - Need approval before mesh exposure
4. **COST_MODEL.md** - Need cost for intelligent routing
5. **MATTER_INTEGRATION.md** - Extends capabilities
6. **ANDROID_APP.md** - Last (largest effort, most dependencies)

---

## Blockers Requiring Immediate Attention

### 🔴 Blocker 1: Cost Model GPU Detection

**COST_MODEL.md** claims to detect Apple Silicon GPU usage by process name matching:

```python
gpu_processes = ["ollama", "mlx_lm", "stable-diffusion"]
return {"gpu_percent": min(active_gpu_processes * 30.0, 100.0)}
```

**This is not GPU detection.** It's guessing. It will:
- Report 30% for an idle Ollama process
- Report 0% for a Metal game using 100% GPU
- Report 60% for two processes where one uses 5% and one uses 95%

**Fix Required:** Either:
1. Implement real GPU monitoring (requires `powermetrics` with sudo or IOKit)
2. Or document as "best effort estimate, not actual measurement"
3. Or remove Apple GPU from cost calculation entirely

### 🔴 Blocker 2: Android App Effort

**ANDROID_APP.md** proposes:
- Rust core with full protocol implementation
- PyO3 bindings for Python
- JNI bindings for Android
- Android app with 4+ capabilities
- On-device inference with llama.cpp
- UI with Jetpack Compose

Without an explicit timeline, but the implicit assumption seems to be "a few weeks."

**Reality:** This is **3-4 months** of focused engineering for a small team. Starting with unrealistic expectations will cause:
- Scope creep
- Quality shortcuts
- Missed deadlines
- Team frustration

**Fix Required:** Add explicit timeline with realistic effort estimates per component.

---

## Recommendations for All Designs

### Before Implementation

1. **Add realistic effort estimates**
   - Multiply initial guess by 2-3x
   - Break down by component with clear milestones

2. **Decide on Windows**
   - Support it and design for it
   - Or explicitly mark as "not supported"

3. **Create shared platform abstraction**
   - One module for battery, CPU, GPU, network detection
   - Used by Cost Model, Capability Scanner, Android App

4. **Define security requirements**
   - Where are secrets stored?
   - What gets logged?
   - What permissions are checked?

5. **Specify testing infrastructure**
   - CI/CD pipeline requirements
   - Test device matrix
   - Performance benchmarks

### During Implementation

1. **Track actual vs estimated effort**
   - Learn from discrepancies
   - Adjust future estimates

2. **Integration tests between components**
   - Scanner → Approval flow
   - Cost → Routing flow
   - Mesh → Matter flow

3. **Real device testing**
   - Multiple macOS versions
   - Multiple Linux distros
   - Multiple Android devices/versions

---

## Final Verdict

| Verdict | Count |
|---------|-------|
| 🟢 Ready for Implementation | 3 |
| 🟡 Needs Work Before Implementation | 3 |
| 🔴 Rejected / Fundamental Problems | 0 |

**Overall Assessment:** The designs are conceptually sound but underestimate execution complexity. The architecture is good—Rust core, gossip protocol, semantic routing, privacy-first approval—but the devil is in the details.

**Recommendation:** 
1. Fix the two blockers (GPU detection, Android effort)
2. Address the "Needs Work" items in each design
3. Proceed with implementation in the recommended order

---

*Review complete. These designs represent significant architectural thinking. The issues identified are fixable. Good luck with implementation.*
