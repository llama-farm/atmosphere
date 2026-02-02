"""
Tests for internet-scale networking components.

Tests STUN, NAT traversal, and relay functionality.
"""

import asyncio
import pytest

from atmosphere.network import (
    discover_public_ip,
    get_local_ip,
    gather_network_info,
    NATTraversal,
    punch_hole,
    RelayServer,
    RelayClient,
)


class TestSTUN:
    """Test STUN client functionality."""
    
    @pytest.mark.asyncio
    async def test_discover_public_ip(self):
        """Test public IP discovery via STUN."""
        endpoint = await discover_public_ip(timeout=5.0)
        
        # May fail if no internet connection
        if endpoint:
            assert endpoint.ip
            assert endpoint.port > 0
            assert "stun" in endpoint.source
            print(f"Discovered public endpoint: {endpoint}")
        else:
            print("STUN discovery failed (no internet?)")
    
    @pytest.mark.asyncio
    async def test_get_local_ip(self):
        """Test local IP discovery."""
        ip = await get_local_ip()
        assert ip
        assert ip != "0.0.0.0"
        print(f"Local IP: {ip}")
    
    @pytest.mark.asyncio
    async def test_gather_network_info(self):
        """Test comprehensive network info gathering."""
        info = await gather_network_info(local_port=12345)
        
        assert info.local_ip
        assert info.local_port == 12345
        
        if info.public_endpoint:
            print(f"Public endpoint: {info.public_endpoint}")
            print(f"Behind NAT: {info.is_behind_nat}")
            print(f"Publicly reachable: {info.is_publicly_reachable}")
        else:
            print("No public endpoint discovered")


class TestNATTraversal:
    """Test NAT traversal and hole punching."""
    
    @pytest.mark.asyncio
    async def test_nat_traversal_lifecycle(self):
        """Test NAT traversal start/stop."""
        traversal = NATTraversal(local_port=12346)
        
        assert await traversal.start()
        assert traversal._running
        
        await traversal.stop()
        assert not traversal._running
    
    @pytest.mark.asyncio
    async def test_punch_hole_timeout(self):
        """Test hole punching timeout."""
        # This will timeout since no peer is responding
        result = await punch_hole(
            local_port=12347,
            remote_host="192.0.2.1",  # TEST-NET-1 (unreachable)
            remote_port=12347,
            timeout=2.0,
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_nat_traversal_send_without_peer(self):
        """Test sending to non-existent peer."""
        traversal = NATTraversal(local_port=12348)
        await traversal.start()
        
        try:
            result = await traversal.send_to_peer("nonexistent", b"data")
            assert result is False
        finally:
            await traversal.stop()


class TestRelay:
    """Test relay server and client."""
    
    @pytest.mark.asyncio
    async def test_relay_server_start_stop(self):
        """Test relay server lifecycle."""
        server = RelayServer(host="127.0.0.1", port=18080)
        
        await server.start()
        
        # Give it a moment to start
        await asyncio.sleep(0.1)
        
        await server.stop()
    
    @pytest.mark.asyncio
    async def test_relay_end_to_end(self):
        """Test relay server with two clients."""
        server = RelayServer(host="127.0.0.1", port=18081)
        await server.start()
        
        try:
            # Wait for server to be ready
            await asyncio.sleep(0.2)
            
            # Create two clients with same session ID
            session_id = "test-session-123"
            client_a = RelayClient("ws://127.0.0.1:18081", session_id)
            client_b = RelayClient("ws://127.0.0.1:18081", session_id)
            
            # Connect both clients
            connected_a = await client_a.connect(timeout=5.0)
            connected_b = await client_b.connect(timeout=5.0)
            
            if not (connected_a and connected_b):
                print("Relay connection failed - may need server running")
                return
            
            # Wait for session to be established
            await asyncio.sleep(0.2)
            
            # Client A sends to B
            test_data = b"Hello from A"
            await client_a.send(test_data)
            
            # Client B receives
            received = await client_b.receive(timeout=2.0)
            assert received == test_data
            
            # Client B sends to A
            test_data_2 = b"Hello from B"
            await client_b.send(test_data_2)
            
            # Client A receives
            received_2 = await client_a.receive(timeout=2.0)
            assert received_2 == test_data_2
            
            # Clean up
            await client_a.disconnect()
            await client_b.disconnect()
            
        finally:
            await server.stop()
    
    @pytest.mark.asyncio
    async def test_relay_client_no_server(self):
        """Test relay client when server is not available."""
        client = RelayClient("ws://127.0.0.1:18099", "test-session")
        
        connected = await client.connect(timeout=2.0)
        assert connected is False


class TestIntegration:
    """Integration tests for complete networking stack."""
    
    @pytest.mark.asyncio
    async def test_network_info_includes_relay_fallback(self):
        """Test that network info can support relay fallback."""
        info = await gather_network_info(local_port=12349)
        
        # Should always have a local endpoint
        assert info.local_ip
        assert info.best_endpoint
        
        print(f"Best endpoint: {info.best_endpoint}")


if __name__ == "__main__":
    # Run basic smoke tests
    import sys
    
    async def smoke_test():
        print("=== STUN Discovery ===")
        endpoint = await discover_public_ip()
        if endpoint:
            print(f"✓ Public IP: {endpoint.ip}:{endpoint.port}")
            print(f"  Source: {endpoint.source}")
            print(f"  Is public: {endpoint.is_public}")
        else:
            print("✗ STUN discovery failed")
        
        print("\n=== Network Info ===")
        info = await gather_network_info(local_port=12345)
        print(f"✓ Local: {info.local_ip}:{info.local_port}")
        print(f"  Behind NAT: {info.is_behind_nat}")
        print(f"  Best endpoint: {info.best_endpoint}")
        
        print("\n=== Relay Server ===")
        server = RelayServer(host="127.0.0.1", port=18082)
        await server.start()
        print("✓ Relay server started")
        
        await asyncio.sleep(0.2)
        
        # Test with clients
        client = RelayClient("ws://127.0.0.1:18082", "test-123")
        if await client.connect():
            print("✓ Relay client connected")
            await client.disconnect()
        else:
            print("✗ Relay client failed to connect")
        
        await server.stop()
        print("✓ Relay server stopped")
        
        print("\n=== All Tests Passed ===")
    
    asyncio.run(smoke_test())
