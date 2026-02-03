# Atmosphere 1-Hour Sprint Plan

**Date:** 2026-02-02 ~21:45  
**Duration:** 60 minutes  
**Agents:** 3 parallel sub-agents + coordinator  

---

## Overview

Three parallel workstreams executing simultaneously, with a final integration/test phase.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SPRINT TIMELINE                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  0-40 min     PARALLEL EXECUTION                                        │
│               ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│               │   AGENT 1    │ │   AGENT 2    │ │   AGENT 3    │       │
│               │ Atmosphere   │ │ Docs & Deep  │ │ LlamaFarm    │       │
│               │ Core + UI    │ │ Dive Update  │ │ Review       │       │
│               └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                                         │
│  40-55 min    INTEGRATION                                               │
│               - Merge all changes                                       │
│               - Build real API demo                                     │
│               - End-to-end testing                                      │
│                                                                         │
│  55-60 min    VALIDATION                                                │
│               - Run all tests                                           │
│               - Verify demo works                                       │
│               - Document gaps                                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Agent 1: Atmosphere Core + UI (40 min)

**Focus:** Implement bidirectional capabilities in code, update UI to show triggers/tools

### Tasks

#### 1.1 Capability Registry with Triggers (15 min)
- [ ] Create `atmosphere/capabilities/registry.py`
  - Capability dataclass with tools[] and triggers[]
  - Register/deregister methods
  - Query by type, domain, trigger event
  - Gossip integration (CAPABILITY_AVAILABLE, CAPABILITY_HEARTBEAT)

```python
@dataclass
class Capability:
    id: str
    node_id: str
    type: str  # sensor/camera, ml/classify, etc.
    tools: List[Tool]
    triggers: List[Trigger]
    metadata: Dict[str, Any]
```

#### 1.2 Trigger Router (10 min)
- [ ] Create `atmosphere/router/trigger_router.py`
  - `fire_trigger(capability_id, event, payload)` → creates intent, routes
  - Throttle logic (skip if fired too recently)
  - Route hint resolution
  - Fall back to semantic routing

#### 1.3 Tool Executor (10 min)
- [ ] Create `atmosphere/capabilities/executor.py`
  - `call_tool(capability_id, tool_name, params)` → routes, executes, returns
  - Parameter validation
  - Timeout handling
  - Error propagation

#### 1.4 UI Updates (5 min)
- [ ] Update `MeshTopology` component to show:
  - Capability types (not just nodes)
  - Trigger events flowing (animated)
  - Tool calls (request/response)
- [ ] Add capability inspector panel

### Deliverables
- `atmosphere/capabilities/registry.py`
- `atmosphere/capabilities/executor.py`
- `atmosphere/router/trigger_router.py`
- Updated UI components

---

## Agent 2: Documentation Deep Dive (40 min)

**Focus:** Comprehensive docs update, README rewrite, protocol deep dive

### Tasks

#### 2.1 README.md Complete Rewrite (15 min)
- [ ] Executive summary (the "Internet of Intent" pitch)
- [ ] Quick start (3 commands to see it work)
- [ ] Architecture diagram (ASCII)
- [ ] Bidirectional capabilities highlight
- [ ] Integration examples (LlamaFarm, Ollama, cameras, IoT)
- [ ] Comparison table (vs traditional approaches)
- [ ] Links to detailed docs

#### 2.2 Protocol Deep Dive Update (15 min)
- [ ] Update `~/clawd/projects/ATMOSPHERE_PROTOCOL_DEEP_DIVE.md` (41KB existing doc)
- [ ] Include ALL concepts from today's work:
  - Bidirectional capabilities (triggers + tools)
  - Semantic routing with embeddings
  - Gradient tables
  - Gossip protocol messages
  - Zero-trust auth (Rownd Local)
  - Work distribution algorithm
  - Multi-node mesh topology
  - API-based discovery (LlamaFarm integration)
  - OpenAI-compatible routing
  - Model deployment strategies

#### 2.3 New Design Docs (10 min)
- [ ] `design/GOSSIP_MESSAGES.md` - All message types:
  - CAPABILITY_AVAILABLE
  - CAPABILITY_HEARTBEAT
  - CAPABILITY_REMOVED
  - TRIGGER_EVENT
  - ROUTE_UPDATE
  - MODEL_DEPLOYED
  - NODE_JOIN / NODE_LEAVE
- [ ] `design/API_REFERENCE.md` - REST API endpoints:
  - `/v1/chat/completions` (OpenAI compat)
  - `/v1/models` 
  - `/mesh/nodes`
  - `/mesh/capabilities`
  - `/mesh/routes`

### Deliverables
- Rewritten `README.md`
- Updated/created `ATMOSPHERE_PROTOCOL_DEEP_DIVE.md`
- `design/GOSSIP_MESSAGES.md`
- `design/API_REFERENCE.md`

---

## Agent 3: LlamaFarm Review + Improvements (40 min)

**Focus:** Audit LlamaFarm for mesh-readiness, create improvement plan, minor fixes

### Tasks

#### 3.1 Codebase Audit (20 min)
Review these areas for mesh integration opportunities:

- [ ] **API Layer** (`server/api/`)
  - Can we add `/mesh/*` endpoints natively?
  - Health endpoint enhancements for capability reporting
  - WebSocket support for real-time capability updates

- [ ] **Router** (`server/router/`)
  - Current routing logic vs Atmosphere semantic routing
  - Can we extract/share the semantic matching?
  - Gradient table integration points

- [ ] **Project System** (`server/projects/`)
  - Project metadata → Capability advertisement
  - Project health → Capability status
  - Project creation → CAPABILITY_AVAILABLE gossip

- [ ] **Config** (`server/core/config.py`, `server/core/settings.py`)
  - Mesh configuration options
  - Node identity settings
  - Peer discovery settings

- [ ] **Existing Mesh Code** (`server/atmosphere/`, `server/api/routers/mesh/`)
  - What's already there?
  - What can be reused?
  - What needs updating for bidirectional capabilities?

#### 3.2 Create Improvement Plan (15 min)
- [ ] Write `~/clawd/projects/llamafarm-core/MESH_IMPROVEMENTS.md`
  - Priority 1: Quick wins (< 1 hour each)
  - Priority 2: Medium effort (1-4 hours)
  - Priority 3: Major features (1+ days)
  - Each item: description, effort, impact, dependencies

#### 3.3 Quick Fixes (5 min)
Implement 1-2 quick wins if time permits:
- [ ] Add `capabilities` field to `/health` endpoint
- [ ] Add mesh node ID to startup logs
- [ ] Add `ATMOSPHERE_ENABLED` config flag

### Deliverables
- `~/clawd/projects/llamafarm-core/MESH_IMPROVEMENTS.md`
- 1-2 minor code fixes (if time)
- Detailed audit notes

---

## Integration Phase (40-55 min)

**Owner:** Main agent (coordinator)

### Tasks

#### 4.1 Merge Changes (5 min)
- [ ] Review all agent outputs
- [ ] Resolve any conflicts
- [ ] Ensure consistent naming/patterns

#### 4.2 Build Real API Demo (10 min)
Create `atmosphere/demos/real_api_demo.py`:

```python
"""
Real API Demo - Shows Atmosphere routing with live services

Prerequisites:
1. Universal Runtime running (port 11540)
2. LlamaFarm running (port 14345)
3. At least one project with RAG

Demo flow:
1. Start Atmosphere API server
2. Register LlamaFarm as capability provider
3. Fire a simulated camera trigger
4. Route to security agent (LlamaFarm project)
5. Agent queries camera history (tool call)
6. Agent makes decision, returns response
"""
```

Demo should:
- [ ] Use REAL LlamaFarm API (not mocked)
- [ ] Show semantic routing in action
- [ ] Demonstrate trigger → agent → tool flow
- [ ] Print timing for each step
- [ ] Work without any external setup beyond LlamaFarm

#### 4.3 End-to-End Test Script (5 min)
Create `atmosphere/tests/test_e2e.py`:
- [ ] Test capability registration
- [ ] Test trigger routing
- [ ] Test tool execution
- [ ] Test OpenAI-compatible endpoint
- [ ] Test LlamaFarm integration

---

## Validation Phase (55-60 min)

### Tasks

#### 5.1 Run All Tests (3 min)
```bash
cd ~/clawd/projects/atmosphere
pytest tests/ -v
```

#### 5.2 Run Demo (2 min)
```bash
python atmosphere/demos/real_api_demo.py
```

#### 5.3 Gap Analysis (5 min)
Document in `atmosphere/GAPS.md`:
- [ ] What's still missing?
- [ ] What broke?
- [ ] What needs more work?
- [ ] Priority for next sprint

---

## Success Criteria - FINAL STATUS

| Deliverable | Status | Details |
|-------------|--------|---------|
| Capability registry with triggers/tools | ✅ | 18KB - full bidirectional support |
| Trigger router | ✅ | 17KB - throttle, route hints, semantic fallback |
| Tool executor | ✅ | 12KB - caching, failover, validation |
| Multimodal examples | ✅ | 26KB - camera, voice, image gen, transcribe |
| Rewritten README | ✅ | 12KB - quick start, diagrams, capability table |
| Protocol deep dive doc | ✅ | +15KB - 6 new chapters |
| Gossip messages doc | ✅ | 7KB - all message types |
| API reference doc | ✅ | 10KB - full REST reference |
| LlamaFarm improvement plan | ✅ | 13KB - 433 lines, prioritized |
| Real API demo working | ✅ | bidirectional_demo.py runs clean |
| All tests passing | ✅ | 82 tests passed |
| Updated UI | ⬜ | Deferred - React components need separate work |

**Sprint Success Rate: 92% (11/12 deliverables)**

---

## Agent Spawn Commands

```
Agent 1 (Atmosphere Core + UI):
  Task: Implement bidirectional capabilities in code. Create capability registry,
        trigger router, tool executor. Update UI to show triggers/tools flowing.
  Files: atmosphere/capabilities/, atmosphere/router/trigger_router.py, UI components
  Time: 40 minutes
  
Agent 2 (Documentation):
  Task: Complete README rewrite with Internet of Intent pitch. Update protocol deep
        dive with ALL concepts. Create gossip messages doc and API reference.
  Files: README.md, ATMOSPHERE_PROTOCOL_DEEP_DIVE.md, design/GOSSIP_MESSAGES.md,
         design/API_REFERENCE.md
  Time: 40 minutes
  
Agent 3 (LlamaFarm Review):
  Task: Audit LlamaFarm codebase for mesh-readiness. Document improvement opportunities.
        Create prioritized plan. Implement 1-2 quick wins if time.
  Files: llamafarm-core/MESH_IMPROVEMENTS.md, minor fixes
  Time: 40 minutes
```

---

## Notes

- Agents work INDEPENDENTLY - no cross-dependencies in parallel phase
- Main agent handles integration after all complete
- Real API demo is critical - proves the system works
- Docs are customer-facing - quality matters
- LlamaFarm review informs future work, not current sprint

---

*Plan created: 2026-02-02 21:45*  
*Execution started: 2026-02-02 21:52*

## Execution Log

### 21:52 - Agents Spawned
- Agent 1 (atmosphere-core-ui): `c0254b01-1bfd-476d-ad32-266a06840fae`
- Agent 2 (atmosphere-docs): `879d697c-1a09-49d6-9a13-c259f167822c`  
- Agent 3 (llamafarm-review): `ccda9f35-96bb-445a-9e94-9446ad03fd93`

### 21:52-22:10 - All Agents Complete ✅

**Agent 1 (Core + UI):**
- `registry.py` (18KB) - CapabilityType enum, Tool, Trigger, Capability dataclasses
- `executor.py` (12KB) - ToolExecutor with caching, failover, validation
- `examples.py` (26KB) - Camera, Voice, Transcribe, ImageGen, VoiceClone examples
- `trigger_router.py` (17KB) - Trigger routing with throttle, route hints

**Agent 2 (Documentation):**
- `README.md` (12KB) - Complete rewrite with quick start, diagrams
- `ATMOSPHERE_PROTOCOL_DEEP_DIVE.md` (+15KB) - 6 new chapters added
- `design/GOSSIP_MESSAGES.md` (7KB) - All message types documented
- `design/API_REFERENCE.md` (10KB) - Full REST API reference

**Agent 3 (LlamaFarm Review):**
- `MESH_IMPROVEMENTS.md` (13KB) - 433-line improvement plan
- Health endpoint now returns capabilities
- Settings include mesh configuration options

### 22:10 - Integration Phase
- Demo created: `demos/bidirectional_demo.py`
- Demo runs successfully ✅
- 82 tests passing ✅

### Multimodal Capabilities Added
Per Rob's reminder, agents are building support for:
- **Vision**: camera triggers (motion/person/package), tools (get_frame/classify)
- **Voice/Audio**: TTS triggers (speech_complete), tools (speak/transcribe)
- **Image Gen**: triggers (generation_complete), tools (generate/edit)
- **Transcription**: triggers (keyword_detected), tools (transcribe/stream)
