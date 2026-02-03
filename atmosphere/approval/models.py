"""
Approval Data Models

Defines the data structures for owner approval configuration.
Uses dataclasses for clean Python representation with YAML serialization.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from fnmatch import fnmatch
from typing import Optional, List, Dict, Any


class MicrophoneMode(str, Enum):
    """Microphone access modes."""
    DISABLED = "disabled"
    TRANSCRIPTION = "transcription"  # Audio → text locally, raw audio never leaves
    FULL = "full"  # Raw audio can be streamed


class CameraMode(str, Enum):
    """Camera access modes."""
    STILLS = "stills"
    VIDEO = "video"


class MeshAccessMode(str, Enum):
    """How mesh access is controlled."""
    ALL = "all"  # Allow all meshes
    ALLOWLIST = "allowlist"  # Only specific meshes
    DENYLIST = "denylist"  # All except specific meshes


@dataclass
class ModelPatterns:
    """Wildcard patterns for model filtering.
    
    Uses Python fnmatch glob syntax:
    - * matches everything
    - ? matches any single character
    - [seq] matches any character in seq
    - [!seq] matches any character not in seq
    """
    allow: List[str] = field(default_factory=list)
    deny: List[str] = field(default_factory=list)
    
    def matches_allow(self, model_name: str) -> bool:
        """Check if model matches any allow pattern."""
        if not self.allow:
            return True  # No patterns = allow all
        return any(fnmatch(model_name.lower(), p.lower()) for p in self.allow)
    
    def matches_deny(self, model_name: str) -> bool:
        """Check if model matches any deny pattern."""
        return any(fnmatch(model_name.lower(), p.lower()) for p in self.deny)
    
    def is_allowed(self, model_name: str) -> bool:
        """Check if model is allowed (deny takes precedence)."""
        if self.matches_deny(model_name):
            return False
        return self.matches_allow(model_name)


@dataclass
class OllamaExposure:
    """Configuration for Ollama model exposure."""
    enabled: bool = True
    allow: List[str] = field(default_factory=list)  # Explicit allow list
    deny: List[str] = field(default_factory=list)  # Explicit deny list
    patterns: ModelPatterns = field(default_factory=ModelPatterns)
    
    def is_model_exposed(self, model_name: str) -> bool:
        """Check if a specific model should be exposed."""
        if not self.enabled:
            return False
        
        # Explicit deny takes precedence
        if model_name in self.deny:
            return False
        
        # Check pattern deny
        if self.patterns.matches_deny(model_name):
            return False
        
        # Explicit allow
        if model_name in self.allow:
            return True
        
        # Check pattern allow
        if self.patterns.matches_allow(model_name):
            return True
        
        # If no allow list or patterns, default to allow all
        if not self.allow and not self.patterns.allow:
            return True
        
        return False


@dataclass
class LlamaFarmExposure:
    """Configuration for LlamaFarm project exposure."""
    enabled: bool = True
    allow: List[str] = field(default_factory=list)
    deny: List[str] = field(default_factory=list)
    
    def is_project_exposed(self, project_name: str) -> bool:
        """Check if a specific project should be exposed."""
        if not self.enabled:
            return False
        if project_name in self.deny:
            return False
        if self.allow and project_name not in self.allow:
            return False
        return True


@dataclass
class ModelExposure:
    """Configuration for all model types."""
    ollama: OllamaExposure = field(default_factory=OllamaExposure)
    llamafarm: LlamaFarmExposure = field(default_factory=LlamaFarmExposure)


@dataclass
class GPULimits:
    """Resource limits for GPU."""
    max_vram_percent: int = 80
    max_concurrent_jobs: int = 3
    priority: str = "medium"  # low, medium, high
    
    @property
    def max_vram_gb(self) -> Optional[float]:
        """Calculate max VRAM in GB if we know total VRAM."""
        return None  # Calculated at runtime


@dataclass
class CPULimits:
    """Resource limits for CPU."""
    max_cores: Optional[int] = None  # None = auto-detect reasonable default
    max_percent: int = 50
    max_concurrent_jobs: int = 5


@dataclass
class GPUExposure:
    """Configuration for GPU exposure."""
    enabled: bool = True
    device: Optional[str] = None  # Auto-populated from scan
    limits: GPULimits = field(default_factory=GPULimits)


@dataclass
class CPUExposure:
    """Configuration for CPU exposure."""
    enabled: bool = True
    device: Optional[str] = None  # Auto-populated from scan
    limits: CPULimits = field(default_factory=CPULimits)


@dataclass
class HardwareExposure:
    """Configuration for hardware resources."""
    gpu: GPUExposure = field(default_factory=GPUExposure)
    cpu: CPUExposure = field(default_factory=CPUExposure)


@dataclass
class CameraSettings:
    """Settings for camera access (if enabled)."""
    mode: CameraMode = CameraMode.STILLS
    max_fps: int = 1
    max_resolution: str = "720p"
    require_notification: bool = True  # Flash LED when capturing


@dataclass
class MicrophoneSettings:
    """Settings for microphone access."""
    transcription_model: str = "whisper-small"
    language: str = "auto"


@dataclass
class ScreenSettings:
    """Settings for screen capture (if enabled)."""
    max_fps: int = 1
    require_notification: bool = True
    exclude_windows: List[str] = field(default_factory=lambda: ["1Password", "*Private*"])


@dataclass
class CameraExposure:
    """Configuration for camera exposure."""
    enabled: bool = False  # OFF by default (privacy-sensitive)
    settings: CameraSettings = field(default_factory=CameraSettings)


@dataclass
class MicrophoneExposure:
    """Configuration for microphone exposure."""
    enabled: bool = False  # OFF by default (privacy-sensitive)
    mode: MicrophoneMode = MicrophoneMode.TRANSCRIPTION
    settings: MicrophoneSettings = field(default_factory=MicrophoneSettings)


@dataclass
class ScreenExposure:
    """Configuration for screen capture exposure."""
    enabled: bool = False  # OFF by default (privacy-sensitive)
    settings: ScreenSettings = field(default_factory=ScreenSettings)


@dataclass
class SensorExposure:
    """Configuration for all sensors (privacy-sensitive hardware)."""
    camera: CameraExposure = field(default_factory=CameraExposure)
    microphone: MicrophoneExposure = field(default_factory=MicrophoneExposure)
    screen: ScreenExposure = field(default_factory=ScreenExposure)
    location: bool = False  # OFF by default


@dataclass
class ResourceLimits:
    """Global resource limits."""
    gpu_percent: int = 80
    cpu_percent: int = 50
    max_concurrent_requests: int = 10


@dataclass
class GlobalRateLimits:
    """Global rate limiting configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000


@dataclass
class PerMeshRateLimits:
    """Per-mesh rate limiting configuration."""
    requests_per_minute: int = 30


@dataclass
class LLMRateLimits:
    """Rate limits specifically for LLM requests."""
    requests_per_minute: int = 20
    max_tokens_per_request: int = 4096


@dataclass
class RateLimitConfig:
    """Complete rate limiting configuration."""
    global_limits: GlobalRateLimits = field(default_factory=GlobalRateLimits)
    per_mesh: PerMeshRateLimits = field(default_factory=PerMeshRateLimits)
    llm: LLMRateLimits = field(default_factory=LLMRateLimits)


@dataclass
class MeshAccess:
    """Configuration for which meshes can access this node."""
    mode: MeshAccessMode = MeshAccessMode.ALLOWLIST
    allow: List[str] = field(default_factory=list)
    deny: List[str] = field(default_factory=list)
    
    def is_mesh_allowed(self, mesh_id: str) -> bool:
        """Check if a mesh is allowed to access this node."""
        if self.mode == MeshAccessMode.ALL:
            return mesh_id not in self.deny
        elif self.mode == MeshAccessMode.ALLOWLIST:
            return mesh_id in self.allow
        elif self.mode == MeshAccessMode.DENYLIST:
            return mesh_id not in self.deny
        return False


@dataclass
class AuthConfig:
    """Authentication configuration."""
    require: bool = True
    methods: List[str] = field(default_factory=lambda: ["token"])
    allow_anonymous: bool = False


@dataclass
class AccessConfig:
    """Complete access control configuration."""
    meshes: MeshAccess = field(default_factory=MeshAccess)
    auth: AuthConfig = field(default_factory=AuthConfig)
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)


@dataclass
class NodeMetadata:
    """Metadata about this node."""
    name: str = ""
    description: str = ""
    location: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class AuditConfig:
    """Audit logging configuration."""
    log_all_requests: bool = True
    log_path: str = "~/.atmosphere/audit.log"
    retain_days: int = 30


@dataclass
class ExposureConfig:
    """Complete exposure configuration - what capabilities are shared."""
    models: ModelExposure = field(default_factory=ModelExposure)
    hardware: HardwareExposure = field(default_factory=HardwareExposure)
    sensors: SensorExposure = field(default_factory=SensorExposure)
    resources: ResourceLimits = field(default_factory=ResourceLimits)


@dataclass
class ApprovalConfig:
    """Complete approval configuration.
    
    This is the root configuration object that gets saved to
    ~/.atmosphere/config.yaml
    """
    version: int = 1
    node: NodeMetadata = field(default_factory=NodeMetadata)
    exposure: ExposureConfig = field(default_factory=ExposureConfig)
    access: AccessConfig = field(default_factory=AccessConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    
    # Metadata (not user-editable)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
    
    def mark_updated(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow().isoformat() + "Z"
    
    @classmethod
    def with_safe_defaults(cls, node_name: str = "") -> "ApprovalConfig":
        """Create a config with safe defaults.
        
        Safe defaults:
        - Models: ON (they're local anyway)
        - GPU: ON with 80% limit
        - CPU: ON with 50% limit
        - Camera: OFF
        - Microphone: OFF
        - Screen: OFF
        - Location: OFF
        """
        config = cls()
        config.node.name = node_name
        
        # Models - ON by default (local inference is the point)
        config.exposure.models.ollama.enabled = True
        config.exposure.models.llamafarm.enabled = True
        
        # Hardware - ON with limits
        config.exposure.hardware.gpu.enabled = True
        config.exposure.hardware.gpu.limits.max_vram_percent = 80
        config.exposure.hardware.cpu.enabled = True
        config.exposure.hardware.cpu.limits.max_percent = 50
        
        # Sensors - OFF by default (privacy-sensitive)
        config.exposure.sensors.camera.enabled = False
        config.exposure.sensors.microphone.enabled = False
        config.exposure.sensors.screen.enabled = False
        config.exposure.sensors.location = False
        
        return config


# Type aliases for cleaner function signatures
ScannedCapabilities = Dict[str, Any]
