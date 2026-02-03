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
    get_hardware_fingerprint,
)
from .tokens import (
    MeshToken,
    MeshInvite,
    TokenStore,
)

# Federation is optional - may not exist yet
try:
    from .federation import (
        FederationLink,
        FederatedMesh,
    )
    _has_federation = True
except ImportError:
    FederationLink = None
    FederatedMesh = None
    _has_federation = False

__all__ = [
    # Identity
    "KeyPair",
    "NodeIdentity",
    "generate_node_identity",
    "load_node_identity",
    "verify_signature",
    "get_hardware_fingerprint",
    # Tokens
    "MeshToken",
    "MeshInvite",
    "TokenStore",
]

if _has_federation:
    __all__.extend(["FederationLink", "FederatedMesh"])
