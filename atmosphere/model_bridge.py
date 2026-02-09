#!/usr/bin/env python3
"""
Model Bridge - Serves models from LlamaFarm to Atmosphere mesh

This module:
- Scans LlamaFarm's model storage and HuggingFace cache
- Builds a model catalog
- Serves models via HTTP
- Gossips model catalog to mesh periodically
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import asyncio
import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about a model available for transfer."""
    model_id: str
    name: str
    type: str  # "vision", "llm", "audio", "embedding"
    format: str  # "pt", "gguf", "tflite", "onnx"
    size_bytes: int
    sha256: str
    version: str
    capabilities: List[str]
    classes: Optional[List[str]] = None
    class_count: Optional[int] = None
    source: str = "huggingface"
    source_ref: str = ""
    metadata: Dict[str, Any] = None
    file_path: str = ""
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization (exclude file_path)."""
        d = asdict(self)
        d.pop('file_path', None)  # Don't expose internal file paths
        return d


class ModelBridge:
    """
    Bridges LlamaFarm models to Atmosphere mesh.
    
    Responsibilities:
    - Scan and catalog models from multiple sources
    - Serve models via HTTP chunked transfer
    - Gossip model catalog to mesh
    """
    
    def __init__(
        self,
        llamafarm_models_dir: Optional[Path] = None,
        huggingface_cache_dir: Optional[Path] = None,
        http_port: int = 14345,
        http_host: str = "0.0.0.0",
        gossip_interval: int = 300  # 5 minutes
    ):
        self.llamafarm_models_dir = llamafarm_models_dir or Path.home() / ".llamafarm" / "models"
        self.huggingface_cache_dir = huggingface_cache_dir or Path.home() / ".cache" / "huggingface" / "hub"
        self.http_port = http_port
        self.http_host = http_host
        self.gossip_interval = gossip_interval
        
        # Catalog: model_id -> ModelInfo
        self.catalog: Dict[str, ModelInfo] = {}
        
        # HTTP server
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        
        # Gossip task
        self.gossip_task: Optional[asyncio.Task] = None
        
        # Atmosphere mesh connection (if available)
        self.mesh_websocket: Optional[aiohttp.ClientWebSocketResponse] = None
        self.mesh_url: Optional[str] = None
    
    async def start(self):
        """Start the model bridge."""
        logger.info("Starting ModelBridge...")
        
        # Scan for models
        await self.scan_models()
        
        # Start HTTP server
        await self.start_http_server()
        
        # Start gossip loop
        self.gossip_task = asyncio.create_task(self.gossip_loop())
        
        logger.info(f"ModelBridge started - {len(self.catalog)} models available")
    
    async def stop(self):
        """Stop the model bridge."""
        logger.info("Stopping ModelBridge...")
        
        if self.gossip_task:
            self.gossip_task.cancel()
            try:
                await self.gossip_task
            except asyncio.CancelledError:
                pass
        
        if self.runner:
            await self.runner.cleanup()
        
        if self.mesh_websocket:
            await self.mesh_websocket.close()
        
        logger.info("ModelBridge stopped")
    
    async def scan_models(self):
        """Scan all model sources and build catalog."""
        logger.info("Scanning for models...")
        
        # Scan LlamaFarm vision models
        await self._scan_llamafarm_vision_models()
        
        # Scan HuggingFace cache
        await self._scan_huggingface_cache()
        
        logger.info(f"Catalog built: {len(self.catalog)} models found")
    
    async def _scan_llamafarm_vision_models(self):
        """
        Scan LlamaFarm's vision models via API.
        Queries both /v1/vision/models and /v1/vision/federation/packages.
        """
        try:
            # Query LlamaFarm vision models API
            async with aiohttp.ClientSession() as session:
                # Get list of models
                async with session.get("http://localhost:11540/v1/vision/models") as resp:
                    if resp.status != 200:
                        logger.warning(f"Failed to query LlamaFarm models: {resp.status}")
                        return
                    
                    data = await resp.json()
                    models = data.get("models", [])
                    
                    logger.info(f"Found {len(models)} vision models from LlamaFarm API")
                    
                    for model in models:
                        model_id = model.get("id")
                        if not model_id:
                            continue
                        
                        # Get model metadata
                        name = model.get("name", model_id)
                        task = model.get("task", "detection")
                        device = model.get("device", "cpu")
                        loaded = model.get("loaded", False)
                        
                        # Try to get package info
                        async with session.get("http://localhost:11540/v1/vision/federation/packages") as pkg_resp:
                            if pkg_resp.status == 200:
                                pkg_data = await pkg_resp.json()
                                packages = pkg_data.get("packages", [])
                                
                                # Find matching package
                                pkg = next((p for p in packages if p.get("model_id") == model_id), None)
                                
                                if pkg:
                                    # Use package info
                                    file_path = pkg.get("path", "")
                                    if file_path and Path(file_path).exists():
                                        size_bytes = Path(file_path).stat().st_size
                                        sha256 = await self._compute_sha256(Path(file_path))
                                    else:
                                        size_bytes = pkg.get("size_bytes", 0)
                                        sha256 = pkg.get("checksum", "unknown")
                                    
                                    classes = pkg.get("class_map", {}).values() if pkg.get("class_map") else None
                                    class_count = len(classes) if classes else pkg.get("num_classes", 0)
                                    version = pkg.get("version", "1.0.0")
                                    metadata = pkg.get("metadata", {})
                                    
                                    model_info = ModelInfo(
                                        model_id=model_id,
                                        name=name,
                                        type="vision",
                                        format="pt",
                                        size_bytes=size_bytes,
                                        sha256=sha256,
                                        version=version,
                                        capabilities=["object_detection"] if task == "detection" else ["classification"],
                                        classes=list(classes) if classes else None,
                                        class_count=class_count,
                                        source="llamafarm_training",
                                        source_ref="local",
                                        metadata=metadata,
                                        file_path=file_path
                                    )
                                    
                                    self.catalog[model_id] = model_info
                                    logger.info(f"Added LlamaFarm vision model: {model_id} ({size_bytes} bytes)")
                
        except Exception as e:
            logger.error(f"Error scanning LlamaFarm vision models: {e}", exc_info=True)
    
    async def _scan_huggingface_cache(self):
        """Scan HuggingFace cache for GGUF and PyTorch models."""
        if not self.huggingface_cache_dir.exists():
            logger.debug(f"HuggingFace cache does not exist: {self.huggingface_cache_dir}")
            return
        
        # Scan for models--{repo} directories
        for model_dir in self.huggingface_cache_dir.glob("models--*"):
            if not model_dir.is_dir():
                continue
            
            # Extract repo name from directory
            # Format: models--{org}--{name}
            dir_name = model_dir.name
            if not dir_name.startswith("models--"):
                continue
            
            parts = dir_name.replace("models--", "").split("--")
            if len(parts) < 2:
                continue
            
            org, name = parts[0], parts[1]
            repo = f"{org}/{name}"
            
            # Look for snapshots
            snapshots_dir = model_dir / "snapshots"
            if not snapshots_dir.exists():
                continue
            
            # Get the most recent snapshot
            snapshots = sorted(snapshots_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            if not snapshots:
                continue
            
            latest_snapshot = snapshots[0]
            
            # Scan for model files
            for model_file in latest_snapshot.iterdir():
                if not model_file.is_file():
                    continue
                
                # Check file extension
                ext = model_file.suffix.lower()
                if ext not in [".gguf", ".pt", ".bin", ".safetensors", ".tflite", ".onnx"]:
                    continue
                
                # Determine model type
                if ext == ".gguf":
                    model_type = "llm"
                    model_format = "gguf"
                    capabilities = ["text_generation", "chat"]
                elif ext in [".pt", ".bin", ".safetensors"]:
                    # Infer from repo name
                    if "yolo" in name.lower():
                        model_type = "vision"
                        capabilities = ["object_detection"]
                    else:
                        model_type = "llm"
                        capabilities = ["text_generation"]
                    model_format = "pt"
                elif ext == ".tflite":
                    model_type = "vision"
                    model_format = "tflite"
                    capabilities = ["object_detection", "classification"]
                elif ext == ".onnx":
                    model_type = "vision"
                    model_format = "onnx"
                    capabilities = ["object_detection", "classification"]
                else:
                    continue
                
                # Compute size and hash
                size_bytes = model_file.stat().st_size
                
                # Skip if too small (likely not a full model)
                if size_bytes < 1_000_000:  # < 1MB
                    continue
                
                sha256 = await self._compute_sha256(model_file)
                
                # Create model ID from repo and filename
                model_id = f"{name}-{model_file.stem}".lower().replace(" ", "-")
                
                model_info = ModelInfo(
                    model_id=model_id,
                    name=f"{org}/{name} - {model_file.stem}",
                    type=model_type,
                    format=model_format,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    version="1.0.0",  # TODO: Extract from model metadata
                    capabilities=capabilities,
                    source="huggingface",
                    source_ref=repo,
                    metadata={
                        "filename": model_file.name,
                        "snapshot": latest_snapshot.name
                    },
                    file_path=str(model_file)
                )
                
                self.catalog[model_id] = model_info
                logger.info(f"Found HuggingFace model: {model_id} ({size_bytes} bytes)")
    
    async def _compute_sha256(self, file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        
        def _hash_file():
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
            return sha256.hexdigest()
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _hash_file)
    
    async def start_http_server(self):
        """Start HTTP server for model downloads."""
        self.app = web.Application()
        
        # Routes
        self.app.router.add_get("/v1/models", self.handle_list_models)
        self.app.router.add_get("/v1/models/{model_id}", self.handle_get_model_info)
        self.app.router.add_get("/v1/models/download/{model_id}", self.handle_download_model)
        self.app.router.add_get("/health", self.handle_health)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, self.http_host, self.http_port)
        await site.start()
        
        logger.info(f"HTTP server started on {self.http_host}:{self.http_port}")
    
    async def handle_list_models(self, request: web.Request) -> web.Response:
        """List all available models."""
        models = [model.to_dict() for model in self.catalog.values()]
        return web.json_response({"models": models})
    
    async def handle_get_model_info(self, request: web.Request) -> web.Response:
        """Get info for a specific model."""
        model_id = request.match_info["model_id"]
        model = self.catalog.get(model_id)
        
        if not model:
            return web.json_response({"error": "Model not found"}, status=404)
        
        return web.json_response(model.to_dict())
    
    async def handle_download_model(self, request: web.Request) -> web.StreamResponse:
        """
        Download a model with support for HTTP Range requests.
        """
        model_id = request.match_info["model_id"]
        model = self.catalog.get(model_id)
        
        if not model:
            return web.json_response({"error": "Model not found"}, status=404)
        
        file_path = Path(model.file_path)
        if not file_path.exists():
            return web.json_response({"error": "Model file not found"}, status=404)
        
        file_size = file_path.stat().st_size
        
        # Parse Range header
        range_header = request.headers.get("Range")
        start_byte = 0
        end_byte = file_size - 1
        
        if range_header:
            # Format: bytes=start-end
            range_match = range_header.replace("bytes=", "").split("-")
            if len(range_match) >= 1 and range_match[0]:
                start_byte = int(range_match[0])
            if len(range_match) >= 2 and range_match[1]:
                end_byte = int(range_match[1])
        
        # Validate range
        if start_byte >= file_size:
            return web.Response(status=416)  # Range Not Satisfiable
        
        content_length = end_byte - start_byte + 1
        
        # Prepare response
        response = web.StreamResponse(
            status=206 if range_header else 200,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(content_length),
                "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Disposition": f'attachment; filename="{model.model_id}.{model.format}"'
            }
        )
        
        await response.prepare(request)
        
        # Stream file
        chunk_size = 65536  # 64KB chunks
        bytes_sent = 0
        
        with open(file_path, "rb") as f:
            f.seek(start_byte)
            
            while bytes_sent < content_length:
                chunk = f.read(min(chunk_size, content_length - bytes_sent))
                if not chunk:
                    break
                
                await response.write(chunk)
                bytes_sent += len(chunk)
        
        await response.write_eof()
        
        logger.info(f"Served model {model_id}: {bytes_sent} bytes (range: {start_byte}-{end_byte})")
        
        return response
    
    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "ok",
            "models_available": len(self.catalog),
            "http_port": self.http_port
        })
    
    async def gossip_loop(self):
        """Periodically gossip model catalog to mesh."""
        while True:
            try:
                await asyncio.sleep(self.gossip_interval)
                await self.gossip_catalog()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in gossip loop: {e}", exc_info=True)
    
    async def gossip_catalog(self):
        """Send model catalog to mesh."""
        if not self.mesh_websocket or self.mesh_websocket.closed:
            logger.debug("No mesh connection - skipping gossip")
            return
        
        # Build catalog message
        catalog_msg = {
            "type": "model_catalog",
            "node_id": os.environ.get("ATMOSPHERE_NODE_ID", "llamafarm-unknown"),
            "node_name": os.environ.get("ATMOSPHERE_NODE_NAME", "LlamaFarm"),
            "timestamp": int(datetime.now().timestamp() * 1000),
            "models": [model.to_dict() for model in self.catalog.values()],
            "transfer_endpoints": {
                "http": f"http://{self._get_local_ip()}:{self.http_port}",
                "websocket": True
            },
            "ttl_seconds": 300
        }
        
        try:
            await self.mesh_websocket.send_json(catalog_msg)
            logger.info(f"Gossiped catalog with {len(self.catalog)} models to mesh")
        except Exception as e:
            logger.error(f"Failed to gossip catalog: {e}")
    
    def _get_local_ip(self) -> str:
        """Get local IP address for HTTP endpoint advertisement."""
        import socket
        try:
            # Create a socket to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    async def connect_to_mesh(self, mesh_url: str):
        """Connect to Atmosphere mesh WebSocket."""
        self.mesh_url = mesh_url
        
        try:
            session = aiohttp.ClientSession()
            self.mesh_websocket = await session.ws_connect(mesh_url)
            logger.info(f"Connected to Atmosphere mesh: {mesh_url}")
            
            # Send initial catalog
            await self.gossip_catalog()
            
        except Exception as e:
            logger.error(f"Failed to connect to mesh: {e}")
    
    def get_stats(self) -> dict:
        """Get statistics about the model bridge."""
        return {
            "total_models": len(self.catalog),
            "vision_models": sum(1 for m in self.catalog.values() if m.type == "vision"),
            "llm_models": sum(1 for m in self.catalog.values() if m.type == "llm"),
            "audio_models": sum(1 for m in self.catalog.values() if m.type == "audio"),
            "total_size_gb": sum(m.size_bytes for m in self.catalog.values()) / 1_000_000_000,
            "http_port": self.http_port,
            "mesh_connected": self.mesh_websocket is not None and not self.mesh_websocket.closed
        }


async def main():
    """Main entry point for standalone testing."""
    logging.basicConfig(level=logging.INFO)
    
    bridge = ModelBridge()
    await bridge.start()
    
    # Print stats
    stats = bridge.get_stats()
    logger.info(f"ModelBridge stats: {json.dumps(stats, indent=2)}")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await bridge.stop()


if __name__ == "__main__":
    asyncio.run(main())
