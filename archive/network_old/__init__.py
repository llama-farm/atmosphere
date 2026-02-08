# Transport layer - simplified
# Only ip_detect for local address discovery

from .ip_detect import (
    get_best_local_ip,
    get_all_local_ips,
    EndpointRegistry,
    EndpointInfo,
)

__all__ = [
    "get_best_local_ip",
    "get_all_local_ips", 
    "EndpointRegistry",
    "EndpointInfo",
]
