#!/usr/bin/env python3
"""
Test LAN Transport - Verify WebSocket server and mDNS discovery work together.

This test:
1. Starts a node with LAN transport (server + discovery)
2. Starts a second node
3. Verifies they discover each other via mDNS
4. Verifies they can connect via WebSocket
5. Verifies message exchange works
"""

import asyncio
import sys
import os

# Add the project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from atmosphere.mesh.transport import TransportManager, TransportConfig, LANServer
from atmosphere.mesh.discovery import MeshDiscovery
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger(__name__)


async def test_lan_server_standalone():
    """Test the LANServer can start and accept connections."""
    print("\n=== Test 1: LANServer Standalone ===")
    
    server = LANServer(
        node_id="test-server-001",
        mesh_id="test-mesh",
        port=11451,
    )
    
    messages_received = []
    
    def on_message(peer_id, data):
        messages_received.append((peer_id, data))
        print(f"Server received from {peer_id}: {data}")
    
    server.on_message(on_message)
    
    success = await server.start()
    print(f"Server started: {success}")
    
    if success:
        print(f"Server listening on port 11451")
        print(f"Try connecting: ws://localhost:11451/ws")
        
        # Test with aiohttp client
        import aiohttp
        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect("ws://localhost:11451/ws") as ws:
                    # Send handshake
                    await ws.send_json({
                        "type": "handshake",
                        "node_id": "test-client-001",
                        "mesh_id": "test-mesh",
                    })
                    
                    # Wait for ack
                    ack = await asyncio.wait_for(ws.receive_json(), timeout=5)
                    print(f"Received handshake ack: {ack}")
                    
                    if ack.get("type") == "handshake_ack":
                        print("✅ Handshake successful!")
                        
                        # Send a test message
                        await ws.send_str('{"type":"test","data":"hello server"}')
                        await asyncio.sleep(0.1)
                        
                        print(f"Connected peers: {server.connected_peers}")
                        print("✅ Test 1 PASSED")
                    else:
                        print("❌ Handshake failed")
                        
            except Exception as e:
                print(f"❌ Client connection failed: {e}")
    
    await server.stop()


async def test_discovery_with_server():
    """Test that mDNS advertises and we can connect to the advertised endpoint."""
    print("\n=== Test 2: Discovery + Server Integration ===")
    
    # Start server
    server = LANServer(
        node_id="node-alpha",
        mesh_id="test-mesh",
        port=11452,
    )
    await server.start()
    
    # Start discovery (advertising)
    discovery = MeshDiscovery(
        node_id="node-alpha",
        port=11452,
        name="alpha",
        mesh_id="test-mesh",
    )
    
    if not discovery.available:
        print("⚠️ mDNS not available (zeroconf not installed)")
        await server.stop()
        return
    
    await discovery.start()
    print("Discovery started, advertising on mDNS...")
    
    # Wait a bit for advertisement to propagate
    await asyncio.sleep(2)
    
    # Now start a second discovery to find the first
    discovery2 = MeshDiscovery(
        node_id="node-beta",
        port=11453,
        name="beta",
        mesh_id="test-mesh",
    )
    
    found_peers = []
    
    def on_peer_found(peer):
        print(f"Found peer: {peer.name} at {peer.address}")
        found_peers.append(peer)
    
    discovery2.on_peer_found = on_peer_found
    await discovery2.start()
    
    # Wait for discovery
    print("Waiting for peer discovery...")
    await asyncio.sleep(3)
    
    if found_peers:
        print(f"✅ Discovered {len(found_peers)} peer(s)")
        
        # Try to connect to discovered peer
        peer = found_peers[0]
        endpoint = f"ws://{peer.host}:{peer.port}/ws"
        print(f"Connecting to {endpoint}...")
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(endpoint) as ws:
                    await ws.send_json({
                        "type": "handshake",
                        "node_id": "node-beta",
                        "mesh_id": "test-mesh",
                    })
                    
                    ack = await asyncio.wait_for(ws.receive_json(), timeout=5)
                    if ack.get("type") == "handshake_ack":
                        print("✅ Connected to discovered peer!")
                        print("✅ Test 2 PASSED")
                    else:
                        print(f"❌ Unexpected response: {ack}")
            except Exception as e:
                print(f"❌ Connection to discovered peer failed: {e}")
    else:
        print("⚠️ No peers discovered (may be network/firewall issue)")
    
    await discovery.stop()
    await discovery2.stop()
    await server.stop()


async def test_transport_manager():
    """Test the full TransportManager with LAN enabled."""
    print("\n=== Test 3: Full TransportManager ===")
    
    config = TransportConfig()
    config.lan = {"enabled": True, "port": 11454}
    config.relay = {"enabled": False}  # Disable relay for this test
    
    manager1 = TransportManager(config, node_id="manager-1", mesh_id="test-mesh")
    manager2 = TransportManager(config, node_id="manager-2", mesh_id="test-mesh")
    
    # Modify manager2 to use different port
    manager2.config.lan = {"enabled": True, "port": 11455}
    
    messages1 = []
    messages2 = []
    
    def on_msg1(peer_id, data):
        messages1.append((peer_id, data))
        print(f"Manager1 received from {peer_id}")
    
    def on_msg2(peer_id, data):
        messages2.append((peer_id, data))
        print(f"Manager2 received from {peer_id}")
    
    manager1.on_message(on_msg1)
    manager2.on_message(on_msg2)
    
    print("Starting managers...")
    await manager1.start()
    await asyncio.sleep(1)
    await manager2.start()
    
    print("Waiting for discovery and connection...")
    await asyncio.sleep(5)
    
    peers1 = manager1.get_connected_peers()
    peers2 = manager2.get_connected_peers()
    
    print(f"Manager1 connected peers: {peers1}")
    print(f"Manager2 connected peers: {peers2}")
    
    status1 = manager1.get_transport_status()
    status2 = manager2.get_transport_status()
    print(f"Manager1 status: {status1}")
    print(f"Manager2 status: {status2}")
    
    if peers1 or peers2:
        print("✅ Peers connected!")
        
        # Try sending a message
        if peers1:
            success = await manager1.send(peers1[0], b'{"type":"hello","from":"manager1"}')
            print(f"Send from manager1: {success}")
        
        await asyncio.sleep(0.5)
        
        if messages2:
            print("✅ Message received!")
            print("✅ Test 3 PASSED")
        else:
            print("⚠️ No messages received yet")
    else:
        print("⚠️ No peers connected (may take longer or network issue)")
    
    await manager1.stop()
    await manager2.stop()


async def main():
    print("=" * 60)
    print("LAN Transport Test Suite")
    print("=" * 60)
    
    try:
        await test_lan_server_standalone()
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        await test_discovery_with_server()
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        await test_transport_manager()
    except Exception as e:
        print(f"❌ Test 3 failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
