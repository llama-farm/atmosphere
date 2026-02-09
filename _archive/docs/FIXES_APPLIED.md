# API Routes Compatibility Fixes

## Summary
Fixed field name mismatches in `atmosphere/api/routes.py` to match the new data models from Phase 1-4.

## Changes Made

### 1. Fixed `/api/capabilities` endpoint (lines ~383-391)
**Issue:** Accessing non-existent fields on `GradientEntry` objects
- `cap.id` → `cap.capability_id` ✅
- `cap.label` → `cap.capability_label` ✅
- `cap.description` → `""` (doesn't exist in GradientEntry) ✅
- `cap.handler` → `"gradient"` (doesn't exist in GradientEntry) ✅
- `cap.models` → `[]` (doesn't exist in GradientEntry) ✅
- `cap.keywords` → `[]` (doesn't exist in GradientEntry) ✅

**Before:**
```python
for cap in [entry for entry in server.router.gradient_table.all_entries() if entry.hops == 0]:
    caps.append(CapabilityInfo(
        id=cap.id,  # ❌ AttributeError
        label=cap.label,  # ❌ AttributeError
        description=cap.description,  # ❌ AttributeError
        handler=cap.handler,  # ❌ AttributeError
        models=cap.models,  # ❌ AttributeError
        keywords=list(cap.keywords) if cap.keywords else [],  # ❌ AttributeError
        source="local"
    ))
```

**After:**
```python
for cap in [entry for entry in server.router.gradient_table.all_entries() if entry.hops == 0]:
    caps.append(CapabilityInfo(
        id=cap.capability_id,  # ✅
        label=cap.capability_label,  # ✅
        description="",  # ✅ GradientEntry doesn't store description
        handler="gradient",  # ✅ Generic handler
        models=[],  # ✅ GradientEntry doesn't store models
        keywords=[],  # ✅ GradientEntry doesn't store keywords
        source="local"
    ))
```

### 2. Fixed `/api/route` endpoint RouteResult field access (lines ~168, ~188)
**Issue:** Accessing nested `result.capability.label` instead of direct `result.capability_label`

**Before:**
```python
"capability": result.capability.label if result.capability else None,  # ❌
"score": result.score,  # ❌ (should be composite_score)
```

**After:**
```python
"capability": result.capability_label,  # ✅
"score": result.composite_score,  # ✅
```

### 3. Fixed `/api/agents` endpoint (line ~1021)
**Issue:** Accessing `cap.label` on GradientEntry

**Before:**
```python
"name": cap.label,  # ❌ AttributeError
```

**After:**
```python
"name": cap.capability_label,  # ✅
```

## Data Model Reference

### GradientEntry (atmosphere/router/gradient.py)
```python
@dataclass
class GradientEntry:
    capability_id: str
    capability_label: str
    capability_vector: np.ndarray
    hops: int
    next_hop: str
    via_node: str
    estimated_latency_ms: float
    last_updated: float
    confidence: float
```

### RouteResult (atmosphere/router/semantic.py)
```python
@dataclass
class RouteResult:
    action: RouteAction
    capability_id: Optional[str]
    capability_label: Optional[str]  # Direct field, not nested!
    node_id: Optional[str]
    semantic_score: float
    composite_score: float  # Not just "score"
    hops: int
    estimated_latency_ms: float
    is_local: bool
    next_hop: Optional[str]
    via_node: Optional[str]
    # ... more fields
```

### CapabilityAnnouncement (atmosphere/core/capability.py)
```python
@dataclass
class CapabilityAnnouncement:
    node_id: str
    node_name: str
    capability_id: str
    project_path: str
    model_alias: str
    model_actual: str
    label: str  # Note: "label", not "capability_label"
    description: str
    keywords: List[str]
    # ... many more fields
```

## Testing Results

### ✅ Working Endpoints
- `GET /api/capabilities` - Returns JSON without AttributeError
- `GET /api/health` - Returns node status
- `GET /api/mesh/status` - Returns mesh info
- `GET /api/mesh/capabilities` - Returns empty array (no capabilities discovered yet)

### ⚠️  Known Separate Issue
The `/api/route` endpoint has an **embedding dimension mismatch** error in the router layer (768 vs 384 dimensions). This is a separate issue from the API routes field compatibility and should be addressed in the router/matcher layer, not in routes.py.

## Files Modified
- `atmosphere/api/routes.py` (4 locations fixed)

## Next Steps
If the embedding dimension mismatch needs to be resolved, check:
- `atmosphere/router/matcher.py` - Embedding alignment logic
- `atmosphere/router/semantic.py` - Intent embedding generation
- Ensure all embeddings use consistent dimensions (either 384 or 768)
