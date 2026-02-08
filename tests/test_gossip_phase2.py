"""
Test Phase 2: Gossip Protocol Implementation

Verifies that capability announcements and gossip messages work correctly.
"""

import pytest
import asyncio
from atmosphere.core.capability import CapabilityAnnouncement, ModelTier, CapabilityType
from atmosphere.core.gossip import GossipManager, GossipMessage, GOSSIP_MSG_ANNOUNCE
from atmosphere.router.gradient import GradientTable
import json


def test_capability_announcement_creation():
    """Test creating a capability announcement."""
    cap = CapabilityAnnouncement(
        node_id="test-node-123",
        node_name="Test Node",
        capability_id="test-node-123:llamafarm/test:default",
        project_path="llamafarm/test/llama-expert",
        model_alias="default",
        model_actual="unsloth/Qwen3-1.7B-GGUF:Q4_K_M",
        model_family="qwen3",
        model_params_b=1.7,
        model_quantization="Q4_K_M",
        model_tier=ModelTier.TINY,
        capability_type=CapabilityType.LLM_CHAT,
        label="Test Llama Expert",
        description="Expert on llamas and alpacas",
        keywords=["llama", "alpaca", "camelid"],
        embedding=[0.1] * 384,  # Simple test embedding
    )
    
    assert cap.node_id == "test-node-123"
    assert cap.capability_id == "test-node-123:llamafarm/test:default"
    assert cap.model_tier == ModelTier.TINY
    assert len(cap.keywords) == 3
    assert cap.embedding_hash != 0  # Should be computed
    print(f"✓ Embedding hash computed: {cap.embedding_hash}")


def test_embedding_hash_computation():
    """Test 32-bit SHA256 hash computation."""
    embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
    
    cap1 = CapabilityAnnouncement(
        node_id="node1",
        node_name="Node 1",
        capability_id="cap1",
        project_path="test",
        model_alias="default",
        model_actual="test-model",
        model_family="test",
        model_params_b=1.0,
        model_quantization="Q4",
        model_tier=ModelTier.TINY,
        capability_type=CapabilityType.LLM_CHAT,
        embedding=embedding,
    )
    
    cap2 = CapabilityAnnouncement(
        node_id="node2",
        node_name="Node 2",
        capability_id="cap2",
        project_path="test",
        model_alias="default",
        model_actual="test-model",
        model_family="test",
        model_params_b=1.0,
        model_quantization="Q4",
        model_tier=ModelTier.TINY,
        capability_type=CapabilityType.LLM_CHAT,
        embedding=embedding,
    )
    
    # Same embedding should produce same hash
    assert cap1.embedding_hash == cap2.embedding_hash
    print(f"✓ Same embedding → same hash: {cap1.embedding_hash}")
    
    # Different embedding should produce different hash (probably)
    cap3 = CapabilityAnnouncement(
        node_id="node3",
        node_name="Node 3",
        capability_id="cap3",
        project_path="test",
        model_alias="default",
        model_actual="test-model",
        model_family="test",
        model_params_b=1.0,
        model_quantization="Q4",
        model_tier=ModelTier.TINY,
        capability_type=CapabilityType.LLM_CHAT,
        embedding=[0.9, 0.8, 0.7, 0.6, 0.5],
    )
    
    assert cap1.embedding_hash != cap3.embedding_hash
    print(f"✓ Different embedding → different hash: {cap3.embedding_hash}")


def test_capability_serialization():
    """Test capability to_dict/from_dict."""
    cap = CapabilityAnnouncement(
        node_id="test-node",
        node_name="Test",
        capability_id="test:cap",
        project_path="test/project",
        model_alias="default",
        model_actual="test-model",
        model_family="test",
        model_params_b=1.0,
        model_quantization="Q4",
        model_tier=ModelTier.TINY,
        capability_type=CapabilityType.LLM_CHAT,
        label="Test Capability",
        embedding=[0.1, 0.2, 0.3],
        keywords=["test", "capability"],
    )
    
    # Serialize
    cap_dict = cap.to_dict()
    assert isinstance(cap_dict, dict)
    assert cap_dict["node_id"] == "test-node"
    assert cap_dict["embedding_hash"] != 0
    print(f"✓ Serialized to dict: {len(cap_dict)} fields")
    
    # Deserialize
    cap2 = CapabilityAnnouncement.from_dict(cap_dict)
    assert cap2.node_id == cap.node_id
    assert cap2.capability_id == cap.capability_id
    assert cap2.embedding_hash == cap.embedding_hash
    print("✓ Deserialized from dict successfully")


def test_gossip_message_creation():
    """Test creating gossip messages."""
    cap = CapabilityAnnouncement(
        node_id="node-a",
        node_name="Node A",
        capability_id="node-a:test:default",
        project_path="test",
        model_alias="default",
        model_actual="test-model",
        model_family="test",
        model_params_b=1.0,
        model_quantization="Q4",
        model_tier=ModelTier.TINY,
        capability_type=CapabilityType.LLM_CHAT,
    )
    
    msg = GossipMessage(
        type=GOSSIP_MSG_ANNOUNCE,
        node_id="node-a",
        timestamp=1234567890.0,
        capabilities=[cap.to_dict()],
        ttl=10,
    )
    
    assert msg.type == GOSSIP_MSG_ANNOUNCE
    assert msg.node_id == "node-a"
    assert len(msg.capabilities) == 1
    print("✓ Gossip message created")
    
    # Serialize to JSON
    json_str = msg.to_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["type"] == GOSSIP_MSG_ANNOUNCE
    print(f"✓ Gossip message serialized to JSON ({len(json_str)} bytes)")
    
    # Deserialize
    msg2 = GossipMessage.from_json(json_str)
    assert msg2.type == msg.type
    assert msg2.node_id == msg.node_id
    assert len(msg2.capabilities) == len(msg.capabilities)
    print("✓ Gossip message deserialized from JSON")


@pytest.mark.asyncio
async def test_gossip_manager_basic():
    """Test basic gossip manager functionality."""
    gradient_table = GradientTable(node_id="test-node")
    
    # Track sent messages
    sent_messages = []
    
    async def mock_send_to_relay(msg: dict):
        sent_messages.append(msg)
    
    gossip = GossipManager(
        node_id="test-node",
        gradient_table=gradient_table,
        send_to_relay=mock_send_to_relay,
        gossip_interval=1.0,  # Short interval for testing
    )
    
    # Add local capability
    cap = CapabilityAnnouncement(
        node_id="test-node",
        node_name="Test Node",
        capability_id="test-node:test:default",
        project_path="test",
        model_alias="default",
        model_actual="test-model",
        model_family="test",
        model_params_b=1.0,
        model_quantization="Q4",
        model_tier=ModelTier.TINY,
        capability_type=CapabilityType.LLM_CHAT,
        embedding=[0.1] * 384,
    )
    
    gossip.add_local_capability(cap)
    
    # Check local capabilities
    local_caps = gossip.get_local_capabilities()
    assert len(local_caps) == 1
    assert local_caps[0].capability_id == cap.capability_id
    print("✓ Local capability added")
    
    # Check gradient table
    entry = gradient_table.get(cap.capability_id)
    assert entry is not None
    assert entry.hops == 0
    print("✓ Local capability added to gradient table (hops=0)")
    
    # Broadcast capabilities
    await gossip.broadcast_capabilities()
    assert len(sent_messages) == 1
    assert sent_messages[0]["type"] == "mesh.broadcast"
    print("✓ Capabilities broadcasted to relay")
    
    # Check all capabilities
    all_caps = gossip.get_all_capabilities()
    assert len(all_caps) == 1
    print("✓ All capabilities retrieved")


@pytest.mark.asyncio
async def test_gossip_announcement_handling():
    """Test receiving and processing announcements."""
    gradient_table = GradientTable(node_id="node-a")
    gossip = GossipManager(
        node_id="node-a",
        gradient_table=gradient_table,
    )
    
    # Create announcement from node-b
    cap_b = CapabilityAnnouncement(
        node_id="node-b",
        node_name="Node B",
        capability_id="node-b:test:default",
        project_path="test",
        model_alias="default",
        model_actual="test-model",
        model_family="test",
        model_params_b=1.0,
        model_quantization="Q4",
        model_tier=ModelTier.TINY,
        capability_type=CapabilityType.LLM_CHAT,
        embedding=[0.5] * 384,
        hops=0,  # Direct from node-b
    )
    
    announcement = {
        "type": GOSSIP_MSG_ANNOUNCE,
        "node_id": "node-b",
        "timestamp": 1234567890.0,
        "capabilities": [cap_b.to_dict()],
        "ttl": 10,
    }
    
    # Handle announcement
    await gossip.handle_announcement("node-b", announcement)
    
    # Check remote capabilities
    all_caps = gossip.get_all_capabilities()
    assert len(all_caps) == 1
    remote_cap = all_caps[0]
    assert remote_cap.node_id == "node-b"
    assert remote_cap.hops == 1  # Incremented from 0
    assert remote_cap.via_node == "node-b"
    print("✓ Remote announcement processed (hops incremented)")
    
    # Check gradient table
    entry = gradient_table.get(remote_cap.capability_id)
    assert entry is not None
    assert entry.hops == 1
    assert entry.next_hop == "node-b"
    print("✓ Gradient table updated from announcement")
    
    # Get stats
    stats = gossip.stats()
    assert stats["local_capabilities"] == 0
    assert stats["remote_nodes"] == 1
    assert stats["total_capabilities"] == 1
    print(f"✓ Stats: {stats}")


if __name__ == "__main__":
    print("=== Phase 2 Gossip Protocol Tests ===\n")
    
    print("1. Testing capability announcement creation...")
    test_capability_announcement_creation()
    print()
    
    print("2. Testing embedding hash computation...")
    test_embedding_hash_computation()
    print()
    
    print("3. Testing capability serialization...")
    test_capability_serialization()
    print()
    
    print("4. Testing gossip message creation...")
    test_gossip_message_creation()
    print()
    
    print("5. Testing gossip manager basic functionality...")
    asyncio.run(test_gossip_manager_basic())
    print()
    
    print("6. Testing gossip announcement handling...")
    asyncio.run(test_gossip_announcement_handling())
    print()
    
    print("=== All Phase 2 Tests Passed! ✅ ===")
