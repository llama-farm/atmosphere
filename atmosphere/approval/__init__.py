"""
Atmosphere Owner Approval Module

Provides the consent-first architecture for capability exposure.
Discovery is automatic, exposure is opt-in.

Key components:
- models: Data structures for approval configuration
- config: YAML config loading/saving
- cli: Interactive approval command

Usage:
    from atmosphere.approval import ApprovalConfig, load_config, save_config
    
    # Load existing config
    config = load_config()
    
    # Create with safe defaults
    config = ApprovalConfig.with_safe_defaults("my-node")
    
    # Check if a model should be exposed
    if config.exposure.models.ollama.is_model_exposed("llama3.2:latest"):
        # Share it with the mesh
        pass
"""

from .models import (
    ApprovalConfig,
    ExposureConfig,
    ModelExposure,
    HardwareExposure,
    SensorExposure,
    ResourceLimits,
    AccessConfig,
    NodeMetadata,
    MicrophoneMode,
    CameraMode,
    MeshAccessMode,
)
from .config import (
    load_config,
    save_config,
    config_exists,
    get_config_path,
    get_config_dir,
    validate_config,
    get_exposure_summary,
)
from .cli import approve

__all__ = [
    # Models
    "ApprovalConfig",
    "ExposureConfig",
    "ModelExposure",
    "HardwareExposure",
    "SensorExposure",
    "ResourceLimits",
    "AccessConfig",
    "NodeMetadata",
    "MicrophoneMode",
    "CameraMode",
    "MeshAccessMode",
    # Config functions
    "load_config",
    "save_config",
    "config_exists",
    "get_config_path",
    "get_config_dir",
    "validate_config",
    "get_exposure_summary",
    # CLI
    "approve",
]
