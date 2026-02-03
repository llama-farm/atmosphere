# Atmosphere Menu Bar App

Atmosphere includes a native macOS menu bar application that runs the API server in the background and provides quick access to common actions.

## Overview

Like Ollama, Atmosphere can run as a menu bar daemon on macOS. When installed:
- The mesh icon appears in your menu bar
- The API server runs automatically on `localhost:11451`
- Any app can hit the local API without manual server management

## Quick Start

### Run Once (Manual)
```bash
atmosphere menubar
```

### Install for Auto-Start
```bash
atmosphere install
```

This creates a LaunchAgent that starts Atmosphere when you log in.

### Remove Auto-Start
```bash
atmosphere uninstall
```

## Menu Bar Features

The menu bar app provides:

- **Status Display**: Shows if the mesh is active and the port
- **Mesh Info**: Number of peers and mesh name
- **Capabilities**: Available AI models/capabilities
- **Quick Actions**:
  - Open Dashboard (web UI)
  - View API Docs
  - View Capabilities endpoint
  - Copy API URL to clipboard
  - Copy sample cURL command
- **Utilities**:
  - View Logs (opens Console.app)
  - Open Config file
  - Restart Server
  - Quit

## Architecture

```
┌─────────────────────────────────────────────┐
│           macOS Menu Bar                     │
│  ┌─────┐                                     │
│  │ 🔺 │ ← Atmosphere icon                   │
│  └─────┘                                     │
└─────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────┐
│        AtmosphereMenuBar (rumps)            │
│  ┌─────────────────────────────────────┐    │
│  │  Background Thread                   │    │
│  │  ├─ FastAPI Server                   │    │
│  │  └─ uvicorn on localhost:11451       │    │
│  └─────────────────────────────────────┘    │
│  ┌─────────────────────────────────────┐    │
│  │  Timer (5s interval)                 │    │
│  │  └─ Updates status, mesh info        │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `atmosphere/app/menubar.py` | Main menu bar application |
| `atmosphere/assets/icon.png` | Menu bar icon (template image) |
| `atmosphere/install/com.llamafarm.atmosphere.plist` | LaunchAgent for auto-start |

## LaunchAgent

The LaunchAgent (`com.llamafarm.atmosphere.plist`) is installed to `~/Library/LaunchAgents/` and configured to:

- Run at login (`RunAtLoad`)
- Restart on crash (`KeepAlive`)
- Log to `/tmp/atmosphere.log` and `/tmp/atmosphere.err`
- Only run in GUI sessions (`LimitLoadToSessionType: Aqua`)

## CLI Commands

```bash
# Run the menu bar app manually
atmosphere menubar

# Install to run on login
atmosphere install

# Remove from login items
atmosphere uninstall

# Run as headless daemon (no menu bar)
atmosphere daemon
```

## Dependencies

- **rumps**: macOS menu bar framework
- **pillow**: Icon generation

Install with:
```bash
pip install rumps pillow
```

Or they're included when you install atmosphere:
```bash
pip install atmosphere-mesh
```

## Customization

### Icon
The menu bar icon is a template image at `atmosphere/assets/icon.png`. You can replace it with your own 22x22 or 44x44 PNG.

To regenerate the default icon:
```bash
python atmosphere/assets/generate_icon.py
```

### Config
Config is stored at `~/.atmosphere/config.json`. Open it via the menu or:
```bash
open ~/.atmosphere/config.json
```

## Troubleshooting

### Menu bar icon not appearing
1. Check if another app is hiding menu bar icons
2. Try running manually: `atmosphere menubar`
3. Check logs: `cat /tmp/atmosphere-menubar.log`

### Server not starting
1. Check if port 11451 is in use: `lsof -i :11451`
2. Run `atmosphere init` first
3. Check logs: `cat /tmp/atmosphere.log`

### LaunchAgent not loading
1. Check plist syntax: `plutil ~/Library/LaunchAgents/com.llamafarm.atmosphere.plist`
2. Check launchd status: `launchctl list | grep atmosphere`
3. Manually load: `launchctl load ~/Library/LaunchAgents/com.llamafarm.atmosphere.plist`

## Development

To run the menu bar app in development:
```bash
cd ~/clawd/projects/atmosphere
source .venv/bin/activate
python -m atmosphere.app.menubar
```

Or via the CLI:
```bash
atmosphere menubar
```
