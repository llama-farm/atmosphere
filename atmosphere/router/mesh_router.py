"""
Mesh-aware semantic router.

Extends semantic routing with full mesh intelligence:
- Gradient table (remote capabilities from gossip)
- Latency-aware scoring
- Hop penalty
- Cost consideration
- Model capability matching (RAG, specializations)
- Peer reachability status
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable, Any

import numpy as np

from .semantic import SemanticRouter, RouteResult, RouteAction
from .matcher import MatchMethod
from ..core.capability import CapabilityAnnouncement as Capability
from .gradient import GradientTable, GradientEntry
from .intent_classifier import classify_intent, IntentClassification, Complexity

logger = logging.getLogger(__name__)

# Scoring weights (tune these based on requirements)
SEMANTIC_WEIGHT = 0.4      # Semantic similarity importance
LATENCY_WEIGHT = 0.25      # Lower latency = better
CAPABILITY_WEIGHT = 0.2    # Model capability match
HOP_WEIGHT = 0.1          # Fewer hops = better
COST_WEIGHT = 0.05        # Lower cost = better

# Penalties and bonuses
MAX_LATENCY_MS = 2000      # Latency above this gets 0 score
HOP_PENALTY_FACTOR = 0.9   # Score multiplier per hop
UNREACHABLE_PENALTY = 0.5  # Penalty for potentially unreachable peers
RAG_BONUS = 0.15          # Bonus for RAG-enabled models
SPECIALIZATION_BONUS = 0.2 # Bonus for specialized models


@dataclass
class MeshRouteCandidate:
    """A candidate route with full scoring breakdown."""
    capability_id: str
    capability_label: str
    node_id: str
    is_local: bool
    
    # Scores (0-1 each)
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
    
    @property
    def composite_score(self) -> float:
        """Compute weighted composite score."""
        base_score = (
            self.semantic_score * SEMANTIC_WEIGHT +
            self.latency_score * LATENCY_WEIGHT +
            self.capability_score * CAPABILITY_WEIGHT +
            self.hop_score * HOP_WEIGHT +
            self.cost_score * COST_WEIGHT
        )
        
        # Apply hop penalty
        for _ in range(self.hops):
            base_score *= HOP_PENALTY_FACTOR
        
        # Apply reachability penalty
        if not self.is_reachable:
            base_score *= UNREACHABLE_PENALTY
        
        return base_score


class MeshRouter:
    """
    Mesh-aware router that considers full network topology.
    
    Routing decision factors:
    1. Semantic similarity (intent → capability match)
    2. Network latency (from gossip/transport data)
    3. Hop count (prefer direct routes)
    4. Model capabilities (RAG, specializations)
    5. Cost (if configured)
    6. Peer reachability (is target accessible?)
    """
    
    def __init__(
        self,
        semantic_router: SemanticRouter,
        peer_reachability_fn: Optional[Callable[[str], bool]] = None,
        model_info_fn: Optional[Callable[[str], Dict]] = None,
    ):
        """
        Args:
            semantic_router: Base semantic router
            peer_reachability_fn: Function to check if peer is reachable
            model_info_fn: Function to get model info for a capability
        """
        self.semantic_router = semantic_router
        self.peer_reachability_fn = peer_reachability_fn or (lambda x: True)
        self.model_info_fn = model_info_fn or (lambda x: {})
    
    async def route(
        self,
        intent: str,
        constraints: Optional[Dict] = None,
    ) -> RouteResult:
        """
        Route an intent using full mesh intelligence.
        
        Args:
            intent: Natural language intent
            constraints: Optional routing constraints (max_latency, prefer_local, etc)
            
        Returns:
            RouteResult with best route decision
        """
        constraints = constraints or {}
        
        # Step 1: Classify intent
        intent_class = classify_intent(intent)
        logger.info(
            f"🎯 INTENT: {intent_class.complexity.name} ({intent_class.task_type.value}) "
            f"→ {intent_class.recommended_model_size}"
        )
        
        # Step 2: Get all candidates (local + remote from gradient table)
        candidates = await self._gather_candidates(intent, intent_class)
        
        if not candidates:
            return RouteResult(
                action=RouteAction.NO_MATCH,
                reason="No capabilities available in mesh",
                method=MatchMethod.FALLBACK,
                intent_classification=intent_class.to_dict(),
            )
        
        # Step 3: Apply constraints filter
        candidates = self._apply_constraints(candidates, constraints)
        
        # Step 4: Score and rank candidates
        candidates.sort(key=lambda c: c.composite_score, reverse=True)
        
        # Log top candidates for debugging
        logger.info(f"📊 Top candidates for '{intent[:40]}...':")
        for i, c in enumerate(candidates[:3]):
            logger.info(
                f"  {i+1}. {c.capability_label} @ {c.node_id[:8]} "
                f"(score={c.composite_score:.2f}, sem={c.semantic_score:.2f}, "
                f"lat={c.estimated_latency_ms:.0f}ms, hops={c.hops})"
            )
        
        # Step 5: Select best candidate
        best = candidates[0]
        
        # Step 6: Build result
        action = RouteAction.PROCESS_LOCAL if best.is_local else RouteAction.FORWARD
        
        # Get the capability object for the result
        capability = self.semantic_router.local_capabilities.get(best.capability_id)
        if not capability and best.capability_id in [e.capability_id for e in self.semantic_router.gradient_table._entries.values()]:
            # Create a temporary capability from gradient entry
            entry = self.semantic_router.gradient_table.get_entry(best.capability_id)
            if entry:
                capability = Capability(
                    id=entry.capability_id,
                    label=entry.capability_label,
                    description="",  # Not stored in gradient
                    vector=entry.capability_vector,
                )
        
        return RouteResult(
            action=action,
            capability=capability,
            score=best.semantic_score,
            adjusted_score=best.composite_score,
            hops=best.hops,
            next_hop=None if best.is_local else best.node_id,
            via_node=best.node_id,
            reason=self._build_reason(best, intent_class),
            method=MatchMethod.EMBEDDING,  # TODO: track actual method
            intent_classification=intent_class.to_dict(),
        )
    
    async def _gather_candidates(
        self,
        intent: str,
        intent_class: IntentClassification,
    ) -> List[MeshRouteCandidate]:
        """Gather all candidate routes from local and remote sources."""
        candidates = []
        
        # Get intent vector for semantic scoring
        intent_vector = None
        if self.semantic_router._embedding_available:
            try:
                intent_vector = await self.semantic_router.embedding_engine.embed(intent)
            except Exception as e:
                logger.debug(f"Embedding failed: {e}")
        
        # Fallback to hash embedding
        intent_hash = self.semantic_router.hash_embedder.embed(intent)
        
        # === Local capabilities ===
        for cap_id, cap in self.semantic_router.local_capabilities.items():
            semantic_score = self._compute_semantic_score(intent_vector, intent_hash, cap)
            
            # Get model info for capability scoring
            model_info = self.model_info_fn(cap_id)
            capability_score = self._compute_capability_score(model_info, intent_class)
            
            candidates.append(MeshRouteCandidate(
                capability_id=cap_id,
                capability_label=cap.label,
                node_id=self.semantic_router.node_id,
                is_local=True,
                semantic_score=semantic_score,
                latency_score=1.0,  # Local = best latency
                capability_score=capability_score,
                hop_score=1.0,  # Local = 0 hops
                hops=0,
                estimated_latency_ms=1.0,  # ~1ms local
                model_info=model_info,
                is_reachable=True,
            ))
        
        # === Remote capabilities from gradient table ===
        for entry in self.semantic_router.gradient_table.all_entries():
            # Skip if it's our own capability
            if entry.via_node == self.semantic_router.node_id:
                continue
            
            # Compute semantic score
            semantic_score = 0.0
            if intent_vector is not None:
                semantic_score = float(np.dot(intent_vector, entry.capability_vector))
            else:
                # Hash fallback
                from .semantic import HashEmbedder
                cap_hash = HashEmbedder().embed(entry.capability_label)
                semantic_score = HashEmbedder.cosine_similarity(intent_hash, cap_hash)
            
            # Compute latency score (inverse normalized)
            latency_score = max(0, 1 - (entry.estimated_latency_ms / MAX_LATENCY_MS))
            
            # Compute hop score
            hop_score = HOP_PENALTY_FACTOR ** entry.hops
            
            # Check reachability
            is_reachable = self.peer_reachability_fn(entry.via_node)
            
            # Get model info if available
            model_info = self.model_info_fn(entry.capability_id)
            capability_score = self._compute_capability_score(model_info, intent_class)
            
            candidates.append(MeshRouteCandidate(
                capability_id=entry.capability_id,
                capability_label=entry.capability_label,
                node_id=entry.via_node,
                is_local=False,
                semantic_score=semantic_score,
                latency_score=latency_score,
                capability_score=capability_score,
                hop_score=hop_score,
                hops=entry.hops,
                estimated_latency_ms=entry.estimated_latency_ms,
                model_info=model_info,
                is_reachable=is_reachable,
            ))
        
        return candidates
    
    def _compute_semantic_score(
        self,
        intent_vector: Optional[np.ndarray],
        intent_hash: np.ndarray,
        cap: Capability,
    ) -> float:
        """Compute semantic similarity score."""
        if intent_vector is not None:
            return float(np.dot(intent_vector, cap.vector))
        
        # Hash fallback
        if cap.hash_vector is not None:
            from .semantic import HashEmbedder
            return HashEmbedder.cosine_similarity(intent_hash, cap.hash_vector)
        
        return 0.0
    
    def _compute_capability_score(
        self,
        model_info: Dict,
        intent_class: IntentClassification,
    ) -> float:
        """
        Score model capabilities against intent requirements.
        
        Considers:
        - RAG availability for knowledge queries
        - Model specialization match
        - Model size appropriateness
        """
        score = 0.5  # Base score
        
        # RAG bonus for knowledge queries
        if model_info.get("has_rag") and intent_class.task_type.value in ["qa", "knowledge", "factual"]:
            score += RAG_BONUS
        
        # Specialization bonus
        specializations = model_info.get("specializations", [])
        if specializations:
            # Check if any specialization matches the intent keywords
            intent_keywords = set(intent_class.task_type.value.split("_"))
            for spec in specializations:
                spec_keywords = set(spec.lower().split("_"))
                if intent_keywords & spec_keywords:
                    score += SPECIALIZATION_BONUS
                    break
        
        # Model size appropriateness
        model_size = model_info.get("size", "medium")
        recommended = intent_class.recommended_model_size
        
        size_scores = {
            ("tiny", "tiny"): 1.0, ("tiny", "small"): 0.9, ("tiny", "medium"): 0.7,
            ("small", "tiny"): 0.8, ("small", "small"): 1.0, ("small", "medium"): 0.9,
            ("medium", "small"): 0.7, ("medium", "medium"): 1.0, ("medium", "large"): 0.9,
            ("large", "medium"): 0.8, ("large", "large"): 1.0, ("large", "huge"): 0.95,
        }
        size_match = size_scores.get((model_size, recommended), 0.7)
        score *= size_match
        
        return min(1.0, score)
    
    def _apply_constraints(
        self,
        candidates: List[MeshRouteCandidate],
        constraints: Dict,
    ) -> List[MeshRouteCandidate]:
        """Filter candidates based on routing constraints."""
        filtered = candidates
        
        # Max latency constraint
        max_latency = constraints.get("max_latency_ms")
        if max_latency:
            filtered = [c for c in filtered if c.estimated_latency_ms <= max_latency]
        
        # Prefer local constraint
        if constraints.get("prefer_local"):
            local = [c for c in filtered if c.is_local]
            if local:
                filtered = local
        
        # Require reachable
        if constraints.get("require_reachable", True):
            filtered = [c for c in filtered if c.is_reachable]
        
        # Max hops constraint
        max_hops = constraints.get("max_hops")
        if max_hops:
            filtered = [c for c in filtered if c.hops <= max_hops]
        
        return filtered if filtered else candidates  # Fall back to all if filter too aggressive
    
    def _build_reason(
        self,
        candidate: MeshRouteCandidate,
        intent_class: IntentClassification,
    ) -> str:
        """Build human-readable routing reason."""
        parts = [
            f"Selected {candidate.capability_label}",
            f"@ {candidate.node_id[:8]}",
            f"(score={candidate.composite_score:.2f})",
        ]
        
        if not candidate.is_local:
            parts.append(f"via {candidate.hops} hop(s)")
            parts.append(f"~{candidate.estimated_latency_ms:.0f}ms")
        
        if candidate.model_info.get("has_rag"):
            parts.append("RAG")
        
        return " ".join(parts)
