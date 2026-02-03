# Packaging Design

> **Goal**: One-command install for Atmosphere on any platform.
> 
> ```bash
> pip install atmosphere-mesh    # PyPI
> brew install llama-farm/tap/atmosphere  # Homebrew
> apt install atmosphere         # Debian/Ubuntu
> docker run llama-farm/atmosphere  # Docker
> ```

## Overview

Atmosphere is a semantic mesh network for AI capabilities. The packaging strategy prioritizes:

1. **Simplicity** - Single command installation
2. **Cross-platform** - macOS, Linux, Windows
3. **Optional dependencies** - Core functionality without heavy ML deps
4. **Bundled UI** - React dashboard included in package

### Current State

| Component | Status | Notes |
|-----------|--------|-------|
| Python package | ✅ Building | `python -m build` works |
| PyPI upload | ⏳ Pending | Need to reserve `atmosphere-mesh` name |
| Homebrew formula | ⏳ Designed | Formula ready, tap needed |
| Debian package | 📋 Planned | Design complete |
| Docker image | 📋 Planned | Multi-stage build ready |
| Windows | ⏳ Deferred | Test after Linux/macOS |

### Build Tested

```bash
# In project root
source .venv/bin/activate
python -m build
# Creates:
#   dist/atmosphere-1.0.0-py3-none-any.whl (176KB)
#   dist/atmosphere-1.0.0.tar.gz (164KB)
```

---

## Package Types

### 1. PyPI (`pip install atmosphere-mesh`)

The primary distribution method. Pure Python with optional native dependencies.

#### pyproject.toml Updates Required

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
# Changed name for PyPI (atmosphere is taken)
name = "atmosphere-mesh"
version = "1.0.0"
description = "Semantic mesh routing for AI capabilities - The Internet of Intent"
readme = "README.md"
license = "MIT"  # SPDX format (new style)
requires-python = ">=3.10"
authors = [
    {name = "Rownd AI", email = "hello@rownd.ai"}
]
keywords = ["ai", "mesh", "routing", "llm", "distributed", "intent", "semantic"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
    "Topic :: System :: Distributed Computing",
    "Framework :: FastAPI",
]

# Core dependencies - what you NEED to run
dependencies = [
    "aiohttp>=3.9.0",
    "cryptography>=41.0.0",
    "fastapi>=0.109.0",
    "uvicorn>=0.25.0",
    "numpy>=1.24.0",
    "click>=8.0.0",
    "rich>=13.0.0",
    "zeroconf>=0.131.0",
    "pydantic>=2.0.0",
    "psutil>=5.9.0",
    "httpx>=0.26.0",     # MISSING - needed for OpenAI compat router
    "PyYAML>=6.0",       # For config files
]

[project.optional-dependencies]
# Development tools
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.26.0",
    "mypy>=1.8.0",
    "ruff>=0.1.0",
    "build",
    "twine",
]

# ML capabilities (heavy deps, optional)
ml = [
    "torch>=2.0.0",
    "transformers>=4.35.0",
    "sentence-transformers>=2.2.0",
]

# Vision capabilities
vision = [
    "pillow>=10.0.0",
    "opencv-python>=4.8.0",
]

# Full install with everything
full = [
    "atmosphere-mesh[ml,vision]",
]

[project.scripts]
atmosphere = "atmosphere.cli:main"

[project.urls]
Homepage = "https://github.com/llama-farm/atmosphere"
Documentation = "https://atmosphere.llama.farm"
Repository = "https://github.com/llama-farm/atmosphere"
Changelog = "https://github.com/llama-farm/atmosphere/blob/main/CHANGELOG.md"
Issues = "https://github.com/llama-farm/atmosphere/issues"

[tool.setuptools]
packages = ["atmosphere"]
include-package-data = true

[tool.setuptools.packages.find]
include = ["atmosphere*"]

[tool.setuptools.package-data]
atmosphere = [
    "ui/dist/**/*",  # Bundled React app
    "py.typed",      # PEP 561 marker
]
```

#### Directory Structure for PyPI

```
atmosphere/
├── atmosphere/
│   ├── __init__.py          # Version, exports
│   ├── cli.py               # Click CLI
│   ├── config.py            # Configuration
│   ├── py.typed             # Type hints marker
│   ├── api/                 # FastAPI server
│   ├── agents/              # Agent system
│   ├── auth/                # Authentication
│   ├── capabilities/        # Capability definitions
│   ├── deployment/          # Model deployment
│   ├── discovery/           # Backend discovery
│   ├── mesh/                # Mesh networking
│   ├── network/             # NAT/STUN/Relay
│   ├── router/              # Semantic routing
│   ├── tools/               # Tool system
│   └── ui/
│       └── dist/            # Pre-built React app (bundled)
│           ├── index.html
│           ├── assets/
│           └── ...
├── pyproject.toml
├── README.md
├── LICENSE
├── CHANGELOG.md
└── MANIFEST.in
```

#### MANIFEST.in (for sdist)

```
include LICENSE
include README.md
include CHANGELOG.md
include pyproject.toml

recursive-include atmosphere/ui/dist *
recursive-include atmosphere *.typed
global-exclude __pycache__
global-exclude *.py[cod]
global-exclude .git*
```

#### Build & Publish Commands

```bash
# Install build tools
pip install build twine

# Build package
python -m build

# Check package
twine check dist/*

# Upload to TestPyPI first
twine upload --repository testpypi dist/*

# Test install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ atmosphere-mesh

# Upload to PyPI (production)
twine upload dist/*
```

#### Known Issues Found

1. **Missing httpx dependency** - `atmosphere/router/openai_compat.py` imports `httpx` but it's not in dependencies
2. **License format deprecated** - Use SPDX string format: `license = "MIT"` instead of table format
3. **UI not bundled** - Need to run `npm run build` in `ui/` before packaging

---

### 2. Homebrew (`brew install llama-farm/tap/atmosphere`)

Homebrew formula for macOS (Intel + Apple Silicon). Uses a custom tap.

#### Tap Setup

```bash
# Create tap repository
gh repo create llama-farm/homebrew-tap --public --description "Homebrew tap for llama-farm projects"

# Clone and add formula
git clone git@github.com:llama-farm/homebrew-tap.git
cd homebrew-tap
mkdir -p Formula
```

#### Formula: `Formula/atmosphere.rb`

```ruby
class Atmosphere < Formula
  include Language::Python::Virtualenv

  desc "The Internet of Intent - semantic mesh routing for AI capabilities"
  homepage "https://github.com/llama-farm/atmosphere"
  url "https://files.pythonhosted.org/packages/source/a/atmosphere-mesh/atmosphere-mesh-1.0.0.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_SHA256"
  license "MIT"

  depends_on "python@3.12"
  depends_on "node" => :build  # For UI build
  depends_on "rust" => :build   # For cryptography

  # Resource definitions for vendored dependencies
  # Generate with: pip-compile --generate-hashes pyproject.toml
  # Then: poet --resources atmosphere-mesh > resources.rb
  
  resource "aiohttp" do
    url "https://files.pythonhosted.org/packages/..."
    sha256 "..."
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/..."
    sha256 "..."
  end

  resource "cryptography" do
    url "https://files.pythonhosted.org/packages/..."
    sha256 "..."
  end

  resource "fastapi" do
    url "https://files.pythonhosted.org/packages/..."
    sha256 "..."
  end

  resource "numpy" do
    url "https://files.pythonhosted.org/packages/..."
    sha256 "..."
  end

  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/..."
    sha256 "..."
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/..."
    sha256 "..."
  end

  resource "uvicorn" do
    url "https://files.pythonhosted.org/packages/..."
    sha256 "..."
  end

  resource "zeroconf" do
    url "https://files.pythonhosted.org/packages/..."
    sha256 "..."
  end

  # ... more resources

  def install
    # Build the React UI first
    cd "ui" do
      system "npm", "ci"
      system "npm", "run", "build"
    end

    # Copy built UI to package
    mkdir_p buildpath/"atmosphere/ui"
    cp_r "ui/dist", buildpath/"atmosphere/ui/"

    # Install Python package
    virtualenv_install_with_resources

    # Generate shell completions
    generate_completions_from_executable(
      bin/"atmosphere", 
      shells: [:bash, :zsh, :fish],
      shell_parameter_format: :click
    )
  end

  def post_install
    # Create data directory
    (var/"atmosphere").mkpath
    
    # Set up launchd service
    (var/"log/atmosphere").mkpath
  end

  def caveats
    <<~EOS
      Atmosphere has been installed!

      To get started:
        atmosphere init           # Initialize this node
        atmosphere serve          # Start the API server
        atmosphere mesh create -n "my-mesh"  # Create a mesh

      To start atmosphere as a background service:
        brew services start atmosphere

      Data is stored in:
        #{var}/atmosphere

      Logs are stored in:
        #{var}/log/atmosphere

      For more information:
        atmosphere --help
        https://atmosphere.llama.farm
    EOS
  end

  # Background service definition
  service do
    run [opt_bin/"atmosphere", "serve"]
    working_dir var/"atmosphere"
    log_path var/"log/atmosphere/atmosphere.log"
    error_log_path var/"log/atmosphere/atmosphere-error.log"
    keep_alive true
    environment_variables PATH: std_service_path_env
  end

  test do
    # Basic CLI test
    assert_match "Atmosphere", shell_output("#{bin}/atmosphere --version")
    
    # Init test (in temp directory)
    ENV["ATMOSPHERE_DATA_DIR"] = testpath
    system "#{bin}/atmosphere", "init"
    assert_predicate testpath/"identity.json", :exist?
    
    # Status test
    assert_match "Node Status", shell_output("#{bin}/atmosphere status")
  end
end
```

#### Generate Resources Script

```bash
#!/bin/bash
# scripts/generate-homebrew-resources.sh

# Install poet if not present
pip install homebrew-pypi-poet

# Generate resources
poet --resources atmosphere-mesh > /tmp/resources.rb

echo "Resources generated. Copy to Formula/atmosphere.rb"
cat /tmp/resources.rb
```

#### Usage After Installation

```bash
# Install from tap
brew tap llama-farm/tap
brew install atmosphere

# Or in one command
brew install llama-farm/tap/atmosphere

# Start service
brew services start atmosphere

# Check status
atmosphere status
```

---

### 3. Debian Package (`apt install atmosphere`)

For Debian/Ubuntu Linux distributions.

#### Debian Directory Structure

```
debian/
├── changelog          # Package changelog
├── compat             # Debhelper compatibility
├── control            # Package metadata
├── copyright          # License info
├── rules              # Build rules
├── atmosphere.install # Files to install
├── atmosphere.service # Systemd service
├── postinst           # Post-install script
├── prerm              # Pre-removal script
└── postrm             # Post-removal script
```

#### debian/control

```
Source: atmosphere
Section: python
Priority: optional
Maintainer: Rownd AI <hello@rownd.ai>
Build-Depends: debhelper-compat (= 13),
               dh-python,
               python3-all,
               python3-setuptools,
               python3-pip,
               python3-venv,
               nodejs (>= 18),
               npm
Standards-Version: 4.6.2
Homepage: https://github.com/llama-farm/atmosphere
Vcs-Git: https://github.com/llama-farm/atmosphere.git
Vcs-Browser: https://github.com/llama-farm/atmosphere

Package: atmosphere
Architecture: all
Depends: ${python3:Depends},
         ${misc:Depends},
         python3 (>= 3.10),
         python3-aiohttp,
         python3-click,
         python3-cryptography,
         python3-fastapi,
         python3-numpy,
         python3-pydantic,
         python3-rich,
         python3-uvicorn,
         python3-zeroconf
Recommends: ollama
Description: Semantic mesh routing for AI capabilities
 Atmosphere is the Internet of Intent - a semantic mesh network
 that routes AI intents to the best available capabilities across
 your personal cloud of devices.
 .
 Features:
  - Automatic discovery of AI backends (Ollama, LlamaFarm, etc.)
  - Semantic routing based on intent understanding
  - Mesh networking for distributed AI
  - Built-in web dashboard
```

#### debian/rules

```makefile
#!/usr/bin/make -f

export DH_VERBOSE=1
export PYBUILD_NAME=atmosphere

%:
	dh $@ --with python3 --buildsystem=pybuild

override_dh_auto_build:
	# Build React UI first
	cd ui && npm ci && npm run build
	# Copy to package
	mkdir -p atmosphere/ui
	cp -r ui/dist atmosphere/ui/
	# Build Python package
	dh_auto_build

override_dh_auto_install:
	dh_auto_install
	# Install systemd service
	install -D -m 644 debian/atmosphere.service debian/atmosphere/lib/systemd/system/atmosphere.service
	# Install bash completion
	install -D -m 644 completions/atmosphere.bash debian/atmosphere/usr/share/bash-completion/completions/atmosphere
```

#### debian/atmosphere.service

```ini
[Unit]
Description=Atmosphere - The Internet of Intent
Documentation=https://atmosphere.llama.farm
After=network.target

[Service]
Type=simple
User=atmosphere
Group=atmosphere
ExecStart=/usr/bin/atmosphere serve
WorkingDirectory=/var/lib/atmosphere
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/atmosphere /var/log/atmosphere

# Environment
Environment="ATMOSPHERE_DATA_DIR=/var/lib/atmosphere"
Environment="ATMOSPHERE_LOG_DIR=/var/log/atmosphere"

[Install]
WantedBy=multi-user.target
```

#### debian/postinst

```bash
#!/bin/bash
set -e

case "$1" in
    configure)
        # Create atmosphere user if it doesn't exist
        if ! getent passwd atmosphere > /dev/null; then
            adduser --system --group --home /var/lib/atmosphere \
                    --no-create-home --disabled-password \
                    --gecos "Atmosphere daemon" atmosphere
        fi

        # Create directories
        mkdir -p /var/lib/atmosphere
        mkdir -p /var/log/atmosphere
        
        # Set ownership
        chown atmosphere:atmosphere /var/lib/atmosphere
        chown atmosphere:atmosphere /var/log/atmosphere

        # Enable and start service
        systemctl daemon-reload
        systemctl enable atmosphere
        
        echo ""
        echo "Atmosphere installed successfully!"
        echo ""
        echo "To initialize: sudo -u atmosphere atmosphere init"
        echo "To start:      systemctl start atmosphere"
        echo "To check:      atmosphere status"
        echo ""
        ;;
esac

#DEBHELPER#

exit 0
```

#### debian/prerm

```bash
#!/bin/bash
set -e

case "$1" in
    remove|upgrade|deconfigure)
        # Stop service
        systemctl stop atmosphere || true
        systemctl disable atmosphere || true
        ;;
esac

#DEBHELPER#

exit 0
```

#### debian/postrm

```bash
#!/bin/bash
set -e

case "$1" in
    purge)
        # Remove data and config
        rm -rf /var/lib/atmosphere
        rm -rf /var/log/atmosphere
        
        # Remove user
        deluser --system atmosphere || true
        ;;
esac

#DEBHELPER#

exit 0
```

#### Build Commands

```bash
# Install build dependencies
sudo apt install devscripts debhelper dh-python python3-all

# Build package
dpkg-buildpackage -us -uc

# Or use pbuilder for clean builds
sudo pbuilder create --distribution jammy
sudo pbuilder build atmosphere_1.0.0-1.dsc

# Install locally
sudo dpkg -i ../atmosphere_1.0.0-1_all.deb
sudo apt -f install  # Fix dependencies
```

---

### 4. Docker Image

Multi-stage build for minimal image size.

#### Dockerfile

```dockerfile
# =============================================================================
# Stage 1: Build UI
# =============================================================================
FROM node:20-alpine AS ui-builder

WORKDIR /app/ui
COPY ui/package*.json ./
RUN npm ci --production=false

COPY ui/ ./
RUN npm run build

# =============================================================================
# Stage 2: Build Python
# =============================================================================
FROM python:3.12-slim AS python-builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY pyproject.toml README.md LICENSE ./
COPY atmosphere/ atmosphere/

# Copy pre-built UI
COPY --from=ui-builder /app/ui/dist atmosphere/ui/dist/

# Install package
RUN pip install --no-cache-dir .

# =============================================================================
# Stage 3: Runtime
# =============================================================================
FROM python:3.12-slim AS runtime

# Labels
LABEL org.opencontainers.image.title="Atmosphere"
LABEL org.opencontainers.image.description="The Internet of Intent - semantic mesh routing for AI"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.source="https://github.com/llama-farm/atmosphere"
LABEL org.opencontainers.image.licenses="MIT"

# Create non-root user
RUN useradd --create-home --shell /bin/bash atmosphere

# Copy virtual environment from builder
COPY --from=python-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set up data directory
RUN mkdir -p /data && chown atmosphere:atmosphere /data
VOLUME /data

# Switch to non-root user
USER atmosphere
WORKDIR /data

# Default environment
ENV ATMOSPHERE_DATA_DIR=/data
ENV ATMOSPHERE_HOST=0.0.0.0
ENV ATMOSPHERE_PORT=11451

# Expose ports
EXPOSE 11451

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:11451/health || exit 1

# Entry point
ENTRYPOINT ["atmosphere"]
CMD ["serve"]
```

#### docker-compose.yml

```yaml
version: '3.8'

services:
  atmosphere:
    image: llama-farm/atmosphere:latest
    container_name: atmosphere
    restart: unless-stopped
    ports:
      - "11451:11451"
    volumes:
      - atmosphere-data:/data
    environment:
      - ATMOSPHERE_NODE_NAME=docker-node
    networks:
      - atmosphere-net

  # Optional: Ollama for local models
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama
    networks:
      - atmosphere-net
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

volumes:
  atmosphere-data:
  ollama-data:

networks:
  atmosphere-net:
    driver: bridge
```

#### Build & Push Commands

```bash
# Build image
docker build -t llama-farm/atmosphere:latest .

# Build for multiple architectures
docker buildx create --name multiarch --use
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t llama-farm/atmosphere:latest \
  -t llama-farm/atmosphere:1.0.0 \
  --push .

# Run locally
docker run -d \
  --name atmosphere \
  -p 11451:11451 \
  -v atmosphere-data:/data \
  llama-farm/atmosphere:latest

# Initialize inside container
docker exec atmosphere atmosphere init

# View logs
docker logs -f atmosphere
```

#### Image Size Analysis

| Stage | Size | Contents |
|-------|------|----------|
| ui-builder | ~300MB | Node + npm packages |
| python-builder | ~500MB | Python + build tools + deps |
| runtime | ~150MB | Python slim + app only |

---

## CLI Entry Points

The `atmosphere` command provides the following subcommands:

```bash
# Node lifecycle
atmosphere init                 # Initialize node identity and scan backends
atmosphere serve               # Start API server (default port 11451)
atmosphere status              # Show node and mesh status
atmosphere network             # Show network connectivity info

# Mesh management
atmosphere mesh create -n NAME # Create new mesh (you become founder)
atmosphere mesh join TARGET    # Join mesh by code, IP, or full token
atmosphere mesh leave          # Leave current mesh
atmosphere mesh invite         # Generate invite code for others
atmosphere mesh status         # Show mesh status

# Agent management
atmosphere agent list          # List running agents
atmosphere agent spawn TYPE    # Spawn new agent
atmosphere agent types         # List available agent types
atmosphere agent invoke ID     # Send intent to agent

# Tool management
atmosphere tool list           # List available tools
atmosphere tool info NAME      # Show tool details
atmosphere tool run NAME       # Execute tool

# Model deployment (optional)
atmosphere model list          # List available models
atmosphere model deploy        # Deploy model to mesh
atmosphere model pull          # Pull model from mesh
```

### Planned Future Commands

```bash
# Cost estimation
atmosphere cost estimate "intent"   # Estimate cost before running

# Mesh discovery
atmosphere scan                     # Scan for nearby nodes
atmosphere approve NODE_ID          # Approve pending join request

# Web UI
atmosphere ui                       # Open web dashboard in browser
```

---

## Package Contents (Installed Layout)

### pip install

```
site-packages/
└── atmosphere/
    ├── __init__.py
    ├── cli.py
    ├── config.py
    ├── py.typed
    ├── api/
    ├── agents/
    ├── auth/
    ├── capabilities/
    ├── deployment/
    ├── discovery/
    ├── mesh/
    ├── network/
    ├── router/
    ├── tools/
    └── ui/
        └── dist/           # Bundled React app
            ├── index.html
            └── assets/

# Entry point script
bin/atmosphere → atmosphere.cli:main
```

### Homebrew install

```
/opt/homebrew/
├── bin/
│   └── atmosphere           # CLI entry point
├── Cellar/atmosphere/1.0.0/
│   └── libexec/
│       ├── bin/
│       │   └── python3      # Virtual env Python
│       └── lib/python3.12/
│           └── site-packages/
│               └── atmosphere/
├── var/
│   ├── atmosphere/          # Data directory
│   └── log/atmosphere/      # Log files
└── etc/bash_completion.d/
    └── atmosphere           # Shell completions
```

### Debian install

```
/usr/
├── bin/
│   └── atmosphere
├── lib/python3/dist-packages/
│   └── atmosphere/
└── share/
    ├── bash-completion/completions/atmosphere
    ├── doc/atmosphere/
    │   ├── README.md
    │   └── changelog.gz
    └── man/man1/atmosphere.1.gz

/var/
├── lib/atmosphere/          # Data directory
└── log/atmosphere/          # Logs

/lib/systemd/system/
└── atmosphere.service
```

---

## Build Process

### Full Release Build

```bash
#!/bin/bash
# scripts/release.sh
set -e

VERSION=${1:-$(python -c "from atmosphere import __version__; print(__version__)")}

echo "🚀 Building Atmosphere v$VERSION"

# 1. Clean previous builds
echo "🧹 Cleaning..."
rm -rf dist/ build/ *.egg-info

# 2. Build UI
echo "🎨 Building UI..."
cd ui
npm ci
npm run build
cd ..

# 3. Copy UI to package
echo "📦 Bundling UI..."
rm -rf atmosphere/ui/dist
cp -r ui/dist atmosphere/ui/

# 4. Build Python package
echo "🐍 Building Python package..."
python -m build

# 5. Verify package
echo "✅ Verifying..."
twine check dist/*

# 6. Run tests
echo "🧪 Running tests..."
pytest tests/ -v

# 7. Test install in clean venv
echo "🔬 Testing install..."
rm -rf .test-venv
python -m venv .test-venv
source .test-venv/bin/activate
pip install dist/atmosphere_mesh-$VERSION-py3-none-any.whl
atmosphere --version
deactivate
rm -rf .test-venv

echo ""
echo "✨ Build complete!"
echo ""
echo "To publish to PyPI:"
echo "  twine upload dist/*"
echo ""
echo "To build Docker:"
echo "  docker build -t llama-farm/atmosphere:$VERSION ."
```

### CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Build UI
        run: |
          cd ui
          npm ci
          npm run build

      - name: Bundle UI
        run: |
          cp -r ui/dist atmosphere/ui/

      - name: Build package
        run: |
          pip install build twine
          python -m build
          twine check dist/*

      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
        run: twine upload dist/*

  docker:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            llama-farm/atmosphere:latest
            llama-farm/atmosphere:${{ github.ref_name }}

  homebrew:
    needs: build
    runs-on: macos-latest
    steps:
      - name: Update Homebrew formula
        env:
          GITHUB_TOKEN: ${{ secrets.TAP_GITHUB_TOKEN }}
        run: |
          VERSION=${{ github.ref_name }}
          VERSION=${VERSION#v}  # Remove 'v' prefix
          
          # Calculate SHA256
          SHA256=$(curl -sL https://files.pythonhosted.org/packages/source/a/atmosphere-mesh/atmosphere-mesh-${VERSION}.tar.gz | shasum -a 256 | cut -d' ' -f1)
          
          # Clone tap
          git clone https://github.com/llama-farm/homebrew-tap.git
          cd homebrew-tap
          
          # Update formula
          sed -i '' "s/version \".*\"/version \"${VERSION}\"/" Formula/atmosphere.rb
          sed -i '' "s/sha256 \".*\"/sha256 \"${SHA256}\"/" Formula/atmosphere.rb
          
          # Commit and push
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git add Formula/atmosphere.rb
          git commit -m "Update atmosphere to ${VERSION}"
          git push
```

---

## Version Management

### Semantic Versioning

```
MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]

1.0.0        - Initial stable release
1.1.0        - New features, backward compatible
1.1.1        - Bug fixes only
2.0.0        - Breaking changes
1.2.0-alpha  - Pre-release
1.2.0-beta.1 - Beta pre-release
```

### Version Bump Script

```bash
#!/bin/bash
# scripts/bump-version.sh

PART=${1:-patch}  # major, minor, patch
CURRENT=$(python -c "from atmosphere import __version__; print(__version__)")

# Calculate new version
IFS='.' read -ra PARTS <<< "$CURRENT"
case $PART in
  major) PARTS[0]=$((PARTS[0]+1)); PARTS[1]=0; PARTS[2]=0 ;;
  minor) PARTS[1]=$((PARTS[1]+1)); PARTS[2]=0 ;;
  patch) PARTS[2]=$((PARTS[2]+1)) ;;
esac
NEW="${PARTS[0]}.${PARTS[1]}.${PARTS[2]}"

echo "Bumping $CURRENT → $NEW"

# Update __init__.py
sed -i '' "s/__version__ = \"$CURRENT\"/__version__ = \"$NEW\"/" atmosphere/__init__.py

# Update pyproject.toml
sed -i '' "s/version = \"$CURRENT\"/version = \"$NEW\"/" pyproject.toml

# Git commit and tag
git add atmosphere/__init__.py pyproject.toml
git commit -m "Bump version to $NEW"
git tag -a "v$NEW" -m "Version $NEW"

echo "Done! Push with: git push && git push --tags"
```

### Changelog Generation

Using `git-cliff`:

```toml
# cliff.toml
[changelog]
header = """
# Changelog\n
All notable changes to Atmosphere.\n
"""
body = """
{% if version %}\
    ## [{{ version | trim_start_matches(pat="v") }}] - {{ timestamp | date(format="%Y-%m-%d") }}
{% else %}\
    ## [unreleased]
{% endif %}\
{% for group, commits in commits | group_by(attribute="group") %}
    ### {{ group | upper_first }}
    {% for commit in commits %}
        - {{ commit.message | upper_first }}\
    {% endfor %}
{% endfor %}\n
"""
trim = true

[git]
conventional_commits = true
filter_unconventional = true
commit_parsers = [
    { message = "^feat", group = "Features" },
    { message = "^fix", group = "Bug Fixes" },
    { message = "^doc", group = "Documentation" },
    { message = "^perf", group = "Performance" },
    { message = "^refactor", group = "Refactor" },
    { message = "^style", group = "Styling" },
    { message = "^test", group = "Testing" },
    { message = "^chore", skip = true },
]
```

---

## Implementation Plan

### Phase 1: PyPI Ready (1-2 hours)

| Task | Effort | Priority |
|------|--------|----------|
| Fix missing httpx dependency | 5 min | 🔴 Critical |
| Update pyproject.toml license format | 5 min | 🔴 Critical |
| Bundle UI into package | 15 min | 🔴 Critical |
| Create MANIFEST.in | 10 min | 🟡 High |
| Test pip install in clean venv | 15 min | 🔴 Critical |
| Reserve `atmosphere-mesh` on PyPI | 10 min | 🟡 High |
| Upload to TestPyPI | 15 min | 🟡 High |
| Upload to PyPI | 5 min | 🟢 Medium |

### Phase 2: Homebrew Formula (2-4 hours)

| Task | Effort | Priority |
|------|--------|----------|
| Create llama-farm/homebrew-tap repo | 15 min | 🟡 High |
| Generate formula resources with poet | 30 min | 🟡 High |
| Test formula locally | 1 hour | 🟡 High |
| Add service definition | 15 min | 🟢 Medium |
| Add shell completions | 15 min | 🟢 Medium |
| Submit to tap | 15 min | 🟡 High |

### Phase 3: Docker Image (1-2 hours)

| Task | Effort | Priority |
|------|--------|----------|
| Create Dockerfile | 30 min | 🟡 High |
| Test multi-stage build | 30 min | 🟡 High |
| Set up Docker Hub repo | 15 min | 🟡 High |
| Create docker-compose.yml | 15 min | 🟢 Medium |
| Build for arm64/amd64 | 30 min | 🟢 Medium |

### Phase 4: Debian Package (4-6 hours)

| Task | Effort | Priority |
|------|--------|----------|
| Create debian/ directory structure | 1 hour | 🟢 Medium |
| Test local dpkg build | 1 hour | 🟢 Medium |
| Set up PPA or apt repo | 2 hours | 🟢 Medium |
| Test on Ubuntu/Debian | 1 hour | 🟢 Medium |

### Phase 5: CI/CD (2-3 hours)

| Task | Effort | Priority |
|------|--------|----------|
| GitHub Actions workflow | 1 hour | 🟡 High |
| Automated version bumping | 30 min | 🟢 Medium |
| Changelog automation | 30 min | 🟢 Medium |
| Multi-platform Docker builds | 30 min | 🟢 Medium |

---

## Quick Fixes Required

Before packaging works correctly, fix these issues:

### 1. Add missing httpx dependency

```bash
# In pyproject.toml, add to dependencies:
"httpx>=0.26.0",
```

### 2. Update license format

```bash
# In pyproject.toml, change:
license = {text = "MIT"}
# To:
license = "MIT"
```

### 3. Create UI bundle script

```bash
#!/bin/bash
# scripts/bundle-ui.sh
cd ui
npm ci
npm run build
cd ..
rm -rf atmosphere/ui/dist
mkdir -p atmosphere/ui
cp -r ui/dist atmosphere/ui/
echo "UI bundled to atmosphere/ui/dist/"
```

### 4. Test CLI works

```bash
# After fixes, test:
rm -rf test_venv
python3 -m venv test_venv
source test_venv/bin/activate
pip install dist/atmosphere-1.0.0-py3-none-any.whl
atmosphere --help
atmosphere init
atmosphere status
```

---

## Appendix: Alternative Package Names

If `atmosphere-mesh` is taken on PyPI, alternatives:

| Name | Available? | Notes |
|------|------------|-------|
| atmosphere-mesh | ⏳ Check | Preferred |
| atmosphere-ai | ⏳ Check | Alternative |
| atmos-mesh | ⏳ Check | Shorter |
| intent-mesh | ⏳ Check | Descriptive |
| llama-atmosphere | ⏳ Check | Brand aligned |

Check availability:
```bash
pip index versions atmosphere-mesh
# If 404, it's available
```
