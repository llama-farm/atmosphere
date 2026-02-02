# Tool System Design

## Overview

Tools are the **actions** that agents can perform in Atmosphere. While capabilities describe what a node *can do* (compute resources, sensors, network access), tools are the specific *functions* agents invoke to accomplish tasks.

```
Capability: "I have GPU compute power"
Tool: analyze_image(image, task) -> detected_objects[]

Capability: "I can send notifications"  
Tool: notify(recipient, message, urgency) -> delivery_status
```

### The Hierarchy

```
Intent (what you want)
    ↓
Routing (find who can help)
    ↓
Capability (what's available)
    ↓
Tool (how to do it)
    ↓
Result (what happened)
```

---

## 1. What IS a Tool?

### Definition

A **tool** is a typed, invocable function with:
- A unique identifier
- Input parameters (validated)
- Output type
- Required capabilities
- Execution constraints
- Permission requirements

### Tools vs Capabilities

| Aspect | Capability | Tool |
|--------|------------|------|
| Abstraction | Resource/ability | Specific action |
| Example | `vision` | `detect_faces(image)` |
| Discovery | Advertised via gossip | Registered with capabilities |
| Matching | Semantic similarity | Exact name + parameter binding |
| Runtime | Always present on node | May be dynamically loaded |

A capability is like "I have a kitchen" — a tool is "make_sandwich(bread, filling)".

### Tool Identity

Tools are identified by:
```
[namespace:]tool_name[@version]

Examples:
  notify                      # Core tool, latest
  matter:turn_on_light        # Matter namespace
  custom:my_analyzer@1.2.0    # Versioned custom tool
```

---

## 2. Tool Definition Schema

### JSON Schema

```json
{
  "$schema": "https://atmosphere.dev/schemas/tool/v1",
  "tool": {
    "name": "notify",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Send notification to a person, device, or channel",
    
    "parameters": {
      "type": "object",
      "required": ["recipient", "message"],
      "properties": {
        "recipient": {
          "type": "string",
          "description": "Email, phone, @handle, or channel ID",
          "pattern": "^[@#]?[\\w.-]+$"
        },
        "message": {
          "type": "string",
          "description": "Notification content",
          "maxLength": 4096
        },
        "urgency": {
          "type": "string",
          "enum": ["low", "medium", "high", "critical"],
          "default": "medium",
          "description": "Delivery priority"
        },
        "channels": {
          "type": "array",
          "items": { "type": "string", "enum": ["push", "sms", "email", "slack"] },
          "description": "Preferred delivery channels (auto if omitted)"
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "delivered": { "type": "boolean" },
        "delivery_id": { "type": "string" },
        "channel_used": { "type": "string" },
        "timestamp": { "type": "string", "format": "date-time" }
      }
    },
    
    "requires": {
      "capabilities": ["notification"],
      "permissions": ["notify:send"],
      "network": true,
      "gpu": false
    },
    
    "execution": {
      "timeout_ms": 30000,
      "retries": 2,
      "idempotent": false,
      "async_allowed": true
    },
    
    "routing": {
      "prefer_local": false,
      "node_affinity": [],
      "hop_limit": 3
    },
    
    "metadata": {
      "category": "communicating",
      "tags": ["notification", "messaging", "alert"],
      "author": "atmosphere",
      "examples": [
        {
          "description": "Send urgent alert",
          "params": { "recipient": "rob@email.com", "message": "Server down!", "urgency": "critical" }
        }
      ]
    }
  }
}
```

### Python Decorator Syntax

Tools can also be defined via decorators:

```python
from atmosphere.tools import tool, param

@tool(
    name="notify",
    namespace="core",
    requires=["notification"],
    permissions=["notify:send"]
)
async def notify(
    recipient: str = param(description="Email, phone, @handle, or channel ID"),
    message: str = param(description="Notification content", max_length=4096),
    urgency: str = param(enum=["low", "medium", "high", "critical"], default="medium")
) -> dict:
    """Send notification to a person, device, or channel."""
    # Implementation
    return {"delivered": True, "delivery_id": "abc123"}
```

### Tool Manifest Files

Nodes expose tools via manifest:

```yaml
# ~/.atmosphere/tools.yaml
tools:
  - name: analyze_image
    source: builtin:vision
    config:
      default_model: llava:7b
      
  - name: query_temperature
    source: plugin:sensors
    config:
      device: /dev/thermal0
      
  - name: custom_analyzer
    source: file:./my_tools/analyzer.py
    entry: analyze
```

---

## 3. Tool Registry and Discovery

### Local Registry

Each node maintains a local tool registry:

```python
class ToolRegistry:
    """Registry of available tools on this node."""
    
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self.handlers: Dict[str, Callable] = {}
    
    def register(self, tool: ToolDefinition, handler: Callable):
        """Register a tool with its handler."""
        key = f"{tool.namespace}:{tool.name}"
        self.tools[key] = tool
        self.handlers[key] = handler
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name (with or without namespace)."""
        if ":" in name:
            return self.tools.get(name)
        # Search all namespaces
        for key, tool in self.tools.items():
            if key.endswith(f":{name}"):
                return tool
        return None
    
    def list_by_capability(self, capability: str) -> List[ToolDefinition]:
        """Get all tools requiring a specific capability."""
        return [t for t in self.tools.values() if capability in t.requires.capabilities]
```

### Mesh-Wide Discovery

Tools propagate through the gossip protocol alongside capabilities:

```json
{
  "type": "capability_announce",
  "node_id": "node-abc123",
  "capabilities": [
    {
      "type": "vision",
      "description": "Image analysis with GPU acceleration",
      "tools": [
        {
          "name": "analyze_image",
          "description": "Detect objects, classify, segment images",
          "parameters_hash": "sha256:abc...",  // For caching
          "constraints": { "gpu": true, "max_image_mb": 50 }
        },
        {
          "name": "detect_faces",
          "description": "Find and identify faces in images"
        }
      ]
    }
  ],
  "timestamp": "2025-02-02T12:00:00Z",
  "signature": "ed25519:..."
}
```

### Tool Discovery Protocol

```
Agent: "I need to notify someone"
    ↓
Router: Semantic match → "notification" capability
    ↓
Registry: Which nodes have notification capability?
    ↓
Tool List: [notify, send_email, send_sms, post_slack]
    ↓
Selection: Best tool for this specific task
    ↓
Invoke: Route to best node, call tool
```

### Discovery Queries

```python
# Find tools by semantic intent
tools = await mesh.discover_tools("send an alert to the user")
# Returns: [notify, send_push, send_sms] with scores

# Find tools by capability
tools = await mesh.find_tools_by_capability("vision")
# Returns: [analyze_image, detect_faces, ocr]

# Find tools by category
tools = await mesh.find_tools_by_category("sensing")
# Returns: [query_sensor, get_camera_frame, read_temperature]
```

---

## 4. Tool Invocation Protocol

### Invocation Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Agent     │────▶│   Router     │────▶│ Target Node │
│             │     │              │     │             │
│ invoke()    │     │ find_node()  │     │ execute()   │
└─────────────┘     └──────────────┘     └─────────────┘
      │                    │                    │
      │  ToolRequest       │  RoutedRequest     │
      │─────────────────▶  │─────────────────▶  │
      │                    │                    │
      │                    │   ToolResponse     │
      │◀────────────────────────────────────────│
      │                    │                    │
```

### Request Message

```json
{
  "type": "tool_invoke",
  "id": "req-uuid-123",
  "tool": "notify",
  "version": ">=1.0.0",
  "params": {
    "recipient": "rob@email.com",
    "message": "Server CPU at 95%!",
    "urgency": "high"
  },
  "context": {
    "agent_id": "monitor-agent-1",
    "session_id": "sess-456",
    "trace_id": "trace-789"
  },
  "routing": {
    "prefer_nodes": [],
    "exclude_nodes": [],
    "hop_budget": 3,
    "timeout_ms": 30000
  },
  "auth": {
    "token": "eyJ...",
    "capabilities_proof": "..."
  },
  "timestamp": "2025-02-02T12:00:00Z",
  "signature": "ed25519:..."
}
```

### Response Message

```json
{
  "type": "tool_response",
  "id": "resp-uuid-789",
  "request_id": "req-uuid-123",
  "status": "success",
  "result": {
    "delivered": true,
    "delivery_id": "del-abc",
    "channel_used": "push",
    "timestamp": "2025-02-02T12:00:01Z"
  },
  "execution": {
    "node_id": "node-xyz",
    "duration_ms": 234,
    "hops": 1
  },
  "timestamp": "2025-02-02T12:00:01Z",
  "signature": "ed25519:..."
}
```

### Error Response

```json
{
  "type": "tool_response",
  "id": "resp-uuid-790",
  "request_id": "req-uuid-123",
  "status": "error",
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "Agent lacks notify:send permission",
    "details": {
      "required": ["notify:send"],
      "actual": ["notify:read"]
    },
    "retryable": false
  }
}
```

### Sync vs Async Invocation

**Synchronous** (default for fast tools):
```python
result = await tool.invoke("notify", recipient="rob", message="Hello")
# Blocks until complete or timeout
```

**Asynchronous** (for long-running tools):
```python
job = await tool.invoke_async("analyze_video", video_url="...", duration="1h")
# Returns immediately with job ID

# Poll for completion
status = await tool.job_status(job.id)
if status.complete:
    result = status.result
```

### Routing Algorithm

```python
async def route_tool_invocation(request: ToolRequest) -> ToolResponse:
    # 1. Find tool definition
    tool = registry.get(request.tool)
    if not tool:
        raise ToolNotFoundError(request.tool)
    
    # 2. Validate parameters
    validate_params(tool.parameters, request.params)
    
    # 3. Check permissions
    if not auth.has_permissions(request.auth, tool.requires.permissions):
        raise PermissionDeniedError(tool.requires.permissions)
    
    # 4. Find capable nodes
    nodes = await mesh.find_nodes_with_capability(tool.requires.capabilities)
    
    # 5. Score and rank nodes
    scored = []
    for node in nodes:
        score = 1.0
        score *= 0.95 ** node.hops  # Hop penalty
        if tool.routing.prefer_local and node.is_local:
            score *= 1.2  # Local preference
        if node.id in request.routing.prefer_nodes:
            score *= 1.1  # Explicit preference
        scored.append((node, score))
    
    scored.sort(key=lambda x: -x[1])
    
    # 6. Try nodes in order
    for node, score in scored:
        try:
            return await node.execute_tool(request)
        except NodeUnavailableError:
            continue
    
    raise NoCapableNodeError(tool.name)
```

### Timeouts and Retries

```python
class InvocationPolicy:
    timeout_ms: int = 30000          # Overall timeout
    connect_timeout_ms: int = 5000   # Connection timeout
    retries: int = 2                 # Retry count
    retry_delay_ms: int = 1000       # Delay between retries
    retry_backoff: float = 2.0       # Exponential backoff
    
    idempotency_key: Optional[str]   # For safe retries
```

---

## 5. Tool Categories

### Sensing Tools

```yaml
category: sensing
description: Tools that observe the world

tools:
  - name: query_sensor
    description: Read value from a sensor
    params:
      sensor_id: string
      time_range: { start: datetime, end: datetime }
    returns: { values: array, unit: string }
    requires: [sensor_access]
    
  - name: get_camera_frame
    description: Capture current frame from camera
    params:
      camera_id: string
      resolution: { width: int, height: int }
    returns: { image: binary, timestamp: datetime }
    requires: [camera_access]
    
  - name: read_temperature
    description: Get temperature reading
    params:
      location: string
      unit: enum [celsius, fahrenheit, kelvin]
    returns: { value: float, unit: string }
    requires: [sensor_access]
    
  - name: get_location
    description: Get device location
    params:
      device_id: string
      accuracy: enum [coarse, balanced, precise]
    returns: { lat: float, lon: float, accuracy_m: float }
    requires: [location_access]
```

### Acting Tools

```yaml
category: acting
description: Tools that change the world

tools:
  - name: control_device
    description: Send command to a device
    params:
      device_id: string
      command: string
      params: object
    returns: { success: bool, new_state: object }
    requires: [device_control]
    permissions: [device:control:{device_id}]
    
  - name: set_thermostat
    description: Set thermostat temperature
    params:
      device_id: string
      target_temp: float
      mode: enum [heat, cool, auto, off]
    returns: { success: bool, current_temp: float }
    requires: [thermostat_control]
    
  - name: turn_on_light
    description: Turn on a light
    params:
      device_id: string
      brightness: int [0-100]
      color: { r: int, g: int, b: int } | string
    returns: { success: bool, state: object }
    requires: [light_control]
```

### Communicating Tools

```yaml
category: communicating
description: Tools that send messages

tools:
  - name: notify
    description: Send notification to person/channel
    params:
      recipient: string
      message: string
      urgency: enum [low, medium, high, critical]
    returns: { delivered: bool, delivery_id: string }
    requires: [notification]
    permissions: [notify:send]
    
  - name: send_email
    description: Send email message
    params:
      to: array[string]
      subject: string
      body: string
      attachments: array[binary]
    returns: { sent: bool, message_id: string }
    requires: [email]
    permissions: [email:send]
    
  - name: post_slack
    description: Post message to Slack
    params:
      channel: string
      text: string
      thread_ts: optional string
    returns: { ok: bool, ts: string }
    requires: [slack_integration]
    
  - name: send_sms
    description: Send SMS message
    params:
      phone: string
      message: string
    returns: { delivered: bool, sid: string }
    requires: [sms]
    permissions: [sms:send]
```

### Querying Tools

```yaml
category: querying
description: Tools that retrieve information

tools:
  - name: search_web
    description: Search the web
    params:
      query: string
      count: int [1-100]
      freshness: enum [day, week, month, any]
    returns: { results: array[{ title, url, snippet }] }
    requires: [internet]
    
  - name: query_database
    description: Query a database
    params:
      database: string
      query: string
      params: array
    returns: { rows: array, columns: array }
    requires: [database_access]
    permissions: [db:query:{database}]
    
  - name: rag_search
    description: Search vector store for relevant context
    params:
      query: string
      collection: string
      limit: int
    returns: { documents: array[{ content, score, metadata }] }
    requires: [embeddings, vector_store]
    
  - name: fetch_url
    description: Fetch content from URL
    params:
      url: string
      extract_mode: enum [raw, markdown, text]
    returns: { content: string, content_type: string }
    requires: [internet]
```

### Computing Tools

```yaml
category: computing
description: Tools that process/transform data

tools:
  - name: run_model
    description: Run ML model inference
    params:
      model: string
      input: any
      params: object
    returns: { output: any, latency_ms: int }
    requires: [ml_runtime]
    
  - name: analyze_image
    description: Analyze image with vision model
    params:
      image: binary | string
      task: enum [detect_objects, classify, segment, ocr, describe]
      model: optional string
    returns: { result: any, confidence: float }
    requires: [vision]
    routing: { prefer_gpu: true }
    
  - name: transcribe_audio
    description: Convert audio to text
    params:
      audio: binary | string
      language: optional string
    returns: { text: string, segments: array }
    requires: [audio, speech_recognition]
    
  - name: generate_embedding
    description: Generate embedding vector
    params:
      text: string | array[string]
      model: optional string
    returns: { embeddings: array[array[float]] }
    requires: [embeddings]
    
  - name: llm_complete
    description: Generate text with LLM
    params:
      prompt: string
      system: optional string
      max_tokens: int
      temperature: float
    returns: { text: string, tokens_used: int }
    requires: [llm]
```

### Managing Tools

```yaml
category: managing
description: Tools that manage system resources

tools:
  - name: spawn_agent
    description: Create new agent instance
    params:
      spec: AgentSpec
      config: object
    returns: { agent_id: string, status: string }
    requires: [agent_runtime]
    permissions: [agent:spawn]
    
  - name: kill_agent
    description: Terminate an agent
    params:
      agent_id: string
      reason: optional string
    returns: { success: bool }
    requires: [agent_runtime]
    permissions: [agent:kill:{agent_id}]
    
  - name: adjust_threshold
    description: Modify agent threshold/parameter
    params:
      agent_id: string
      param: string
      value: any
    returns: { success: bool, old_value: any }
    requires: [agent_runtime]
    permissions: [agent:configure:{agent_id}]
    
  - name: store_data
    description: Store key-value data
    params:
      key: string
      value: any
      ttl_seconds: optional int
    returns: { success: bool, key: string }
    requires: [storage]
    permissions: [storage:write]
    
  - name: get_data
    description: Retrieve stored data
    params:
      key: string
    returns: { value: any, exists: bool }
    requires: [storage]
    permissions: [storage:read]
```

---

## 6. Permission Model

### Permission Structure

```
[namespace]:[action]:[resource]

Examples:
  notify:send              # Can send notifications
  device:control:*         # Can control any device
  device:control:light-1   # Can control specific light
  agent:spawn              # Can spawn agents
  storage:read:config/*    # Can read config keys
```

### Permission Hierarchy

```
root
├── notify
│   ├── send
│   └── read
├── device
│   ├── control
│   │   ├── light
│   │   ├── thermostat
│   │   └── lock
│   └── read
├── agent
│   ├── spawn
│   ├── kill
│   └── configure
├── storage
│   ├── read
│   └── write
└── admin
    └── *
```

### Token-Based Permissions

Permissions are embedded in agent tokens:

```json
{
  "type": "agent_token",
  "agent_id": "monitor-agent-1",
  "issued_at": "2025-02-02T00:00:00Z",
  "expires_at": "2025-02-03T00:00:00Z",
  "permissions": [
    "notify:send",
    "sensor:read:*",
    "device:read:*"
  ],
  "constraints": {
    "max_hops": 2,
    "allowed_nodes": ["node-a", "node-b"],
    "rate_limit": { "per_minute": 100 }
  },
  "issuer": "mesh-root",
  "signature": "ed25519:..."
}
```

### Permission Checking

```python
class PermissionChecker:
    def has_permission(self, token: AgentToken, required: str) -> bool:
        """Check if token grants required permission."""
        for perm in token.permissions:
            if self._matches(perm, required):
                return True
        return False
    
    def _matches(self, granted: str, required: str) -> bool:
        """Check if granted permission covers required."""
        granted_parts = granted.split(":")
        required_parts = required.split(":")
        
        for g, r in zip(granted_parts, required_parts):
            if g == "*":
                return True
            if g != r:
                return False
        
        return len(granted_parts) >= len(required_parts)
```

### Dangerous Tool Protection

Tools marked as dangerous require additional safeguards:

```json
{
  "tool": {
    "name": "delete_all_data",
    "dangerous": true,
    "requires": {
      "permissions": ["admin:destroy"],
      "confirmation": true,
      "multi_party": 2
    },
    "audit": {
      "log_params": true,
      "log_result": true,
      "notify_admins": true
    }
  }
}
```

Multi-party approval flow:
```
Agent: invoke("delete_all_data", ...)
    ↓
System: "Dangerous operation. Requires 2 approvals."
    ↓
Admin 1: approve(request_id, signature)
Admin 2: approve(request_id, signature)
    ↓
System: Execute with full audit trail
```

---

## 7. Matter Device Integration

### Matter Clusters as Tools

Matter devices expose clusters, which map to tools:

```
Matter Device: Smart Light (light-living-room)
├── OnOff Cluster → turn_on_light, turn_off_light
├── LevelControl Cluster → set_brightness
├── ColorControl Cluster → set_color
└── OccupancySensing Cluster → get_occupancy
```

### Matter Tool Generator

```python
class MatterToolGenerator:
    """Generate Atmosphere tools from Matter device clusters."""
    
    CLUSTER_MAPPINGS = {
        "OnOff": {
            "tools": [
                {
                    "name": "turn_on",
                    "command": "On",
                    "params": {}
                },
                {
                    "name": "turn_off",
                    "command": "Off",
                    "params": {}
                },
                {
                    "name": "toggle",
                    "command": "Toggle",
                    "params": {}
                }
            ]
        },
        "LevelControl": {
            "tools": [
                {
                    "name": "set_level",
                    "command": "MoveToLevel",
                    "params": {
                        "level": {"type": "int", "min": 0, "max": 254},
                        "transition_time": {"type": "int", "default": 0}
                    }
                }
            ]
        },
        "Thermostat": {
            "tools": [
                {
                    "name": "set_temperature",
                    "command": "SetpointRaiseLower",
                    "params": {
                        "mode": {"type": "enum", "values": ["heat", "cool", "both"]},
                        "amount": {"type": "int"}
                    }
                }
            ]
        }
    }
    
    def generate_tools(self, device: MatterDevice) -> List[ToolDefinition]:
        """Generate tools for a Matter device."""
        tools = []
        for cluster in device.clusters:
            if cluster.name in self.CLUSTER_MAPPINGS:
                for tool_spec in self.CLUSTER_MAPPINGS[cluster.name]["tools"]:
                    tool = self._create_tool(device, cluster, tool_spec)
                    tools.append(tool)
        return tools
```

### Matter Tool Definition

```json
{
  "tool": {
    "name": "matter_command",
    "namespace": "matter",
    "description": "Send command to Matter/Thread device",
    
    "parameters": {
      "type": "object",
      "required": ["device_id", "cluster", "command"],
      "properties": {
        "device_id": {
          "type": "string",
          "description": "Matter device ID or friendly name"
        },
        "endpoint": {
          "type": "integer",
          "description": "Endpoint number (default: 1)",
          "default": 1
        },
        "cluster": {
          "type": "string",
          "description": "Cluster name (OnOff, LevelControl, etc.)"
        },
        "command": {
          "type": "string",
          "description": "Command name"
        },
        "params": {
          "type": "object",
          "description": "Command parameters"
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "success": { "type": "boolean" },
        "device_state": { "type": "object" },
        "error": { "type": "string" }
      }
    },
    
    "requires": {
      "capabilities": ["matter_bridge"],
      "permissions": ["device:control:{device_id}"]
    },
    
    "routing": {
      "node_affinity": ["matter-bridge-node"],
      "prefer_local": true,
      "hop_limit": 1
    }
  }
}
```

### Device-Specific Tool Generation

```python
# When a Matter device joins the network, generate friendly tools:

device = MatterDevice(
    id="light-living-room",
    type="extended_color_light",
    clusters=["OnOff", "LevelControl", "ColorControl"]
)

# Generated tools:
tools = [
    Tool(
        name="light_living_room_on",
        description="Turn on the living room light",
        params={},
        handler=lambda: matter.command("light-living-room", "OnOff", "On")
    ),
    Tool(
        name="light_living_room_off",
        description="Turn off the living room light",
        params={},
        handler=lambda: matter.command("light-living-room", "OnOff", "Off")
    ),
    Tool(
        name="light_living_room_brightness",
        description="Set living room light brightness",
        params={"level": int},
        handler=lambda level: matter.command("light-living-room", "LevelControl", "MoveToLevel", {"level": level})
    ),
    Tool(
        name="light_living_room_color",
        description="Set living room light color",
        params={"hue": int, "saturation": int},
        handler=lambda h, s: matter.command("light-living-room", "ColorControl", "MoveToHueAndSaturation", {"hue": h, "saturation": s})
    )
]
```

### Matter Bridge Capability Announcement

```json
{
  "type": "capability_announce",
  "node_id": "matter-bridge-01",
  "capabilities": [
    {
      "type": "matter_bridge",
      "description": "Matter/Thread bridge with 12 devices",
      "tools": [
        { "name": "matter:light_living_room_on" },
        { "name": "matter:light_living_room_off" },
        { "name": "matter:light_living_room_brightness" },
        { "name": "matter:thermostat_set_temp" },
        { "name": "matter:lock_front_door" }
      ],
      "devices": [
        {
          "id": "light-living-room",
          "name": "Living Room Light",
          "type": "extended_color_light",
          "reachable": true
        },
        {
          "id": "thermostat-main",
          "name": "Main Thermostat",
          "type": "thermostat",
          "reachable": true
        }
      ]
    }
  ]
}
```

---

## 8. Core Tool Definitions

### 1. notify

```json
{
  "tool": {
    "name": "notify",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Send notification to a person, device, or channel",
    "category": "communicating",
    
    "parameters": {
      "type": "object",
      "required": ["recipient", "message"],
      "properties": {
        "recipient": {
          "type": "string",
          "description": "Email, phone number, @handle, #channel, or device ID"
        },
        "message": {
          "type": "string",
          "maxLength": 4096
        },
        "urgency": {
          "type": "string",
          "enum": ["low", "medium", "high", "critical"],
          "default": "medium"
        },
        "title": {
          "type": "string",
          "maxLength": 256
        },
        "channels": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "delivered": { "type": "boolean" },
        "delivery_id": { "type": "string" },
        "channel_used": { "type": "string" },
        "timestamp": { "type": "string", "format": "date-time" }
      }
    },
    
    "requires": {
      "capabilities": ["notification"],
      "permissions": ["notify:send"]
    },
    
    "execution": {
      "timeout_ms": 30000,
      "retries": 2,
      "async_allowed": true
    }
  }
}
```

### 2. analyze_image

```json
{
  "tool": {
    "name": "analyze_image",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Analyze image using vision model",
    "category": "computing",
    
    "parameters": {
      "type": "object",
      "required": ["image"],
      "properties": {
        "image": {
          "oneOf": [
            { "type": "string", "format": "uri" },
            { "type": "string", "contentEncoding": "base64" }
          ],
          "description": "Image URL or base64-encoded data"
        },
        "task": {
          "type": "string",
          "enum": ["detect_objects", "classify", "segment", "ocr", "describe", "custom"],
          "default": "describe"
        },
        "prompt": {
          "type": "string",
          "description": "Custom prompt for analysis"
        },
        "model": {
          "type": "string",
          "description": "Preferred model (auto-select if omitted)"
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "result": { "type": "any" },
        "confidence": { "type": "number" },
        "model_used": { "type": "string" },
        "processing_ms": { "type": "integer" }
      }
    },
    
    "requires": {
      "capabilities": ["vision"],
      "gpu_preferred": true
    },
    
    "execution": {
      "timeout_ms": 60000,
      "retries": 1
    },
    
    "routing": {
      "prefer_gpu": true
    }
  }
}
```

### 3. control_matter_device

```json
{
  "tool": {
    "name": "control_matter_device",
    "namespace": "matter",
    "version": "1.0.0",
    "description": "Send command to Matter/Thread smart home device",
    "category": "acting",
    
    "parameters": {
      "type": "object",
      "required": ["device_id", "cluster", "command"],
      "properties": {
        "device_id": {
          "type": "string",
          "description": "Device ID or friendly name"
        },
        "endpoint": {
          "type": "integer",
          "default": 1
        },
        "cluster": {
          "type": "string",
          "description": "Matter cluster (OnOff, LevelControl, Thermostat, DoorLock, etc.)"
        },
        "command": {
          "type": "string",
          "description": "Cluster command name"
        },
        "params": {
          "type": "object",
          "description": "Command parameters"
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "success": { "type": "boolean" },
        "device_state": { "type": "object" },
        "error_code": { "type": "integer" }
      }
    },
    
    "requires": {
      "capabilities": ["matter_bridge"],
      "permissions": ["device:control"]
    },
    
    "routing": {
      "node_affinity": ["matter-bridge"],
      "hop_limit": 1
    }
  }
}
```

### 4. search_web

```json
{
  "tool": {
    "name": "search_web",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Search the web for information",
    "category": "querying",
    
    "parameters": {
      "type": "object",
      "required": ["query"],
      "properties": {
        "query": {
          "type": "string",
          "maxLength": 1000
        },
        "count": {
          "type": "integer",
          "minimum": 1,
          "maximum": 100,
          "default": 10
        },
        "freshness": {
          "type": "string",
          "enum": ["day", "week", "month", "year", "any"],
          "default": "any"
        },
        "safe_search": {
          "type": "boolean",
          "default": true
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "results": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": { "type": "string" },
              "url": { "type": "string" },
              "snippet": { "type": "string" }
            }
          }
        },
        "total_results": { "type": "integer" }
      }
    },
    
    "requires": {
      "capabilities": ["internet"],
      "permissions": ["web:search"]
    }
  }
}
```

### 5. spawn_agent

```json
{
  "tool": {
    "name": "spawn_agent",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Create a new agent instance",
    "category": "managing",
    
    "parameters": {
      "type": "object",
      "required": ["agent_type"],
      "properties": {
        "agent_type": {
          "type": "string",
          "description": "Type of agent to spawn"
        },
        "name": {
          "type": "string",
          "description": "Human-readable name"
        },
        "config": {
          "type": "object",
          "description": "Agent-specific configuration"
        },
        "permissions": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Permissions to grant (subset of caller's)"
        },
        "ttl_seconds": {
          "type": "integer",
          "description": "Auto-terminate after duration"
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "agent_id": { "type": "string" },
        "status": { "type": "string" },
        "token": { "type": "string" }
      }
    },
    
    "requires": {
      "capabilities": ["agent_runtime"],
      "permissions": ["agent:spawn"]
    },
    
    "execution": {
      "timeout_ms": 10000
    }
  }
}
```

### 6. query_sensor

```json
{
  "tool": {
    "name": "query_sensor",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Read values from a sensor",
    "category": "sensing",
    
    "parameters": {
      "type": "object",
      "required": ["sensor_id"],
      "properties": {
        "sensor_id": {
          "type": "string",
          "description": "Sensor identifier"
        },
        "time_range": {
          "type": "object",
          "properties": {
            "start": { "type": "string", "format": "date-time" },
            "end": { "type": "string", "format": "date-time" }
          }
        },
        "aggregation": {
          "type": "string",
          "enum": ["none", "avg", "min", "max", "sum"],
          "default": "none"
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "values": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "timestamp": { "type": "string" },
              "value": { "type": "number" }
            }
          }
        },
        "unit": { "type": "string" },
        "sensor_type": { "type": "string" }
      }
    },
    
    "requires": {
      "capabilities": ["sensor_access"],
      "permissions": ["sensor:read"]
    }
  }
}
```

### 7. llm_complete

```json
{
  "tool": {
    "name": "llm_complete",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Generate text using LLM",
    "category": "computing",
    
    "parameters": {
      "type": "object",
      "required": ["prompt"],
      "properties": {
        "prompt": {
          "type": "string",
          "description": "Input prompt"
        },
        "system": {
          "type": "string",
          "description": "System prompt"
        },
        "model": {
          "type": "string",
          "description": "Model to use (auto-select if omitted)"
        },
        "max_tokens": {
          "type": "integer",
          "default": 1024
        },
        "temperature": {
          "type": "number",
          "minimum": 0,
          "maximum": 2,
          "default": 0.7
        },
        "stream": {
          "type": "boolean",
          "default": false
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "text": { "type": "string" },
        "model_used": { "type": "string" },
        "tokens_used": {
          "type": "object",
          "properties": {
            "prompt": { "type": "integer" },
            "completion": { "type": "integer" }
          }
        },
        "finish_reason": { "type": "string" }
      }
    },
    
    "requires": {
      "capabilities": ["llm"]
    },
    
    "execution": {
      "timeout_ms": 120000,
      "stream_supported": true
    }
  }
}
```

### 8. store_data

```json
{
  "tool": {
    "name": "store_data",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Store key-value data persistently",
    "category": "managing",
    
    "parameters": {
      "type": "object",
      "required": ["key", "value"],
      "properties": {
        "key": {
          "type": "string",
          "pattern": "^[a-zA-Z0-9_/.-]+$",
          "maxLength": 256
        },
        "value": {
          "description": "Value to store (any JSON-serializable type)"
        },
        "ttl_seconds": {
          "type": "integer",
          "minimum": 0,
          "description": "Auto-expire after seconds (0 = never)"
        },
        "if_not_exists": {
          "type": "boolean",
          "default": false
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "success": { "type": "boolean" },
        "key": { "type": "string" },
        "created": { "type": "boolean" },
        "expires_at": { "type": "string", "format": "date-time" }
      }
    },
    
    "requires": {
      "capabilities": ["storage"],
      "permissions": ["storage:write"]
    }
  }
}
```

### 9. get_camera_frame

```json
{
  "tool": {
    "name": "get_camera_frame",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Capture current frame from camera",
    "category": "sensing",
    
    "parameters": {
      "type": "object",
      "required": ["camera_id"],
      "properties": {
        "camera_id": {
          "type": "string",
          "description": "Camera identifier"
        },
        "resolution": {
          "type": "object",
          "properties": {
            "width": { "type": "integer" },
            "height": { "type": "integer" }
          }
        },
        "format": {
          "type": "string",
          "enum": ["jpeg", "png", "raw"],
          "default": "jpeg"
        },
        "quality": {
          "type": "integer",
          "minimum": 1,
          "maximum": 100,
          "default": 85
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "image": { "type": "string", "contentEncoding": "base64" },
        "format": { "type": "string" },
        "width": { "type": "integer" },
        "height": { "type": "integer" },
        "timestamp": { "type": "string", "format": "date-time" }
      }
    },
    
    "requires": {
      "capabilities": ["camera_access"],
      "permissions": ["camera:capture"]
    },
    
    "routing": {
      "prefer_local": true,
      "hop_limit": 1
    }
  }
}
```

### 10. rag_search

```json
{
  "tool": {
    "name": "rag_search",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Search vector store for relevant documents",
    "category": "querying",
    
    "parameters": {
      "type": "object",
      "required": ["query"],
      "properties": {
        "query": {
          "type": "string",
          "description": "Search query"
        },
        "collection": {
          "type": "string",
          "description": "Vector collection name"
        },
        "limit": {
          "type": "integer",
          "minimum": 1,
          "maximum": 100,
          "default": 10
        },
        "min_score": {
          "type": "number",
          "minimum": 0,
          "maximum": 1,
          "default": 0.5
        },
        "filter": {
          "type": "object",
          "description": "Metadata filter"
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "documents": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "id": { "type": "string" },
              "content": { "type": "string" },
              "score": { "type": "number" },
              "metadata": { "type": "object" }
            }
          }
        },
        "total_searched": { "type": "integer" }
      }
    },
    
    "requires": {
      "capabilities": ["embeddings", "vector_store"],
      "permissions": ["rag:search"]
    }
  }
}
```

### 11. transcribe_audio

```json
{
  "tool": {
    "name": "transcribe_audio",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Convert audio to text",
    "category": "computing",
    
    "parameters": {
      "type": "object",
      "required": ["audio"],
      "properties": {
        "audio": {
          "oneOf": [
            { "type": "string", "format": "uri" },
            { "type": "string", "contentEncoding": "base64" }
          ]
        },
        "language": {
          "type": "string",
          "description": "ISO language code (auto-detect if omitted)"
        },
        "model": {
          "type": "string",
          "description": "Model preference"
        },
        "timestamps": {
          "type": "boolean",
          "default": false
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "text": { "type": "string" },
        "language": { "type": "string" },
        "segments": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "start": { "type": "number" },
              "end": { "type": "number" },
              "text": { "type": "string" }
            }
          }
        },
        "confidence": { "type": "number" }
      }
    },
    
    "requires": {
      "capabilities": ["audio", "speech_recognition"]
    }
  }
}
```

### 12. send_email

```json
{
  "tool": {
    "name": "send_email",
    "namespace": "core",
    "version": "1.0.0",
    "description": "Send email message",
    "category": "communicating",
    
    "parameters": {
      "type": "object",
      "required": ["to", "subject", "body"],
      "properties": {
        "to": {
          "type": "array",
          "items": { "type": "string", "format": "email" },
          "minItems": 1
        },
        "cc": {
          "type": "array",
          "items": { "type": "string", "format": "email" }
        },
        "bcc": {
          "type": "array",
          "items": { "type": "string", "format": "email" }
        },
        "subject": {
          "type": "string",
          "maxLength": 256
        },
        "body": {
          "type": "string"
        },
        "html": {
          "type": "boolean",
          "default": false
        },
        "attachments": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "filename": { "type": "string" },
              "content": { "type": "string", "contentEncoding": "base64" },
              "content_type": { "type": "string" }
            }
          }
        }
      }
    },
    
    "returns": {
      "type": "object",
      "properties": {
        "sent": { "type": "boolean" },
        "message_id": { "type": "string" },
        "timestamp": { "type": "string", "format": "date-time" }
      }
    },
    
    "requires": {
      "capabilities": ["email"],
      "permissions": ["email:send"]
    }
  }
}
```

---

## 9. Implementation Notes

### Tool Handler Interface

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel

class ToolContext(BaseModel):
    """Context passed to tool handlers."""
    agent_id: str
    session_id: str
    trace_id: str
    permissions: list[str]
    node_id: str

class ToolResult(BaseModel):
    """Standard tool result wrapper."""
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

class ToolHandler(ABC):
    """Base class for tool handlers."""
    
    @property
    @abstractmethod
    def definition(self) -> dict:
        """Return the tool definition JSON."""
        pass
    
    @abstractmethod
    async def execute(
        self,
        params: Dict[str, Any],
        context: ToolContext
    ) -> ToolResult:
        """Execute the tool with given parameters."""
        pass
    
    async def validate(self, params: Dict[str, Any]) -> bool:
        """Validate parameters before execution."""
        # Default: use JSON schema validation
        return True
```

### Integration with Capabilities

```python
class CapabilityWithTools(CapabilityHandler):
    """Capability handler that exposes tools."""
    
    @property
    def tools(self) -> List[ToolDefinition]:
        """Return tools provided by this capability."""
        return []
    
    def get_tool_handler(self, tool_name: str) -> Optional[ToolHandler]:
        """Get handler for a specific tool."""
        return None
```

### Mesh Integration

```python
# In mesh/gossip.py
class CapabilityAnnouncement:
    """Extended to include tools."""
    node_id: str
    capabilities: List[Capability]
    tools: List[ToolSummary]  # Name, description, param hash
    timestamp: datetime
    signature: bytes
```

---

## Summary

The tool system provides:

1. **Clear separation**: Capabilities describe resources; tools describe actions
2. **Strong typing**: JSON Schema for parameters and returns
3. **Discovery**: Tools propagate with capabilities via gossip
4. **Security**: Permission-based access control
5. **Routing**: Semantic + capability-based routing to best node
6. **Matter integration**: Smart home devices expose standard tools
7. **Extensibility**: Plugin architecture for custom tools

This design enables agents to "do things" across the mesh while maintaining security, discoverability, and type safety.
