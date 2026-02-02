"""
Core tests for Atmosphere.
"""

import pytest
import asyncio
import tempfile
from pathlib import Path

from atmosphere.config import Config, get_config, reset_config
from atmosphere.auth.identity import KeyPair, NodeIdentity, generate_node_identity
from atmosphere.mesh.node import MeshIdentity, Node


class TestKeyPair:
    """Tests for Ed25519 keypair operations."""
    
    def test_generate(self):
        """Test keypair generation."""
        kp = KeyPair.generate()
        assert kp.private_key is not None
        assert kp.public_key is not None
    
    def test_key_id(self):
        """Test key ID generation."""
        kp = KeyPair.generate()
        key_id = kp.key_id()
        assert len(key_id) == 16  # SHA256 truncated to 16 chars
    
    def test_sign_verify(self):
        """Test signing and verification."""
        kp = KeyPair.generate()
        message = b"test message"
        
        signature = kp.sign(message)
        assert len(signature) == 64  # Ed25519 signature is 64 bytes
        
        # Verify with public key
        from atmosphere.auth.identity import verify_signature
        assert verify_signature(kp.public_bytes(), message, signature)
    
    def test_export_import(self):
        """Test key export and import."""
        kp1 = KeyPair.generate()
        private_bytes = kp1.private_bytes()
        
        kp2 = KeyPair.from_private_bytes(private_bytes)
        
        assert kp1.public_key_b64() == kp2.public_key_b64()
        assert kp1.key_id() == kp2.key_id()


class TestNodeIdentity:
    """Tests for node identity."""
    
    def test_generate(self):
        """Test identity generation."""
        identity = generate_node_identity("test-node")
        
        assert identity.name == "test-node"
        assert len(identity.node_id) == 16
        assert identity.hardware_hash is not None
    
    def test_save_load(self):
        """Test saving and loading identity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "identity.json"
            
            identity1 = generate_node_identity("test-node")
            identity1.save(path)
            
            identity2 = NodeIdentity.load(path)
            
            assert identity1.node_id == identity2.node_id
            assert identity1.name == identity2.name
            assert identity1.hardware_hash == identity2.hardware_hash


class TestMeshIdentity:
    """Tests for mesh identity."""
    
    def test_create(self):
        """Test mesh creation."""
        mesh = MeshIdentity.create(
            name="test-mesh",
            threshold=2,
            total_shares=3
        )
        
        assert mesh.name == "test-mesh"
        assert mesh.threshold == 2
        assert mesh.total_shares == 3
        assert len(mesh.mesh_id) == 16
        assert mesh.can_issue_certificates()
    
    def test_founding_members(self):
        """Test founding member creation."""
        mesh = MeshIdentity.create(
            name="test-mesh",
            threshold=2,
            total_shares=3,
            founding_capabilities=["mesh-admin", "llm"]
        )
        
        assert len(mesh.founding_members) == 1
        assert "mesh-admin" in mesh.founding_members[0].capabilities
    
    def test_pending_shares(self):
        """Test pending shares for distribution."""
        mesh = MeshIdentity.create(
            name="test-mesh",
            threshold=2,
            total_shares=3
        )
        
        pending = mesh.get_pending_shares()
        assert len(pending) == 2  # 3 total - 1 for creator
    
    def test_save_load(self):
        """Test saving and loading mesh."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mesh.json"
            
            mesh1 = MeshIdentity.create(name="test-mesh")
            mesh1.save(path)
            
            mesh2 = MeshIdentity.load(path)
            
            assert mesh1.mesh_id == mesh2.mesh_id
            assert mesh1.name == mesh2.name
            assert mesh2.can_issue_certificates()


class TestNode:
    """Tests for Node class."""
    
    def test_create(self):
        """Test standalone node creation."""
        node = Node.create("test-node")
        
        assert node.name == "test-node"
        assert not node.is_mesh_member
        assert not node.is_founder
    
    def test_create_with_mesh(self):
        """Test node creation with mesh."""
        node = Node.create_with_mesh(
            node_name="test-node",
            mesh_name="test-mesh"
        )
        
        assert node.is_mesh_member
        assert node.is_founder
        assert node.mesh.name == "test-mesh"


class TestConfig:
    """Tests for configuration."""
    
    def test_default_config(self):
        """Test default configuration."""
        reset_config()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(data_dir=Path(tmpdir))
            
            assert config.server.port == 11451  # Atmosphere API port
            assert config.mdns_enabled is True
    
    def test_save_load(self):
        """Test saving and loading config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            config1 = Config(
                data_dir=path,
                node_id="test-id",
                node_name="test-name"
            )
            config1.save()
            
            config2 = Config.load(path)
            
            assert config2.node_id == "test-id"
            assert config2.node_name == "test-name"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
