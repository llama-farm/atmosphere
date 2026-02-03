# Atmosphere Relay Server - Deployment Guide

## Overview

The Atmosphere Relay Server enables mesh connections when direct P2P isn't possible:
- Both devices behind NAT
- No port forwarding available
- Cellular data on mobile devices

Both clients connect **outbound** to the relay - no firewall changes needed.

## Quick Start (Local Testing)

```bash
# With Docker Compose
cd ~/clawd/projects/atmosphere/relay
docker compose up

# Or directly with Python
pip install -r requirements.txt
python server.py
```

Test health: http://localhost:8765/health

## Deployment Options

### 1. Railway.app (Recommended - Free Tier)

Railway offers free hosting with automatic SSL.

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

**railway.json:**
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE"
  },
  "deploy": {
    "startCommand": "python server.py",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100
  }
}
```

After deployment, you'll get a URL like: `wss://atmosphere-relay-production.up.railway.app`

### 2. Fly.io (Global Edge - Free Tier)

Fly.io offers edge deployment for low latency.

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login and launch
fly auth login
fly launch
```

**fly.toml:**
```toml
app = "atmosphere-relay"
primary_region = "ord"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8765
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true

[[services]]
  internal_port = 8765
  protocol = "tcp"

  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]

  [[services.ports]]
    port = 80
    handlers = ["http"]

  [services.concurrency]
    type = "connections"
    hard_limit = 1000
    soft_limit = 800

[checks]
  [checks.health]
    port = 8765
    type = "http"
    interval = "30s"
    timeout = "5s"
    path = "/health"
```

Deploy: `fly deploy`

URL: `wss://atmosphere-relay.fly.dev`

### 3. DigitalOcean App Platform

```bash
# Using doctl CLI
doctl apps create --spec app-spec.yaml
```

**app-spec.yaml:**
```yaml
name: atmosphere-relay
services:
  - name: relay
    dockerfile_path: Dockerfile
    source_dir: /
    github:
      repo: your-username/atmosphere
      branch: main
      deploy_on_push: true
    http_port: 8765
    instance_size_slug: basic-xxs
    instance_count: 1
    health_check:
      http_path: /health
```

### 4. DigitalOcean Droplet ($5/mo)

```bash
# SSH into your droplet
ssh root@your-droplet-ip

# Install Docker
curl -fsSL https://get.docker.com | sh

# Clone and run
git clone https://github.com/your-repo/atmosphere.git
cd atmosphere/relay
docker compose up -d

# Setup nginx reverse proxy with SSL (optional)
apt install nginx certbot python3-certbot-nginx
```

**nginx config** (/etc/nginx/sites-available/relay):
```nginx
server {
    server_name relay.yourdomain.com;
    
    location / {
        proxy_pass http://localhost:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

```bash
# Enable site and get SSL
ln -s /etc/nginx/sites-available/relay /etc/nginx/sites-enabled/
certbot --nginx -d relay.yourdomain.com
```

### 5. Self-Hosted (Any VPS)

Requirements:
- Docker or Python 3.12+
- Port 8765 (or 80/443 with reverse proxy)
- ~256MB RAM

```bash
# Clone repo
git clone https://github.com/your-repo/atmosphere.git
cd atmosphere/relay

# Option A: Docker
docker compose up -d

# Option B: Systemd service
sudo cp atmosphere-relay.service /etc/systemd/system/
sudo systemctl enable atmosphere-relay
sudo systemctl start atmosphere-relay
```

**atmosphere-relay.service:**
```ini
[Unit]
Description=Atmosphere Relay Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/atmosphere/relay
ExecStart=/usr/bin/python3 server.py
Restart=always
RestartSec=5
Environment=PORT=8765
Environment=LOG_LEVEL=info

[Install]
WantedBy=multi-user.target
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8765` | Server port |
| `HOST` | `0.0.0.0` | Bind address |
| `LOG_LEVEL` | `info` | Logging level (debug, info, warning, error) |

### Client Configuration

Set the relay URL in Atmosphere:

```bash
# On Mac (in .bashrc or .zshrc)
export ATMOSPHERE_RELAY_URL="wss://relay.yourdomain.com"

# Or in Atmosphere config
echo "relay_url: wss://relay.yourdomain.com" >> ~/.atmosphere/config.yaml
```

## Security Considerations

### Token Validation (TODO)

Currently the relay accepts all connections. For production:

1. Validate tokens against the mesh's public key
2. Implement rate limiting per node
3. Add IP-based allowlists if needed

### SSL/TLS

Always use `wss://` (WebSocket Secure) in production:
- Railway/Fly.io: Automatic SSL
- Self-hosted: Use nginx + certbot

### Rate Limiting

Add nginx rate limiting for DDoS protection:

```nginx
limit_req_zone $binary_remote_addr zone=relay:10m rate=10r/s;

server {
    location / {
        limit_req zone=relay burst=20;
        # ... proxy config
    }
}
```

## Monitoring

### Health Check

```bash
curl https://relay.yourdomain.com/health
# {"status": "ok", "meshes": 2, "connections": 5, "uptime_seconds": 3600}
```

### Statistics

```bash
curl https://relay.yourdomain.com/stats
# Detailed stats about meshes, connections, and message counts
```

### Logging

Docker logs:
```bash
docker compose logs -f relay
```

Systemd logs:
```bash
journalctl -u atmosphere-relay -f
```

## Troubleshooting

### Connection Issues

1. **WebSocket upgrade fails**
   - Check nginx configuration includes upgrade headers
   - Verify SSL certificate is valid

2. **Timeout on registration**
   - Client must send register message within 30 seconds
   - Check network connectivity

3. **Peer not found errors**
   - Peer may have disconnected
   - Check mesh_id matches on both sides

### Performance

- Each connection uses ~1KB RAM
- Message relay is lightweight (just JSON forwarding)
- Suitable for 1000+ connections on a small VPS

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Relay Server                             │
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │ MeshRoom A  │    │ MeshRoom B  │    │ MeshRoom C  │    │
│  │             │    │             │    │             │    │
│  │ ┌─────────┐ │    │ ┌─────────┐ │    │ ┌─────────┐ │    │
│  │ │ Peer 1  │ │    │ │ Peer 1  │ │    │ │ Peer 1  │ │    │
│  │ │ (Mac)   │ │    │ │ (iPhone)│ │    │ │ (Pi)    │ │    │
│  │ └─────────┘ │    │ └─────────┘ │    │ └─────────┘ │    │
│  │ ┌─────────┐ │    │ ┌─────────┐ │    │             │    │
│  │ │ Peer 2  │ │    │ │ Peer 2  │ │    │             │    │
│  │ │(Android)│ │    │ │ (Mac)   │ │    │             │    │
│  │ └─────────┘ │    │ └─────────┘ │    │             │    │
│  └─────────────┘    └─────────────┘    └─────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘

Message Flow:
  Android → Relay → Mac
  
  1. Android sends: {"type": "llm_request", "prompt": "Hello"}
  2. Relay forwards to Mac (has LLM capability)
  3. Mac processes and sends: {"type": "llm_response", "response": "Hi!"}
  4. Relay forwards to Android
```

## Cost Estimates

| Platform | Free Tier | Paid |
|----------|-----------|------|
| Railway | 500 hours/month | $5/mo for always-on |
| Fly.io | 3 shared VMs | $1.94/mo per VM |
| DigitalOcean | None | $5/mo droplet |
| Render | 750 hours/month | $7/mo |
