#!/usr/bin/env python3
"""
Two Node Mesh Demo

Demonstrates setting up a simple two-node mesh:
1. Node A creates a mesh and becomes a founder
2. Node B joins the mesh using the join code
3. Both nodes can route intents to each other

Usage:
    # Terminal 1 - Start Node A (founder)
    python examples/two_node_mesh.py --role founder --port 11434

    # Terminal 2 - Start Node B (joiner)
    python examples/two_node_mesh.py --role joiner --port 11435 --join-target localhost:11434
"""

import argparse
import asyncio
import logging
import sys

from atmosphere.config import Config, DEFAULT_DATA_DIR
from atmosphere.mesh.node import Node, NodeIdentity, MeshIdentity
from atmosphere.mesh.join import MeshJoin, generate_join_code
from atmosphere.router.semantic import SemanticRouter
from atmosphere.api.server import AtmosphereServer, create_app

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def run_founder(port: int, mesh_name: str):
    """Run a founder node that creates a mesh."""
    logger.info(f"Starting founder node on port {port}")
    
    # Create node with mesh
    node = Node.create_with_mesh(
        node_name=f"founder-{port}",
        mesh_name=mesh_name
    )
    
    logger.info(f"Created mesh: {node.mesh.name} ({node.mesh.mesh_id})")
    logger.info(f"Node ID: {node.node_id}")
    
    # Generate join code
    join_code = generate_join_code(
        mesh=node.mesh,
        endpoint=f"localhost:{port}"
    )
    
    logger.info(f"Join code: {join_code.code}")
    logger.info(f"Full join info: {join_code.to_compact()[:80]}...")
    
    # Initialize router
    router = SemanticRouter(node_id=node.node_id)
    await router.initialize()
    
    # Register capabilities
    await router.register_capability(
        label="llm",
        description="Language model for text generation",
        handler="ollama"
    )
    
    logger.info(f"Registered {len(router.local_capabilities)} capabilities")
    
    # Start API server
    import uvicorn
    config = Config()
    config.server.port = port
    
    app = create_app(config)
    
    logger.info(f"Founder node ready at http://localhost:{port}")
    logger.info("Share this join info with other nodes:")
    logger.info(f"  atmosphere mesh join localhost:{port}")
    
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning"))
    await server.serve()


async def run_joiner(port: int, join_target: str):
    """Run a joiner node that connects to an existing mesh."""
    logger.info(f"Starting joiner node on port {port}")
    
    # Create standalone node
    identity = NodeIdentity.generate(f"joiner-{port}")
    logger.info(f"Node ID: {identity.node_id}")
    
    # Join the mesh
    join = MeshJoin(identity)
    
    logger.info(f"Joining mesh at {join_target}...")
    success, message, token = await join.join_by_endpoint(join_target)
    await join.close()
    
    if not success:
        logger.error(f"Failed to join: {message}")
        sys.exit(1)
    
    logger.info(f"Joined mesh: {token.mesh_name}")
    logger.info(f"Token expires in {token.time_remaining // 3600}h")
    
    # Create node with mesh info
    mesh_data = {
        "mesh_id": token.mesh_id,
        "name": token.mesh_name,
        "master_public_key": token.mesh_public_key,
        "threshold": 1,
        "total_shares": 1,
        "founding_members": []
    }
    mesh = MeshIdentity.from_dict(mesh_data)
    
    node = Node(identity=identity, mesh=mesh)
    
    # Initialize router
    router = SemanticRouter(node_id=node.node_id)
    await router.initialize()
    
    # Register different capabilities
    await router.register_capability(
        label="embeddings",
        description="Text embeddings for semantic search",
        handler="ollama"
    )
    
    logger.info(f"Registered {len(router.local_capabilities)} capabilities")
    
    # Start API server
    import uvicorn
    config = Config()
    config.server.port = port
    
    app = create_app(config)
    
    logger.info(f"Joiner node ready at http://localhost:{port}")
    
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning"))
    await server.serve()


async def main():
    parser = argparse.ArgumentParser(description="Two Node Mesh Demo")
    parser.add_argument("--role", choices=["founder", "joiner"], required=True)
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--mesh-name", default="demo-mesh")
    parser.add_argument("--join-target", help="Target for joiner (host:port)")
    
    args = parser.parse_args()
    
    if args.role == "founder":
        await run_founder(args.port, args.mesh_name)
    else:
        if not args.join_target:
            print("--join-target required for joiner role")
            sys.exit(1)
        await run_joiner(args.port, args.join_target)


if __name__ == "__main__":
    asyncio.run(main())
