"""
Routing constraints and filtering.

Provides flexible constraint system for route selection:
- max_latency_ms: Maximum acceptable latency
- prefer_local: Prefer local capabilities over remote
- require_rag: Only match capabilities with RAG support
- model_size_min/max: Model size constraints
- require_reachable: Only use reachable nodes
- max_hops: Maximum hop count
- min_score: Minimum semantic score

Constraints can be combined to create complex routing policies.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set, Callable, Any

logger = logging.getLogger(__name__)


class ModelSize(Enum):
    """Model size categories."""
    TINY = "tiny"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    HUGE = "huge"
    
    @classmethod
    def from_string(cls, size: str) -> "ModelSize":
        """Parse model size from string."""
        try:
            return cls(size.lower())
        except ValueError:
            return cls.MEDIUM
    
    def __lt__(self, other):
        """Enable comparison for min/max filtering."""
        order = {
            ModelSize.TINY: 0,
            ModelSize.SMALL: 1,
            ModelSize.MEDIUM: 2,
            ModelSize.LARGE: 3,
            ModelSize.HUGE: 4,
        }
        return order[self] < order[other]
    
    def __le__(self, other):
        return self < other or self == other
    
    def __gt__(self, other):
        return not self <= other
    
    def __ge__(self, other):
        return not self < other


@dataclass
class RouteConstraints:
    """
    Routing constraints for filtering candidates.
    
    All constraints are optional. If not specified, no filtering is applied.
    
    Example:
        constraints = RouteConstraints(
            max_latency_ms=200,
            prefer_local=True,
            require_rag=True,
            model_size_min="small",
            model_size_max="medium",
        )
        
        filtered = filter_candidates(candidates, constraints)
    """
    
    # Latency constraints
    max_latency_ms: Optional[float] = None
    
    # Locality constraints
    prefer_local: bool = False  # If True, only use local if any available
    require_local: bool = False  # If True, only return local candidates
    
    # Capability constraints
    require_rag: bool = False
    require_specialization: Optional[str] = None  # e.g., "code", "medical"
    
    # Model size constraints
    model_size_min: Optional[str] = None  # "tiny", "small", etc.
    model_size_max: Optional[str] = None
    
    # Network constraints
    require_reachable: bool = True
    max_hops: Optional[int] = None
    
    # Score constraints
    min_semantic_score: Optional[float] = None
    min_composite_score: Optional[float] = None
    
    # Custom constraints
    custom_filter: Optional[Callable[[Any], bool]] = None
    
    # Exclusions
    exclude_nodes: Set[str] = field(default_factory=set)
    exclude_capabilities: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> dict:
        """Convert to dict for logging/serialization."""
        return {
            k: v for k, v in self.__dict__.items()
            if v is not None and k != "custom_filter"
        }


def filter_candidates(
    candidates: List[Any],
    constraints: RouteConstraints,
) -> List[Any]:
    """
    Filter route candidates based on constraints.
    
    Args:
        candidates: List of RouteCandidate objects
        constraints: Constraint specification
        
    Returns:
        Filtered list of candidates
        
    Note: If all candidates are filtered out, returns original list
          (fail-safe to avoid complete routing failure)
    """
    if not candidates:
        return []
    
    original_count = len(candidates)
    filtered = candidates
    
    # Track which filters removed candidates (for logging)
    filters_applied = []
    
    # === Latency constraint ===
    if constraints.max_latency_ms is not None:
        before = len(filtered)
        filtered = [
            c for c in filtered
            if c.estimated_latency_ms <= constraints.max_latency_ms
        ]
        if len(filtered) < before:
            filters_applied.append(
                f"max_latency_ms={constraints.max_latency_ms} "
                f"(removed {before - len(filtered)})"
            )
    
    # === Locality constraints ===
    if constraints.require_local:
        before = len(filtered)
        filtered = [c for c in filtered if c.is_local]
        if len(filtered) < before:
            filters_applied.append(f"require_local (removed {before - len(filtered)})")
    elif constraints.prefer_local:
        local = [c for c in filtered if c.is_local]
        if local:
            before = len(filtered)
            filtered = local
            if len(filtered) < before:
                filters_applied.append(f"prefer_local (kept {len(filtered)} local)")
    
    # === Reachability constraint ===
    if constraints.require_reachable:
        before = len(filtered)
        filtered = [c for c in filtered if c.is_reachable]
        if len(filtered) < before:
            filters_applied.append(
                f"require_reachable (removed {before - len(filtered)})"
            )
    
    # === Hop constraint ===
    if constraints.max_hops is not None:
        before = len(filtered)
        filtered = [c for c in filtered if c.hops <= constraints.max_hops]
        if len(filtered) < before:
            filters_applied.append(
                f"max_hops={constraints.max_hops} (removed {before - len(filtered)})"
            )
    
    # === RAG constraint ===
    if constraints.require_rag:
        before = len(filtered)
        filtered = [
            c for c in filtered
            if c.model_info.get("has_rag", False)
        ]
        if len(filtered) < before:
            filters_applied.append(f"require_rag (removed {before - len(filtered)})")
    
    # === Specialization constraint ===
    if constraints.require_specialization:
        before = len(filtered)
        spec = constraints.require_specialization.lower()
        filtered = [
            c for c in filtered
            if spec in [s.lower() for s in c.model_info.get("specializations", [])]
        ]
        if len(filtered) < before:
            filters_applied.append(
                f"require_specialization={spec} (removed {before - len(filtered)})"
            )
    
    # === Model size constraints ===
    if constraints.model_size_min or constraints.model_size_max:
        before = len(filtered)
        
        min_size = ModelSize.from_string(constraints.model_size_min) if constraints.model_size_min else None
        max_size = ModelSize.from_string(constraints.model_size_max) if constraints.model_size_max else None
        
        def size_check(candidate):
            size_str = candidate.model_info.get("size", "medium")
            size = ModelSize.from_string(size_str)
            
            if min_size and size < min_size:
                return False
            if max_size and size > max_size:
                return False
            return True
        
        filtered = [c for c in filtered if size_check(c)]
        
        if len(filtered) < before:
            size_range = f"{constraints.model_size_min or '?'}-{constraints.model_size_max or '?'}"
            filters_applied.append(
                f"model_size={size_range} (removed {before - len(filtered)})"
            )
    
    # === Score constraints ===
    if constraints.min_semantic_score is not None:
        before = len(filtered)
        filtered = [
            c for c in filtered
            if c.semantic_score >= constraints.min_semantic_score
        ]
        if len(filtered) < before:
            filters_applied.append(
                f"min_semantic_score={constraints.min_semantic_score:.2f} "
                f"(removed {before - len(filtered)})"
            )
    
    if constraints.min_composite_score is not None:
        before = len(filtered)
        filtered = [
            c for c in filtered
            if c.composite_score >= constraints.min_composite_score
        ]
        if len(filtered) < before:
            filters_applied.append(
                f"min_composite_score={constraints.min_composite_score:.2f} "
                f"(removed {before - len(filtered)})"
            )
    
    # === Exclusions ===
    if constraints.exclude_nodes:
        before = len(filtered)
        filtered = [
            c for c in filtered
            if c.node_id not in constraints.exclude_nodes
        ]
        if len(filtered) < before:
            filters_applied.append(
                f"exclude_nodes (removed {before - len(filtered)})"
            )
    
    if constraints.exclude_capabilities:
        before = len(filtered)
        filtered = [
            c for c in filtered
            if c.capability_id not in constraints.exclude_capabilities
        ]
        if len(filtered) < before:
            filters_applied.append(
                f"exclude_capabilities (removed {before - len(filtered)})"
            )
    
    # === Custom filter ===
    if constraints.custom_filter:
        before = len(filtered)
        filtered = [c for c in filtered if constraints.custom_filter(c)]
        if len(filtered) < before:
            filters_applied.append(
                f"custom_filter (removed {before - len(filtered)})"
            )
    
    # === Fail-safe: Return original if all filtered out ===
    if not filtered:
        logger.warning(
            f"⚠️  All {original_count} candidates filtered out by constraints: "
            f"{', '.join(filters_applied)}. Returning original list."
        )
        return candidates
    
    # Log filter summary
    if filters_applied:
        logger.info(
            f"🔽 Filtered {original_count} → {len(filtered)} candidates: "
            f"{', '.join(filters_applied)}"
        )
    
    return filtered


def create_latency_constraint(max_ms: float) -> RouteConstraints:
    """Create constraint for maximum latency."""
    return RouteConstraints(max_latency_ms=max_ms)


def create_local_only_constraint() -> RouteConstraints:
    """Create constraint to only use local capabilities."""
    return RouteConstraints(require_local=True)


def create_rag_constraint(
    require_rag: bool = True,
    max_latency_ms: Optional[float] = None,
) -> RouteConstraints:
    """Create constraint for RAG-enabled models."""
    return RouteConstraints(
        require_rag=require_rag,
        max_latency_ms=max_latency_ms,
    )


def create_fast_route_constraint(
    max_latency_ms: float = 100,
    max_hops: int = 1,
    prefer_local: bool = True,
) -> RouteConstraints:
    """Create constraint for fast, low-latency routing."""
    return RouteConstraints(
        max_latency_ms=max_latency_ms,
        max_hops=max_hops,
        prefer_local=prefer_local,
    )


def merge_constraints(
    *constraint_list: RouteConstraints,
) -> RouteConstraints:
    """
    Merge multiple constraints (taking most restrictive).
    
    Example:
        c1 = RouteConstraints(max_latency_ms=200)
        c2 = RouteConstraints(require_rag=True)
        merged = merge_constraints(c1, c2)
        # merged has both max_latency_ms=200 and require_rag=True
    """
    if not constraint_list:
        return RouteConstraints()
    
    merged = RouteConstraints()
    
    for constraints in constraint_list:
        # Take minimum latency
        if constraints.max_latency_ms is not None:
            if merged.max_latency_ms is None:
                merged.max_latency_ms = constraints.max_latency_ms
            else:
                merged.max_latency_ms = min(merged.max_latency_ms, constraints.max_latency_ms)
        
        # Take minimum hops
        if constraints.max_hops is not None:
            if merged.max_hops is None:
                merged.max_hops = constraints.max_hops
            else:
                merged.max_hops = min(merged.max_hops, constraints.max_hops)
        
        # OR boolean constraints
        merged.prefer_local = merged.prefer_local or constraints.prefer_local
        merged.require_local = merged.require_local or constraints.require_local
        merged.require_rag = merged.require_rag or constraints.require_rag
        merged.require_reachable = merged.require_reachable or constraints.require_reachable
        
        # Take most restrictive model size
        if constraints.model_size_min:
            if not merged.model_size_min:
                merged.model_size_min = constraints.model_size_min
            else:
                min_current = ModelSize.from_string(merged.model_size_min)
                min_new = ModelSize.from_string(constraints.model_size_min)
                merged.model_size_min = max(min_current, min_new).value
        
        if constraints.model_size_max:
            if not merged.model_size_max:
                merged.model_size_max = constraints.model_size_max
            else:
                max_current = ModelSize.from_string(merged.model_size_max)
                max_new = ModelSize.from_string(constraints.model_size_max)
                merged.model_size_max = min(max_current, max_new).value
        
        # Union exclusions
        merged.exclude_nodes |= constraints.exclude_nodes
        merged.exclude_capabilities |= constraints.exclude_capabilities
        
        # Take maximum score thresholds
        if constraints.min_semantic_score is not None:
            if merged.min_semantic_score is None:
                merged.min_semantic_score = constraints.min_semantic_score
            else:
                merged.min_semantic_score = max(
                    merged.min_semantic_score,
                    constraints.min_semantic_score
                )
        
        if constraints.min_composite_score is not None:
            if merged.min_composite_score is None:
                merged.min_composite_score = constraints.min_composite_score
            else:
                merged.min_composite_score = max(
                    merged.min_composite_score,
                    constraints.min_composite_score
                )
    
    return merged
