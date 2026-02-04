"""
FastAPI server for Atmosphere.
"""
import sys
print("[MODULE] Loading atmosphere.api.server", flush=True)
sys.stderr.write("[MODULE] Loading atmosphere.api.server (stderr)\n")
sys.stderr.flush()

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

import aiohttp
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from ..config import Config, get_config
from ..mesh.node import Node, NodeIdentity, MeshIdentity
from ..router.semantic import SemanticRouter
from ..router.executor import Executor
from ..mesh.gossip import GossipProtocol
from ..mesh.discovery import MeshDiscovery
from ..network.relay import RelayClient
from ..network.resilient_transport import (
    ResilientTransportManager,
    TransportType,
)
from ..network.mesh_connection import MeshConnectionManager, MeshConfig

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
        print("[INIT] AtmosphereServer created", flush=True)
        self.config = config or get_config()
        
        # Components (initialized in start())
        self.node: Optional[Node] = None
        self.router: Optional[SemanticRouter] = None
        self.executor: Optional[Executor] = None
        self.gossip: Optional[GossipProtocol] = None
        self.discovery: Optional[MeshDiscovery] = None
        self.relay_client: Optional[RelayClient] = None
        
        # Resilient multi-transport mesh connectivity
        self.mesh_connection: Optional[MeshConnectionManager] = None
        
        self._running = False
        self._relay_task: Optional[asyncio.Task] = None
        self._relay_peers: dict = {}  # node_id -> peer info from relay
    
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
        
        # Register LlamaFarm project handler
        self.executor.register_handler("llamafarm_project", self._handle_llamafarm_project)
        
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
            print("[LLAMAFARM] Creating FastProjectRouter...", flush=True)
            fast_router = FastProjectRouter()
            print(f"[LLAMAFARM] Initializing from API: {LLAMAFARM_BASE}", flush=True)
            await fast_router.initialize_from_api(LLAMAFARM_BASE)
            print(f"[LLAMAFARM] Loaded {len(fast_router.projects)} projects", flush=True)
            
            # Store reference for routing use
            self._fast_router = fast_router
            
            registered_count = 0
            for model_path, project in fast_router.projects.items():
                print(f"[LLAMAFARM] Processing: {model_path}", flush=True)
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
                print(f"[LLAMAFARM] Registered: llamafarm/{project.namespace}/{project.name}", flush=True)
                registered_count += 1
            
            print(f"[LLAMAFARM] Registered {registered_count} LlamaFarm projects as capabilities", flush=True)
            logger.info(f"Registered {registered_count} LlamaFarm projects as capabilities (using FastProjectRouter)")
            
        except Exception as e:
            print(f"[LLAMAFARM] ERROR: {e}", flush=True)
            logger.warning(f"Failed to register LlamaFarm projects: {e}")
            import traceback
            traceback.print_exc()
    
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
        print("[START] Entering start()", flush=True)
        await self.initialize()
        print("[START] After initialize()", flush=True)
        
        # Start mDNS discovery
        if self.discovery:
            await self.discovery.start()
        
        # Connect to relay server for NAT traversal
        await self._connect_to_relay()
        
        # Start gossip protocol for capability propagation
        await self._start_gossip()
        
        # Initialize resilient multi-transport mesh connectivity
        print("[START] Calling _start_resilient_mesh...", flush=True)
        await self._start_resilient_mesh()
        print("[START] _start_resilient_mesh completed", flush=True)
        
        self._running = True
        logger.info(
            f"Atmosphere server running at http://{self.config.server.host}:{self.config.server.port}"
        )
    
    async def _start_gossip(self) -> None:
        """Start the gossip protocol for capability propagation."""
        from ..mesh.gossip import GossipProtocol, CapabilityInfo
        
        if not self.node or not self.router:
            logger.debug("No node/router, skipping gossip")
            return
        
        # Build local capability list for gossip
        local_caps = []
        for cap_id, cap in self.router.local_capabilities.items():
            # Get embedding vector for capability
            vector = cap.vector.tolist() if hasattr(cap, 'vector') and cap.vector is not None else []
            local_caps.append(CapabilityInfo(
                id=cap_id,
                label=cap.label,
                description=cap.description,
                vector=vector,
                local=True,
                hops=0,
                models=cap.models if hasattr(cap, 'models') else []
            ))
        
        # Create gossip protocol
        self.gossip = GossipProtocol(
            node_id=self.node.node_id,
            gradient_table=self.router.gradient_table,
            local_capabilities=local_caps,
            announce_interval=self.config.gossip_interval or 30
        )
        
        # Set broadcast callback - sends via relay if connected
        async def broadcast_gossip(node_id: str, data: bytes):
            """Broadcast gossip message to all connected peers."""
            import base64
            import json
            
            # Parse the gossip announcement to get capabilities
            try:
                announcement = json.loads(data.decode())
            except:
                announcement = {}
            
            # Wrap announcement for relay using broadcast message type
            # Relay expects: {"type": "broadcast", "payload": {...}}
            relay_msg = {
                "type": "broadcast",
                "payload": {
                    "type": "gossip",
                    "node_id": node_id,
                    "data": base64.b64encode(data).decode(),
                    "capabilities": [c.get("label", c.get("id", "")) for c in announcement.get("capabilities", [])]
                }
            }
            
            # Send via relay
            if self.relay_client and self.relay_client.ws:
                try:
                    await self.relay_client.send(relay_msg)
                    logger.debug(f"Broadcast gossip via relay: {len(announcement.get('capabilities', []))} capabilities")
                except Exception as e:
                    logger.debug(f"Relay broadcast failed: {e}")
            
            # Also broadcast to mDNS-discovered peers
            if self.discovery:
                for peer in self.discovery.peers:
                    try:
                        # Direct peer broadcast would go here (e.g. UDP or TCP)
                        pass
                    except Exception:
                        pass
        
        self.gossip.set_broadcast_callback(broadcast_gossip)
        
        # Start gossip loop
        await self.gossip.start()
        logger.info(f"Gossip protocol started with {len(local_caps)} local capabilities")
    
    async def _start_resilient_mesh(self) -> None:
        """
        Start resilient multi-transport mesh connectivity.
        
        Philosophy: Connect ALL, Use BEST, Failover INSTANT.
        
        - Connects via ALL available transports simultaneously (LAN, Relay, BLE, etc.)
        - Routes messages via best transport (lowest latency + highest reliability)
        - Instant failover when primary fails (already connected to alternatives)
        - Continuous health monitoring keeps connections warm
        """
        print("[SERVER] _start_resilient_mesh called")
        if not self.node or not self.node.mesh:
            print("[SERVER] No mesh configured, skipping resilient mesh")
            logger.debug("No mesh configured, skipping resilient mesh")
            return
        print(f"[SERVER] Node={self.node.node_id}, Mesh={self.node.mesh.mesh_id}")
        
        relay_url = getattr(self.config, 'relay_url', None)
        
        # Create mesh configuration
        # NOTE: Disable relay in MeshConnectionManager because AtmosphereServer
        # handles the relay connection separately (with founder registration, token handling, etc.)
        config = MeshConfig(
            node_id=self.node.node_id,
            mesh_id=self.node.mesh.mesh_id,
            local_host=self.config.server.host,
            local_port=self.config.server.port,
            relay_url=relay_url,
            enable_mdns=self.config.mdns_enabled,
            enable_relay=False,  # Handled by AtmosphereServer._connect_to_relay()
            enable_lan=True,
            enable_ble=False,  # Future
            enable_wifi_direct=False,  # Future
            enable_matter=False,  # Future
        )
        
        # Create mesh connection manager
        self.mesh_connection = MeshConnectionManager(config)
        
        # Wire up event handlers
        def on_peer_discovered(peer_id: str, peer_info: dict):
            logger.info(f"[RESILIENT] Peer discovered: {peer_id}")
            # Add to relay_peers for API visibility
            self._relay_peers[peer_id] = {
                **peer_info,
                "via": "resilient_mesh",
            }
        
        def on_peer_connected(peer_id: str):
            logger.info(f"[RESILIENT] Peer connected: {peer_id}")
            # Broadcast to local WebSocket clients
            asyncio.create_task(manager.broadcast({
                "type": "peer_connected",
                "peer_id": peer_id,
                "via": "resilient_mesh",
            }))
        
        def on_peer_disconnected(peer_id: str):
            logger.info(f"[RESILIENT] Peer disconnected: {peer_id}")
            asyncio.create_task(manager.broadcast({
                "type": "peer_disconnected",
                "peer_id": peer_id,
            }))
        
        def on_message(peer_id: str, message: bytes):
            logger.debug(f"[RESILIENT] Message from {peer_id}: {len(message)} bytes")
            # Process gossip or other mesh messages
            asyncio.create_task(self._handle_resilient_message(peer_id, message))
        
        self.mesh_connection.on_peer_discovered(on_peer_discovered)
        self.mesh_connection.on_peer_connected(on_peer_connected)
        self.mesh_connection.on_peer_disconnected(on_peer_disconnected)
        self.mesh_connection.on_message(on_message)
        
        # Start the manager
        await self.mesh_connection.start()
        
        # If we have relay peers already discovered, add them to resilient mesh
        for peer_id, peer_info in list(self._relay_peers.items()):
            if peer_id != self.node.node_id:
                await self.mesh_connection.add_peer(peer_id, peer_info)
        
        logger.info(f"[RESILIENT] Multi-transport mesh started (LAN={config.enable_lan}, Relay={config.enable_relay})")
    
    async def _handle_resilient_message(self, peer_id: str, message: bytes) -> None:
        """Handle message received via resilient mesh transports."""
        try:
            import json
            data = json.loads(message.decode())
            msg_type = data.get("type", "")
            
            if msg_type == "gossip" and self.gossip:
                # Handle gossip announcement
                import base64
                gossip_data = base64.b64decode(data.get("data", ""))
                await self.gossip.handle_announcement(gossip_data, peer_id)
                
            elif msg_type == "chat_request":
                # Handle chat request from peer
                response = await self._handle_relay_chat(data)
                # Send response back via resilient mesh
                if self.mesh_connection:
                    await self.mesh_connection.send(
                        peer_id, 
                        json.dumps(response).encode()
                    )
                    
            elif msg_type == "route_request":
                # Handle route request from peer
                response = await self._handle_relay_route(data)
                if self.mesh_connection:
                    await self.mesh_connection.send(
                        peer_id,
                        json.dumps(response).encode()
                    )
                    
            else:
                logger.debug(f"Unknown resilient message type: {msg_type}")
                
        except Exception as e:
            logger.error(f"Error handling resilient message: {e}")
    
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
            # Create relay client using mesh_id as session
            self.relay_client = RelayClient(relay_url, session_id=mesh_id)
            
            if await self.relay_client.connect(timeout=10.0):
                logger.info(f"Connected to relay: {relay_url}/relay/{mesh_id}")
                
                # If founder, register mesh with public key (relay v2.0 security)
                if self.node.is_founder and hasattr(mesh, 'master_public_key') and mesh.master_public_key:
                    import base64
                    
                    # Create founder proof by signing mesh_id
                    founder_proof = ""
                    # Try to use the master keypair if available (founder who created mesh)
                    # or the local keypair if it was added to the mesh identity
                    signing_key = getattr(mesh, '_master_keypair', mesh._local_key_pair)
                    
                    if signing_key:
                        try:
                            sig = signing_key.sign(mesh_id.encode())
                            founder_proof = base64.b64encode(sig).decode()
                        except Exception as e:
                            logger.warning(f"Could not create founder proof: {e}")
                    
                    # Ensure public key is string
                    pub_key = mesh.master_public_key
                    if isinstance(pub_key, bytes):
                        pub_key = base64.b64encode(pub_key).decode()

                    # Get node's public key for proof verification
                    node_pub_key = ""
                    if signing_key:
                        node_pub_key = signing_key.public_key_b64()
                    
                    # Get capabilities to advertise
                    caps = list(self.router.local_capabilities.keys()) if self.router else []
                    # Add generic LLM capability for routing
                    if caps and "llm" not in caps:
                        caps.append("llm")
                    
                    register_msg = {
                        "type": "register_mesh",
                        "mesh_id": mesh_id,
                        "mesh_public_key": pub_key,
                        "founder_proof": founder_proof,
                        "node_id": self.node.node_id,
                        "name": mesh.name,
                        "node_public_key": node_pub_key,  # For proof verification
                        "capabilities": caps  # Include capabilities so relay knows what we can do
                    }
                    await self.relay_client.send(register_msg)
                    logger.info(f"Registered mesh {mesh_id} with relay (founder) with {len(caps)} capabilities")
                else:
                    # Non-founder joins with their node info
                    join_msg = {
                        "type": "join",
                        "mesh_id": mesh_id,
                        "node_id": self.node.node_id,
                        "node_name": self.node.name,
                        "capabilities": list(self.router.local_capabilities.keys()) if self.router else []
                    }
                    await self.relay_client.send(join_msg)
                    logger.info(f"Joined mesh {mesh_id} via relay")
                
                # Start relay message handler
                self._relay_task = asyncio.create_task(self._handle_relay_messages())
            else:
                logger.warning(f"Failed to connect to relay: {relay_url}")
                
        except Exception as e:
            logger.error(f"Relay connection error: {e}")
    
    async def _handle_relay_messages(self) -> None:
        """Handle incoming messages from relay."""
        if not self.relay_client or not self.relay_client.ws:
            return
        
        try:
            logger.info("Relay message handler started, listening for messages...")
            
            # Start ping task to keep connection alive
            ping_task = asyncio.create_task(self._relay_ping_loop())
            
            try:
                # Use async for which handles closure correctly
                async for msg in self.relay_client.ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._process_relay_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.BINARY:
                        await self._process_relay_message(msg.data.decode())
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"Relay WebSocket error: {self.relay_client.ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.info("Relay connection closed by server")
                        break
                
                logger.warning("Relay message loop exited (connection closed)")
            finally:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass
                    
        except asyncio.CancelledError:
            logger.debug("Relay handler cancelled")
            return  # Don't reconnect if cancelled
        except Exception as e:
            logger.error(f"Relay message handler error: {e}", exc_info=True)
        
        # Only reconnect if still running
        if self._running:
            await self._reconnect_relay()
            
    async def _relay_ping_loop(self) -> None:
        """Send periodic pings to keep relay connection alive."""
        while True:
            try:
                await asyncio.sleep(20)  # Ping every 20 seconds
                if self.relay_client and self.relay_client.ws and not self.relay_client.ws.closed:
                    await self.relay_client.send({"type": "ping"})
                    logger.debug("Sent ping to relay")
                else:
                    logger.warning("Relay WS closed during ping loop, breaking")
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Ping error (will reconnect): {e}")
                break
    
    async def _process_relay_message(self, data: str) -> None:
        """Process a message received from relay."""
        import json
        try:
            msg = json.loads(data)
            msg_type = msg.get("type", "")
            
            if msg_type == "chat_request" or msg_type == "llm_request":
                # Forward to local LLM (handle both message types)
                response = await self._handle_relay_chat(msg)
                if self.relay_client:
                    # PASS THE DICT, NOT BYTES! RelayClient handles the encoding.
                    # The relay server expects a TEXT frame, not BINARY.
                    await self.relay_client.send(response)
                    logger.info(f"Sent LLM response back via relay to {msg.get('from', 'unknown')}")
            elif msg_type == "route_request":
                # Handle routing request
                response = await self._handle_relay_route(msg)
                if self.relay_client:
                    await self.relay_client.send(response)
            elif msg_type == "peer_joined":
                # A new peer joined the mesh
                node_id = msg.get("node_id", "unknown")
                name = msg.get("name", node_id[:8])
                capabilities = msg.get("capabilities", [])
                host = msg.get("host")  # LAN address if available
                port = msg.get("port", 11451)
                device_type = msg.get("device_type", "unknown")
                model = msg.get("model", "")
                logger.info(f"Peer joined via relay: {name} ({node_id}) with {len(capabilities)} capabilities")
                
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
                if self.mesh_connection:
                    await self.mesh_connection.add_peer(node_id, peer_info)
                    logger.debug(f"Added peer {node_id} to resilient mesh")
                
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
                if self.mesh_connection:
                    await self.mesh_connection.transport_manager.disconnect_peer(node_id)
                    
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
                        if self.mesh_connection:
                            await self.mesh_connection.add_peer(node_id, peer_info)
                        
                        # Register capabilities (non-critical)
                        for cap in peer.get("capabilities", []):
                            if self.router and cap:
                                try:
                                    await self.router.register_capability(
                                        label=f"{node_id}:{cap}",
                                        description=f"Remote capability '{cap}' from {peer.get('name', node_id[:8])}",
                                        handler=f"remote:{node_id}"
                                    )
                                except Exception as e:
                                    logger.debug(f"Could not register remote cap: {e}")
                                
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
                
                # Handle gossip messages
                if payload_type == "gossip" and self.gossip:
                    import base64
                    try:
                        gossip_data = base64.b64decode(payload.get("data", ""))
                        await self.gossip.handle_announcement(gossip_data, from_node)
                        logger.info(f"Processed gossip from {from_node} via relay")
                    except Exception as e:
                        logger.warning(f"Failed to process gossip from {from_node}: {e}")
                
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
            model = msg.get("model", "auto")
            request_id = msg.get("request_id", "")
            from_node = msg.get("from", "")  # Who sent the request
            
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
        
        # Stop resilient mesh
        if self.mesh_connection:
            await self.mesh_connection.stop()
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
            "capabilities": list(self.router.local_capabilities.keys()) if self.router else [],
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

# Create app instance for uvicorn
app = create_app()

