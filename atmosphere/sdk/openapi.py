"""OpenAPI spec parsing for automatic capability discovery."""

import logging
from typing import Dict, List, Any, Optional
import httpx

from .capability import Capability, CapabilityType, EndpointSpec, ToolSpec, ToolParam

logger = logging.getLogger(__name__)


class OpenAPIParser:
    """
    Parse OpenAPI/Swagger spec and generate Atmosphere capabilities.
    
    Extracts endpoint descriptions, parameters, and tags from the OpenAPI JSON
    that FastAPI generates automatically.
    """
    
    def __init__(self, spec_url: str):
        """
        Initialize parser.
        
        Args:
            spec_url: URL to OpenAPI JSON (e.g., http://localhost:8074/openapi.json)
        """
        self.spec_url = spec_url
        self.spec: Optional[Dict[str, Any]] = None
    
    async def fetch_spec(self) -> Dict[str, Any]:
        """Fetch the OpenAPI spec from the app."""
        async with httpx.AsyncClient() as client:
            response = await client.get(self.spec_url, timeout=10.0)
            response.raise_for_status()
            self.spec = response.json()
            return self.spec
    
    def _resolve_ref(self, ref: str) -> Dict[str, Any]:
        """Resolve a $ref pointer in the OpenAPI spec."""
        if not ref.startswith("#/"):
            return {}
        parts = ref[2:].split("/")
        obj = self.spec
        for p in parts:
            if isinstance(obj, dict):
                obj = obj.get(p, {})
            else:
                return {}
        return obj if isinstance(obj, dict) else {}

    def _resolve_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve a schema, following $ref if present."""
        if "$ref" in schema:
            return self._resolve_ref(schema["$ref"])
        return schema

    def _schema_to_type(self, schema: Dict[str, Any]) -> str:
        """Convert JSON Schema type to tool param type."""
        schema = self._resolve_schema(schema)
        t = schema.get("type", "string")
        if t == "integer":
            return "number"
        if t in ("string", "number", "boolean", "object", "array"):
            return t
        return "string"

    def _extract_params_from_schema(self, schema: Dict[str, Any]) -> List[ToolParam]:
        """Extract ToolParam list from a JSON Schema object."""
        schema = self._resolve_schema(schema)
        if schema.get("type") != "object":
            return []
        required_set = set(schema.get("required", []))
        params = []
        for name, prop in schema.get("properties", {}).items():
            prop = self._resolve_schema(prop)
            params.append(ToolParam(
                name=name,
                type=self._schema_to_type(prop),
                description=prop.get("description", prop.get("title", "")),
                required=name in required_set,
                default=prop.get("default"),
                enum=prop.get("enum"),
            ))
        return params

    def _extract_returns(self, responses: Dict[str, Any]) -> str:
        """Extract return description from OpenAPI responses."""
        for code in ("200", "201", "2XX"):
            resp = responses.get(code, {})
            if isinstance(resp, dict):
                desc = resp.get("description", "")
                # Try to get schema description
                content = resp.get("content", {})
                json_content = content.get("application/json", {})
                schema = json_content.get("schema", {})
                schema = self._resolve_schema(schema)
                schema_desc = schema.get("description", schema.get("title", ""))
                return desc or schema_desc or "Successful response"
        return "Response"

    def parse_tools(self, app_name: str) -> Dict[str, Dict[str, ToolSpec]]:
        """
        Parse OpenAPI spec into ToolSpec objects grouped by tag.
        
        Returns:
            Dict of tag -> {tool_name: ToolSpec}
        """
        if not self.spec:
            raise ValueError("Must call fetch_spec() first")

        tools_by_tag: Dict[str, Dict[str, ToolSpec]] = {}

        for path, path_item in self.spec.get("paths", {}).items():
            for method, operation in path_item.items():
                if method.upper() not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    continue

                tags = operation.get("tags", ["default"])
                tag = tags[0].lower()

                # Tool name from operationId
                op_id = operation.get("operationId", "")
                tool_name = op_id.split("_api_")[0] if "_api_" in op_id else op_id
                if not tool_name:
                    tool_name = f"{method}_{path.replace('/', '_').strip('_')}"

                # Description
                summary = operation.get("summary", "")
                description = operation.get("description", "") or summary
                if summary and description and summary != description:
                    description = f"{summary}. {description}"

                # Collect parameters
                params: List[ToolParam] = []

                # Path and query parameters
                for p in operation.get("parameters", []):
                    schema = p.get("schema", {})
                    params.append(ToolParam(
                        name=p["name"],
                        type=self._schema_to_type(schema),
                        description=p.get("description", ""),
                        required=p.get("required", p.get("in") == "path"),
                        default=schema.get("default"),
                        enum=schema.get("enum"),
                    ))

                # Request body
                request_body = operation.get("requestBody", {})
                if request_body:
                    content = request_body.get("content", {})
                    json_content = content.get("application/json", {})
                    body_schema = json_content.get("schema", {})
                    if body_schema:
                        params.extend(self._extract_params_from_schema(body_schema))

                # Returns
                returns = self._extract_returns(operation.get("responses", {}))

                endpoint = EndpointSpec(
                    method=method.upper(),
                    path=path,
                    description=description or f"{method.upper()} {path}",
                )

                tool = ToolSpec(
                    name=tool_name,
                    description=description or f"{method.upper()} {path}",
                    parameters=params,
                    returns=returns,
                    endpoint=endpoint,
                    tags=[tag],
                )

                if tag not in tools_by_tag:
                    tools_by_tag[tag] = {}
                tools_by_tag[tag][tool_name] = tool

        return tools_by_tag

    def parse_capabilities(
        self,
        app_name: str,
        capability_type_map: Optional[Dict[str, CapabilityType]] = None,
        keyword_overrides: Optional[Dict[str, List[str]]] = None,
        push_events: Optional[Dict[str, List[str]]] = None
    ) -> List[Capability]:
        """
        Parse OpenAPI spec into Atmosphere capabilities.
        
        Groups endpoints by tag (e.g., "anomaly", "agent") and creates
        one capability per tag.
        
        Args:
            app_name: Application name (e.g., "horizon")
            capability_type_map: Map tag -> CapabilityType (defaults to APP_QUERY)
            keyword_overrides: Map tag -> list of keywords to add
            push_events: Map tag -> list of push events this capability emits
        
        Returns:
            List of Capability objects
        """
        if not self.spec:
            raise ValueError("Must call fetch_spec() first")
        
        capability_type_map = capability_type_map or {}
        keyword_overrides = keyword_overrides or {}
        push_events = push_events or {}
        
        # Group paths by tag
        paths_by_tag: Dict[str, List[Dict[str, Any]]] = {}
        
        for path, path_item in self.spec.get("paths", {}).items():
            for method, operation in path_item.items():
                if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    continue
                
                tags = operation.get("tags", ["default"])
                for tag in tags:
                    if tag not in paths_by_tag:
                        paths_by_tag[tag] = []
                    
                    paths_by_tag[tag].append({
                        "path": path,
                        "method": method.upper(),
                        "operation": operation,
                        "operationId": operation.get("operationId", ""),
                        "summary": operation.get("summary", ""),
                        "description": operation.get("description", ""),
                        "parameters": operation.get("parameters", []),
                    })
        
        # Create capabilities
        capabilities = []
        
        for tag, endpoints in paths_by_tag.items():
            # Determine capability ID and type
            capability_id = f"app/{app_name}/{tag}"
            capability_type = capability_type_map.get(tag, CapabilityType.APP_QUERY)
            
            # Build endpoint dict for capability
            endpoint_dict = {}
            keywords_set = set()
            
            for endpoint in endpoints:
                # Use operationId as endpoint name, or generate from method+path
                endpoint_name = endpoint["operationId"]
                if not endpoint_name:
                    # Generate name: get_active_anomalies, etc.
                    endpoint_name = f"{endpoint['method'].lower()}{endpoint['path'].replace('/', '_')}"
                
                # Clean up endpoint name
                endpoint_name = endpoint_name.replace(f"{tag}_", "").replace("_", "_").strip("_")
                
                endpoint_dict[endpoint_name] = {
                    "method": endpoint["method"],
                    "path": endpoint["path"],
                    "description": endpoint["description"] or endpoint["summary"] or "No description",
                }
                
                # Extract keywords from summary and description
                text = f"{endpoint['summary']} {endpoint['description']}".lower()
                words = text.split()
                keywords_set.update([w.strip(",.!?:;") for w in words if len(w) > 4])
            
            # Add tag itself as keyword
            keywords_set.add(tag.lower())
            
            # Add manual keyword overrides
            if tag in keyword_overrides:
                keywords_set.update(keyword_overrides[tag])
            
            # Get tag description from OpenAPI spec (if available)
            tag_description = ""
            for tag_obj in self.spec.get("tags", []):
                if tag_obj.get("name") == tag:
                    tag_description = tag_obj.get("description", "")
                    break
            
            if not tag_description:
                # Generate description from endpoint summaries
                tag_description = f"API endpoints for {tag}. " + ". ".join([
                    e["summary"] for e in endpoints[:3] if e["summary"]
                ])
            
            capability = Capability(
                id=capability_id,
                type=capability_type,
                description=tag_description,
                keywords=sorted(list(keywords_set)),
                endpoints=endpoint_dict,
                push_events=push_events.get(tag, []),
                metadata={
                    "source": "openapi",
                    "spec_url": self.spec_url,
                    "tag": tag,
                }
            )
            
            capabilities.append(capability)
            logger.info(f"Generated capability: {capability_id} with {len(endpoint_dict)} endpoints")
        
        return capabilities


async def register_from_openapi(
    app_name: str,
    openapi_url: str,
    capability_type_map: Optional[Dict[str, CapabilityType]] = None,
    keyword_overrides: Optional[Dict[str, List[str]]] = None,
    push_events: Optional[Dict[str, List[str]]] = None
) -> List[Capability]:
    """
    Auto-discover and register capabilities from OpenAPI spec.
    
    Example:
        ```python
        capabilities = await register_from_openapi(
            app_name="horizon",
            openapi_url="http://localhost:8074/openapi.json",
            capability_type_map={
                "anomaly": CapabilityType.APP_QUERY,
                "agent": CapabilityType.APP_ACTION,
                "knowledge": CapabilityType.APP_CHAT,
            },
            keyword_overrides={
                "anomaly": ["alert", "critical", "mission"],
                "agent": ["hil", "approval", "human-in-the-loop"],
            },
            push_events={
                "anomaly": ["anomaly.new", "anomaly.critical", "anomaly.resolved"],
                "agent": ["action.needs_approval", "action.approved"],
            }
        )
        ```
    
    Args:
        app_name: Application name (e.g., "horizon")
        openapi_url: URL to OpenAPI JSON (e.g., http://localhost:8074/openapi.json)
        capability_type_map: Optional map of tag -> CapabilityType
        keyword_overrides: Optional map of tag -> additional keywords
        push_events: Optional map of tag -> push event names
    
    Returns:
        List of generated Capability objects
    """
    parser = OpenAPIParser(openapi_url)
    await parser.fetch_spec()
    
    return parser.parse_capabilities(
        app_name=app_name,
        capability_type_map=capability_type_map,
        keyword_overrides=keyword_overrides,
        push_events=push_events
    )
