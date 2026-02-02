# Example Flow: Image Detection → Agent → Tools

This document shows exactly what happens when a camera frame triggers the system.

## Scenario

A camera on a production line captures a frame that might contain a defect.

## The Flow

```
TIME    EVENT
─────────────────────────────────────────────────────────────────────────

T+0ms   CAMERA: New frame captured
        │
        │ Frame stored in local ring buffer
        │ frame_id: "cam-01:frame:847291"
        │
        ▼

T+1ms   EDGE NODE: Watcher triggers vision_agent
        │
        │ Activation message (tiny!):
        │ {
        │   "activate": "vision_agent@1.2",
        │   "trigger": "new_frame",
        │   "input": {"frame_ref": "local:cam-01:frame:847291"}
        │ }
        │
        │ Agent already loaded (sleeping), wakes up
        │
        ▼

T+5ms   VISION_AGENT: Calls detect_objects tool
        │
        │ Tool call:
        │ {
        │   "tool": "detect_objects@1.0",
        │   "params": {
        │     "image_ref": "local:cam-01:frame:847291",
        │     "model": "tinyyolo-defects@1.3",
        │     "confidence_threshold": 0.5
        │   }
        │ }
        │
        │ Tool executes LOCALLY (image never leaves node)
        │
        ▼

T+150ms DETECT_OBJECTS: Returns result
        │
        │ Result:
        │ {
        │   "objects": [
        │     {"class": "widget", "confidence": 0.95, "bbox": [100, 50, 200, 180]},
        │     {"class": "unknown", "confidence": 0.42, "bbox": [300, 120, 80, 60]}
        │   ],
        │   "inference_time_ms": 145
        │ }
        │
        │ Agent analyzes: One detection is uncertain (0.42 < 0.85 threshold)
        │
        ▼

T+151ms VISION_AGENT: Decides to escalate uncertain detection
        │
        │ Checks escalation config:
        │ - target_capability: "vision:large_model"
        │ - timeout_ms: 5000
        │
        │ Creates escalation request:
        │ {
        │   "type": "escalate_classification",
        │   "image_ref": "edge-01:cam-01:frame:847291",  ← Reference, not image!
        │   "crop_bbox": [300, 120, 80, 60],             ← Just the uncertain region
        │   "local_prediction": {"class": "unknown", "confidence": 0.42},
        │   "model_used": "tinyyolo-defects@1.3",
        │   "callback": "edge-01:vision_agent:instance_42"
        │ }
        │
        ▼

T+152ms ROUTER: Routes escalation to GPU node
        │
        │ Gradient table lookup:
        │ - capability: "vision:large_model"
        │ - best node: "gpu-01" (score 0.91, 2 hops, load 0.3)
        │
        │ Forwards escalation request (still tiny, ~200 bytes)
        │
        ▼

T+160ms GPU NODE: Receives escalation request
        │
        │ Requests image crop directly from edge:
        │ "edge-01, send crop of frame:847291 at bbox [300,120,80,60]"
        │
        ▼

T+180ms EDGE NODE: Sends cropped image to GPU node
        │
        │ Direct P2P transfer (not through coordinator)
        │ Size: ~50KB (just the crop, not full 2MB frame)
        │
        ▼

T+200ms GPU NODE: Runs large model on crop
        │
        │ Model: yolov8x-defects@2.1
        │ Input: 80x60 crop
        │
        ▼

T+450ms GPU NODE: Classification complete
        │
        │ Result:
        │ {
        │   "class": "defect_scratch",
        │   "confidence": 0.94,
        │   "severity": "medium",
        │   "metadata": {
        │     "defect_type": "surface_scratch",
        │     "estimated_depth_mm": 0.3
        │   }
        │ }
        │
        │ Sends result back to edge callback
        │
        ▼

T+460ms VISION_AGENT (on edge): Receives escalation result
        │
        │ Now knows: The "unknown" was a defect_scratch
        │
        │ Decision tree:
        │ 1. ✓ Classification complete
        │ 2. → Log the event
        │ 3. → Check if notification needed (severity=medium → yes)
        │ 4. → Store learning sample
        │
        ▼

T+461ms VISION_AGENT: Calls log_event tool
        │
        │ {
        │   "tool": "log_event@1.0",
        │   "params": {
        │     "event_type": "defect_detected",
        │     "severity": "warning",
        │     "data": {
        │       "frame_id": "cam-01:frame:847291",
        │       "defect_class": "defect_scratch",
        │       "confidence": 0.94,
        │       "bbox": [300, 120, 80, 60],
        │       "production_line": "line-3",
        │       "timestamp": "2024-02-02T12:00:00Z"
        │     },
        │     "tags": ["defect", "line-3", "scratch"]
        │   }
        │ }
        │
        │ Executes locally, logged to local DB
        │
        ▼

T+465ms VISION_AGENT: Calls notify tool
        │
        │ {
        │   "tool": "notify@1.0",
        │   "params": {
        │     "recipient": "#quality-alerts",
        │     "urgency": "high",
        │     "title": "Defect Detected - Line 3",
        │     "message": "Surface scratch detected on widget. Confidence: 94%. Review recommended."
        │   }
        │ }
        │
        │ Tool routes to notification node (has Slack capability)
        │
        ▼

T+470ms ROUTER: Routes notify to notification node
        │
        │ Gradient table: notify → cloud-01 (has notifications capability)
        │
        ▼

T+550ms CLOUD NODE: Sends Slack notification
        │
        │ Slack API call → delivered
        │
        ▼

T+465ms VISION_AGENT: Calls store_learning_sample tool (parallel)
        │
        │ {
        │   "tool": "store_learning_sample@1.0",
        │   "params": {
        │     "sample_type": "image_classification",
        │     "data_ref": "local:cam-01:frame:847291:crop:[300,120,80,60]",
        │     "label": "defect_scratch",
        │     "metadata": {
        │       "source": "escalation",
        │       "source_model": "tinyyolo-defects@1.3",
        │       "escalation_model": "yolov8x-defects@2.1",
        │       "local_confidence": 0.42,
        │       "final_confidence": 0.94
        │     }
        │   }
        │ }
        │
        │ Stored in local learning queue (image stays on edge!)
        │ Only metadata travels
        │
        ▼

T+470ms VISION_AGENT: Returns final result
        │
        │ {
        │   "status": "complete",
        │   "detections": [
        │     {"class": "widget", "confidence": 0.95, "bbox": [100, 50, 200, 180]},
        │     {"class": "defect_scratch", "confidence": 0.94, "bbox": [300, 120, 80, 60],
        │      "severity": "medium", "escalated": true}
        │   ],
        │   "actions_taken": ["logged", "notified", "sample_stored"],
        │   "total_time_ms": 470
        │ }
        │
        │ Agent returns to sleep
        │
        ▼

T+600ms SLACK: Quality team receives notification
        │
        │ "🔴 Defect Detected - Line 3
        │  Surface scratch detected on widget.
        │  Confidence: 94%
        │  [View Details]"
        │

─────────────────────────────────────────────────────────────────────────
COMPLETE
```

## Bandwidth Analysis

| Transfer | Size | Notes |
|----------|------|-------|
| Agent activation | 200 bytes | Reference-based, no image |
| Escalation request | 200 bytes | Reference + bbox + metadata |
| Image crop transfer | 50 KB | Direct P2P, only the crop |
| Classification result | 500 bytes | Just the labels + metadata |
| Log event | 500 bytes | Structured data |
| Notify request | 200 bytes | Routes to notification node |
| Learning sample metadata | 300 bytes | Image stays local! |
| **Total network** | **~52 KB** | For a 2MB frame |

**The full 2MB frame never leaves the edge node.** Only a 50KB crop was transferred for escalation.

## What Happens Later

### Learning Queue Fills Up

After 100 escalated samples accumulate:

```
T+???    LEARNING_AGENT: Wakes up (threshold reached)
         │
         │ Collects sample manifest:
         │ "I have 100 samples labeled by escalation"
         │ 
         │ Creates training request:
         │ {
         │   "type": "training_job",
         │   "mission": "production-inspection",
         │   "base_model": "tinyyolo-defects@1.3",
         │   "samples": {
         │     "source_node": "edge-01",
         │     "count": 100,
         │     "manifest_ref": "edge-01:learning:batch_42"
         │   }
         │ }
         │
         ▼
         
         Routes to training node (tier_3 with GPU)
         Training node requests samples from edge
         Trains updated model → tinyyolo-defects@1.4
         New model deploys to all edge nodes
         Escalation rate drops (edge model is smarter now)
```

## Key Points

1. **Agent activation is tiny** — Just a reference + trigger type
2. **Tools execute locally when possible** — Image never leaves for local inference
3. **Escalation sends references** — Not the actual image
4. **Only crops transfer** — Not full frames
5. **Results are metadata** — Not raw data
6. **Learning samples stay local** — Only metadata ships
7. **Agent returns to sleep** — Zero resources when idle
