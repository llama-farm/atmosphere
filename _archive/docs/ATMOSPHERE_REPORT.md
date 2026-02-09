# Atmosphere: Comprehensive Technical Report

**Report Generated:** February 2026  
**Author:** Atmosphere Documentation Agent

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Core Concepts](#3-core-concepts)
4. [Transport Layer](#4-transport-layer)
5. [SDK Integration](#5-sdk-integration)
6. [LlamaFarm Integration](#6-llamafarm-integration)
7. [Current Capabilities](#7-current-capabilities)
8. [Gaps & TODO](#8-gaps--todo)

---

## 1. Executive Summary

**Atmosphere** is a decentralized mesh networking protocol and platform that routes AI inference requests based on *semantic intent* rather than explicit addresses. Unlike traditional networks where clients must know which server to call, Atmosphere allows clients to express what they need ("analyze this image for defects") and the mesh automatically routes the request to the best available capability.

The core innovation is the **gradient table** architecture combined with a **gossip protocol**. Each node maintains a routing table that maps capability embeddings (semantic vectors) to routing information. When an intent arrives, the semantic router uses a 3-tier cascade (neural embeddings → hash-based fallback → keyword matching) to find the best matching capability. If the capability is local, it executes immediately; if remote, the request routes through the mesh to the appropriate node. This happens in sub-millisecond time thanks to pre-computed embeddings.

Atmosphere is designed as a true platform with cross-platform support. The Python/Mac server handles the core mesh orchestration and AI backend discovery (Ollama, LlamaFarm, vLLM). The Android app participates in the mesh while contributing device-specific capabilities (camera, voice, local inference). Third-party apps can leverage the entire mesh through the Android SDK, which exposes a simple API for chat completions, capability discovery, RAG, and more—all without needing to know or care about the underlying topology.

---

## 2. Architecture Overview

### 2.1 Protocol Stack

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ATMOSPHERE PROTOCOL STACK                        │
├─────────────────────────────────────────────────────────────────────────┤
│  WORK LAYER          Your apps, LlamaFarm, agents, tools                 │
│                      Intent expression, capability consumption           │
├─────────────────────────────────────────────────────────────────────────┤
│  ROUTING LAYER       Semantic routing, gradient tables                   │
│                      Pre-computed embeddings (<1ms routing)              │
│                      3-tier cascade: embedding → hash → keyword          │
├─────────────────────────────────────────────────────────────────────────┤
│  MESH LAYER          Gossip protocol, peer discovery                     │
│                      Session tracking, capability announcements          │
│                      O(log N) propagation, no central authority          │
├─────────────────────────────────────────────────────────────────────────┤
│  IDENTITY LAYER      Ed25519 keypairs (planned)                          │
│                      Mesh tokens for join authentication                 │
│                      Offline token verification                          │
├─────────────────────────────────────────────────────────────────────────┤
│  TRANSPORT LAYER     WebSocket (Cloud Relay), LAN (mDNS), BLE Mesh       │
│                      WiFi Direct, WiFi Aware (future)                    │
│                      Automatic failover across transports                │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **Atmosphere Server** | `atmosphere/` (Python/Mac) | Core mesh node, API server, backend discovery, gossip protocol |
| **Atmosphere Android** | `atmosphere-android/app/` | Android mesh node, local inference, device capabilities |
| **Atmosphere SDK** | `atmosphere-android/atmosphere-sdk/` | AIDL-based SDK for 3rd-party Android apps |
| **Demo Client** | `demo-client/` | Reference implementation of SDK usage |
| **UI Dashboard** | `atmosphere/ui/` | React-based mesh visualization and control |

### 2.3 How Components Connect

```
┌────────────────────────────────────────────────────────────────────────────┐
│                             CLOUD RELAY                                     │
│                    wss://atmosphere-relay-production.up.railway.app         │
└────────────────────────────────────────────────────────────────────────────┘
                      ▲                              ▲
                      │ WebSocket                    │ WebSocket
                      ▼                              ▼
┌──────────────────────────────┐      ┌──────────────────────────────┐
│      MAC/PYTHON NODE         │      │        ANDROID NODE          │
│                              │      │                              │
│  ┌──────────────────────┐   │      │   ┌──────────────────────┐   │
│  │   Gossip Protocol    │◄──┼──────┼──►│   Gossip Protocol    │   │
│  │   Gradient Table     │   │      │   │   Gradient Table     │   │
│  └──────────────────────┘   │      │   └──────────────────────┘   │
│                              │      │                              │
│  ┌──────────────────────┐   │      │   ┌──────────────────────┐   │
│  │   Backend Discovery  │   │      │   │  Local Inference     │   │
│  │   • Ollama           │   │      │   │  • llama.cpp         │   │
│  │   • LlamaFarm        │   │      │   │  • On-device models  │   │
│  │   • vLLM             │   │      │   └──────────────────────┘   │
│  └──────────────────────┘   │      │                              │
│                              │      │   ┌──────────────────────┐   │
│  ┌──────────────────────┐   │      │   │  Device Capabilities │   │
│  │   Semantic Router    │   │      │   │  • Camera, Voice     │   │
│  │   3-tier Cascade     │   │      │   │  • GPS, Sensors      │   │
│  └──────────────────────┘   │      │   └──────────────────────┘   │
│                              │      │              ▲                │
│  ┌──────────────────────┐   │      │              │ AIDL/Binder    │
│  │   REST API (11451)   │   │      │              ▼                │
│  │   WebSocket Events   │   │      │   ┌──────────────────────┐   │
│  └──────────────────────┘   │      │   │   ATMOSPHERE SDK     │   │
│                              │      │   │   (3rd-party apps)   │   │
└──────────────────────────────┘      │   └──────────────────────┘   │
         ▲                            └──────────────────────────────┘
         │ LAN (mDNS, port 11450)                    ▲
         │ BLE Mesh (future)                         │
         └───────────────────────────────────────────┘
```

---

## 3. Core Concepts

### 3.1 Semantic Routing

Atmosphere routes by **intent meaning**, not by address. When you send a request like "summarize this document", the semantic router:

1. **Embeds the intent** into a vector using neural embeddings (or hash-based fallback)
2. **Searches the gradient table** for capabilities with similar vectors
3. **Applies a 3-tier cascade** to ensure routing always works:
   - **Tier 1: Neural Embeddings** (best quality, requires embedding model)
   - **Tier 2: Hash Embeddings** (character n-grams, fast, no dependencies)
   - **Tier 3: Keyword Matching** (pure text overlap, last resort)
4. **Routes to the best match** locally or forwards through the mesh

```python
# From atmosphere/router/semantic.py
class SemanticRouter:
    async def route(self, intent: str) -> RouteResult:
        # Tier 1: Embedding match
        if intent_vector is not None:
            result = self._match_embedding(intent_vector)
            if result.score >= self.embedding_min_score:
                return result
        
        # Tier 2: Hash fallback
        result = self._match_hash(intent_hash_vector)
        if result.score >= self.hash_min_score:
            return result
        
        # Tier 3: Keyword fallback
        result = self._match_keywords(intent_keywords)
        if result.score >= self.keyword_min_score:
            return result
```

### 3.2 Gradient Table

Each node maintains a **gradient table**—a map from capability embeddings to routing information (next hop, hops, latency, confidence). The table is updated via gossip announcements.

```python
# From atmosphere/router/gradient.py
@dataclass
class GradientEntry:
    capability_id: str
    capability_label: str
    capability_vector: np.ndarray  # Semantic embedding
    hops: int                       # Distance to capability
    next_hop: str                   # Immediate peer to forward to
    via_node: str                   # Original capability source
    estimated_latency_ms: float
    confidence: float               # Decays with hops (0.95^hops)
```

The gradient table supports:
- **Update only if better**: New routes only replace existing if they have fewer hops
- **Automatic expiration**: Entries expire after 5 minutes without refresh
- **Fast vector search**: Pre-computed index for O(1) similarity lookup

### 3.3 Gossip Protocol

Nodes periodically broadcast capability announcements to their peers. Announcements propagate through the mesh with TTL (time-to-live) decrement, ensuring eventual consistency without flooding.

**Announcement Contents:**
- `from_node`: Source node ID
- `capabilities`: List of capability info with vectors
- `resources`: CPU load, memory, battery status
- `endpoints`: Dynamic IP addresses and ports
- `ihave`: Capability IDs this node has
- `iwant`: Capability IDs this node needs (future)
- `node_cost`: Dynamic routing cost based on resources

```python
# From atmosphere/mesh/gossip.py
class GossipProtocol:
    async def announce(self):
        """Broadcast capabilities every 30 seconds"""
        announcement = self.build_announcement()
        await self._broadcast_callback(self.node_id, announcement.to_json())
    
    async def handle_announcement(self, data, from_peer):
        """Process incoming announcement, update tables, forward if TTL > 0"""
        # Update endpoint registry
        # Update routing table
        # Update gradient table
        # Forward with decremented TTL
```

### 3.4 Bidirectional Capabilities

Every capability is both a **TRIGGER** (push) and a **TOOL** (pull):

```
┌───────────────┐                      ┌───────────────┐
│   TRIGGERS    │                      │    TOOLS      │
│   (push)      │                      │    (pull)     │
├───────────────┤                      ├───────────────┤
│ • motion      │                      │ • get_frame() │
│ • person      │                      │ • get_clip()  │
│ • package     │                      │ • get_history │
└───────────────┘                      └───────────────┘
```

For example, a camera capability can:
- **Push** events when motion is detected (trigger)
- **Respond** to requests for current frame (tool)

### 3.5 Mesh Tokens & Authentication

Meshes use signed tokens for join authentication:

```kotlin
// From TransportManager.kt
data class MeshToken(
    val meshId: String,
    val nodeId: String?,
    val issuedAt: Long,
    val expiresAt: Long,
    val capabilities: List<String>,
    val issuerId: String,
    val nonce: String,
    val signature: String
)
```

Tokens are verified offline using the mesh's public key, allowing nodes to join without a central authority.

---

## 4. Transport Layer

### 4.1 Multi-Transport Architecture

Atmosphere supports multiple transports with automatic failover:

```kotlin
// From TransportManager.kt
enum class TransportType(val priority: Int) {
    LAN(1),          // Local network WebSocket - fastest
    WIFI_DIRECT(2),  // WiFi P2P - no router needed
    BLE_MESH(3),     // Bluetooth mesh - works offline
    MATTER(4),       // Smart home devices
    RELAY(5);        // Cloud relay - always works (fallback)
}
```

### 4.2 Transport Selection

```kotlin
// Priority order: prefer faster transports
for (type in TransportType.values().sortedBy { it.priority }) {
    val transport = transports[type]
    if (transport != null && transport.connected) {
        if (transport.send(message)) {
            preferred = type
            return true
        }
    }
}
```

### 4.3 Cloud Relay

The primary transport for initial connectivity:
- **URL**: `wss://atmosphere-relay-production.up.railway.app`
- **Protocol**: WebSocket with JSON messages
- **Features**: Mesh registration, message routing, peer discovery

### 4.4 LAN Transport

Direct local network connectivity:
- **Discovery**: mDNS (`_atmosphere._tcp.local`)
- **Port**: 11450 (default)
- **Speed**: Fastest option when available

### 4.5 BLE Mesh (Implemented but Beta)

True mesh networking for offline scenarios:

```kotlin
// From BleTransport.kt
object BleUuids {
    val MESH_SERVICE_UUID = UUID.fromString("A7A05F30-0001-4000-8000-00805F9B34FB")
    val TX_CHAR_UUID = UUID.fromString("A7A05F30-0002-4000-8000-00805F9B34FB")
    val RX_CHAR_UUID = UUID.fromString("A7A05F30-0003-4000-8000-00805F9B34FB")
}
```

**Features:**
- **GATT server & client** for bidirectional communication
- **Message fragmentation** for payloads > MTU
- **TTL-based routing** with flood forwarding
- **Loop prevention** via nonce cache
- **Mesh filtering** by mesh_id in service data

### 4.6 WiFi Direct (Implemented)

Android WiFi P2P for high-bandwidth offline:
- Creates soft AP for direct device-to-device
- Higher bandwidth than BLE (~250 Mbps)
- One device becomes group owner

### 4.7 WiFi Aware (Planned for iOS 19)

The EU DMA is forcing Apple to adopt WiFi Aware, enabling true cross-platform P2P WiFi. This will be the preferred offline transport once available.

### 4.8 Failover Logic

```
Connection Attempt:
1. Try LAN (mDNS discovery, port 11450)
2. Try WiFi Direct (if Android, create/join group)
3. Try BLE Mesh (always available on modern phones)
4. Fall back to Cloud Relay (always works)

During Operation:
- Monitor transport health via periodic probes
- Switch to better transport when available
- Maintain multiple connections for redundancy
```

---

## 5. SDK Integration

### 5.1 Android SDK Overview

Third-party Android apps integrate with Atmosphere via the SDK:

```kotlin
// Check if Atmosphere app is installed
if (!AtmosphereClient.isInstalled(context)) {
    // Show install prompt
    val installUrl = AtmosphereClient.getInstallUrl()
}

// Connect to Atmosphere service
val atmosphere = AtmosphereClient.connect(context)

// Send chat request - mesh handles routing
val result = atmosphere.chat(
    messages = listOf(ChatMessage.user("Hello, mesh!"))
)
```

### 5.2 AIDL Interface

The SDK communicates via Android's AIDL (Android Interface Definition Language):

```aidl
interface IAtmosphereService {
    String getVersion();
    String route(String intent, String payload);
    String chatCompletion(String messagesJson, String model);
    List<AtmosphereCapability> getCapabilities();
    String invokeCapability(String capabilityId, String payload);
    String getMeshStatus();
    String getCostMetrics();
    String joinMesh(String meshId, String credentialsJson);
    
    // RAG Support
    String createRagIndex(String indexId, String documentsJson);
    String queryRag(String indexId, String query, boolean generateAnswer);
    String deleteRagIndex(String indexId);
    String listRagIndexes();
}
```

### 5.3 Key SDK Methods

| Method | Purpose |
|--------|---------|
| `chat(messages)` | Chat completion via mesh |
| `capabilities()` | List all available capabilities |
| `route(intent)` | Find best capability without executing |
| `invoke(capabilityId, payload)` | Call specific capability |
| `meshStatus()` | Get connection status |
| `costs()` | Get device cost metrics |
| `createRagIndex()` | Create local RAG index |
| `queryRag()` | Query RAG with optional answer generation |

### 5.4 Platform Thesis (Proven)

The Demo Client proves that Atmosphere is a **platform**, not just an app:

```
┌─────────────────────────────────────────────────────────────┐
│                    Demo Client App                          │
│  1. Upload Documents → createRagIndex("secret_base")        │
│  2. Ask Question → queryRag("Where is the base?")           │
│  3. Display Answer                                          │
└─────────────────────────────────────────────────────────────┘
                              │
                         AIDL/Binder
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Atmosphere Service                         │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ LocalRagStore│→ │ Retrieval    │→ │ LocalInference  │   │
│  │ (BM25 Index) │  │ (Top-K Docs) │  │ (LLM Answer)    │   │
│  └──────────────┘  └──────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────┘

🔒 100% On-Device — No Cloud, No Mac, No Network Required
```

---

## 6. LlamaFarm Integration

### 6.1 Backend Discovery

Atmosphere auto-discovers LlamaFarm instances on the local machine:

```python
# From atmosphere/discovery/scanner.py
async def scan_llamafarm(self, host="localhost", port=14345):
    # Check health
    async with session.get(f"{backend.url}/health") as resp:
        if resp.status == 200:
            backend.healthy = True
    
    # Import discoverable projects
    async with session.get(f"{backend.url}/v1/projects/discoverable") as resp:
        projects = await resp.json()
```

### 6.2 Project-Based API

LlamaFarm uses a namespace/project structure:

```
/v1/projects/{namespace}/{project}/chat/completions
```

Only projects in the **"discoverable"** namespace are exposed to the mesh.

### 6.3 Capability Import

```python
# From atmosphere/discovery/llamafarm.py
async def import_capabilities(self) -> Dict[str, List[str]]:
    projects = await self.list_discoverable_projects()
    
    for project in projects:
        capability_id = f"{namespace}/{project_name}"
        project_type = config.get("type", "llm")
        capabilities[project_type].append(capability_id)
    
    return capabilities  # {"llm": [...], "vision": [...], "rag": [...]}
```

### 6.4 Semantic Routing to LlamaFarm

When an intent matches a LlamaFarm capability:

1. Semantic router finds best matching project
2. Request routes through mesh to the LlamaFarm node
3. LlamaFarm executes using the project's configured model
4. Response returns through mesh to original requester

---

## 7. Current Capabilities

### 7.1 What's Implemented and Working

| Feature | Status | Notes |
|---------|--------|-------|
| **Gossip Protocol** | ✅ Complete | Capability announcements, TTL-based propagation |
| **Gradient Table** | ✅ Complete | Vector similarity, hop-adjusted routing |
| **Semantic Router** | ✅ Complete | 3-tier cascade (embedding/hash/keyword) |
| **Cloud Relay** | ✅ Complete | WebSocket-based mesh connectivity |
| **Android Mesh Node** | ✅ Complete | Full mesh participation |
| **Android SDK** | ✅ Complete | AIDL-based service binding |
| **LlamaFarm Integration** | ✅ Complete | Project discovery, chat completion |
| **Ollama Integration** | ✅ Complete | Model discovery, inference |
| **Local RAG (Android)** | ✅ Complete | BM25-based retrieval |
| **BLE Transport** | ⚡ Beta | Working but needs production testing |
| **WiFi Direct** | ⚡ Beta | Android-only, working |
| **React Dashboard** | ✅ Complete | Mesh visualization, gossip feed |
| **Intent Classification** | ✅ Complete | Complexity analysis, model sizing |
| **Cost-Based Routing** | ✅ Complete | Battery, CPU, memory awareness |
| **Voice Capability** | ✅ Complete | STT/TTS on Android |
| **Camera Capability** | ⚡ Partial | Capture works, approval flow TODO |

### 7.2 Supported AI Backends

| Backend | Auto-Discovery | Chat | Embeddings | Vision |
|---------|---------------|------|------------|--------|
| Ollama | ✅ | ✅ | ✅ | ✅ |
| LlamaFarm | ✅ | ✅ | ✅ | ✅ |
| vLLM | ✅ | ✅ | ❌ | ❌ |
| OpenAI | ❌ Manual | ✅ | ✅ | ✅ |

### 7.3 Transport Status

| Transport | Mac | Android | iOS |
|-----------|-----|---------|-----|
| Cloud Relay | ✅ | ✅ | 🔜 |
| LAN (WebSocket) | ✅ | ⚡ | 🔜 |
| BLE Mesh | 🔜 | ⚡ | 🔜 |
| WiFi Direct | ❌ | ⚡ | ❌ |
| WiFi Aware | ❌ | 🔜 | 🔜 (iOS 19) |

Legend: ✅ Complete, ⚡ Beta, 🔜 Planned, ❌ N/A

---

## 8. Gaps & TODO

### 8.1 High Priority

| Gap | Description | Impact |
|-----|-------------|--------|
| **iOS App** | No iOS Atmosphere node exists | Can't form mesh with iPhones |
| **Ed25519 Identity** | Key generation exists but not fully integrated | Security holes in mesh auth |
| **Streaming Responses** | Chat completions return all-at-once | Poor UX for long responses |
| **Production BLE Testing** | BLE mesh works in dev, untested at scale | May fail with >5 devices |
| **Mesh Persistence** | Routing tables lost on restart | Cold start latency |

### 8.2 Medium Priority

| Gap | Description | Impact |
|-----|-------------|--------|
| **LAN Transport (Android)** | mDNS discovery not fully wired | Falls back to relay on LAN |
| **Matter Integration** | Research complete, no implementation | Can't route through smart home |
| **Agent Framework** | Designed but not complete | No stateful agents |
| **Model Deployment Push** | Can pull models, can't push | Manual model distribution |
| **Multimodal Input (SDK)** | Text only, no image/audio | Limited third-party use cases |

### 8.3 Low Priority / Future

| Gap | Description | Impact |
|-----|-------------|--------|
| **WiFi Aware** | Waiting for iOS 19 | No cross-platform P2P WiFi |
| **Thread Bridge** | Requires dedicated hardware | Can't mesh with Thread devices |
| **Organic Learning** | Models can't improve at edge | Static inference only |
| **Federation** | Single mesh only | Can't span organizations |
| **Kotlin Multiplatform SDK** | Android only | iOS apps can't use SDK |

### 8.4 Known Issues

1. **Token Replay on Reconnect**: Fixed in TOKEN_REPLAY_FIX.md but needs verification
2. **Native Loading on Some Devices**: Some devices fail llama.cpp loading (NATIVE_LOADING_FIXES.md)
3. **GATT Connection Limits**: BLE can only maintain ~5 simultaneous connections
4. **WiFi Direct Group Owner**: Only one device can be GO, complicates topology

### 8.5 Research Completed (Ready for Implementation)

The `research/offline-mesh/` folder contains detailed designs ready for implementation:

- **BLE_MESH_DESIGN.md**: Full protocol spec, message format, Android/iOS code
- **WIFI_DIRECT_DESIGN.md**: Android implementation, limitations
- **MATTER_INTEGRATION.md**: Thread bridge concept
- **POC_BLE_DISCOVERY.md**: Working proof-of-concept code

---

## Appendix A: Key File Locations

| Purpose | Path |
|---------|------|
| Main Python Package | `atmosphere/` |
| Gossip Protocol | `atmosphere/mesh/gossip.py` |
| Semantic Router | `atmosphere/router/semantic.py` |
| Gradient Table | `atmosphere/router/gradient.py` |
| LlamaFarm Backend | `atmosphere/discovery/llamafarm.py` |
| Transport Abstraction | `atmosphere/mesh/transport.py` |
| Smart Routing Table | `atmosphere/mesh/routing.py` |
| Android App | `atmosphere-android/app/` |
| BLE Transport (Android) | `app/.../transport/BleTransport.kt` |
| Transport Manager | `app/.../network/TransportManager.kt` |
| Android SDK | `atmosphere-android/atmosphere-sdk/` |
| SDK Client | `atmosphere-sdk/.../sdk/AtmosphereClient.kt` |
| Demo Client | `demo-client/app/` |
| React Dashboard | `atmosphere/ui/` |
| Offline Mesh Research | `atmosphere/research/offline-mesh/` |

---

## Appendix B: Configuration

### Default Ports

| Service | Port |
|---------|------|
| Atmosphere API | 11451 |
| Mesh LAN Transport | 11450 |
| LlamaFarm | 14345 |
| Ollama | 11434 |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ATMOSPHERE_PORT` | 11451 | API server port |
| `ATMOSPHERE_RELAY` | Railway URL | Cloud relay endpoint |
| `LF_DATA_DIR` | `~/.llamafarm` | LlamaFarm data directory |

---

## Appendix C: Message Types

### Gossip Announcement

```json
{
  "type": "announce",
  "from": "node-id-abc123",
  "capabilities": [
    {
      "id": "node-id:llm",
      "label": "llm",
      "description": "Language model for text generation...",
      "vector": [0.12, -0.34, ...],
      "local": true,
      "hops": 0
    }
  ],
  "resources": {
    "cpu_load": 0.25,
    "memory_percent": 45.2,
    "battery_percent": 85,
    "plugged_in": true
  },
  "endpoints": {
    "local_ips": ["192.168.1.100"],
    "local_port": 11450
  },
  "ttl": 10,
  "node_cost": 1.0
}
```

### BLE Message Header

```
┌────┬────┬────┬────┬────────┬────────┬────────┐
│ V  │ T  │TTL │ F  │ SEQ    │ FRAG   │ TOTAL  │
│ 1  │ 1  │ 1  │ 1  │ 2      │ 1      │ 1      │
└────┴────┴────┴────┴────────┴────────┴────────┘
Total: 8 bytes
```

---

*This report was generated by analyzing the actual codebase across `atmosphere/`, `atmosphere-android/`, and `demo-client/` directories.*
