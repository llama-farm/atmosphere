"""
Model Packager for Atmosphere mesh.

Packages models for transfer between nodes, handling serialization,
compression, chunking, and verification.
"""

import base64
import gzip
import hashlib
import io
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Dict, Iterator, List, Optional, Tuple
import yaml

from .registry import ModelManifest

logger = logging.getLogger(__name__)

# Constants
CHUNK_SIZE = 64 * 1024  # 64KB chunks
COMPRESSION_THRESHOLD = 1024  # Compress files larger than 1KB
MAX_INLINE_SIZE = 256 * 1024  # Models under 256KB can be sent inline


@dataclass
class ModelPackage:
    """
    A packaged model ready for transfer.
    
    Contains the model file (possibly compressed) plus manifest.
    """
    manifest: ModelManifest
    data: bytes
    compressed: bool = False
    original_size: int = 0
    chunk_count: int = 1
    
    def to_dict(self) -> dict:
        return {
            "manifest": self.manifest.to_dict(),
            "data_base64": base64.b64encode(self.data).decode(),
            "compressed": self.compressed,
            "original_size": self.original_size,
            "chunk_count": self.chunk_count,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModelPackage":
        return cls(
            manifest=ModelManifest.from_dict(data["manifest"]),
            data=base64.b64decode(data["data_base64"]),
            compressed=data.get("compressed", False),
            original_size=data.get("original_size", 0),
            chunk_count=data.get("chunk_count", 1),
        )
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "ModelPackage":
        return cls.from_dict(json.loads(json_str))


@dataclass
class ModelChunk:
    """
    A chunk of a model package for streaming transfer.
    """
    model_name: str
    model_version: str
    chunk_index: int
    total_chunks: int
    data: bytes
    checksum: str  # SHA256 of this chunk
    
    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "data_base64": base64.b64encode(self.data).decode(),
            "checksum": self.checksum,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModelChunk":
        return cls(
            model_name=data["model_name"],
            model_version=data["model_version"],
            chunk_index=data["chunk_index"],
            total_chunks=data["total_chunks"],
            data=base64.b64decode(data["data_base64"]),
            checksum=data["checksum"],
        )
    
    def verify(self) -> bool:
        """Verify chunk checksum."""
        computed = hashlib.sha256(self.data).hexdigest()
        return computed == self.checksum


@dataclass
class TransferSession:
    """
    Tracks an in-progress model transfer.
    """
    model_name: str
    model_version: str
    total_chunks: int
    manifest: Optional[ModelManifest] = None
    received_chunks: Dict[int, bytes] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    compressed: bool = False
    original_size: int = 0
    
    @property
    def complete(self) -> bool:
        return len(self.received_chunks) == self.total_chunks
    
    @property
    def progress(self) -> float:
        return len(self.received_chunks) / self.total_chunks if self.total_chunks > 0 else 0
    
    def add_chunk(self, chunk: ModelChunk) -> bool:
        """Add a received chunk. Returns True if transfer is now complete."""
        if not chunk.verify():
            logger.warning(f"Chunk {chunk.chunk_index} failed verification")
            return False
        
        self.received_chunks[chunk.chunk_index] = chunk.data
        return self.complete
    
    def assemble(self) -> bytes:
        """Assemble all chunks into complete data."""
        if not self.complete:
            raise ValueError("Transfer not complete")
        
        parts = [self.received_chunks[i] for i in range(self.total_chunks)]
        return b"".join(parts)


class ModelPackager:
    """
    Packages and unpackages models for mesh transfer.
    
    Handles:
    - Serialization of different model formats
    - Compression for efficient transfer
    - Chunking for large models
    - Checksum verification
    
    Usage:
        packager = ModelPackager()
        
        # Package a model
        package = await packager.package(manifest, model_path)
        
        # Or stream chunks
        async for chunk in packager.stream_chunks(manifest, model_path):
            await send_chunk(chunk)
        
        # Receive and reassemble
        session = packager.start_transfer(model_name, version, total_chunks)
        for chunk in incoming_chunks:
            if packager.receive_chunk(session, chunk):
                model_data = packager.complete_transfer(session)
    """
    
    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        compress: bool = True,
        compression_level: int = 6
    ):
        self.chunk_size = chunk_size
        self.compress = compress
        self.compression_level = compression_level
        
        # Active transfer sessions
        self._sessions: Dict[str, TransferSession] = {}
    
    def _session_key(self, model_name: str, version: str) -> str:
        return f"{model_name}:{version}"
    
    # ==================== Packaging ====================
    
    async def package(
        self,
        manifest: ModelManifest,
        model_path: Path
    ) -> ModelPackage:
        """
        Package a model for transfer.
        
        Args:
            manifest: Model manifest
            model_path: Path to model file
        
        Returns:
            ModelPackage ready for transfer
        """
        model_path = Path(model_path)
        
        # Read model data
        with open(model_path, "rb") as f:
            data = f.read()
        
        original_size = len(data)
        compressed = False
        
        # Compress if beneficial
        if self.compress and original_size > COMPRESSION_THRESHOLD:
            compressed_data = gzip.compress(data, compresslevel=self.compression_level)
            if len(compressed_data) < original_size * 0.9:  # At least 10% savings
                data = compressed_data
                compressed = True
                logger.debug(f"Compressed {original_size} -> {len(data)} bytes")
        
        return ModelPackage(
            manifest=manifest,
            data=data,
            compressed=compressed,
            original_size=original_size,
            chunk_count=self._count_chunks(len(data)),
        )
    
    async def unpackage(
        self,
        package: ModelPackage,
        dest_dir: Path
    ) -> Path:
        """
        Unpackage a model to disk.
        
        Args:
            package: Model package
            dest_dir: Directory to write to
        
        Returns:
            Path to written model file
        """
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Decompress if needed
        data = package.data
        if package.compressed:
            data = gzip.decompress(data)
        
        # Verify size
        if package.original_size and len(data) != package.original_size:
            raise ValueError(f"Size mismatch: expected {package.original_size}, got {len(data)}")
        
        # Verify checksum
        checksum = hashlib.sha256(data).hexdigest()
        if package.manifest.checksum_sha256 and checksum != package.manifest.checksum_sha256:
            raise ValueError(f"Checksum mismatch")
        
        # Write file
        filename = f"{package.manifest.name}-{package.manifest.version}{Path(package.manifest.file).suffix}"
        dest_path = dest_dir / filename
        
        with open(dest_path, "wb") as f:
            f.write(data)
        
        logger.info(f"Unpackaged model to {dest_path}")
        return dest_path
    
    # ==================== Chunked Streaming ====================
    
    def _count_chunks(self, size: int) -> int:
        """Calculate number of chunks needed."""
        return (size + self.chunk_size - 1) // self.chunk_size
    
    async def stream_chunks(
        self,
        manifest: ModelManifest,
        model_path: Path
    ) -> Iterator[ModelChunk]:
        """
        Stream model as chunks for transfer.
        
        Yields ModelChunk objects for streaming to peer.
        
        Args:
            manifest: Model manifest
            model_path: Path to model file
        
        Yields:
            ModelChunk objects
        """
        model_path = Path(model_path)
        
        # Read and optionally compress
        with open(model_path, "rb") as f:
            data = f.read()
        
        if self.compress and len(data) > COMPRESSION_THRESHOLD:
            compressed = gzip.compress(data, compresslevel=self.compression_level)
            if len(compressed) < len(data) * 0.9:
                data = compressed
        
        total_chunks = self._count_chunks(len(data))
        
        for i in range(total_chunks):
            start = i * self.chunk_size
            end = min(start + self.chunk_size, len(data))
            chunk_data = data[start:end]
            
            yield ModelChunk(
                model_name=manifest.name,
                model_version=manifest.version,
                chunk_index=i,
                total_chunks=total_chunks,
                data=chunk_data,
                checksum=hashlib.sha256(chunk_data).hexdigest(),
            )
    
    def create_chunks(
        self,
        manifest: ModelManifest,
        model_path: Path
    ) -> List[ModelChunk]:
        """
        Create all chunks for a model (non-streaming version).
        
        Args:
            manifest: Model manifest
            model_path: Path to model file
        
        Returns:
            List of ModelChunk objects
        """
        model_path = Path(model_path)
        chunks = []
        
        with open(model_path, "rb") as f:
            data = f.read()
        
        if self.compress and len(data) > COMPRESSION_THRESHOLD:
            compressed = gzip.compress(data, compresslevel=self.compression_level)
            if len(compressed) < len(data) * 0.9:
                data = compressed
        
        total_chunks = self._count_chunks(len(data))
        
        for i in range(total_chunks):
            start = i * self.chunk_size
            end = min(start + self.chunk_size, len(data))
            chunk_data = data[start:end]
            
            chunks.append(ModelChunk(
                model_name=manifest.name,
                model_version=manifest.version,
                chunk_index=i,
                total_chunks=total_chunks,
                data=chunk_data,
                checksum=hashlib.sha256(chunk_data).hexdigest(),
            ))
        
        return chunks
    
    # ==================== Receiving ====================
    
    def start_transfer(
        self,
        model_name: str,
        version: str,
        total_chunks: int,
        manifest: ModelManifest = None,
        compressed: bool = False,
        original_size: int = 0
    ) -> TransferSession:
        """
        Start a new transfer session.
        
        Args:
            model_name: Name of model being received
            version: Model version
            total_chunks: Expected number of chunks
            manifest: Optional model manifest
            compressed: Whether data is compressed
            original_size: Original uncompressed size
        
        Returns:
            TransferSession to track progress
        """
        key = self._session_key(model_name, version)
        
        session = TransferSession(
            model_name=model_name,
            model_version=version,
            total_chunks=total_chunks,
            manifest=manifest,
            compressed=compressed,
            original_size=original_size,
        )
        
        self._sessions[key] = session
        logger.info(f"Started transfer session for {model_name}:{version}, expecting {total_chunks} chunks")
        
        return session
    
    def get_session(self, model_name: str, version: str) -> Optional[TransferSession]:
        """Get an existing transfer session."""
        return self._sessions.get(self._session_key(model_name, version))
    
    def receive_chunk(self, session: TransferSession, chunk: ModelChunk) -> bool:
        """
        Receive a chunk into a transfer session.
        
        Args:
            session: Transfer session
            chunk: Received chunk
        
        Returns:
            True if transfer is now complete
        """
        return session.add_chunk(chunk)
    
    async def complete_transfer(
        self,
        session: TransferSession,
        dest_dir: Path
    ) -> Path:
        """
        Complete a transfer session and write the model.
        
        Args:
            session: Completed transfer session
            dest_dir: Directory to write model to
        
        Returns:
            Path to written model file
        """
        if not session.complete:
            raise ValueError("Transfer not complete")
        
        # Assemble data
        data = session.assemble()
        
        # Decompress if needed
        if session.compressed:
            data = gzip.decompress(data)
            
            if session.original_size and len(data) != session.original_size:
                raise ValueError(f"Size mismatch after decompression")
        
        # Verify checksum if manifest available
        if session.manifest and session.manifest.checksum_sha256:
            checksum = hashlib.sha256(data).hexdigest()
            if checksum != session.manifest.checksum_sha256:
                raise ValueError("Checksum verification failed")
        
        # Write file
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        suffix = Path(session.manifest.file).suffix if session.manifest else ".model"
        filename = f"{session.model_name}-{session.model_version}{suffix}"
        dest_path = dest_dir / filename
        
        with open(dest_path, "wb") as f:
            f.write(data)
        
        # Clean up session
        key = self._session_key(session.model_name, session.model_version)
        self._sessions.pop(key, None)
        
        logger.info(f"Completed transfer: {dest_path}")
        return dest_path
    
    def cancel_transfer(self, model_name: str, version: str) -> None:
        """Cancel an in-progress transfer."""
        key = self._session_key(model_name, version)
        if key in self._sessions:
            del self._sessions[key]
            logger.info(f"Cancelled transfer for {model_name}:{version}")
    
    # ==================== Utilities ====================
    
    def estimate_transfer_time(
        self,
        size_bytes: int,
        bandwidth_mbps: float = 10.0
    ) -> float:
        """
        Estimate transfer time in seconds.
        
        Args:
            size_bytes: Size of model
            bandwidth_mbps: Estimated bandwidth in Mbps
        
        Returns:
            Estimated seconds
        """
        bits = size_bytes * 8
        mbits = bits / 1_000_000
        return mbits / bandwidth_mbps
    
    def can_inline(self, size_bytes: int) -> bool:
        """Check if a model is small enough to send inline."""
        return size_bytes <= MAX_INLINE_SIZE
    
    def active_sessions(self) -> List[TransferSession]:
        """Get all active transfer sessions."""
        return list(self._sessions.values())
    
    def session_stats(self) -> dict:
        """Get statistics about active sessions."""
        sessions = self.active_sessions()
        return {
            "active_count": len(sessions),
            "sessions": [
                {
                    "model": f"{s.model_name}:{s.model_version}",
                    "progress": s.progress,
                    "received_chunks": len(s.received_chunks),
                    "total_chunks": s.total_chunks,
                }
                for s in sessions
            ]
        }
