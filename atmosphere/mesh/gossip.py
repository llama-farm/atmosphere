"""
Gossip protocol for capability propagation.

Nodes periodically announce their capabilities to neighbors.
Announcements propagate through the mesh with TTL decrement.
Includes dynamic endpoint discovery for multi-homed nodes.
Enhanced with smart routing table for true mesh routing.
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Dict, List, Optional, Set
import logging

import numpy as np

from ..router.gradient import GradientTable, GradientEntry
from ..network.ip_detect import EndpointRegistry, EndpointInfo, get_best_local_ip, get_all_local_ips
from .routing import RoutingTable, RouteEntry, TransportType

logger = logging.getLogger(__name__)

# Protocol constants
ANNOUNCE_INTERVAL_SEC = 30

# Type for UI event callback (for broadcasting to WebSocket clients)
UIEventCallback = Callable[[dict], Awaitable[None]]
MAX_TTL = 10
MAX_CAPABILITIES_PER_ANNOUNCE = 50
NONCE_CACHE_SEC = 300


@dataclass
class CapabilityInfo:
    """Capability information for announcements."""
    id: str
    label: str
    description: str
    vector: List[float]
    local: bool = True
    hops: int = 0
    via: Optional[str] = None
    models: List[str] = field(default_factory=list)
    constraints: dict = field(default_factory=dict)
    estimated_latency_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "vector": self.vector,
            "local": self.local,
            "hops": self.hops,
            "via": self.via,
            "models": self.models,
            "constraints": self.constraints,
            "estimated_latency_ms": self.estimated_latency_ms
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CapabilityInfo":
        return cls(
            id=data["id"],
            label=data["label"],
            description=data.get("description", ""),
            vector=data["vector"],
            local=data.get("local", False),
            hops=data.get("hops", 0),
            via=data.get("via"),
            models=data.get("models", []),
            constraints=data.get("constraints", {}),
            estimated_latency_ms=data.get("estimated_latency_ms", 0)
        )


@dataclass
class ResourceInfo:
    """Node resource information."""
    cpu_available: float = 1.0
    memory_available_mb: int = 0
    gpu_available: float = 0.0
    battery_percent: Optional[int] = None
    plugged_in: bool = True  # Whether on AC power
    cpu_load: float = 0.0    # Current CPU load (0-1)
    memory_percent: float = 0.0  # Current memory usage percent

    def to_dict(self) -> dict:
        return {
            "cpu_available": self.cpu_available,
            "memory_available_mb": self.memory_available_mb,
            "gpu_available": self.gpu_available,
            "battery_percent": self.battery_percent,
            "plugged_in": self.plugged_in,
            "cpu_load": self.cpu_load,
            "memory_percent": self.memory_percent
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ResourceInfo":
        return cls(
            cpu_available=data.get("cpu_available", 1.0),
            memory_available_mb=data.get("memory_available_mb", 0),
            gpu_available=data.get("gpu_available", 0.0),
            battery_percent=data.get("battery_percent"),
            plugged_in=data.get("plugged_in", True),
            cpu_load=data.get("cpu_load", 0.0),
            memory_percent=data.get("memory_percent", 0.0)
        )
    
    def calculate_cost(self) -> float:
        """
        Calculate dynamic routing cost based on resources.
        Lower cost = more preferred for routing.
        
        Factors:
        - Battery status (unplugged = higher cost)
        - CPU load (busy = higher cost)
        - Memory pressure (low = higher cost)
        """
        cost = 1.0
        
        # Battery factor: unplugged devices cost more
        if not self.plugged_in:
            if self.battery_percent is not None:
                if self.battery_percent < 20:
                    cost *= 3.0  # Critical battery - avoid
                elif self.battery_percent < 50:
                    cost *= 1.5  # Low battery - prefer plugged
                else:
                    cost *= 1.2  # On battery but OK
        
        # CPU factor: busy devices cost more
        if self.cpu_load > 0.8:
            cost *= 2.0  # Very busy
        elif self.cpu_load > 0.5:
            cost *= 1.3  # Moderately busy
        
        # Memory factor
        if self.memory_percent > 90:
            cost *= 1.5  # Memory pressure
        elif self.memory_percent > 70:
            cost *= 1.1  # Getting full
        
        return round(cost, 2)


@dataclass
class Announcement:
    """A capability announcement message with IHAVE/IWANT gossip metadata."""
    type: str = "announce"
    from_node: str = ""
    capabilities: List[CapabilityInfo] = field(default_factory=list)
    resources: Optional[ResourceInfo] = None
    endpoints: Optional[EndpointInfo] = None  # Dynamic endpoint info
    timestamp: float = field(default_factory=time.time)
    ttl: int = MAX_TTL
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    
    # IHAVE/IWANT gossip fields
    ihave: List[str] = field(default_factory=list)  # Capability IDs this node has
    iwant: List[str] = field(default_factory=list)  # Capability IDs this node wants
    node_cost: float = 1.0  # Dynamic routing cost (lower = preferred)
    transport_type: str = ""  # Transport used: "ble", "lan", "relay"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "from": self.from_node,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "resources": self.resources.to_dict() if self.resources else None,
            "endpoints": self.endpoints.to_dict() if self.endpoints else None,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
            "nonce": self.nonce,
            "ihave": self.ihave,
            "iwant": self.iwant,
            "node_cost": self.node_cost,
            "transport_type": self.transport_type
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Announcement":
        return cls(
            type=data.get("type", "announce"),
            from_node=data.get("from", ""),
            capabilities=[
                CapabilityInfo.from_dict(c) for c in data.get("capabilities", [])
            ],
            resources=ResourceInfo.from_dict(data["resources"]) if data.get("resources") else None,
            endpoints=EndpointInfo.from_dict(data["endpoints"]) if data.get("endpoints") else None,
            timestamp=data.get("timestamp", time.time()),
            ttl=data.get("ttl", MAX_TTL),
            nonce=data.get("nonce", ""),
            ihave=data.get("ihave", []),
            iwant=data.get("iwant", []),
            node_cost=data.get("node_cost", 1.0),
            transport_type=data.get("transport_type", "")
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, data: str) -> "Announcement":
        return cls.from_dict(json.loads(data))


# Type for broadcast callback
BroadcastCallback = Callable[[str, bytes], Awaitable[None]]


class GossipProtocol:
    """
    Gossip protocol for capability propagation.
    
    Periodically announces capabilities to peers. Processes incoming
    announcements and updates gradient table. Propagates dynamic
    endpoint information for multi-homed networking.
    
    Enhanced with smart routing table for true mesh routing.
    """

    def __init__(
        self,
        node_id: str,
        gradient_table: GradientTable,
        local_capabilities: List[CapabilityInfo],
        announce_interval: float = ANNOUNCE_INTERVAL_SEC,
        endpoint_registry: Optional[EndpointRegistry] = None
    ):
        self.node_id = node_id
        self.gradient_table = gradient_table
        self.local_capabilities = local_capabilities
        self.announce_interval = announce_interval
        self.endpoint_registry = endpoint_registry

        self._broadcast_callback: Optional[BroadcastCallback] = None
        self._ui_event_callback: Optional[UIEventCallback] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._nonce_cache: Dict[str, float] = {}
        self._nonce_cache_lock = asyncio.Lock()
        self._known_nodes: Dict[str, float] = {}

        # Smart routing table
        self.routing_table = RoutingTable(node_id)
        
        # Metrics
        self._announcements_sent = 0
        self._announcements_received = 0
        self._announcements_forwarded = 0
        self._endpoint_updates = 0
        self._route_updates = 0

    def set_broadcast_callback(self, callback: BroadcastCallback) -> None:
        """Set the callback for broadcasting messages to peers."""
        self._broadcast_callback = callback
    
    def set_ui_event_callback(self, callback: UIEventCallback) -> None:
        """Set the callback for broadcasting events to UI clients."""
        self._ui_event_callback = callback
    
    async def _emit_ui_event(self, event: dict) -> None:
        """Emit an event to UI clients if callback is set."""
        if self._ui_event_callback:
            try:
                await self._ui_event_callback(event)
            except Exception as e:
                logger.debug(f"Failed to emit UI event: {e}")

    def update_local_capabilities(self, capabilities: List[CapabilityInfo]) -> None:
        """Update the list of local capabilities."""
        self.local_capabilities = capabilities

    def get_resource_info(self) -> ResourceInfo:
        """Get current resource usage with dynamic cost factors."""
        import psutil
        try:
            cpu_percent = psutil.cpu_percent(interval=None)  # Non-blocking
            cpu_available = 1.0 - (cpu_percent / 100.0)
            mem = psutil.virtual_memory()
            memory_available_mb = mem.available // (1024 * 1024)
            memory_percent = mem.percent
            
            # Get battery status
            battery_percent = None
            plugged_in = True
            try:
                battery = psutil.sensors_battery()
                if battery:
                    battery_percent = int(battery.percent)
                    plugged_in = battery.power_plugged
            except Exception:
                pass  # No battery (desktop)
            
            return ResourceInfo(
                cpu_available=cpu_available,
                memory_available_mb=memory_available_mb,
                gpu_available=0.8,
                battery_percent=battery_percent,
                plugged_in=plugged_in,
                cpu_load=cpu_percent / 100.0,
                memory_percent=memory_percent
            )
        except Exception as e:
            logger.warning(f"Failed to get resource info: {e}")
            return ResourceInfo()

    def build_announcement(self, transport_type: str = "") -> Announcement:
        """Build an announcement message with capabilities, endpoints, and dynamic cost."""
        capabilities = []
        ihave_ids = []  # IHAVE: capability IDs we have

        for cap in self.local_capabilities[:MAX_CAPABILITIES_PER_ANNOUNCE]:
            capabilities.append(CapabilityInfo(
                id=cap.id,
                label=cap.label,
                description=cap.description,
                vector=cap.vector if isinstance(cap.vector, list) else cap.vector.tolist(),
                local=True,
                hops=0,
                models=cap.models,
                constraints=cap.constraints
            ))
            ihave_ids.append(cap.id)

        remaining_slots = MAX_CAPABILITIES_PER_ANNOUNCE - len(capabilities)
        for entry_dict in self.gradient_table.export_for_gossip(max_hops=5)[:remaining_slots]:
            entry = GradientEntry.from_dict(entry_dict)
            capabilities.append(CapabilityInfo(
                id=entry.capability_id,
                label=entry.capability_label,
                description="",
                vector=entry.capability_vector.tolist(),
                local=False,
                hops=entry.hops,
                via=entry.via_node,
                estimated_latency_ms=entry.estimated_latency_ms
            ))
            ihave_ids.append(entry.capability_id)

        # Get current endpoint info (with refreshed IPs)
        endpoint_info = None
        if self.endpoint_registry:
            self.endpoint_registry.refresh_my_ips()
            endpoint_info = self.endpoint_registry.get_my_endpoint_info()

        # Calculate dynamic node cost
        resources = self.get_resource_info()
        node_cost = resources.calculate_cost()

        return Announcement(
            from_node=self.node_id,
            capabilities=capabilities,
            resources=resources,
            endpoints=endpoint_info,
            ttl=MAX_TTL,
            ihave=ihave_ids,
            iwant=[],  # Can be populated with capability requests
            node_cost=node_cost,
            transport_type=transport_type
        )

    async def announce(self) -> None:
        """Broadcast capability announcement to all peers."""
        if not self._broadcast_callback:
            return

        announcement = self.build_announcement()
        data = announcement.to_json().encode()

        try:
            await self._broadcast_callback(self.node_id, data)
            self._announcements_sent += 1
            
            # Emit UI event for gossip announcement sent
            await self._emit_ui_event({
                "type": "gossip_sent",
                "event": "announcement_sent",
                "from_node": self.node_id,
                "capability_count": len(announcement.capabilities),
                "ttl": announcement.ttl,
                "node_cost": announcement.node_cost,
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Failed to broadcast announcement: {e}")

    async def handle_announcement(
        self,
        data: bytes,
        from_peer: str,
        forward_callback: Optional[BroadcastCallback] = None
    ) -> None:
        """Handle an incoming announcement."""
        try:
            announcement = Announcement.from_json(data.decode())
        except Exception as e:
            logger.warning(f"Invalid announcement from {from_peer}: {e}")
            return

        if not await self._check_nonce(announcement.nonce, announcement.timestamp):
            return

        self._announcements_received += 1
        self._known_nodes[announcement.from_node] = time.time()

        # Emit UI event for gossip announcement received
        await self._emit_ui_event({
            "type": "gossip_received",
            "event": "announcement_received",
            "from_node": announcement.from_node,
            "from_peer": from_peer,
            "capability_count": len(announcement.capabilities),
            "capabilities": [c.label for c in announcement.capabilities[:10]],
            "ttl": announcement.ttl,
            "node_cost": announcement.node_cost,
            "timestamp": time.time()
        })

        # Update endpoint registry with peer's current IPs
        if announcement.endpoints and self.endpoint_registry:
            if self.endpoint_registry.update_peer(announcement.endpoints):
                self._endpoint_updates += 1
                logger.info(f"Updated endpoints for {announcement.from_node}: {announcement.endpoints.local_ips}")

        # Update routing table from announcement
        route_updates = self.routing_table.on_peer_announcement(announcement.to_dict())
        if route_updates > 0:
            self._route_updates += route_updates
            logger.debug(f"Routing table: {route_updates} route updates from {announcement.from_node}")
            
            # Emit UI event for routing table updates
            await self._emit_ui_event({
                "type": "routing_update",
                "event": "routes_updated",
                "from_node": announcement.from_node,
                "updates": route_updates,
                "total_routes": len(self.routing_table.routes),
                "timestamp": time.time()
            })

        updates = 0
        for cap in announcement.capabilities:
            vector = np.array(cap.vector, dtype=np.float32)
            new_hops = cap.hops + 1 if not cap.local else 1

            updated = self.gradient_table.update(
                capability_id=cap.id,
                capability_label=cap.label,
                capability_vector=vector,
                hops=new_hops,
                next_hop=from_peer,
                via_node=cap.via or announcement.from_node,
                estimated_latency_ms=cap.estimated_latency_ms + 10
            )
            if updated:
                updates += 1

        if announcement.ttl > 1 and forward_callback:
            forwarded = Announcement(
                from_node=announcement.from_node,
                capabilities=announcement.capabilities,
                resources=announcement.resources,
                timestamp=announcement.timestamp,
                ttl=announcement.ttl - 1,
                nonce=announcement.nonce
            )

            for cap in forwarded.capabilities:
                if not cap.local:
                    cap.hops += 1

            try:
                await forward_callback(self.node_id, forwarded.to_json().encode())
                self._announcements_forwarded += 1
            except Exception as e:
                logger.error(f"Failed to forward announcement: {e}")

    async def _check_nonce(self, nonce: str, timestamp: float) -> bool:
        """Check if nonce is new (not a replay)."""
        now = time.time()

        if abs(now - timestamp) > NONCE_CACHE_SEC:
            return False

        async with self._nonce_cache_lock:
            expired = [
                n for n, t in self._nonce_cache.items()
                if now - t > NONCE_CACHE_SEC
            ]
            for n in expired:
                del self._nonce_cache[n]

            if nonce in self._nonce_cache:
                return False

            self._nonce_cache[nonce] = timestamp
            return True

    async def _announce_loop(self) -> None:
        """Periodic announcement loop."""
        while self._running:
            try:
                await self.announce()
            except Exception as e:
                logger.error(f"Announcement failed: {e}")
            await asyncio.sleep(self.announce_interval)

    async def start(self) -> None:
        """Start periodic announcements."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._announce_loop())
        logger.info("Gossip protocol started")

    async def stop(self) -> None:
        """Stop periodic announcements."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Gossip protocol stopped")

    def known_nodes(self) -> Set[str]:
        """Return set of nodes we've heard from recently."""
        now = time.time()
        return {
            node_id for node_id, last_seen in self._known_nodes.items()
            if now - last_seen < NONCE_CACHE_SEC
        }

    def stats(self) -> dict:
        """Get gossip protocol statistics."""
        # Calculate current node cost
        resources = self.get_resource_info()
        node_cost = resources.calculate_cost()
        
        stats = {
            "announcements_sent": self._announcements_sent,
            "announcements_received": self._announcements_received,
            "announcements_forwarded": self._announcements_forwarded,
            "endpoint_updates": self._endpoint_updates,
            "route_updates": self._route_updates,
            "known_nodes": len(self.known_nodes()),
            "gradient_table_size": len(self.gradient_table),
            "node_cost": node_cost,
            "cost_factors": {
                "cpu_load": resources.cpu_load,
                "memory_percent": resources.memory_percent,
                "battery_percent": resources.battery_percent,
                "plugged_in": resources.plugged_in
            }
        }
        
        # Add routing table stats
        stats["routing"] = self.routing_table.stats()
        
        # Add endpoint registry info if available
        if self.endpoint_registry:
            my_info = self.endpoint_registry.get_my_endpoint_info()
            stats["my_endpoints"] = {
                "local_ips": my_info.local_ips,
                "port": my_info.local_port,
                "relay": my_info.relay_url
            }
            stats["known_peer_endpoints"] = len(self.endpoint_registry.get_all_peers())
        
        return stats
    
    def get_routing_table(self) -> RoutingTable:
        """Get the routing table for external access."""
        return self.routing_table
    
    def get_best_route(self, dest_id: str) -> Optional[RouteEntry]:
        """Get the best route to a destination node."""
        return self.routing_table.get_best_route(dest_id)
