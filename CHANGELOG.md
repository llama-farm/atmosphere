# Changelog

All notable changes to Atmosphere will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2024-02-02

### Added
- Initial release of Atmosphere mesh networking
- Semantic routing for AI capabilities
- Automatic discovery of Ollama and LlamaFarm backends
- mDNS mesh discovery for local networks
- NAT traversal with STUN/TURN for internet connectivity
- CLI tool with commands: `init`, `serve`, `status`, `mesh`, `agent`, `tool`, `model`, `network`
- FastAPI-based REST API server
- WebSocket support for real-time mesh communication
- Authentication and identity management
- Capability registry for LLM, embeddings, vision
- Tool execution framework
- Model deployment and distribution system
- Docker support with multi-stage build
- Homebrew formula for macOS

### Dependencies
- aiohttp >= 3.9.0
- cryptography >= 41.0.0
- fastapi >= 0.109.0
- uvicorn >= 0.25.0
- numpy >= 1.24.0
- click >= 8.0.0
- rich >= 13.0.0
- zeroconf >= 0.131.0
- pydantic >= 2.0.0
- psutil >= 5.9.0
- httpx >= 0.26.0
- PyYAML >= 6.0

[Unreleased]: https://github.com/llama-farm/atmosphere/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/llama-farm/atmosphere/releases/tag/v1.0.0
