"""
Model Distributor for Atmosphere mesh.

Handles distribution of models across the mesh using various strategies:
- Push: Admin pushes to specific nodes
- Pull: Node requests from mesh
- Gossip: Automatic peer-to-peer discovery
- Organic: Auto-deployment to new nodes
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Awaitable, Dict, List, Optional, Set
import json

from .registry import ModelRegistry, ModelManifest, ModelEntry
from .packager import ModelPackager, ModelPackage, ModelChunk, TransferSession

logger = logging.getLogger(__name__)


class DeploymentStrategy(Enum):
    """Model deployment strategy."""
    PUSH = "push"       # Admin pushes to nodes
    PULL = "pull"       # Node pulls from mesh
    GOSSIP = "gossip"   # Peer discovery and transfer
    ORGANIC = "organic" # Auto-deploy to matching nodes


class TransferStatus(Enum):
    """Status of a model transfer."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class NodeCapabilities:
    """
    Capabilities of a node for model deployment decisions.
    """
    node_id: str
    role: str = "unknown"  # edge, gateway, central, etc.
    memory_mb: int = 0
    cpu_cores: int = 0
    has_gpu: bool = False
    architecture: str = "unknown"
    
    # What this node is interested in
    interests: List[str] = field(default_factory=list)
    
    # Constraints
    max_model_size_mb: int = 100
    max_models: int = 10
    
    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "memory_mb": self.memory_mb,
            "cpu_cores": self.cpu_cores,
            "has_gpu": self.has_gpu,
            "architecture": self.architecture,
            "interests": self.interests,
            "max_model_size_mb": self.max_model_size_mb,
            "max_models": self.max_models,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "NodeCapabilities":
        return cls(
            node_id=data["node_id"],
            role=data.get("role", "unknown"),
            memory_mb=data.get("memory_mb", 0),
            cpu_cores=data.get("cpu_cores", 0),
            has_gpu=data.get("has_gpu", False),
            architecture=data.get("architecture", "unknown"),
            interests=data.get("interests", []),
            max_model_size_mb=data.get("max_model_size_mb", 100),
            max_models=data.get("max_models", 10),
        )
    
    def can_run_model(self, manifest: ModelManifest) -> bool:
        """Check if this node can run a model."""
        reqs = manifest.node_requirements
        
        if self.memory_mb < reqs.min_memory_mb:
            return False
        
        if self.cpu_cores < reqs.min_cpu_cores:
            return False
        
        if reqs.gpu_required and not self.has_gpu:
            return False
        
        if self.architecture not in reqs.architectures:
            return False
        
        size_mb = manifest.size_bytes / (1024 * 1024)
        if size_mb > self.max_model_size_mb:
            return False
        
        return True
    
    def wants_model(self, manifest: ModelManifest) -> bool:
        """Check if this node wants a model based on role/interests."""
        # Check role match
        if manifest.roles and self.role not in manifest.roles:
            return False
        
        # Check capability interests
        if self.interests:
            if not any(cap in self.interests for cap in manifest.capabilities):
                return False
        
        return True


@dataclass
class TransferRecord:
    """
    Record of a model transfer.
    """
    transfer_id: str
    model_name: str
    model_version: str
    from_node: str
    to_node: str
    strategy: DeploymentStrategy
    status: TransferStatus = TransferStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    bytes_transferred: int = 0
    total_bytes: int = 0
    
    def to_dict(self) -> dict:
        return {
            "transfer_id": self.transfer_id,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "strategy": self.strategy.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "bytes_transferred": self.bytes_transferred,
            "total_bytes": self.total_bytes,
        }
    
    @property
    def progress(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return self.bytes_transferred / self.total_bytes


@dataclass
class DeploymentRule:
    """
    Rule for automatic model deployment.
    """
    name: str
    trigger: str  # node_join, model_publish, manual
    conditions: Dict[str, Any] = field(default_factory=dict)
    models: List[Dict[str, Any]] = field(default_factory=list)
    enabled: bool = True
    
    def matches_node(self, capabilities: NodeCapabilities) -> bool:
        """Check if a node matches this rule's conditions."""
        if not self.enabled:
            return False
        
        if "role" in self.conditions:
            if capabilities.role != self.conditions["role"]:
                return False
        
        if "min_memory_mb" in self.conditions:
            if capabilities.memory_mb < self.conditions["min_memory_mb"]:
                return False
        
        if "has_gpu" in self.conditions:
            if capabilities.has_gpu != self.conditions["has_gpu"]:
                return False
        
        return True
    
    def get_models_for_node(
        self,
        capabilities: NodeCapabilities,
        available_models: List[ModelManifest]
    ) -> List[ModelManifest]:
        """Get models this rule wants deployed to a node."""
        if not self.matches_node(capabilities):
            return []
        
        result = []
        for spec in self.models:
            name = spec.get("name", "*")
            version = spec.get("version", "latest")
            
            for model in available_models:
                if name == "*" or model.name == name:
                    if version == "latest" or model.version == version:
                        if capabilities.can_run_model(model):
                            result.append(model)
        
        return result


# Callback types
SendPackageCallback = Callable[[str, ModelPackage], Awaitable[bool]]
SendChunkCallback = Callable[[str, ModelChunk], Awaitable[bool]]
RequestModelCallback = Callable[[str, str, str], Awaitable[Optional[ModelPackage]]]


class ModelDistributor:
    """
    Distributes models across the Atmosphere mesh.
    
    Coordinates with the registry and packager to move models
    between nodes using various strategies.
    
    Usage:
        distributor = ModelDistributor(
            node_id="my-node",
            registry=registry,
            packager=packager
        )
        
        # Set up callbacks for network communication
        distributor.set_send_callback(send_to_node)
        
        # Push a model to a node
        await distributor.push("my-model", "1.0.0", "target-node")
        
        # Pull a model from the mesh
        await distributor.pull("needed-model")
        
        # Deploy to all capable nodes
        await distributor.deploy("my-model", strategy=DeploymentStrategy.ORGANIC)
    """
    
    def __init__(
        self,
        node_id: str,
        registry: ModelRegistry,
        packager: ModelPackager,
        models_dir: Path = None
    ):
        self.node_id = node_id
        self.registry = registry
        self.packager = packager
        self.models_dir = models_dir or Path.home() / ".atmosphere" / "models"
        
        # Known nodes and their capabilities
        self._node_capabilities: Dict[str, NodeCapabilities] = {}
        
        # Transfer history
        self._transfers: Dict[str, TransferRecord] = {}
        self._transfer_counter = 0
        
        # Deployment rules
        self._rules: List[DeploymentRule] = []
        
        # Callbacks for network operations
        self._send_package: Optional[SendPackageCallback] = None
        self._send_chunk: Optional[SendChunkCallback] = None
        self._request_model: Optional[RequestModelCallback] = None
        
        # Events
        self.on_transfer_complete: Optional[Callable[[TransferRecord], None]] = None
        self.on_transfer_failed: Optional[Callable[[TransferRecord], None]] = None
    
    def set_send_callback(self, callback: SendPackageCallback) -> None:
        """Set callback for sending packages to nodes."""
        self._send_package = callback
    
    def set_chunk_callback(self, callback: SendChunkCallback) -> None:
        """Set callback for sending chunks to nodes."""
        self._send_chunk = callback
    
    def set_request_callback(self, callback: RequestModelCallback) -> None:
        """Set callback for requesting models from nodes."""
        self._request_model = callback
    
    # ==================== Node Management ====================
    
    def register_node(self, capabilities: NodeCapabilities) -> None:
        """Register a node and its capabilities."""
        self._node_capabilities[capabilities.node_id] = capabilities
        logger.info(f"Registered node {capabilities.node_id} (role={capabilities.role})")
    
    def unregister_node(self, node_id: str) -> None:
        """Unregister a node."""
        self._node_capabilities.pop(node_id, None)
    
    def get_node_capabilities(self, node_id: str) -> Optional[NodeCapabilities]:
        """Get capabilities for a node."""
        return self._node_capabilities.get(node_id)
    
    def find_capable_nodes(self, manifest: ModelManifest) -> List[str]:
        """Find nodes capable of running a model."""
        return [
            node_id for node_id, caps in self._node_capabilities.items()
            if caps.can_run_model(manifest) and caps.wants_model(manifest)
        ]
    
    def find_nodes_with_model(self, name: str, version: str = None) -> Set[str]:
        """Find nodes that have a specific model."""
        return self.registry.find_nodes_with_model(name, version)
    
    # ==================== Push (Admin-initiated) ====================
    
    async def push(
        self,
        model_name: str,
        version: str,
        target_node: str,
        chunked: bool = True
    ) -> TransferRecord:
        """
        Push a model to a specific node.
        
        Args:
            model_name: Name of model to push
            version: Model version
            target_node: Target node ID
            chunked: Use chunked transfer for large models
        
        Returns:
            TransferRecord tracking the transfer
        """
        # Get local model
        entry = self.registry.get_local(model_name, version)
        if not entry:
            raise ValueError(f"Model {model_name}:{version} not found locally")
        
        # Create transfer record
        record = self._create_transfer(
            model_name, version, self.node_id, target_node,
            DeploymentStrategy.PUSH
        )
        record.total_bytes = entry.manifest.size_bytes
        record.status = TransferStatus.IN_PROGRESS
        record.started_at = datetime.now()
        
        try:
            if chunked and entry.manifest.size_bytes > self.packager.chunk_size:
                # Chunked transfer
                await self._push_chunked(entry, target_node, record)
            else:
                # Single package transfer
                await self._push_package(entry, target_node, record)
            
            record.status = TransferStatus.COMPLETED
            record.completed_at = datetime.now()
            logger.info(f"Push completed: {model_name}:{version} -> {target_node}")
            
            if self.on_transfer_complete:
                self.on_transfer_complete(record)
            
        except Exception as e:
            record.status = TransferStatus.FAILED
            record.error = str(e)
            logger.error(f"Push failed: {e}")
            
            if self.on_transfer_failed:
                self.on_transfer_failed(record)
        
        return record
    
    async def _push_package(
        self,
        entry: ModelEntry,
        target_node: str,
        record: TransferRecord
    ) -> None:
        """Push model as single package."""
        if not self._send_package:
            raise RuntimeError("Send callback not configured")
        
        package = await self.packager.package(entry.manifest, entry.path)
        success = await self._send_package(target_node, package)
        
        if not success:
            raise RuntimeError(f"Failed to send package to {target_node}")
        
        record.bytes_transferred = len(package.data)
    
    async def _push_chunked(
        self,
        entry: ModelEntry,
        target_node: str,
        record: TransferRecord
    ) -> None:
        """Push model as chunks."""
        if not self._send_chunk:
            raise RuntimeError("Chunk callback not configured")
        
        chunks = self.packager.create_chunks(entry.manifest, entry.path)
        
        for chunk in chunks:
            success = await self._send_chunk(target_node, chunk)
            if not success:
                raise RuntimeError(f"Failed to send chunk {chunk.chunk_index}")
            record.bytes_transferred += len(chunk.data)
    
    async def push_to_role(
        self,
        model_name: str,
        version: str,
        role: str
    ) -> List[TransferRecord]:
        """Push model to all nodes with a specific role."""
        targets = [
            node_id for node_id, caps in self._node_capabilities.items()
            if caps.role == role
        ]
        
        records = []
        for target in targets:
            record = await self.push(model_name, version, target)
            records.append(record)
        
        return records
    
    async def push_to_all(
        self,
        model_name: str,
        version: str
    ) -> List[TransferRecord]:
        """Push model to all capable nodes."""
        entry = self.registry.get_local(model_name, version)
        if not entry:
            raise ValueError(f"Model {model_name}:{version} not found locally")
        
        targets = self.find_capable_nodes(entry.manifest)
        targets = [t for t in targets if t != self.node_id]
        
        records = []
        for target in targets:
            record = await self.push(model_name, version, target)
            records.append(record)
        
        return records
    
    # ==================== Pull (Node-initiated) ====================
    
    async def pull(
        self,
        model_name: str,
        version: str = None,
        from_node: str = None
    ) -> TransferRecord:
        """
        Pull a model from the mesh.
        
        Args:
            model_name: Name of model to pull
            version: Specific version (or None for latest)
            from_node: Specific node to pull from (or None for auto-select)
        
        Returns:
            TransferRecord tracking the transfer
        """
        if not self._request_model:
            raise RuntimeError("Request callback not configured")
        
        # Find source node
        if from_node is None:
            nodes = self.find_nodes_with_model(model_name, version)
            if not nodes:
                raise ValueError(f"No nodes have model {model_name}")
            from_node = list(nodes)[0]  # TODO: Select nearest/best
        
        # Determine version
        if version is None:
            mesh_info = self.registry.get_mesh_model(model_name)
            if mesh_info:
                version = mesh_info.latest_version()
        
        if version is None:
            raise ValueError(f"Cannot determine version for {model_name}")
        
        # Create transfer record
        record = self._create_transfer(
            model_name, version, from_node, self.node_id,
            DeploymentStrategy.PULL
        )
        record.status = TransferStatus.IN_PROGRESS
        record.started_at = datetime.now()
        
        try:
            # Request model
            package = await self._request_model(from_node, model_name, version)
            if not package:
                raise RuntimeError(f"Failed to get model from {from_node}")
            
            record.total_bytes = len(package.data)
            record.bytes_transferred = len(package.data)
            
            # Unpack and register
            model_path = await self.packager.unpackage(package, self.models_dir)
            await self.registry.register_local(
                package.manifest, model_path, source_node=from_node
            )
            
            record.status = TransferStatus.COMPLETED
            record.completed_at = datetime.now()
            logger.info(f"Pull completed: {model_name}:{version} from {from_node}")
            
            if self.on_transfer_complete:
                self.on_transfer_complete(record)
            
        except Exception as e:
            record.status = TransferStatus.FAILED
            record.error = str(e)
            logger.error(f"Pull failed: {e}")
            
            if self.on_transfer_failed:
                self.on_transfer_failed(record)
        
        return record
    
    async def pull_by_capability(
        self,
        capability: str
    ) -> List[TransferRecord]:
        """Pull all models with a specific capability."""
        mesh_models = self.registry.list_mesh()
        records = []
        
        for info in mesh_models:
            # Check if any version has this capability (would need manifest)
            # For now, pull and check
            if not self.registry.has_local(info.name):
                try:
                    record = await self.pull(info.name)
                    entry = self.registry.get_local(info.name)
                    if entry and capability in entry.manifest.capabilities:
                        records.append(record)
                except Exception as e:
                    logger.warning(f"Failed to pull {info.name}: {e}")
        
        return records
    
    # ==================== Organic Deployment ====================
    
    def add_deployment_rule(self, rule: DeploymentRule) -> None:
        """Add an automatic deployment rule."""
        self._rules.append(rule)
    
    def remove_deployment_rule(self, name: str) -> bool:
        """Remove a deployment rule by name."""
        for i, rule in enumerate(self._rules):
            if rule.name == name:
                del self._rules[i]
                return True
        return False
    
    async def handle_node_join(
        self,
        capabilities: NodeCapabilities
    ) -> List[TransferRecord]:
        """
        Handle a new node joining - trigger organic deployment.
        
        Args:
            capabilities: Capabilities of the joining node
        
        Returns:
            List of transfers initiated
        """
        self.register_node(capabilities)
        
        # Get all local models (this node might be the source)
        local_models = [e.manifest for e in self.registry.list_local()]
        
        # Find models to deploy based on rules
        models_to_deploy = []
        for rule in self._rules:
            if rule.trigger == "node_join":
                models = rule.get_models_for_node(capabilities, local_models)
                models_to_deploy.extend(models)
        
        # Also check model-level deployment specs
        for model in local_models:
            if capabilities.wants_model(model) and capabilities.can_run_model(model):
                if model not in models_to_deploy:
                    models_to_deploy.append(model)
        
        # Deploy models
        records = []
        for model in models_to_deploy:
            try:
                record = await self.push(
                    model.name, model.version, capabilities.node_id
                )
                records.append(record)
            except Exception as e:
                logger.error(f"Failed to deploy {model.name} to {capabilities.node_id}: {e}")
        
        if records:
            logger.info(f"Organic deployment: sent {len(records)} models to {capabilities.node_id}")
        
        return records
    
    async def deploy(
        self,
        model_name: str,
        version: str = None,
        strategy: DeploymentStrategy = DeploymentStrategy.ORGANIC,
        target_nodes: List[str] = None,
        target_role: str = None
    ) -> List[TransferRecord]:
        """
        Deploy a model using the specified strategy.
        
        Args:
            model_name: Model to deploy
            version: Specific version (or None for latest)
            strategy: Deployment strategy
            target_nodes: Specific nodes (for PUSH strategy)
            target_role: Target role (for PUSH strategy)
        
        Returns:
            List of transfers initiated
        """
        # Get model
        entry = self.registry.get_local(model_name, version)
        if not entry:
            raise ValueError(f"Model {model_name} not found locally")
        
        if version is None:
            version = entry.manifest.version
        
        if strategy == DeploymentStrategy.PUSH:
            if target_nodes:
                records = []
                for node in target_nodes:
                    records.append(await self.push(model_name, version, node))
                return records
            elif target_role:
                return await self.push_to_role(model_name, version, target_role)
            else:
                return await self.push_to_all(model_name, version)
        
        elif strategy == DeploymentStrategy.ORGANIC:
            # Find all capable nodes we know about
            targets = self.find_capable_nodes(entry.manifest)
            targets = [t for t in targets if t != self.node_id]
            
            # Don't push to nodes that already have it
            existing = self.find_nodes_with_model(model_name, version)
            targets = [t for t in targets if t not in existing]
            
            records = []
            for target in targets:
                try:
                    records.append(await self.push(model_name, version, target))
                except Exception as e:
                    logger.error(f"Failed to deploy to {target}: {e}")
            
            return records
        
        else:
            raise ValueError(f"Unsupported strategy for deploy: {strategy}")
    
    # ==================== Receive Handling ====================
    
    async def receive_package(
        self,
        package: ModelPackage,
        from_node: str
    ) -> ModelEntry:
        """
        Handle receiving a model package.
        
        Args:
            package: Received model package
            from_node: Node that sent it
        
        Returns:
            Registered ModelEntry
        """
        # Unpack
        model_path = await self.packager.unpackage(package, self.models_dir)
        
        # Register
        entry = await self.registry.register_local(
            package.manifest, model_path, source_node=from_node
        )
        
        logger.info(f"Received model {package.manifest.id} from {from_node}")
        return entry
    
    async def receive_chunk(
        self,
        chunk: ModelChunk,
        from_node: str,
        manifest: ModelManifest = None
    ) -> Optional[ModelEntry]:
        """
        Handle receiving a model chunk.
        
        Args:
            chunk: Received chunk
            from_node: Node that sent it
            manifest: Model manifest (required for first chunk)
        
        Returns:
            ModelEntry if transfer is complete, None otherwise
        """
        # Get or create session
        session = self.packager.get_session(chunk.model_name, chunk.model_version)
        
        if session is None:
            if manifest is None:
                logger.warning(f"Received chunk without session or manifest")
                return None
            
            session = self.packager.start_transfer(
                chunk.model_name,
                chunk.model_version,
                chunk.total_chunks,
                manifest=manifest
            )
        
        # Add chunk
        complete = self.packager.receive_chunk(session, chunk)
        
        if complete:
            # Complete transfer
            model_path = await self.packager.complete_transfer(session, self.models_dir)
            
            # Register
            entry = await self.registry.register_local(
                session.manifest, model_path, source_node=from_node
            )
            
            logger.info(f"Received complete model {session.model_name}:{session.model_version}")
            return entry
        
        return None
    
    # ==================== Transfer Management ====================
    
    def _create_transfer(
        self,
        model_name: str,
        version: str,
        from_node: str,
        to_node: str,
        strategy: DeploymentStrategy
    ) -> TransferRecord:
        """Create a new transfer record."""
        self._transfer_counter += 1
        transfer_id = f"xfer-{self._transfer_counter:06d}"
        
        record = TransferRecord(
            transfer_id=transfer_id,
            model_name=model_name,
            model_version=version,
            from_node=from_node,
            to_node=to_node,
            strategy=strategy,
        )
        
        self._transfers[transfer_id] = record
        return record
    
    def get_transfer(self, transfer_id: str) -> Optional[TransferRecord]:
        """Get a transfer record."""
        return self._transfers.get(transfer_id)
    
    def list_transfers(
        self,
        status: TransferStatus = None,
        model_name: str = None
    ) -> List[TransferRecord]:
        """List transfer records with optional filters."""
        records = list(self._transfers.values())
        
        if status:
            records = [r for r in records if r.status == status]
        if model_name:
            records = [r for r in records if r.model_name == model_name]
        
        return records
    
    # ==================== Stats ====================
    
    def stats(self) -> dict:
        """Get distributor statistics."""
        transfers = list(self._transfers.values())
        
        by_status = {}
        for t in transfers:
            s = t.status.value
            by_status[s] = by_status.get(s, 0) + 1
        
        return {
            "known_nodes": len(self._node_capabilities),
            "deployment_rules": len(self._rules),
            "total_transfers": len(transfers),
            "transfers_by_status": by_status,
            "active_sessions": len(self.packager.active_sessions()),
        }
