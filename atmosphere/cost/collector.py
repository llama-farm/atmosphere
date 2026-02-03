"""
Cost Factor Collection - Platform-specific system metric collection.

Collects power state, CPU load, GPU load (heuristic on Apple Silicon),
memory usage, and network state for cost-based routing decisions.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import psutil


@dataclass
class NodeCostFactors:
    """All cost factors for a node at a point in time."""
    
    node_id: str
    timestamp: float
    
    # Power state
    on_battery: bool = False
    battery_percent: float = 100.0
    plugged_in: bool = True
    
    # Compute load
    cpu_load: float = 0.0  # Normalized 0-1 (can exceed 1.0 for overload)
    gpu_load: float = 0.0  # 0-100%, heuristic on Apple Silicon
    gpu_estimated: bool = False  # True if GPU load is a heuristic, not measured
    memory_percent: float = 0.0  # 0-100%
    memory_available_gb: float = 0.0
    
    # Network
    bandwidth_mbps: Optional[float] = None
    is_metered: bool = False
    latency_ms: Optional[float] = None
    
    # API (if proxying to cloud)
    api_model: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for gossip/JSON."""
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "on_battery": self.on_battery,
            "battery_percent": self.battery_percent,
            "plugged_in": self.plugged_in,
            "cpu_load": self.cpu_load,
            "gpu_load": self.gpu_load,
            "gpu_estimated": self.gpu_estimated,
            "memory_percent": self.memory_percent,
            "memory_available_gb": self.memory_available_gb,
            "bandwidth_mbps": self.bandwidth_mbps,
            "is_metered": self.is_metered,
            "latency_ms": self.latency_ms,
            "api_model": self.api_model,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> NodeCostFactors:
        """Deserialize from dictionary."""
        return cls(
            node_id=data["node_id"],
            timestamp=data.get("timestamp", time.time()),
            on_battery=data.get("on_battery", False),
            battery_percent=data.get("battery_percent", 100.0),
            plugged_in=data.get("plugged_in", True),
            cpu_load=data.get("cpu_load", 0.0),
            gpu_load=data.get("gpu_load", 0.0),
            gpu_estimated=data.get("gpu_estimated", False),
            memory_percent=data.get("memory_percent", 0.0),
            memory_available_gb=data.get("memory_available_gb", 0.0),
            bandwidth_mbps=data.get("bandwidth_mbps"),
            is_metered=data.get("is_metered", False),
            latency_ms=data.get("latency_ms"),
            api_model=data.get("api_model"),
        )
    
    def __repr__(self) -> str:
        parts = [f"NodeCostFactors(node_id={self.node_id!r}"]
        if self.on_battery:
            parts.append(f"on_battery=True, battery={self.battery_percent:.0f}%")
        else:
            parts.append("plugged_in=True")
        parts.append(f"cpu={self.cpu_load:.1%}")
        if self.gpu_load > 0:
            est = " (est)" if self.gpu_estimated else ""
            parts.append(f"gpu={self.gpu_load:.0f}%{est}")
        parts.append(f"mem={self.memory_percent:.0f}%")
        if self.is_metered:
            parts.append("metered=True")
        return ", ".join(parts) + ")"


class CostCollector(ABC):
    """Abstract base class for platform-specific cost collection."""
    
    def __init__(self, node_id: Optional[str] = None):
        """
        Initialize collector.
        
        Args:
            node_id: Unique identifier for this node. Defaults to hostname.
        """
        self.node_id = node_id or platform.node()
    
    @abstractmethod
    def collect(self) -> NodeCostFactors:
        """Collect all cost factors for this node."""
        pass
    
    def _get_power_state_psutil(self) -> dict:
        """
        Get power state using psutil (cross-platform).
        
        Returns:
            Dict with on_battery, battery_percent, plugged_in
        """
        battery = psutil.sensors_battery()
        if battery is None:
            # Desktop without battery - always plugged in
            return {
                "on_battery": False,
                "battery_percent": 100.0,
                "plugged_in": True,
            }
        
        return {
            "on_battery": not battery.power_plugged,
            "battery_percent": battery.percent,
            "plugged_in": battery.power_plugged,
        }
    
    def _get_cpu_load_psutil(self) -> float:
        """
        Get normalized CPU load using psutil.
        
        Returns:
            CPU load normalized to number of cores (0.0-2.0+)
        """
        try:
            # getloadavg returns 1, 5, 15 minute averages
            load_avg = psutil.getloadavg()
            cpu_count = psutil.cpu_count() or 1
            # Normalize by core count, cap at 2.0
            return min(load_avg[0] / cpu_count, 2.0)
        except (AttributeError, OSError):
            # Windows doesn't have load average - use cpu_percent
            return psutil.cpu_percent(interval=0.1) / 100.0
    
    def _get_memory_psutil(self) -> dict:
        """
        Get memory usage using psutil.
        
        Returns:
            Dict with memory_percent, memory_available_gb
        """
        mem = psutil.virtual_memory()
        return {
            "memory_percent": mem.percent,
            "memory_available_gb": mem.available / (1024**3),
        }


class MacOSCostCollector(CostCollector):
    """Cost factor collection for macOS (including Apple Silicon)."""
    
    # Known GPU-heavy processes for heuristic detection
    GPU_PROCESSES = [
        "ollama",
        "mlx_lm",
        "mlx",
        "stable-diffusion",
        "whisper",
        "whisper.cpp",
        "llama.cpp",
        "llamafile",
    ]
    
    def collect(self) -> NodeCostFactors:
        """Collect all cost factors for macOS."""
        # Use psutil for most metrics (atomic-ish collection)
        power = self._get_power_state_psutil()
        cpu_load = self._get_cpu_load_psutil()
        memory = self._get_memory_psutil()
        
        # GPU is heuristic on Apple Silicon
        gpu_load, gpu_estimated = self._get_gpu_load()
        
        # Network state
        is_metered = self._is_metered_connection()
        
        return NodeCostFactors(
            node_id=self.node_id,
            timestamp=time.time(),
            on_battery=power["on_battery"],
            battery_percent=power["battery_percent"],
            plugged_in=power["plugged_in"],
            cpu_load=cpu_load,
            gpu_load=gpu_load,
            gpu_estimated=gpu_estimated,
            memory_percent=memory["memory_percent"],
            memory_available_gb=memory["memory_available_gb"],
            is_metered=is_metered,
        )
    
    def _get_gpu_load(self) -> tuple[float, bool]:
        """
        Get GPU load estimate.
        
        ⚠️ IMPORTANT: On Apple Silicon, this is a HEURISTIC ESTIMATE.
        
        Apple Silicon does not expose GPU utilization without:
        - `sudo powermetrics` (requires root)
        - Private IOKit APIs (unstable)
        
        This uses a combination of:
        1. Presence of known GPU-heavy processes
        2. Power consumption as a proxy (higher power often correlates with GPU activity)
        
        Returns:
            Tuple of (gpu_load_percent, is_estimated)
            is_estimated is True if this is a heuristic, not a real measurement
        """
        # Try NVIDIA first (for hackintosh or eGPU)
        nvidia = self._get_nvidia_gpu()
        if nvidia is not None:
            return nvidia, False
        
        # Apple Silicon heuristic
        return self._get_apple_gpu_heuristic(), True
    
    def _get_nvidia_gpu(self) -> Optional[float]:
        """Try to get NVIDIA GPU utilization via nvidia-smi."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except (subprocess.SubprocessError, FileNotFoundError, ValueError):
            pass
        return None
    
    def _get_apple_gpu_heuristic(self) -> float:
        """
        ⚠️ HEURISTIC ESTIMATE - NOT actual GPU measurement.
        
        Uses process detection and power consumption as proxies.
        This is NOT accurate - it's a rough estimate that errs on the side
        of overestimating GPU load (safer for routing decisions).
        
        Returns:
            Estimated GPU load 0-100%
        """
        estimated_load = 0.0
        
        # Check for known GPU-heavy processes
        try:
            # Use pgrep to find processes
            for proc_name in self.GPU_PROCESSES:
                result = subprocess.run(
                    ["/usr/bin/pgrep", "-x", proc_name],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0 and result.stdout.strip():
                    # Process exists - add estimated load
                    # Each process adds 20-30% estimated load
                    # This is conservative (overestimates) to avoid routing
                    # heavy work to potentially busy GPUs
                    estimated_load += 25.0
        except subprocess.SubprocessError:
            pass
        
        # Check power consumption as additional proxy
        power_estimate = self._get_power_proxy()
        if power_estimate is not None:
            # If power draw is high, assume some GPU activity
            # M1 Max baseline is ~10W idle, ~40W under load
            if power_estimate > 30:
                estimated_load = max(estimated_load, 50.0)
            elif power_estimate > 20:
                estimated_load = max(estimated_load, 25.0)
        
        return min(estimated_load, 100.0)
    
    def _get_power_proxy(self) -> Optional[float]:
        """
        Get estimated power consumption in watts.
        
        Uses ioreg to read battery discharge rate (when on battery)
        or current power draw from SMC.
        
        Returns:
            Estimated watts, or None if unavailable
        """
        try:
            result = subprocess.run(
                ["/usr/sbin/ioreg", "-r", "-d", "1", "-w", "0", "-c", "AppleSmartBattery"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            amperage = None
            voltage = None
            
            for line in result.stdout.split("\n"):
                if "InstantAmperage" in line:
                    match = re.search(r'"InstantAmperage"\s*=\s*(\d+)', line)
                    if match:
                        amperage = int(match.group(1))
                if "Voltage" in line and voltage is None:
                    match = re.search(r'"Voltage"\s*=\s*(\d+)', line)
                    if match:
                        voltage = int(match.group(1))
            
            if amperage is not None and voltage is not None:
                # Calculate watts: V * A (convert from mV * mA to W)
                return (amperage * voltage) / 1_000_000
        except subprocess.SubprocessError:
            pass
        
        return None
    
    def _is_metered_connection(self) -> bool:
        """
        Detect if on a metered connection (iPhone hotspot, etc.).
        
        This is heuristic-based - checks for:
        1. iPhone USB/WiFi tethering
        2. Known hotspot SSID patterns
        
        Returns:
            True if likely on metered connection
        """
        try:
            # Check for iPhone interface
            result = subprocess.run(
                ["/usr/sbin/networksetup", "-listallhardwareports"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "iPhone" in result.stdout:
                return True
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        # Try to get WiFi SSID via networksetup
        try:
            # First get the WiFi interface name
            result = subprocess.run(
                ["/usr/sbin/networksetup", "-listallhardwareports"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            # Find Wi-Fi device name (usually en0 or en1)
            wifi_device = None
            lines = result.stdout.split("\n")
            for i, line in enumerate(lines):
                if "Wi-Fi" in line or "AirPort" in line:
                    # Next line with "Device:" has the interface name
                    for j in range(i+1, min(i+3, len(lines))):
                        if "Device:" in lines[j]:
                            wifi_device = lines[j].split(":")[-1].strip()
                            break
                    break
            
            if wifi_device:
                # Get current network name
                result = subprocess.run(
                    ["/usr/sbin/networksetup", "-getairportnetwork", wifi_device],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                # Output: "Current Wi-Fi Network: NetworkName" or "You are not associated..."
                if "Current Wi-Fi Network:" in result.stdout:
                    ssid = result.stdout.split(":")[-1].strip().lower()
                    hotspot_patterns = ["iphone", "android", "hotspot", "mobile", "tether", "galaxy"]
                    if any(p in ssid for p in hotspot_patterns):
                        return True
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        return False


class LinuxCostCollector(CostCollector):
    """Cost factor collection for Linux."""
    
    def collect(self) -> NodeCostFactors:
        """Collect all cost factors for Linux."""
        power = self._get_power_state()
        cpu_load = self._get_cpu_load_psutil()
        memory = self._get_memory_psutil()
        gpu_load, gpu_estimated = self._get_gpu_load()
        is_metered = self._is_metered_connection()
        
        return NodeCostFactors(
            node_id=self.node_id,
            timestamp=time.time(),
            on_battery=power["on_battery"],
            battery_percent=power["battery_percent"],
            plugged_in=power["plugged_in"],
            cpu_load=cpu_load,
            gpu_load=gpu_load,
            gpu_estimated=gpu_estimated,
            memory_percent=memory["memory_percent"],
            memory_available_gb=memory["memory_available_gb"],
            is_metered=is_metered,
        )
    
    def _get_power_state(self) -> dict:
        """Get power state from /sys or psutil."""
        # Try psutil first (handles most cases)
        power = self._get_power_state_psutil()
        
        # If psutil returns desktop values but /sys has battery info, use that
        from pathlib import Path
        power_supply = Path("/sys/class/power_supply")
        
        if power_supply.exists():
            # Find battery
            for p in power_supply.iterdir():
                if p.name.startswith("BAT"):
                    try:
                        status = (p / "status").read_text().strip()
                        capacity = int((p / "capacity").read_text().strip())
                        
                        power["on_battery"] = status == "Discharging"
                        power["battery_percent"] = float(capacity)
                        power["plugged_in"] = status != "Discharging"
                    except (IOError, ValueError):
                        pass
                    break
        
        return power
    
    def _get_gpu_load(self) -> tuple[float, bool]:
        """
        Get GPU load on Linux.
        
        Tries nvidia-smi first (accurate), then AMD rocm-smi.
        Falls back to heuristic if neither available.
        
        Returns:
            Tuple of (gpu_load_percent, is_estimated)
        """
        # Try NVIDIA
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return float(result.stdout.strip()), False
        except (subprocess.SubprocessError, FileNotFoundError, ValueError):
            pass
        
        # Try AMD
        try:
            result = subprocess.run(
                ["rocm-smi", "--showuse"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Parse rocm-smi output
                match = re.search(r"GPU use \(%\):\s+(\d+)", result.stdout)
                if match:
                    return float(match.group(1)), False
        except (subprocess.SubprocessError, FileNotFoundError, ValueError):
            pass
        
        # Fallback: no GPU or can't measure
        return 0.0, True
    
    def _is_metered_connection(self) -> bool:
        """
        Detect metered connection via NetworkManager D-Bus.
        
        Returns:
            True if NetworkManager reports metered connection
        """
        try:
            # Try dbus-based detection
            import dbus
            bus = dbus.SystemBus()
            nm = bus.get_object(
                "org.freedesktop.NetworkManager",
                "/org/freedesktop/NetworkManager"
            )
            props = dbus.Interface(nm, "org.freedesktop.DBus.Properties")
            
            # NM_METERED_YES = 1, NM_METERED_GUESS_YES = 3
            metered = props.Get("org.freedesktop.NetworkManager", "Metered")
            return metered in (1, 3)
        except Exception:
            pass
        
        return False


class StubCostCollector(CostCollector):
    """Stub collector for unsupported platforms or containers."""
    
    def collect(self) -> NodeCostFactors:
        """Return default cost factors."""
        return NodeCostFactors(
            node_id=self.node_id,
            timestamp=time.time(),
            cpu_load=0.5,  # Assume moderate load
            memory_percent=50.0,
        )


def get_cost_collector(node_id: Optional[str] = None) -> CostCollector:
    """
    Get the appropriate cost collector for the current platform.
    
    Args:
        node_id: Optional node identifier. Defaults to hostname.
    
    Returns:
        Platform-specific CostCollector instance
    """
    system = platform.system()
    
    if system == "Darwin":
        return MacOSCostCollector(node_id)
    elif system == "Linux":
        return LinuxCostCollector(node_id)
    else:
        # Windows or unknown - return stub
        return StubCostCollector(node_id)
