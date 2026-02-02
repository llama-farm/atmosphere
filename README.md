# Atmosphere

> **The Internet of Intent** — Route intelligence to capability, not packets to addresses.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**Atmosphere** is a semantic mesh protocol that routes AI requests to the right capability on the right node. Instead of hardcoding which model handles which request, Atmosphere discovers capabilities across a distributed mesh and routes intelligently based on intent.

## 📄 White Paper

For the full technical deep-dive, see the **[Atmosphere Protocol White Paper](https://drive.google.com/file/d/1-LmkSI4cMZcQiCG6uUgJSerJi2FwUNli/view?usp=sharing)**.

---

## 🎯 What Problem Does This Solve?

**Traditional AI APIs:**
```
Client → knows exact endpoint → calls specific model
```

**Atmosphere:**
```
Client → expresses intent → mesh routes to best capability
```

### Example

```bash
# Traditional: You must know exactly which model to call
curl https://api.openai.com/v1/chat/completions \
  -d '{"model": "gpt-4", "messages": [...]}'

# Atmosphere: Express intent, mesh finds the right capability
curl http://localhost:8000/v1/chat/completions \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "What do llamas eat?"}]}'

# Atmosphere routes to the "llama-expert" project with RAG database
# because it semantically matches the query
```

---

## ✨ Key Features

- **🔍 Semantic Routing** — Routes based on intent, not hardcoded paths
- **🌐 Mesh Networking** — Discover capabilities across distributed nodes
- **🔌 OpenAI Compatible** — Drop-in replacement for OpenAI API
- **⚡ Fast Routing** — Pre-computed embeddings, sub-millisecond decisions
- **📦 Model Deployment** — Automatically distribute models across the mesh
- **🔄 Gossip Protocol** — Sync routing tables without central authority
- **👁️ Multi-Modal** — Route text, images, audio, and tool calls
- **🤖 Agent Framework** — Discover and invoke agents across the mesh
- **🔧 Tool Execution** — Execute tools on remote nodes (cameras, IoT, APIs)

---

## 🦌 The Vision: Capability Mesh

Atmosphere isn't just for text — it routes **any intent** to **any capability**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                      CAPABILITY MESH                                 │
│                                                                      │
│   "What is this?"     "Research llamas"    "Take a photo"          │
│         │                    │                   │                  │
│         ▼                    ▼                   ▼                  │
│   ┌──────────┐        ┌──────────┐        ┌──────────┐             │
│   │  Vision  │        │  Agent   │        │   Tool   │             │
│   │ Classify │        │ Research │        │  Camera  │             │
│   └──────────┘        └──────────┘        └──────────┘             │
│         │                    │                   │                  │
│         ▼                    ▼                   ▼                  │
│      rob-mac              rob-mac           edge-gateway            │
│   (has YOLO model)    (has research agent)  (has camera)           │
└─────────────────────────────────────────────────────────────────────┘
```

### Example: The Deer Scenario

A tiny edge sensor sees movement but can't identify the animal:

```
Edge Sensor → "I see an animal" (low confidence)
      ↓
Mesh Routes → rob-mac (has wildlife classifier)
      ↓
Classification → "White-tailed deer" (94% confidence)
      ↓
Learning Loop → Train edge model → Deploy back
      ↓
Next time → Sensor handles locally
```

See [design/CAPABILITY_MESH.md](design/CAPABILITY_MESH.md) for the full architecture.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- [LlamaFarm](https://github.com/llama-farm/llamafarm) (for local model execution)

### Installation

```bash
# Clone the repository
git clone https://github.com/llama-farm/atmosphere.git
cd atmosphere

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Start Atmosphere
uvicorn atmosphere.api.server:create_app --factory --port 8000
```

### Quick Test

```bash
# List available models (discovered from LlamaFarm)
curl http://localhost:8000/v1/models

# Chat with semantic routing
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         ATMOSPHERE                               │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   OpenAI     │    │   Semantic   │    │    Mesh      │       │
│  │   API Layer  │───▶│    Router    │───▶│   Network    │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                   │                │
│         ▼                   ▼                   ▼                │
│  ┌──────────────────────────────────────────────────────┐       │
│  │                    DISCOVERY                          │       │
│  │  • API-based project discovery                        │       │
│  │  • Pre-computed embeddings for fast matching          │       │
│  │  • Domain/topic/capability indexing                   │       │
│  └──────────────────────────────────────────────────────┘       │
│                              │                                   │
└──────────────────────────────│───────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  LlamaFarm   │      │   Ollama     │      │   OpenAI     │
│  (Universal  │      │              │      │   (Cloud)    │
│   Runtime)   │      │              │      │              │
└──────────────┘      └──────────────┘      └──────────────┘
```

---

## 🔧 How It Works

### 1. Discovery

Atmosphere discovers AI capabilities by querying provider APIs:

```python
# Discovers projects from LlamaFarm API
discovery = APIDiscovery("http://localhost:14345")
projects = await discovery.discover()

# Returns structured metadata:
# {
#   "namespace": "default",
#   "name": "llama-expert-14",
#   "domain": "camelids",
#   "capabilities": ["chat", "rag"],
#   "topics": ["llamas", "alpacas", "fiber"]
# }
```

### 2. Routing

The semantic router uses pre-computed embeddings for fast matching:

```python
# Route by explicit path
result = router.route("default/llama-expert-14")

# Route by content (semantic)
result = router.route_by_content([
    {"role": "user", "content": "How do I care for my llama?"}
])
# → Routes to llama-expert project (domain: camelids)
```

### 3. Execution

Requests are proxied to the appropriate backend:

```python
# Atmosphere → LlamaFarm → Universal Runtime
POST /v1/projects/default/llama-expert-14/chat/completions
```

---

## 🔌 Extending to Other Providers

Atmosphere is designed to be provider-agnostic. Add new providers by implementing the adapter interface:

### Creating a Custom Adapter

```python
# atmosphere/adapters/my_provider.py

from atmosphere.adapters.base import BaseAdapter

class MyProviderAdapter(BaseAdapter):
    """Adapter for MyProvider API."""
    
    def __init__(self, base_url: str, api_key: str = None):
        self.base_url = base_url
        self.api_key = api_key
    
    async def discover(self) -> list[Project]:
        """Discover available models/capabilities."""
        # Query your provider's API
        response = await self.client.get(f"{self.base_url}/models")
        
        projects = []
        for model in response.json()["models"]:
            projects.append(Project(
                namespace="myprovider",
                name=model["id"],
                domain=self._detect_domain(model),
                capabilities=["chat"],
            ))
        return projects
    
    async def chat(self, project: Project, messages: list) -> dict:
        """Execute a chat completion."""
        response = await self.client.post(
            f"{self.base_url}/chat",
            json={"model": project.name, "messages": messages}
        )
        return response.json()
```

### Registering the Adapter

```python
# atmosphere/config.py

ADAPTERS = {
    "llamafarm": LlamaFarmAdapter,
    "ollama": OllamaAdapter,
    "openai": OpenAIAdapter,
    "myprovider": MyProviderAdapter,  # Add your adapter
}
```

### Built-in Adapters

| Adapter | Description | Status |
|---------|-------------|--------|
| `LlamaFarmAdapter` | LlamaFarm Universal Runtime | ✅ Complete |
| `OllamaAdapter` | Ollama local models | ✅ Complete |
| `OpenAIAdapter` | OpenAI API (cloud) | 🔄 Planned |
| `AnthropicAdapter` | Anthropic Claude | 🔄 Planned |
| `vLLMAdapter` | vLLM inference server | 🔄 Planned |

---

## 🌐 Mesh Networking

Atmosphere nodes discover each other and share routing information via gossip protocol.

### Starting a Mesh

```bash
# Node 1 (Rob's Mac)
atmosphere start --port 11451 --gossip-port 11450

# Node 2 (Matt's Dell) - joins the mesh
atmosphere start --port 11451 --gossip-port 11450 \
  --seed-peer "rob-mac.local:11450"
```

### Gossip Messages

```python
# When a new project is discovered
ROUTE_UPDATE = {
    "type": "route_update",
    "action": "add",
    "project": "default/llama-expert-14",
    "domain": "camelids",
    "capabilities": ["chat", "rag"],
    "nodes": ["rob-mac"]
}

# When a model is deployed
MODEL_DEPLOYED = {
    "type": "model_deployed",
    "model": "network-anomaly-v3",
    "node": "matt-dell",
    "version": "1.0.0"
}
```

---

## 📦 Model Deployment

Automatically distribute trained models across the mesh:

```bash
# List local models
atmosphere model list

# Push model to specific node
atmosphere model push network-detector matt-dell

# Deploy to all capable nodes
atmosphere model deploy network-detector --all
```

### Model Manifest

```yaml
name: network-anomaly-detector
version: 1.0.0
type: anomaly_detector
format: sklearn
size_bytes: 12345678

capabilities:
  - anomaly_detection
  - network_monitoring

node_requirements:
  min_memory_mb: 512
  gpu_required: false
```

---

## 🎯 Typed Intents (Coming Soon)

Beyond OpenAI-compatible chat, Atmosphere supports typed intents for any capability:

```bash
# Vision classification
curl -X POST http://localhost:8000/v1/intent \
  -d '{
    "type": "vision/classify",
    "domain": "wildlife",
    "data": {"image": "<base64>"},
    "preferences": {"latency": "low"}
  }'

# Agent invocation
curl -X POST http://localhost:8000/v1/agent/invoke \
  -d '{
    "query": "Research the latest on llama breeding"
  }'

# Tool execution
curl -X POST http://localhost:8000/v1/tool/execute \
  -d '{
    "tool": "camera-front@edge-gateway",
    "action": "capture"
  }'
```

### Supported Capability Types

| Category | Types | Description |
|----------|-------|-------------|
| **LLM** | chat, reasoning, code, summarize | Text generation |
| **Vision** | classify, detect, ocr, segment | Image processing |
| **Audio** | transcribe, generate, identify | Audio processing |
| **Agent** | research, workflow, monitor | Autonomous tasks |
| **Tool** | camera, iot, api, file | Device/API control |
| **ML** | anomaly, classify, forecast | ML inference |

---

## 🛣️ Roadmap

- [x] **Phase 1**: Single-node routing with LlamaFarm
- [x] **Phase 2**: OpenAI-compatible API layer
- [x] **Phase 3**: API-based discovery
- [ ] **Phase 4**: Multi-node mesh networking
- [ ] **Phase 5**: Model deployment & distribution
- [ ] **Phase 6**: Edge learning loop (train → deploy → learn)
- [ ] **Phase 7**: Typed intents (vision, audio, agents, tools)
- [ ] **Phase 8**: Distributed embeddings (SimHash for edge devices)

---

## 📁 Project Structure

```
atmosphere/
├── api/                    # FastAPI server
│   ├── server.py          # Main application
│   └── routes.py          # API routes
├── router/                 # Semantic routing
│   ├── fast_router.py     # Embedding-based router
│   ├── openai_compat.py   # OpenAI API compatibility
│   └── project_router.py  # Project routing logic
├── discovery/              # Capability discovery
│   ├── api_discovery.py   # API-based discovery
│   └── llamafarm.py       # LlamaFarm adapter
├── deployment/             # Model deployment
│   └── registry.py        # Model registry
├── mesh/                   # Mesh networking
│   ├── discovery.py       # mDNS/gossip discovery
│   ├── gossip.py          # Gossip protocol
│   └── network.py         # STUN/NAT traversal
├── adapters/               # Provider adapters
│   ├── llamafarm.py       # LlamaFarm adapter
│   └── ollama.py          # Ollama adapter
└── design/                 # Design documents
    └── MODEL_DEPLOYMENT.md
```

---

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone and setup
git clone https://github.com/llama-farm/atmosphere.git
cd atmosphere
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linting
ruff check .
```

---

## 📜 License

Apache 2.0 - See [LICENSE](LICENSE) for details.

---

## 🔗 Related Projects

- [LlamaFarm](https://github.com/llama-farm/llamafarm) - Edge AI runtime
- [Rownd-Local](https://github.com/llama-farm/rownd-local) - Decentralized identity for mesh auth

---

<p align="center">
  <b>Route intelligence, not packets.</b>
</p>
