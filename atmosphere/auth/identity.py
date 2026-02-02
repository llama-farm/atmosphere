"""
Node identity using Ed25519 cryptography.

Each node has a unique identity defined by its Ed25519 keypair.
The public key serves as the node ID.
"""

import base64
import hashlib
import json
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature


@dataclass
class KeyPair:
    """Ed25519 key pair for signing."""
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey
    
    @classmethod
    def generate(cls) -> "KeyPair":
        """Generate a new random key pair."""
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        return cls(private_key=private_key, public_key=public_key)
    
    @classmethod
    def from_private_bytes(cls, private_bytes: bytes) -> "KeyPair":
        """Load key pair from private key bytes."""
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        public_key = private_key.public_key()
        return cls(private_key=private_key, public_key=public_key)
    
    def private_bytes(self) -> bytes:
        """Export private key as raw bytes (32 bytes)."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
    
    def public_bytes(self) -> bytes:
        """Export public key as raw bytes (32 bytes)."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    
    def public_key_b64(self) -> str:
        """Export public key as base64 string."""
        return base64.b64encode(self.public_bytes()).decode('ascii')
    
    def key_id(self) -> str:
        """Get the key ID (hash of public key)."""
        return hashlib.sha256(self.public_bytes()).hexdigest()[:16]
    
    def sign(self, message: bytes) -> bytes:
        """Sign a message."""
        return self.private_key.sign(message)
    
    def sign_b64(self, message: bytes) -> str:
        """Sign a message and return base64 signature."""
        return base64.b64encode(self.sign(message)).decode('ascii')


def verify_signature(
    public_key_bytes: bytes,
    message: bytes,
    signature: bytes
) -> bool:
    """Verify an Ed25519 signature."""
    try:
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def verify_signature_b64(
    public_key_b64: str,
    message: bytes,
    signature_b64: str
) -> bool:
    """Verify a base64-encoded signature."""
    try:
        public_key_bytes = base64.b64decode(public_key_b64)
        signature = base64.b64decode(signature_b64)
        return verify_signature(public_key_bytes, message, signature)
    except Exception:
        return False


def get_hardware_fingerprint() -> str:
    """
    Get a hardware fingerprint for this device.
    
    Combines multiple system identifiers into a stable hash.
    """
    components = [
        platform.node(),
        platform.machine(),
        platform.processor(),
    ]
    
    # Try to get a more stable ID on macOS
    try:
        result = subprocess.run(
            ['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
            capture_output=True,
            text=True
        )
        if 'IOPlatformUUID' in result.stdout:
            for line in result.stdout.split('\n'):
                if 'IOPlatformUUID' in line:
                    uuid_str = line.split('"')[-2]
                    components.append(uuid_str)
                    break
    except Exception:
        pass
    
    combined = '|'.join(components)
    return hashlib.sha256(combined.encode()).hexdigest()


@dataclass
class NodeIdentity:
    """
    A node's identity in the Atmosphere mesh.
    
    Contains the keypair and metadata about this node.
    """
    keypair: KeyPair
    name: str
    hardware_hash: str
    created_at: int
    
    @property
    def node_id(self) -> str:
        """Get the node ID (short hash of public key)."""
        return self.keypair.key_id()
    
    @property
    def public_key(self) -> str:
        """Get the public key as base64."""
        return self.keypair.public_key_b64()
    
    def sign(self, message: bytes) -> str:
        """Sign a message and return base64 signature."""
        return self.keypair.sign_b64(message)
    
    def to_dict(self) -> dict:
        """Serialize identity (public parts only)."""
        return {
            "node_id": self.node_id,
            "public_key": self.public_key,
            "name": self.name,
            "hardware_hash": self.hardware_hash,
            "created_at": self.created_at
        }
    
    def save(self, path: Path) -> None:
        """Save identity to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "private_key": self.keypair.private_bytes().hex(),
            "name": self.name,
            "hardware_hash": self.hardware_hash,
            "created_at": self.created_at
        }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Set restrictive permissions
        path.chmod(0o600)
    
    @classmethod
    def load(cls, path: Path) -> "NodeIdentity":
        """Load identity from file."""
        with open(path, 'r') as f:
            data = json.load(f)
        
        keypair = KeyPair.from_private_bytes(bytes.fromhex(data["private_key"]))
        
        return cls(
            keypair=keypair,
            name=data["name"],
            hardware_hash=data["hardware_hash"],
            created_at=data["created_at"]
        )


def generate_node_identity(name: Optional[str] = None) -> NodeIdentity:
    """Generate a new node identity."""
    if name is None:
        name = platform.node() or "atmosphere-node"
    
    return NodeIdentity(
        keypair=KeyPair.generate(),
        name=name,
        hardware_hash=get_hardware_fingerprint(),
        created_at=int(time.time())
    )


def load_node_identity(path: Path) -> Optional[NodeIdentity]:
    """Load node identity from file, or return None if not found."""
    if not path.exists():
        return None
    return NodeIdentity.load(path)
