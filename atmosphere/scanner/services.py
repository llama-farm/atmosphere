"""
Service Detection Module

Detects running AI services: Ollama, LlamaFarm, Universal Runtime, etc.
"""

import asyncio
import logging
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import httpx

logger = logging.getLogger(__name__)


# Known AI/ML service ports
KNOWN_SERVICES = {
    11434: ("ollama", "Ollama LLM Server"),
    14345: ("llamafarm", "LlamaFarm API"),
    11540: ("universal-runtime", "Universal Runtime"),
    8000: ("api", "FastAPI/Generic HTTP"),
    8080: ("http", "HTTP Server"),
    5000: ("flask", "Flask/Generic HTTP"),
    6333: ("qdrant", "Qdrant Vector DB"),
    19530: ("milvus", "Milvus Vector DB"),
    8983: ("solr", "Apache Solr"),
    9200: ("elasticsearch", "Elasticsearch"),
    6379: ("redis", "Redis"),
    5432: ("postgres", "PostgreSQL"),
    27017: ("mongodb", "MongoDB"),
    7860: ("gradio", "Gradio Interface"),
    8501: ("streamlit", "Streamlit App"),
}


@dataclass
class ServiceInfo:
    """Information about a detected service."""
    name: str
    port: int
    type: str
    endpoint: str
    healthy: bool = False
    version: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "port": self.port,
            "type": self.type,
            "endpoint": self.endpoint,
            "healthy": self.healthy,
            "version": self.version,
            "details": self.details,
        }


def _probe_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a port is open (TCP connect)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


async def detect_services(
    host: str = "localhost",
    ports: Optional[List[int]] = None,
    verify: bool = True,
    timeout: float = 2.0
) -> List[ServiceInfo]:
    """
    Detect running services on known AI/ML ports.
    
    Args:
        host: Host to scan (default: localhost)
        ports: Specific ports to check (default: all known ports)
        verify: Whether to verify services via HTTP (default: True)
        timeout: Connection timeout in seconds
    
    Returns:
        List of ServiceInfo objects for detected services
    """
    if ports is None:
        ports = list(KNOWN_SERVICES.keys())
    
    services = []
    
    # Parallel port probing
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=min(len(ports), 20)) as executor:
        probe_tasks = {
            port: loop.run_in_executor(executor, _probe_port, host, port, timeout)
            for port in ports
        }
        
        for port, future in probe_tasks.items():
            try:
                is_open = await future
                if is_open:
                    service_type, name = KNOWN_SERVICES.get(port, ("unknown", f"Service on {port}"))
                    endpoint = f"http://{host}:{port}"
                    
                    service = ServiceInfo(
                        name=name,
                        port=port,
                        type=service_type,
                        endpoint=endpoint,
                        healthy=False,
                    )
                    
                    # Verify service if requested
                    if verify:
                        service = await _verify_service(service, timeout)
                    
                    services.append(service)
            except Exception as e:
                logger.debug(f"Error probing port {port}: {e}")
    
    return services


async def _verify_service(service: ServiceInfo, timeout: float = 2.0) -> ServiceInfo:
    """
    Verify a service is responding and gather details.
    
    Tries common health check endpoints.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Service-specific verification
            if service.type == "ollama":
                return await _verify_ollama(service, client)
            elif service.type == "llamafarm":
                return await _verify_llamafarm(service, client)
            elif service.type == "universal-runtime":
                return await _verify_universal_runtime(service, client)
            elif service.type == "qdrant":
                return await _verify_qdrant(service, client)
            else:
                return await _verify_generic_http(service, client)
                
    except Exception as e:
        logger.debug(f"Service verification failed for {service.name}: {e}")
        return service


async def _verify_ollama(service: ServiceInfo, client: httpx.AsyncClient) -> ServiceInfo:
    """Verify Ollama service and get model count."""
    try:
        response = await client.get(f"{service.endpoint}/api/tags")
        if response.status_code == 200:
            data = response.json()
            model_count = len(data.get("models", []))
            service.healthy = True
            service.details = {"model_count": model_count}
        
        # Get version
        try:
            version_response = await client.get(f"{service.endpoint}/api/version")
            if version_response.status_code == 200:
                service.version = version_response.json().get("version")
        except Exception:
            pass
            
    except Exception:
        pass
    
    return service


async def _verify_llamafarm(service: ServiceInfo, client: httpx.AsyncClient) -> ServiceInfo:
    """Verify LlamaFarm service."""
    try:
        response = await client.get(f"{service.endpoint}/health")
        if response.status_code == 200:
            service.healthy = True
        else:
            # Try v1 models as fallback
            response = await client.get(f"{service.endpoint}/v1/models")
            if response.status_code == 200:
                service.healthy = True
                data = response.json()
                model_count = len(data.get("data", []))
                service.details = {"model_count": model_count}
    except Exception:
        pass
    
    return service


async def _verify_universal_runtime(service: ServiceInfo, client: httpx.AsyncClient) -> ServiceInfo:
    """Verify Universal Runtime service."""
    try:
        response = await client.get(f"{service.endpoint}/health")
        if response.status_code == 200:
            service.healthy = True
            service.details = response.json()
    except Exception:
        pass
    
    return service


async def _verify_qdrant(service: ServiceInfo, client: httpx.AsyncClient) -> ServiceInfo:
    """Verify Qdrant vector database."""
    try:
        response = await client.get(f"{service.endpoint}/collections")
        if response.status_code == 200:
            service.healthy = True
            data = response.json()
            collection_count = len(data.get("result", {}).get("collections", []))
            service.details = {"collection_count": collection_count}
    except Exception:
        pass
    
    return service


async def _verify_generic_http(service: ServiceInfo, client: httpx.AsyncClient) -> ServiceInfo:
    """Verify generic HTTP service."""
    health_endpoints = ["/health", "/healthz", "/api/health", "/"]
    
    for endpoint in health_endpoints:
        try:
            response = await client.get(f"{service.endpoint}{endpoint}")
            if response.status_code < 500:
                service.healthy = True
                return service
        except Exception:
            continue
    
    return service


def get_services_summary(services: List[ServiceInfo]) -> str:
    """Generate a human-readable summary of detected services."""
    if not services:
        return "No services detected"
    
    lines = []
    
    for service in sorted(services, key=lambda s: s.port):
        status = "✓" if service.healthy else "?"
        
        details = []
        if service.version:
            details.append(f"v{service.version}")
        if service.details:
            if "model_count" in service.details:
                details.append(f"{service.details['model_count']} models")
            if "collection_count" in service.details:
                details.append(f"{service.details['collection_count']} collections")
        
        detail_str = f" ({', '.join(details)})" if details else ""
        lines.append(f"  {status} {service.name}: {service.endpoint}{detail_str}")
    
    return "\n".join(lines)
