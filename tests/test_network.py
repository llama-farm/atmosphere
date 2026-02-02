"""
Tests for network utilities (STUN, NAT traversal).
"""

import pytest
import asyncio
import struct

from atmosphere.mesh.network import (
    PublicEndpoint,
    _build_stun_request,
    _parse_stun_response,
    discover_public_ip,
    get_local_ip,
    gather_network_info,
    STUN_MAGIC_COOKIE,
    STUN_BINDING_RESPONSE,
    ATTR_XOR_MAPPED_ADDRESS,
)


class TestPublicEndpoint:
    """Tests for PublicEndpoint."""
    
    def test_str(self):
        """Test string representation."""
        ep = PublicEndpoint(ip="1.2.3.4", port=11451, source="test")
        assert str(ep) == "1.2.3.4:11451"
    
    def test_is_public_true(self):
        """Test public IP detection."""
        ep = PublicEndpoint(ip="8.8.8.8", port=443, source="test")
        assert ep.is_public is True
    
    def test_is_public_false_private(self):
        """Test private IP detection."""
        # 192.168.x.x
        ep = PublicEndpoint(ip="192.168.1.1", port=80, source="test")
        assert ep.is_public is False
        
        # 10.x.x.x
        ep = PublicEndpoint(ip="10.0.0.1", port=80, source="test")
        assert ep.is_public is False
        
        # 172.16-31.x.x
        ep = PublicEndpoint(ip="172.16.0.1", port=80, source="test")
        assert ep.is_public is False
    
    def test_is_public_false_localhost(self):
        """Test localhost detection."""
        ep = PublicEndpoint(ip="127.0.0.1", port=80, source="test")
        assert ep.is_public is False


class TestStunProtocol:
    """Tests for STUN protocol implementation."""
    
    def test_build_request(self):
        """Test STUN request building."""
        request, transaction_id = _build_stun_request()
        
        # Request should be 20 bytes (header only)
        assert len(request) == 20
        
        # Transaction ID should be 12 bytes
        assert len(transaction_id) == 12
        
        # Parse header
        msg_type, msg_len, magic = struct.unpack(">HHI", request[:8])
        assert msg_type == 0x0001  # Binding request
        assert msg_len == 0  # No attributes
        assert magic == STUN_MAGIC_COOKIE
    
    def test_parse_response_xor_mapped(self):
        """Test parsing XOR-MAPPED-ADDRESS response."""
        # Build a mock response
        transaction_id = b'\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c'
        
        # XOR values for IP 1.2.3.4, port 12345
        xor_port = 12345 ^ (STUN_MAGIC_COOKIE >> 16)
        xor_ip = (1 << 24 | 2 << 16 | 3 << 8 | 4) ^ STUN_MAGIC_COOKIE
        
        # Build attribute
        attr = struct.pack(
            ">HH",
            ATTR_XOR_MAPPED_ADDRESS,
            8  # Length
        )
        attr += b'\x00\x01'  # Reserved + Family (IPv4)
        attr += struct.pack(">H", xor_port)
        attr += struct.pack(">I", xor_ip)
        
        # Build response header
        header = struct.pack(
            ">HHI",
            STUN_BINDING_RESPONSE,
            len(attr),
            STUN_MAGIC_COOKIE,
        )
        response = header + transaction_id + attr
        
        # Parse
        result = _parse_stun_response(response, transaction_id)
        
        assert result is not None
        ip, port = result
        assert ip == "1.2.3.4"
        assert port == 12345
    
    def test_parse_response_wrong_transaction(self):
        """Test rejecting response with wrong transaction ID."""
        transaction_id = b'\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c'
        wrong_id = b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff'
        
        # Build minimal valid response
        header = struct.pack(
            ">HHI",
            STUN_BINDING_RESPONSE,
            0,
            STUN_MAGIC_COOKIE,
        )
        response = header + wrong_id
        
        result = _parse_stun_response(response, transaction_id)
        assert result is None


class TestNetworkDiscovery:
    """Tests for network discovery functions."""
    
    @pytest.mark.asyncio
    async def test_get_local_ip(self):
        """Test local IP detection."""
        ip = await get_local_ip()
        
        # Should return a valid IP
        assert ip is not None
        assert len(ip.split('.')) == 4 or '::' in ip  # IPv4 or IPv6
    
    @pytest.mark.asyncio
    async def test_gather_network_info(self):
        """Test gathering full network info."""
        info = await gather_network_info(local_port=11451)
        
        assert info.local_ip is not None
        assert info.local_port == 11451
        # public_endpoint may or may not be detected
        assert isinstance(info.is_behind_nat, bool)
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        True,  # Skip by default - requires network
        reason="Requires network access to STUN servers"
    )
    async def test_discover_public_ip_real(self):
        """Test real STUN discovery (requires network)."""
        endpoint = await discover_public_ip()
        
        if endpoint:
            assert endpoint.ip is not None
            assert endpoint.port > 0
            assert endpoint.source.startswith("stun:")


class TestNetworkInfo:
    """Tests for NetworkInfo."""
    
    @pytest.mark.asyncio
    async def test_best_endpoint_with_public(self):
        """Test best endpoint returns public when available."""
        info = await gather_network_info(11451)
        
        # best_endpoint should return something
        endpoint = info.best_endpoint
        assert endpoint is not None
        assert ':' in endpoint  # Should be ip:port format
    
    @pytest.mark.asyncio  
    async def test_is_publicly_reachable(self):
        """Test public reachability check."""
        info = await gather_network_info(11451)
        
        # is_publicly_reachable should be a boolean
        assert isinstance(info.is_publicly_reachable, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
