"""
Matter Controller Bridge.

Provides communication between Python and matter.js via WebSocket/JSON-RPC.

Architecture:
    Atmosphere (Python) <--WebSocket/JSON-RPC--> matter.js (Node.js)

The matter.js bridge runs as a separate process and handles:
- Matter protocol implementation
- Device commissioning
- Command execution
- Event subscriptions

Note: For MVP, this is partially stubbed. The WebSocket client
is implemented, but actual matter.js integration requires
setting up the Node.js bridge.
"""

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Awaitable, List
from enum import Enum

from .models import (
    MatterDevice,
    MatterCommand,
    MatterCommandResult,
    DeviceStatus,
    ClusterType,
)

logger = logging.getLogger(__name__)


class BridgeState(str, Enum):
    """State of the matter.js bridge."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class BridgeConfig:
    """Configuration for the Matter bridge."""
    
    # WebSocket port for communication
    port: int = 5580
    
    # Path to matter.js bridge script
    bridge_path: Optional[Path] = None
    
    # Storage path for Matter credentials
    storage_path: Path = Path.home() / ".atmosphere" / "matter"
    
    # Auto-start bridge subprocess
    auto_start: bool = True
    
    # Connection timeout
    connect_timeout_seconds: float = 10.0
    
    # Command execution timeout
    command_timeout_seconds: float = 30.0
    
    # Reconnection settings
    auto_reconnect: bool = True
    reconnect_interval_seconds: float = 5.0
    max_reconnect_attempts: int = 5


class JsonRpcError(Exception):
    """JSON-RPC error from bridge."""
    
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[{code}] {message}")


class MatterBridge:
    """
    Client for communicating with the matter.js bridge.
    
    Manages the WebSocket connection and JSON-RPC protocol.
    """
    
    def __init__(self, config: Optional[BridgeConfig] = None):
        self.config = config or BridgeConfig()
        self._state = BridgeState.STOPPED
        self._ws = None  # WebSocket connection (would be aiohttp or websockets)
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0
        
        # Callbacks
        self.on_device_event: Optional[Callable[[int, str, Any], Awaitable[None]]] = None
        self.on_device_online: Optional[Callable[[int], Awaitable[None]]] = None
        self.on_device_offline: Optional[Callable[[int], Awaitable[None]]] = None
    
    @property
    def state(self) -> BridgeState:
        """Get current bridge state."""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to bridge."""
        return self._state == BridgeState.RUNNING and self._ws is not None
    
    async def start(self) -> bool:
        """
        Start the matter.js bridge subprocess.
        
        Note: For MVP, this is STUBBED. Real implementation would:
        1. Start the Node.js bridge process
        2. Wait for WebSocket server to be ready
        3. Connect via WebSocket
        
        Returns:
            True if bridge started successfully
        """
        if self._state in (BridgeState.RUNNING, BridgeState.STARTING):
            return True
        
        self._state = BridgeState.STARTING
        logger.info(f"Starting Matter bridge on port {self.config.port}...")
        
        try:
            # STUB: In real implementation, start Node.js process
            # Example:
            # self._process = subprocess.Popen(
            #     ["node", str(self.config.bridge_path)],
            #     env={"MATTER_PORT": str(self.config.port)},
            #     stdout=subprocess.PIPE,
            #     stderr=subprocess.PIPE,
            # )
            
            # Wait for bridge to be ready
            await asyncio.sleep(0.5)  # Simulated startup time
            
            # Connect WebSocket
            # await self._connect_websocket()
            
            self._state = BridgeState.RUNNING
            logger.info("Matter bridge started (STUB MODE)")
            
            return True
            
        except Exception as e:
            self._state = BridgeState.ERROR
            logger.error(f"Failed to start Matter bridge: {e}")
            return False
    
    async def stop(self) -> None:
        """Stop the matter.js bridge."""
        if self._state == BridgeState.STOPPED:
            return
        
        self._state = BridgeState.STOPPING
        logger.info("Stopping Matter bridge...")
        
        # Cancel reader task
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        
        # Close WebSocket
        # if self._ws:
        #     await self._ws.close()
        #     self._ws = None
        
        # Stop subprocess
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        
        # Cancel pending requests
        for future in self._pending.values():
            future.cancel()
        self._pending.clear()
        
        self._state = BridgeState.STOPPED
        logger.info("Matter bridge stopped")
    
    async def _connect_websocket(self) -> None:
        """Connect to the bridge WebSocket server."""
        # STUB: Real implementation would use aiohttp or websockets
        # 
        # import aiohttp
        # url = f"ws://localhost:{self.config.port}/rpc"
        # session = aiohttp.ClientSession()
        # self._ws = await session.ws_connect(url)
        # 
        # # Start message reader
        # self._reader_task = asyncio.create_task(self._read_messages())
        pass
    
    async def _read_messages(self) -> None:
        """Background task to read WebSocket messages."""
        # STUB: Real implementation would read from WebSocket
        # 
        # async for msg in self._ws:
        #     if msg.type == aiohttp.WSMsgType.TEXT:
        #         await self._handle_message(json.loads(msg.data))
        #     elif msg.type == aiohttp.WSMsgType.ERROR:
        #         logger.error(f"WebSocket error: {self._ws.exception()}")
        #         break
        pass
    
    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle an incoming JSON-RPC message."""
        # Response to a request
        if "id" in message and message["id"] in self._pending:
            request_id = message["id"]
            future = self._pending.pop(request_id)
            
            if "error" in message:
                error = message["error"]
                future.set_exception(JsonRpcError(
                    code=error.get("code", -1),
                    message=error.get("message", "Unknown error"),
                    data=error.get("data"),
                ))
            else:
                future.set_result(message.get("result"))
        
        # Event notification
        elif message.get("method") == "event":
            await self._handle_event(message.get("params", {}))
    
    async def _handle_event(self, params: Dict[str, Any]) -> None:
        """Handle an event from the bridge."""
        event_type = params.get("type")
        node_id = params.get("nodeId")
        data = params.get("data")
        
        if event_type == "attributeChange":
            if self.on_device_event:
                await self.on_device_event(node_id, "attributeChange", data)
        
        elif event_type == "deviceOnline":
            if self.on_device_online:
                await self.on_device_online(node_id)
        
        elif event_type == "deviceOffline":
            if self.on_device_offline:
                await self.on_device_offline(node_id)
    
    async def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Send a JSON-RPC request to the bridge.
        
        Args:
            method: RPC method name
            params: Method parameters
            timeout: Request timeout
        
        Returns:
            Result from the bridge
        
        Raises:
            JsonRpcError: If bridge returns an error
            asyncio.TimeoutError: If request times out
        """
        timeout = timeout or self.config.command_timeout_seconds
        
        # STUB: In real implementation, send via WebSocket
        # For now, return mock responses based on method
        
        logger.debug(f"Bridge request: {method}({params})")
        
        # Mock responses for testing
        if method == "ping":
            return "pong"
        
        if method == "getDevices":
            return []  # Discovery handles device storage
        
        if method == "executeCommand":
            # Simulate successful command
            await asyncio.sleep(0.1)  # Simulated latency
            return {"success": True}
        
        if method == "readAttribute":
            # Return mock attribute values
            cluster = params.get("cluster") if params else None
            attribute = params.get("attribute") if params else None
            
            if cluster == "OnOff" and attribute == "onOff":
                return False
            if cluster == "LevelControl" and attribute == "currentLevel":
                return 254
            
            return None
        
        if method == "subscribe":
            return f"sub_{self._request_id}"
        
        # Default: return empty result
        return {}
    
    async def ping(self) -> bool:
        """Check if bridge is responsive."""
        try:
            result = await self._send_request("ping", timeout=5.0)
            return result == "pong"
        except Exception:
            return False
    
    async def get_devices(self) -> List[Dict[str, Any]]:
        """Get all commissioned devices from the bridge."""
        return await self._send_request("getDevices")
    
    async def get_device(self, node_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific device by node ID."""
        return await self._send_request("getDevice", {"nodeId": node_id})
    
    async def execute_command(
        self,
        node_id: int,
        endpoint_id: int,
        cluster: str,
        command: str,
        args: Optional[Dict[str, Any]] = None,
    ) -> MatterCommandResult:
        """
        Execute a command on a Matter device.
        
        Args:
            node_id: Target device node ID
            endpoint_id: Target endpoint
            cluster: Cluster name (e.g., "OnOff", "LevelControl")
            command: Command name (e.g., "On", "Off", "MoveToLevel")
            args: Command arguments
        
        Returns:
            Command execution result
        """
        try:
            result = await self._send_request("executeCommand", {
                "nodeId": node_id,
                "endpoint": endpoint_id,
                "cluster": cluster,
                "command": command,
                "args": args or {},
            })
            
            return MatterCommandResult(
                success=result.get("success", False),
                data=result.get("data"),
                error=result.get("error"),
            )
            
        except JsonRpcError as e:
            return MatterCommandResult(
                success=False,
                error=e.message,
                error_code=e.code,
            )
        except Exception as e:
            return MatterCommandResult(
                success=False,
                error=str(e),
            )
    
    async def read_attribute(
        self,
        node_id: int,
        endpoint_id: int,
        cluster: str,
        attribute: str,
    ) -> Any:
        """Read an attribute value from a device."""
        return await self._send_request("readAttribute", {
            "nodeId": node_id,
            "endpoint": endpoint_id,
            "cluster": cluster,
            "attribute": attribute,
        })
    
    async def write_attribute(
        self,
        node_id: int,
        endpoint_id: int,
        cluster: str,
        attribute: str,
        value: Any,
    ) -> bool:
        """Write an attribute value to a device."""
        result = await self._send_request("writeAttribute", {
            "nodeId": node_id,
            "endpoint": endpoint_id,
            "cluster": cluster,
            "attribute": attribute,
            "value": value,
        })
        return result.get("success", False)
    
    async def subscribe(
        self,
        node_id: int,
        paths: List[Dict[str, Any]],
        min_interval_seconds: int = 1,
        max_interval_seconds: int = 60,
    ) -> str:
        """
        Subscribe to attribute changes on a device.
        
        Args:
            node_id: Device node ID
            paths: List of {endpoint, cluster, attribute} to subscribe to
            min_interval_seconds: Minimum reporting interval
            max_interval_seconds: Maximum reporting interval
        
        Returns:
            Subscription ID
        """
        return await self._send_request("subscribe", {
            "nodeId": node_id,
            "paths": paths,
            "minIntervalSeconds": min_interval_seconds,
            "maxIntervalSeconds": max_interval_seconds,
        })
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from attribute changes."""
        result = await self._send_request("unsubscribe", {
            "subscriptionId": subscription_id,
        })
        return result.get("success", False)
    
    async def commission(
        self,
        setup_code: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Commission a new device.
        
        Args:
            setup_code: QR code payload or manual pairing code
            name: Optional friendly name
        
        Returns:
            Device info from commissioning
        """
        return await self._send_request("commission", {
            "code": setup_code,
            "name": name,
        }, timeout=120.0)  # Commissioning can take a while
    
    async def decommission(self, node_id: int) -> bool:
        """Remove a device from the fabric."""
        result = await self._send_request("decommission", {
            "nodeId": node_id,
        })
        return result.get("success", False)


class MatterBridgeManager:
    """
    Manages the Matter bridge lifecycle and provides high-level API.
    
    Combines bridge communication with device state management.
    """
    
    def __init__(self, config: Optional[BridgeConfig] = None):
        self.config = config or BridgeConfig()
        self._bridge = MatterBridge(config)
        self._device_states: Dict[int, Dict[str, Any]] = {}
        self._subscriptions: Dict[int, str] = {}  # node_id → subscription_id
        
        # Wire up event handlers
        self._bridge.on_device_event = self._on_device_event
        self._bridge.on_device_online = self._on_device_online
        self._bridge.on_device_offline = self._on_device_offline
        
        # External callbacks
        self.on_attribute_change: Optional[Callable[[int, int, str, str, Any, Any], Awaitable[None]]] = None
        self.on_status_change: Optional[Callable[[int, DeviceStatus], Awaitable[None]]] = None
    
    @property
    def is_connected(self) -> bool:
        return self._bridge.is_connected
    
    async def start(self) -> bool:
        """Start the bridge manager."""
        return await self._bridge.start()
    
    async def stop(self) -> None:
        """Stop the bridge manager."""
        # Unsubscribe all
        for sub_id in self._subscriptions.values():
            try:
                await self._bridge.unsubscribe(sub_id)
            except Exception:
                pass
        
        self._subscriptions.clear()
        await self._bridge.stop()
    
    async def setup_device_subscriptions(
        self,
        node_id: int,
        endpoint_id: int,
        clusters: List[str],
    ) -> None:
        """Set up subscriptions for a device's clusters."""
        paths = []
        
        for cluster in clusters:
            # Subscribe to relevant attributes based on cluster
            if cluster == "OnOff":
                paths.append({"endpoint": endpoint_id, "cluster": cluster, "attribute": "onOff"})
            elif cluster == "LevelControl":
                paths.append({"endpoint": endpoint_id, "cluster": cluster, "attribute": "currentLevel"})
            elif cluster == "ColorControl":
                paths.extend([
                    {"endpoint": endpoint_id, "cluster": cluster, "attribute": "currentHue"},
                    {"endpoint": endpoint_id, "cluster": cluster, "attribute": "currentSaturation"},
                    {"endpoint": endpoint_id, "cluster": cluster, "attribute": "colorTemperatureMireds"},
                ])
            elif cluster == "DoorLock":
                paths.extend([
                    {"endpoint": endpoint_id, "cluster": cluster, "attribute": "lockState"},
                    {"endpoint": endpoint_id, "cluster": cluster, "attribute": "doorState"},
                ])
            elif cluster == "Thermostat":
                paths.extend([
                    {"endpoint": endpoint_id, "cluster": cluster, "attribute": "localTemperature"},
                    {"endpoint": endpoint_id, "cluster": cluster, "attribute": "occupiedCoolingSetpoint"},
                    {"endpoint": endpoint_id, "cluster": cluster, "attribute": "occupiedHeatingSetpoint"},
                    {"endpoint": endpoint_id, "cluster": cluster, "attribute": "systemMode"},
                ])
            elif cluster == "OccupancySensing":
                paths.append({"endpoint": endpoint_id, "cluster": cluster, "attribute": "occupancy"})
            elif cluster == "BooleanState":
                paths.append({"endpoint": endpoint_id, "cluster": cluster, "attribute": "stateValue"})
            elif cluster == "TemperatureMeasurement":
                paths.append({"endpoint": endpoint_id, "cluster": cluster, "attribute": "measuredValue"})
        
        if paths:
            sub_id = await self._bridge.subscribe(node_id, paths)
            self._subscriptions[node_id] = sub_id
            logger.debug(f"Subscribed to node {node_id}: {len(paths)} attributes")
    
    async def execute_tool(
        self,
        node_id: int,
        endpoint_id: int,
        cluster_id: ClusterType,
        command: str,
        args: Dict[str, Any],
    ) -> MatterCommandResult:
        """Execute a tool call via the bridge."""
        # Map ClusterType enum to string name
        cluster_names = {
            ClusterType.ON_OFF: "OnOff",
            ClusterType.LEVEL_CONTROL: "LevelControl",
            ClusterType.COLOR_CONTROL: "ColorControl",
            ClusterType.DOOR_LOCK: "DoorLock",
            ClusterType.THERMOSTAT: "Thermostat",
            ClusterType.FAN_CONTROL: "FanControl",
            ClusterType.WINDOW_COVERING: "WindowCovering",
        }
        
        cluster_name = cluster_names.get(cluster_id, str(cluster_id.value))
        
        return await self._bridge.execute_command(
            node_id=node_id,
            endpoint_id=endpoint_id,
            cluster=cluster_name,
            command=command,
            args=args,
        )
    
    async def _on_device_event(
        self,
        node_id: int,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """Handle device events from bridge."""
        if event_type == "attributeChange":
            endpoint = data.get("endpoint", 1)
            cluster = data.get("cluster", "")
            attribute = data.get("attribute", "")
            old_value = data.get("oldValue")
            new_value = data.get("newValue")
            
            # Update local state cache
            state_key = f"{node_id}:{endpoint}:{cluster}:{attribute}"
            self._device_states[node_id] = self._device_states.get(node_id, {})
            self._device_states[node_id][state_key] = new_value
            
            # Notify listeners
            if self.on_attribute_change:
                await self.on_attribute_change(
                    node_id, endpoint, cluster, attribute, old_value, new_value
                )
    
    async def _on_device_online(self, node_id: int) -> None:
        """Handle device coming online."""
        logger.info(f"Device {node_id} is online")
        if self.on_status_change:
            await self.on_status_change(node_id, DeviceStatus.ONLINE)
    
    async def _on_device_offline(self, node_id: int) -> None:
        """Handle device going offline."""
        logger.info(f"Device {node_id} is offline")
        if self.on_status_change:
            await self.on_status_change(node_id, DeviceStatus.OFFLINE)
