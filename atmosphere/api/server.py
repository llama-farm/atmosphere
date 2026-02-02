"""
FastAPI server for Atmosphere.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from ..config import Config, get_config
from ..mesh.node import Node, NodeIdentity, MeshIdentity
from ..router.semantic import SemanticRouter
from ..router.executor import Executor
from ..mesh.gossip import GossipProtocol
from ..mesh.discovery import MeshDiscovery

logger = logging.getLogger(__name__)

# Global server instance
_server: Optional["AtmosphereServer"] = None


def get_server() -> Optional["AtmosphereServer"]:
    """Get the global server instance."""
    return _server


class AtmosphereServer:
    """
    Atmosphere API server.
    
    Manages all components:
    - Node identity
    - Mesh membership
    - Semantic router
    - Execution engine
    - Gossip protocol
    - mDNS discovery
    """
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        
        # Components (initialized in start())
        self.node: Optional[Node] = None
        self.router: Optional[SemanticRouter] = None
        self.executor: Optional[Executor] = None
        self.gossip: Optional[GossipProtocol] = None
        self.discovery: Optional[MeshDiscovery] = None
        
        self._running = False
    
    async def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing Atmosphere server...")
        
        # Load or create node identity
        if self.config.identity_path.exists():
            identity = NodeIdentity.load(self.config.identity_path)
            logger.info(f"Loaded identity: {identity.name} ({identity.node_id})")
        else:
            raise RuntimeError(
                "Node not initialized. Run 'atmosphere init' first."
            )
        
        # Load mesh if configured
        mesh = None
        if self.config.mesh_path.exists():
            mesh = MeshIdentity.load(self.config.mesh_path)
            logger.info(f"Loaded mesh: {mesh.name} ({mesh.mesh_id})")
        
        self.node = Node(identity=identity, mesh=mesh)
        
        # Initialize router
        self.router = SemanticRouter(node_id=self.node.node_id)
        await self.router.initialize()
        
        # Register capabilities based on available backends
        await self._register_capabilities()
        
        # Initialize executor
        self.executor = Executor(
            router=self.router,
            node_id=self.node.node_id,
            port=self.config.server.port
        )
        await self.executor.initialize()
        
        # Initialize discovery
        if self.config.mdns_enabled:
            self.discovery = MeshDiscovery(
                node_id=self.node.node_id,
                port=self.config.server.port,
                name=self.node.name,
                mesh_id=mesh.mesh_id if mesh else None,
                capabilities=list(self.router.local_capabilities.keys())
            )
        
        logger.info("Atmosphere server initialized")
    
    async def _register_capabilities(self) -> None:
        """Register capabilities based on available backends."""
        from ..discovery.scanner import scan_backends
        
        backends = await scan_backends()
        
        for backend in backends:
            for capability in backend.capabilities:
                desc = self._get_capability_description(capability)
                await self.router.register_capability(
                    label=capability,
                    description=desc,
                    handler=backend.type.value,
                    models=[m.name for m in backend.models]
                )
    
    def _get_capability_description(self, capability: str) -> str:
        """Get description for capability embedding."""
        descriptions = {
            "llm": "Language model for text generation, summarization, analysis, and reasoning",
            "embeddings": "Text embeddings for semantic search and similarity matching",
            "vision": "Image and video analysis, object detection, scene understanding",
            "audio": "Speech-to-text transcription, text-to-speech synthesis",
            "code": "Code generation, completion, and execution",
            "rag": "Retrieval-augmented generation for document Q&A",
            "agents": "Autonomous agents for complex multi-step tasks",
        }
        return descriptions.get(capability, f"{capability} capability")
    
    async def start(self) -> None:
        """Start the server and all services."""
        await self.initialize()
        
        # Start mDNS discovery
        if self.discovery:
            await self.discovery.start()
        
        # TODO: Start gossip protocol
        
        self._running = True
        logger.info(
            f"Atmosphere server running at http://{self.config.server.host}:{self.config.server.port}"
        )
    
    async def stop(self) -> None:
        """Stop the server and all services."""
        logger.info("Stopping Atmosphere server...")
        
        self._running = False
        
        if self.discovery:
            await self.discovery.stop()
        
        if self.gossip:
            await self.gossip.stop()
        
        if self.executor:
            await self.executor.close()
        
        if self.router:
            await self.router.close()
        
        logger.info("Atmosphere server stopped")
    
    def status(self) -> dict:
        """Get server status."""
        return {
            "running": self._running,
            "node_id": self.node.node_id if self.node else None,
            "node_name": self.node.name if self.node else None,
            "mesh_id": self.node.mesh.mesh_id if self.node and self.node.mesh else None,
            "mesh_name": self.node.mesh.name if self.node and self.node.mesh else None,
            "capabilities": list(self.router.local_capabilities.keys()) if self.router else [],
            "peers": len(self.discovery.peers) if self.discovery else 0,
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _server
    
    # Startup
    config = get_config()
    _server = AtmosphereServer(config)
    
    try:
        await _server.start()
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise
    
    # Initialize router from LlamaFarm API (async discovery)
    try:
        from ..router.fast_router import get_fast_router
        router = get_fast_router()
        await router.initialize_from_api()
        logger.info("Router initialized from LlamaFarm API")
    except Exception as e:
        logger.warning(f"API discovery failed, using file-based: {e}")
        # Fall back to sync file-based loading
        from ..router.fast_router import get_fast_router
        router = get_fast_router()
        router.initialize()
    
    yield
    
    # Shutdown
    await _server.stop()
    _server = None


def create_app(config: Optional[Config] = None) -> FastAPI:
    """Create the FastAPI application."""
    from .routes import router
    from ..router.openai_compat import openai_router
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from pathlib import Path
    
    if config:
        from ..config import set_config
        set_config(config)
    
    app = FastAPI(
        title="Atmosphere",
        description="Semantic mesh routing for AI capabilities",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include internal API routes
    app.include_router(router, prefix="/api")
    
    # Include OpenAI-compatible routes at /v1
    # These provide: /v1/chat/completions, /v1/completions, /v1/embeddings, /v1/models
    app.include_router(openai_router)
    
    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok"}
    
    # API status
    @app.get("/api")
    async def api_status():
        server = get_server()
        if server:
            return {
                "name": "Atmosphere",
                "version": "1.0.0",
                **server.status()
            }
        return {"name": "Atmosphere", "version": "1.0.0", "status": "starting"}
    
    # Serve UI if built
    ui_dist = Path(__file__).parent.parent.parent / "ui" / "dist"
    if ui_dist.exists():
        app.mount("/assets", StaticFiles(directory=ui_dist / "assets"), name="assets")
        
        @app.get("/")
        async def serve_ui():
            return FileResponse(ui_dist / "index.html")
    else:
        @app.get("/")
        async def root():
            return {
                "name": "Atmosphere",
                "version": "1.0.0",
                "message": "UI not built. Run 'cd ui && npm run build' to build the UI."
            }
    
    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 11451,  # Atmosphere API port (NOT Ollama's 11434)
    reload: bool = False
):
    """Run the server with uvicorn."""
    app = create_app()
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
