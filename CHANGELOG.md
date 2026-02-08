# Changelog

All notable changes to Atmosphere will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-02-03

### Added
- Initial release of Atmosphere mesh routing platform
- Semantic intent routing with sub-millisecond latency
- Zero-config mesh networking with mDNS discovery
- Bidirectional capabilities (triggers + tools)
- OpenAI-compatible API endpoint (`/v1/chat/completions`)
- LlamaFarm integration with automatic project discovery
- Ollama integration for local model routing
- FastAPI-based REST API server
- WebSocket support for real-time mesh updates
- CLI tool (`atmosphere`) for node management
- macOS menu bar app (`atmosphere-app`)
- Multi-tier semantic routing (embedding → hash → keyword)
- Cost-aware routing based on node resources
- Ed25519 cryptographic identity for nodes
- Mesh membership with founder approval workflow
- Agent framework with stateful execution
- Tool execution system for remote capability invocation
- Trigger routing for event-driven workflows
- Python package distribution (`atmosphere-mesh`)
- Homebrew formula for macOS installation
- Comprehensive API documentation
- Installation guide

### Core Endpoints
- `POST /v1/chat/completions` - OpenAI-compatible chat
- `GET /api/capabilities` - List available capabilities
- `POST /api/execute` - Execute an intent
- `GET /api/mesh/status` - Mesh network status
- `WebSocket /api/ws` - Real-time updates
- `POST /route` - Route intent to capability
- `POST /route/project` - Route to LlamaFarm project

### Integrations
- LlamaFarm (http://localhost:14345)
- Ollama (http://localhost:11434)
- OpenAI API compatibility

### Platform Support
- macOS 10.14+
- Linux (Ubuntu 20.04+, Debian 11+)
- Windows 10+ (experimental)
- Python 3.10, 3.11, 3.12, 3.13

### Dependencies
- FastAPI >= 0.109.0
- uvicorn >= 0.25.0
- aiohttp >= 3.9.0
- pydantic >= 2.0.0
- cryptography >= 41.0.0
- zeroconf >= 0.131.0
- rumps >= 0.4.0 (macOS only)

## [Unreleased]

### Planned Features
- Web UI dashboard (React + D3.js visualizations)
- Mobile app (iOS/Android) for mesh monitoring
- Model deployment and synchronization
- Organic learning loops (edge → cloud)
- BLE and LoRa transport support
- QUIC for improved mesh connectivity
- Advanced routing strategies (A/B testing, canary)
- Capability marketplace
- Mesh federation (cross-organization)
- Enhanced security (capability-level permissions)
- Windows installer (MSI)
- Debian/Ubuntu packages (apt)
- Docker images
- Kubernetes operator

---

[1.0.0]: https://github.com/llama-farm/atmosphere/releases/tag/v1.0.0
