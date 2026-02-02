# Atmosphere Integration Layer Design

**Version:** 1.0  
**Status:** Draft  
**Last Updated:** 2025-02-02

## Overview

This document specifies how external systems integrate with Atmosphere. The integration layer provides a clean abstraction between Atmosphere's orchestration core and the systems it coordinates.

### Design Principles

1. **Atmosphere orchestrates, adapters execute** — Atmosphere routes intents; adapters talk to backends
2. **Discovery is automatic** — Adapters find their systems without manual configuration
3. **Capabilities flow up** — Adapters register capabilities; mesh propagates them
4. **Tools flow down** — Intents resolve to tool calls; adapters execute them
5. **Secrets stay local** — API keys never enter gossip; only capability availability is advertised

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ATMOSPHERE NODE                                    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         INTENT ROUTER                                │   │
│  │                                                                      │   │
│  │   Intent → Embed → Match Capabilities → Route (local/remote)        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      ADAPTER REGISTRY                                │   │
│  │                                                                      │   │
│  │   • Manages adapter lifecycle                                        │   │
│  │   • Aggregates capabilities from all adapters                       │   │
│  │   • Dispatches tool calls to appropriate adapter                    │   │
│  │   • Handles adapter health monitoring                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│          │              │              │              │              │      │
│          ▼              ▼              ▼              ▼              ▼      │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│   │LlamaFarm │   │  Ollama  │   │  Matter  │   │Cloud APIs│   │  Custom  │ │
│   │ Adapter  │   │ Adapter  │   │ Adapter  │   │ Adapter  │   │ Adapters │ │
│   └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘ │
└────────┼──────────────┼──────────────┼──────────────┼──────────────┼───────┘
         │              │              │              │              │
         ▼              ▼              ▼              ▼              ▼
    ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
    │LlamaFarm│   │ Ollama  │   │ Thread  │   │ OpenAI  │   │  Your   │
    │  :8000  │   │ :11434  │   │ Border  │   │  API    │   │ System  │
    └─────────┘   └─────────┘   │ Router  │   └─────────┘   └─────────┘
                                └─────────┘
```

---

## Core Interface Specification

### `AtmosphereAdapter` (Base Class)

All integrations implement this interface:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import asyncio


class AdapterState(Enum):
    """Adapter lifecycle states."""
    UNINITIALIZED = "uninitialized"
    DISCOVERING = "discovering"
    CONNECTED = "connected"
    DEGRADED = "degraded"      # Partially working
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class Capability:
    """A capability this adapter provides."""
    id: str                           # Unique ID: "{adapter}:{type}:{subtype}"
    type: str                         # Category: llm, embeddings, vision, device, etc.
    name: str                         # Human-readable name
    description: str                  # For semantic matching
    models: List[str] = field(default_factory=list)  # Available models (if applicable)
    constraints: Dict[str, Any] = field(default_factory=dict)  # Resource limits, etc.
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Tool:
    """A tool exposed by this adapter."""
    name: str                         # Tool name for invocation
    description: str                  # For semantic matching & LLM tool use
    parameters: Dict[str, Any]        # JSON Schema for parameters
    capability_id: str                # Which capability provides this
    returns: Dict[str, Any] = field(default_factory=dict)  # Return schema
    examples: List[Dict] = field(default_factory=list)     # Usage examples


@dataclass  
class ToolResult:
    """Result of a tool execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration_ms: float = 0
    usage: Dict[str, Any] = field(default_factory=dict)  # Tokens, cost, etc.


@dataclass
class HealthStatus:
    """Health check result."""
    healthy: bool
    state: AdapterState
    latency_ms: float = 0
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class AtmosphereAdapter(ABC):
    """
    Base class for all Atmosphere integrations.
    
    Lifecycle:
    1. __init__() - Adapter created with config
    2. discover() - Probe for backend availability  
    3. connect() - Establish connection, enumerate capabilities
    4. get_capabilities() / get_tools() - Expose to mesh
    5. execute_tool() - Handle tool calls
    6. health_check() - Periodic monitoring
    7. disconnect() - Clean shutdown
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._state = AdapterState.UNINITIALIZED
        self._capabilities: List[Capability] = []
        self._tools: List[Tool] = []
    
    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier for this adapter type (e.g., 'llamafarm', 'ollama')."""
        pass
    
    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Human-readable name."""
        pass
    
    @property
    def state(self) -> AdapterState:
        """Current adapter state."""
        return self._state
    
    # --- Discovery & Connection ---
    
    @abstractmethod
    async def discover(self) -> bool:
        """
        Check if the backend system is available.
        
        Should be fast and non-destructive. Called during startup
        and periodically to detect newly available backends.
        
        Returns:
            True if backend is reachable, False otherwise
        """
        pass
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection and enumerate capabilities.
        
        Called after discover() returns True. Should:
        - Establish persistent connection if needed
        - Query backend for available models/features
        - Populate self._capabilities and self._tools
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    async def disconnect(self) -> None:
        """
        Clean shutdown.
        
        Override to close connections, release resources.
        """
        self._state = AdapterState.DISCONNECTED
    
    # --- Capability & Tool Exposure ---
    
    def get_capabilities(self) -> List[Capability]:
        """Return capabilities this adapter provides."""
        return self._capabilities
    
    def get_tools(self) -> List[Tool]:
        """Return tools this adapter exposes."""
        return self._tools
    
    def get_capability(self, capability_id: str) -> Optional[Capability]:
        """Get a specific capability by ID."""
        for cap in self._capabilities:
            if cap.id == capability_id:
                return cap
        return None
    
    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Get a specific tool by name."""
        for tool in self._tools:
            if tool.name == tool_name:
                return tool
        return None
    
    # --- Execution ---
    
    @abstractmethod
    async def execute_tool(
        self, 
        tool_name: str, 
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        Execute a tool call.
        
        Args:
            tool_name: Name of the tool to execute
            params: Parameters for the tool (validated against schema)
            context: Optional execution context (user, session, etc.)
            
        Returns:
            ToolResult with success/failure and data
        """
        pass
    
    # --- Health & Monitoring ---
    
    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """
        Check backend health.
        
        Called periodically. Should update self._state.
        
        Returns:
            HealthStatus with current state
        """
        pass
    
    # --- Event Hooks (Optional) ---
    
    async def on_capability_change(self) -> None:
        """
        Called when capabilities change.
        
        Override to handle dynamic capability updates
        (e.g., new model pulled to Ollama).
        """
        pass
    
    async def on_mesh_join(self, mesh_id: str) -> None:
        """Called when node joins a mesh."""
        pass
    
    async def on_mesh_leave(self) -> None:
        """Called when node leaves mesh."""
        pass
```

---

## Adapter Registry

The registry manages all adapters on a node:

```python
class AdapterRegistry:
    """
    Central registry for all adapters on this node.
    
    Responsibilities:
    - Adapter lifecycle management
    - Capability aggregation for mesh gossip
    - Tool call dispatch
    - Health monitoring
    """
    
    def __init__(self):
        self._adapters: Dict[str, AtmosphereAdapter] = {}
        self._capability_index: Dict[str, AtmosphereAdapter] = {}  # cap_id -> adapter
        self._tool_index: Dict[str, AtmosphereAdapter] = {}        # tool_name -> adapter
        self._discovery_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None
    
    def register(self, adapter: AtmosphereAdapter) -> None:
        """Register an adapter (doesn't connect yet)."""
        self._adapters[adapter.adapter_id] = adapter
    
    async def start(self) -> None:
        """
        Start all adapters.
        
        - Runs discovery on all registered adapters
        - Connects to available backends
        - Starts background health monitoring
        """
        for adapter in self._adapters.values():
            await self._try_connect(adapter)
        
        self._rebuild_indexes()
        self._health_task = asyncio.create_task(self._health_loop())
        self._discovery_task = asyncio.create_task(self._discovery_loop())
    
    async def stop(self) -> None:
        """Stop all adapters and background tasks."""
        if self._health_task:
            self._health_task.cancel()
        if self._discovery_task:
            self._discovery_task.cancel()
        
        for adapter in self._adapters.values():
            await adapter.disconnect()
    
    async def _try_connect(self, adapter: AtmosphereAdapter) -> bool:
        """Attempt discovery and connection."""
        try:
            if await adapter.discover():
                return await adapter.connect()
        except Exception as e:
            logging.warning(f"Adapter {adapter.adapter_id} failed: {e}")
        return False
    
    def _rebuild_indexes(self) -> None:
        """Rebuild capability and tool indexes."""
        self._capability_index.clear()
        self._tool_index.clear()
        
        for adapter in self._adapters.values():
            if adapter.state == AdapterState.CONNECTED:
                for cap in adapter.get_capabilities():
                    self._capability_index[cap.id] = adapter
                for tool in adapter.get_tools():
                    self._tool_index[tool.name] = adapter
    
    # --- Capability Access ---
    
    def get_all_capabilities(self) -> List[Capability]:
        """Get all capabilities from all connected adapters."""
        caps = []
        for adapter in self._adapters.values():
            if adapter.state in (AdapterState.CONNECTED, AdapterState.DEGRADED):
                caps.extend(adapter.get_capabilities())
        return caps
    
    def get_all_tools(self) -> List[Tool]:
        """Get all tools from all connected adapters."""
        tools = []
        for adapter in self._adapters.values():
            if adapter.state in (AdapterState.CONNECTED, AdapterState.DEGRADED):
                tools.extend(adapter.get_tools())
        return tools
    
    # --- Tool Execution ---
    
    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        Execute a tool by name.
        
        Dispatches to the appropriate adapter.
        """
        adapter = self._tool_index.get(tool_name)
        if not adapter:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}"
            )
        
        if adapter.state not in (AdapterState.CONNECTED, AdapterState.DEGRADED):
            return ToolResult(
                success=False,
                error=f"Adapter {adapter.adapter_id} not available"
            )
        
        return await adapter.execute_tool(tool_name, params, context)
    
    # --- Background Tasks ---
    
    async def _health_loop(self, interval: float = 30.0) -> None:
        """Periodic health checks."""
        while True:
            await asyncio.sleep(interval)
            for adapter in self._adapters.values():
                try:
                    status = await adapter.health_check()
                    if status.state != adapter.state:
                        self._rebuild_indexes()
                        await self._on_state_change(adapter)
                except Exception:
                    pass
    
    async def _discovery_loop(self, interval: float = 60.0) -> None:
        """Periodic discovery for new backends."""
        while True:
            await asyncio.sleep(interval)
            for adapter in self._adapters.values():
                if adapter.state == AdapterState.DISCONNECTED:
                    if await self._try_connect(adapter):
                        self._rebuild_indexes()
                        await self._on_state_change(adapter)
    
    async def _on_state_change(self, adapter: AtmosphereAdapter) -> None:
        """Handle adapter state changes (notify mesh, etc.)."""
        # Trigger capability re-announcement to mesh
        pass
```

---

## LlamaFarm Adapter (Detailed)

LlamaFarm provides advanced AI capabilities: LLM, embeddings, RAG, vision, agents.

### Discovery

```python
class LlamaFarmAdapter(AtmosphereAdapter):
    """
    Adapter for LlamaFarm AI runtime.
    
    LlamaFarm provides:
    - Multi-model LLM inference
    - Embeddings generation
    - RAG (projects with vector stores)
    - Vision analysis
    - Agent execution
    
    Discovery:
    - Default: http://localhost:14345
    - Environment: LLAMAFARM_URL
    - Config: llamafarm.url
    
    The adapter auto-discovers LlamaFarm projects and maps them
    to capabilities. Each project becomes a capability.
    """
    
    DEFAULT_URLS = [
        "http://localhost:14345",
        "http://localhost:8000",
    ]
    
    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self._url: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._api_key: Optional[str] = None
        self._projects: List[Dict] = []
        self._models: List[Dict] = []
    
    @property
    def adapter_id(self) -> str:
        return "llamafarm"
    
    @property
    def adapter_name(self) -> str:
        return "LlamaFarm"
    
    async def discover(self) -> bool:
        """
        Find LlamaFarm server.
        
        Check order:
        1. Config URL
        2. Environment variable
        3. Default ports
        """
        urls_to_try = []
        
        # Config
        if self.config.get("url"):
            urls_to_try.append(self.config["url"])
        
        # Environment
        import os
        if env_url := os.environ.get("LLAMAFARM_URL"):
            urls_to_try.append(env_url)
        
        # Defaults
        urls_to_try.extend(self.DEFAULT_URLS)
        
        # API key
        self._api_key = self.config.get("api_key") or os.environ.get("LLAMAFARM_API_KEY")
        
        # Try each URL
        for url in urls_to_try:
            if await self._check_url(url):
                self._url = url
                return True
        
        return False
    
    async def _check_url(self, url: str) -> bool:
        """Check if URL responds like LlamaFarm."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/health", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # LlamaFarm returns {"status": "healthy", ...}
                        return data.get("status") == "healthy"
        except:
            pass
        return False
    
    async def connect(self) -> bool:
        """Connect and enumerate capabilities."""
        if not self._url:
            return False
        
        self._state = AdapterState.DISCOVERING
        
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120),
            headers=headers
        )
        
        try:
            # Get projects
            async with self._session.get(f"{self._url}/v1/projects") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._projects = data.get("data", [])
            
            # Get models
            async with self._session.get(f"{self._url}/v1/models") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._models = data.get("data", [])
            
            self._build_capabilities()
            self._build_tools()
            self._state = AdapterState.CONNECTED
            return True
            
        except Exception as e:
            self._state = AdapterState.ERROR
            return False
    
    def _build_capabilities(self) -> None:
        """Build capabilities from LlamaFarm projects and models."""
        self._capabilities = []
        
        # Core LLM capability (always present if models exist)
        if self._models:
            model_names = [m.get("id", "") for m in self._models]
            self._capabilities.append(Capability(
                id=f"{self.adapter_id}:llm",
                type="llm",
                name="LlamaFarm LLM",
                description="Large language model inference, chat completion, text generation",
                models=model_names,
                metadata={"url": self._url}
            ))
        
        # Embeddings capability
        embedding_models = [m for m in self._models 
                          if "embed" in m.get("id", "").lower()]
        if embedding_models:
            self._capabilities.append(Capability(
                id=f"{self.adapter_id}:embeddings",
                type="embeddings",
                name="LlamaFarm Embeddings",
                description="Text embeddings for semantic search and similarity",
                models=[m["id"] for m in embedding_models]
            ))
        
        # Project-based capabilities
        for project in self._projects:
            proj_id = project.get("id", "")
            proj_type = project.get("type", "")
            proj_name = project.get("name", proj_id)
            
            if proj_type == "rag":
                self._capabilities.append(Capability(
                    id=f"{self.adapter_id}:rag:{proj_id}",
                    type="rag",
                    name=f"RAG: {proj_name}",
                    description=f"Retrieval augmented generation from {proj_name} knowledge base",
                    metadata={"project_id": proj_id}
                ))
            
            elif proj_type == "agent":
                self._capabilities.append(Capability(
                    id=f"{self.adapter_id}:agent:{proj_id}",
                    type="agent",
                    name=f"Agent: {proj_name}",
                    description=f"AI agent for complex tasks: {proj_name}",
                    metadata={"project_id": proj_id}
                ))
    
    def _build_tools(self) -> None:
        """Build tool definitions from capabilities."""
        self._tools = []
        
        # LLM tools
        if any(c.type == "llm" for c in self._capabilities):
            self._tools.append(Tool(
                name="llamafarm_chat",
                description="Generate chat completion using LlamaFarm",
                parameters={
                    "type": "object",
                    "properties": {
                        "messages": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                                    "content": {"type": "string"}
                                }
                            },
                            "description": "Chat messages"
                        },
                        "model": {"type": "string", "description": "Model to use"},
                        "temperature": {"type": "number", "default": 0.7},
                        "max_tokens": {"type": "integer"}
                    },
                    "required": ["messages"]
                },
                capability_id=f"{self.adapter_id}:llm"
            ))
            
            self._tools.append(Tool(
                name="llamafarm_generate",
                description="Generate text completion",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Input prompt"},
                        "model": {"type": "string"},
                        "temperature": {"type": "number", "default": 0.7},
                        "max_tokens": {"type": "integer"}
                    },
                    "required": ["prompt"]
                },
                capability_id=f"{self.adapter_id}:llm"
            ))
        
        # Embeddings tools
        if any(c.type == "embeddings" for c in self._capabilities):
            self._tools.append(Tool(
                name="llamafarm_embed",
                description="Generate text embeddings for semantic search",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to embed"},
                        "model": {"type": "string"}
                    },
                    "required": ["text"]
                },
                capability_id=f"{self.adapter_id}:embeddings"
            ))
        
        # RAG tools (one per project)
        for cap in self._capabilities:
            if cap.type == "rag":
                proj_id = cap.metadata.get("project_id", "")
                self._tools.append(Tool(
                    name=f"llamafarm_rag_query_{proj_id}",
                    description=f"Query {cap.name} knowledge base",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "top_k": {"type": "integer", "default": 5}
                        },
                        "required": ["query"]
                    },
                    capability_id=cap.id
                ))
    
    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Execute a LlamaFarm tool."""
        import time
        start = time.time()
        
        try:
            if tool_name == "llamafarm_chat":
                result = await self._chat(params)
            elif tool_name == "llamafarm_generate":
                result = await self._generate(params)
            elif tool_name == "llamafarm_embed":
                result = await self._embed(params)
            elif tool_name.startswith("llamafarm_rag_query_"):
                project_id = tool_name.replace("llamafarm_rag_query_", "")
                result = await self._rag_query(project_id, params)
            else:
                return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
            
            duration = (time.time() - start) * 1000
            return ToolResult(
                success=True,
                data=result,
                duration_ms=duration,
                usage=result.get("usage", {}) if isinstance(result, dict) else {}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000
            )
    
    async def _chat(self, params: Dict) -> Dict:
        """Execute chat completion."""
        async with self._session.post(
            f"{self._url}/v1/chat/completions",
            json=params
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(await resp.text())
            return await resp.json()
    
    async def _generate(self, params: Dict) -> Dict:
        """Execute text generation."""
        async with self._session.post(
            f"{self._url}/v1/completions",
            json=params
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(await resp.text())
            return await resp.json()
    
    async def _embed(self, params: Dict) -> Dict:
        """Generate embeddings."""
        async with self._session.post(
            f"{self._url}/v1/embeddings",
            json={"input": params["text"], "model": params.get("model")}
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(await resp.text())
            return await resp.json()
    
    async def _rag_query(self, project_id: str, params: Dict) -> Dict:
        """Query RAG project."""
        async with self._session.post(
            f"{self._url}/v1/rag/{project_id}/query",
            json=params
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(await resp.text())
            return await resp.json()
    
    async def health_check(self) -> HealthStatus:
        """Check LlamaFarm health."""
        import time
        start = time.time()
        
        try:
            async with self._session.get(f"{self._url}/health") as resp:
                latency = (time.time() - start) * 1000
                
                if resp.status == 200:
                    data = await resp.json()
                    self._state = AdapterState.CONNECTED
                    return HealthStatus(
                        healthy=True,
                        state=self._state,
                        latency_ms=latency,
                        details=data
                    )
                else:
                    self._state = AdapterState.DEGRADED
                    return HealthStatus(
                        healthy=False,
                        state=self._state,
                        message=f"HTTP {resp.status}"
                    )
        except Exception as e:
            self._state = AdapterState.DISCONNECTED
            return HealthStatus(
                healthy=False,
                state=self._state,
                message=str(e)
            )
```

---

## Ollama Adapter (Detailed)

Ollama is simpler - pure model serving.

```python
class OllamaAdapter(AtmosphereAdapter):
    """
    Adapter for Ollama local LLM server.
    
    Ollama provides:
    - LLM inference (generate, chat)
    - Embeddings (with embedding models)
    - Vision (with multimodal models)
    
    Discovery:
    - Default: http://localhost:11434
    - Environment: OLLAMA_HOST
    - Config: ollama.url
    
    Models are dynamically discovered. Capabilities depend on
    which models are pulled.
    """
    
    DEFAULT_URL = "http://localhost:11434"
    
    # Model name patterns for capability detection
    EMBEDDING_PATTERNS = ["embed", "nomic", "bge", "e5"]
    VISION_PATTERNS = ["vision", "llava", "bakllava", "moondream"]
    CODE_PATTERNS = ["code", "deepseek-coder", "codellama", "starcoder"]
    
    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self._url: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._models: List[Dict] = []
    
    @property
    def adapter_id(self) -> str:
        return "ollama"
    
    @property
    def adapter_name(self) -> str:
        return "Ollama"
    
    async def discover(self) -> bool:
        """Find Ollama server."""
        import os
        
        urls_to_try = []
        
        if self.config.get("url"):
            urls_to_try.append(self.config["url"])
        
        if env_url := os.environ.get("OLLAMA_HOST"):
            urls_to_try.append(env_url)
        
        urls_to_try.append(self.DEFAULT_URL)
        
        for url in urls_to_try:
            if await self._check_url(url):
                self._url = url
                return True
        
        return False
    
    async def _check_url(self, url: str) -> bool:
        """Check if URL responds like Ollama."""
        try:
            async with aiohttp.ClientSession() as session:
                # Ollama responds to /api/tags
                async with session.get(f"{url}/api/tags", timeout=5) as resp:
                    return resp.status == 200
        except:
            pass
        return False
    
    async def connect(self) -> bool:
        """Connect and enumerate models."""
        if not self._url:
            return False
        
        self._state = AdapterState.DISCOVERING
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120)
        )
        
        try:
            await self._refresh_models()
            self._build_capabilities()
            self._build_tools()
            self._state = AdapterState.CONNECTED
            return True
        except Exception:
            self._state = AdapterState.ERROR
            return False
    
    async def _refresh_models(self) -> None:
        """Refresh model list from Ollama."""
        async with self._session.get(f"{self._url}/api/tags") as resp:
            if resp.status == 200:
                data = await resp.json()
                self._models = data.get("models", [])
    
    def _detect_model_capabilities(self, model_name: str) -> List[str]:
        """Detect capabilities based on model name."""
        name_lower = model_name.lower()
        caps = []
        
        # Embedding models
        if any(p in name_lower for p in self.EMBEDDING_PATTERNS):
            caps.append("embeddings")
        else:
            # Default to LLM
            caps.append("llm")
        
        # Vision models
        if any(p in name_lower for p in self.VISION_PATTERNS):
            caps.append("vision")
        
        # Code models (still LLM, but tagged)
        if any(p in name_lower for p in self.CODE_PATTERNS):
            caps.append("code")
        
        return caps
    
    def _build_capabilities(self) -> None:
        """Build capabilities from available models."""
        self._capabilities = []
        
        # Group models by capability
        llm_models = []
        embedding_models = []
        vision_models = []
        
        for model in self._models:
            name = model.get("name", "")
            caps = self._detect_model_capabilities(name)
            
            if "llm" in caps:
                llm_models.append(name)
            if "embeddings" in caps:
                embedding_models.append(name)
            if "vision" in caps:
                vision_models.append(name)
        
        # Create capabilities
        if llm_models:
            self._capabilities.append(Capability(
                id=f"{self.adapter_id}:llm",
                type="llm",
                name="Ollama LLM",
                description="Local large language model inference",
                models=llm_models,
                metadata={"url": self._url}
            ))
        
        if embedding_models:
            self._capabilities.append(Capability(
                id=f"{self.adapter_id}:embeddings",
                type="embeddings",
                name="Ollama Embeddings",
                description="Local text embeddings",
                models=embedding_models
            ))
        
        if vision_models:
            self._capabilities.append(Capability(
                id=f"{self.adapter_id}:vision",
                type="vision",
                name="Ollama Vision",
                description="Local image analysis with vision models",
                models=vision_models
            ))
    
    def _build_tools(self) -> None:
        """Build tools from capabilities."""
        self._tools = []
        
        if any(c.type == "llm" for c in self._capabilities):
            self._tools.extend([
                Tool(
                    name="ollama_generate",
                    description="Generate text with Ollama",
                    parameters={
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string"},
                            "model": {"type": "string"},
                            "system": {"type": "string"},
                            "temperature": {"type": "number", "default": 0.7}
                        },
                        "required": ["prompt"]
                    },
                    capability_id=f"{self.adapter_id}:llm"
                ),
                Tool(
                    name="ollama_chat",
                    description="Chat with Ollama",
                    parameters={
                        "type": "object",
                        "properties": {
                            "messages": {
                                "type": "array",
                                "items": {"type": "object"}
                            },
                            "model": {"type": "string"},
                            "temperature": {"type": "number", "default": 0.7}
                        },
                        "required": ["messages"]
                    },
                    capability_id=f"{self.adapter_id}:llm"
                )
            ])
        
        if any(c.type == "embeddings" for c in self._capabilities):
            self._tools.append(Tool(
                name="ollama_embed",
                description="Generate embeddings with Ollama",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "model": {"type": "string", "default": "nomic-embed-text"}
                    },
                    "required": ["text"]
                },
                capability_id=f"{self.adapter_id}:embeddings"
            ))
        
        if any(c.type == "vision" for c in self._capabilities):
            self._tools.append(Tool(
                name="ollama_vision",
                description="Analyze image with Ollama vision model",
                parameters={
                    "type": "object",
                    "properties": {
                        "image": {"type": "string", "description": "Base64 image or URL"},
                        "prompt": {"type": "string", "default": "Describe this image"},
                        "model": {"type": "string"}
                    },
                    "required": ["image"]
                },
                capability_id=f"{self.adapter_id}:vision"
            ))
    
    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Execute Ollama tool."""
        import time
        start = time.time()
        
        try:
            if tool_name == "ollama_generate":
                result = await self._generate(params)
            elif tool_name == "ollama_chat":
                result = await self._chat(params)
            elif tool_name == "ollama_embed":
                result = await self._embed(params)
            elif tool_name == "ollama_vision":
                result = await self._vision(params)
            else:
                return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
            
            return ToolResult(
                success=True,
                data=result,
                duration_ms=(time.time() - start) * 1000
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000
            )
    
    async def _generate(self, params: Dict) -> Dict:
        """Generate text."""
        payload = {
            "model": params.get("model", self._models[0]["name"] if self._models else "llama3.2"),
            "prompt": params["prompt"],
            "stream": False,
            "options": {"temperature": params.get("temperature", 0.7)}
        }
        if params.get("system"):
            payload["system"] = params["system"]
        
        async with self._session.post(f"{self._url}/api/generate", json=payload) as resp:
            if resp.status != 200:
                raise RuntimeError(await resp.text())
            return await resp.json()
    
    async def _chat(self, params: Dict) -> Dict:
        """Chat completion."""
        payload = {
            "model": params.get("model", self._models[0]["name"] if self._models else "llama3.2"),
            "messages": params["messages"],
            "stream": False,
            "options": {"temperature": params.get("temperature", 0.7)}
        }
        
        async with self._session.post(f"{self._url}/api/chat", json=payload) as resp:
            if resp.status != 200:
                raise RuntimeError(await resp.text())
            return await resp.json()
    
    async def _embed(self, params: Dict) -> Dict:
        """Generate embedding."""
        payload = {
            "model": params.get("model", "nomic-embed-text"),
            "prompt": params["text"]
        }
        
        async with self._session.post(f"{self._url}/api/embeddings", json=payload) as resp:
            if resp.status != 200:
                raise RuntimeError(await resp.text())
            return await resp.json()
    
    async def _vision(self, params: Dict) -> Dict:
        """Vision analysis."""
        # Ollama vision uses chat with images
        messages = [{
            "role": "user",
            "content": params.get("prompt", "Describe this image"),
            "images": [params["image"]]  # Base64 encoded
        }]
        
        vision_models = [c.models for c in self._capabilities if c.type == "vision"]
        default_model = vision_models[0][0] if vision_models and vision_models[0] else "llava"
        
        return await self._chat({
            "messages": messages,
            "model": params.get("model", default_model)
        })
    
    async def health_check(self) -> HealthStatus:
        """Check Ollama health."""
        import time
        start = time.time()
        
        try:
            async with self._session.get(f"{self._url}/api/tags") as resp:
                latency = (time.time() - start) * 1000
                
                if resp.status == 200:
                    # Refresh models on health check
                    data = await resp.json()
                    old_count = len(self._models)
                    self._models = data.get("models", [])
                    
                    # Rebuild if models changed
                    if len(self._models) != old_count:
                        self._build_capabilities()
                        self._build_tools()
                        await self.on_capability_change()
                    
                    self._state = AdapterState.CONNECTED
                    return HealthStatus(
                        healthy=True,
                        state=self._state,
                        latency_ms=latency,
                        details={"model_count": len(self._models)}
                    )
                else:
                    self._state = AdapterState.DEGRADED
                    return HealthStatus(healthy=False, state=self._state)
        except Exception as e:
            self._state = AdapterState.DISCONNECTED
            return HealthStatus(healthy=False, state=self._state, message=str(e))
```

### LlamaFarm vs Ollama: Conflict Resolution

When both are present:

```python
class AdapterPriorityPolicy:
    """
    Policy for choosing between adapters with overlapping capabilities.
    """
    
    # Priority order (higher = preferred)
    PRIORITY = {
        "llamafarm": 100,  # Full-featured, prefer when available
        "ollama": 80,      # Simpler, good fallback
        "vllm": 90,        # Production server
        "openai": 70,      # Cloud fallback
    }
    
    @classmethod
    def select_adapter(
        cls,
        capability_type: str,
        adapters: List[AtmosphereAdapter],
        context: Optional[Dict] = None
    ) -> AtmosphereAdapter:
        """
        Select the best adapter for a capability.
        
        Considers:
        - Adapter priority
        - Current load/latency
        - User preferences
        - Cost (cloud vs local)
        """
        candidates = []
        
        for adapter in adapters:
            for cap in adapter.get_capabilities():
                if cap.type == capability_type:
                    priority = cls.PRIORITY.get(adapter.adapter_id, 50)
                    candidates.append((priority, adapter))
        
        if not candidates:
            raise ValueError(f"No adapter for {capability_type}")
        
        # Sort by priority (descending)
        candidates.sort(key=lambda x: -x[0])
        
        # Apply user preferences if any
        if context and context.get("prefer_local"):
            # Boost local adapters
            for i, (p, a) in enumerate(candidates):
                if a.adapter_id in ("llamafarm", "ollama"):
                    candidates[i] = (p + 50, a)
            candidates.sort(key=lambda x: -x[0])
        
        return candidates[0][1]
```

---

## Matter Adapter (Detailed)

Matter bridges smart home devices into Atmosphere.

```python
class MatterAdapter(AtmosphereAdapter):
    """
    Adapter for Matter/Thread smart home devices.
    
    Matter provides:
    - Device discovery via mDNS
    - Device commissioning
    - Cluster-based control (OnOff, LevelControl, etc.)
    
    This adapter:
    - Discovers Matter controllers on the network
    - Bridges devices as capabilities/tools
    - Translates tool calls to Matter commands
    
    Requires:
    - A Matter controller (chip-tool, Home Assistant, etc.)
    - Network access to the Thread border router
    
    Note: This adapter typically runs on ONE node in the mesh
    (the one with the Matter controller). It exposes devices
    to the entire mesh.
    """
    
    # Matter cluster types to capability mapping
    CLUSTER_CAPABILITIES = {
        "OnOff": "switch",
        "LevelControl": "dimmer", 
        "ColorControl": "light",
        "Thermostat": "climate",
        "DoorLock": "lock",
        "WindowCovering": "shade",
        "MediaPlayback": "media",
        "TemperatureMeasurement": "sensor",
        "OccupancySensing": "sensor",
    }
    
    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self._controller_url: Optional[str] = None
        self._devices: List[Dict] = []
        self._session: Optional[aiohttp.ClientSession] = None
    
    @property
    def adapter_id(self) -> str:
        return "matter"
    
    @property
    def adapter_name(self) -> str:
        return "Matter"
    
    async def discover(self) -> bool:
        """
        Discover Matter controller.
        
        Looks for:
        1. Config-specified controller
        2. Home Assistant with Matter integration
        3. Local chip-tool server
        """
        import os
        
        urls_to_try = []
        
        if self.config.get("controller_url"):
            urls_to_try.append(self.config["controller_url"])
        
        # Home Assistant
        ha_url = os.environ.get("HASS_URL")
        ha_token = os.environ.get("HASS_TOKEN")
        if ha_url and ha_token:
            urls_to_try.append(("homeassistant", ha_url, ha_token))
        
        # Local Matter controller
        urls_to_try.append(("chip-tool", "http://localhost:5580", None))
        
        for entry in urls_to_try:
            if isinstance(entry, tuple):
                ctrl_type, url, token = entry
                if await self._check_controller(ctrl_type, url, token):
                    self._controller_url = url
                    self._controller_type = ctrl_type
                    self._controller_token = token
                    return True
            else:
                if await self._check_controller("generic", entry, None):
                    self._controller_url = entry
                    return True
        
        return False
    
    async def _check_controller(self, ctrl_type: str, url: str, token: Optional[str]) -> bool:
        """Check if Matter controller is reachable."""
        try:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            
            async with aiohttp.ClientSession(headers=headers) as session:
                if ctrl_type == "homeassistant":
                    # Check for Matter integration
                    async with session.get(f"{url}/api/config") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            # Check if matter component is loaded
                            return "matter" in data.get("components", [])
                else:
                    # Generic controller health check
                    async with session.get(f"{url}/health") as resp:
                        return resp.status == 200
        except:
            pass
        return False
    
    async def connect(self) -> bool:
        """Connect and enumerate devices."""
        if not self._controller_url:
            return False
        
        self._state = AdapterState.DISCOVERING
        
        headers = {}
        if hasattr(self, '_controller_token') and self._controller_token:
            headers["Authorization"] = f"Bearer {self._controller_token}"
        
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers=headers
        )
        
        try:
            await self._refresh_devices()
            self._build_capabilities()
            self._build_tools()
            self._state = AdapterState.CONNECTED
            return True
        except Exception:
            self._state = AdapterState.ERROR
            return False
    
    async def _refresh_devices(self) -> None:
        """Refresh device list from controller."""
        if getattr(self, '_controller_type', '') == "homeassistant":
            # Home Assistant API
            async with self._session.get(
                f"{self._controller_url}/api/states"
            ) as resp:
                if resp.status == 200:
                    states = await resp.json()
                    # Filter for Matter devices
                    self._devices = [
                        s for s in states 
                        if s.get("attributes", {}).get("matter_device_id")
                    ]
        else:
            # Generic Matter controller API
            async with self._session.get(
                f"{self._controller_url}/devices"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._devices = data.get("devices", [])
    
    def _build_capabilities(self) -> None:
        """Build capabilities from Matter devices."""
        self._capabilities = []
        
        # Group devices by type
        device_types = {}
        for device in self._devices:
            clusters = device.get("clusters", [])
            for cluster in clusters:
                cap_type = self.CLUSTER_CAPABILITIES.get(cluster)
                if cap_type:
                    if cap_type not in device_types:
                        device_types[cap_type] = []
                    device_types[cap_type].append(device)
        
        # Create capabilities
        for cap_type, devices in device_types.items():
            device_names = [d.get("name", d.get("node_id")) for d in devices]
            
            self._capabilities.append(Capability(
                id=f"{self.adapter_id}:{cap_type}",
                type="device",
                name=f"Matter {cap_type.title()}s",
                description=f"Control Matter {cap_type} devices: {', '.join(device_names)}",
                metadata={
                    "device_type": cap_type,
                    "device_count": len(devices),
                    "device_ids": [d.get("node_id") for d in devices]
                }
            ))
    
    def _build_tools(self) -> None:
        """Build tools for device control."""
        self._tools = []
        
        for device in self._devices:
            device_id = device.get("node_id") or device.get("entity_id")
            device_name = device.get("name", device_id)
            clusters = device.get("clusters", [])
            
            # Generate tools based on device clusters
            if "OnOff" in clusters:
                self._tools.append(Tool(
                    name=f"matter_{device_id}_power",
                    description=f"Turn {device_name} on or off",
                    parameters={
                        "type": "object",
                        "properties": {
                            "state": {
                                "type": "string",
                                "enum": ["on", "off", "toggle"],
                                "description": "Desired power state"
                            }
                        },
                        "required": ["state"]
                    },
                    capability_id=f"{self.adapter_id}:switch"
                ))
            
            if "LevelControl" in clusters:
                self._tools.append(Tool(
                    name=f"matter_{device_id}_level",
                    description=f"Set {device_name} brightness/level (0-100)",
                    parameters={
                        "type": "object",
                        "properties": {
                            "level": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 100,
                                "description": "Level percentage"
                            },
                            "transition_time": {
                                "type": "number",
                                "description": "Transition time in seconds"
                            }
                        },
                        "required": ["level"]
                    },
                    capability_id=f"{self.adapter_id}:dimmer"
                ))
            
            if "ColorControl" in clusters:
                self._tools.append(Tool(
                    name=f"matter_{device_id}_color",
                    description=f"Set {device_name} color",
                    parameters={
                        "type": "object",
                        "properties": {
                            "hue": {"type": "integer", "minimum": 0, "maximum": 360},
                            "saturation": {"type": "integer", "minimum": 0, "maximum": 100},
                            "color_temp": {"type": "integer", "description": "Color temp in Kelvin"}
                        }
                    },
                    capability_id=f"{self.adapter_id}:light"
                ))
            
            if "Thermostat" in clusters:
                self._tools.append(Tool(
                    name=f"matter_{device_id}_climate",
                    description=f"Control {device_name} thermostat",
                    parameters={
                        "type": "object",
                        "properties": {
                            "mode": {
                                "type": "string",
                                "enum": ["heat", "cool", "auto", "off"]
                            },
                            "target_temp": {
                                "type": "number",
                                "description": "Target temperature"
                            }
                        }
                    },
                    capability_id=f"{self.adapter_id}:climate"
                ))
        
        # Also create aggregate tools
        self._tools.append(Tool(
            name="matter_all_lights_off",
            description="Turn off all Matter lights",
            parameters={"type": "object", "properties": {}},
            capability_id=f"{self.adapter_id}:switch"
        ))
        
        self._tools.append(Tool(
            name="matter_scene",
            description="Activate a Matter scene by name",
            parameters={
                "type": "object",
                "properties": {
                    "scene_name": {"type": "string", "description": "Scene name"}
                },
                "required": ["scene_name"]
            },
            capability_id=f"{self.adapter_id}:switch"
        ))
    
    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Execute Matter device command."""
        import time
        start = time.time()
        
        try:
            if tool_name == "matter_all_lights_off":
                result = await self._all_lights_off()
            elif tool_name == "matter_scene":
                result = await self._activate_scene(params["scene_name"])
            elif "_power" in tool_name:
                device_id = tool_name.replace("matter_", "").replace("_power", "")
                result = await self._set_power(device_id, params["state"])
            elif "_level" in tool_name:
                device_id = tool_name.replace("matter_", "").replace("_level", "")
                result = await self._set_level(device_id, params["level"], params.get("transition_time"))
            elif "_color" in tool_name:
                device_id = tool_name.replace("matter_", "").replace("_color", "")
                result = await self._set_color(device_id, params)
            elif "_climate" in tool_name:
                device_id = tool_name.replace("matter_", "").replace("_climate", "")
                result = await self._set_climate(device_id, params)
            else:
                return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
            
            return ToolResult(
                success=True,
                data=result,
                duration_ms=(time.time() - start) * 1000
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000
            )
    
    async def _set_power(self, device_id: str, state: str) -> Dict:
        """Set device power state."""
        if getattr(self, '_controller_type', '') == "homeassistant":
            service = "turn_on" if state == "on" else "turn_off" if state == "off" else "toggle"
            async with self._session.post(
                f"{self._controller_url}/api/services/switch/{service}",
                json={"entity_id": device_id}
            ) as resp:
                return {"status": "ok" if resp.status == 200 else "error"}
        else:
            # Generic Matter API
            async with self._session.post(
                f"{self._controller_url}/devices/{device_id}/clusters/OnOff",
                json={"command": state.title()}
            ) as resp:
                return await resp.json()
    
    async def _set_level(self, device_id: str, level: int, transition: Optional[float]) -> Dict:
        """Set device level."""
        # Implementation depends on controller type
        return {"device_id": device_id, "level": level, "status": "ok"}
    
    async def _set_color(self, device_id: str, params: Dict) -> Dict:
        """Set device color."""
        return {"device_id": device_id, "color": params, "status": "ok"}
    
    async def _set_climate(self, device_id: str, params: Dict) -> Dict:
        """Set thermostat settings."""
        return {"device_id": device_id, "climate": params, "status": "ok"}
    
    async def _all_lights_off(self) -> Dict:
        """Turn off all lights."""
        results = []
        for device in self._devices:
            if "OnOff" in device.get("clusters", []):
                device_id = device.get("node_id") or device.get("entity_id")
                result = await self._set_power(device_id, "off")
                results.append(result)
        return {"devices_affected": len(results)}
    
    async def _activate_scene(self, scene_name: str) -> Dict:
        """Activate a scene."""
        return {"scene": scene_name, "status": "ok"}
    
    async def health_check(self) -> HealthStatus:
        """Check Matter controller health."""
        import time
        start = time.time()
        
        try:
            if getattr(self, '_controller_type', '') == "homeassistant":
                async with self._session.get(f"{self._controller_url}/api/") as resp:
                    latency = (time.time() - start) * 1000
                    healthy = resp.status == 200
            else:
                async with self._session.get(f"{self._controller_url}/health") as resp:
                    latency = (time.time() - start) * 1000
                    healthy = resp.status == 200
            
            self._state = AdapterState.CONNECTED if healthy else AdapterState.DEGRADED
            return HealthStatus(
                healthy=healthy,
                state=self._state,
                latency_ms=latency,
                details={"device_count": len(self._devices)}
            )
        except Exception as e:
            self._state = AdapterState.DISCONNECTED
            return HealthStatus(healthy=False, state=self._state, message=str(e))
```

---

## Cloud API Adapter Pattern

For external APIs (OpenAI, Anthropic, web services):

```python
class CloudAPIAdapter(AtmosphereAdapter):
    """
    Base adapter for cloud APIs.
    
    Key considerations:
    - API keys must NEVER be gossiped
    - Only capability availability is advertised
    - Rate limiting and cost tracking
    - Automatic fallback on quota exhaustion
    
    Subclasses:
    - OpenAIAdapter
    - AnthropicAdapter
    - WebSearchAdapter
    - etc.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self._api_key: Optional[str] = None
        self._rate_limiter: Optional[RateLimiter] = None
        self._usage_tracker: Optional[UsageTracker] = None
    
    @property
    def requires_api_key(self) -> bool:
        """Whether this API requires authentication."""
        return True
    
    @property
    def api_key_env_var(self) -> str:
        """Environment variable for API key."""
        return f"{self.adapter_id.upper()}_API_KEY"
    
    async def discover(self) -> bool:
        """
        Check if API is available.
        
        For cloud APIs, this checks:
        1. API key is configured
        2. Network is available
        3. API responds (optional health check)
        """
        import os
        
        # Check for API key
        self._api_key = (
            self.config.get("api_key") or
            os.environ.get(self.api_key_env_var)
        )
        
        if self.requires_api_key and not self._api_key:
            return False
        
        # Check network
        if not await self._check_network():
            return False
        
        return True
    
    async def _check_network(self) -> bool:
        """Check network availability."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://1.1.1.1", timeout=5) as resp:
                    return resp.status in (200, 301, 302)
        except:
            return False
    
    def get_capabilities(self) -> List[Capability]:
        """
        Return capabilities WITHOUT exposing API key.
        
        The capability metadata should NOT contain secrets.
        """
        caps = super().get_capabilities()
        
        # Ensure no secrets leak
        for cap in caps:
            cap.metadata.pop("api_key", None)
            cap.metadata.pop("secret", None)
            cap.metadata.pop("token", None)
        
        return caps


class OpenAIAdapter(CloudAPIAdapter):
    """Adapter for OpenAI API."""
    
    BASE_URL = "https://api.openai.com/v1"
    
    @property
    def adapter_id(self) -> str:
        return "openai"
    
    @property
    def adapter_name(self) -> str:
        return "OpenAI"
    
    @property
    def api_key_env_var(self) -> str:
        return "OPENAI_API_KEY"
    
    async def connect(self) -> bool:
        if not self._api_key:
            return False
        
        self._session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=aiohttp.ClientTimeout(total=120)
        )
        
        # Verify key works
        try:
            async with self._session.get(f"{self.BASE_URL}/models") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._models = data.get("data", [])
                    self._build_capabilities()
                    self._build_tools()
                    self._state = AdapterState.CONNECTED
                    return True
                elif resp.status == 401:
                    self._state = AdapterState.ERROR
                    return False
        except Exception:
            self._state = AdapterState.ERROR
            return False
        
        return False
    
    def _build_capabilities(self) -> None:
        self._capabilities = [
            Capability(
                id=f"{self.adapter_id}:llm",
                type="llm",
                name="OpenAI GPT",
                description="OpenAI GPT models for chat and completion",
                models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
                metadata={"provider": "openai", "cloud": True}
            ),
            Capability(
                id=f"{self.adapter_id}:embeddings",
                type="embeddings",
                name="OpenAI Embeddings",
                description="OpenAI text embeddings",
                models=["text-embedding-3-small", "text-embedding-3-large"]
            ),
            Capability(
                id=f"{self.adapter_id}:vision",
                type="vision",
                name="OpenAI Vision",
                description="GPT-4 Vision for image analysis",
                models=["gpt-4o"]
            ),
            Capability(
                id=f"{self.adapter_id}:tts",
                type="audio",
                name="OpenAI TTS",
                description="Text to speech synthesis",
                models=["tts-1", "tts-1-hd"]
            ),
            Capability(
                id=f"{self.adapter_id}:stt",
                type="audio",
                name="OpenAI Whisper",
                description="Speech to text transcription",
                models=["whisper-1"]
            )
        ]
    
    def _build_tools(self) -> None:
        self._tools = [
            Tool(
                name="openai_chat",
                description="Chat with OpenAI GPT models",
                parameters={
                    "type": "object",
                    "properties": {
                        "messages": {"type": "array", "items": {"type": "object"}},
                        "model": {"type": "string", "default": "gpt-4o-mini"},
                        "temperature": {"type": "number", "default": 0.7}
                    },
                    "required": ["messages"]
                },
                capability_id=f"{self.adapter_id}:llm"
            ),
            Tool(
                name="openai_embed",
                description="Generate embeddings with OpenAI",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "model": {"type": "string", "default": "text-embedding-3-small"}
                    },
                    "required": ["text"]
                },
                capability_id=f"{self.adapter_id}:embeddings"
            )
        ]
    
    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        import time
        start = time.time()
        
        try:
            if tool_name == "openai_chat":
                async with self._session.post(
                    f"{self.BASE_URL}/chat/completions",
                    json={
                        "model": params.get("model", "gpt-4o-mini"),
                        "messages": params["messages"],
                        "temperature": params.get("temperature", 0.7)
                    }
                ) as resp:
                    data = await resp.json()
                    return ToolResult(
                        success=resp.status == 200,
                        data=data,
                        duration_ms=(time.time() - start) * 1000,
                        usage=data.get("usage", {})
                    )
            
            elif tool_name == "openai_embed":
                async with self._session.post(
                    f"{self.BASE_URL}/embeddings",
                    json={
                        "model": params.get("model", "text-embedding-3-small"),
                        "input": params["text"]
                    }
                ) as resp:
                    data = await resp.json()
                    return ToolResult(
                        success=resp.status == 200,
                        data=data,
                        duration_ms=(time.time() - start) * 1000,
                        usage=data.get("usage", {})
                    )
            
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000
            )
    
    async def health_check(self) -> HealthStatus:
        import time
        start = time.time()
        
        try:
            async with self._session.get(f"{self.BASE_URL}/models") as resp:
                return HealthStatus(
                    healthy=resp.status == 200,
                    state=AdapterState.CONNECTED if resp.status == 200 else AdapterState.DEGRADED,
                    latency_ms=(time.time() - start) * 1000
                )
        except Exception as e:
            return HealthStatus(
                healthy=False,
                state=AdapterState.DISCONNECTED,
                message=str(e)
            )
```

### Secret Management

```python
class SecretManager:
    """
    Manages API keys and secrets for adapters.
    
    Secrets are:
    - Stored locally (never gossiped)
    - Loaded from config, environment, or secure store
    - Available only to local adapters
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self._secrets: Dict[str, str] = {}
        self._config_path = config_path
    
    def get(self, key: str) -> Optional[str]:
        """Get a secret by key."""
        import os
        
        # Check cache
        if key in self._secrets:
            return self._secrets[key]
        
        # Check environment
        env_key = key.upper().replace(".", "_")
        if env_value := os.environ.get(env_key):
            self._secrets[key] = env_value
            return env_value
        
        # Check config file
        if self._config_path:
            # Load from secure config
            pass
        
        return None
    
    def set(self, key: str, value: str) -> None:
        """Set a secret (memory only, call save() to persist)."""
        self._secrets[key] = value
    
    def clear(self, key: str) -> None:
        """Clear a secret."""
        self._secrets.pop(key, None)
```

---

## Custom Adapter Guide

How to create your own adapter:

### Step 1: Define Your Adapter Class

```python
from atmosphere.adapters.base import (
    AtmosphereAdapter, 
    Capability, 
    Tool, 
    ToolResult,
    HealthStatus,
    AdapterState
)


class MySystemAdapter(AtmosphereAdapter):
    """
    Adapter for MySystem.
    
    MySystem provides:
    - [List what your system does]
    """
    
    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        # Your initialization
    
    @property
    def adapter_id(self) -> str:
        return "mysystem"  # Unique identifier
    
    @property
    def adapter_name(self) -> str:
        return "MySystem"  # Human-readable name
```

### Step 2: Implement Discovery

```python
    async def discover(self) -> bool:
        """
        Check if MySystem is available.
        
        Be fast and non-destructive.
        """
        try:
            # Check your system's availability
            # Examples:
            # - HTTP health endpoint
            # - Socket connection
            # - File existence
            # - Process running
            
            return await self._check_mysystem()
        except:
            return False
    
    async def _check_mysystem(self) -> bool:
        """Your specific check logic."""
        # Implement your check
        pass
```

### Step 3: Implement Connection

```python
    async def connect(self) -> bool:
        """
        Establish connection and enumerate capabilities.
        """
        self._state = AdapterState.DISCOVERING
        
        try:
            # 1. Connect to your system
            # 2. Query available features
            # 3. Build capabilities and tools
            
            await self._establish_connection()
            await self._query_features()
            
            self._build_capabilities()
            self._build_tools()
            
            self._state = AdapterState.CONNECTED
            return True
            
        except Exception as e:
            self._state = AdapterState.ERROR
            return False
    
    def _build_capabilities(self) -> None:
        """Build capabilities based on your system's features."""
        self._capabilities = [
            Capability(
                id=f"{self.adapter_id}:feature1",
                type="your_type",  # llm, device, sensor, etc.
                name="Feature 1",
                description="Does amazing things",
                # Add models if applicable
                # Add constraints if needed
            ),
            # More capabilities...
        ]
    
    def _build_tools(self) -> None:
        """Build tools from capabilities."""
        self._tools = [
            Tool(
                name="mysystem_do_thing",
                description="Does the thing",
                parameters={
                    "type": "object",
                    "properties": {
                        "input": {"type": "string"}
                    },
                    "required": ["input"]
                },
                capability_id=f"{self.adapter_id}:feature1"
            ),
            # More tools...
        ]
```

### Step 4: Implement Tool Execution

```python
    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Execute a tool call."""
        import time
        start = time.time()
        
        try:
            # Dispatch to appropriate handler
            if tool_name == "mysystem_do_thing":
                result = await self._do_thing(params["input"])
            else:
                return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
            
            return ToolResult(
                success=True,
                data=result,
                duration_ms=(time.time() - start) * 1000
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000
            )
    
    async def _do_thing(self, input: str) -> Any:
        """Your actual implementation."""
        # Call your system
        pass
```

### Step 5: Implement Health Check

```python
    async def health_check(self) -> HealthStatus:
        """Periodic health check."""
        import time
        start = time.time()
        
        try:
            healthy = await self._check_mysystem()
            self._state = AdapterState.CONNECTED if healthy else AdapterState.DEGRADED
            
            return HealthStatus(
                healthy=healthy,
                state=self._state,
                latency_ms=(time.time() - start) * 1000
            )
            
        except Exception as e:
            self._state = AdapterState.DISCONNECTED
            return HealthStatus(
                healthy=False,
                state=self._state,
                message=str(e)
            )
```

### Step 6: Register Your Adapter

```python
# In your code:
from atmosphere.adapters import AdapterRegistry

registry = AdapterRegistry()
registry.register(MySystemAdapter())
await registry.start()
```

Or create an entry point for automatic discovery:

```python
# setup.py or pyproject.toml
[project.entry-points."atmosphere.adapters"]
mysystem = "mypackage.adapters:MySystemAdapter"
```

---

## Adapter Registration with the Mesh

When adapters connect/disconnect, the mesh needs to know:

```python
class MeshCapabilityAnnouncer:
    """
    Announces adapter capabilities to the mesh.
    
    When adapters change:
    1. Aggregate all capabilities
    2. Convert to gossip-safe format
    3. Announce via gossip protocol
    """
    
    def __init__(self, registry: AdapterRegistry, mesh: MeshNode):
        self._registry = registry
        self._mesh = mesh
        self._last_announced: Dict[str, Any] = {}
    
    async def on_adapter_change(self, adapter: AtmosphereAdapter) -> None:
        """Called when an adapter's state changes."""
        await self.announce()
    
    async def announce(self) -> None:
        """Announce current capabilities to mesh."""
        # Gather all capabilities
        capabilities = self._registry.get_all_capabilities()
        
        # Convert to gossip format (no secrets!)
        gossip_caps = []
        for cap in capabilities:
            gossip_caps.append({
                "id": cap.id,
                "type": cap.type,
                "name": cap.name,
                "description": cap.description,
                "models": cap.models,
                # Exclude: metadata that might contain secrets
            })
        
        # Check if changed
        new_hash = self._hash_capabilities(gossip_caps)
        if new_hash == self._last_announced.get("hash"):
            return  # No change
        
        # Announce via gossip
        await self._mesh.gossip.announce_capabilities(gossip_caps)
        
        self._last_announced = {
            "hash": new_hash,
            "time": time.time(),
            "capabilities": gossip_caps
        }
    
    def _hash_capabilities(self, caps: List[Dict]) -> str:
        import hashlib
        import json
        content = json.dumps(caps, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
```

---

## Capability and Tool Flow

### Flow: Intent → Tool Execution

```
1. User: "Turn on the living room lights"
   ↓
2. Intent Router:
   - Embed intent
   - Find matching capabilities: matter:switch (score: 0.92)
   - Route: local (matter adapter has it)
   ↓
3. Adapter Registry:
   - Look up capability_id → matter adapter
   - Find best tool: matter_living_room_power
   ↓
4. Matter Adapter:
   - execute_tool("matter_living_room_power", {"state": "on"})
   - Call Home Assistant API
   ↓
5. Result flows back:
   ToolResult(success=True, data={"status": "ok"})
```

### Flow: Remote Execution (Multi-Hop)

```
1. Node A: "Analyze this image" (no vision capability)
   ↓
2. Intent Router (Node A):
   - No local vision capability
   - Check gradient table: Node B has ollama:vision
   ↓
3. Forward to Node B:
   - Signed execution request
   - Include image data
   ↓
4. Node B executes:
   - Ollama adapter processes image
   - Returns result
   ↓
5. Node A receives result
```

---

## Summary

| Adapter | Discovery | Capabilities | Key Tools |
|---------|-----------|--------------|-----------|
| **LlamaFarm** | HTTP :14345, :8000 | llm, embeddings, rag, vision, agents | chat, generate, embed, rag_query |
| **Ollama** | HTTP :11434 | llm, embeddings, vision (model-dependent) | generate, chat, embed, vision |
| **Matter** | mDNS, Home Assistant | device:switch, device:light, etc. | power, level, color, climate |
| **OpenAI** | API key + network | llm, embeddings, vision, audio | chat, embed, vision |
| **Custom** | User-defined | User-defined | User-defined |

### Key Points

1. **Adapters are local** — They run on nodes, not in the mesh
2. **Capabilities are global** — They propagate via gossip
3. **Secrets stay local** — API keys never leave the node
4. **Tools are the interface** — LLMs call tools, adapters execute them
5. **Health is monitored** — Adapters self-report, mesh routes around failures

---

## Next Steps

1. Implement `AtmosphereAdapter` base class
2. Port existing `discovery/` code to adapter pattern
3. Create Matter adapter prototype
4. Design tool schema validation
5. Implement capability announcer for gossip
