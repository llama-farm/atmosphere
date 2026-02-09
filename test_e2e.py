#!/usr/bin/env python3
"""
End-to-end test: Atmosphere mesh + HORIZON tools/functions

Tests:
1. SDK auto-discovery from OpenAPI spec
2. Mesh connection with relay protocol  
3. Tool listing via REST API
4. Tool invocation via REST API (mesh proxy → HORIZON HTTP)
5. Direct SDK tool calling
6. WebSocket tool_call message routing

Prereqs:
  - Atmosphere server on :11451
  - HORIZON server on :8074
"""

import asyncio
import json
import sys
import httpx
from websockets.asyncio.client import connect

ATMOSPHERE_URL = "http://localhost:11451"
HORIZON_URL = "http://localhost:8074"
MESH_WS = "ws://localhost:11451/api/mesh/ws"

PASS = "✅"
FAIL = "❌"
results = []

def report(name: str, passed: bool, detail: str = ""):
    status = PASS if passed else FAIL
    results.append((name, passed))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))

async def run_tests():
    print("\n" + "=" * 60)
    print("  ATMOSPHERE E2E TEST SUITE")
    print("=" * 60)
    
    # ─── 1. Health Checks ───
    print("\n🏥 Health Checks")
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{ATMOSPHERE_URL}/health", timeout=5)
            report("Atmosphere health", r.status_code == 200, r.text[:50])
        except Exception as e:
            report("Atmosphere health", False, str(e))
            print("  ⛔ Atmosphere not running — aborting")
            return
        
        try:
            r = await client.get(f"{HORIZON_URL}/health", timeout=5)
            report("HORIZON health", r.status_code == 200, r.text[:50])
        except Exception as e:
            report("HORIZON health", False, str(e))
            print("  ⛔ HORIZON not running — aborting")
            return

    # ─── 2. SDK Auto-Discovery ───
    print("\n🔍 SDK Auto-Discovery (OpenAPI → Tools)")
    from atmosphere.sdk import AtmosphereApp
    app = AtmosphereApp(
        name="horizon-test",
        description="E2E test",
        mesh_url=ATMOSPHERE_URL,
        app_base_url=HORIZON_URL
    )
    await app.register_from_openapi()
    cap_count = len(app._capabilities)
    tool_count = sum(len(c.tools) for c in app._capabilities)
    report("Capabilities discovered", cap_count > 0, f"{cap_count} capabilities")
    report("Tools extracted", tool_count > 0, f"{tool_count} tools total")
    
    # Check specific tools exist
    all_tools = {}
    for c in app._capabilities:
        all_tools.update(c.tools)
    
    key_tools = ["get_mission_summary", "run_anomaly_scan", "query_knowledge", "search_osint"]
    for tool_name in key_tools:
        report(f"Tool '{tool_name}' found", tool_name in all_tools)

    # Check tool has parameters
    if "query_knowledge" in all_tools:
        tool = all_tools["query_knowledge"]
        has_params = len(tool.parameters) > 0
        report("Tool has parameters", has_params, 
               f"{len(tool.parameters)} params: {[p.name for p in tool.parameters]}")

    # ─── 3. Mesh Connection ───
    print("\n🌐 Mesh Connection (Relay Protocol)")
    await app.start()
    report("SDK mesh connect", app._client.is_connected)
    await asyncio.sleep(1)

    # ─── 4. Direct SDK Tool Calling ───
    print("\n🔧 Direct SDK Tool Calls (SDK → HTTP → HORIZON)")
    
    # Mission summary
    try:
        result = await app.call_tool("get_mission_summary")
        has_callsign = "callsign" in str(result)
        report("get_mission_summary", has_callsign, 
               f"callsign={result.get('callsign', '?')}, route={result.get('route', '?')}")
    except Exception as e:
        report("get_mission_summary", False, str(e)[:80])

    # Anomaly scan
    try:
        result = await app.call_tool("run_anomaly_scan")
        report("run_anomaly_scan", result is not None, f"Got response: {str(result)[:60]}")
    except Exception as e:
        report("run_anomaly_scan", False, str(e)[:80])

    # Active anomalies
    try:
        result = await app.call_tool("get_active_anomalies")
        report("get_active_anomalies", "by_severity" in str(result), str(result)[:80])
    except Exception as e:
        report("get_active_anomalies", False, str(e)[:80])

    # Knowledge query
    try:
        result = await app.call_tool("query_knowledge", 
            question="What is the maximum cargo floor loading for a C-17?",
            include_context=True)
        has_answer = "answer" in str(result)
        report("query_knowledge", has_answer, 
               f"confidence={result.get('confidence', '?')}, answer={str(result.get('answer', ''))[:60]}")
    except Exception as e:
        report("query_knowledge", False, str(e)[:80])

    # OSINT search
    try:
        result = await app.call_tool("search_osint")
        has_items = "items" in str(result)
        item_count = len(result.get("items", [])) if isinstance(result, dict) else 0
        report("search_osint", has_items, f"{item_count} intel items")
    except Exception as e:
        report("search_osint", False, str(e)[:80])

    # Voice status
    try:
        result = await app.call_tool("get_voice_status")
        report("get_voice_status", result is not None, str(result)[:60])
    except Exception as e:
        report("get_voice_status", False, str(e)[:80])

    # ─── 5. REST API Tool Listing ───
    print("\n📋 REST API Tool Listing")
    async with httpx.AsyncClient() as client:
        try:
            # List apps
            r = await client.get(f"{ATMOSPHERE_URL}/api/apps", timeout=5)
            report("GET /api/apps", r.status_code == 200, f"{len(r.json().get('apps', []))} apps")
        except Exception as e:
            report("GET /api/apps", False, str(e)[:80])

        try:
            # List tools for horizon
            r = await client.get(f"{ATMOSPHERE_URL}/api/apps/horizon-test/tools", timeout=5)
            if r.status_code == 200:
                tools = r.json().get("tools", [])
                report("GET /api/apps/{app}/tools", True, f"{len(tools)} tools listed")
            else:
                report("GET /api/apps/{app}/tools", False, f"HTTP {r.status_code}: {r.text[:60]}")
        except Exception as e:
            report("GET /api/apps/{app}/tools", False, str(e)[:80])

    # ─── 6. WebSocket tool_call ───
    print("\n🔌 WebSocket Tool Call (mesh peer → tool_call → response)")
    try:
        ws = await connect(MESH_WS)
        await ws.send(json.dumps({
            "type": "join",
            "node_id": "test-peer-e2e",
            "name": "e2e-tester"
        }))
        # Read joined + peers
        joined = json.loads(await ws.recv())
        peers = json.loads(await ws.recv())
        report("WS join", joined.get("type") == "joined", f"mesh={joined.get('mesh')}")
        
        # Drain any pending gossip messages first
        import time
        await asyncio.sleep(1)
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
        except (asyncio.TimeoutError, Exception):
            pass
        
        # Try sending a tool_call (this goes through AppMeshManager)
        await ws.send(json.dumps({
            "type": "tool_call",
            "request_id": "test-001",
            "app": "horizon-test",
            "tool": "get_mission_summary",
            "params": {}
        }))
        
        # Wait for response (skip gossip/capability messages)
        try:
            found = False
            for _ in range(10):  # Max 10 messages to skip
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                resp_data = json.loads(response)
                rtype = resp_data.get("type", "")
                # Check for tool response (direct or wrapped in message)
                if rtype in ["tool_response", "app_response"]:
                    report("WS tool_call → response", True, f"type={rtype}, {str(resp_data)[:60]}")
                    found = True
                    break
                elif rtype == "message":
                    payload = resp_data.get("payload", {})
                    ptype = payload.get("type", "")
                    if ptype in ["tool_response", "app_response"]:
                        report("WS tool_call → response", True, f"wrapped type={ptype}, {str(payload)[:60]}")
                        found = True
                        break
                # Skip gossip, capability_announce, etc.
            if not found:
                report("WS tool_call → response", False, "No tool_response in 10 messages")
        except asyncio.TimeoutError:
            report("WS tool_call → response", False, "Timeout (5s)")
        
        await ws.close()
    except Exception as e:
        report("WS tool_call", False, str(e)[:80])

    # ─── Cleanup ───
    await app.stop()

    # ─── Summary ───
    print("\n" + "=" * 60)
    passed = sum(1 for _, p in results if p)
    total = len(results)
    failed = total - passed
    print(f"  Results: {passed}/{total} passed" + (f", {failed} FAILED" if failed else " — ALL PASSED! 🎉"))
    print("=" * 60 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
