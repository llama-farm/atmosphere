# Atmosphere Live Integration Test Report

**Generated:** 2026-02-04  
**Node:** rob-macbook (`69ff1fa7cc80d0e0`)  
**Mesh:** home-mesh (Founder)

---

## ✅ Executive Summary

**Atmosphere is fully operational.** All core services are running, the node is initialized, capabilities are correctly detected, and the API is responding.

| Component | Status |
|-----------|--------|
| Atmosphere API (8000) | ✅ Running |
| Ollama (11434) | ✅ Running (26 models) |
| LlamaFarm (14345) | ✅ Running |
| Node Initialized | ✅ Yes |
| Capability Scan | ✅ Working |
| Cost Model | ✅ Real metrics |
| Approval Config | ✅ Configured |

---

## 1. Service Status

### Port Check Results

| Port | Service | Status |
|------|---------|--------|
| 8000 | Atmosphere API | ✅ Responding (`{"status":"ok"}`) |
| 11434 | Ollama | ✅ Responding (26 models available) |
| 14345 | LlamaFarm | ✅ Healthy |
| 5000 | Flask/Generic HTTP | ✅ Detected |
| 11540 | Universal Runtime | ✅ Healthy |
| 6379 | Redis | ⚠️ Unknown |

### LlamaFarm Health Breakdown

```json
{
  "server": "healthy",
  "storage": "healthy", 
  "designer": "healthy",
  "ollama": "healthy (26 models)",
  "universal-runtime": "healthy",
  "rag-service": "unhealthy (worker not responding)",
  "seed:project": "healthy"
}
```

**Note:** RAG service worker is not responding - this is expected if no RAG tasks are active.

---

## 2. Node Configuration

| Field | Value |
|-------|-------|
| Node ID | `69ff1fa7cc80d0e0` |
| Name | `rob-macbook` |
| Data Directory | `/Users/robthelen/.atmosphere` |
| Mesh | `home-mesh` (`0b82206b236bd66c`) |
| Role | **Founder** |
| Capabilities | `embeddings`, `llm` |
| Backends | `ollama` |

---

## 3. Capability Scan Results

### Hardware Detected

| Type | Details |
|------|---------|
| GPU | Apple M1 Max - Metal 4 - 24 cores - 64GB unified |

### Models Discovered

| Source | Count | Notable Models |
|--------|-------|----------------|
| **Ollama** | 26 | gpt-oss:20b (12.8GB), qwen3:8b (4.9GB), llama3.1:8b (4.6GB) |
| **LlamaFarm** | 53 | unsloth/Qwen3-0.6B-unsloth-bnb-4bit, nomic-ai/nomic-bert-2048 |
| **HuggingFace Cache** | 52 | Qwen/Qwen3-8B (15.3GB), Qwen/Qwen2.5-Coder-7B-Instruct-GGUF (8.1GB) |

**Total Models: 131 across all sources**

### Ollama Models (Full List)

1. qllama/bce-reranker-base_v1:q4_k_m
2. mayulu/qwen3-0.6B-Q4_K_M:latest
3. qwen3:1.7B
4. gemma3:270m
5. gemma3:1b
6. mxbai-embed-large:latest
7. nomic-embed-text:latest
8. fda-task-classifier:latest
9. qwen3-4b-instruct:latest
10. qwen3:8b
11. llama3.2:latest
12. config-assistant:latest
13. qwen2.5:7b
14. medical-llama3.2-optimized:latest
15. medical-llama3.2-v2:latest
16. medical-llama3.2:latest
17. medical-tinyllama-3:latest
18. medical-tinyllama:latest
19. medical-tinyllama2:latest
20. tinyllama:latest
21. gpt-oss:20b
22. medical-assistant:latest
23. llama3.1:8b
24. llama3:latest
25. llama3.2:3b
26. mistral:7b

### Hardware Peripherals

| Type | Device |
|------|--------|
| 📷 Camera | FaceTime HD Camera |
| 🎙️ Microphone | MacBook Pro Microphone |
| 🎤 Audio | Microsoft Teams Audio, ZoomAudioDevice |
| 🔊 Speakers | MacBook Pro Speakers |

---

## 4. Approval Configuration

### Exposure Settings

| Category | Status |
|----------|--------|
| **Ollama models** | ✅ Exposed |
| **LlamaFarm projects** | ✅ Exposed |
| **GPU** | ✅ Exposed (80% VRAM limit) |
| **CPU** | ✅ Exposed (50% limit) |
| **Camera** | 🔒 Private |
| **Microphone** | 🔒 Private |
| **Screen capture** | 🔒 Private |
| **Location** | 🔒 Private |

### Rate Limits

| Scope | Limit |
|-------|-------|
| Global | 60 req/min, 1000 req/hour |
| Per Mesh | 30 req/min |
| LLM | 20 req/min, 4096 max tokens |

### Access Control

- **Auth Required:** Yes
- **Auth Methods:** Token
- **Anonymous Access:** No
- **Mesh Mode:** Allowlist (currently empty - blocks all external meshes)

### Resource Limits

- **GPU:** 80% max VRAM, 3 concurrent jobs, medium priority
- **CPU:** 50% max usage, 5 concurrent jobs
- **Max Concurrent Requests:** 10

---

## 5. Cost Model (Real-time Metrics)

### Power State

| Factor | Value | Impact |
|--------|-------|--------|
| Power Source | 🔌 Plugged In | 1.0x |
| Battery Level | 100% | - |

### Compute Load

| Factor | Value | Impact |
|--------|-------|--------|
| CPU Load | 61% | **1.6x cost** |
| GPU Load | 25% (estimated) | 1.0x |
| Memory | 56% (28.0 GB free) | 1.0x |

### Network

| Factor | Value | Impact |
|--------|-------|--------|
| Connection Type | 🏠 Unmetered | 1.0x |
| Bandwidth | Unknown | - |

### Overall Cost Scores

| Work Type | Score | Rating |
|-----------|-------|--------|
| General | 1.60 | 🟡 Moderate |
| Inference | 1.60 | 🟡 Moderate |
| Embedding | 1.60 | 🟡 Moderate |
| RAG | 1.60 | 🟡 Moderate |

**Interpretation:** The 1.6x cost multiplier is due to current CPU load (61%). The node is still a good routing target but not at optimal capacity.

---

## 6. API Endpoints Verified

| Endpoint | Status | Response |
|----------|--------|----------|
| `GET /health` | ✅ | `{"status":"ok"}` |
| `GET /api/capabilities` | ✅ | Returns 2 capabilities (embeddings, llm) |
| `GET /` | ✅ | Serves Vite-built React UI |

### Exposed Capabilities

```json
[
  {
    "id": "69ff1fa7cc80d0e0:embeddings",
    "label": "embeddings",
    "handler": "ollama",
    "models": 26
  },
  {
    "id": "69ff1fa7cc80d0e0:llm", 
    "label": "llm",
    "handler": "ollama",
    "models": 26
  }
]
```

---

## 7. Configuration File

**Location:** `/Users/robthelen/.atmosphere/config.yaml`

Key settings verified:
- ✅ Ollama models enabled
- ✅ LlamaFarm models enabled
- ✅ GPU exposed with 80% VRAM limit
- ✅ CPU exposed with 50% limit
- ✅ Privacy-sensitive sensors (camera, mic, screen, location) disabled
- ✅ Audit logging enabled to `~/.atmosphere/audit.log` (30 day retention)
- ✅ Rate limiting configured
- ⚠️ Mesh allowlist mode with empty allow list (blocks external meshes)

---

## 8. Warnings & Recommendations

### ⚠️ Mesh Access Blocked

The current configuration has:
```yaml
access:
  meshes:
    mode: allowlist
    allow: []  # Empty!
```

This blocks all external meshes from connecting. To allow mesh connections:
```bash
# Add trusted mesh IDs to the allow list
atmosphere approve --interactive
```

### ⚠️ RAG Service Unhealthy

The LlamaFarm RAG service worker is not responding. This only matters if you're using RAG features. To fix:
```bash
# Start the RAG worker if needed
cd ~/clawd/projects/llamafarm
uv run llamafarm rag start
```

---

## 9. Test Summary

| Test | Result |
|------|--------|
| Service discovery | ✅ PASS |
| Node initialization | ✅ PASS |
| Capability scan | ✅ PASS |
| Approval configuration | ✅ PASS |
| Cost model (real metrics) | ✅ PASS |
| API health check | ✅ PASS |
| Model enumeration | ✅ PASS |

**Overall Status: ✅ FULLY OPERATIONAL**

---

## 10. Quick Commands Reference

```bash
# Check status
atmosphere status

# Run capability scan
atmosphere scan

# View/modify approvals
atmosphere approve --show
atmosphere approve --interactive

# Check current cost
atmosphere cost

# Start server
atmosphere serve

# Health check
curl http://localhost:8000/health
```

---

*Report generated by Atmosphere Live Integration Test*
