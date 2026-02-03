"""
Configuration management for Atmosphere.

Handles:
- Node identity storage
- Mesh membership
- Backend configuration
- Runtime settings
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_DATA_DIR = Path.home() / ".atmosphere"

# Port allocation (Ollama uses 11434, LlamaFarm uses 14345)
DEFAULT_API_PORT = 11451    # Atmosphere HTTP API
DEFAULT_GOSSIP_PORT = 11450  # TCP gossip protocol


@dataclass
class BackendConfig:
    """Configuration for an AI backend."""
    type: str  # ollama, llamafarm, universal, vllm, etc.
    host: str = "localhost"
    port: int = 11434  # Backend ports vary: Ollama=11434, LlamaFarm=14345, Universal=11540
    api_key: Optional[str] = None
    models: List[str] = field(default_factory=list)
    enabled: bool = True
    priority: int = 10  # Lower = higher priority for routing
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "host": self.host,
            "port": self.port,
            "api_key": self.api_key,
            "models": self.models,
            "enabled": self.enabled,
            "priority": self.priority
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "BackendConfig":
        # Filter to only known fields to handle config evolution
        known_fields = {"type", "host", "port", "api_key", "models", "enabled", "priority"}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class MeshConfig:
    """Configuration for mesh membership."""
    mesh_id: Optional[str] = None
    mesh_name: Optional[str] = None
    mesh_public_key: Optional[str] = None
    role: str = "member"  # founder, member
    token_path: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "mesh_id": self.mesh_id,
            "mesh_name": self.mesh_name,
            "mesh_public_key": self.mesh_public_key,
            "role": self.role,
            "token_path": self.token_path
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MeshConfig":
        return cls(**data)


@dataclass
class ServerConfig:
    """Configuration for the API server."""
    host: str = "0.0.0.0"
    port: int = DEFAULT_API_PORT
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    debug: bool = False
    
    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "cors_origins": self.cors_origins,
            "debug": self.debug
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ServerConfig":
        return cls(**data)


@dataclass
class Config:
    """
    Main Atmosphere configuration.
    
    Stored at ~/.atmosphere/config.json
    """
    # Node identity
    node_id: Optional[str] = None
    node_name: Optional[str] = None
    
    # Paths
    data_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR)
    
    # Components
    backends: Dict[str, BackendConfig] = field(default_factory=dict)
    mesh: MeshConfig = field(default_factory=MeshConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    
    # Discovery
    mdns_enabled: bool = True
    gossip_interval: int = 30
    
    # Relay server for NAT traversal
    relay_url: Optional[str] = None  # e.g., wss://atmosphere-relay-production.up.railway.app
    
    # Capabilities
    capabilities: List[str] = field(default_factory=list)
    
    @property
    def config_path(self) -> Path:
        return self.data_dir / "config.json"
    
    @property
    def identity_path(self) -> Path:
        return self.data_dir / "identity.json"
    
    @property
    def mesh_path(self) -> Path:
        return self.data_dir / "mesh.json"
    
    @property
    def token_path(self) -> Path:
        return self.data_dir / "token.json"
    
    @property
    def gradient_path(self) -> Path:
        return self.data_dir / "gradient.json"
    
    def ensure_data_dir(self) -> None:
        """Create data directory if it doesn't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def save(self) -> None:
        """Save configuration to disk."""
        self.ensure_data_dir()
        
        data = {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "backends": {k: v.to_dict() for k, v in self.backends.items()},
            "mesh": self.mesh.to_dict(),
            "server": self.server.to_dict(),
            "mdns_enabled": self.mdns_enabled,
            "gossip_interval": self.gossip_interval,
            "relay_url": self.relay_url,
            "capabilities": self.capabilities
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.debug(f"Configuration saved to {self.config_path}")
    
    @classmethod
    def load(cls, data_dir: Optional[Path] = None) -> "Config":
        """Load configuration from disk."""
        data_dir = data_dir or DEFAULT_DATA_DIR
        config_path = data_dir / "config.json"
        
        if not config_path.exists():
            return cls(data_dir=data_dir)
        
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        config = cls(
            data_dir=data_dir,
            node_id=data.get("node_id"),
            node_name=data.get("node_name"),
            mdns_enabled=data.get("mdns_enabled", True),
            gossip_interval=data.get("gossip_interval", 30),
            relay_url=data.get("relay_url"),
            capabilities=data.get("capabilities", [])
        )
        
        # Load backends
        for name, backend_data in data.get("backends", {}).items():
            config.backends[name] = BackendConfig.from_dict(backend_data)
        
        # Load mesh config
        if "mesh" in data:
            config.mesh = MeshConfig.from_dict(data["mesh"])
        
        # Load server config
        if "server" in data:
            config.server = ServerConfig.from_dict(data["server"])
        
        return config
    
    @classmethod
    def exists(cls, data_dir: Optional[Path] = None) -> bool:
        """Check if configuration exists."""
        data_dir = data_dir or DEFAULT_DATA_DIR
        return (data_dir / "config.json").exists()


# Global config instance
_config: Optional[Config] = None


def get_config(data_dir: Optional[Path] = None) -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.load(data_dir)
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config


def reset_config() -> None:
    """Reset the global configuration instance."""
    global _config
    _config = None
