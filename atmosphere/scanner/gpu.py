"""
GPU Detection Module

Detects available GPUs: Metal (macOS), CUDA (NVIDIA), ROCm (AMD).
"""

import json
import logging
import platform
import subprocess
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """Information about a detected GPU."""
    name: str
    vendor: str
    type: str  # "metal", "cuda", "rocm", "vulkan"
    cores: Optional[int] = None
    memory_mb: Optional[int] = None
    metal_version: Optional[str] = None
    cuda_version: Optional[str] = None
    compute_capability: Optional[str] = None
    unified_memory: bool = False
    index: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "vendor": self.vendor,
            "type": self.type,
            "cores": self.cores,
            "memory_mb": self.memory_mb,
            "metal_version": self.metal_version,
            "cuda_version": self.cuda_version,
            "compute_capability": self.compute_capability,
            "unified_memory": self.unified_memory,
            "index": self.index,
        }


def detect_gpus() -> List[GPUInfo]:
    """
    Detect all available GPUs on the system.
    
    Returns list of GPUInfo objects for detected GPUs.
    Safe to call on any platform - returns empty list if no GPUs found.
    """
    gpus = []
    
    system = platform.system()
    
    if system == "Darwin":
        metal_gpu = _detect_metal_gpu()
        if metal_gpu:
            gpus.append(metal_gpu)
    elif system == "Linux":
        # Try CUDA first (NVIDIA)
        cuda_gpus = _detect_cuda_gpus()
        gpus.extend(cuda_gpus)
        
        # Try ROCm (AMD)
        if not cuda_gpus:
            rocm_gpus = _detect_rocm_gpus()
            gpus.extend(rocm_gpus)
    
    return gpus


def _detect_metal_gpu() -> Optional[GPUInfo]:
    """Detect Apple Silicon GPU via system_profiler."""
    try:
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.warning(f"system_profiler failed: {result.stderr}")
            return None
        
        data = json.loads(result.stdout)
        displays = data.get("SPDisplaysDataType", [])
        
        for gpu in displays:
            name = gpu.get("sppci_model", "Unknown GPU")
            vendor = gpu.get("sppci_vendor", "Unknown")
            
            # Metal version can be in different keys
            metal_version = gpu.get("spdisplays_metal", "")
            if not metal_version:
                # Try the mtlgpufamilysupport key (newer macOS)
                mtl_support = gpu.get("spdisplays_mtlgpufamilysupport", "")
                if mtl_support:
                    # Extract version from "spdisplays_metal4" -> "4"
                    if "metal" in mtl_support.lower():
                        # Clean up to just the version number
                        metal_version = mtl_support.replace("spdisplays_metal", "")
            
            # Get GPU cores
            cores = gpu.get("sppci_cores", 0)
            if isinstance(cores, str):
                try:
                    cores = int(cores)
                except ValueError:
                    cores = 0
            
            # Check for unified memory (Apple Silicon)
            is_apple_silicon = "Apple" in vendor or "Apple" in name
            
            # Get system memory for Apple Silicon
            memory_mb = None
            if is_apple_silicon:
                memory_mb = _get_system_memory_mb()
            else:
                # Try to get VRAM
                vram_str = gpu.get("spdisplays_vram", "")
                if vram_str:
                    memory_mb = _parse_memory_string(vram_str)
            
            # Clean up vendor string
            clean_vendor = vendor.replace("sppci_vendor_", "")
            if not clean_vendor or clean_vendor == "Unknown":
                if "Apple" in name:
                    clean_vendor = "Apple"
            
            # Return if this is a GPU (not just a display)
            device_type = gpu.get("sppci_device_type", "")
            if device_type == "spdisplays_gpu" or is_apple_silicon or metal_version:
                return GPUInfo(
                    name=name,
                    vendor=clean_vendor,
                    type="metal",
                    cores=cores,
                    memory_mb=memory_mb,
                    metal_version=metal_version,
                    unified_memory=is_apple_silicon,
                )
        
        return None
        
    except subprocess.TimeoutExpired:
        logger.warning("system_profiler timed out")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse system_profiler output: {e}")
        return None
    except Exception as e:
        logger.warning(f"Metal GPU detection failed: {e}")
        return None


def _get_system_memory_mb() -> Optional[int]:
    """Get total system memory in MB (for unified memory Macs)."""
    try:
        result = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            bytes_val = int(result.stdout.strip())
            return bytes_val // (1024 * 1024)
    except Exception:
        pass
    return None


def _parse_memory_string(mem_str: str) -> Optional[int]:
    """Parse memory string like '8 GB' to MB."""
    try:
        parts = mem_str.strip().split()
        if len(parts) >= 2:
            value = float(parts[0])
            unit = parts[1].upper()
            if "GB" in unit:
                return int(value * 1024)
            elif "MB" in unit:
                return int(value)
            elif "TB" in unit:
                return int(value * 1024 * 1024)
    except Exception:
        pass
    return None


def _detect_cuda_gpus() -> List[GPUInfo]:
    """Detect NVIDIA GPUs via nvidia-smi."""
    gpus = []
    
    try:
        # Check if nvidia-smi exists
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,driver_version,compute_cap",
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                try:
                    gpus.append(GPUInfo(
                        name=parts[1],
                        vendor="NVIDIA",
                        type="cuda",
                        index=int(parts[0]),
                        memory_mb=int(float(parts[2])),
                        cuda_version=parts[3],
                        compute_capability=parts[4],
                    ))
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse CUDA GPU info: {e}")
        
        return gpus
        
    except FileNotFoundError:
        # nvidia-smi not installed
        return []
    except subprocess.TimeoutExpired:
        logger.warning("nvidia-smi timed out")
        return []
    except Exception as e:
        logger.warning(f"CUDA GPU detection failed: {e}")
        return []


def _detect_rocm_gpus() -> List[GPUInfo]:
    """Detect AMD GPUs via rocm-smi."""
    gpus = []
    
    try:
        result = subprocess.run(
            ["rocm-smi", "--showproductname"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        # Parse rocm-smi output
        current_idx = 0
        for line in result.stdout.split("\n"):
            if "GPU[" in line:
                # Extract GPU name
                if "Card series:" in line:
                    name = line.split(":")[-1].strip()
                    gpus.append(GPUInfo(
                        name=name,
                        vendor="AMD",
                        type="rocm",
                        index=current_idx,
                    ))
                    current_idx += 1
        
        return gpus
        
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.warning(f"ROCm GPU detection failed: {e}")
        return []


def get_gpu_summary(gpus: List[GPUInfo]) -> str:
    """Generate a human-readable summary of detected GPUs."""
    if not gpus:
        return "No GPUs detected"
    
    lines = []
    for gpu in gpus:
        parts = [gpu.name]
        
        if gpu.metal_version:
            parts.append(f"Metal {gpu.metal_version}")
        elif gpu.cuda_version:
            parts.append(f"CUDA {gpu.cuda_version}")
        
        if gpu.cores:
            parts.append(f"{gpu.cores} cores")
        
        if gpu.memory_mb:
            if gpu.memory_mb >= 1024:
                mem_str = f"{gpu.memory_mb / 1024:.0f}GB"
            else:
                mem_str = f"{gpu.memory_mb}MB"
            
            if gpu.unified_memory:
                parts.append(f"{mem_str} unified")
            else:
                parts.append(f"{mem_str} VRAM")
        
        lines.append(" - ".join(parts))
    
    return "\n".join(lines)
