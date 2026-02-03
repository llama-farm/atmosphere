"""
Cost Gossip - Propagate cost factors through the mesh.

Handles NODE_COST_UPDATE message broadcasting and tracking
of remote node cost factors for distributed routing decisions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

from .collector import NodeCostFactors
from .model import WorkRequest, compute_node_cost


# Message version for compatibility checking
COST_MESSAGE_VERSION = 1


class GossipClient(Protocol):
    """Protocol for gossip client integration."""
    
    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to the mesh."""
        ...


@dataclass
class CostGossipState:
    """
    Track cost factors from gossip updates.
    
    Maintains a cache of NodeCostFactors received from other nodes,
    with staleness tracking.
    """
    
    # node_id -> (NodeCostFactors, receive_timestamp)
    node_costs: dict[str, tuple[NodeCostFactors, float]] = field(default_factory=dict)
    
    # How old before we consider cost data stale (seconds)
    # Different thresholds for different urgency levels
    power_stale_seconds: float = 30.0  # Power state changes need fast propagation
    default_stale_seconds: float = 60.0  # Other factors can be a bit stale
    
    def handle_cost_update(self, message: dict) -> Optional[NodeCostFactors]:
        """
        Process a NODE_COST_UPDATE gossip message.
        
        Args:
            message: The gossip message dict
        
        Returns:
            The parsed NodeCostFactors, or None if invalid
        """
        if message.get("type") != "NODE_COST_UPDATE":
            return None
        
        node_id = message.get("node_id")
        if not node_id:
            return None
        
        # Check version compatibility
        version = message.get("version", 1)
        if version > COST_MESSAGE_VERSION:
            # Future version - try to parse anyway
            pass
        
        # Parse cost factors
        cost_factors = message.get("cost_factors", {})
        
        try:
            factors = NodeCostFactors(
                node_id=node_id,
                timestamp=message.get("timestamp", time.time()),
                on_battery=cost_factors.get("on_battery", False),
                battery_percent=cost_factors.get("battery_percent", 100.0),
                plugged_in=not cost_factors.get("on_battery", False),
                cpu_load=cost_factors.get("cpu_load", 0.0),
                gpu_load=cost_factors.get("gpu_load", 0.0),
                gpu_estimated=cost_factors.get("gpu_estimated", True),
                memory_percent=cost_factors.get("memory_percent", 0.0),
                memory_available_gb=cost_factors.get("memory_available_gb", 0.0),
                bandwidth_mbps=cost_factors.get("bandwidth_mbps"),
                is_metered=cost_factors.get("is_metered", False),
                latency_ms=cost_factors.get("latency_ms"),
            )
        except (TypeError, ValueError):
            return None
        
        self.node_costs[node_id] = (factors, time.time())
        return factors
    
    def get_node_cost(self, node_id: str) -> Optional[NodeCostFactors]:
        """
        Get cost factors for a node, if fresh enough.
        
        Args:
            node_id: The node to query
        
        Returns:
            NodeCostFactors if available and fresh, None otherwise
        """
        if node_id not in self.node_costs:
            return None
        
        factors, received_at = self.node_costs[node_id]
        age = time.time() - received_at
        
        # Use shorter threshold for power-sensitive decisions
        if factors.on_battery and age > self.power_stale_seconds:
            return None
        
        if age > self.default_stale_seconds:
            return None
        
        return factors
    
    def get_fresh_costs(self) -> list[NodeCostFactors]:
        """
        Get all non-stale cost factors.
        
        Returns:
            List of NodeCostFactors that are still fresh
        """
        now = time.time()
        fresh = []
        
        for factors, received_at in self.node_costs.values():
            age = now - received_at
            
            # Use appropriate threshold
            threshold = (
                self.power_stale_seconds if factors.on_battery
                else self.default_stale_seconds
            )
            
            if age < threshold:
                fresh.append(factors)
        
        return fresh
    
    def prune_stale(self) -> int:
        """
        Remove stale entries from the cache.
        
        Returns:
            Number of entries removed
        """
        now = time.time()
        stale_ids = []
        
        for node_id, (factors, received_at) in self.node_costs.items():
            age = now - received_at
            # Use longer threshold for pruning (2x default)
            if age > self.default_stale_seconds * 2:
                stale_ids.append(node_id)
        
        for node_id in stale_ids:
            del self.node_costs[node_id]
        
        return len(stale_ids)


def build_cost_message(factors: NodeCostFactors) -> dict:
    """
    Build a NODE_COST_UPDATE gossip message.
    
    Args:
        factors: The local node's cost factors
    
    Returns:
        Message dict ready for gossip broadcast
    """
    # Pre-compute overall cost for quick filtering
    overall_cost = compute_node_cost(factors, WorkRequest())
    
    return {
        "type": "NODE_COST_UPDATE",
        "version": COST_MESSAGE_VERSION,
        "node_id": factors.node_id,
        "timestamp": time.time(),
        "ttl": 60,  # Seconds until stale
        "cost_factors": {
            "on_battery": factors.on_battery,
            "battery_percent": factors.battery_percent,
            "cpu_load": factors.cpu_load,
            "gpu_load": factors.gpu_load,
            "gpu_estimated": factors.gpu_estimated,
            "memory_percent": factors.memory_percent,
            "memory_available_gb": factors.memory_available_gb,
            "bandwidth_mbps": factors.bandwidth_mbps,
            "is_metered": factors.is_metered,
            "overall_cost": overall_cost,
        }
    }


@dataclass
class CostBroadcaster:
    """
    Manage periodic cost factor broadcasts.
    
    Broadcasts cost updates:
    - On regular intervals (every 30 seconds)
    - Immediately when significant changes are detected
    """
    
    node_id: str
    gossip_client: Optional[GossipClient] = None
    
    # Broadcast interval
    interval_seconds: float = 30.0
    
    # Thresholds for "significant change" that triggers immediate broadcast
    battery_threshold: float = 10.0  # percent change
    cpu_threshold: float = 0.20  # normalized load change
    power_state_changed: bool = False  # plugged/unplugged triggers immediate
    
    # State tracking
    last_broadcast: Optional[NodeCostFactors] = None
    last_broadcast_time: float = 0.0
    
    def should_broadcast(self, current: NodeCostFactors) -> bool:
        """
        Check if we should broadcast an update.
        
        Args:
            current: Current cost factors
        
        Returns:
            True if an update should be broadcast
        """
        now = time.time()
        
        # Always broadcast on interval
        if now - self.last_broadcast_time > self.interval_seconds:
            return True
        
        # First broadcast
        if self.last_broadcast is None:
            return True
        
        last = self.last_broadcast
        
        # Power state change (plugged/unplugged)
        if current.on_battery != last.on_battery:
            return True
        
        # Significant battery change
        if abs(current.battery_percent - last.battery_percent) > self.battery_threshold:
            return True
        
        # Significant CPU load change
        if abs(current.cpu_load - last.cpu_load) > self.cpu_threshold:
            return True
        
        # Network metered state change
        if current.is_metered != last.is_metered:
            return True
        
        return False
    
    async def maybe_broadcast(self, current: NodeCostFactors) -> bool:
        """
        Broadcast if needed.
        
        Args:
            current: Current cost factors
        
        Returns:
            True if a broadcast was sent
        """
        if not self.should_broadcast(current):
            return False
        
        if self.gossip_client is None:
            # No gossip client configured, just track state
            self.last_broadcast = current
            self.last_broadcast_time = time.time()
            return False
        
        message = build_cost_message(current)
        await self.gossip_client.broadcast(message)
        
        self.last_broadcast = current
        self.last_broadcast_time = time.time()
        return True
    
    def force_broadcast_needed(self) -> None:
        """Mark that the next check should trigger a broadcast."""
        self.last_broadcast_time = 0.0
