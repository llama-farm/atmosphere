"""
3-Tier Cascade Matcher for capability routing.

Implements a robust cascade matching system that works even when
embeddings are unavailable:

Tier 1: Embedding cosine similarity (best quality, requires ML model)
Tier 2: Hash matching (32-bit hashes, fast, no dependencies)
Tier 3: Keyword overlap (fallback, always works)

Each tier has configurable thresholds. If a tier produces a match
above its threshold, routing uses that result. Otherwise, cascade
to the next tier.
"""

import hashlib
import logging
import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class MatchMethod(Enum):
    """Which matching tier produced the result."""
    EMBEDDING = "embedding"  # Tier 1: Neural embeddings
    HASH = "hash"            # Tier 2: Hash-based similarity
    KEYWORD = "keyword"      # Tier 3: Keyword overlap
    FALLBACK = "fallback"    # No tier passed threshold


# Default thresholds for each tier
EMBEDDING_MIN_SCORE = 0.65  # Use embedding result if above this
HASH_MIN_SCORE = 0.40       # Use hash result if above this
KEYWORD_MIN_SCORE = 0.30    # Use keyword result if above this


@dataclass
class MatchResult:
    """Result from a single tier match."""
    score: float
    capability_id: str
    capability_label: str
    method: MatchMethod
    passed_threshold: bool = False
    metadata: Dict = None


class KeywordExtractor:
    """
    Extract meaningful keywords from text for fallback matching.
    
    Uses simple heuristics - no external dependencies.
    """
    
    # Common stopwords to filter out
    STOPWORDS = frozenset([
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
        "been", "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "shall", "can",
        "this", "that", "these", "those", "i", "you", "he", "she", "it", "we",
        "they", "what", "which", "who", "whom", "how", "when", "where", "why",
        "all", "each", "every", "both", "few", "more", "most", "other", "some",
        "such", "no", "not", "only", "same", "so", "than", "too", "very", "just",
        "about", "into", "through", "during", "before", "after", "above", "below",
        "between", "under", "again", "further", "then", "once", "here", "there"
    ])
    
    MIN_WORD_LENGTH = 3
    
    @classmethod
    def extract(cls, text: str, max_keywords: int = 20) -> Set[str]:
        """
        Extract keywords from text.
        
        Returns set of lowercase keywords.
        """
        if not text:
            return set()
        
        # Tokenize: lowercase, split on non-alphanumeric
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        
        # Filter stopwords and short words
        keywords = [
            w for w in words 
            if w not in cls.STOPWORDS and len(w) >= cls.MIN_WORD_LENGTH
        ]
        
        # Get most common keywords
        counts = Counter(keywords)
        top_keywords = [kw for kw, _ in counts.most_common(max_keywords)]
        
        return set(top_keywords)
    
    @classmethod
    def match_score(cls, query_keywords: Set[str], target_keywords: Set[str]) -> float:
        """
        Compute keyword match score using Jaccard similarity.
        
        Returns score in [0, 1].
        """
        if not query_keywords or not target_keywords:
            return 0.0
        
        intersection = len(query_keywords & target_keywords)
        union = len(query_keywords | target_keywords)
        
        if union == 0:
            return 0.0
        
        return intersection / union


class HashEmbedder:
    """
    Hash-based embedding fallback.
    
    Uses character n-grams hashed to vector positions.
    Fast, deterministic, and requires no ML models.
    """
    
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
    
    def embed(self, text: str) -> np.ndarray:
        """Generate hash-based embedding."""
        vec = np.zeros(self.dimension, dtype=np.float32)
        text = text.lower()
        
        # Character trigrams
        for i in range(len(text) - 2):
            ngram = text[i:i+3]
            h = int(hashlib.md5(ngram.encode()).hexdigest(), 16)
            pos = h % self.dimension
            vec[pos] += 1.0
        
        # Word unigrams with higher weight
        for word in text.split():
            if len(word) >= 3:
                h = int(hashlib.md5(word.encode()).hexdigest(), 16)
                pos = h % self.dimension
                vec[pos] += 2.0
        
        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        
        return vec
    
    @staticmethod
    def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between normalized vectors."""
        return float(np.dot(vec1, vec2))
    
    @staticmethod
    def compute_hash_32bit(text: str) -> int:
        """
        DEPRECATED: Use compute_simhash_64bit for cross-platform compatibility.
        
        Compute 32-bit hash for fast comparison.
        Used for quick capability identification without full embedding.
        """
        h = hashlib.md5(text.encode()).digest()
        return int.from_bytes(h[:4], 'big')
    
    @staticmethod
    def compute_simhash_64bit(text: str) -> int:
        """
        Compute 64-bit SimHash for cross-platform compatibility.
        
        This uses the unified SimHash algorithm that produces identical
        results on Python and Kotlin/Android. Preferred over compute_hash_32bit.
        """
        from .simhash import compute_simhash
        return compute_simhash(text)
    
    @staticmethod
    def simhash_similarity(hash1: int, hash2: int) -> float:
        """
        Compute Hamming similarity between two 64-bit SimHashes.
        
        Returns value in [0, 1] where 1.0 = identical.
        """
        from .simhash import simhash_similarity
        return simhash_similarity(hash1, hash2)


@dataclass
class CapabilityMatch:
    """Represents a capability that can be matched."""
    id: str
    label: str
    description: str
    
    # Optional pre-computed features
    embedding_vector: Optional[np.ndarray] = None
    hash_vector: Optional[np.ndarray] = None
    hash_32bit: Optional[int] = None
    simhash_64bit: Optional[int] = None  # Cross-platform 64-bit SimHash
    keywords: Optional[Set[str]] = None
    
    # Metadata for scoring
    metadata: Dict = None


class CascadeMatcher:
    """
    3-tier cascade matcher for semantic routing.
    
    Tries each tier in order until one passes its threshold:
    1. Embedding similarity (if available)
    2. Hash-based similarity
    3. Keyword overlap
    
    Usage:
        matcher = CascadeMatcher()
        
        # Register capabilities
        matcher.add_capability(cap_id, label, description, embedding=vec)
        
        # Match an intent
        result = matcher.match(intent_text, intent_embedding=vec)
    """
    
    def __init__(
        self,
        embedding_min_score: float = EMBEDDING_MIN_SCORE,
        hash_min_score: float = HASH_MIN_SCORE,
        keyword_min_score: float = KEYWORD_MIN_SCORE,
    ):
        """
        Args:
            embedding_min_score: Threshold for Tier 1 (embedding)
            hash_min_score: Threshold for Tier 2 (hash)
            keyword_min_score: Threshold for Tier 3 (keyword)
        """
        self.embedding_min_score = embedding_min_score
        self.hash_min_score = hash_min_score
        self.keyword_min_score = keyword_min_score
        
        self.hash_embedder = HashEmbedder()
        self.capabilities: Dict[str, CapabilityMatch] = {}
    
    def add_capability(
        self,
        cap_id: str,
        label: str,
        description: str,
        embedding_vector: Optional[np.ndarray] = None,
        hash_vector: Optional[np.ndarray] = None,
        hash_32bit: Optional[int] = None,
        simhash_64bit: Optional[int] = None,
        keywords: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ):
        """
        Register a capability for matching.
        
        Args:
            cap_id: Unique capability identifier
            label: Short label
            description: Full description
            embedding_vector: Pre-computed embedding (Tier 1)
            hash_vector: Pre-computed hash embedding (Tier 2)
            hash_32bit: Pre-computed 32-bit hash (DEPRECATED, for legacy)
            simhash_64bit: 64-bit SimHash for cross-platform matching
            keywords: Pre-extracted keywords (Tier 3)
            metadata: Additional metadata for scoring/filtering
        """
        # Auto-compute missing features
        if hash_vector is None:
            hash_vector = self.hash_embedder.embed(description)
        
        if hash_32bit is None:
            hash_32bit = HashEmbedder.compute_hash_32bit(description)
        
        # Compute cross-platform 64-bit SimHash
        if simhash_64bit is None:
            simhash_64bit = HashEmbedder.compute_simhash_64bit(f"{label} {description}")
        
        if keywords is None:
            keywords = KeywordExtractor.extract(description)
        
        self.capabilities[cap_id] = CapabilityMatch(
            id=cap_id,
            label=label,
            description=description,
            embedding_vector=embedding_vector,
            hash_vector=hash_vector,
            hash_32bit=hash_32bit,
            simhash_64bit=simhash_64bit,
            keywords=keywords,
            metadata=metadata or {},
        )
        
        logger.debug(
            f"Added capability: {label} (emb={'✓' if embedding_vector is not None else '✗'}, "
            f"simhash=0x{simhash_64bit:016x}, keywords={len(keywords)})"
        )
    
    def remove_capability(self, cap_id: str) -> bool:
        """Remove a capability."""
        if cap_id in self.capabilities:
            del self.capabilities[cap_id]
            return True
        return False
    
    def match(
        self,
        intent_text: str,
        intent_embedding: Optional[np.ndarray] = None,
        return_all_scores: bool = False,
    ) -> Tuple[Optional[MatchResult], Optional[List[MatchResult]]]:
        """
        Match an intent using the 3-tier cascade.
        
        Args:
            intent_text: Intent text to match
            intent_embedding: Pre-computed intent embedding (optional)
            return_all_scores: If True, return all candidate scores
            
        Returns:
            Tuple of (best_result, all_results)
            best_result is None if no match found
            all_results is None unless return_all_scores=True
        """
        if not self.capabilities:
            return None, None
        
        # Pre-compute intent features
        intent_keywords = KeywordExtractor.extract(intent_text)
        intent_hash_vector = self.hash_embedder.embed(intent_text)
        intent_hash_32bit = HashEmbedder.compute_hash_32bit(intent_text)
        intent_simhash = HashEmbedder.compute_simhash_64bit(intent_text)
        
        all_results = []
        
        # === TIER 1: Embedding Match ===
        if intent_embedding is not None:
            tier1_result = self._match_embedding(intent_embedding)
            if tier1_result:
                if return_all_scores:
                    all_results.append(tier1_result)
                
                if tier1_result.score >= self.embedding_min_score:
                    tier1_result.passed_threshold = True
                    logger.debug(
                        f"✓ Tier 1 (embedding): {tier1_result.capability_label} "
                        f"score={tier1_result.score:.3f} >= {self.embedding_min_score:.3f}"
                    )
                    return tier1_result, (all_results if return_all_scores else None)
        
        # === TIER 2: Hash Match ===
        tier2_result = self._match_hash(intent_hash_vector, intent_hash_32bit, intent_simhash)
        if tier2_result:
            if return_all_scores:
                all_results.append(tier2_result)
            
            if tier2_result.score >= self.hash_min_score:
                tier2_result.passed_threshold = True
                logger.debug(
                    f"✓ Tier 2 (hash): {tier2_result.capability_label} "
                    f"score={tier2_result.score:.3f} >= {self.hash_min_score:.3f}"
                )
                return tier2_result, (all_results if return_all_scores else None)
        
        # === TIER 3: Keyword Match ===
        tier3_result = self._match_keyword(intent_keywords)
        if tier3_result:
            if return_all_scores:
                all_results.append(tier3_result)
            
            if tier3_result.score >= self.keyword_min_score:
                tier3_result.passed_threshold = True
                logger.debug(
                    f"✓ Tier 3 (keyword): {tier3_result.capability_label} "
                    f"score={tier3_result.score:.3f} >= {self.keyword_min_score:.3f}"
                )
                return tier3_result, (all_results if return_all_scores else None)
        
        # === FALLBACK: Return best from any tier ===
        logger.debug("✗ No tier passed threshold, using fallback (best score)")
        
        # Collect best from each tier
        candidates = [r for r in all_results if r] if return_all_scores else []
        
        if not candidates:
            # Compute all if we didn't already
            if intent_embedding is not None:
                tier1 = self._match_embedding(intent_embedding)
                if tier1:
                    candidates.append(tier1)
            
            tier2 = self._match_hash(intent_hash_vector, intent_hash_32bit, intent_simhash)
            if tier2:
                candidates.append(tier2)
            
            tier3 = self._match_keyword(intent_keywords)
            if tier3:
                candidates.append(tier3)
        
        if candidates:
            best = max(candidates, key=lambda r: r.score)
            best.method = MatchMethod.FALLBACK
            return best, (all_results if return_all_scores else None)
        
        return None, (all_results if return_all_scores else None)
    
    def _match_embedding(self, intent_embedding: np.ndarray) -> Optional[MatchResult]:
        """Tier 1: Match using neural embeddings."""
        best_cap_id = None
        best_score = 0.0
        
        for cap_id, cap in self.capabilities.items():
            if cap.embedding_vector is None:
                continue
            
            score = float(np.dot(intent_embedding, cap.embedding_vector))
            if score > best_score:
                best_score = score
                best_cap_id = cap_id
        
        if best_cap_id:
            cap = self.capabilities[best_cap_id]
            return MatchResult(
                score=best_score,
                capability_id=best_cap_id,
                capability_label=cap.label,
                method=MatchMethod.EMBEDDING,
                metadata=cap.metadata,
            )
        
        return None
    
    def _match_hash(
        self,
        intent_hash_vector: np.ndarray,
        intent_hash_32bit: int,
        intent_simhash: Optional[int] = None,
    ) -> Optional[MatchResult]:
        """
        Tier 2: Match using hash-based embeddings.
        
        Uses two scoring methods and picks the best:
        1. Hash vector cosine similarity (384-dim vectors)
        2. SimHash Hamming similarity (64-bit, cross-platform)
        """
        best_cap_id = None
        best_score = 0.0
        
        for cap_id, cap in self.capabilities.items():
            score = 0.0
            
            # Method 1: Hash vector similarity (legacy/local)
            if cap.hash_vector is not None:
                score = HashEmbedder.cosine_similarity(intent_hash_vector, cap.hash_vector)
            
            # Method 2: 64-bit SimHash (cross-platform)
            if intent_simhash is not None and cap.simhash_64bit is not None:
                simhash_score = HashEmbedder.simhash_similarity(intent_simhash, cap.simhash_64bit)
                # Use the better of the two scores
                score = max(score, simhash_score)
            
            if score > best_score:
                best_score = score
                best_cap_id = cap_id
        
        if best_cap_id:
            cap = self.capabilities[best_cap_id]
            return MatchResult(
                score=best_score,
                capability_id=best_cap_id,
                capability_label=cap.label,
                method=MatchMethod.HASH,
                metadata=cap.metadata,
            )
        
        return None
    
    def _match_keyword(self, intent_keywords: Set[str]) -> Optional[MatchResult]:
        """Tier 3: Match using keyword overlap."""
        best_cap_id = None
        best_score = 0.0
        
        for cap_id, cap in self.capabilities.items():
            if not cap.keywords:
                continue
            
            score = KeywordExtractor.match_score(intent_keywords, cap.keywords)
            if score > best_score:
                best_score = score
                best_cap_id = cap_id
        
        if best_cap_id:
            cap = self.capabilities[best_cap_id]
            return MatchResult(
                score=best_score,
                capability_id=best_cap_id,
                capability_label=cap.label,
                method=MatchMethod.KEYWORD,
                metadata=cap.metadata,
            )
        
        return None
    
    def rank_all(
        self,
        intent_text: str,
        intent_embedding: Optional[np.ndarray] = None,
        top_k: int = 5,
    ) -> List[Tuple[str, float, MatchMethod]]:
        """
        Rank all capabilities by best match score across cascade tiers.
        
        Returns list of (capability_id, score, method) tuples.
        """
        if not self.capabilities:
            return []
        
        intent_keywords = KeywordExtractor.extract(intent_text)
        intent_hash_vector = self.hash_embedder.embed(intent_text)
        
        scores = []
        
        for cap_id, cap in self.capabilities.items():
            best_score = 0.0
            best_method = MatchMethod.FALLBACK
            
            # Try embedding
            if intent_embedding is not None and cap.embedding_vector is not None:
                emb_score = float(np.dot(intent_embedding, cap.embedding_vector))
                if emb_score > best_score:
                    best_score = emb_score
                    best_method = MatchMethod.EMBEDDING
            
            # Try hash
            if cap.hash_vector is not None:
                hash_score = HashEmbedder.cosine_similarity(intent_hash_vector, cap.hash_vector)
                if hash_score > best_score:
                    best_score = hash_score
                    best_method = MatchMethod.HASH
            
            # Try keyword
            if cap.keywords:
                kw_score = KeywordExtractor.match_score(intent_keywords, cap.keywords)
                if kw_score > best_score:
                    best_score = kw_score
                    best_method = MatchMethod.KEYWORD
            
            scores.append((cap_id, best_score, best_method))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
    
    def clear(self):
        """Clear all registered capabilities."""
        self.capabilities.clear()
    
    def __len__(self) -> int:
        return len(self.capabilities)
