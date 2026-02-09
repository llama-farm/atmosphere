"""WebSocket client for Atmosphere mesh connection."""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable
from websockets.asyncio.client import connect, ClientConnection
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class MeshClient:
    """
    WebSocket client to connect to local Atmosphere node.
    
    Handles message routing between the app and the mesh.
    """
    
    def __init__(self, mesh_url: str = "ws://localhost:11451/ws"):
        """
        Initialize mesh client.
        
        Args:
            mesh_url: WebSocket URL of local Atmosphere node
        """
        self.mesh_url = mesh_url
        self._ws: Optional[ClientConnection] = None
        self._running = False
        self._message_handlers: Dict[str, Callable] = {}
        self._receive_task: Optional[asyncio.Task] = None
    
    def on(self, message_type: str, handler: Callable) -> None:
        """
        Register a message handler.
        
        Args:
            message_type: Type of message to handle (e.g., "app_request")
            handler: Async function to handle the message
        """
        self._message_handlers[message_type] = handler
        logger.debug(f"Registered handler for: {message_type}")
    
    async def connect(self) -> None:
        """Connect to the Atmosphere mesh."""
        try:
            logger.info(f"Connecting to Atmosphere mesh at {self.mesh_url}")
            self._ws = await connect(self.mesh_url)
            self._running = True
            
            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            logger.info("Connected to Atmosphere mesh")
        except Exception as e:
            logger.error(f"Failed to connect to mesh: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from the mesh."""
        self._running = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        logger.info("Disconnected from Atmosphere mesh")
    
    async def send(self, message: Dict[str, Any]) -> None:
        """
        Send a message to the mesh.
        
        Args:
            message: Message dictionary
        """
        if not self._ws:
            raise RuntimeError("Not connected to mesh")
        
        try:
            await self._ws.send(json.dumps(message))
            logger.debug(f"Sent message: {message.get('type', 'unknown')}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise
    
    async def _receive_loop(self) -> None:
        """Receive and handle messages from the mesh."""
        while self._running and self._ws:
            try:
                raw_message = await self._ws.recv()
                
                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode('utf-8')
                
                message = json.loads(raw_message)
                await self._handle_message(message)
                
            except ConnectionClosed:
                logger.warning("WebSocket connection closed")
                self._running = False
                break
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
            except Exception as e:
                logger.error(f"Error in receive loop: {e}")
    
    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """
        Handle an incoming message.
        
        Args:
            message: Parsed message dictionary
        """
        msg_type = message.get("type", "unknown")
        logger.debug(f"Received message: {msg_type}")
        
        handler = self._message_handlers.get(msg_type)
        if handler:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"Error handling {msg_type}: {e}")
        else:
            logger.debug(f"No handler for message type: {msg_type}")
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to mesh."""
        return self._ws is not None and self._running
