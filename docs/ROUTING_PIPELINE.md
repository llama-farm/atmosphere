# Routing Pipeline - Phase 3 Architecture

## Overview

The refactored semantic router uses a unified pipeline for ALL capabilities (local + remote).

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        ROUTING PIPELINE                          │
└─────────────────────────────────────────────────────────────────┘

  INPUT: "Write a Python function to sort a list"
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 0: Intent Classification (THE CROWN JEWEL)                │
│ ─────────────────────────────────────────────────────────────── │
│  • Complexity: MODERATE                                          │
│  • Task Type: code                                               │
│  • Recommended Model: small                                      │
│  • Requires RAG: false                                           │
│  • Latency Sensitive: false                                      │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Gather Candidates from Gradient Table                   │
│ ─────────────────────────────────────────────────────────────── │
│  Gradient Table (ALL capabilities):                              │
│    • llm-code @ node-laptop (hops=0, local)                     │
│    • llm-general @ node-laptop (hops=0, local)                  │
│    • llm-rag @ node-server (hops=1, remote)                     │
│    • llama-expert @ node-desktop (hops=2, remote)               │
│    • embedding @ node-laptop (hops=0, local)                    │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: 3-Tier Cascade Matching (matcher.py)                    │
│ ─────────────────────────────────────────────────────────────── │
│  Tier 1: Embedding Match                                         │
│    └─→ Cosine similarity with neural embeddings                 │
│        ├─ llm-code: 0.89 ✓ (>= 0.65 threshold)                  │
│        ├─ llm-general: 0.72 ✓                                    │
│        └─ llm-rag: 0.68 ✓                                        │
│  ─────────────────────────────────────────────────────────────── │
│  Tier 2: Hash Match (if Tier 1 fails)                           │
│    └─→ Hash-based similarity (32-bit hash + vector)             │
│        └─ (not used, Tier 1 succeeded)                          │
│  ─────────────────────────────────────────────────────────────── │
│  Tier 3: Keyword Match (if Tier 2 fails)                        │
│    └─→ Keyword overlap (Jaccard similarity)                     │
│        └─ (not used, Tier 1 succeeded)                          │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Composite Scoring (scorer.py)                           │
│ ─────────────────────────────────────────────────────────────── │
│  For each candidate, compute:                                    │
│                                                                  │
│  llm-code @ node-laptop:                                         │
│    • semantic_score = 0.89 * 0.40 = 0.356                       │
│    • latency_score  = 1.00 * 0.25 = 0.250 (local = best)        │
│    • capability_score = 0.95 * 0.20 = 0.190                     │
│      └─ +0.15 RAG bonus                                          │
│      └─ +0.20 specialization bonus (code match)                 │
│    • hop_score = 1.00 * 0.10 = 0.100 (0 hops)                   │
│    • cost_score = 1.00 * 0.05 = 0.050 (free)                    │
│    ────────────────────────────────────                          │
│    COMPOSITE = 0.946                                             │
│                                                                  │
│  llm-general @ node-laptop:                                      │
│    • semantic = 0.72 * 0.40 = 0.288                             │
│    • latency  = 1.00 * 0.25 = 0.250                             │
│    • capability = 0.70 * 0.20 = 0.140                           │
│    • hop = 1.00 * 0.10 = 0.100                                  │
│    • cost = 1.00 * 0.05 = 0.050                                 │
│    ────────────────────────────────────                          │
│    COMPOSITE = 0.828                                             │
│                                                                  │
│  llm-rag @ node-server:                                          │
│    • semantic = 0.68 * 0.40 = 0.272                             │
│    • latency  = 0.98 * 0.25 = 0.245 (50ms)                      │
│    • capability = 0.80 * 0.20 = 0.160 (RAG bonus)               │
│    • hop = 0.90 * 0.10 = 0.090 (1 hop)                          │
│    • cost = 1.00 * 0.05 = 0.050                                 │
│    ────────────────────────────────────                          │
│    COMPOSITE = 0.817                                             │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Constraint Filtering (constraints.py)                   │
│ ─────────────────────────────────────────────────────────────── │
│  Constraints: {prefer_local: true}                               │
│                                                                  │
│  Before: [llm-code, llm-general, llm-rag, llama-expert, ...]    │
│  After:  [llm-code, llm-general] ← kept 2 local                 │
│                                                                  │
│  Log: "Filtered 5 → 2 candidates: prefer_local (kept 2 local)"  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Rank & Select Best                                      │
│ ─────────────────────────────────────────────────────────────── │
│  Sorted by composite score:                                      │
│    1. llm-code @ node-laptop (0.946) ← SELECTED                 │
│    2. llm-general @ node-laptop (0.828)                         │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ OUTPUT: RouteResult                                              │
│ ─────────────────────────────────────────────────────────────── │
│  action: PROCESS_LOCAL                                           │
│  capability_id: node-laptop:llm-code                             │
│  capability_label: llm-code                                      │
│  node_id: node-laptop                                            │
│  semantic_score: 0.89                                            │
│  composite_score: 0.946                                          │
│  hops: 0                                                         │
│  estimated_latency_ms: 1.0                                       │
│  is_local: true                                                  │
│  match_method: EMBEDDING                                         │
│                                                                  │
│  reason: "Routed to llm-code@node-laptop because:                │
│           semantic=0.89 (embedding), latency=1ms, has_rag=true,  │
│           specialization=code,programming, hops=0, cost=$0.00,   │
│           composite=0.946"                                       │
│                                                                  │
│  score_breakdown: {                                              │
│    semantic: 0.89,                                               │
│    latency: 1.00,                                                │
│    capability: 0.95,                                             │
│    hop: 1.00,                                                    │
│    cost: 1.00                                                    │
│  }                                                               │
│                                                                  │
│  intent_classification: {                                        │
│    complexity: "MODERATE",                                       │
│    task_type: "code",                                            │
│    recommended_model_size: "small"                               │
│  }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

## Key Benefits

### 1. Unified Gradient Table
- **Before:** Local capabilities in separate dict, remote in gradient table
- **After:** ALL capabilities in gradient table (local have hops=0)
- **Benefit:** Single source of truth, consistent treatment

### 2. 3-Tier Cascade
- **Tier 1:** Neural embeddings (best quality)
- **Tier 2:** Hash-based (fast, no ML deps)
- **Tier 3:** Keywords (always works)
- **Benefit:** Routing works even without embeddings

### 3. Composite Scoring
- Balances 5 factors: semantic, latency, capability, hops, cost
- Each factor scored 0-1, then weighted
- **Benefit:** Holistic decision making, not just semantic match

### 4. Flexible Constraints
- Can filter by latency, locality, RAG, model size, hops, etc.
- Fail-safe: returns original list if all filtered
- **Benefit:** Easy to create routing policies

### 5. Detailed Logging
- Every step logged with context
- Score breakdown shows WHY a route was chosen
- **Benefit:** Debuggable, explainable routing decisions

## Example Logs

### Simple Case
```
🎯 INTENT: TRIVIAL (general) → tiny
📊 Gathered 3 candidates from gradient table
📊 Top candidates for 'What's the capital of France?':
  1. llm-general @ node-lap (score=0.812)
✅ ROUTED to llm-general @ node-lap: semantic=0.92 (hash), latency=1ms, ...
```

### With Constraints
```
🎯 INTENT: MODERATE (code) → small
📊 Gathered 5 candidates from gradient table
🔽 Filtered 5 → 2 candidates: max_latency_ms=100 (removed 3)
📊 Top candidates for 'Write a Python function...':
  1. llm-code @ node-lap (score=0.946)
  2. llm-general @ node-lap (score=0.828)
✅ ROUTED to llm-code @ node-lap: semantic=0.89 (embedding), has_rag=true, ...
```

### Cascade Fallback
```
🎯 INTENT: COMPLEX (knowledge) → medium
📊 Gathered 4 candidates from gradient table
✓ Tier 2 (hash): llm-rag score=0.42 >= 0.40
📊 Top candidates for 'Explain quantum entanglement...':
  1. llm-rag @ node-ser (score=0.715)
✅ ROUTED to llm-rag @ node-ser: semantic=0.65 (hash), latency=50ms, has_rag=true, ...
```

## Module Breakdown

### matcher.py
- `CascadeMatcher`: Main matching class
- `KeywordExtractor`: Extract keywords from text
- `HashEmbedder`: Hash-based embedding fallback
- `MatchResult`: Result from single tier match

### scorer.py
- `RouteCandidate`: Candidate with all scoring factors
- `CompositeScorer`: Compute individual and composite scores
- `create_candidate()`: Convenience function

### constraints.py
- `RouteConstraints`: Constraint specification dataclass
- `filter_candidates()`: Apply constraints with logging
- Helper functions: `create_fast_route_constraint()`, etc.

### semantic.py
- `SemanticRouter`: Main router class (refactored)
- Uses gradient table for ALL capabilities
- Integrates matcher, scorer, constraints
- Detailed logging throughout

## Testing

See `examples/phase3_routing_example.py` for comprehensive examples.

Run with:
```bash
cd ~/clawd/projects/atmosphere
python3 examples/phase3_routing_example.py
```

## Performance Characteristics

- **Latency:** <10ms for local routing (no network calls)
- **Memory:** O(n) where n = number of capabilities in mesh
- **Scalability:** Handles 100s of capabilities efficiently
- **Fallback:** Always routes even if embeddings fail
- **Battery:** Minimal impact (hash/keyword matching is fast)
