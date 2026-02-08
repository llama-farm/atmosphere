#!/usr/bin/env python3
"""
Test joining mesh with a valid token.
"""

import asyncio
import json
import time
import sys
import hashlib

try:
    import websockets
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets


RELAY_URL = "wss://atmosphere-relay-production.up.railway.app"
MESH_ID = "0b82206b236bd66c"

# Valid token from Mac
TOKEN = {
    "mesh_id": "0b82206b236bd66c",
    "node_id": None,
    "issued_at": 1770448591,
    "expires_at": 1770534991,
    "capabilities": ["participant", "llm", "embeddings"],
    "issuer_id": "69ff1fa7cc80d0e0",
    "nonce": "2eaaa9b048365d7897cff542a915c013",
    "signature": "EmcM+7oSCROrB5nWOP0aOCVlWbP9R/dV20BdZRbZvGxeVTUquGi4uKRjs+Skfzm+CS2/iv5Km/n1Gjvo+XXGAA=="
}

TEST_NODE_ID = hashlib.sha256(f"test-peer-{time.time()}".encode()).hexdigest()[:16]
TEST_NODE_NAME = "Test-Peer-Python"


async def connect_with_token():
    """Connect to relay with valid token."""
    ws_url = f"{RELAY_URL}/relay/{MESH_ID}"
    
    print(f"\n🔌 Connecting with token to: {ws_url}")
    print(f"   Node ID: {TEST_NODE_ID}")
    print(f"   Token issuer: {TOKEN['issuer_id']}")
    
    try:
        async with websockets.connect(ws_url) as ws:
            print("✅ WebSocket connected!")
            
            # Send join message WITH token
            join_msg = {
                "type": "join",
                "node_id": TEST_NODE_ID,
                "name": TEST_NODE_NAME,
                "token": TOKEN,
                "capabilities": [],
                "timestamp": time.time()
            }
            
            print(f"\n📤 Sending JOIN with token...")
            await ws.send(json.dumps(join_msg))
            
            # Listen for messages
            print("\n📥 Listening for messages (30 seconds)...")
            
            received_capabilities = False
            received_join_confirm = False
            peer_count = 0
            capabilities_list = []
            
            start_time = time.time()
            
            while time.time() - start_time < 45:  # 45 second timeout
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    data = json.loads(msg)
                    msg_type = data.get("type", "unknown")
                    
                    print(f"\n📨 Received: {msg_type}")
                    
                    if msg_type == "error":
                        code = data.get("code", "UNKNOWN")
                        message = data.get("message", "No message")
                        print(f"   ❌ Error: {code} - {message}")
                        break
                    
                    elif msg_type == "joined":
                        received_join_confirm = True
                        mesh_name = data.get("mesh", "unknown")
                        node_count = data.get("node_count", 0)
                        print(f"   ✅ Joined mesh '{mesh_name}' ({node_count} nodes)")
                    
                    elif msg_type == "peers":
                        peers = data.get("peers", [])
                        peer_count = len(peers)
                        print(f"   👥 Peers in mesh: {peer_count}")
                        for peer in peers:
                            name = peer.get("name", peer.get("node_id", "unknown")[:8])
                            print(f"      - {name}")
                    
                    elif msg_type == "peer_joined":
                        peer_id = data.get("node_id", "unknown")
                        peer_name = data.get("name", peer_id[:8])
                        print(f"   👋 Peer joined: {peer_name}")
                    
                    elif msg_type == "message":
                        from_node = data.get("from", "unknown")
                        payload = data.get("payload", {})
                        payload_type = payload.get("type", "unknown")
                        print(f"   📬 Message from {from_node}: {payload_type}")
                        
                        # Check for capability announcements
                        if payload_type in ("capability_announce", "capability.announce", "gossip.announce"):
                            received_capabilities = True
                            caps = payload.get("capabilities", [])
                            print(f"   🎯 CAPABILITY ANNOUNCEMENT: {len(caps)} capabilities!")
                            for cap in caps:
                                cap_id = cap.get("capability_id", cap.get("id", "unknown"))
                                label = cap.get("label", cap.get("name", ""))
                                capabilities_list.append({"id": cap_id, "label": label})
                                print(f"      - {cap_id}")
                                print(f"        Label: {label}")
                    
                    elif msg_type == "broadcast":
                        payload = data.get("payload", {})
                        payload_type = payload.get("type", "unknown")
                        print(f"   📢 Broadcast: {payload_type}")
                        
                        if payload_type in ("capability_announce", "capability.announce"):
                            received_capabilities = True
                            caps = payload.get("capabilities", [])
                            print(f"   🎯 CAPABILITIES: {len(caps)}")
                    
                    elif msg_type == "ping":
                        await ws.send(json.dumps({"type": "pong"}))
                        print("   🏓 Pong")
                    
                    else:
                        # Show first 200 chars of other messages
                        print(f"   📋 {json.dumps(data)[:200]}...")
                    
                except asyncio.TimeoutError:
                    print("   (waiting...)")
                    # After joining, send a test request to trigger capability broadcast
                    if received_join_confirm and not received_capabilities:
                        print("\n   📤 Requesting capability discovery...")
                        await ws.send(json.dumps({
                            "type": "broadcast",
                            "payload": {
                                "type": "capability.request",
                                "from": TEST_NODE_ID
                            }
                        }))
            
            # Summary
            print("\n" + "="*60)
            print("TEST SUMMARY")
            print("="*60)
            print(f"Join confirmed:       {'✅ YES' if received_join_confirm else '❌ NO'}")
            print(f"Peers discovered:     {peer_count}")
            print(f"Capabilities received: {'✅ YES' if received_capabilities else '❌ NO'}")
            
            if capabilities_list:
                print(f"\nCapabilities found ({len(capabilities_list)}):")
                for cap in capabilities_list:
                    print(f"  - {cap['id']}: {cap['label']}")
            
            if received_join_confirm and received_capabilities:
                print("\n🎉 FULL SUCCESS! Mesh connection and capability discovery working!")
                return True
            elif received_join_confirm:
                print("\n⚠️  PARTIAL SUCCESS: Joined mesh but no capabilities received.")
                print("   Issue: Mac's gossip may not be broadcasting to relay properly.")
                return False
            else:
                print("\n❌ FAILURE: Could not join mesh.")
                return False
    
    except websockets.exceptions.ConnectionClosed as e:
        print(f"❌ Connection closed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("="*60)
    print("ATMOSPHERE TOKEN JOIN TEST")
    print("="*60)
    
    success = asyncio.run(connect_with_token())
    sys.exit(0 if success else 1)
