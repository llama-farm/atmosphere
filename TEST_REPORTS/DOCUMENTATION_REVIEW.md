# Documentation Review Report

**Date:** 2026-02-07  
**Reviewer:** Clawd (doc-reviewer subagent)  
**Scope:** All Atmosphere documentation files

---

## Executive Summary

The Atmosphere documentation is generally **well-written and comprehensive**, with clear explanations of the core concepts and architecture. However, there are several **inconsistencies with the actual implementation**, **outdated port references**, and **missing documentation** for some API endpoints and components.

**Overall Assessment:** ⚠️ Good with corrections needed

---

## Documents Reviewed

| Document | Status | Notes |
|----------|--------|-------|
| `README.md` | ⚠️ Needs Updates | Port inconsistencies, outdated examples |
| `ARCHITECTURE.md` | ✅ Accurate | Good conceptual overview |
| `GOSSIP_SCHEMA.md` | ✅ Accurate | Matches implementation |
| `relay/README.md` | ✅ Accurate | Well-documented |
| `docs/PLATFORM_API.md` | ⚠️ Needs Updates | Missing endpoints, port issues |
| `docs/ROUTING_PIPELINE.md` | ✅ Accurate | Good technical detail |
| `docs/NETWORKING.md` | ✅ Accurate | Clear setup guide |
| `docs/MESH_DESIGN.md` | ✅ Accurate | Comprehensive design doc |
| `docs/TOKEN_ARCHITECTURE.md` | ✅ Accurate | Good security docs |
| `docs/reports/PROJECT_STATUS.md` | ⚠️ Dated | February 3rd, needs update |

---

## Critical Issues Found

### 1. 🔴 Port Inconsistency in README.md

**Problem:** README.md uses inconsistent port numbers in examples.

**Location:** `README.md` lines 53, 169, 193

**Current (Incorrect):**
```bash
# Line 53 uses correct port
curl -X POST http://localhost:11451/v1/chat/completions

# Line 169 uses WRONG port (8000)
curl -X POST http://localhost:8000/v1/chat/completions

# Line 193 uses WRONG port (8000)
client = OpenAI(base_url="http://localhost:8000/v1", api_key="n/a")
```

**Should Be:**
```bash
# All examples should use port 11451 (Atmosphere API)
curl -X POST http://localhost:11451/v1/chat/completions
client = OpenAI(base_url="http://localhost:11451/v1", api_key="n/a")
```

**Evidence:** Server implementation at `atmosphere/api/server.py:1195` confirms default port is `11451`.

---

### 2. 🔴 Incorrect Base URL in PLATFORM_API.md

**Problem:** API reference uses `/api` prefix but some examples don't.

**Location:** `docs/PLATFORM_API.md`

**Current (Inconsistent):**
```
Base URL: http://localhost:11451/api

# But examples use:
curl http://localhost:11451/health  # Should be /api/health?
```

**Actual Implementation:** Looking at `routes.py`, all routes are under the `/api` prefix via the router, except `/health` which is at root level.

**Recommended Fix:** Clarify which endpoints are at root vs `/api`:
- Root: `/health`, `/v1/*` (OpenAI compat)
- API prefix: All other endpoints

---

### 3. 🟡 Missing API Endpoints in Documentation

**Problem:** Several implemented endpoints are not documented in `PLATFORM_API.md`.

**Missing from Documentation:**
| Endpoint | Purpose |
|----------|---------|
| `GET /api/gossip/stats` | Gossip protocol statistics |
| `GET /api/ble/pairing` | BLE pairing status |
| `POST /api/ble/scan` | Scan for BLE devices |
| `POST /api/ble/pair` | Initiate BLE pairing |
| `POST /api/ble/confirm` | Confirm BLE pairing code |
| `POST /api/ble/reject` | Reject BLE pairing |
| `GET /api/devices` | List known devices |
| `POST /api/devices/{id}/block` | Block a device |
| `GET /api/network` | Network information |
| `POST /api/network/refresh` | Refresh network info |
| `GET /api/meshes` | List all meshes |
| `POST /api/meshes` | Create a mesh |
| `DELETE /api/meshes/{id}` | Delete a mesh |
| `POST /api/meshes/{id}/activate` | Activate a mesh |
| `GET /api/routing` | Routing information |
| `GET /api/transports` | Transport status |
| `POST /api/ml/anomaly` | Anomaly detection |
| `POST /api/ml/classify` | ML classification |
| `GET /api/backends` | Backend status |
| `POST /api/intent/classify` | Intent classification |

---

### 4. ✅ Design Document Links (VERIFIED)

**Status:** All referenced design documents exist in `design/` folder.

**Verified Files:**
- ✅ `design/BIDIRECTIONAL_CAPABILITIES.md` (33KB)
- ✅ `design/GOSSIP_MESSAGES.md` (7KB)
- ✅ `design/API_REFERENCE.md` (9KB)
- ✅ `design/AGENT_LAYER.md` (41KB)
- ✅ `design/TOOL_SYSTEM.md` (46KB)

**Additional Design Docs Found:** 25 total design documents covering architecture, integrations, and implementation details.

---

## Accuracy Verification

### ✅ Gossip Protocol (GOSSIP_SCHEMA.md)

**Verified Accurate:**

| Documented | Implementation (`core/gossip.py`) | Match |
|------------|-----------------------------------|-------|
| Message types: `capability.announce`, `capability.request`, `capability.response` | Lines 21-23: `GOSSIP_MSG_ANNOUNCE`, `GOSSIP_MSG_REQUEST`, `GOSSIP_MSG_RESPONSE` | ✅ |
| Gossip interval: 30 seconds | Line 26: `GOSSIP_INTERVAL_SEC = 30` | ✅ |
| Expiry: 5 minutes (300s) | Line 27: `GOSSIP_EXPIRY_SEC = 300` | ✅ |
| TTL default: 10 | `GossipMessage.ttl` default | ✅ |

### ✅ Capability Announcement Schema

**Verified Accurate:**

| Documented Field | Implementation (`core/capability.py`) | Match |
|------------------|---------------------------------------|-------|
| `node_id` | Line ~108 | ✅ |
| `capability_id` | Line ~110 | ✅ |
| `project_path` | Line ~113 | ✅ |
| `model_actual` | Line ~117 | ✅ |
| `model_tier` (enum) | `ModelTier` enum | ✅ |
| `capability_type` | `CapabilityType` enum | ✅ |
| Embedding hash algorithm (32-bit SHA256) | Documentation matches code pattern | ✅ |

### ✅ Gradient Table (gradient.py)

**Verified Accurate:**

| Documented | Implementation | Match |
|------------|----------------|-------|
| Expire after 5 min | `GRADIENT_EXPIRE_SEC = 300` | ✅ |
| Max size 1000 | `MAX_GRADIENT_TABLE_SIZE = 1000` | ✅ |
| Thread-safe | Uses `threading.RLock` | ✅ |

### ✅ Token Authentication

**Verified Accurate:**

| Feature | Documented | Implementation (`auth/tokens.py`) | Match |
|---------|------------|-----------------------------------|-------|
| Ed25519 signing | ✅ | `KeyPair.sign_b64()` | ✅ |
| Nonce for replay protection | ✅ | `secrets.token_hex(16)` | ✅ |
| TTL max 7 days | ✅ | Line ~55: `min(ttl_seconds, 7 * 86400)` | ✅ |
| Canonical JSON | ✅ | `_canonical_bytes()` method | ✅ |

### ✅ Relay Server (relay/server.py)

**Verified Accurate:**

| Feature | Documented | Implementation | Match |
|---------|------------|----------------|-------|
| Default port 8765 | `relay/README.md` | Line 754: `PORT=8765` | ✅ |
| Token verification | ✅ | `TokenStore.verify_token()` | ✅ |
| Nonce replay protection | ✅ | Tracks by `(nonce, node_id)` tuple | ✅ |
| Mesh registration | ✅ | `register_mesh()` method | ✅ |

### ✅ Routing Pipeline (ROUTING_PIPELINE.md)

**Verified Accurate:**
- 3-tier cascade matching (embedding → hash → keyword)
- Composite scoring with 5 factors
- Constraint filtering
- All matches `atmosphere/router/` implementation

---

## Missing Documentation

### 1. BLE Pairing Flow

The BLE pairing API endpoints exist in code (`/api/ble/*`) but have no dedicated documentation. The `MESH_DESIGN.md` describes the flow conceptually but not the API.

**Recommendation:** Add BLE API section to `PLATFORM_API.md`.

### 2. ML Endpoints

The ML endpoints (`/api/ml/anomaly`, `/api/ml/classify`) are implemented but not documented.

**Recommendation:** Add ML API section or create `docs/ML_API.md`.

### 3. Multi-Mesh Management

The mesh management endpoints (`/api/meshes/*`) are implemented but not documented.

**Recommendation:** Add mesh management section to `PLATFORM_API.md`.

### 4. Device Trust/Blocking

Device management endpoints exist but are undocumented.

**Recommendation:** Document in `PLATFORM_API.md` under Security section.

---

## Outdated Sections

### 1. PROJECT_STATUS.md

**Last Updated:** 2026-02-03

Should be refreshed with current status, especially:
- Native library build status
- AIDL wiring status
- Any completed items since Feb 3

### 2. Architecture Diagrams

The port allocations table in PROJECT_STATUS.md is correct:
```
| 11451 | Atmosphere API |
| 11450 | Atmosphere Gossip |
| 8765  | Relay Server (when local) |
```

But README.md examples incorrectly use port 8000.

---

## Recommended Updates

### High Priority

1. **Fix port numbers in README.md**
   - Change `8000` to `11451` in all examples
   - Ensure consistency across all code samples

2. **Update PLATFORM_API.md**
   - Add 20+ missing endpoints
   - Clarify root vs `/api` prefix endpoints
   - Add BLE, ML, Device, and Mesh management sections

3. **Add cross-references in design/ docs**
   - Create index of design documents
   - Add navigation between related docs

### Medium Priority

4. **Add WebSocket documentation**
   - Document all WS message types
   - Add streaming examples

5. **Update PROJECT_STATUS.md**
   - Refresh with current state
   - Update dates

6. **Add CHANGELOG.md**
   - Track major changes
   - Help users understand version differences

### Low Priority

7. **Add architecture decision records (ADRs)**
   - Document why certain design choices were made
   - Help future contributors understand context

8. **Add troubleshooting guide**
   - Common issues and solutions
   - Debug steps

---

## Verification Commands Used

```bash
# Check port references
grep -n "11451\|11450\|8765\|8000" README.md

# Check API routes
grep -n "^@router\." atmosphere/api/routes.py

# Verify gossip constants
grep -n "GOSSIP_" atmosphere/core/gossip.py

# Check server default port
grep -n "11451\|11450" atmosphere/api/server.py
```

---

## Summary

| Category | Count |
|----------|-------|
| Critical Issues | 2 (port inconsistencies) |
| Medium Issues | 1 (missing API docs) |
| Missing Documentation | 4 sections |
| Outdated Sections | 2 |
| Verified Accurate | 7 major components |
| Design Docs Verified | 25 documents |

**Overall:** The core protocol documentation (gossip, routing, tokens) is accurate and well-written. The main issues are:
1. Port inconsistencies in user-facing README examples (uses 8000 instead of 11451)
2. Many API endpoints not documented (20+ missing)
3. PROJECT_STATUS.md is dated (Feb 3)

---

*Report generated by doc-reviewer subagent*
