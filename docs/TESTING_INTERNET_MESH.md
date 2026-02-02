# Testing Internet Mesh: Portland ↔ Seattle

Quick guide for testing internet-scale mesh networking between two machines on different networks.

## Prerequisites

- Two machines on different networks
- Internet connection on both
- Git and Python 3.8+ installed

## Rob's Machine (Portland)

### 1. Setup

```bash
cd ~/clawd/projects/atmosphere
git pull  # Get latest changes
pip install -e .
```

### 2. Initialize Mesh

```bash
atmosphere init rob-portland-mesh
```

Output:
```
✓ Mesh initialized: rob-portland-mesh
  Mesh ID: mesh-a1b2c3d4
  Node ID: node-rob-macbook
```

### 3. Start Server

```bash
atmosphere serve --port 7777
```

Output:
```
Starting Atmosphere server...
✓ Server started on 0.0.0.0:7777

Network Info:
  Local IP:    192.168.1.100
  Local Port:  7777
  Public IP:   203.0.113.10  (via STUN)
  Public Port: 7777
  NAT Type:    full_cone
  
Server is ready for connections.
```

### 4. Generate Join Code

In another terminal:

```bash
atmosphere join
```

Output:
```
Join Code: MESH-ABCD-1234-EFGH

Full join code (copy this):
eyJtZXNoX2lkIjoibWVzaC1hMWIyYzNkNCIsIm1lc2hfbmFtZSI6InJvYi1wb3J0bGFuZC1tZXNoIiwibWVzaF9wdWJsaWNfa2V5IjoiLS0tLi4uIiwiZW5kcG9pbnQiOiIxOTIuMTY4LjEuMTAwOjc3NzciLCJwdWJsaWNfZW5kcG9pbnQiOiIyMDMuMC4xMTMuMTA6Nzc3NyIsInJlbGF5X3VybHMiOltdLCJjcmVhdGVkX2F0IjoxNzM4NTU1MjAwLCJleHBpcmVzX2F0IjoxNzM4NjQxNjAwfQ==

Share this code with the person joining your mesh.
Expires in 24 hours.
```

### 5. Send Code to Matt

Send the full join code to Matt via:
- Slack/Discord
- Email
- Text message
- Any secure channel

**Keep the code safe:** Anyone with this code can join your mesh for 24 hours.

---

## Matt's Machine (Seattle)

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/atmosphere.git
cd atmosphere
pip install -e .
```

### 2. Join Rob's Mesh

```bash
atmosphere join <paste-rob's-join-code>
```

Output:
```
Joining mesh: rob-portland-mesh
Mesh ID: mesh-a1b2c3d4

Network discovery:
✓ Local IP: 10.0.1.50
✓ Public IP: 198.51.100.20:7890 (via STUN)

Attempting connection to Rob's mesh...
  Local endpoint:  192.168.1.100:7777 (LAN - will fail)
  Public endpoint: 203.0.113.10:7777 (Internet)

Trying direct P2P connection (UDP hole punching)...
  Sending punch packets to 203.0.113.10:7777...
  ✓ Received response from peer!
  ✓ P2P connection established in 2.3s

✓ Successfully joined mesh: rob-portland-mesh

Mesh Status:
  Node ID: node-matt-seattle
  Role: compute
  Peers: 1 connected
    - node-rob-macbook (Portland) [direct P2P, 45ms]
```

**If P2P fails:**
```
Trying direct P2P connection (UDP hole punching)...
  ⏱ Timeout after 10s
  ✗ P2P connection failed

Falling back to relay server...
  Connecting to ws://relay.atmosphere.dev:8080...
  ✓ Relay connection established
  
✓ Successfully joined mesh: rob-portland-mesh [via relay]

Mesh Status:
  Node ID: node-matt-seattle
  Role: compute
  Peers: 1 connected
    - node-rob-macbook (Portland) [relay, 85ms]
```

### 3. Verify Connection

```bash
atmosphere peers
```

Output:
```
Connected Peers (1):

node-rob-macbook
  Name:       Rob's MacBook
  Location:   Portland
  Connection: Direct P2P (or Relay)
  Latency:    45ms (or 85ms via relay)
  Status:     Online
  Tier:       compute
```

---

## Both Machines: Test Communication

### Send a Message

**Rob's machine:**
```bash
atmosphere send --to node-matt-seattle "Hello from Portland!"
```

**Matt's machine:**
```bash
atmosphere send --to node-rob-macbook "Hello from Seattle!"
```

### Run a Distributed Task

**Rob's machine:**
```bash
atmosphere execute "What's the weather like?" --use-mesh
```

This should use Matt's node to help process the request.

---

## Troubleshooting

### "STUN discovery failed"

**On either machine:**
```bash
atmosphere network
```

Check output:
- Public IP should be detected
- If "Not detected", check firewall/internet

**Fix:**
- Ensure UDP port 3478/19302 not blocked
- Try different STUN server: `atmosphere network --stun stun.cloudflare.com`

### "P2P connection failed"

This is OK - relay fallback should work.

**Why P2P might fail:**
- Symmetric NAT on both sides (check with `atmosphere network`)
- Firewall blocking UDP
- ISP restrictions

**Verify relay fallback:**
```bash
atmosphere peers
```

Should show `[relay]` connection.

### "Join code expired"

**Rob's machine:**
```bash
atmosphere join  # Generate new code
```

Send the new code to Matt.

### "Connection refused"

**Check Rob's server is running:**
```bash
# On Rob's machine
ps aux | grep atmosphere
```

Should show `atmosphere serve` process.

**Restart if needed:**
```bash
atmosphere serve --port 7777
```

---

## Network Requirements

### Ports

**Rob's machine needs:**
- UDP port 7777 (for STUN/P2P) - can be random
- TCP port 7777 (for HTTP API) - optional

**No port forwarding required!** NAT traversal handles it.

### Bandwidth

**Minimum:**
- 1 Mbps upload/download
- <200ms latency

**Recommended:**
- 10 Mbps upload/download  
- <100ms latency

### Firewall

**Allow outbound:**
- UDP to ports 3478, 19302 (STUN)
- UDP to any port (P2P)
- TCP/WebSocket to port 8080 (relay fallback)

**No inbound rules needed** (NAT traversal handles it).

---

## Success Criteria

✅ Both machines can see each other in `atmosphere peers`  
✅ Messages can be sent between machines  
✅ Distributed tasks can run across the mesh  
✅ Connection survives network changes (IP changes, WiFi reconnect)

---

## What to Document

After successful test, note:

1. **Network setup:**
   - Rob's NAT type
   - Matt's NAT type
   - Connection type (P2P or relay)
   - Latency

2. **Issues encountered:**
   - Any errors
   - How you fixed them
   - Time to establish connection

3. **Performance:**
   - Message round-trip time
   - File transfer speed (if tested)
   - Stability over time

---

## Clean Up

**Matt's machine (to leave mesh):**
```bash
atmosphere leave
```

**Rob's machine (to shut down):**
```bash
# Ctrl+C in the serve terminal
# Or:
pkill -f "atmosphere serve"
```

---

## Next Steps

Once basic internet mesh works:

1. **Add more nodes** - Test with 3+ machines
2. **Test mesh healing** - Disconnect/reconnect nodes
3. **Performance tests** - Large file transfers, streaming
4. **Security** - Enable encryption, authentication
5. **Production relay** - Deploy dedicated relay server

---

## Reference Commands

```bash
# Check network status
atmosphere network

# View mesh info
atmosphere status

# List peers
atmosphere peers

# View logs
atmosphere logs

# Advanced: Watch STUN/NAT logs
ATMOSPHERE_DEBUG=1 atmosphere network
```

---

## Questions?

If you hit issues:

1. Check logs: `atmosphere logs`
2. Run diagnostics: `atmosphere network --verbose`
3. File an issue: `atmosphere/issues` on GitHub

Include:
- Output of `atmosphere network`
- Connection logs
- NAT types of both machines
