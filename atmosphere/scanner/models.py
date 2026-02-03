"""
Model Detection Module

Detects AI models: Ollama, HuggingFace cache, GGUF files, LlamaFarm.
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about a detected model."""
    name: str
    source: str  # "ollama", "huggingface", "gguf", "llamafarm"
    size_bytes: int = 0
    family: Optional[str] = None
    parameter_size: Optional[str] = None
    quantization: Optional[str] = None
    path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "size_bytes": self.size_bytes,
            "size_human": _format_size(self.size_bytes),
            "family": self.family,
            "parameter_size": self.parameter_size,
            "quantization": self.quantization,
            "path": self.path,
        }


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    if size_bytes == 0:
        return "0B"
    
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}PB"


async def detect_models(
    ollama_host: str = "localhost",
    ollama_port: int = 11434,
    llamafarm_host: str = "localhost", 
    llamafarm_port: int = 14345,
    scan_huggingface: bool = True,
    scan_gguf: bool = False,
) -> Dict[str, List[ModelInfo]]:
    """
    Detect all available models from various sources.
    
    Returns dict with keys: "ollama", "huggingface", "gguf", "llamafarm"
    """
    results = {
        "ollama": [],
        "huggingface": [],
        "gguf": [],
        "llamafarm": [],
    }
    
    # Detect Ollama models
    try:
        results["ollama"] = await detect_ollama_models(ollama_host, ollama_port)
    except Exception as e:
        logger.warning(f"Ollama model detection failed: {e}")
    
    # Detect LlamaFarm models
    try:
        results["llamafarm"] = await detect_llamafarm_models(llamafarm_host, llamafarm_port)
    except Exception as e:
        logger.debug(f"LlamaFarm model detection failed: {e}")
    
    # Detect HuggingFace cache (local, no permissions needed)
    if scan_huggingface:
        try:
            results["huggingface"] = detect_huggingface_models()
        except Exception as e:
            logger.warning(f"HuggingFace model detection failed: {e}")
    
    # GGUF scanning is opt-in (can be slow)
    if scan_gguf:
        try:
            results["gguf"] = detect_gguf_files()
        except Exception as e:
            logger.warning(f"GGUF detection failed: {e}")
    
    return results


async def detect_ollama_models(
    host: str = "localhost",
    port: int = 11434,
    timeout: float = 5.0
) -> List[ModelInfo]:
    """
    Detect models available in Ollama.
    
    Queries the Ollama API at /api/tags.
    """
    models = []
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"http://{host}:{port}/api/tags")
            
            if response.status_code != 200:
                logger.warning(f"Ollama returned status {response.status_code}")
                return []
            
            data = response.json()
            
            for model in data.get("models", []):
                details = model.get("details", {})
                
                models.append(ModelInfo(
                    name=model.get("name", "unknown"),
                    source="ollama",
                    size_bytes=model.get("size", 0),
                    family=details.get("family"),
                    parameter_size=details.get("parameter_size"),
                    quantization=details.get("quantization_level"),
                ))
            
            return models
            
    except httpx.ConnectError:
        logger.debug(f"Cannot connect to Ollama at {host}:{port}")
        return []
    except httpx.TimeoutException:
        logger.warning(f"Ollama request timed out")
        return []
    except Exception as e:
        logger.warning(f"Ollama detection error: {e}")
        return []


async def detect_llamafarm_models(
    host: str = "localhost",
    port: int = 14345,
    timeout: float = 5.0
) -> List[ModelInfo]:
    """
    Detect models available via LlamaFarm.
    
    Queries the LlamaFarm API.
    """
    models = []
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Try v1 models endpoint
            response = await client.get(f"http://{host}:{port}/v1/models")
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            
            for model in data.get("data", []):
                models.append(ModelInfo(
                    name=model.get("id", "unknown"),
                    source="llamafarm",
                ))
            
            return models
            
    except httpx.ConnectError:
        return []
    except Exception as e:
        logger.debug(f"LlamaFarm detection error: {e}")
        return []


def detect_huggingface_models(
    cache_dir: Optional[Path] = None
) -> List[ModelInfo]:
    """
    Detect models in the HuggingFace cache directory.
    
    Does not require any permissions - just reads filesystem.
    """
    if cache_dir is None:
        # Check environment variable first
        hf_home = os.environ.get("HF_HOME")
        if hf_home:
            cache_dir = Path(hf_home) / "hub"
        else:
            cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    
    if not cache_dir.exists():
        return []
    
    models = []
    
    try:
        for entry in cache_dir.iterdir():
            if not entry.is_dir():
                continue
            
            name = entry.name
            
            # Parse directory name: models--org--name
            if name.startswith("models--"):
                parts = name.split("--")[1:]
                if len(parts) >= 2:
                    repo_id = "/".join(parts)
                elif parts:
                    repo_id = parts[0]
                else:
                    continue
                
                # Find snapshots and calculate size
                snapshots_dir = entry / "snapshots"
                if snapshots_dir.exists():
                    total_size = 0
                    
                    for snapshot in snapshots_dir.iterdir():
                        if snapshot.is_dir():
                            try:
                                for f in snapshot.rglob("*"):
                                    if f.is_file():
                                        total_size += f.stat().st_size
                            except (PermissionError, OSError):
                                pass
                    
                    if total_size > 0:
                        models.append(ModelInfo(
                            name=repo_id,
                            source="huggingface",
                            size_bytes=total_size,
                            path=str(entry),
                        ))
        
        return models
        
    except PermissionError:
        logger.warning(f"Permission denied reading HuggingFace cache")
        return []
    except Exception as e:
        logger.warning(f"HuggingFace cache scan error: {e}")
        return []


def detect_gguf_files(
    search_paths: Optional[List[Path]] = None,
    max_depth: int = 3
) -> List[ModelInfo]:
    """
    Find GGUF model files on disk.
    
    Note: This can be slow for deep directory structures.
    Only searches in safe default paths unless explicitly configured.
    """
    if search_paths is None:
        # Only search reasonable default paths
        search_paths = [
            Path.home() / "models",
            Path.home() / ".ollama" / "models",
            Path.home() / ".cache" / "lm-studio",
        ]
    
    models = []
    
    for search_path in search_paths:
        if not search_path.exists():
            continue
        
        # Validate path is under home directory (security)
        try:
            search_path.resolve().relative_to(Path.home())
        except ValueError:
            logger.warning(f"Skipping GGUF search path outside home: {search_path}")
            continue
        
        try:
            # Use Python's pathlib for safe iteration
            for gguf_file in _find_gguf_files(search_path, max_depth):
                name = gguf_file.stem
                
                # Extract quantization from filename
                quantization = _extract_quantization(name)
                
                models.append(ModelInfo(
                    name=name,
                    source="gguf",
                    size_bytes=gguf_file.stat().st_size,
                    quantization=quantization,
                    path=str(gguf_file),
                ))
                
        except PermissionError:
            logger.debug(f"Permission denied: {search_path}")
        except Exception as e:
            logger.warning(f"GGUF search error in {search_path}: {e}")
    
    return models


def _find_gguf_files(path: Path, max_depth: int, current_depth: int = 0) -> List[Path]:
    """Recursively find GGUF files up to max_depth."""
    files = []
    
    if current_depth > max_depth:
        return files
    
    try:
        for entry in path.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".gguf":
                files.append(entry)
            elif entry.is_dir() and current_depth < max_depth:
                files.extend(_find_gguf_files(entry, max_depth, current_depth + 1))
    except PermissionError:
        pass
    
    return files


def _extract_quantization(name: str) -> Optional[str]:
    """Extract quantization level from model filename."""
    name_upper = name.upper()
    
    # Common quantization patterns
    quants = [
        "Q8_0", "Q6_K", "Q5_K_M", "Q5_K_S", "Q5_0", 
        "Q4_K_M", "Q4_K_S", "Q4_0", "Q3_K_M", "Q3_K_S",
        "Q2_K", "IQ4_XS", "IQ3_XS", "IQ2_XS",
        "F32", "F16", "BF16"
    ]
    
    for quant in quants:
        if quant in name_upper:
            return quant
    
    return None


def get_models_summary(models: Dict[str, List[ModelInfo]]) -> str:
    """Generate a human-readable summary of detected models."""
    lines = []
    
    # Ollama
    ollama_models = models.get("ollama", [])
    if ollama_models:
        lines.append(f"Ollama ({len(ollama_models)} models):")
        for m in sorted(ollama_models, key=lambda x: x.size_bytes, reverse=True)[:5]:
            size = _format_size(m.size_bytes)
            lines.append(f"  • {m.name} ({size})")
        if len(ollama_models) > 5:
            lines.append(f"  ... and {len(ollama_models) - 5} more")
    
    # LlamaFarm
    llamafarm_models = models.get("llamafarm", [])
    if llamafarm_models:
        lines.append(f"\nLlamaFarm ({len(llamafarm_models)} models):")
        for m in llamafarm_models[:5]:
            lines.append(f"  • {m.name}")
    
    # HuggingFace
    hf_models = models.get("huggingface", [])
    if hf_models:
        total_size = sum(m.size_bytes for m in hf_models)
        lines.append(f"\nHuggingFace Cache ({len(hf_models)} models, {_format_size(total_size)} total):")
        for m in sorted(hf_models, key=lambda x: x.size_bytes, reverse=True)[:3]:
            size = _format_size(m.size_bytes)
            lines.append(f"  • {m.name} ({size})")
        if len(hf_models) > 3:
            lines.append(f"  ... and {len(hf_models) - 3} more")
    
    # GGUF
    gguf_models = models.get("gguf", [])
    if gguf_models:
        lines.append(f"\nGGUF Files ({len(gguf_models)} models):")
        for m in gguf_models[:3]:
            size = _format_size(m.size_bytes)
            lines.append(f"  • {m.name} ({size})")
    
    if not lines:
        return "No models detected"
    
    return "\n".join(lines)
