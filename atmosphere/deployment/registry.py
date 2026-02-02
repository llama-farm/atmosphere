"""
Model Registry for Atmosphere mesh.

Tracks available models, their metadata, versions, and which nodes have them.
Supports both local registry and mesh-wide model discovery.
"""

import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import yaml

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_MODELS_DIR = Path.home() / ".atmosphere" / "models"
DEFAULT_REGISTRY_FILE = DEFAULT_MODELS_DIR / "registry.yaml"
LLAMAFARM_MODELS_DIR = Path.home() / ".llamafarm" / "models"


@dataclass
class NodeRequirements:
    """Requirements a node must meet to run a model."""
    min_memory_mb: int = 512
    min_cpu_cores: int = 1
    gpu_required: bool = False
    architectures: List[str] = field(default_factory=lambda: ["x86_64", "arm64"])
    
    def to_dict(self) -> dict:
        return {
            "min_memory_mb": self.min_memory_mb,
            "min_cpu_cores": self.min_cpu_cores,
            "gpu_required": self.gpu_required,
            "architectures": self.architectures,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "NodeRequirements":
        return cls(
            min_memory_mb=data.get("min_memory_mb", 512),
            min_cpu_cores=data.get("min_cpu_cores", 1),
            gpu_required=data.get("gpu_required", False),
            architectures=data.get("architectures", ["x86_64", "arm64"]),
        )


@dataclass
class ModelManifest:
    """
    Model manifest containing metadata for deployment.
    
    This describes everything needed to deploy and run a model.
    """
    name: str
    version: str
    type: str  # anomaly_detector, classifier, embedder, router
    
    # File info
    file: str = ""
    format: str = "sklearn"  # sklearn, pytorch, onnx, tensorflow, mlx
    size_bytes: int = 0
    checksum_sha256: str = ""
    
    # Training info
    trained_on: Optional[datetime] = None
    training_data_domain: str = ""
    training_node: str = ""
    
    # Requirements
    requirements: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    node_requirements: NodeRequirements = field(default_factory=NodeRequirements)
    
    # Config
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Deployment
    priority: str = "normal"  # critical, high, normal, low
    roles: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "type": self.type,
            "file": self.file,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "checksum_sha256": self.checksum_sha256,
            "trained_on": self.trained_on.isoformat() if self.trained_on else None,
            "training_data_domain": self.training_data_domain,
            "training_node": self.training_node,
            "requirements": self.requirements,
            "capabilities": self.capabilities,
            "node_requirements": self.node_requirements.to_dict(),
            "config": self.config,
            "priority": self.priority,
            "roles": self.roles,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModelManifest":
        trained_on = None
        if data.get("trained_on"):
            try:
                trained_on = datetime.fromisoformat(data["trained_on"])
            except (ValueError, TypeError):
                pass
        
        node_req = data.get("node_requirements", {})
        if isinstance(node_req, dict):
            node_req = NodeRequirements.from_dict(node_req)
        
        return cls(
            name=data["name"],
            version=data["version"],
            type=data.get("type", "unknown"),
            file=data.get("file", ""),
            format=data.get("format", "sklearn"),
            size_bytes=data.get("size_bytes", 0),
            checksum_sha256=data.get("checksum_sha256", ""),
            trained_on=trained_on,
            training_data_domain=data.get("training_data_domain", ""),
            training_node=data.get("training_node", ""),
            requirements=data.get("requirements", []),
            capabilities=data.get("capabilities", []),
            node_requirements=node_req,
            config=data.get("config", {}),
            priority=data.get("priority", "normal"),
            roles=data.get("roles", []),
        )
    
    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), default_flow_style=False)
    
    @classmethod
    def from_yaml(cls, yaml_str: str) -> "ModelManifest":
        return cls.from_dict(yaml.safe_load(yaml_str))
    
    @property
    def id(self) -> str:
        """Unique identifier for this model version."""
        return f"{self.name}:{self.version}"


@dataclass
class ModelEntry:
    """
    A model entry in the local registry.
    
    Tracks a model that is available on this node.
    """
    manifest: ModelManifest
    path: Path
    loaded: bool = False
    loaded_at: Optional[datetime] = None
    source_node: str = ""
    received_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "manifest": self.manifest.to_dict(),
            "path": str(self.path),
            "loaded": self.loaded,
            "loaded_at": self.loaded_at.isoformat() if self.loaded_at else None,
            "source_node": self.source_node,
            "received_at": self.received_at.isoformat() if self.received_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModelEntry":
        loaded_at = None
        received_at = None
        if data.get("loaded_at"):
            try:
                loaded_at = datetime.fromisoformat(data["loaded_at"])
            except (ValueError, TypeError):
                pass
        if data.get("received_at"):
            try:
                received_at = datetime.fromisoformat(data["received_at"])
            except (ValueError, TypeError):
                pass
        
        return cls(
            manifest=ModelManifest.from_dict(data["manifest"]),
            path=Path(data["path"]),
            loaded=data.get("loaded", False),
            loaded_at=loaded_at,
            source_node=data.get("source_node", ""),
            received_at=received_at,
        )


@dataclass
class MeshModelInfo:
    """
    Information about a model across the mesh.
    
    Tracks which nodes have which versions.
    """
    name: str
    versions: Dict[str, Set[str]] = field(default_factory=dict)  # version -> node_ids
    first_seen: Optional[datetime] = None
    
    def add_node(self, version: str, node_id: str) -> None:
        if version not in self.versions:
            self.versions[version] = set()
        self.versions[version].add(node_id)
        if self.first_seen is None:
            self.first_seen = datetime.now()
    
    def remove_node(self, version: str, node_id: str) -> None:
        if version in self.versions:
            self.versions[version].discard(node_id)
    
    def get_nodes(self, version: str = None) -> Set[str]:
        if version:
            return self.versions.get(version, set())
        return set().union(*self.versions.values())
    
    def latest_version(self) -> Optional[str]:
        if not self.versions:
            return None
        return sorted(self.versions.keys(), reverse=True)[0]
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "versions": {v: list(nodes) for v, nodes in self.versions.items()},
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
        }


class ModelRegistry:
    """
    Model registry for the Atmosphere mesh.
    
    Manages:
    - Local models available on this node
    - Mesh-wide model discovery via gossip
    - Import from LlamaFarm
    
    Usage:
        registry = ModelRegistry()
        await registry.load()
        
        # List models
        for model in registry.list_local():
            print(f"{model.manifest.name} v{model.manifest.version}")
        
        # Import from LlamaFarm
        registry.import_from_llamafarm("anomaly/detector.joblib", "my-detector")
        
        # Check mesh
        mesh_models = registry.list_mesh()
    """
    
    def __init__(
        self,
        models_dir: Path = DEFAULT_MODELS_DIR,
        registry_file: Path = DEFAULT_REGISTRY_FILE,
        node_id: str = ""
    ):
        self.models_dir = Path(models_dir)
        self.registry_file = Path(registry_file)
        self.node_id = node_id
        
        # Local models on this node
        self._local_models: Dict[str, ModelEntry] = {}  # model_id -> entry
        
        # Mesh-wide model knowledge
        self._mesh_models: Dict[str, MeshModelInfo] = {}  # name -> info
        
        self._loaded = False
    
    async def load(self) -> None:
        """Load registry from disk."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        if self.registry_file.exists():
            try:
                with open(self.registry_file) as f:
                    data = yaml.safe_load(f) or {}
                
                for model_id, entry_data in data.get("models", {}).items():
                    self._local_models[model_id] = ModelEntry.from_dict(entry_data)
                
                for name, mesh_data in data.get("mesh_models", {}).items():
                    info = MeshModelInfo(name=name)
                    for version, nodes in mesh_data.get("versions", {}).items():
                        for node in nodes:
                            info.add_node(version, node)
                    self._mesh_models[name] = info
                
                logger.info(f"Loaded registry: {len(self._local_models)} local, {len(self._mesh_models)} mesh models")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
        
        self._loaded = True
    
    async def save(self) -> None:
        """Save registry to disk."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        data = {
            "models": {
                model_id: entry.to_dict()
                for model_id, entry in self._local_models.items()
            },
            "mesh_models": {
                name: info.to_dict()
                for name, info in self._mesh_models.items()
            }
        }
        
        with open(self.registry_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
        
        logger.debug("Registry saved")
    
    # ==================== Local Models ====================
    
    def list_local(self) -> List[ModelEntry]:
        """List all local models."""
        return list(self._local_models.values())
    
    def get_local(self, name: str, version: str = None) -> Optional[ModelEntry]:
        """Get a local model by name and optionally version."""
        if version:
            return self._local_models.get(f"{name}:{version}")
        
        # Find latest version
        matching = [
            e for e in self._local_models.values()
            if e.manifest.name == name
        ]
        if not matching:
            return None
        return sorted(matching, key=lambda e: e.manifest.version, reverse=True)[0]
    
    def has_local(self, name: str, version: str = None) -> bool:
        """Check if a model is available locally."""
        return self.get_local(name, version) is not None
    
    async def register_local(
        self,
        manifest: ModelManifest,
        model_path: Path,
        source_node: str = ""
    ) -> ModelEntry:
        """Register a model as available locally."""
        # Copy to models directory if not already there
        dest_path = self.models_dir / f"{manifest.name}-{manifest.version}{model_path.suffix}"
        
        if model_path != dest_path:
            shutil.copy2(model_path, dest_path)
            logger.info(f"Copied model to {dest_path}")
        
        entry = ModelEntry(
            manifest=manifest,
            path=dest_path,
            source_node=source_node or self.node_id,
            received_at=datetime.now(),
        )
        
        self._local_models[manifest.id] = entry
        await self.save()
        
        logger.info(f"Registered local model: {manifest.id}")
        return entry
    
    async def unregister_local(self, name: str, version: str, delete_file: bool = False) -> bool:
        """Unregister a local model."""
        model_id = f"{name}:{version}"
        
        if model_id not in self._local_models:
            return False
        
        entry = self._local_models.pop(model_id)
        
        if delete_file and entry.path.exists():
            entry.path.unlink()
            logger.info(f"Deleted model file: {entry.path}")
        
        await self.save()
        logger.info(f"Unregistered local model: {model_id}")
        return True
    
    def find_by_capability(self, capability: str) -> List[ModelEntry]:
        """Find local models with a specific capability."""
        return [
            e for e in self._local_models.values()
            if capability in e.manifest.capabilities
        ]
    
    def find_by_type(self, model_type: str) -> List[ModelEntry]:
        """Find local models of a specific type."""
        return [
            e for e in self._local_models.values()
            if e.manifest.type == model_type
        ]
    
    # ==================== Mesh Models ====================
    
    def list_mesh(self) -> List[MeshModelInfo]:
        """List all models known in the mesh."""
        return list(self._mesh_models.values())
    
    def get_mesh_model(self, name: str) -> Optional[MeshModelInfo]:
        """Get mesh-wide info for a model."""
        return self._mesh_models.get(name)
    
    def update_mesh_model(self, name: str, version: str, node_id: str) -> None:
        """Update mesh knowledge about a model."""
        if name not in self._mesh_models:
            self._mesh_models[name] = MeshModelInfo(name=name)
        self._mesh_models[name].add_node(version, node_id)
    
    def find_nodes_with_model(self, name: str, version: str = None) -> Set[str]:
        """Find nodes that have a specific model."""
        info = self._mesh_models.get(name)
        if not info:
            return set()
        
        if version:
            return info.versions.get(version, set())
        return info.get_nodes()
    
    def list_available(self) -> List[MeshModelInfo]:
        """List models available in mesh that we don't have locally."""
        available = []
        for info in self._mesh_models.values():
            local = self.get_local(info.name)
            if local is None:
                available.append(info)
            elif info.latest_version() != local.manifest.version:
                # Newer version available
                available.append(info)
        return available
    
    # ==================== Import ====================
    
    def detect_format(self, path: Path) -> str:
        """Detect model format from file extension."""
        suffix = path.suffix.lower()
        formats = {
            ".joblib": "sklearn",
            ".pkl": "sklearn",
            ".pickle": "sklearn",
            ".onnx": "onnx",
            ".pt": "pytorch",
            ".pth": "pytorch",
            ".safetensors": "safetensors",
            ".h5": "tensorflow",
            ".keras": "tensorflow",
        }
        return formats.get(suffix, "unknown")
    
    def compute_checksum(self, path: Path) -> str:
        """Compute SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    async def import_model(
        self,
        path: Path,
        name: str,
        version: str = "1.0.0",
        model_type: str = "unknown",
        capabilities: List[str] = None,
        config: Dict[str, Any] = None,
    ) -> ModelEntry:
        """
        Import a model file into the registry.
        
        Args:
            path: Path to model file
            name: Name for the model
            version: Version string
            model_type: Type (anomaly_detector, classifier, etc.)
            capabilities: List of capabilities
            config: Model configuration
        
        Returns:
            ModelEntry for the imported model
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        
        # Detect format and compute checksum
        format_type = self.detect_format(path)
        checksum = self.compute_checksum(path)
        size = path.stat().st_size
        
        manifest = ModelManifest(
            name=name,
            version=version,
            type=model_type,
            file=path.name,
            format=format_type,
            size_bytes=size,
            checksum_sha256=checksum,
            trained_on=datetime.now(),
            capabilities=capabilities or [],
            config=config or {},
        )
        
        return await self.register_local(manifest, path, source_node=self.node_id)
    
    async def import_from_llamafarm(
        self,
        subpath: str,
        name: str = None,
        model_type: str = None,
        capabilities: List[str] = None,
    ) -> ModelEntry:
        """
        Import a model from LlamaFarm's models directory.
        
        Args:
            subpath: Path relative to ~/.llamafarm/models/
            name: Name for the model (default: derived from filename)
            model_type: Type of model
            capabilities: List of capabilities
        
        Returns:
            ModelEntry for the imported model
        """
        full_path = LLAMAFARM_MODELS_DIR / subpath
        if not full_path.exists():
            raise FileNotFoundError(f"LlamaFarm model not found: {full_path}")
        
        if name is None:
            # Derive name from filename
            name = full_path.stem.replace("_", "-").lower()
        
        # Try to detect type from path
        if model_type is None:
            if "anomaly" in str(full_path).lower():
                model_type = "anomaly_detector"
            elif "classifier" in str(full_path).lower():
                model_type = "classifier"
            else:
                model_type = "unknown"
        
        return await self.import_model(
            path=full_path,
            name=name,
            model_type=model_type,
            capabilities=capabilities,
        )
    
    async def scan_llamafarm(self, model_type: str = None) -> List[Path]:
        """
        Scan LlamaFarm models directory for importable models.
        
        Args:
            model_type: Filter by type (anomaly, classifier, etc.)
        
        Returns:
            List of paths to model files
        """
        if not LLAMAFARM_MODELS_DIR.exists():
            return []
        
        models = []
        extensions = {".joblib", ".pkl", ".onnx", ".pt", ".pth", ".safetensors"}
        
        for path in LLAMAFARM_MODELS_DIR.rglob("*"):
            if path.suffix.lower() in extensions:
                if model_type is None or model_type.lower() in path.parts:
                    models.append(path)
        
        return sorted(models)
    
    # ==================== Stats ====================
    
    def stats(self) -> dict:
        """Get registry statistics."""
        total_size = sum(
            e.manifest.size_bytes for e in self._local_models.values()
        )
        
        return {
            "local_models": len(self._local_models),
            "mesh_models": len(self._mesh_models),
            "total_size_bytes": total_size,
            "loaded_count": sum(1 for e in self._local_models.values() if e.loaded),
            "by_type": self._count_by_type(),
            "by_capability": self._count_by_capability(),
        }
    
    def _count_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in self._local_models.values():
            t = entry.manifest.type
            counts[t] = counts.get(t, 0) + 1
        return counts
    
    def _count_by_capability(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in self._local_models.values():
            for cap in entry.manifest.capabilities:
                counts[cap] = counts.get(cap, 0) + 1
        return counts
