#!/usr/bin/env python3
"""
Simulate a mesh peer connecting to the Atmosphere relay.

This script mimics what the Android app does:
1. Parse an invite token
2. Connect to relay WebSocket
3. Send join message with token
4. Listen for capability announcements
5. Send a test LLM request
"""

import asyncio
import json
import time
import sys
import base64
import hashlib

try:
    import websockets
except ImportError:
    print("Installing websockets...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets


# Configuration
RELAY_URL = "wss://atmosphere-relay-production.up.railway.app"
MESH_ID = "0b82206b236bd66c"  # From the Mac's mesh.json

# Generate a fake node ID for this test peer
TEST_NODE_ID = hashlib.sha256(f"test-peer-{time.time()}".encode()).hexdigest()[:16]
TEST_NODE_NAME = "Test-Peer-Python"


async def connect_as_peer():
    """Connect to relay as a mesh peer."""
    ws_url = f"{RELAY_URL}/relay/{MESH_ID}"
    print(f"\n🔌 Connecting to: {ws_url}")
    print(f"   Node ID: {TEST_NODE_ID}")
    print(f"   Node Name: {TEST_NODE_NAME}")
    
    try:
        async with websockets.connect(ws_url) as ws:
            print("✅ WebSocket connected!")
            
            # Send join message (without token for now - testing if relay allows)
            join_msg = {
                "type": "join",
                "node_id": TEST_NODE_ID,
                "name": TEST_NODE_NAME,
                "capabilities": [],
                "timestamp": time.time()
            }
            
            print(f"\n📤 Sending JOIN: {json.dumps(join_msg)[:100]}...")
            await ws.send(json.dumps(join_msg))
            
            # Listen for messages
            print("\n📥 Waiting for messages...")
            
            received_capabilities = False
            message_count = 0
            
            while message_count < 20:  # Listen for up to 20 messages or timeout
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    message_count += 1
                    
                    data = json.loads(msg)
                    msg_type = data.get("type", "unknown")
                    
                    print(f"\n📨 [{message_count}] Received: {msg_type}")
                    
                    if msg_type == "error":
                        code = data.get("code", "UNKNOWN")
                        message = data.get("message", "No message")
                        print(f"   ❌ Error: {code} - {message}")
                        if code == "TOKEN_REQUIRED":
                            print("\n⚠️  Mesh requires a token to join!")
                            print("   This is expected - the mesh is secured.")
                            print("   Need to get a valid invite token from Mac.")
                            break
                    
                    elif msg_type == "joined":
                        mesh_name = data.get("mesh", "unknown")
                        node_count = data.get("node_count", 0)
                        print(f"   ✅ Joined mesh '{mesh_name}' ({node_count} nodes)")
                    
                    elif msg_type == "peers":
                        peers = data.get("peers", [])
                        print(f"   👥 Peers: {len(peers)}")
                        for peer in peers:
                            print(f"      - {peer.get('name', peer.get('node_id', 'unknown'))}")
                    
                    elif msg_type == "message":
                        # This is a forwarded message from another peer
                        from_node = data.get("from", "unknown")
                        payload = data.get("payload", {})
                        payload_type = payload.get("type", "unknown")
                        print(f"   📬 Message from {from_node}: {payload_type}")
                        
                        if payload_type in ("capability_announce", "capability.announce", "gossip.announce"):
                            received_capabilities = True
                            caps = payload.get("capabilities", [])
                            print(f"   🎯 CAPABILITY ANNOUNCEMENT: {len(caps)} capabilities!")
                            for cap in caps[:5]:
                                cap_id = cap.get("capability_id", cap.get("id", "unknown"))
                                label = cap.get("label", cap.get("name", ""))
                                print(f"      - {cap_id}: {label}")
                    
                    elif msg_type == "broadcast":
                        # Broadcast message
                        payload = data.get("payload", {})
                        payload_type = payload.get("type", "unknown")
                        print(f"   📢 Broadcast: {payload_type}")
                        print(f"      {json.dumps(payload)[:200]}...")
                        
                        if payload_type in ("capability_announce", "capability.announce"):
                            received_capabilities = True
                    
                    elif msg_type == "ping":
                        await ws.send(json.dumps({"type": "pong"}))
                        print("   🏓 Responded to ping")
                    
                    else:
                        print(f"   📋 Data: {json.dumps(data)[:200]}...")
                        
                except asyncio.TimeoutError:
                    print("   (timeout - no message)")
                    if message_count > 5:
                        break
            
            # Summary
            print("\n" + "="*50)
            print("SUMMARY")
            print("="*50)
            print(f"Messages received: {message_count}")
            print(f"Capabilities received: {'✅ YES' if received_capabilities else '❌ NO'}")
            
            if received_capabilities:
                print("\n🎉 SUCCESS! Capability announcements are flowing!")
            else:
                print("\n⚠️  No capability announcements received.")
                print("   Possible issues:")
                print("   1. Mac gossip not broadcasting to relay")
                print("   2. Relay not forwarding broadcasts")
                print("   3. Message format mismatch")
            
    except websockets.exceptions.ConnectionClosed as e:
        print(f"❌ Connection closed: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")


async def test_with_token(token_json: str):
    """Connect with a valid invite token."""
    try:
        token = json.loads(token_json)
    except json.JSONDecodeError:
        # Try base64 decode
        try:
            token_bytes = base64.urlsafe_b64decode(token_json)
            token = json.loads(token_bytes)
        except Exception as e:
            print(f"❌ Failed to parse token: {e}")
            return
    
    mesh_id = token.get("mesh_id", MESH_ID)
    ws_url = f"{RELAY_URL}/relay/{mesh_id}"
    
    print(f"\n🔌 Connecting with token to: {ws_url}")
    print(f"   Token mesh_id: {mesh_id}")
    
    try:
        async with websockets.connect(ws_url) as ws:
            print("✅ WebSocket connected!")
            
            # Send join message WITH token
            join_msg = {
                "type": "join",
                "node_id": TEST_NODE_ID,
                "name": TEST_NODE_NAME,
                "token": token,  # Include the full token
                "capabilities": [],
                "timestamp": time.time()
            }
            
            print(f"\n📤 Sending JOIN with token...")
            await ws.send(json.dumps(join_msg))
            
            # Listen for response
            for i in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    msg_type = data.get("type", "unknown")
                    
                    print(f"\n📨 Received: {msg_type}")
                    
                    if msg_type == "error":
                        print(f"   ❌ {data.get('code')}: {data.get('message')}")
                        break
                    elif msg_type == "joined":
                        print(f"   ✅ Successfully joined mesh!")
                        # Continue listening for capabilities
                    else:
                        print(f"   {json.dumps(data)[:200]}")
                        
                except asyncio.TimeoutError:
                    break
                    
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("="*50)
    print("ATMOSPHERE MESH PEER SIMULATOR")
    print("="*50)
    
    if len(sys.argv) > 1:
        # Token provided as argument
        token = sys.argv[1]
        print(f"\nUsing provided token...")
        asyncio.run(test_with_token(token))
    else:
        # Try to connect without token first
        print("\nAttempting connection without token (to test relay behavior)...")
        asyncio.run(connect_as_peer())
