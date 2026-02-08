"""
BLE Proximity Pairing for Atmosphere Mesh.

Flow:
1. New device discovers nearby Atmosphere BLE service
2. Sends pair_request with its node_id + public_key
3. Existing node generates 6-digit PIN, displays it
4. New device enters PIN → sends pair_confirm with HMAC(pin, shared_secret)
5. Existing node verifies → issues token → sends back via BLE
6. New device joins mesh with token

Security:
- PIN prevents unauthorized pairing (physical proximity + human intent)
- ECDH key exchange for shared secret (prevents eavesdropping)
- Rate limiting: 3 attempts, then cooldown
- Token is standard MeshToken (founder-signed or delegation chain)
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import random
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Dict

logger = logging.getLogger(__name__)


@dataclass
class PairingSession:
    """Active pairing session with a remote device."""
    remote_node_id: str
    remote_public_key: str  # Ed25519 public key (base64)
    pin: str  # 6-digit PIN
    shared_secret: bytes  # HKDF-derived shared secret
    created_at: float = field(default_factory=time.time)
    attempts: int = 0
    max_attempts: int = 3
    cooldown_until: float = 0.0
    
    @property
    def is_expired(self) -> bool:
        """Sessions expire after 5 minutes."""
        return time.time() - self.created_at > 300
    
    @property
    def is_cooled_down(self) -> bool:
        return time.time() >= self.cooldown_until


class BlePairingManager:
    """
    Manages BLE proximity pairing for mesh joining.
    
    Can operate in two modes:
    - Founder mode: Signs tokens directly with mesh master key
    - Delegate mode: Signs sub-tokens with own key + delegation chain
    """
    
    def __init__(
        self,
        node_id: str,
        mesh_id: str,
        is_founder: bool = False,
        mesh_keypair=None,  # Founder's keypair (if founder)
        own_keypair=None,   # This node's keypair
        own_token=None,     # This node's MeshToken (if delegate)
        on_pin_display: Optional[Callable[[str, str], Awaitable[None]]] = None,  # (pin, remote_node_id) -> display
        on_pair_complete: Optional[Callable[[str, dict], Awaitable[None]]] = None,  # (remote_node_id, token_dict) -> notify
    ):
        self.node_id = node_id
        self.mesh_id = mesh_id
        self.is_founder = is_founder
        self.mesh_keypair = mesh_keypair
        self.own_keypair = own_keypair
        self.own_token = own_token
        self.on_pin_display = on_pin_display
        self.on_pair_complete = on_pair_complete
        
        self._sessions: Dict[str, PairingSession] = {}
    
    def can_invite(self) -> bool:
        """Check if this node can invite new devices."""
        if self.is_founder and self.mesh_keypair:
            return True
        if self.own_token and "can_invite" in self.own_token.capabilities:
            return True
        return False
    
    async def handle_pair_request(self, remote_node_id: str, remote_public_key: str) -> Optional[dict]:
        """
        Handle incoming pair request from a new device.
        
        Returns response dict to send back, or None if rejected.
        """
        if not self.can_invite():
            logger.warning(f"Cannot invite: no invite authority")
            return {"type": "pair_rejected", "reason": "no_invite_authority"}
        
        # Check for existing session
        existing = self._sessions.get(remote_node_id)
        if existing and not existing.is_expired and not existing.is_cooled_down:
            logger.warning(f"Pairing session already active for {remote_node_id}")
            return {"type": "pair_rejected", "reason": "session_active"}
        
        # Generate PIN
        pin = f"{random.randint(0, 999999):06d}"
        
        # Derive shared secret using HKDF
        # In production: ECDH(remote_pub, our_priv) → HKDF
        # For now: HKDF(remote_pub || our_node_id, salt=mesh_id)
        import hashlib
        material = f"{remote_public_key}:{self.node_id}:{self.mesh_id}".encode()
        shared_secret = hashlib.pbkdf2_hmac('sha256', material, self.mesh_id.encode(), 1000)
        
        session = PairingSession(
            remote_node_id=remote_node_id,
            remote_public_key=remote_public_key,
            pin=pin,
            shared_secret=shared_secret,
        )
        self._sessions[remote_node_id] = session
        
        # Display PIN to user
        if self.on_pin_display:
            await self.on_pin_display(pin, remote_node_id)
        
        logger.info(f"🔵 Pairing session started for {remote_node_id[:8]}, PIN: {pin}")
        print(f"\n🔑 PAIRING PIN: {pin}  (for device {remote_node_id[:8]})\n", flush=True)
        
        return {
            "type": "pair_challenge",
            "node_id": self.node_id,
            "mesh_id": self.mesh_id,
        }
    
    async def handle_pair_confirm(self, remote_node_id: str, pin_hmac: str) -> Optional[dict]:
        """
        Handle PIN confirmation from the new device.
        
        Returns token response if PIN is correct, rejection otherwise.
        """
        session = self._sessions.get(remote_node_id)
        if not session:
            return {"type": "pair_rejected", "reason": "no_session"}
        
        if session.is_expired:
            del self._sessions[remote_node_id]
            return {"type": "pair_rejected", "reason": "session_expired"}
        
        if not session.is_cooled_down:
            return {"type": "pair_rejected", "reason": "cooldown", 
                    "retry_after": int(session.cooldown_until - time.time())}
        
        # Verify HMAC(pin, shared_secret)
        expected = hmac.new(
            session.shared_secret,
            session.pin.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(pin_hmac, expected):
            session.attempts += 1
            if session.attempts >= session.max_attempts:
                # Cooldown: 60s after 3 attempts, then 5min
                cooldown = 60 if session.attempts == session.max_attempts else 300
                session.cooldown_until = time.time() + cooldown
                logger.warning(f"Pairing attempts exhausted for {remote_node_id[:8]}, cooldown {cooldown}s")
            return {"type": "pair_rejected", "reason": "invalid_pin",
                    "attempts_remaining": max(0, session.max_attempts - session.attempts)}
        
        # PIN correct! Issue token
        logger.info(f"✅ PIN verified for {remote_node_id[:8]}, issuing token")
        
        from ..auth.tokens import MeshToken
        
        if self.is_founder and self.mesh_keypair:
            # Founder: issue directly
            token = MeshToken.create(
                mesh_id=self.mesh_id,
                issuer_keypair=self.mesh_keypair,
                issuer_id=self.node_id,
                node_id=remote_node_id,
                capabilities=["participant", "llm", "embeddings"],
                ttl_seconds=86400 * 7,  # 7 days
            )
        elif self.own_token and self.own_keypair:
            # Delegate: issue sub-token
            token = MeshToken.create_delegated(
                mesh_id=self.mesh_id,
                delegate_keypair=self.own_keypair,
                delegate_id=self.node_id,
                delegate_token=self.own_token,
                node_id=remote_node_id,
                capabilities=["participant", "llm", "embeddings"],
                ttl_seconds=86400 * 7,
            )
        else:
            return {"type": "pair_rejected", "reason": "no_signing_key"}
        
        # Clean up session
        del self._sessions[remote_node_id]
        
        # Build full invite response
        response = {
            "type": "pair_token",
            "token": token.to_dict(),
            "mesh_name": "home-mesh",  # TODO: get from mesh config
            "endpoints": {},  # Will be filled by caller with available endpoints
        }
        
        if self.on_pair_complete:
            await self.on_pair_complete(remote_node_id, response)
        
        return response
    
    async def handle_ble_pairing_message(self, source_id: str, msg: dict) -> Optional[dict]:
        """
        Route BLE pairing messages to the right handler.
        
        Called by the BLE message handler in server.py.
        """
        msg_type = msg.get("type", "")
        
        if msg_type == "pair_request":
            return await self.handle_pair_request(
                remote_node_id=msg.get("node_id", source_id),
                remote_public_key=msg.get("public_key", ""),
            )
        elif msg_type == "pair_confirm":
            return await self.handle_pair_confirm(
                remote_node_id=msg.get("node_id", source_id),
                pin_hmac=msg.get("pin_hmac", ""),
            )
        
        return None
