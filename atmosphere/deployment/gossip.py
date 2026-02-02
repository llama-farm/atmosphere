"""
Model Gossip Protocol for Atmosphere mesh.

Extends the core gossip protocol with model-specific messages for
instant propagation of model updates across the mesh.

Message Types:
- ROUTE_UPDATE: Model routing table updates with pre-computed embeddings
- MODEL_DEPLOYED: Instant notification when a model is deployed to a node
- MODEL_AVAILABLE: Periodic announcement of available models
- MODEL_REQUEST: Request models by criteria
- MODEL_OFFER: Offer to send a model
- SYNC_REQUEST: Request full inventory on join
- SYNC_RESPONSE: Full routing table + model inventory

Design Goals:
- Updates reach all nodes in seconds
- Optimistic local updates, eventual consistency
- New nodes get full state on join
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable, Dict, List, Optional, Set
from datetime import datetime

from .registry import ModelRegistry, ModelManifest, ModelEntry

logger = logging.getLogger(__name__)

# Protocol constants
MODEL_ANNOUNCE_INTERVAL_SEC = 60
ROUTE_UPDATE_TTL = 10  # Hops before route update dies
NONCE_CACHE_TTL_SEC = 300
SYNC_TIMEOUT_SEC = 10


class MessageType(Enum):
    """Types of model-related gossip messages."""
    # Fast propagation (instant)
    ROUTE_UPDATE = "route_update"
    MODEL_DEPLOYED = "model_deployed"
    
    # Discovery (periodic/on-demand)
    MODEL_AVAILABLE = "model_available"
    MODEL_REQUEST = "model_request"
    MODEL_OFFER = "model_offer"
    MODEL_ACK = "model_ack"
    
    # Sync (on join)
    SYNC_REQUEST = "sync_request"
    SYNC_RESPONSE = "sync_response"


@dataclass
class ModelRoute:
    """
    A model route entry with pre-computed embedding for fast matching.
    
    This is what gets gossiped for instant routing table updates.
    """
    project: str  # e.g., "default/llama-expert-14" or model name
    version: str
    model_type: str
    embedding: List[float]  # Pre-computed for fast semantic matching
    nodes: List[str]  # Which nodes have this model
    capabilities: List[str]
    size_bytes: int
    checksum: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "version": self.version,
            "model_type": self.model_type,
            "embedding": self.embedding,
            "nodes": self.nodes,
            "capabilities": self.capabilities,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "metadata": self.metadata,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModelRoute":
        return cls(
            project=data["project"],
            version=data.get("version", "1.0.0"),
            model_type=data.get("model_type", "unknown"),
            embedding=data.get("embedding", []),
            nodes=data.get("nodes", []),
            capabilities=data.get("capabilities", []),
            size_bytes=data.get("size_bytes", 0),
            checksum=data.get("checksum", ""),
            metadata=data.get("metadata", {}),
            updated_at=data.get("updated_at", time.time()),
        )
    
    @classmethod
    def from_manifest(cls, manifest: ModelManifest, nodes: List[str], embedding: List[float] = None) -> "ModelRoute":
        return cls(
            project=manifest.name,
            version=manifest.version,
            model_type=manifest.type,
            embedding=embedding or [],
            nodes=nodes,
            capabilities=manifest.capabilities,
            size_bytes=manifest.size_bytes,
            checksum=manifest.checksum_sha256,
            metadata=manifest.config,
        )


@dataclass
class ModelMessage:
    """
    A model-related gossip message.
    
    Supports all message types with appropriate payloads.
    """
    type: MessageType
    from_node: str
    to_node: Optional[str] = None  # None for broadcast
    timestamp: float = field(default_factory=time.time)
    ttl: int = ROUTE_UPDATE_TTL
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    
    # ROUTE_UPDATE payload
    action: Optional[str] = None  # "add", "update", "remove"
    route: Optional[ModelRoute] = None
    
    # MODEL_DEPLOYED payload
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    deployed_node: Optional[str] = None
    
    # MODEL_AVAILABLE payload (periodic announcements)
    routes: List[ModelRoute] = field(default_factory=list)
    
    # MODEL_REQUEST payload
    criteria: Optional[Dict[str, Any]] = None
    urgency: str = "normal"
    
    # MODEL_OFFER/ACK payload
    offer_route: Optional[ModelRoute] = None
    transfer_options: Dict[str, str] = field(default_factory=dict)
    accepted: bool = False
    
    # SYNC_REQUEST/RESPONSE payload
    node_capabilities: Optional[Dict[str, Any]] = None
    full_routes: List[ModelRoute] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "from": self.from_node,
            "to": self.to_node,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
            "nonce": self.nonce,
            "action": self.action,
            "route": self.route.to_dict() if self.route else None,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "deployed_node": self.deployed_node,
            "routes": [r.to_dict() for r in self.routes],
            "criteria": self.criteria,
            "urgency": self.urgency,
            "offer_route": self.offer_route.to_dict() if self.offer_route else None,
            "transfer_options": self.transfer_options,
            "accepted": self.accepted,
            "node_capabilities": self.node_capabilities,
            "full_routes": [r.to_dict() for r in self.full_routes],
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModelMessage":
        return cls(
            type=MessageType(data["type"]),
            from_node=data["from"],
            to_node=data.get("to"),
            timestamp=data.get("timestamp", time.time()),
            ttl=data.get("ttl", ROUTE_UPDATE_TTL),
            nonce=data.get("nonce", ""),
            action=data.get("action"),
            route=ModelRoute.from_dict(data["route"]) if data.get("route") else None,
            model_name=data.get("model_name"),
            model_version=data.get("model_version"),
            deployed_node=data.get("deployed_node"),
            routes=[ModelRoute.from_dict(r) for r in data.get("routes", [])],
            criteria=data.get("criteria"),
            urgency=data.get("urgency", "normal"),
            offer_route=ModelRoute.from_dict(data["offer_route"]) if data.get("offer_route") else None,
            transfer_options=data.get("transfer_options", {}),
            accepted=data.get("accepted", False),
            node_capabilities=data.get("node_capabilities"),
            full_routes=[ModelRoute.from_dict(r) for r in data.get("full_routes", [])],
        )
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "ModelMessage":
        return cls.from_dict(json.loads(json_str))


# Callback types
BroadcastCallback = Callable[[bytes], Awaitable[None]]
SendCallback = Callable[[str, bytes], Awaitable[bool]]
EmbedCallback = Callable[[str], Awaitable[List[float]]]


class ModelRoutingTable:
    """
    In-memory routing table for models.
    
    Tracks which models are available where, with embeddings
    for fast semantic matching.
    """
    
    def __init__(self):
        self._routes: Dict[str, ModelRoute] = {}  # project -> route
        self._by_node: Dict[str, Set[str]] = {}  # node_id -> set of projects
        self._by_capability: Dict[str, Set[str]] = {}  # capability -> set of projects
        self._lock = asyncio.Lock()
    
    async def add_or_update(self, route: ModelRoute) -> bool:
        """
        Add or update a route. Returns True if this was a new/updated entry.
        """
        async with self._lock:
            existing = self._routes.get(route.project)
            
            # Skip if we have a newer version
            if existing and existing.updated_at > route.updated_at:
                return False
            
            self._routes[route.project] = route
            
            # Update indexes
            for node in route.nodes:
                if node not in self._by_node:
                    self._by_node[node] = set()
                self._by_node[node].add(route.project)
            
            for cap in route.capabilities:
                if cap not in self._by_capability:
                    self._by_capability[cap] = set()
                self._by_capability[cap].add(route.project)
            
            return True
    
    async def remove(self, project: str) -> bool:
        """Remove a route."""
        async with self._lock:
            if project not in self._routes:
                return False
            
            route = self._routes.pop(project)
            
            # Clean up indexes
            for node in route.nodes:
                if node in self._by_node:
                    self._by_node[node].discard(project)
            
            for cap in route.capabilities:
                if cap in self._by_capability:
                    self._by_capability[cap].discard(project)
            
            return True
    
    async def add_node_to_route(self, project: str, node_id: str) -> bool:
        """Add a node as having a model."""
        async with self._lock:
            if project not in self._routes:
                return False
            
            route = self._routes[project]
            if node_id not in route.nodes:
                route.nodes.append(node_id)
                route.updated_at = time.time()
                
                if node_id not in self._by_node:
                    self._by_node[node_id] = set()
                self._by_node[node_id].add(project)
            
            return True
    
    async def remove_node_from_route(self, project: str, node_id: str) -> bool:
        """Remove a node from having a model."""
        async with self._lock:
            if project not in self._routes:
                return False
            
            route = self._routes[project]
            if node_id in route.nodes:
                route.nodes.remove(node_id)
                route.updated_at = time.time()
                
                if node_id in self._by_node:
                    self._by_node[node_id].discard(project)
            
            return True
    
    def get(self, project: str) -> Optional[ModelRoute]:
        """Get a specific route."""
        return self._routes.get(project)
    
    def get_all(self) -> List[ModelRoute]:
        """Get all routes."""
        return list(self._routes.values())
    
    def get_by_node(self, node_id: str) -> List[ModelRoute]:
        """Get routes available on a specific node."""
        projects = self._by_node.get(node_id, set())
        return [self._routes[p] for p in projects if p in self._routes]
    
    def get_by_capability(self, capability: str) -> List[ModelRoute]:
        """Get routes with a specific capability."""
        projects = self._by_capability.get(capability, set())
        return [self._routes[p] for p in projects if p in self._routes]
    
    def find_nodes_with_model(self, project: str) -> List[str]:
        """Find nodes that have a specific model."""
        route = self._routes.get(project)
        return route.nodes if route else []
    
    def export_for_sync(self) -> List[ModelRoute]:
        """Export all routes for sync response."""
        return list(self._routes.values())
    
    def stats(self) -> dict:
        return {
            "total_routes": len(self._routes),
            "nodes_with_models": len(self._by_node),
            "capabilities_indexed": len(self._by_capability),
        }


class ModelGossip:
    """
    Model-aware gossip protocol extension.
    
    Handles:
    - Instant propagation of route updates (ROUTE_UPDATE)
    - Deployment notifications (MODEL_DEPLOYED)
    - Full sync on node join (SYNC_REQUEST/RESPONSE)
    - Periodic model announcements
    - Request/offer flow for pulling models
    
    Usage:
        gossip = ModelGossip(
            node_id="my-node",
            registry=registry,
        )
        
        gossip.set_broadcast_callback(broadcast_to_peers)
        gossip.set_send_callback(send_to_peer)
        
        await gossip.start()
        
        # When a model is deployed locally
        await gossip.broadcast_deployment("network-anomaly-v3", "1.0.0")
        
        # When a new node joins, it requests sync
        await gossip.request_sync()
        
        # Handle incoming messages
        await gossip.handle_message(data, from_peer)
    """
    
    def __init__(
        self,
        node_id: str,
        registry: ModelRegistry,
        announce_interval: float = MODEL_ANNOUNCE_INTERVAL_SEC
    ):
        self.node_id = node_id
        self.registry = registry
        self.announce_interval = announce_interval
        
        # Routing table (shared state)
        self.routing_table = ModelRoutingTable()
        
        # Callbacks
        self._broadcast: Optional[BroadcastCallback] = None
        self._send: Optional[SendCallback] = None
        self._embed: Optional[EmbedCallback] = None  # For computing embeddings
        
        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._nonce_cache: Dict[str, float] = {}
        self._pending_syncs: Dict[str, asyncio.Future] = {}
        
        # Events
        self.on_route_update: Optional[Callable[[ModelRoute, str], Awaitable[None]]] = None
        self.on_model_deployed: Optional[Callable[[str, str, str], Awaitable[None]]] = None
        self.on_sync_complete: Optional[Callable[[int], Awaitable[None]]] = None
    
    def set_broadcast_callback(self, callback: BroadcastCallback) -> None:
        """Set callback for broadcasting to all peers."""
        self._broadcast = callback
    
    def set_send_callback(self, callback: SendCallback) -> None:
        """Set callback for sending to specific peer."""
        self._send = callback
    
    def set_embed_callback(self, callback: EmbedCallback) -> None:
        """Set callback for computing embeddings."""
        self._embed = callback
    
    # ==================== Fast Propagation ====================
    
    async def broadcast_route_update(
        self,
        route: ModelRoute,
        action: str = "add"
    ) -> None:
        """
        Broadcast a route update to all peers immediately.
        
        This is the fast path - updates propagate in seconds.
        """
        if not self._broadcast:
            logger.warning("Cannot broadcast: no callback configured")
            return
        
        msg = ModelMessage(
            type=MessageType.ROUTE_UPDATE,
            from_node=self.node_id,
            action=action,
            route=route,
        )
        
        await self._broadcast(msg.to_json().encode())
        logger.info(f"Broadcast route update: {action} {route.project}")
    
    async def broadcast_deployment(
        self,
        model_name: str,
        version: str,
        embedding: List[float] = None
    ) -> None:
        """
        Broadcast that a model was deployed to this node.
        
        Called when a model is successfully deployed/loaded.
        All nodes learn about this in seconds.
        """
        if not self._broadcast:
            return
        
        # Get embedding if we have an embed callback
        if embedding is None and self._embed:
            try:
                embedding = await self._embed(model_name)
            except Exception as e:
                logger.warning(f"Failed to compute embedding: {e}")
                embedding = []
        
        # First, send MODEL_DEPLOYED for instant notification
        msg = ModelMessage(
            type=MessageType.MODEL_DEPLOYED,
            from_node=self.node_id,
            model_name=model_name,
            model_version=version,
            deployed_node=self.node_id,
        )
        
        await self._broadcast(msg.to_json().encode())
        
        # Also update the routing table and broadcast route update
        entry = self.registry.get_local(model_name, version)
        if entry:
            route = ModelRoute.from_manifest(
                entry.manifest,
                nodes=[self.node_id],
                embedding=embedding or []
            )
            
            # Update local routing table
            await self.routing_table.add_or_update(route)
            
            # Broadcast the route update
            await self.broadcast_route_update(route, "add")
        
        logger.info(f"Broadcast deployment: {model_name}:{version}")
    
    async def broadcast_removal(self, model_name: str) -> None:
        """Broadcast that a model was removed from this node."""
        if not self._broadcast:
            return
        
        route = self.routing_table.get(model_name)
        if route:
            # Remove this node from the route
            await self.routing_table.remove_node_from_route(model_name, self.node_id)
            
            # Broadcast update
            updated_route = self.routing_table.get(model_name)
            if updated_route:
                await self.broadcast_route_update(updated_route, "update")
            else:
                # Model no longer exists anywhere
                msg = ModelMessage(
                    type=MessageType.ROUTE_UPDATE,
                    from_node=self.node_id,
                    action="remove",
                    route=route,
                )
                await self._broadcast(msg.to_json().encode())
    
    # ==================== Sync on Join ====================
    
    async def request_sync(self, target_node: str = None) -> int:
        """
        Request full routing table sync.
        
        Called when a new node joins the mesh.
        Returns number of routes received.
        """
        if not self._broadcast and not self._send:
            raise RuntimeError("No send callback configured")
        
        msg = ModelMessage(
            type=MessageType.SYNC_REQUEST,
            from_node=self.node_id,
            to_node=target_node,
            node_capabilities=self._get_node_capabilities(),
        )
        
        # Create future for response
        future: asyncio.Future = asyncio.Future()
        self._pending_syncs[msg.nonce] = future
        
        if target_node and self._send:
            await self._send(target_node, msg.to_json().encode())
        elif self._broadcast:
            await self._broadcast(msg.to_json().encode())
        
        # Wait for response
        try:
            routes_received = await asyncio.wait_for(future, timeout=SYNC_TIMEOUT_SEC)
            logger.info(f"Sync complete: received {routes_received} routes")
            
            if self.on_sync_complete:
                await self.on_sync_complete(routes_received)
            
            return routes_received
        except asyncio.TimeoutError:
            logger.warning("Sync request timed out")
            return 0
        finally:
            self._pending_syncs.pop(msg.nonce, None)
    
    async def _send_sync_response(self, to_node: str, request_nonce: str) -> None:
        """Send full routing table to requesting node."""
        if not self._send:
            return
        
        routes = self.routing_table.export_for_sync()
        
        msg = ModelMessage(
            type=MessageType.SYNC_RESPONSE,
            from_node=self.node_id,
            to_node=to_node,
            nonce=request_nonce,  # Echo nonce for correlation
            full_routes=routes,
        )
        
        await self._send(to_node, msg.to_json().encode())
        logger.info(f"Sent sync response to {to_node}: {len(routes)} routes")
    
    def _get_node_capabilities(self) -> Dict[str, Any]:
        """Get this node's capabilities for sync."""
        # TODO: Integrate with actual node capabilities
        return {
            "node_id": self.node_id,
            "local_models": len(self.registry.list_local()),
        }
    
    # ==================== Periodic Announcements ====================
    
    async def announce(self) -> None:
        """
        Broadcast all available models periodically.
        
        This is the background sync - complements fast updates.
        """
        if not self._broadcast:
            return
        
        routes = []
        for entry in self.registry.list_local():
            route = ModelRoute.from_manifest(
                entry.manifest,
                nodes=[self.node_id],
            )
            routes.append(route)
            
            # Also update local routing table
            await self.routing_table.add_or_update(route)
        
        if not routes:
            return
        
        msg = ModelMessage(
            type=MessageType.MODEL_AVAILABLE,
            from_node=self.node_id,
            routes=routes,
        )
        
        try:
            await self._broadcast(msg.to_json().encode())
            logger.debug(f"Announced {len(routes)} models")
        except Exception as e:
            logger.error(f"Failed to announce models: {e}")
    
    # ==================== Request/Offer Flow ====================
    
    async def request_model(
        self,
        name: str = None,
        capabilities: List[str] = None,
        max_size_bytes: int = None,
        urgency: str = "normal"
    ) -> str:
        """
        Request models matching criteria.
        
        Returns request nonce for tracking responses.
        """
        if not self._broadcast:
            raise RuntimeError("Broadcast callback not configured")
        
        criteria = {}
        if name:
            criteria["name"] = name
        if capabilities:
            criteria["capabilities"] = capabilities
        if max_size_bytes:
            criteria["max_size_bytes"] = max_size_bytes
        
        msg = ModelMessage(
            type=MessageType.MODEL_REQUEST,
            from_node=self.node_id,
            criteria=criteria,
            urgency=urgency,
        )
        
        await self._broadcast(msg.to_json().encode())
        logger.info(f"Requested models: {criteria}")
        
        return msg.nonce
    
    async def offer_model(
        self,
        to_node: str,
        route: ModelRoute,
        transfer_options: Dict[str, str] = None
    ) -> None:
        """Offer a model to a requesting peer."""
        if not self._send:
            return
        
        msg = ModelMessage(
            type=MessageType.MODEL_OFFER,
            from_node=self.node_id,
            to_node=to_node,
            offer_route=route,
            transfer_options=transfer_options or {},
        )
        
        await self._send(to_node, msg.to_json().encode())
        logger.info(f"Offered {route.project} to {to_node}")
    
    async def accept_offer(self, to_node: str, route: ModelRoute) -> None:
        """Accept a model offer."""
        if not self._send:
            return
        
        msg = ModelMessage(
            type=MessageType.MODEL_ACK,
            from_node=self.node_id,
            to_node=to_node,
            offer_route=route,
            accepted=True,
        )
        
        await self._send(to_node, msg.to_json().encode())
    
    # ==================== Message Handling ====================
    
    async def handle_message(self, data: bytes, from_peer: str) -> None:
        """Handle an incoming model gossip message."""
        try:
            msg = ModelMessage.from_json(data.decode())
        except Exception as e:
            logger.warning(f"Invalid model message from {from_peer}: {e}")
            return
        
        # Check nonce (prevent replay)
        if not self._check_nonce(msg.nonce, msg.timestamp):
            return
        
        # Route by message type
        handlers = {
            MessageType.ROUTE_UPDATE: self._handle_route_update,
            MessageType.MODEL_DEPLOYED: self._handle_model_deployed,
            MessageType.MODEL_AVAILABLE: self._handle_model_available,
            MessageType.MODEL_REQUEST: self._handle_model_request,
            MessageType.MODEL_OFFER: self._handle_model_offer,
            MessageType.MODEL_ACK: self._handle_model_ack,
            MessageType.SYNC_REQUEST: self._handle_sync_request,
            MessageType.SYNC_RESPONSE: self._handle_sync_response,
        }
        
        handler = handlers.get(msg.type)
        if handler:
            await handler(msg, from_peer)
    
    async def _handle_route_update(self, msg: ModelMessage, from_peer: str) -> None:
        """Handle ROUTE_UPDATE - instant routing table update."""
        if not msg.route:
            return
        
        action = msg.action or "add"
        
        if action == "remove":
            await self.routing_table.remove(msg.route.project)
        else:
            # Optimistic local update
            updated = await self.routing_table.add_or_update(msg.route)
            
            if updated and self.on_route_update:
                await self.on_route_update(msg.route, action)
        
        # Forward with TTL decrement
        if msg.ttl > 1 and self._broadcast:
            forwarded = ModelMessage(
                type=MessageType.ROUTE_UPDATE,
                from_node=msg.from_node,
                action=action,
                route=msg.route,
                timestamp=msg.timestamp,
                ttl=msg.ttl - 1,
                nonce=msg.nonce,
            )
            try:
                await self._broadcast(forwarded.to_json().encode())
            except Exception as e:
                logger.error(f"Failed to forward route update: {e}")
    
    async def _handle_model_deployed(self, msg: ModelMessage, from_peer: str) -> None:
        """Handle MODEL_DEPLOYED - instant deployment notification."""
        if not msg.model_name or not msg.deployed_node:
            return
        
        # Update routing table
        await self.routing_table.add_node_to_route(msg.model_name, msg.deployed_node)
        
        # Also update registry's mesh knowledge
        self.registry.update_mesh_model(
            msg.model_name,
            msg.model_version or "unknown",
            msg.deployed_node
        )
        
        if self.on_model_deployed:
            await self.on_model_deployed(
                msg.model_name,
                msg.model_version or "unknown",
                msg.deployed_node
            )
        
        logger.info(f"Model deployed: {msg.model_name} on {msg.deployed_node}")
        
        # Forward with TTL decrement
        if msg.ttl > 1 and self._broadcast:
            forwarded = ModelMessage(
                type=MessageType.MODEL_DEPLOYED,
                from_node=msg.from_node,
                model_name=msg.model_name,
                model_version=msg.model_version,
                deployed_node=msg.deployed_node,
                timestamp=msg.timestamp,
                ttl=msg.ttl - 1,
                nonce=msg.nonce,
            )
            try:
                await self._broadcast(forwarded.to_json().encode())
            except Exception as e:
                logger.error(f"Failed to forward deployment: {e}")
    
    async def _handle_model_available(self, msg: ModelMessage, from_peer: str) -> None:
        """Handle MODEL_AVAILABLE - periodic announcement."""
        for route in msg.routes:
            await self.routing_table.add_or_update(route)
            self.registry.update_mesh_model(route.project, route.version, from_peer)
        
        logger.debug(f"Received {len(msg.routes)} models from {from_peer}")
        
        # Forward with TTL decrement
        if msg.ttl > 1 and self._broadcast:
            forwarded = ModelMessage(
                type=MessageType.MODEL_AVAILABLE,
                from_node=msg.from_node,
                routes=msg.routes,
                timestamp=msg.timestamp,
                ttl=msg.ttl - 1,
                nonce=msg.nonce,
            )
            try:
                await self._broadcast(forwarded.to_json().encode())
            except Exception as e:
                logger.error(f"Failed to forward announcement: {e}")
    
    async def _handle_model_request(self, msg: ModelMessage, from_peer: str) -> None:
        """Handle MODEL_REQUEST - offer matching models."""
        if not msg.criteria:
            return
        
        # Find matching local models
        for entry in self.registry.list_local():
            if self._matches_criteria(entry.manifest, msg.criteria):
                route = ModelRoute.from_manifest(
                    entry.manifest,
                    nodes=[self.node_id]
                )
                await self.offer_model(msg.from_node, route)
        
        # Forward request
        if msg.ttl > 1 and self._broadcast:
            forwarded = ModelMessage(
                type=MessageType.MODEL_REQUEST,
                from_node=msg.from_node,
                criteria=msg.criteria,
                urgency=msg.urgency,
                timestamp=msg.timestamp,
                ttl=msg.ttl - 1,
                nonce=msg.nonce,
            )
            try:
                await self._broadcast(forwarded.to_json().encode())
            except Exception as e:
                logger.error(f"Failed to forward request: {e}")
    
    async def _handle_model_offer(self, msg: ModelMessage, from_peer: str) -> None:
        """Handle MODEL_OFFER - decide whether to accept."""
        if not msg.offer_route:
            return
        
        # Check if we need this model
        if self.registry.has_local(msg.offer_route.project, msg.offer_route.version):
            return  # Already have it
        
        # Accept the offer
        await self.accept_offer(from_peer, msg.offer_route)
        
        # TODO: Trigger actual pull via distributor
        logger.info(f"Accepted offer for {msg.offer_route.project} from {from_peer}")
    
    async def _handle_model_ack(self, msg: ModelMessage, from_peer: str) -> None:
        """Handle MODEL_ACK - start transfer if accepted."""
        if not msg.offer_route or not msg.accepted:
            return
        
        # TODO: Trigger actual push via distributor
        logger.info(f"Offer accepted for {msg.offer_route.project} by {from_peer}")
    
    async def _handle_sync_request(self, msg: ModelMessage, from_peer: str) -> None:
        """Handle SYNC_REQUEST - send full routing table."""
        await self._send_sync_response(msg.from_node, msg.nonce)
    
    async def _handle_sync_response(self, msg: ModelMessage, from_peer: str) -> None:
        """Handle SYNC_RESPONSE - populate routing table."""
        routes_received = 0
        
        for route in msg.full_routes:
            if await self.routing_table.add_or_update(route):
                routes_received += 1
                # Also update registry
                for node in route.nodes:
                    self.registry.update_mesh_model(route.project, route.version, node)
        
        logger.info(f"Sync response: received {routes_received} routes from {from_peer}")
        
        # Complete pending sync future
        if msg.nonce in self._pending_syncs:
            future = self._pending_syncs[msg.nonce]
            if not future.done():
                future.set_result(routes_received)
    
    def _matches_criteria(self, manifest: ModelManifest, criteria: Dict[str, Any]) -> bool:
        """Check if a manifest matches request criteria."""
        if "name" in criteria and manifest.name != criteria["name"]:
            return False
        
        if "capabilities" in criteria:
            if not all(c in manifest.capabilities for c in criteria["capabilities"]):
                return False
        
        if "max_size_bytes" in criteria:
            if manifest.size_bytes > criteria["max_size_bytes"]:
                return False
        
        return True
    
    # ==================== Nonce Handling ====================
    
    def _check_nonce(self, nonce: str, timestamp: float) -> bool:
        """Check if nonce is new (not a replay)."""
        now = time.time()
        
        # Reject old messages
        if abs(now - timestamp) > NONCE_CACHE_TTL_SEC:
            return False
        
        # Clean old entries
        expired = [
            n for n, t in self._nonce_cache.items()
            if now - t > NONCE_CACHE_TTL_SEC
        ]
        for n in expired:
            del self._nonce_cache[n]
        
        # Check for duplicate
        if nonce in self._nonce_cache:
            return False
        
        self._nonce_cache[nonce] = timestamp
        return True
    
    # ==================== Lifecycle ====================
    
    async def _announce_loop(self) -> None:
        """Periodic announcement loop."""
        while self._running:
            try:
                await self.announce()
            except Exception as e:
                logger.error(f"Model announcement failed: {e}")
            await asyncio.sleep(self.announce_interval)
    
    async def start(self) -> None:
        """Start the gossip protocol."""
        if self._running:
            return
        
        # Initialize routing table from local registry
        for entry in self.registry.list_local():
            route = ModelRoute.from_manifest(entry.manifest, nodes=[self.node_id])
            await self.routing_table.add_or_update(route)
        
        self._running = True
        self._task = asyncio.create_task(self._announce_loop())
        logger.info(f"Model gossip started with {len(self.routing_table.get_all())} local routes")
    
    async def stop(self) -> None:
        """Stop the gossip protocol."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Model gossip stopped")
    
    # ==================== Stats ====================
    
    def stats(self) -> dict:
        """Get gossip statistics."""
        return {
            "running": self._running,
            "routing_table": self.routing_table.stats(),
            "nonce_cache_size": len(self._nonce_cache),
            "pending_syncs": len(self._pending_syncs),
        }
