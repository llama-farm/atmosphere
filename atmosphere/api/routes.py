"""
API routes for Atmosphere.
"""

import asyncio
import logging
import platform
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .server import get_server, manager
from ..router.semantic import RouteAction
from ..registry.devices import get_device_registry, TrustLevel

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Request/Response Models ============

class RouteRequest(BaseModel):
    """Request to route an intent."""
    intent: str = Field(..., description="Natural language description of what to do")


class RouteResponse(BaseModel):
    """Response from routing."""
    action: str
    capability: Optional[str] = None
    score: float = 0.0
    hops: int = 0
    next_hop: Optional[str] = None
    node_id: Optional[str] = None


class ExecuteRequest(BaseModel):
    """Request to execute an intent."""
    intent: str = Field(..., description="What to do")
    kwargs: Dict[str, Any] = Field(default_factory=dict, description="Arguments")
    origin: Optional[str] = None
    hops: int = 0


class ExecuteResponse(BaseModel):
    """Response from execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0
    node_id: Optional[str] = None
    hops: int = 0
    capability: Optional[str] = None


class ChatMessage(BaseModel):
    """A chat message."""
    role: str = Field(..., description="user, assistant, or system")
    content: str = Field(..., description="Message content")


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str = Field(default="default", description="Model to use")
    messages: List[ChatMessage] = Field(..., description="Chat messages")
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: Optional[int] = None
    stream: bool = False


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[dict]
    usage: dict


class JoinRequest(BaseModel):
    """Request to join a mesh."""
    device: dict
    timestamp: int
    signature: str


class JoinResponse(BaseModel):
    """Response to join request."""
    success: bool
    mesh_id: Optional[str] = None
    mesh_name: Optional[str] = None
    token: Optional[dict] = None
    error: Optional[str] = None


class CapabilityInfo(BaseModel):
    """Information about a capability."""
    id: str
    label: str
    description: str
    handler: str
    models: List[str] = []


class MeshStatus(BaseModel):
    """Mesh network status."""
    mesh_id: Optional[str] = None
    mesh_name: Optional[str] = None
    node_count: int = 0
    peer_count: int = 0
    capabilities: List[str] = []
    is_founder: bool = False


# ============ Routes ============

@router.post("/route", response_model=RouteResponse)
async def route_intent(request: RouteRequest):
    """
    Route an intent to the best capability.
    
    Uses semantic matching with cost-aware ranking:
    - Finds capabilities matching the intent
    - Ranks by: (similarity_score / node_cost)
    - Returns best option with cost info
    
    Returns routing decision without executing.
    """
    server = get_server()
    if not server or not server.router:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    result = await server.router.route(request.intent)
    
    # Get cost info for the selected node
    node_cost = None
    if result.capability:
        try:
            from ..cost.collector import get_cost_collector
            from ..cost.model import compute_node_cost, WorkRequest
            collector = get_cost_collector()
            factors = collector.collect()
            node_cost = compute_node_cost(factors, WorkRequest())
        except Exception:
            pass
    
    return RouteResponse(
        action=result.action.value,
        capability=result.capability.label if result.capability else None,
        score=result.score,
        hops=result.hops,
        next_hop=result.next_hop,
        node_id=server.node.node_id if result.action == RouteAction.PROCESS_LOCAL and server.node else result.via_node
    )


class ProjectRouteRequest(BaseModel):
    """Request to route to a LlamaFarm project."""
    intent: str = Field(..., description="User intent/query")
    messages: Optional[List[ChatMessage]] = Field(default=None, description="Optional chat messages for context")


class ProjectRouteResponse(BaseModel):
    """Response from project routing."""
    project: Optional[str] = None
    namespace: Optional[str] = None
    name: Optional[str] = None
    score: float = 0.0
    tier: str = "fallback"
    domain: Optional[str] = None
    reason: str = ""


@router.post("/route/project", response_model=ProjectRouteResponse)
async def route_to_project(request: ProjectRouteRequest):
    """
    Route an intent to the best LlamaFarm project using FastProjectRouter.
    
    Uses semantic matching with 3-tier cascade:
    1. Embedding match (neural or hash-based)
    2. Hash fallback (character n-gram matching)  
    3. Keyword match (pure keyword overlap)
    
    Returns the best matching project without executing.
    """
    server = get_server()
    if not server:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    # Use FastProjectRouter if available
    fast_router = getattr(server, '_fast_router', None)
    if not fast_router:
        raise HTTPException(status_code=503, detail="FastProjectRouter not initialized")
    
    # Build messages for routing
    if request.messages:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
    else:
        messages = [{"role": "user", "content": request.intent}]
    
    # Route using FastProjectRouter
    result = fast_router.route("auto", messages)
    
    return ProjectRouteResponse(
        project=result.project.model_path if result.project else None,
        namespace=result.project.namespace if result.project else None,
        name=result.project.name if result.project else None,
        score=result.score,
        tier=result.tier.value,
        domain=result.project.domain if result.project else None,
        reason=result.reason
    )


@router.post("/route/project/test")
async def test_project_routing(request: ProjectRouteRequest):
    """
    Test all cascade tiers for project routing.
    
    Useful for debugging and understanding routing decisions.
    Returns detailed information about each routing tier.
    """
    server = get_server()
    if not server:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    fast_router = getattr(server, '_fast_router', None)
    if not fast_router:
        raise HTTPException(status_code=503, detail="FastProjectRouter not initialized")
    
    # Test cascade
    return fast_router.test_cascade(request.intent)


@router.post("/execute", response_model=ExecuteResponse)
async def execute_intent(request: ExecuteRequest):
    """
    Route and execute an intent.
    
    Returns the execution result.
    """
    server = get_server()
    if not server or not server.executor:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    result = await server.executor.execute(request.intent, **request.kwargs)
    
    return ExecuteResponse(
        success=result.success,
        data=result.data,
        error=result.error,
        execution_time_ms=result.execution_time_ms,
        node_id=result.node_id,
        hops=result.hops,
        capability=result.capability
    )


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completion endpoint.
    
    Routes to the best available LLM.
    """
    server = get_server()
    if not server or not server.executor:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    # Convert messages to dict format
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    
    # Execute chat
    result = await server.executor.execute_capability(
        "chat",
        messages=messages,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    # Format as OpenAI response
    response_message = result.data.get("message", {})
    
    # Extract routing info (THE CROWN JEWEL!)
    routing_info = result.data.get("_routing")
    backend = result.data.get("_backend")
    
    response_dict = {
        "id": f"chatcmpl-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{
            "index": 0,
            "message": response_message,
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }
    
    # Add routing info (THE CROWN JEWEL!)
    if routing_info:
        response_dict["routing"] = routing_info
    if backend:
        response_dict["backend"] = backend
    
    return JSONResponse(content=response_dict)


@router.get("/capabilities", response_model=List[CapabilityInfo])
async def list_capabilities():
    """List all available capabilities."""
    server = get_server()
    if not server or not server.router:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    caps = []
    for cap in server.router.local_capabilities.values():
        caps.append(CapabilityInfo(
            id=cap.id,
            label=cap.label,
            description=cap.description,
            handler=cap.handler,
            models=cap.models
        ))
    
    return caps


@router.get("/mesh/status", response_model=MeshStatus)
async def mesh_status():
    """Get mesh network status."""
    server = get_server()
    if not server:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    mesh = server.node.mesh if server.node else None
    
    # Count peers from both local discovery and relay
    local_peers = len(server.discovery.peers) if server.discovery else 0
    relay_peers = len(getattr(server, '_relay_peers', {}))
    total_peers = local_peers + relay_peers
    
    # Node count: self + peers
    node_count = 1 + total_peers
    
    return MeshStatus(
        mesh_id=mesh.mesh_id if mesh else None,
        mesh_name=mesh.name if mesh else None,
        node_count=node_count,
        peer_count=total_peers,
        capabilities=list(server.router.local_capabilities.keys()) if server.router else [],
        is_founder=server.node.is_founder if server.node else False
    )


@router.post("/mesh/join", response_model=JoinResponse)
async def join_mesh(request: JoinRequest):
    """
    Handle a join request from another node.
    
    Only founders can approve join requests.
    """
    server = get_server()
    if not server or not server.node:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    if not server.node.is_founder:
        raise HTTPException(
            status_code=403,
            detail="This node is not a mesh founder"
        )
    
    # Issue token
    from ..auth.tokens import TokenIssuer
    
    mesh = server.node.mesh
    identity = server.node.identity
    
    issuer = TokenIssuer(mesh, identity)
    
    device = request.device
    token = issuer.issue_token(
        device_id=device["device_id"],
        device_public_key=device["public_key"],
        device_name=device["name"],
        hardware_hash=device["hardware_hash"],
        capabilities=device.get("capabilities", []),
        tier=device.get("tier", "compute"),
        validity_hours=24
    )
    
    return JoinResponse(
        success=True,
        mesh_id=mesh.mesh_id,
        mesh_name=mesh.name,
        token=token.to_dict()
    )


@router.get("/mesh/peers")
async def list_peers():
    """List all discovered peers (local mDNS + relay)."""
    server = get_server()
    if not server:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    peers = []
    
    # Add local mDNS-discovered peers
    if server.discovery:
        for p in server.discovery.peers:
            peers.append({
                "node_id": p.node_id,
                "name": p.name,
                "address": p.address,
                "mesh_id": p.mesh_id,
                "capabilities": p.capabilities,
                "via": "mdns"
            })
    
    # Add relay-connected peers
    relay_peers = getattr(server, '_relay_peers', {})
    for node_id, peer_info in relay_peers.items():
        # Avoid duplicates (same node via both mdns and relay)
        if not any(p.get("node_id") == node_id for p in peers):
            peers.append({
                "node_id": node_id,
                "name": peer_info.get("name", node_id[:8]),
                "address": None,  # No direct address for relay peers
                "mesh_id": server.node.mesh.mesh_id if server.node and server.node.mesh else None,
                "capabilities": peer_info.get("capabilities", []),
                "via": "relay",
                "is_founder": peer_info.get("is_founder", False)
            })
    
    return {
        "peers": peers,
        "count": len(peers),
        "sources": {
            "mdns": len(server.discovery.peers) if server.discovery else 0,
            "relay": len(relay_peers)
        }
    }


@router.get("/mesh/topology")
async def mesh_topology():
    """
    Get mesh topology for visualization.
    
    Returns nodes and their connections, including cost data.
    """
    server = get_server()
    if not server:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    nodes = []
    links = []
    
    # Get local node cost
    local_cost = None
    factors = None
    try:
        from ..cost.collector import get_cost_collector
        from ..cost.model import compute_node_cost, WorkRequest
        collector = get_cost_collector()
        factors = collector.collect()
        local_cost = compute_node_cost(factors, WorkRequest())
    except Exception as e:
        logger.error(f"Failed to get local cost: {e}")
        local_cost = 1.0
    
    # Add this node
    this_node = {
        "id": server.node.node_id if server.node else "local",
        "name": server.node.identity.name if server.node else platform.node(),
        "status": "active",
        "isLeader": server.node.is_founder if server.node else True,
        "type": "llm",  # Default type
        "triggers": [],
        "tools": list(server.router.local_capabilities.keys()) if server.router else [],
        "cost": local_cost,
        "costFactors": factors.to_dict() if factors else None,
    }
    nodes.append(this_node)
    
    # Add discovered peers with their cost data (if available via gossip)
    peer_costs = {}
    try:
        # Try to get cost gossip state from server
        if hasattr(server, 'cost_gossip_state') and server.cost_gossip_state:
            for peer_factors in server.cost_gossip_state.get_fresh_costs():
                peer_costs[peer_factors.node_id] = {
                    "cost": compute_node_cost(peer_factors, WorkRequest()),
                    "factors": peer_factors.to_dict()
                }
    except Exception:
        pass
    
    # Track added node IDs to avoid duplicates
    added_node_ids = {this_node["id"]}
    
    # Add mDNS-discovered peers
    if server.discovery:
        for peer in server.discovery.peers:
            if peer.node_id not in added_node_ids:
                peer_cost_data = peer_costs.get(peer.node_id, {})
                nodes.append({
                    "id": peer.node_id,
                    "name": peer.name,
                    "status": "active",
                    "isLeader": False,
                    "type": "llm",
                    "triggers": [],
                    "tools": peer.capabilities,
                    "cost": peer_cost_data.get("cost"),
                    "costFactors": peer_cost_data.get("factors"),
                    "via": "mdns",
                })
                # Add link from this node to peer
                links.append({
                    "source": this_node["id"],
                    "target": peer.node_id,
                })
                added_node_ids.add(peer.node_id)
    
    # Add relay-connected peers
    relay_peers = getattr(server, '_relay_peers', {})
    for node_id, peer_info in relay_peers.items():
        if node_id not in added_node_ids:
            peer_cost_data = peer_costs.get(node_id, {})
            nodes.append({
                "id": node_id,
                "name": peer_info.get("name", node_id[:8]),
                "status": "active",
                "isLeader": peer_info.get("is_founder", False),
                "type": "llm",
                "triggers": [],
                "tools": peer_info.get("capabilities", []),
                "cost": peer_cost_data.get("cost"),
                "costFactors": peer_cost_data.get("factors"),
                "via": "relay",
            })
            # Add link from this node to relay peer
            links.append({
                "source": this_node["id"],
                "target": node_id,
                "type": "relay",  # Mark as relay connection
            })
            added_node_ids.add(node_id)
    
    return {
        "nodes": nodes,
        "links": links,
        "mesh_id": server.node.mesh.mesh_id if server.node and server.node.mesh else None,
        "mesh_name": server.node.mesh.name if server.node and server.node.mesh else "Local Mesh",
    }


@router.get("/mesh/transports")
async def get_transport_status():
    """
    Get resilient transport status for all peer connections.
    
    Shows:
    - All active transports per peer (LAN, Relay, BLE, etc.)
    - Real-time latency and health metrics for each
    - Which transport is currently "best" (lowest latency + highest reliability)
    - Failover history and reconnection attempts
    
    Design Philosophy:
    - ALL available transports are connected simultaneously
    - Messages route through BEST transport (by score)
    - Instant failover when primary fails (already connected to alternatives)
    - Continuous health monitoring keeps connections warm
    """
    server = get_server()
    if not server:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    # Check if resilient transport manager is available
    resilient_manager = getattr(server, 'resilient_transport', None)
    
    transports = {
        "node_id": server.node.node_id if server.node else "unknown",
        "transport_types": ["lan", "relay", "ble", "wifi_direct", "matter"],
        "enabled": {
            "lan": True,
            "relay": bool(getattr(server.config, 'relay_url', None)),
            "ble": False,  # Future
            "wifi_direct": False,  # Future
            "matter": False,  # Future
        },
        "global_stats": {
            "messages_sent": 0,
            "messages_received": 0,
            "failovers": 0,
            "reconnects": 0,
        },
        "peers": {},
    }
    
    if resilient_manager:
        # Use resilient transport manager status
        status = resilient_manager.get_status()
        transports["global_stats"] = status.get("stats", transports["global_stats"])
        transports["peers"] = status.get("peers", {})
    else:
        # Fallback: build status from existing connections
        # mDNS peers
        if server.discovery:
            for peer in server.discovery.peers:
                peer_id = peer.get("node_id", peer.get("id", "unknown"))
                transports["peers"][peer_id] = {
                    "reachable": True,
                    "transports": {
                        "lan": {
                            "state": "connected",
                            "latency_ms": None,  # Would need to ping
                            "score": 0.9,  # LAN assumed fast
                        }
                    },
                    "best_transport": "lan",
                }
        
        # Relay peers
        relay_peers = getattr(server, '_relay_peers', {})
        for peer_id, peer_info in relay_peers.items():
            if peer_id not in transports["peers"]:
                transports["peers"][peer_id] = {
                    "reachable": True,
                    "transports": {},
                    "best_transport": "relay",
                }
            transports["peers"][peer_id]["transports"]["relay"] = {
                "state": "connected",
                "latency_ms": None,
                "score": 0.5,  # Relay assumed slower
            }
    
    # Add relay server connection status
    transports["relay"] = {
        "connected": bool(server.relay_client and server.relay_client.ws and not server.relay_client.ws.closed),
        "url": getattr(server.config, 'relay_url', None),
        "peer_count": len(getattr(server, '_relay_peers', {})),
    }
    
    return transports


@router.post("/mesh/token")
async def generate_invite_token():
    """
    Generate an invite token for others to join the mesh.
    
    Includes multiple endpoints for connectivity:
    - local: For same-network connections (fastest)
    - public: For internet connections (requires port forwarding)
    - relay: For fallback when direct connection fails
    
    Token is cryptographically signed by the mesh founder.
    """
    server = get_server()
    if not server or not server.node:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    import json
    import urllib.parse
    from ..network import gather_network_info
    from ..auth.tokens import MeshToken
    
    # Get mesh info
    mesh = server.node.mesh if server.node else None
    if not mesh:
        raise HTTPException(status_code=400, detail="Not connected to any mesh")
    
    # Get the mesh master keypair for signing (only founders have this)
    mesh_keypair = getattr(mesh, '_master_keypair', None)
    if not mesh_keypair:
        raise HTTPException(status_code=403, detail="Only mesh founders can issue tokens")
    
    node_id = server.node.node_id if server.node else "unknown"
    
    # Create a properly signed token
    mesh_token = MeshToken.create(
        mesh_id=mesh.mesh_id,
        issuer_keypair=mesh_keypair,
        issuer_id=node_id,
        node_id=None,  # Open invite (any node can use)
        capabilities=["participant", "llm", "embeddings"],
        ttl_seconds=86400,  # 24 hours
    )
    
    # Get token dict for JSON serialization
    token_dict = mesh_token.to_dict()
    
    # Also generate a short display code for easy reference
    token_display = f"ATM-{mesh_token.nonce[:8].upper()}"
    
    # Gather network info (local IP + STUN discovery for public IP)
    port = 11451  # Default Atmosphere port
    try:
        network_info = await gather_network_info(port)
        local_ip = network_info.local_ip
        public_endpoint = network_info.public_endpoint
    except Exception as e:
        logger.warning(f"Network discovery failed: {e}")
        # Fallback to basic local IP
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            local_ip = "127.0.0.1"
        public_endpoint = None
    
    mesh = server.node.mesh if server.node else None
    
    # Build multi-path endpoints
    endpoints = {
        "local": f"ws://{local_ip}:{port}",
    }
    
    # Add public endpoint if discovered via STUN
    if public_endpoint and public_endpoint.is_public:
        endpoints["public"] = f"ws://{public_endpoint.ip}:{port}"
    
    # Add relay endpoints if configured (config takes precedence over env var)
    import os
    relay_url = None
    if server.config and server.config.relay_url:
        relay_url = server.config.relay_url
    else:
        relay_url = os.environ.get("ATMOSPHERE_RELAY_URL")
    
    if relay_url:
        mesh_id = mesh.mesh_id if mesh else "default"
        # Ensure wss:// for secure relay
        if relay_url.startswith("https://"):
            relay_url = relay_url.replace("https://", "wss://")
        elif relay_url.startswith("http://"):
            relay_url = relay_url.replace("http://", "ws://")
        endpoints["relay"] = f"{relay_url}/relay/{mesh_id}"
    
    # Build comprehensive invite payload
    mesh_name = mesh.name if mesh else "local"
    mesh_id = mesh.mesh_id
    node_name = server.node.name if server.node else "unknown"
    expires_at = mesh_token.expires_at
    
    # Get capabilities this mesh offers
    capabilities = []
    if server.node:
        try:
            caps = server.node.capabilities.list() if hasattr(server.node, 'capabilities') else []
            capabilities = [c.name if hasattr(c, 'name') else str(c) for c in caps[:10]]  # Limit for QR size
        except:
            capabilities = []
    
    # Get mesh public key for verification
    mesh_public_key = mesh_keypair.public_key_b64()
    
    # Comprehensive invite object - everything needed to join
    # v2 includes the full signed token
    invite = {
        "v": 2,  # Protocol version - v2 has signed token
        "t": token_dict,  # Short key for smaller QR
        "td": token_display,
        "m": {
            "i": mesh_id,
            "n": mesh_name,
            "f": node_name,
            "fi": node_id,
            "pk": mesh_public_key,
        },
        "e": endpoints,
        "c": capabilities,
        "n": {
            "l": local_ip,
            "p": public_endpoint.ip if public_endpoint else None,
            "n": public_endpoint.ip != local_ip if public_endpoint else True,
        },
        "ex": expires_at,
        "cr": int(time.time()),
    }
    
    # Compact JSON for QR code (no spaces)
    invite_json = json.dumps(invite, separators=(',', ':'))
    
    # QR data is the full invite as base64 for compactness
    import base64
    invite_b64 = base64.urlsafe_b64encode(invite_json.encode()).decode()
    qr_data = f"atmosphere://join/{invite_b64}"
    
    # Also provide legacy URL version (with encoded token)
    endpoints_json = urllib.parse.quote(json.dumps(endpoints))
    token_json = urllib.parse.quote(json.dumps(token_dict))
    qr_data_legacy = f"atmosphere://join?token={token_json}&mesh={mesh_name}&endpoints={endpoints_json}"
    
    # Primary endpoint for legacy compatibility
    primary_endpoint = endpoints.get("public") or endpoints.get("local", f"ws://{local_ip}:{port}")
    
    return {
        # Full invite object
        "invite": invite,
        # Individual fields for convenience
        "token": token_dict,  # Full signed token for API callers
        "token_display": token_display,  # Short human-readable code
        "mesh_id": mesh_id,
        "mesh_name": mesh_name,
        "mesh_public_key": mesh_public_key,  # For verification
        "endpoints": endpoints,
        "capabilities": capabilities,
        "network_info": {
            "local_ip": local_ip,
            "public_ip": public_endpoint.ip if public_endpoint else None,
            "is_behind_nat": public_endpoint.ip != local_ip if public_endpoint else True,
            "stun_source": public_endpoint.source if public_endpoint else None,
        },
        # Legacy single endpoint for backwards compatibility
        "endpoint": primary_endpoint,
        "expires_at": expires_at,
        # QR data - comprehensive base64 version
        "qr_data": qr_data,
        # Legacy QR format for older clients
        "qr_data_legacy": qr_data_legacy,
    }


@router.get("/agents")
async def list_agents():
    """
    List registered agents and their status.
    """
    server = get_server()
    if not server:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    # For now, return demo agents based on capabilities
    # In a full implementation, this would track actual registered agents
    agents = []
    
    if server.router:
        for cap_id, cap in server.router.local_capabilities.items():
            agents.append({
                "id": f"agent-{cap_id[:8]}",
                "name": cap.label,
                "status": "running",
                "capabilities": [cap_id],
                "uptime": int(time.time()) % 86400,  # Demo uptime
                "last_activity": int(time.time()) - 60,
            })
    
    # Add a main orchestrator agent
    agents.insert(0, {
        "id": "orchestrator",
        "name": "Main Orchestrator",
        "status": "running",
        "capabilities": ["routing", "coordination"],
        "uptime": int(time.time()) % 86400,
        "last_activity": int(time.time()) - 10,
    })
    
    return {"agents": agents}


@router.patch("/agents/{agent_id}")
async def update_agent(agent_id: str, status: str = None):
    """Update agent status (pause/resume)."""
    # Demo implementation - would actually control agents
    return {"success": True, "agent_id": agent_id, "status": status or "running"}


@router.get("/projects")
async def list_projects(namespace: str = None, discoverable_only: bool = False):
    """
    List LlamaFarm projects exposed to the mesh.
    
    Args:
        namespace: Filter by namespace
        discoverable_only: If true, only return discoverable projects
        
    Returns:
        List of projects with their capabilities
    """
    server = get_server()
    if not server:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    try:
        from ..discovery.llamafarm import LlamaFarmBackend, LlamaFarmConfig
        
        backend = LlamaFarmBackend(LlamaFarmConfig())
        
        if discoverable_only or namespace == "discoverable":
            projects = await backend.list_discoverable_projects()
        elif namespace:
            projects = await backend.list_projects(namespace=namespace)
        else:
            projects = await backend.list_projects()
        
        await backend.close()
        
        # Format for mesh exposure
        formatted = []
        for p in projects:
            ns = p.get("namespace", "default")
            name = p.get("name", "")
            formatted.append({
                "id": f"{ns}/{name}",  # Composite ID for invoke endpoint
                "name": name,
                "description": p.get("description", ""),
                "namespace": ns,
                "type": p.get("type", "chat"),
                "system_prompt": p.get("system_prompt", "")[:200] + "..." if len(p.get("system_prompt", "")) > 200 else p.get("system_prompt", ""),
                "capabilities": ["llm", "chat"],
                "mesh_exposed": ns == "discoverable",
            })
        
        return {"projects": formatted, "count": len(formatted)}
    
    except Exception as e:
        logger.warning(f"Failed to fetch projects: {e}")
        return {"projects": [], "count": 0, "error": str(e)}


class ProjectInvokeRequest(BaseModel):
    """Request to invoke a LlamaFarm project."""
    prompt: str
    context: Optional[List[dict]] = None


@router.post("/projects/{namespace}/{project_name}/invoke")
async def invoke_project(namespace: str, project_name: str, request: ProjectInvokeRequest):
    """
    Invoke a LlamaFarm project with a prompt.
    
    Args:
        namespace: Project namespace (e.g., 'discoverable')
        project_name: Project name (e.g., 'llama-expert-14')
        request: Prompt and optional context
        
    Returns:
        Project response
    """
    server = get_server()
    if not server:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    try:
        import aiohttp
        
        messages = request.context or []
        messages.append({"role": "user", "content": request.prompt})
        
        # Call LlamaFarm project endpoint directly
        payload = {"messages": messages}
        
        async with aiohttp.ClientSession() as session:
            url = f"http://localhost:14345/v1/projects/{namespace}/{project_name}/chat/completions"
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise HTTPException(status_code=resp.status, detail=error)
                result = await resp.json()
        
        return {
            "success": True,
            "project_id": f"{namespace}/{project_name}",
            "response": result["choices"][0]["message"]["content"],
            "usage": result.get("usage", {})
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to invoke project {namespace}/{project_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost/current")
async def get_current_cost():
    """
    Get current cost factors for this node.
    
    Always collects fresh system metrics - no caching.
    """
    try:
        from ..cost.collector import get_cost_collector
        from ..cost.model import compute_node_cost, WorkRequest
        collector = get_cost_collector()
        factors = collector.collect()
        
        # Calculate cost multiplier
        cost = compute_node_cost(factors, WorkRequest())
        
        return {
            "node_id": factors.node_id,
            "timestamp": factors.timestamp,
            "power": {
                "on_battery": factors.on_battery,
                "battery_percent": factors.battery_percent,
                "plugged_in": factors.plugged_in,
            },
            "compute": {
                "cpu_load": factors.cpu_load,
                "gpu_load": factors.gpu_load,
                "gpu_estimated": factors.gpu_estimated,
                "memory_percent": factors.memory_percent,
                "memory_available_gb": factors.memory_available_gb,
            },
            "network": {
                "bandwidth_mbps": factors.bandwidth_mbps,
                "is_metered": factors.is_metered,
                "latency_ms": factors.latency_ms,
            },
            "cost_multiplier": cost,
        }
    except Exception as e:
        logger.error(f"Failed to collect cost factors: {e}")
        # Return defaults
        return {
            "node_id": platform.node(),
            "timestamp": time.time(),
            "power": {
                "on_battery": False,
                "battery_percent": 100.0,
                "plugged_in": True,
            },
            "compute": {
                "cpu_load": 0.1,
                "gpu_load": 0.0,
                "gpu_estimated": True,
                "memory_percent": 50.0,
                "memory_available_gb": 8.0,
            },
            "network": {
                "bandwidth_mbps": None,
                "is_metered": False,
                "latency_ms": None,
            },
            "cost_multiplier": 1.0,
        }


class ApprovalConfig(BaseModel):
    """Approval configuration model."""
    models: dict = Field(default_factory=dict)
    hardware: dict = Field(default_factory=dict)
    privacy: dict = Field(default_factory=dict)
    access: dict = Field(default_factory=dict)


@router.get("/approval/config")
async def get_approval_config():
    """Get current approval configuration."""
    import yaml
    from pathlib import Path
    
    config_path = Path.home() / ".atmosphere" / "approval.yaml"
    
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        except:
            config = {}
    else:
        # Return defaults
        config = {
            "models": {
                "ollama": {"enabled": True, "selected": []},
                "llamafarm": {"enabled": True, "selected": []},
            },
            "hardware": {
                "gpu": {"enabled": True, "max_vram_percent": 80},
                "cpu": {"enabled": True, "max_cores": None},
            },
            "privacy": {
                "camera": {"enabled": False, "mode": "off"},
                "microphone": {"enabled": False, "mode": "off"},
                "screen": {"enabled": False},
            },
            "access": {
                "mesh_allowlist": [],
                "mesh_denylist": [],
                "rate_limit": {"enabled": False, "requests_per_minute": 60},
            },
        }
    
    return config


@router.post("/approval/config")
async def save_approval_config(config: ApprovalConfig):
    """Save approval configuration."""
    import yaml
    from pathlib import Path
    
    config_dir = Path.home() / ".atmosphere"
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / "approval.yaml"
    
    with open(config_path, 'w') as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False)
    
    return {"success": True, "message": "Configuration saved"}


@router.get("/embeddings")
async def generate_embeddings(text: str = Query(..., description="Text to embed")):
    """Generate text embeddings."""
    server = get_server()
    if not server or not server.router:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    vector = await server.router.embedding_engine.embed(text)
    
    return {
        "embedding": vector.tolist(),
        "dimension": len(vector)
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    server = get_server()
    return {
        "status": "healthy" if server and server._running else "starting",
        "node_id": server.node.node_id if server and server.node else None
    }


# ============ Permissions Endpoints ============

@router.get("/permissions/status")
async def get_permissions_status():
    """
    Get macOS permission status for privacy-sensitive capabilities.
    
    Returns the current status of Camera, Microphone, and Screen Recording
    permissions, along with instructions for enabling them.
    """
    import subprocess
    
    def check_permission_via_test(service: str) -> str:
        """
        Check permission by attempting to access the resource.
        More reliable than TCC database queries.
        """
        if platform.system() != "Darwin":
            return "not_applicable"
        
        if service == "camera":
            try:
                # Try to access camera via AVFoundation (Python)
                # If permission not granted, this will fail
                result = subprocess.run(
                    ["python3", "-c", """
import AVFoundation
devices = AVFoundation.AVCaptureDevice.devicesWithMediaType_(AVFoundation.AVMediaTypeVideo)
print('granted' if devices else 'no_devices')
"""],
                    capture_output=True, text=True, timeout=5
                )
                if "granted" in result.stdout:
                    return "granted"
                elif "no_devices" in result.stdout:
                    return "no_devices"
                return "not_determined"
            except Exception:
                # Fallback: check if imagesnap works
                try:
                    result = subprocess.run(
                        ["imagesnap", "-l"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0 and "Video Devices" in result.stdout:
                        return "granted"
                    return "not_determined"
                except FileNotFoundError:
                    return "unknown"
                except Exception:
                    return "unknown"
        
        elif service == "microphone":
            try:
                # Try to list audio input devices
                result = subprocess.run(
                    ["python3", "-c", """
import AVFoundation
devices = AVFoundation.AVCaptureDevice.devicesWithMediaType_(AVFoundation.AVMediaTypeAudio)
print('granted' if devices else 'no_devices')
"""],
                    capture_output=True, text=True, timeout=5
                )
                if "granted" in result.stdout:
                    return "granted"
                return "not_determined"
            except Exception:
                return "unknown"
        
        elif service == "screen":
            try:
                # Check if we can take a screenshot
                result = subprocess.run(
                    ["screencapture", "-x", "-c"],  # Capture to clipboard silently
                    capture_output=True, text=True, timeout=5
                )
                # If this fails with permission error, screen recording is not allowed
                return "granted" if result.returncode == 0 else "denied"
            except Exception:
                return "unknown"
        
        return "unknown"
    
    # Get permission status for each capability
    camera_status = check_permission_via_test("camera")
    mic_status = check_permission_via_test("microphone")
    screen_status = check_permission_via_test("screen")
    
    return {
        "platform": platform.system(),
        "permissions": {
            "camera": {
                "status": camera_status,
                "settings_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
                "instructions": "System Settings → Privacy & Security → Camera → Enable for Terminal/Python"
            },
            "microphone": {
                "status": mic_status,
                "settings_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
                "instructions": "System Settings → Privacy & Security → Microphone → Enable for Terminal/Python"
            },
            "screen_recording": {
                "status": screen_status,
                "settings_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
                "instructions": "System Settings → Privacy & Security → Screen Recording → Enable for Terminal/Python"
            }
        },
        "timestamp": time.time()
    }


@router.post("/permissions/open-settings")
async def open_permission_settings(permission: str = Query(..., description="camera, microphone, or screen_recording")):
    """
    Open macOS System Settings to the appropriate privacy pane.
    """
    import subprocess
    
    if platform.system() != "Darwin":
        raise HTTPException(status_code=400, detail="This endpoint is only available on macOS")
    
    settings_urls = {
        "camera": "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
        "microphone": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
        "screen_recording": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    }
    
    if permission not in settings_urls:
        raise HTTPException(status_code=400, detail=f"Unknown permission: {permission}")
    
    try:
        subprocess.run(["open", settings_urls[permission]], check=True)
        return {"success": True, "message": f"Opened settings for {permission}"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to open settings: {e}")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates and mesh communication.
    
    Handles:
    - join: Authenticate and join the mesh
    - llm_request: Route LLM prompts to LlamaFarm/Ollama
    - intent: Route intents through the semantic router
    - Mesh status, gossip messages, cost updates
    """
    await manager.connect(websocket)
    try:
        # Send initial status
        server = get_server()
        if server:
            mesh = server.node.mesh if server.node else None
            await websocket.send_json({
                "type": "mesh_status",
                "data": {
                    "mesh_id": mesh.mesh_id if mesh else None,
                    "mesh_name": mesh.name if mesh else None,
                    "node_count": len(mesh.founding_members) if mesh else 0,
                    "peer_count": len(server.discovery.peers) if server.discovery else 0,
                    "capabilities": list(server.router.local_capabilities.keys()) if server.router else [],
                }
            })
            
            # Send initial cost data
            try:
                from ..cost.collector import get_cost_collector
                from ..cost.model import compute_node_cost, WorkRequest
                collector = get_cost_collector()
                factors = collector.collect()
                cost = compute_node_cost(factors, WorkRequest())
                await websocket.send_json({
                    "type": "cost_update",
                    "node_id": factors.node_id,
                    "cost": cost,
                    "factors": factors.to_dict(),
                    "timestamp": time.time()
                })
            except Exception as e:
                logger.error(f"Failed to send initial cost: {e}")
        
        # Handle incoming messages and periodic updates concurrently
        async def handle_incoming_messages():
            """Handle incoming WebSocket messages from clients."""
            while True:
                try:
                    data = await websocket.receive_json()
                    msg_type = data.get("type")
                    request_id = data.get("request_id")
                    
                    if msg_type == "join":
                        # Handle mesh join request
                        token = data.get("token")
                        node_id = data.get("node_id", "unknown")
                        node_name = data.get("name", "unknown")
                        capabilities = data.get("capabilities", [])
                        mesh = server.node.mesh if server and server.node else None
                        
                        # Log join (token may be dict or string)
                        token_preview = str(token)[:30] if token else 'none'
                        logger.info(f"Client {node_name} ({node_id}) joining mesh with token: {token_preview}...")
                        await websocket.send_json({
                            "type": "joined",
                            "mesh": mesh.name if mesh else "home-mesh",
                            "mesh_id": mesh.mesh_id if mesh else "default"
                        })
                        
                    elif msg_type == "llm_request":
                        # Handle LLM request - route to LlamaFarm/Ollama
                        prompt = data.get("prompt", "")
                        model = data.get("model")
                        
                        logger.info(f"LLM request received: {prompt[:50]}...")
                        
                        try:
                            response = await call_llamafarm_llm(prompt, model)
                            await websocket.send_json({
                                "type": "llm_response",
                                "response": response,
                                "request_id": request_id
                            })
                            logger.info(f"LLM response sent for request {request_id}")
                        except Exception as e:
                            logger.error(f"LLM request failed: {e}")
                            await websocket.send_json({
                                "type": "error",
                                "message": str(e),
                                "request_id": request_id
                            })
                    
                    elif msg_type == "pong":
                        # Pong response - connection is alive
                        pass
                    
                    elif msg_type == "intent":
                        # Handle intent routing
                        intent_text = data.get("text", "")
                        if server and server.executor:
                            try:
                                result = await server.executor.execute(intent_text)
                                await websocket.send_json({
                                    "type": "intent_response",
                                    "success": result.success,
                                    "data": result.data,
                                    "error": result.error,
                                    "request_id": request_id
                                })
                            except Exception as e:
                                await websocket.send_json({
                                    "type": "error",
                                    "message": str(e),
                                    "request_id": request_id
                                })
                    
                    else:
                        logger.debug(f"Unknown message type: {msg_type}")
                        
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "message": str(e)
                        })
                    except:
                        break
        
        async def send_periodic_updates():
            """Send periodic cost updates and keepalive pings."""
            last_cost_broadcast = time.time()
            while True:
                try:
                    await asyncio.sleep(10)  # Check every 10 seconds
                    
                    now = time.time()
                    
                    # Broadcast cost update every 30 seconds
                    if now - last_cost_broadcast >= 30:
                        try:
                            from ..cost.collector import get_cost_collector
                            from ..cost.model import compute_node_cost, WorkRequest
                            collector = get_cost_collector()
                            factors = collector.collect()
                            cost = compute_node_cost(factors, WorkRequest())
                            
                            cost_message = {
                                "type": "cost_update",
                                "node_id": factors.node_id,
                                "cost": cost,
                                "factors": factors.to_dict(),
                                "timestamp": now
                            }
                            
                            await websocket.send_json(cost_message)
                            last_cost_broadcast = now
                        except Exception as e:
                            logger.error(f"Failed to send cost update: {e}")
                    
                    # Send ping to keep connection alive
                    await websocket.send_json({"type": "ping", "timestamp": now})
                    
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Periodic update error: {e}")
                    break
        
        # Run both message handler and periodic updates concurrently
        await asyncio.gather(
            handle_incoming_messages(),
            send_periodic_updates(),
            return_exceptions=True
        )
        
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def call_llamafarm_llm(prompt: str, model: str = None) -> str:
    """
    Call LlamaFarm or Ollama to get an LLM response.
    
    Tries LlamaFarm first (port 14345), falls back to Ollama (port 11434).
    """
    import httpx
    
    # Default model
    if not model:
        model = "llama3.2"
    
    # Try LlamaFarm first
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "http://localhost:14345/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"LlamaFarm request failed, trying Ollama: {e}")
    
    # Fall back to Ollama direct
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["message"]["content"]
            else:
                raise Exception(f"Ollama returned status {resp.status_code}")
    except Exception as e:
        logger.error(f"Both LlamaFarm and Ollama failed: {e}")
        raise Exception(f"LLM request failed: {e}")


@router.get("/integrations")
async def list_integrations(all: bool = False):
    """
    Discover and list available backend integrations.
    
    Args:
        all: If True, show all LlamaFarm namespaces. 
             If False (default), only show "discoverable" namespace.
    
    Scans for:
    - LlamaFarm (port 14345) - filtered to discoverable namespace by default
    - Ollama (port 11434)
    - Other discovered backends via mDNS
    """
    import socket
    import requests
    from ..adapters.llamafarm import LlamaFarmDiscovery
    
    integrations = []
    
    # Check LlamaFarm with filtered discovery
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 14345))
        sock.close()
        
        if result == 0:
            # Use namespace filter: None = show all, "discoverable" = filtered
            namespace = None if all else "discoverable"
            discovery = LlamaFarmDiscovery(namespace=namespace)
            
            # Get models from LlamaFarm
            model_count = 0
            models_sample = []
            try:
                response = requests.get('http://localhost:14345/v1/models', timeout=2)
                models = response.json().get('data', [])
                model_count = len(models)
                models_sample = [m.get('id', 'unknown') for m in models[:5]]
            except:
                pass
            
            # Discover projects (filtered by namespace)
            projects = discovery.discover_projects()
            specialized_models = discovery.discover_models()
            
            integrations.append({
                "id": "llamafarm",
                "name": "LlamaFarm",
                "type": "llm_backend",
                "address": "localhost:14345",
                "status": "healthy",
                "capabilities": ["chat", "embeddings", "completions"],
                "connected": True,
                
                # Filtered LlamaFarm data
                "projects": projects,
                "specialized_models": specialized_models,
                "models": models_sample,
                "model_count": model_count,
                "namespace": namespace or "all",
            })
        else:
            integrations.append({
                "id": "llamafarm",
                "name": "LlamaFarm",
                "type": "llm_backend",
                "address": "localhost:14345",
                "status": "offline",
                "connected": False,
            })
    except Exception as e:
        logger.error(f"Error checking LlamaFarm: {e}")
        integrations.append({
            "id": "llamafarm",
            "name": "LlamaFarm",
            "type": "llm_backend",
            "address": "localhost:14345",
            "status": "error",
            "connected": False,
            "error": str(e)
        })
    
    # Check Ollama (direct)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 11434))
        sock.close()
        
        if result == 0:
            # Try to get model list
            try:
                response = requests.get('http://localhost:11434/api/tags', timeout=2)
                models = response.json().get('models', [])
                model_count = len(models)
                model_names = [m.get('name', 'unknown') for m in models[:5]]
            except:
                model_count = 0
                model_names = []
            
            integrations.append({
                "id": "ollama",
                "name": "Ollama (Direct)",
                "type": "llm_backend",
                "address": "localhost:11434",
                "status": "healthy",
                "capabilities": ["chat", "embeddings", "completions"],
                "models": model_names,
                "model_count": model_count,
                "connected": True,
            })
        else:
            integrations.append({
                "id": "ollama",
                "name": "Ollama (Direct)",
                "type": "llm_backend",
                "address": "localhost:11434",
                "status": "offline",
                "connected": False,
            })
    except Exception as e:
        logger.error(f"Error checking Ollama: {e}")
    
    # TODO: Add mDNS discovery for other backends
    
    return {
        "integrations": integrations,
        "timestamp": time.time()
    }


class TestRequest(BaseModel):
    """Request to test an integration."""
    integration_id: str = Field(..., description="Integration ID (llamafarm, ollama)")
    prompt: str = Field(..., description="Test prompt")
    model: Optional[str] = Field(default=None, description="Specific model to use")


class TestResponse(BaseModel):
    """Response from integration test."""
    success: bool
    response: Optional[str] = None
    error: Optional[str] = None
    latency_ms: float
    model_used: Optional[str] = None


@router.post("/integrations/test", response_model=TestResponse)
async def test_integration(request: TestRequest):
    """
    Test an integration by executing a prompt.
    
    Returns the response and latency.
    """
    server = get_server()
    if not server or not server.executor:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    start_time = time.time()
    
    try:
        # Execute through the executor (will route to LlamaFarm or Ollama)
        result = await server.executor.execute_capability(
            "chat",
            messages=[{"role": "user", "content": request.prompt}],
            model=request.model
        )
        
        latency_ms = (time.time() - start_time) * 1000
        
        if result.success:
            # Extract response text
            response_text = result.data.get("message", {}).get("content", "") if isinstance(result.data, dict) else str(result.data)
            model_used = result.data.get("model") if isinstance(result.data, dict) else request.model
            
            return TestResponse(
                success=True,
                response=response_text,
                latency_ms=latency_ms,
                model_used=model_used
            )
        else:
            return TestResponse(
                success=False,
                error=result.error,
                latency_ms=latency_ms
            )
    
    except Exception as e:
        logger.error(f"Integration test failed: {e}")
        latency_ms = (time.time() - start_time) * 1000
        return TestResponse(
            success=False,
            error=str(e),
            latency_ms=latency_ms
        )


# ============ ML Endpoints ============

class AnomalyDetectRequest(BaseModel):
    """Request for anomaly detection."""
    model: str = Field(..., description="Model name")
    data: List[Any] = Field(..., description="Data to analyze")
    action: str = Field(default="detect", description="Action: detect, fit, score")


class ClassifierRequest(BaseModel):
    """Request for classification."""
    model: str = Field(..., description="Model name")
    data: List[Any] = Field(..., description="Data to classify")
    action: str = Field(default="predict", description="Action: predict, fit")
    X: Optional[List[Any]] = Field(default=None, description="Training features (for fit)")
    y: Optional[List[Any]] = Field(default=None, description="Training labels (for fit)")


class MLResponse(BaseModel):
    """Response from ML operations."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0
    model_used: Optional[str] = None


@router.post("/ml/anomaly", response_model=MLResponse)
async def anomaly_detection(request: AnomalyDetectRequest):
    """
    Anomaly detection endpoint.
    
    Supports:
    - detect: Detect anomalies in data
    - fit: Train a new anomaly detector
    - score: Get anomaly scores
    """
    server = get_server()
    if not server or not server.executor:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    start_time = time.time()
    
    try:
        result = await server.executor.execute_capability(
            "anomaly_detection",
            model=request.model,
            data=request.data,
            action=request.action
        )
        
        latency_ms = (time.time() - start_time) * 1000
        
        return MLResponse(
            success=result.success,
            data=result.data,
            error=result.error,
            execution_time_ms=latency_ms,
            model_used=request.model
        )
    
    except Exception as e:
        logger.error(f"Anomaly detection failed: {e}")
        latency_ms = (time.time() - start_time) * 1000
        return MLResponse(
            success=False,
            error=str(e),
            execution_time_ms=latency_ms
        )


@router.post("/ml/classify", response_model=MLResponse)
async def classify(request: ClassifierRequest):
    """
    Classification endpoint.
    
    Supports:
    - predict: Classify data
    - fit: Train a new classifier
    """
    server = get_server()
    if not server or not server.executor:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    start_time = time.time()
    
    try:
        kwargs = {
            "model": request.model,
            "data": request.data,
            "action": request.action
        }
        
        if request.action == "fit":
            if request.X is None or request.y is None:
                raise HTTPException(
                    status_code=400,
                    detail="X and y are required for training"
                )
            kwargs["X"] = request.X
            kwargs["y"] = request.y
        
        result = await server.executor.execute_capability(
            "classification",
            **kwargs
        )
        
        latency_ms = (time.time() - start_time) * 1000
        
        return MLResponse(
            success=result.success,
            data=result.data,
            error=result.error,
            execution_time_ms=latency_ms,
            model_used=request.model
        )
    
    except Exception as e:
        logger.error(f"Classification failed: {e}")
        latency_ms = (time.time() - start_time) * 1000
        return MLResponse(
            success=False,
            error=str(e),
            execution_time_ms=latency_ms
        )


@router.get("/ml/anomaly/models")
async def list_anomaly_models():
    """List available anomaly detection models."""
    server = get_server()
    if not server or not server.executor:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    try:
        result = await server.executor.execute_capability(
            "anomaly_detection",
            action="list"
        )
        
        return {
            "success": result.success,
            "models": result.data if result.success else [],
            "error": result.error
        }
    
    except Exception as e:
        logger.error(f"Failed to list anomaly models: {e}")
        return {
            "success": False,
            "models": [],
            "error": str(e)
        }


@router.get("/ml/classifier/models")
async def list_classifier_models():
    """List available classifier models."""
    server = get_server()
    if not server or not server.executor:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    try:
        result = await server.executor.execute_capability(
            "classification",
            action="list"
        )
        
        return {
            "success": result.success,
            "models": result.data if result.success else [],
            "error": result.error
        }
    
    except Exception as e:
        logger.error(f"Failed to list classifier models: {e}")
        return {
            "success": False,
            "models": [],
            "error": str(e)
        }


@router.get("/backends")
async def list_backends():
    """
    List configured backends for this Atmosphere node.
    
    Returns only the backends that are configured in ~/.atmosphere/config.json,
    not the full LlamaFarm catalog.
    """
    import socket
    
    server = get_server()
    config = server.config if server else None
    
    backends = []
    
    if config and config.backends:
        for name, backend in config.backends.items():
            # Check if backend is reachable
            status = "offline"
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((backend.host, backend.port))
                sock.close()
                if result == 0:
                    status = "healthy"
            except:
                pass
            
            backends.append({
                "id": name,
                "name": name.title(),
                "type": backend.type,
                "host": backend.host,
                "port": backend.port,
                "enabled": backend.enabled,
                "priority": backend.priority,
                "status": status,
                "capabilities": ["chat", "embeddings"] if backend.type in ["ollama", "universal", "llamafarm"] else []
            })
    
    return {"backends": backends, "timestamp": int(time.time())}


@router.post("/intent/classify")
async def classify_intent_endpoint(request: dict):
    """
    Classify an intent without executing it.
    
    THE CROWN JEWEL - shows routing decisions.
    
    Request body: {"text": "your question here"}
    """
    from ..router.intent_classifier import classify_intent
    
    text = request.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text' field")
    
    classification = classify_intent(text)
    
    return {
        "text": text,
        "classification": {
            "complexity": classification.complexity.name,
            "complexity_value": classification.complexity.value,
            "task_type": classification.task_type.value,
            "model_size": classification.recommended_model_size,
            "domain": classification.domain.value,
            "requirements": {
                "tools": classification.needs_tools,
                "rag": classification.needs_rag,
                "vision": classification.needs_vision,
                "code": classification.needs_code,
            },
            "confidence": classification.confidence,
            "matched_patterns": classification.matched_patterns
        }
    }


# ============================================================================
# Device Registry API
# ============================================================================

@router.get("/devices")
async def list_devices():
    """
    List all known devices (online and offline).
    
    Shows all devices that have ever connected to the mesh.
    """
    registry = get_device_registry()
    devices = registry.get_all_devices()
    
    return {
        "devices": [d.to_dict() for d in devices],
        "online_count": len([d for d in devices if d.status == "online"]),
        "offline_count": len([d for d in devices if d.status == "offline"]),
        "total_count": len(devices),
        "timestamp": int(time.time())
    }


@router.get("/devices/{device_id}")
async def get_device(device_id: str):
    """Get info about a specific device."""
    registry = get_device_registry()
    device = registry.get_device(device_id)
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return device.to_dict()


@router.post("/devices/{device_id}/block")
async def block_device(device_id: str):
    """Block a device from connecting."""
    registry = get_device_registry()
    device = registry.get_device(device_id)
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    registry.block_device(device_id)
    return {"status": "blocked", "device_id": device_id}


@router.post("/devices/{device_id}/unblock")
async def unblock_device(device_id: str):
    """Unblock a device."""
    registry = get_device_registry()
    device = registry.get_device(device_id)
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    registry.unblock_device(device_id)
    return {"status": "unblocked", "device_id": device_id}


@router.delete("/devices/{device_id}")
async def remove_device(device_id: str):
    """Remove a device from the registry."""
    registry = get_device_registry()
    device = registry.get_device(device_id)
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    registry.remove_device(device_id)
    return {"status": "removed", "device_id": device_id}
