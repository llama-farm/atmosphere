#!/usr/bin/env python3
"""
Multi-Hop Routing Demo

Demonstrates semantic routing across multiple hops:

     [Node A: LLM]
          |
     [Node B: Router]
          |
     [Node C: Vision]

When a "vision" intent arrives at Node B, it routes to Node C.
When an "LLM" intent arrives at Node B, it routes to Node A.

This shows how Atmosphere automatically discovers and routes
to the best capability without centralized coordination.

Usage:
    python examples/multi_hop_demo.py
"""

import asyncio
import logging
import numpy as np

from atmosphere.router.gradient import GradientTable
from atmosphere.router.semantic import SemanticRouter, RouteAction, Capability
from atmosphere.router.embeddings import EmbeddingEngine

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def simulate_gossip(
    node_a_caps: list,
    node_c_caps: list,
    node_b_table: GradientTable,
    embedding_engine: EmbeddingEngine
):
    """Simulate gossip protocol populating Node B's gradient table."""
    
    # Node A advertises LLM capability
    for cap in node_a_caps:
        vec = await embedding_engine.embed(cap["description"])
        node_b_table.update(
            capability_id=f"node-a:{cap['label']}",
            capability_label=cap["label"],
            capability_vector=vec,
            hops=1,
            next_hop="node-a:11434",
            via_node="node-a"
        )
    
    # Node C advertises Vision capability
    for cap in node_c_caps:
        vec = await embedding_engine.embed(cap["description"])
        node_b_table.update(
            capability_id=f"node-c:{cap['label']}",
            capability_label=cap["label"],
            capability_vector=vec,
            hops=1,
            next_hop="node-c:11436",
            via_node="node-c"
        )


async def main():
    print("\n" + "="*60)
    print("    🌐 Atmosphere Multi-Hop Routing Demo")
    print("="*60 + "\n")
    
    # Initialize embedding engine
    print("Initializing embedding engine...")
    engine = EmbeddingEngine()
    try:
        await engine.initialize()
    except RuntimeError as e:
        print(f"\n❌ {e}")
        print("\nPlease install Ollama and run:")
        print("  ollama pull nomic-embed-text")
        return
    
    print(f"✓ Using {engine.backend} backend\n")
    
    # Define capabilities for each node
    node_a_caps = [
        {
            "label": "llm",
            "description": "Language model for text generation, summarization, and analysis"
        }
    ]
    
    node_c_caps = [
        {
            "label": "vision",
            "description": "Vision model for image analysis and object detection"
        }
    ]
    
    # Node B is the router - has no local capabilities
    node_b = SemanticRouter(node_id="node-b")
    node_b.embedding_engine = engine  # Share the engine
    node_b._initialized = True
    
    # Simulate gossip protocol
    print("Simulating gossip protocol...")
    await simulate_gossip(node_a_caps, node_c_caps, node_b.gradient_table, engine)
    
    print(f"✓ Gradient table has {len(node_b.gradient_table)} entries\n")
    
    # Test routing various intents
    test_intents = [
        "summarize this document",
        "analyze this image for objects",
        "generate code to sort a list",
        "describe what's in this photo",
        "write a haiku about nature",
        "detect faces in the image",
    ]
    
    print("="*60)
    print("  Routing Test")
    print("="*60 + "\n")
    
    for intent in test_intents:
        result = await node_b.route(intent)
        
        if result.action == RouteAction.FORWARD:
            print(f"Intent: \"{intent}\"")
            print(f"  → Route to: {result.next_hop}")
            print(f"    Score: {result.score:.3f}, Hops: {result.hops}")
            print()
        elif result.action == RouteAction.NO_MATCH:
            print(f"Intent: \"{intent}\"")
            print(f"  ✗ No match (score: {result.score:.3f})")
            print()
    
    # Show gradient table stats
    stats = node_b.gradient_table.stats()
    print("="*60)
    print("  Gradient Table Stats")
    print("="*60)
    print(f"  Entries: {stats['size']}")
    print(f"  Avg hops: {stats['avg_hops']:.1f}")
    print(f"  Unique next hops: {stats['unique_next_hops']}")
    print()
    
    await engine.close()
    print("Demo complete!\n")


if __name__ == "__main__":
    asyncio.run(main())
