#!/usr/bin/env python3
"""
Test relay.py structure and API.

This validates that the relay connection class is correctly structured
and can be instantiated. Actual connection tests require a running relay server.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from atmosphere.transport import RelayConnection, RelayMessage


def test_relay_message():
    """Test RelayMessage dataclass."""
    print("Testing RelayMessage structure...")
    
    msg = RelayMessage(
        target_node="node-2",
        source_node="node-1",
        payload={"hello": "world"},
        message_id="msg-123"
    )
    
    assert msg.target_node == "node-2"
    assert msg.source_node == "node-1"
    assert msg.payload == {"hello": "world"}
    assert msg.message_id == "msg-123"
    
    print("✓ RelayMessage works correctly")


def test_relay_connection_init():
    """Test RelayConnection can be initialized."""
    print("\nTesting RelayConnection initialization...")
    
    def dummy_callback(msg: RelayMessage):
        pass
    
    conn = RelayConnection(
        node_id="test-node",
        mesh_id="test-mesh",
        token="test-token",
        relay_url="wss://example.com",
        on_message=dummy_callback,
        max_reconnect_delay=30.0
    )
    
    assert conn.node_id == "test-node"
    assert conn.mesh_id == "test-mesh"
    assert conn.token == "test-token"
    assert conn.relay_url == "wss://example.com"
    assert conn.on_message == dummy_callback
    assert conn.max_reconnect_delay == 30.0
    assert conn.connected == False
    
    print("✓ RelayConnection initialized correctly")


def test_relay_connection_repr():
    """Test RelayConnection string representation."""
    print("\nTesting RelayConnection repr...")
    
    conn = RelayConnection(
        node_id="test-node",
        mesh_id="test-mesh",
        token="test-token"
    )
    
    repr_str = repr(conn)
    assert "test-node" in repr_str
    assert "disconnected" in repr_str
    
    print(f"✓ Repr works: {repr_str}")


def main():
    """Run all structure tests."""
    print("=" * 60)
    print("Atmosphere Relay - Structure Tests")
    print("=" * 60)
    
    try:
        test_relay_message()
        test_relay_connection_init()
        test_relay_connection_repr()
        
        print("\n" + "=" * 60)
        print("✓ All structure tests passed!")
        print("=" * 60)
        print("\nNote: Actual connection tests require:")
        print("  1. A running relay server")
        print("  2. Valid mesh_id and token")
        print("  3. Network connectivity")
        print("\nThe relay.py module is correctly structured and ready to use.")
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
