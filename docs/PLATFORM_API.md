# Atmosphere Platform API Reference

**Version**: 1.0.0  
**Base URL**: `http://localhost:11451/api`

Atmosphere exposes a REST and WebSocket API that allows any application to leverage the mesh network for AI capabilities. Use it as a drop-in replacement for OpenAI's API or access the full mesh routing capabilities.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Authentication](#authentication)
3. [REST Endpoints](#rest-endpoints)
   - [Chat Completions](#chat-completions)
   - [Route Intent](#route-intent)
   - [Execute Intent](#execute-intent)
   - [Capabilities](#capabilities)
   - [Mesh Status](#mesh-status)
4. [WebSocket API](#websocket-api)
5. [OpenAI Compatibility](#openai-compatibility)
6. [Error Handling](#error-handling)
7. [Examples](#examples)

---

## Quick Start

### Test the API

```bash
# Health check
curl http://localhost:11451/health

# Get capabilities
curl http://localhost:11451/api/capabilities

# Chat completion
curl -X POST http://localhost:11451/api/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

### Python Example

```python
import requests

# Chat with the mesh
response = requests.post("http://localhost:11451/api/chat/completions", json={
    "model": "auto",
    "messages": [
        {"role": "user", "content": "Summarize quantum computing"}
    ]
})

result = response.json()
print(result["choices"][0]["message"]["content"])
```

---

## Authentication

Currently, Atmosphere runs locally and does not require authentication for localhost connections. For remote access, mesh tokens are required.

### Mesh Tokens

When connecting to a remote mesh, you need a token:

```bash
# Get an invite token (if you're the founder)
curl http://localhost:11451/api/mesh/token

# Join a mesh with a token
curl -X POST http://localhost:11451/api/mesh/join \
  -H "Content-Type: application/json" \
  -d '{
    "device": {...},
    "token": "...",
    "signature": "..."
  }'
```

---

## REST Endpoints

### Chat Completions

**POST** `/api/chat/completions`

OpenAI-compatible chat completion endpoint. Routes to the best available LLM in the mesh.

#### Request

```json
{
  "model": "auto",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

#### Response

```json
{
  "id": "chatcmpl-1234567890",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "llamafarm/discoverable/llama-expert-14",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

---

### Route Intent

**POST** `/api/route`

Route a natural language intent to the best capability without executing it.

#### Request

```json
{
  "intent": "summarize this document"
}
```

#### Response

```json
{
  "action": "PROCESS_LOCAL",
  "capability": "llamafarm/discoverable/document-expert",
  "score": 0.89,
  "hops": 0,
  "next_hop": null,
  "node_id": "abc123"
}
```

---

### Execute Intent

**POST** `/api/execute`

Route and execute a natural language intent.

#### Request

```json
{
  "intent": "What's the weather like?",
  "kwargs": {
    "location": "San Francisco"
  },
  "origin": null,
  "hops": 0
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "response": "The weather in San Francisco is currently 65°F and sunny."
  },
  "error": null,
  "execution_time_ms": 234.5,
  "node_id": "abc123",
  "hops": 0,
  "capability": "weather"
}
```

---

### Capabilities

**GET** `/api/capabilities`

List all available capabilities in the mesh.

#### Response

```json
[
  {
    "id": "llamafarm/discoverable/llama-expert-14",
    "label": "llamafarm/discoverable/llama-expert-14",
    "description": "Expert LLM for general knowledge and reasoning",
    "handler": "llamafarm_project",
    "models": ["llama-3.1-14b"]
  },
  {
    "id": "embeddings",
    "label": "embeddings",
    "description": "Text embeddings for semantic search",
    "handler": "llamafarm",
    "models": ["sentence-transformers"]
  }
]
```

---

### Mesh Status

**GET** `/api/mesh/status`

Get current mesh network status.

#### Response

```json
{
  "mesh_id": "abc123def456",
  "mesh_name": "home-mesh",
  "node_count": 3,
  "peer_count": 2,
  "capabilities": ["llm", "embeddings", "vision"],
  "is_founder": true
}
```

---

### Mesh Topology

**GET** `/api/mesh/topology`

Get mesh topology for visualization.

#### Response

```json
{
  "nodes": [
    {
      "id": "node1",
      "name": "MacBook Pro",
      "status": "active",
      "isLeader": true,
      "type": "llm",
      "triggers": [],
      "tools": ["llm", "embeddings"],
      "cost": 0.5,
      "costFactors": {
        "cpu_load": 0.3,
        "battery_percent": 85.0
      }
    }
  ],
  "links": [
    {
      "source": "node1",
      "target": "node2",
      "type": "relay"
    }
  ],
  "mesh_id": "abc123",
  "mesh_name": "home-mesh"
}
```

---

### Project Routing

**POST** `/api/route/project`

Route to the best LlamaFarm project using semantic matching.

#### Request

```json
{
  "intent": "Explain quantum entanglement",
  "messages": [
    {"role": "user", "content": "Explain quantum entanglement"}
  ]
}
```

#### Response

```json
{
  "project": "discoverable/physics-expert",
  "namespace": "discoverable",
  "name": "physics-expert",
  "score": 0.92,
  "tier": "embedding",
  "domain": "physics",
  "reason": "Matched domain keywords: quantum, physics"
}
```

---

### Cost Metrics

**GET** `/api/cost/current`

Get current node cost factors.

#### Response

```json
{
  "node_id": "abc123",
  "timestamp": 1234567890.123,
  "power": {
    "on_battery": false,
    "battery_percent": 85.0,
    "plugged_in": true
  },
  "compute": {
    "cpu_load": 0.3,
    "gpu_load": 0.1,
    "gpu_estimated": false,
    "memory_percent": 45.0,
    "memory_available_gb": 12.5
  },
  "network": {
    "bandwidth_mbps": 100.0,
    "is_metered": false,
    "latency_ms": 15.0
  },
  "cost_multiplier": 0.5
}
```

---

## WebSocket API

**WebSocket** `ws://localhost:11451/api/ws`

Real-time updates and mesh communication.

### Connect

```javascript
const ws = new WebSocket('ws://localhost:11451/api/ws');

ws.onopen = () => {
  console.log('Connected to Atmosphere');
  
  // Join mesh
  ws.send(JSON.stringify({
    type: 'join',
    node_id: 'my-app',
    name: 'My App',
    capabilities: ['custom_capability']
  }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log('Received:', msg);
};
```

### Message Types

#### Client → Server

**join** - Join the mesh
```json
{
  "type": "join",
  "node_id": "my-app",
  "name": "My App",
  "capabilities": ["llm"]
}
```

**llm_request** - Request LLM inference
```json
{
  "type": "llm_request",
  "request_id": "req123",
  "prompt": "Hello!",
  "model": "auto"
}
```

**intent** - Execute an intent
```json
{
  "type": "intent",
  "request_id": "req456",
  "text": "What's the weather?"
}
```

#### Server → Client

**joined** - Mesh join confirmation
```json
{
  "type": "joined",
  "mesh": "home-mesh",
  "mesh_id": "abc123"
}
```

**llm_response** - LLM response
```json
{
  "type": "llm_response",
  "request_id": "req123",
  "response": "Hello! How can I help?"
}
```

**mesh_status** - Mesh status update
```json
{
  "type": "mesh_status",
  "data": {
    "mesh_id": "abc123",
    "node_count": 3,
    "peer_count": 2
  }
}
```

**cost_update** - Cost metrics update
```json
{
  "type": "cost_update",
  "node_id": "abc123",
  "cost": 0.5,
  "factors": {...}
}
```

---

## OpenAI Compatibility

Atmosphere is a **drop-in replacement** for OpenAI's API.

### Setup

```python
from openai import OpenAI

# Point to Atmosphere instead of OpenAI
client = OpenAI(
    base_url="http://localhost:11451/v1",
    api_key="not-needed"  # Local mesh doesn't need auth
)

# Use exactly like OpenAI
response = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

### Available Endpoints

- `POST /v1/chat/completions` - Chat completions
- `POST /v1/completions` - Text completions
- `POST /v1/embeddings` - Text embeddings
- `GET /v1/models` - List available models

---

## Error Handling

All endpoints return standard HTTP status codes:

- `200` - Success
- `400` - Bad request (invalid parameters)
- `403` - Forbidden (not authorized)
- `500` - Internal server error
- `503` - Service unavailable (server not ready)

### Error Response Format

```json
{
  "detail": "Server not ready"
}
```

---

## Examples

### Python: Route and Execute

```python
import requests

# Route an intent
response = requests.post("http://localhost:11451/api/route", json={
    "intent": "summarize this article about AI"
})

route_result = response.json()
print(f"Best capability: {route_result['capability']}")
print(f"Score: {route_result['score']}")

# Execute the intent
response = requests.post("http://localhost:11451/api/execute", json={
    "intent": "summarize this article about AI",
    "kwargs": {
        "article": "..." # Article text
    }
})

result = response.json()
print(result['data']['response'])
```

### JavaScript: WebSocket Chat

```javascript
const ws = new WebSocket('ws://localhost:11451/api/ws');

ws.onopen = () => {
  // Send chat request
  ws.send(JSON.stringify({
    type: 'llm_request',
    request_id: 'chat1',
    prompt: 'Tell me a joke',
    model: 'auto'
  }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  if (msg.type === 'llm_response') {
    console.log('AI:', msg.response);
  }
};
```

### Node.js: OpenAI Compatibility

```javascript
import OpenAI from 'openai';

const openai = new OpenAI({
  baseURL: 'http://localhost:11451/v1',
  apiKey: 'not-needed'
});

async function chat() {
  const completion = await openai.chat.completions.create({
    model: 'auto',
    messages: [
      { role: 'user', content: 'What is quantum computing?' }
    ]
  });

  console.log(completion.choices[0].message.content);
}

chat();
```

### cURL: Get Capabilities

```bash
# List all capabilities
curl http://localhost:11451/api/capabilities | jq

# Filter for LLM capabilities
curl http://localhost:11451/api/capabilities | jq '.[] | select(.handler == "llamafarm_project")'

# Get mesh status
curl http://localhost:11451/api/mesh/status | jq
```

---

## Advanced Features

### Multi-Node Routing

Atmosphere automatically routes requests to the best node based on:
- **Semantic matching** - Which capability best matches the intent
- **Cost factors** - CPU, battery, network conditions
- **Availability** - Is the capability currently available?

No configuration needed - just send your request and the mesh handles it.

### Cost-Aware Execution

The mesh tracks real-time cost metrics:
- Battery level and power state
- CPU/GPU utilization
- Network bandwidth and latency
- Memory availability

Requests automatically route to the most efficient node.

### LlamaFarm Project Routing

When you have multiple LlamaFarm projects, Atmosphere uses semantic matching to route to the best one:

```python
# Automatically routes to the best project for this topic
response = requests.post("http://localhost:11451/api/chat/completions", json={
    "model": "auto",
    "messages": [
        {"role": "user", "content": "Explain general relativity"}
    ]
})

# Might route to: discoverable/physics-expert
# Or: discoverable/science-tutor
# Depends on semantic match score
```

---

## SDK Support

- **Python**: Use OpenAI SDK with `base_url="http://localhost:11451/v1"`
- **JavaScript**: Use OpenAI SDK with `baseURL: 'http://localhost:11451/v1'`
- **Android**: Use Atmosphere SDK (see `atmosphere-sdk/README.md`)
- **iOS**: Coming soon

---

## Need Help?

- **Documentation**: See `docs/` folder
- **Examples**: See `examples/` folder
- **Issues**: File on GitHub
- **Architecture**: See `ARCHITECTURE.md`

---

**Made with ❤️ by the Atmosphere team**
