"""
Tests for semantic routing.
"""

import pytest
import asyncio
import numpy as np

from atmosphere.router.gradient import GradientTable, GradientEntry
from atmosphere.router.semantic import SemanticRouter, RouteAction, Capability


class TestGradientTable:
    """Tests for gradient table."""
    
    def test_create(self):
        """Test table creation."""
        table = GradientTable(node_id="test-node")
        assert len(table) == 0
    
    def test_update(self):
        """Test adding entries."""
        table = GradientTable(node_id="test-node")
        
        vector = np.random.randn(768).astype(np.float32)
        vector = vector / np.linalg.norm(vector)
        
        updated = table.update(
            capability_id="cap-1",
            capability_label="llm",
            capability_vector=vector,
            hops=1,
            next_hop="peer-1",
            via_node="peer-1"
        )
        
        assert updated is True
        assert len(table) == 1
    
    def test_update_better_route(self):
        """Test that better routes replace worse ones."""
        table = GradientTable(node_id="test-node")
        
        vector = np.random.randn(768).astype(np.float32)
        
        # Add with 2 hops
        table.update(
            capability_id="cap-1",
            capability_label="llm",
            capability_vector=vector,
            hops=2,
            next_hop="peer-1",
            via_node="peer-2"
        )
        
        # Add with 1 hop (better)
        updated = table.update(
            capability_id="cap-1",
            capability_label="llm",
            capability_vector=vector,
            hops=1,
            next_hop="peer-3",
            via_node="peer-3"
        )
        
        assert updated is True
        entry = table.get("cap-1")
        assert entry.hops == 1
        assert entry.next_hop == "peer-3"
    
    def test_find_best_route(self):
        """Test finding best route by similarity."""
        table = GradientTable(node_id="test-node")
        
        # Add two capabilities
        vec1 = np.random.randn(768).astype(np.float32)
        vec1 = vec1 / np.linalg.norm(vec1)
        
        vec2 = np.random.randn(768).astype(np.float32)
        vec2 = vec2 / np.linalg.norm(vec2)
        
        table.update("cap-1", "llm", vec1, 1, "peer-1", "peer-1")
        table.update("cap-2", "vision", vec2, 1, "peer-2", "peer-2")
        
        # Query with vec1 should return cap-1
        entry = table.find_best_route(vec1, min_score=0.5)
        assert entry is not None
        assert entry.capability_id == "cap-1"
    
    def test_prune_expired(self):
        """Test pruning expired entries."""
        import time
        
        table = GradientTable(node_id="test-node", expire_sec=0.1)
        
        vector = np.random.randn(768).astype(np.float32)
        table.update("cap-1", "llm", vector, 1, "peer-1", "peer-1")
        
        assert len(table) == 1
        
        # Wait for expiration
        time.sleep(0.2)
        
        pruned = table.prune_expired()
        assert pruned == 1
        assert len(table) == 0


class TestCapability:
    """Tests for Capability class."""
    
    def test_create(self):
        """Test capability creation."""
        vector = np.random.randn(768).astype(np.float32)
        
        cap = Capability(
            id="node-1:llm",
            label="llm",
            description="Language model",
            vector=vector,
            handler="ollama",
            models=["llama3.2"]
        )
        
        assert cap.label == "llm"
        assert isinstance(cap.vector, np.ndarray)


@pytest.mark.asyncio
class TestSemanticRouter:
    """Tests for semantic router (requires Ollama)."""
    
    async def test_create(self):
        """Test router creation."""
        router = SemanticRouter(node_id="test-node")
        assert router.node_id == "test-node"
        assert len(router.local_capabilities) == 0
    
    # Note: Full router tests require Ollama for embeddings
    # These are integration tests that would run with a real backend


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
