# Session Mesh: Distributed Session Management for Atmosphere

> Sessions follow intents across the mesh. Context persists even when work moves.

## The Problem

Current state:
- User starts conversation with Node A
- Intent routes to Node B (has the right capability)
- Node B has NO context — who is this? what happened before?
- Result: broken experience, repeated auth, lost state

## Design Principles

### 1. Sessions Are First-Class Mesh Citizens

Like agents and tools, sessions get gossiped. Every node in the mesh knows about active sessions (metadata only, not full state).

```
Session = Identity + Context + Routing Hints + Security Envelope
```

### 2. Context Follows Work (Not Data)

We don't replicate full conversation history everywhere. Instead:
- **Session Token**: Lightweight proof of session membership
- **Context Window**: Last N turns (configurable per session type)
- **Artifact References**: Pointers to stored artifacts (not the artifacts themselves)

### 3. Session Affinity with Graceful Migration

Sessions prefer to stay on one node (cache locality, state consistency) but can migrate when:
- Original node goes offline
- Capability required isn't available locally
- Load balancing triggers migration

---

## Architecture

### Session Identity

```
┌─────────────────────────────────────────────────────────────────┐
│                        MeshSession                              │
├─────────────────────────────────────────────────────────────────┤
│  session_id:    "sess-abc123def456"                             │
│  mesh_id:       "mesh-production-01"                            │
│  user_id:       "user-rob" (optional, federated)                │
│  created_at:    1738531200                                      │
│  last_active:   1738534800                                      │
│  ttl:           3600 (seconds until expiry)                     │
│  origin_node:   "edge-mac-01" (where session started)           │
│  current_node:  "edge-jetson-02" (where session is now)         │
│  affinity:      "soft" | "hard" | "none"                        │
│  capabilities:  ["vision", "llm"] (what this session needs)     │
│  security:      SessionSecurity (tokens, permissions)           │
└─────────────────────────────────────────────────────────────────┘
```

### Session Context (Portable State)

```
┌─────────────────────────────────────────────────────────────────┐
│                     SessionContext                              │
├─────────────────────────────────────────────────────────────────┤
│  messages:      [Message] (last N, compressed)                  │
│  variables:     {key: value} (accumulated state)                │
│  artifacts:     [ArtifactRef] (pointers, not data)              │
│  agent_state:   {agent_id: state} (per-agent scratch)           │
│  routing_hints: {capability: preferred_node}                    │
│  version:       42 (monotonic, for conflict resolution)         │
└─────────────────────────────────────────────────────────────────┘
```

### Session Security Envelope

```python
@dataclass
class SessionSecurity:
    """Cryptographic session protection."""
    
    # Session token (signed by origin node)
    token: str
    token_signature: str
    
    # What this session is allowed to do
    allowed_capabilities: List[str]
    allowed_nodes: List[str]  # Empty = any node
    max_escalation_tier: str  # "iot", "edge", "cloud"
    
    # Federation (if session crosses mesh boundaries)
    federation_token: Optional[str]
    parent_mesh_id: Optional[str]
    
    # User identity (if authenticated)
    user_principal: Optional[str]
    user_signature: Optional[str]
```

---

## Session Lifecycle

### 1. Session Creation

```
User → Node A: "Analyze this image"
Node A:
  1. Generate session_id
  2. Create SessionContext (empty)
  3. Sign session token
  4. Gossip session announcement
  5. Begin processing
```

### 2. Session Migration (Soft)

```
Node A → Intent Router: "Need vision capability"
Intent Router: "Node B is best for vision"
Node A → Node B: 
  {
    "type": "session_migrate",
    "session": MeshSession,
    "context": SessionContext,
    "intent": Intent,
    "signature": "..."
  }
Node B:
  1. Verify session token
  2. Accept context
  3. Continue processing
  4. Gossip updated current_node
```

### 3. Session Fork (Parallel Work)

```
Intent requires multiple capabilities → Fork session into sub-sessions
Parent Session: "sess-abc123"
  ├── Child: "sess-abc123:vision-01" → Node B (vision)
  ├── Child: "sess-abc123:llm-01" → Node C (LLM)
  └── Child: "sess-abc123:search-01" → Node D (RAG)

Results merge back to parent session on completion.
```

### 4. Session Resume (Reconnection)

```
User reconnects after disconnect:
  1. Presents session_id + user token
  2. Any node can verify via gossip registry
  3. Fetch context from last known current_node (or artifact store)
  4. Resume from last checkpoint
```

### 5. Session Expiry

```
TTL expires OR explicit close:
  1. Gossip session tombstone
  2. Persist final context to artifact store (if configured)
  3. Clean up local state
  4. Session ID enters graveyard (prevent replay)
```

---

## Gossip Protocol Extension

### Session Announcements

Sessions get their own gossip channel (low frequency, small payloads):

```python
@dataclass
class SessionGossip:
    """Lightweight session state for mesh awareness."""
    
    session_id: str
    mesh_id: str
    origin_node: str
    current_node: str
    last_active: int
    ttl: int
    capabilities_needed: List[str]
    state: str  # "active", "migrating", "paused", "closed"
    version: int
```

### Gossip Frequency

- **Session create/close**: Immediate gossip
- **Session active**: Every 60s heartbeat (only if still active)
- **Session migrate**: Immediate gossip (both old and new node)
- **Session update**: Piggyback on heartbeat (unless urgent)

---

## Context Transfer Protocol

### Small Context (< 10KB)

Inline in migration message:

```json
{
  "type": "session_migrate",
  "session_id": "sess-abc123",
  "context": {
    "messages": [...],
    "variables": {...},
    "artifacts": [...]
  }
}
```

### Large Context (> 10KB)

Reference-based transfer:

```json
{
  "type": "session_migrate",
  "session_id": "sess-abc123",
  "context_ref": {
    "store": "artifact-store-01",
    "key": "sessions/sess-abc123/context-v42",
    "hash": "sha256:abc123...",
    "size": 156789
  }
}
```

Receiving node fetches context from artifact store if needed.

### Context Compression

For repeated patterns (common in multi-turn conversations):

```python
def compress_context(context: SessionContext) -> bytes:
    """
    Delta-encode messages against common patterns.
    
    Typical compression: 3-5x for conversational sessions.
    """
    patterns = get_common_patterns()  # Gossiped, shared across mesh
    deltas = []
    for msg in context.messages:
        best_match = find_best_pattern(msg, patterns)
        if best_match and similarity(msg, best_match) > 0.8:
            deltas.append(("delta", best_match.id, diff(best_match, msg)))
        else:
            deltas.append(("full", msg))
    return zstd.compress(msgpack.pack(deltas))
```

---

## Conflict Resolution

### Split-Brain Recovery

If network partition causes session to exist on multiple nodes:

1. **Version wins**: Higher version number is authoritative
2. **Timestamp tiebreaker**: If same version, most recent update wins
3. **Merge if possible**: For append-only state (messages), merge both
4. **Alert if conflict**: For mutable state (variables), alert and prefer origin_node

### Concurrent Updates

Using CRDT-like structures where possible:

```python
class SessionVariables:
    """Last-writer-wins register set with vector clock."""
    
    def __init__(self):
        self._data: Dict[str, Tuple[Any, VectorClock]] = {}
    
    def set(self, key: str, value: Any, node_id: str):
        clock = self._data.get(key, (None, VectorClock()))[1].increment(node_id)
        self._data[key] = (value, clock)
    
    def merge(self, other: "SessionVariables"):
        for key, (value, clock) in other._data.items():
            if key not in self._data:
                self._data[key] = (value, clock)
            else:
                my_value, my_clock = self._data[key]
                if clock > my_clock:
                    self._data[key] = (value, clock)
                elif not (my_clock > clock):
                    # Concurrent: use deterministic tiebreaker
                    self._data[key] = max(
                        [(value, clock), (my_value, my_clock)],
                        key=lambda x: (x[1].sum(), hash(str(x[0])))
                    )
```

---

## Security Model

### Session Hijacking Prevention

1. **Token binding**: Session token includes origin IP hash (optional)
2. **Token rotation**: New token generated on each migration
3. **Signature chain**: Each node signs handoff, creating audit trail
4. **Revocation**: Compromised tokens can be revoked via gossip

### Cross-Mesh Sessions

When session needs to access federated mesh:

```
Local Mesh                      Federated Mesh
┌─────────┐                    ┌─────────┐
│ Node A  │ ───────────────────│ Node X  │
│         │   Federation Link   │         │
│ Session │   + Delegated       │ Session │
│ sess-01 │   Session Token     │ sess-01 │
└─────────┘                    │ :fed-01 │
                               └─────────┘

Session becomes "sess-01:fed-01" in federated mesh.
Parent mesh can revoke delegation at any time.
```

---

## Implementation Phases

### Phase 1: Basic Session Tracking (MVP)

```python
@dataclass
class MeshSession:
    session_id: str
    origin_node: str
    current_node: str
    created_at: float
    last_active: float
    context: Dict[str, Any]  # Simple dict for now

class SessionStore:
    """Local session storage with gossip sync."""
    
    def __init__(self, node_id: str, gossip: GossipProtocol):
        self.node_id = node_id
        self.gossip = gossip
        self.sessions: Dict[str, MeshSession] = {}
    
    async def create(self, capabilities: List[str]) -> MeshSession:
        session = MeshSession(
            session_id=f"sess-{uuid.uuid4().hex[:12]}",
            origin_node=self.node_id,
            current_node=self.node_id,
            created_at=time.time(),
            last_active=time.time(),
            context={}
        )
        self.sessions[session.session_id] = session
        await self.gossip.announce_session(session)
        return session
    
    async def migrate(self, session_id: str, target_node: str) -> bool:
        session = self.sessions.get(session_id)
        if not session or session.current_node != self.node_id:
            return False
        
        # Send to target
        success = await self._send_migration(session, target_node)
        if success:
            session.current_node = target_node
            session.last_active = time.time()
            await self.gossip.announce_session(session)
        return success
```

### Phase 2: Context Management

- Proper SessionContext structure
- Compression for large contexts
- Artifact references
- Context checkpointing

### Phase 3: Security & Federation

- Session tokens with signatures
- Permission scoping
- Cross-mesh federation
- Revocation and audit

### Phase 4: Advanced Features

- Session forking for parallel work
- CRDT-based conflict resolution
- Predictive session pre-positioning
- Session analytics and optimization

---

## API Additions

### Intent Router Extensions

```python
@router.post("/mesh/intent")
async def route_intent(request: IntentRequest):
    # Existing routing logic...
    
    # NEW: Session handling
    if request.session_id:
        session = await session_store.get(request.session_id)
        if session and session.current_node != self.node_id:
            # Session is elsewhere - forward or migrate?
            if should_migrate(session, best_node):
                await session_store.migrate(session.session_id, best_node.id)
    else:
        # Create new session
        session = await session_store.create(required_capabilities)
        
    return IntentResponse(
        session_id=session.session_id,
        routed_to=best_node.id,
        ...
    )
```

### Session Management Endpoints

```python
@router.get("/mesh/sessions")
async def list_sessions():
    """List all sessions this node knows about."""
    pass

@router.get("/mesh/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details and context."""
    pass

@router.post("/mesh/sessions/{session_id}/migrate")
async def migrate_session(session_id: str, target_node: str):
    """Explicitly migrate session to another node."""
    pass

@router.delete("/mesh/sessions/{session_id}")
async def close_session(session_id: str):
    """Close session and clean up."""
    pass
```

---

## Metrics

Track for optimization:
- `session_create_total`: Sessions created
- `session_migrate_total`: Migrations (by reason)
- `session_migrate_latency_ms`: Time to complete migration
- `session_context_bytes`: Context size histogram
- `session_lifetime_seconds`: How long sessions live
- `session_conflict_total`: Split-brain conflicts resolved

---

## Integration with Existing Systems

### Rownd Local Integration

If user has authenticated identity:
```python
session.security.user_principal = rownd_identity.member_id
session.security.user_signature = rownd_identity.sign(session.session_id)
```

### LlamaFarm Integration

Sessions map to LlamaFarm conversation threads:
```python
llamafarm_thread = await llamafarm.create_thread(
    external_id=session.session_id,
    metadata={"mesh_origin": session.origin_node}
)
session.context["llamafarm_thread_id"] = llamafarm_thread.id
```

### Agent Layer Integration

Agents receive session context on invocation:
```python
async def invoke_agent(agent: Agent, intent: Intent, session: MeshSession):
    return await agent.run(
        intent=intent,
        context=session.context,
        session_id=session.session_id,
        on_update=lambda ctx: session_store.update_context(session.session_id, ctx)
    )
```

---

## Summary

Sessions in Atmosphere:
1. **Identity**: Unique ID, gossiped across mesh
2. **Context**: Portable state that follows work
3. **Security**: Signed tokens, capability scoping
4. **Migration**: Seamless handoff between nodes
5. **Federation**: Cross-mesh sessions with delegation

The goal: User doesn't know or care which node is handling their request. Session state is always there.
