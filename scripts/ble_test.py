#!/usr/bin/env python3
"""
BLE Mesh Test Script

Run this on Mac while Android app has BLE enabled.
Usage: python3 scripts/ble_test.py
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

from atmosphere.transport.ble_mac import BleTransport, MESH_SERVICE_UUID

async def main():
    print("=" * 60)
    print("🔵 Atmosphere BLE Mesh Test")
    print("=" * 60)
    print(f"Service UUID: {MESH_SERVICE_UUID}")
    print()
    
    transport = BleTransport(
        node_name='Atmosphere-Mac',
        capabilities=['relay', 'llm', 'embeddings']
    )
    
    discovered_peers = {}
    
    def on_peer_discovered(info):
        if info.nodeId not in discovered_peers:
            print(f"\n🎉 NEW PEER DISCOVERED!")
            print(f"   Name:    {info.name}")
            print(f"   Node ID: {info.nodeId}")
            print(f"   RSSI:    {info.rssi} dBm")
            if info.capabilities:
                print(f"   Caps:    {', '.join(info.capabilities)}")
            discovered_peers[info.nodeId] = info
            print()
    
    def on_peer_lost(peer_id):
        print(f"🔴 Peer lost: {peer_id}")
        if peer_id in discovered_peers:
            del discovered_peers[peer_id]
    
    def on_message(msg):
        print(f"📨 Message from {msg.source_id}: {len(msg.payload)} bytes")
        try:
            print(f"   Payload: {msg.payload[:100]}")
        except:
            pass
    
    transport.on_peer_discovered = on_peer_discovered
    transport.on_peer_lost = on_peer_lost
    transport.on_message = on_message
    
    print("Starting BLE transport...")
    await transport.start()
    print(f"✅ Running as: {transport.node_name} ({transport.node_id})")
    print()
    print("📱 Now start BLE on Android:")
    print("   App → Test tab → Connectivity → BLE Mesh → Start")
    print()
    print("Press Ctrl+C to stop")
    print("-" * 60)
    
    try:
        tick = 0
        while True:
            await asyncio.sleep(5)
            tick += 5
            peers = transport.get_peers()
            status = f"[{tick}s] Peers: {len(peers)}"
            if peers:
                status += " → " + ", ".join(p.name or p.node_id[:8] for p in peers)
            print(status)
    except KeyboardInterrupt:
        print("\n\nStopping...")
    
    await transport.stop()
    print("Done!")
    
    if discovered_peers:
        print(f"\n📊 Total peers discovered: {len(discovered_peers)}")
        for p in discovered_peers.values():
            print(f"   - {p.name} ({p.nodeId})")

if __name__ == "__main__":
    asyncio.run(main())
