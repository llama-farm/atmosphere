"""
App Mesh handlers - Route requests to registered applications.

Handles:
- capability_register: Apps announce their capabilities
- app_request: Requests routed to apps through the mesh  
- app_response: Responses from apps back to requesters
- push_event: Events pushed from apps to subscribers
- HTTP proxy: Direct HTTP calls to registered app endpoints
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional, Set, List
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


class AppMeshManager:
    """
    Manages application registrations and request routing.
    
    Apps connect via WebSocket and register capabilities. Requests
    are routed through the mesh to the appropriate app based on
    semantic matching or explicit capability IDs.
    """
    
    def __init__(self, capability_registry):
        """
        Initialize app mesh manager.
        
        Args:
            capability_registry: CapabilityRegistry instance
        """
        self.registry = capability_registry
        self._app_connections: Dict[str, Any] = {}  # app_name -> websocket
        self._app_base_urls: Dict[str, str] = {}  # app_name -> base URL for HTTP proxy
        self._pending_requests: Dict[str, Dict[str, Any]] = {}  # request_id -> request_info
        self._event_subscriptions: Dict[str, Set[str]] = {}  # event_pattern -> set of subscriber websockets
        self._http_client = httpx.AsyncClient(timeout=30.0)
        
    async def handle_capability_register(
        self,
        message: Dict[str, Any],
        websocket: Any
    ) -> None:
        """
        Handle app capability registration.
        
        Message format:
        {
            "type": "capability_register",
            "app_name": "horizon",
            "app_description": "...",
            "capability": {
                "id": "app/horizon/anomaly",
                "type": "app/query",
                "description": "...",
                "keywords": [...],
                "endpoints": {...},
                "push_events": [...]
            }
        }
        """
        try:
            app_name = message.get("app_name")
            capability_data = message.get("capability", {})
            
            if not app_name or not capability_data:
                logger.error("Invalid capability_register message")
                return
            
            # Store app connection and base URL
            if app_name not in self._app_connections:
                self._app_connections[app_name] = websocket
                logger.info(f"Registered app connection: {app_name}")
            
            # Store base URL for HTTP proxy (from capability metadata or message)
            app_base_url = message.get("app_base_url") or capability_data.get("metadata", {}).get("app_base_url")
            if app_base_url:
                self._app_base_urls[app_name] = app_base_url
                logger.info(f"  HTTP proxy: {app_base_url}")
            
            # Convert to Capability and register
            from ..capabilities.registry import Capability, CapabilityType, Tool, Trigger
            from .server import get_server
            
            _server = get_server()
            node_id = _server.node.node_id if _server and _server.node else "local"
            
            # Create tools from endpoints
            tools = []
            for endpoint_name, endpoint_spec in capability_data.get("endpoints", {}).items():
                tools.append(Tool(
                    name=endpoint_name,
                    description=endpoint_spec.get("description", ""),
                    parameters=endpoint_spec.get("params", {}),
                ))
            
            # Create triggers from push events
            triggers = []
            for event_name in capability_data.get("push_events", []):
                triggers.append(Trigger(
                    event=event_name,
                    description=f"Push event: {event_name}",
                    intent_template=f"{event_name}: {{data}}",
                ))
            
            capability = Capability(
                id=capability_data["id"],
                node_id=node_id,
                type=CapabilityType(capability_data["type"]),
                tools=tools,
                triggers=triggers,
                metadata={
                    "app_name": app_name,
                    "app_base_url": app_base_url or "",
                    "description": capability_data.get("description", ""),
                    "keywords": capability_data.get("keywords", []),
                    "endpoints": capability_data.get("endpoints", {}),
                    "tools": capability_data.get("tools", {}),  # Tool definitions from OpenAPI
                }
            )
            
            await self.registry.register(capability)
            
            logger.info(f"✓ Registered capability: {capability.id} from {app_name}")
            
            # Send acknowledgment
            await websocket.send_json({
                "type": "capability_registered",
                "capability_id": capability.id,
                "status": "success"
            })
            
            # If mesh is available, propagate to other nodes via gossip
            if _server and hasattr(_server, 'gossip') and _server.gossip:
                try:
                    gossip_msg = self.registry.generate_available_message(capability)
                    if gossip_msg:
                        await _server.gossip.broadcast_capabilities()
                except Exception:
                    pass  # Gossip propagation is best-effort
            
        except Exception as e:
            logger.error(f"Error registering capability: {e}", exc_info=True)
            await websocket.send_json({
                "type": "capability_registered",
                "status": "error",
                "error": str(e)
            })
    
    async def handle_tool_call(
        self,
        message: Dict[str, Any],
        source_websocket: Any = None
    ) -> Optional[Dict[str, Any]]:
        """
        Handle a tool_call message: resolve tool → endpoint → HTTP request.
        
        Message format:
        {
            "type": "tool_call",
            "app": "horizon",
            "tool": "scan_anomalies",
            "params": {...},
            "request_id": "uuid"  # optional
        }
        
        Returns response dict or sends via websocket.
        """
        try:
            request_id = message.get("request_id") or str(uuid.uuid4())
            app_name = message.get("app")
            tool_name = message.get("tool")
            params = message.get("params", {})

            if not app_name or not tool_name:
                error = {"type": "tool_response", "request_id": request_id, "status": 400, "body": {"error": "Missing 'app' or 'tool'"}}
                if source_websocket:
                    await source_websocket.send_json(error)
                return error

            # Find the tool across all capabilities for this app
            base_url = self._app_base_urls.get(app_name)
            tool_endpoint = None

            for cap_id, cap in self.registry._capabilities.items():
                if cap.metadata.get("app_name") != app_name:
                    continue
                endpoints = cap.metadata.get("endpoints", {})
                tools = cap.metadata.get("tools", {})
                # Check tools first
                if tool_name in tools:
                    t = tools[tool_name]
                    ep = t.get("endpoint", {}) if isinstance(t, dict) else {}
                    tool_endpoint = ep
                    break
                # Fall back to endpoints
                if tool_name in endpoints:
                    tool_endpoint = endpoints[tool_name]
                    break

            if not tool_endpoint or not base_url:
                error = {"type": "tool_response", "request_id": request_id, "status": 404, "body": {"error": f"Tool '{tool_name}' not found for app '{app_name}'"}}
                if source_websocket:
                    await source_websocket.send_json(error)
                return error

            # Build HTTP request
            method = tool_endpoint.get("method", "GET").upper()
            path = tool_endpoint.get("path", f"/{tool_name}")
            url = f"{base_url.rstrip('/')}{path}"

            # Substitute path params
            import re
            for key in re.findall(r'\{(\w+)\}', path):
                if key in params:
                    url = url.replace(f"{{{key}}}", str(params.pop(key)))

            try:
                if method == "GET":
                    response = await self._http_client.get(url, params=params)
                elif method in ("POST", "PUT", "PATCH"):
                    response = await self._http_client.request(method, url, json=params if params else None)
                elif method == "DELETE":
                    response = await self._http_client.delete(url, params=params)
                else:
                    response = await self._http_client.request(method, url)

                try:
                    body = response.json()
                except Exception:
                    body = {"text": response.text}

                result = {"type": "tool_response", "request_id": request_id, "status": response.status_code, "body": body, "tool": tool_name}
                logger.info(f"✓ Tool call {app_name}/{tool_name} → {response.status_code}")

            except httpx.ConnectError:
                result = {"type": "tool_response", "request_id": request_id, "status": 503, "body": {"error": f"App unreachable: {app_name}"}}
            except httpx.TimeoutException:
                result = {"type": "tool_response", "request_id": request_id, "status": 504, "body": {"error": f"App timeout: {app_name}"}}

            if source_websocket:
                await source_websocket.send_json(result)
            return result

        except Exception as e:
            logger.error(f"Error handling tool_call: {e}", exc_info=True)
            error = {"type": "tool_response", "request_id": message.get("request_id", ""), "status": 500, "body": {"error": str(e)}}
            if source_websocket:
                await source_websocket.send_json(error)
            return error

    def get_tools_for_app(self, app_name: str) -> Dict[str, Any]:
        """
        Get all tools for a given app, across all its capabilities.
        Used by GET /apps/{app_name}/tools endpoint.
        """
        tools = {}
        for cap_id, cap in self.registry._capabilities.items():
            if cap.metadata.get("app_name") != app_name:
                continue
            # Prefer tools from metadata
            cap_tools = cap.metadata.get("tools", {})
            if cap_tools:
                tools.update(cap_tools)
            else:
                # Fall back to endpoints as pseudo-tools
                for ep_name, ep_spec in cap.metadata.get("endpoints", {}).items():
                    tools[ep_name] = {
                        "name": ep_name,
                        "description": ep_spec.get("description", ""),
                        "parameters": [],
                        "returns": "Response",
                        "endpoint": ep_spec,
                    }
        return tools

    async def handle_app_request(
        self,
        message: Dict[str, Any],
        source_websocket: Any = None
    ) -> None:
        """
        Handle a request to an app capability.
        
        Message format:
        {
            "type": "app_request",
            "request_id": "uuid",
            "capability_id": "app/horizon/anomaly",
            "endpoint": "list_active",
            "params": {...},
            "headers": {...},
            "source_node": "node-id"  # optional, for mesh routing
        }
        """
        try:
            request_id = message.get("request_id") or str(uuid.uuid4())
            capability_id = message.get("capability_id")
            endpoint = message.get("endpoint")
            
            if not capability_id or not endpoint:
                logger.error("Invalid app_request message")
                return
            
            # Find the capability
            capability = self.registry.get(capability_id)
            if not capability:
                logger.error(f"Capability not found: {capability_id}")
                if source_websocket:
                    await source_websocket.send_json({
                        "type": "app_response",
                        "request_id": request_id,
                        "status": 404,
                        "body": {"error": "Capability not found"}
                    })
                return
            
            # Get the app name from metadata
            app_name = capability.metadata.get("app_name")
            if not app_name or app_name not in self._app_connections:
                logger.error(f"App not connected: {app_name}")
                if source_websocket:
                    await source_websocket.send_json({
                        "type": "app_response",
                        "request_id": request_id,
                        "status": 503,
                        "body": {"error": "App not available"}
                    })
                return
            
            # Store pending request
            self._pending_requests[request_id] = {
                "source_websocket": source_websocket,
                "timestamp": time.time(),
                "capability_id": capability_id,
                "endpoint": endpoint
            }
            
            # Forward request to app
            app_ws = self._app_connections[app_name]
            await app_ws.send_json({
                "type": "app_request",
                "request_id": request_id,
                "capability_id": capability_id,
                "endpoint": endpoint,
                "params": message.get("params", {}),
                "headers": message.get("headers", {}),
                "source_node": message.get("source_node")
            })
            
            logger.debug(f"Forwarded request {request_id} to {app_name}")
            
        except Exception as e:
            logger.error(f"Error handling app_request: {e}", exc_info=True)
    
    async def handle_app_response(
        self,
        message: Dict[str, Any],
        app_websocket: Any
    ) -> None:
        """
        Handle a response from an app.
        
        Message format:
        {
            "type": "app_response",
            "request_id": "uuid",
            "status": 200,
            "body": {...},
            "timestamp": "..."
        }
        """
        try:
            request_id = message.get("request_id")
            
            if not request_id or request_id not in self._pending_requests:
                logger.warning(f"Unknown request_id: {request_id}")
                return
            
            # Get the original requester
            request_info = self._pending_requests.pop(request_id)
            source_ws = request_info.get("source_websocket")
            
            if source_ws:
                # Forward response back to requester
                await source_ws.send_json(message)
                logger.debug(f"Forwarded response for {request_id}")
            else:
                logger.debug(f"Response {request_id} has no source (may be from another node)")
            
        except Exception as e:
            logger.error(f"Error handling app_response: {e}", exc_info=True)
    
    async def handle_push_event(
        self,
        message: Dict[str, Any],
        app_websocket: Any
    ) -> None:
        """
        Handle a push event from an app.
        
        Message format:
        {
            "type": "push_event",
            "event": "anomaly.new",
            "data": {...},
            "timestamp": "..."
        }
        
        Events are propagated via gossip to all mesh nodes and delivered
        to local subscribers.
        """
        try:
            event = message.get("event")
            data = message.get("data", {})
            
            if not event:
                logger.error("Invalid push_event message")
                return
            
            logger.info(f"Push event: {event}")
            
            # Find subscribers matching the event pattern
            subscribers = self._find_subscribers(event)
            
            # Deliver to local subscribers
            delivery_msg = {
                "type": "push_delivery",
                "event": event,
                "data": data,
                "timestamp": message.get("timestamp", datetime.utcnow().isoformat())
            }
            
            for subscriber_ws in subscribers:
                try:
                    await subscriber_ws.send_json(delivery_msg)
                except Exception as e:
                    logger.error(f"Error delivering to subscriber: {e}")
            
            logger.debug(f"Delivered event {event} to {len(subscribers)} local subscribers")
            
            # Propagate to other mesh nodes via gossip
            from .server import get_server
            _server = get_server()
            if _server and _server.node:
                await _server.node.gossip({
                    "type": "push_event",
                    "event": event,
                    "data": data,
                    "timestamp": message.get("timestamp"),
                    "source_node": node.node_id
                })
            
        except Exception as e:
            logger.error(f"Error handling push_event: {e}", exc_info=True)
    
    async def subscribe_to_events(
        self,
        patterns: List[str],
        websocket: Any
    ) -> None:
        """
        Subscribe a websocket to event patterns.
        
        Args:
            patterns: List of event patterns (supports wildcards: "anomaly.*")
            websocket: WebSocket to receive events
        """
        for pattern in patterns:
            if pattern not in self._event_subscriptions:
                self._event_subscriptions[pattern] = set()
            self._event_subscriptions[pattern].add(id(websocket))
            logger.info(f"Subscribed to events: {pattern}")
    
    async def unsubscribe(self, websocket: Any) -> None:
        """Unsubscribe a websocket from all events."""
        ws_id = id(websocket)
        for pattern, subscribers in self._event_subscriptions.items():
            subscribers.discard(ws_id)
    
    def _find_subscribers(self, event: str) -> List[Any]:
        """Find all websockets subscribed to an event."""
        subscribers = []
        for pattern, ws_ids in self._event_subscriptions.items():
            if self._match_pattern(event, pattern):
                subscribers.extend(ws_ids)
        return subscribers
    
    def _match_pattern(self, event: str, pattern: str) -> bool:
        """Check if event matches pattern (supports wildcards)."""
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event.startswith(prefix)
        return event == pattern
    
    async def proxy_http_request(
        self,
        capability_id: str,
        endpoint: str,
        params: Dict[str, Any] = None,
        method: str = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Proxy a request directly to an app via HTTP.
        
        This is the fast path — no WebSocket round-trip needed. The mesh
        node calls the app's HTTP API directly using the stored base URL
        and endpoint path from the capability's metadata.
        
        Args:
            capability_id: e.g., "app/horizon/anomaly"
            endpoint: Endpoint name from the capability (e.g., "get_active_anomalies")
            params: Query params or body params
            method: HTTP method override (auto-detected from capability if not provided)
        
        Returns:
            {"status": int, "body": dict} or None if capability not found
        """
        params = params or {}
        
        # Find the capability
        capability = self.registry.get(capability_id)
        if not capability:
            logger.warning(f"Capability not found: {capability_id}")
            return None
        
        # Get app base URL
        app_name = capability.metadata.get("app_name")
        base_url = self._app_base_urls.get(app_name) if app_name else None
        
        if not base_url:
            # Try to extract from capability metadata
            base_url = capability.metadata.get("app_base_url")
        
        if not base_url:
            logger.warning(f"No base URL for app: {app_name}")
            return None
        
        # Find the endpoint spec
        endpoints = capability.metadata.get("endpoints", {})
        ep_spec = endpoints.get(endpoint)
        
        if not ep_spec:
            logger.warning(f"Endpoint not found: {endpoint} in {capability_id}")
            # Try matching by partial name
            for ep_name, spec in endpoints.items():
                if endpoint.lower() in ep_name.lower() or ep_name.lower() in endpoint.lower():
                    ep_spec = spec
                    break
        
        if not ep_spec:
            logger.warning(f"No matching endpoint for: {endpoint}")
            return None
        
        # Build the HTTP request
        http_method = (method or ep_spec.get("method", "GET")).upper()
        path = ep_spec.get("path", f"/{endpoint}")
        url = f"{base_url.rstrip('/')}{path}"
        
        try:
            if http_method == "GET":
                response = await self._http_client.get(url, params=params)
            elif http_method == "POST":
                response = await self._http_client.post(url, json=params)
            elif http_method == "PUT":
                response = await self._http_client.put(url, json=params)
            elif http_method == "DELETE":
                response = await self._http_client.delete(url, params=params)
            else:
                response = await self._http_client.request(http_method, url, json=params)
            
            # Parse response
            try:
                body = response.json()
            except Exception:
                body = {"text": response.text}
            
            logger.info(f"✓ Proxied {http_method} {url} → {response.status_code}")
            
            return {
                "status": response.status_code,
                "body": body,
            }
            
        except httpx.ConnectError:
            logger.error(f"App unreachable: {url}")
            return {"status": 503, "body": {"error": f"App unreachable: {app_name}"}}
        except httpx.TimeoutException:
            logger.error(f"App timeout: {url}")
            return {"status": 504, "body": {"error": f"App timeout: {app_name}"}}
        except Exception as e:
            logger.error(f"HTTP proxy error: {e}")
            return {"status": 500, "body": {"error": str(e)}}

    async def disconnect_app(self, app_name: str) -> None:
        """Handle app disconnection."""
        if app_name in self._app_connections:
            del self._app_connections[app_name]
            logger.info(f"App disconnected: {app_name}")
            
            # Deregister app's capabilities
            for cap_id, cap in list(self.registry._capabilities.items()):
                if cap.metadata.get("app_name") == app_name:
                    await self.registry.deregister(cap_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get app mesh statistics."""
        return {
            "connected_apps": len(self._app_connections),
            "apps": list(self._app_connections.keys()),
            "pending_requests": len(self._pending_requests),
            "event_subscriptions": len(self._event_subscriptions),
        }


# Global instance
_app_mesh_manager: Optional[AppMeshManager] = None


def get_app_mesh_manager(capability_registry=None) -> AppMeshManager:
    """Get the global app mesh manager."""
    global _app_mesh_manager
    if _app_mesh_manager is None:
        if capability_registry is None:
            from ..capabilities.registry import get_registry
            capability_registry = get_registry()
        _app_mesh_manager = AppMeshManager(capability_registry)
    return _app_mesh_manager
