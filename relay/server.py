"""
Atmosphere Relay Server v2.0 - With Token Security

A lightweight WebSocket relay server that enables mesh connections when direct P2P 
isn't possible (both parties behind NAT, no port forwarding, etc.)

SECURITY:
- Mesh founders register the mesh's public key on first connect
- All subsequent joins require a signed token from a founder
- Tokens are verified against the mesh public key
- Nonces prevent replay attacks

Architecture:
    ┌─────────────┐      ┌─────────────────┐      ┌─────────────┐
    │   Android   │─────▶│  Relay Server   │◀─────│     Mac     │
    │  (cell data)│      │ (cloud/VPS)     │      │ (behind NAT)│
    └─────────────┘      └─────────────────┘      └─────────────┘

Both devices connect OUTBOUND to the relay (no port forwarding needed).
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
import asyncio
import base64
import hashlib
import json
import logging
import time
import os

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("atmosphere.relay")

app = FastAPI(
    title="Atmosphere Relay Server",
    description="Secure WebSocket relay for Atmosphere mesh networking",
    version="2.0.0"
)

# Add CORS middleware for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Token Verification
# ============================================================================

class TokenStore:
    """
    Stores mesh public keys and verifies tokens.
    """
    
    def __init__(self):
        self._mesh_keys: dict[str, bytes] = {}  # mesh_id -> public key
        self._mesh_names: dict[str, str] = {}  # mesh_id -> name
        self._founders: dict[str, set] = defaultdict(set)  # mesh_id -> founder node_ids
        self._used_nonces: set[str] = set()
        self._nonce_expiry: dict[str, float] = {}
    
    def register_mesh(
        self, 
        mesh_id: str, 
        public_key_b64: str, 
        founder_proof: str,
        founder_node_id: str,
        mesh_name: str = ""
    ) -> tuple[bool, str]:
        """
        Register a mesh's public key. Only first founder can register.
        
        Args:
            mesh_id: The mesh ID
            public_key_b64: Base64-encoded Ed25519 public key
            founder_proof: Signature of mesh_id by the mesh's private key
            founder_node_id: The founder's node ID
            mesh_name: Human-readable mesh name
        
        Returns:
            (success, message)
        """
        # Allow re-registration by existing founders
        if mesh_id in self._mesh_keys:
            if founder_node_id in self._founders[mesh_id]:
                logger.info(f"Founder {founder_node_id} re-registered mesh {mesh_id}")
                return True, "Already registered"
            return False, "Mesh already registered by different founder"
        
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            
            public_key = base64.b64decode(public_key_b64)
            pubkey = Ed25519PublicKey.from_public_bytes(public_key)
            sig_bytes = base64.b64decode(founder_proof)
            
            # Verify founder owns the mesh key
            pubkey.verify(sig_bytes, mesh_id.encode())
            
            self._mesh_keys[mesh_id] = public_key
            self._mesh_names[mesh_id] = mesh_name
            self._founders[mesh_id].add(founder_node_id)
            
            logger.info(f"Mesh {mesh_id} ({mesh_name}) registered by founder {founder_node_id}")
            return True, "Mesh registered"
            
        except Exception as e:
            logger.warning(f"Mesh registration failed for {mesh_id}: {e}")
            return False, f"Invalid founder proof: {e}"
    
    def is_founder(self, mesh_id: str, node_id: str) -> bool:
        """Check if a node is a founder of a mesh."""
        return node_id in self._founders.get(mesh_id, set())
    
    def is_mesh_registered(self, mesh_id: str) -> bool:
        """Check if a mesh is registered."""
        return mesh_id in self._mesh_keys
    
    def verify_token(self, token_data: dict, node_id: str) -> tuple[bool, str]:
        """
        Verify a join token.
        
        Args:
            token_data: The token dictionary
            node_id: The node trying to join
        
        Returns:
            (success, error_message)
        """
        try:
            mesh_id = token_data.get("mesh_id")
            expires_at = token_data.get("expires_at", 0)
            bound_node = token_data.get("node_id")
            nonce = token_data.get("nonce")
            signature = token_data.get("signature")
            issuer_id = token_data.get("issuer_id")
            
            # Check required fields
            if not all([mesh_id, nonce, signature, issuer_id]):
                return False, "Missing required token fields"
            
            # Check expiration
            if time.time() > expires_at:
                return False, "Token expired"
            
            # Check node binding
            if bound_node and bound_node != node_id:
                return False, "Token bound to different node"
            
            # Check replay
            if nonce in self._used_nonces:
                return False, "Token already used (replay)"
            
            # Get mesh public key
            mesh_key = self._mesh_keys.get(mesh_id)
            if not mesh_key:
                return False, "Mesh not registered"
            
            # Verify signature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            
            # Build canonical bytes (must match client-side)
            canonical = {
                "mesh_id": mesh_id,
                "node_id": bound_node,
                "issued_at": token_data.get("issued_at"),
                "expires_at": expires_at,
                "capabilities": sorted(token_data.get("capabilities", [])),
                "issuer_id": issuer_id,
                "nonce": nonce,
            }
            canonical_bytes = json.dumps(
                canonical, sort_keys=True, separators=(',', ':')
            ).encode()
            
            pubkey = Ed25519PublicKey.from_public_bytes(mesh_key)
            sig_bytes = base64.b64decode(signature)
            pubkey.verify(sig_bytes, canonical_bytes)
            
            # Mark nonce as used
            self._used_nonces.add(nonce)
            self._nonce_expiry[nonce] = expires_at
            
            logger.info(f"Token verified for node {node_id} joining mesh {mesh_id}")
            return True, ""
            
        except Exception as e:
            logger.warning(f"Token verification failed: {e}")
            return False, f"Invalid token: {e}"
    
    def cleanup_expired(self):
        """Remove expired nonces."""
        now = time.time()
        expired = [n for n, exp in self._nonce_expiry.items() if exp < now]
        for nonce in expired:
            self._used_nonces.discard(nonce)
            del self._nonce_expiry[nonce]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired nonces")


# Global token store
token_store = TokenStore()


# ============================================================================
# Peer & Mesh Management
# ============================================================================

@dataclass
class PeerInfo:
    """Information about a connected peer."""
    node_id: str
    websocket: WebSocket
    capabilities: list = field(default_factory=list)
    name: str = ""
    is_founder: bool = False
    joined_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "capabilities": self.capabilities,
            "is_founder": self.is_founder,
            "joined_at": self.joined_at,
        }


@dataclass 
class MeshRoom:
    """A mesh room containing connected peers."""
    mesh_id: str
    name: str = ""
    peers: dict = field(default_factory=dict)  # node_id -> PeerInfo
    created_at: float = field(default_factory=time.time)
    
    @property
    def peer_count(self) -> int:
        return len(self.peers)
    
    def get_peer_list(self, exclude: Optional[str] = None) -> list:
        return [nid for nid in self.peers.keys() if nid != exclude]
    
    def get_peer_info_list(self, exclude: Optional[str] = None) -> list:
        return [p.to_dict() for nid, p in self.peers.items() if nid != exclude]


# Global state
meshes: dict[str, MeshRoom] = {}

stats = {
    "total_connections": 0,
    "total_messages_relayed": 0,
    "total_llm_requests": 0,
    "auth_failures": 0,
    "started_at": time.time(),
}


# ============================================================================
# HTTP Endpoints
# ============================================================================

@app.get("/")
async def root():
    return {
        "service": "Atmosphere Relay Server",
        "version": "2.0.0",
        "security": "token-verified",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "stats": "/stats",
            "relay": "/relay/{mesh_id}",
        }
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "meshes": len(meshes),
        "connections": sum(m.peer_count for m in meshes.values()),
        "registered_meshes": len(token_store._mesh_keys),
        "uptime_seconds": time.time() - stats["started_at"],
    }


@app.get("/stats")
async def get_stats():
    mesh_stats = []
    for mesh_id, mesh in meshes.items():
        mesh_stats.append({
            "mesh_id": mesh_id,
            "name": mesh.name,
            "peer_count": mesh.peer_count,
            "created_at": mesh.created_at,
        })
    
    return {
        "uptime_seconds": time.time() - stats["started_at"],
        "total_connections": stats["total_connections"],
        "total_messages_relayed": stats["total_messages_relayed"],
        "total_llm_requests": stats["total_llm_requests"],
        "auth_failures": stats["auth_failures"],
        "active_meshes": len(meshes),
        "registered_meshes": len(token_store._mesh_keys),
        "active_connections": sum(m.peer_count for m in meshes.values()),
        "meshes": mesh_stats,
    }


# ============================================================================
# WebSocket Relay
# ============================================================================

@app.websocket("/relay/{mesh_id}")
async def relay_endpoint(websocket: WebSocket, mesh_id: str):
    """
    WebSocket relay endpoint for mesh communication.
    
    Protocol:
    
    1. FOUNDER REGISTRATION (first connection):
       {"type": "register_mesh", "mesh_id": "...", "mesh_public_key": "base64...",
        "founder_proof": "base64...", "node_id": "...", "name": "..."}
       
       Server responds:
       {"type": "mesh_registered", "success": true}
    
    2. MEMBER JOIN (with token):
       {"type": "join", "node_id": "...", "token": {...}, "capabilities": [...]}
       
       Server verifies token, then responds:
       {"type": "peers", "peers": [...]}
    
    3. MESSAGING:
       - {"type": "broadcast", "payload": {...}}
       - {"type": "direct", "target": "node_id", "payload": {...}}
       - {"type": "llm_request", ...}
       - {"type": "llm_response", ...}
       - {"type": "ping"}
    """
    await websocket.accept()
    stats["total_connections"] += 1
    
    node_id = None
    peer_info = None
    is_founder = False
    
    try:
        # Wait for registration/join message (30 second timeout)
        try:
            msg = await asyncio.wait_for(websocket.receive_json(), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("Registration timeout")
            await websocket.close(1008, "Registration timeout")
            return
        
        msg_type = msg.get("type")
        
        # ================================================================
        # Handle Founder Registration
        # ================================================================
        if msg_type == "register_mesh":
            node_id = msg.get("node_id")
            mesh_public_key = msg.get("mesh_public_key")
            founder_proof = msg.get("founder_proof")
            mesh_name = msg.get("name", mesh_id[:8])
            capabilities = msg.get("capabilities", [])
            name = msg.get("display_name", node_id[:8] if node_id else "unknown")
            
            if not all([node_id, mesh_public_key, founder_proof]):
                await websocket.send_json({
                    "type": "error",
                    "code": "MISSING_FIELDS",
                    "message": "Missing required fields for mesh registration"
                })
                await websocket.close(1008, "Missing required fields")
                return
            
            success, message = token_store.register_mesh(
                mesh_id, mesh_public_key, founder_proof, node_id, mesh_name
            )
            
            if not success:
                stats["auth_failures"] += 1
                await websocket.send_json({
                    "type": "error",
                    "code": "REGISTRATION_FAILED",
                    "message": message
                })
                await websocket.close(1008, message)
                return
            
            # Founder is now registered
            is_founder = True
            await websocket.send_json({"type": "mesh_registered", "success": True})
            logger.info(f"Founder {node_id} registered mesh {mesh_id}")
        
        # ================================================================
        # Handle Member Join
        # ================================================================
        elif msg_type in ("join", "register"):
            node_id = msg.get("node_id")
            token_data = msg.get("token")
            capabilities = msg.get("capabilities", [])
            name = msg.get("name", node_id[:8] if node_id else "unknown")
            
            if not node_id:
                await websocket.close(1008, "node_id required")
                return
            
            # Check if this is a founder rejoining
            if token_store.is_founder(mesh_id, node_id):
                is_founder = True
                logger.info(f"Founder {node_id} rejoining mesh {mesh_id}")
            
            # Non-founders must have a valid token
            elif token_data:
                success, error = token_store.verify_token(token_data, node_id)
                if not success:
                    stats["auth_failures"] += 1
                    await websocket.send_json({
                        "type": "error",
                        "code": "TOKEN_INVALID",
                        "message": error
                    })
                    await websocket.close(1008, f"Token verification failed: {error}")
                    return
            
            # No token and mesh requires it
            elif token_store.is_mesh_registered(mesh_id):
                stats["auth_failures"] += 1
                await websocket.send_json({
                    "type": "error",
                    "code": "TOKEN_REQUIRED",
                    "message": "This mesh requires a token to join"
                })
                await websocket.close(1008, "Token required")
                return
            
            # Mesh not registered - allow for backward compatibility / open meshes
            else:
                logger.warning(f"Node {node_id} joining unregistered mesh {mesh_id}")
        
        else:
            await websocket.close(1008, "First message must be register_mesh or join")
            return
        
        # ================================================================
        # Add to Mesh Room
        # ================================================================
        
        # Create mesh room if needed
        if mesh_id not in meshes:
            meshes[mesh_id] = MeshRoom(
                mesh_id=mesh_id,
                name=token_store._mesh_names.get(mesh_id, mesh_id[:8])
            )
            logger.info(f"Created mesh room: {mesh_id}")
        
        mesh = meshes[mesh_id]
        
        # Handle reconnection
        if node_id in mesh.peers:
            old_peer = mesh.peers[node_id]
            try:
                await old_peer.websocket.close(1000, "Replaced by new connection")
            except:
                pass
            logger.info(f"Replaced existing connection for {node_id}")
        
        # Create peer info
        peer_info = PeerInfo(
            node_id=node_id,
            websocket=websocket,
            capabilities=capabilities,
            name=name,
            is_founder=is_founder,
        )
        mesh.peers[node_id] = peer_info
        
        logger.info(f"Node {node_id} ({'founder' if is_founder else 'member'}) joined mesh {mesh_id}")
        
        # Notify others
        await broadcast_to_mesh(mesh_id, node_id, {
            "type": "peer_joined",
            "node_id": node_id,
            "name": name,
            "capabilities": capabilities,
            "is_founder": is_founder,
        })
        
        # Send peer list
        await websocket.send_json({
            "type": "peers",
            "peers": mesh.get_peer_info_list(exclude=node_id),
        })
        
        # ================================================================
        # Main Message Loop
        # ================================================================
        while True:
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                continue
            
            if peer_info:
                peer_info.last_seen = time.time()
            
            msg_type = data.get("type")
            
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "timestamp": time.time()})
            
            elif msg_type == "broadcast":
                payload = data.get("payload", {})
                payload["from"] = node_id
                await broadcast_to_mesh(mesh_id, node_id, {
                    "type": "message",
                    "from": node_id,
                    "payload": payload,
                })
                stats["total_messages_relayed"] += mesh.peer_count - 1
            
            elif msg_type == "direct":
                target = data.get("target")
                payload = data.get("payload", {})
                
                if target and target in mesh.peers:
                    try:
                        await mesh.peers[target].websocket.send_json({
                            "type": "message",
                            "from": node_id,
                            "payload": payload,
                        })
                        stats["total_messages_relayed"] += 1
                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Failed to send to {target}",
                        })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Peer {target} not found",
                    })
            
            elif msg_type == "llm_request":
                stats["total_llm_requests"] += 1
                request_id = data.get("request_id")
                prompt = data.get("prompt")
                model = data.get("model")
                
                llm_peers = [
                    p for nid, p in mesh.peers.items()
                    if nid != node_id and ("llm" in p.capabilities or "chat" in p.capabilities)
                ]
                
                if llm_peers:
                    target_peer = llm_peers[0]
                    try:
                        await target_peer.websocket.send_json({
                            "type": "llm_request",
                            "from": node_id,
                            "request_id": request_id,
                            "prompt": prompt,
                            "model": model,
                        })
                        stats["total_messages_relayed"] += 1
                    except Exception as e:
                        await websocket.send_json({
                            "type": "llm_error",
                            "request_id": request_id,
                            "error": "Failed to reach LLM peer",
                        })
                else:
                    await broadcast_to_mesh(mesh_id, node_id, {
                        "type": "llm_request",
                        "from": node_id,
                        "request_id": request_id,
                        "prompt": prompt,
                        "model": model,
                    })
            
            elif msg_type == "llm_response":
                target = data.get("target")
                request_id = data.get("request_id")
                response = data.get("response")
                error = data.get("error")
                
                if target and target in mesh.peers:
                    try:
                        await mesh.peers[target].websocket.send_json({
                            "type": "llm_response",
                            "from": node_id,
                            "request_id": request_id,
                            "response": response,
                            "error": error,
                        })
                        stats["total_messages_relayed"] += 1
                    except Exception:
                        pass
            
            elif msg_type == "capabilities_update":
                new_caps = data.get("capabilities", [])
                if peer_info:
                    peer_info.capabilities = new_caps
                    await broadcast_to_mesh(mesh_id, node_id, {
                        "type": "peer_updated",
                        "node_id": node_id,
                        "capabilities": new_caps,
                    })
    
    except WebSocketDisconnect:
        logger.info(f"Node {node_id} disconnected from mesh {mesh_id}")
    except Exception as e:
        logger.error(f"Error in relay for {node_id}: {e}")
    finally:
        if node_id and mesh_id in meshes:
            mesh = meshes[mesh_id]
            mesh.peers.pop(node_id, None)
            
            await broadcast_to_mesh(mesh_id, None, {
                "type": "peer_left",
                "node_id": node_id,
            })
            
            if mesh.peer_count == 0:
                del meshes[mesh_id]
                logger.info(f"Removed empty mesh room: {mesh_id}")


async def broadcast_to_mesh(mesh_id: str, exclude_node: Optional[str], message: dict):
    """Broadcast to all peers in a mesh except excluded node."""
    if mesh_id not in meshes:
        return
    
    mesh = meshes[mesh_id]
    failed_peers = []
    
    for node_id, peer in list(mesh.peers.items()):
        if node_id != exclude_node:
            try:
                await peer.websocket.send_json(message)
            except Exception:
                failed_peers.append(node_id)
    
    for node_id in failed_peers:
        mesh.peers.pop(node_id, None)


# ============================================================================
# Background Tasks
# ============================================================================

async def cleanup_stale_connections():
    """Remove stale connections and expired nonces."""
    while True:
        await asyncio.sleep(60)
        
        stale_timeout = 120
        now = time.time()
        
        for mesh_id, mesh in list(meshes.items()):
            stale_peers = [
                nid for nid, p in mesh.peers.items()
                if now - p.last_seen > stale_timeout
            ]
            
            for node_id in stale_peers:
                peer = mesh.peers.pop(node_id, None)
                if peer:
                    try:
                        await peer.websocket.close(1000, "Connection timeout")
                    except:
                        pass
                    logger.info(f"Removed stale peer {node_id}")
                    
                    await broadcast_to_mesh(mesh_id, None, {
                        "type": "peer_left",
                        "node_id": node_id,
                    })
            
            if mesh.peer_count == 0:
                del meshes[mesh_id]
        
        # Cleanup expired nonces
        token_store.cleanup_expired()


@app.on_event("startup")
async def startup():
    asyncio.create_task(cleanup_stale_connections())
    logger.info("Atmosphere Relay Server v2.0 started (token-secured)")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8765"))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
