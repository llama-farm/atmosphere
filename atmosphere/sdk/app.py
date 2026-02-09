"""Main AtmosphereApp class."""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import httpx

from .capability import Capability, CapabilityType, ToolSpec, ToolParam
from .client import MeshClient
from .events import EventEmitter
from .openapi import register_from_openapi, OpenAPIParser

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
    
    async def register_from_openapi(
        self,
        openapi_url: Optional[str] = None,
        capability_type_map: Optional[Dict[str, CapabilityType]] = None,
        keyword_overrides: Optional[Dict[str, List[str]]] = None,
        push_events: Optional[Dict[str, List[str]]] = None
    ) -> None:
        """
        Auto-discover and register capabilities from OpenAPI spec.
        
        This is the recommended way to register FastAPI apps — it reads
        endpoint descriptions directly from your route definitions.
        
        Example:
            ```python
            app = AtmosphereApp("horizon", app_base_url="http://localhost:8074")
            
            await app.register_from_openapi(
                capability_type_map={
                    "anomaly": CapabilityType.APP_QUERY,
                    "agent": CapabilityType.APP_ACTION,
                },
                keyword_overrides={
                    "anomaly": ["alert", "critical", "fuel", "weather"],
                },
                push_events={
                    "anomaly": ["anomaly.new", "anomaly.critical"],
                }
            )
            
            await app.start()
            ```
        
        Args:
            openapi_url: URL to OpenAPI JSON (defaults to {app_base_url}/openapi.json)
            capability_type_map: Map tag -> CapabilityType (defaults to APP_QUERY)
            keyword_overrides: Map tag -> additional keywords
            push_events: Map tag -> push event names
        """
        if openapi_url is None:
            openapi_url = f"{self.app_base_url}/openapi.json"
        
        logger.info(f"Auto-discovering capabilities from {openapi_url}")
        
        capabilities = await register_from_openapi(
            app_name=self.name,
            openapi_url=openapi_url,
            capability_type_map=capability_type_map,
            keyword_overrides=keyword_overrides,
            push_events=push_events
        )
        
        for capability in capabilities:
            self.register(capability)
        
        logger.info(f"✓ Auto-registered {len(capabilities)} capabilities from OpenAPI spec")
    
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
    
    def get_tools(self) -> Dict[str, ToolSpec]:
        """Get all tools across all registered capabilities."""
        tools = {}
        for cap in self._capabilities:
            tools.update(cap.tools)
        return tools

    def get_tool(self, tool_name: str) -> Optional[ToolSpec]:
        """Find a tool by name across all capabilities."""
        for cap in self._capabilities:
            if tool_name in cap.tools:
                return cap.tools[tool_name]
        return None

    async def call_tool(self, tool_name: str, **params: Any) -> Any:
        """
        Call a tool by name with parameters.
        
        Resolves the tool to its underlying HTTP endpoint, validates
        parameters, and makes the request.
        
        Args:
            tool_name: Name of the tool (e.g., "get_active_anomalies")
            **params: Tool parameters
            
        Returns:
            Response data from the app
            
        Raises:
            ValueError: If tool not found or required params missing
        """
        tool = self.get_tool(tool_name)
        if not tool:
            available = list(self.get_tools().keys())
            raise ValueError(f"Tool '{tool_name}' not found. Available: {available}")

        # Validate required parameters
        for p in tool.parameters:
            if p.required and p.name not in params and p.default is None:
                raise ValueError(f"Missing required parameter '{p.name}' for tool '{tool_name}'")

        # Fill defaults
        for p in tool.parameters:
            if p.name not in params and p.default is not None:
                params[p.name] = p.default

        # Build HTTP request from endpoint spec
        ep = tool.endpoint
        method = ep.method.upper()
        path = ep.path
        url = f"{self.app_base_url}{path}"

        # Separate path params, query params, body params
        path_params = {}
        query_params = {}
        body_params = {}

        # Identify path parameters from the URL template
        import re
        path_param_names = set(re.findall(r'\{(\w+)\}', path))

        for key, value in params.items():
            if key in path_param_names:
                path_params[key] = value
                url = url.replace(f"{{{key}}}", str(value))
            elif method == "GET":
                query_params[key] = value
            else:
                body_params[key] = value

        logger.debug(f"Calling tool {tool_name}: {method} {url}")

        if method == "GET":
            response = await self._http_client.get(url, params=query_params)
        elif method in ("POST", "PUT", "PATCH"):
            response = await self._http_client.request(method, url, json=body_params if body_params else None)
        elif method == "DELETE":
            response = await self._http_client.delete(url, params=query_params)
        else:
            response = await self._http_client.request(method, url)

        response.raise_for_status()

        try:
            return response.json()
        except Exception:
            return {"data": response.text}

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
                "app_base_url": self.app_base_url,
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
    
    async def register_from_openapi(
        self,
        openapi_url: str = None,
        *,
        prefix_filter: str = "/api/",
        group_by_tag: bool = True,
        extra_keywords: Dict[str, List[str]] = None,
        push_events: Dict[str, List[str]] = None,
    ) -> int:
        """
        Auto-discover and register capabilities from an OpenAPI spec.
        
        This reads the FastAPI/OpenAPI JSON and creates capabilities
        automatically — endpoint descriptions, parameters, and types
        come directly from the spec. Zero duplication.
        
        Args:
            openapi_url: URL to fetch OpenAPI JSON (default: {app_base_url}/openapi.json)
            prefix_filter: Only include paths starting with this prefix
            group_by_tag: Group endpoints into capabilities by their first tag
            extra_keywords: Additional keywords per tag/capability (e.g. {"anomaly": ["alert", "fuel"]})
            push_events: Push events per tag/capability (e.g. {"anomaly": ["anomaly.new"]})
        
        Returns:
            Number of capabilities registered
        
        Example:
            ```python
            app = AtmosphereApp("horizon", mesh_url="http://localhost:11451")
            
            # One line: auto-discover everything from FastAPI
            await app.register_from_openapi()
            
            # Or with enrichment:
            await app.register_from_openapi(
                extra_keywords={"anomaly": ["fuel", "deviation", "threat"]},
                push_events={"anomaly": ["anomaly.new", "anomaly.critical"]}
            )
            
            await app.start()
            ```
        """
        url = openapi_url or f"{self.app_base_url}/openapi.json"
        extra_keywords = extra_keywords or {}
        push_events = push_events or {}
        
        logger.info(f"Discovering capabilities from OpenAPI spec: {url}")
        
        response = await self._http_client.get(url)
        response.raise_for_status()
        spec = response.json()

        # Parse tools from the spec
        parser = OpenAPIParser(url)
        parser.spec = spec
        tools_by_tag = parser.parse_tools(self.name)
        
        # Noise words to exclude from keyword extraction
        NOISE_WORDS = {
            "", "none", "null", "with", "from", "that", "this", "will", "have",
            "been", "the", "and", "for", "are", "but", "not", "you", "all",
            "can", "her", "was", "one", "our", "out", "when", "which", "their",
            "said", "each", "tell", "does", "set", "three", "want", "air",
            "well", "also", "play", "small", "end", "put", "home", "read",
            "hand", "port", "large", "spell", "add", "even", "land", "here",
            "must", "big", "high", "such", "follow", "act", "why", "ask",
            "men", "change", "went", "light", "kind", "off", "need", "house",
            "picture", "try", "again", "animal", "point", "mother", "world",
            "near", "build", "self", "earth", "father", "get", "its", "only",
            "optional", "optionally", "returns", "return", "filtered", "filter",
            "data", "list", "status", "current", "including",
        }
        
        # Group paths by tag
        tag_endpoints: Dict[str, List[Dict]] = {}
        tag_descriptions: Dict[str, str] = {}
        
        # Extract tag descriptions from spec
        for tag_info in spec.get("tags", []):
            tag_descriptions[tag_info["name"].lower()] = tag_info.get("description", "")
        
        for path, methods in spec.get("paths", {}).items():
            if prefix_filter and not path.startswith(prefix_filter):
                continue
            
            for method, operation in methods.items():
                if method in ("parameters", "servers", "summary", "description"):
                    continue  # skip non-method keys
                
                tags = operation.get("tags", ["default"])
                tag = tags[0].lower() if group_by_tag else "default"
                
                if tag not in tag_endpoints:
                    tag_endpoints[tag] = []
                
                # Build endpoint name from operationId or path
                op_id = operation.get("operationId", "")
                # FastAPI generates operationId like "get_active_anomalies_api_anomaly_active_get"
                # Clean it up
                endpoint_name = op_id.split("_api_")[0] if "_api_" in op_id else op_id
                if not endpoint_name:
                    endpoint_name = f"{method}_{path.replace('/', '_').strip('_')}"
                
                summary = operation.get("summary", "")
                description = operation.get("description", summary)
                
                # Extract keywords from description (words > 4 chars, excluding noise)
                desc_words = set(
                    w.lower().strip(".,!?()—-:;\"'") 
                    for w in (description + " " + summary).split() 
                    if len(w) > 4
                ) - NOISE_WORDS
                
                tag_endpoints[tag].append({
                    "name": endpoint_name,
                    "method": method.upper(),
                    "path": path,
                    "description": description or summary or f"{method.upper()} {path}",
                    "summary": summary,
                    "parameters": [
                        {
                            "name": p.get("name"),
                            "in": p.get("in"),
                            "required": p.get("required", False),
                            "description": p.get("description", ""),
                        }
                        for p in operation.get("parameters", [])
                    ],
                    "keywords": desc_words,
                })
        
        # Create a Capability for each tag group
        count = 0
        for tag, endpoints in tag_endpoints.items():
            # Auto-infer capability type from HTTP methods used
            methods_used = {ep["method"] for ep in endpoints}
            has_mutations = bool(methods_used & {"POST", "PUT", "DELETE", "PATCH"})
            has_reads = "GET" in methods_used
            has_stream = any("stream" in ep["path"] or "sse" in ep["path"] or "events" in ep["path"] for ep in endpoints)
            has_query = any("query" in ep["path"] or "search" in ep["path"] or "ask" in ep["path"] for ep in endpoints)
            
            if has_stream:
                inferred_type = "app/stream"
            elif has_query:
                inferred_type = "app/chat"
            elif has_mutations and not has_reads:
                inferred_type = "app/action"
            elif has_mutations and has_reads:
                inferred_type = "app/action"  # Mixed = action (superset)
            else:
                inferred_type = "app/query"
            
            # Merge keywords from all endpoints + extras
            all_keywords = set()
            all_keywords.add(tag)
            all_keywords.add(self.name)
            for ep in endpoints:
                all_keywords.update(ep["keywords"])
            if tag in extra_keywords:
                all_keywords.update(extra_keywords[tag])
            all_keywords -= NOISE_WORDS
            
            # Build endpoints dict
            ep_dict = {}
            for ep in endpoints:
                ep_dict[ep["name"]] = {
                    "method": ep["method"],
                    "path": ep["path"],
                    "description": ep["description"],
                }
            
            # Use tag description from spec, or auto-generate
            cap_description = tag_descriptions.get(tag, "")
            if not cap_description:
                summaries = [ep["summary"] or ep["description"] for ep in endpoints if ep.get("summary") or ep.get("description")]
                cap_description = f"{tag.title()} operations: " + "; ".join(summaries[:5])
            
            # Attach tools parsed from OpenAPI
            tag_tools = tools_by_tag.get(tag, {})

            capability = Capability(
                id=f"app/{self.name}/{tag}",
                type=inferred_type,
                description=cap_description,
                keywords=sorted(all_keywords),
                endpoints=ep_dict,
                tools=tag_tools,
                push_events=push_events.get(tag, []),
            )
            
            self.register(capability)
            count += 1
            logger.info(f"  Auto-registered: {capability.id} ({len(endpoints)} endpoints, type={inferred_type})")
        
        logger.info(f"✓ Discovered {count} capabilities with {sum(len(e) for e in tag_endpoints.values())} total endpoints")
        return count
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to mesh."""
        return self._client.is_connected
