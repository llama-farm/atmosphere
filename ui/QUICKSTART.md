# Quick Start Guide

## 1. Install Dependencies

```bash
cd ~/clawd/projects/atmosphere/ui
npm install
```

## 2. Start Development Server

```bash
npm run dev
```

This will:
- Start the Vite dev server on port **11451**
- Proxy API requests to port **8000**
- Enable hot module replacement (HMR)

## 3. Open in Browser

Navigate to: **http://localhost:11451**

You'll see:
- 📊 **Dashboard** - Default landing page
- 🕸️ **Mesh Topology** - Interactive network graph
- ⚡ **Intent Router** - Demo routing interface
- 🤖 **Agent Inspector** - Agent control panel
- 📡 **Gossip Feed** - Live message stream
- 🔗 **Join Panel** - Mesh connection interface

## 4. Production Build

```bash
# Build for production
npm run build

# Preview the build
npm run preview
```

Built files go to `dist/` directory.

## 5. Serve with FastAPI

```bash
# From project root
python -m atmosphere.api.server
```

The API will automatically serve the UI from `ui/dist/` if it exists.

## Troubleshooting

**Port already in use:**
```bash
# Change port in vite.config.js
server: { port: 3000 }
```

**API not responding:**
- Ensure backend is running on port 8000
- Check proxy settings in vite.config.js

**WebSocket not connecting:**
- Verify `/ws` endpoint exists
- Check browser console for errors

## Development Tips

- UI updates instantly with HMR
- WebSocket auto-reconnects
- Check browser DevTools console for errors
- Use React DevTools for component inspection

## File Structure

```
ui/
├── src/
│   ├── components/     # React components
│   ├── hooks/          # Custom React hooks
│   ├── App.jsx         # Main application
│   └── main.jsx        # Entry point
├── dist/               # Production build (after npm run build)
└── vite.config.js      # Vite configuration
```

## Environment Variables

Create `.env.local` (optional):
```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

Leave empty to use proxy in development.

---

**Ready to go!** 🚀
