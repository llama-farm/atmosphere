"""
Cost Model - Dynamic cost-aware routing for Atmosphere mesh.

Collects system metrics (power, CPU, memory, GPU, network) and uses them
to score nodes for intelligent work routing.
"""

from .collector import (
    CostCollector,
    NodeCostFactors,
    get_cost_collector,
)
from .model import (
    WorkRequest,
    compute_node_cost,
    power_cost_multiplier,
    compute_load_multiplier,
    network_cost_multiplier,
)
from .gossip import CostGossipState, CostBroadcaster
from .router import CostAwareRouter

__all__ = [
    # Collector
    "CostCollector",
    "NodeCostFactors",
    "get_cost_collector",
    # Model
    "WorkRequest",
    "compute_node_cost",
    "power_cost_multiplier",
    "compute_load_multiplier",
    "network_cost_multiplier",
    # Gossip
    "CostGossipState",
    "CostBroadcaster",
    # Router
    "CostAwareRouter",
]
