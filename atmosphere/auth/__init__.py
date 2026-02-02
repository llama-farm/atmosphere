"""
Authentication and identity management for Atmosphere.

Provides:
- Node identity (Ed25519 keypairs)
- Mesh tokens (offline-verifiable membership)
- Federation (hierarchical mesh trust)
"""

from .identity import (
    KeyPair,
    NodeIdentity,
    generate_node_identity,
    load_node_identity,
    verify_signature,
)
from .tokens import (
    MeshToken,
    TokenIssuer,
    TokenVerifier,
)
from .federation import (
    FederationLink,
    FederatedMesh,
)

__all__ = [
    # Identity
    "KeyPair",
    "NodeIdentity",
    "generate_node_identity",
    "load_node_identity",
    "verify_signature",
    # Tokens
    "MeshToken",
    "TokenIssuer",
    "TokenVerifier",
    # Federation
    "FederationLink",
    "FederatedMesh",
]
