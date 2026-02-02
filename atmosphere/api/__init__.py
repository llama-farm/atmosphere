"""
API server for Atmosphere.

Provides REST and WebSocket endpoints for:
- Intent routing
- Capability execution
- Mesh management
- OpenAI-compatible chat completions
"""

from .server import create_app, AtmosphereServer
from .routes import router

__all__ = [
    "create_app",
    "AtmosphereServer",
    "router",
]
