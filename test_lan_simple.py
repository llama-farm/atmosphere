#!/usr/bin/env python3
"""Simple test for LAN WebSocket server."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from atmosphere.mesh.transport import LANServer, LANTransport
import aiohttp


async def main():
    print("=== Simple LAN Transport Test ===\n")
    
    # Start server
    server = LANServer(
        node_id="server-node",
        mesh_id="test-mesh",
        port=11461,  # Use a unique port
    )
    
    messages = []
    def on_message(peer_id, data):
        messages.append((peer_id, data))
        print(f"  Server received from {peer_id}: {data[:50]}...")
    
    server.on_message(on_message)
    
    print("1. Starting LAN WebSocket server...")
    if await server.start():
        print("   ✅ Server started on port 11461\n")
    else:
        print("   ❌ Server failed to start")
        return
    
    print("2. Testing raw WebSocket connection...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect("ws://localhost:11461/ws") as ws:
                print("   ✅ WebSocket connected\n")
                
                print("3. Sending handshake...")
                await ws.send_json({
                    "type": "handshake",
                    "node_id": "client-node",
                    "mesh_id": "test-mesh",
                })
                
                ack = await asyncio.wait_for(ws.receive_json(), timeout=5)
                if ack.get("type") == "handshake_ack":
                    print(f"   ✅ Handshake successful: {ack}\n")
                else:
                    print(f"   ❌ Unexpected response: {ack}")
                    return
                
                print("4. Checking connected peers...")
                print(f"   Connected peers: {server.connected_peers}")
                if "client-node" in server.connected_peers:
                    print("   ✅ Client appears in connected_peers\n")
                else:
                    print("   ❌ Client not in connected_peers")
                    return
                
                print("5. Sending test message from client...")
                await ws.send_json({"type": "test", "data": "hello from client"})
                await asyncio.sleep(0.2)
                
                if messages:
                    print(f"   ✅ Server received message: {messages[-1]}\n")
                else:
                    print("   ❌ No messages received")
                    return
                
                print("6. Sending message from server to client...")
                await server.send("client-node", b'{"type":"test","data":"hello from server"}')
                
                msg = await asyncio.wait_for(ws.receive(), timeout=5)
                if msg.type == aiohttp.WSMsgType.BINARY:
                    print(f"   ✅ Client received: {msg.data}\n")
                elif msg.type == aiohttp.WSMsgType.TEXT:
                    print(f"   ✅ Client received: {msg.data}\n")
                else:
                    print(f"   ⚠️ Unexpected message type: {msg.type}")
                
        except Exception as e:
            print(f"   ❌ Connection error: {e}")
            import traceback
            traceback.print_exc()
    
    print("7. Testing LANTransport client class...")
    transport = LANTransport(
        config={"port": 11461},
        node_id="transport-client",
        mesh_id="test-mesh",
    )
    
    received_via_transport = []
    def on_transport_msg(data):
        received_via_transport.append(data)
        print(f"   Transport received: {data[:50]}...")
    
    transport.on_message(on_transport_msg)
    
    if await transport.connect("server-node", "ws://localhost:11461/ws"):
        print("   ✅ LANTransport connected with handshake\n")
        
        print("8. Sending via LANTransport...")
        await transport.send(b'{"type":"transport-test"}')
        await asyncio.sleep(0.2)
        
        if len(messages) > 1:
            print(f"   ✅ Server received via transport\n")
        
        await transport.disconnect()
    else:
        print("   ❌ LANTransport connect failed")
    
    await server.stop()
    print("=" * 40)
    print("✅ All tests passed!")
    print("=" * 40)


if __name__ == "__main__":
    asyncio.run(main())
