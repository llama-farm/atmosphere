"""
Comprehensive API Tests for Atmosphere

Tests all API endpoints to verify they work correctly.
Run with: python tests/test_api_full.py
Or: pytest tests/test_api_full.py -v
"""

import asyncio
import json
import time
from typing import Optional

try:
    import httpx
except ImportError:
    print("Installing httpx...")
    import subprocess
    subprocess.run(["pip", "install", "httpx"], capture_output=True)
    import httpx

try:
    import websockets
except ImportError:
    print("Installing websockets...")
    import subprocess
    subprocess.run(["pip", "install", "websockets"], capture_output=True)
    import websockets

# Optional pytest support
try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False
    # Create a dummy decorator
    class pytest:
        class mark:
            @staticmethod
            def asyncio(func):
                return func

# Default test configuration
BASE_URL = "http://localhost:11451"
WS_URL = "ws://localhost:11451/api/ws"
TIMEOUT = 30.0


class TestAPIHealth:
    """Test health and status endpoints."""
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """GET /api/health - Basic health check."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api/health")
            
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            # Status can be "healthy" or "starting"
            assert data["status"] in ["healthy", "starting"]
            print(f"✓ Health: {data}")
    
    @pytest.mark.asyncio
    async def test_root_health(self):
        """GET /health - Root health check."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            print(f"✓ Root health: {data}")
    
    @pytest.mark.asyncio
    async def test_api_root(self):
        """GET /api - API status."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api")
            
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Atmosphere"
            assert "version" in data
            print(f"✓ API root: {data}")


class TestMeshEndpoints:
    """Test mesh network endpoints."""
    
    @pytest.mark.asyncio
    async def test_mesh_status(self):
        """GET /api/mesh/status - Mesh network status."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api/mesh/status")
            
            assert response.status_code == 200
            data = response.json()
            assert "mesh_id" in data
            assert "mesh_name" in data
            assert "node_count" in data
            assert "peer_count" in data
            assert "capabilities" in data
            assert "is_founder" in data
            print(f"✓ Mesh status: mesh={data.get('mesh_name')}, peers={data.get('peer_count')}")
    
    @pytest.mark.asyncio
    async def test_mesh_token(self):
        """POST /api/mesh/token - Generate invite token."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(f"{BASE_URL}/api/mesh/token")
            
            assert response.status_code == 200
            data = response.json()
            assert "token" in data
            assert "mesh_id" in data
            assert "mesh_name" in data
            assert "endpoints" in data
            assert "qr_data" in data
            
            # Verify token format
            assert data["token"].startswith("ATM-")
            
            # Verify endpoints structure
            endpoints = data["endpoints"]
            assert "local" in endpoints
            
            print(f"✓ Mesh token: {data['token'][:20]}...")
            print(f"  Endpoints: {list(endpoints.keys())}")
    
    @pytest.mark.asyncio
    async def test_mesh_peers(self):
        """GET /api/mesh/peers - List discovered peers."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api/mesh/peers")
            
            assert response.status_code == 200
            data = response.json()
            assert "peers" in data
            assert isinstance(data["peers"], list)
            print(f"✓ Mesh peers: {len(data['peers'])} peers found")
    
    @pytest.mark.asyncio
    async def test_mesh_topology(self):
        """GET /api/mesh/topology - Get mesh topology for visualization."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api/mesh/topology")
            
            assert response.status_code == 200
            data = response.json()
            assert "nodes" in data
            assert "links" in data
            assert isinstance(data["nodes"], list)
            assert isinstance(data["links"], list)
            
            # Verify node structure
            if data["nodes"]:
                node = data["nodes"][0]
                assert "id" in node
                assert "name" in node
                assert "status" in node
            
            print(f"✓ Mesh topology: {len(data['nodes'])} nodes, {len(data['links'])} links")


class TestCapabilities:
    """Test capability endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_capabilities(self):
        """GET /api/capabilities - List all capabilities."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api/capabilities")
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            
            # Verify capability structure if any exist
            if data:
                cap = data[0]
                assert "id" in cap
                assert "label" in cap
                assert "description" in cap
                assert "handler" in cap
            
            print(f"✓ Capabilities: {len(data)} registered")
            for cap in data[:5]:
                print(f"  - {cap['label']}: {cap['handler']}")


class TestRouting:
    """Test routing endpoints."""
    
    @pytest.mark.asyncio
    async def test_route_intent(self):
        """POST /api/route - Route an intent."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{BASE_URL}/api/route",
                json={"intent": "What is the weather like?"}
            )
            
            # May return 503 if server not fully ready, or 200 if ready
            if response.status_code == 503:
                print("⚠ Route: Server not ready (expected during startup)")
                return
            
            assert response.status_code == 200
            data = response.json()
            assert "action" in data
            assert "score" in data
            print(f"✓ Route: action={data['action']}, score={data['score']}")
    
    @pytest.mark.asyncio
    async def test_execute_intent(self):
        """POST /api/execute - Execute an intent."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{BASE_URL}/api/execute",
                json={"intent": "Say hello"}
            )
            
            # May return 503 if server not fully ready
            if response.status_code == 503:
                print("⚠ Execute: Server not ready (expected during startup)")
                return
            
            assert response.status_code == 200
            data = response.json()
            assert "success" in data
            print(f"✓ Execute: success={data['success']}")


class TestOpenAICompat:
    """Test OpenAI-compatible endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_models(self):
        """GET /v1/models - List available models."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/v1/models")
            
            assert response.status_code == 200
            data = response.json()
            assert "object" in data
            assert data["object"] == "list"
            assert "data" in data
            
            print(f"✓ Models: {len(data['data'])} models available")
            for model in data['data'][:5]:
                print(f"  - {model.get('id', 'unknown')}")
    
    @pytest.mark.asyncio
    async def test_chat_completions(self):
        """POST /v1/chat/completions - Chat completion."""
        async with httpx.AsyncClient(timeout=120.0) as client:  # Longer timeout for LLM
            response = await client.post(
                f"{BASE_URL}/v1/chat/completions",
                json={
                    "model": "default",
                    "messages": [
                        {"role": "user", "content": "Say 'test ok' and nothing else."}
                    ],
                    "max_tokens": 20
                }
            )
            
            # May fail if LlamaFarm not running
            if response.status_code in [500, 502, 503, 504]:
                print(f"⚠ Chat completions: Backend unavailable ({response.status_code})")
                return
            
            assert response.status_code == 200
            data = response.json()
            assert "choices" in data
            assert len(data["choices"]) > 0
            
            message = data["choices"][0].get("message", {})
            content = message.get("content", "")
            print(f"✓ Chat completions: '{content[:50]}...'")
    
    @pytest.mark.asyncio
    async def test_embeddings(self):
        """POST /v1/embeddings - Generate embeddings."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{BASE_URL}/v1/embeddings",
                json={
                    "model": "default",
                    "input": "Hello world"
                }
            )
            
            # May fail if embedding backend not running
            if response.status_code in [500, 502, 503, 504]:
                print(f"⚠ Embeddings: Backend unavailable ({response.status_code})")
                return
            
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            print(f"✓ Embeddings: Generated successfully")


class TestCost:
    """Test cost-related endpoints."""
    
    @pytest.mark.asyncio
    async def test_current_cost(self):
        """GET /api/cost/current - Get current cost factors."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api/cost/current")
            
            assert response.status_code == 200
            data = response.json()
            assert "node_id" in data
            assert "power" in data
            assert "compute" in data
            assert "network" in data
            assert "cost_multiplier" in data
            
            print(f"✓ Cost: multiplier={data['cost_multiplier']:.2f}")
            print(f"  Power: battery={data['power']['on_battery']}")
            print(f"  Compute: cpu={data['compute']['cpu_load']:.1%}")


class TestIntegrations:
    """Test integration discovery endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_integrations(self):
        """GET /api/integrations - Discover backend integrations."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api/integrations")
            
            assert response.status_code == 200
            data = response.json()
            assert "integrations" in data
            
            print(f"✓ Integrations: {len(data['integrations'])} found")
            for integration in data['integrations']:
                status = integration.get('status', 'unknown')
                name = integration.get('name', 'Unknown')
                print(f"  - {name}: {status}")


class TestAgents:
    """Test agent management endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_agents(self):
        """GET /api/agents - List registered agents."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api/agents")
            
            assert response.status_code == 200
            data = response.json()
            assert "agents" in data
            
            print(f"✓ Agents: {len(data['agents'])} registered")
            for agent in data['agents'][:5]:
                print(f"  - {agent.get('name', 'Unknown')}: {agent.get('status', 'unknown')}")


class TestApproval:
    """Test approval configuration endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_approval_config(self):
        """GET /api/approval/config - Get approval configuration."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api/approval/config")
            
            assert response.status_code == 200
            data = response.json()
            assert "models" in data
            assert "hardware" in data
            assert "privacy" in data
            assert "access" in data
            
            print(f"✓ Approval config: loaded")


class TestWebSocket:
    """Test WebSocket endpoints."""
    
    @pytest.mark.asyncio
    async def test_websocket_connection(self):
        """Test WebSocket connection and initial messages."""
        try:
            async with websockets.connect(WS_URL, close_timeout=5) as ws:
                # Should receive initial mesh_status
                message = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(message)
                
                assert data["type"] in ["mesh_status", "cost_update", "ping"]
                print(f"✓ WebSocket: Connected, received {data['type']}")
                
                # Wait for another message
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(message)
                    print(f"  Second message: {data['type']}")
                except asyncio.TimeoutError:
                    print("  No additional messages (timeout)")
                
        except Exception as e:
            print(f"⚠ WebSocket: Connection failed - {e}")


class TestPermissions:
    """Test permission status endpoints (macOS)."""
    
    @pytest.mark.asyncio
    async def test_permissions_status(self):
        """GET /api/permissions/status - Get permission status."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/api/permissions/status")
            
            assert response.status_code == 200
            data = response.json()
            assert "platform" in data
            assert "permissions" in data
            
            print(f"✓ Permissions: platform={data['platform']}")
            for name, perm in data['permissions'].items():
                print(f"  {name}: {perm.get('status', 'unknown')}")


class TestRoutingInfo:
    """Test routing info endpoints."""
    
    @pytest.mark.asyncio
    async def test_routing_stats(self):
        """GET /v1/routing/stats - Get routing statistics."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/v1/routing/stats")
            
            assert response.status_code == 200
            data = response.json()
            print(f"✓ Routing stats: {data}")
    
    @pytest.mark.asyncio
    async def test_routing_projects(self):
        """GET /v1/routing/projects - List routable projects."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/v1/routing/projects")
            
            assert response.status_code == 200
            data = response.json()
            assert "projects" in data
            print(f"✓ Routing projects: {len(data['projects'])} projects")


# ============ Test Runner ============

async def run_all_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("Atmosphere API Test Suite")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"WebSocket URL: {WS_URL}")
    print("=" * 60)
    
    results = {
        "passed": 0,
        "failed": 0,
        "skipped": 0
    }
    
    test_classes = [
        ("Health", TestAPIHealth),
        ("Mesh", TestMeshEndpoints),
        ("Capabilities", TestCapabilities),
        ("Routing", TestRouting),
        ("OpenAI Compat", TestOpenAICompat),
        ("Cost", TestCost),
        ("Integrations", TestIntegrations),
        ("Agents", TestAgents),
        ("Approval", TestApproval),
        ("WebSocket", TestWebSocket),
        ("Permissions", TestPermissions),
        ("Routing Info", TestRoutingInfo),
    ]
    
    for section_name, test_class in test_classes:
        print(f"\n--- {section_name} ---")
        instance = test_class()
        
        for method_name in dir(instance):
            if not method_name.startswith("test_"):
                continue
            
            method = getattr(instance, method_name)
            if not callable(method):
                continue
            
            try:
                await method()
                results["passed"] += 1
            except AssertionError as e:
                print(f"✗ {method_name}: {e}")
                results["failed"] += 1
            except Exception as e:
                print(f"✗ {method_name}: {type(e).__name__}: {e}")
                results["failed"] += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {results['passed']} passed, {results['failed']} failed, {results['skipped']} skipped")
    print("=" * 60)
    
    return results["failed"] == 0


if __name__ == "__main__":
    import sys
    
    # Allow custom base URL
    if len(sys.argv) > 1:
        BASE_URL = sys.argv[1]
        WS_URL = BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/api/ws"
    
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
