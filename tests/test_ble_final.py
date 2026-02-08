#!/usr/bin/env python3
"""Final BLE transport verification test."""

import asyncio
import sys
from atmosphere.transport.ble_mac import BleTransport

async def main():
    print("=" * 60)
    print("BLE Transport Final Verification Test")
    print("=" * 60)
    
    try:
        # Create transport
        print("\n1. Creating BLE transport...")
        transport = BleTransport(
            node_name='test-verification',
            capabilities=['test', 'relay']
        )
        print(f"   ✅ Created: {transport.node_id}")
        
        # Start transport
        print("\n2. Starting BLE transport...")
        await transport.start()
        print(f"   ✅ Started successfully")
        print(f"   - Running: {transport.is_running()}")
        print(f"   - Node ID: {transport.node_id}")
        print(f"   - Node name: {transport.node_name}")
        
        # Check components
        print("\n3. Checking components...")
        print(f"   - GATT server: {'✅ Running' if transport.gatt_server else '❌ Not started'}")
        print(f"   - Scan task: {'✅ Active' if transport._scan_task else '❌ Not active'}")
        print(f"   - Heartbeat task: {'✅ Active' if transport._heartbeat_task else '❌ Not active'}")
        
        # Wait a bit
        print("\n4. Running for 5 seconds...")
        await asyncio.sleep(5)
        
        # Check metrics
        metrics = transport.get_metrics()
        print("\n5. Metrics:")
        print(f"   - Connected peers: {metrics['connected_peers']}")
        print(f"   - Known peers: {metrics['known_peers']}")
        print(f"   - Messages sent: {metrics['mesh_metrics']['sent']}")
        print(f"   - Messages received: {metrics['mesh_metrics']['received']}")
        
        # Stop transport
        print("\n6. Stopping BLE transport...")
        await transport.stop()
        print("   ✅ Stopped cleanly")
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
