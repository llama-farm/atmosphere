"""
API routes for Atmosphere.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .server import get_server
from ..router.semantic import RouteAction

logger = logging.getLogger(__name__)

router = APIRouter()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()


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
    
    Returns routing decision without executing.
    """
    server = get_server()
    if not server or not server.router:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    result = await server.router.route(request.intent)
    
    return RouteResponse(
        action=result.action.value,
        capability=result.capability.label if result.capability else None,
        score=result.score,
        hops=result.hops,
        next_hop=result.next_hop,
        node_id=server.node.node_id if result.action == RouteAction.PROCESS_LOCAL else result.via_node
    )


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
    
    return ChatCompletionResponse(
        id=f"chatcmpl-{int(time.time() * 1000)}",
        created=int(time.time()),
        model=request.model,
        choices=[{
            "index": 0,
            "message": response_message,
            "finish_reason": "stop"
        }],
        usage={
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    )


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
    
    return MeshStatus(
        mesh_id=mesh.mesh_id if mesh else None,
        mesh_name=mesh.name if mesh else None,
        node_count=len(mesh.founding_members) if mesh else 0,
        peer_count=len(server.discovery.peers) if server.discovery else 0,
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
    """List discovered peers."""
    server = get_server()
    if not server or not server.discovery:
        raise HTTPException(status_code=503, detail="Server not ready")
    
    return {
        "peers": [
            {
                "node_id": p.node_id,
                "name": p.name,
                "address": p.address,
                "mesh_id": p.mesh_id,
                "capabilities": p.capabilities
            }
            for p in server.discovery.peers
        ]
    }


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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.
    
    Sends mesh status, gossip messages, and capability changes.
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
        
        # Keep connection alive and listen for updates
        while True:
            try:
                # Ping every 30 seconds to keep connection alive
                await asyncio.sleep(30)
                await websocket.send_json({"type": "ping", "timestamp": time.time()})
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@router.get("/integrations")
async def list_integrations():
    """
    Discover and list available backend integrations.
    
    Scans for:
    - LlamaFarm (port 14345) with full project/model discovery
    - Ollama (port 11434)
    - Other discovered backends via mDNS
    """
    import socket
    import requests
    from ..adapters.llamafarm import LlamaFarmDiscovery
    
    integrations = []
    
    # Check LlamaFarm with full discovery
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 14345))
        sock.close()
        
        if result == 0:
            discovery = LlamaFarmDiscovery()
            
            # Get Ollama models from LlamaFarm
            ollama_models = []
            ollama_model_count = 0
            try:
                response = requests.get('http://localhost:14345/v1/models', timeout=2)
                models = response.json().get('data', [])
                ollama_model_count = len(models)
                ollama_models = [m.get('id', 'unknown') for m in models[:5]]  # First 5
            except:
                pass
            
            # Discover projects and specialized models
            projects = discovery.discover_projects()
            specialized_models = discovery.discover_models()
            config = discovery.get_config()
            
            # Calculate total capabilities
            total_models = ollama_model_count
            for category, info in specialized_models.items():
                total_models += info.get('count', 0)
            
            integrations.append({
                "id": "llamafarm",
                "name": "LlamaFarm",
                "type": "llm_backend",
                "address": "localhost:14345",
                "status": "healthy",
                "capabilities": ["chat", "embeddings", "completions", "classification", "anomaly-detection", "routing"],
                "connected": True,
                
                # Rich LlamaFarm data
                "config": config,
                "projects": projects,
                "specialized_models": specialized_models,
                "ollama_models": ollama_models,
                "ollama_model_count": ollama_model_count,
                "total_model_count": total_models,
                
                # Legacy fields for compatibility
                "models": ollama_models,
                "model_count": ollama_model_count,
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
