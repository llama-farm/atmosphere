# Atmosphere — Python SDK

Python SDK for the [Atmosphere](https://github.com/llama-farm/atmosphere-core) mesh network.

> **Note:** The core mesh engine has moved to Rust (`atmosphere-core`). This Python package wraps the Python bridge and is largely superseded by the Rust daemon + JNI for Android.

## Still Useful For

- **Python scripting** — quick mesh interactions from Python
- **Prototyping** — rapid experimentation with mesh topologies
- **Mac menu bar UI** — the macOS status-bar app lives here

## Installation

```bash
pip install -e .
```

## Usage

```python
import atmosphere
# See examples/ for mesh client usage
```

## Project Structure

```
atmosphere/       # Core Python package
config/           # Configuration files
docs/             # Documentation
examples/         # Usage examples
mac_ui/           # macOS menu bar application
research/         # Research notes
tests/            # Test suite
```

## Related Projects

- [atmosphere-core](https://github.com/llama-farm/atmosphere-core) — Rust mesh engine (9 crates)
- [atmosphere-android](https://github.com/llama-farm/atmosphere-android) — Android client

## License

Apache-2.0
