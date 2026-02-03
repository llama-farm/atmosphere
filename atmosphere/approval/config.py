"""
Approval Configuration Management

Handles loading, saving, and validating approval configurations.
Uses YAML for human-readable storage.
"""

import os
import platform
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar, get_type_hints, get_origin, get_args, Union

import yaml

from .models import (
    ApprovalConfig,
    ExposureConfig,
    ModelExposure,
    OllamaExposure,
    LlamaFarmExposure,
    ModelPatterns,
    HardwareExposure,
    GPUExposure,
    CPUExposure,
    GPULimits,
    CPULimits,
    SensorExposure,
    CameraExposure,
    MicrophoneExposure,
    ScreenExposure,
    CameraSettings,
    MicrophoneSettings,
    ScreenSettings,
    CameraMode,
    MicrophoneMode,
    ResourceLimits,
    AccessConfig,
    MeshAccess,
    MeshAccessMode,
    AuthConfig,
    RateLimitConfig,
    GlobalRateLimits,
    PerMeshRateLimits,
    LLMRateLimits,
    NodeMetadata,
    AuditConfig,
)


T = TypeVar('T')


def get_config_dir() -> Path:
    """Get the platform-appropriate config directory.
    
    - macOS: ~/Library/Application Support/atmosphere
    - Linux: ~/.config/atmosphere (or XDG_CONFIG_HOME)
    - Windows: %APPDATA%/atmosphere
    
    Falls back to ~/.atmosphere for simplicity and cross-platform consistency.
    """
    system = platform.system()
    
    # For simplicity, we use ~/.atmosphere everywhere
    # This is more discoverable and works on all platforms
    return Path.home() / ".atmosphere"


def get_config_path() -> Path:
    """Get the full path to the config file."""
    return get_config_dir() / "config.yaml"


def ensure_config_dir() -> Path:
    """Ensure the config directory exists with proper permissions."""
    config_dir = get_config_dir()
    
    if not config_dir.exists():
        config_dir.mkdir(parents=True, mode=0o700)
    
    return config_dir


def _dataclass_to_dict(obj: Any) -> Any:
    """Convert a dataclass (or nested dataclasses) to a dict.
    
    Handles:
    - Nested dataclasses
    - Enums (converted to their values)
    - Lists and dicts
    - Basic types
    """
    if obj is None:
        return None
    
    if isinstance(obj, Enum):
        return obj.value
    
    if is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        for field in fields(obj):
            value = getattr(obj, field.name)
            result[field.name] = _dataclass_to_dict(value)
        return result
    
    if isinstance(obj, list):
        return [_dataclass_to_dict(item) for item in obj]
    
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    
    return obj


def _dict_to_dataclass(cls: Type[T], data: Any) -> T:
    """Convert a dict to a dataclass instance.
    
    Handles:
    - Nested dataclasses
    - Enums
    - Optional fields
    - Default values for missing fields
    """
    if data is None:
        # Try to create with defaults if possible
        try:
            return cls()
        except TypeError:
            return None
    
    if not is_dataclass(cls):
        # Handle enum conversion
        if isinstance(cls, type) and issubclass(cls, Enum):
            return cls(data)
        return data
    
    # Get field types
    type_hints = get_type_hints(cls)
    kwargs = {}
    
    for field in fields(cls):
        field_name = field.name
        field_type = type_hints.get(field_name, field.type)
        
        if field_name in data:
            value = data[field_name]
            
            # Handle Optional types
            origin = get_origin(field_type)
            if origin is Union:
                args = get_args(field_type)
                # Check if it's Optional (Union with None)
                if type(None) in args:
                    non_none_types = [a for a in args if a is not type(None)]
                    if non_none_types and value is not None:
                        field_type = non_none_types[0]
            
            # Handle List types
            if origin is list:
                args = get_args(field_type)
                if args and is_dataclass(args[0]):
                    value = [_dict_to_dataclass(args[0], item) for item in value]
            
            # Handle nested dataclasses
            elif is_dataclass(field_type) and isinstance(value, dict):
                value = _dict_to_dataclass(field_type, value)
            
            # Handle Enums
            elif isinstance(field_type, type) and issubclass(field_type, Enum):
                try:
                    value = field_type(value)
                except ValueError:
                    # Keep the default if value is invalid
                    continue
            
            kwargs[field_name] = value
    
    return cls(**kwargs)


def save_config(config: ApprovalConfig, path: Optional[Path] = None) -> Path:
    """Save the approval config to YAML.
    
    Args:
        config: The configuration to save
        path: Optional custom path (defaults to ~/.atmosphere/config.yaml)
    
    Returns:
        The path where the config was saved
    """
    if path is None:
        path = get_config_path()
    
    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Update timestamp
    config.mark_updated()
    
    # Convert to dict
    data = _dataclass_to_dict(config)
    
    # Add a helpful header comment
    yaml_content = f"""# Atmosphere Node Configuration
# Generated: {config.updated_at or config.created_at}
# 
# This file controls what capabilities your node exposes to the mesh.
# Edit with care - changes take effect immediately on reload.
#
# Documentation: https://atmosphere.llama.farm/docs/approval
# 
# Safe defaults:
#   - Models: Exposed (local inference is the point)
#   - GPU/CPU: Exposed with limits
#   - Camera/Microphone/Screen: OFF (privacy-sensitive)
#

"""
    
    # Dump YAML with nice formatting
    yaml_content += yaml.dump(
        data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=80,
    )
    
    # Write with secure permissions
    with open(path, 'w') as f:
        f.write(yaml_content)
    
    # Set restrictive permissions (owner read/write only)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows doesn't support chmod the same way
    
    return path


def load_config(path: Optional[Path] = None) -> Optional[ApprovalConfig]:
    """Load the approval config from YAML.
    
    Args:
        path: Optional custom path (defaults to ~/.atmosphere/config.yaml)
    
    Returns:
        The loaded configuration, or None if file doesn't exist
    """
    if path is None:
        path = get_config_path()
    
    if not path.exists():
        return None
    
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
    
    if data is None:
        return ApprovalConfig()
    
    return _dict_to_dataclass(ApprovalConfig, data)


def config_exists(path: Optional[Path] = None) -> bool:
    """Check if a config file exists."""
    if path is None:
        path = get_config_path()
    return path.exists()


def validate_config(config: ApprovalConfig) -> list[str]:
    """Validate a configuration and return any warnings/errors.
    
    Returns:
        List of warning/error messages (empty if valid)
    """
    warnings = []
    
    # Check version
    if config.version < 1:
        warnings.append("Config version must be >= 1")
    
    # Check resource limits are sensible
    if config.exposure.hardware.gpu.limits.max_vram_percent > 100:
        warnings.append("GPU VRAM limit cannot exceed 100%")
    if config.exposure.hardware.gpu.limits.max_vram_percent < 10:
        warnings.append("GPU VRAM limit below 10% may cause issues")
    
    if config.exposure.hardware.cpu.limits.max_percent > 100:
        warnings.append("CPU limit cannot exceed 100%")
    if config.exposure.hardware.cpu.limits.max_percent < 10:
        warnings.append("CPU limit below 10% may cause issues")
    
    # Check rate limits are positive
    if config.access.rate_limits.global_limits.requests_per_minute <= 0:
        warnings.append("Rate limit must be positive")
    
    # Check mesh access mode consistency
    if config.access.meshes.mode == MeshAccessMode.ALLOWLIST and not config.access.meshes.allow:
        warnings.append("Allowlist mode with empty allow list will block all meshes")
    
    # Privacy warnings (informational)
    if config.exposure.sensors.camera.enabled:
        warnings.append("⚠️  Camera access is enabled - mesh agents can capture images")
    if config.exposure.sensors.microphone.enabled:
        if config.exposure.sensors.microphone.mode == MicrophoneMode.FULL:
            warnings.append("⚠️  Full microphone access enabled - raw audio can leave this node")
    if config.exposure.sensors.screen.enabled:
        warnings.append("⚠️  Screen capture enabled - your desktop is visible to mesh agents")
    
    return warnings


def get_exposure_summary(config: ApprovalConfig) -> Dict[str, Any]:
    """Get a summary of what's exposed vs private.
    
    Returns a dict with 'exposed' and 'private' lists.
    """
    exposed = []
    private = []
    
    # Models
    if config.exposure.models.ollama.enabled:
        exposed.append("Ollama models")
    else:
        private.append("Ollama models")
    
    if config.exposure.models.llamafarm.enabled:
        exposed.append("LlamaFarm projects")
    else:
        private.append("LlamaFarm projects")
    
    # Hardware
    if config.exposure.hardware.gpu.enabled:
        limit = config.exposure.hardware.gpu.limits.max_vram_percent
        exposed.append(f"GPU ({limit}% VRAM limit)")
    else:
        private.append("GPU")
    
    if config.exposure.hardware.cpu.enabled:
        limit = config.exposure.hardware.cpu.limits.max_percent
        exposed.append(f"CPU ({limit}% limit)")
    else:
        private.append("CPU")
    
    # Sensors (privacy-sensitive)
    if config.exposure.sensors.camera.enabled:
        exposed.append("📷 Camera")
    else:
        private.append("📷 Camera")
    
    if config.exposure.sensors.microphone.enabled:
        mode = config.exposure.sensors.microphone.mode.value
        exposed.append(f"🎤 Microphone ({mode})")
    else:
        private.append("🎤 Microphone")
    
    if config.exposure.sensors.screen.enabled:
        exposed.append("🖥️ Screen capture")
    else:
        private.append("🖥️ Screen capture")
    
    if config.exposure.sensors.location:
        exposed.append("📍 Location")
    else:
        private.append("📍 Location")
    
    return {
        "exposed": exposed,
        "private": private,
        "limits": {
            "rate_limit": f"{config.access.rate_limits.global_limits.requests_per_minute} req/min",
            "auth_required": config.access.auth.require,
        }
    }
