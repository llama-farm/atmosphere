# Semantic Router Deep Review

**Date:** 2025-01-16  
**Reviewer:** Router Reviewer Subagent  
**Files Reviewed:**
- `atmosphere/router/semantic.py`
- `atmosphere/router/gradient.py`
- `atmosphere/router/matcher.py`
- `atmosphere/router/keywords.py`
- `atmosphere/router/scorer.py`
- `atmosphere/router/constraints.py`
- `atmosphere/router/embeddings.py`
- `atmosphere/router/intent_classifier.py`
- `atmosphere/core/capability.py`
- Android: `router/SemanticRouter.kt`
- Android: `router/HashMatcher.kt`
- Android: `router/RoutingDecision.kt`
- Android: `router/Capability.kt`

---

## 1. Routing Algorithm Explanation

### Overview

The semantic router uses a **3-tier cascade matching** system combined with **composite scoring** to route intents to capabilities:

```
┌─────────────────────────────────────────────────────────────┐
│                    ROUTING PIPELINE                          │
├─────────────────────────────────────────────────────────────┤
│  Layer 0: Intent Classification (on-device, <2ms)           │
│     ↓                                                        │
│  Step 1: Gather candidates from Gradient Table               │
│     ↓                                                        │
│  Step 2: 3-Tier Cascade Matching                             │
│     ├── Tier 1: Embedding cosine similarity (threshold 0.65) │
│     ├── Tier 2: Hash-based similarity (threshold 0.40)       │
│     └── Tier 3: Keyword Jaccard similarity (threshold 0.30)  │
│     ↓                                                        │
│  Step 3: Composite Scoring                                   │
│     ├── Semantic:   40% weight                               │
│     ├── Latency:    25% weight                               │
│     ├── Capability: 20% weight                               │
│     ├── Hop:        10% weight                               │
│     └── Cost:        5% weight                               │
│     ↓                                                        │
│  Step 4: Constraint Filtering                                │
│     ↓                                                        │
│  Step 5: Select Best + Build Explanation                     │
└─────────────────────────────────────────────────────────────┘
```

### Cascade Matching Details

#### Tier 1: Embedding Matching (Mac Only)
- Uses neural embeddings via LlamaFarm Universal or Ollama
- Model: `nomic-ai/nomic-embed-text-v1.5` (768-dim) or `nomic-embed-text` (384-dim)
- Threshold: 0.65 for pass
- Fallthrough to Tier 2 if no embeddings available or below threshold

#### Tier 2: Hash-Based Matching
- **Mac**: Uses character n-gram hashing to 384-dim vectors
  - Trigram hashing with MD5 → position in vector
  - Word unigrams with 2x weight
  - Cosine similarity between hash vectors
- **Android**: Uses 64-bit "SimHash" (Hamming distance)
  - Actually NOT a true SimHash - it's keyword-based hash mixing
  - `hash = hash XOR (keywordHash * 0x27d4eb2d)`
- Threshold: 0.40 (Mac), 0.70 for "similar" (Android)

#### Tier 3: Keyword Matching
- Extracts keywords (words ≥3 chars, excluding stopwords)
- Jaccard similarity: `|intersection| / |union|`
- Both platforms have identical stopword lists
- Threshold: 0.30 for pass

### Gradient Table

The gradient table is the core routing state:
- Maps `capability_id` → `GradientEntry`
- Entries contain: capability vector, hops, next_hop, latency, confidence
- Confidence decay: `0.95^hops` (prefer closer routes)
- TTL: 300 seconds (5 minutes)
- Max size: 1000 entries with LRU-like eviction

### Composite Scoring Formula

```python
base_score = (
    semantic_score  * 0.40 +  # From cascade matcher
    latency_score   * 0.25 +  # 1 - (latency / max_latency)
    capability_score * 0.20 + # RAG bonus, specialization bonus
    hop_score       * 0.10 +  # 0.9^hops
    cost_score      * 0.05    # 1 - (cost / $0.10)
)

# Apply penalties
final_score = base_score * (0.9^hops) * (0.5 if unreachable else 1.0)
```

---

## 2. Bugs and Inconsistencies Found

### 🔴 CRITICAL: SimHash Mismatch (Mac vs Android)

**Location:** `matcher.py` vs `HashMatcher.kt`

**Issue:** The Mac uses a **32-bit SHA256-based hash** while Android uses a **64-bit "SimHash"** - but neither is a true locality-sensitive hash!

**Mac (capability.py:115-126):**
```python
def _compute_simhash(self) -> int:
    # Uses SHA256 - NOT locality-sensitive!
    embedding_bytes = json.dumps(self.embedding).encode('utf-8')
    sha256_hash = hashlib.sha256(embedding_bytes).digest()
    return int.from_bytes(sha256_hash[:4], 'big')  # 32-bit
```

**Mac (matcher.py:114-134):**
```python
class HashEmbedder:
    # Uses n-gram hashing for similarity - different approach
    def embed(self, text: str) -> np.ndarray:
        for i in range(len(text) - 2):
            ngram = text[i:i+3]
            h = int(hashlib.md5(ngram.encode()).hexdigest(), 16)
            pos = h % self.dimension
            vec[pos] += 1.0
```

**Android (HashMatcher.kt:180-188):**
```kotlin
fun computeKeywordHash(keywords: List<String>): Long {
    // Simple XOR mixing - NOT SimHash!
    keywords.forEach { keyword ->
        val kHash = keyword.lowercase().hashCode().toLong()
        hash = hash xor (kHash * 0x27d4eb2d)
    }
    return hash
}
```

**Impact:** Cross-platform hash comparison will NOT work. A capability registered on Mac cannot be hash-matched on Android.

**Recommendation:** Implement consistent SimHash algorithm on both platforms:
1. Use proper 64-bit SimHash based on text n-grams
2. Or use MinHash for set similarity
3. Ensure bit-level compatibility

---

### 🔴 CRITICAL: Hash Type Mismatch (32-bit vs 64-bit)

**Issue:** Python uses 32-bit hashes, Android uses 64-bit.

**Mac (capability.py:116):**
```python
embedding_hash: int = 0  # 32-bit SHA256 hash
```

**Android (CapabilityAnnouncement.kt):**
```kotlin
val embeddingHash: Long = 0L  // 64-bit
```

**Impact:** Serialization/deserialization between platforms will truncate hashes.

---

### 🟡 MEDIUM: Cascade Matching Logic Bug

**Location:** `semantic.py:242-280` (`_gather_candidates`)

**Issue:** The cascade matcher is called once per gradient entry, but the matcher finds the **best overall match**, not the score for that specific entry.

```python
for entry in self.gradient_table.all_entries():
    # BUG: This matches the intent against ALL capabilities,
    # not just this entry!
    match_result, _ = self.matcher.match(
        intent_text=intent,
        intent_embedding=intent_embedding,
    )
    
    if match_result.capability_id != entry.capability_id:
        # This entry didn't win - gets fallback score
        semantic_score = 0.1  # LOW score
```

**Impact:** Capabilities that don't win the global match get artificially low scores (0.1), even if they have good semantic similarity.

**Recommendation:** Change to per-capability scoring:
```python
semantic_score = self.matcher.score_capability(intent, entry.capability_id)
```

---

### 🟡 MEDIUM: Duplicate Hop Penalty

**Location:** `scorer.py:186-190`

**Issue:** Hop penalty is applied twice - once in `hop_score` and again in `compute_composite`:

```python
# First application
candidate.hop_score = self.hop_penalty_factor ** candidate.hops  # 0.9^hops

# Second application (!)
for _ in range(candidate.hops):
    base_score *= hop_penalty_factor  # Another 0.9^hops
```

**Impact:** A 3-hop route gets penalized by `0.9^6 = 0.53` instead of `0.9^3 = 0.73`.

---

### 🟡 MEDIUM: Inconsistent Embedding Dimensions

**Location:** `embeddings.py` vs `matcher.py`

**Issue:** 
- `EmbeddingEngine` uses 768-dim embeddings (nomic-embed-text-v1.5)
- `HashEmbedder` uses 384-dim hash vectors
- `GradientEntry` creates zero vectors of 384-dim

```python
# gradient.py
capability_vector=np.zeros(384)  # Mismatch with 768-dim embeddings!
```

**Impact:** Vector operations may fail or produce incorrect results.

---

### 🟢 MINOR: Fail-Safe Returns All Candidates

**Location:** `constraints.py:167-171`

**Issue:** When all candidates are filtered out, the code returns the **original unfiltered list**:

```python
if not filtered:
    logger.warning("All candidates filtered out. Returning original list.")
    return candidates  # Returns candidates that DON'T meet constraints!
```

**Impact:** Constraints can be silently ignored.

---

### 🟢 MINOR: Keyword Duplication

**Location:** `keywords.py` and `matcher.py`

Both files contain identical `KeywordExtractor` classes with the same stopword lists. This is code duplication.

---

## 3. Performance Concerns

### Embedding Cache Size
- Cache limited to 1000 entries
- LRU-style eviction (removes oldest first)
- **Concern:** High-traffic scenarios could cause cache thrashing

### Gradient Table Rebuilds
- Vector index rebuilds on every `_rebuild_index()` call
- Uses `np.stack()` which allocates new memory
- **Concern:** Memory pressure with large capability sets

### Intent Classification Regex
- 15+ compiled regex patterns checked on every intent
- **Concern:** Could be slow for very long intents

### Android Hash Computation
- `computeKeywordHash` uses Java's `hashCode()` which is 32-bit
- Multiplied by magic number, XOR'd - potential for collisions

---

## 4. Mac vs Android Differences

| Feature | Mac (Python) | Android (Kotlin) |
|---------|--------------|------------------|
| **Embedding** | LlamaFarm/Ollama neural embeddings | None (hash+keywords only) |
| **Hash Type** | 32-bit SHA256 OR 384-dim n-gram vectors | 64-bit keyword XOR hash |
| **SimHash** | Not true SimHash (SHA256-based) | Not true SimHash (keyword-based) |
| **Keyword Stopwords** | 91 words | 58 words |
| **Thresholds** | 0.65/0.40/0.30 | 0.95/0.70/0.30 (different!) |
| **Scoring Weights** | Identical (0.40/0.25/0.20/0.10/0.05) | Identical ✓ |
| **Constraints** | Full set | Full set ✓ |
| **Gradient Table** | Thread-safe with RLock | Via GossipManager |
| **Capability Cache** | 1000 embeddings | 1000 embeddings ✓ |

### Threshold Differences

**Mac:**
```python
EMBEDDING_MIN_SCORE = 0.65
HASH_MIN_SCORE = 0.40
KEYWORD_MIN_SCORE = 0.30
```

**Android:**
```kotlin
// Hash matching
if (hashScore >= 0.95f) HASH_EXACT
else if (hashScore >= 0.70f) HASH_SIMILAR  // Different!

// Keyword matching
if (keywordScore >= 0.80f) KEYWORD_EXACT   // Different!
else if (keywordScore >= 0.30f) KEYWORD_OVERLAP
```

---

## 5. Edge Case Analysis

### ✅ No Capabilities
```python
# semantic.py:200
if not candidates:
    return RouteResult(action=RouteAction.NO_MATCH, ...)
```
**Status:** Handled correctly

### ✅ Expired Capabilities
```python
# gradient.py:120
def all_entries(self) -> List[GradientEntry]:
    return [e for e in self._entries.values() if not e.is_expired()]
```
**Status:** Expired entries filtered out

### ⚠️ All Capabilities Filtered
```python
# constraints.py:167
if not filtered:
    return candidates  # Returns unfiltered!
```
**Status:** Fail-safe behavior may violate user constraints

### ✅ Embedding Unavailable
```python
# semantic.py:62
if not self._embedding_available:
    # Falls back to hash+keyword matching
```
**Status:** Graceful degradation

---

## 6. Recommended Improvements

### High Priority

1. **Unified Hash Algorithm**
   - Implement proper 64-bit SimHash on both platforms
   - Use consistent text preprocessing (lowercase, tokenization)
   - Test cross-platform hash matching

2. **Fix Double Hop Penalty**
   - Remove one of the hop penalty applications in `scorer.py`

3. **Fix Cascade Matching Bug**
   - Score each capability individually, not via global match

4. **Standardize Thresholds**
   - Use same threshold values on Mac and Android
   - Document the thresholds clearly

### Medium Priority

5. **Embedding Dimension Consistency**
   - Use consistent embedding dimension (768 or 384)
   - Update gradient table zero-vector size

6. **Remove Code Duplication**
   - Consolidate `KeywordExtractor` into single module

7. **Improve Fail-Safe Behavior**
   - Add option for strict constraint enforcement
   - Return empty list instead of bypassing constraints

### Low Priority

8. **Performance Optimizations**
   - Batch capability scoring in `_gather_candidates`
   - Lazy index rebuilding in gradient table
   - Compile regex patterns once at module level

9. **Better Logging**
   - Add timing metrics for routing decisions
   - Log cascade tier hit rates

10. **Test Coverage**
    - Add unit tests for hash compatibility
    - Add integration tests for cross-platform routing

---

## 7. Summary

The semantic router is well-architected with a clean separation of concerns:
- Intent classification → Cascade matching → Composite scoring → Constraint filtering

**Main Issues:**
1. **Hash incompatibility** between Mac and Android is the most critical issue
2. **Double hop penalty** over-penalizes remote routes
3. **Cascade matching bug** gives non-winners artificially low scores
4. **Threshold differences** may cause inconsistent routing behavior

**Strengths:**
- Clean 3-tier cascade design with graceful degradation
- Comprehensive constraint system
- Good logging and explanation generation
- Consistent scoring weights across platforms

**Recommendation:** Focus on fixing the hash incompatibility first, as this prevents cross-platform capability matching entirely. The other bugs are less severe but should be addressed before production use.
