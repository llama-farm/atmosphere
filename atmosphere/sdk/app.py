"""Main AtmosphereApp class."""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import httpx

from .capability import Capability
from .client import MeshClient
from .events import EventEmitter

logger = logging.getLogger(__name__)


class AtmosphereApp:
    """
    Atmosphere mesh application.
    
    Register your application's APIs with the Atmosphere mesh,
    making them discoverable and callable from anywhere on the mesh.
    
    Example:
        ```python
        app = AtmosphereApp(
            name="horizon",
            description="Mission intelligence for disconnected ops",
            mesh_url="http://localhost:11451"
        )
        
        app.register(Capability(...))
        
        await app.start()
        ```
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        mesh_url: str = "http://localhost:11451",
        app_base_url: str = "http://localhost:8074"
    ):
        """
        Initialize Atmosphere app.
        
        Args:
            name: Application name (e.g., "horizon")
            description: Human-readable description
            mesh_url: URL of local Atmosphere node (HTTP, converted to WS)
            app_base_url: Base URL of your actual application
        """
        self.name = name
        self.description = description
        self.app_base_url = app_base_url
        
        # Convert HTTP URL to WebSocket
        ws_url = mesh_url.replace("http://", "ws://").replace("https://", "wss://")
        if not ws_url.endswith("/ws"):
            ws_url = ws_url.rstrip("/") + "/ws"
        
        self._client = MeshClient(ws_url)
        self._capabilities: List[Capability] = []
        self._request_handler: Optional[Callable] = None
        self._http_client = httpx.AsyncClient(timeout=30.0)
        
        # Event emitter
        self.events = EventEmitter(self._send_event)
        
        # Register message handlers
        self._client.on("app_request", self._handle_app_request)
        self._client.on("push_delivery", self._handle_push_delivery)
    
    def register(self, capability: Capability) -> None:
        """
        Register a capability with the mesh.
        
        Args:
            capability: Capability specification
        """
        self._capabilities.append(capability)
        logger.info(f"Registered capability: {capability.id}")
    
    def on_request(self, handler: Callable) -> None:
        """
        Register a custom request handler.
        
        If provided, this handler will be called instead of the default
        HTTP proxy behavior. Useful for custom routing logic.
        
        Args:
            handler: Async function(request_data) -> response_data
        """
        self._request_handler = handler
        logger.info("Registered custom request handler")
    
    async def start(self) -> None:
        """
        Start the application and connect to mesh.
        
        This will:
        1. Connect to local Atmosphere node
        2. Announce all registered capabilities
        3. Begin listening for requests
        """
        logger.info(f"Starting Atmosphere app: {self.name}")
        
        # Connect to mesh
        await self._client.connect()
        
        # Announce capabilities
        await self._announce_capabilities()
        
        logger.info(f"✓ {self.name} is now visible on the mesh")
    
    async def stop(self) -> None:
        """Stop the application and disconnect from mesh."""
        logger.info(f"Stopping Atmosphere app: {self.name}")
        await self._client.disconnect()
        await self._http_client.aclose()
    
    async def _announce_capabilities(self) -> None:
        """Announce all registered capabilities to the mesh."""
        for capability in self._capabilities:
            message = {
                "type": "capability_register",
                "app_name": self.name,
                "app_description": self.description,
                "capability": capability.to_dict()
            }
            await self._client.send(message)
            logger.info(f"Announced capability: {capability.id}")
    
    async def _handle_app_request(self, message: Dict[str, Any]) -> None:
        """
        Handle an incoming app request from the mesh.
        
        Args:
            message: Request message from mesh
        """
        request_id = message.get("request_id")
        capability_id = message.get("capability_id")
        endpoint = message.get("endpoint")
        params = message.get("params", {})
        headers = message.get("headers", {})
        
        logger.info(f"Handling request: {capability_id}/{endpoint} [{request_id}]")
        
        try:
            # Find the capability
            capability = self._find_capability(capability_id)
            if not capability:
                await self._send_response(request_id, 404, {"error": "Capability not found"})
                return
            
            # Get endpoint spec
            endpoint_spec = capability.endpoints.get(endpoint)
            if not endpoint_spec:
                await self._send_response(request_id, 404, {"error": "Endpoint not found"})
                return
            
            # Use custom handler if provided
            if self._request_handler:
                result = await self._request_handler({
                    "capability_id": capability_id,
                    "endpoint": endpoint,
                    "params": params,
                    "headers": headers
                })
                await self._send_response(request_id, 200, result)
            else:
                # Default: proxy to local app
                result = await self._proxy_request(endpoint_spec, params, headers)
                await self._send_response(request_id, 200, result)
        
        except Exception as e:
            logger.error(f"Error handling request {request_id}: {e}")
            await self._send_response(request_id, 500, {"error": str(e)})
    
    async def _proxy_request(
        self,
        endpoint_spec: Dict[str, Any],
        params: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Any:
        """
        Proxy a request to the local app.
        
        Args:
            endpoint_spec: Endpoint specification
            params: Request parameters
            headers: Request headers
        
        Returns:
            Response data from the app
        """
        method = endpoint_spec["method"].upper()
        path = endpoint_spec["path"]
        url = f"{self.app_base_url}{path}"
        
        # Format path with params if needed
        if "{" in path:
            # Path parameter substitution
            for key, value in params.items():
                url = url.replace(f"{{{key}}}", str(value))
        
        logger.debug(f"Proxying {method} {url}")
        
        # Make the request
        if method == "GET":
            response = await self._http_client.get(url, params=params, headers=headers)
        elif method == "POST":
            response = await self._http_client.post(url, json=params, headers=headers)
        elif method == "PUT":
            response = await self._http_client.put(url, json=params, headers=headers)
        elif method == "DELETE":
            response = await self._http_client.delete(url, params=params, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        
        # Try to parse JSON, fall back to text
        try:
            return response.json()
        except:
            return {"data": response.text}
    
    async def _send_response(
        self,
        request_id: str,
        status: int,
        body: Any
    ) -> None:
        """
        Send a response back through the mesh.
        
        Args:
            request_id: Request ID to respond to
            status: HTTP status code
            body: Response body
        """
        message = {
            "type": "app_response",
            "request_id": request_id,
            "status": status,
            "body": body,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._client.send(message)
    
    async def _send_event(self, message: Dict[str, Any]) -> None:
        """
        Send an event through the mesh.
        
        Args:
            message: Event message
        """
        await self._client.send(message)
    
    async def _handle_push_delivery(self, message: Dict[str, Any]) -> None:
        """
        Handle a push event delivery from the mesh.
        
        Args:
            message: Push delivery message
        """
        event = message.get("event")
        data = message.get("data", {})
        
        logger.debug(f"Received push event: {event}")
        
        # Notify local event listeners
        await self.events._notify_local(event, data)
    
    def _find_capability(self, capability_id: str) -> Optional[Capability]:
        """Find a capability by ID."""
        for cap in self._capabilities:
            if cap.id == capability_id:
                return cap
        return None
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to mesh."""
        return self._client.is_connected
