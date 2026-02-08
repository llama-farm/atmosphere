"""
Unified 64-bit SimHash implementation for cross-platform capability matching.

SimHash is a locality-sensitive hashing algorithm where similar documents
produce hashes with high Hamming similarity (few differing bits).

This implementation is designed to be identical across:
- Python (Mac/Linux Atmosphere nodes)
- Kotlin/Android (mobile Atmosphere nodes)

Algorithm:
1. Tokenize text into words (lowercase, min 3 chars, no stopwords)
2. For each token, compute a stable 64-bit hash
3. For each bit position, accumulate +1 (bit=1) or -1 (bit=0) weighted by token count
4. Final hash: set bit i to 1 if sum[i] > 0, else 0

The hash function uses FNV-1a which is simple, fast, and deterministic.
"""

import re
from typing import List, Set, Tuple

# FNV-1a 64-bit constants (same values used in Kotlin implementation)
FNV64_OFFSET_BASIS = 0xcbf29ce484222325
FNV64_PRIME = 0x00000100000001B3
MASK_64 = 0xFFFFFFFFFFFFFFFF

# Stopwords - identical list used in Android
STOPWORDS: Set[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "should", "could", "may", "might", "can", "this", "that",
    "what", "which", "who", "when", "where", "why", "how", "i", "you",
    "he", "she", "it", "we", "they", "my", "your", "his", "her", "its",
    "our", "their", "all", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "no", "not", "only", "same", "so", "than",
    "too", "very", "just", "about", "into", "through", "during", "before",
    "after", "above", "below", "between", "under", "again", "further",
    "then", "once", "here", "there"
})

MIN_WORD_LENGTH = 3


def fnv1a_64(text: str) -> int:
    """
    Compute FNV-1a 64-bit hash of a string.
    
    This is a simple, fast, and deterministic hash function.
    Produces identical results across Python and Kotlin.
    
    Args:
        text: String to hash
        
    Returns:
        64-bit unsigned integer hash
    """
    h = FNV64_OFFSET_BASIS
    for char in text.encode('utf-8'):
        h ^= char
        h = (h * FNV64_PRIME) & MASK_64
    return h


def extract_tokens(text: str, max_tokens: int = 50) -> List[str]:
    """
    Extract tokens from text for SimHash computation.
    
    Uses identical logic to Android implementation:
    - Lowercase
    - Split on non-alphanumeric
    - Filter short words and stopwords
    - Deduplicate but preserve order
    
    Args:
        text: Input text
        max_tokens: Maximum number of tokens to return
        
    Returns:
        List of lowercase tokens
    """
    if not text:
        return []
    
    # Lowercase and extract words (3+ alphanumeric chars)
    words = re.findall(r'\b[a-zA-Z0-9]{3,}\b', text.lower())
    
    # Filter stopwords
    tokens = [w for w in words if w not in STOPWORDS]
    
    # Deduplicate while preserving order
    seen = set()
    unique_tokens = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            unique_tokens.append(token)
    
    return unique_tokens[:max_tokens]


def compute_simhash(text: str) -> int:
    """
    Compute 64-bit SimHash of text.
    
    SimHash produces locality-sensitive hashes where similar texts
    have hashes with high Hamming similarity (few differing bits).
    
    Args:
        text: Input text (description, keywords joined, etc.)
        
    Returns:
        64-bit unsigned integer SimHash
    """
    tokens = extract_tokens(text)
    
    if not tokens:
        return 0
    
    # Accumulator for each bit position
    bit_sums = [0] * 64
    
    for token in tokens:
        # Compute hash for this token
        token_hash = fnv1a_64(token)
        
        # For each bit position, add +1 or -1
        for i in range(64):
            if (token_hash >> i) & 1:
                bit_sums[i] += 1
            else:
                bit_sums[i] -= 1
    
    # Build final hash from sign of sums
    result = 0
    for i in range(64):
        if bit_sums[i] > 0:
            result |= (1 << i)
    
    return result


def compute_simhash_from_tokens(tokens: List[str]) -> int:
    """
    Compute 64-bit SimHash from pre-extracted tokens.
    
    Use this when you've already extracted keywords/tokens.
    
    Args:
        tokens: List of tokens (already lowercase, filtered)
        
    Returns:
        64-bit unsigned integer SimHash
    """
    if not tokens:
        return 0
    
    bit_sums = [0] * 64
    
    for token in tokens:
        token_lower = token.lower()
        token_hash = fnv1a_64(token_lower)
        
        for i in range(64):
            if (token_hash >> i) & 1:
                bit_sums[i] += 1
            else:
                bit_sums[i] -= 1
    
    result = 0
    for i in range(64):
        if bit_sums[i] > 0:
            result |= (1 << i)
    
    return result


def hamming_distance(hash1: int, hash2: int) -> int:
    """
    Compute Hamming distance between two 64-bit hashes.
    
    Hamming distance = number of differing bits.
    
    Args:
        hash1: First 64-bit hash
        hash2: Second 64-bit hash
        
    Returns:
        Number of differing bits (0-64)
    """
    xor = hash1 ^ hash2
    return bin(xor).count('1')


def simhash_similarity(hash1: int, hash2: int) -> float:
    """
    Compute similarity between two SimHashes.
    
    Returns value in [0, 1] where:
    - 1.0 = identical hashes
    - 0.0 = completely different (32 bits differ)
    
    Args:
        hash1: First 64-bit SimHash
        hash2: Second 64-bit SimHash
        
    Returns:
        Similarity score in [0, 1]
    """
    if hash1 == 0 or hash2 == 0:
        return 0.0
    
    distance = hamming_distance(hash1, hash2)
    return 1.0 - (distance / 64.0)


def is_similar(hash1: int, hash2: int, threshold: float = 0.7) -> bool:
    """
    Check if two SimHashes are similar.
    
    Args:
        hash1: First 64-bit SimHash
        hash2: Second 64-bit SimHash  
        threshold: Minimum similarity (default 0.7 = max 19 differing bits)
        
    Returns:
        True if similarity >= threshold
    """
    return simhash_similarity(hash1, hash2) >= threshold


def explain_simhash(text: str) -> str:
    """
    Generate explanation of SimHash computation for debugging.
    
    Args:
        text: Input text
        
    Returns:
        Human-readable explanation
    """
    tokens = extract_tokens(text)
    simhash = compute_simhash(text)
    
    lines = [
        f"SimHash Analysis",
        f"================",
        f"Input: {text[:100]}{'...' if len(text) > 100 else ''}",
        f"Tokens ({len(tokens)}): {', '.join(tokens[:10])}{'...' if len(tokens) > 10 else ''}",
        f"SimHash: 0x{simhash:016x}",
        f"Binary: {bin(simhash)[2:].zfill(64)}",
        "",
        "Token hashes:",
    ]
    
    for token in tokens[:5]:
        h = fnv1a_64(token)
        lines.append(f"  {token}: 0x{h:016x}")
    
    if len(tokens) > 5:
        lines.append(f"  ... and {len(tokens) - 5} more tokens")
    
    return "\n".join(lines)


# === Verification functions for cross-platform testing ===

def verify_fnv1a() -> List[Tuple[str, int]]:
    """
    Return test vectors for FNV-1a verification.
    
    These exact values should be produced by both Python and Kotlin.
    """
    test_cases = [
        ("", FNV64_OFFSET_BASIS),  # Empty string = offset basis
        ("hello", 0xa430d84680aabd0b),
        ("world", 0x9a50a0067e4bcf0b),
        ("test", 0xd38f1a5f83c343e9),
        ("capability", 0xe38b6d21d9a80c9b),
        ("router", 0xe78e68f7e3a9b4e2),
    ]
    return test_cases


def verify_simhash() -> List[Tuple[str, int]]:
    """
    Return test vectors for SimHash verification.
    
    These exact values should be produced by both Python and Kotlin.
    """
    return [
        ("hello world", compute_simhash("hello world")),
        ("The quick brown fox jumps over the lazy dog",
         compute_simhash("The quick brown fox jumps over the lazy dog")),
        ("Machine learning for natural language processing",
         compute_simhash("Machine learning for natural language processing")),
    ]


if __name__ == "__main__":
    # Run verification
    print("FNV-1a Test Vectors:")
    for text, expected in verify_fnv1a():
        actual = fnv1a_64(text)
        status = "✓" if actual == expected else "✗"
        print(f"  {status} '{text}' -> 0x{actual:016x} (expected 0x{expected:016x})")
    
    print("\nSimHash Examples:")
    texts = [
        "Generate images from text descriptions using AI",
        "Create pictures from text using artificial intelligence",
        "Play music on speakers",
    ]
    
    hashes = [(t, compute_simhash(t)) for t in texts]
    
    for text, h in hashes:
        print(f"\n{explain_simhash(text)}")
    
    print("\n\nSimilarity Matrix:")
    for i, (t1, h1) in enumerate(hashes):
        for j, (t2, h2) in enumerate(hashes):
            if j >= i:
                sim = simhash_similarity(h1, h2)
                dist = hamming_distance(h1, h2)
                print(f"  [{i}] vs [{j}]: {sim:.3f} (dist={dist})")
