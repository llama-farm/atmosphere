"""
Federation: Hierarchical mesh trust for multi-organization deployments.

Supports disconnected operation - child meshes can operate independently
when the parent is unreachable.
"""

import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from .identity import verify_signature_b64


@dataclass
class FederationLink:
    """A cryptographic link between a child mesh and its parent."""
    child_mesh_id: str
    child_mesh_name: str
    child_public_key: str
    
    parent_mesh_id: str
    parent_mesh_name: str
    parent_public_key: str
    
    # Permissions
    allowed_capabilities: List[str]
    max_tier: str
    can_create_children: bool
    
    # Validity
    created_at: int
    expires_at: int  # 0 = never expires
    
    # Parent's signature
    parent_signature: str
    
    def to_dict(self) -> dict:
        return {
            "child": {
                "mesh_id": self.child_mesh_id,
                "mesh_name": self.child_mesh_name,
                "public_key": self.child_public_key
            },
            "parent": {
                "mesh_id": self.parent_mesh_id,
                "mesh_name": self.parent_mesh_name,
                "public_key": self.parent_public_key
            },
            "permissions": {
                "allowed_capabilities": self.allowed_capabilities,
                "max_tier": self.max_tier,
                "can_create_children": self.can_create_children
            },
            "validity": {
                "created_at": self.created_at,
                "expires_at": self.expires_at
            },
            "parent_signature": self.parent_signature
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "FederationLink":
        return cls(
            child_mesh_id=data["child"]["mesh_id"],
            child_mesh_name=data["child"]["mesh_name"],
            child_public_key=data["child"]["public_key"],
            parent_mesh_id=data["parent"]["mesh_id"],
            parent_mesh_name=data["parent"]["mesh_name"],
            parent_public_key=data["parent"]["public_key"],
            allowed_capabilities=data["permissions"]["allowed_capabilities"],
            max_tier=data["permissions"]["max_tier"],
            can_create_children=data["permissions"]["can_create_children"],
            created_at=data["validity"]["created_at"],
            expires_at=data["validity"]["expires_at"],
            parent_signature=data["parent_signature"]
        )
    
    @property
    def is_expired(self) -> bool:
        if self.expires_at == 0:
            return False
        return time.time() > self.expires_at
    
    def verify(self) -> bool:
        """Verify the parent's signature on this link."""
        link_data = {
            "child": {
                "mesh_id": self.child_mesh_id,
                "mesh_name": self.child_mesh_name,
                "public_key": self.child_public_key
            },
            "parent": {
                "mesh_id": self.parent_mesh_id,
                "mesh_name": self.parent_mesh_name,
                "public_key": self.parent_public_key
            },
            "permissions": {
                "allowed_capabilities": self.allowed_capabilities,
                "max_tier": self.max_tier,
                "can_create_children": self.can_create_children
            },
            "validity": {
                "created_at": self.created_at,
                "expires_at": self.expires_at
            }
        }
        
        message = json.dumps(link_data, sort_keys=True).encode()
        return verify_signature_b64(
            self.parent_public_key,
            message,
            self.parent_signature
        )


class FederatedMesh:
    """
    A mesh that participates in a federation hierarchy.
    
    Supports:
    - Root mesh (no parent)
    - Child mesh (has parent, may have children)
    - Leaf mesh (has parent, no children)
    """
    
    def __init__(self, mesh_identity):
        self.mesh = mesh_identity
        self.parent_link: Optional[FederationLink] = None
        self.child_links: Dict[str, FederationLink] = {}
        self._known_meshes: Dict[str, dict] = {}
    
    @property
    def is_root(self) -> bool:
        """Is this the root of the federation tree?"""
        return self.parent_link is None
    
    @property
    def federation_path(self) -> List[str]:
        """Path from root to this mesh."""
        if self.parent_link is None:
            return [self.mesh.mesh_id]
        return [self.parent_link.parent_mesh_id, self.mesh.mesh_id]
    
    def create_child_mesh(
        self,
        child_mesh,
        allowed_capabilities: Optional[List[str]] = None,
        max_tier: str = "compute",
        can_create_children: bool = True,
        expires_in_days: int = 0
    ) -> FederationLink:
        """Create a federation link to a child mesh."""
        if not hasattr(self.mesh, '_local_key_pair') or self.mesh._local_key_pair is None:
            raise RuntimeError("Cannot create children without local keypair")
        
        created_at = int(time.time())
        expires_at = 0 if expires_in_days == 0 else created_at + (expires_in_days * 86400)
        caps = allowed_capabilities or []
        
        signer_public_key = self.mesh._local_key_pair.public_key_b64()
        
        link_data = {
            "child": {
                "mesh_id": child_mesh.mesh_id,
                "mesh_name": child_mesh.name,
                "public_key": child_mesh.master_public_key
            },
            "parent": {
                "mesh_id": self.mesh.mesh_id,
                "mesh_name": self.mesh.name,
                "public_key": signer_public_key
            },
            "permissions": {
                "allowed_capabilities": caps,
                "max_tier": max_tier,
                "can_create_children": can_create_children
            },
            "validity": {
                "created_at": created_at,
                "expires_at": expires_at
            }
        }
        
        message = json.dumps(link_data, sort_keys=True).encode()
        signature = self.mesh._local_key_pair.sign_b64(message)
        
        link = FederationLink(
            child_mesh_id=child_mesh.mesh_id,
            child_mesh_name=child_mesh.name,
            child_public_key=child_mesh.master_public_key,
            parent_mesh_id=self.mesh.mesh_id,
            parent_mesh_name=self.mesh.name,
            parent_public_key=signer_public_key,
            allowed_capabilities=caps,
            max_tier=max_tier,
            can_create_children=can_create_children,
            created_at=created_at,
            expires_at=expires_at,
            parent_signature=signature
        )
        
        self.child_links[child_mesh.mesh_id] = link
        return link
    
    def accept_parent_link(self, link: FederationLink) -> bool:
        """Accept a federation link from a parent mesh."""
        if link.child_mesh_id != self.mesh.mesh_id:
            return False
        
        if not link.verify():
            return False
        
        self.parent_link = link
        return True
    
    def can_operate_disconnected(self) -> bool:
        """Can this mesh operate without connection to parent?"""
        return True  # Always yes - that's the design!
    
    def get_disconnected_capabilities(self) -> dict:
        """What can we do while disconnected from parent?"""
        return {
            "issue_local_tokens": True,
            "verify_local_tokens": True,
            "verify_parent_tokens": True,
            "issue_cross_mesh_tokens": False,
            "create_child_mesh": self.parent_link.can_create_children if self.parent_link else True,
            "revoke_local_devices": True,
            "propagate_revocations": False
        }
