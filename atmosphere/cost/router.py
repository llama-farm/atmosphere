"""
Cost-Aware Router - Integrate cost factors into routing decisions.

Wraps the capability router to add cost-based node selection
among capable nodes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Protocol, Any

from .collector import NodeCostFactors
from .model import WorkRequest, compute_node_cost, select_best_node
from .gossip import CostGossipState


class ProjectRouter(Protocol):
    """Protocol for the project/capability router."""
    
    def route(self, model: str, messages: list[dict]) -> Any:
        """Route a request to a project."""
        ...


@dataclass
class RouteResult:
    """Result of a cost-aware routing decision."""
    
    success: bool
    selected_node: Optional[str] = None
    cost_score: float = 0.0
    reason: str = ""
    project: Optional[Any] = None
    
    # Cost breakdown for debugging/observability
    cost_breakdown: dict = field(default_factory=dict)


@dataclass
class CostAwareRouter:
    """
    Router that considers node cost in selection.
    
    Integrates with the capability router for capability matching,
    then applies cost-based selection among capable nodes.
    """
    
    cost_state: CostGossipState
    local_node_id: str
    local_cost_collector: Optional[Any] = None  # CostCollector
    
    # Configuration
    budget_sensitivity: float = 1.0
    min_cost_difference: float = 0.2  # Hysteresis threshold
    
    # Sticky routing to prevent oscillation
    _last_selected: dict = field(default_factory=dict)  # work_key -> node_id
    
    def route_to_node(
        self,
        candidate_nodes: list[str],
        work: Optional[WorkRequest] = None,
        work_key: Optional[str] = None,
        budget_sensitivity: Optional[float] = None,
    ) -> RouteResult:
        """
        Select the best node from candidates based on cost.
        
        Args:
            candidate_nodes: List of node IDs that can handle the work
            work: Description of the work (for cost calculation)
            work_key: Key for sticky routing (e.g., model name)
            budget_sensitivity: Override for budget sensitivity
        
        Returns:
            RouteResult with selected node and cost info
        """
        if not candidate_nodes:
            return RouteResult(
                success=False,
                reason="No candidate nodes available"
            )
        
        if work is None:
            work = WorkRequest()
        
        sensitivity = budget_sensitivity or self.budget_sensitivity
        
        # Get cost factors for each candidate
        node_factors = []
        cost_breakdown = {}
        
        for node_id in candidate_nodes:
            factors = self._get_node_factors(node_id)
            if factors is not None:
                node_factors.append(factors)
                cost = compute_node_cost(factors, work, sensitivity)
                cost_breakdown[node_id] = {
                    "cost": cost,
                    "on_battery": factors.on_battery,
                    "battery_percent": factors.battery_percent,
                    "cpu_load": factors.cpu_load,
                    "memory_percent": factors.memory_percent,
                }
        
        if not node_factors:
            # No cost data - use first candidate
            return RouteResult(
                success=True,
                selected_node=candidate_nodes[0],
                cost_score=1.0,
                reason="No cost data available, using first candidate",
                cost_breakdown={},
            )
        
        # Get sticky preference if any
        prefer_current = None
        if work_key and work_key in self._last_selected:
            prefer_current = self._last_selected[work_key]
        
        # Select best node with hysteresis
        best_node, best_cost = select_best_node(
            nodes=node_factors,
            work=work,
            budget_sensitivity=sensitivity,
            min_cost_difference=self.min_cost_difference,
            prefer_current=prefer_current,
        )
        
        # Update sticky routing
        if work_key:
            self._last_selected[work_key] = best_node.node_id
        
        # Build reason string
        if len(node_factors) > 1:
            sorted_nodes = sorted(
                cost_breakdown.items(),
                key=lambda x: x[1]["cost"]
            )
            reason_parts = [f"{node_id}: {info['cost']:.2f}" for node_id, info in sorted_nodes[:3]]
            reason = f"Selected {best_node.node_id} (costs: {', '.join(reason_parts)})"
        else:
            reason = f"Selected {best_node.node_id} (only candidate with cost data)"
        
        return RouteResult(
            success=True,
            selected_node=best_node.node_id,
            cost_score=best_cost,
            reason=reason,
            cost_breakdown=cost_breakdown,
        )
    
    def _get_node_factors(self, node_id: str) -> Optional[NodeCostFactors]:
        """
        Get cost factors for a node.
        
        For local node, collect fresh data.
        For remote nodes, use gossip state.
        """
        if node_id == self.local_node_id:
            if self.local_cost_collector:
                return self.local_cost_collector.collect()
            else:
                # No collector, create minimal factors
                return NodeCostFactors(
                    node_id=node_id,
                    timestamp=time.time(),
                )
        else:
            return self.cost_state.get_node_cost(node_id)
    
    def estimate_tokens(self, messages: list[dict]) -> int:
        """
        Rough token estimate from messages.
        
        Args:
            messages: List of message dicts with 'content' key
        
        Returns:
            Estimated token count
        """
        text = " ".join(
            m.get("content", "")
            for m in messages
            if isinstance(m.get("content"), str)
        )
        # Rough approximation: ~4 chars per token
        return len(text) // 4


@dataclass
class IntegratedCostRouter:
    """
    Full integration with project router.
    
    This wraps a capability/project router and adds cost-aware
    node selection on top of capability matching.
    """
    
    project_router: ProjectRouter
    cost_router: CostAwareRouter
    
    def route(
        self,
        model: str,
        messages: list[dict],
        work_type: str = "inference",
        budget_sensitivity: float = 1.0,
    ) -> RouteResult:
        """
        Route a request considering both capability and cost.
        
        Args:
            model: Model name to route
            messages: Request messages
            work_type: Type of work ("inference", "embedding", etc.)
            budget_sensitivity: Cost sensitivity (1.0 = balanced)
        
        Returns:
            RouteResult with selected node
        """
        # Step 1: Get capability-matched project
        project_result = self.project_router.route(model, messages)
        
        if not getattr(project_result, 'success', True):
            return RouteResult(
                success=False,
                reason=getattr(project_result, 'reason', "No capable project found"),
            )
        
        project = getattr(project_result, 'project', None)
        
        # Step 2: Get nodes that have this project
        candidate_nodes = getattr(project, 'nodes', None)
        if candidate_nodes is None:
            # Try to get nodes from project result
            candidate_nodes = getattr(project_result, 'nodes', None)
        
        if not candidate_nodes:
            # Only one node (implicit) - use project router result
            return RouteResult(
                success=True,
                selected_node=getattr(project_result, 'node_id', None),
                cost_score=1.0,
                reason="Single node project",
                project=project,
            )
        
        # Step 3: Build work request
        work = WorkRequest(
            work_type=work_type,
            estimated_input_tokens=self.cost_router.estimate_tokens(messages),
            requires_gpu=work_type in ("inference", "embedding"),
            model_preference=model,
        )
        
        # Step 4: Select lowest cost node
        cost_result = self.cost_router.route_to_node(
            candidate_nodes=list(candidate_nodes),
            work=work,
            work_key=model,  # Sticky routing per model
            budget_sensitivity=budget_sensitivity,
        )
        
        cost_result.project = project
        return cost_result
