"""
Atmosphere Capability Scanner

Discovers system capabilities: GPUs, models, hardware, and services.
"""

from .gpu import detect_gpus, GPUInfo
from .models import detect_models, ModelInfo
from .hardware import detect_hardware, CameraInfo, MicrophoneInfo
from .services import detect_services, ServiceInfo
from .permissions import check_permissions, PermissionStatus

__all__ = [
    "detect_gpus",
    "detect_models",
    "detect_hardware",
    "detect_services",
    "check_permissions",
    "GPUInfo",
    "ModelInfo",
    "CameraInfo",
    "MicrophoneInfo",
    "ServiceInfo",
    "PermissionStatus",
]
