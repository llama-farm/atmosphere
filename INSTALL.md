# Installation Guide

## macOS

### Method 1: Homebrew (Recommended)

The easiest way to install Atmosphere on macOS is via Homebrew:

```bash
# Add the Atmosphere tap
brew tap llama-farm/atmosphere

# Install
brew install atmosphere

# Verify installation
atmosphere --version

# Initialize your node
atmosphere init

# Start the menu bar app
atmosphere menubar
```

**Menu Bar App:**
The menu bar app provides a native macOS interface with:
- ☁️ icon in your menu bar
- One-click server start/stop
- Quick access to dashboard, API docs, and capabilities
- Auto-updates with mesh status
- System tray notifications

**Background Service:**
To run Atmosphere as a background service:

```bash
# Start service
brew services start atmosphere

# Stop service  
brew services stop atmosphere

# Restart service
brew services restart atmosphere
```

### Method 2: pip (Python Package)

Install via pip if you prefer managing Python packages directly:

```bash
# Install the package
pip install atmosphere-mesh

# Verify installation
atmosphere --version

# Initialize your node
atmosphere init

# Start the API server
atmosphere serve --host 0.0.0.0 --port 11451
```

**Install from source:**

```bash
git clone https://github.com/llama-farm/atmosphere.git
cd atmosphere
pip install -e .
```

### Method 3: From GitHub Release

Download the latest release from GitHub:

```bash
# Download wheel
curl -LO https://github.com/llama-farm/atmosphere/releases/latest/download/atmosphere_mesh-1.0.0-py3-none-any.whl

# Install
pip install atmosphere_mesh-1.0.0-py3-none-any.whl
```

---

## Linux

### Via pip

```bash
# Install
pip install atmosphere-mesh

# Initialize
atmosphere init

# Start server
atmosphere serve
```

### Via apt (Ubuntu/Debian)

```bash
# Add repository (coming soon)
curl -fsSL https://atmosphere.llama.farm/install.sh | sudo bash

# Install
sudo apt install atmosphere

# Start service
sudo systemctl start atmosphere
sudo systemctl enable atmosphere
```

---

## Windows

### Via pip

```bash
# Install
pip install atmosphere-mesh

# Initialize
atmosphere init

# Start server
atmosphere serve
```

### Via MSI Installer (coming soon)

Download the MSI installer from the [releases page](https://github.com/llama-farm/atmosphere/releases).

---

## Verify Installation

After installation, verify everything works:

```bash
# Check version
atmosphere --version

# Initialize node (if not already done)
atmosphere init

# Scan for AI backends
atmosphere scan

# Check status
atmosphere status

# Start server
atmosphere serve
```

Open your browser to http://localhost:11451 to see the dashboard.

---

## Auto-Start on Login (macOS)

To run Atmosphere automatically when you log in:

```bash
# Install as login item
atmosphere install

# This adds the menu bar app to your login items
# The server will start automatically in the background
```

To remove:

```bash
atmosphere uninstall
```

---

## Configuration

Atmosphere stores configuration in `~/.atmosphere/`:

```
~/.atmosphere/
├── identity.json       # Node identity (Ed25519 keypair)
├── mesh.json          # Mesh membership (if joined)
├── config.json        # User preferences
└── capabilities/      # Registered capabilities
```

---

## Next Steps

After installation:

1. **Scan for capabilities:**
   ```bash
   atmosphere scan
   ```

2. **View available capabilities:**
   ```bash
   atmosphere status
   ```

3. **Start the API server:**
   ```bash
   atmosphere serve
   ```

4. **Test the API:**
   ```bash
   curl http://localhost:11451/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"messages": [{"role": "user", "content": "Hello!"}]}'
   ```

5. **Read the documentation:**
   - [API Reference](design/API_REFERENCE.md)
   - [Architecture](ARCHITECTURE.md)
   - [White Paper](https://drive.google.com/file/d/1-LmkSI4cMZcQiCG6uUgJSerJi2FwUNli/view?usp=sharing)

---

## Troubleshooting

### Command not found

If `atmosphere` command is not found after installation:

```bash
# Check if it's in your PATH
which atmosphere

# If using pip, try:
python3 -m atmosphere --version

# Add to PATH (in ~/.bashrc or ~/.zshrc):
export PATH="$HOME/.local/bin:$PATH"
```

### Menu bar app won't start

The menu bar app requires macOS 10.14+. Make sure you have:

```bash
# Install dependencies
pip install rumps pillow
```

### Port already in use

If port 11451 is in use, specify a different port:

```bash
atmosphere serve --port 8000
```

Or update `~/.atmosphere/config.json`:

```json
{
  "server": {
    "port": 8000
  }
}
```

### No capabilities found

Run the scanner to detect AI backends:

```bash
atmosphere scan --verbose
```

Make sure you have at least one AI backend installed:
- [LlamaFarm](https://llama.farm) (recommended)
- [Ollama](https://ollama.ai)
- OpenAI API key

---

## Uninstall

### Homebrew

```bash
brew uninstall atmosphere
brew untap llama-farm/atmosphere
```

### pip

```bash
pip uninstall atmosphere-mesh
```

### Remove configuration

```bash
rm -rf ~/.atmosphere
```

---

## Getting Help

- **Documentation:** https://atmosphere.llama.farm
- **GitHub Issues:** https://github.com/llama-farm/atmosphere/issues
- **Discord:** https://discord.gg/llamafarm
