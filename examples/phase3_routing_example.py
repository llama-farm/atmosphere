#!/usr/bin/env python3
"""
Phase 3 Routing Example - Detailed Routing Decision Log

This example demonstrates the refactored semantic router with:
1. Unified gradient table for ALL capabilities (local + remote)
2. 3-tier cascade matching (embedding → hash → keyword)
3. Composite scoring (semantic + latency + capability + hop + cost)
4. Constraint filtering
5. Detailed logging showing WHY a route was chosen

Run this to see the complete routing decision pipeline in action.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from atmosphere.router.semantic import SemanticRouter
from atmosphere.router.constraints import (
    RouteConstraints,
    create_fast_route_constraint,
    create_rag_constraint,
)

# Configure logging to show all details
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s [%(name)s] %(message)s',
)

# Silence some noisy loggers
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)


async def main():
    """Demonstrate Phase 3 routing with detailed logging."""
    
    print("=" * 80)
    print("PHASE 3 SEMANTIC ROUTER - EXAMPLE ROUTING DECISIONS")
    print("=" * 80)
    print()
    
    # === SETUP: Create router ===
    print("📝 Setting up semantic router...")
    router = SemanticRouter(
        node_id="node-laptop-001",
        model_info_fn=get_model_info,  # Provide model metadata
        peer_reachability_fn=lambda node: node != "node-offline-999",
    )
    
    await router.initialize()
    print(f"✓ Router initialized (embeddings: {router._embedding_available})")
    print()
    
    # === REGISTER LOCAL CAPABILITIES ===
    print("📝 Registering local capabilities...")
    
    await router.register_capability(
        label="llm-general",
        description="General purpose language model for conversation, writing, and reasoning tasks",
        handler="llamafarm/qwen",
        models=["Qwen3-1.7B"],
        has_rag=False,
        model_size="small",
        specializations=["general", "conversation"],
    )
    
    await router.register_capability(
        label="llm-code",
        description="Specialized code generation and analysis model for Python, JavaScript, and other languages",
        handler="llamafarm/codellama",
        models=["CodeLlama-7B"],
        has_rag=True,
        model_size="medium",
        specializations=["code", "programming", "software"],
    )
    
    await router.register_capability(
        label="embedding",
        description="Text embedding model for semantic search and similarity",
        handler="llamafarm/minilm",
        models=["all-MiniLM-L6-v2"],
        has_rag=False,
        model_size="tiny",
        specializations=["embedding", "search"],
    )
    
    print()
    
    # === SIMULATE REMOTE CAPABILITIES ===
    print("📝 Simulating remote capabilities from gossip...")
    
    # Remote llama expert (2 hops away)
    import numpy as np
    await router.update_remote_capability(
        capability_id="node-desktop-002:llama-expert",
        capability_label="llama-expert",
        capability_vector=np.random.randn(384).astype(np.float32),
        hops=2,
        next_hop="node-relay-001",
        via_node="node-desktop-002",
        estimated_latency_ms=150,
    )
    
    # Remote RAG-enabled model (1 hop)
    await router.update_remote_capability(
        capability_id="node-server-003:llm-rag",
        capability_label="llm-rag",
        capability_vector=np.random.randn(384).astype(np.float32),
        hops=1,
        next_hop="node-server-003",
        via_node="node-server-003",
        estimated_latency_ms=50,
    )
    
    print("✓ Registered 3 local + 2 remote capabilities")
    print()
    
    # === ROUTING EXAMPLES ===
    print("=" * 80)
    print("ROUTING EXAMPLES")
    print("=" * 80)
    print()
    
    # Example 1: Simple conversation (should match local general LLM)
    print("─" * 80)
    print("📍 EXAMPLE 1: Simple Conversation")
    print("─" * 80)
    intent1 = "What's the capital of France?"
    print(f"Intent: {intent1}")
    print()
    
    result1 = await router.route(intent1)
    print_result(result1)
    print()
    
    # Example 2: Code generation (should match local code LLM)
    print("─" * 80)
    print("📍 EXAMPLE 2: Code Generation")
    print("─" * 80)
    intent2 = "Write a Python function to calculate fibonacci numbers"
    print(f"Intent: {intent2}")
    print()
    
    result2 = await router.route(intent2)
    print_result(result2)
    print()
    
    # Example 3: With fast route constraint (prefer local)
    print("─" * 80)
    print("📍 EXAMPLE 3: Fast Route Constraint")
    print("─" * 80)
    intent3 = "Summarize this article about machine learning"
    constraints3 = create_fast_route_constraint(max_latency_ms=100, max_hops=0)
    print(f"Intent: {intent3}")
    print(f"Constraints: max_latency=100ms, max_hops=0, prefer_local=True")
    print()
    
    result3 = await router.route(intent3, constraints=constraints3)
    print_result(result3)
    print()
    
    # Example 4: With RAG constraint
    print("─" * 80)
    print("📍 EXAMPLE 4: RAG Required")
    print("─" * 80)
    intent4 = "What are the latest updates to the Python documentation?"
    constraints4 = create_rag_constraint(require_rag=True)
    print(f"Intent: {intent4}")
    print(f"Constraints: require_rag=True")
    print()
    
    result4 = await router.route(intent4, constraints=constraints4)
    print_result(result4)
    print()
    
    # Example 5: Custom constraints (prefer small models, low latency)
    print("─" * 80)
    print("📍 EXAMPLE 5: Custom Constraints (Small Models + Low Latency)")
    print("─" * 80)
    intent5 = "Translate 'hello world' to Spanish"
    constraints5 = RouteConstraints(
        max_latency_ms=50,
        model_size_max="small",
        prefer_local=True,
    )
    print(f"Intent: {intent5}")
    print(f"Constraints: max_latency=50ms, model_size_max=small, prefer_local=True")
    print()
    
    result5 = await router.route(intent5, constraints=constraints5)
    print_result(result5)
    print()
    
    # === STATISTICS ===
    print("=" * 80)
    print("ROUTER STATISTICS")
    print("=" * 80)
    stats = router.stats()
    print(f"Node ID: {stats['node_id']}")
    print(f"Embedding Available: {stats['embedding_available']}")
    print(f"Local Capabilities: {stats['local_capabilities']}")
    print(f"Total Capabilities: {stats['total_capabilities']}")
    print(f"Gradient Stats: {stats['gradient_stats']}")
    print()
    
    # === CLEANUP ===
    await router.close()
    print("✓ Router closed")


def get_model_info(capability_id: str) -> dict:
    """Mock function to provide model metadata for scoring."""
    
    # Parse capability ID
    if "llm-general" in capability_id:
        return {
            "handler": "llamafarm/qwen",
            "models": ["Qwen3-1.7B"],
            "has_rag": False,
            "size": "small",
            "specializations": ["general", "conversation"],
        }
    elif "llm-code" in capability_id:
        return {
            "handler": "llamafarm/codellama",
            "models": ["CodeLlama-7B"],
            "has_rag": True,
            "size": "medium",
            "specializations": ["code", "programming", "software"],
        }
    elif "embedding" in capability_id:
        return {
            "handler": "llamafarm/minilm",
            "models": ["all-MiniLM-L6-v2"],
            "has_rag": False,
            "size": "tiny",
            "specializations": ["embedding", "search"],
        }
    elif "llama-expert" in capability_id:
        return {
            "handler": "remote/ollama",
            "models": ["Llama-3-8B"],
            "has_rag": True,
            "size": "medium",
            "specializations": ["llama", "alpaca", "animals"],
        }
    elif "llm-rag" in capability_id:
        return {
            "handler": "remote/rag-service",
            "models": ["Unknown"],
            "has_rag": True,
            "size": "large",
            "specializations": ["knowledge", "qa"],
        }
    
    return {}


def print_result(result):
    """Pretty print a routing result."""
    if result.action.value == "no_match":
        print("❌ NO MATCH")
        print(f"   Reason: {result.reason}")
        return
    
    print(f"✅ MATCHED: {result.capability_label}")
    print(f"   Node: {result.node_id}")
    print(f"   Action: {result.action.value}")
    print(f"   Match Method: {result.match_method.value}")
    print(f"   Semantic Score: {result.semantic_score:.3f}")
    print(f"   Composite Score: {result.composite_score:.3f}")
    
    if result.score_breakdown:
        print(f"   Score Breakdown:")
        for factor, score in result.score_breakdown.items():
            print(f"     {factor}: {score:.3f}")
    
    print(f"   Latency: {result.estimated_latency_ms:.0f}ms")
    print(f"   Hops: {result.hops}")
    print(f"   Local: {result.is_local}")
    
    if result.intent_classification:
        ic = result.intent_classification
        print(f"   Intent: {ic['complexity']} ({ic['task_type']}) → {ic['recommended_model_size']}")
    
    print(f"   📋 {result.reason}")


if __name__ == "__main__":
    asyncio.run(main())
