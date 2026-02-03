"""
Atmosphere Integrations.

External system integrations that bring capabilities into the Atmosphere mesh.

Available Integrations:
- matter: Matter/Thread smart home protocol integration
"""

from . import matter

__all__ = [
    "matter",
]
