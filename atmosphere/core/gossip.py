"""
Gossip Protocol for Capability Distribution

Manages peer-to-peer gossip of capability announcements across the mesh.
Each node broadcasts its capabilities, receives announcements from peers,
and maintains a gradient table for routing.
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
import json

from .capability import CapabilityAnnouncement
from ..router.gradient import GradientTable, GradientEntry
import numpy as np

logger = logging.getLogger(__name__)


# Gossip message types
GOSSIP_MSG_ANNOUNCE = "capability_announce"  # Use underscore for cross-platform compat
GOSSIP_MSG_REQUEST = "capability_request"   # Use underscore for cross-platform compat
GOSSIP_MSG_RESPONSE = "capability_response"  # Use underscore for cross-platform compat

# Configuration
GOSSIP_INTERVAL_SEC = 30  # Broadcast capabilities every 30 seconds
GOSSIP_EXPIRY_SEC = 300   # Capabilities expire after 5 minutes


@dataclass
class GossipMessage:
    """
    Gossip protocol message format.
    
    Schema:
    {
        "type": "capability_announce" | "capability_request" | "capability_response",
        "node_id": "abc123...",
        "timestamp": 1234567890.123,
        "capabilities": [...],  // For announce/response
        "ttl": 10,
        "nonce": "abc123...",  // For deduplication
        "signature": "..."
    }
    """
    type: str
    node_id: str
    timestamp: float
    capabilities: List[Dict] = None
    ttl: int = 10
    nonce: str = ""  # Added for deduplication
    signature: str = ""
    
    def __post_init__(self):
        """Generate nonce if not provided."""
        import uuid
        if not self.nonce:
            self.nonce = uuid.uuid4().hex[:16]
    
    def to_dict(self) -> dict:
        """Serialize for transmission."""
        return {
            "type": self.type,
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "capabilities": self.capabilities or [],
            "ttl": self.ttl,
            "nonce": self.nonce,
            "signature": self.signature,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "GossipMessage":
        """Deserialize from transmission."""
        return cls(
            type=data["type"],
            node_id=data["node_id"],
            timestamp=data.get("timestamp", time.time()),
            capabilities=data.get("capabilities", []),
            ttl=data.get("ttl", 10),
            nonce=data.get("nonce", ""),
            signature=data.get("signature", ""),
        )
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "GossipMessage":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


class GossipManager:
    """
    Manages capability gossip protocol.
    
    Responsibilities:
    - Broadcast local capabilities to all peers
    - Receive and process capability announcements
    - Update gradient table with routing information
    - Handle capability requests/responses
    - Maintain freshness (re-broadcast periodically)
    - Deduplicate via nonce cache
    - Forward announcements with TTL > 1
    """
    
    def __init__(
        self,
        node_id: str,
        gradient_table: GradientTable,
        send_to_relay: Optional[Callable] = None,
        gossip_interval: float = GOSSIP_INTERVAL_SEC,
        expiry_sec: float = GOSSIP_EXPIRY_SEC,
    ):
        """
        Initialize gossip manager.
        
        Args:
            node_id: This node's ID
            gradient_table: Shared gradient table for routing
            send_to_relay: Async function to send messages to relay
            gossip_interval: How often to broadcast capabilities (seconds)
            expiry_sec: How long capabilities remain valid (seconds)
        """
        self.node_id = node_id
        self.gradient_table = gradient_table
        self.send_to_relay = send_to_relay
        self.gossip_interval = gossip_interval
        self.expiry_sec = expiry_sec
        
        # Local capabilities we're announcing
        self._local_capabilities: Dict[str, CapabilityAnnouncement] = {}
        
        # Remote capabilities we've learned about (node_id -> capabilities)
        self._remote_capabilities: Dict[str, Dict[str, CapabilityAnnouncement]] = {}
        
        # Nonce cache for deduplication (nonce -> timestamp)
        self._seen_nonces: Dict[str, float] = {}
        self._nonce_cache_ttl = 300  # 5 minutes
        
        # Background task handle
        self._gossip_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"GossipManager initialized for node {node_id}")
    
    def add_local_capability(self, capability: CapabilityAnnouncement) -> None:
        """
        Register a local capability for announcement.
        
        This should be called when:
        - LlamaFarm discovers a new project
        - A sensor becomes available
        - An agent registers a tool
        """
        capability.node_id = self.node_id
        capability.hops = 0
        capability.via_node = None
        
        self._local_capabilities[capability.capability_id] = capability
        
        # Also add to gradient table (hops=0, local)
        self._update_gradient_table(capability)
        
        logger.info(f"Added local capability: {capability.capability_id}")
    
    def remove_local_capability(self, capability_id: str) -> bool:
        """Remove a local capability."""
        if capability_id in self._local_capabilities:
            del self._local_capabilities[capability_id]
            self.gradient_table.remove(capability_id)
            logger.info(f"Removed local capability: {capability_id}")
            return True
        return False
    
    def get_local_capabilities(self) -> List[CapabilityAnnouncement]:
        """Get all local capabilities."""
        return list(self._local_capabilities.values())
    
    def _build_announce_message(self) -> dict:
        """Build a gossip announce message dict (for direct send without relay)."""
        capabilities = list(self._local_capabilities.values())
        now = time.time()
        for cap in capabilities:
            cap.timestamp = now
            cap.expires_at = now + 300
        cap_dicts = [cap.to_dict() for cap in capabilities]
        msg = GossipMessage(
            type=GOSSIP_MSG_ANNOUNCE,
            node_id=self.node_id,
            timestamp=now,
            capabilities=cap_dicts,
            ttl=10,
        )
        return msg.to_dict()

    async def broadcast_capabilities(
        self,
        capabilities: Optional[List[CapabilityAnnouncement]] = None
    ) -> None:
        """
        Broadcast capabilities to all peers via relay.
        
        Args:
            capabilities: Specific capabilities to broadcast, or None for all local
        """
        if capabilities is None:
            capabilities = list(self._local_capabilities.values())
        
        if not capabilities:
            logger.debug("No capabilities to broadcast")
            return
        
        if not self.send_to_relay:
            logger.warning("No relay send function configured")
            return
        
        # Refresh timestamps before broadcast (capabilities expire after 5 min)
        now = time.time()
        for cap in capabilities:
            cap.timestamp = now
            cap.expires_at = now + 300  # 5 minutes
        
        # Serialize capabilities
        cap_dicts = [cap.to_dict() for cap in capabilities]
        
        # Create gossip message
        msg = GossipMessage(
            type=GOSSIP_MSG_ANNOUNCE,
            node_id=self.node_id,
            timestamp=time.time(),
            capabilities=cap_dicts,
            ttl=10,
        )
        
        # Send to relay (broadcast to all peers)
        # Relay expects "type": "broadcast", not "mesh.broadcast"
        try:
            await self.send_to_relay({
                "type": "broadcast",
                "payload": msg.to_dict(),
            })
            print(f"[GOSSIP] Broadcasted {len(capabilities)} capabilities", flush=True)
            logger.debug(f"Broadcasted {len(capabilities)} capabilities")
        except Exception as e:
            logger.error(f"Failed to broadcast capabilities: {e}")
    
    def _check_nonce(self, nonce: str) -> bool:
        """
        Check if nonce is new (not a replay). Returns True if new, False if seen.
        """
        now = time.time()
        
        # Cleanup expired nonces
        expired = [n for n, t in self._seen_nonces.items() 
                   if now - t > self._nonce_cache_ttl]
        for n in expired:
            del self._seen_nonces[n]
        
        # Check if we've seen this nonce
        if nonce in self._seen_nonces:
            return False
        
        # Mark as seen
        self._seen_nonces[nonce] = now
        return True
    
    async def handle_announcement(
        self,
        node_id: str,
        announcement: Dict
    ) -> None:
        """
        Handle incoming capability announcement from a peer.
        
        Args:
            node_id: Source node ID (who sent it to us, may differ from originator)
            announcement: Gossip message dict
        """
        try:
            msg = GossipMessage.from_dict(announcement)
            
            if msg.type != GOSSIP_MSG_ANNOUNCE:
                logger.warning(f"Unexpected message type: {msg.type}")
                return
            
            # Ignore our own announcements
            if msg.node_id == self.node_id:
                return
            
            # Check TTL
            if msg.ttl <= 0:
                logger.debug(f"Dropping announcement with TTL=0 from {node_id}")
                return
            
            # Nonce deduplication - skip if we've already processed this
            if not self._check_nonce(msg.nonce):
                logger.debug(f"Dropping duplicate announcement (nonce={msg.nonce[:8]}...) from {node_id}")
                return
            
            # Process each capability
            capabilities = []
            for cap_dict in msg.capabilities:
                try:
                    cap = CapabilityAnnouncement.from_dict(cap_dict)
                    
                    # Skip expired
                    if cap.is_expired():
                        continue
                    
                    # Increment hops (we're learning about it from node_id)
                    cap.hops += 1
                    cap.via_node = node_id
                    cap.ttl = msg.ttl - 1
                    
                    capabilities.append(cap)
                    
                    # Update gradient table
                    self._update_gradient_table(cap)
                    
                except Exception as e:
                    logger.error(f"Failed to parse capability: {e}")
                    continue
            
            # Store remote capabilities
            if capabilities:
                if msg.node_id not in self._remote_capabilities:
                    self._remote_capabilities[msg.node_id] = {}
                
                for cap in capabilities:
                    self._remote_capabilities[msg.node_id][cap.capability_id] = cap
                
                logger.info(
                    f"Learned {len(capabilities)} capabilities from {msg.node_id} "
                    f"via {node_id} (hops={capabilities[0].hops}, ttl={msg.ttl})"
                )
            
            # Forward if TTL > 1 (multi-hop propagation)
            if msg.ttl > 1 and self.send_to_relay:
                forwarded_msg = GossipMessage(
                    type=msg.type,
                    node_id=msg.node_id,  # Keep original source
                    timestamp=msg.timestamp,
                    capabilities=msg.capabilities,
                    ttl=msg.ttl - 1,  # Decrement TTL
                    nonce=msg.nonce,  # Keep same nonce for deduplication
                    signature=msg.signature,
                )
                try:
                    await self.send_to_relay({
                        "type": "broadcast",
                        "payload": forwarded_msg.to_dict(),
                    })
                    logger.debug(f"Forwarded announcement from {msg.node_id} (ttl={msg.ttl - 1})")
                except Exception as e:
                    logger.warning(f"Failed to forward announcement: {e}")
        
        except Exception as e:
            logger.error(f"Failed to handle announcement: {e}")
    
    def _update_gradient_table(self, capability: CapabilityAnnouncement) -> None:
        """
        Update gradient table with capability routing information.
        
        This converts the capability announcement into a gradient table entry.
        """
        # Determine next hop
        next_hop = capability.via_node if capability.hops > 0 else self.node_id
        
        # Convert embedding to numpy array if present
        capability_vector = None
        if capability.embedding:
            capability_vector = np.array(capability.embedding, dtype=np.float32)
        else:
            # Create zero vector if no embedding
            capability_vector = np.zeros(384, dtype=np.float32)
        
        # Update gradient table
        updated = self.gradient_table.update(
            capability_id=capability.capability_id,
            capability_label=capability.label or capability.capability_id,
            capability_vector=capability_vector,
            hops=capability.hops,
            next_hop=next_hop,
            via_node=capability.via_node or self.node_id,
            estimated_latency_ms=capability.estimated_latency_ms,
        )
        
        if updated:
            logger.debug(
                f"Updated gradient table: {capability.capability_id} "
                f"(hops={capability.hops}, next_hop={next_hop})"
            )
    
    def get_all_capabilities(self) -> List[CapabilityAnnouncement]:
        """
        Get all known capabilities across the mesh.
        
        Returns:
            Combined list of local + remote capabilities
        """
        capabilities = []
        
        # Add local capabilities
        capabilities.extend(self._local_capabilities.values())
        
        # Add remote capabilities from all nodes
        for node_caps in self._remote_capabilities.values():
            capabilities.extend(node_caps.values())
        
        # Filter expired
        capabilities = [cap for cap in capabilities if not cap.is_expired()]
        
        return capabilities
    
    def get_capabilities_by_node(self, node_id: str) -> List[CapabilityAnnouncement]:
        """Get capabilities announced by a specific node."""
        if node_id == self.node_id:
            return list(self._local_capabilities.values())
        
        node_caps = self._remote_capabilities.get(node_id, {})
        return [cap for cap in node_caps.values() if not cap.is_expired()]
    
    def invalidate_node(self, node_id: str) -> int:
        """
        Remove all capabilities from a disconnected node.
        
        Returns:
            Number of capabilities removed
        """
        count = 0
        
        # Remove from remote capabilities
        if node_id in self._remote_capabilities:
            count = len(self._remote_capabilities[node_id])
            del self._remote_capabilities[node_id]
        
        # Remove from gradient table
        count += self.gradient_table.invalidate_node(node_id)
        
        if count > 0:
            logger.info(f"Invalidated {count} capabilities from node {node_id}")
        
        return count
    
    def prune_expired(self) -> int:
        """
        Remove expired capabilities.
        
        Returns:
            Number of capabilities pruned
        """
        count = 0
        
        # Prune remote capabilities
        for node_id in list(self._remote_capabilities.keys()):
            node_caps = self._remote_capabilities[node_id]
            expired = [
                cap_id for cap_id, cap in node_caps.items()
                if cap.is_expired()
            ]
            for cap_id in expired:
                del node_caps[cap_id]
                count += 1
            
            # Remove node if no capabilities left
            if not node_caps:
                del self._remote_capabilities[node_id]
        
        # Prune gradient table
        count += self.gradient_table.prune_expired()
        
        if count > 0:
            logger.debug(f"Pruned {count} expired capabilities")
        
        return count
    
    async def start(self) -> None:
        """Start periodic gossip broadcasts."""
        if self._running:
            logger.warning("Gossip manager already running")
            return
        
        self._running = True
        self._gossip_task = asyncio.create_task(self._gossip_loop())
        logger.info("Gossip manager started")
    
    async def stop(self) -> None:
        """Stop gossip broadcasts."""
        self._running = False
        
        if self._gossip_task:
            self._gossip_task.cancel()
            try:
                await self._gossip_task
            except asyncio.CancelledError:
                pass
            self._gossip_task = None
        
        logger.info("Gossip manager stopped")
    
    async def _gossip_loop(self) -> None:
        """Background task for periodic capability broadcasting."""
        # Broadcast immediately on start, then periodically
        first_broadcast = True
        
        while self._running:
            try:
                # Broadcast local capabilities
                if self._local_capabilities:
                    if first_broadcast:
                        logger.info(f"Initial capability broadcast ({len(self._local_capabilities)} capabilities)")
                        first_broadcast = False
                    await self.broadcast_capabilities()
                
                # Prune expired capabilities
                self.prune_expired()
                
                # Wait for next interval
                await asyncio.sleep(self.gossip_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in gossip loop: {e}")
    
    def stats(self) -> dict:
        """Get gossip manager statistics."""
        all_caps = self.get_all_capabilities()
        
        return {
            "node_id": self.node_id,
            "local_capabilities": len(self._local_capabilities),
            "remote_nodes": len(self._remote_capabilities),
            "total_capabilities": len(all_caps),
            "gradient_table_size": len(self.gradient_table),
            "gradient_stats": self.gradient_table.stats(),
        }
