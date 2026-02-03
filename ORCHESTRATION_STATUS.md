# Atmosphere Build Orchestration

**Started:** 2026-02-03 02:41 CT  
**Status:** 🟡 DESIGN PHASE

---

## Phase 1: Design Agents (ACTIVE)

| Agent | Label | Task | Status |
|-------|-------|------|--------|
| 1 | design-capability-scanner | Capability Scanner design | 🔄 Running |
| 2 | design-owner-approval | Owner Approval UI design | 🔄 Running |
| 3 | design-packaging | pip/Homebrew packaging | 🔄 Running |
| 4 | design-cost-model | Dynamic cost model | 🔄 Running |
| 5 | design-android-app | Android app (shared core) | 🔄 Running |
| 6 | design-matter-iot | Matter/IoT integration | 🔄 Running |
| 7 | design-fight-agent | Review & challenge designs | 🔄 Waiting for designs |

## Expected Outputs (Design Phase)

- [x] `design/CAPABILITY_SCANNER.md` (59KB) ✅
- [x] `design/OWNER_APPROVAL.md` (77KB) ✅
- [x] `design/PACKAGING.md` (32KB) ✅
- [x] `design/COST_MODEL.md` (41KB) ✅
- [x] `design/ANDROID_APP.md` (82KB) ✅
- [x] `design/MATTER_INTEGRATION.md` (48KB) ✅
- [ ] `design/reviews/SUMMARY.md` (in progress)

---

## Phase 2: Implementation Agents (PENDING)

Will spawn after designs are reviewed and approved:

| Agent | Task | Depends On |
|-------|------|------------|
| impl-capability-scanner | Build scanner | Design approved |
| impl-owner-approval | Build approval UI | Design approved |
| impl-packaging | Build pip/brew packages | Design approved |
| impl-cost-model | Build cost system | Design approved |
| impl-android-core | Build Rust core | Design approved |
| impl-android-app | Build Android app | Rust core |
| impl-matter | Build Matter bridge | Design approved |

---

## Phase 3: Integration & Testing (PENDING)

| Agent | Task |
|-------|------|
| integration-test | Run all demos on real APIs |
| ui-integration | Verify UI components work |
| e2e-test | Full end-to-end workflow |

---

## Services Status

```
✅ LlamaFarm: http://localhost:14345 (healthy)
✅ Universal Runtime: http://localhost:11540 (healthy)
✅ Ollama: http://localhost:11434 (26 models)
```

---

## Key Decisions

### Android: Shared Core Strategy
- ✅ Use Rust core with JNI bindings
- ❌ Do NOT rewrite protocol in Kotlin
- ❌ Do NOT use Python + Chaquopy (too heavy)

### Packaging Priority
1. PyPI (pip install atmosphere-mesh)
2. Homebrew (brew install llama-farm/tap/atmosphere)
3. Debian/Ubuntu (apt install atmosphere)
4. Docker image

### Cost Model Factors
- Battery state (2x-5x multiplier)
- CPU/GPU load (linear scaling)
- Network type (metered = 3x)
- Cloud API costs (actual $$$)

---

## Timeline Estimate

| Phase | Duration | Status |
|-------|----------|--------|
| Design | 30-60 min | 🔄 Active |
| Review | 15-30 min | ⏳ Pending |
| Implementation | 2-4 hours | ⏳ Pending |
| Testing | 30-60 min | ⏳ Pending |

---

*Last updated: 2026-02-03 02:42 CT*
