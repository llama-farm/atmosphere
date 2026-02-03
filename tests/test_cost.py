"""
Tests for the cost model module.
"""

import time
import pytest

from atmosphere.cost import (
    get_cost_collector,
    NodeCostFactors,
    WorkRequest,
    compute_node_cost,
    power_cost_multiplier,
    compute_load_multiplier,
    network_cost_multiplier,
    CostGossipState,
    CostBroadcaster,
    CostAwareRouter,
)
from atmosphere.cost.gossip import build_cost_message


class TestNodeCostFactors:
    """Tests for NodeCostFactors dataclass."""
    
    def test_default_values(self):
        """Test default values are sensible."""
        factors = NodeCostFactors(
            node_id="test-node",
            timestamp=time.time(),
        )
        assert factors.on_battery is False
        assert factors.battery_percent == 100.0
        assert factors.plugged_in is True
        assert factors.cpu_load == 0.0
        assert factors.gpu_load == 0.0
        assert factors.memory_percent == 0.0
    
    def test_to_dict_from_dict(self):
        """Test serialization round-trip."""
        original = NodeCostFactors(
            node_id="test-node",
            timestamp=123456.789,
            on_battery=True,
            battery_percent=75.5,
            cpu_load=0.5,
            gpu_load=30.0,
            gpu_estimated=True,
            memory_percent=65.0,
            is_metered=True,
        )
        
        d = original.to_dict()
        restored = NodeCostFactors.from_dict(d)
        
        assert restored.node_id == original.node_id
        assert restored.timestamp == original.timestamp
        assert restored.on_battery == original.on_battery
        assert restored.battery_percent == original.battery_percent
        assert restored.cpu_load == original.cpu_load
        assert restored.gpu_load == original.gpu_load
        assert restored.gpu_estimated == original.gpu_estimated
        assert restored.memory_percent == original.memory_percent
        assert restored.is_metered == original.is_metered


class TestPowerCostMultiplier:
    """Tests for power_cost_multiplier function."""
    
    def test_plugged_in(self):
        """Plugged in should have 1.0x multiplier."""
        assert power_cost_multiplier(on_battery=False) == 1.0
        assert power_cost_multiplier(on_battery=False, battery_percent=50) == 1.0
    
    def test_on_battery_high_charge(self):
        """On battery with high charge should be 2.0x."""
        assert power_cost_multiplier(on_battery=True, battery_percent=100) == 2.0
        assert power_cost_multiplier(on_battery=True, battery_percent=75) == 2.0
        assert power_cost_multiplier(on_battery=True, battery_percent=51) == 2.0
    
    def test_on_battery_medium_charge(self):
        """On battery with medium charge should be 3.0x."""
        assert power_cost_multiplier(on_battery=True, battery_percent=49) == 3.0
        assert power_cost_multiplier(on_battery=True, battery_percent=35) == 3.0
        assert power_cost_multiplier(on_battery=True, battery_percent=20) == 3.0
    
    def test_on_battery_low_charge(self):
        """On battery with low charge should be 5.0x."""
        assert power_cost_multiplier(on_battery=True, battery_percent=19) == 5.0
        assert power_cost_multiplier(on_battery=True, battery_percent=10) == 5.0
        assert power_cost_multiplier(on_battery=True, battery_percent=0) == 5.0


class TestComputeLoadMultiplier:
    """Tests for compute_load_multiplier function."""
    
    def test_idle_cpu(self):
        """Low CPU load should have 1.0x multiplier."""
        assert compute_load_multiplier(cpu_load=0.0) == 1.0
        assert compute_load_multiplier(cpu_load=0.24) == 1.0
    
    def test_light_cpu(self):
        """Light CPU load should have 1.3x multiplier."""
        assert compute_load_multiplier(cpu_load=0.26) == 1.3
        assert compute_load_multiplier(cpu_load=0.49) == 1.3
    
    def test_moderate_cpu(self):
        """Moderate CPU load should have 1.6x multiplier."""
        assert compute_load_multiplier(cpu_load=0.51) == 1.6
        assert compute_load_multiplier(cpu_load=0.74) == 1.6
    
    def test_heavy_cpu(self):
        """Heavy CPU load should have 2.0x multiplier."""
        assert compute_load_multiplier(cpu_load=0.76) == 2.0
        assert compute_load_multiplier(cpu_load=1.0) == 2.0
        assert compute_load_multiplier(cpu_load=1.5) == 2.0  # Overloaded
    
    def test_gpu_for_inference(self):
        """GPU load should affect inference work."""
        # Low GPU
        mult = compute_load_multiplier(cpu_load=0.0, gpu_load=20.0, work_type="inference")
        assert mult == 1.0
        
        # Medium GPU
        mult = compute_load_multiplier(cpu_load=0.0, gpu_load=40.0, work_type="inference")
        assert mult == 1.5
        
        # High GPU
        mult = compute_load_multiplier(cpu_load=0.0, gpu_load=75.0, work_type="inference")
        assert mult == 2.0
    
    def test_gpu_ignored_for_general(self):
        """GPU load should not affect general work."""
        mult = compute_load_multiplier(cpu_load=0.0, gpu_load=100.0, work_type="general")
        assert mult == 1.0
    
    def test_memory_pressure(self):
        """Memory pressure should increase cost."""
        assert compute_load_multiplier(cpu_load=0.0, memory_percent=79.0) == 1.0
        assert compute_load_multiplier(cpu_load=0.0, memory_percent=85.0) == 1.5
        assert compute_load_multiplier(cpu_load=0.0, memory_percent=95.0) == 2.5


class TestNetworkCostMultiplier:
    """Tests for network_cost_multiplier function."""
    
    def test_unmetered_fast(self):
        """Fast unmetered connection should have 1.0x multiplier."""
        assert network_cost_multiplier(bandwidth_mbps=500, is_metered=False) == 1.0
        assert network_cost_multiplier(bandwidth_mbps=100, is_metered=False) == 1.0
    
    def test_unmetered_moderate(self):
        """Moderate unmetered connection should have 1.2x multiplier."""
        assert network_cost_multiplier(bandwidth_mbps=50, is_metered=False) == 1.2
        assert network_cost_multiplier(bandwidth_mbps=10, is_metered=False) == 1.2
    
    def test_unmetered_slow(self):
        """Slow unmetered connection should have 2.0x multiplier."""
        assert network_cost_multiplier(bandwidth_mbps=5, is_metered=False) == 2.0
        assert network_cost_multiplier(bandwidth_mbps=1, is_metered=False) == 2.0
    
    def test_unmetered_very_slow(self):
        """Very slow connection should have 5.0x multiplier."""
        assert network_cost_multiplier(bandwidth_mbps=0.5, is_metered=False) == 5.0
    
    def test_metered(self):
        """Metered connection should have 3.0x multiplier."""
        assert network_cost_multiplier(bandwidth_mbps=100, is_metered=True) == 3.0
    
    def test_unknown_bandwidth(self):
        """Unknown bandwidth should assume okay."""
        assert network_cost_multiplier(bandwidth_mbps=None, is_metered=False) == 1.0


class TestComputeNodeCost:
    """Tests for compute_node_cost function."""
    
    def test_ideal_node(self):
        """Ideal node (plugged in, idle) should have low cost."""
        node = NodeCostFactors(
            node_id="ideal",
            timestamp=time.time(),
            on_battery=False,
            battery_percent=100,
            cpu_load=0.1,
            gpu_load=0.0,
            memory_percent=30.0,
            is_metered=False,
        )
        work = WorkRequest(work_type="general")
        cost = compute_node_cost(node, work)
        assert cost == 1.0
    
    def test_battery_node(self):
        """Node on battery should have higher cost."""
        node = NodeCostFactors(
            node_id="laptop",
            timestamp=time.time(),
            on_battery=True,
            battery_percent=75,
            cpu_load=0.1,
            gpu_load=0.0,
            memory_percent=30.0,
            is_metered=False,
        )
        work = WorkRequest(work_type="general")
        cost = compute_node_cost(node, work)
        assert cost == 2.0  # 2.0x for battery
    
    def test_busy_node(self):
        """Busy node should have higher cost."""
        node = NodeCostFactors(
            node_id="busy",
            timestamp=time.time(),
            on_battery=False,
            cpu_load=0.8,
            gpu_load=60.0,
            memory_percent=85.0,
            is_metered=False,
        )
        work = WorkRequest(work_type="inference")
        cost = compute_node_cost(node, work)
        # 2.0x CPU * 2.0x GPU * 1.5x memory = 6.0
        assert cost == 6.0
    
    def test_combined_factors(self):
        """Test combined factors multiply correctly."""
        node = NodeCostFactors(
            node_id="stressed",
            timestamp=time.time(),
            on_battery=True,
            battery_percent=30,  # 3.0x
            cpu_load=0.6,  # 1.6x
            gpu_load=40.0,  # 1.5x for inference
            memory_percent=50.0,  # 1.0x
            is_metered=True,  # 3.0x
        )
        work = WorkRequest(work_type="inference")
        cost = compute_node_cost(node, work)
        # 3.0 * 1.6 * 1.5 * 1.0 * 3.0 = 21.6
        assert cost == pytest.approx(21.6, rel=0.01)


class TestCostGossipState:
    """Tests for CostGossipState."""
    
    def test_handle_cost_update(self):
        """Test handling gossip updates."""
        state = CostGossipState()
        
        msg = {
            "type": "NODE_COST_UPDATE",
            "version": 1,
            "node_id": "remote-node",
            "timestamp": time.time(),
            "cost_factors": {
                "on_battery": True,
                "battery_percent": 60,
                "cpu_load": 0.5,
                "memory_percent": 70,
            }
        }
        
        factors = state.handle_cost_update(msg)
        
        assert factors is not None
        assert factors.node_id == "remote-node"
        assert factors.on_battery is True
        assert factors.battery_percent == 60
    
    def test_get_fresh_costs(self):
        """Test getting fresh cost data."""
        state = CostGossipState()
        state.default_stale_seconds = 60
        
        # Add fresh node
        msg = {
            "type": "NODE_COST_UPDATE",
            "version": 1,
            "node_id": "fresh-node",
            "timestamp": time.time(),
            "cost_factors": {}
        }
        state.handle_cost_update(msg)
        
        fresh = state.get_fresh_costs()
        assert len(fresh) == 1
        assert fresh[0].node_id == "fresh-node"
    
    def test_stale_data_excluded(self):
        """Test that stale data is excluded."""
        state = CostGossipState()
        state.default_stale_seconds = 0.1  # Very short for testing
        
        msg = {
            "type": "NODE_COST_UPDATE",
            "version": 1,
            "node_id": "stale-node",
            "timestamp": time.time(),
            "cost_factors": {}
        }
        state.handle_cost_update(msg)
        
        # Wait for staleness
        import time as t
        t.sleep(0.2)
        
        fresh = state.get_fresh_costs()
        assert len(fresh) == 0


class TestCostBroadcaster:
    """Tests for CostBroadcaster."""
    
    def test_should_broadcast_first_time(self):
        """First collection should trigger broadcast."""
        broadcaster = CostBroadcaster(node_id="test")
        factors = NodeCostFactors(node_id="test", timestamp=time.time())
        
        assert broadcaster.should_broadcast(factors) is True
    
    def test_should_not_broadcast_immediately(self):
        """Same factors shouldn't trigger immediate rebroadcast."""
        broadcaster = CostBroadcaster(node_id="test")
        factors = NodeCostFactors(node_id="test", timestamp=time.time())
        
        # Simulate first broadcast
        broadcaster.last_broadcast = factors
        broadcaster.last_broadcast_time = time.time()
        
        assert broadcaster.should_broadcast(factors) is False
    
    def test_should_broadcast_on_power_change(self):
        """Power state change should trigger broadcast."""
        broadcaster = CostBroadcaster(node_id="test")
        
        factors1 = NodeCostFactors(node_id="test", timestamp=time.time(), on_battery=False)
        broadcaster.last_broadcast = factors1
        broadcaster.last_broadcast_time = time.time()
        
        factors2 = NodeCostFactors(node_id="test", timestamp=time.time(), on_battery=True)
        
        assert broadcaster.should_broadcast(factors2) is True


class TestCostAwareRouter:
    """Tests for CostAwareRouter."""
    
    def test_selects_lowest_cost(self):
        """Router should select lowest cost node."""
        state = CostGossipState()
        
        # Add nodes with different costs
        for msg in [
            {"type": "NODE_COST_UPDATE", "node_id": "expensive",
             "timestamp": time.time(), "cost_factors": {"on_battery": True, "battery_percent": 20}},
            {"type": "NODE_COST_UPDATE", "node_id": "cheap",
             "timestamp": time.time(), "cost_factors": {"on_battery": False, "cpu_load": 0.1}},
            {"type": "NODE_COST_UPDATE", "node_id": "moderate",
             "timestamp": time.time(), "cost_factors": {"on_battery": False, "cpu_load": 0.6}},
        ]:
            state.handle_cost_update(msg)
        
        router = CostAwareRouter(
            cost_state=state,
            local_node_id="local",
        )
        
        result = router.route_to_node(
            candidate_nodes=["expensive", "cheap", "moderate"],
            work=WorkRequest(work_type="general"),
        )
        
        assert result.success is True
        assert result.selected_node == "cheap"


class TestCollector:
    """Tests for the cost collector."""
    
    def test_get_collector_returns_collector(self):
        """get_cost_collector should return a collector."""
        collector = get_cost_collector()
        assert collector is not None
    
    def test_collect_returns_factors(self):
        """collect() should return NodeCostFactors."""
        collector = get_cost_collector()
        factors = collector.collect()
        
        assert isinstance(factors, NodeCostFactors)
        assert factors.node_id is not None
        assert factors.timestamp > 0
        assert 0 <= factors.battery_percent <= 100
        assert 0 <= factors.cpu_load <= 2.0
        assert 0 <= factors.memory_percent <= 100


class TestBuildCostMessage:
    """Tests for build_cost_message function."""
    
    def test_message_structure(self):
        """Test message has required fields."""
        factors = NodeCostFactors(
            node_id="test-node",
            timestamp=time.time(),
            on_battery=True,
            battery_percent=50,
        )
        
        msg = build_cost_message(factors)
        
        assert msg["type"] == "NODE_COST_UPDATE"
        assert msg["version"] == 1
        assert msg["node_id"] == "test-node"
        assert "timestamp" in msg
        assert "ttl" in msg
        assert "cost_factors" in msg
        assert "overall_cost" in msg["cost_factors"]
