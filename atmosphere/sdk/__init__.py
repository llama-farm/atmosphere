"""
Atmosphere SDK - Register applications with Atmosphere mesh.

Allows any Python app to expose its APIs as discoverable, routable
capabilities that can be queried from anywhere on the mesh.

Recommended usage (auto-discovery from OpenAPI):
    ```python
    from atmosphere.sdk import AtmosphereApp, CapabilityType
    
    app = AtmosphereApp(
        name="myapp",
        description="My FastAPI application",
        app_base_url="http://localhost:8000"
    )
    
    await app.register_from_openapi(
        capability_type_map={"users": CapabilityType.APP_QUERY},
        push_events={"notifications": ["notification.new"]}
    )
    
    await app.start()
    ```
"""

from .capability import Capability, CapabilityType, EndpointSpec, ToolSpec, ToolParam
from .app import AtmosphereApp
from .events import EventEmitter
from .openapi import register_from_openapi

__all__ = [
    "Capability",
    "CapabilityType",
    "EndpointSpec",
    "ToolSpec",
    "ToolParam",
    "AtmosphereApp",
    "EventEmitter",
    "register_from_openapi",
]
