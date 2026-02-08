import json
import base64
import time
from atmosphere.auth.tokens import MeshToken, MeshInvite
from atmosphere.auth.identity import KeyPair
from pathlib import Path

# Load mesh identity
mesh_path = Path.home() / ".atmosphere" / "mesh.json"
with open(mesh_path, "r") as f:
    mesh_data = json.load(f)

# Load my identity (private key)
identity_path = Path.home() / ".atmosphere" / "identity.json"
with open(identity_path, "r") as f:
    id_data = json.load(f)

# Create keypair
private_key = bytes.fromhex(id_data["private_key"])
keypair = KeyPair.from_private_bytes(private_key)

# Create signed token
token = MeshToken.create(
    mesh_id=mesh_data["mesh_id"],
    issuer_keypair=keypair,
    issuer_id="118c1963042d52fc", # From mesh.json founding_members
    ttl_seconds=86400 * 7 # 7 days
)

# Create invite
invite = MeshInvite(
    token=token,
    mesh_name=mesh_data["name"],
    endpoints=["wss://atmosphere-relay-production.up.railway.app"],
    mesh_public_key=mesh_data["master_public_key"]
)

# Print deep link
print(f"atmosphere://join/{invite.encode()}")
