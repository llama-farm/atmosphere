"""
NAT traversal and UDP hole punching.

Implements:
- UDP hole punching for direct P2P connections
- Connection negotiation protocol
- Fallback to relay when P2P fails
"""

import asyncio
import json
import logging
import socket
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, Callable

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """State of a P2P connection attempt."""
    INIT = "init"
    PUNCHING = "punching"
    ESTABLISHED = "established"
    FAILED = "failed"
    RELAY = "relay"


@dataclass
class ConnectionAttempt:
    """Tracks a P2P connection attempt."""
    peer_id: str
    local_endpoint: Tuple[str, int]
    remote_endpoint: Tuple[str, int]
    state: ConnectionState
    started_at: float
    established_at: Optional[float] = None
    relay_url: Optional[str] = None
    
    @property
    def duration(self) -> float:
        """Time spent on this attempt in seconds."""
        if self.established_at:
            return self.established_at - self.started_at
        return time.time() - self.started_at
    
    @property
    def is_direct(self) -> bool:
        """Check if this is a direct P2P connection."""
        return self.state == ConnectionState.ESTABLISHED and not self.relay_url


class NATTraversal:
    """
    Handles NAT traversal and UDP hole punching.
    
    Process:
    1. Both peers discover their public endpoints (STUN)
    2. Both peers exchange endpoints via signaling channel
    3. Both peers simultaneously send UDP packets to each other
    4. NAT creates bidirectional mapping, packets flow
    """
    
    def __init__(
        self,
        local_port: int,
        on_message: Optional[Callable[[bytes, Tuple[str, int]], None]] = None
    ):
        """
        Initialize NAT traversal.
        
        Args:
            local_port: Local UDP port to use
            on_message: Callback for received messages
        """
        self.local_port = local_port
        self.on_message = on_message
        self.sock: Optional[socket.socket] = None
        self._running = False
        self._receive_task: Optional[asyncio.Task] = None
        self._attempts: dict[str, ConnectionAttempt] = {}
    
    async def start(self) -> bool:
        """Start the NAT traversal UDP listener."""
        if self._running:
            return True
        
        try:
            # Create UDP socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.setblocking(False)
            self.sock.bind(("0.0.0.0", self.local_port))
            
            self._running = True
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            logger.info(f"NAT traversal started on UDP port {self.local_port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start NAT traversal: {e}")
            return False
    
    async def stop(self) -> None:
        """Stop the NAT traversal listener."""
        self._running = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self.sock:
            self.sock.close()
            self.sock = None
    
    async def _receive_loop(self) -> None:
        """Receive incoming UDP packets."""
        loop = asyncio.get_event_loop()
        
        while self._running:
            try:
                data, addr = await loop.sock_recvfrom(self.sock, 4096)
                
                # Handle the message
                if self.on_message:
                    try:
                        self.on_message(data, addr)
                    except Exception as e:
                        logger.error(f"Error in message handler: {e}")
                
            except Exception as e:
                if self._running:
                    logger.error(f"Error receiving UDP packet: {e}")
    
    async def punch_hole(
        self,
        peer_id: str,
        remote_host: str,
        remote_port: int,
        timeout: float = 10.0,
    ) -> ConnectionAttempt:
        """
        Attempt UDP hole punching to establish P2P connection.
        
        Args:
            peer_id: Unique identifier for the peer
            remote_host: Peer's public IP
            remote_port: Peer's public port
            timeout: How long to attempt connection (seconds)
            
        Returns:
            ConnectionAttempt with result
        """
        if not self._running:
            raise RuntimeError("NAT traversal not started")
        
        remote_endpoint = (remote_host, remote_port)
        local_endpoint = ("0.0.0.0", self.local_port)
        
        attempt = ConnectionAttempt(
            peer_id=peer_id,
            local_endpoint=local_endpoint,
            remote_endpoint=remote_endpoint,
            state=ConnectionState.PUNCHING,
            started_at=time.time(),
        )
        
        self._attempts[peer_id] = attempt
        
        logger.info(f"Punching hole to {remote_host}:{remote_port} for peer {peer_id}")
        
        # Send punch packets repeatedly
        punch_msg = json.dumps({
            "type": "punch",
            "peer_id": peer_id,
            "timestamp": time.time(),
        }).encode()
        
        loop = asyncio.get_event_loop()
        start_time = time.time()
        success = False
        
        while time.time() - start_time < timeout:
            try:
                # Send punch packet
                await loop.sock_sendto(self.sock, punch_msg, remote_endpoint)
                
                # Check if we've received response
                if attempt.state == ConnectionState.ESTABLISHED:
                    success = True
                    break
                
                # Wait before next attempt
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.debug(f"Punch attempt failed: {e}")
        
        if success:
            attempt.established_at = time.time()
            logger.info(f"P2P connection established to {peer_id} in {attempt.duration:.1f}s")
        else:
            attempt.state = ConnectionState.FAILED
            logger.warning(f"P2P connection to {peer_id} failed after {timeout}s")
        
        return attempt
    
    def mark_established(self, peer_id: str) -> None:
        """Mark a connection as established (called by message handler)."""
        if peer_id in self._attempts:
            attempt = self._attempts[peer_id]
            if attempt.state == ConnectionState.PUNCHING:
                attempt.state = ConnectionState.ESTABLISHED
                attempt.established_at = time.time()
    
    async def send_to_peer(
        self,
        peer_id: str,
        data: bytes,
    ) -> bool:
        """
        Send data to a peer.
        
        Args:
            peer_id: Peer identifier
            data: Data to send
            
        Returns:
            True if sent, False if peer not connected
        """
        if peer_id not in self._attempts:
            return False
        
        attempt = self._attempts[peer_id]
        if attempt.state != ConnectionState.ESTABLISHED:
            return False
        
        try:
            loop = asyncio.get_event_loop()
            await loop.sock_sendto(self.sock, data, attempt.remote_endpoint)
            return True
        except Exception as e:
            logger.error(f"Failed to send to peer {peer_id}: {e}")
            return False


async def punch_hole(
    local_port: int,
    remote_host: str,
    remote_port: int,
    timeout: float = 10.0,
) -> bool:
    """
    Simple helper to punch a hole without setting up full NATTraversal.
    
    Args:
        local_port: Local UDP port to use
        remote_host: Remote host public IP
        remote_port: Remote host public port
        timeout: Timeout in seconds
        
    Returns:
        True if successful, False otherwise
    """
    traversal = NATTraversal(local_port)
    
    try:
        if not await traversal.start():
            return False
        
        attempt = await traversal.punch_hole(
            peer_id="peer",
            remote_host=remote_host,
            remote_port=remote_port,
            timeout=timeout,
        )
        
        return attempt.state == ConnectionState.ESTABLISHED
        
    finally:
        await traversal.stop()


async def establish_p2p_connection(
    local_port: int,
    remote_endpoint: Tuple[str, int],
    relay_url: Optional[str] = None,
    timeout: float = 10.0,
) -> Tuple[bool, Optional[str]]:
    """
    Attempt to establish P2P connection with automatic relay fallback.
    
    Args:
        local_port: Local UDP port
        remote_endpoint: (host, port) of peer
        relay_url: Optional relay server URL for fallback
        timeout: Timeout for P2P attempt
        
    Returns:
        (success, connection_type) where connection_type is "direct" or "relay"
    """
    remote_host, remote_port = remote_endpoint
    
    # Try direct P2P first
    logger.info(f"Attempting direct P2P to {remote_host}:{remote_port}...")
    
    traversal = NATTraversal(local_port)
    
    try:
        if not await traversal.start():
            logger.warning("Could not start NAT traversal")
            if relay_url:
                return await _fallback_to_relay(relay_url)
            return False, None
        
        attempt = await traversal.punch_hole(
            peer_id="peer",
            remote_host=remote_host,
            remote_port=remote_port,
            timeout=timeout,
        )
        
        if attempt.state == ConnectionState.ESTABLISHED:
            logger.info("✓ Direct P2P connection established")
            return True, "direct"
        
        # P2P failed, try relay
        if relay_url:
            logger.info("P2P failed, falling back to relay...")
            return await _fallback_to_relay(relay_url)
        
        logger.warning("P2P failed and no relay available")
        return False, None
        
    finally:
        await traversal.stop()


async def _fallback_to_relay(relay_url: str) -> Tuple[bool, Optional[str]]:
    """
    Fallback to relay connection.
    
    Args:
        relay_url: WebSocket URL of relay server
        
    Returns:
        (success, "relay")
    """
    from .relay import RelayClient
    
    try:
        client = RelayClient(relay_url)
        if await client.connect():
            logger.info("✓ Relay connection established")
            return True, "relay"
        else:
            logger.error("Relay connection failed")
            return False, None
    except Exception as e:
        logger.error(f"Relay connection error: {e}")
        return False, None
