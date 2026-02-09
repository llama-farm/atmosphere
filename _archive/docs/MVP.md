# Atmosphere MVP Specification

**Version:** 1.0  
**Date:** 2025-02-02  
**Target Completion:** 4 weeks  

---

## Executive Summary

This document defines the Minimum Viable Product for Atmosphere — the Internet of Intent. The MVP proves the core thesis: **semantic routing of work to capability across a resilient mesh**. We prioritize breadth over depth: a working end-to-end system with basic implementations across all critical components, rather than a perfect implementation of any single piece.

---

## 1. Scope Definition

### ✅ MVP Must Have

| # | Component | What's In | Success Criteria |
|---|-----------|-----------|------------------|
| 1 | **Core Mesh** | Node join/leave, gossip protocol, gradient tables, heartbeat | 3+ nodes discovering and routing to each other |
| 2 | **Semantic Routing** | Intent embedding, capability matching, best-node routing, fallback | 95%+ routing accuracy on test intents |
| 3 | **Security** | Rownd Local integration, token issuance, offline verification, basic revocation | Join requires valid token; revoked tokens rejected |
| 4 | **Agent System** | Agent registry (gossip-distributed), base+diff invocation, 3 working agents, sleeping agents | Agents deploy, wake, and execute across mesh |
| 5 | **Tool System** | Tool registry (gossip-distributed), provider announcements, 10 core tools, local + remote execution | Tools invoke locally and route to remote nodes |
| 6 | **LlamaFarm Integration** | Inference adapter, embeddings adapter, config sync, model distribution | Intent routes to LlamaFarm-backed node, returns result |
| 7 | **Offline Model Distribution** | Package models with config, mesh/local transfer, integrity verification | Model transfers to offline node, loads, serves inference |
| 8 | **Basic Matter Bridge** | Device discovery, expose as tools, command execution | Matter device controlled via mesh intent |
| 9 | **Knowledge Distribution** | RAG data sync, embedding sync, document chunks | RAG query routed to node with relevant chunks |

### 🔜 MVP Deferred (v1.1+)

| # | Component | Why Deferred |
|---|-----------|--------------|
| 1 | Training loop (model updates) | Complexity; inference-first |
| 2 | Multi-hop complex workflows | Standard routing sufficient for MVP |
| 3 | Full orchestrator agents | Basic agents prove the architecture |
| 4 | Cloud API adapters (OpenAI, Anthropic) | Local-first focus |
| 5 | Advanced federation (cross-mesh) | Single mesh first |
| 6 | Agentic delegation chains | Sequential agent invocation works first |
| 7 | Full Matter commissioning | Discovery + control sufficient |
| 8 | Production-grade monitoring | Basic health/metrics for now |
| 9 | Kubernetes deployment | Manual multi-node deployment |
| 10 | Rate limiting / cost tracking | Trust-based MVP |

---

## 2. Architecture (MVP Subset)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTENT                                     │
│                   "What's the temperature in the garage?"                    │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ATMOSPHERE NODE                                    │
│                                                                              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐       │
│  │  Semantic Router │───▶│  Gradient Table  │───▶│  Route Decision  │       │
│  │  (embed intent)  │    │  (cap → next hop)│    │  (local/remote)  │       │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘       │
│           ▲                       ▲                       │                  │
│           │                       │                       ▼                  │
│  ┌────────┴─────────┐    ┌───────┴────────┐    ┌──────────────────┐        │
│  │ LlamaFarm Adapter│    │ Gossip Protocol │    │   Execute Work   │        │
│  │ (local inference)│    │ (state sync)    │    │   (or forward)   │        │
│  └──────────────────┘    └────────────────┘    └──────────────────┘        │
│                                   │                       │                  │
│                                   ▼                       ▼                  │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                     REGISTRIES (Gossip-Synced)                   │       │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │       │
│  │  │   Agents    │  │    Tools    │  │ Capabilities│              │       │
│  │  │  (3 active) │  │  (10 core)  │  │  (all nodes)│              │       │
│  │  └─────────────┘  └─────────────┘  └─────────────┘              │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                        SECURITY LAYER                            │       │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │       │
│  │  │ Rownd Local │  │   Tokens    │  │ Revocation  │              │       │
│  │  │ (Ed25519)   │  │ (offline OK)│  │  (gossip)   │              │       │
│  │  └─────────────┘  └─────────────┘  └─────────────┘              │       │
│  └─────────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
     ┌────────────┐          ┌────────────┐          ┌────────────┐
     │  Node B    │          │  Node C    │          │  Node D    │
     │ (LlamaFarm)│          │  (Matter)  │          │  (Vision)  │
     │  70B LLM   │          │  Devices   │          │  Camera    │
     └────────────┘          └────────────┘          └────────────┘
```

### Data Flow (MVP)

```
1. Intent arrives → Embed with local embeddings
2. Match against gradient table → Find best node
3. If local: Execute via registered tool/agent
4. If remote: Forward to next-hop (single hop in MVP)
5. Result returns through same path
6. Gossip updates gradient tables with routing success/failure
```

---

## 3. Implementation Phases

### Phase 1: Foundation (Week 1)

**Goal:** Nodes can join, discover each other, and route intents.

| Task | Description | Deliverable | Est. Hours |
|------|-------------|-------------|------------|
| 1.1 | Gossip protocol implementation | `mesh/gossip.py` with pub/sub and state merge | 8h |
| 1.2 | Gradient table implementation | `router/gradient.py` with capability→hop cache | 8h |
| 1.3 | Node lifecycle (join/leave) | `mesh/node.py` with join handshake | 6h |
| 1.4 | Heartbeat + health tracking | `mesh/health.py` with failure detection | 4h |
| 1.5 | Basic semantic routing | `router/semantic.py` using existing embeddings | 6h |
| 1.6 | mDNS discovery | `mesh/discovery.py` for LAN discovery | 4h |
| 1.7 | Integration testing | 3-node mesh test harness | 4h |

**Test Criteria:**
- [ ] Start 3 nodes on different ports
- [ ] Nodes discover each other via mDNS within 30s
- [ ] Gradient tables converge within 5 gossip rounds
- [ ] Intent routes to capable node (not just random)
- [ ] Node A sees Node B go offline within 60s of kill

---

### Phase 2: Security (Week 2, Days 1-3)

**Goal:** Mesh membership requires cryptographic authorization.

| Task | Description | Deliverable | Est. Hours |
|------|-------------|-------------|------------|
| 2.1 | Rownd Local integration | `auth/identity.py` with Ed25519 keypairs | 6h |
| 2.2 | Token issuance on join | `auth/tokens.py` - mesh signs join request | 4h |
| 2.3 | Offline token verification | Signature check without network call | 4h |
| 2.4 | Basic revocation (gossip) | Revocation list propagates via gossip | 4h |
| 2.5 | Token refresh flow | Re-issue before expiry | 3h |

**Test Criteria:**
- [ ] Node cannot join mesh without valid token
- [ ] Token verifies offline (no network call)
- [ ] Revoked node rejected within 2 gossip rounds
- [ ] Token refresh happens automatically before expiry

---

### Phase 3: Agents & Tools (Week 2, Day 4 - Week 3, Day 3)

**Goal:** Agents and tools are mesh-native and distributed.

#### 3A: Tool System (4 days)

| Task | Description | Deliverable | Est. Hours |
|------|-------------|-------------|------------|
| 3.1 | Tool registry schema | `tools/registry.py` with JSON schema | 4h |
| 3.2 | Gossip sync for tools | Tool manifests propagate via gossip | 4h |
| 3.3 | Tool invocation (local) | `tools/executor.py` runs local tools | 4h |
| 3.4 | Tool invocation (remote) | Route to node with tool, execute there | 6h |
| 3.5 | Implement 10 core tools | See tool list below | 12h |

**MVP Tools (10 minimum):**

| Tool | Capability | Description |
|------|------------|-------------|
| `llm:generate` | llm | Text generation via LlamaFarm |
| `llm:embed` | embeddings | Text embedding |
| `vision:analyze` | vision | Image analysis |
| `vision:detect` | vision | Object detection |
| `rag:query` | rag | Query knowledge base |
| `notify:send` | notification | Send alert/notification |
| `matter:list_devices` | matter | List Matter devices |
| `matter:execute` | matter | Execute device command |
| `system:health` | system | Node health metrics |
| `mesh:route` | routing | Route intent to capability |

#### 3B: Agent System (4 days)

| Task | Description | Deliverable | Est. Hours |
|------|-------------|-------------|------------|
| 3.6 | Agent registry schema | `agents/registry.py` with agent definitions | 4h |
| 3.7 | Gossip sync for agents | Agent manifests propagate | 4h |
| 3.8 | Base + diff loading | Small activation footprint | 6h |
| 3.9 | Sleeping agent mechanism | Wake on matching intent | 4h |
| 3.10 | Implement 3 agents | See agent list below | 12h |

**MVP Agents (3 minimum):**

| Agent | Type | Description |
|-------|------|-------------|
| `vision_monitor` | Reactive | Watches camera, emits anomalies |
| `anomaly_detector` | Deliberative | Analyzes sensor patterns |
| `notifier` | Reactive | Routes alerts to appropriate channels |

**Test Criteria:**
- [ ] Tool registry syncs across 3 nodes within 30s
- [ ] Remote tool invocation works (Node A calls tool on Node B)
- [ ] All 10 tools execute successfully
- [ ] Agent wakes on matching intent
- [ ] Sleeping agent uses <1MB resident memory
- [ ] Agent invokes tool successfully

---

### Phase 4: LlamaFarm Integration (Week 3, Days 4-7)

**Goal:** Atmosphere routes to LlamaFarm for inference/embeddings.

| Task | Description | Deliverable | Est. Hours |
|------|-------------|-------------|------------|
| 4.1 | LlamaFarm inference adapter | `discovery/llamafarm.py` - generation API | 6h |
| 4.2 | LlamaFarm embeddings adapter | Same file - embedding API | 4h |
| 4.3 | Config sync | `llamafarm.yaml` distributed to nodes | 4h |
| 4.4 | Model distribution | Package model + config for transfer | 8h |
| 4.5 | Offline model loading | Verify and load on disconnected node | 6h |

**Test Criteria:**
- [ ] Intent requiring 70B routes to LlamaFarm node
- [ ] Embeddings generated via LlamaFarm adapter
- [ ] `llamafarm.yaml` changes propagate within 60s
- [ ] Model package transfers to node (can use USB/local)
- [ ] Offline node loads model and serves inference

---

### Phase 5: Matter Bridge (Week 4, Days 1-3)

**Goal:** Smart home devices controllable via mesh intents.

| Task | Description | Deliverable | Est. Hours |
|------|-------------|-------------|------------|
| 5.1 | Matter device discovery | `matter/bridge.py` - scan local network | 6h |
| 5.2 | Device → Tool mapping | Each device becomes mesh tool | 4h |
| 5.3 | Command execution | Send commands to Matter devices | 6h |
| 5.4 | State synchronization | Device state available in mesh | 4h |

**Test Criteria:**
- [ ] Matter devices discovered and listed
- [ ] "Turn on living room light" routes to correct device
- [ ] Light actually turns on
- [ ] Device state (on/off) visible in mesh

---

### Phase 6: Knowledge Distribution & Demo (Week 4, Days 4-7)

**Goal:** RAG works across mesh; full demo scenario passes.

| Task | Description | Deliverable | Est. Hours |
|------|-------------|-------------|------------|
| 6.1 | RAG chunk distribution | Distribute document chunks to nodes | 6h |
| 6.2 | Embedding sync | Pre-computed embeddings follow chunks | 4h |
| 6.3 | RAG query routing | Query routes to node with relevant chunks | 4h |
| 6.4 | Demo scenario | End-to-end scripted demo | 8h |
| 6.5 | Documentation | Setup guide, API reference | 8h |

**Test Criteria:**
- [ ] Document chunks distributed across 3+ nodes
- [ ] RAG query finds relevant chunks regardless of location
- [ ] Full demo scenario (below) executes successfully
- [ ] Documentation allows new user to run demo

---

## 4. Demo Scenario: "Home Intelligence"

This end-to-end scenario proves the MVP works.

### Setup

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HOME MESH                                     │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐        │
│  │   Mac Studio   │  │  Dell Server   │  │   Raspberry Pi │        │
│  │                │  │                │  │                │        │
│  │  - Atmosphere  │  │  - Atmosphere  │  │  - Atmosphere  │        │
│  │  - LlamaFarm   │  │  - LlamaFarm   │  │  - Matter      │        │
│  │  - 7B model    │  │  - 70B model   │  │  - Sensors     │        │
│  │  - RAG chunks  │  │  - RAG chunks  │  │  - Camera      │        │
│  └────────────────┘  └────────────────┘  └────────────────┘        │
│          │                   │                   │                  │
│          └───────────────────┴───────────────────┘                  │
│                           MESH                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Scenario Script

```bash
# 1. MESH DISCOVERY
# User runs on Mac Studio
$ atmosphere mesh status
Nodes: 3 (Mac-Studio, Dell-Server, Garage-Pi)
Capabilities:
  - llm: Mac-Studio (7B), Dell-Server (70B)
  - vision: Garage-Pi
  - matter: Garage-Pi
  - rag: Mac-Studio, Dell-Server
Status: Healthy

# 2. SIMPLE ROUTING
# Intent routes to best node
$ atmosphere intent "What's 2+2?"
→ Routed to: Mac-Studio (local, llm, 0 hops)
← Result: "2+2 = 4"

# 3. SEMANTIC CAPABILITY MATCHING
# Complex query routes to 70B
$ atmosphere intent "Analyze the security implications of our network topology"
→ Routed to: Dell-Server (llm/70b, 1 hop)
← Result: [Detailed analysis from 70B model]

# 4. RAG QUERY
# Knowledge retrieval across mesh
$ atmosphere intent "What does our IoT security policy say about cameras?"
→ Chunks retrieved from: Mac-Studio (2 chunks), Dell-Server (1 chunk)
→ Synthesis on: Dell-Server
← Result: "According to your IoT security policy..."

# 5. MATTER DEVICE CONTROL
# Smart home via natural language
$ atmosphere intent "Turn on the garage lights"
→ Routed to: Garage-Pi (matter, 1 hop)
→ Tool: matter:execute(device="garage_light", action="on")
← Result: "Garage lights turned on"

# 6. AGENT ACTIVATION
# Camera monitoring agent wakes
$ atmosphere agent invoke vision_monitor --input "Check garage camera"
→ Agent: vision_monitor (Garage-Pi)
→ Tool: vision:analyze(source="garage_cam")
← Analysis: "No anomalies detected. 1 vehicle present."

# 7. OFFLINE RESILIENCE
# Disconnect Dell-Server
$ atmosphere node disconnect Dell-Server
# (simulate network failure)

$ atmosphere intent "What's the weather like?"
→ Fallback: Mac-Studio (llm/7b, local)
← Result: [7B model response - degraded but functional]

# 8. TOKEN VERIFICATION
# Security check
$ atmosphere auth verify
Token: Valid (expires in 23h)
Verified: Offline (no network call)

# 9. MESH RECOVERY
$ atmosphere node reconnect Dell-Server
→ Gossip sync: 3 rounds
→ Gradient tables: Updated
$ atmosphere mesh status
Nodes: 3 (all healthy)
```

### Demo Success Criteria

| Step | Requirement | Pass/Fail |
|------|-------------|-----------|
| 1 | 3+ nodes in mesh, all healthy | |
| 2 | Simple intent routes locally | |
| 3 | Complex intent routes to best node | |
| 4 | RAG query retrieves from multiple nodes | |
| 5 | Matter device responds to command | |
| 6 | Agent wakes and executes | |
| 7 | Mesh continues with node failure | |
| 8 | Token verifies without network | |
| 9 | Mesh recovers when node returns | |

---

## 5. Risk Assessment

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Gossip convergence too slow** | Routes stale, wrong nodes selected | Tune gossip interval; add push on significant changes |
| **LlamaFarm adapter complexity** | Integration delays entire stack | Start adapter early; mock if needed |
| **Matter protocol complexity** | Bridge incomplete in time | Use existing Matter library; limit to basic on/off |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Model distribution size** | Slow offline transfer | Support resume; use delta/diff if models share base |
| **Agent memory footprint** | Sleeping agents not actually small | Implement lazy loading; measure early |
| **Token revocation latency** | Revoked node operates too long | Shorter gossip for revocations; gossip priority |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Embedding model differences** | Routing inconsistency | Standardize on single embedding model |
| **Network partition handling** | Temporary mesh split | MVP accepts this; self-heals on reconnect |

---

## 6. Definition of Done

### MVP is complete when:

1. **All 9 core components** have basic working implementations
2. **Demo scenario** executes end-to-end successfully
3. **Test criteria** for each phase are met
4. **Documentation** allows a new user to:
   - Set up a 3-node mesh
   - Route an intent
   - Control a Matter device
   - Understand the architecture

### Non-Goals for MVP

- Performance optimization
- Beautiful UI
- Production hardening
- Multi-mesh federation
- Cloud integration
- Full test coverage (aim for critical paths only)

---

## 7. Timeline Summary

```
Week 1 ─────────────────────────────────────────────────────
  │ Phase 1: Foundation
  │ - Gossip protocol
  │ - Gradient tables
  │ - Node lifecycle
  │ - Basic routing
  └─────────────────────────────────────────────────────────

Week 2 ─────────────────────────────────────────────────────
  │ Phase 2: Security (Days 1-3)
  │ - Rownd Local
  │ - Token flow
  │
  │ Phase 3A: Tools (Days 4-7 start)
  │ - Tool registry
  │ - 10 core tools
  └─────────────────────────────────────────────────────────

Week 3 ─────────────────────────────────────────────────────
  │ Phase 3B: Agents (Days 1-4)
  │ - Agent registry
  │ - 3 working agents
  │
  │ Phase 4: LlamaFarm (Days 4-7)
  │ - Adapters
  │ - Model distribution
  └─────────────────────────────────────────────────────────

Week 4 ─────────────────────────────────────────────────────
  │ Phase 5: Matter (Days 1-3)
  │ - Device bridge
  │ - Commands working
  │
  │ Phase 6: Demo (Days 4-7)
  │ - Knowledge distribution
  │ - End-to-end demo
  │ - Documentation
  └─────────────────────────────────────────────────────────

Day 28: MVP Complete ✓
```

---

## Appendix A: File Structure (MVP)

```
atmosphere/
├── atmosphere/
│   ├── mesh/
│   │   ├── gossip.py        # Gossip protocol
│   │   ├── gradient.py      # Gradient tables
│   │   ├── node.py          # Node lifecycle
│   │   ├── health.py        # Heartbeat/health
│   │   └── discovery.py     # mDNS discovery
│   ├── router/
│   │   ├── semantic.py      # Intent embedding + matching
│   │   ├── executor.py      # Work execution/forwarding
│   │   └── gradient.py      # Routing decisions
│   ├── auth/
│   │   ├── identity.py      # Ed25519 keypairs (Rownd Local)
│   │   ├── tokens.py        # Token issue/verify
│   │   └── revocation.py    # Revocation list
│   ├── tools/
│   │   ├── registry.py      # Tool definitions
│   │   ├── executor.py      # Local/remote execution
│   │   └── builtin/         # 10 core tools
│   │       ├── llm.py
│   │       ├── vision.py
│   │       ├── rag.py
│   │       ├── notify.py
│   │       ├── matter.py
│   │       └── system.py
│   ├── agents/
│   │   ├── registry.py      # Agent definitions
│   │   ├── runtime.py       # Agent lifecycle
│   │   ├── sleeping.py      # Sleeping agent mechanism
│   │   └── builtin/         # 3 MVP agents
│   │       ├── vision_monitor.py
│   │       ├── anomaly_detector.py
│   │       └── notifier.py
│   ├── discovery/
│   │   ├── llamafarm.py     # LlamaFarm adapter
│   │   └── ollama.py        # Ollama adapter (fallback)
│   ├── matter/
│   │   └── bridge.py        # Matter device bridge
│   ├── knowledge/
│   │   ├── chunks.py        # Document distribution
│   │   └── sync.py          # Embedding sync
│   └── api/
│       ├── server.py        # FastAPI server
│       └── routes.py        # REST endpoints
├── tests/
│   ├── test_mesh.py
│   ├── test_routing.py
│   ├── test_auth.py
│   ├── test_tools.py
│   ├── test_agents.py
│   └── test_demo.py         # Full demo scenario test
├── docs/
│   ├── QUICKSTART.md
│   ├── API.md
│   └── DEMO.md
└── examples/
    └── demo_home.py         # Demo scenario script
```

---

## Appendix B: Key Metrics to Track

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Routing accuracy | >95% | Test suite with labeled intents |
| Gossip convergence | <5 rounds | Log round count to full sync |
| Routing latency | <50ms local, <200ms remote | Time from intent to route decision |
| Token verification | <5ms | Benchmark offline verify |
| Agent wake time | <100ms | Time from intent match to executing |
| Sleeping agent memory | <1MB | RSS measurement |

---

*This document is the source of truth for Atmosphere MVP scope. When in doubt, cut scope to meet the 4-week timeline.*
