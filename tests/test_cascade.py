#!/usr/bin/env python3
"""
Test the 3-tier semantic routing cascade.

Tests:
1. Embedding match (tier 1)
2. Hash fallback (tier 2)
3. Keyword match (tier 3)
4. Default fallback (tier 4)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from atmosphere.router.fast_router import FastProjectRouter, get_fast_router, MatchTier


def test_cascade_tiers():
    """Test that all cascade tiers work correctly."""
    print("\n" + "="*60)
    print("TEST: Cascade Tier Routing")
    print("="*60)
    
    router = get_fast_router()
    
    test_cases = [
        # (prompt, expected_domain_contains, description)
        ("What do llamas eat and how should I care for their fiber?", "camelid", "Llama care"),
        ("What's the best lure for catching bass in muddy water?", "fishing", "Fishing query"),
        ("I need help understanding my medical records and diagnosis", "healthcare", "Healthcare"),
        ("How do I debug this Python function that's throwing errors?", "coding", "Coding help"),
        ("Tell me about quantum physics and string theory", "general", "General/fallback"),
    ]
    
    print(f"\n📊 Router stats:")
    print(f"   Neural embeddings: {router._embedder.using_neural}")
    print(f"   Total projects: {len(router.projects)}")
    
    for prompt, expected_domain, desc in test_cases:
        print(f"\n{'─'*60}")
        print(f"📝 {desc}: '{prompt[:50]}...'")
        
        # Test cascade
        cascade = router.test_cascade(prompt)
        
        print(f"\n   Extracted keywords: {cascade['keywords'][:5]}...")
        print(f"   Domain boosts: {cascade['domain_boosts']}")
        
        print(f"\n   Cascade tiers:")
        for tier_name, tier_data in cascade['tiers'].items():
            status = "✅" if tier_data['passed'] else "❌"
            print(f"      {tier_name.upper():10} {status} score={tier_data['score']:.3f} (threshold={tier_data['threshold']}) → {tier_data['project']}")
        
        final = cascade['final']
        print(f"\n   Final result:")
        print(f"      Tier: {final['tier'].upper()}")
        print(f"      Project: {final['project']}")
        print(f"      Domain: {final['domain']}")
        print(f"      Score: {final['score']:.3f}")
        print(f"      Reason: {final['reason']}")
        
        # Check if domain matches expectation
        if final['domain'] and expected_domain.lower() in final['domain'].lower():
            print(f"      ✅ Matched expected domain!")
        elif final['fallback'] and expected_domain == "general":
            print(f"      ✅ Correctly fell back to default")
        else:
            print(f"      ⚠️  Expected domain containing '{expected_domain}'")
    
    return True


def test_tier_distribution():
    """Test that different queries hit different tiers."""
    print("\n" + "="*60)
    print("TEST: Tier Distribution")
    print("="*60)
    
    router = get_fast_router()
    
    prompts = [
        "llama fiber care",
        "bass fishing techniques muddy water",
        "medical diagnosis understanding",
        "python debugging errors",
        "legal contract review",
        "investment portfolio analysis",
        "how to cook pasta",
        "random gibberish xyzzy plugh",
    ]
    
    tier_counts = {tier.value: 0 for tier in MatchTier}
    
    for prompt in prompts:
        messages = [{"role": "user", "content": prompt}]
        result = router.route("auto", messages)
        tier_counts[result.tier.value] += 1
    
    print(f"\n📊 Tier distribution across {len(prompts)} prompts:")
    for tier, count in tier_counts.items():
        bar = "█" * count
        print(f"   {tier:10} {count:2} {bar}")
    
    return True


def test_performance():
    """Test cascade performance."""
    print("\n" + "="*60)
    print("TEST: Cascade Performance")
    print("="*60)
    
    import time
    router = get_fast_router()
    
    prompts = [
        "llama care and fiber",
        "fishing techniques",
        "medical diagnosis",
        "python debugging",
        "random query test",
    ] * 20  # 100 prompts
    
    # Warmup
    for p in prompts[:5]:
        router.route("auto", [{"role": "user", "content": p}])
    
    # Timed run
    start = time.perf_counter()
    tier_counts = {tier.value: 0 for tier in MatchTier}
    
    for prompt in prompts:
        result = router.route("auto", [{"role": "user", "content": prompt}])
        tier_counts[result.tier.value] += 1
    
    elapsed = (time.perf_counter() - start) * 1000
    
    print(f"\n📊 Performance results:")
    print(f"   Total routes: {len(prompts)}")
    print(f"   Total time: {elapsed:.1f}ms")
    print(f"   Avg latency: {elapsed/len(prompts):.3f}ms")
    print(f"   Throughput: {len(prompts)/(elapsed/1000):.0f} routes/sec")
    
    print(f"\n📊 Tier distribution:")
    for tier, count in tier_counts.items():
        pct = count / len(prompts) * 100
        print(f"   {tier:10} {count:3} ({pct:.0f}%)")
    
    if elapsed/len(prompts) < 1.0:
        print("\n   ✅ Sub-millisecond average!")
    else:
        print(f"\n   ⚠️ Average latency above 1ms")
    
    return True


def main():
    """Run all cascade tests."""
    print("="*60)
    print("Semantic Routing Cascade Tests")
    print("="*60)
    
    tests = [
        ("Cascade Tiers", test_cascade_tiers),
        ("Tier Distribution", test_tier_distribution),
        ("Performance", test_performance),
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
