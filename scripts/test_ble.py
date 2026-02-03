#!/usr/bin/env python3
"""
Test script for Atmosphere BLE Transport.

Usage:
    python scripts/test_ble.py [--name NODE_NAME]
"""

import asyncio
import argparse
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from atmosphere.transport.ble_mac import (
    BleTransport, 
    BleMessage, 
    MessageType,
    MESH_SERVICE_UUID,
    BLEAK_AVAILABLE,
    BLESS_AVAILABLE
)


def on_message(msg: BleMessage):
    """Handle incoming messages."""
    try:
        data = msg.decode_cbor()
        print(f"📨 Message from {msg.source_id}: {data}")
    except:
        print(f"📨 Raw message from {msg.source_id}: {msg.payload[:50]}...")


def on_peer_discovered(info):
    """Handle peer discovery."""
    print(f"🔵 Peer discovered: {info.name} ({info.node_id})")
    print(f"   Platform: {info.platform}")
    print(f"   Capabilities: {info.capabilities}")


def on_peer_lost(peer_id: str):
    """Handle peer disconnection."""
    print(f"🔴 Peer lost: {peer_id}")


async def main():
    parser = argparse.ArgumentParser(description="Atmosphere BLE Transport Test")
    parser.add_argument("--name", default=None, help="Node name")
    parser.add_argument("--scan-only", action="store_true", help="Only scan, don't advertise")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("\n" + "=" * 60)
    print("   Atmosphere BLE Transport Test")
    print("=" * 60)
    print(f"\n📦 Dependencies:")
    print(f"   - bleak (BLE client): {'✅ Available' if BLEAK_AVAILABLE else '❌ Not installed'}")
    print(f"   - bless (GATT server): {'✅ Available' if BLESS_AVAILABLE else '⚠️  Not installed (peripheral mode disabled)'}")
    
    if not BLEAK_AVAILABLE:
        print("\n❌ bleak is required. Install with: pip install bleak")
        return
    
    print(f"\n🔧 Configuration:")
    print(f"   Service UUID: {MESH_SERVICE_UUID}")
    
    transport = BleTransport(node_name=args.name)
    
    transport.on_message = on_message
    transport.on_peer_discovered = on_peer_discovered
    transport.on_peer_lost = on_peer_lost
    
    try:
        await transport.start()
        
        print(f"\n🌐 BLE Transport running:")
        print(f"   Node name: {transport.node_name}")
        print(f"   Node ID: {transport.node_id}")
        print(f"   Capabilities: {transport.capabilities}")
        
        print("\n📡 Scanning for Atmosphere nodes...")
        print("   Press Ctrl+C to stop\n")
        
        # Periodic status and hello broadcasts
        iteration = 0
        while True:
            await asyncio.sleep(10)
            iteration += 1
            
            peers = transport.get_peers()
            print(f"\n📊 Status (iteration {iteration}):")
            print(f"   Connected peers: {len(peers)}")
            
            for peer in peers:
                print(f"   - {peer.name} ({peer.node_id})")
                print(f"     Platform: {peer.platform}, RSSI: {peer.rssi}")
            
            # Send periodic hello
            await transport.broadcast_hello()
            print("   📤 Broadcasted HELLO")
    
    except KeyboardInterrupt:
        print("\n\n⏹️ Stopping...")
    
    finally:
        await transport.stop()
        print("✅ BLE transport stopped")


if __name__ == "__main__":
    asyncio.run(main())
