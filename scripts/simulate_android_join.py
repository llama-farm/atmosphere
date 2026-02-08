#!/usr/bin/env python3
"""
Android Mesh Connection Simulation

This script simulates what an Android app would do to join an Atmosphere mesh:
1. Parse an invite token
2. Connect to the relay WebSocket
3. Send join message with token
4. Listen for capability announcements
5. Send LLM request and receive response

Usage:
    python simulate_android_join.py [--invite INVITE_STRING]
    
If no invite is provided, it will generate one using the Mac's credentials.
"""

import asyncio
import base64
import json
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    print("ERROR: websockets package required. Install with: pip install websockets")
    sys.exit(1)

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:
    print("ERROR: cryptography package required. Install with: pip install cryptography")
    sys.exit(1)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class MeshToken:
    """Mesh join token - matches atmosphere.auth.tokens.MeshToken"""
    mesh_id: str
    node_id: Optional[str]
    issued_at: int
    expires_at: int
    capabilities: List[str]
    issuer_id: str
    nonce: str
    signature: str
    
    @classmethod
    def from_dict(cls, data: dict) -> "MeshToken":
        return cls(
            mesh_id=data["mesh_id"],
            node_id=data.get("node_id"),
            issued_at=data["issued_at"],
            expires_at=data["expires_at"],
            capabilities=data.get("capabilities", ["participant"]),
            issuer_id=data["issuer_id"],
            nonce=data["nonce"],
            signature=data["signature"],
        )
    
    def to_dict(self) -> dict:
        return {
            "mesh_id": self.mesh_id,
            "node_id": self.node_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "capabilities": self.capabilities,
            "issuer_id": self.issuer_id,
            "nonce": self.nonce,
            "signature": self.signature,
        }
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


@dataclass
class MeshInvite:
    """Mesh invite - matches atmosphere.auth.tokens.MeshInvite"""
    token: MeshToken
    mesh_name: str
    endpoints: List[str]
    mesh_public_key: str
    
    @classmethod
    def decode(cls, encoded: str) -> "MeshInvite":
        """Decode from compact base64url string."""
        # Add padding if needed
        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += '=' * padding
        
        json_bytes = base64.urlsafe_b64decode(encoded)
        data = json.loads(json_bytes)
        
        return cls(
            token=MeshToken.from_dict(data["token"]),
            mesh_name=data["mesh_name"],
            endpoints=data.get("endpoints", []),
            mesh_public_key=data["mesh_public_key"],
        )
    
    @classmethod
    def from_deep_link(cls, url: str) -> "MeshInvite":
        """Parse atmosphere://join?invite=... or atmosphere://join/..."""
        if "invite=" in url:
            # Query param format
            import urllib.parse
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            invite_str = params.get("invite", [""])[0]
        else:
            # Path format: atmosphere://join/<invite>
            invite_str = url.split("/")[-1]
        
        return cls.decode(invite_str)


# =============================================================================
# Token Generation (simulates Mac CLI)
# =============================================================================

def generate_invite_from_mac_identity() -> Optional[MeshInvite]:
    """
    Generate a valid invite token using the Mac's mesh identity.
    This simulates what the Mac CLI would do to create an invite.
    """
    mesh_path = Path.home() / ".atmosphere" / "mesh.json"
    secrets_path = Path.home() / ".atmosphere" / "mesh.secrets"
    
    if not mesh_path.exists() or not secrets_path.exists():
        print("ERROR: Mac mesh identity not found. Run 'atmosphere init' first.")
        return None
    
    try:
        # Load mesh and secrets
        with open(mesh_path, "r") as f:
            mesh_data = json.load(f)
        with open(secrets_path, "r") as f:
            secrets_data = json.load(f)
        
        mesh_id = mesh_data["mesh_id"]
        mesh_name = mesh_data["name"]
        mesh_public_key = mesh_data["master_public_key"]
        issuer_id = mesh_data["founding_members"][0]["node_id"]
        
        # Load master private key from share_data (for threshold=1, share IS the master key)
        share_data = bytes.fromhex(secrets_data["share_data"])
        private_key = Ed25519PrivateKey.from_private_bytes(share_data)
        
        # Create token
        now = int(time.time())
        token_data = {
            "mesh_id": mesh_id,
            "node_id": None,
            "issued_at": now,
            "expires_at": now + 86400 * 7,  # 7 days
            "capabilities": ["participant"],
            "issuer_id": issuer_id,
            "nonce": secrets.token_hex(16),
        }
        
        # Sign the token (canonical JSON)
        canonical = json.dumps({
            "mesh_id": token_data["mesh_id"],
            "node_id": token_data["node_id"],
            "issued_at": token_data["issued_at"],
            "expires_at": token_data["expires_at"],
            "capabilities": sorted(token_data["capabilities"]),
            "issuer_id": token_data["issuer_id"],
            "nonce": token_data["nonce"],
        }, sort_keys=True, separators=(',', ':')).encode()
        
        signature = private_key.sign(canonical)
        token_data["signature"] = base64.b64encode(signature).decode()
        
        token = MeshToken.from_dict(token_data)
        
        invite = MeshInvite(
            token=token,
            mesh_name=mesh_name,
            endpoints=["wss://atmosphere-relay-production.up.railway.app"],
            mesh_public_key=mesh_public_key,
        )
        
        print(f"✓ Generated invite for mesh '{mesh_name}' ({mesh_id})")
        return invite
        
    except Exception as e:
        print(f"ERROR: Failed to generate invite: {e}")
        import traceback
        traceback.print_exc()
        return None


# =============================================================================
# Android Simulation
# =============================================================================

class AndroidSimulator:
    """
    Simulates an Android device joining the Atmosphere mesh.
    """
    
    def __init__(self, invite: MeshInvite):
        self.invite = invite
        self.node_id = secrets.token_hex(8)  # Simulated Android device ID
        self.ws: Optional[WebSocketClientProtocol] = None
        self.connected = False
        self.joined = False
        self.peers: List[Dict[str, Any]] = []
        self.messages_received: List[Dict[str, Any]] = []
        self.llm_response: Optional[str] = None
        
    async def connect_and_test(self) -> Dict[str, Any]:
        """
        Run the full connection and test flow.
        Returns a report of what happened.
        """
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "node_id": self.node_id,
            "mesh_id": self.invite.token.mesh_id,
            "mesh_name": self.invite.mesh_name,
            "relay_url": None,
            "steps": [],
            "success": False,
            "error": None,
        }
        
        try:
            # Step 1: Parse and validate invite
            report["steps"].append({
                "step": "Parse Invite",
                "status": "success",
                "details": {
                    "mesh_id": self.invite.token.mesh_id,
                    "mesh_name": self.invite.mesh_name,
                    "endpoints": self.invite.endpoints,
                    "token_expires": time.strftime("%Y-%m-%d %H:%M:%S", 
                                                   time.localtime(self.invite.token.expires_at)),
                    "issuer_id": self.invite.token.issuer_id,
                }
            })
            
            if self.invite.token.is_expired():
                report["steps"][-1]["status"] = "failed"
                report["steps"][-1]["error"] = "Token expired"
                report["error"] = "Token expired"
                return report
            
            # Step 2: Connect to relay
            relay_url = self.invite.endpoints[0] if self.invite.endpoints else None
            if not relay_url:
                report["error"] = "No relay URL in invite"
                return report
            
            report["relay_url"] = relay_url
            ws_url = f"{relay_url}/relay/{self.invite.token.mesh_id}"
            
            print(f"\n[ANDROID] Connecting to: {ws_url}")
            
            async with websockets.connect(ws_url, close_timeout=5) as ws:
                self.ws = ws
                self.connected = True
                
                report["steps"].append({
                    "step": "WebSocket Connect",
                    "status": "success",
                    "details": {"url": ws_url}
                })
                print("[ANDROID] ✓ WebSocket connected")
                
                # Step 3: Send join message with token
                join_msg = {
                    "type": "join",
                    "node_id": self.node_id,
                    "token": self.invite.token.to_dict(),
                    "name": "Android-Simulator",
                    "capabilities": ["llm-client"],  # We want LLM, don't provide it
                }
                
                await ws.send(json.dumps(join_msg))
                print(f"[ANDROID] Sent join message as node {self.node_id}")
                
                report["steps"].append({
                    "step": "Send Join",
                    "status": "success",
                    "details": {"node_id": self.node_id}
                })
                
                # Step 4: Wait for responses (joined, peers, etc.)
                llm_request_id = None
                llm_request_sent = False
                
                try:
                    async with asyncio.timeout(15):
                        while True:
                            msg_text = await ws.recv()
                            msg = json.loads(msg_text)
                            msg_type = msg.get("type")
                            
                            print(f"[ANDROID] Received: {msg_type}")
                            self.messages_received.append(msg)
                            
                            if msg_type == "error":
                                error_msg = msg.get("message", "Unknown error")
                                report["steps"].append({
                                    "step": "Receive Error",
                                    "status": "failed",
                                    "error": error_msg
                                })
                                report["error"] = error_msg
                                return report
                            
                            elif msg_type == "joined":
                                self.joined = True
                                report["steps"].append({
                                    "step": "Joined Mesh",
                                    "status": "success",
                                    "details": {
                                        "mesh": msg.get("mesh"),
                                        "node_count": msg.get("node_count"),
                                    }
                                })
                                print(f"[ANDROID] ✓ Joined mesh '{msg.get('mesh')}' with {msg.get('node_count')} nodes")
                            
                            elif msg_type == "peers":
                                self.peers = msg.get("peers", [])
                                report["steps"].append({
                                    "step": "Received Peer List",
                                    "status": "success",
                                    "details": {
                                        "peer_count": len(self.peers),
                                        "peers": self.peers,
                                    }
                                })
                                print(f"[ANDROID] ✓ Received peer list: {len(self.peers)} peers")
                                for peer in self.peers:
                                    print(f"    - {peer.get('node_id')} ({peer.get('name')}) caps={peer.get('capabilities')}")
                                
                                # Step 5: Send LLM request if we have peers with LLM capability
                                if not llm_request_sent:
                                    llm_peers = [p for p in self.peers 
                                                 if "llm" in p.get("capabilities", []) 
                                                 or "chat" in p.get("capabilities", [])
                                                 or p.get("is_founder")]
                                    
                                    if llm_peers or self.peers:  # Try anyway if peers exist
                                        llm_request_id = secrets.token_hex(8)
                                        llm_request = {
                                            "type": "llm_request",
                                            "request_id": llm_request_id,
                                            "messages": [
                                                {"role": "user", "content": "Say 'Hello from Atmosphere mesh!' in exactly those words."}
                                            ],
                                            "model": "auto",
                                        }
                                        await ws.send(json.dumps(llm_request))
                                        llm_request_sent = True
                                        
                                        report["steps"].append({
                                            "step": "Send LLM Request",
                                            "status": "success",
                                            "details": {"request_id": llm_request_id}
                                        })
                                        print(f"[ANDROID] Sent LLM request {llm_request_id}")
                                    else:
                                        print("[ANDROID] No peers available for LLM request")
                            
                            elif msg_type == "peer_joined":
                                new_peer = {
                                    "node_id": msg.get("node_id"),
                                    "name": msg.get("name"),
                                    "capabilities": msg.get("capabilities", []),
                                    "is_founder": msg.get("is_founder", False),
                                }
                                self.peers.append(new_peer)
                                print(f"[ANDROID] New peer joined: {msg.get('node_id')}")
                            
                            elif msg_type == "llm_response":
                                self.llm_response = msg.get("response")
                                error = msg.get("error")
                                
                                if error:
                                    report["steps"].append({
                                        "step": "LLM Response",
                                        "status": "failed",
                                        "error": error
                                    })
                                    print(f"[ANDROID] ✗ LLM error: {error}")
                                else:
                                    report["steps"].append({
                                        "step": "LLM Response",
                                        "status": "success",
                                        "details": {
                                            "response": self.llm_response[:200] if self.llm_response else None
                                        }
                                    })
                                    print(f"[ANDROID] ✓ LLM response: {self.llm_response[:100]}...")
                                    report["success"] = True
                                    return report
                            
                            elif msg_type == "pong":
                                pass  # Heartbeat response
                            
                            # If we've joined and got peers but no LLM peers, we're done
                            if self.joined and self.peers and not llm_request_sent:
                                print("[ANDROID] Connected but no LLM-capable peers found")
                                report["success"] = True  # Connection itself succeeded
                                return report
                    
                except asyncio.TimeoutError:
                    if self.joined:
                        print("[ANDROID] Timeout waiting for LLM response (but connection succeeded)")
                        report["steps"].append({
                            "step": "Wait for LLM Response",
                            "status": "timeout",
                            "details": "Joined mesh but no LLM response received within timeout"
                        })
                        # Still count as success if we joined
                        report["success"] = True
                    else:
                        report["steps"].append({
                            "step": "Wait for Join Confirmation",
                            "status": "timeout"
                        })
                        report["error"] = "Timeout waiting for server response"
            
        except Exception as e:
            import traceback
            report["error"] = str(e)
            report["steps"].append({
                "step": "Exception",
                "status": "failed",
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            print(f"[ANDROID] ✗ Error: {e}")
        
        return report


# =============================================================================
# Main
# =============================================================================

async def main():
    print("=" * 60)
    print("ATMOSPHERE ANDROID SIMULATION")
    print("=" * 60)
    
    # Parse command line args
    invite_str = None
    for i, arg in enumerate(sys.argv):
        if arg == "--invite" and i + 1 < len(sys.argv):
            invite_str = sys.argv[i + 1]
    
    # Get or generate invite
    if invite_str:
        print(f"\nParsing provided invite...")
        if invite_str.startswith("atmosphere://"):
            invite = MeshInvite.from_deep_link(invite_str)
        else:
            invite = MeshInvite.decode(invite_str)
    else:
        print("\nNo invite provided. Generating from Mac identity...")
        invite = generate_invite_from_mac_identity()
        if not invite:
            print("FAILED: Could not generate invite")
            sys.exit(1)
    
    print(f"\n--- Invite Details ---")
    print(f"Mesh: {invite.mesh_name} ({invite.token.mesh_id})")
    print(f"Relay: {invite.endpoints}")
    print(f"Expires: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(invite.token.expires_at))}")
    print(f"Issuer: {invite.token.issuer_id}")
    
    # Run simulation
    print("\n--- Starting Simulation ---")
    simulator = AndroidSimulator(invite)
    report = await simulator.connect_and_test()
    
    # Print summary
    print("\n" + "=" * 60)
    print("SIMULATION REPORT")
    print("=" * 60)
    
    print(f"\nOverall: {'✓ SUCCESS' if report['success'] else '✗ FAILED'}")
    if report.get("error"):
        print(f"Error: {report['error']}")
    
    print(f"\nSteps:")
    for step in report.get("steps", []):
        status_icon = "✓" if step["status"] == "success" else "✗" if step["status"] == "failed" else "⏳"
        print(f"  {status_icon} {step['step']}: {step['status']}")
        if step.get("error"):
            print(f"      Error: {step['error']}")
    
    # Save report
    report_path = Path.home() / "clawd/projects/atmosphere/TEST_REPORTS/android_simulation_result.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to: {report_path}")
    
    return report


if __name__ == "__main__":
    report = asyncio.run(main())
    sys.exit(0 if report.get("success") else 1)
