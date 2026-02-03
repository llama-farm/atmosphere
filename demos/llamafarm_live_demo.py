#!/usr/bin/env python3
"""
Live LlamaFarm Integration Demo

Shows Atmosphere routing to real LlamaFarm projects.
Requires: LlamaFarm running on localhost:14345
"""

import asyncio
import time

try:
    import httpx
except ImportError:
    print("❌ httpx not installed. Run: pip install httpx")
    exit(1)

LLAMAFARM_URL = "http://localhost:14345"


async def main():
    print("\n🌐 ATMOSPHERE LIVE DEMO - Real LlamaFarm Integration\n")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=60) as client:
        # 1. Check health
        print("\n1. Checking LlamaFarm health...")
        try:
            r = await client.get(f"{LLAMAFARM_URL}/health")
            health = r.json()
            print(f"   ✅ LlamaFarm healthy: status={health.get('status')}")
            
            # Show component status
            components = health.get('components', [])
            healthy = sum(1 for c in components if c.get('status') == 'healthy')
            print(f"   📊 Components: {healthy}/{len(components)} healthy")
            
            # Show ollama models if available
            for c in components:
                if c.get('name') == 'ollama':
                    details = c.get('details', {})
                    model_count = details.get('model_count', 0)
                    print(f"   🦙 Ollama: {model_count} model(s) available")
                    
        except httpx.ConnectError:
            print(f"   ❌ LlamaFarm not reachable at {LLAMAFARM_URL}")
            print("   Start with: cd ~/clawd/projects/llamafarm-core/server && uv run python main.py")
            return
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return
        
        # 2. List projects (discovery)
        print("\n2. Discovering projects...")
        projects_list = []
        try:
            # LlamaFarm projects API requires namespace in path
            r = await client.get(f"{LLAMAFARM_URL}/v1/projects/default")
            projects = r.json()
            projects_list = projects.get('projects', [])
            total = projects.get('total', len(projects_list))
            print(f"   📁 Found {total} projects in 'default' namespace")
            for p in projects_list[:5]:
                ns = p.get('namespace', 'default')
                name = p.get('name', 'unknown')
                print(f"      - {ns}/{name}")
            if total > 5:
                print(f"      ... and {total - 5} more")
        except Exception as e:
            print(f"   ⚠️  Could not list projects: {e}")
        
        # 3. Check Universal Runtime
        print("\n3. Checking Universal Runtime...")
        try:
            r = await client.get("http://localhost:11540/health")
            ur_health = r.json()
            device = ur_health.get('device', {}).get('device', 'unknown')
            gpu = ur_health.get('device', {}).get('gpu_name', 'unknown')
            print(f"   ✅ Universal Runtime healthy")
            print(f"   🖥️  Device: {device} ({gpu})")
            loaded = ur_health.get('loaded_models', [])
            if loaded:
                print(f"   📦 Loaded models: {', '.join(loaded)}")
            else:
                print(f"   📦 No models currently loaded (will load on demand)")
        except Exception as e:
            print(f"   ⚠️  Universal Runtime: {e}")
        
        # 4. Route a chat completion (semantic routing)
        print("\n4. Testing chat completion routing...")
        
        # If we found projects, try using one for chat
        if projects_list:
            project = projects_list[0]
            ns = project.get('namespace', 'default')
            name = project.get('name')
            
            print(f"   🔄 Trying project: {ns}/{name}")
            start = time.time()
            try:
                r = await client.post(
                    f"{LLAMAFARM_URL}/v1/projects/{ns}/{name}/chat/completions",
                    json={
                        "messages": [
                            {"role": "user", "content": "Say hello in exactly 5 words."}
                        ],
                        "max_tokens": 50,
                        "stream": False
                    }
                )
                elapsed = (time.time() - start) * 1000
                
                if r.status_code == 200:
                    result = r.json()
                    content = result.get('choices', [{}])[0].get('message', {}).get('content', 'No response')
                    content = content.strip()[:100]
                    print(f"   ✅ Response in {elapsed:.0f}ms")
                    print(f"   💬 \"{content}\"")
                else:
                    print(f"   ⚠️  Status {r.status_code}: {r.text[:100]}")
            except Exception as e:
                print(f"   ⚠️  Error: {e}")
        else:
            print("   ⚠️  No projects found to test chat completion")
        
        # Also try direct Ollama for comparison
        print("\n   🦙 Trying direct Ollama API...")
        start = time.time()
        try:
            r = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "tinyllama:latest",
                    "prompt": "Say hello in exactly 5 words.",
                    "stream": False
                }
            )
            elapsed = (time.time() - start) * 1000
            
            if r.status_code == 200:
                result = r.json()
                content = result.get('response', 'No response').strip()[:100]
                print(f"   ✅ Ollama response in {elapsed:.0f}ms")
                print(f"   💬 \"{content}\"")
            else:
                print(f"   ⚠️  Ollama status {r.status_code}")
        except Exception as e:
            print(f"   ⚠️  Ollama error: {e}")
        
        # 5. Demonstrate Atmosphere concepts
        print("\n" + "=" * 60)
        print("\n5. 🌍 ATMOSPHERE MESH CONCEPTS\n")
        
        print("   📤 PUSH (Triggers):")
        print("      Camera detects motion")
        print("         → fires 'motion_detected' event")
        print("         → Atmosphere routes to security agent")
        print("         → Agent receives event with image/metadata")
        
        print("\n   📥 PULL (Tools):")
        print("      Security agent needs more context")
        print("         → calls camera.get_frame(camera_id='front')")
        print("         → Atmosphere routes tool call to camera node")
        print("         → Returns current frame to agent")
        
        print("\n   🔄 BIDIRECTIONAL:")
        print("      Same mesh, same routing, both directions!")
        print("      Triggers PUSH to agents, agents PULL via tools")
        
        print("\n   🌐 DISCOVERY:")
        project_count = len(projects_list) if projects_list else 0
        print(f"      LlamaFarm projects discovered: {project_count}")
        print("      Each project = potential routing target")
        print("      Semantic routing matches intent → capability")
        
        print("\n" + "=" * 60)
        print("✅ Demo complete!")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
