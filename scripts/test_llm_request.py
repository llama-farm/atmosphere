#!/usr/bin/env python3
"""
Test sending an LLM request through the mesh.
"""

import asyncio
import json
import time
import sys
import hashlib
import uuid

try:
    import websockets
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets


RELAY_URL = "wss://atmosphere-relay-production.up.railway.app"
MESH_ID = "0b82206b236bd66c"

TOKEN = {
    "mesh_id": "0b82206b236bd66c",
    "node_id": None,
    "issued_at": 1770448723,
    "expires_at": 1770535123,
    "capabilities": ["participant", "llm", "embeddings"],
    "issuer_id": "69ff1fa7cc80d0e0",
    "nonce": "a37b762068ba9e3fa7221df30dea1636",
    "signature": "P90lgbDDm980fvFPVcA34y/iUTXO2iBI6/P5cqtUnF0JOXQqISmiq5lJbjnQGWiMelQ1RuwZ4QQHD13sE3A1Aw=="
}

# Mac's node ID (the founder that has the LLM)
MAC_NODE_ID = "69ff1fa7cc80d0e0"

TEST_NODE_ID = hashlib.sha256(f"test-llm-{time.time()}".encode()).hexdigest()[:16]
TEST_NODE_NAME = "LLM-Test-Client"


async def test_llm_request():
    """Connect and send an LLM request."""
    ws_url = f"{RELAY_URL}/relay/{MESH_ID}"
    
    print(f"\n🔌 Connecting to: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as ws:
            print("✅ WebSocket connected!")
            
            # Join mesh
            join_msg = {
                "type": "join",
                "node_id": TEST_NODE_ID,
                "name": TEST_NODE_NAME,
                "token": TOKEN,
                "capabilities": [],
                "timestamp": time.time()
            }
            
            print(f"\n📤 Sending JOIN...")
            await ws.send(json.dumps(join_msg))
            
            # Wait for join confirmation
            joined = False
            for _ in range(5):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    data = json.loads(msg)
                    if data.get("type") == "joined":
                        print(f"✅ Joined mesh!")
                        joined = True
                        break
                    elif data.get("type") == "error":
                        print(f"❌ Error: {data.get('message')}")
                        return False
                except asyncio.TimeoutError:
                    continue
            
            if not joined:
                print("❌ Failed to join mesh")
                return False
            
            # Drain remaining messages (peers, capability announcements)
            for _ in range(5):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(msg)
                    print(f"   📨 {data.get('type', 'unknown')}")
                except asyncio.TimeoutError:
                    break
            
            # Now send LLM request
            request_id = str(uuid.uuid4())
            
            llm_request = {
                "type": "llm_request",
                "request_id": request_id,
                "target": MAC_NODE_ID,  # Send to Mac
                "payload": {
                    "messages": [
                        {"role": "user", "content": "Tell me a short joke about llamas."}
                    ],
                    "model": "auto",
                    "max_tokens": 100
                }
            }
            
            print(f"\n📤 Sending LLM request...")
            print(f"   Request ID: {request_id}")
            print(f"   Target: {MAC_NODE_ID}")
            print(f"   Prompt: 'Tell me a short joke about llamas.'")
            
            await ws.send(json.dumps(llm_request))
            
            # Wait for response
            print(f"\n📥 Waiting for LLM response (30 seconds)...")
            
            llm_response = None
            start_time = time.time()
            
            while time.time() - start_time < 30:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    msg_type = data.get("type", "unknown")
                    
                    print(f"\n   📨 Received: {msg_type}")
                    
                    if msg_type == "llm_response":
                        req_id = data.get("request_id", "")
                        if req_id == request_id:
                            llm_response = data
                            print(f"   ✅ Got LLM response!")
                            break
                        else:
                            print(f"   ⚠️  Response for different request: {req_id}")
                    
                    elif msg_type == "message":
                        payload = data.get("payload", {})
                        payload_type = payload.get("type", "unknown")
                        print(f"      Payload type: {payload_type}")
                        
                        if payload_type in ("llm_response", "chat_response"):
                            req_id = payload.get("request_id", "")
                            if req_id == request_id:
                                llm_response = payload
                                print(f"   ✅ Got LLM response (via message wrapper)!")
                                break
                    
                    elif msg_type == "error":
                        print(f"   ❌ Error: {data.get('message')}")
                    
                    elif msg_type == "ping":
                        await ws.send(json.dumps({"type": "pong"}))
                    
                    else:
                        print(f"      Data: {json.dumps(data)[:150]}...")
                        
                except asyncio.TimeoutError:
                    print("   (waiting...)")
            
            # Summary
            print("\n" + "="*60)
            print("LLM TEST SUMMARY")
            print("="*60)
            
            if llm_response:
                print("✅ LLM Response received!")
                
                # Try to extract the response text
                response_text = llm_response.get("response", "")
                if not response_text:
                    response_text = llm_response.get("content", "")
                if not response_text:
                    payload = llm_response.get("payload", {})
                    response_text = payload.get("response", payload.get("content", ""))
                
                if response_text:
                    print(f"\n📝 Response:\n{response_text}")
                else:
                    print(f"\n📋 Full response data:\n{json.dumps(llm_response, indent=2)}")
                
                return True
            else:
                print("❌ No LLM response received")
                print("\nPossible issues:")
                print("1. Mac not receiving the llm_request")
                print("2. Mac not routing to LlamaFarm")
                print("3. LlamaFarm not responding")
                print("4. Response not being sent back via relay")
                return False
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("="*60)
    print("ATMOSPHERE LLM REQUEST TEST")
    print("="*60)
    
    success = asyncio.run(test_llm_request())
    sys.exit(0 if success else 1)
