"""
Cost Model - Cost calculation and node scoring.

Computes routing costs based on power state, compute load, network conditions,
and API costs to enable intelligent work routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .collector import NodeCostFactors


# =============================================================================
# API Cost Table
# =============================================================================

@dataclass
class APIModelCost:
    """API pricing per million tokens."""
    input_per_million: float   # $ per 1M input tokens
    output_per_million: float  # $ per 1M output tokens


# API costs as of 2024 (update periodically)
API_COSTS: dict[str, APIModelCost] = {
    # OpenAI
    "gpt-4o": APIModelCost(2.50, 10.00),
    "gpt-4o-mini": APIModelCost(0.15, 0.60),
    "gpt-4-turbo": APIModelCost(10.00, 30.00),
    "gpt-3.5-turbo": APIModelCost(0.50, 1.50),
    
    # Anthropic
    "claude-3-5-sonnet": APIModelCost(3.00, 15.00),
    "claude-3-5-sonnet-20241022": APIModelCost(3.00, 15.00),
    "claude-3-haiku": APIModelCost(0.25, 1.25),
    "claude-3-opus": APIModelCost(15.00, 75.00),
    
    # Google
    "gemini-1.5-pro": APIModelCost(1.25, 5.00),
    "gemini-1.5-flash": APIModelCost(0.075, 0.30),
}


def estimate_api_cost(
    model: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int
) -> float:
    """
    Estimate API cost for a request in USD.
    
    Args:
        model: Model name (e.g., "gpt-4o", "claude-3-5-sonnet")
        estimated_input_tokens: Estimated input token count
        estimated_output_tokens: Estimated output token count
    
    Returns:
        Estimated cost in USD (0.0 if model not found or local)
    """
    # Check exact match first
    cost = API_COSTS.get(model)
    
    # Try wildcard patterns for local models
    if cost is None:
        for pattern, c in API_COSTS.items():
            if pattern.endswith("*") and model.startswith(pattern[:-1]):
                cost = c
                break
    
    if cost is None:
        return 0.0  # Unknown model, assume free/local
    
    input_cost = (estimated_input_tokens / 1_000_000) * cost.input_per_million
    output_cost = (estimated_output_tokens / 1_000_000) * cost.output_per_million
    
    return input_cost + output_cost


# =============================================================================
# Work Request
# =============================================================================

@dataclass
class WorkRequest:
    """Description of work to be routed."""
    
    work_type: str = "general"  # "inference", "embedding", "rag", "general"
    estimated_input_tokens: int = 1000
    estimated_output_tokens: int = 500
    data_size_bytes: int = 0
    requires_gpu: bool = False
    model_preference: Optional[str] = None


# =============================================================================
# Cost Multipliers
# =============================================================================

def power_cost_multiplier(
    on_battery: bool,
    battery_percent: float = 100.0
) -> float:
    """
    Calculate cost multiplier from power state.
    
    Args:
        on_battery: True if running on battery power
        battery_percent: Current battery percentage (0-100)
    
    Returns:
        Cost multiplier (1.0 = baseline, higher = more expensive)
    
    Multipliers:
        - Plugged in: 1.0x (free power)
        - On battery, >50%: 2.0x (preserve battery)
        - On battery, 20-50%: 3.0x (getting urgent)
        - On battery, <20%: 5.0x (critical - avoid if possible)
    """
    if not on_battery:
        return 1.0
    
    if battery_percent < 20:
        return 5.0
    elif battery_percent < 50:
        return 3.0
    else:
        return 2.0


def compute_load_multiplier(
    cpu_load: float,
    gpu_load: float = 0.0,
    memory_percent: float = 0.0,
    work_type: str = "general"
) -> float:
    """
    Calculate cost multiplier from compute load.
    
    Args:
        cpu_load: Normalized CPU load (0-2.0, where 1.0 = 100% of all cores)
        gpu_load: GPU utilization percentage (0-100)
        memory_percent: Memory usage percentage (0-100)
        work_type: Type of work ("inference", "embedding", "rag", "general")
    
    Returns:
        Cost multiplier (1.0 = baseline, higher = more expensive)
    
    CPU Multipliers:
        - <25% load: 1.0x (idle)
        - 25-50% load: 1.3x (light work)
        - 50-75% load: 1.6x (moderate work)
        - >75% load: 2.0x (heavy work)
    
    GPU Multipliers (for inference/embedding work):
        - <25% load: 1.0x
        - 25-50% load: 1.5x
        - >50% load: 2.0x
    
    Memory Multipliers:
        - <80%: 1.0x (plenty of room)
        - 80-90%: 1.5x (getting tight)
        - >90%: 2.5x (memory pressure)
    """
    multiplier = 1.0
    
    # CPU load
    if cpu_load > 0.75:
        multiplier *= 2.0
    elif cpu_load > 0.50:
        multiplier *= 1.6
    elif cpu_load > 0.25:
        multiplier *= 1.3
    
    # GPU load (only for GPU-intensive work)
    if work_type in ("inference", "embedding", "generation"):
        if gpu_load > 50:
            multiplier *= 2.0
        elif gpu_load > 25:
            multiplier *= 1.5
    
    # Memory pressure
    if memory_percent > 90:
        multiplier *= 2.5
    elif memory_percent > 80:
        multiplier *= 1.5
    
    return multiplier


def network_cost_multiplier(
    bandwidth_mbps: Optional[float],
    is_metered: bool,
    work_type: str = "general"
) -> float:
    """
    Calculate cost multiplier from network conditions.
    
    Args:
        bandwidth_mbps: Estimated bandwidth in Mbps (None if unknown)
        is_metered: True if connection is metered (mobile hotspot, etc.)
        work_type: Type of work
    
    Returns:
        Cost multiplier (1.0 = baseline, higher = more expensive)
    
    Bandwidth Multipliers:
        - >100 Mbps: 1.0x (fast)
        - 10-100 Mbps: 1.2x (acceptable)
        - 1-10 Mbps: 2.0x (slow)
        - <1 Mbps: 5.0x (very slow)
    
    Metered: 3.0x (data costs money)
    
    Data-heavy work (rag, file_transfer) amplifies network costs.
    """
    multiplier = 1.0
    
    # Metered connection is expensive
    if is_metered:
        multiplier *= 3.0
    
    # Bandwidth impact
    if bandwidth_mbps is not None:
        if bandwidth_mbps < 1:
            multiplier *= 5.0
        elif bandwidth_mbps < 10:
            multiplier *= 2.0
        elif bandwidth_mbps < 100:
            multiplier *= 1.2
    # Unknown bandwidth: assume it's okay (multiplier stays 1.0)
    
    # Data-heavy work is more sensitive to network
    if work_type in ("rag", "file_transfer", "embedding_large"):
        # Amplify network-related costs for data-heavy work
        if is_metered or (bandwidth_mbps is not None and bandwidth_mbps < 10):
            multiplier *= 1.5
    
    return multiplier


# =============================================================================
# Main Cost Calculation
# =============================================================================

def compute_node_cost(
    node: NodeCostFactors,
    work: WorkRequest,
    budget_sensitivity: float = 1.0
) -> float:
    """
    Compute total cost score for routing work to a node.
    
    Lower cost = better routing choice.
    
    Args:
        node: Current cost factors for the node
        work: Description of the work to route
        budget_sensitivity: 1.0 = balanced, >1 = cost-conscious, <1 = quality-focused
    
    Returns:
        Cost score (1.0 = baseline, higher = more expensive)
    
    The cost is a product of individual multipliers:
    - Power: 1.0-5.0x based on battery state
    - CPU: 1.0-2.0x based on load
    - GPU: 1.0-2.0x for inference work
    - Memory: 1.0-2.5x based on pressure
    - Network: 1.0-5.0x based on bandwidth/metered
    - API: Added cost for cloud API calls
    - Latency: Penalty for high latency (>100ms)
    """
    cost = 1.0
    
    # === Power State ===
    cost *= power_cost_multiplier(node.on_battery, node.battery_percent)
    
    # === Compute Load ===
    cost *= compute_load_multiplier(
        cpu_load=node.cpu_load,
        gpu_load=node.gpu_load,
        memory_percent=node.memory_percent,
        work_type=work.work_type,
    )
    
    # === Network ===
    cost *= network_cost_multiplier(
        bandwidth_mbps=node.bandwidth_mbps,
        is_metered=node.is_metered,
        work_type=work.work_type,
    )
    
    # === Data-Heavy Work Additional Penalty ===
    if work.data_size_bytes > 1_000_000:  # > 1MB
        if node.is_metered or (node.bandwidth_mbps and node.bandwidth_mbps < 10):
            cost *= 1.5
    
    # === Latency Penalty ===
    if node.latency_ms is not None and node.latency_ms > 100:
        # +1.0 per 500ms over 100ms baseline
        cost *= 1.0 + (node.latency_ms - 100) / 500
    
    # === Cloud API Cost ===
    if node.api_model:
        estimated_usd = estimate_api_cost(
            node.api_model,
            work.estimated_input_tokens,
            work.estimated_output_tokens,
        )
        # Scale: $0.01 = 1.0 added cost
        cost += estimated_usd * 100 * budget_sensitivity
    
    return cost


def select_best_node(
    nodes: list[NodeCostFactors],
    work: WorkRequest,
    budget_sensitivity: float = 1.0,
    min_cost_difference: float = 0.2,
    prefer_current: Optional[str] = None,
) -> tuple[NodeCostFactors, float]:
    """
    Select the best node for a work request with hysteresis.
    
    Args:
        nodes: List of candidate nodes with cost factors
        work: Description of the work to route
        budget_sensitivity: Cost sensitivity (1.0 = balanced)
        min_cost_difference: Minimum relative cost difference to switch nodes (hysteresis)
        prefer_current: Node ID to prefer (sticky routing)
    
    Returns:
        Tuple of (best_node, cost_score)
    
    Raises:
        ValueError: If no nodes available
    """
    if not nodes:
        raise ValueError("No nodes available")
    
    # Score all candidates
    scored = [
        (node, compute_node_cost(node, work, budget_sensitivity))
        for node in nodes
    ]
    
    # Sort by cost (ascending - lower is better)
    scored.sort(key=lambda x: x[1])
    
    best_node, best_cost = scored[0]
    
    # Hysteresis: prefer current node unless significantly worse
    if prefer_current and prefer_current != best_node.node_id:
        for node, cost in scored:
            if node.node_id == prefer_current:
                # Only switch if new node is significantly cheaper
                if cost <= best_cost * (1 + min_cost_difference):
                    return node, cost
                break
    
    return best_node, best_cost
