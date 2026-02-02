"""
Model Deployment System for Atmosphere Mesh.

Enables automatic distribution of trained ML models across mesh nodes.
Supports push, pull, gossip, and organic deployment strategies.

Key Features:
- Instant propagation via gossip (ROUTE_UPDATE, MODEL_DEPLOYED)
- Full sync on node join (SYNC_REQUEST/RESPONSE)
- Pre-computed embeddings for fast semantic matching
- Optimistic local updates, eventual consistency
"""

from .registry import ModelRegistry, ModelManifest, ModelEntry
from .packager import ModelPackager
from .distributor import ModelDistributor
from .gossip import (
    ModelGossip,
    ModelMessage,
    MessageType,
    ModelRoute,
    ModelRoutingTable,
)

__all__ = [
    # Registry
    "ModelRegistry",
    "ModelManifest", 
    "ModelEntry",
    # Packager
    "ModelPackager",
    # Distributor
    "ModelDistributor",
    # Gossip
    "ModelGossip",
    "ModelMessage",
    "MessageType",
    "ModelRoute",
    "ModelRoutingTable",
]
