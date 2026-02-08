#!/usr/bin/env python3
"""
Test script for BLE pairing functionality.

This script tests:
1. BLE transport initialization
2. GATT server notify mechanism
3. Pairing protocol flow
4. Credential exchange

Usage:
    python scripts/test_ble_pairing.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from atmosphere.transport.ble_mac import BleTransport
from atmosphere.transport.ble_pairing import (
    BlePairingManager, 
    PairingCredentials,
    integrate_pairing_with_transport
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_ble_transport():
    """Test BLE transport initialization and basic functionality."""
    logger.info("=" * 60)
    logger.info("Test 1: BLE Transport Initialization")
    logger.info("=" * 60)
    
    transport = BleTransport(
        node_name="Test-Mac-Node",
        capabilities=["llm", "rag", "vision"]
    )
    
    # Set up message handler
    def on_message(msg):
        logger.info(f"📨 Received message from {msg.source_id}: {len(msg.payload)} bytes")
    
    def on_peer_discovered(peer_info):
        logger.info(f"🔵 Discovered peer: {peer_info.name} ({peer_info.node_id}) at {peer_info.rssi} dBm")
    
    transport.on_message = on_message
    transport.on_peer_discovered = on_peer_discovered
    
    try:
        await transport.start()
        logger.info(f"✅ BLE transport started: {transport.node_name} ({transport.node_id})")
        
        # Wait for discovery
        logger.info("Scanning for peers (30 seconds)...")
        await asyncio.sleep(30)
        
        # Show discovered peers
        peers = transport.get_peers()
        logger.info(f"📊 Discovered {len(peers)} peers:")
        for peer in peers:
            logger.info(f"  - {peer.name} ({peer.node_id}): {peer.rssi} dBm, {peer.platform}")
        
        # Test heartbeat
        logger.info("Sending heartbeat...")
        await transport.broadcast_hello()
        
        # Test metrics
        metrics = transport.get_metrics()
        logger.info(f"📈 Metrics: {metrics}")
        
        await transport.stop()
        logger.info("✅ BLE transport stopped cleanly")
        return True
        
    except Exception as e:
        logger.error(f"❌ BLE transport test failed: {e}", exc_info=True)
        return False


async def test_pairing_protocol():
    """Test BLE proximity pairing protocol."""
    logger.info("=" * 60)
    logger.info("Test 2: BLE Pairing Protocol")
    logger.info("=" * 60)
    
    # Create transport
    transport = BleTransport(
        node_name="Mac-Test-Pairing",
        capabilities=["llm"]
    )
    
    # Create credentials
    local_creds = PairingCredentials(
        node_id="test-mac-node-001",
        node_name="Mac Test Node",
        mesh_id="test-mesh-123",
        relay_token="test-relay-token",
        relay_url="wss://relay.atmosphere.dev",
        local_endpoints=[{"ip": "192.168.1.100", "port": 11451}],
        capabilities=["llm", "vision"]
    )
    
    # Track pairing events
    pairing_events = {
        "code_displayed": False,
        "code_value": None,
        "peer_name": None,
        "completed": False,
        "failed": False
    }
    
    def on_code_display(code: str, peer_name: str):
        logger.info(f"🔐 PAIRING CODE: {code}")
        logger.info(f"   Peer: {peer_name}")
        pairing_events["code_displayed"] = True
        pairing_events["code_value"] = code
        pairing_events["peer_name"] = peer_name
    
    def on_pairing_complete(peer_creds: PairingCredentials):
        logger.info(f"✅ PAIRING COMPLETE!")
        logger.info(f"   Peer: {peer_creds.node_name} ({peer_creds.node_id})")
        logger.info(f"   Mesh: {peer_creds.mesh_id}")
        logger.info(f"   Capabilities: {peer_creds.capabilities}")
        pairing_events["completed"] = True
    
    def on_pairing_failed(peer_id: str, reason: str):
        logger.error(f"❌ PAIRING FAILED: {peer_id} - {reason}")
        pairing_events["failed"] = True
    
    # Create pairing manager
    pairing_manager = BlePairingManager(
        local_credentials=local_creds,
        on_code_display=on_code_display,
        on_pairing_complete=on_pairing_complete,
        on_pairing_failed=on_pairing_failed
    )
    
    # Integrate with transport
    integrate_pairing_with_transport(transport, pairing_manager)
    
    try:
        # Start transport and pairing
        await transport.start()
        pairing_manager.start()
        
        logger.info("✅ Pairing manager started")
        logger.info("📱 Waiting for pairing requests from nearby devices...")
        logger.info("   (Have another device initiate pairing)")
        
        # Wait for pairing activity (60 seconds)
        await asyncio.sleep(60)
        
        # Report results
        logger.info("=" * 60)
        logger.info("Pairing Test Results:")
        logger.info(f"  Code displayed: {pairing_events['code_displayed']}")
        if pairing_events['code_displayed']:
            logger.info(f"  Code value: {pairing_events['code_value']}")
            logger.info(f"  Peer name: {pairing_events['peer_name']}")
        logger.info(f"  Completed: {pairing_events['completed']}")
        logger.info(f"  Failed: {pairing_events['failed']}")
        logger.info("=" * 60)
        
        # Cleanup
        pairing_manager.stop()
        await transport.stop()
        
        return pairing_events["completed"]
        
    except Exception as e:
        logger.error(f"❌ Pairing test failed: {e}", exc_info=True)
        return False


async def test_gatt_notify():
    """Test GATT server notification mechanism."""
    logger.info("=" * 60)
    logger.info("Test 3: GATT Server Notify")
    logger.info("=" * 60)
    
    transport = BleTransport(
        node_name="Notify-Test-Mac",
        capabilities=["test"]
    )
    
    try:
        await transport.start()
        logger.info("✅ Transport started with GATT server")
        
        # Test sending notifications
        test_data = b"Test notification data - this should be chunked if over 182 bytes" * 5
        logger.info(f"📤 Sending test data: {len(test_data)} bytes")
        
        # This will use the fixed notify mechanism
        await transport.broadcast(test_data)
        logger.info("✅ Notification sent successfully")
        
        # Wait a bit for any responses
        await asyncio.sleep(5)
        
        await transport.stop()
        return True
        
    except Exception as e:
        logger.error(f"❌ GATT notify test failed: {e}", exc_info=True)
        return False


async def main():
    """Run all tests."""
    logger.info("🧪 BLE Pairing Test Suite")
    logger.info("=" * 60)
    
    results = {}
    
    # Test 1: BLE Transport
    logger.info("\n")
    results["transport"] = await test_ble_transport()
    
    # Test 2: Pairing Protocol
    logger.info("\n")
    results["pairing"] = await test_pairing_protocol()
    
    # Test 3: GATT Notify
    logger.info("\n")
    results["gatt_notify"] = await test_gatt_notify()
    
    # Summary
    logger.info("\n")
    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"  {test:20s}: {status}")
    logger.info("=" * 60)
    
    all_passed = all(results.values())
    if all_passed:
        logger.info("🎉 All tests passed!")
        sys.exit(0)
    else:
        logger.error("❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
