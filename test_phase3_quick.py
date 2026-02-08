#!/usr/bin/env python3
"""Quick test to verify Phase 3 components work."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from atmosphere.router.matcher import CascadeMatcher, MatchMethod
from atmosphere.router.scorer import RouteCandidate, CompositeScorer, create_candidate
from atmosphere.router.constraints import RouteConstraints, filter_candidates
from atmosphere.router.semantic import SemanticRouter


async def test_matcher():
    """Test cascade matcher."""
    print("Testing CascadeMatcher...")
    
    matcher = CascadeMatcher()
    
    # Add capability
    matcher.add_capability(
        cap_id="test:llm",
        label="llm",
        description="Language model for text generation and conversation",
    )
    
    # Match intent
    result, _ = matcher.match("Generate some text for me")
    
    assert result is not None, "Matcher should find a match"
    assert result.capability_id == "test:llm"
    print(f"✓ Matcher found: {result.capability_label} (method={result.method.value}, score={result.score:.2f})")


def test_scorer():
    """Test composite scorer."""
    print("Testing CompositeScorer...")
    
    # Create candidate
    candidate = create_candidate(
        capability_id="test:llm",
        capability_label="llm",
        node_id="node-test",
        is_local=True,
        semantic_score=0.85,
        estimated_latency_ms=1.0,
        hops=0,
        model_info={"has_rag": True, "size": "small"},
    )
    
    # Compute capability score
    scorer = CompositeScorer()
    scorer.compute_capability_score(
        candidate,
        intent_classification={
            "task_type": "qa",
            "recommended_model_size": "small",
        }
    )
    
    # Check composite score
    composite = candidate.composite_score
    assert 0 <= composite <= 1, f"Composite score should be 0-1, got {composite}"
    
    explanation = candidate.explain()
    print(f"✓ Composite score: {composite:.3f}")
    print(f"  {explanation}")


def test_constraints():
    """Test constraint filtering."""
    print("Testing RouteConstraints...")
    
    # Create candidates
    candidates = [
        create_candidate("c1", "fast-local", "node-1", True, 0.9, 1.0, 0),
        create_candidate("c2", "slow-remote", "node-2", False, 0.8, 500, 2),
        create_candidate("c3", "medium-remote", "node-3", False, 0.85, 100, 1),
    ]
    
    # Filter with latency constraint
    constraints = RouteConstraints(max_latency_ms=200)
    filtered = filter_candidates(candidates, constraints)
    
    assert len(filtered) == 2, f"Should filter to 2 candidates, got {len(filtered)}"
    print(f"✓ Filtered {len(candidates)} → {len(filtered)} candidates")


async def test_semantic_router():
    """Test semantic router."""
    print("Testing SemanticRouter...")
    
    router = SemanticRouter(node_id="test-node")
    await router.initialize()
    
    # Register capability
    await router.register_capability(
        label="test-llm",
        description="Test language model",
    )
    
    # Route intent
    result = await router.route("Test intent")
    
    assert result.matched, "Router should find a match"
    print(f"✓ Router matched: {result.capability_label} (score={result.composite_score:.3f})")
    
    # Get stats
    stats = router.stats()
    assert stats["local_capabilities"] == 1
    print(f"✓ Router stats: {stats['local_capabilities']} local, {stats['total_capabilities']} total")
    
    await router.close()


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 3 Quick Test")
    print("=" * 60)
    print()
    
    try:
        await test_matcher()
        print()
        
        test_scorer()
        print()
        
        test_constraints()
        print()
        
        await test_semantic_router()
        print()
        
        print("=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
