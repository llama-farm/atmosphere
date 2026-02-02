"""
Atmosphere - The Internet of Intent

A semantic mesh network for AI capabilities. Route intents to the best
available resources across your personal cloud of devices.

Example:
    >>> from atmosphere import Atmosphere
    >>> atm = Atmosphere()
    >>> await atm.initialize()
    >>> result = await atm.execute("summarize this document", document=doc)
"""

__version__ = "1.0.0"

from .config import Config, get_config
from .mesh.node import Node, NodeIdentity

__all__ = [
    "__version__",
    "Config",
    "get_config",
    "Node",
    "NodeIdentity",
]
