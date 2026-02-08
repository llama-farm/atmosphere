#!/usr/bin/env python3
"""
Simple test for relay connection.

Tests:
1. Connection to relay
2. Send/receive messages between two nodes
3. Reconnection after disconnect
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from atmosphere.transport import create_relay_connection, RelayMessage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TestNode:
    """Simple test node that can send/receive messages."""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.relay = None
        self.messages_received = []
    
    async def on_message(self, msg: RelayMessage):
        """Handle incoming messages."""
        logger.info(f"[{self.node_id}] Received from {msg.source_node}: {msg.payload}")
        self.messages_received.append(msg)
    
    async def connect(self):
        """Connect to relay."""
        logger.info(f"[{self.node_id}] Connecting to relay...")
        self.relay = await create_relay_connection(
            self.node_id,
            on_message=self.on_message
        )
        
        if self.relay.connected:
            logger.info(f"[{self.node_id}] ✓ Connected!")
        else:
            logger.error(f"[{self.node_id}] ✗ Failed to connect")
    
    async def send_to(self, target_node_id: str, message: dict):
        """Send message to another node."""
        logger.info(f"[{self.node_id}] Sending to {target_node_id}: {message}")
        success = await self.relay.send(target_node_id, message)
        
        if success:
            logger.info(f"[{self.node_id}] ✓ Sent")
        else:
            logger.error(f"[{self.node_id}] ✗ Send failed")
        
        return success
    
    async def disconnect(self):
        """Disconnect from relay."""
        if self.relay:
            await self.relay.disconnect()


async def test_basic_send_receive():
    """Test basic send/receive between two nodes."""
    logger.info("\n" + "="*60)
    logger.info("TEST: Basic Send/Receive")
    logger.info("="*60)
    
    # Create two test nodes
    node1 = TestNode("test-node-1")
    node2 = TestNode("test-node-2")
    
    try:
        # Connect both
        await node1.connect()
        await node2.connect()
        
        # Give connections time to stabilize
        await asyncio.sleep(1)
        
        # Node 1 sends to Node 2
        await node1.send_to("test-node-2", {"greeting": "Hello from Node 1!"})
        
        # Wait for message delivery
        await asyncio.sleep(2)
        
        # Check if Node 2 received it
        if node2.messages_received:
            logger.info("✓ TEST PASSED: Message received")
            msg = node2.messages_received[0]
            logger.info(f"  Source: {msg.source_node}")
            logger.info(f"  Payload: {msg.payload}")
        else:
            logger.error("✗ TEST FAILED: No message received")
        
        # Node 2 replies
        await node2.send_to("test-node-1", {"greeting": "Hello back from Node 2!"})
        
        # Wait for reply
        await asyncio.sleep(2)
        
        # Check if Node 1 received reply
        if node1.messages_received:
            logger.info("✓ TEST PASSED: Reply received")
            msg = node1.messages_received[0]
            logger.info(f"  Source: {msg.source_node}")
            logger.info(f"  Payload: {msg.payload}")
        else:
            logger.error("✗ TEST FAILED: No reply received")
        
    finally:
        await node1.disconnect()
        await node2.disconnect()


async def test_reconnection():
    """Test reconnection after disconnect."""
    logger.info("\n" + "="*60)
    logger.info("TEST: Reconnection")
    logger.info("="*60)
    
    node = TestNode("test-reconnect-node")
    
    try:
        # Initial connection
        await node.connect()
        logger.info("✓ Initial connection established")
        
        # Simulate disconnect
        await node.relay.disconnect()
        await asyncio.sleep(1)
        logger.info("  Disconnected")
        
        # Reconnect
        await node.connect()
        await asyncio.sleep(2)
        
        if node.relay.connected:
            logger.info("✓ TEST PASSED: Reconnection successful")
        else:
            logger.error("✗ TEST FAILED: Reconnection failed")
        
    finally:
        await node.disconnect()


async def main():
    """Run all tests."""
    logger.info("\n" + "="*60)
    logger.info("Atmosphere Relay - Simple Test Suite")
    logger.info("="*60)
    
    try:
        await test_basic_send_receive()
        await asyncio.sleep(2)
        
        await test_reconnection()
        
        logger.info("\n" + "="*60)
        logger.info("All tests complete!")
        logger.info("="*60)
        
    except KeyboardInterrupt:
        logger.info("\nTests interrupted by user")
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
