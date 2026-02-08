"""
LlamaFarm Integration for Atmosphere

Auto-discovers capabilities from LlamaFarm projects and converts them
to CapabilityAnnouncement objects for mesh routing.

Only projects in the 'discoverable' namespace are exposed to the mesh.
"""

import logging
from typing import List, Optional

from ..core.capability import CapabilityAnnouncement, ModelTier
from ..cost.collector import NodeCostFactors
from ..discovery.llamafarm import LlamaFarmBackend, LlamaFarmConfig

logger = logging.getLogger(__name__)


async def discover_llamafarm_capabilities(
    node_id: str,
    node_name: str,
    llamafarm_url: str = "http://localhost:14345",
    cost_factors: Optional[NodeCostFactors] = None,
) -> List[CapabilityAnnouncement]:
    """
    Discover all capabilities from LlamaFarm's 'discoverable' namespace.
    
    Args:
        node_id: This node's ID (Ed25519 hash)
        node_name: Human-readable node name
        llamafarm_url: LlamaFarm server URL
        cost_factors: Optional cost factors for this node
        
    Returns:
        List of CapabilityAnnouncement objects, one per model in each project
    """
    announcements: List[CapabilityAnnouncement] = []
    
    # Parse URL to extract host/port
    from urllib.parse import urlparse
    parsed = urlparse(llamafarm_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 14345
    
    config = LlamaFarmConfig(host=host, port=port)
    backend = LlamaFarmBackend(config)
    
    try:
        # Check health
        healthy = await backend.health_check()
        if not healthy:
            logger.warning(f"LlamaFarm at {llamafarm_url} is not responding")
            return []
        
        logger.info(f"Discovering capabilities from LlamaFarm at {llamafarm_url}")
        
        # List projects in 'discoverable' namespace ONLY
        # These are the projects meant to be exposed to the mesh
        projects = await backend.list_discoverable_projects()
        
        if not projects:
            logger.info("No discoverable LlamaFarm projects found")
            return []
        
        logger.info(f"Found {len(projects)} discoverable projects")
        
        # For each project, extract capabilities
        for project_data in projects:
            try:
                namespace = project_data.get("namespace", "discoverable")
                project_name = project_data.get("name", "")
                config_data = project_data.get("config", {})
                
                if not project_name:
                    logger.warning(f"Project missing name: {project_data}")
                    continue
                
                # Use the Capability factory method to create announcements
                project_announcements = CapabilityAnnouncement.from_llamafarm_project(
                    node_id=node_id,
                    node_name=node_name,
                    namespace=namespace,
                    project_name=project_name,
                    project_config=config_data,
                    cost_factors=cost_factors,
                )
                
                announcements.extend(project_announcements)
                
                logger.info(
                    f"Registered {len(project_announcements)} capabilities "
                    f"from project '{namespace}/{project_name}'"
                )
                
            except Exception as e:
                logger.error(f"Failed to process project {project_data.get('name')}: {e}", exc_info=True)
                continue
        
        logger.info(f"Total capabilities discovered from LlamaFarm: {len(announcements)}")
        
    except Exception as e:
        logger.error(f"Failed to discover LlamaFarm capabilities: {e}", exc_info=True)
    
    finally:
        await backend.close()
    
    return announcements


async def test_discovery():
    """Test function for manual verification."""
    import asyncio
    
    # Mock node info
    node_id = "test-node-123"
    node_name = "Test Node"
    
    caps = await discover_llamafarm_capabilities(
        node_id=node_id,
        node_name=node_name,
    )
    
    print(f"\n=== Discovered {len(caps)} capabilities ===\n")
    
    for cap in caps:
        print(f"ID: {cap.capability_id}")
        print(f"  Project: {cap.project_path}")
        print(f"  Model: {cap.model_actual}")
        print(f"  Family: {cap.model_family}")
        print(f"  Tier: {cap.model_tier.value}")
        print(f"  Params: {cap.model_params_b}B")
        print(f"  Label: {cap.label}")
        print(f"  Keywords: {cap.keywords}")
        print(f"  Good for: {cap.good_for}")
        print(f"  Has RAG: {cap.has_rag}")
        print()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_discovery())
