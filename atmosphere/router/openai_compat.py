"""
OpenAI-Compatible API Endpoints for Atmosphere

Provides OpenAI API compatibility layer that routes requests
to LlamaFarm projects based on the model field.

Uses FastProjectRouter for sub-millisecond routing decisions.
NO LLM CALLS for routing - uses pre-computed embeddings.

Endpoints:
- POST /v1/chat/completions - Chat completion (routed)
- POST /v1/completions - Text completion (routed)
- POST /v1/embeddings - Embedding generation
- GET /v1/models - List all available models
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Union

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .fast_router import get_fast_router, ProjectEntry, RouteResult

logger = logging.getLogger(__name__)

# Create router for OpenAI-compatible endpoints
openai_router = APIRouter(prefix="/v1", tags=["openai-compatible"])

# LlamaFarm base URL
LLAMAFARM_BASE = "http://localhost:14345"

# Timeout settings
REQUEST_TIMEOUT = 120.0


# ============ Request/Response Models ============

class ChatMessage(BaseModel):
    """A chat message."""
    role: str = Field(..., description="user, assistant, or system")
    content: str = Field(..., description="Message content")
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str = Field(default="default", description="Model to use (can be namespace/project or project name)")
    messages: List[ChatMessage] = Field(..., description="Chat messages")
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    max_tokens: Optional[int] = None
    stream: bool = False
    stop: Optional[Union[str, List[str]]] = None
    presence_penalty: float = Field(default=0, ge=-2, le=2)
    frequency_penalty: float = Field(default=0, ge=-2, le=2)
    user: Optional[str] = None


class CompletionRequest(BaseModel):
    """OpenAI-compatible completion request."""
    model: str = Field(default="default", description="Model to use")
    prompt: Union[str, List[str]] = Field(..., description="Prompt(s) to complete")
    max_tokens: Optional[int] = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    stream: bool = False
    stop: Optional[Union[str, List[str]]] = None
    suffix: Optional[str] = None
    echo: bool = False


class EmbeddingRequest(BaseModel):
    """OpenAI-compatible embedding request."""
    model: str = Field(default="default", description="Model to use")
    input: Union[str, List[str]] = Field(..., description="Text(s) to embed")
    encoding_format: str = Field(default="float", description="float or base64")


class ModelInfo(BaseModel):
    """Model information."""
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "llamafarm"
    
    # Extended info for Atmosphere
    namespace: Optional[str] = None
    domain: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    description: Optional[str] = None


# ============ Helper Functions ============

async def proxy_to_llamafarm(
    project: ProjectEntry,
    endpoint: str,
    payload: Dict[str, Any],
    stream: bool = False
) -> Union[Dict[str, Any], StreamingResponse]:
    """
    Proxy a request to LlamaFarm.
    
    Args:
        project: Target project
        endpoint: API endpoint (e.g., "chat/completions")
        payload: Request payload
        stream: Whether to stream the response
    
    Returns:
        Response data or StreamingResponse
    """
    url = f"{LLAMAFARM_BASE}/v1/projects/{project.namespace}/{project.name}/{endpoint}"
    
    logger.info(f"Routing to LlamaFarm: {url}")
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        if stream:
            # Stream response
            async def stream_generator():
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"LlamaFarm error: {error_text}")
                        yield f"data: {{'error': 'LlamaFarm error: {response.status_code}'}}\n\n"
                        return
                    
                    async for chunk in response.aiter_bytes():
                        yield chunk
            
            return StreamingResponse(
                stream_generator(),
                media_type="text/event-stream"
            )
        else:
            # Regular request
            response = await client.post(url, json=payload)
            
            if response.status_code != 200:
                logger.error(f"LlamaFarm error: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"LlamaFarm error: {response.text}"
                )
            
            return response.json()


def build_openai_response(
    data: Dict[str, Any],
    model: str,
    result: RouteResult
) -> Dict[str, Any]:
    """
    Build an OpenAI-compatible response with routing metadata.
    """
    response = data.copy()
    
    # Add routing metadata as a custom field
    response["_atmosphere"] = {
        "routed_to": result.project.model_path if result.project else None,
        "score": result.score,
        "reason": result.reason,
        "fallback": result.fallback,
        "latency_ms": result.latency_ms
    }
    
    # Ensure model field reflects actual project used
    if result.project:
        response["model"] = result.project.model_path
    
    return response


# ============ Endpoints ============

@openai_router.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completion endpoint.
    
    Uses FAST pre-computed embeddings for routing - NO LLM calls.
    Sub-millisecond routing decisions.
    
    Model can be:
    - Explicit path: "default/llama-expert-14"
    - Project name: "llama-expert-14"
    - "default" or "auto" for content-based routing
    """
    router = get_fast_router()
    
    # Convert messages to dict format (exclude null fields)
    messages = []
    for m in request.messages:
        msg = {"role": m.role, "content": m.content}
        if m.name:  # Only include name if not None
            msg["name"] = m.name
        messages.append(msg)
    
    # Route the request (FAST - no LLM calls)
    result = router.route(request.model, messages)
    
    if not result.success:
        raise HTTPException(
            status_code=404,
            detail=f"No suitable project found: {result.reason}"
        )
    
    logger.info(f"Routing '{request.model}' → {result.project.model_path} (score={result.score:.2f}, latency={result.latency_ms:.2f}ms)")
    
    # Build payload for LlamaFarm
    payload = {
        "model": result.project.models[0] if result.project.models else "default",
        "messages": messages,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stream": request.stream,
    }
    
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.stop:
        payload["stop"] = request.stop
    
    # Proxy to LlamaFarm
    response = await proxy_to_llamafarm(
        result.project,
        "chat/completions",
        payload,
        stream=request.stream
    )
    
    if request.stream:
        return response  # StreamingResponse
    
    return build_openai_response(response, request.model, result)


@openai_router.post("/completions")
async def completions(request: CompletionRequest):
    """
    OpenAI-compatible text completion endpoint.
    
    Uses FAST pre-computed embeddings for routing.
    """
    router = get_fast_router()
    
    # Convert prompt to messages format
    prompts = [request.prompt] if isinstance(request.prompt, str) else request.prompt
    messages = [{"role": "user", "content": prompts[0]}]
    
    # Route the request (FAST)
    result = router.route(request.model, messages)
    
    if not result.success:
        raise HTTPException(
            status_code=404,
            detail=f"No suitable project found: {result.reason}"
        )
    
    logger.info(f"Routing completion '{request.model}' → {result.project.model_path} ({result.latency_ms:.2f}ms)")
    
    # Build payload - convert to chat format
    payload = {
        "model": result.project.models[0] if result.project.models else "default",
        "messages": messages,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stream": request.stream,
    }
    
    # Proxy to LlamaFarm (using chat/completions internally)
    response = await proxy_to_llamafarm(
        result.project,
        "chat/completions",
        payload,
        stream=request.stream
    )
    
    if request.stream:
        return response
    
    # Convert chat response to completion format
    chat_response = response
    completion_response = {
        "id": chat_response.get("id", f"cmpl-{int(time.time()*1000)}"),
        "object": "text_completion",
        "created": chat_response.get("created", int(time.time())),
        "model": result.project.model_path,
        "choices": [
            {
                "text": choice.get("message", {}).get("content", ""),
                "index": choice.get("index", 0),
                "logprobs": None,
                "finish_reason": choice.get("finish_reason", "stop")
            }
            for choice in chat_response.get("choices", [])
        ],
        "usage": chat_response.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
        "_atmosphere": {
            "routed_to": result.project.model_path,
            "score": result.score,
            "reason": result.reason,
            "fallback": result.fallback,
            "latency_ms": result.latency_ms
        }
    }
    
    return completion_response


@openai_router.post("/embeddings")
async def embeddings(request: EmbeddingRequest):
    """
    OpenAI-compatible embedding endpoint.
    
    Routes to LlamaFarm's embedding service.
    """
    # Embeddings go to the universal runtime
    # No routing needed for embeddings
    
    inputs = [request.input] if isinstance(request.input, str) else request.input
    
    # For now, route to the default project or use Universal directly
    url = f"{LLAMAFARM_BASE}/v1/embeddings"
    
    payload = {
        "model": request.model if request.model != "default" else "sentence-transformers/all-MiniLM-L6-v2",
        "input": inputs,
        "encoding_format": request.encoding_format
    }
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(url, json=payload)
        
        if response.status_code != 200:
            # Fall back to Universal runtime directly
            universal_url = "http://localhost:11540/v1/embeddings"
            response = await client.post(universal_url, json=payload)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Embedding error: {response.text}"
                )
        
        return response.json()


@openai_router.get("/models")
async def list_models():
    """
    List all available models across the mesh.
    
    Returns LlamaFarm projects as models plus any raw Ollama models.
    """
    router = get_fast_router()
    projects = router.list_projects()
    
    models = []
    
    # Add LlamaFarm projects as models
    for project in projects:
        models.append(ModelInfo(
            id=project.model_path,
            owned_by="llamafarm",
            namespace=project.namespace,
            domain=project.domain,
            capabilities=project.capabilities,
            description=project.description[:100] if project.description else None
        ))
    
    # Try to get raw Ollama models too
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # From Universal runtime
            response = await client.get(f"{LLAMAFARM_BASE}/v1/models")
            if response.status_code == 200:
                ollama_models = response.json().get("data", [])
                for m in ollama_models:
                    # Don't duplicate if already listed
                    model_id = m.get("id", "")
                    if not any(existing.id == model_id for existing in models):
                        models.append(ModelInfo(
                            id=model_id,
                            owned_by="ollama",
                            created=m.get("created", int(time.time()))
                        ))
    except Exception as e:
        logger.warning(f"Could not fetch Ollama models: {e}")
    
    return {
        "object": "list",
        "data": [m.model_dump() for m in models]
    }


@openai_router.get("/models/{model_id:path}")
async def get_model(model_id: str):
    """
    Get information about a specific model.
    """
    router = get_fast_router()
    project = router.get_project(model_id)
    
    if project:
        return ModelInfo(
            id=project.model_path,
            owned_by="llamafarm",
            namespace=project.namespace,
            domain=project.domain,
            capabilities=project.capabilities,
            description=project.description[:100] if project.description else None
        ).model_dump()
    
    # Check if it's an Ollama model
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{LLAMAFARM_BASE}/v1/models/{model_id}")
            if response.status_code == 200:
                return response.json()
    except:
        pass
    
    raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")


# ============ Routing Info Endpoints ============

@openai_router.get("/routing/stats")
async def routing_stats():
    """Get routing statistics including latency info."""
    router = get_fast_router()
    return router.get_stats()


@openai_router.get("/routing/projects")
async def list_routable_projects(
    domain: Optional[str] = None,
    capability: Optional[str] = None
):
    """List all routable projects with optional filters."""
    router = get_fast_router()
    projects = router.list_projects(domain=domain, capability=capability)
    
    return {
        "projects": [
            {
                "model_path": p.model_path,
                "namespace": p.namespace,
                "name": p.name,
                "domain": p.domain,
                "capabilities": p.capabilities,
                "topics": p.topics,
                "has_rag": p.has_rag,
                "has_tools": p.has_tools,
                "nodes": p.nodes
            }
            for p in projects
        ]
    }


@openai_router.post("/routing/test")
async def test_routing(request: ChatCompletionRequest):
    """
    Test routing without executing.
    
    Returns the routing decision with latency metrics.
    FAST - uses pre-computed embeddings, no LLM calls.
    """
    router = get_fast_router()
    
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    
    # Use fast routing
    result = router.route(request.model, messages)
    
    return {
        "model_requested": request.model,
        "routed_to": result.project.model_path if result.project else None,
        "namespace": result.project.namespace if result.project else None,
        "project_name": result.project.name if result.project else None,
        "domain": result.project.domain if result.project else None,
        "capabilities": result.project.capabilities if result.project else [],
        "nodes": result.project.nodes if result.project else [],
        "score": result.score,
        "reason": result.reason,
        "fallback": result.fallback,
        "success": result.success,
        "latency_ms": result.latency_ms
    }
