# Atmosphere API Reference

> **REST API for the Internet of Intent**

Base URL: `http://localhost:8000`

---

## OpenAI-Compatible Endpoints

### POST /v1/chat/completions

OpenAI-compatible chat completions with semantic routing.

**Request:**
```json
{
  "model": "default/llama-expert-14",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What's the best llama breed for wool?"}
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

**Routing Behavior:**
- If `model` matches a known project path (e.g., `default/llama-expert-14`), routes directly
- If `model` is semantic (e.g., `llama-expert`), uses semantic matching to find best project
- If `model` is omitted, routes based on message content semantics

**Response:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1770077000,
  "model": "default/llama-expert-14",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "For wool production, the Suri alpaca..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 50,
    "completion_tokens": 150,
    "total_tokens": 200
  },
  "atmosphere": {
    "routed_to": "default/llama-expert-14",
    "routing_method": "explicit",
    "routing_time_ms": 0.5,
    "node_id": "rob-mac"
  }
}
```

---

### GET /v1/models

List available models/capabilities.

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "default/llama-expert-14",
      "object": "model",
      "created": 1770000000,
      "owned_by": "llamafarm",
      "atmosphere": {
        "type": "llm/chat",
        "node_id": "rob-mac",
        "domain": "camelids",
        "has_rag": true,
        "status": "online"
      }
    },
    {
      "id": "default/fishing-assistant",
      "object": "model",
      "created": 1770000000,
      "owned_by": "llamafarm",
      "atmosphere": {
        "type": "llm/chat",
        "node_id": "rob-mac",
        "domain": "fishing",
        "has_rag": true,
        "status": "online"
      }
    }
  ]
}
```

---

## Mesh Endpoints

### GET /mesh/status

Get mesh status and statistics.

**Response:**
```json
{
  "node_id": "rob-mac",
  "status": "online",
  "uptime_seconds": 3600,
  "peers": {
    "connected": 3,
    "known": 5
  },
  "capabilities": {
    "total": 12,
    "healthy": 11,
    "by_type": {
      "llm/chat": 5,
      "sensor/camera": 3,
      "audio/transcribe": 2,
      "vision/classify": 2
    }
  },
  "routing": {
    "cache_entries": 150,
    "avg_routing_time_ms": 0.8
  }
}
```

---

### GET /mesh/nodes

List all known nodes in the mesh.

**Query Parameters:**
- `status` (optional): Filter by status (online, offline, all)
- `limit` (optional): Max results (default 100)

**Response:**
```json
{
  "nodes": [
    {
      "id": "rob-mac",
      "address": "192.168.1.10:11450",
      "status": "online",
      "last_seen": "2026-02-02T18:00:00Z",
      "capabilities_count": 5,
      "resources": {
        "memory_gb": 64,
        "gpu": "M1 Max",
        "load": 0.3
      }
    },
    {
      "id": "dell-gpu",
      "address": "192.168.1.20:11450",
      "status": "online",
      "last_seen": "2026-02-02T18:00:05Z",
      "capabilities_count": 4,
      "resources": {
        "memory_gb": 128,
        "gpu": "RTX 4090",
        "load": 0.6
      }
    }
  ],
  "total": 2
}
```

---

### GET /mesh/capabilities

List all capabilities across the mesh.

**Query Parameters:**
- `type` (optional): Filter by capability type (e.g., `llm/chat`, `sensor/camera`)
- `node_id` (optional): Filter by node
- `healthy_only` (optional): Only return healthy capabilities (default true)
- `limit` (optional): Max results (default 100)

**Response:**
```json
{
  "capabilities": [
    {
      "id": "front-door-camera",
      "node_id": "home-server",
      "type": "sensor/camera",
      "status": "online",
      "tools": ["get_frame", "get_history", "get_clip"],
      "triggers": ["motion_detected", "person_detected", "package_detected"],
      "metadata": {
        "location": "front door"
      },
      "last_heartbeat": "2026-02-02T18:00:00Z"
    }
  ],
  "total": 1
}
```

---

### GET /mesh/capabilities/{capability_id}

Get detailed information about a specific capability.

**Response:**
```json
{
  "id": "front-door-camera",
  "node_id": "home-server",
  "type": "sensor/camera",
  "status": "online",
  "tools": [
    {
      "name": "get_frame",
      "description": "Capture current camera frame",
      "parameters": {
        "resolution": {"type": "string", "enum": ["full", "720p", "thumbnail"]}
      },
      "returns": {"type": "image/jpeg"}
    },
    {
      "name": "get_history",
      "description": "Get motion events",
      "parameters": {
        "since": {"type": "duration", "default": "1h"}
      },
      "returns": {"type": "array"}
    }
  ],
  "triggers": [
    {
      "event": "motion_detected",
      "description": "Motion detected in frame",
      "intent_template": "motion detected at {location}",
      "route_hint": "security/*",
      "priority": "normal",
      "throttle": "30s"
    }
  ],
  "metadata": {
    "location": "front door",
    "hardware": "Reolink RLC-810A"
  },
  "last_heartbeat": "2026-02-02T18:00:00Z",
  "version": "1.0.0"
}
```

---

### POST /mesh/capabilities

Register a new capability.

**Request:**
```json
{
  "id": "my-camera",
  "type": "sensor/camera",
  "tools": [
    {
      "name": "get_frame",
      "description": "Get current frame"
    }
  ],
  "triggers": [
    {
      "event": "motion_detected",
      "intent_template": "motion at {location}",
      "route_hint": "security/*"
    }
  ],
  "metadata": {
    "location": "backyard"
  }
}
```

**Response:**
```json
{
  "id": "my-camera",
  "status": "registered",
  "node_id": "rob-mac"
}
```

---

### DELETE /mesh/capabilities/{capability_id}

Deregister a capability.

**Response:**
```json
{
  "id": "my-camera",
  "status": "deregistered"
}
```

---

### GET /mesh/routes

Get current routing table (gradient table).

**Response:**
```json
{
  "routes": [
    {
      "capability_type": "llm/chat",
      "best_node": "rob-mac",
      "hops": 0,
      "score": 0.96,
      "latency_ms": 1
    },
    {
      "capability_type": "vision/classify",
      "best_node": "jetson-01",
      "hops": 2,
      "score": 0.91,
      "latency_ms": 12
    }
  ],
  "updated_at": "2026-02-02T18:00:00Z"
}
```

---

## Tool & Trigger Endpoints

### POST /capabilities/{capability_id}/tools/{tool_name}

Execute a tool on a capability (PULL).

**Request:**
```json
{
  "params": {
    "resolution": "720p"
  },
  "options": {
    "timeout_ms": 5000,
    "allow_fallback": true
  }
}
```

**Response:**
```json
{
  "status": "success",
  "result": "<base64-encoded-image>",
  "duration_ms": 150,
  "capability_id": "front-door-camera",
  "used_fallback": false
}
```

---

### POST /trigger/{capability_id}/{event}

Fire a trigger manually (PUSH).

**Request:**
```json
{
  "payload": {
    "location": "front door",
    "confidence": 0.94,
    "timestamp": "2026-02-02T18:00:00Z"
  }
}
```

**Response:**
```json
{
  "status": "routed",
  "intent": "person detected at front door",
  "routed_to": "security-agent",
  "routing_time_ms": 0.5
}
```

---

## Discovery Endpoints

### POST /discover

Discover capabilities matching a query.

**Request:**
```json
{
  "query": "detect objects in images",
  "type_filter": "vision/*",
  "limit": 5
}
```

**Response:**
```json
{
  "capabilities": [
    {
      "id": "wildlife-classifier",
      "type": "vision/classify",
      "score": 0.94,
      "node_id": "jetson-01"
    },
    {
      "id": "general-detector",
      "type": "vision/detect",
      "score": 0.89,
      "node_id": "dell-gpu"
    }
  ]
}
```

---

### GET /discover/projects

Discover LlamaFarm projects (API-based discovery).

**Query Parameters:**
- `namespace` (optional): Filter by namespace (default: all)
- `refresh` (optional): Force cache refresh

**Response:**
```json
{
  "projects": [
    {
      "namespace": "default",
      "name": "llama-expert-14",
      "domain": "camelids",
      "capabilities": ["chat", "rag"],
      "model": "unsloth/Qwen3-1.7B-GGUF:Q4_K_M"
    }
  ],
  "total": 165,
  "cached": true,
  "cache_age_seconds": 120
}
```

---

## Health Endpoints

### GET /health

Basic health check.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "node_id": "rob-mac"
}
```

---

### GET /health/detailed

Detailed health with capability status.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "node_id": "rob-mac",
  "uptime_seconds": 3600,
  "capabilities": {
    "total": 12,
    "healthy": 11,
    "degraded": 1
  },
  "integrations": {
    "llamafarm": {
      "status": "connected",
      "url": "http://localhost:14345",
      "projects": 165
    },
    "ollama": {
      "status": "connected",
      "url": "http://localhost:11434",
      "models": 5
    }
  }
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "capability_not_found",
    "message": "Capability 'camera-xyz' not found in registry",
    "details": {
      "capability_id": "camera-xyz",
      "searched_nodes": ["rob-mac", "dell-gpu"]
    }
  }
}
```

**Error Codes:**
- `capability_not_found` - Capability doesn't exist
- `capability_offline` - Capability exists but is offline
- `tool_not_found` - Tool doesn't exist on capability
- `validation_error` - Parameter validation failed
- `timeout` - Execution timed out
- `routing_failed` - No route to capability
- `auth_required` - Authentication required
- `auth_failed` - Authentication failed

---

*Document Version: 1.0*  
*Date: 2026-02-02*
