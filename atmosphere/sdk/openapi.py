"""OpenAPI spec parsing for automatic capability discovery."""

import logging
from typing import Dict, List, Any, Optional
import httpx

from .capability import Capability, CapabilityType

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
