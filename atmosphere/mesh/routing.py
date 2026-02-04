"""
Smart Routing Table for Atmosphere Mesh.

True mesh routing with multi-transport support, cost-based selection,
and automatic failover.
"""

import asyncio
import time
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class TransportType(Enum):
    """Available transport types."""
    BLE = "ble"
    LAN = "lan"
    RELAY = "relay"
    WIFI_DIRECT = "wifi_direct"
    MATTER = "matter"


@dataclass
class RouteEntry:
    """A route to a destination node."""
    destination: str
    next_hop: str
    transport: TransportType
    hop_count: int
    latency_ms: float
    last_updated: float
    # Quality metrics
    reliability: float = 1.0  # 0-1 delivery success rate
    bandwidth_kbps: float = 0.0  # Estimated bandwidth
    cost: float = 1.0  # Computed cost for routing decisions
    # Source info
    via_node: Optional[str] = None  # Original source (for multi-hop)
    capabilities: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "destination": self.destination,
            "next_hop": self.next_hop,
            "transport": self.transport.value,
            "hop_count": self.hop_count,
            "latency_ms": self.latency_ms,
            "last_updated": self.last_updated,
            "reliability": self.reliability,
            "bandwidth_kbps": self.bandwidth_kbps,
            "cost": self.cost,
            "via_node": self.via_node,
            "capabilities": self.capabilities,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "RouteEntry":
        return cls(
            destination=data["destination"],
            next_hop=data["next_hop"],
            transport=TransportType(data.get("transport", "relay")),
            hop_count=data.get("hop_count", 1),
            latency_ms=data.get("latency_ms", 100),
            last_updated=data.get("last_updated", time.time()),
            reliability=data.get("reliability", 1.0),
            bandwidth_kbps=data.get("bandwidth_kbps", 0),
            cost=data.get("cost", 1.0),
            via_node=data.get("via_node"),
            capabilities=data.get("capabilities", []),
        )
    
    def compute_cost(self) -> float:
        """
        Compute routing cost (lower is better).
        
        Formula: cost = (latency_factor + hop_factor) / reliability
        
        Prefers: low latency, fewer hops, high reliability
        """
        # Normalize latency (0-1 scale, 1000ms = 1.0)
        latency_factor = min(1.0, self.latency_ms / 1000)
        
        # Normalize hops (0-1 scale, 10 hops = 1.0)
        hop_factor = min(1.0, self.hop_count / 10)
        
        # Combine factors
        base_cost = (latency_factor * 0.6 + hop_factor * 0.4)
        
        # Adjust by reliability (divide by reliability, minimum 0.1)
        self.cost = base_cost / max(0.1, self.reliability)
        
        return self.cost
    
    @property
    def is_stale(self) -> bool:
        """Check if route is stale (not updated in 5 minutes)."""
        return time.time() - self.last_updated > 300


class RoutingTable:
    """
    Smart routing table with multi-path support.
    
    Features:
    - Multiple routes per destination (different transports)
    - Automatic best route selection
    - Route aging and cleanup
    - Learning from gossip announcements
    - Persistence to disk
    """
    
    # Route for each destination, keyed by (destination, transport)
    routes: Dict[tuple, RouteEntry]
    
    # Callback for route changes
    on_route_change: Optional[Callable[[str, RouteEntry], None]]
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.routes: Dict[tuple, RouteEntry] = {}
        self.on_route_change = None
        self._lock = asyncio.Lock()
        
        # Stats
        self.route_updates = 0
        self.route_lookups = 0
    
    def get_best_route(self, dest_id: str) -> Optional[RouteEntry]:
        """
        Get the best route to a destination.
        
        Selection criteria (in order):
        1. Non-stale routes
        2. Lowest cost (computed from latency, hops, reliability)
        3. Prefer direct (1-hop) routes
        """
        self.route_lookups += 1
        
        candidates = []
        for (dest, transport), entry in self.routes.items():
            if dest == dest_id and not entry.is_stale:
                entry.compute_cost()
                candidates.append(entry)
        
        if not candidates:
            return None
        
        # Sort by cost (ascending), then by hop_count (ascending)
        candidates.sort(key=lambda r: (r.cost, r.hop_count))
        return candidates[0]
    
    def get_all_routes(self, dest_id: str) -> List[RouteEntry]:
        """Get all known routes to a destination."""
        routes = []
        for (dest, transport), entry in self.routes.items():
            if dest == dest_id:
                entry.compute_cost()
                routes.append(entry)
        routes.sort(key=lambda r: r.cost)
        return routes
    
    def update_route(
        self,
        dest_id: str,
        via: str,
        transport: TransportType,
        hops: int,
        latency_ms: float = 100,
        reliability: float = 1.0,
        capabilities: List[str] = None,
        via_node: Optional[str] = None,
    ) -> bool:
        """
        Update or add a route entry.
        
        Returns True if this is a new or improved route.
        """
        key = (dest_id, transport)
        now = time.time()
        
        new_entry = RouteEntry(
            destination=dest_id,
            next_hop=via,
            transport=transport,
            hop_count=hops,
            latency_ms=latency_ms,
            last_updated=now,
            reliability=reliability,
            via_node=via_node or dest_id,
            capabilities=capabilities or [],
        )
        new_entry.compute_cost()
        
        # Check if this is better than existing
        existing = self.routes.get(key)
        if existing:
            existing.compute_cost()
            # Update if: newer, better cost, or same cost but fresher
            if new_entry.cost < existing.cost or (
                new_entry.cost <= existing.cost * 1.1 and 
                new_entry.last_updated > existing.last_updated
            ):
                self.routes[key] = new_entry
                self.route_updates += 1
                if self.on_route_change:
                    self.on_route_change(dest_id, new_entry)
                return True
            else:
                # Just update timestamp if route is similar
                existing.last_updated = now
                return False
        else:
            # New route
            self.routes[key] = new_entry
            self.route_updates += 1
            if self.on_route_change:
                self.on_route_change(dest_id, new_entry)
            return True
    
    def on_peer_announcement(self, announcement: dict) -> int:
        """
        Learn routes from gossip announcement.
        
        Extracts:
        - Direct route to announcing node
        - Multi-hop routes to nodes announced by that node
        
        Returns number of routes updated.
        """
        from_node = announcement.get("from", "")
        if not from_node or from_node == self.node_id:
            return 0
        
        updates = 0
        
        # Determine transport type from announcement
        endpoints = announcement.get("endpoints")
        transport = TransportType.RELAY  # Default
        if endpoints:
            if endpoints.get("local_ips"):
                transport = TransportType.LAN
            # Could add BLE detection here
        
        # Direct route to announcing node
        if self.update_route(
            dest_id=from_node,
            via=from_node,
            transport=transport,
            hops=1,
            latency_ms=announcement.get("latency_ms", 50),
            capabilities=[c.get("label", c.get("id", "")) for c in announcement.get("capabilities", [])],
        ):
            updates += 1
        
        # Multi-hop routes from announced capabilities
        for cap in announcement.get("capabilities", []):
            via_node = cap.get("via")
            if via_node and via_node != from_node and via_node != self.node_id:
                # This capability came from another node via from_node
                hops = cap.get("hops", 1) + 1  # Add our hop
                if self.update_route(
                    dest_id=via_node,
                    via=from_node,  # Next hop is the announcing node
                    transport=transport,
                    hops=hops,
                    latency_ms=cap.get("estimated_latency_ms", 100) + 10,
                    via_node=via_node,
                    capabilities=[cap.get("label", cap.get("id", ""))],
                ):
                    updates += 1
        
        return updates
    
    def remove_peer(self, peer_id: str):
        """Remove all routes through a peer."""
        to_remove = [
            key for key, entry in self.routes.items()
            if entry.next_hop == peer_id or entry.destination == peer_id
        ]
        for key in to_remove:
            del self.routes[key]
    
    def cleanup_stale(self) -> int:
        """Remove stale routes. Returns count removed."""
        to_remove = [key for key, entry in self.routes.items() if entry.is_stale]
        for key in to_remove:
            del self.routes[key]
        return len(to_remove)
    
    def get_destinations(self) -> List[str]:
        """Get all known destinations."""
        return list(set(dest for dest, _ in self.routes.keys()))
    
    def get_transport_status(self) -> Dict[str, dict]:
        """Get status of each transport type."""
        status = {}
        for transport in TransportType:
            routes = [e for (_, t), e in self.routes.items() if t == transport]
            if routes:
                status[transport.value] = {
                    "route_count": len(routes),
                    "avg_latency_ms": sum(r.latency_ms for r in routes) / len(routes),
                    "avg_reliability": sum(r.reliability for r in routes) / len(routes),
                    "destinations": list(set(r.destination for r in routes)),
                }
        return status
    
    def export(self) -> List[dict]:
        """Export all routes for API/persistence."""
        return [entry.to_dict() for entry in self.routes.values()]
    
    def import_routes(self, routes: List[dict]):
        """Import routes from persistence."""
        for data in routes:
            entry = RouteEntry.from_dict(data)
            key = (entry.destination, entry.transport)
            self.routes[key] = entry
    
    def stats(self) -> dict:
        """Get routing table statistics."""
        now = time.time()
        active_routes = [e for e in self.routes.values() if not e.is_stale]
        
        return {
            "total_routes": len(self.routes),
            "active_routes": len(active_routes),
            "stale_routes": len(self.routes) - len(active_routes),
            "unique_destinations": len(self.get_destinations()),
            "route_updates": self.route_updates,
            "route_lookups": self.route_lookups,
            "transport_breakdown": {
                t.value: len([e for (_, tt), e in self.routes.items() if tt == t])
                for t in TransportType
            },
        }


# ============================================================================
# Mesh Persistence
# ============================================================================

@dataclass
class SavedMesh:
    """A saved mesh configuration."""
    mesh_id: str
    mesh_name: str
    peers: List[dict]  # List of peer info dicts
    endpoints: List[str]  # Known endpoints
    created_at: float
    last_connected: float
    is_founder: bool = False
    public_key: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "mesh_id": self.mesh_id,
            "mesh_name": self.mesh_name,
            "peers": self.peers,
            "endpoints": self.endpoints,
            "created_at": self.created_at,
            "last_connected": self.last_connected,
            "is_founder": self.is_founder,
            "public_key": self.public_key,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SavedMesh":
        return cls(
            mesh_id=data["mesh_id"],
            mesh_name=data["mesh_name"],
            peers=data.get("peers", []),
            endpoints=data.get("endpoints", []),
            created_at=data.get("created_at", time.time()),
            last_connected=data.get("last_connected", time.time()),
            is_founder=data.get("is_founder", False),
            public_key=data.get("public_key"),
        )


class MeshPersistence:
    """
    Persistence layer for mesh configurations.
    
    Saves to ~/.atmosphere/meshes.json
    """
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path.home() / ".atmosphere"
        self.meshes_file = self.config_dir / "meshes.json"
        self._meshes: Dict[str, SavedMesh] = {}
        self._active_mesh: Optional[str] = None
        self._lock = asyncio.Lock()
    
    def load(self) -> bool:
        """Load meshes from disk."""
        if not self.meshes_file.exists():
            logger.info("No meshes.json found, starting fresh")
            return False
        
        try:
            with open(self.meshes_file) as f:
                data = json.load(f)
            
            self._meshes = {
                mesh_id: SavedMesh.from_dict(mesh_data)
                for mesh_id, mesh_data in data.get("meshes", {}).items()
            }
            self._active_mesh = data.get("active_mesh")
            
            logger.info(f"Loaded {len(self._meshes)} meshes, active: {self._active_mesh}")
            return True
        except Exception as e:
            logger.error(f"Failed to load meshes: {e}")
            return False
    
    def save(self) -> bool:
        """Save meshes to disk."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            data = {
                "meshes": {
                    mesh_id: mesh.to_dict()
                    for mesh_id, mesh in self._meshes.items()
                },
                "active_mesh": self._active_mesh,
                "version": 1,
                "saved_at": time.time(),
            }
            
            with open(self.meshes_file, "w") as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved {len(self._meshes)} meshes")
            return True
        except Exception as e:
            logger.error(f"Failed to save meshes: {e}")
            return False
    
    def add_mesh(self, mesh: SavedMesh) -> None:
        """Add or update a mesh."""
        self._meshes[mesh.mesh_id] = mesh
        self.save()
    
    def remove_mesh(self, mesh_id: str) -> bool:
        """Remove a mesh. Returns True if found and removed."""
        if mesh_id in self._meshes:
            del self._meshes[mesh_id]
            if self._active_mesh == mesh_id:
                self._active_mesh = None
            self.save()
            return True
        return False
    
    def get_mesh(self, mesh_id: str) -> Optional[SavedMesh]:
        """Get a mesh by ID."""
        return self._meshes.get(mesh_id)
    
    def list_meshes(self) -> List[SavedMesh]:
        """List all saved meshes."""
        return list(self._meshes.values())
    
    def set_active_mesh(self, mesh_id: Optional[str]) -> bool:
        """Set the active mesh. Returns True if mesh exists."""
        if mesh_id is None:
            self._active_mesh = None
            self.save()
            return True
        if mesh_id in self._meshes:
            self._active_mesh = mesh_id
            self._meshes[mesh_id].last_connected = time.time()
            self.save()
            return True
        return False
    
    def get_active_mesh(self) -> Optional[SavedMesh]:
        """Get the active mesh."""
        if self._active_mesh:
            return self._meshes.get(self._active_mesh)
        return None
    
    @property
    def active_mesh_id(self) -> Optional[str]:
        return self._active_mesh
    
    def update_mesh_peers(self, mesh_id: str, peers: List[dict]) -> bool:
        """Update the peer list for a mesh."""
        if mesh_id in self._meshes:
            self._meshes[mesh_id].peers = peers
            self._meshes[mesh_id].last_connected = time.time()
            self.save()
            return True
        return False
    
    def update_mesh_endpoints(self, mesh_id: str, endpoints: List[str]) -> bool:
        """Update the endpoint list for a mesh."""
        if mesh_id in self._meshes:
            self._meshes[mesh_id].endpoints = endpoints
            self.save()
            return True
        return False


# Singleton instance
_mesh_persistence: Optional[MeshPersistence] = None


def get_mesh_persistence() -> MeshPersistence:
    """Get or create the mesh persistence singleton."""
    global _mesh_persistence
    if _mesh_persistence is None:
        _mesh_persistence = MeshPersistence()
        _mesh_persistence.load()
    return _mesh_persistence
