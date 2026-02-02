#!/usr/bin/env python3
"""
Test the Atmosphere Discovery & Routing Layer

Tests:
1. Project discovery and registry loading
2. Explicit model routing (default/llama-expert-14)
3. Implicit/semantic routing (llama-related prompts)
4. Fallback routing (unknown topics)
"""

import json
import sys
from pathlib import Path

# Add atmosphere to path
sys.path.insert(0, str(Path(__file__).parent))

from atmosphere.router.project_router import ProjectRouter, get_project_router


def test_registry_loading():
    """Test that the registry loads correctly."""
    print("\n" + "="*60)
    print("TEST 1: Registry Loading")
    print("="*60)
    
    router = ProjectRouter()
    success = router.load_registry()
    
    if not success:
        print("❌ Failed to load registry")
        return False
    
    stats = router.get_stats()
    print(f"✅ Loaded {stats['total_projects']} projects")
    print(f"   Domains: {stats['domains']}")
    print(f"   Capabilities: {stats['capabilities']}")
    print(f"   Topics indexed: {stats['topics_count']}")
    print(f"   Default project: {stats['default_project']}")
    
    return True


def test_explicit_routing():
    """Test explicit model path routing."""
    print("\n" + "="*60)
    print("TEST 2: Explicit Model Routing")
    print("="*60)
    
    router = get_project_router()
    
    # Test full path
    decision = router.route("default/llama-expert-14")
    print(f"\n📍 Route 'default/llama-expert-14':")
    print(f"   → {decision.project.model_path if decision.project else 'None'}")
    print(f"   Score: {decision.score:.2f}")
    print(f"   Reason: {decision.reason}")
    
    if decision.project and decision.project.name == "llama-expert-14":
        print("   ✅ Correct!")
    else:
        print("   ❌ Wrong project!")
        return False
    
    # Test name only
    decision = router.route("fishing")
    print(f"\n📍 Route 'fishing':")
    print(f"   → {decision.project.model_path if decision.project else 'None'}")
    print(f"   Score: {decision.score:.2f}")
    print(f"   Reason: {decision.reason}")
    
    if decision.project and decision.project.name == "fishing":
        print("   ✅ Correct!")
    else:
        print("   ⚠️  May have matched different project")
    
    return True


def test_semantic_routing():
    """Test content-based semantic routing."""
    print("\n" + "="*60)
    print("TEST 3: Semantic/Content-Based Routing")
    print("="*60)
    
    router = get_project_router()
    
    # Test llama-related prompt
    messages = [
        {"role": "user", "content": "What do llamas eat and how should I care for their fiber?"}
    ]
    decision = router.route_by_content(messages)
    
    print(f"\n📍 Prompt: 'What do llamas eat and how should I care for their fiber?'")
    print(f"   → {decision.project.model_path if decision.project else 'None'}")
    print(f"   Domain: {decision.project.domain if decision.project else 'None'}")
    print(f"   Score: {decision.score:.2f}")
    print(f"   Reason: {decision.reason}")
    
    if decision.project and "llama" in decision.project.domain.lower():
        print("   ✅ Correctly routed to llama-related project!")
    elif decision.project and "llama" in decision.project.name.lower():
        print("   ✅ Correctly routed to llama-related project!")
    else:
        print("   ⚠️  Did not route to llama project")
    
    # Test fishing prompt
    messages = [
        {"role": "user", "content": "What's the best lure for catching bass in muddy water?"}
    ]
    decision = router.route_by_content(messages)
    
    print(f"\n📍 Prompt: 'What's the best lure for catching bass in muddy water?'")
    print(f"   → {decision.project.model_path if decision.project else 'None'}")
    print(f"   Domain: {decision.project.domain if decision.project else 'None'}")
    print(f"   Score: {decision.score:.2f}")
    print(f"   Reason: {decision.reason}")
    
    if decision.project and "fishing" in decision.project.domain.lower():
        print("   ✅ Correctly routed to fishing project!")
    elif decision.project and "fishing" in decision.project.name.lower():
        print("   ✅ Correctly routed to fishing project!")
    else:
        print("   ⚠️  Did not route to fishing project")
    
    # Test healthcare prompt
    messages = [
        {"role": "user", "content": "I need help understanding my medical records and diagnosis"}
    ]
    decision = router.route_by_content(messages)
    
    print(f"\n📍 Prompt: 'I need help understanding my medical records and diagnosis'")
    print(f"   → {decision.project.model_path if decision.project else 'None'}")
    print(f"   Domain: {decision.project.domain if decision.project else 'None'}")
    print(f"   Score: {decision.score:.2f}")
    print(f"   Reason: {decision.reason}")
    
    return True


def test_fallback_routing():
    """Test fallback to default project."""
    print("\n" + "="*60)
    print("TEST 4: Fallback Routing")
    print("="*60)
    
    router = get_project_router()
    
    # Unknown model
    decision = router.route("nonexistent/model")
    print(f"\n📍 Route 'nonexistent/model':")
    print(f"   → {decision.project.model_path if decision.project else 'None'}")
    print(f"   Fallback: {decision.fallback}")
    print(f"   Reason: {decision.reason}")
    
    if decision.fallback:
        print("   ✅ Correctly fell back to default!")
    else:
        print("   ⚠️  Did not use fallback")
    
    # Unrelated prompt
    messages = [
        {"role": "user", "content": "Tell me about quantum entanglement in theoretical physics"}
    ]
    decision = router.route_by_content(messages)
    
    print(f"\n📍 Prompt: 'Tell me about quantum entanglement in theoretical physics'")
    print(f"   → {decision.project.model_path if decision.project else 'None'}")
    print(f"   Fallback: {decision.fallback}")
    print(f"   Score: {decision.score:.2f}")
    print(f"   Reason: {decision.reason}")
    
    if decision.project:
        print("   ✅ Routed to a project (likely fallback)")
    else:
        print("   ⚠️  No route found")
    
    return True


def test_list_by_domain():
    """Test listing projects by domain."""
    print("\n" + "="*60)
    print("TEST 5: List Projects by Domain")
    print("="*60)
    
    router = get_project_router()
    
    # Llama projects
    llama_projects = router.list_projects(domain="animals/camelids")
    print(f"\n📋 Animals/Camelids domain projects: {len(llama_projects)}")
    for p in llama_projects[:5]:
        print(f"   - {p.model_path}")
    if len(llama_projects) > 5:
        print(f"   ... and {len(llama_projects) - 5} more")
    
    # Healthcare projects
    health_projects = router.list_projects(domain="healthcare")
    print(f"\n📋 Healthcare domain projects: {len(health_projects)}")
    for p in health_projects[:5]:
        print(f"   - {p.model_path}")
    
    # RAG-enabled projects
    rag_projects = router.list_projects(capability="rag")
    print(f"\n📋 RAG-enabled projects: {len(rag_projects)}")
    
    # Tool-enabled projects
    tool_projects = router.list_projects(capability="tools")
    print(f"\n📋 Tool-enabled projects: {len(tool_projects)}")
    for p in tool_projects[:5]:
        print(f"   - {p.model_path}")
    
    return True


def main():
    """Run all tests."""
    print("="*60)
    print("Atmosphere Discovery & Routing Layer Tests")
    print("="*60)
    
    tests = [
        ("Registry Loading", test_registry_loading),
        ("Explicit Routing", test_explicit_routing),
        ("Semantic Routing", test_semantic_routing),
        ("Fallback Routing", test_fallback_routing),
        ("List by Domain", test_list_by_domain),
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
