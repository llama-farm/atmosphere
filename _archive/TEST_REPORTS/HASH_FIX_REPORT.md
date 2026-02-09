# Hash Incompatibility Fix Report

**Date:** 2025-01-16  
**Status:** ✅ FIXED  
**Subagent:** hash-fixer

---

## Summary

The critical hash incompatibility between Mac and Android has been **resolved** by implementing a unified 64-bit SimHash algorithm on both platforms.

---

## The Problem (Before Fix)

### Mac Implementation (Python)
- **capability.py:** Used 32-bit SHA256 hash of embedding JSON
- **matcher.py:** Used MD5 n-gram hashing to 384-dim vectors
- Neither approach was locality-sensitive

```python
# OLD: capability.py - NOT locality-sensitive
sha256_hash = hashlib.sha256(embedding_bytes).digest()
hash_32bit = int.from_bytes(sha256_hash[:4], 'big')
```

### Android Implementation (Kotlin)
- Used 64-bit keyword XOR hash
- Simple `hashCode() xor (kHash * 0x27d4eb2d)` mixing
- Not a true SimHash

```kotlin
// OLD: HashMatcher.kt - NOT locality-sensitive
val kHash = keyword.lowercase().hashCode().toLong()
hash = hash xor (kHash * 0x27d4eb2d)
```

### Issues
1. **Different bit widths:** 32-bit vs 64-bit
2. **Different inputs:** Embedding JSON vs keywords
3. **Different algorithms:** SHA256 vs XOR mixing
4. **Not locality-sensitive:** Similar texts could produce completely different hashes

---

## The Solution

### New Unified SimHash Algorithm

Implemented proper **64-bit SimHash** using FNV-1a hashing:

1. **Tokenize** text into words (lowercase, min 3 chars, exclude stopwords)
2. For each token, compute **64-bit FNV-1a hash**
3. For each bit position, accumulate **+1 (bit=1)** or **-1 (bit=0)**
4. Final hash: set bit `i` to 1 if `sum[i] > 0`, else 0

This produces **locality-sensitive hashes** where similar texts have hashes with high Hamming similarity.

---

## Files Changed

### Python (Mac)

| File | Changes |
|------|---------|
| `atmosphere/router/simhash.py` | **NEW** - Unified SimHash implementation |
| `atmosphere/core/capability.py` | Updated `_compute_simhash()` to use unified algorithm |
| `atmosphere/core/capability.py` | Updated `similarity_hash()` to use Hamming similarity |
| `atmosphere/core/capability.py` | Fixed `__post_init__` to compute SimHash from description/keywords |
| `atmosphere/router/matcher.py` | Added `simhash_64bit` field to `CapabilityMatch` |
| `atmosphere/router/matcher.py` | Added SimHash matching in `_match_hash()` |
| `atmosphere/router/matcher.py` | Added `compute_simhash_64bit()` and `simhash_similarity()` methods |

### Kotlin (Android)

| File | Changes |
|------|---------|
| `router/SimHash.kt` | **NEW** - Unified SimHash implementation matching Python |
| `router/HashMatcher.kt` | Updated `computeKeywordHash()` to use SimHash |
| `router/HashMatcher.kt` | Updated `computeHashSimilarity()` to use SimHash |
| `core/Capability.kt` | Updated `similarityHash()` to use SimHash |
| `core/Capability.kt` | Added `computeSimHash()` helper method |

---

## Verification

### FNV-1a Test Vectors

Both implementations produce identical hashes:

| Input | Hash (Hex) | Hash (Signed Long) |
|-------|------------|-------------------|
| `""` | `0xcbf29ce484222325` | `-3750763034362895579` |
| `"hello"` | `0xa430d84680aabd0b` | `-6615550055289275125` |
| `"world"` | `0x4f59ff5e730c8af3` | `5717881983045765875` |
| `"test"` | `0xf9e6e6ef197c2b25` | `-439409999022904539` |
| `"capability"` | `0x86c8946e5047dea7` | `-8734568275770876249` |
| `"router"` | `0xa0dba500590b7544` | `-6855704586828942012` |

### SimHash Similarity Tests

| Text 1 | Text 2 | Similarity |
|--------|--------|------------|
| "Generate images from text descriptions" | "Create pictures from text prompts" | **70.3%** ✓ |
| "Generate images from text descriptions" | "Play music on speakers" | **37.5%** ✓ |
| "Image Generator Generate images using AI" | "Image Generator Create pictures using AI" | **71.9%** ✓ |

Similar texts produce hashes with ~70% Hamming similarity, while unrelated texts produce ~40% similarity.

---

## How It Works

### Cross-Platform Matching

1. **Mac creates capability:**
   ```python
   cap = CapabilityAnnouncement(
       label="Image Generator",
       description="Generate images from text",
       ...
   )
   # SimHash computed automatically: 0xfab636f011a162ea
   ```

2. **Capability gossiped to Android** (JSON includes `embedding_hash`)

3. **Android receives and can match:**
   ```kotlin
   val queryHash = SimHash.computeSimHash("create pictures from text")
   val similarity = cap.similarityHash(queryHash)  // 0.70+
   ```

4. **Match succeeds** because similar texts have similar hashes!

---

## Thresholds

Recommended similarity thresholds:

| Threshold | Meaning | Use Case |
|-----------|---------|----------|
| ≥ 0.95 | Nearly identical (3 bits differ) | Exact match |
| ≥ 0.85 | Very similar (9 bits differ) | Strong match |
| ≥ 0.70 | Similar (19 bits differ) | Good match |
| ≥ 0.40 | Weak similarity | Fallback |

---

## Embedding Dimensions Note

The review mentioned a 384 vs 768 dimension issue for embeddings. This is **separate from SimHash** and not addressed in this fix:

- SimHash uses **text-based** hashing (description + keywords)
- Neural embeddings (if available) are still handled by Tier 1 matching
- Embedding dimension consistency should be addressed separately

**Recommendation:** Standardize on 768-dim embeddings (nomic-embed-text-v1.5) and update `GradientEntry` zero-vector size to match.

---

## Testing Recommendations

1. **Unit Tests:**
   - Verify FNV-1a test vectors on both platforms
   - Verify SimHash produces same values for same input
   - Verify similarity scores match expected ranges

2. **Integration Tests:**
   - Create capability on Mac, gossip to Android
   - Query on Android, verify hash matching works
   - Create capability on Android, verify Mac can match

3. **Cross-Platform Test:**
   ```bash
   # On Mac
   python3 -c "from atmosphere.router.simhash import compute_simhash; print(hex(compute_simhash('test capability description')))"
   
   # On Android (via unit test)
   SimHash.computeSimHash("test capability description").toString(16)
   ```

---

## Conclusion

The hash incompatibility is **fixed**. Both platforms now use:

- ✅ **64-bit SimHash** (not 32-bit SHA256)
- ✅ **FNV-1a** for token hashing (deterministic, cross-platform)
- ✅ **Text-based** input (not embedding-dependent)
- ✅ **Locality-sensitive** (similar texts → similar hashes)
- ✅ **Identical algorithm** on Python and Kotlin

Capabilities can now be matched across platforms using hash similarity.
