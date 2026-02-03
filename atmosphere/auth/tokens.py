"""
Mesh authentication tokens.

Tokens provide cryptographically signed authorization to join a mesh.
Only mesh founders can issue valid tokens.
"""

import base64
import hashlib
import json
import secrets
import struct
import time
from dataclasses import dataclass
from typing import Optional, List

from .identity import KeyPair


@dataclass
class MeshToken:
    """
    A signed token authorizing a node to join a mesh.
    
    Tokens are:
    - Issued by mesh founders (who hold signing keys)
    - Time-limited (default 24h, max 7 days)
    - Bound to a specific node_id (optional, for invites)
    - Scoped to capabilities (what the node can do)
    """
    mesh_id: str
    node_id: Optional[str]  # None = open invite (any node)
    issued_at: int
    expires_at: int
    capabilities: List[str]
    issuer_id: str  # Node ID of the founder who issued
    nonce: str  # Random to prevent replay
    signature: str  # Ed25519 signature (base64)
    
    @classmethod
    def create(
        cls,
        mesh_id: str,
        issuer_keypair: KeyPair,
        issuer_id: str,
        node_id: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        ttl_seconds: int = 86400,  # 24 hours
    ) -> "MeshToken":
        """
        Create a new signed mesh token.
        
        Args:
            mesh_id: The mesh this token grants access to
            issuer_keypair: The founder's keypair for signing
            issuer_id: The founder's node ID
            node_id: Specific node this token is for (None = any)
            capabilities: What the node can do (default: ["participant"])
            ttl_seconds: How long until expiration (max 7 days)
        """
        now = int(time.time())
        ttl_seconds = min(ttl_seconds, 7 * 86400)  # Max 7 days
        
        token = cls(
            mesh_id=mesh_id,
            node_id=node_id,
            issued_at=now,
            expires_at=now + ttl_seconds,
            capabilities=capabilities or ["participant"],
            issuer_id=issuer_id,
            nonce=secrets.token_hex(16),
            signature="",
        )
        
        # Sign the token
        token.signature = token._sign(issuer_keypair)
        return token
    
    def _canonical_bytes(self) -> bytes:
        """Get canonical bytes for signing/verification."""
        # Deterministic JSON encoding
        data = {
            "mesh_id": self.mesh_id,
            "node_id": self.node_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "capabilities": sorted(self.capabilities),
            "issuer_id": self.issuer_id,
            "nonce": self.nonce,
        }
        return json.dumps(data, sort_keys=True, separators=(',', ':')).encode()
    
    def _sign(self, keypair: KeyPair) -> str:
        """Sign with the issuer's keypair."""
        return keypair.sign_b64(self._canonical_bytes())
    
    def verify(self, issuer_public_key: bytes) -> bool:
        """
        Verify the token signature.
        
        Args:
            issuer_public_key: The public key of the issuer
        
        Returns:
            True if signature is valid
        """
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            
            pubkey = Ed25519PublicKey.from_public_bytes(issuer_public_key)
            sig_bytes = base64.b64decode(self.signature)
            pubkey.verify(sig_bytes, self._canonical_bytes())
            return True
        except Exception:
            return False
    
    def is_expired(self) -> bool:
        """Check if token has expired."""
        return time.time() > self.expires_at
    
    def is_valid_for_node(self, node_id: str) -> bool:
        """Check if this token is valid for a specific node."""
        if self.is_expired():
            return False
        if self.node_id is not None and self.node_id != node_id:
            return False
        return True
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "mesh_id": self.mesh_id,
            "node_id": self.node_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "capabilities": self.capabilities,
            "issuer_id": self.issuer_id,
            "nonce": self.nonce,
            "signature": self.signature,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MeshToken":
        """Create from dictionary."""
        return cls(
            mesh_id=data["mesh_id"],
            node_id=data.get("node_id"),
            issued_at=data["issued_at"],
            expires_at=data["expires_at"],
            capabilities=data.get("capabilities", ["participant"]),
            issuer_id=data["issuer_id"],
            nonce=data["nonce"],
            signature=data["signature"],
        )
    
    def encode(self) -> str:
        """Encode token to compact string for QR codes."""
        # Use base64url for URL-safe encoding
        json_bytes = json.dumps(self.to_dict(), separators=(',', ':')).encode()
        return base64.urlsafe_b64encode(json_bytes).decode().rstrip('=')
    
    @classmethod
    def decode(cls, encoded: str) -> "MeshToken":
        """Decode token from compact string."""
        # Add padding if needed
        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += '=' * padding
        
        json_bytes = base64.urlsafe_b64decode(encoded)
        data = json.loads(json_bytes)
        return cls.from_dict(data)


@dataclass
class MeshInvite:
    """
    A shareable invite containing connection info + token.
    
    Used for QR codes and deep links.
    """
    token: MeshToken
    mesh_name: str
    endpoints: List[str]  # ["local:192.168.1.100:11450", "relay:wss://..."]
    mesh_public_key: str  # For verification
    
    def to_dict(self) -> dict:
        return {
            "token": self.token.to_dict(),
            "mesh_name": self.mesh_name,
            "endpoints": self.endpoints,
            "mesh_public_key": self.mesh_public_key,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MeshInvite":
        return cls(
            token=MeshToken.from_dict(data["token"]),
            mesh_name=data["mesh_name"],
            endpoints=data.get("endpoints", []),
            mesh_public_key=data["mesh_public_key"],
        )
    
    def encode(self) -> str:
        """Encode for QR code / deep link."""
        json_bytes = json.dumps(self.to_dict(), separators=(',', ':')).encode()
        return base64.urlsafe_b64encode(json_bytes).decode().rstrip('=')
    
    @classmethod
    def decode(cls, encoded: str) -> "MeshInvite":
        """Decode from QR code / deep link."""
        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += '=' * padding
        
        json_bytes = base64.urlsafe_b64decode(encoded)
        data = json.loads(json_bytes)
        return cls.from_dict(data)
    
    def to_deep_link(self) -> str:
        """Generate atmosphere:// deep link."""
        return f"atmosphere://join?invite={self.encode()}"
    
    @classmethod
    def from_deep_link(cls, url: str) -> "MeshInvite":
        """Parse atmosphere:// deep link."""
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        invite_str = params.get("invite", [""])[0]
        return cls.decode(invite_str)


class TokenStore:
    """
    Stores issued and received tokens.
    
    Used by relay server to cache mesh public keys.
    """
    
    def __init__(self):
        self._mesh_keys: dict[str, bytes] = {}  # mesh_id -> public key
        self._used_nonces: set[str] = set()  # Prevent replay
        self._nonce_expiry: dict[str, int] = {}  # nonce -> expires_at
    
    def register_mesh(self, mesh_id: str, public_key: bytes, founder_proof: str) -> bool:
        """
        Register a mesh's public key.
        
        Only the first founder to connect can register.
        """
        if mesh_id in self._mesh_keys:
            return False  # Already registered
        
        # Verify founder proof (signature of mesh_id by the mesh key)
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            
            pubkey = Ed25519PublicKey.from_public_bytes(public_key)
            sig_bytes = base64.b64decode(founder_proof)
            pubkey.verify(sig_bytes, mesh_id.encode())
            
            self._mesh_keys[mesh_id] = public_key
            return True
        except Exception:
            return False
    
    def get_mesh_key(self, mesh_id: str) -> Optional[bytes]:
        """Get the public key for a mesh."""
        return self._mesh_keys.get(mesh_id)
    
    def verify_token(self, token: MeshToken, node_id: str) -> tuple[bool, str]:
        """
        Verify a token for joining a mesh.
        
        Returns:
            (success, error_message)
        """
        # Check expiration
        if token.is_expired():
            return False, "Token expired"
        
        # Check node binding
        if token.node_id and token.node_id != node_id:
            return False, "Token bound to different node"
        
        # Check replay (nonce already used)
        if token.nonce in self._used_nonces:
            return False, "Token already used (replay)"
        
        # Get mesh public key
        mesh_key = self.get_mesh_key(token.mesh_id)
        if not mesh_key:
            return False, "Mesh not registered"
        
        # Verify signature
        if not token.verify(mesh_key):
            return False, "Invalid signature"
        
        # Mark nonce as used
        self._used_nonces.add(token.nonce)
        self._nonce_expiry[token.nonce] = token.expires_at
        
        return True, ""
    
    def cleanup_expired_nonces(self):
        """Remove expired nonces to prevent memory growth."""
        now = time.time()
        expired = [
            nonce for nonce, exp in self._nonce_expiry.items()
            if exp < now
        ]
        for nonce in expired:
            self._used_nonces.discard(nonce)
            del self._nonce_expiry[nonce]
