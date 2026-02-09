"""
Atmosphere SDK - Register applications with Atmosphere mesh.

Allows any Python app to expose its APIs as discoverable, routable
capabilities that can be queried from anywhere on the mesh.
"""

from .capability import Capability, CapabilityType
from .app import AtmosphereApp
from .events import EventEmitter

__all__ = [
    "Capability",
    "CapabilityType",
    "AtmosphereApp",
    "EventEmitter",
]
