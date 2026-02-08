"""
FastAPI server for Atmosphere.
"""

import asyncio
import logging
import platform
import time
from contextlib import asynccontextmanager
from typing import Optional, Any, Dict, Union

import aiohttp
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from ..config import Config, get_config
from ..mesh.node import Node, NodeIdentity, MeshIdentity
from ..router.semantic import SemanticRouter
from ..router.mesh_router import MeshRouter
from ..router.executor import Executor
from ..mesh.gossip import GossipProtocol
from ..mesh.discovery import MeshDiscovery
from ..mesh.routing import get_mesh_persistence, SavedMesh
from ..transport.relay import RelayConnection as RelayClient
from ..core.gossip import GossipManager
from ..integration.llamafarm import discover_llamafarm_capabilities

logger = logging.getLogger(__name__)

# WebSocket connection manager for broadcasting to local clients
class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected WebSocket clients."""
        for connection in self.active_connections[:]:  # Copy list to avoid modification during iteration
            try:
                await connection.send_json(message)
            except Exception:
                self.active_connections.remove(connection)

# Global manager instance (shared with routes.py)
manager = ConnectionManager()

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
        logger.debug("AtmosphereServer created")
        self.config = config or get_config()
        
        # Components (initialized in start())
        self.node: Optional[Node] = None
        self.router: Optional[SemanticRouter] = None
        self.mesh_router: Optional[MeshRouter] = None  # Mesh-aware router
        self.executor: Optional[Executor] = None
        self.gossip: Optional[GossipManager] = None
        self.discovery: Optional[MeshDiscovery] = None
        self.relay_client: Optional[RelayClient] = None
        
        # BLE transport and pairing (Mac only)
        self.ble_transport: Optional[Any] = None
        self.ble_pairing_manager: Optional[Any] = None
        
        self._running = False
        self._relay_task: Optional[asyncio.Task] = None
        self._relay_peers: dict = {}  # node_id -> peer info from relay
    
    async def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing Atmosphere server...")
        
        # Load mesh persistence (saved meshes across restarts)
        persistence = get_mesh_persistence()
        logger.info(f"Loaded {len(persistence.list_meshes())} saved meshes")
        
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
            
            # Auto-save to persistence if not already saved
            if not persistence.get_mesh(mesh.mesh_id):
                persistence.add_mesh(SavedMesh(
                    mesh_id=mesh.mesh_id,
                    mesh_name=mesh.name,
                    peers=[],
                    endpoints=[],
                    created_at=mesh.created_at if hasattr(mesh, 'created_at') else time.time(),
                    last_connected=time.time(),
                    is_founder=hasattr(mesh, '_master_keypair') and mesh._master_keypair is not None,
                ))
                logger.info(f"Auto-saved mesh {mesh.name} to persistence")
            
            # Set as active mesh
            persistence.set_active_mesh(mesh.mesh_id)
        
        self.node = Node(identity=identity, mesh=mesh)
        
        # Initialize router
        self.router = SemanticRouter(node_id=self.node.node_id)
        await self.router.initialize()
        
        # Initialize mesh-aware router (uses gossip data, latency, cost)
        self.mesh_router = MeshRouter(
            semantic_router=self.router,
            peer_reachability_fn=self._check_peer_reachable,
            model_info_fn=self._get_model_info,
        )
        
        # Register capabilities based on available backends
        await self._register_capabilities()
        
        # Initialize executor
        self.executor = Executor(
            router=self.router,
            node_id=self.node.node_id,
            port=self.config.server.port
        )
        await self.executor.initialize()
        
        # Register LlamaFarm project handler
        self.executor.register_handler("llamafarm_project", self._handle_llamafarm_project)
        
        # Initialize discovery
        if self.config.mdns_enabled:
            self.discovery = MeshDiscovery(
                node_id=self.node.node_id,
                port=self.config.server.port,
                name=self.node.name,
                mesh_id=mesh.mesh_id if mesh else None,
                capabilities=list(self.router.local_capability_ids)
            )
        
        logger.info("Atmosphere server initialized")
    
    async def _handle_llamafarm_project(self, intent: str, **kwargs) -> dict:
        """Handle execution of LlamaFarm project capabilities."""
        import aiohttp
        import base64
        
        # Get the capability that was matched by SemanticRouter
        capability_label = kwargs.get('_capability_label', '')
        
        # Always use FastProjectRouter for better semantic routing
        # This ensures we route to the best project even if SemanticRouter matched a different one
        if hasattr(self, '_fast_router') and self._fast_router:
            messages = kwargs.get('messages', [{"role": "user", "content": intent}])
            route_result = self._fast_router.route('auto', messages)
            if route_result.project and route_result.score > 0.1:
                namespace = route_result.project.namespace
                project_name = route_result.project.name
                logger.info(f"FastProjectRouter routed '{intent[:50]}...' to {namespace}/{project_name} (score={route_result.score:.3f}, tier={route_result.tier.value})")
            else:
                # Fallback to parsing capability label
                parts = capability_label.split('/')
                if len(parts) >= 3:
                    namespace = parts[1]
                    project_name = parts[2]
                else:
                    namespace = "discoverable"
                    project_name = capability_label.replace("llamafarm/", "") or "llama-expert-14"
        else:
            # No FastProjectRouter, parse from capability label
            parts = capability_label.split('/')
            if len(parts) >= 3:
                namespace = parts[1]
                project_name = parts[2]
            else:
                namespace = "discoverable"
                project_name = capability_label.replace("llamafarm/", "") or "llama-expert-14"
        
        try:
            # Check if this is a "capabilities" request (boil down config)
            if intent.strip().lower() == "get_capabilities":
                # Fetch project config and boil it down
                async with aiohttp.ClientSession() as session:
                    url = f"http://localhost:14345/v1/projects/{namespace}/{project_name}"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            project_data = await resp.json()
                            # Boil down: extract system prompt and tools
                            system_prompt = project_data.get("config", {}).get("system_prompt", "")
                            tools = project_data.get("config", {}).get("tools", [])
                            return {
                                "id": f"llamafarm/{namespace}/{project_name}",
                                "description": system_prompt[:500],
                                "tools": [t.get("name") for t in tools if isinstance(t, dict)],
                                "type": "llamafarm_project"
                            }

            # Use the project's chat endpoint: /v1/projects/{namespace}/{project}/chat/completions
            messages = kwargs.get('messages', [{"role": "user", "content": intent}])
            if isinstance(messages, str):
                messages = [{"role": "user", "content": messages}]
            
            payload = {
                "messages": messages,
                "temperature": kwargs.get("temperature", 0.7),
                "rag": kwargs.get("rag", False),  # Disable RAG by default to avoid blocking on Celery
            }
            if kwargs.get("max_tokens"):
                payload["max_tokens"] = kwargs["max_tokens"]
            
            async with aiohttp.ClientSession() as session:
                url = f"http://localhost:14345/v1/projects/{namespace}/{project_name}/chat/completions"
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        raise RuntimeError(f"LlamaFarm project chat failed: {error}")
                    
                    result = await resp.json()
            
            return {
                "response": result["choices"][0]["message"]["content"],
                "project": project_name,
                "namespace": namespace,
                "usage": result.get("usage", {})
            }
            
        except Exception as e:
            logger.error(f"LlamaFarm project execution failed: {e}")
            raise
    
    async def _register_capabilities(self) -> None:
        """Register capabilities based on available backends and LlamaFarm projects."""
        from ..discovery.scanner import scan_backends
        from ..router.fast_router import FastProjectRouter, LLAMAFARM_BASE
        
        # Register generic backend capabilities
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
        
        # Register LlamaFarm projects using FastProjectRouter for better semantic matching
        # FastProjectRouter scans multiple namespaces and has pre-computed embeddings
        try:
            logger.debug("Creating FastProjectRouter")
            fast_router = FastProjectRouter()
            logger.debug(f"Initializing from API: {LLAMAFARM_BASE}")
            await fast_router.initialize_from_api(LLAMAFARM_BASE)
            logger.debug(f"Loaded {len(fast_router.projects)} projects")
            
            # Store reference for routing use
            self._fast_router = fast_router
            
            registered_count = 0
            for model_path, project in fast_router.projects.items():
                # Skip test namespaces
                if project.namespace.startswith("test"):
                    continue
                
                # Build description from project metadata
                description = project.description
                if not description:
                    description = f"LlamaFarm project: {project.name} ({project.domain})"
                if project.topics:
                    description += f" Topics: {', '.join(project.topics)}"
                
                # Register as capability with semantic-rich description
                await self.router.register_capability(
                    label=f"llamafarm/{project.namespace}/{project.name}",
                    description=description,
                    handler="llamafarm_project",
                    models=project.models
                )
                registered_count += 1
            
            logger.info(f"Registered {registered_count} LlamaFarm projects as capabilities (using FastProjectRouter)")
            
        except Exception as e:
            logger.warning(f"Failed to register LlamaFarm projects: {e}")
    
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
    
    def _check_peer_reachable(self, peer_id: str) -> bool:
        """Check if a peer is currently reachable via relay."""
        # Check relay peers
        if peer_id in self._relay_peers:
            return True
        # Check mDNS discovery
        if self.discovery:
            for peer in self.discovery.peers:
                if peer.node_id == peer_id:
                    return True
        return False
    
    def _get_model_info(self, capability_id: str) -> dict:
        """
        Get model info for a capability (from LlamaFarm config).
        
        Returns info like:
        - has_rag: bool (uses RAG/retrieval)
        - specializations: list (e.g., ["llama", "camelid"])
        - size: str (tiny, small, medium, large)
        - context_length: int
        """
        # Parse capability_id to extract project info
        # Format: node_id:llamafarm/namespace/project
        parts = capability_id.split(":")
        if len(parts) < 2:
            return {}
        
        cap_path = parts[1]
        if not cap_path.startswith("llamafarm/"):
            return {}
        
        # Try to get project config from LlamaFarm
        try:
            import httpx
            llamafarm_url = getattr(self.config, 'llamafarm_url', 'http://localhost:14345')
            # Extract namespace/project from capability path
            path_parts = cap_path.replace("llamafarm/", "").split("/")
            if len(path_parts) >= 2:
                namespace, project = path_parts[0], path_parts[1]
                resp = httpx.get(f"{llamafarm_url}/v1/projects/{namespace}/{project}", timeout=2.0)
                if resp.status_code == 200:
                    proj = resp.json().get("project", {}).get("config", {})
                    
                    # Extract model info from project config
                    runtime = proj.get("runtime", {})
                    models = runtime.get("models", [])
                    default_model = next((m for m in models if m.get("default")), models[0] if models else {})
                    
                    # Check for RAG
                    has_rag = bool(proj.get("rag") or proj.get("retrieval"))
                    
                    # Extract specializations from description/topics
                    specializations = []
                    desc = proj.get("description", "")
                    topics = proj.get("topics", [])
                    if topics:
                        specializations.extend(topics)
                    
                    # Estimate model size from model name
                    model_name = default_model.get("model", "").lower()
                    size = "medium"
                    if any(s in model_name for s in ["1b", "1.5b", "tiny", "mini"]):
                        size = "tiny"
                    elif any(s in model_name for s in ["3b", "7b", "small"]):
                        size = "small"
                    elif any(s in model_name for s in ["13b", "14b", "20b"]):
                        size = "medium"
                    elif any(s in model_name for s in ["30b", "34b", "70b", "large"]):
                        size = "large"
                    
                    return {
                        "has_rag": has_rag,
                        "specializations": specializations,
                        "size": size,
                        "model": default_model.get("model", ""),
                        "context_length": default_model.get("context_length", 4096),
                    }
        except Exception as e:
            logger.debug(f"Could not get model info for {capability_id}: {e}")
        
        return {}
    
    async def start(self) -> None:
        """Start the server and all services."""
        logger.debug("Starting AtmosphereServer")
        await self.initialize()
        logger.debug("Initialization complete")
        
        # Start mDNS discovery
        if self.discovery:
            await self.discovery.start()
        
        # Connect to relay server for NAT traversal
        await self._connect_to_relay()
        
        # Start gossip protocol for capability propagation
        await self._start_gossip()
        
        # Start BLE transport and pairing (Mac/iOS only)
        await self._start_ble()
        
        self._running = True
        logger.info(
            f"Atmosphere server running at http://{self.config.server.host}:{self.config.server.port}"
        )
    
    async def _send_to_relay(self, msg: Dict[str, Any]) -> None:
        """Send message to relay (used by GossipManager)."""
        import json
        print(f"[SEND_TO_RELAY] Called with msg type: {msg.get('type')}", flush=True)
        if self.relay_client and self.relay_client.connected and self.relay_client.ws:
            print(f"[SEND_TO_RELAY] Relay connected, sending: {json.dumps(msg)[:200]}", flush=True)
            await self.relay_client.ws.send(json.dumps(msg))
            print(f"[SEND_TO_RELAY] Sent successfully", flush=True)
        else:
            print(f"[SEND_TO_RELAY] Relay not ready: connected={self.relay_client.connected if self.relay_client else None}, ws={bool(self.relay_client.ws) if self.relay_client else None}", flush=True)

    async def _start_gossip(self) -> None:
        """Start the gossip protocol for capability propagation."""
        print(f"[GOSSIP] _start_gossip called, node={self.node}, router={self.router}", flush=True)
        if not self.node or not self.router:
            print("[GOSSIP] Skipping gossip - no node or router", flush=True)
            logger.debug("No node/router, skipping gossip")
            return
        
        print(f"[GOSSIP] Creating GossipManager for node {self.node.node_id}", flush=True)
        # Create gossip manager
        self.gossip = GossipManager(
            node_id=self.node.node_id,
            gradient_table=self.router.gradient_table,
            send_to_relay=self._send_to_relay
        )
        print("[GOSSIP] GossipManager created", flush=True)
        
        # Discover and register local capabilities from LlamaFarm
        print("[GOSSIP] Discovering LlamaFarm capabilities...", flush=True)
        local_capabilities = await discover_llamafarm_capabilities(
            node_id=self.node.node_id,
            node_name=self.node.name,
            llamafarm_url=getattr(self.config, 'llamafarm_url', 'http://localhost:14345'),
        )
        print(f"[GOSSIP] Discovered {len(local_capabilities)} capabilities", flush=True)
        
        # Fallback to Ollama if LlamaFarm has no capabilities
        if not local_capabilities:
            print("[GOSSIP] No LlamaFarm capabilities, checking Ollama...", flush=True)
            try:
                import httpx
                resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    if models:
                        # Create a generic Ollama capability
                        from ..core.capability import CapabilityAnnouncement, CapabilityType, ModelTier
                        ollama_cap = CapabilityAnnouncement(
                            node_id=self.node.node_id,
                            node_name=self.node.name,
                            capability_id=f"{self.node.node_id}:ollama/chat:default",
                            project_path="ollama/chat",
                            model_alias="default",
                            model_actual=models[0].get("name", "llama3.2"),
                            model_family="llama",
                            model_params_b=3.0,
                            model_quantization="Q4_K_M",
                            model_tier=ModelTier.SMALL,
                            capability_type=CapabilityType.LLM_CHAT,
                            label="Ollama Chat",
                            description="Local Ollama LLM for chat and inference",
                            keywords=["llm", "chat", "ai", "assistant", "ollama"],
                            has_streaming=True,
                        )
                        local_capabilities.append(ollama_cap)
                        print(f"[GOSSIP] Added Ollama fallback capability: {ollama_cap.capability_id}", flush=True)
            except Exception as e:
                print(f"[GOSSIP] Ollama fallback failed: {e}", flush=True)
        
        for capability in local_capabilities:
            print(f"[GOSSIP] Adding capability: {capability.capability_id}", flush=True)
            self.gossip.add_local_capability(capability)
        
        # Start gossip loop
        print("[GOSSIP] Starting gossip broadcast loop...", flush=True)
        await self.gossip.start()
        print(f"[GOSSIP] ✅ Gossip started with {len(local_capabilities)} local capabilities", flush=True)
        logger.info(f"Gossip protocol started with {len(local_capabilities)} local capabilities")
    
    async def _start_ble(self) -> None:
        """
        Start BLE transport and proximity pairing (Mac/iOS only).
        
        Enables:
        - BLE mesh discovery and messaging
        - Proximity pairing with tap-to-pair UX
        - Automatic credential exchange
        """
        print(f"[BLE] _start_ble called, platform={platform.system()}", flush=True)
        # Only start BLE on supported platforms
        if platform.system() not in ['Darwin', 'iOS']:
            print("[BLE] Not on Darwin/iOS, skipping", flush=True)
            return
        
        if not self.node:
            print("[BLE] No node configured, skipping", flush=True)
            return
        
        print(f"[BLE] Starting BLE for node: {self.node.name}", flush=True)
        try:
            from ..transport.ble_mac import BleTransport
            print("[BLE] Imported BleTransport", flush=True)
            from ..transport.ble_pairing import BlePairingManager, PairingCredentials, integrate_pairing_with_transport
            
            print("[BLE] Creating BleTransport...", flush=True)
            
            # Create BLE transport
            self.ble_transport = BleTransport(
                node_name=self.node.name,
                capabilities=list(self.router.local_capability_ids) if self.router else []
            )
            
            # Set message handler
            def on_ble_message(msg):
                logger.info(f"BLE message from {msg.source_id}: {len(msg.payload)} bytes")
                # Handle BLE mesh messages (gossip, chat, etc.)
                asyncio.create_task(self._handle_resilient_message(msg.source_id, msg.payload))
            
            def on_ble_peer_discovered(peer_info):
                logger.info(f"BLE peer discovered: {peer_info.name} ({peer_info.node_id})")
                # Broadcast to local WebSocket clients
                asyncio.create_task(manager.broadcast({
                    "type": "ble_peer_discovered",
                    "peer_id": peer_info.node_id,
                    "name": peer_info.name,
                    "rssi": peer_info.rssi,
                    "platform": peer_info.platform,
                }))
                # Register BLE peer in mesh
            
            self.ble_transport.on_message = on_ble_message
            self.ble_transport.on_peer_discovered = on_ble_peer_discovered
            
            # Build local credentials for pairing
            local_creds = PairingCredentials(
                node_id=self.node.node_id,
                node_name=self.node.name,
                mesh_id=self.node.mesh.mesh_id if self.node.mesh else "",
                relay_token="",  # TODO: Get from relay client if connected
                relay_url=getattr(self.config, 'relay_url', ""),
                local_endpoints=[{
                    "ip": self.config.server.host,
                    "port": self.config.server.port
                }],
                capabilities=list(self.router.local_capability_ids) if self.router else []
            )
            
            # Create pairing manager
            self.ble_pairing_manager = BlePairingManager(
                local_credentials=local_creds,
                on_code_display=self._on_pairing_code_display,
                on_pairing_complete=self._on_pairing_complete,
                on_pairing_failed=self._on_pairing_failed
            )
            
            # Integrate pairing with transport
            integrate_pairing_with_transport(self.ble_transport, self.ble_pairing_manager)
            
            # Start transport and pairing manager
            await self.ble_transport.start()
            self.ble_pairing_manager.start()
            
            logger.info(f"✅ BLE transport started: {self.node.name} ({self.ble_transport.node_id})")
            
        except ImportError as e:
            print(f"[BLE] ImportError: {e}", flush=True)
        except Exception as e:
            print(f"[BLE] Exception: {e}", flush=True)
            import traceback
            traceback.print_exc()
    
    async def _on_pairing_code_display(self, code: str, peer_name: str):
        """Handle pairing code display (send to UI)."""
        logger.info(f"🔐 Pairing code: {code} (peer: {peer_name})")
        # Broadcast to WebSocket clients
        await manager.broadcast({
            "event_type": "BLE_PAIRING_CODE",
            "code": code,
            "peer_name": peer_name
        })
    
    async def _on_pairing_complete(self, peer_credentials):
        """Handle successful pairing."""
        logger.info(f"✅ Pairing complete with {peer_credentials.node_name}")
        
        # Broadcast to UI
        await manager.broadcast({
            "event_type": "BLE_PAIRING_COMPLETE",
            "peer_id": peer_credentials.node_id,
            "peer_name": peer_credentials.node_name
        })
    
    async def _on_pairing_failed(self, peer_id: str, reason: str):
        """Handle pairing failure."""
        logger.warning(f"❌ Pairing failed with {peer_id}: {reason}")
        await manager.broadcast({
            "event_type": "BLE_PAIRING_FAILED",
            "peer_id": peer_id,
            "reason": reason
        })
    
    async def _connect_to_relay(self) -> None:
        """Connect to relay server for NAT traversal and remote mesh access."""
        relay_url = getattr(self.config, 'relay_url', None)
        print(f"[RELAY-DEBUG] _connect_to_relay called, relay_url={relay_url}", flush=True)
        
        if not relay_url:
            logger.debug("No relay URL configured, skipping relay connection")
            print("[RELAY-DEBUG] No relay URL, skipping", flush=True)
            return
        
        if not self.node or not self.node.mesh:
            logger.debug("No mesh configured, skipping relay connection")
            return
            
        # Avoid double connection
        if self.relay_client and self.relay_client.ws and not self.relay_client.ws.closed:
            logger.debug("Already connected to relay, skipping")
            return
        
        mesh = self.node.mesh
        mesh_id = mesh.mesh_id
        
        try:
            # Check if we're the founder (can issue certificates)
            is_founder = mesh.can_issue_certificates()
            mesh_public_key = None
            founder_proof = None
            node_public_key = None
            
            if is_founder:
                # Get mesh public key (already base64 encoded in MeshIdentity)
                mesh_public_key = mesh.master_public_key
                
                # Create founder proof: sign mesh_id with our node identity
                # The identity.sign() method returns base64 already
                founder_proof = self.node.identity.sign(mesh_id.encode())
                
                # Get our node public key (identity.public_key is already base64)
                node_public_key = self.node.identity.public_key
                
                print(f"[RELAY] 🔑 Founder registration: mesh_id={mesh_id}, mesh_key={mesh_public_key[:20]}...", flush=True)
                logger.info(f"Founder connecting to relay with mesh key")
            
            # Create relay client with founder credentials if applicable
            self.relay_client = RelayClient(
                node_id=self.node.node_id,
                mesh_id=mesh_id,
                token="",  # Token handled by mesh registration
                relay_url=relay_url,
                on_message=self._on_relay_message,
                # Founder fields
                is_founder=is_founder,
                mesh_public_key=mesh_public_key,
                founder_proof=founder_proof,
                node_public_key=node_public_key,
                mesh_name=mesh.name,
            )
            
            # Start connection in background (non-blocking)
            await self.relay_client.connect()
            logger.info(f"Relay connection started: {relay_url}/relay/{mesh_id} (founder={is_founder})")
            
            # Note: Registration and message handling will happen in the RelayConnection's
            # callback when the connection is established
                
        except Exception as e:
            logger.error(f"Relay connection error: {e}")
    
    async def _on_relay_message(self, msg) -> None:
        """Handle incoming message from RelayConnection."""
        try:
            # msg is a RelayMessage object, payload is a dict
            await self._process_relay_message(msg.payload)
        except Exception as e:
            logger.error(f"Error handling relay message: {e}", exc_info=True)

    async def _process_relay_message(self, data: Union[str, Dict[str, Any]]) -> None:
        """Process a message received from relay."""
        import json
        try:
            if isinstance(data, str):
                msg = json.loads(data)
            else:
                msg = data
            msg_type = msg.get("type", "")
            
            if msg_type == "joined":
                # We successfully joined the mesh via relay
                mesh_name = msg.get("mesh", "unknown")
                node_count = msg.get("node_count", 0)
                logger.info(f"✓ Joined mesh '{mesh_name}' via relay ({node_count} nodes)")
                print(f"[RELAY] Joined mesh! Triggering gossip broadcast...", flush=True)
                
                # Trigger immediate gossip broadcast now that relay is ready
                if self.gossip and self.gossip._local_capabilities:
                    asyncio.create_task(self.gossip.broadcast_capabilities())
                    print(f"[RELAY] Gossip broadcast triggered ({len(self.gossip._local_capabilities)} capabilities)", flush=True)
                
            elif msg_type == "chat_request" or msg_type == "llm_request" or msg_type == "inference_request":
                # Forward to local LLM (handle both message types)
                response = await self._handle_relay_chat(msg)
                if self.relay_client:
                    # Send response back via broadcast
                    response["type"] = "llm_response"
                    await self._send_to_relay({
                        "type": "broadcast",
                        "payload": response
                    })
                    logger.info(f"Sent LLM response back via relay to {msg.get('from', 'unknown')}")
            elif msg_type == "route_request":
                # Handle routing request
                response = await self._handle_relay_route(msg)
                if self.relay_client:
                    response["type"] = "route_response"
                    await self._send_to_relay({
                        "type": "broadcast", 
                        "payload": response
                    })
            elif msg_type == "peer_joined":
                # A new peer joined the mesh
                node_id = msg.get("node_id", "unknown")
                name = msg.get("name", node_id[:8])
                capabilities = msg.get("capabilities", [])
                host = msg.get("host")  # LAN address if available
                port = msg.get("port", 11451)
                device_type = msg.get("device_type", "unknown")
                model = msg.get("model", "")
                print(f"[PEER] New peer joined: {name} ({node_id})", flush=True)
                logger.info(f"Peer joined via relay: {name} ({node_id}) with {len(capabilities)} capabilities")
                
                # Re-broadcast our capabilities so the new peer sees them
                if self.gossip and self.gossip._local_capabilities:
                    print(f"[PEER] Re-broadcasting capabilities to new peer", flush=True)
                    asyncio.create_task(self.gossip.broadcast_capabilities())
                
                # Register device in persistent registry
                from ..registry.devices import get_device_registry
                registry = get_device_registry()
                registry.register_device(
                    device_id=node_id,
                    name=name,
                    device_type=device_type,
                    capabilities=capabilities,
                    endpoint="relay" if not host else f"ws://{host}:{port}",
                    model=model
                )
                
                # Build peer info
                peer_info = {
                    "node_id": node_id,
                    "name": name,
                    "capabilities": capabilities,
                    "is_founder": msg.get("is_founder", False),
                    "via": "relay",
                    "relay_url": getattr(self.config, 'relay_url', None),
                }
                
                # Add LAN address if provided (for multi-transport)
                if host:
                    peer_info["lan_address"] = f"ws://{host}:{port}/mesh/ws"
                    peer_info["host"] = host
                    peer_info["port"] = port
                
                # Store peer info in _relay_peers dict
                self._relay_peers[node_id] = peer_info
                
                # ADD TO RESILIENT MESH for multi-transport connectivity
                # This enables: Connect ALL, Use BEST, Failover INSTANT
                
                # Register remote capabilities (non-critical, skip if method missing)
                for cap in capabilities:
                    if self.router and cap:
                        try:
                            # Try register_capability with remote info embedded
                            await self.router.register_capability(
                                label=f"{node_id}:{cap}",
                                description=f"Remote capability '{cap}' from {name} (node {node_id})",
                                handler=f"remote:{node_id}"
                            )
                        except Exception as e:
                            logger.debug(f"Could not register remote capability {cap}: {e}")
                        
                # Broadcast to local WebSocket clients
                await manager.broadcast({
                    "type": "peer_joined",
                    "node_id": node_id,
                    "name": name,
                    "capabilities": capabilities
                })
                
            elif msg_type == "peer_left":
                # A peer left the mesh
                node_id = msg.get("node_id", "unknown")
                logger.info(f"Peer left via relay: {node_id}")
                
                # Mark device offline in registry (don't remove - keep history)
                from ..registry.devices import get_device_registry
                registry = get_device_registry()
                registry.mark_offline(node_id)
                
                # Remove from _relay_peers dict
                if node_id in self._relay_peers:
                    del self._relay_peers[node_id]
                
                # Remove from resilient mesh
                await manager.broadcast({
                    "type": "peer_left", 
                    "node_id": node_id
                })
                
            elif msg_type == "peers":
                # Received peer list from relay
                peers = msg.get("peers", [])
                logger.info(f"Received peer list from relay: {len(peers)} peers")
                
                # Update _relay_peers dict with peer list
                for peer in peers:
                    node_id = peer.get("node_id")
                    if node_id and node_id != (self.node.node_id if self.node else None):
                        # Build peer info for resilient mesh
                        peer_info = {
                            **peer,
                            "relay_url": getattr(self.config, 'relay_url', None),
                        }
                        if peer.get("host"):
                            peer_info["lan_address"] = f"ws://{peer['host']}:{peer.get('port', 11451)}/mesh/ws"
                        
                        self._relay_peers[node_id] = peer_info
                        
                        # ADD TO RESILIENT MESH for multi-transport
            elif msg_type == "mesh_registered":
                # Mesh registration confirmed by relay
                logger.info(f"Mesh registration confirmed by relay: success={msg.get('success')}")
                
            elif msg_type == "joined":
                # We successfully joined the mesh
                logger.info(f"Joined mesh via relay: {msg.get('mesh')} ({msg.get('mesh_id')}), node_count={msg.get('node_count')}")
                
            elif msg_type == "pong":
                # Ping response - connection alive
                logger.debug("Relay pong received")
                
            elif msg_type == "message":
                # Broadcast message from another peer
                payload = msg.get("payload", {})
                from_node = msg.get("from", "unknown")
                payload_type = payload.get("type", "unknown")
                logger.debug(f"Relay broadcast from {from_node}: {payload_type}")
                
                # Handle capability announcements from GossipManager
                # GossipManager sends: {"type": "broadcast", "payload": {"type": "capability.announce", ...}}
                if payload_type == "capability.announce" and self.gossip:
                    try:
                        await self.gossip.handle_announcement(from_node, payload)
                        logger.info(f"Processed capability announcement from {from_node} via relay")
                    except Exception as e:
                        logger.warning(f"Failed to process capability announcement from {from_node}: {e}")
                
                # Handle inference requests forwarded through relay
                elif payload_type == "inference_request":
                    logger.info(f"📥 Received inference_request from {from_node} via relay")
                    print(f"[RELAY] 📥 Inference request from {from_node}", flush=True)
                    # Process the inference request
                    response = await self._handle_relay_chat(payload)
                    if self.relay_client:
                        # Send response back to the requesting node via broadcast
                        response["target_node"] = from_node
                        response["type"] = "llm_response"
                        await self._send_to_relay({
                            "type": "broadcast",
                            "payload": response
                        })
                        logger.info(f"✅ Sent inference response to {from_node}")
                
                # Also handle legacy "gossip" type for backwards compatibility
                elif payload_type == "gossip" and self.gossip:
                    import base64
                    try:
                        gossip_data = base64.b64decode(payload.get("data", ""))
                        # Legacy format - parse and convert
                        import json
                        gossip_dict = json.loads(gossip_data.decode())
                        await self.gossip.handle_announcement(from_node, gossip_dict)
                        logger.info(f"Processed legacy gossip from {from_node} via relay")
                    except Exception as e:
                        logger.warning(f"Failed to process legacy gossip from {from_node}: {e}")
                
                # Forward to local WebSocket clients
                await manager.broadcast({
                    "type": "relay_message",
                    "from": from_node,
                    "payload": payload
                })
            else:
                logger.debug(f"Unknown relay message type: {msg_type}")
        except Exception as e:
            logger.error(f"Error processing relay message: {e}")
    
    async def _handle_relay_chat(self, msg: dict) -> dict:
        """Handle chat request from relay."""
        try:
            messages = msg.get("messages", [])
            # Support both "prompt" (string) and "messages" (array) formats
            prompt = msg.get("prompt", "")
            if prompt and not messages:
                messages = [{"role": "user", "content": prompt}]
            model = msg.get("model", "auto")
            # Default to a known good model if "auto" or empty
            if model in ("auto", "", "default", None):
                model = "qwen3:1.7b"  # Fast, good quality default
            request_id = msg.get("request_id", "")
            from_node = msg.get("from", msg.get("node_id", ""))  # Who sent the request
            
            # Use executor to handle (execute_capability, not execute_chat)
            if self.executor:
                exec_result = await self.executor.execute_capability(
                    "chat",
                    messages=messages,
                    model=model
                )
                
                # Extract the actual content string from ExecutionResult
                content = ""
                routing_info = None
                backend = None
                
                if exec_result.success and exec_result.data:
                    data = exec_result.data
                    if isinstance(data, dict):
                        # Try common response formats
                        content = data.get("content") or data.get("response") or data.get("message", {}).get("content", str(data))
                        # Extract routing info (THE CROWN JEWEL!)
                        routing_info = data.get("_routing")
                        backend = data.get("_backend")
                    else:
                        content = str(data)
                else:
                    raise Exception(exec_result.error or "Chat execution failed")

                # Return llm_response with target for relay to route back
                # Include routing info for visibility!
                response = {
                    "type": "llm_response",
                    "request_id": request_id,
                    "target": from_node,  # Route back to requester
                    "response": content
                }
                
                # Add routing info if available (THE CROWN JEWEL!)
                if routing_info:
                    response["routing"] = routing_info
                if backend:
                    response["backend"] = backend
                    
                return response
        except Exception as e:
            logger.error(f"Error in relay chat handling: {e}")
            return {
                "type": "llm_response",
                "request_id": msg.get("request_id", ""),
                "target": msg.get("from", ""),
                "error": str(e)
            }
        return {}
    
    async def _handle_relay_route(self, msg: dict) -> dict:
        """Handle route request from relay."""
        try:
            intent = msg.get("intent", "")
            payload = msg.get("payload", {})
            request_id = msg.get("request_id", "")
            
            if self.executor:
                result = await self.executor.route_and_execute(intent, payload)
                return {
                    "type": "route_response",
                    "request_id": request_id,
                    "response": result
                }
        except Exception as e:
            return {
                "type": "route_response",
                "request_id": msg.get("request_id", ""),
                "error": str(e)
            }
    
    async def _reconnect_relay(self, attempt: int = 0) -> None:
        """Attempt to reconnect to relay after disconnect with exponential backoff."""
        if not self._running:
            return
        
        # Exponential backoff: 2s, 4s, 8s, 16s, 30s max (mesh should keep trying forever)
        delays = [2, 4, 8, 16, 30]
        delay = delays[min(attempt, len(delays) - 1)]
        
        logger.info(f"Relay disconnected. Reconnecting in {delay}s (attempt {attempt + 1})...")
        await asyncio.sleep(delay)
        
        if self._running:
            try:
                # Clean up old connection first
                if self.relay_client:
                    try:
                        await self.relay_client.disconnect()
                    except Exception:
                        pass
                    self.relay_client = None
                
                await self._connect_to_relay()
                logger.info("Relay reconnection successful!")
            except Exception as e:
                logger.error(f"Reconnection attempt {attempt + 1} failed: {e}")
                # Try again with incremented attempt counter
                asyncio.create_task(self._reconnect_relay(attempt + 1))
    
    async def stop(self) -> None:
        """Stop the server and all services."""
        logger.info("Stopping Atmosphere server...")
        
        self._running = False
        
        # Stop BLE transport and pairing
        if self.ble_pairing_manager:
            self.ble_pairing_manager.stop()
            logger.info("BLE pairing manager stopped")
        
        if self.ble_transport:
            await self.ble_transport.stop()
            logger.info("BLE transport stopped")
        
        # Stop resilient mesh
            logger.info("Resilient mesh stopped")
        
        # Cancel relay task
        if self._relay_task:
            self._relay_task.cancel()
            try:
                await self._relay_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect from relay
        if self.relay_client:
            await self.relay_client.disconnect()
            logger.info("Disconnected from relay")
        
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
        relay_connected = (
            self.relay_client is not None and 
            self.relay_client.ws is not None and 
            not self.relay_client.ws.closed
        )
        
        # Count relay peers
        relay_peer_count = len(self._relay_peers) if hasattr(self, '_relay_peers') else 0
        
        # Get mDNS peer count
        mdns_peer_count = len(self.discovery.peers) if self.discovery else 0
        
        # Total unique peers (combine mDNS and relay, removing duplicates)
        all_peer_ids = set()
        if self.discovery:
            for p in self.discovery.peers:
                all_peer_ids.add(p.get("node_id", p.get("id", str(p))))
        if hasattr(self, '_relay_peers'):
            all_peer_ids.update(self._relay_peers.keys())
        
        return {
            "running": self._running,
            "node_id": self.node.node_id if self.node else None,
            "node_name": self.node.name if self.node else None,
            "mesh_id": self.node.mesh.mesh_id if self.node and self.node.mesh else None,
            "mesh_name": self.node.mesh.name if self.node and self.node.mesh else None,
            "capabilities": list(self.router.local_capability_ids) if self.router else [],
            "peers": {
                "total": len(all_peer_ids),
                "mdns": mdns_peer_count,
                "relay": relay_peer_count,
            },
            "relay": {
                "connected": relay_connected,
                "url": getattr(self.config, 'relay_url', None),
                "peer_count": relay_peer_count,
            },
            "transports": {
                "enabled": {
                    "lan": True,
                    "relay": relay_connected,
                    "ble": False,  # Future
                    "wifi_direct": False,  # Future
                    "matter": False,  # Future
                },
                "design": "multi-transport-resilience",
                "philosophy": "Connect ALL, Use BEST, Failover INSTANT",
            },
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _server
    
    # Import the module to ensure we set _server in the correct namespace
    # (fixes issue when running as __main__ vs importing)
    import atmosphere.api.server as server_module
    
    # Startup
    config = get_config()
    _server = AtmosphereServer(config)
    server_module._server = _server  # Also set in the imported module namespace
    
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

# Create app instance for uvicorn
app = create_app()



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Run Atmosphere API server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=11451, help='Port to bind to')
    parser.add_argument('--reload', action='store_true', help='Enable auto-reload')
    args = parser.parse_args()
    
    run_server(host=args.host, port=args.port, reload=args.reload)
