# Design Review: COST_MODEL.md

**Reviewer:** Fight Agent (Critic)  
**Date:** 2026-02-02  
**Rating:** 🟡 NEEDS WORK - Has issues but fixable

---

## Summary

The cost model design is **conceptually strong** - the idea of dynamically routing work based on power state, compute load, and network conditions is excellent. However, the implementation details have **significant gaps, platform-specific assumptions, and missing edge cases** that will cause problems in production.

---

## Technical Soundness

### ✅ What Works

- [x] Multi-factor cost model makes sense (power, compute, network, API costs)
- [x] Platform-specific detection approaches are generally correct
- [x] Gossip integration concept is sound
- [x] API cost table is useful and current

### ❌ Critical Issues

#### 1. **Race Condition in Cost Collection**

The `MacOSCostCollector` runs multiple subprocess calls:

```python
def collect(self) -> NodeCostFactors:
    return NodeCostFactors(
        **self._get_power_state(),   # subprocess call
        **self._get_compute_load(),  # multiple subprocess calls
        **self._get_network_state()  # subprocess call
    )
```

**Challenge:** What if the system state changes between calls? You could have:
- Power state: "on battery"
- CPU load: measured while plugged in (low because charging)
- Network: measured after power state changed again

This creates **inconsistent snapshots**. A single moment in time should be captured atomically where possible.

**Mitigation:** Use `psutil` for most metrics in a single call, or add timestamps to each factor and reject internally-inconsistent data.

#### 2. **GPU Detection for Apple Silicon is WRONG**

```python
def get_apple_gpu_estimate() -> dict | None:
    gpu_processes = ["ollama", "mlx_lm", "stable-diffusion"]
    # ...
    return {
        "gpu_percent": min(active_gpu_processes * 30.0, 100.0),
    }
```

**This is not GPU detection. This is process name matching.**

**Challenge:** 
- What if someone runs a GPU workload with a different process name?
- What if Ollama is running but IDLE (not inferring)?
- What if a Metal game is running and using 100% GPU but isn't in your list?

**The 30% per process is completely made up.** A single Ollama process running a 7B model uses ~60% GPU. Running a 70B model might use 95%. The estimate is worthless.

**Reality:** Apple Silicon GPU monitoring requires:
- `powermetrics` (needs sudo)
- Or IOKit/Metal Performance HUD integration
- Or accept that we CAN'T accurately measure Apple GPU and document this limitation

#### 3. **psutil is Not in Dependencies**

The design relies heavily on `psutil`:
- `psutil.sensors_battery()`
- `psutil.cpu_percent()`
- `psutil.virtual_memory()`
- `psutil.net_io_counters()`
- `psutil.getloadavg()`

**But psutil is listed in PACKAGING.md as a core dependency... or is it?**

Cross-reference with PACKAGING.md shows `psutil>=5.9.0` in the example but needs verification. If it's not actually in `pyproject.toml`, the entire cost collection system fails at runtime with `ImportError`.

#### 4. **Stale Cost Data Threshold is Too Long**

```python
stale_threshold_seconds: float = 120.0
```

**Challenge:** 120 seconds is an eternity for power state. Consider:
- User unplugs laptop at T=0
- Cost data says "plugged in" for up to 2 minutes
- Heavy inference routed to laptop draining battery

**Recommendation:** 30-60 seconds max for power state. Consider different thresholds for different factors.

#### 5. **Network Bandwidth Estimation is Aspirational**

```python
class BandwidthEstimator:
    """Estimate available bandwidth from transfer history."""
```

**Challenge:** This requires:
1. Actually recording every transfer
2. Maintaining the window of samples
3. Having enough samples to estimate

**What happens on a fresh node with no transfer history?** `estimate_mbps()` returns `None`, and the routing logic uses... what default?

The design shows:
```python
if bandwidth_mbps is not None:
    # apply penalties
```

But never defines what happens when it's None. Is it assumed to be fast? Slow? Unknown?

#### 6. **Metered Connection Detection is Unreliable**

macOS detection:
```python
# Check for iPhone USB/WiFi tethering
if "iPhone" in iface_result.stdout:
    return True

# Check WiFi SSID for hotspot patterns
hotspot_patterns = ["iphone", "android", "hotspot", "mobile", "tether"]
```

**Problems:**
- User's home WiFi is named "iPhone Backup Network" - falsely detected as metered
- USB Ethernet adapter named "iPhone USB" - false positive
- Legitimate hotspot named "Bob's Network" - false negative
- VPN connections - completely unhandled

**Challenge:** Metered detection is inherently unreliable. The design should:
1. Allow explicit user override
2. Treat "unknown" as a separate state
3. Not rely on SSID name matching

---

## Completeness

### ❌ Missing Critical Pieces

#### 1. **No Cost Normalization**

Different factors have different scales:
- CPU load: 0-1 (or 0-2 for overload)
- Battery percent: 0-100
- Bandwidth: 0-1000+ Mbps
- API cost: $0-$0.10+ per request

The multipliers are applied, but there's no discussion of:
- Are these multipliers balanced?
- How were the specific values (2.0x, 3.0x, 5.0x) chosen?
- Has anyone actually tested if battery penalty of 5.0x is enough to route away from a low-battery node?

**Challenge:** The multipliers look like guesses. Where's the empirical validation?

#### 2. **No Hysteresis / Oscillation Prevention**

Consider:
- Node A: cost 2.0
- Node B: cost 2.1
- Work routed to Node A
- Node A now: cost 2.2
- Node B now: cost 2.0
- Work routed to Node B
- ...

**Challenge:** Without hysteresis, routing will oscillate between nodes that are close in cost. This causes:
- Cache misses
- Connection churn
- Poor locality

**Recommendation:** Add minimum cost difference threshold (e.g., 20%) before switching nodes, or sticky routing for a time window.

#### 3. **No Cost History/Trending**

The model captures current state but not trends:
- Battery at 50% and charging vs. Battery at 50% and draining
- CPU load spiking up vs. settling down
- Bandwidth improving vs. degrading

**Challenge:** A node whose battery is charging at 50% should be preferred over one draining at 50%. Current design treats them the same.

#### 4. **No Multi-Workload Awareness**

Cost calculation is per-request, but:
- What if a node is about to receive 10 routed requests?
- What if a single heavy request will spike CPU for 30 seconds?
- What if the workload is batched?

**Challenge:** By the time cost is calculated, 5 other requests might have been routed to the same "cheap" node, all based on the same cost snapshot.

**Recommendation:** Include pending/queued work in cost calculation.

#### 5. **Thermal Throttling Acknowledged but Not Implemented**

Open question mentions:
> "Thermal throttling: Should we detect and penalize thermally-throttled nodes?"

**This should be a YES, not a question.** Thermal throttling:
- Dramatically reduces performance
- Indicates the node is already stressed
- Is detectable on both macOS and Linux

Why is this not in the design?

---

## Code Sharing / Consistency

### ⚠️ Issues

#### 1. **Duplication Between Collectors**

`MacOSCostCollector` and `LinuxCostCollector` share:
- Same return structure
- Same logic for combining factors
- Similar subprocess error handling

**Recommendation:** Create `BaseCostCollector` abstract class with shared methods, platform-specific implementations only for detection.

#### 2. **Inconsistent Error Handling**

Some methods:
```python
except Exception:
    return {}  # Silently swallow
```

Others:
```python
except Exception:
    pass  # Also silent
```

**Challenge:** Silent failures hide bugs. At minimum, log at DEBUG level.

#### 3. **Magic Numbers Everywhere**

```python
score *= 0.95 ** cap.hop_count  # Why 0.95?
score *= 1.1  # Large model boost - arbitrary
result["gpu_load"] = min(active_gpu_processes * 30.0, 100.0)  # 30% made up
```

**Recommendation:** Define these as named constants with comments explaining the rationale:
```python
HOP_PENALTY_FACTOR = 0.95  # 5% cost increase per hop - based on typical network latency
LARGE_MODEL_BOOST = 1.1   # Prefer larger models for complex tasks - empirically tuned
```

---

## Cross-Platform

### ✅ macOS and Linux Covered

Both platforms have implementations, though with issues noted above.

### ❌ Windows Completely Missing

No `WindowsCostCollector`. No discussion of:
- `wmic` for battery status
- `typeperf` for CPU counters
- Network metrics on Windows
- GPU detection (NVIDIA, AMD, Intel)

**Challenge:** Windows support is either in scope or out. If out, document it. If in, implement it.

### ⚠️ Container Awareness

What happens when running in Docker/Kubernetes?
- `psutil.sensors_battery()` returns `None`
- `/sys/class/power_supply/` doesn't exist
- CPU/memory limits from cgroups not accounted for

**Challenge:** A container with 2 CPU limit looks idle (node has 64 cores at 3% = low load) but is actually maxed out within its limit.

**Recommendation:** Detect container environment and read cgroup limits.

---

## Specific Challenges

### "Budget Sensitivity Per-User"

Open question:
> "Budget sensitivity: Should this be per-user or system-wide?"

**Neither is right on its own.** Consider:
- System-wide default
- Per-mesh override
- Per-request override via API

All three are needed for different use cases.

### "The 120-Second Stale Threshold"

**Challenge:** What's the basis for this number? 
- Too short: Excessive gossip traffic
- Too long: Stale routing decisions

This needs empirical testing with real workloads, not a magic number.

### "API Cost Table Maintenance"

```python
API_COSTS: Dict[str, APIModelCost] = {
    "gpt-4o": APIModelCost(2.50, 10.00),
    # ...
}
```

**Challenge:** API prices change frequently. This table will be outdated within months.

**Recommendation:**
1. Fetch pricing from provider APIs dynamically
2. Or cache with TTL and refresh
3. Or at minimum document that this needs regular updates

### "Significant Change Detection"

```python
self.battery_threshold = 10.0  # percent
self.cpu_threshold = 0.20  # normalized
```

**Challenge:** These thresholds interact:
- Battery drops 5% (below threshold)
- CPU drops 15% (below threshold)
- Network changes from metered to unmetered (significant!)

But you only check individual thresholds. What if the **combined** cost changes significantly but each individual factor doesn't?

---

## Implementation Plan Review

### Estimates Are Questionable

| Phase | Claimed | Reality Check |
|-------|---------|---------------|
| Phase 1: Local Collection | 2-3 days | Reasonable if platforms work. GPU detection will eat time. |
| Phase 2: Gossip Integration | 2-3 days | Depends on existing gossip stability. Could be fast or slow. |
| Phase 3: Router Integration | 3-4 days | This is where the real complexity lives. 5-7 days more likely. |
| Phase 4: API Costs | 1-2 days | Table maintenance not included. Add 1 day. |
| Phase 5: Network Awareness | 2-3 days | Metered detection is harder than it looks. 4-5 days. |
| Phase 6: Observability | 1-2 days | Reasonable. |

**Total claimed: 11-17 days**  
**My estimate: 18-25 days realistically**

---

## Recommendations

### Critical (Must Fix)

1. **Fix GPU detection or admit it's broken**
   - Apple Silicon: Either require sudo for powermetrics or document as "best effort"
   - Don't pretend process name matching is GPU monitoring

2. **Reduce stale threshold for power state**
   - 30 seconds max
   - Different factors can have different thresholds

3. **Add hysteresis to prevent oscillation**
   - Minimum cost difference to switch
   - Or sticky routing with timeout

4. **Handle unknown bandwidth**
   - Explicit default when no samples
   - Not just `None` falling through

5. **Validate psutil dependency exists**
   - Cross-reference with PACKAGING.md
   - Ensure it's actually in pyproject.toml

### High Priority

1. **Document container behavior**
   - Detect cgroup limits
   - Adjust CPU/memory reading accordingly

2. **Add cost normalization discussion**
   - Explain how multipliers were chosen
   - Plan for empirical tuning

3. **Implement thermal detection**
   - It's easy on both platforms
   - High value signal

### Nice to Have

1. **Trending / prediction**
   - Battery charging vs. draining
   - Load trending up/down

2. **Windows support**
   - If you want it, design it
   - If not, explicitly exclude

---

## Verdict

🟡 **NEEDS WORK**

The concept is excellent. The execution has gaps:
- GPU detection is fictional on Apple Silicon
- Stale thresholds are too long for power state
- No oscillation prevention
- Missing edge cases (containers, unknown bandwidth)
- Magic numbers without justification

**Blocker?** Yes - GPU detection for Apple Silicon will cause incorrect routing decisions. Either fix it or document the limitation clearly.

---

*This design is ambitious and mostly sound, but the devil is in the details. The issues above will cause real problems when heterogeneous nodes with different power states compete for work.*
