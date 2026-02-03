#!/usr/bin/env python3
"""
Bidirectional Capabilities Demo

Demonstrates the core insight: Every capability is both a TRIGGER and a TOOL.

Run this demo:
    cd ~/clawd/projects/atmosphere
    python demos/bidirectional_demo.py

No external services required - uses simulated capabilities.
"""

import asyncio
import json
import time
from typing import Dict, Any, List

# Import from our new capability system
import sys
sys.path.insert(0, '.')

from atmosphere.capabilities.registry import (
    CapabilityRegistry,
    Capability,
    CapabilityType,
    Tool,
    Trigger,
    GossipMessage,
)
from atmosphere.capabilities.examples import (
    CAMERA_CAPABILITY,
    VOICE_CAPABILITY,
    TRANSCRIBE_CAPABILITY,
    IMAGE_GEN_CAPABILITY,
)


def banner(text: str):
    """Print a banner."""
    width = 70
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width + "\n")


def section(text: str):
    """Print a section header."""
    print(f"\n--- {text} ---\n")


async def demo_capability_registration():
    """Demo: Register capabilities and query them."""
    banner("CAPABILITY REGISTRATION")
    
    # Create a fresh registry
    registry = CapabilityRegistry(node_id="demo-node")
    
    # Register multimodal capabilities
    capabilities = [
        CAMERA_CAPABILITY,
        VOICE_CAPABILITY,
        TRANSCRIBE_CAPABILITY,
        IMAGE_GEN_CAPABILITY,
    ]
    
    for cap in capabilities:
        await registry.register(cap)
        tools = [t.name for t in cap.tools]
        triggers = [t.event for t in cap.triggers]
        print(f"✅ Registered: {cap.id}")
        print(f"   Type: {cap.type.value}")
        print(f"   Tools (PULL):    {tools}")
        print(f"   Triggers (PUSH): {triggers}")
        print()
    
    section("Registry Stats")
    stats = registry.stats()
    print(json.dumps(stats, indent=2))
    
    return registry


async def demo_query_capabilities(registry: CapabilityRegistry):
    """Demo: Query capabilities by type, trigger, and tool."""
    banner("QUERYING CAPABILITIES")
    
    section("Find by Type: SENSOR_CAMERA")
    cameras = registry.find_by_type(CapabilityType.SENSOR_CAMERA, healthy_only=False)
    for cam in cameras:
        print(f"  📷 {cam.id} - {len(cam.tools)} tools, {len(cam.triggers)} triggers")
    
    section("Find by Trigger: 'person_detected'")
    caps = registry.find_by_trigger("person_detected", healthy_only=False)
    for cap in caps:
        print(f"  🔔 {cap.id} can trigger 'person_detected'")
    
    section("Find by Trigger: 'speech_complete'")
    caps = registry.find_by_trigger("speech_complete", healthy_only=False)
    for cap in caps:
        print(f"  🔔 {cap.id} can trigger 'speech_complete'")
    
    section("Find by Tool: 'get_frame'")
    caps = registry.find_by_tool("get_frame", healthy_only=False)
    for cap in caps:
        print(f"  🔧 {cap.id} has tool 'get_frame'")
    
    section("Find by Route Hint: 'audio/*'")
    caps = registry.find_by_route_hint("audio/*", healthy_only=False)
    for cap in caps:
        print(f"  🎯 {cap.id} matches 'audio/*' ({cap.type.value})")


async def demo_bidirectional_flow():
    """Demo: Show the bidirectional nature - trigger → agent → tool."""
    banner("BIDIRECTIONAL FLOW")
    
    print("""
    This demonstrates the core insight:
    
    1. Camera TRIGGERS 'person_detected' → pushes to mesh
    2. Security Agent receives the trigger
    3. Agent CALLS camera.get_frame() → pulls from mesh
    4. Agent CALLS llm.analyze() → pulls from mesh
    5. Agent CALLS voice.speak() → pulls from mesh
    6. Voice capability TRIGGERS 'speech_complete'
    """)
    
    section("Simulated Flow")
    
    # Step 1: Camera fires trigger
    print("📷 Camera detects person...")
    trigger_payload = {
        "location": "front door",
        "confidence": 0.94,
        "timestamp": time.time(),
    }
    print(f"   TRIGGER: person_detected")
    print(f"   Payload: {json.dumps(trigger_payload, indent=6)}")
    
    # Step 2: Security agent receives
    print("\n🤖 Security Agent receives trigger via mesh routing...")
    print("   Route hint: agent/security")
    print("   Intent: 'person detected at front door'")
    
    # Step 3: Agent calls camera tool
    print("\n🔧 Agent CALLS camera.get_frame() (PULL)...")
    print("   → Mesh routes to camera capability")
    print("   ← Returns: <image data>")
    
    # Step 4: Agent calls LLM
    print("\n🔧 Agent CALLS llm.analyze() (PULL)...")
    print("   → Mesh routes to best LLM capability")
    print("   ← Returns: 'Delivery person with package'")
    
    # Step 5: Agent calls voice
    print("\n🔧 Agent CALLS voice.speak() (PULL)...")
    print("   → Mesh routes to voice capability")
    print("   → Text: 'Delivery person at front door'")
    
    # Step 6: Voice fires trigger
    print("\n🔊 Voice capability completes...")
    print("   TRIGGER: speech_complete")
    print("   Payload: {text_preview: 'Delivery...', duration_ms: 1500}")
    
    print("\n✅ Full bidirectional flow complete!")
    print("   2 TRIGGERS fired (push)")
    print("   3 TOOLS called (pull)")


async def demo_gossip_messages(registry: CapabilityRegistry):
    """Demo: Show gossip message generation."""
    banner("GOSSIP PROTOCOL MESSAGES")
    
    section("CAPABILITY_AVAILABLE Message")
    cap = registry.get("front-door-camera")
    if cap:
        msg = registry.generate_available_message(cap)
        # Truncate capability data for display
        msg_display = {**msg}
        msg_display["capability"] = {"id": msg["capability"]["id"], "type": msg["capability"]["type"], "...": "truncated"}
        print(json.dumps(msg_display, indent=2))
    
    section("CAPABILITY_HEARTBEAT Message")
    msg = registry.generate_heartbeat_message()
    print(json.dumps(msg, indent=2))
    
    section("CAPABILITY_UNAVAILABLE Message")
    msg = registry.generate_unavailable_message("front-door-camera", "maintenance")
    print(json.dumps(msg, indent=2))


async def demo_multimodal_capabilities():
    """Demo: Show all multimodal capability types."""
    banner("MULTIMODAL CAPABILITY TYPES")
    
    capabilities = {
        "Vision/Camera": [
            ("TRIGGERS", ["motion_detected", "person_detected", "package_detected", "vehicle_detected"]),
            ("TOOLS", ["get_frame", "get_history", "get_clip", "set_mode"]),
        ],
        "Voice/TTS": [
            ("TRIGGERS", ["speech_complete"]),
            ("TOOLS", ["speak", "list_voices", "speak_ssml"]),
        ],
        "Transcription": [
            ("TRIGGERS", ["transcription_complete", "keyword_detected", "speaker_change"]),
            ("TOOLS", ["transcribe", "transcribe_url", "transcribe_stream"]),
        ],
        "Image Generation": [
            ("TRIGGERS", ["generation_complete", "variation_complete"]),
            ("TOOLS", ["generate", "edit", "variations", "upscale"]),
        ],
        "Voice Cloning": [
            ("TRIGGERS", ["clone_ready"]),
            ("TOOLS", ["clone", "speak_cloned"]),
        ],
    }
    
    for category, items in capabilities.items():
        print(f"\n📌 {category}")
        for label, values in items:
            direction = "⬆️ PUSH" if label == "TRIGGERS" else "⬇️ PULL"
            print(f"   {direction} {label}: {', '.join(values)}")


async def main():
    """Run all demos."""
    print("\n" + "🌐" * 35)
    print("\n   ATMOSPHERE: BIDIRECTIONAL CAPABILITIES DEMO")
    print("\n" + "🌐" * 35)
    
    print("""
    The Internet of Intent
    ----------------------
    
    Core Insight: Every capability is BIDIRECTIONAL
    
    • TRIGGERS (push): Capability emits events into the mesh
    • TOOLS (pull): External systems call capability functions
    
    Same registration. Same routing. Both directions.
    """)
    
    # Run demos
    registry = await demo_capability_registration()
    await demo_query_capabilities(registry)
    await demo_bidirectional_flow()
    await demo_gossip_messages(registry)
    await demo_multimodal_capabilities()
    
    banner("DEMO COMPLETE")
    
    print("""
    Summary:
    --------
    ✅ Registered 4 multimodal capabilities
    ✅ Queried by type, trigger, tool, and route hint
    ✅ Demonstrated bidirectional flow (trigger → agent → tools)
    ✅ Generated gossip protocol messages
    ✅ Showed all multimodal capability types
    
    Next: Run with real LlamaFarm integration
          python demos/llamafarm_integration_demo.py
    """)


if __name__ == "__main__":
    asyncio.run(main())
