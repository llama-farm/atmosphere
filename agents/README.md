# Atmosphere Agents

Agents are the decision-makers in the mesh. They receive triggers, think, and act.

## Two Parts to Every Agent

### 1. The Instructions (Markdown)

The `.md` file is what the agent "reads" — its personality, decision logic, examples. This is what an LLM loads as context when the agent runs.

```
vision_agent.md
├── Your Job (what you do)
├── Tools You Have (what you can call)
├── Decision Logic (how to think)
├── Examples (concrete scenarios)
└── What You Don't Do (boundaries)
```

### 2. The Config (YAML)

The `.yaml` file is machine config — what triggers the agent, resource limits, which tools to load. The runtime reads this.

```yaml
# vision_agent.yaml
agent:
  id: vision_agent
  version: "1.2"
  instructions: vision_agent.md  # ← Links to the markdown
  
  triggers:
    - new_frame
    - motion_detected
  
  tools:
    - detect_objects
    - classify_image
    - notify
  
  resources:
    max_memory_mb: 256
    timeout_s: 30
```

## Agent Types

| Type | Complexity | Runs On | Use Case |
|------|------------|---------|----------|
| **Reactive** | Simple if/then | ESP32, RPi | Sensor response, quick decisions |
| **Deliberative** | Multi-step reasoning | Edge, workstation | Research, analysis |
| **Orchestrator** | Coordinates others | Any | Complex workflows |
| **Cognitive** | Full LLM reasoning | GPU node | Open-ended tasks |

## Agents in This Directory

| Agent | Type | Purpose |
|-------|------|---------|
| `vision_agent` | Reactive | Image/video analysis, defect detection |
| `anomaly_agent` | Reactive | Sensor monitoring, anomaly detection |
| `notification_agent` | Reactive | Message delivery across channels |
| `research_agent` | Deliberative | Information gathering, RAG search |
| `orchestrator_agent` | Orchestrator | Multi-step workflow coordination |
| `learning_agent` | Deliberative | Model training loop management |
| `provisioning_agent` | Reactive | New device setup and configuration |

## How Agents Get Activated

1. **Trigger fires** (new sensor reading, user request, schedule)
2. **Router finds agent** (semantic match or explicit reference)
3. **Agent loads** (if sleeping) or **receives message** (if running)
4. **Instructions loaded** as LLM context (for cognitive agents)
5. **Agent executes**, calls tools, makes decisions
6. **Returns result**, goes back to sleep

## Creating a New Agent

1. **Write the markdown** — What should the agent do? How should it think?
   ```markdown
   # My New Agent
   
   You do X when Y happens.
   
   ## Tools You Have
   - tool_a
   - tool_b
   
   ## Decision Logic
   ...
   ```

2. **Write the config** — How does it get triggered? What resources?
   ```yaml
   agent:
     id: my_new_agent
     version: "1.0"
     instructions: my_new_agent.md
     triggers:
       - my_trigger
     tools:
       - tool_a
       - tool_b
   ```

3. **Register with mesh** — The config gets gossiped to all nodes

4. **Deploy** — Nodes with matching capabilities can now run it

## Activation Messages

When activating an agent, send minimal data:

```json
{
  "activate": "vision_agent@1.2",
  "trigger": "new_frame",
  "input": {
    "frame_ref": "local:camera_01:frame_12847"
  }
}
```

**NOT** the full instructions, tool definitions, or images. Just references.

## Agent-to-Agent Communication

Agents can spawn or call other agents:

```
orchestrator_agent
    ├── spawns → vision_agent (on edge-01)
    ├── spawns → vision_agent (on edge-02)
    ├── waits for results
    └── spawns → notification_agent (results summary)
```

Each agent runs independently. The orchestrator just coordinates.
