# Atmosphere UI

A stunning web interface for the Atmosphere mesh network.

## Features

- **Dashboard**: Real-time mesh status, connected nodes, and capability count
- **Mesh Topology**: Interactive D3.js force-directed graph visualization
- **Intent Router Demo**: Watch intents route to the correct nodes with animations
- **Agent Inspector**: Monitor and control agents (wake/sleep states)
- **Live Gossip Feed**: Real-time stream of capability announcements
- **Join Panel**: Connect to existing meshes or invite others

## Tech Stack

- React 18 + Vite
- D3.js for mesh visualization
- WebSocket for real-time updates
- Lucide React for icons
- Modern dark theme with animations

## Development

```bash
# Install dependencies
npm install

# Start dev server (runs on port 11451)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Integration

The UI expects:
- API endpoints at `/v1/*`
- WebSocket endpoint at `/ws`
- Backend running on port 8000 (proxied in dev mode)

## Design

- Dark theme with gradient accents
- Fully responsive (mobile-first)
- Real-time animations and transitions
- Accessible and keyboard-friendly

## Port Configuration

- **Dev**: Port 11451 (serves UI + proxies API to :8000)
- **Production**: Can be served from FastAPI on :11451

The Vite config is set up to proxy API requests to the backend during development.
