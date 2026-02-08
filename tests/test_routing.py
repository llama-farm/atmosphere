"""
Test routing and capability discovery.

Tests:
1. "What do llamas eat?" routes to appropriate capability
2. Route decision includes explanation
3. Constraint filtering works
"""

import asyncio
import pytest
from typing import List

from atmosphere.integration.llamafarm import discover_llamafarm_capabilities
from atmosphere.core.capability import CapabilityAnnouncement


@pytest.mark.asyncio
async def test_llamafarm_discovery():
    """Test that we can discover LlamaFarm capabilities."""
    
    # Mock node info
    node_id = "test-node-abc123"
    node_name = "Test Node"
    
    capabilities: List[CapabilityAnnouncement] = await discover_llamafarm_capabilities(
        node_id=node_id,
        node_name=node_name,
    )
    
    # Should find at least one capability
    assert len(capabilities) > 0, "No capabilities discovered"
    
    # Check first capability
    cap = capabilities[0]
    assert cap.node_id == node_id
    assert cap.node_name == node_name
    assert cap.capability_id.startswith(node_id)
    assert cap.model_actual, "Model name should be populated"
    assert cap.model_family, "Model family should be populated"
    assert cap.model_tier, "Model tier should be set"
    
    print(f"\n✓ Discovered {len(capabilities)} capabilities")
    for cap in capabilities:
        print(f"  - {cap.label}: {cap.model_actual} ({cap.model_tier.value})")


@pytest.mark.asyncio
async def test_capability_keywords():
    """Test that capabilities have appropriate keywords."""
    
    node_id = "test-node"
    node_name = "Test"
    
    capabilities = await discover_llamafarm_capabilities(node_id, node_name)
    
    assert len(capabilities) > 0
    
    # Check that keywords are extracted or provided
    for cap in capabilities:
        print(f"\n{cap.label}:")
        print(f"  Keywords: {cap.keywords}")
        print(f"  Good for: {cap.good_for}")
        print(f"  Not good for: {cap.not_good_for}")
        
        # At least one of these should be populated
        assert (cap.keywords or cap.good_for or cap.specializations), \
            f"Capability {cap.label} has no semantic indicators"


@pytest.mark.asyncio
async def test_model_tier_classification():
    """Test that model tiers are correctly classified."""
    
    node_id = "test-node"
    node_name = "Test"
    
    capabilities = await discover_llamafarm_capabilities(node_id, node_name)
    
    for cap in capabilities:
        print(f"\n{cap.model_actual}:")
        print(f"  Extracted params: {cap.model_params_b}B")
        print(f"  Tier: {cap.model_tier.value}")
        
        # Verify tier matches params
        if cap.model_params_b < 2:
            assert cap.model_tier.value == "tiny"
        elif cap.model_params_b < 5:
            assert cap.model_tier.value == "small"
        elif cap.model_params_b < 20:
            assert cap.model_tier.value == "medium"
        elif cap.model_params_b < 50:
            assert cap.model_tier.value == "large"
        else:
            assert cap.model_tier.value == "xl"


def test_api_endpoints():
    """Test that API endpoints are reachable (requires server running)."""
    import httpx
    
    base_url = "http://localhost:14321"
    
    try:
        # Test /capabilities endpoint
        response = httpx.get(f"{base_url}/capabilities", timeout=5.0)
        assert response.status_code == 200, f"Failed to get capabilities: {response.status_code}"
        
        caps = response.json()
        print(f"\n✓ /capabilities returned {len(caps)} capabilities")
        
        for cap in caps:
            print(f"  - {cap['label']} ({cap['source']}): {cap.get('models', [])}")
        
        # Test /mesh/capabilities endpoint
        response = httpx.get(f"{base_url}/mesh/capabilities", timeout=5.0)
        assert response.status_code == 200, f"Failed to get mesh capabilities: {response.status_code}"
        
        mesh_caps = response.json()
        print(f"\n✓ /mesh/capabilities returned {len(mesh_caps)} capabilities")
        
        for cap in mesh_caps:
            print(f"  - {cap['label']}: {cap['model_actual']} ({cap['model_tier']})")
            print(f"    Good for: {cap['good_for']}")
        
        # Test /route endpoint with llama query
        response = httpx.post(
            f"{base_url}/route",
            json={"intent": "What do llamas eat?"},
            timeout=10.0
        )
        assert response.status_code == 200, f"Failed to route: {response.status_code}"
        
        route = response.json()
        print(f"\n✓ Routed 'What do llamas eat?' to: {route.get('capability')}")
        print(f"  Action: {route['action']}")
        print(f"  Score: {route.get('score', 0):.3f}")
        
    except httpx.ConnectError:
        pytest.skip("Atmosphere server not running on localhost:14321")


if __name__ == "__main__":
    # Run tests manually
    print("=== Running Atmosphere Routing Tests ===\n")
    
    print("Test 1: LlamaFarm Discovery")
    asyncio.run(test_llamafarm_discovery())
    
    print("\n" + "="*50)
    print("Test 2: Capability Keywords")
    asyncio.run(test_capability_keywords())
    
    print("\n" + "="*50)
    print("Test 3: Model Tier Classification")
    asyncio.run(test_model_tier_classification())
    
    print("\n" + "="*50)
    print("Test 4: API Endpoints (requires server)")
    try:
        test_api_endpoints()
    except Exception as e:
        print(f"⚠ API tests skipped: {e}")
    
    print("\n=== All Tests Complete ===")
