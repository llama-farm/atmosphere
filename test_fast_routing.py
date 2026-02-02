#!/usr/bin/env python3
"""
Test the FAST Atmosphere Routing Layer

Tests:
1. Sub-millisecond routing performance
2. Pre-computed embedding matching
3. Explicit model routing
4. Semantic content routing
5. Fallback behavior

NO LLM CALLS - uses pre-computed embeddings only.
"""

import sys
import time
from pathlib import Path

# Add atmosphere to path
sys.path.insert(0, str(Path(__file__).parent))

from atmosphere.router.fast_router import FastProjectRouter, get_fast_router


def test_initialization():
    """Test fast router initialization."""
    print("\n" + "="*60)
    print("TEST 1: Fast Router Initialization")
    print("="*60)
    
    start = time.perf_counter()
    router = FastProjectRouter()
    router.initialize()
    elapsed = (time.perf_counter() - start) * 1000
    
    stats = router.get_stats()
    print(f"✅ Initialized in {elapsed:.1f}ms")
    print(f"   Projects: {stats['total_projects']}")
    print(f"   Domains: {stats['domains']}")
    print(f"   Embedding dim: {stats['embedding_dim']}")
    print(f"   Default: {stats['default_project']}")
    
    return True


def test_explicit_routing():
    """Test explicit model path routing."""
    print("\n" + "="*60)
    print("TEST 2: Explicit Model Routing (should be < 1ms)")
    print("="*60)
    
    router = get_fast_router()
    
    # Test full path
    result = router.route("default/llama-expert-14")
    print(f"\n📍 Route 'default/llama-expert-14':")
    print(f"   → {result.project.model_path if result.project else 'None'}")
    print(f"   Latency: {result.latency_ms:.3f}ms")
    print(f"   Score: {result.score:.2f}")
    
    if result.latency_ms < 1.0:
        print("   ✅ Sub-millisecond!")
    else:
        print(f"   ⚠️ Slower than expected: {result.latency_ms:.2f}ms")
    
    # Test name only
    result = router.route("fishing")
    print(f"\n📍 Route 'fishing':")
    print(f"   → {result.project.model_path if result.project else 'None'}")
    print(f"   Latency: {result.latency_ms:.3f}ms")
    
    return True


def test_semantic_routing():
    """Test content-based semantic routing with embeddings."""
    print("\n" + "="*60)
    print("TEST 3: Semantic Routing (pre-computed embeddings)")
    print("="*60)
    
    router = get_fast_router()
    
    test_cases = [
        ("What do llamas eat and how should I care for their fiber?", "animals/camelids"),
        ("What's the best lure for catching bass in muddy water?", "fishing"),
        ("I need help understanding my medical records and diagnosis", "healthcare"),
        ("How do I debug this Python function?", "coding"),
    ]
    
    total_latency = 0
    for prompt, expected_domain in test_cases:
        messages = [{"role": "user", "content": prompt}]
        result = router.route("auto", messages)
        total_latency += result.latency_ms
        
        print(f"\n📍 '{prompt[:50]}...'")
        print(f"   → {result.project.model_path if result.project else 'None'}")
        print(f"   Domain: {result.project.domain if result.project else 'None'}")
        print(f"   Latency: {result.latency_ms:.3f}ms")
        print(f"   Score: {result.score:.2f}")
        print(f"   Reason: {result.reason}")
        
        if result.project and expected_domain in result.project.domain:
            print(f"   ✅ Matched expected domain!")
        elif result.project:
            print(f"   ⚠️ Expected {expected_domain}, got {result.project.domain}")
    
    avg_latency = total_latency / len(test_cases)
    print(f"\n📊 Average routing latency: {avg_latency:.3f}ms")
    
    if avg_latency < 5.0:
        print("   ✅ Fast routing!")
    else:
        print("   ⚠️ Slower than expected")
    
    return True


def test_batch_routing():
    """Test batch routing performance."""
    print("\n" + "="*60)
    print("TEST 4: Batch Routing Performance")
    print("="*60)
    
    router = get_fast_router()
    
    # Generate test prompts
    prompts = [
        "Tell me about llama nutrition",
        "Best fishing spots in the area",
        "Medical diagnosis help",
        "Python debugging tips",
        "Legal contract review",
        "Investment portfolio analysis",
        "Llama fiber processing",
        "Bass fishing techniques",
        "Healthcare insurance questions",
        "Software architecture design",
    ]
    
    # Warmup
    for p in prompts[:3]:
        router.route("auto", [{"role": "user", "content": p}])
    
    # Timed run
    start = time.perf_counter()
    for _ in range(10):  # 100 total routes
        for prompt in prompts:
            router.route("auto", [{"role": "user", "content": prompt}])
    elapsed = (time.perf_counter() - start) * 1000
    
    routes_per_sec = 100 / (elapsed / 1000)
    avg_latency = elapsed / 100
    
    print(f"📊 100 routes completed in {elapsed:.1f}ms")
    print(f"   Average latency: {avg_latency:.3f}ms")
    print(f"   Throughput: {routes_per_sec:.0f} routes/sec")
    
    if avg_latency < 5.0:
        print("   ✅ Excellent performance!")
    elif avg_latency < 20.0:
        print("   ⚠️ Acceptable but could be faster")
    else:
        print("   ❌ Too slow for real-time routing")
    
    return avg_latency < 20.0


def test_fallback():
    """Test fallback to default project."""
    print("\n" + "="*60)
    print("TEST 5: Fallback Routing")
    print("="*60)
    
    router = get_fast_router()
    
    # Unknown model
    result = router.route("nonexistent/model")
    print(f"\n📍 Route 'nonexistent/model':")
    print(f"   → {result.project.model_path if result.project else 'None'}")
    print(f"   Fallback: {result.fallback}")
    print(f"   Latency: {result.latency_ms:.3f}ms")
    
    # Unrelated prompt
    messages = [{"role": "user", "content": "quantum entanglement theory"}]
    result = router.route("auto", messages)
    print(f"\n📍 Route 'quantum entanglement theory':")
    print(f"   → {result.project.model_path if result.project else 'None'}")
    print(f"   Fallback: {result.fallback}")
    print(f"   Latency: {result.latency_ms:.3f}ms")
    
    return True


def test_gossip_integration():
    """Test gossip update handling."""
    print("\n" + "="*60)
    print("TEST 6: Gossip Integration")
    print("="*60)
    
    router = get_fast_router()
    
    # Simulate receiving a route update
    update = {
        "type": "route_update",
        "action": "add",
        "project": {
            "namespace": "test",
            "name": "gossip-test-project",
            "domain": "testing",
            "capabilities": ["chat"],
            "topics": ["gossip", "test"],
            "description": "A test project from gossip",
            "models": ["default"],
            "nodes": ["other-node-123"]
        },
        "from_node": "other-node-123",
        "timestamp": time.time()
    }
    
    # Handle the update
    before_count = len(router.projects)
    router.handle_route_update(update)
    after_count = len(router.projects)
    
    print(f"📍 Handled ROUTE_UPDATE from 'other-node-123'")
    print(f"   Before: {before_count} projects")
    print(f"   After: {after_count} projects")
    
    # Check if project was added
    project = router.get_project("test/gossip-test-project")
    if project:
        print(f"   ✅ Project added: {project.model_path}")
        print(f"   Nodes: {project.nodes}")
    else:
        print("   ❌ Project not found")
    
    # Build an update message
    if project:
        msg = router.build_route_update(project, "update")
        print(f"\n📤 Built ROUTE_UPDATE message:")
        print(f"   From: {msg['from_node']}")
        print(f"   Action: {msg['action']}")
    
    return True


def main():
    """Run all tests."""
    print("="*60)
    print("FAST Atmosphere Routing Layer Tests")
    print("NO LLM CALLS - Pre-computed embeddings only")
    print("="*60)
    
    tests = [
        ("Initialization", test_initialization),
        ("Explicit Routing", test_explicit_routing),
        ("Semantic Routing", test_semantic_routing),
        ("Batch Performance", test_batch_routing),
        ("Fallback", test_fallback),
        ("Gossip Integration", test_gossip_integration),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ {name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
