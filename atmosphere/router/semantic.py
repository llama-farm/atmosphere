"""
Semantic router for intent-based capability matching.

REFACTORED (Phase 3) - Uses gradient table for ALL capabilities:
- Local capabilities are added to gradient table with hops=0
- Remote capabilities come from gossip into gradient table
- Single unified matching pipeline using matcher + scorer + constraints
- Detailed logging of routing decisions

Routes intents using:
1. Intent classification (Layer 0 - THE CROWN JEWEL)
2. 3-tier cascade matching (embedding → hash → keyword)
3. Composite scoring (semantic + latency + capability + hop + cost)
4. Constraint filtering
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from .gradient import GradientTable
from .embeddings import EmbeddingEngine
from .matcher import CascadeMatcher, MatchMethod, MatchResult
from .scorer import CompositeScorer, RouteCandidate, create_candidate
from .constraints import RouteConstraints, filter_candidates
from .intent_classifier import classify_intent, IntentClassification

logger = logging.getLogger(__name__)


class RouteAction(Enum):
    """Actions from routing decision."""
    PROCESS_LOCAL = "process_local"
    FORWARD = "forward"
    NO_MATCH = "no_match"


@dataclass
class RouteResult:
    """Result of routing decision."""
    action: RouteAction
    
    # Selected route
    capability_id: Optional[str] = None
    capability_label: Optional[str] = None
    node_id: Optional[str] = None
    
    # Scores
    semantic_score: float = 0.0
    composite_score: float = 0.0
    
    # Route metadata
    hops: int = 0
    estimated_latency_ms: float = 0.0
    is_local: bool = False
    next_hop: Optional[str] = None
    via_node: Optional[str] = None
    
    # Decision explanation
    reason: str = ""
    match_method: MatchMethod = MatchMethod.FALLBACK
    score_breakdown: Dict[str, float] = None
    
    # Intent classification
    intent_classification: Optional[dict] = None

    @property
    def matched(self) -> bool:
        return self.action != RouteAction.NO_MATCH


class SemanticRouter:
    """
    Semantic router for intent-based capability matching.
    
    Uses gradient table for ALL capabilities (local + remote):
    - Local capabilities are registered with hops=0
    - Remote capabilities come from gossip updates
    - All capabilities go through same matching/scoring pipeline
    
    Usage:
        router = SemanticRouter(node_id="node-abc")
        await router.initialize()
        
        # Register local capabilities
        await router.register_capability("llm", "Language model inference")
        
        # Route an intent
        result = await router.route("summarize this document")
        
        if result.action == RouteAction.PROCESS_LOCAL:
            # Execute locally
            pass
        elif result.action == RouteAction.FORWARD:
            # Forward to result.next_hop
            pass
    """

    def __init__(
        self,
        node_id: str,
        model_info_fn: Optional[callable] = None,
        peer_reachability_fn: Optional[callable] = None,
    ):
        """
        Args:
            node_id: This node's identifier
            model_info_fn: Function to get model info for capability
            peer_reachability_fn: Function to check if peer is reachable
        """
        self.node_id = node_id
        self.model_info_fn = model_info_fn or (lambda x: {})
        self.peer_reachability_fn = peer_reachability_fn or (lambda x: True)
        
        # Core components
        self.gradient_table = GradientTable(node_id)
        self.matcher = CascadeMatcher()
        self.scorer = CompositeScorer()
        self.embedding_engine = EmbeddingEngine()
        
        # Track local capability IDs for quick lookup
        self.local_capability_ids: Set[str] = set()
        
        self._initialized = False
        self._embedding_available = False

    async def initialize(self) -> None:
        """Initialize the router."""
        if self._initialized:
            return
        
        try:
            await self.embedding_engine.initialize()
            self._embedding_available = True
            logger.info("✓ Semantic router initialized with neural embeddings")
        except Exception as e:
            logger.warning(f"⚠️  Neural embeddings unavailable, using hash+keyword fallback: {e}")
            self._embedding_available = False
        
        self._initialized = True

    async def close(self) -> None:
        """Close the router."""
        if self._embedding_available:
            await self.embedding_engine.close()
        self._initialized = False

    async def register_capability(
        self,
        label: str,
        description: str,
        handler: str = "default",
        models: Optional[List[str]] = None,
        constraints: Optional[dict] = None,
        specializations: Optional[List[str]] = None,
        has_rag: bool = False,
        model_size: str = "medium",
    ) -> str:
        """
        Register a local capability.
        
        This adds the capability to the gradient table with hops=0
        and to the cascade matcher for matching.
        
        Args:
            label: Short label (e.g., "llm", "vision")
            description: Full description for embedding
            handler: Handler function/service name
            models: Available models for this capability
            constraints: Resource constraints
            specializations: Model specializations (e.g., ["code", "medical"])
            has_rag: Whether this capability has RAG support
            model_size: Model size category ("tiny", "small", "medium", "large", "huge")
            
        Returns:
            The capability ID (node_id:label)
        """
        if not self._initialized:
            await self.initialize()
        
        cap_id = f"{self.node_id}:{label}"
        
        # Generate embeddings
        embedding_vector = None
        if self._embedding_available:
            try:
                embedding_vector = await self.embedding_engine.embed(description)
            except Exception as e:
                logger.warning(f"Embedding failed for {label}: {e}")
        
        # Model metadata
        model_info = {
            "handler": handler,
            "models": models or [],
            "constraints": constraints or {},
            "specializations": specializations or [],
            "has_rag": has_rag,
            "size": model_size,
        }
        
        # Add to gradient table (hops=0 for local)
        self.gradient_table.update(
            capability_id=cap_id,
            capability_label=label,
            capability_vector=embedding_vector if embedding_vector is not None else np.zeros(384),
            hops=0,
            next_hop=self.node_id,
            via_node=self.node_id,
            estimated_latency_ms=1.0,  # Local = ~1ms
        )
        
        # Add to matcher
        self.matcher.add_capability(
            cap_id=cap_id,
            label=label,
            description=description,
            embedding_vector=embedding_vector,
            metadata=model_info,
        )
        
        # Track as local
        self.local_capability_ids.add(cap_id)
        
        logger.info(
            f"📝 Registered capability: {label} "
            f"(emb={'✓' if embedding_vector is not None else '✗'}, "
            f"rag={'✓' if has_rag else '✗'}, size={model_size})"
        )
        
        return cap_id

    async def route(
        self,
        intent: str,
        constraints: Optional[RouteConstraints] = None,
    ) -> RouteResult:
        """
        Route an intent using unified gradient table + cascade + scoring.
        
        Pipeline:
        0. Classify intent (complexity, task type, requirements)
        1. Match using cascade (embedding → hash → keyword)
        2. Gather candidates from gradient table
        3. Score candidates (semantic + latency + capability + hop + cost)
        4. Apply constraints filtering
        5. Select best candidate
        6. Build detailed result with explanation
        
        Args:
            intent: Natural language intent
            constraints: Optional routing constraints
            
        Returns:
            RouteResult with routing decision
        """
        if not self._initialized:
            await self.initialize()
        
        constraints = constraints or RouteConstraints()
        
        # === LAYER 0: Intent Classification (THE CROWN JEWEL) ===
        intent_class = classify_intent(intent)
        logger.info(
            f"🎯 INTENT: {intent_class.complexity.name} ({intent_class.task_type.value}) "
            f"→ {intent_class.recommended_model_size}"
        )
        
        # === STEP 1: Gather all candidates from gradient table ===
        candidates = await self._gather_candidates(intent, intent_class)
        
        if not candidates:
            return RouteResult(
                action=RouteAction.NO_MATCH,
                reason="No capabilities available in mesh",
                match_method=MatchMethod.FALLBACK,
                intent_classification=intent_class.to_dict(),
            )
        
        logger.debug(f"📊 Gathered {len(candidates)} candidates from gradient table")
        
        # === STEP 2: Apply constraints filtering ===
        filtered = filter_candidates(candidates, constraints)
        
        if not filtered:
            return RouteResult(
                action=RouteAction.NO_MATCH,
                reason=f"All {len(candidates)} candidates filtered by constraints",
                match_method=MatchMethod.FALLBACK,
                intent_classification=intent_class.to_dict(),
            )
        
        # === STEP 3: Rank by composite score ===
        ranked = self.scorer.rank_candidates(filtered)
        
        # Log top candidates
        logger.info(f"📊 Top candidates for '{intent[:40]}...':")
        for i, candidate in enumerate(ranked[:3]):
            logger.info(
                f"  {i+1}. {candidate.capability_label} @ {candidate.node_id[:8]} "
                f"({candidate.explain()})"
            )
        
        # === STEP 4: Select best ===
        best = ranked[0]
        
        # === STEP 5: Build result ===
        action = RouteAction.PROCESS_LOCAL if best.is_local else RouteAction.FORWARD
        
        result = RouteResult(
            action=action,
            capability_id=best.capability_id,
            capability_label=best.capability_label,
            node_id=best.node_id,
            semantic_score=best.semantic_score,
            composite_score=best.composite_score,
            hops=best.hops,
            estimated_latency_ms=best.estimated_latency_ms,
            is_local=best.is_local,
            next_hop=None if best.is_local else best.node_id,
            via_node=best.node_id,
            reason=self._build_reason(best, intent_class),
            match_method=best.match_method,
            score_breakdown=best.score_breakdown,
            intent_classification=intent_class.to_dict(),
        )
        
        # Log final decision
        logger.info(
            f"✅ ROUTED to {best.capability_label} @ {best.node_id[:8]}: {result.reason}"
        )
        
        return result

    async def _gather_candidates(
        self,
        intent: str,
        intent_class: IntentClassification,
    ) -> List[RouteCandidate]:
        """
        Gather and score all candidates from gradient table.
        
        Uses unified pipeline:
        1. Get intent embedding (if available)
        2. Match against all gradient entries using cascade
        3. Create RouteCandidate for each with computed scores
        """
        candidates = []
        
        # Get intent embedding
        intent_embedding = None
        if self._embedding_available:
            try:
                intent_embedding = await self.embedding_engine.embed(intent)
            except Exception as e:
                logger.debug(f"Embedding failed: {e}")
        
        # Process all gradient entries
        for entry in self.gradient_table.all_entries():
            # Check if capability is registered in matcher
            # (It might not be if it's a remote capability from gossip)
            if entry.capability_id not in self.matcher.capabilities:
                # Add remote capability to matcher on the fly
                self.matcher.add_capability(
                    cap_id=entry.capability_id,
                    label=entry.capability_label,
                    description=entry.capability_label,  # Use label as description
                    embedding_vector=entry.capability_vector,
                    metadata={},
                )
            
            # Match using cascade
            match_result, _ = self.matcher.match(
                intent_text=intent,
                intent_embedding=intent_embedding,
                return_all_scores=False,
            )
            
            if not match_result or match_result.capability_id != entry.capability_id:
                # This entry didn't match (or matcher returned different capability)
                # Create a fallback candidate with low score
                semantic_score = 0.1
                match_method = MatchMethod.FALLBACK
            else:
                semantic_score = match_result.score
                match_method = match_result.method
            
            # Get model info
            model_info = self.model_info_fn(entry.capability_id)
            
            # Check if local
            is_local = entry.capability_id in self.local_capability_ids
            
            # Check reachability
            is_reachable = self.peer_reachability_fn(entry.via_node) if not is_local else True
            
            # Create candidate
            candidate = create_candidate(
                capability_id=entry.capability_id,
                capability_label=entry.capability_label,
                node_id=entry.via_node,
                is_local=is_local,
                semantic_score=semantic_score,
                estimated_latency_ms=entry.estimated_latency_ms,
                hops=entry.hops,
                model_info=model_info,
                is_reachable=is_reachable,
                match_method=match_method.value,
            )
            
            # Compute capability score
            self.scorer.compute_capability_score(candidate, intent_class.to_dict())
            
            # Store match method
            candidate.match_method = match_method.value
            
            candidates.append(candidate)
        
        return candidates

    def _build_reason(
        self,
        candidate: RouteCandidate,
        intent_class: IntentClassification,
    ) -> str:
        """
        Build detailed human-readable routing reason.
        
        Example:
        "Routed to llama-expert@node-abc because: semantic=0.85 (embedding), 
        latency=50ms, has_rag=true, specialization=animals, hops=1, cost=$0.00"
        """
        parts = []
        
        # Semantic match
        parts.append(f"semantic={candidate.semantic_score:.2f} ({candidate.match_method})")
        
        # Latency
        if not candidate.is_local:
            parts.append(f"latency={candidate.estimated_latency_ms:.0f}ms")
        
        # Capability features
        if candidate.model_info.get("has_rag"):
            parts.append("has_rag=true")
        
        specializations = candidate.model_info.get("specializations", [])
        if specializations:
            parts.append(f"specialization={','.join(specializations[:2])}")
        
        # Hops
        if candidate.hops > 0:
            parts.append(f"hops={candidate.hops}")
        
        # Cost
        parts.append(f"cost=$0.00" if candidate.is_local else "cost=API")
        
        # Composite score
        parts.append(f"composite={candidate.composite_score:.3f}")
        
        return f"Routed to {candidate.capability_label}@{candidate.node_id[:8]} because: {', '.join(parts)}"

    async def update_remote_capability(
        self,
        capability_id: str,
        capability_label: str,
        capability_vector: np.ndarray,
        hops: int,
        next_hop: str,
        via_node: str,
        estimated_latency_ms: Optional[float] = None,
    ) -> bool:
        """
        Update gradient table with remote capability from gossip.
        
        This is called when receiving capability announcements.
        """
        return self.gradient_table.update(
            capability_id=capability_id,
            capability_label=capability_label,
            capability_vector=capability_vector,
            hops=hops,
            next_hop=next_hop,
            via_node=via_node,
            estimated_latency_ms=estimated_latency_ms,
        )

    def get_local_capabilities(self) -> List[Tuple[str, str, np.ndarray]]:
        """
        Get local capabilities for gossip announcements.
        
        Returns list of (id, label, vector) tuples.
        """
        capabilities = []
        for cap_id in self.local_capability_ids:
            entry = self.gradient_table.get(cap_id)
            if entry:
                capabilities.append((
                    entry.capability_id,
                    entry.capability_label,
                    entry.capability_vector,
                ))
        return capabilities

    def invalidate_node(self, node_id: str) -> int:
        """
        Remove all capabilities from a disconnected node.
        
        Returns number of capabilities removed.
        """
        return self.gradient_table.invalidate_node(node_id)

    def prune_expired(self) -> int:
        """
        Remove expired gradient entries.
        
        Returns number of entries removed.
        """
        return self.gradient_table.prune_expired()

    def stats(self) -> dict:
        """Get router statistics."""
        return {
            "node_id": self.node_id,
            "embedding_available": self._embedding_available,
            "local_capabilities": len(self.local_capability_ids),
            "total_capabilities": len(self.gradient_table),
            "matcher_capabilities": len(self.matcher),
            "gradient_stats": self.gradient_table.stats(),
        }

    async def test_cascade(self, intent: str) -> Dict:
        """
        Test cascade matching for an intent (debugging).
        
        Returns detailed breakdown of each tier's results.
        """
        if not self._initialized:
            await self.initialize()
        
        intent_embedding = None
        if self._embedding_available:
            try:
                intent_embedding = await self.embedding_engine.embed(intent)
            except Exception:
                pass
        
        results = {
            "intent": intent,
            "embedding_available": self._embedding_available,
            "tiers": {},
        }
        
        # Test each tier
        best_result, all_results = self.matcher.match(
            intent_text=intent,
            intent_embedding=intent_embedding,
            return_all_scores=True,
        )
        
        if best_result:
            results["best"] = {
                "capability": best_result.capability_label,
                "score": best_result.score,
                "method": best_result.method.value,
                "passed_threshold": best_result.passed_threshold,
            }
        
        if all_results:
            results["all_tiers"] = [
                {
                    "capability": r.capability_label,
                    "score": r.score,
                    "method": r.method.value,
                    "passed": r.passed_threshold,
                }
                for r in all_results
            ]
        
        return results
