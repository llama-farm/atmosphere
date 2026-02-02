# Atmosphere: End-to-End Scenarios

**Proof that the Internet of Intent works**

This document contains four detailed scenarios demonstrating how Atmosphere's architecture handles real-world problems. Each scenario shows:
- Data flowing through the Data Plane
- Watchers creating intents in the Decision Plane
- Semantic routing in the Intent Plane
- Agents executing with Tools

---

## Table of Contents
1. [Smart Factory Anomaly Response](#scenario-1-smart-factory-anomaly-response)
2. [Personal Assistant Query](#scenario-2-personal-assistant-query)
3. [Multi-Device Automation](#scenario-3-multi-device-automation)
4. [Security Incident Response](#scenario-4-security-incident-response)

---

## Scenario 1: Smart Factory Anomaly Response

### Overview
A vibration sensor detects abnormal frequency on Machine 3. The system automatically correlates data, analyzes the anomaly, triggers visual inspection, predicts failure, and notifies maintenance—all within seconds.

### Infrastructure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FACTORY FLOOR                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   [S1] [S2] [S3] [S4] [S5] [S6] [S7] [S8] [S9] [S10]   ← Vibration Sensors  │
│    │    │    │    │    │    │    │    │    │    │        (no compute)        │
│    └────┴────┼────┴────┴────┴────┴────┴────┴────┘                           │
│              │                                                               │
│         ┌────▼────┐                                                          │
│         │  S3     │  ← ANOMALY: 847 Hz (normal: 400-500 Hz)                 │
│         │ Machine │                                                          │
│         └────┬────┘                                                          │
│              │                                                               │
│   [CAM-1]────┼────[CAM-2]────────[CAM-3]              ← Cameras             │
│   (motion)   │    (motion)        (motion)              (local detect)       │
│              │                                                               │
└──────────────┼──────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           EDGE LAYER                                          │
│  ┌────────────────────────────────────────────────────────────┐              │
│  │              JETSON NANO (Edge Gateway)                     │              │
│  │  node_id: factory-edge-01                                   │              │
│  │  capabilities: [data_aggregation, threshold_watch, camera]  │              │
│  │                                                             │              │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │              │
│  │  │ Sensor      │  │ Threshold   │  │ Camera      │         │              │
│  │  │ Aggregator  │  │ Watcher     │  │ Controller  │         │              │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │              │
│  └────────────────────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────────────────┘
               │
               │ mesh connection (encrypted, signed)
               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        ON-PREMISE DATA CENTER                                 │
│  ┌────────────────────────────────────────────────────────────┐              │
│  │              DELL WORKSTATION (ML Node)                     │              │
│  │  node_id: factory-ml-01                                     │              │
│  │  capabilities: [llm, vision, anomaly_detection, prediction] │              │
│  │  GPU: RTX 4090                                              │              │
│  │                                                             │              │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │              │
│  │  │ Anomaly     │  │ Vision      │  │ Predictive  │         │              │
│  │  │ Classifier  │  │ Analyzer    │  │ Model       │         │              │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │              │
│  └────────────────────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────────────────┘
               │
               │ mesh connection (TLS, signed)
               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              CLOUD                                            │
│  ┌────────────────────────────────────────────────────────────┐              │
│  │              CLOUD INSTANCE (Storage/Training)              │              │
│  │  node_id: factory-cloud-01                                  │              │
│  │  capabilities: [storage, notification, training, reporting] │              │
│  │                                                             │              │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │              │
│  │  │ Time-Series │  │ Notification│  │ Model       │         │              │
│  │  │ Database    │  │ Service     │  │ Trainer     │         │              │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │              │
│  └────────────────────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Timing Diagram

```
Time      S3        Jetson         Dell WS       Cloud         Human
─────────────────────────────────────────────────────────────────────────────
T=0       ●─────────────────────────────────────────────────────────────────
          │ 847 Hz reading
          │
T=5ms     └────►●────────────────────────────────────────────────────────────
                │ Sensor aggregator receives
                │ Buffer: [S3: 847Hz]
                │
T=10ms          ●────────────────────────────────────────────────────────────
                │ Threshold watcher triggers
                │ (847 > 500 Hz threshold)
                │
T=15ms          ●────────────────────────────────────────────────────────────
                │ Creates intent:
                │ "investigate_anomaly"
                │
T=20ms          └─────────────►●──────────────────────────────────────────────
                               │ Semantic router receives
                               │ Routes to anomaly_detection
                               │
T=50ms                         ●──────────────────────────────────────────────
                               │ Anomaly classifier runs
                               │ Result: bearing_wear (0.89)
                               │
T=100ms         ◄──────────────●──────────────────────────────────────────────
                │              │ Request: get camera frame
                │              │ (CAM-2, nearest to Machine 3)
                │
T=150ms         ●──────────────►──────────────────────────────────────────────
                │ Frame captured
                │ 1920x1080 JPEG
                │
T=200ms                        ●──────────────────────────────────────────────
                               │ Vision analyzer runs
                               │ Detects: heat discoloration,
                               │ vibration blur on bearing
                               │
T=300ms                        ●──────────────────────────────────────────────
                               │ Predictive model runs
                               │ MTBF: 72 hours (confidence 0.84)
                               │
T=350ms                        ●──────────────►●──────────────────────────────
                               │              │ Store anomaly record
                               │              │ Send notification
                               │
T=400ms                                       ●──────────────────►●───────────
                                              │                   │ Push alert
                                              │                   │ "Machine 3
                                              │                   │  bearing wear
                                              │                   │  72h to fail"
                                              │
T=500ms                        ●──────────────────────────────────────────────
                               │ Creates follow-up intent:
                               │ "schedule_maintenance"
                               │
T=600ms                                       ●──────────────────────────────
                                              │ Maintenance ticket created
                                              │ Parts order initiated
                                              │
T+24h                                         ●──────────────────────────────
                                              │ Retrain model with new data
                                              │ (background job)
```

### Agent Inventory

| Agent | Node | Role | Capabilities |
|-------|------|------|--------------|
| `sensor-aggregator` | Jetson | Collect/buffer sensor data | data_aggregation |
| `threshold-watcher` | Jetson | Detect out-of-range values | threshold_watch |
| `anomaly-agent` | Dell WS | Classify anomaly type | anomaly_detection, llm |
| `vision-agent` | Dell WS | Analyze camera frames | vision |
| `predictor-agent` | Dell WS | Estimate time-to-failure | prediction |
| `notifier-agent` | Cloud | Send alerts, create tickets | notification |
| `trainer-agent` | Cloud | Improve models over time | training |

### Message Formats

#### Data Plane: Sensor Reading
```json
{
  "type": "sensor_reading",
  "source": {
    "node_id": "factory-edge-01",
    "sensor_id": "vibration-sensor-03"
  },
  "timestamp": "2024-01-15T14:32:05.847Z",
  "data": {
    "frequency_hz": 847.3,
    "amplitude_g": 2.4,
    "temperature_c": 45.2
  },
  "signature": "ed25519:abc123..."
}
```

#### Decision Plane: Watcher Trigger
```json
{
  "type": "watcher_trigger",
  "watcher_id": "vibration-threshold-watch",
  "triggered_at": "2024-01-15T14:32:05.857Z",
  "condition": {
    "field": "data.frequency_hz",
    "operator": "gt",
    "threshold": 500,
    "actual": 847.3
  },
  "context": {
    "sensor_id": "vibration-sensor-03",
    "machine": "machine-03",
    "location": "assembly-line-2"
  }
}
```

#### Intent Plane: Anomaly Investigation Intent
```json
{
  "type": "intent",
  "id": "intent-7f3a2b1c",
  "created_at": "2024-01-15T14:32:05.865Z",
  "origin_node": "factory-edge-01",
  "intent": "investigate equipment anomaly",
  "embedding": [0.23, -0.45, 0.12, ...],  // 768-dim vector
  "context": {
    "machine_id": "machine-03",
    "anomaly_type": "vibration",
    "severity": "high",
    "readings": {
      "frequency_hz": 847.3,
      "normal_range": [400, 500]
    }
  },
  "constraints": {
    "max_latency_ms": 1000,
    "require_visual": true
  },
  "signature": "ed25519:def456..."
}
```

#### Tool Calls

**1. Anomaly Classification**
```json
{
  "tool": "classify_anomaly",
  "agent": "anomaly-agent",
  "node": "factory-ml-01",
  "params": {
    "sensor_type": "vibration",
    "readings": {
      "frequency_hz": 847.3,
      "amplitude_g": 2.4,
      "temperature_c": 45.2
    },
    "historical_baseline": {
      "frequency_mean": 450,
      "frequency_std": 25
    }
  },
  "result": {
    "classification": "bearing_wear",
    "confidence": 0.89,
    "alternative_diagnoses": [
      {"type": "misalignment", "confidence": 0.07},
      {"type": "imbalance", "confidence": 0.04}
    ]
  }
}
```

**2. Camera Frame Capture**
```json
{
  "tool": "capture_frame",
  "agent": "vision-agent",
  "node": "factory-edge-01",
  "params": {
    "camera_id": "cam-02",
    "resolution": "1920x1080",
    "format": "jpeg"
  },
  "result": {
    "frame_id": "frame-8a4b2c1d",
    "timestamp": "2024-01-15T14:32:05.950Z",
    "size_bytes": 245760,
    "data_uri": "atmosphere://factory-edge-01/frames/frame-8a4b2c1d"
  }
}
```

**3. Visual Analysis**
```json
{
  "tool": "analyze_image",
  "agent": "vision-agent", 
  "node": "factory-ml-01",
  "params": {
    "image_uri": "atmosphere://factory-edge-01/frames/frame-8a4b2c1d",
    "analysis_types": ["thermal_anomaly", "motion_blur", "component_damage"],
    "region_of_interest": {
      "machine": "machine-03",
      "component": "bearing"
    }
  },
  "result": {
    "findings": [
      {
        "type": "thermal_anomaly",
        "location": {"x": 320, "y": 180, "w": 50, "h": 50},
        "severity": 0.72,
        "description": "Elevated heat signature near bearing housing"
      },
      {
        "type": "motion_blur",
        "location": {"x": 315, "y": 175, "w": 60, "h": 60},
        "severity": 0.85,
        "description": "Excessive vibration visible in bearing area"
      }
    ],
    "overall_assessment": "Visual confirmation of bearing degradation"
  }
}
```

**4. Failure Prediction**
```json
{
  "tool": "predict_failure",
  "agent": "predictor-agent",
  "node": "factory-ml-01",
  "params": {
    "machine_id": "machine-03",
    "component": "bearing",
    "current_readings": {
      "frequency_hz": 847.3,
      "visual_severity": 0.85
    },
    "model": "bearing-degradation-v2"
  },
  "result": {
    "predicted_failure_hours": 72,
    "confidence": 0.84,
    "confidence_interval": [48, 96],
    "recommendation": "schedule_preventive_maintenance",
    "urgency": "high"
  }
}
```

**5. Send Notification**
```json
{
  "tool": "send_notification",
  "agent": "notifier-agent",
  "node": "factory-cloud-01",
  "params": {
    "channels": ["push", "email", "slack"],
    "recipients": ["maintenance-team", "shift-supervisor"],
    "priority": "high",
    "message": {
      "title": "Machine 3 Bearing Wear Detected",
      "body": "Vibration anomaly detected. Visual inspection confirms bearing degradation. Predicted failure in 72 hours. Maintenance scheduled.",
      "data": {
        "machine_id": "machine-03",
        "anomaly_id": "anomaly-7f3a2b1c",
        "predicted_failure_hours": 72,
        "action_url": "https://factory.example.com/maintenance/machine-03"
      }
    }
  },
  "result": {
    "sent": true,
    "delivery_ids": ["push-123", "email-456", "slack-789"]
  }
}
```

### Intent Chain

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ INTENT CHAIN: Factory Anomaly Response                                        │
└──────────────────────────────────────────────────────────────────────────────┘

[1] investigate_anomaly
    │   Origin: threshold-watcher @ factory-edge-01
    │   Routed to: anomaly-agent @ factory-ml-01
    │   Semantic match: 0.94 (anomaly_detection capability)
    │
    ├──► [2] capture_visual_evidence
    │        Origin: anomaly-agent @ factory-ml-01
    │        Routed to: camera-controller @ factory-edge-01
    │        Semantic match: 0.91 (camera capability)
    │        Result: Frame captured
    │
    ├──► [3] analyze_visual_data
    │        Origin: anomaly-agent @ factory-ml-01
    │        Routed to: vision-agent @ factory-ml-01 (local)
    │        Semantic match: 0.96 (vision capability)
    │        Result: Bearing degradation confirmed
    │
    ├──► [4] predict_time_to_failure
    │        Origin: anomaly-agent @ factory-ml-01
    │        Routed to: predictor-agent @ factory-ml-01 (local)
    │        Semantic match: 0.88 (prediction capability)
    │        Result: 72 hours estimated
    │
    └──► [5] alert_and_schedule
             Origin: anomaly-agent @ factory-ml-01
             Routed to: notifier-agent @ factory-cloud-01
             Semantic match: 0.92 (notification capability)
             │
             ├──► [5a] send_notification
             │         Tool call: push, email, slack
             │
             ├──► [5b] create_maintenance_ticket
             │         Creates CMMS work order
             │
             └──► [5c] initiate_parts_order
                       Checks inventory, orders bearing if needed

[BACKGROUND - Async]

[6] store_anomaly_data
    Origin: notifier-agent @ factory-cloud-01
    Routed to: storage @ factory-cloud-01 (local)
    Purpose: Time-series storage for model training

[7] retrain_model (T+24h)
    Origin: scheduler @ factory-cloud-01
    Routed to: trainer-agent @ factory-cloud-01
    Purpose: Improve prediction accuracy with new data
```

### Failure Modes & Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| **Jetson offline** | No heartbeat from factory-edge-01 | Cloud alerts ops team. Sensors buffer locally (4h). Failover to backup gateway if available. |
| **Dell WS overloaded** | Latency >1s on intent routing | Intent queued. Cloud LLM used as fallback (higher latency but functional). |
| **Network partition** (edge↔cloud) | No ack from cloud within 5s | Edge operates autonomously. Local notification (on-site alarm). Sync when reconnected. |
| **False positive** | Human feedback via mobile app | Feedback stored. Model retrained with corrected label. Threshold adjusted. |
| **Camera failure** | Frame capture timeout | Anomaly classified without visual. Lower confidence noted. Adjacent cameras tried. |
| **Sensor drift** | Gradual baseline shift | Baseline auto-recalibrated weekly. Alert if drift exceeds 10%. |

---

## Scenario 2: Personal Assistant Query

### Overview
User asks their phone a question about a past decision. The system routes between phone, home server, and cloud to find the answer in personal notes and synthesize a response.

### Infrastructure

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              USER DEVICE                                      │
│  ┌────────────────────────────────────────────────────────────┐              │
│  │                    IPHONE (Local Node)                      │              │
│  │  node_id: user-phone-01                                     │              │
│  │  capabilities: [voice_input, local_llm, tts, display]       │              │
│  │                                                             │              │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │              │
│  │  │ Whisper     │  │ Intent      │  │ TTS         │         │              │
│  │  │ (voice→txt) │  │ Classifier  │  │ Engine      │         │              │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │              │
│  │  ┌─────────────┐                                            │              │
│  │  │ On-device   │  ← Small LLM for simple queries            │              │
│  │  │ LLM (3B)    │                                            │              │
│  │  └─────────────┘                                            │              │
│  └────────────────────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────────────────┘
                │
                │ Local network (WiFi)
                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                            HOME NETWORK                                       │
│  ┌────────────────────────────────────────────────────────────┐              │
│  │                HOME SERVER (Personal Data Node)             │              │
│  │  node_id: home-server-01                                    │              │
│  │  capabilities: [rag, calendar, notes, personal_context]     │              │
│  │                                                             │              │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │              │
│  │  │ RAG Engine  │  │ Calendar    │  │ Notes       │         │              │
│  │  │ (personal)  │  │ API         │  │ Search      │         │              │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │              │
│  │  ┌─────────────┐  ┌─────────────┐                          │              │
│  │  │ Vector DB   │  │ Local LLM   │  ← Llama 3 70B           │              │
│  │  │ (embeddings)│  │ (Ollama)    │                          │              │
│  │  └─────────────┘  └─────────────┘                          │              │
│  └────────────────────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────────────────┘
                │
                │ Internet (encrypted)
                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              CLOUD                                            │
│  ┌────────────────────────────────────────────────────────────┐              │
│  │              CLOUD SERVICES (Optional Augmentation)         │              │
│  │  node_id: user-cloud-01                                     │              │
│  │  capabilities: [web_search, advanced_llm, real_time_data]   │              │
│  │                                                             │              │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │              │
│  │  │ Web Search  │  │ Claude API  │  │ Real-time   │         │              │
│  │  │ (Brave)     │  │ (Opus)      │  │ APIs        │         │              │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │              │
│  └────────────────────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Timing Diagram

```
Time      User         Phone          Home Server       Cloud
───────────────────────────────────────────────────────────────────────────
T=0       ●─────────────────────────────────────────────────────────────────
          │ "What did I decide
          │  about the Austin trip?"
          │
T=50ms    └────►●──────────────────────────────────────────────────────────
                │ Whisper processes audio
                │ Transcript: "What did I
                │ decide about the Austin trip?"
                │
T=100ms         ●──────────────────────────────────────────────────────────
                │ Intent classifier runs
                │ Type: personal_recall
                │ Needs: rag (personal notes)
                │
T=120ms         ●──────────────────────────────────────────────────────────
                │ Creates intent:
                │ "recall personal decision"
                │
T=130ms         │──────────────►●──────────────────────────────────────────
                │               │ Semantic router receives
                │               │ Routes to: rag capability
                │               │ Match: 0.93
                │
T=150ms                         ●──────────────────────────────────────────
                                │ RAG search begins
                                │ Query embedding created
                                │
T=200ms                         ●──────────────────────────────────────────
                                │ Vector search complete
                                │ Found 3 relevant chunks:
                                │ - Note from Jan 3
                                │ - Calendar "Austin planning"
                                │ - Email thread summary
                                │
T=250ms                         ●──────────────────────────────────────────
                                │ Calendar API queried
                                │ Related events found
                                │
T=400ms                         ●──────────────────────────────────────────
                                │ Local LLM synthesizes answer
                                │ "Based on your notes from
                                │  January 3rd, you decided..."
                                │
T=450ms         ◄───────────────●──────────────────────────────────────────
                │               │ Response returned
                │               │
T=500ms         ●──────────────────────────────────────────────────────────
                │ TTS generates audio
                │
T=700ms ◄───────●──────────────────────────────────────────────────────────
        │       │ Audio plays to user
        │       │ "Based on your notes..."
        │
T=3000ms        ●──────────────────────────────────────────────────────────
        ●────►  │ User follow-up:
                │ "What are flights like?"
                │
T=3050ms        ●──────────────────────────────────────────────────────────
                │ Intent: web_search_needed
                │ (requires real-time data)
                │
T=3100ms        │──────────────────────────────►●──────────────────────────
                │                               │ Web search executes
                │                               │ "Austin flights from [city]"
                │
T=3300ms        │                               ●──────────────────────────
                │                               │ Cloud LLM summarizes
                │                               │ results with personal
                │                               │ context (dates from notes)
                │
T=3500ms        ◄───────────────────────────────●──────────────────────────
                │ Final response delivered
```

### Agent Inventory

| Agent | Node | Role | Capabilities |
|-------|------|------|--------------|
| `voice-input-agent` | Phone | Capture and transcribe speech | voice_input |
| `intent-router` | Phone | Classify query, route to best node | intent_classification |
| `rag-agent` | Home Server | Search personal documents | rag, notes, calendar |
| `synthesis-agent` | Home Server | Compose natural response | llm |
| `web-agent` | Cloud | Search web for real-time info | web_search |
| `response-agent` | Phone | Deliver answer via TTS/display | tts, display |

### Message Formats

#### Voice Input
```json
{
  "type": "voice_input",
  "source": {
    "node_id": "user-phone-01",
    "device": "iphone_microphone"
  },
  "timestamp": "2024-01-15T09:15:32.000Z",
  "audio": {
    "format": "opus",
    "sample_rate": 16000,
    "duration_ms": 2100,
    "data_uri": "atmosphere://user-phone-01/audio/voice-123"
  }
}
```

#### Intent: Personal Recall
```json
{
  "type": "intent",
  "id": "intent-personal-recall-456",
  "created_at": "2024-01-15T09:15:32.120Z",
  "origin_node": "user-phone-01",
  "intent": "recall personal decision about trip",
  "embedding": [0.12, -0.34, 0.78, ...],
  "context": {
    "transcript": "What did I decide about the Austin trip?",
    "query_type": "personal_recall",
    "entities": {
      "location": "Austin",
      "topic": "trip planning",
      "temporal": "past_decision"
    }
  },
  "constraints": {
    "prefer_local": true,
    "privacy_level": "personal",
    "max_latency_ms": 2000
  }
}
```

#### Tool Calls

**1. RAG Search**
```json
{
  "tool": "rag_search",
  "agent": "rag-agent",
  "node": "home-server-01",
  "params": {
    "query": "Austin trip decision",
    "query_embedding": [0.12, -0.34, 0.78, ...],
    "sources": ["notes", "calendar", "email_summaries"],
    "top_k": 5,
    "date_range": {
      "start": "2023-10-01",
      "end": "2024-01-15"
    }
  },
  "result": {
    "chunks": [
      {
        "source": "notes/2024-01-03-planning.md",
        "content": "Decided to do Austin trip in March instead of February. Better weather, SXSW too crowded. Will fly Southwest, stay at Hotel San Jose.",
        "relevance": 0.94,
        "timestamp": "2024-01-03T14:22:00Z"
      },
      {
        "source": "calendar/austin-planning",
        "content": "March 15-18: Austin Trip (tentative)",
        "relevance": 0.87,
        "timestamp": "2024-01-03T14:30:00Z"
      },
      {
        "source": "email_summaries/2023-12-28",
        "content": "Thread with Sarah about Austin - she suggested Hotel San Jose, mentioned good breakfast tacos nearby",
        "relevance": 0.72,
        "timestamp": "2023-12-28T10:15:00Z"
      }
    ]
  }
}
```

**2. Answer Synthesis**
```json
{
  "tool": "synthesize_answer",
  "agent": "synthesis-agent",
  "node": "home-server-01",
  "params": {
    "query": "What did I decide about the Austin trip?",
    "context_chunks": ["...RAG results..."],
    "style": "conversational",
    "max_tokens": 150
  },
  "result": {
    "answer": "Based on your notes from January 3rd, you decided to do the Austin trip in March instead of February. You mentioned the weather would be better and you wanted to avoid the SXSW crowds. You're planning to fly Southwest and stay at Hotel San Jose, which Sarah recommended. You have March 15-18 tentatively blocked on your calendar.",
    "confidence": 0.92,
    "sources_used": 3
  }
}
```

**3. Web Search (Follow-up)**
```json
{
  "tool": "web_search",
  "agent": "web-agent",
  "node": "user-cloud-01",
  "params": {
    "query": "Austin flights from Chicago March 2024",
    "search_engine": "brave",
    "max_results": 5,
    "freshness": "recent"
  },
  "result": {
    "results": [
      {
        "title": "Cheap flights to Austin from Chicago",
        "url": "https://...",
        "snippet": "Flights from $89 one-way on Southwest..."
      }
    ]
  }
}
```

### Intent Chain

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ INTENT CHAIN: Personal Assistant Query                                        │
└──────────────────────────────────────────────────────────────────────────────┘

[1] transcribe_voice_input
    │   Origin: user @ user-phone-01
    │   Handled by: voice-input-agent @ user-phone-01 (local)
    │   Result: "What did I decide about the Austin trip?"
    │
    └──► [2] classify_and_route_intent
             Origin: voice-input-agent @ user-phone-01
             Handled by: intent-router @ user-phone-01 (local)
             Classification: personal_recall
             Routing decision: home-server-01 (rag capability)
             │
             └──► [3] retrieve_personal_context
                      Origin: intent-router @ user-phone-01
                      Routed to: rag-agent @ home-server-01
                      Semantic match: 0.93 (rag capability)
                      │
                      ├──► [3a] vector_search_notes
                      │         Tool: rag_search
                      │         Result: 3 relevant chunks
                      │
                      ├──► [3b] query_calendar
                      │         Tool: calendar_search
                      │         Result: March 15-18 event
                      │
                      └──► [4] synthesize_response
                               Origin: rag-agent @ home-server-01
                               Handled by: synthesis-agent @ home-server-01
                               │
                               └──► [5] deliver_response
                                        Origin: synthesis-agent @ home-server-01
                                        Routed to: response-agent @ user-phone-01
                                        Delivered via: TTS

[FOLLOW-UP QUERY - New Chain]

[6] transcribe_follow_up
    │   "What are flights like?"
    │
    └──► [7] classify_intent
             Classification: web_search_needed
             Context enrichment: Austin, March dates
             │
             └──► [8] web_search_with_context
                      Origin: intent-router @ user-phone-01
                      Routed to: web-agent @ user-cloud-01
                      Semantic match: 0.89 (web_search)
                      Personal context injected: destination, dates
                      │
                      └──► [9] summarize_results
                               Handled by: cloud LLM
                               Combines web results with personal context
```

### Failure Modes & Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| **Home server offline** | No response within 500ms | Phone's local LLM attempts answer from cached context. If no cache, responds "I can't access your notes right now, but I can search the web." |
| **No matching documents** | RAG returns 0 results | synthesis-agent asks clarifying question: "I don't see notes about an Austin trip. Do you mean a different city, or should I search your email?" |
| **Voice not understood** | Whisper confidence <0.6 | Ask user to repeat. Show transcript for confirmation. |
| **Network down (home)** | No route to any peer | Phone operates in standalone mode with local LLM. Queue personal queries for when connectivity returns. |
| **Privacy concern** | Query contains sensitive entity | Ensure routing stays local (home-server-01). Never send personal financial/health data to cloud without explicit consent. |
| **Cloud timeout** | Web search >3s | Return partial answer from local sources. "Here's what I found locally. Web search is taking longer than usual." |

---

## Scenario 3: Multi-Device Automation

### Overview
Energy price spikes, triggering a coordinated response across smart home devices to reduce consumption and optimize battery usage.

### Infrastructure

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              SMART HOME                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Matter Fabric                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                      │   │
│   │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │   │
│   │  │    Nest     │    │   Philips   │    │   Smart     │              │   │
│   │  │  Thermostat │    │  Hue Lights │    │   Plugs     │              │   │
│   │  │  (Matter)   │    │  (Matter)   │    │  (Matter)   │              │   │
│   │  └─────────────┘    └─────────────┘    └─────────────┘              │   │
│   │                                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│                              │ Matter Controller                             │
│                              ▼                                               │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                    HOME HUB (Raspberry Pi 5)                          │  │
│   │  node_id: home-hub-01                                                 │  │
│   │  capabilities: [matter_controller, automation, local_llm]             │  │
│   │                                                                       │  │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                   │  │
│   │  │ Matter      │  │ Energy      │  │ Automation  │                   │  │
│   │  │ Bridge      │  │ Watcher     │  │ Engine      │                   │  │
│   │  └─────────────┘  └─────────────┘  └─────────────┘                   │  │
│   │  ┌─────────────┐  ┌─────────────┐                                    │  │
│   │  │ Weather     │  │ Llama 3 8B  │                                    │  │
│   │  │ Sensor      │  │ (reasoning) │                                    │  │
│   │  └─────────────┘  └─────────────┘                                    │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                              │                                               │
└──────────────────────────────┼───────────────────────────────────────────────┘
                               │
                               │ Local Network
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                            ENERGY DEVICES                                     │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                     TESLA POWERWALL                                   │   │
│   │  node_id: powerwall-01                                                │   │
│   │  capabilities: [battery_storage, grid_interface, solar]               │   │
│   │                                                                       │   │
│   │  Current State:                                                       │   │
│   │  - Battery: 85% (12.75 kWh)                                          │   │
│   │  - Solar production: 2.1 kW                                          │   │
│   │  - Grid status: connected                                             │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
                               │
                               │ Internet
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              CLOUD SERVICES                                   │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                    ENERGY PRICE API                                   │   │
│   │  Polls every 5 min                                                    │   │
│   │  Current: $0.45/kWh (SPIKE - normal: $0.12/kWh)                      │   │
│   │  Forecast: High prices until 9 PM                                     │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                    WEATHER API                                        │   │
│   │  Current: 85°F, sunny                                                 │   │
│   │  Forecast: 78°F by 8 PM                                               │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Timing Diagram

```
Time       Price API      Home Hub        Powerwall     Matter Devices    User
─────────────────────────────────────────────────────────────────────────────────
T=0        ●───────────────────────────────────────────────────────────────────
           │ Price update:
           │ $0.45/kWh
           │
T=100ms    └────►●─────────────────────────────────────────────────────────────
                 │ Energy watcher receives
                 │ Triggers: price > $0.30
                 │
T=150ms          ●─────────────────────────────────────────────────────────────
                 │ Creates intent:
                 │ "optimize energy usage"
                 │
T=200ms          ●─────────────────────────────────────────────────────────────
                 │ Local LLM reasons:
                 │ - High price for 6+ hours
                 │ - Battery at 85%
                 │ - Weather: 85°F → 78°F
                 │ - Solar producing 2.1kW
                 │
T=400ms          ●─────────────────────────────────────────────────────────────
                 │ Decision:
                 │ 1. Switch to battery
                 │ 2. Pre-cool house now
                 │ 3. Dim lights 30%
                 │ 4. Disable car charging
                 │
T=500ms          │────────►●───────────────────────────────────────────────────
                 │         │ Command: go off-grid
                 │         │ Reserve: 20%
                 │
T=600ms          │         ●───────────────────────────────────────────────────
                 │         │ Powerwall switches
                 │         │ to battery power
                 │
T=700ms          │─────────────────────────────►●──────────────────────────────
                 │                              │ Thermostat: 68°F (pre-cool)
                 │                              │ Lights: 70% brightness
                 │                              │ EV plug: charging paused
                 │
T=1000ms         ●─────────────────────────────────────────────────────────────
                 │ Sends notification intent
                 │
T=1200ms                                                                  ●─────
                                                                          │ Push:
                                                                          │ "Energy
                                                                          │ prices
                                                                          │ high.
                                                                          │ Switched
                                                                          │ to
                                                                          │ battery."
                                                                          │

T+3h             ●─────────────────────────────────────────────────────────────
                 │ Forecast check:
                 │ Price staying high
                 │ Battery at 45%
                 │
T+3h+100ms       ●─────────────────────────────────────────────────────────────
                 │ Decision: reduce AC
                 │ to preserve battery
                 │
T+3h+200ms       │─────────────────────────────►●──────────────────────────────
                 │                              │ Thermostat: 72°F
                 │                              │ (still comfortable)
                 │

T+6h             ●─────────────────────────────────────────────────────────────
                 │ Price drops to $0.10
                 │ Resume grid power
                 │ Resume car charging
                 │ Recharge Powerwall
```

### Agent Inventory

| Agent | Node | Role | Capabilities |
|-------|------|------|--------------|
| `price-watcher` | Home Hub | Monitor energy prices | api_polling |
| `weather-watcher` | Home Hub | Monitor weather | sensor_read, api_polling |
| `energy-optimizer` | Home Hub | Decide optimal strategy | llm, optimization |
| `matter-controller` | Home Hub | Control Matter devices | matter_controller |
| `powerwall-agent` | Powerwall | Manage battery | battery_control |
| `notification-agent` | Home Hub | Alert user | notification |

### Message Formats

#### Data Plane: Price Update
```json
{
  "type": "energy_price_update",
  "source": {
    "node_id": "cloud-energy-api",
    "provider": "gridstatus.io"
  },
  "timestamp": "2024-01-15T15:00:00Z",
  "data": {
    "price_kwh": 0.45,
    "currency": "USD",
    "region": "ERCOT_NORTH",
    "forecast": [
      {"hour": 16, "price": 0.48},
      {"hour": 17, "price": 0.52},
      {"hour": 18, "price": 0.45},
      {"hour": 19, "price": 0.38},
      {"hour": 20, "price": 0.22},
      {"hour": 21, "price": 0.15}
    ]
  }
}
```

#### Decision Plane: Watcher Trigger
```json
{
  "type": "watcher_trigger",
  "watcher_id": "energy-price-spike",
  "triggered_at": "2024-01-15T15:00:00.100Z",
  "condition": {
    "field": "data.price_kwh",
    "operator": "gt",
    "threshold": 0.30,
    "actual": 0.45
  },
  "context": {
    "price_ratio": 3.75,  // 0.45 / 0.12 normal
    "high_price_hours": 6,
    "current_consumption_kw": 3.2
  }
}
```

#### Intent: Energy Optimization
```json
{
  "type": "intent",
  "id": "intent-energy-opt-789",
  "created_at": "2024-01-15T15:00:00.150Z",
  "origin_node": "home-hub-01",
  "intent": "optimize home energy usage for high price period",
  "embedding": [0.45, -0.23, 0.67, ...],
  "context": {
    "trigger": "price_spike",
    "current_price": 0.45,
    "normal_price": 0.12,
    "high_price_duration_hours": 6,
    "battery_level": 0.85,
    "solar_production_kw": 2.1,
    "weather": {
      "current_temp_f": 85,
      "forecast_temp_f": 78,
      "condition": "sunny"
    },
    "occupancy": "home",
    "preferences": {
      "comfort_priority": 0.7,
      "cost_priority": 0.9,
      "min_battery_reserve": 0.20
    }
  },
  "constraints": {
    "max_latency_ms": 5000,
    "local_only": true
  }
}
```

#### Tool Calls

**1. LLM Reasoning**
```json
{
  "tool": "reason_optimization",
  "agent": "energy-optimizer",
  "node": "home-hub-01",
  "params": {
    "model": "llama3-8b",
    "prompt": "Given the context, determine optimal energy strategy...",
    "context": {
      "price_spike": true,
      "duration_hours": 6,
      "battery_kwh": 12.75,
      "battery_reserve_min": 0.20,
      "solar_kw": 2.1,
      "current_load_kw": 3.2,
      "temperature_current": 85,
      "temperature_forecast": 78
    }
  },
  "result": {
    "strategy": "battery_priority_with_precool",
    "reasoning": "With 6 hours of high prices and 12.75 kWh battery, we can cover most usage. Pre-cooling now (85°F → 68°F) while solar is producing will let us raise thermostat later. Weather cools naturally to 78°F by evening.",
    "actions": [
      {"device": "powerwall", "action": "go_off_grid", "params": {"reserve": 0.20}},
      {"device": "thermostat", "action": "set_temp", "params": {"temp_f": 68}},
      {"device": "lights", "action": "dim", "params": {"brightness": 0.70}},
      {"device": "ev_charger", "action": "pause", "params": {}}
    ],
    "estimated_savings_usd": 4.50
  }
}
```

**2. Powerwall Control**
```json
{
  "tool": "powerwall_command",
  "agent": "powerwall-agent",
  "node": "powerwall-01",
  "params": {
    "command": "set_operation_mode",
    "mode": "self_consumption",
    "backup_reserve_percent": 20,
    "grid_charging": false
  },
  "result": {
    "success": true,
    "previous_mode": "backup_only",
    "new_mode": "self_consumption",
    "grid_status": "disconnected"
  }
}
```

**3. Matter Device Control**
```json
{
  "tool": "matter_command",
  "agent": "matter-controller",
  "node": "home-hub-01",
  "params": {
    "commands": [
      {
        "device_id": "matter-thermostat-01",
        "cluster": "thermostat",
        "command": "SetpointRaiseLower",
        "params": {"mode": "cool", "amount": -7}
      },
      {
        "device_id": "matter-lights-living",
        "cluster": "level_control",
        "command": "MoveToLevel",
        "params": {"level": 178, "transition_time": 20}
      },
      {
        "device_id": "matter-plug-evcharger",
        "cluster": "on_off",
        "command": "Off",
        "params": {}
      }
    ]
  },
  "result": {
    "results": [
      {"device_id": "matter-thermostat-01", "success": true},
      {"device_id": "matter-lights-living", "success": true},
      {"device_id": "matter-plug-evcharger", "success": true}
    ]
  }
}
```

### Intent Chain

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ INTENT CHAIN: Multi-Device Energy Optimization                                │
└──────────────────────────────────────────────────────────────────────────────┘

[1] optimize_energy_usage
    │   Origin: price-watcher @ home-hub-01
    │   Trigger: price spike $0.45/kWh
    │   Handled by: energy-optimizer @ home-hub-01 (local)
    │
    ├──► [2] gather_context
    │        Tool calls (parallel):
    │        - get_battery_status → 85%, 12.75 kWh
    │        - get_weather_forecast → 85°F→78°F
    │        - get_current_loads → 3.2 kW
    │        - get_solar_production → 2.1 kW
    │
    ├──► [3] reason_strategy
    │        Local LLM determines optimal approach
    │        Result: battery_priority_with_precool
    │
    ├──► [4] execute_powerwall_actions
    │        Origin: energy-optimizer @ home-hub-01
    │        Routed to: powerwall-agent @ powerwall-01
    │        Action: go off-grid, reserve 20%
    │
    ├──► [5] execute_matter_actions
    │        Origin: energy-optimizer @ home-hub-01
    │        Routed to: matter-controller @ home-hub-01 (local)
    │        Actions: thermostat 68°F, lights 70%, EV pause
    │
    └──► [6] notify_user
             Origin: energy-optimizer @ home-hub-01
             Routed to: notification-agent @ home-hub-01
             Message: "Energy prices high. Optimizing..."

[CONTINUOUS MONITORING - Async Loop]

[7] monitor_and_adjust (every 30 min)
    │   Origin: energy-optimizer @ home-hub-01
    │   Checks: battery level, price forecast, comfort
    │
    ├──► [7a] adjust_if_needed
    │         T+3h: Battery at 45%, raise thermostat to 72°F
    │
    └──► [7b] resume_when_clear
             T+6h: Price drops to $0.10
             - Reconnect to grid
             - Resume EV charging
             - Recharge Powerwall
```

### Optimization Logic (Detailed)

```python
def optimize_energy(context):
    """
    Energy optimization decision tree
    """
    price = context.current_price
    normal = context.normal_price
    battery = context.battery_kwh
    reserve_min = context.battery_reserve_min
    solar = context.solar_production_kw
    load = context.current_load_kw
    hours_high = context.high_price_duration_hours
    
    # Calculate available battery
    usable_battery = battery * (1 - reserve_min)  # 12.75 * 0.8 = 10.2 kWh
    
    # Calculate energy needed
    net_load = load - solar  # 3.2 - 2.1 = 1.1 kW
    energy_needed = net_load * hours_high  # 1.1 * 6 = 6.6 kWh
    
    # Can we cover it?
    if usable_battery >= energy_needed:
        strategy = "full_battery"
    elif usable_battery >= energy_needed * 0.5:
        strategy = "battery_with_reduction"
    else:
        strategy = "maximum_reduction"
    
    # Weather-based pre-conditioning
    if context.weather.cooling_trend:
        # Pre-cool now while solar is available
        precool = True
        target_temp = context.preferences.min_temp - 4  # Go colder now
    else:
        precool = False
        target_temp = context.preferences.max_temp  # Raise temp to reduce AC
    
    return {
        "strategy": strategy,
        "precool": precool,
        "target_temp": target_temp,
        "battery_action": "go_off_grid",
        "estimated_savings": (price - normal) * energy_needed
    }
```

### Failure Modes & Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| **Price API down** | No update in 10 min | Use last known price + conservative estimate. Alert user. |
| **Powerwall offline** | Command timeout | Continue with Matter devices only. Grid stays connected. Alert user. |
| **Matter device unreachable** | No response to command | Retry 3x. Skip device. Continue with others. Log failure. |
| **Battery depletes early** | Level < reserve before price drops | Reconnect to grid. Pay high price. Log for future optimization. |
| **User override** | User manually adjusts thermostat | Respect user preference. Adjust strategy around new constraint. |
| **Solar drops unexpectedly** | Clouds, evening earlier | Recalculate. May reconnect to grid earlier. |

---

## Scenario 4: Security Incident Response

### Overview
Motion detected at 3 AM. Face not recognized. System coordinates cameras, analyzes threat, takes protective actions, and alerts the homeowner—all while requiring human approval for escalation.

### Infrastructure

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              PROPERTY                                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    [CAM-1]          [CAM-2]          [CAM-3]          [CAM-4]               │
│    Front           Driveway         Side Yard        Back Yard              │
│    ┌───┐           ┌───┐            ┌───┐            ┌───┐                  │
│    │ ◉ │           │ ◉ │            │ ◉ │            │ ◉ │                  │
│    └───┘           └───┘            └───┘            └───┘                  │
│      │               │                │                │                     │
│    [CAM-5]        [M-1]  [M-2]      [CAM-6]          [CAM-7]    [CAM-8]     │
│    Porch          Motion Motion     Garage           Pool        Gate       │
│    ┌───┐          ┌───┐  ┌───┐     ┌───┐            ┌───┐       ┌───┐      │
│    │ ◉ │          │ ○ │  │ ● │←    │ ◉ │            │ ◉ │       │ ◉ │      │
│    └───┘          └───┘  └───┘ │   └───┘            └───┘       └───┘      │
│                         TRIGGER!                                             │
│                                                                              │
│    Matter Sensors:                                                           │
│    [D-1] Front Door    [W-1] Living Window    [W-2] Bedroom Window          │
│    [D-2] Back Door     [D-3] Garage Door                                    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                            EDGE PROCESSING                                    │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                    LOCAL NVR (Synology)                               │   │
│   │  node_id: nvr-01                                                      │   │
│   │  capabilities: [video_record, motion_detect, person_detect]           │   │
│   │                                                                       │   │
│   │  8 camera streams @ 1080p                                            │   │
│   │  30-day rolling storage                                              │   │
│   │  Local person detection (basic)                                       │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                WORKSTATION (Face Recognition)                         │   │
│   │  node_id: security-ml-01                                              │   │
│   │  capabilities: [face_recognition, threat_assessment, llm]             │   │
│   │  GPU: RTX 3080                                                        │   │
│   │                                                                       │   │
│   │  Known faces database: 12 people (family, friends, contractors)       │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                HOME HUB (Matter Controller)                           │   │
│   │  node_id: home-hub-01                                                 │   │
│   │  capabilities: [matter_controller, automation, siren, lights]         │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              CLOUD                                            │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                NOTIFICATION SERVICE                                   │   │
│   │  node_id: cloud-notify-01                                             │   │
│   │  capabilities: [push_notification, sms, call_service]                 │   │
│   │                                                                       │   │
│   │  Emergency contacts: Owner, Spouse, Neighbor, Police (escalation)    │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Timing Diagram

```
Time       Motion     NVR          Workstation    Home Hub      Cloud       Owner
─────────────────────────────────────────────────────────────────────────────────────
T=0        ●──────────────────────────────────────────────────────────────────────
           │ M-2 triggers
           │ (side yard)
           │
T=50ms     └────►●────────────────────────────────────────────────────────────────
                 │ Motion event received
                 │ Checks: 3:14 AM, unusual
                 │
T=100ms          ●────────────────────────────────────────────────────────────────
                 │ Activates cameras:
                 │ CAM-3 (side), CAM-6 (garage)
                 │ Starts recording
                 │
T=200ms          ●────────────────────────────────────────────────────────────────
                 │ Person detected in frame
                 │ Confidence: 0.94
                 │
T=250ms          │────────►●──────────────────────────────────────────────────────
                 │         │ Face extraction begins
                 │         │ Frame quality: good
                 │         │
T=400ms                    ●──────────────────────────────────────────────────────
                           │ Face recognition complete
                           │ Result: NO MATCH
                           │ Confidence: 0.97 (definitely a face,
                           │ definitely not known)
                           │
T=450ms                    ●──────────────────────────────────────────────────────
                           │ Creates intent:
                           │ "unknown person security event"
                           │ Threat level: ELEVATED
                           │
T=500ms                    ●──────────────────────────────────────────────────────
                           │ Behavior analysis begins
                           │ Tracking movement pattern
                           │
T=600ms          │─────────●──────────────────────────────────────────────────────
                 │         │ Multi-camera correlation
                 │         │ CAM-3, CAM-6 tracking
                 │         │ Path: toward garage
                 │         │
T=700ms                    │─────────────►●────────────────────────────────────────
                           │              │ AUTOMATIC ACTIONS:
                           │              │ - Flood lights ON
                           │              │ - All doors: verify locked
                           │              │
T=800ms                    │              │────────────────────►●─────────────────
                           │              │                     │ Priority alert
                           │              │                     │ sent
                           │              │                     │
T=1000ms                                                        │────────────►●───
                                                                │             │ 📱
                                                                │             │ALERT
                                                                │             │"Motion
                                                                │             │ at 3AM
                                                                │             │Unknown
                                                                │             │ person
                                                                │             │[View]"
                                                                │             │
T=1500ms                   ●──────────────────────────────────────────────────────
                           │ Person approaches garage door
                           │ Door sensor: no open attempt yet
                           │
T=2000ms                   ●──────────────────────────────────────────────────────
                           │ Person tries door handle
                           │ DOOR SENSOR: tamper detected
                           │
T=2050ms                   ●──────────────────────────────────────────────────────
                           │ Threat level: HIGH
                           │ Creates intent:
                           │ "potential intrusion attempt"
                           │
T=2100ms                   │─────────────►●────────────────────────────────────────
                           │              │ REQUIRES APPROVAL:
                           │              │ - Sound siren?
                           │              │ - Call police?
                           │              │
T=2200ms                                  │────────────────────►●─────────────────
                                          │                     │ Escalation
                                          │                     │ request sent
                                          │                     │
T=2500ms                                                        │────────────►●───
                                                                │             │ 📱
                                                                │             │URGENT
                                                                │             │"Door
                                                                │             │tamper!
                                                                │             │[Siren]
                                                                │             │[Police]
                                                                │             │[Ignore]"
                                                                │             │
T=5000ms                                                                      │
           ●──────────────────────────────────────────────────────────────────●
           │ Owner taps [Siren]                                               │
           │                                                                  │
T=5100ms                                  ●────────────────────────────────────
                                          │ Siren activated
                                          │ (loud alarm)
                                          │
T=5200ms   ●──────────────────────────────────────────────────────────────────
           │ Person flees
           │ (detected by CAM-3, CAM-8)
           │
T=6000ms                   ●──────────────────────────────────────────────────────
                           │ All clear
                           │ Person left property
                           │ Threat level: LOW
                           │
T=6100ms                                                        │────────────►●───
                                                                │             │ 📱
                                                                │             │"All
                                                                │             │ clear.
                                                                │             │Person
                                                                │             │ left.
                                                                │             │[Video]"
```

### Agent Inventory

| Agent | Node | Role | Capabilities |
|-------|------|------|--------------|
| `motion-watcher` | NVR | Detect motion, activate cameras | motion_detect |
| `person-detector` | NVR | Identify humans in frame | person_detect |
| `face-agent` | Workstation | Recognize known/unknown faces | face_recognition |
| `threat-agent` | Workstation | Assess threat level, track behavior | threat_assessment, llm |
| `security-controller` | Home Hub | Control lights, sirens, locks | matter_controller, siren |
| `notification-agent` | Cloud | Send alerts, handle escalation | push, sms, call |

### Message Formats

#### Data Plane: Motion Event
```json
{
  "type": "motion_event",
  "source": {
    "node_id": "nvr-01",
    "sensor_id": "motion-sensor-02"
  },
  "timestamp": "2024-01-15T03:14:22.000Z",
  "data": {
    "zone": "side_yard",
    "confidence": 0.91,
    "size": "person_sized",
    "direction": "toward_garage"
  }
}
```

#### Decision Plane: Security Watcher Trigger
```json
{
  "type": "watcher_trigger",
  "watcher_id": "night-motion-watch",
  "triggered_at": "2024-01-15T03:14:22.050Z",
  "condition": {
    "rules": [
      {"field": "time", "operator": "between", "value": ["23:00", "06:00"]},
      {"field": "zone", "operator": "in", "value": ["side_yard", "back_yard", "garage"]},
      {"field": "size", "operator": "eq", "value": "person_sized"}
    ]
  },
  "severity": "elevated"
}
```

#### Intent: Security Event
```json
{
  "type": "intent",
  "id": "intent-security-abc123",
  "created_at": "2024-01-15T03:14:22.450Z",
  "origin_node": "security-ml-01",
  "intent": "investigate unknown person security event",
  "embedding": [0.89, -0.12, 0.45, ...],
  "context": {
    "event_type": "unknown_person",
    "time": "03:14:22",
    "location": "side_yard",
    "face_match": false,
    "face_confidence": 0.97,
    "behavior": {
      "direction": "toward_garage",
      "speed": "walking",
      "posture": "crouched"
    },
    "threat_level": "elevated"
  },
  "constraints": {
    "max_latency_ms": 500,
    "local_processing": true
  },
  "escalation_required": ["siren", "police_call"]
}
```

#### Tool Calls

**1. Face Recognition**
```json
{
  "tool": "recognize_face",
  "agent": "face-agent",
  "node": "security-ml-01",
  "params": {
    "frame_uri": "atmosphere://nvr-01/frames/frame-security-001",
    "face_region": {"x": 120, "y": 80, "w": 64, "h": 64},
    "known_faces_db": "home_faces_v2",
    "threshold": 0.85
  },
  "result": {
    "match_found": false,
    "confidence_face_exists": 0.97,
    "best_match": {
      "name": null,
      "similarity": 0.34
    },
    "face_embedding": [0.12, -0.45, ...],
    "analysis": {
      "estimated_age": "30-45",
      "gender": "male",
      "wearing_mask": false
    }
  }
}
```

**2. Multi-Camera Tracking**
```json
{
  "tool": "track_person",
  "agent": "threat-agent",
  "node": "nvr-01",
  "params": {
    "person_embedding": [0.23, 0.67, ...],
    "cameras": ["cam-3", "cam-6", "cam-8"],
    "duration_seconds": 30
  },
  "result": {
    "track_id": "track-001",
    "path": [
      {"camera": "cam-3", "time": "03:14:22", "position": {"x": 0.3, "y": 0.5}},
      {"camera": "cam-3", "time": "03:14:25", "position": {"x": 0.5, "y": 0.4}},
      {"camera": "cam-6", "time": "03:14:28", "position": {"x": 0.2, "y": 0.6}}
    ],
    "direction": "toward_garage",
    "speed_estimate": "walking",
    "confidence": 0.88
  }
}
```

**3. Threat Assessment**
```json
{
  "tool": "assess_threat",
  "agent": "threat-agent",
  "node": "security-ml-01",
  "params": {
    "context": {
      "time_of_day": "03:14",
      "face_known": false,
      "behavior": "approaching_building",
      "door_tamper": true,
      "vehicle_present": false
    },
    "model": "threat-assessment-v3"
  },
  "result": {
    "threat_level": "high",
    "confidence": 0.91,
    "reasoning": "Unknown person at 3 AM attempting to access locked door. No vehicle (not a delivery). Behavior pattern matches prowler profile.",
    "recommended_actions": [
      {"action": "notify_owner", "priority": "immediate"},
      {"action": "sound_siren", "requires_approval": true},
      {"action": "call_police", "requires_approval": true},
      {"action": "record_all_cameras", "priority": "immediate"}
    ]
  }
}
```

**4. Security Actions (Automatic)**
```json
{
  "tool": "execute_security_actions",
  "agent": "security-controller",
  "node": "home-hub-01",
  "params": {
    "actions": [
      {
        "device": "flood_lights",
        "command": "on",
        "params": {"brightness": 100}
      },
      {
        "device": "all_doors",
        "command": "verify_locked",
        "params": {}
      },
      {
        "device": "nvr",
        "command": "record_all",
        "params": {"duration": 600}
      }
    ]
  },
  "result": {
    "flood_lights": {"success": true},
    "door_front": {"success": true, "status": "locked"},
    "door_back": {"success": true, "status": "locked"},
    "door_garage": {"success": true, "status": "locked"},
    "nvr_recording": {"success": true, "clip_id": "incident-2024-01-15-031422"}
  }
}
```

**5. Escalation Request (Requires Approval)**
```json
{
  "tool": "request_approval",
  "agent": "notification-agent",
  "node": "cloud-notify-01",
  "params": {
    "incident_id": "incident-2024-01-15-031422",
    "recipient": "owner",
    "urgency": "immediate",
    "message": {
      "title": "🚨 Door Tamper Detected",
      "body": "Unknown person tried garage door at 3:14 AM",
      "actions": [
        {"id": "siren", "label": "Sound Siren", "destructive": false},
        {"id": "police", "label": "Call Police", "destructive": false},
        {"id": "ignore", "label": "Ignore", "destructive": true}
      ],
      "video_url": "atmosphere://nvr-01/clips/incident-2024-01-15-031422",
      "timeout_seconds": 60,
      "timeout_action": "siren"
    }
  },
  "result": {
    "notification_id": "notif-456",
    "delivered": true,
    "awaiting_response": true
  }
}
```

### Intent Chain

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ INTENT CHAIN: Security Incident Response                                      │
└──────────────────────────────────────────────────────────────────────────────┘

[1] investigate_motion_event
    │   Origin: motion-watcher @ nvr-01
    │   Trigger: Motion at 3:14 AM, side yard
    │   Severity: ELEVATED
    │
    ├──► [2] activate_cameras
    │        Tool: nvr_command
    │        Cameras: CAM-3, CAM-6 activated
    │        Recording started
    │
    ├──► [3] detect_person
    │        Agent: person-detector @ nvr-01
    │        Result: Person detected, confidence 0.94
    │
    └──► [4] identify_person
             Origin: person-detector @ nvr-01
             Routed to: face-agent @ security-ml-01
             │
             ├──► [4a] extract_face
             │         Tool: face_extraction
             │         Result: Face found, good quality
             │
             └──► [4b] match_face
                      Tool: recognize_face
                      Result: NO MATCH (0.97 confidence unknown)
                      │
                      └──► [5] assess_threat
                               Origin: face-agent @ security-ml-01
                               Handled by: threat-agent @ security-ml-01
                               Threat level: ELEVATED
                               │
                               ├──► [6] automatic_response
                               │        Origin: threat-agent
                               │        Routed to: security-controller
                               │        Actions:
                               │        - Flood lights ON
                               │        - Verify doors locked
                               │        - Record all cameras
                               │
                               ├──► [7] notify_owner
                               │        Origin: threat-agent
                               │        Routed to: notification-agent
                               │        Alert sent with video link
                               │
                               └──► [8] track_person
                                        Origin: threat-agent
                                        Handled by: threat-agent
                                        Multi-camera tracking active
                                        │
                                        └──► [9] door_tamper_detected
                                                 Threat level: HIGH
                                                 │
                                                 └──► [10] escalation_request
                                                           Origin: threat-agent
                                                           Routed to: notification-agent
                                                           REQUIRES APPROVAL
                                                           │
                                                           ├──► [10a] owner_approves_siren
                                                           │         Siren activated
                                                           │
                                                           └──► [11] person_flees
                                                                     Tracked via CAM-3, CAM-8
                                                                     │
                                                                     └──► [12] all_clear
                                                                               Threat level: LOW
                                                                               Notification sent
                                                                               Incident logged
```

### Automatic vs Human-Approved Actions

| Action | Automatic | Requires Approval | Why |
|--------|-----------|-------------------|-----|
| Activate cameras | ✅ | | Non-disruptive |
| Flood lights on | ✅ | | Non-disruptive, deters intruders |
| Verify doors locked | ✅ | | Protective, no noise |
| Start recording | ✅ | | Evidence collection |
| Send alert | ✅ | | Owner needs to know |
| Sound siren | | ✅ | Loud, may be false alarm |
| Call police | | ✅ | Serious escalation |
| Unlock door (for police) | | ✅ | Security critical |
| Arm additional systems | | ✅ | May trap someone |

### Failure Modes & Recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| **Camera offline** | No heartbeat | Use adjacent cameras. Alert "Camera X offline during incident." |
| **Face recognition fails** | Timeout or error | Proceed with "unknown person" assumption. Use body tracking instead. |
| **Network down** | No route to cloud | Local siren available. Local storage continues. SMS gateway as backup. |
| **Owner doesn't respond** | Approval timeout (60s) | Default action: sound siren. Better safe than sorry at 3 AM. |
| **False positive** | Owner marks as false alarm | Log for training. Adjust motion sensitivity. Add to "known" if appropriate. |
| **Power outage** | UPS battery kick-in | Cameras on PoE switch with UPS. 2-hour backup. Cell backup for alerts. |
| **Intruder disables hub** | Hub stops responding | Dead man's switch: cloud alerts owner if hub goes silent during active incident. |

---

## Summary: Architecture Validation

These four scenarios demonstrate that the Atmosphere architecture can handle:

| Requirement | Validated By |
|-------------|--------------|
| **Multi-hop routing** | Factory: Edge→ML→Cloud, Assistant: Phone→Server→Cloud |
| **Semantic routing** | All scenarios use intent embedding for capability matching |
| **Real-time response** | Security: <1s threat assessment, Factory: <500ms anomaly detection |
| **Local-first privacy** | Assistant: Personal data stays on home server |
| **Graceful degradation** | All scenarios have failure modes with fallbacks |
| **Human-in-the-loop** | Security: Escalation requires approval |
| **Continuous learning** | Factory: Model retraining, Security: False positive feedback |
| **Cross-protocol** | Energy: Matter + REST API + custom sensors |
| **Intent chaining** | All scenarios show one intent spawning others |

### Key Design Patterns Emerged

1. **Watcher → Intent → Agent → Tool** is the fundamental flow
2. **Local processing preferred**, cloud for augmentation
3. **Automatic for reversible**, approval for irreversible
4. **Multi-sensor correlation** increases confidence
5. **Intent chains** enable complex workflows
6. **Failure modes** are first-class citizens

---

*This document proves the Internet of Intent architecture works for real-world scenarios spanning industrial, personal, home automation, and security domains.*
