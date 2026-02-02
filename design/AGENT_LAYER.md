# Agent Layer Design for Atmosphere

**Version:** 0.1 (Draft)  
**Status:** Design Phase  
**Author:** Claude (subagent)  
**Date:** 2025-02-02

---

## Executive Summary

This document defines how **agents** work in Atmosphere's Internet of Intent. Agents are autonomous units of computation that can perceive, decide, and act within the mesh network. They build upon the existing capability and intent routing systems while adding lifecycle management, hierarchical delegation, and distributed coordination.

---

## 1. What IS an Agent?

### Definition

An **agent** is a stateful entity that:
1. **Receives intents** or events
2. **Makes decisions** about how to fulfill them
3. **Takes actions** (which may include spawning sub-agents or creating new intents)
4. **Reports results** to its parent or originator

Unlike a **capability** (which is a stateless function that executes and returns), an agent has:
- **Lifecycle** - It exists over time, can be idle or active
- **Context** - It maintains state between invocations
- **Autonomy** - It can make decisions, not just execute instructions
- **Delegation** - It can spawn child agents and wait for results

### The Agent Spectrum

Agents exist on a spectrum from minimal to maximal:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        THE AGENT SPECTRUM                                │
├────────────────┬───────────────────┬───────────────────┬────────────────┤
│    REACTIVE    │    DELIBERATIVE   │    ORCHESTRATOR   │    COGNITIVE   │
│   (Minimal)    │    (Standard)     │    (Complex)      │    (Full)      │
├────────────────┼───────────────────┼───────────────────┼────────────────┤
│ ESP32          │ Raspberry Pi      │ Edge Server       │ Cloud/GPU      │
│ ~50 KB RAM     │ ~512 MB RAM       │ ~4 GB RAM         │ ~16+ GB RAM    │
├────────────────┼───────────────────┼───────────────────┼────────────────┤
│ Event→Action   │ Event→Plan→Action │ Orchestrate       │ Reason, Learn  │
│ No state       │ Simple state      │ Complex state     │ Full context   │
│ No planning    │ Rule-based        │ Goal-driven       │ LLM-powered    │
│ No delegation  │ Fixed delegation  │ Dynamic spawn     │ Meta-reasoning │
└────────────────┴───────────────────┴───────────────────┴────────────────┘
```

### Agent vs Capability

| Aspect | Capability | Agent |
|--------|------------|-------|
| Lifecycle | Stateless function call | Persistent entity |
| Invocation | Request → Response | Start, interact, stop |
| State | None (or session-only) | Maintained across calls |
| Delegation | None | Can spawn children |
| Decision-making | None (pure execution) | Makes choices |
| Resource cost | Per-invocation | Ongoing (even if idle) |

**Key insight**: An agent *uses* capabilities but is not a capability. An agent might invoke the `llm` capability to reason, or the `vision` capability to see.

---

## 2. Agent Types

### 2.1 Reactive Agent (Minimal)

The smallest possible agent. Runs on ESP32, ATmega, or similar constrained devices.

**Characteristics:**
- Condition → Action rules only
- No persistent memory between events
- Cannot delegate to children
- Cannot use LLMs

**Example:** Vibration threshold agent
```
IF vibration > threshold THEN emit("anomaly_detected", {level: vibration})
```

**Use cases:**
- Sensor threshold monitoring
- Simple automation rules
- Edge filtering/aggregation

### 2.2 Deliberative Agent (Standard)

Has state and can follow multi-step plans.

**Characteristics:**
- Maintains context/state
- Can execute sequential steps
- Rule-based planning (if-then-else trees)
- Can delegate to other agents (fixed patterns)

**Example:** Data collection agent
```
STATE: samples = []
ON event("collect"):
  sample = read_sensor()
  samples.append(sample)
  IF len(samples) >= 10:
    delegate("aggregator", {"data": samples})
    samples = []
```

### 2.3 Orchestrator Agent (Complex)

Manages workflows and coordinates multiple agents.

**Characteristics:**
- Goal-oriented behavior
- Dynamic agent spawning
- Parallel coordination
- Error handling and retry logic

**Example:** Anomaly investigation orchestrator
```
ON intent("investigate_anomaly"):
  data_agent = spawn("data_collector", target=sensors)
  context_agent = spawn("context_gatherer", target=logs)
  
  await all([data_agent, context_agent])
  
  diagnosis = delegate("diagnostic_agent", {
    sensor_data: data_agent.result,
    context: context_agent.result
  })
  
  return diagnosis
```

### 2.4 Cognitive Agent (Full)

LLM-powered agent with full reasoning capabilities.

**Characteristics:**
- Natural language understanding
- Chain-of-thought reasoning
- Tool use (capabilities as tools)
- Learning from feedback
- Meta-level planning

**Example:** Research agent
```
ON intent("research competitor pricing"):
  # LLM reasons about the task
  plan = reason("""
    To research competitor pricing I need to:
    1. Identify which competitors to check
    2. Find agents with web access
    3. Gather pricing data
    4. Synthesize findings
  """)
  
  # Execute plan with tool use
  for step in plan.steps:
    result = await execute_step(step)
    plan = replan_if_needed(plan, result)
  
  return synthesize(all_results)
```

---

## 3. Agent Anatomy

### 3.1 Minimal Agent Structure

Every agent, from ESP32 to Claude, must have:

```python
@dataclass
class AgentCore:
    # === REQUIRED ===
    id: str                    # Unique identifier (UUID or hash)
    type: str                  # Agent type identifier
    node_id: str               # Host node
    
    # === LIFECYCLE ===
    state: AgentState          # created | running | suspended | terminated
    parent_id: Optional[str]   # Who spawned this agent (None for root)
    
    # === COMMUNICATION ===
    inbox: MessageQueue        # Incoming messages/intents
    capabilities: List[str]    # What this agent can do
```

### 3.2 Full Agent Structure (Extensions)

```python
@dataclass
class FullAgent(AgentCore):
    # === STATE ===
    context: Dict[str, Any]    # Agent's working memory
    goals: List[Goal]          # What it's trying to achieve
    
    # === DELEGATION ===
    children: Dict[str, str]   # child_id -> status
    pending_results: Dict      # Awaited child results
    
    # === REASONING ===
    reasoning_backend: str     # "rules" | "llm" | "hybrid"
    model: Optional[str]       # LLM model if applicable
    
    # === RESOURCE LIMITS ===
    max_children: int          # Spawn limit
    timeout_ms: int            # Max lifetime
    memory_limit_kb: int       # Context size limit
```

### 3.3 Agent Message Format

All agent communication uses a standard envelope:

```python
@dataclass
class AgentMessage:
    # === ROUTING ===
    id: str                    # Message ID
    from_agent: str            # Source agent ID
    to_agent: str              # Target agent ID (or "*" for broadcast)
    via_node: Optional[str]    # If cross-node, which node
    
    # === CONTENT ===
    type: MessageType          # intent | result | event | control
    payload: Dict[str, Any]    # Type-specific content
    
    # === METADATA ===
    timestamp: int             # Unix ms
    ttl_hops: int              # Max hops before discard
    priority: int              # 0-9 (higher = more urgent)
    
    # === SECURITY ===
    signature: str             # Ed25519 signature
```

**Message Types:**

| Type | Description | Payload |
|------|-------------|---------|
| `intent` | Request agent to do something | `{intent: str, args: dict}` |
| `result` | Response to an intent | `{status: str, data: any, error?: str}` |
| `event` | Notification (no response expected) | `{event: str, data: dict}` |
| `control` | Lifecycle commands | `{command: "suspend"|"resume"|"terminate"}` |

---

## 4. Agent Lifecycle

### 4.1 State Machine

```
                    ┌──────────────────────────────────┐
                    │                                  │
                    │         ┌──────────┐             │
         spawn()    │    ┌───→│ RUNNING  │←───┐       │ resume()
            │       │    │    └────┬─────┘    │       │
            ▼       │    │         │          │       │
       ┌────────┐   │    │         │suspend() │       │
       │CREATED │───┘    │         ▼          │       │
       └────────┘        │    ┌──────────┐    │       │
                         │    │SUSPENDED │────┘       │
                         │    └────┬─────┘            │
                         │         │                  │
                         │         │terminate()       │
                         │         │                  │
                         │         ▼                  │
                         │   ┌────────────┐           │
                         └──→│ TERMINATED │←──────────┘
                             └────────────┘
                                   │
                                   │ cleanup
                                   ▼
                               [garbage collected]
```

### 4.2 Lifecycle Operations

**Spawning an Agent:**

```python
async def spawn_agent(
    agent_type: str,
    parent_id: Optional[str] = None,
    initial_intent: Optional[str] = None,
    target_node: Optional[str] = None,  # None = local
    config: Optional[Dict] = None
) -> str:  # Returns agent_id
    """
    Create and start a new agent.
    
    1. Generate agent ID
    2. Find or negotiate hosting node
    3. Instantiate agent from type registry
    4. Send initial intent (if provided)
    5. Return agent ID for tracking
    """
```

**Who Can Spawn:**
- **Any agent** can spawn child agents (within resource limits)
- **The mesh** can spawn root agents (user-initiated or event-triggered)
- **Capabilities** can request agent spawning (e.g., capability suggests "this needs an agent")

**Agent Termination:**

Agents terminate when:
1. **Task complete** - Agent decides it's done, calls `self.terminate(result)`
2. **Parent terminates** - Cascade termination to children (configurable)
3. **Timeout** - Exceeded `timeout_ms`
4. **Resource limit** - Exceeded memory/children limits
5. **Explicit kill** - Control message from parent or mesh admin
6. **Error** - Unrecoverable error

```python
async def terminate_agent(
    agent_id: str,
    reason: str,
    cascade: bool = True,  # Terminate children?
    force: bool = False    # Skip graceful shutdown?
) -> TerminationResult:
    """
    Terminate an agent and optionally its children.
    """
```

### 4.3 Parent-Child Relationship

```
ROOT AGENT (user-spawned)
│
├── CHILD A (data collection)
│   ├── GRANDCHILD A1 (sensor 1)
│   └── GRANDCHILD A2 (sensor 2)
│
└── CHILD B (analysis)
    └── GRANDCHILD B1 (LLM reasoning)
```

**Rules:**
1. Children know their parent (`parent_id`)
2. Parents track their children (`children` dict)
3. Results flow upward (child → parent)
4. Termination cascades downward by default
5. Orphaned agents (parent died) get adopted by mesh root or terminate

---

## 5. Agent Communication

### 5.1 Intra-Node Communication

Agents on the same node use direct message passing:

```python
# Same node - direct queue access
async def send_local(message: AgentMessage):
    target_agent = agent_registry.get(message.to_agent)
    await target_agent.inbox.put(message)
```

**Performance:** Microseconds, zero serialization for simple types.

### 5.2 Cross-Node Communication

Agents on different nodes use the mesh transport:

```python
# Cross-node - serialize and route
async def send_remote(message: AgentMessage, target_node: str):
    # 1. Serialize message
    wire_format = serialize(message)
    
    # 2. Sign with node key
    wire_format.signature = node.identity.sign(wire_format.payload)
    
    # 3. Route through mesh
    route_result = await router.route_message(wire_format, target_node)
    
    # 4. Delivery confirmation (or error)
    return route_result
```

**Performance:** Milliseconds, depends on hops.

### 5.3 Intent-Based Communication

Agents can communicate via intents (letting the mesh route):

```python
# Let the mesh find the right agent
async def broadcast_intent(intent: str, args: dict) -> str:
    """
    Send an intent without knowing the target agent.
    The mesh routes to the best available agent.
    Returns request_id for tracking.
    """
    message = AgentMessage(
        type=MessageType.INTENT,
        to_agent="*",  # Broadcast
        payload={"intent": intent, "args": args}
    )
    return await mesh.route_intent(message)
```

### 5.4 Delegation Pattern

Parent agent delegating to a child:

```python
class OrchestratorAgent(Agent):
    async def handle_intent(self, intent: str, args: dict):
        if intent == "investigate_anomaly":
            # Spawn child for data collection
            collector_id = await self.spawn_child(
                agent_type="data_collector",
                initial_intent="collect_sensor_data",
                args={"sensors": args["sensor_ids"]}
            )
            
            # Wait for result (with timeout)
            result = await self.await_child(collector_id, timeout_ms=30000)
            
            if result.status == "success":
                # Continue with analysis
                return await self.analyze(result.data)
            else:
                # Handle failure
                return self.escalate(result.error)
```

---

## 6. Agent Discovery

### 6.1 Agent Registration

When an agent starts, it registers with the mesh:

```python
@dataclass
class AgentRegistration:
    agent_id: str
    agent_type: str
    node_id: str
    capabilities: List[str]      # What can this agent do?
    intents: List[str]           # What intents does it handle?
    intent_embeddings: List[np.ndarray]  # For semantic matching
    resource_profile: ResourceProfile    # Cost/performance hints
```

### 6.2 Discovery Mechanisms

**Option A: Agent Registry (Centralized-ish)**
```python
# Global registry replicated across mesh
agent_registry = {
    "agent-123": AgentRegistration(...),
    "agent-456": AgentRegistration(...),
}

# Find agents that can handle an intent
def find_agents(intent: str) -> List[AgentRegistration]:
    intent_vec = embed(intent)
    return rank_by_similarity(agent_registry.values(), intent_vec)
```

**Option B: Gossip-Based Discovery (Decentralized)**
```python
# Each node maintains a partial view
# Gossip protocol propagates registrations

async def on_gossip_receive(registrations: List[AgentRegistration]):
    for reg in registrations:
        if reg.timestamp > local_registry.get(reg.agent_id).timestamp:
            local_registry[reg.agent_id] = reg
            # Re-gossip to neighbors
            await gossip_to_peers(reg)
```

**Option C: Capability-Based Discovery (Hybrid)**

Treat agent types as special capabilities. Use existing semantic routing:

```python
# Register agent type as capability
router.register_capability(
    label="agent:anomaly_investigator",
    description="Agent that investigates sensor anomalies, gathers data, runs diagnostics",
    handler="spawn_anomaly_investigator"
)

# Intent routing finds it
result = await router.route("investigate this vibration anomaly")
# result.capability = "agent:anomaly_investigator"
# result.handler calls spawn_anomaly_investigator()
```

**Recommendation:** Option C (Capability-Based) for MVP. Agents register as capabilities, reusing existing routing infrastructure. Extend to gossip-based for scale later.

### 6.3 Agent Types vs Agent Instances

**Agent Type**: Template/class (e.g., "anomaly_investigator")  
**Agent Instance**: Running entity (e.g., "agent-abc123")

```
Agent Type: "research_agent"
│
├── Instance: "research-001" (running, investigating pricing)
├── Instance: "research-002" (running, investigating competitors)
└── Instance: "research-003" (suspended, waiting for data)
```

Discovery can find either:
- "Find an agent that can research" → finds the type, spawns new instance
- "Check on research-001" → finds the specific instance

---

## 7. Integration with Intent System

### 7.1 How Intents Become Agents

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTENT                               │
│            "investigate the vibration anomaly"                   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SEMANTIC ROUTER                              │
│    Embed intent → Match capabilities → Route decision            │
└─────────────────────────────┬───────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   ┌─────────┐          ┌─────────┐           ┌─────────┐
   │CAPABILITY│          │ AGENT   │           │NO MATCH │
   │(stateless)│         │(stateful)│          │         │
   └────┬────┘          └────┬────┘           └─────────┘
        │                    │
        ▼                    ▼
   Execute &            Spawn agent
   return result        Agent handles intent
                        May spawn children
                        Returns result when done
```

### 7.2 Agent as Capability Handler

```python
class AgentCapabilityHandler(CapabilityHandler):
    """Wraps an agent type as a capability."""
    
    def __init__(self, agent_type: str, description: str):
        self._agent_type = agent_type
        self._description = description
    
    @property
    def capability_type(self) -> str:
        return f"agent:{self._agent_type}"
    
    @property
    def description(self) -> str:
        return self._description
    
    async def execute(self, **kwargs) -> Any:
        # Spawn agent and wait for completion
        agent_id = await spawn_agent(
            agent_type=self._agent_type,
            initial_intent=kwargs.get("intent"),
            config=kwargs
        )
        
        # Wait for result (with timeout)
        result = await agent_manager.await_result(
            agent_id, 
            timeout_ms=kwargs.get("timeout_ms", 60000)
        )
        
        return result
```

### 7.3 Agents Creating Intents

Agents can emit intents that get routed through the mesh:

```python
class ResearchAgent(Agent):
    async def run(self):
        # Agent creates an intent for the mesh to route
        weather_data = await self.emit_intent(
            "get weather forecast for location",
            {"location": "Chicago", "days": 7}
        )
        
        # Mesh routes this to a weather capability/agent
        # Result comes back to this agent
        
        return self.synthesize(weather_data)
```

---

## 8. Code Sketches

### 8.1 Minimal Agent (ESP32/Embedded)

```c
// Minimal agent in C for embedded systems
// ~2KB code, ~500B RAM

typedef struct {
    uint8_t id[16];           // UUID
    uint8_t type;             // Agent type enum
    uint8_t state;            // RUNNING | SUSPENDED | TERMINATED
    void (*handler)(uint8_t* msg, uint16_t len);
} MinimalAgent;

typedef struct {
    uint8_t type;             // MESSAGE_INTENT | MESSAGE_EVENT
    uint8_t payload_len;
    uint8_t payload[64];      // Fixed max payload
} MinimalMessage;

// The entire agent runtime
void agent_loop(MinimalAgent* agent) {
    MinimalMessage msg;
    while (agent->state == RUNNING) {
        if (queue_receive(&msg, 100)) {  // 100ms timeout
            agent->handler(msg.payload, msg.payload_len);
        }
    }
}

// Example: vibration threshold agent
void vibration_handler(uint8_t* payload, uint16_t len) {
    float vibration = *(float*)payload;
    if (vibration > THRESHOLD) {
        MinimalMessage alert = {
            .type = MESSAGE_EVENT,
            .payload_len = sizeof(float),
        };
        memcpy(alert.payload, &vibration, sizeof(float));
        mesh_send(&alert, PARENT_NODE);
    }
}
```

### 8.2 Standard Agent (Python)

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import asyncio

class AgentState(Enum):
    CREATED = "created"
    RUNNING = "running"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"

@dataclass
class Agent:
    """Standard Python agent implementation."""
    
    id: str
    type: str
    node_id: str
    parent_id: Optional[str] = None
    state: AgentState = AgentState.CREATED
    
    # Internal
    context: Dict[str, Any] = field(default_factory=dict)
    children: Dict[str, str] = field(default_factory=dict)
    _inbox: asyncio.Queue = field(default_factory=asyncio.Queue)
    
    async def start(self):
        """Start the agent's main loop."""
        self.state = AgentState.RUNNING
        try:
            await self.on_start()
            while self.state == AgentState.RUNNING:
                message = await asyncio.wait_for(
                    self._inbox.get(),
                    timeout=1.0  # Heartbeat interval
                )
                await self._handle_message(message)
        except asyncio.TimeoutError:
            pass  # Heartbeat, check state
        except Exception as e:
            await self.on_error(e)
        finally:
            await self.on_stop()
    
    async def _handle_message(self, message: 'AgentMessage'):
        """Route message to appropriate handler."""
        if message.type == MessageType.INTENT:
            result = await self.handle_intent(
                message.payload["intent"],
                message.payload.get("args", {})
            )
            await self._send_result(message.from_agent, result)
        
        elif message.type == MessageType.RESULT:
            # Child result
            child_id = message.from_agent
            if child_id in self.children:
                await self.on_child_result(child_id, message.payload)
        
        elif message.type == MessageType.CONTROL:
            await self._handle_control(message.payload["command"])
    
    # Override these in subclasses
    async def on_start(self):
        """Called when agent starts."""
        pass
    
    async def on_stop(self):
        """Called when agent stops."""
        pass
    
    async def on_error(self, error: Exception):
        """Called on unhandled error."""
        pass
    
    async def handle_intent(self, intent: str, args: dict) -> Any:
        """Handle an incoming intent. Override this."""
        raise NotImplementedError
    
    async def on_child_result(self, child_id: str, result: dict):
        """Called when a child agent returns a result."""
        pass
    
    # Agent operations
    async def spawn_child(
        self,
        agent_type: str,
        initial_intent: Optional[str] = None,
        args: Optional[dict] = None
    ) -> str:
        """Spawn a child agent."""
        child_id = await agent_manager.spawn(
            agent_type=agent_type,
            parent_id=self.id,
            initial_intent=initial_intent,
            args=args
        )
        self.children[child_id] = "running"
        return child_id
    
    async def emit_intent(self, intent: str, args: dict) -> Any:
        """Emit an intent to the mesh and await result."""
        return await mesh.route_and_execute(intent, args)
    
    def terminate(self, result: Any = None):
        """Terminate this agent."""
        self.state = AgentState.TERMINATED
        self._final_result = result
```

### 8.3 Cognitive Agent (LLM-Powered)

```python
class CognitiveAgent(Agent):
    """Agent with LLM-powered reasoning."""
    
    def __init__(self, *args, model: str = "llama3.2", **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model
        self.conversation_history = []
        self.available_tools = []
    
    async def handle_intent(self, intent: str, args: dict) -> Any:
        """Use LLM to reason about and execute the intent."""
        
        # Build prompt with context
        prompt = self._build_prompt(intent, args)
        
        # Reasoning loop
        max_iterations = 10
        for i in range(max_iterations):
            # Get LLM response
            response = await self._call_llm(prompt)
            
            # Parse for tool calls
            tool_call = self._parse_tool_call(response)
            
            if tool_call:
                # Execute tool (capability or child agent)
                result = await self._execute_tool(tool_call)
                
                # Add to context
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response
                })
                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result)
                })
                
                # Continue reasoning
                prompt = self._build_continuation_prompt()
            else:
                # No tool call = final answer
                return self._extract_answer(response)
        
        return {"error": "Max iterations exceeded"}
    
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM capability."""
        return await self.emit_intent(
            "generate text with language model",
            {
                "model": self.model,
                "messages": self.conversation_history + [
                    {"role": "user", "content": prompt}
                ]
            }
        )
    
    async def _execute_tool(self, tool_call) -> Any:
        """Execute a tool call."""
        if tool_call.type == "capability":
            return await self.emit_intent(
                tool_call.capability,
                tool_call.args
            )
        elif tool_call.type == "spawn_agent":
            child_id = await self.spawn_child(
                tool_call.agent_type,
                tool_call.intent,
                tool_call.args
            )
            return await agent_manager.await_result(child_id)
```

### 8.4 Anomaly Response Agent (Complete Example)

```python
@register_agent("anomaly_investigator")
class AnomalyInvestigatorAgent(Agent):
    """
    Spawned when an anomaly is detected.
    Gathers data, diagnoses, and decides on action.
    """
    
    DESCRIPTION = """
    Agent that investigates sensor anomalies by gathering additional data,
    running diagnostics, and deciding whether to alert humans, adjust 
    thresholds, or dismiss as noise.
    """
    
    async def handle_intent(self, intent: str, args: dict) -> Any:
        if intent == "investigate_anomaly":
            return await self._investigate(args)
        raise ValueError(f"Unknown intent: {intent}")
    
    async def _investigate(self, args: dict) -> dict:
        anomaly = args["anomaly"]
        sensor_id = anomaly["sensor_id"]
        
        # Phase 1: Gather more data
        self.context["phase"] = "data_collection"
        
        # Spawn parallel data collectors
        sensor_task = self.spawn_child(
            "data_collector",
            initial_intent="collect_sensor_history",
            args={"sensor_id": sensor_id, "window_minutes": 30}
        )
        
        context_task = self.spawn_child(
            "context_gatherer", 
            initial_intent="gather_environmental_context",
            args={"location": anomaly.get("location")}
        )
        
        # Wait for both
        sensor_data = await agent_manager.await_result(sensor_task)
        context_data = await agent_manager.await_result(context_task)
        
        # Phase 2: Diagnose
        self.context["phase"] = "diagnosis"
        
        diagnosis = await self._diagnose(
            anomaly=anomaly,
            sensor_history=sensor_data,
            environmental_context=context_data
        )
        
        # Phase 3: Decide action
        self.context["phase"] = "decision"
        
        action = await self._decide_action(diagnosis)
        
        # Execute action
        if action["type"] == "alert":
            await self.emit_intent(
                "send notification to human",
                {
                    "urgency": action["urgency"],
                    "message": action["message"]
                }
            )
        elif action["type"] == "adjust_threshold":
            await self.emit_intent(
                "update sensor threshold",
                {
                    "sensor_id": sensor_id,
                    "new_threshold": action["threshold"]
                }
            )
        # else: ignore
        
        return {
            "status": "complete",
            "diagnosis": diagnosis,
            "action_taken": action
        }
    
    async def _diagnose(self, anomaly, sensor_history, environmental_context) -> dict:
        """Run diagnostic analysis."""
        # Could be rule-based or LLM-powered
        
        # Rule-based example:
        readings = sensor_history["readings"]
        avg = sum(readings) / len(readings)
        std = (sum((x - avg)**2 for x in readings) / len(readings)) ** 0.5
        
        anomaly_value = anomaly["value"]
        z_score = (anomaly_value - avg) / std if std > 0 else 0
        
        if z_score > 3:
            severity = "high"
        elif z_score > 2:
            severity = "medium"
        else:
            severity = "low"
        
        return {
            "severity": severity,
            "z_score": z_score,
            "baseline_avg": avg,
            "baseline_std": std,
            "environmental_factors": environmental_context.get("factors", [])
        }
    
    async def _decide_action(self, diagnosis: dict) -> dict:
        """Decide what action to take based on diagnosis."""
        severity = diagnosis["severity"]
        env_factors = diagnosis.get("environmental_factors", [])
        
        # If environmental factors explain it, lower severity
        if "construction_nearby" in env_factors or "traffic_event" in env_factors:
            if severity == "high":
                severity = "medium"
            elif severity == "medium":
                severity = "low"
        
        if severity == "high":
            return {
                "type": "alert",
                "urgency": "high",
                "message": f"High severity anomaly detected. Z-score: {diagnosis['z_score']:.2f}"
            }
        elif severity == "medium":
            return {
                "type": "alert", 
                "urgency": "low",
                "message": f"Medium anomaly detected, may warrant investigation."
            }
        else:
            # Noise - maybe adjust threshold
            if diagnosis["z_score"] < 1.5:
                return {
                    "type": "adjust_threshold",
                    "threshold": diagnosis["baseline_avg"] + 2.5 * diagnosis["baseline_std"]
                }
            return {"type": "ignore"}
```

---

## 9. Resource Management

### 9.1 Agent Resource Profiles

```python
@dataclass
class ResourceProfile:
    """Resource requirements/limits for an agent."""
    
    # Memory
    memory_kb: int = 1024          # Max working memory
    context_tokens: int = 4096     # Max LLM context (if applicable)
    
    # Computation
    cpu_budget_ms: int = 1000      # CPU time per decision cycle
    max_children: int = 10         # Max concurrent children
    
    # Time
    timeout_ms: int = 60000        # Max lifetime
    idle_timeout_ms: int = 30000   # Suspend if idle this long
    
    # Network
    max_messages_per_sec: int = 10 # Rate limit
    max_hops: int = 3              # Max delegation depth
```

### 9.2 Resource Accounting

```python
class AgentResourceManager:
    """Tracks and enforces resource limits."""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.active_agents: Dict[str, ResourceUsage] = {}
        self.node_limits = self._detect_node_capacity()
    
    def can_spawn(self, profile: ResourceProfile) -> bool:
        """Check if node has capacity for new agent."""
        current_memory = sum(u.memory_kb for u in self.active_agents.values())
        current_agents = len(self.active_agents)
        
        return (
            current_memory + profile.memory_kb <= self.node_limits.memory_kb
            and current_agents < self.node_limits.max_agents
        )
    
    async def enforce_limits(self, agent_id: str):
        """Check and enforce limits for an agent."""
        usage = self.active_agents.get(agent_id)
        profile = usage.profile
        
        if usage.memory_kb > profile.memory_kb:
            await self._suspend_agent(agent_id, "memory_exceeded")
        
        if usage.lifetime_ms > profile.timeout_ms:
            await self._terminate_agent(agent_id, "timeout")
        
        if usage.child_count > profile.max_children:
            await self._reject_spawn(agent_id, "child_limit")
```

### 9.3 Agent Placement

Where should an agent run?

```python
async def find_best_node(
    agent_type: str,
    requirements: ResourceProfile,
    preferences: Dict[str, Any]
) -> str:
    """Find the best node to host an agent."""
    
    candidates = []
    
    for node in mesh.get_nodes():
        # Check if node can run this agent type
        if agent_type not in node.supported_agent_types:
            continue
        
        # Check resource availability
        if not node.resource_manager.can_spawn(requirements):
            continue
        
        # Score based on preferences
        score = 0.0
        
        # Prefer local
        if node.id == local_node_id:
            score += 0.3
        
        # Prefer fewer hops
        hops = mesh.hops_to(node.id)
        score -= 0.1 * hops
        
        # Prefer nodes with required capabilities
        for cap in preferences.get("required_capabilities", []):
            if cap in node.capabilities:
                score += 0.2
        
        candidates.append((node.id, score))
    
    if not candidates:
        raise NoCapacityError("No node can host this agent")
    
    # Return best node
    return max(candidates, key=lambda x: x[1])[0]
```

---

## 10. Security Considerations

### 10.1 Agent Identity

Each agent inherits trust from its host node:

```python
@dataclass
class AgentIdentity:
    agent_id: str
    node_id: str
    parent_chain: List[str]  # Chain of parent agent IDs
    spawn_time: int
    
    # Derived from node identity
    def sign(self, message: bytes) -> str:
        """Sign message using host node's key."""
        return node.identity.sign(
            self.agent_id.encode() + message
        )
```

### 10.2 Permission Model

```python
class AgentPermissions:
    """What an agent is allowed to do."""
    
    can_spawn_children: bool = True
    max_children: int = 10
    
    can_access_network: bool = True
    allowed_domains: List[str] = field(default_factory=list)  # Empty = all
    
    can_access_capabilities: List[str] = field(default_factory=list)  # Empty = all
    
    can_modify_state: bool = False  # Can modify mesh/node state?
    
    resource_limits: ResourceProfile = field(default_factory=ResourceProfile)
```

### 10.3 Sandboxing Options

For untrusted agents:

1. **Process isolation** - Run in separate process with limited syscalls
2. **WASM sandbox** - Compile agent to WASM, run in sandbox
3. **Container** - Docker/Podman for full isolation
4. **Trust level** - Adjust permissions based on agent source

---

## 11. Open Questions

### For Future Design Iterations

1. **State persistence**: Should agents survive node restarts? How?

2. **Agent migration**: Can an agent move from one node to another? When?

3. **Learning**: Can agents improve over time? How is knowledge shared?

4. **Consensus**: When multiple agents could handle an intent, who decides?

5. **Billing/quotas**: In a multi-tenant mesh, how are agent resources billed?

6. **Debugging**: How do you debug a distributed agent hierarchy?

7. **Versioning**: How do you upgrade agent types without breaking running instances?

---

## 12. Implementation Roadmap

### Phase 1: MVP (Week 1-2)
- [ ] Agent base class and lifecycle
- [ ] Simple agent registry (in-memory)
- [ ] Agent-as-capability wrapper
- [ ] Basic spawn/terminate
- [ ] Local-only communication

### Phase 2: Distribution (Week 3-4)
- [ ] Cross-node agent spawning
- [ ] Cross-node messaging
- [ ] Agent discovery via gossip
- [ ] Resource limits and enforcement

### Phase 3: Cognition (Week 5-6)
- [ ] CognitiveAgent with LLM integration
- [ ] Tool use framework
- [ ] Multi-step reasoning
- [ ] Learning from feedback

### Phase 4: Production (Week 7-8)
- [ ] Security hardening
- [ ] Monitoring and observability
- [ ] Agent persistence
- [ ] Performance optimization

---

## Appendix A: Message Format (Wire Protocol)

```
Agent Message Binary Format (for constrained devices):

 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Version    |     Type      |    Priority   |   TTL Hops    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         Message ID                            |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        From Agent ID                          |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         To Agent ID                           |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Payload Length        |          Reserved             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                         Payload Data                          |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                    Signature (64 bytes)                       |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

Total header: 28 bytes + payload + 64 byte signature
```

---

## Appendix B: Comparison with Existing Systems

| System | Model | Key Difference from Atmosphere Agents |
|--------|-------|--------------------------------------|
| **Akka/Erlang Actors** | Message-passing concurrency | No semantic routing, no LLM integration |
| **Kubernetes Pods** | Container orchestration | Too heavy for edge, no intent-based dispatch |
| **AWS Lambda** | Serverless functions | Stateless, cloud-only, no mesh |
| **AutoGPT** | Autonomous LLM agents | Single-node, no distribution |
| **CrewAI** | Multi-agent orchestration | No embedded support, cloud-focused |
| **LangGraph** | LLM workflow graphs | No embedded support, single runtime |

Atmosphere agents combine:
- Lightweight enough for ESP32
- Distributed across mesh
- Intent-routed (semantic)
- Hierarchical (parent-child)
- Range from reactive to cognitive

---

*End of Document*
