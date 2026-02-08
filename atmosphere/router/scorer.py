"""
Composite scoring system for route selection.

Combines multiple factors to score routing candidates:
- Semantic similarity (how well capability matches intent)
- Latency (network/execution time)
- Capability features (RAG, specialization, model size)
- Hop count (prefer direct routes)
- Cost (API costs, battery, bandwidth)

Each factor contributes to a weighted composite score that determines
the best route for a given intent.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# Scoring weights (tune based on requirements)
SEMANTIC_WEIGHT = 0.4      # Semantic similarity importance
LATENCY_WEIGHT = 0.25      # Lower latency = better
CAPABILITY_WEIGHT = 0.2    # Model capability match
HOP_WEIGHT = 0.1          # Fewer hops = better
COST_WEIGHT = 0.05        # Lower cost = better

# Scoring parameters
MAX_LATENCY_MS = 2000      # Latency above this gets 0 score
HOP_PENALTY_FACTOR = 0.9   # Score multiplier per hop
UNREACHABLE_PENALTY = 0.5  # Penalty for potentially unreachable peers

# Capability bonuses
RAG_BONUS = 0.15          # Bonus for RAG-enabled models
SPECIALIZATION_BONUS = 0.2 # Bonus for specialized models


@dataclass
class RouteCandidate:
    """
    A candidate route with all scoring factors.
    
    Used by the scorer to compute composite scores.
    """
    capability_id: str
    capability_label: str
    node_id: str
    is_local: bool
    
    # Core scores (0-1 each)
    semantic_score: float = 0.0
    latency_score: float = 0.0
    capability_score: float = 0.0
    hop_score: float = 0.0
    cost_score: float = 1.0  # Default to best (no cost)
    
    # Metadata
    estimated_latency_ms: float = 0.0
    hops: int = 0
    model_info: Dict[str, Any] = field(default_factory=dict)
    is_reachable: bool = True
    match_method: str = "unknown"
    
    # Detailed breakdown for logging
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    
    @property
    def composite_score(self) -> float:
        """Compute weighted composite score."""
        return CompositeScorer.compute_composite(self)
    
    def explain(self) -> str:
        """Generate human-readable explanation of scoring."""
        return CompositeScorer.explain_score(self)


class CompositeScorer:
    """
    Composite scoring system for route selection.
    
    Combines semantic, latency, capability, hop, and cost factors
    into a single score that can be used to rank routing candidates.
    
    Usage:
        scorer = CompositeScorer()
        
        # Create candidate
        candidate = RouteCandidate(...)
        
        # Compute scores
        scorer.compute_semantic_score(candidate, intent_match_score)
        scorer.compute_latency_score(candidate)
        scorer.compute_capability_score(candidate, intent_classification)
        scorer.compute_hop_score(candidate)
        scorer.compute_cost_score(candidate)
        
        # Get composite score
        final_score = candidate.composite_score
    """
    
    def __init__(
        self,
        semantic_weight: float = SEMANTIC_WEIGHT,
        latency_weight: float = LATENCY_WEIGHT,
        capability_weight: float = CAPABILITY_WEIGHT,
        hop_weight: float = HOP_WEIGHT,
        cost_weight: float = COST_WEIGHT,
        max_latency_ms: float = MAX_LATENCY_MS,
        hop_penalty_factor: float = HOP_PENALTY_FACTOR,
        unreachable_penalty: float = UNREACHABLE_PENALTY,
    ):
        self.semantic_weight = semantic_weight
        self.latency_weight = latency_weight
        self.capability_weight = capability_weight
        self.hop_weight = hop_weight
        self.cost_weight = cost_weight
        
        self.max_latency_ms = max_latency_ms
        self.hop_penalty_factor = hop_penalty_factor
        self.unreachable_penalty = unreachable_penalty
    
    def compute_semantic_score(
        self,
        candidate: RouteCandidate,
        match_score: float,
    ):
        """
        Set semantic similarity score.
        
        This comes from the cascade matcher (embedding/hash/keyword match).
        
        Args:
            candidate: Route candidate to update
            match_score: Match score from cascade matcher (0-1)
        """
        candidate.semantic_score = max(0.0, min(1.0, match_score))
        candidate.score_breakdown["semantic"] = candidate.semantic_score
    
    def compute_latency_score(
        self,
        candidate: RouteCandidate,
    ):
        """
        Compute latency score (0-1, higher is better).
        
        Local capabilities get 1.0 (best latency).
        Remote capabilities are scored based on estimated_latency_ms.
        
        Args:
            candidate: Route candidate to update
        """
        if candidate.is_local:
            candidate.latency_score = 1.0
        else:
            # Normalize latency: 0ms = 1.0, max_latency_ms = 0.0
            latency = candidate.estimated_latency_ms
            candidate.latency_score = max(0.0, 1.0 - (latency / self.max_latency_ms))
        
        candidate.score_breakdown["latency"] = candidate.latency_score
    
    def compute_capability_score(
        self,
        candidate: RouteCandidate,
        intent_classification: Optional[Dict] = None,
    ):
        """
        Score model capabilities against intent requirements.
        
        Considers:
        - RAG availability for knowledge queries
        - Model specialization match
        - Model size appropriateness
        
        Args:
            candidate: Route candidate to update
            intent_classification: Intent classification dict from Layer 0
        """
        model_info = candidate.model_info
        score = 0.5  # Base score
        
        if intent_classification:
            # RAG bonus for knowledge queries
            task_type = intent_classification.get("task_type", "")
            if model_info.get("has_rag") and task_type in ["qa", "knowledge", "factual"]:
                score += RAG_BONUS
                logger.debug(f"  +RAG bonus ({RAG_BONUS}) for {candidate.capability_label}")
            
            # Specialization bonus
            specializations = model_info.get("specializations", [])
            if specializations:
                # Check if any specialization matches intent keywords/task type
                task_keywords = set(task_type.split("_"))
                for spec in specializations:
                    spec_keywords = set(spec.lower().split("_"))
                    if task_keywords & spec_keywords:
                        score += SPECIALIZATION_BONUS
                        logger.debug(
                            f"  +Specialization bonus ({SPECIALIZATION_BONUS}) "
                            f"for {spec} match"
                        )
                        break
            
            # Model size appropriateness
            model_size = model_info.get("size", "medium")
            recommended = intent_classification.get("recommended_model_size", "medium")
            
            size_scores = {
                ("tiny", "tiny"): 1.0, ("tiny", "small"): 0.9, ("tiny", "medium"): 0.7,
                ("small", "tiny"): 0.8, ("small", "small"): 1.0, ("small", "medium"): 0.9,
                ("medium", "small"): 0.7, ("medium", "medium"): 1.0, ("medium", "large"): 0.9,
                ("large", "medium"): 0.8, ("large", "large"): 1.0, ("large", "huge"): 0.95,
            }
            size_match = size_scores.get((model_size, recommended), 0.7)
            score *= size_match
            
            logger.debug(
                f"  Size match: {model_size} vs {recommended} → {size_match:.2f}x"
            )
        
        candidate.capability_score = min(1.0, score)
        candidate.score_breakdown["capability"] = candidate.capability_score
    
    def compute_hop_score(
        self,
        candidate: RouteCandidate,
    ):
        """
        Compute hop score (0-1, higher is better).
        
        Local capabilities get 1.0 (0 hops).
        Remote capabilities are penalized by hop_penalty_factor per hop.
        
        Args:
            candidate: Route candidate to update
        """
        if candidate.is_local:
            candidate.hop_score = 1.0
        else:
            # Apply exponential penalty per hop
            candidate.hop_score = self.hop_penalty_factor ** candidate.hops
        
        candidate.score_breakdown["hop"] = candidate.hop_score
    
    def compute_cost_score(
        self,
        candidate: RouteCandidate,
        estimated_cost_usd: float = 0.0,
    ):
        """
        Compute cost score (0-1, higher is better = lower cost).
        
        Local models are free (score = 1.0).
        API costs are normalized ($0.01 = ~0.9, $0.10 = ~0.5).
        
        Args:
            candidate: Route candidate to update
            estimated_cost_usd: Estimated API cost in USD
        """
        if candidate.is_local:
            candidate.cost_score = 1.0
        else:
            # Normalize cost: 0 = 1.0, $0.10 = 0.0
            # Using exponential decay for better scaling
            candidate.cost_score = max(0.0, 1.0 - (estimated_cost_usd / 0.10))
        
        candidate.score_breakdown["cost"] = candidate.cost_score
    
    @staticmethod
    def compute_composite(
        candidate: RouteCandidate,
        semantic_weight: float = SEMANTIC_WEIGHT,
        latency_weight: float = LATENCY_WEIGHT,
        capability_weight: float = CAPABILITY_WEIGHT,
        hop_weight: float = HOP_WEIGHT,
        cost_weight: float = COST_WEIGHT,
        hop_penalty_factor: float = HOP_PENALTY_FACTOR,
        unreachable_penalty: float = UNREACHABLE_PENALTY,
    ) -> float:
        """
        Compute final composite score from all factors.
        
        Args:
            candidate: Route candidate with computed factor scores
            *_weight: Weight for each scoring factor
            hop_penalty_factor: Multiplier per hop
            unreachable_penalty: Multiplier for unreachable nodes
            
        Returns:
            Composite score (0-1, higher is better)
        """
        # Weighted sum of factors
        base_score = (
            candidate.semantic_score * semantic_weight +
            candidate.latency_score * latency_weight +
            candidate.capability_score * capability_weight +
            candidate.hop_score * hop_weight +
            candidate.cost_score * cost_weight
        )
        
        # Apply hop penalty (exponential)
        for _ in range(candidate.hops):
            base_score *= hop_penalty_factor
        
        # Apply reachability penalty
        if not candidate.is_reachable:
            base_score *= unreachable_penalty
        
        return base_score
    
    @staticmethod
    def explain_score(candidate: RouteCandidate) -> str:
        """
        Generate human-readable explanation of scoring.
        
        Returns string like:
        "score=0.85 (semantic=0.90*0.4 + latency=0.95*0.25 + capability=0.75*0.2 + hop=1.0*0.1 + cost=1.0*0.05)"
        """
        parts = []
        
        if candidate.semantic_score > 0:
            parts.append(f"semantic={candidate.semantic_score:.2f}*{SEMANTIC_WEIGHT}")
        
        if candidate.latency_score > 0:
            parts.append(f"latency={candidate.latency_score:.2f}*{LATENCY_WEIGHT}")
        
        if candidate.capability_score > 0:
            parts.append(f"capability={candidate.capability_score:.2f}*{CAPABILITY_WEIGHT}")
        
        if candidate.hop_score > 0:
            parts.append(f"hop={candidate.hop_score:.2f}*{HOP_WEIGHT}")
        
        if candidate.cost_score > 0:
            parts.append(f"cost={candidate.cost_score:.2f}*{COST_WEIGHT}")
        
        explanation = " + ".join(parts)
        
        # Add modifiers
        modifiers = []
        if candidate.hops > 0:
            modifiers.append(f"{candidate.hops} hops")
        if not candidate.is_reachable:
            modifiers.append("unreachable")
        
        if modifiers:
            explanation += f" → {', '.join(modifiers)}"
        
        return f"score={candidate.composite_score:.3f} ({explanation})"
    
    def rank_candidates(
        self,
        candidates: List[RouteCandidate],
    ) -> List[RouteCandidate]:
        """
        Rank candidates by composite score.
        
        Args:
            candidates: List of route candidates
            
        Returns:
            Sorted list (highest score first)
        """
        return sorted(candidates, key=lambda c: c.composite_score, reverse=True)


def create_candidate(
    capability_id: str,
    capability_label: str,
    node_id: str,
    is_local: bool,
    semantic_score: float = 0.0,
    estimated_latency_ms: float = 0.0,
    hops: int = 0,
    model_info: Optional[Dict] = None,
    is_reachable: bool = True,
    match_method: str = "unknown",
) -> RouteCandidate:
    """
    Convenience function to create a route candidate.
    
    Automatically computes latency, hop, and cost scores.
    Semantic and capability scores must be computed separately.
    """
    candidate = RouteCandidate(
        capability_id=capability_id,
        capability_label=capability_label,
        node_id=node_id,
        is_local=is_local,
        semantic_score=semantic_score,
        estimated_latency_ms=estimated_latency_ms,
        hops=hops,
        model_info=model_info or {},
        is_reachable=is_reachable,
        match_method=match_method,
    )
    
    # Compute basic scores
    scorer = CompositeScorer()
    scorer.compute_latency_score(candidate)
    scorer.compute_hop_score(candidate)
    scorer.compute_cost_score(candidate)
    
    return candidate
