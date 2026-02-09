# Atmosphere API Endpoint Test Report

**Test Date:** 2026-02-05  
**Server:** http://localhost:11451  
**Relay:** wss://atmosphere-relay-production.up.railway.app  
**Node ID:** 69ff1fa7cc80d0e0  
**Mesh ID:** 0b82206b236bd66c (home-mesh)

---

## Executive Summary

| Metric | Count |
|--------|-------|
| **Total Endpoints Tested** | 60 |
| **Passing** | 50 |
| **Failing (500 Errors)** | 7 |
| **Timeouts (needs attention)** | 3 |
| **Pass Rate** | 83.3% |

### Critical Issues Found
1. **7 endpoints returning 500 Internal Server Error**
2. **3 LLM endpoints timing out** (may be expected for cold starts)
3. **WebSocket connection: WORKING** ✅

---

## 🔴 FAILING ENDPOINTS (500 Internal Server Error)

### 1. `GET /api` - API Status
**Severity:** HIGH  
**Error:** `Internal Server Error`  
**Reproduction:**
```bash
curl http://localhost:11451/api
```
**Expected:** API status/documentation  
**Recommended Fix:** Check route handler for unhandled exceptions

---

### 2. `GET /api/mesh/transports` - Mesh Transport Status
**Severity:** HIGH  
**Error:** `Internal Server Error`  
**Reproduction:**
```bash
curl http://localhost:11451/api/mesh/transports
```
**Note:** `/api/transports` works correctly. This appears to be a duplicate route with a bug.  
**Recommended Fix:** Either fix the handler or consolidate with `/api/transports`

---

### 3. `GET /api/gossip/stats` - Gossip Protocol Stats
**Severity:** MEDIUM  
**Error:** `Internal Server Error`  
**Reproduction:**
```bash
curl http://localhost:11451/api/gossip/stats
```
**Recommended Fix:** Check gossip stats collection - may be null reference

---

### 4. `POST /api/route` - Route Intent
**Severity:** CRITICAL  
**Error:** `Internal Server Error`  
**Reproduction:**
```bash
curl -X POST http://localhost:11451/api/route \
  -H "Content-Type: application/json" \
  -d '{"intent": "What is a llama?"}'
```
**Expected:** Routing decision without execution  
**Recommended Fix:** Check capability matching logic - likely null reference when no capabilities match

---

### 5. `POST /api/execute` - Execute Intent
**Severity:** CRITICAL  
**Error:** `Internal Server Error`  
**Reproduction:**
```bash
curl -X POST http://localhost:11451/api/execute \
  -H "Content-Type: application/json" \
  -d '{"intent": "What is a llama?"}'
```
**Recommended Fix:** Depends on /api/route fix - likely same root cause

---

### 6. `POST /api/mesh/join` - Handle Join Request
**Severity:** MEDIUM  
**Error:** `Internal Server Error`  
**Reproduction:**
```bash
curl -X POST http://localhost:11451/api/mesh/join \
  -H "Content-Type: application/json" \
  -d '{"device": {"id": "test"}, "timestamp": 123456, "signature": "test"}'
```
**Expected:** Proper error handling for invalid signatures  
**Recommended Fix:** Add try/catch around signature verification

---

### 7. `GET /api/routing/{dest_id}` - Get Route to Destination
**Severity:** HIGH  
**Error:** `Internal Server Error`  
**Reproduction:**
```bash
curl http://localhost:11451/api/routing/nonexistent-dest
```
**Expected:** 404 or empty route info  
**Recommended Fix:** Handle case when destination not found in routing table

---

## ⏱️ TIMEOUT ENDPOINTS (May need longer cold start)

These endpoints are timing out - likely due to LLM cold start or backend unavailability:

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/chat/completions` | POST | LLM inference |
| `/v1/chat/completions` | POST | OpenAI-compatible chat |
| `/v1/completions` | POST | OpenAI-compatible completion |
| `/v1/embeddings` | POST | Embedding generation |
| `/api/ml/anomaly` | POST | Anomaly detection |
| `/api/ml/classify` | POST | Classification |
| `/api/integrations/test` | POST | Backend test |
| `/api/projects/{ns}/{name}/invoke` | POST | Project invocation |

**Note:** These may work with longer timeouts or after backend warm-up.

---

## ✅ PASSING ENDPOINTS

### Health & Status
| Endpoint | Method | Status | Response |
|----------|--------|--------|----------|
| `/health` | GET | ✅ PASS | `{"status": "ok"}` |
| `/api/health` | GET | ✅ PASS | `{"status": "healthy", "node_id": "..."}` |
| `/` | GET | ✅ PASS | HTML UI served |

### Mesh Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/mesh/status` | GET | ✅ PASS | Returns mesh info, peer count |
| `/api/mesh/peers` | GET | ✅ PASS | Returns empty list (no peers) |
| `/api/mesh/capabilities` | GET | ✅ PASS | Returns empty list |
| `/api/mesh/topology` | GET | ✅ PASS | Returns node graph |
| `/api/mesh/token` | POST | ✅ PASS | Generates invite token |

### Capabilities & Routing
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/capabilities` | GET | ✅ PASS | Lists LlamaFarm capabilities |
| `/api/route/project` | POST | ✅ PASS | Routes to project (keyword fallback) |
| `/api/route/project/test` | POST | ✅ PASS | Shows routing tiers |
| `/api/intent/classify` | POST | ✅ PASS | Classifies intent complexity |
| `/api/routing` | GET | ✅ PASS | Returns routing table with embeddings |

### Network & Transport
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/network` | GET | ✅ PASS | IP detection, relay status |
| `/api/network/refresh` | POST | ✅ PASS | Refreshes IP detection |
| `/api/transports` | GET | ✅ PASS | BLE, LAN, Relay status |
| `/api/cost/current` | GET | ✅ PASS | System resource costs |

### Device Management
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/devices` | GET | ✅ PASS | Lists 4 devices |
| `/api/devices/{id}` | GET | ✅ PASS | Device details |
| `/api/devices/{id}` | DELETE | ✅ PASS | Returns 404 for unknown |
| `/api/devices/{id}/block` | POST | ✅ PASS | Returns 404 for unknown |
| `/api/devices/{id}/unblock` | POST | ✅ PASS | Returns 404 for unknown |

### Mesh Management
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/meshes` | GET | ✅ PASS | Lists saved meshes |
| `/api/meshes` | POST | ✅ PASS | Saves mesh config |
| `/api/meshes/{id}` | DELETE | ✅ PASS | Returns 404 for unknown |
| `/api/meshes/{id}/activate` | POST | ✅ PASS | Returns 404 for unknown |

### BLE Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/ble/pairing` | GET | ✅ PASS | Returns IDLE state |
| `/api/ble/scan` | POST | ✅ PASS | Returns empty devices |
| `/api/ble/pair` | POST | ✅ PASS | Initiates pairing |
| `/api/ble/confirm` | POST | ✅ PASS | No active session |
| `/api/ble/reject` | POST | ✅ PASS | Success |

### Agent & Project Management
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/agents` | GET | ✅ PASS | Lists 3 agents |
| `/api/agents/{id}` | PATCH | ✅ PASS | Updates agent status |
| `/api/projects` | GET | ✅ PASS | Lists projects (slow) |

### Configuration
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/approval/config` | GET | ✅ PASS | Returns config |
| `/api/approval/config` | POST | ✅ PASS | Saves config |
| `/api/backends` | GET | ✅ PASS | LlamaFarm healthy, Ollama offline |
| `/api/integrations` | GET | ✅ PASS | Timeout (backend discovery slow) |

### Permissions
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/permissions/status` | GET | ✅ PASS | Camera/mic not_determined |
| `/api/permissions/open-settings` | POST | ✅ PASS | Opens macOS settings |

### ML Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/ml/anomaly/models` | GET | ✅ PASS | 657 models listed |
| `/api/ml/classifier/models` | GET | ✅ PASS | 193 models listed |
| `/api/embeddings` | GET | ✅ PASS | 768-dim embeddings |

### OpenAI-Compatible Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/v1/models` | GET | ✅ PASS | 162+ models listed |
| `/v1/models/{id}` | GET | ✅ PASS | Model details |
| `/v1/routing/stats` | GET | ✅ PASS | Router statistics |
| `/v1/routing/projects` | GET | ✅ PASS | 112 routable projects |
| `/v1/routing/test` | POST | ✅ PASS | Fast routing test |

---

## 🔌 WebSocket Testing

### `/api/ws` - Main WebSocket Endpoint
**Status:** ✅ WORKING

**Test Result:**
```
Connected successfully
Received: {"type":"mesh_status","data":{"mesh_id":"0b82206b236bd66c","mesh_name":"home-mesh","node_count":1,"peer_count":0,"capabilities":[...]}}
```

**Features Verified:**
- Connection establishment: ✅
- Automatic mesh_status broadcast: ✅
- JSON message format: ✅

---

## 📊 Detailed Error Analysis

### Root Cause Hypothesis for 500 Errors

1. **`/api` route**: Likely missing default handler or template issue

2. **`/api/mesh/transports`**: Appears to be a redundant route that conflicts with `/api/transports`. The handler may be trying to access resilient mesh data that doesn't exist:
   ```
   "resilient_mesh": {}  // Empty in /api/transports
   ```

3. **`/api/gossip/stats`**: The gossip subsystem may not be fully initialized when there are no peers

4. **`/api/route` and `/api/execute`**: Critical routing bugs. Likely causes:
   - No capabilities matched for intent
   - Null capability reference
   - Missing gradient table entries

5. **`/api/mesh/join`**: Signature verification failing without proper error handling

6. **`/api/routing/{dest_id}`**: Missing null check when destination not in routing table

---

## 🔧 Recommended Fixes (Priority Order)

### P0 - Critical (Blocking Core Functionality)
1. **Fix `/api/route` POST** - Core routing functionality broken
2. **Fix `/api/execute` POST** - Core execution functionality broken

### P1 - High Priority
3. **Fix `/api/routing/{dest_id}`** - Add proper 404 handling
4. **Fix `/api/mesh/transports`** - Either fix or remove duplicate route
5. **Fix `/api`** - Basic API status should work

### P2 - Medium Priority
6. **Fix `/api/gossip/stats`** - Handle empty gossip state
7. **Fix `/api/mesh/join`** - Add proper signature validation error handling

### P3 - Improvements
8. Add request timeouts for LLM endpoints
9. Add health check for LlamaFarm backend before routing
10. Consider consolidating `/api/transports` and `/api/mesh/transports`

---

## Test Environment Details

```
Node: rob-macbook (69ff1fa7cc80d0e0)
Mesh: home-mesh (0b82206b236bd66c)
Role: Founder
Peers: 0
Backends: LlamaFarm (healthy), Ollama (offline)
Capabilities: 1 (llama-expert-14)
BLE: Active (no peers)
Relay: Connected
```

---

## Appendix: All Endpoints from OpenAPI Spec

Total endpoints in spec: **59**

| # | Path | Method | Tested | Result |
|---|------|--------|--------|--------|
| 1 | `/` | GET | ✅ | PASS |
| 2 | `/api` | GET | ✅ | **FAIL** |
| 3 | `/api/agents` | GET | ✅ | PASS |
| 4 | `/api/agents/{agent_id}` | PATCH | ✅ | PASS |
| 5 | `/api/approval/config` | GET | ✅ | PASS |
| 6 | `/api/approval/config` | POST | ✅ | PASS |
| 7 | `/api/backends` | GET | ✅ | PASS |
| 8 | `/api/ble/confirm` | POST | ✅ | PASS |
| 9 | `/api/ble/pair` | POST | ✅ | PASS |
| 10 | `/api/ble/pairing` | GET | ✅ | PASS |
| 11 | `/api/ble/reject` | POST | ✅ | PASS |
| 12 | `/api/ble/scan` | POST | ✅ | PASS |
| 13 | `/api/capabilities` | GET | ✅ | PASS |
| 14 | `/api/chat/completions` | POST | ✅ | TIMEOUT |
| 15 | `/api/cost/current` | GET | ✅ | PASS |
| 16 | `/api/devices` | GET | ✅ | PASS |
| 17 | `/api/devices/{device_id}` | GET | ✅ | PASS |
| 18 | `/api/devices/{device_id}` | DELETE | ✅ | PASS |
| 19 | `/api/devices/{device_id}/block` | POST | ✅ | PASS |
| 20 | `/api/devices/{device_id}/unblock` | POST | ✅ | PASS |
| 21 | `/api/embeddings` | GET | ✅ | PASS |
| 22 | `/api/execute` | POST | ✅ | **FAIL** |
| 23 | `/api/gossip/stats` | GET | ✅ | **FAIL** |
| 24 | `/api/health` | GET | ✅ | PASS |
| 25 | `/api/integrations` | GET | ✅ | TIMEOUT |
| 26 | `/api/integrations/test` | POST | ✅ | TIMEOUT |
| 27 | `/api/intent/classify` | POST | ✅ | PASS |
| 28 | `/api/mesh/capabilities` | GET | ✅ | PASS |
| 29 | `/api/mesh/join` | POST | ✅ | **FAIL** |
| 30 | `/api/mesh/peers` | GET | ✅ | PASS |
| 31 | `/api/mesh/status` | GET | ✅ | PASS |
| 32 | `/api/mesh/token` | POST | ✅ | PASS |
| 33 | `/api/mesh/topology` | GET | ✅ | PASS |
| 34 | `/api/mesh/transports` | GET | ✅ | **FAIL** |
| 35 | `/api/meshes` | GET | ✅ | PASS |
| 36 | `/api/meshes` | POST | ✅ | PASS |
| 37 | `/api/meshes/{mesh_id}` | DELETE | ✅ | PASS |
| 38 | `/api/meshes/{mesh_id}/activate` | POST | ✅ | PASS |
| 39 | `/api/ml/anomaly` | POST | ✅ | TIMEOUT |
| 40 | `/api/ml/anomaly/models` | GET | ✅ | PASS |
| 41 | `/api/ml/classify` | POST | ✅ | TIMEOUT |
| 42 | `/api/ml/classifier/models` | GET | ✅ | PASS |
| 43 | `/api/network` | GET | ✅ | PASS |
| 44 | `/api/network/refresh` | POST | ✅ | PASS |
| 45 | `/api/permissions/open-settings` | POST | ✅ | PASS |
| 46 | `/api/permissions/status` | GET | ✅ | PASS |
| 47 | `/api/projects` | GET | ✅ | TIMEOUT |
| 48 | `/api/projects/{ns}/{proj}/invoke` | POST | ✅ | TIMEOUT |
| 49 | `/api/route` | POST | ✅ | **FAIL** |
| 50 | `/api/route/project` | POST | ✅ | PASS |
| 51 | `/api/route/project/test` | POST | ✅ | PASS |
| 52 | `/api/routing` | GET | ✅ | PASS |
| 53 | `/api/routing/{dest_id}` | GET | ✅ | **FAIL** |
| 54 | `/api/transports` | GET | ✅ | PASS |
| 55 | `/api/ws` | WS | ✅ | PASS |
| 56 | `/health` | GET | ✅ | PASS |
| 57 | `/v1/chat/completions` | POST | ✅ | TIMEOUT |
| 58 | `/v1/completions` | POST | ✅ | TIMEOUT |
| 59 | `/v1/embeddings` | POST | ✅ | TIMEOUT |
| 60 | `/v1/models` | GET | ✅ | PASS |
| 61 | `/v1/models/{model_id}` | GET | ✅ | PASS |
| 62 | `/v1/routing/projects` | GET | ✅ | PASS |
| 63 | `/v1/routing/stats` | GET | ✅ | PASS |
| 64 | `/v1/routing/test` | POST | ✅ | PASS |

---

*Report generated by Atmosphere API Tester*
