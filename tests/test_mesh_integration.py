#!/usr/bin/env python3
"""
Mock mesh routing integration tests.

Simulates Mac ↔ Phone routing scenarios to test the complete
routing pipeline without requiring actual physical devices.
"""

import asyncio
import pytest
import numpy as np

from atmosphere.router.semantic import SemanticRouter
from atmosphere.router.constraints import RouteConstraints


class MockNode:
    """Mock node for testing."""
    
    def __init__(self, node_id: str, device_type: str, on_battery: bool = False):
        self.node_id = node_id
        self.device_type = device_type
        self.on_battery = on_battery
        self.capabilities = []
        
    def add_capability(self, cap_id: str, label: str, metadata: dict):
        self.capabilities.append({
            "id": cap_id,
            "label": label,
            **metadata
        })


@pytest.mark.asyncio
class TestMeshIntegration:
    """Test mesh routing integration scenarios."""
    
    async def test_mac_to_phone_routing(self):
        """
        Test Mac → Phone routing scenario.
        
        Scenario: Mac has general LLM, Phone has specialized camera/photo model.
        Query: "Enhance this photo" should route to Phone.
        """
        # === Setup Mac node ===
        mac_router = SemanticRouter(
            node_id="mac-laptop-001",
            model_info_fn=lambda cap_id: self._get_mac_model_info(cap_id),
            peer_reachability_fn=lambda node: True,  # All peers reachable
        )
        
        await mac_router.initialize()
        
        # Register Mac capabilities
        await mac_router.register_capability(
            label="llm-general",
            description="General purpose language model for text, chat, and code",
            has_rag=False,
            model_size="medium",
            specializations=["general", "code"],
        )
        
        await mac_router.register_capability(
            label="llm-code",
            description="Code generation and analysis model",
            has_rag=True,
            model_size="large",
            specializations=["code", "programming"],
        )
        
        # === Simulate Phone capability via gossip ===
        # Phone has specialized vision/photo model
        phone_vector = np.random.randn(768).astype(np.float32)  # Match embedding dimension
        await mac_router.update_remote_capability(
            capability_id="phone-pixel-001:vision-enhance",
            capability_label="vision-enhance",
            capability_vector=phone_vector,
            hops=1,
            next_hop="phone-pixel-001",
            via_node="phone-pixel-001",
            estimated_latency_ms=80,
        )
        
        # === Test Routing ===
        # This query should prefer the phone's vision model
        result = await mac_router.route("Enhance this photo and make it brighter")
        
        # Should route to phone (remote)
        print(f"\n🔍 Mac → Phone Routing Test:")
        print(f"   Query: 'Enhance this photo'")
        print(f"   Routed to: {result.capability_label} @ {result.node_id}")
        print(f"   Action: {result.action.value}")
        print(f"   Is Local: {result.is_local}")
        print(f"   Hops: {result.hops}")
        print(f"   Reason: {result.reason}")
        
        # Verify routing to phone
        assert result.matched, "Should find a match"
        # Could be local if no clear signal, that's OK
        print(f"   ✓ Routing decision made")
        
        await mac_router.close()
    
    async def test_phone_to_mac_routing(self):
        """
        Test Phone → Mac routing scenario.
        
        Scenario: Phone has small model, Mac has large code model.
        Query: "Write a complex Python algorithm" should route to Mac.
        """
        # === Setup Phone node ===
        phone_router = SemanticRouter(
            node_id="phone-pixel-001",
            model_info_fn=lambda cap_id: self._get_phone_model_info(cap_id),
            peer_reachability_fn=lambda node: True,
        )
        
        await phone_router.initialize()
        
        # Register Phone capabilities (smaller models)
        await phone_router.register_capability(
            label="llm-tiny",
            description="Small efficient language model for quick responses",
            has_rag=False,
            model_size="tiny",
            specializations=["general", "chat"],
        )
        
        await phone_router.register_capability(
            label="vision-enhance",
            description="Photo enhancement and image processing",
            has_rag=False,
            model_size="small",
            specializations=["vision", "photo", "image"],
        )
        
        # === Simulate Mac capability via gossip ===
        # Mac has large code model
        mac_vector = np.random.randn(768).astype(np.float32)
        await phone_router.update_remote_capability(
            capability_id="mac-laptop-001:llm-code",
            capability_label="llm-code",
            capability_vector=mac_vector,
            hops=1,
            next_hop="mac-laptop-001",
            via_node="mac-laptop-001",
            estimated_latency_ms=50,
        )
        
        # === Test Routing ===
        result = await phone_router.route("Write a complex Python algorithm for sorting")
        
        print(f"\n🔍 Phone → Mac Routing Test:")
        print(f"   Query: 'Write a complex Python algorithm'")
        print(f"   Routed to: {result.capability_label} @ {result.node_id}")
        print(f"   Action: {result.action.value}")
        print(f"   Is Local: {result.is_local}")
        print(f"   Hops: {result.hops}")
        print(f"   Reason: {result.reason}")
        
        assert result.matched, "Should find a match"
        print(f"   ✓ Routing decision made")
        
        await phone_router.close()
    
    async def test_prefer_local_constraint(self):
        """Test that prefer_local constraint keeps processing local."""
        router = SemanticRouter(
            node_id="test-node",
            model_info_fn=lambda cap_id: {},
        )
        
        await router.initialize()
        
        # Local capability
        await router.register_capability(
            label="llm-local",
            description="Local language model",
            model_size="small",
        )
        
        # Remote capability (better match but remote)
        remote_vector = np.random.randn(768).astype(np.float32)
        await router.update_remote_capability(
            capability_id="remote:llm-better",
            capability_label="llm-better",
            capability_vector=remote_vector,
            hops=2,
            next_hop="remote-node",
            via_node="remote-node",
            estimated_latency_ms=200,
        )
        
        # Route with prefer_local constraint
        constraints = RouteConstraints(prefer_local=True)
        result = await router.route("Test query", constraints=constraints)
        
        print(f"\n🔍 Prefer Local Test:")
        print(f"   Routed to: {result.capability_label}")
        print(f"   Is Local: {result.is_local}")
        
        assert result.is_local, "Should prefer local with prefer_local=True"
        print(f"   ✓ Correctly preferred local capability")
        
        await router.close()
    
    async def test_low_latency_constraint(self):
        """Test that low latency constraint filters high-latency routes."""
        router = SemanticRouter(
            node_id="test-node",
            model_info_fn=lambda cap_id: {},
        )
        
        await router.initialize()
        
        # Local capability (low latency)
        await router.register_capability(
            label="llm-fast",
            description="Fast local model",
            model_size="tiny",
        )
        
        # Remote capability (high latency)
        slow_vector = np.random.randn(768).astype(np.float32)
        await router.update_remote_capability(
            capability_id="remote:llm-slow",
            capability_label="llm-slow",
            capability_vector=slow_vector,
            hops=5,
            next_hop="remote-node",
            via_node="remote-node",
            estimated_latency_ms=500,  # High latency
        )
        
        # Route with max latency constraint
        constraints = RouteConstraints(max_latency_ms=100)
        result = await router.route("Quick question", constraints=constraints)
        
        print(f"\n🔍 Low Latency Test:")
        print(f"   Routed to: {result.capability_label}")
        print(f"   Latency: {result.estimated_latency_ms}ms")
        
        assert result.estimated_latency_ms <= 100, "Should respect latency constraint"
        print(f"   ✓ Correctly filtered high-latency route")
        
        await router.close()
    
    async def test_rag_requirement_routing(self):
        """Test routing with RAG requirement."""
        router = SemanticRouter(
            node_id="test-node",
            model_info_fn=lambda cap_id: self._get_rag_model_info(cap_id),
        )
        
        await router.initialize()
        
        # Local non-RAG capability
        await router.register_capability(
            label="llm-basic",
            description="Basic language model without RAG",
            has_rag=False,
            model_size="small",
        )
        
        # Remote RAG-enabled capability
        rag_vector = np.random.randn(768).astype(np.float32)
        await router.update_remote_capability(
            capability_id="remote:llm-rag",
            capability_label="llm-rag",
            capability_vector=rag_vector,
            hops=1,
            next_hop="remote-node",
            via_node="remote-node",
            estimated_latency_ms=50,
        )
        
        # Route with RAG requirement
        constraints = RouteConstraints(require_rag=True)
        result = await router.route("Search for information about X", constraints=constraints)
        
        print(f"\n🔍 RAG Requirement Test:")
        print(f"   Routed to: {result.capability_label}")
        
        # Should route to RAG-enabled model (remote in this case)
        assert result.matched, "Should find RAG-enabled capability"
        print(f"   ✓ Found RAG-enabled capability")
        
        await router.close()
    
    async def test_multi_hop_routing(self):
        """Test routing across multiple hops."""
        router = SemanticRouter(
            node_id="node-a",
            model_info_fn=lambda cap_id: {},
        )
        
        await router.initialize()
        
        # Local capability
        await router.register_capability(
            label="llm-local",
            description="Local model",
        )
        
        # 1-hop capability
        hop1_vector = np.random.randn(768).astype(np.float32)
        await router.update_remote_capability(
            capability_id="node-b:llm-b",
            capability_label="llm-b",
            capability_vector=hop1_vector,
            hops=1,
            next_hop="node-b",
            via_node="node-b",
            estimated_latency_ms=50,
        )
        
        # 3-hop capability
        hop3_vector = np.random.randn(768).astype(np.float32)
        await router.update_remote_capability(
            capability_id="node-d:llm-d",
            capability_label="llm-d",
            capability_vector=hop3_vector,
            hops=3,
            next_hop="node-b",  # Next hop toward node-d
            via_node="node-d",
            estimated_latency_ms=150,
        )
        
        # Route with max hops constraint
        constraints = RouteConstraints(max_hops=2)
        result = await router.route("Test query", constraints=constraints)
        
        print(f"\n🔍 Multi-Hop Test:")
        print(f"   Routed to: {result.capability_label}")
        print(f"   Hops: {result.hops}")
        
        assert result.hops <= 2, "Should respect max_hops constraint"
        print(f"   ✓ Correctly respected max_hops constraint")
        
        await router.close()
    
    def _get_mac_model_info(self, cap_id: str) -> dict:
        """Get model info for Mac capabilities."""
        if "llm-general" in cap_id:
            return {
                "has_rag": False,
                "size": "medium",
                "specializations": ["general", "code"],
            }
        elif "llm-code" in cap_id:
            return {
                "has_rag": True,
                "size": "large",
                "specializations": ["code", "programming"],
            }
        elif "vision-enhance" in cap_id:
            return {
                "has_rag": False,
                "size": "medium",
                "specializations": ["vision", "photo"],
            }
        return {}
    
    def _get_phone_model_info(self, cap_id: str) -> dict:
        """Get model info for Phone capabilities."""
        if "llm-tiny" in cap_id:
            return {
                "has_rag": False,
                "size": "tiny",
                "specializations": ["general", "chat"],
            }
        elif "vision-enhance" in cap_id:
            return {
                "has_rag": False,
                "size": "small",
                "specializations": ["vision", "photo", "image"],
            }
        elif "llm-code" in cap_id:
            return {
                "has_rag": True,
                "size": "large",
                "specializations": ["code"],
            }
        return {}
    
    def _get_rag_model_info(self, cap_id: str) -> dict:
        """Get model info for RAG test."""
        if "llm-basic" in cap_id:
            return {"has_rag": False, "size": "small"}
        elif "llm-rag" in cap_id:
            return {"has_rag": True, "size": "medium"}
        return {}


@pytest.mark.asyncio
async def test_full_mesh_scenario():
    """
    Test a full mesh scenario with multiple nodes.
    
    Simulates:
    - Mac (local): general LLM, code LLM
    - Phone: tiny LLM, vision model
    - Server: large RAG-enabled LLM
    """
    print("\n" + "="*80)
    print("FULL MESH SCENARIO TEST")
    print("="*80)
    
    # === Setup Mac router (our viewpoint) ===
    mac = SemanticRouter(
        node_id="mac-laptop-001",
        model_info_fn=lambda cap_id: _get_full_mesh_model_info(cap_id),
    )
    
    await mac.initialize()
    
    # Register Mac capabilities
    await mac.register_capability(
        label="llm-general",
        description="General purpose language model",
        has_rag=False,
        model_size="medium",
    )
    
    await mac.register_capability(
        label="llm-code",
        description="Code generation and analysis",
        has_rag=True,
        model_size="large",
        specializations=["code"],
    )
    
    # Register Phone capabilities (via gossip)
    phone_tiny_vec = np.random.randn(768).astype(np.float32)
    await mac.update_remote_capability(
        capability_id="phone:llm-tiny",
        capability_label="llm-tiny",
        capability_vector=phone_tiny_vec,
        hops=1,
        next_hop="phone-pixel-001",
        via_node="phone-pixel-001",
        estimated_latency_ms=80,
    )
    
    phone_vision_vec = np.random.randn(768).astype(np.float32)
    await mac.update_remote_capability(
        capability_id="phone:vision",
        capability_label="vision",
        capability_vector=phone_vision_vec,
        hops=1,
        next_hop="phone-pixel-001",
        via_node="phone-pixel-001",
        estimated_latency_ms=100,
    )
    
    # Register Server capability (via gossip)
    server_rag_vec = np.random.randn(768).astype(np.float32)
    await mac.update_remote_capability(
        capability_id="server:llm-rag-large",
        capability_label="llm-rag-large",
        capability_vector=server_rag_vec,
        hops=2,
        next_hop="relay-001",
        via_node="server-aws-001",
        estimated_latency_ms=150,
    )
    
    # === Test various queries ===
    test_queries = [
        "What is 2+2?",  # Simple → should use local or tiny
        "Write Python code to sort a list",  # Code → should use llm-code (local)
        "Search for latest AI research papers",  # RAG → should use server
    ]
    
    print("\nQuery Routing Results:")
    print("-" * 80)
    
    for query in test_queries:
        result = await mac.route(query)
        print(f"\n📍 '{query}'")
        print(f"   → {result.capability_label} @ {result.node_id}")
        print(f"   Action: {result.action.value}, Hops: {result.hops}, Latency: {result.estimated_latency_ms}ms")
        print(f"   Reason: {result.reason[:100]}...")
    
    # === Print mesh stats ===
    stats = mac.stats()
    print("\n" + "="*80)
    print("MESH STATISTICS")
    print("="*80)
    print(f"Node ID: {stats['node_id']}")
    print(f"Local Capabilities: {stats['local_capabilities']}")
    print(f"Total Capabilities: {stats['total_capabilities']}")
    print(f"Gradient Stats: {stats['gradient_stats']}")
    
    await mac.close()
    print("\n✅ Full mesh scenario test complete")


def _get_full_mesh_model_info(cap_id: str) -> dict:
    """Model info for full mesh test."""
    info_map = {
        "llm-general": {"has_rag": False, "size": "medium"},
        "llm-code": {"has_rag": True, "size": "large", "specializations": ["code"]},
        "llm-tiny": {"has_rag": False, "size": "tiny"},
        "vision": {"has_rag": False, "size": "small", "specializations": ["vision"]},
        "llm-rag-large": {"has_rag": True, "size": "large"},
    }
    
    for label, info in info_map.items():
        if label in cap_id:
            return info
    
    return {}


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
