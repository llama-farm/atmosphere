"""
BLE Proximity Pairing Protocol for Atmosphere Mesh.

Simple pairing flow:
1. Devices discover each other via BLE
2. User initiates pairing on one device
3. Both show same 6-digit code (derived from ECDH shared secret)
4. User confirms codes match
5. Devices exchange credentials (tokens, IPs, mesh info)

This eliminates QR codes - just get close and tap!
"""

import asyncio
import hashlib
import secrets
import struct
import time
import json
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, Callable, Dict, Any
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)


class PairingState(IntEnum):
    """Pairing state machine."""
    IDLE = 0
    ADVERTISING = 1       # Waiting for pairing request
    INITIATING = 2        # Sent pairing request, waiting for response
    CODE_DISPLAY = 3      # Showing code, waiting for confirmation
    EXCHANGING = 4        # Exchanging credentials
    COMPLETED = 5         # Pairing successful
    FAILED = 6            # Pairing failed


class PairingMessageType(IntEnum):
    """Pairing protocol message types."""
    PAIR_REQUEST = 0x50      # "I want to pair"
    PAIR_ACCEPT = 0x51       # "OK, here's my public key"
    CODE_CONFIRM = 0x52      # "I confirmed the code"
    CREDENTIALS = 0x53       # "Here are my credentials"
    PAIR_COMPLETE = 0x54     # "Pairing complete"
    PAIR_REJECT = 0x5F       # "Rejected"


@dataclass
class PairingCredentials:
    """Credentials exchanged during pairing."""
    node_id: str
    node_name: str
    mesh_id: str
    relay_token: str = ""           # Token for relay authentication
    relay_url: str = ""             # Relay server URL
    local_endpoints: list = field(default_factory=list)  # [{"ip": "192.168.1.x", "port": 11451}]
    capabilities: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "mesh_id": self.mesh_id,
            "relay_token": self.relay_token,
            "relay_url": self.relay_url,
            "local_endpoints": self.local_endpoints,
            "capabilities": self.capabilities
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> 'PairingCredentials':
        return cls(
            node_id=d.get("node_id", ""),
            node_name=d.get("node_name", ""),
            mesh_id=d.get("mesh_id", ""),
            relay_token=d.get("relay_token", ""),
            relay_url=d.get("relay_url", ""),
            local_endpoints=d.get("local_endpoints", []),
            capabilities=d.get("capabilities", [])
        )


@dataclass
class PairingSession:
    """Active pairing session with a peer."""
    peer_id: str
    peer_name: str = ""
    state: PairingState = PairingState.IDLE
    
    # ECDH key exchange
    private_key: Optional[x25519.X25519PrivateKey] = None
    public_key: Optional[bytes] = None
    peer_public_key: Optional[bytes] = None
    shared_secret: Optional[bytes] = None
    
    # Verification code
    code: str = ""
    code_confirmed_local: bool = False
    code_confirmed_peer: bool = False
    
    # Exchanged credentials
    local_credentials: Optional[PairingCredentials] = None
    peer_credentials: Optional[PairingCredentials] = None
    
    # Timing
    started_at: float = 0
    timeout: float = 60.0  # 60 second timeout
    
    def is_expired(self) -> bool:
        return time.time() - self.started_at > self.timeout


class BlePairingManager:
    """
    Manages BLE proximity pairing.
    
    Usage:
        manager = BlePairingManager(
            local_credentials=my_creds,
            on_code_display=lambda code: show_code(code),
            on_pairing_complete=lambda creds: save_peer(creds)
        )
        
        # When user taps "Pair" on a discovered peer:
        await manager.initiate_pairing(peer_id)
        
        # When user confirms the code matches:
        await manager.confirm_code()
    """
    
    def __init__(
        self,
        local_credentials: PairingCredentials,
        on_code_display: Optional[Callable[[str, str], None]] = None,  # (code, peer_name)
        on_pairing_complete: Optional[Callable[[PairingCredentials], None]] = None,
        on_pairing_failed: Optional[Callable[[str, str], None]] = None,  # (peer_id, reason)
        send_message: Optional[Callable[[str, bytes], asyncio.Future]] = None  # (peer_id, data)
    ):
        self.local_credentials = local_credentials
        self.on_code_display = on_code_display
        self.on_pairing_complete = on_pairing_complete
        self.on_pairing_failed = on_pairing_failed
        self.send_message = send_message
        
        self.sessions: Dict[str, PairingSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    def start(self):
        """Start the pairing manager."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    def stop(self):
        """Stop the pairing manager."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        self.sessions.clear()
    
    async def _cleanup_loop(self):
        """Clean up expired sessions."""
        while True:
            await asyncio.sleep(5)
            expired = [pid for pid, s in self.sessions.items() if s.is_expired()]
            for pid in expired:
                logger.info(f"Pairing session with {pid} expired")
                if self.on_pairing_failed:
                    self.on_pairing_failed(pid, "timeout")
                del self.sessions[pid]
    
    # ========================================================================
    # Public API
    # ========================================================================
    
    async def initiate_pairing(self, peer_id: str, peer_name: str = "") -> bool:
        """
        Initiate pairing with a peer.
        Called when user taps "Pair" on a discovered device.
        """
        if peer_id in self.sessions:
            logger.warning(f"Already pairing with {peer_id}")
            return False
        
        # Generate ECDH key pair
        private_key = x25519.X25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        session = PairingSession(
            peer_id=peer_id,
            peer_name=peer_name,
            state=PairingState.INITIATING,
            private_key=private_key,
            public_key=public_key,
            started_at=time.time(),
            local_credentials=self.local_credentials
        )
        self.sessions[peer_id] = session
        
        # Send pairing request
        msg = self._build_message(PairingMessageType.PAIR_REQUEST, {
            "node_id": self.local_credentials.node_id,
            "node_name": self.local_credentials.node_name,
            "public_key": public_key.hex()
        })
        
        if self.send_message:
            await self.send_message(peer_id, msg)
            logger.info(f"Sent pairing request to {peer_id}")
            return True
        
        return False
    
    async def handle_incoming_request(self, peer_id: str, peer_name: str, peer_public_key: bytes):
        """
        Handle incoming pairing request.
        Called when we receive a PAIR_REQUEST.
        """
        # Generate our key pair
        private_key = x25519.X25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        # Compute shared secret
        peer_key = x25519.X25519PublicKey.from_public_bytes(peer_public_key)
        shared_secret = private_key.exchange(peer_key)
        
        # Generate verification code
        code = self._derive_code(shared_secret)
        
        session = PairingSession(
            peer_id=peer_id,
            peer_name=peer_name,
            state=PairingState.CODE_DISPLAY,
            private_key=private_key,
            public_key=public_key,
            peer_public_key=peer_public_key,
            shared_secret=shared_secret,
            code=code,
            started_at=time.time(),
            local_credentials=self.local_credentials
        )
        self.sessions[peer_id] = session
        
        # Send accept with our public key
        msg = self._build_message(PairingMessageType.PAIR_ACCEPT, {
            "node_id": self.local_credentials.node_id,
            "node_name": self.local_credentials.node_name,
            "public_key": public_key.hex()
        })
        
        if self.send_message:
            await self.send_message(peer_id, msg)
        
        # Display code to user
        if self.on_code_display:
            self.on_code_display(code, peer_name)
        
        logger.info(f"Pairing with {peer_name}: code = {code}")
    
    async def confirm_code(self, peer_id: str) -> bool:
        """
        User confirmed the code matches.
        Called when user taps "Confirm" on the code display.
        """
        session = self.sessions.get(peer_id)
        if not session or session.state != PairingState.CODE_DISPLAY:
            return False
        
        session.code_confirmed_local = True
        
        # Send confirmation
        msg = self._build_message(PairingMessageType.CODE_CONFIRM, {
            "node_id": self.local_credentials.node_id
        })
        
        if self.send_message:
            await self.send_message(peer_id, msg)
        
        # Check if both sides confirmed
        await self._check_both_confirmed(session)
        return True
    
    async def reject_pairing(self, peer_id: str, reason: str = "rejected"):
        """User rejected the pairing."""
        session = self.sessions.get(peer_id)
        if session:
            msg = self._build_message(PairingMessageType.PAIR_REJECT, {"reason": reason})
            if self.send_message:
                await self.send_message(peer_id, msg)
            del self.sessions[peer_id]
    
    # ========================================================================
    # Message Handling
    # ========================================================================
    
    async def handle_message(self, peer_id: str, data: bytes):
        """Handle incoming pairing protocol message."""
        try:
            msg_type = data[0]
            payload = json.loads(data[1:].decode('utf-8'))
            
            if msg_type == PairingMessageType.PAIR_REQUEST:
                await self._handle_pair_request(peer_id, payload)
            elif msg_type == PairingMessageType.PAIR_ACCEPT:
                await self._handle_pair_accept(peer_id, payload)
            elif msg_type == PairingMessageType.CODE_CONFIRM:
                await self._handle_code_confirm(peer_id, payload)
            elif msg_type == PairingMessageType.CREDENTIALS:
                await self._handle_credentials(peer_id, payload)
            elif msg_type == PairingMessageType.PAIR_COMPLETE:
                await self._handle_complete(peer_id, payload)
            elif msg_type == PairingMessageType.PAIR_REJECT:
                await self._handle_reject(peer_id, payload)
            else:
                logger.warning(f"Unknown pairing message type: {msg_type}")
                
        except Exception as e:
            logger.error(f"Error handling pairing message: {e}")
    
    async def _handle_pair_request(self, peer_id: str, payload: dict):
        """Handle incoming pairing request."""
        peer_name = payload.get("node_name", peer_id)
        peer_public_key = bytes.fromhex(payload.get("public_key", ""))
        
        if len(peer_public_key) != 32:
            logger.error(f"Invalid public key from {peer_id}")
            return
        
        await self.handle_incoming_request(peer_id, peer_name, peer_public_key)
    
    async def _handle_pair_accept(self, peer_id: str, payload: dict):
        """Handle pairing acceptance (response to our request)."""
        session = self.sessions.get(peer_id)
        if not session or session.state != PairingState.INITIATING:
            return
        
        peer_public_key = bytes.fromhex(payload.get("public_key", ""))
        peer_name = payload.get("node_name", peer_id)
        
        if len(peer_public_key) != 32:
            logger.error(f"Invalid public key from {peer_id}")
            return
        
        # Compute shared secret
        peer_key = x25519.X25519PublicKey.from_public_bytes(peer_public_key)
        shared_secret = session.private_key.exchange(peer_key)
        
        # Generate verification code
        code = self._derive_code(shared_secret)
        
        session.peer_public_key = peer_public_key
        session.peer_name = peer_name
        session.shared_secret = shared_secret
        session.code = code
        session.state = PairingState.CODE_DISPLAY
        
        # Display code to user
        if self.on_code_display:
            self.on_code_display(code, peer_name)
        
        logger.info(f"Pairing with {peer_name}: code = {code}")
    
    async def _handle_code_confirm(self, peer_id: str, payload: dict):
        """Handle peer's code confirmation."""
        session = self.sessions.get(peer_id)
        if not session:
            return
        
        session.code_confirmed_peer = True
        await self._check_both_confirmed(session)
    
    async def _check_both_confirmed(self, session: PairingSession):
        """Check if both sides confirmed, then exchange credentials."""
        if session.code_confirmed_local and session.code_confirmed_peer:
            session.state = PairingState.EXCHANGING
            
            # Send our credentials
            msg = self._build_message(PairingMessageType.CREDENTIALS, 
                                      self.local_credentials.to_dict())
            if self.send_message:
                await self.send_message(session.peer_id, msg)
    
    async def _handle_credentials(self, peer_id: str, payload: dict):
        """Handle received credentials."""
        session = self.sessions.get(peer_id)
        if not session:
            return
        
        session.peer_credentials = PairingCredentials.from_dict(payload)
        
        # If we haven't sent ours yet (we received first), send now
        if session.state == PairingState.CODE_DISPLAY:
            session.state = PairingState.EXCHANGING
            msg = self._build_message(PairingMessageType.CREDENTIALS,
                                      self.local_credentials.to_dict())
            if self.send_message:
                await self.send_message(peer_id, msg)
        
        # Send completion
        msg = self._build_message(PairingMessageType.PAIR_COMPLETE, {
            "node_id": self.local_credentials.node_id
        })
        if self.send_message:
            await self.send_message(peer_id, msg)
        
        # Check if complete
        await self._check_complete(session)
    
    async def _handle_complete(self, peer_id: str, payload: dict):
        """Handle pairing complete message."""
        session = self.sessions.get(peer_id)
        if not session:
            return
        
        session.state = PairingState.COMPLETED
        
        if session.peer_credentials and self.on_pairing_complete:
            self.on_pairing_complete(session.peer_credentials)
        
        logger.info(f"✅ Pairing complete with {session.peer_name}")
        del self.sessions[peer_id]
    
    async def _check_complete(self, session: PairingSession):
        """Check if pairing is complete."""
        if session.peer_credentials and session.state == PairingState.EXCHANGING:
            # We have their credentials and sent ours
            if self.on_pairing_complete:
                self.on_pairing_complete(session.peer_credentials)
            
            logger.info(f"✅ Pairing complete with {session.peer_name}")
    
    async def _handle_reject(self, peer_id: str, payload: dict):
        """Handle pairing rejection."""
        reason = payload.get("reason", "rejected")
        logger.info(f"Pairing rejected by {peer_id}: {reason}")
        
        if self.on_pairing_failed:
            self.on_pairing_failed(peer_id, reason)
        
        if peer_id in self.sessions:
            del self.sessions[peer_id]
    
    # ========================================================================
    # Helpers
    # ========================================================================
    
    def _build_message(self, msg_type: PairingMessageType, payload: dict) -> bytes:
        """Build pairing protocol message."""
        return bytes([msg_type]) + json.dumps(payload).encode('utf-8')
    
    def _derive_code(self, shared_secret: bytes) -> str:
        """Derive 6-digit verification code from shared secret."""
        # Hash the shared secret
        h = hashlib.sha256(shared_secret + b"atmosphere-pairing-code").digest()
        # Take first 4 bytes as integer, mod 1000000 for 6 digits
        num = struct.unpack(">I", h[:4])[0] % 1000000
        return f"{num:06d}"
    
    def get_session_state(self, peer_id: str) -> Optional[PairingState]:
        """Get current pairing state for a peer."""
        session = self.sessions.get(peer_id)
        return session.state if session else None
    
    def get_display_code(self, peer_id: str) -> Optional[str]:
        """Get the verification code for display."""
        session = self.sessions.get(peer_id)
        if session and session.state == PairingState.CODE_DISPLAY:
            return session.code
        return None


# ============================================================================
# Integration with BleTransport
# ============================================================================

def integrate_pairing_with_transport(transport, pairing_manager: BlePairingManager):
    """
    Integrate pairing manager with BLE transport.
    
    Sets up the send_message callback and message routing.
    """
    async def send_pairing_message(peer_id: str, data: bytes):
        """Send pairing message via BLE transport."""
        from .ble_mac import MessageType
        await transport.send(data, msg_type=MessageType.MESH_INFO, target=peer_id)
    
    pairing_manager.send_message = send_pairing_message
    
    # Add message handler for pairing messages
    original_on_message = transport.on_message
    
    def handle_message(msg):
        # Check if it's a pairing message (0x50-0x5F)
        if msg.payload and len(msg.payload) > 0:
            msg_type = msg.payload[0]
            if 0x50 <= msg_type <= 0x5F:
                asyncio.create_task(
                    pairing_manager.handle_message(msg.source_id, msg.payload)
                )
                return
        
        # Pass to original handler
        if original_on_message:
            original_on_message(msg)
    
    transport.on_message = handle_message
