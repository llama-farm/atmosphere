# Atmosphere

**The Internet of Intent — Route Intelligence, Not Packets**

> Traditional networks route packets to addresses.  
> Atmosphere routes work to capability.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## The Vision

What if your devices stopped being isolated islands and became one intelligent mesh? Your Mac, your GPU server, your edge devices, your cameras—all seamlessly sharing capabilities. You don't ask "which model should I call?" You just express intent: *"analyze this image for defects"*—and the mesh routes to the best available capability.

Atmosphere is the protocol that makes this real. No central server. Works offline. Scales from 3 devices to 3 billion. Secure by default with cryptographic identity.

---

## Quick Start

### Install via pip

```bash
# Install the package
pip install atmosphere-mesh

# Initialize your node
atmosphere init

# Start the API server
atmosphere serve
```

### Install via Homebrew (macOS)

```bash
# Add the tap
brew tap llama-farm/atmosphere

# Install
brew install atmosphere

# Start the service
brew services start atmosphere
```

### Quick Test

```bash
# Route your first intent
curl -X POST http://localhost:11451/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}]}'
```

The mesh automatically discovers local capabilities (LlamaFarm, Ollama) and routes your request.

---

## Core Concept: Bidirectional Capabilities

**Every capability is both a TRIGGER and a TOOL.**

This is the key insight. A camera doesn't just *provide* frames—it *pushes* events when something happens:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BIDIRECTIONAL CAPABILITY                              │
│                                                                          │
│                         ┌──────────────┐                                 │
│                         │   CAMERA     │                                 │
│                         │  capability  │                                 │
│                         └──────┬───────┘                                 │
│                                │                                         │
│            ┌───────────────────┴───────────────────┐                     │
│            │                                       │                     │
│            ▼                                       ▼                     │
│    ┌───────────────┐                      ┌───────────────┐              │
│    │   TRIGGERS    │                      │    TOOLS      │              │
│    │   (push)      │                      │    (pull)     │              │
│    ├───────────────┤                      ├───────────────┤              │
│    │ • motion      │                      │ • get_frame() │              │
│    │ • person      │                      │ • get_clip()  │              │
│    │ • package     │                      │ • get_history │              │
│    │ • vehicle     │                      │ • list_events │              │
│    └───────┬───────┘                      └───────┬───────┘              │
│            │                                       │                     │
│            │ "person detected"                     │ agent.call()        │
│            ▼                                       ▼                     │
│    ┌───────────────┐                      ┌───────────────┐              │
│    │   SECURITY    │                      │   SECURITY    │              │
│    │    AGENT      │───────────────────▶  │    AGENT      │              │
│    │  (reactive)   │   same agent can     │  (proactive)  │              │
│    └───────────────┘   both receive and   └───────────────┘              │
│                        invoke                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

**Example workflow:**
1. Camera **TRIGGERS** "person detected" → routes to security agent
2. Agent **CALLS** `camera.get_history()` → reviews motion events  
3. Agent **CALLS** `phone.notify()` → sends alert
4. Agent **TRIGGERS** "alert sent" → logged for audit

---

## Capability Types

| Category | Type | Triggers | Tools |
|----------|------|----------|-------|
| **Vision** | `sensor/camera` | motion, person, package, vehicle | get_frame, get_clip, get_history |
| **Voice** | `audio/generate` | speech_complete | speak, list_voices |
| **Transcription** | `audio/transcribe` | transcription_complete, keyword | transcribe, transcribe_stream |
| **Image Gen** | `vision/generate` | generation_complete | generate, edit, variations |
| **LLM** | `llm/chat` | — | chat, complete, embed |
| **IoT** | `iot/*` | threshold, anomaly, state_change | get_value, set_value, list_devices |
| **Agent** | `agent/*` | task_complete, decision_made | invoke, query_state |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ATMOSPHERE PROTOCOL STACK                        │
├─────────────────────────────────────────────────────────────────────────┤
│  WORK LAYER          Your apps, LlamaFarm, agents, tools                 │
│                      Intent expression, capability consumption           │
├─────────────────────────────────────────────────────────────────────────┤
│  ROUTING LAYER       Semantic routing, gradient tables                   │
│                      Pre-computed embeddings (<1ms routing)              │
│                      Capability matching, load balancing                 │
├─────────────────────────────────────────────────────────────────────────┤
│  MESH LAYER          Gossip protocol, peer discovery                     │
│                      Session tracking, capability announcements          │
│                      O(log N) propagation, no central authority          │
├─────────────────────────────────────────────────────────────────────────┤
│  IDENTITY LAYER      Rownd Local (Ed25519 keypairs)                      │
│                      Offline token verification                          │
│                      Federation, delegation, revocation                  │
├─────────────────────────────────────────────────────────────────────────┤
│  TRANSPORT LAYER     TCP/UDP, WebSocket, QUIC                            │
│                      STUN/NAT traversal, mDNS discovery                  │
│                      LoRa, BLE, WiFi (future)                            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Integrations

### LlamaFarm

Atmosphere auto-discovers LlamaFarm projects and registers them as capabilities:

```python
# LlamaFarm project with semantic metadata
{
    "namespace": "default",
    "name": "llama-expert-14",
    "domain": "camelids",
    "capabilities": ["chat", "rag"],
    "topics": ["llamas", "alpacas", "fiber"]
}

# Atmosphere routes semantically
curl -X POST http://localhost:8000/v1/chat/completions \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "How do I care for my llama?"}]}'
# → Automatically routes to llama-expert project
```

### Ollama

Local models via Ollama are auto-discovered and added to the capability mesh:

```bash
# Ollama models become routable
atmosphere status
# → ollama:llama3.2 (llm/chat)
# → ollama:nomic-embed (llm/embed)
```

### OpenAI-Compatible API

Drop-in replacement for OpenAI API—mesh handles routing:

```python
from openai import OpenAI

# Point to Atmosphere instead of OpenAI
client = OpenAI(base_url="http://localhost:8000/v1", api_key="n/a")

# Same API, intelligent routing
response = client.chat.completions.create(
    model="auto",  # Let mesh decide
    messages=[{"role": "user", "content": "What is this?"}]
)
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| **🔍 Semantic Routing** | Routes by intent meaning, not hardcoded paths |
| **⚡ Sub-millisecond** | Pre-computed embeddings, O(1) gradient table lookup |
| **🌐 Zero Config Mesh** | mDNS discovery, gossip sync, no central server |
| **🔐 Zero Trust Auth** | Ed25519 identity, offline token verification |
| **📦 Model Deployment** | Push models to nodes, organic learning loops |
| **👁️ Multimodal** | Vision, voice, image gen—all bidirectional |
| **🤖 Agent Framework** | Stateful agents with delegation |

---

## Model Deployment Strategies

| Strategy | Description | Use Case |
|----------|-------------|----------|
| **Push** | Admin deploys model to specific nodes | Production rollout |
| **Pull** | Node requests model it needs | On-demand capability |
| **Gossip** | Model spreads organically through mesh | Popular models |
| **Organic** | Edge learns → pushes improved model | ML learning loops |

---

## Platforms

| Platform | Status | Repository |
|----------|--------|------------|
| **Mac/Linux** (Python) | ✅ Server + WebUI + CLI | This repo |
| **Android** | ✅ ONNX Vision + Mesh + SDK | [atmosphere-android](https://github.com/llama-farm/atmosphere-android) |
| **macOS** (SwiftUI) | 🚧 BLE + Chat + Gossip | `AtmosphereMac/` in this repo |
| **OpenHoof** (Agents) | ✅ Event-driven agents | [openhoof](https://github.com/llama-farm/openhoof) |

### What's Working Today

- **Cross-platform mesh**: Android phone ↔ Mac laptop via LAN + WebSocket relay (~2s latency)
- **On-device vision**: YOLOv8n ONNX running at 40-60ms/frame on Pixel, 80 COCO classes
- **Semantic routing**: SimHash + keyword cascade routes queries to the best model/capability
- **Gossip protocol**: Capabilities propagate across mesh, gradient tables auto-update
- **WebUI dashboard**: Real-time gossip feed, routing table, capability browser at `:11451`
- **Android SDK**: Third-party apps bind via AIDL for chat, vision, and mesh status
- **Vision escalation**: Low-confidence detections auto-route to more powerful mesh peers

---

## Links

- **[Architecture Deep Dive](ARCHITECTURE.md)** — Full protocol specification
- **[Bidirectional Capabilities](design/BIDIRECTIONAL_CAPABILITIES.md)** — Trigger/tool duality
- **[Protocol Specification](design/GOSSIP_MESSAGES.md)** — Gossip message types
- **[API Reference](design/API_REFERENCE.md)** — REST and WebSocket endpoints
- **[Agent Layer](design/AGENT_LAYER.md)** — Stateful agent framework
- **[Tool System](design/TOOL_SYSTEM.md)** — Remote tool execution
- **[White Paper](https://drive.google.com/file/d/1-LmkSI4cMZcQiCG6uUgJSerJi2FwUNli/view?usp=sharing)** — Full technical deep-dive

---

## Contributing

```bash
git clone https://github.com/llama-farm/atmosphere.git
cd atmosphere
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

---

## License

Apache 2.0 — See [LICENSE](LICENSE)

---

<p align="center">
  <b>Route intelligence, not packets.</b>
</p>
