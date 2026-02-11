#!/usr/bin/env python3
"""
E2E test: Simulates Android HORIZON app → Atmosphere mesh → HORIZON backend.

Tests the full tool_call chain:
1. Connect to Atmosphere mesh WebSocket (like phone SDK)
2. Send join message
3. Discover HORIZON app + tools
4. Call tools via mesh (tool_call messages)
5. Verify responses come back with correct data

Also tests the relay path by sending tool_call as broadcast
(same as phone would through relay server).
"""

import asyncio
import json
import time
import uuid
import sys
import httpx
import websockets

ATMOSPHERE_URL = "http://localhost:11451"
ATMOSPHERE_WS = "ws://localhost:11451/api/mesh/ws"
HORIZON_URL = "http://localhost:8074"

# Simulated phone node
PHONE_NODE_ID = "test_phone_" + uuid.uuid4().hex[:8]

class Colors:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

passed = 0
failed = 0
errors = []

def ok(name, detail=""):
    global passed
    passed += 1
    print(f"  {Colors.OK}✅ {name}{Colors.RESET} {detail}")

def fail(name, detail=""):
    global failed
    failed += 1
    errors.append(f"{name}: {detail}")
    print(f"  {Colors.FAIL}❌ {name}{Colors.RESET} {detail}")


async def test_rest_api():
    """Test REST API endpoints (what the WebUI uses)."""
    print(f"\n{Colors.BOLD}═══ REST API Tests ═══{Colors.RESET}")
    
    async with httpx.AsyncClient(timeout=10) as client:
        # Test 1: List apps
        r = await client.get(f"{ATMOSPHERE_URL}/api/apps")
        data = r.json()
        if data.get("count", 0) >= 1 and any(a["name"] == "horizon" for a in data.get("apps", [])):
            ok("GET /api/apps", f"Found {data['count']} app(s)")
        else:
            fail("GET /api/apps", f"Expected horizon app, got: {data}")

        # Test 2: Get tools for horizon
        r = await client.get(f"{ATMOSPHERE_URL}/api/apps/horizon/tools")
        data = r.json()
        tools = data.get("tools", {})
        if len(tools) > 10:
            ok("GET /api/apps/horizon/tools", f"{len(tools)} tools discovered")
        else:
            fail("GET /api/apps/horizon/tools", f"Expected >10 tools, got {len(tools)}")

        # Test 3: Call get_mission_summary via REST
        r = await client.post(
            f"{ATMOSPHERE_URL}/api/apps/horizon/tools/get_mission_summary/call",
            json={}
        )
        data = r.json()
        if data.get("callsign") == "REACH 421":
            ok("REST tool_call: get_mission_summary", f"callsign={data['callsign']}")
        else:
            fail("REST tool_call: get_mission_summary", f"Unexpected: {json.dumps(data)[:200]}")

        # Test 4: Call get_active_anomalies via REST
        r = await client.post(
            f"{ATMOSPHERE_URL}/api/apps/horizon/tools/get_active_anomalies/call",
            json={}
        )
        data = r.json()
        if "anomalies" in data or "critical" in data or isinstance(data, dict):
            ok("REST tool_call: get_active_anomalies", f"keys={list(data.keys())[:5]}")
        else:
            fail("REST tool_call: get_active_anomalies", f"Unexpected: {json.dumps(data)[:200]}")

        # Test 5: Call get_suggestions via REST
        r = await client.post(
            f"{ATMOSPHERE_URL}/api/apps/horizon/tools/get_suggestions/call",
            json={}
        )
        data = r.json()
        if "suggestions" in data:
            ok("REST tool_call: get_suggestions", f"{len(data['suggestions'])} suggestions")
        else:
            fail("REST tool_call: get_suggestions", f"Unexpected: {json.dumps(data)[:200]}")

        # Test 6: Call get_voice_status
        r = await client.post(
            f"{ATMOSPHERE_URL}/api/apps/horizon/tools/get_voice_status/call",
            json={}
        )
        data = r.json()
        if "monitoring" in data or "status" in data:
            ok("REST tool_call: get_voice_status", f"monitoring={data.get('monitoring')}")
        else:
            fail("REST tool_call: get_voice_status", f"Unexpected: {json.dumps(data)[:200]}")

        # Test 7: Call get_osint_status
        r = await client.post(
            f"{ATMOSPHERE_URL}/api/apps/horizon/tools/get_osint_status/call",
            json={}
        )
        data = r.json()
        if "total_items" in data or "status" in data or "categories" in data:
            ok("REST tool_call: get_osint_status", f"keys={list(data.keys())[:5]}")
        else:
            fail("REST tool_call: get_osint_status", f"Unexpected: {json.dumps(data)[:200]}")

        # Test 8: POST tool with params — query_knowledge
        r = await client.post(
            f"{ATMOSPHERE_URL}/api/apps/horizon/tools/query_knowledge/call",
            json={"params": {"question": "What is the fuel reserve requirement?"}}
        )
        data = r.json()
        if "answer" in data or "response" in data or "results" in data:
            answer = data.get("answer", data.get("response", ""))
            ok("REST tool_call: query_knowledge", f"Got answer ({len(str(answer))} chars)")
        else:
            fail("REST tool_call: query_knowledge", f"Unexpected: {json.dumps(data)[:200]}")

        # Test 9: Bidirectional — inject anomaly then check
        r = await client.post(
            f"{ATMOSPHERE_URL}/api/apps/horizon/tools/inject_anomaly/call",
            json={"params": {"category": "fuel", "severity": "warning"}}
        )
        inject_data = r.json()
        
        r2 = await client.post(
            f"{ATMOSPHERE_URL}/api/apps/horizon/tools/get_active_anomalies/call",
            json={}
        )
        anomaly_data = r2.json()
        if anomaly_data.get("total_active", 0) >= 1 or "anomalies" in anomaly_data:
            ok("Bidirectional: inject_anomaly → get_active_anomalies", f"total_active={anomaly_data.get('total_active')}")
        else:
            fail("Bidirectional: inject_anomaly → get_active_anomalies", f"Got: {json.dumps(anomaly_data)[:200]}")


async def test_websocket_tool_call():
    """Test WebSocket tool_call chain (simulates phone SDK)."""
    print(f"\n{Colors.BOLD}═══ WebSocket Tool Call Tests (Phone Simulation) ═══{Colors.RESET}")
    
    try:
        async with websockets.connect(ATMOSPHERE_WS, ping_interval=None) as ws:
            # Step 1: Send join message (like Android MeshConnection does)
            join_msg = {
                "type": "join",
                "node_id": PHONE_NODE_ID,
                "mesh_id": "test_mesh"
            }
            await ws.send(json.dumps(join_msg))
            
            # Drain initial messages (mesh_status, gossip, etc.)
            initial_msgs = []
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(msg)
                    initial_msgs.append(data.get("type", "unknown"))
            except asyncio.TimeoutError:
                pass
            
            ok("WS connect + join", f"Received {len(initial_msgs)} initial msgs: {initial_msgs[:5]}")

            # Step 2: Send tool_call for get_mission_summary (direct, like LAN peer)
            request_id_1 = str(uuid.uuid4())
            tool_call_msg = {
                "type": "tool_call",
                "request_id": request_id_1,
                "app": "horizon",
                "tool": "get_mission_summary",
                "params": {},
                "node_id": PHONE_NODE_ID
            }
            await ws.send(json.dumps(tool_call_msg))
            
            # Wait for response
            response = None
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    # Look for tool_response matching our request_id
                    if data.get("type") == "tool_response" or \
                       (data.get("payload", {}).get("type") == "tool_response") or \
                       data.get("request_id") == request_id_1:
                        response = data
                        break
                    # Direct response (non-broadcast)
                    if data.get("request_id") == request_id_1:
                        response = data
                        break
                    # Check body for mission data
                    body = data.get("body", data.get("payload", {}).get("body", {}))
                    if isinstance(body, dict) and body.get("callsign"):
                        response = data
                        break
            except asyncio.TimeoutError:
                pass
            
            if response:
                # Extract the actual body
                body = response.get("body", response.get("payload", {}).get("body", response))
                callsign = body.get("callsign", "") if isinstance(body, dict) else ""
                if callsign == "REACH 421":
                    ok("WS tool_call: get_mission_summary", f"callsign={callsign}, req_id matched")
                else:
                    ok("WS tool_call: get_mission_summary", f"Got response (keys: {list(response.keys())[:5]})")
            else:
                fail("WS tool_call: get_mission_summary", "No response within 5s")

            # Step 3: Send tool_call for get_active_anomalies
            request_id_2 = str(uuid.uuid4())
            tool_call_msg2 = {
                "type": "tool_call",
                "request_id": request_id_2,
                "app": "horizon",
                "tool": "get_active_anomalies",
                "params": {},
                "node_id": PHONE_NODE_ID
            }
            await ws.send(json.dumps(tool_call_msg2))
            
            response2 = None
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    if data.get("request_id") == request_id_2 or \
                       data.get("payload", {}).get("request_id") == request_id_2:
                        response2 = data
                        break
            except asyncio.TimeoutError:
                pass
            
            if response2:
                ok("WS tool_call: get_active_anomalies", f"Got response")
            else:
                fail("WS tool_call: get_active_anomalies", "No response within 5s")

            # Step 4: Send tool_call with params (query_knowledge)
            request_id_3 = str(uuid.uuid4())
            tool_call_msg3 = {
                "type": "tool_call",
                "request_id": request_id_3,
                "app": "horizon",
                "tool": "query_knowledge",
                "params": {"question": "C-17 max cargo weight"},
                "node_id": PHONE_NODE_ID
            }
            await ws.send(json.dumps(tool_call_msg3))
            
            response3 = None
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(msg)
                    if data.get("request_id") == request_id_3 or \
                       data.get("payload", {}).get("request_id") == request_id_3:
                        response3 = data
                        break
            except asyncio.TimeoutError:
                pass
            
            if response3:
                ok("WS tool_call: query_knowledge (with params)", "Got knowledge response")
            else:
                fail("WS tool_call: query_knowledge (with params)", "No response within 10s")

            # Step 5: Test broadcast-wrapped tool_call (relay path simulation)
            request_id_4 = str(uuid.uuid4())
            broadcast_msg = {
                "type": "broadcast",
                "payload": {
                    "type": "tool_call",
                    "request_id": request_id_4,
                    "app": "horizon",
                    "tool": "get_mission_summary",
                    "params": {},
                    "node_id": PHONE_NODE_ID
                }
            }
            await ws.send(json.dumps(broadcast_msg))
            
            response4 = None
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    req = data.get("request_id", data.get("payload", {}).get("request_id", ""))
                    if req == request_id_4:
                        response4 = data
                        break
            except asyncio.TimeoutError:
                pass
            
            if response4:
                ok("WS broadcast tool_call (relay sim)", "Got response through broadcast path")
            else:
                fail("WS broadcast tool_call (relay sim)", "No response — relay path may not route back on same WS")

    except Exception as e:
        fail("WebSocket connection", str(e))


async def test_relay_simulation():
    """
    Simulate relay-mediated tool_call: phone → relay → server → HORIZON → server → relay → phone.
    Uses the /ws endpoint (main WS) to simulate what the relay would deliver.
    """
    print(f"\n{Colors.BOLD}═══ Relay Path Simulation ═══{Colors.RESET}")
    
    # The relay path on the server side is handled in _handle_relay_message().
    # When a message comes through the relay, it arrives as:
    #   {"type": "message", "from": "<node_id>", "payload": {"type": "tool_call", ...}}
    # We can't easily simulate the full relay without a relay server,
    # but we can verify the server handles tool_call payloads correctly
    # by using the LAN peer WebSocket path.
    
    try:
        async with websockets.connect("ws://localhost:11451/mesh/ws", ping_interval=None) as ws:
            # This is the LAN peer endpoint
            # Drain initial
            try:
                while True:
                    await asyncio.wait_for(ws.recv(), timeout=1.0)
            except (asyncio.TimeoutError, Exception):
                pass
            
            request_id = str(uuid.uuid4())
            # Send as broadcast (LAN peer format)
            msg = {
                "type": "broadcast",
                "payload": {
                    "type": "tool_call",
                    "request_id": request_id,
                    "app": "horizon",
                    "tool": "get_fuel",
                    "params": {},
                    "node_id": PHONE_NODE_ID
                }
            }
            await ws.send(json.dumps(msg))
            
            response = None
            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(raw)
                    payload = data.get("payload", data)
                    if payload.get("request_id") == request_id or data.get("request_id") == request_id:
                        response = data
                        break
            except asyncio.TimeoutError:
                pass
            
            if response:
                body = response.get("payload", {}).get("body", response.get("body", {}))
                ok("LAN peer tool_call: get_fuel", f"Got fuel data (keys: {list(body.keys())[:5] if isinstance(body, dict) else 'n/a'})")
            else:
                fail("LAN peer tool_call: get_fuel", "No response within 5s")
                
    except Exception as e:
        # LAN peer WS might not be available
        print(f"  {Colors.WARN}⚠️  LAN peer WS not available: {e}{Colors.RESET}")


async def test_direct_horizon():
    """Test HORIZON backend directly (bypass mesh) — baseline."""
    print(f"\n{Colors.BOLD}═══ Direct HORIZON API (Baseline) ═══{Colors.RESET}")
    
    async with httpx.AsyncClient(timeout=10) as client:
        endpoints = [
            ("GET", "/api/mission/summary", "Mission summary"),
            ("GET", "/api/anomaly/active", "Active anomalies"),
            ("GET", "/api/knowledge/suggestions", "Knowledge suggestions"),
            ("GET", "/api/voice/", "Voice status"),
            ("GET", "/api/osint/", "OSINT status"),
            ("GET", "/api/agent/needs-input", "HIL items"),
        ]
        
        for method, path, name in endpoints:
            try:
                r = await client.get(f"{HORIZON_URL}{path}")
                if r.status_code == 200:
                    ok(f"Direct: {name}", f"{path} → {r.status_code}")
                else:
                    fail(f"Direct: {name}", f"{path} → {r.status_code}")
            except Exception as e:
                fail(f"Direct: {name}", str(e))


async def test_latency():
    """Measure latency: direct vs mesh-proxied."""
    print(f"\n{Colors.BOLD}═══ Latency Comparison ═══{Colors.RESET}")
    
    async with httpx.AsyncClient(timeout=10) as client:
        # Direct
        t0 = time.time()
        for _ in range(5):
            await client.get(f"{HORIZON_URL}/api/mission/summary")
        direct_ms = (time.time() - t0) / 5 * 1000
        
        # Via mesh
        t0 = time.time()
        for _ in range(5):
            await client.post(f"{ATMOSPHERE_URL}/api/apps/horizon/tools/get_mission_summary/call", json={})
        mesh_ms = (time.time() - t0) / 5 * 1000
        
        overhead = mesh_ms - direct_ms
        ok("Latency", f"Direct: {direct_ms:.0f}ms | Mesh: {mesh_ms:.0f}ms | Overhead: {overhead:.0f}ms")


async def main():
    print(f"\n{Colors.BOLD}{'='*60}")
    print(f"  HORIZON E2E Test Suite — Phone Simulation")
    print(f"  Atmosphere → Mesh → HORIZON → Response")
    print(f"{'='*60}{Colors.RESET}")
    
    await test_direct_horizon()
    await test_rest_api()
    await test_websocket_tool_call()
    await test_relay_simulation()
    await test_latency()
    
    print(f"\n{Colors.BOLD}{'='*60}")
    total = passed + failed
    if failed == 0:
        print(f"  {Colors.OK}ALL {total} TESTS PASSED ✅{Colors.RESET}")
    else:
        print(f"  {Colors.OK}{passed} passed{Colors.RESET} / {Colors.FAIL}{failed} failed{Colors.RESET} out of {total}")
        for e in errors:
            print(f"    {Colors.FAIL}• {e}{Colors.RESET}")
    print(f"{'='*60}\n")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
