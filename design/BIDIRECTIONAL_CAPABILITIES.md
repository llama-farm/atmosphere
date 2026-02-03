# Bidirectional Capabilities

> **Every capability is both a trigger and a tool.**

---

## The Core Insight

Traditional systems treat sensors and services as one-directional:
- **Sensors push** → Events flow to handlers
- **Services get called** → Requests go to endpoints

Atmosphere unifies these: **Every capability is bidirectional.**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│                        BIDIRECTIONAL CAPABILITY                         │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                                                                  │   │
│  │   PUSH (Trigger)                    PULL (Tool)                 │   │
│  │                                                                  │   │
│  │   Camera detects motion      ←→     Agent queries camera        │   │
│  │   Model finishes training    ←→     Agent invokes inference     │   │
│  │   Sensor hits threshold      ←→     Agent reads current value   │   │
│  │   Schedule fires             ←→     Agent checks schedule       │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Same capability registration. Same routing fabric. Both directions.   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Why this matters:**
- A camera isn't just a passive sensor you query
- A model isn't just an endpoint you call
- Everything is a peer in the mesh that can both initiate and respond

---

## Capability Schema

Every capability declares both its **triggers** (what it can push) and its **tools** (what you can pull):

```yaml
capability:
  # Identity
  id: front-door-camera
  node: home-server
  type: sensor/camera
  
  # Location and metadata
  location: "front door"
  hardware: "Reolink RLC-810A"
  
  # ═══════════════════════════════════════════════════════════════════
  # TOOLS - What agents can call (PULL)
  # ═══════════════════════════════════════════════════════════════════
  tools:
    - name: get_frame
      description: "Capture current camera frame"
      parameters:
        resolution:
          type: string
          enum: [full, 720p, thumbnail]
          default: 720p
      returns:
        type: image/jpeg
        
    - name: get_history
      description: "Get motion events from specified time range"
      parameters:
        since:
          type: duration
          description: "Time range (e.g., '10m', '1h', '24h')"
          default: "1h"
        limit:
          type: integer
          default: 50
      returns:
        type: array
        items:
          type: object
          properties:
            timestamp: datetime
            type: string  # motion, person, vehicle, animal
            confidence: float
            thumbnail: image/jpeg
            
    - name: get_clip
      description: "Get video clip around a timestamp"
      parameters:
        timestamp:
          type: datetime
          required: true
        before_seconds:
          type: integer
          default: 5
        after_seconds:
          type: integer
          default: 10
      returns:
        type: video/mp4
        
    - name: get_snapshot_url
      description: "Get live snapshot URL (for streaming)"
      returns:
        type: string
        format: uri

  # ═══════════════════════════════════════════════════════════════════
  # TRIGGERS - What this capability can push (PUSH)
  # ═══════════════════════════════════════════════════════════════════
  triggers:
    - event: motion_detected
      description: "General motion detected in frame"
      intent_template: "motion detected at {location}"
      payload:
        timestamp: datetime
        region: string          # where in frame
        confidence: float
        frame: image/jpeg       # snapshot at detection
      route_hint: security/*    # suggest routing target
      throttle: 30s             # min time between triggers
      
    - event: person_detected
      description: "Human detected in frame"
      intent_template: "person detected at {location}"
      payload:
        timestamp: datetime
        confidence: float
        count: integer          # number of people
        frame: image/jpeg
        faces: array            # face crops if available
      route_hint: security/*
      priority: high            # escalate this
      throttle: 10s
      
    - event: vehicle_detected
      description: "Vehicle detected (car, truck, motorcycle)"
      intent_template: "vehicle detected at {location}: {vehicle_type}"
      payload:
        timestamp: datetime
        vehicle_type: string
        confidence: float
        frame: image/jpeg
        license_plate: string   # if readable
      route_hint: security/*
      throttle: 60s
      
    - event: package_detected
      description: "Package/delivery detected"
      intent_template: "package arrived at {location}"
      payload:
        timestamp: datetime
        confidence: float
        frame: image/jpeg
      route_hint: notifications/*
      priority: normal
      
    - event: animal_detected
      description: "Animal detected"
      intent_template: "{animal_type} detected at {location}"
      payload:
        timestamp: datetime
        animal_type: string
        confidence: float
        frame: image/jpeg
      route_hint: wildlife/*
      throttle: 5m
      
    - event: camera_offline
      description: "Camera connection lost"
      intent_template: "camera offline: {location}"
      payload:
        last_seen: datetime
        error: string
      route_hint: alerts/*
      priority: critical
```

---

## How It Works

### Push Flow (Trigger → Intent → Agent)

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   CAMERA         │     │   ATMOSPHERE     │     │   AGENT          │
│                  │     │   MESH           │     │                  │
│ 1. Detect motion │────▶│ 2. Create intent │────▶│ 4. Handle intent │
│                  │     │ 3. Route by type │     │                  │
└──────────────────┘     └──────────────────┘     └──────────────────┘

Detailed flow:

1. Camera's on-device ML detects motion
2. Camera capability publishes trigger:
   {
     event: "motion_detected",
     capability_id: "front-door-camera",
     payload: { timestamp, confidence, frame }
   }
3. Mesh creates intent from trigger:
   {
     type: "sensor/event",
     text: "motion detected at front door",
     source: "front-door-camera",
     data: { ... payload ... }
   }
4. Router finds best handler:
   - Check route_hint: security/*
   - Find capable agent with security domain
   - Route intent to agent
5. Agent receives intent, decides action:
   - Check time (night? day?)
   - Check history (is this normal?)
   - Maybe query camera for more context
   - Take action or ignore
```

### Pull Flow (Agent → Tool → Response)

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   AGENT          │     │   ATMOSPHERE     │     │   CAMERA         │
│                  │     │   MESH           │     │                  │
│ 1. Need context  │────▶│ 2. Route tool    │────▶│ 3. Execute tool  │
│ 5. Use response  │◀────│    call          │◀────│ 4. Return data   │
└──────────────────┘     └──────────────────┘     └──────────────────┘

Detailed flow:

1. Agent is reasoning about a security event
2. Agent calls tool:
   mesh.call("front-door-camera", "get_history", { since: "30m" })
3. Mesh routes to camera capability
4. Camera returns recent motion events
5. Agent uses history to make decision:
   - "Ah, there was motion 5 times in the last 30 min"
   - "But it's all squirrels (animal_detected, confidence 0.92)"
   - "This is normal, no action needed"
```

### Bidirectional Conversation

The real power: **triggers and tools in the same workflow**:

```
Timeline:

T+0s:    Camera detects person
         → Trigger: person_detected at front door
         
T+0.1s:  Intent routes to SecurityAgent
         
T+0.2s:  SecurityAgent receives intent
         → "Person at front door, let me check context"
         
T+0.3s:  SecurityAgent calls camera tool
         → get_history(since="10m")
         
T+0.4s:  Camera returns: 
         - 2 motion events (wind?)
         - 1 vehicle event (delivery truck)
         - Current person event
         
T+0.5s:  SecurityAgent reasons:
         → "Delivery truck + person = probably delivery driver"
         → Check time: 2:30 PM (normal delivery hours)
         → Decision: This is expected, no alert
         
T+0.6s:  SecurityAgent calls notification tool (low priority)
         → "Delivery may have arrived at front door"

--- 2 minutes later ---

T+120s:  Camera detects package
         → Trigger: package_detected at front door
         
T+120.1s: Intent routes to NotificationAgent
          
T+120.2s: NotificationAgent correlates:
          → Recent person_detected + package_detected
          → "Confirmed: package delivered"
          
T+120.3s: NotificationAgent sends:
          → Push notification to user
          → "📦 Package delivered at front door"
          → Includes frame from camera
```

---

## More Examples

### Model as Bidirectional Capability

A trained model isn't just an inference endpoint:

```yaml
capability:
  id: wildlife-classifier-v3
  node: gpu-server
  type: ml/vision/classify
  domain: wildlife
  
  tools:
    - name: classify
      description: "Classify wildlife in image"
      parameters:
        image: image/*
        top_k: integer
      returns:
        predictions: array
        
    - name: get_embeddings
      description: "Get image embeddings for similarity search"
      parameters:
        image: image/*
      returns:
        embedding: float[512]
        
    - name: get_confidence_threshold
      description: "Get current confidence threshold"
      returns:
        threshold: float
        
    - name: get_class_list
      description: "List all classes this model can detect"
      returns:
        classes: array
        
  triggers:
    - event: training_complete
      description: "Model training finished"
      intent_template: "model {model_id} training complete"
      payload:
        accuracy: float
        epochs: integer
        duration: duration
      route_hint: deployment/*
      
    - event: accuracy_degradation
      description: "Model accuracy dropped below threshold"
      intent_template: "model {model_id} accuracy degraded to {accuracy}"
      payload:
        current_accuracy: float
        expected_accuracy: float
        sample_failures: array
      route_hint: ml-ops/*
      priority: high
      
    - event: drift_detected
      description: "Data drift detected in inference inputs"
      intent_template: "data drift detected for {model_id}"
      payload:
        drift_score: float
        affected_features: array
      route_hint: ml-ops/*
```

### IoT Device as Bidirectional Capability

A thermostat that both reports and responds:

```yaml
capability:
  id: living-room-thermostat
  node: home-hub
  type: iot/hvac
  location: living room
  
  tools:
    - name: get_temperature
      description: "Get current temperature"
      returns:
        current: float
        target: float
        humidity: float
        
    - name: set_temperature
      description: "Set target temperature"
      parameters:
        target: float
        hold_until: datetime  # optional
      returns:
        success: boolean
        
    - name: get_schedule
      description: "Get programmed schedule"
      returns:
        schedule: object
        
    - name: set_mode
      description: "Set HVAC mode"
      parameters:
        mode: [heat, cool, auto, off]
      returns:
        success: boolean
        
  triggers:
    - event: temperature_anomaly
      description: "Temperature outside normal range"
      intent_template: "temperature anomaly in {location}: {current}°F (expected {expected}°F)"
      payload:
        current: float
        expected: float
        trend: [rising, falling, stable]
      route_hint: home/*
      
    - event: hvac_malfunction
      description: "HVAC system not responding"
      intent_template: "HVAC malfunction in {location}"
      payload:
        error_code: string
        last_successful: datetime
      route_hint: alerts/*
      priority: high
      
    - event: occupancy_change
      description: "Room occupancy changed (via motion/presence)"
      intent_template: "{location} now {state}"
      payload:
        state: [occupied, vacant]
        confidence: float
      route_hint: automation/*
      throttle: 5m
```

### Agent as Bidirectional Capability

Even agents can be capabilities that trigger and respond:

```yaml
capability:
  id: security-agent
  node: home-server
  type: agent/security
  
  tools:
    - name: get_status
      description: "Get current security status"
      returns:
        mode: [home, away, night, vacation]
        active_alerts: array
        last_event: object
        
    - name: arm
      description: "Arm the security system"
      parameters:
        mode: [away, night, vacation]
      returns:
        success: boolean
        
    - name: acknowledge_alert
      description: "Acknowledge and dismiss an alert"
      parameters:
        alert_id: string
        action: [dismiss, escalate, investigate]
      returns:
        success: boolean
        
    - name: get_event_history
      description: "Get security event history"
      parameters:
        since: duration
        types: array
      returns:
        events: array
        
  triggers:
    - event: intrusion_detected
      description: "Possible intrusion detected"
      intent_template: "⚠️ INTRUSION ALERT: {location}"
      payload:
        location: string
        confidence: float
        evidence: array  # frames, sensor data
      route_hint: notifications/*
      priority: critical
      
    - event: all_clear
      description: "Security check complete, no issues"
      intent_template: "security check complete: all clear"
      payload:
        checked_zones: array
        duration: duration
      route_hint: logs/*
      
    - event: mode_change
      description: "Security mode changed"
      intent_template: "security mode changed to {mode}"
      payload:
        previous_mode: string
        new_mode: string
        changed_by: string  # user, schedule, automation
      route_hint: home/*
```

---

## The Routing Fabric

Both push and pull use the same routing infrastructure:

```
                    ┌─────────────────────────────────────────────┐
                    │              ROUTING FABRIC                  │
                    │                                              │
  PUSH (Triggers)   │   ┌─────────────────────────────────────┐  │   PULL (Tools)
  ──────────────────│──▶│                                     │◀─│────────────────
                    │   │         CAPABILITY REGISTRY          │  │
  Trigger fires     │   │                                     │  │   Tool call
  Create intent     │   │   capability_id → node              │  │   Route to cap
  Route by type     │   │   type → [capability_ids]           │  │   Execute
  Deliver to agent  │   │   domain → [capability_ids]         │  │   Return result
                    │   │                                     │  │
                    │   └─────────────────────────────────────┘  │
                    │                                              │
                    │   Same registry. Same gossip updates.       │
                    │   Same routing logic. Both directions.      │
                    │                                              │
                    └─────────────────────────────────────────────┘
```

### Intent Routing (Push)

When a trigger fires:

```python
def handle_trigger(capability_id: str, event: str, payload: dict):
    """Route a trigger event to the appropriate handler."""
    
    # 1. Get capability metadata
    cap = registry.get_capability(capability_id)
    trigger = cap.get_trigger(event)
    
    # 2. Create intent from trigger template
    intent = Intent(
        type=f"trigger/{cap.type}/{event}",
        text=trigger.intent_template.format(**payload, **cap.metadata),
        source=capability_id,
        data=payload,
        priority=trigger.priority,
    )
    
    # 3. Apply throttle (skip if too recent)
    if throttle_check(capability_id, event, trigger.throttle):
        return  # Throttled, skip
    
    # 4. Route using standard mesh routing
    if trigger.route_hint:
        # Try hint first
        targets = registry.find_by_pattern(trigger.route_hint)
        if targets:
            route_to_best(intent, targets)
            return
    
    # 5. Fall back to semantic routing
    route_semantic(intent)
```

### Tool Routing (Pull)

When an agent calls a tool:

```python
async def call_tool(capability_id: str, tool_name: str, params: dict) -> Any:
    """Route a tool call to the capability."""
    
    # 1. Find capability
    cap = registry.get_capability(capability_id)
    if not cap:
        raise CapabilityNotFound(capability_id)
    
    # 2. Validate tool exists
    tool = cap.get_tool(tool_name)
    if not tool:
        raise ToolNotFound(tool_name)
    
    # 3. Validate parameters
    validate_params(tool.parameters, params)
    
    # 4. Route to node
    node = mesh.get_node(cap.node)
    if not node.is_online:
        # Try to find alternative
        alternatives = registry.find_by_type(cap.type)
        node = find_best_alternative(alternatives)
    
    # 5. Execute and return
    result = await node.execute_tool(capability_id, tool_name, params)
    return result
```

---

## Capability Lifecycle

Capabilities announce themselves via gossip:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        CAPABILITY LIFECYCLE                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. REGISTER                                                             │
│     Node starts up, capability becomes available                         │
│     → Gossip: CAPABILITY_AVAILABLE { id, type, tools, triggers }        │
│     → All nodes update their registry                                    │
│                                                                          │
│  2. HEARTBEAT                                                            │
│     Every 30s, node announces capabilities still available               │
│     → Gossip: CAPABILITY_HEARTBEAT { ids, status }                      │
│     → Nodes update freshness timestamps                                  │
│                                                                          │
│  3. UPDATE                                                               │
│     Capability changes (new tools, updated triggers)                     │
│     → Gossip: CAPABILITY_UPDATED { id, changes }                        │
│     → All nodes merge updates                                            │
│                                                                          │
│  4. SUSPEND                                                              │
│     Capability temporarily unavailable (maintenance, overload)           │
│     → Gossip: CAPABILITY_SUSPENDED { id, reason, resume_estimate }      │
│     → Routers skip this capability until resumed                         │
│                                                                          │
│  5. DEREGISTER                                                           │
│     Capability going offline permanently                                 │
│     → Gossip: CAPABILITY_REMOVED { id }                                 │
│     → All nodes remove from registry                                     │
│                                                                          │
│  6. TIMEOUT                                                              │
│     No heartbeat for 5 minutes                                           │
│     → Nodes mark capability as stale                                     │
│     → Routing avoids stale capabilities                                  │
│     → After 15 min, auto-deregister                                      │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Cross-Capability Workflows

The magic happens when capabilities interact:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   CROSS-CAPABILITY WORKFLOW                             │
│                                                                         │
│  "Notify me when someone's at the door, but only if I'm not home"      │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐   person_detected    ┌──────────────────┐            │
│  │   Camera     │─────────────────────▶│  Security Agent  │            │
│  └──────────────┘                      └────────┬─────────┘            │
│                                                  │                      │
│                                         "Am I home?"                    │
│                                                  │                      │
│                                                  ▼                      │
│                                        ┌──────────────────┐            │
│  ┌──────────────┐   get_location       │  Phone Location  │            │
│  │   Phone      │◀─────────────────────│  (tool call)     │            │
│  └──────────────┘                      └────────┬─────────┘            │
│         │                                        │                      │
│         │ "500m from home"                       │                      │
│         ▼                                        ▼                      │
│  ┌──────────────────────────────────────────────────────┐              │
│  │  Security Agent decides: User is away, send alert   │              │
│  └──────────────────────────────────────┬───────────────┘              │
│                                          │                              │
│                          send_notification                              │
│                                          │                              │
│                                          ▼                              │
│                                ┌──────────────────┐                    │
│                                │  Notification    │                    │
│                                │  Service         │                    │
│                                └────────┬─────────┘                    │
│                                          │                              │
│                                          ▼                              │
│                                ┌──────────────────┐                    │
│                                │  📱 User gets    │                    │
│                                │  push: "Someone  │                    │
│                                │  at front door"  │                    │
│                                └──────────────────┘                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

Capabilities involved:
- Camera (trigger: person_detected)
- Phone (tool: get_location)
- Notification Service (tool: send_notification)
- Security Agent (orchestrates, uses tools, handles triggers)
```

---

## Implementation

### Capability Registration (Python)

```python
from atmosphere import Capability, Tool, Trigger

# Define a camera capability
camera = Capability(
    id="front-door-camera",
    type="sensor/camera",
    location="front door",
    
    tools=[
        Tool(
            name="get_frame",
            description="Capture current camera frame",
            parameters={"resolution": {"type": "string", "default": "720p"}},
            handler=capture_frame,  # Function to call
        ),
        Tool(
            name="get_history",
            description="Get motion events",
            parameters={"since": {"type": "duration", "default": "1h"}},
            handler=get_motion_history,
        ),
    ],
    
    triggers=[
        Trigger(
            event="motion_detected",
            intent_template="motion detected at {location}",
            payload_schema={"timestamp": "datetime", "confidence": "float"},
            route_hint="security/*",
            throttle="30s",
        ),
        Trigger(
            event="person_detected",
            intent_template="person detected at {location}",
            payload_schema={"timestamp": "datetime", "confidence": "float"},
            route_hint="security/*",
            priority="high",
            throttle="10s",
        ),
    ],
)

# Register with mesh
mesh.register_capability(camera)

# Fire a trigger (when motion is detected)
camera.fire_trigger("motion_detected", {
    "timestamp": datetime.now(),
    "confidence": 0.87,
    "frame": captured_frame,
})
```

### Agent Using Capabilities (Python)

```python
from atmosphere import Agent, mesh

class SecurityAgent(Agent):
    """Agent that handles security events using bidirectional capabilities."""
    
    async def handle_intent(self, intent):
        """Handle incoming trigger events."""
        
        if intent.type == "trigger/sensor/camera/person_detected":
            await self.handle_person_detected(intent)
    
    async def handle_person_detected(self, intent):
        """Respond to person detection."""
        
        # 1. Get more context (PULL from camera)
        camera_id = intent.source
        history = await mesh.call_tool(
            camera_id, 
            "get_history", 
            {"since": "10m"}
        )
        
        # 2. Check if user is home (PULL from phone)
        location = await mesh.call_tool(
            "user-phone",
            "get_location",
            {}
        )
        
        # 3. Decide action
        distance_from_home = self.calculate_distance(location, HOME_COORDS)
        
        if distance_from_home > 100:  # User is away
            # Get current frame for notification
            frame = await mesh.call_tool(camera_id, "get_frame", {})
            
            # Send notification (PULL from notification service)
            await mesh.call_tool(
                "notification-service",
                "send_push",
                {
                    "title": "Someone at front door",
                    "body": f"Person detected while you're away",
                    "image": frame,
                    "priority": "high",
                }
            )
        else:
            # User is home, just log it
            self.log(f"Person at door, but user is home. No action.")
```

---

## Benefits

### 1. Unified Mental Model

No more thinking about "events" vs "APIs" vs "sensors" vs "services". Everything is a capability with:
- Things it can do (tools)
- Things it can tell you about (triggers)

### 2. Composability

Mix and match capabilities in workflows:
```
Camera trigger → Agent reasoning → Phone tool → Notification tool
```

Each piece is independent, connected by the mesh.

### 3. Discoverability

Query the mesh: "What can detect people?" Returns all capabilities with `person_detected` trigger or `detect_person` tool.

### 4. Resilience

If one camera goes offline:
- Its triggers stop firing (gracefully)
- Tool calls to it fail fast
- Alternative capabilities can be discovered
- Mesh routes around the failure

### 5. Scaling

Add more cameras:
- They register automatically
- Triggers route to available agents
- Load balances naturally
- No configuration changes needed

---

## Summary

**Every capability in Atmosphere is bidirectional:**

| Direction | Mechanism | Example |
|-----------|-----------|---------|
| **PUSH** | Triggers | Camera detects motion → publishes intent |
| **PULL** | Tools | Agent queries camera → gets history |

**Same registration. Same routing. Same mesh. Both directions.**

This unifies:
- Sensors and services
- Events and requests
- Reactive and proactive
- Push and pull

Into one coherent model: **The Capability Mesh**.

---

*Document Version: 1.0*  
*Date: 2026-02-02*  
*Author: Atmosphere Protocol Team*
