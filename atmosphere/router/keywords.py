"""
Shared keyword extraction and matching utilities.

Used by both SemanticRouter and FastProjectRouter for fallback matching.
"""

import re
from collections import Counter
from typing import Set


class KeywordUtils:
    """
    Keyword extractor and matcher for text-based routing fallback.
    
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
    
    # Minimum word length to consider
    MIN_WORD_LENGTH = 3
    
    @classmethod
    def extract(cls, text: str, max_keywords: int = 20) -> Set[str]:
        """
        Extract keywords from text.
        
        Args:
            text: Input text to extract keywords from
            max_keywords: Maximum number of keywords to return
            
        Returns:
            Set of lowercase keywords
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
        Compute keyword match score using Jaccard-like similarity.
        
        Args:
            query_keywords: Keywords from the query/intent
            target_keywords: Keywords from the target/capability
        
        Returns:
            Score in [0, 1] representing keyword overlap
        """
        if not query_keywords or not target_keywords:
            return 0.0
        
        intersection = len(query_keywords & target_keywords)
        union = len(query_keywords | target_keywords)
        
        return intersection / union if union > 0 else 0.0


# Backward compatibility aliases
KeywordExtractor = KeywordUtils
KeywordMatcher = KeywordUtils
