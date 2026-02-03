#!/usr/bin/env python3
"""
Trigger Flow Demo - Bidirectional Event Routing

Simulates the complete flow:
1. Camera fires a motion trigger
2. Atmosphere routes to security agent
3. Agent processes and calls tools back
4. Full bidirectional mesh in action

This is a simulation to illustrate the architecture.
"""

import asyncio
import time
import random
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class TriggerEvent:
    """Event fired by a sensor/device."""
    source: str          # e.g., "camera/front-door"
    event_type: str      # e.g., "motion_detected"
    payload: Dict[str, Any]
    timestamp: float
    
    def __str__(self):
        return f"[{self.event_type}] from {self.source}"


@dataclass  
class ToolCall:
    """Tool call from an agent."""
    caller: str          # e.g., "security-agent"
    tool: str            # e.g., "camera.get_frame"
    args: Dict[str, Any]
    timestamp: float


@dataclass
class ToolResult:
    """Result from a tool call."""
    success: bool
    data: Any
    latency_ms: float


class SimulatedCamera:
    """Simulated camera device."""
    
    def __init__(self, name: str, location: str):
        self.name = name
        self.location = location
        self.frame_count = 0
    
    def detect_motion(self) -> Optional[TriggerEvent]:
        """Simulate motion detection."""
        if random.random() > 0.3:  # 70% chance of motion
            return TriggerEvent(
                source=f"camera/{self.name}",
                event_type="motion_detected",
                payload={
                    "confidence": round(random.uniform(0.7, 0.99), 2),
                    "region": random.choice(["center", "left", "right"]),
                    "frame_id": f"frame_{self.frame_count}",
                    "location": self.location,
                },
                timestamp=time.time()
            )
        return None
    
    def get_frame(self) -> Dict[str, Any]:
        """Get current frame (simulated)."""
        self.frame_count += 1
        return {
            "frame_id": f"frame_{self.frame_count}",
            "timestamp": time.time(),
            "resolution": "1920x1080",
            "format": "jpeg",
            "size_bytes": random.randint(50000, 150000),
            # In reality: base64 encoded image data
            "data": f"<simulated_frame_{self.frame_count}_data>"
        }


class SimulatedAgent:
    """Simulated security agent."""
    
    def __init__(self, name: str):
        self.name = name
        self.events_processed = 0
        self.tools_called = 0
    
    async def process_trigger(self, event: TriggerEvent, router: 'AtmosphereRouter') -> str:
        """Process incoming trigger event."""
        self.events_processed += 1
        
        # Simulate thinking time
        await asyncio.sleep(0.05)
        
        response_parts = [f"🔔 Received: {event}"]
        
        # Agent decides to get more context
        if event.payload.get('confidence', 0) > 0.8:
            response_parts.append("   ↳ High confidence - requesting frame")
            
            # Call tool back through the mesh
            tool_call = ToolCall(
                caller=self.name,
                tool="camera.get_frame",
                args={"camera_id": event.source.split("/")[1]},
                timestamp=time.time()
            )
            
            result = await router.route_tool_call(tool_call)
            self.tools_called += 1
            
            if result.success:
                response_parts.append(f"   ↳ Got frame: {result.data.get('frame_id')} ({result.latency_ms:.1f}ms)")
                response_parts.append(f"   ↳ Action: Logging event with frame evidence")
            else:
                response_parts.append(f"   ↳ Tool failed: {result.data}")
        else:
            response_parts.append("   ↳ Low confidence - monitoring only")
        
        return "\n".join(response_parts)


class AtmosphereRouter:
    """Simulated Atmosphere mesh router."""
    
    def __init__(self):
        self.devices: Dict[str, SimulatedCamera] = {}
        self.agents: Dict[str, SimulatedAgent] = {}
        self.trigger_routes: Dict[str, str] = {}  # event_type -> agent_name
        self.metrics = {
            "triggers_routed": 0,
            "tools_routed": 0,
            "total_latency_ms": 0,
        }
    
    def register_device(self, camera: SimulatedCamera):
        self.devices[camera.name] = camera
        print(f"   📷 Registered device: camera/{camera.name} ({camera.location})")
    
    def register_agent(self, agent: SimulatedAgent):
        self.agents[agent.name] = agent
        print(f"   🤖 Registered agent: {agent.name}")
    
    def add_trigger_route(self, event_type: str, agent_name: str):
        self.trigger_routes[event_type] = agent_name
        print(f"   🔀 Route: {event_type} → {agent_name}")
    
    async def route_trigger(self, event: TriggerEvent) -> Optional[str]:
        """Route trigger to appropriate agent."""
        start = time.time()
        
        agent_name = self.trigger_routes.get(event.event_type)
        if not agent_name or agent_name not in self.agents:
            return None
        
        agent = self.agents[agent_name]
        result = await agent.process_trigger(event, self)
        
        latency = (time.time() - start) * 1000
        self.metrics["triggers_routed"] += 1
        self.metrics["total_latency_ms"] += latency
        
        return result
    
    async def route_tool_call(self, call: ToolCall) -> ToolResult:
        """Route tool call to appropriate device."""
        start = time.time()
        
        # Parse tool: "camera.get_frame" -> device type + method
        parts = call.tool.split(".")
        device_type = parts[0]
        method = parts[1] if len(parts) > 1 else "default"
        
        camera_id = call.args.get("camera_id")
        
        if device_type == "camera" and camera_id in self.devices:
            camera = self.devices[camera_id]
            
            if method == "get_frame":
                # Simulate network latency
                await asyncio.sleep(random.uniform(0.01, 0.03))
                data = camera.get_frame()
                
                latency = (time.time() - start) * 1000
                self.metrics["tools_routed"] += 1
                self.metrics["total_latency_ms"] += latency
                
                return ToolResult(success=True, data=data, latency_ms=latency)
        
        return ToolResult(
            success=False,
            data={"error": f"Unknown tool: {call.tool}"},
            latency_ms=(time.time() - start) * 1000
        )


async def run_demo():
    """Run the trigger flow demonstration."""
    
    print("\n" + "=" * 70)
    print("🌊 ATMOSPHERE TRIGGER FLOW DEMO")
    print("   Bidirectional Event Routing Simulation")
    print("=" * 70)
    
    # Setup
    print("\n📦 SETUP - Registering mesh components:\n")
    
    router = AtmosphereRouter()
    
    # Register devices
    front_camera = SimulatedCamera("front-door", "Main Entrance")
    back_camera = SimulatedCamera("backyard", "Back Patio")
    router.register_device(front_camera)
    router.register_device(back_camera)
    
    # Register agents
    security_agent = SimulatedAgent("security-agent")
    router.register_agent(security_agent)
    
    # Configure routes
    router.add_trigger_route("motion_detected", "security-agent")
    
    print("\n" + "-" * 70)
    print("🎬 SIMULATION - Running trigger flow:\n")
    
    # Simulate multiple motion events
    cameras = [front_camera, back_camera]
    
    for i in range(5):
        camera = random.choice(cameras)
        event = camera.detect_motion()
        
        if event:
            print(f"\n⚡ Event {i+1}: Motion at {camera.location}")
            print(f"   Payload: confidence={event.payload['confidence']}, region={event.payload['region']}")
            
            # Route through Atmosphere
            result = await router.route_trigger(event)
            if result:
                for line in result.split("\n"):
                    print(f"   {line}")
        else:
            print(f"\n   Event {i+1}: No motion detected at {camera.location}")
        
        await asyncio.sleep(0.1)  # Simulate time between events
    
    # Summary
    print("\n" + "-" * 70)
    print("📊 METRICS SUMMARY:\n")
    
    avg_latency = (
        router.metrics["total_latency_ms"] / 
        max(1, router.metrics["triggers_routed"] + router.metrics["tools_routed"])
    )
    
    print(f"   Triggers routed:  {router.metrics['triggers_routed']}")
    print(f"   Tool calls:       {router.metrics['tools_routed']}")
    print(f"   Avg latency:      {avg_latency:.1f}ms")
    print(f"   Agent processed:  {security_agent.events_processed} events")
    print(f"   Agent tool calls: {security_agent.tools_called}")
    
    print("\n" + "-" * 70)
    print("🔄 FLOW VISUALIZATION:\n")
    print("   ┌─────────────┐     trigger      ┌─────────────────┐")
    print("   │   Camera    │ ──────────────→  │   Atmosphere    │")
    print("   │  (motion)   │                  │     Router      │")
    print("   └─────────────┘                  └────────┬────────┘")
    print("         ↑                                   │ route")
    print("         │                                   ↓")
    print("         │ tool result            ┌─────────────────┐")
    print("         │                        │  Security Agent │")
    print("         │                        │   (processes)   │")
    print("         │                        └────────┬────────┘")
    print("         │                                 │ tool call")
    print("         │      route                      ↓")
    print("   ┌─────────────┐                ┌─────────────────┐")
    print("   │   Camera    │ ←───────────── │   Atmosphere    │")
    print("   │ (get_frame) │   tool call    │     Router      │")
    print("   └─────────────┘                └─────────────────┘")
    
    print("\n" + "=" * 70)
    print("✅ Demo complete!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(run_demo())
