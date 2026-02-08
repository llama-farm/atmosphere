"""
Base WebSocket transport for LAN and Relay connections.
"""

import asyncio
import json
import logging
import time
from typing import Optional, Callable
import aiohttp

from ..resilient_transport import Transport, TransportType, TransportState

log = logging.getLogger(__name__)


class BaseWebSocketTransport(Transport):
    """
    Base class for WebSocket-based transports.
    
    Handles:
    - WebSocket connection management
    - Message send/receive
    - Ping/pong for latency measurement
    - Automatic reconnection state tracking
    """
    
    def __init__(self, transport_type: TransportType):
        super().__init__(transport_type)
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._address: Optional[str] = None
        self._ping_event: Optional[asyncio.Event] = None
        self._ping_start: float = 0
    
    async def connect(self, address: str) -> bool:
        """Connect to WebSocket endpoint."""
        self._address = address
        
        try:
            if self._session is None:
                self._session = aiohttp.ClientSession()
            
            self.metrics.state = TransportState.CONNECTING
            
            self._ws = await self._session.ws_connect(
                address,
                heartbeat=20.0,  # Prevent idle timeouts
                timeout=aiohttp.ClientTimeout(total=10.0)
            )
            
            self.metrics.state = TransportState.CONNECTED
            
            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            log.debug(f"Connected to {address}")
            return True
            
        except Exception as e:
            log.warning(f"Failed to connect to {address}: {e}")
            self.metrics.state = TransportState.FAILED
            return False
    
    async def disconnect(self):
        """Disconnect from WebSocket."""
        self.metrics.state = TransportState.DISCONNECTED
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        
        if self._ws and not self._ws.closed:
            await self._ws.close()
            self._ws = None
        
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def send(self, message: bytes) -> bool:
        """Send message over WebSocket."""
        if not self._ws or self._ws.closed:
            self.metrics.state = TransportState.FAILED
            return False
        
        try:
            await self._ws.send_bytes(message)
            return True
        except Exception as e:
            log.warning(f"Send failed: {e}")
            self.metrics.state = TransportState.FAILED
            return False
    
    async def send_json(self, data: dict) -> bool:
        """Send JSON message over WebSocket."""
        if not self._ws or self._ws.closed:
            self.metrics.state = TransportState.FAILED
            return False
        
        try:
            await self._ws.send_json(data)
            return True
        except Exception as e:
            log.warning(f"Send JSON failed: {e}")
            self.metrics.state = TransportState.FAILED
            return False
    
    async def ping(self) -> float:
        """
        Ping the peer and return latency in milliseconds.
        Uses WebSocket ping/pong protocol.
        """
        if not self._ws or self._ws.closed:
            raise ConnectionError("Not connected")
        
        self._ping_event = asyncio.Event()
        self._ping_start = time.monotonic()
        
        try:
            await self._ws.ping()
            
            # Wait for pong (handled in receive loop)
            await asyncio.wait_for(self._ping_event.wait(), timeout=5.0)
            
            latency_ms = (time.monotonic() - self._ping_start) * 1000
            return latency_ms
            
        except asyncio.TimeoutError:
            raise ConnectionError("Ping timeout")
        finally:
            self._ping_event = None
    
    async def _receive_loop(self):
        """Background task to receive messages."""
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    # Handle text message
                    self._handle_text_message(msg.data)
                    
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    # Handle binary message
                    if self._message_handler:
                        self._message_handler(msg.data)
                        
                elif msg.type == aiohttp.WSMsgType.PONG:
                    # Handle pong response
                    if self._ping_event:
                        self._ping_event.set()
                        
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    log.error(f"WebSocket error: {self._ws.exception()}")
                    break
                    
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    break
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Receive loop error: {e}")
        finally:
            if self.metrics.state == TransportState.CONNECTED:
                self.metrics.state = TransportState.FAILED
    
    def _handle_text_message(self, data: str):
        """Handle incoming text message. Override in subclasses."""
        try:
            msg = json.loads(data)
            # Convert to bytes for message handler
            if self._message_handler:
                self._message_handler(data.encode('utf-8'))
        except json.JSONDecodeError:
            if self._message_handler:
                self._message_handler(data.encode('utf-8'))
