# Dynamic Cost Model Design

## Overview

The Atmosphere mesh routes work to the **best** node, not just any capable node. Cost-aware routing ensures:

1. **Efficiency**: Work goes where it's cheapest to execute
2. **Battery preservation**: Laptops on battery aren't drained by heavy workloads
3. **Load balancing**: Busy nodes shed work to idle ones
4. **Cost optimization**: Cloud API costs are tracked and factored into routing decisions
5. **Network awareness**: Metered/slow connections avoid large data transfers

Without cost awareness, a mesh with heterogeneous nodes (desktop, laptop, cloud VM) would route randomly, potentially draining laptop batteries while desktop power goes unused.

## Cost Factors

### Power State

The most impactful cost factor. A node on battery power is expensive—we want to preserve battery for the human's actual work.

#### Detection Methods

**macOS** - `pmset -g batt`:
```bash
$ pmset -g batt
Now drawing from 'Battery Power'
 -InternalBattery-0 (id=35324003)	74%; discharging; 2:30 remaining present: true
```

**macOS** - `ioreg` for precise values:
```bash
$ /usr/sbin/ioreg -l | grep -i "currentcapacity\|maxcapacity"
    "CurrentCapacity" = 74
    "MaxCapacity" = 100
    "AppleRawCurrentCapacity" = 5301
    "AppleRawMaxCapacity" = 7502
```

**Linux** - `/sys/class/power_supply/`:
```bash
$ cat /sys/class/power_supply/BAT0/status
Discharging

$ cat /sys/class/power_supply/BAT0/capacity
74

$ cat /sys/class/power_supply/AC/online
0
```

**Cross-platform Python** (psutil):
```python
import psutil

def get_power_state() -> dict:
    """Get battery/power state. Returns None values on desktop."""
    battery = psutil.sensors_battery()
    if battery is None:
        # Desktop - always plugged in
        return {
            "on_battery": False,
            "battery_percent": 100.0,
            "plugged_in": True,
            "secs_left": None
        }
    return {
        "on_battery": not battery.power_plugged,
        "battery_percent": battery.percent,
        "plugged_in": battery.power_plugged,
        "secs_left": battery.secsleft if battery.secsleft > 0 else None
    }
```

#### Cost Multipliers

| State | Multiplier | Rationale |
|-------|------------|-----------|
| Plugged in | 1.0x | Free power |
| On battery, >50% | 2.0x | Preserve battery |
| On battery, 20-50% | 3.0x | More urgency |
| On battery, <20% | 5.0x | Critical - avoid unless necessary |
| Low power mode active | +1.0x | User explicitly preserving battery |

```python
def power_cost_multiplier(power_state: dict) -> float:
    """Calculate cost multiplier from power state."""
    if not power_state["on_battery"]:
        return 1.0
    
    pct = power_state["battery_percent"]
    if pct < 20:
        return 5.0
    elif pct < 50:
        return 3.0
    else:
        return 2.0
```

---

### Compute Load

A busy node costs more—routing work there adds latency and degrades quality for all tasks.

#### Detection Methods

**macOS/Linux** - `top` (one-shot):
```bash
$ top -l 1 -n 0 | head -5
Processes: 1025 total, 8 running, 1017 sleeping, 7385 threads 
Load Avg: 5.63, 6.78, 10.41 
CPU usage: 38.71% user, 13.37% sys, 47.91% idle 
```

**Linux** - `/proc/stat`:
```bash
$ cat /proc/stat | head -1
cpu  123456 789 101112 131415 1617 1819 2021 0 0 0
```

**Cross-platform Python** (psutil):
```python
import psutil

def get_compute_load() -> dict:
    """Get CPU and memory load."""
    cpu_percent = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    
    # Load averages (1, 5, 15 min)
    try:
        load_avg = psutil.getloadavg()
        # Normalize by CPU count
        cpu_count = psutil.cpu_count()
        normalized_load = load_avg[0] / cpu_count if cpu_count else load_avg[0]
    except (AttributeError, OSError):
        # Windows doesn't have load average
        normalized_load = cpu_percent / 100.0
    
    return {
        "cpu_percent": cpu_percent,
        "cpu_load_normalized": min(normalized_load, 2.0),  # Cap at 2.0
        "memory_percent": mem.percent,
        "memory_available_gb": mem.available / (1024**3),
        "cpu_count": psutil.cpu_count()
    }
```

**macOS memory pressure** (more accurate than raw %):
```bash
$ /usr/bin/memory_pressure
System-wide memory free percentage: 88%
```

```python
import subprocess
import re

def get_macos_memory_pressure() -> float:
    """Get macOS system memory pressure (0.0-1.0, lower is better)."""
    try:
        result = subprocess.run(
            ["/usr/bin/memory_pressure"],
            capture_output=True, text=True, timeout=5
        )
        match = re.search(r"free percentage: (\d+)%", result.stdout)
        if match:
            free_pct = int(match.group(1))
            return 1.0 - (free_pct / 100.0)  # Convert to pressure
    except Exception:
        pass
    return 0.5  # Default to moderate pressure
```

#### GPU Load

**NVIDIA** (nvidia-smi):
```bash
$ nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits
45, 8192, 24576
```

```python
def get_nvidia_gpu_load() -> dict | None:
    """Get NVIDIA GPU utilization."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            return {
                "gpu_percent": float(parts[0].strip()),
                "gpu_memory_used_mb": float(parts[1].strip()),
                "gpu_memory_total_mb": float(parts[2].strip()),
                "gpu_memory_percent": float(parts[1]) / float(parts[2]) * 100
            }
    except Exception:
        pass
    return None
```

**macOS Apple Silicon** - GPU monitoring is severely limited without sudo:
```python
def get_apple_gpu_estimate() -> dict | None:
    """
    ⚠️ IMPORTANT: This is a HEURISTIC ESTIMATE, NOT actual GPU measurement.
    
    Apple Silicon does not expose GPU utilization metrics without:
    - `sudo powermetrics` (requires root access)
    - Private IOKit APIs (unstable, may break between macOS versions)
    
    This function provides a *best-effort estimate* based on:
    1. Presence of known GPU-heavy processes
    2. System power consumption as a proxy
    
    For accurate GPU cost attribution, consider:
    - Option A: Run `sudo powermetrics --samplers gpu_power -i 1000 -n 1` 
      periodically (requires elevated privileges)
    - Option B: Use power consumption as proxy (see below)
    - Option C: Exclude Apple GPU from cost calculations and document limitation
    
    DO NOT use this for billing or critical routing decisions.
    """
    # Check if GPU-heavy processes are running
    gpu_processes = ["ollama", "mlx", "stable-diffusion", "whisper.cpp"]
    
    try:
        result = subprocess.run(
            ["pgrep", "-l", "-f", "|".join(gpu_processes)],
            capture_output=True, text=True, timeout=5
        )
        active_gpu_processes = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
        
        # VERY rough estimate: this is NOT accurate
        # A process being present doesn't mean it's using the GPU
        estimated_load = min(active_gpu_processes * 25.0, 100.0)
        
        return {
            "gpu_percent": estimated_load,
            "gpu_memory_percent": None,  # Cannot detect on Apple Silicon
            "estimated": True,  # ALWAYS True - this is never a real measurement
            "accuracy": "low",  # Be explicit about accuracy
            "method": "process_heuristic"
        }
    except Exception:
        pass
    return None


def get_apple_power_proxy() -> dict | None:
    """
    Alternative: Use power consumption as a GPU activity proxy.
    
    Higher power draw often correlates with GPU usage, though this
    cannot distinguish CPU vs GPU power consumption without sudo.
    
    Available without elevated permissions.
    """
    try:
        # Get battery discharge rate (if on battery)
        result = subprocess.run(
            ["pmset", "-g", "batt"],
            capture_output=True, text=True, timeout=5
        )
        
        # Get instantaneous power draw (if available)
        power_result = subprocess.run(
            ["ioreg", "-r", "-d", "1", "-w", "0", "-c", "AppleSmartBattery"],
            capture_output=True, text=True, timeout=5
        )
        
        power_info = {}
        for line in power_result.stdout.split("\n"):
            if "InstantAmperage" in line:
                match = re.search(r'"InstantAmperage"\s*=\s*(\d+)', line)
                if match:
                    power_info["amperage_ma"] = int(match.group(1))
            if "Voltage" in line and "voltage" not in power_info:
                match = re.search(r'"Voltage"\s*=\s*(\d+)', line)
                if match:
                    power_info["voltage_mv"] = int(match.group(1))
        
        if "amperage_ma" in power_info and "voltage_mv" in power_info:
            # Calculate approximate wattage
            watts = (power_info["amperage_ma"] * power_info["voltage_mv"]) / 1_000_000
            power_info["estimated_watts"] = watts
            # Rough categorization: >15W suggests significant GPU activity on M-series
            power_info["likely_gpu_active"] = watts > 15.0
        
        return power_info
    except Exception:
        pass
    return None
```

> **⚠️ Known Limitation:** Apple Silicon GPU utilization cannot be accurately measured 
> without `sudo powermetrics`. The above heuristics are best-effort approximations.
> For production deployments, consider:
> 1. Running a privileged daemon that periodically samples `powermetrics`
> 2. Using power consumption as a proxy for overall system load
> 3. Accepting that Apple GPU cost attribution will be imprecise

#### Cost Multipliers

| Load | Multiplier | Work Type |
|------|------------|-----------|
| CPU < 25% | 1.0x | All |
| CPU 25-50% | 1.3x | All |
| CPU 50-75% | 1.6x | All |
| CPU > 75% | 2.0x | All |
| GPU < 25% | 1.0x | Inference |
| GPU 25-50% | 1.5x | Inference |
| GPU > 50% | 2.0x | Inference |
| Memory > 80% | 1.5x | All |
| Memory > 90% | 2.5x | All |

```python
def compute_load_multiplier(load: dict, work_type: str = "general") -> float:
    """Calculate cost multiplier from compute load."""
    multiplier = 1.0
    
    # CPU load
    cpu = load.get("cpu_load_normalized", 0.5)
    if cpu > 0.75:
        multiplier *= 2.0
    elif cpu > 0.50:
        multiplier *= 1.6
    elif cpu > 0.25:
        multiplier *= 1.3
    
    # Memory pressure
    mem = load.get("memory_percent", 50)
    if mem > 90:
        multiplier *= 2.5
    elif mem > 80:
        multiplier *= 1.5
    
    # GPU (only for inference work)
    if work_type in ("inference", "embedding", "generation"):
        gpu = load.get("gpu_percent", 0)
        if gpu > 50:
            multiplier *= 2.0
        elif gpu > 25:
            multiplier *= 1.5
    
    return multiplier
```

---

### Network

Network cost matters for data-heavy work (large context, file transfers, RAG with big documents).

#### Detection Methods

**Bandwidth estimation** - Use recent transfer history:
```python
import time

class BandwidthEstimator:
    """Estimate available bandwidth from transfer history."""
    
    def __init__(self, window_seconds: float = 60.0):
        self.window = window_seconds
        self.samples: list[tuple[float, int, float]] = []  # (timestamp, bytes, duration)
    
    def record_transfer(self, bytes_transferred: int, duration_seconds: float):
        """Record a completed transfer."""
        now = time.time()
        self.samples.append((now, bytes_transferred, duration_seconds))
        # Prune old samples
        self.samples = [(t, b, d) for t, b, d in self.samples 
                        if now - t < self.window]
    
    def estimate_mbps(self) -> float | None:
        """Estimate bandwidth in Mbps."""
        if not self.samples:
            return None
        
        total_bytes = sum(b for _, b, _ in self.samples)
        total_duration = sum(d for _, _, d in self.samples)
        
        if total_duration < 0.1:
            return None
        
        bytes_per_sec = total_bytes / total_duration
        return bytes_per_sec * 8 / 1_000_000  # Convert to Mbps
```

**macOS network interface stats**:
```bash
$ /usr/sbin/netstat -ib | grep -E "^en0|^en1"
en0    1500  <Link#4>    bc:d0:74:05:db:ca  1234567  0  5678901234  987654  0  1234567890  0
```

```python
def get_network_interface_stats() -> dict:
    """Get network interface statistics (macOS/Linux)."""
    try:
        import psutil
        counters = psutil.net_io_counters(pernic=True)
        
        # Prefer active interfaces (most traffic)
        best_iface = max(counters.items(), 
                         key=lambda x: x[1].bytes_sent + x[1].bytes_recv)
        iface_name, stats = best_iface
        
        return {
            "interface": iface_name,
            "bytes_sent": stats.bytes_sent,
            "bytes_recv": stats.bytes_recv,
            "packets_sent": stats.packets_sent,
            "packets_recv": stats.packets_recv
        }
    except Exception:
        return {}
```

**Metered connection detection**:

macOS - Check for known mobile hotspot patterns:
```python
import subprocess
import re

def is_metered_macos() -> bool:
    """
    Detect if on a metered connection (macOS).
    Checks for iPhone hotspot, low-bandwidth connections.
    """
    try:
        # Check for iPhone USB/WiFi tethering
        result = subprocess.run(
            ["/usr/sbin/networksetup", "-listallhardwareports"],
            capture_output=True, text=True, timeout=5
        )
        if "iPhone" in result.stdout:
            return True
        
        # Check WiFi SSID for hotspot patterns
        result = subprocess.run(
            ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
            capture_output=True, text=True, timeout=5
        )
        ssid_match = re.search(r"SSID: (.+)", result.stdout)
        if ssid_match:
            ssid = ssid_match.group(1).strip()
            # Common hotspot patterns
            hotspot_patterns = ["iphone", "android", "hotspot", "mobile", "tether"]
            if any(p in ssid.lower() for p in hotspot_patterns):
                return True
    except Exception:
        pass
    return False
```

Linux - NetworkManager D-Bus:
```python
def is_metered_linux() -> bool:
    """
    Detect if on a metered connection (Linux).
    Uses NetworkManager D-Bus API.
    """
    try:
        import dbus
        bus = dbus.SystemBus()
        nm = bus.get_object("org.freedesktop.NetworkManager",
                           "/org/freedesktop/NetworkManager")
        props = dbus.Interface(nm, "org.freedesktop.DBus.Properties")
        
        # NM_METERED_YES = 1, NM_METERED_GUESS_YES = 3
        metered = props.Get("org.freedesktop.NetworkManager", "Metered")
        return metered in (1, 3)
    except Exception:
        pass
    return False
```

#### Cost Multipliers

| Condition | Multiplier | Rationale |
|-----------|------------|-----------|
| High bandwidth (>100 Mbps) | 1.0x | Fast |
| Medium bandwidth (10-100 Mbps) | 1.2x | Acceptable |
| Low bandwidth (<10 Mbps) | 2.0x | Slow |
| Very low bandwidth (<1 Mbps) | 5.0x | Avoid data-heavy work |
| Metered connection | 3.0x | $$ per byte |
| Unknown/offline | 10.0x | Can't reach |

```python
def network_cost_multiplier(
    bandwidth_mbps: float | None,
    is_metered: bool,
    work_type: str = "general"
) -> float:
    """Calculate cost multiplier from network conditions."""
    multiplier = 1.0
    
    # Metered connection is expensive
    if is_metered:
        multiplier *= 3.0
    
    # Bandwidth impact (mainly for data-heavy work)
    if bandwidth_mbps is not None:
        if bandwidth_mbps < 1:
            multiplier *= 5.0
        elif bandwidth_mbps < 10:
            multiplier *= 2.0
        elif bandwidth_mbps < 100:
            multiplier *= 1.2
    
    # Data-heavy work types are more sensitive
    if work_type in ("rag", "file_transfer", "embedding_large"):
        multiplier = multiplier ** 1.5  # Amplify network cost
    
    return multiplier
```

---

### Cloud API Costs

When routing to cloud APIs (OpenAI, Anthropic, etc.), include actual dollar cost.

#### Cost Table (as of 2024)

| Provider | Model | Input ($/1M tok) | Output ($/1M tok) |
|----------|-------|------------------|-------------------|
| OpenAI | gpt-4o | $2.50 | $10.00 |
| OpenAI | gpt-4o-mini | $0.15 | $0.60 |
| OpenAI | gpt-4-turbo | $10.00 | $30.00 |
| Anthropic | claude-3-5-sonnet | $3.00 | $15.00 |
| Anthropic | claude-3-haiku | $0.25 | $1.25 |
| Anthropic | claude-3-opus | $15.00 | $75.00 |
| Google | gemini-1.5-pro | $1.25 | $5.00 |
| Google | gemini-1.5-flash | $0.075 | $0.30 |

```python
from dataclasses import dataclass
from typing import Dict

@dataclass
class APIModelCost:
    input_per_million: float  # $ per 1M input tokens
    output_per_million: float  # $ per 1M output tokens

API_COSTS: Dict[str, APIModelCost] = {
    # OpenAI
    "gpt-4o": APIModelCost(2.50, 10.00),
    "gpt-4o-mini": APIModelCost(0.15, 0.60),
    "gpt-4-turbo": APIModelCost(10.00, 30.00),
    "gpt-3.5-turbo": APIModelCost(0.50, 1.50),
    
    # Anthropic
    "claude-3-5-sonnet": APIModelCost(3.00, 15.00),
    "claude-3-5-sonnet-20241022": APIModelCost(3.00, 15.00),
    "claude-3-haiku": APIModelCost(0.25, 1.25),
    "claude-3-opus": APIModelCost(15.00, 75.00),
    
    # Google
    "gemini-1.5-pro": APIModelCost(1.25, 5.00),
    "gemini-1.5-flash": APIModelCost(0.075, 0.30),
    
    # Local (free)
    "llama-*": APIModelCost(0.0, 0.0),
    "mistral-*": APIModelCost(0.0, 0.0),
}

def estimate_api_cost(
    model: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int
) -> float:
    """Estimate API cost for a request."""
    # Check exact match first, then wildcards
    cost = API_COSTS.get(model)
    if cost is None:
        for pattern, c in API_COSTS.items():
            if pattern.endswith("*") and model.startswith(pattern[:-1]):
                cost = c
                break
    
    if cost is None:
        return 0.0  # Unknown model, assume free/local
    
    input_cost = (estimated_input_tokens / 1_000_000) * cost.input_per_million
    output_cost = (estimated_output_tokens / 1_000_000) * cost.output_per_million
    
    return input_cost + output_cost
```

#### Incorporating API Cost into Routing

```python
def api_cost_penalty(
    estimated_cost_usd: float,
    budget_sensitivity: float = 1.0
) -> float:
    """
    Convert API cost to routing cost multiplier.
    
    budget_sensitivity: 1.0 = normal, >1 = cost-conscious, <1 = quality-focused
    """
    # Scale: $0.01 = 1.0 added cost, $0.10 = 10.0 added cost
    # This makes API cost comparable to other factors
    return 1.0 + (estimated_cost_usd * 100 * budget_sensitivity)
```

---

## Cost Calculation

The complete cost calculation combines all factors:

```python
from dataclasses import dataclass
from typing import Optional
import time

@dataclass
class NodeCostFactors:
    """All cost factors for a node."""
    node_id: str
    timestamp: float
    
    # Power
    on_battery: bool = False
    battery_percent: float = 100.0
    
    # Compute
    cpu_load: float = 0.0  # 0-1 normalized
    gpu_load: float = 0.0  # 0-100%
    memory_percent: float = 0.0
    
    # Network
    bandwidth_mbps: Optional[float] = None
    is_metered: bool = False
    latency_ms: Optional[float] = None
    
    # API costs (if this node proxies to cloud APIs)
    api_model: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "on_battery": self.on_battery,
            "battery_percent": self.battery_percent,
            "cpu_load": self.cpu_load,
            "gpu_load": self.gpu_load,
            "memory_percent": self.memory_percent,
            "bandwidth_mbps": self.bandwidth_mbps,
            "is_metered": self.is_metered,
            "latency_ms": self.latency_ms,
            "api_model": self.api_model
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "NodeCostFactors":
        return cls(**data)


@dataclass
class WorkRequest:
    """Description of work to be routed."""
    work_type: str  # "inference", "embedding", "rag", "general"
    estimated_input_tokens: int = 1000
    estimated_output_tokens: int = 500
    data_size_bytes: int = 0
    requires_gpu: bool = False
    model_preference: Optional[str] = None


def compute_node_cost(
    node: NodeCostFactors,
    work: WorkRequest,
    budget_sensitivity: float = 1.0
) -> float:
    """
    Compute total cost score for routing work to a node.
    
    Lower cost = better choice.
    
    Args:
        node: Current cost factors for the node
        work: Description of the work to route
        budget_sensitivity: 1.0 = balanced, >1 = cost-conscious, <1 = quality-focused
    
    Returns:
        Cost score (1.0 = baseline, higher = more expensive)
    """
    cost = 1.0
    
    # === Power State ===
    if node.on_battery:
        cost *= 2.0
        if node.battery_percent < 20:
            cost *= 2.5
        elif node.battery_percent < 50:
            cost *= 1.5
    
    # === Compute Load ===
    # CPU impact
    if node.cpu_load > 0.75:
        cost *= 2.0
    elif node.cpu_load > 0.50:
        cost *= 1.6
    elif node.cpu_load > 0.25:
        cost *= 1.3
    
    # GPU impact (for inference work)
    if work.work_type in ("inference", "embedding", "generation") or work.requires_gpu:
        if node.gpu_load > 50:
            cost *= 2.0
        elif node.gpu_load > 25:
            cost *= 1.5
    
    # Memory pressure
    if node.memory_percent > 90:
        cost *= 2.5
    elif node.memory_percent > 80:
        cost *= 1.5
    
    # === Network ===
    if node.is_metered:
        cost *= 3.0
    
    if node.bandwidth_mbps is not None:
        if node.bandwidth_mbps < 1:
            cost *= 5.0
        elif node.bandwidth_mbps < 10:
            cost *= 2.0
        elif node.bandwidth_mbps < 100:
            cost *= 1.2
    
    # Data-heavy work is more sensitive to network
    if work.work_type in ("rag", "file_transfer") or work.data_size_bytes > 1_000_000:
        # Amplify network-related costs
        if node.is_metered or (node.bandwidth_mbps and node.bandwidth_mbps < 10):
            cost *= 1.5
    
    # Latency penalty
    if node.latency_ms is not None and node.latency_ms > 100:
        cost *= 1.0 + (node.latency_ms - 100) / 500  # +1.0 per 500ms over 100ms
    
    # === Cloud API Cost ===
    if node.api_model:
        estimated_usd = estimate_api_cost(
            node.api_model,
            work.estimated_input_tokens,
            work.estimated_output_tokens
        )
        cost += estimated_usd * 100 * budget_sensitivity
    
    return cost


def select_best_node(
    nodes: list[NodeCostFactors],
    work: WorkRequest,
    budget_sensitivity: float = 1.0,
    capability_filter: Optional[list[str]] = None
) -> tuple[NodeCostFactors, float]:
    """
    Select the best node for a work request.
    
    Returns:
        Tuple of (best_node, cost_score)
    """
    if not nodes:
        raise ValueError("No nodes available")
    
    # Filter by capabilities if specified
    candidates = nodes
    if capability_filter:
        # This would integrate with the router's capability tracking
        pass
    
    # Score all candidates
    scored = [(node, compute_node_cost(node, work, budget_sensitivity)) 
              for node in candidates]
    
    # Sort by cost (ascending)
    scored.sort(key=lambda x: x[1])
    
    return scored[0]
```

---

## Gossip Integration

Cost factors must propagate through the mesh via gossip for distributed routing decisions.

### NODE_COST_UPDATE Message

```yaml
type: NODE_COST_UPDATE
version: 1
node_id: "robs-macbook"
timestamp: 1706900000.123
ttl: 60  # Seconds until stale

cost_factors:
  # Power
  on_battery: true
  battery_percent: 74.0
  
  # Compute
  cpu_load: 0.38  # Normalized 0-1
  gpu_load: 15.0  # Percent
  memory_percent: 88.0
  
  # Network
  bandwidth_mbps: 250.0
  is_metered: false
  
  # Derived
  overall_cost: 2.4  # Pre-computed for quick filtering

signature: "..."  # Optional: signed for authenticity
```

### Integration with Existing Gossip

```python
from dataclasses import dataclass, field
from typing import Dict, Optional
import time

@dataclass
class CostGossipState:
    """Track cost factors from gossip updates."""
    
    # node_id -> (NodeCostFactors, receive_timestamp)
    node_costs: Dict[str, tuple[NodeCostFactors, float]] = field(default_factory=dict)
    
    # How old before we consider cost data stale
    stale_threshold_seconds: float = 120.0
    
    def handle_cost_update(self, message: dict) -> None:
        """Process a NODE_COST_UPDATE gossip message."""
        node_id = message.get("node_id")
        if not node_id:
            return
        
        factors = NodeCostFactors(
            node_id=node_id,
            timestamp=message.get("timestamp", time.time()),
            on_battery=message["cost_factors"].get("on_battery", False),
            battery_percent=message["cost_factors"].get("battery_percent", 100.0),
            cpu_load=message["cost_factors"].get("cpu_load", 0.0),
            gpu_load=message["cost_factors"].get("gpu_load", 0.0),
            memory_percent=message["cost_factors"].get("memory_percent", 0.0),
            bandwidth_mbps=message["cost_factors"].get("bandwidth_mbps"),
            is_metered=message["cost_factors"].get("is_metered", False),
            latency_ms=message["cost_factors"].get("latency_ms")
        )
        
        self.node_costs[node_id] = (factors, time.time())
    
    def get_node_cost(self, node_id: str) -> Optional[NodeCostFactors]:
        """Get cost factors for a node, if fresh enough."""
        if node_id not in self.node_costs:
            return None
        
        factors, received_at = self.node_costs[node_id]
        age = time.time() - received_at
        
        if age > self.stale_threshold_seconds:
            return None  # Too stale
        
        return factors
    
    def get_all_fresh_costs(self) -> list[NodeCostFactors]:
        """Get all non-stale cost factors."""
        now = time.time()
        return [
            factors for factors, received_at in self.node_costs.values()
            if now - received_at < self.stale_threshold_seconds
        ]
    
    def build_cost_update(self, local_factors: NodeCostFactors) -> dict:
        """Build a gossip message for our own cost factors."""
        return {
            "type": "NODE_COST_UPDATE",
            "version": 1,
            "node_id": local_factors.node_id,
            "timestamp": time.time(),
            "ttl": 60,
            "cost_factors": {
                "on_battery": local_factors.on_battery,
                "battery_percent": local_factors.battery_percent,
                "cpu_load": local_factors.cpu_load,
                "gpu_load": local_factors.gpu_load,
                "memory_percent": local_factors.memory_percent,
                "bandwidth_mbps": local_factors.bandwidth_mbps,
                "is_metered": local_factors.is_metered,
                "overall_cost": compute_node_cost(local_factors, WorkRequest("general"))
            }
        }
```

### Broadcast Frequency

- **Full update**: Every 30 seconds, or when significant change detected
- **Significant change thresholds**:
  - Battery: plugged in ↔ unplugged, or >10% change
  - CPU: >20% change in normalized load
  - Network: metered ↔ unmetered, or bandwidth category change
  
```python
class CostBroadcaster:
    """Manage periodic cost factor broadcasts."""
    
    def __init__(self, gossip_client, node_id: str):
        self.gossip = gossip_client
        self.node_id = node_id
        self.last_broadcast: Optional[NodeCostFactors] = None
        self.last_broadcast_time: float = 0
        
        # Thresholds for "significant change"
        self.battery_threshold = 10.0  # percent
        self.cpu_threshold = 0.20  # normalized
        self.interval_seconds = 30.0
    
    def should_broadcast(self, current: NodeCostFactors) -> bool:
        """Check if we should broadcast an update."""
        now = time.time()
        
        # Always broadcast on interval
        if now - self.last_broadcast_time > self.interval_seconds:
            return True
        
        # Check for significant changes
        if self.last_broadcast is None:
            return True
        
        last = self.last_broadcast
        
        # Power state change
        if current.on_battery != last.on_battery:
            return True
        if abs(current.battery_percent - last.battery_percent) > self.battery_threshold:
            return True
        
        # CPU load change
        if abs(current.cpu_load - last.cpu_load) > self.cpu_threshold:
            return True
        
        # Network state change
        if current.is_metered != last.is_metered:
            return True
        
        return False
    
    async def maybe_broadcast(self, current: NodeCostFactors) -> bool:
        """Broadcast if needed. Returns True if broadcast sent."""
        if not self.should_broadcast(current):
            return False
        
        message = CostGossipState().build_cost_update(current)
        await self.gossip.broadcast(message)
        
        self.last_broadcast = current
        self.last_broadcast_time = time.time()
        return True
```

---

## Routing Integration

The router uses cost in its selection process:

```python
class CostAwareRouter:
    """
    Router that considers node cost in selection.
    
    Integrates with FastProjectRouter for capability matching,
    then applies cost-based selection among capable nodes.
    """
    
    def __init__(
        self,
        project_router: "FastProjectRouter",
        cost_state: CostGossipState,
        local_node_id: str
    ):
        self.project_router = project_router
        self.cost_state = cost_state
        self.local_node_id = local_node_id
    
    def route(
        self,
        model: str,
        messages: list[dict],
        work_type: str = "inference",
        budget_sensitivity: float = 1.0
    ) -> "RouteResult":
        """
        Route a request considering both capability and cost.
        """
        # Step 1: Get capability-matched project
        route_result = self.project_router.route(model, messages)
        
        if not route_result.success:
            return route_result
        
        project = route_result.project
        
        # Step 2: Get nodes that have this project
        candidate_nodes = project.nodes
        
        if len(candidate_nodes) <= 1:
            # Only one node has this project, no cost choice
            return route_result
        
        # Step 3: Get cost factors for each candidate
        work = WorkRequest(
            work_type=work_type,
            estimated_input_tokens=self._estimate_tokens(messages),
            requires_gpu=work_type in ("inference", "embedding")
        )
        
        node_costs = []
        for node_id in candidate_nodes:
            cost_factors = self.cost_state.get_node_cost(node_id)
            
            if cost_factors is None:
                # No cost data - use default moderate cost
                cost_factors = NodeCostFactors(
                    node_id=node_id,
                    timestamp=time.time(),
                    cpu_load=0.5  # Assume moderate load
                )
            
            cost_score = compute_node_cost(cost_factors, work, budget_sensitivity)
            node_costs.append((node_id, cost_score))
        
        # Step 4: Select lowest cost node
        node_costs.sort(key=lambda x: x[1])
        best_node_id, best_cost = node_costs[0]
        
        # Step 5: Update route result with selected node
        route_result.selected_node = best_node_id
        route_result.cost_score = best_cost
        route_result.reason += f" (node: {best_node_id}, cost: {best_cost:.2f})"
        
        return route_result
    
    def _estimate_tokens(self, messages: list[dict]) -> int:
        """Rough token estimate from messages."""
        text = " ".join(m.get("content", "") for m in messages if isinstance(m.get("content"), str))
        return len(text) // 4  # Rough approximation
```

---

## Platform-Specific Detection

### Complete macOS Implementation

```python
import subprocess
import re
import os
from typing import Optional
import time

class MacOSCostCollector:
    """Collect cost factors on macOS."""
    
    def __init__(self, node_id: Optional[str] = None):
        self.node_id = node_id or os.uname().nodename
    
    def collect(self) -> NodeCostFactors:
        """Collect all cost factors."""
        return NodeCostFactors(
            node_id=self.node_id,
            timestamp=time.time(),
            **self._get_power_state(),
            **self._get_compute_load(),
            **self._get_network_state()
        )
    
    def _get_power_state(self) -> dict:
        """Get battery/power state."""
        try:
            result = subprocess.run(
                ["pmset", "-g", "batt"],
                capture_output=True, text=True, timeout=5
            )
            output = result.stdout
            
            on_battery = "Battery Power" in output
            
            # Parse percentage
            pct_match = re.search(r"(\d+)%", output)
            battery_percent = float(pct_match.group(1)) if pct_match else 100.0
            
            return {
                "on_battery": on_battery,
                "battery_percent": battery_percent
            }
        except Exception:
            return {"on_battery": False, "battery_percent": 100.0}
    
    def _get_compute_load(self) -> dict:
        """Get CPU, GPU, memory load."""
        result = {
            "cpu_load": 0.5,
            "gpu_load": 0.0,
            "memory_percent": 50.0
        }
        
        # CPU from top
        try:
            top_result = subprocess.run(
                ["top", "-l", "1", "-n", "0"],
                capture_output=True, text=True, timeout=10
            )
            
            # Parse CPU usage
            cpu_match = re.search(r"CPU usage: ([\d.]+)% user, ([\d.]+)% sys", top_result.stdout)
            if cpu_match:
                user = float(cpu_match.group(1))
                sys = float(cpu_match.group(2))
                result["cpu_load"] = (user + sys) / 100.0
            
            # Parse load average
            load_match = re.search(r"Load Avg: ([\d.]+)", top_result.stdout)
            if load_match:
                load_avg = float(load_match.group(1))
                cpu_count = os.cpu_count() or 1
                result["cpu_load"] = min(load_avg / cpu_count, 2.0)
        except Exception:
            pass
        
        # Memory from memory_pressure
        try:
            mem_result = subprocess.run(
                ["/usr/bin/memory_pressure"],
                capture_output=True, text=True, timeout=5
            )
            free_match = re.search(r"free percentage: (\d+)%", mem_result.stdout)
            if free_match:
                free_pct = int(free_match.group(1))
                result["memory_percent"] = 100.0 - free_pct
        except Exception:
            pass
        
        # GPU (estimate from processes)
        try:
            gpu_processes = ["ollama", "mlx", "stable-diffusion", "whisper"]
            ps_result = subprocess.run(
                ["pgrep", "-l", "-f", "|".join(gpu_processes)],
                capture_output=True, text=True, timeout=5
            )
            if ps_result.stdout.strip():
                active = len(ps_result.stdout.strip().split("\n"))
                result["gpu_load"] = min(active * 30.0, 100.0)
        except Exception:
            pass
        
        return result
    
    def _get_network_state(self) -> dict:
        """Get network bandwidth and metered status."""
        result = {
            "bandwidth_mbps": None,
            "is_metered": False
        }
        
        # Check for iPhone tethering
        try:
            iface_result = subprocess.run(
                ["/usr/sbin/networksetup", "-listallhardwareports"],
                capture_output=True, text=True, timeout=5
            )
            if "iPhone" in iface_result.stdout:
                result["is_metered"] = True
        except Exception:
            pass
        
        # Note: Bandwidth would be tracked via transfer history,
        # not directly detectable
        
        return result
```

### Complete Linux Implementation

```python
import subprocess
import os
import re
from pathlib import Path
from typing import Optional
import time

class LinuxCostCollector:
    """Collect cost factors on Linux."""
    
    def __init__(self, node_id: Optional[str] = None):
        self.node_id = node_id or os.uname().nodename
    
    def collect(self) -> NodeCostFactors:
        """Collect all cost factors."""
        return NodeCostFactors(
            node_id=self.node_id,
            timestamp=time.time(),
            **self._get_power_state(),
            **self._get_compute_load(),
            **self._get_network_state()
        )
    
    def _get_power_state(self) -> dict:
        """Get battery/power state from /sys."""
        power_supply = Path("/sys/class/power_supply")
        
        if not power_supply.exists():
            # Desktop without battery
            return {"on_battery": False, "battery_percent": 100.0}
        
        # Find battery
        battery_path = None
        for p in power_supply.iterdir():
            if p.name.startswith("BAT"):
                battery_path = p
                break
        
        if battery_path is None:
            return {"on_battery": False, "battery_percent": 100.0}
        
        # Read status
        try:
            status = (battery_path / "status").read_text().strip()
            on_battery = status == "Discharging"
            
            capacity = int((battery_path / "capacity").read_text().strip())
            
            return {
                "on_battery": on_battery,
                "battery_percent": float(capacity)
            }
        except Exception:
            return {"on_battery": False, "battery_percent": 100.0}
    
    def _get_compute_load(self) -> dict:
        """Get CPU, GPU, memory load."""
        result = {
            "cpu_load": 0.5,
            "gpu_load": 0.0,
            "memory_percent": 50.0
        }
        
        # CPU from load average
        try:
            with open("/proc/loadavg") as f:
                parts = f.read().split()
                load_1min = float(parts[0])
                cpu_count = os.cpu_count() or 1
                result["cpu_load"] = min(load_1min / cpu_count, 2.0)
        except Exception:
            pass
        
        # Memory from /proc/meminfo
        try:
            meminfo = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = int(parts[1].strip().split()[0])
                        meminfo[key] = value
            
            total = meminfo.get("MemTotal", 1)
            available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            result["memory_percent"] = 100.0 * (1 - available / total)
        except Exception:
            pass
        
        # GPU from nvidia-smi
        try:
            nvidia_result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if nvidia_result.returncode == 0:
                result["gpu_load"] = float(nvidia_result.stdout.strip())
        except Exception:
            pass
        
        return result
    
    def _get_network_state(self) -> dict:
        """Get network state via NetworkManager D-Bus."""
        result = {
            "bandwidth_mbps": None,
            "is_metered": False
        }
        
        try:
            import dbus
            bus = dbus.SystemBus()
            nm = bus.get_object(
                "org.freedesktop.NetworkManager",
                "/org/freedesktop/NetworkManager"
            )
            props = dbus.Interface(nm, "org.freedesktop.DBus.Properties")
            
            metered = props.Get("org.freedesktop.NetworkManager", "Metered")
            # NM_METERED_YES = 1, NM_METERED_GUESS_YES = 3
            result["is_metered"] = metered in (1, 3)
        except Exception:
            pass
        
        return result
```

### Cross-Platform Factory

```python
import platform

def get_cost_collector(node_id: Optional[str] = None) -> "BaseCostCollector":
    """Get the appropriate cost collector for the current platform."""
    system = platform.system()
    
    if system == "Darwin":
        return MacOSCostCollector(node_id)
    elif system == "Linux":
        return LinuxCostCollector(node_id)
    else:
        # Windows or unknown - return stub
        return StubCostCollector(node_id)


class StubCostCollector:
    """Stub collector for unsupported platforms."""
    
    def __init__(self, node_id: Optional[str] = None):
        self.node_id = node_id or os.uname().nodename
    
    def collect(self) -> NodeCostFactors:
        return NodeCostFactors(
            node_id=self.node_id,
            timestamp=time.time()
        )
```

---

## Implementation Plan

### Phase 1: Local Collection (2-3 days)
- [ ] Implement `MacOSCostCollector` with battery, CPU, memory
- [ ] Implement `LinuxCostCollector` with battery, CPU, memory, nvidia-smi
- [ ] Add GPU estimation for Apple Silicon
- [ ] Unit tests for all collectors
- [ ] CLI tool to display current cost factors

### Phase 2: Gossip Integration (2-3 days)
- [ ] Define `NODE_COST_UPDATE` message type
- [ ] Implement `CostGossipState` for tracking remote costs
- [ ] Implement `CostBroadcaster` for periodic updates
- [ ] Add significant-change detection for immediate broadcasts
- [ ] Integration tests with mock gossip

### Phase 3: Router Integration (3-4 days)
- [ ] Modify `FastProjectRouter` to accept cost state
- [ ] Implement `CostAwareRouter` wrapper
- [ ] Add cost scoring to route selection
- [ ] Add budget sensitivity configuration
- [ ] Integration tests with multi-node scenarios

### Phase 4: API Costs (1-2 days)
- [ ] Build API cost table
- [ ] Track cloud API usage per request
- [ ] Include API cost in routing decisions
- [ ] Add cost reporting/logging

### Phase 5: Network Awareness (2-3 days)
- [ ] Implement metered connection detection (macOS, Linux)
- [ ] Add bandwidth tracking from transfer history
- [ ] Integrate latency measurement
- [ ] Adjust routing for data-heavy work types

### Phase 6: Observability (1-2 days)
- [ ] Cost factor dashboard/API endpoint
- [ ] Routing decision logging with cost breakdown
- [ ] Alerts for sustained high-cost routing
- [ ] Cost trend tracking

**Total Estimate: 11-17 days**

---

## Open Questions

1. **Cache invalidation**: How quickly should stale cost data be discarded?
   - Current: 120 seconds
   - Trade-off: Fresher data vs. fewer broadcasts

2. **Budget sensitivity**: Should this be per-user or system-wide?
   - Per-user allows "premium" vs. "economy" tiers
   - System-wide is simpler

3. **GPU memory**: Should we track GPU memory separately from utilization?
   - Some workloads fit in memory but still contend for compute

4. **Thermal throttling**: Should we detect and penalize thermally-throttled nodes?
   - macOS: `pmset -g therm`
   - Linux: `/sys/class/thermal/`

5. **Historical smoothing**: Should we smooth cost factors over time?
   - Prevents routing oscillation from brief load spikes
   - Adds latency to cost changes
