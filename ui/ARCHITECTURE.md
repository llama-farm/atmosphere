# UI Architecture

## Overview

The Atmosphere UI is a modern React application built with Vite, featuring real-time WebSocket updates, D3.js visualizations, and a dark theme optimized for demo presentations.

## Structure

```
ui/
├── src/
│   ├── components/          # React components
│   │   ├── Dashboard.jsx    # Real-time mesh status
│   │   ├── MeshTopology.jsx # D3.js force-directed graph
│   │   ├── IntentRouter.jsx # Intent routing demo with animations
│   │   ├── AgentInspector.jsx # Agent control panel
│   │   ├── GossipFeed.jsx   # Live gossip message stream
│   │   └── JoinPanel.jsx    # Mesh joining interface
│   ├── hooks/
│   │   └── useWebSocket.js  # WebSocket connection manager
│   ├── App.jsx              # Main app with navigation
│   ├── App.css              # App-level styles
│   ├── index.css            # Global styles and theme
│   └── main.jsx             # Entry point
├── public/                  # Static assets
├── index.html               # HTML template
├── vite.config.js           # Vite configuration
└── package.json             # Dependencies

```

## Components

### Dashboard
- Real-time mesh statistics
- Connected nodes count
- Total capabilities
- Active agents
- Recent activity feed
- Health indicators with pulse animations

### Mesh Topology
- D3.js force-directed graph
- Interactive node dragging
- Zoom and pan support
- Color-coded node states (leader/active)
- Capability count badges
- Real-time updates from gossip protocol

### Intent Router Demo
- Intent input with auto-suggestions
- Animated routing visualization
- Real-time confidence scores
- Execution time tracking
- Visual flow from user to target node

### Agent Inspector
- Grid view of all agents
- Real-time status (running/suspended)
- Wake/sleep controls
- Capability lists
- Uptime tracking
- Activity indicators

### Gossip Feed
- Live message stream
- Filterable by type (capabilities/nodes/errors)
- Message timestamps
- Color-coded by event type
- Auto-scroll with manual override
- Statistics dashboard

### Join Panel
- Token-based mesh joining
- Invitation token generation
- Copy-to-clipboard functionality
- Join confirmation with mesh details
- Two-panel layout (join/invite)

## State Management

- **Component State**: Local state with `useState` for UI state
- **WebSocket**: Custom `useWebSocket` hook for real-time data
- **Props**: Data passed from App to components via `wsData`

## WebSocket Integration

The `useWebSocket` hook:
- Auto-reconnects on disconnect
- Maintains message history (last 100)
- Provides connection status
- Handles JSON parsing
- Exposes send function

Message flow:
1. App component establishes WebSocket connection
2. Receives real-time updates
3. Passes `lastMessage` to child components
4. Components react to new data

## Styling

### Theme System
CSS variables in `index.css`:
- Background colors (primary/secondary/tertiary)
- Text colors (primary/secondary/tertiary)
- Accent colors (primary/secondary/success/warning/danger)
- Border and glow effects

### Animations
- `pulse`: Opacity animation for status indicators
- `glow`: Box shadow pulse for emphasis
- `slideIn`: Horizontal slide for new items
- `fadeIn`: Opacity fade for page transitions

### Responsive Design
- Desktop-first approach
- Breakpoints:
  - 968px: Tablet (hide sidebar, show menu)
  - 768px: Mobile (single column, compact)
- Mobile menu overlay
- Touch-friendly controls

## API Integration

### REST Endpoints
- `GET /v1/mesh/status` - Mesh statistics
- `GET /v1/mesh/topology` - Node graph data
- `POST /v1/route` - Intent routing
- `GET /v1/agents` - Agent list
- `PATCH /v1/agents/:id` - Agent control
- `POST /v1/mesh/join` - Join mesh
- `POST /v1/mesh/token` - Generate token

### WebSocket
- Endpoint: `/ws`
- Message types:
  - `gossip`: Capability announcements
  - `status`: Mesh status updates
  - `route`: Intent routing events
  - `agent`: Agent state changes

## Performance

- Code splitting by route
- Lazy loading for D3.js
- Debounced WebSocket updates
- Limited message history (50-100 items)
- CSS animations (GPU accelerated)
- Optimized re-renders with React.memo (if needed)

## Development

```bash
# Install
npm install

# Dev server (with API proxy)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Lint
npm run lint
```

## Production Deployment

1. Build the UI: `npm run build`
2. Output goes to `dist/`
3. FastAPI serves static files from `ui/dist/`
4. Access at `http://localhost:11451/`

The API automatically serves the UI if `ui/dist/` exists, otherwise returns JSON status.

## Design Principles

1. **Dark Theme**: Optimized for presentations and demos
2. **Real-time**: WebSocket updates create live feel
3. **Animations**: Smooth transitions and feedback
4. **Responsive**: Works on all screen sizes
5. **Accessible**: Keyboard navigation, ARIA labels
6. **Performance**: Fast load, smooth interactions

## Future Enhancements

- [ ] Node detail modal with full capability list
- [ ] Agent execution logs viewer
- [ ] Intent history and replay
- [ ] Mesh performance graphs
- [ ] Settings panel for theme customization
- [ ] Export topology as PNG/SVG
- [ ] Real-time capability heat map
- [ ] Multi-language support
