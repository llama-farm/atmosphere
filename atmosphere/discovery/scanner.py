"""
Backend scanner for discovering AI services.

Scans the local system for available AI backends and their capabilities.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

import aiohttp

logger = logging.getLogger(__name__)


class BackendType(Enum):
    """Types of AI backends."""
    OLLAMA = "ollama"
    LLAMAFARM = "llamafarm"
    VLLM = "vllm"
    OPENAI = "openai"
    CUSTOM = "custom"


@dataclass
class ModelInfo:
    """Information about an available model."""
    name: str
    family: str = ""
    size: str = ""
    quantization: str = ""
    capabilities: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    def supports_capability(self, capability: str) -> bool:
        """Check if model supports a capability."""
        return capability in self.capabilities


@dataclass
class BackendInfo:
    """Information about a discovered backend."""
    type: BackendType
    host: str
    port: int
    healthy: bool = False
    version: str = ""
    models: List[ModelInfo] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
    
    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "host": self.host,
            "port": self.port,
            "healthy": self.healthy,
            "version": self.version,
            "models": [
                {
                    "name": m.name,
                    "family": m.family,
                    "capabilities": m.capabilities
                }
                for m in self.models
            ],
            "capabilities": self.capabilities,
            "metadata": self.metadata
        }


class Scanner:
    """
    Scans for available AI backends.
    
    Usage:
        scanner = Scanner()
        backends = await scanner.scan()
        
        for backend in backends:
            print(f"{backend.type}: {len(backend.models)} models")
    """
    
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session
    
    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def scan_ollama(
        self,
        host: str = "localhost",
        port: int = 11434
    ) -> Optional[BackendInfo]:
        """Scan for Ollama backend."""
        backend = BackendInfo(
            type=BackendType.OLLAMA,
            host=host,
            port=port
        )
        
        session = await self._get_session()
        
        try:
            # Check health
            async with session.get(f"{backend.url}/api/tags") as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                backend.healthy = True
                
                # Parse models
                for model_data in data.get("models", []):
                    name = model_data.get("name", "")
                    details = model_data.get("details", {})
                    
                    # Determine capabilities from model name/family
                    capabilities = ["llm"]
                    family = details.get("family", "")
                    
                    if "embed" in name.lower() or "nomic" in name.lower():
                        capabilities = ["embeddings"]
                    elif "vision" in name.lower() or "llava" in name.lower():
                        capabilities.append("vision")
                    elif "code" in name.lower():
                        capabilities.append("code")
                    
                    model = ModelInfo(
                        name=name,
                        family=family,
                        size=details.get("parameter_size", ""),
                        quantization=details.get("quantization_level", ""),
                        capabilities=capabilities,
                        parameters=details
                    )
                    backend.models.append(model)
                
                # Aggregate capabilities
                all_caps = set()
                for model in backend.models:
                    all_caps.update(model.capabilities)
                backend.capabilities = list(all_caps)
                
                logger.info(f"Ollama found: {len(backend.models)} models")
                return backend
                
        except aiohttp.ClientError as e:
            logger.debug(f"Ollama not available at {host}:{port}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Error scanning Ollama: {e}")
            return None
    
    async def scan_llamafarm(
        self,
        host: str = "localhost",
        port: int = 8000
    ) -> Optional[BackendInfo]:
        """Scan for LlamaFarm backend."""
        backend = BackendInfo(
            type=BackendType.LLAMAFARM,
            host=host,
            port=port
        )
        
        session = await self._get_session()
        
        try:
            # Check health
            async with session.get(f"{backend.url}/health") as resp:
                if resp.status != 200:
                    return None
                
                backend.healthy = True
            
            # Get info
            async with session.get(f"{backend.url}/info") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    backend.version = data.get("version", "")
                    backend.metadata["data_directory"] = data.get("data_directory")
            
            # Get models/capabilities
            async with session.get(f"{backend.url}/v1/models") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for model_data in data.get("data", []):
                        model = ModelInfo(
                            name=model_data.get("id", ""),
                            capabilities=model_data.get("capabilities", ["llm"])
                        )
                        backend.models.append(model)
            
            # Standard LlamaFarm capabilities
            backend.capabilities = ["llm", "embeddings", "vision", "rag", "agents"]
            
            logger.info(f"LlamaFarm found at {host}:{port}")
            return backend
            
        except aiohttp.ClientError as e:
            logger.debug(f"LlamaFarm not available at {host}:{port}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Error scanning LlamaFarm: {e}")
            return None
    
    async def scan_vllm(
        self,
        host: str = "localhost",
        port: int = 8000
    ) -> Optional[BackendInfo]:
        """Scan for vLLM backend."""
        backend = BackendInfo(
            type=BackendType.VLLM,
            host=host,
            port=port
        )
        
        session = await self._get_session()
        
        try:
            # vLLM uses OpenAI-compatible API
            async with session.get(f"{backend.url}/v1/models") as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                backend.healthy = True
                
                for model_data in data.get("data", []):
                    model = ModelInfo(
                        name=model_data.get("id", ""),
                        capabilities=["llm"]
                    )
                    backend.models.append(model)
                
                backend.capabilities = ["llm"]
                logger.info(f"vLLM found at {host}:{port}")
                return backend
                
        except aiohttp.ClientError as e:
            logger.debug(f"vLLM not available at {host}:{port}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Error scanning vLLM: {e}")
            return None
    
    async def scan(self) -> List[BackendInfo]:
        """
        Scan for all available backends.
        
        Returns list of discovered and healthy backends.
        """
        backends = []
        
        # Scan common ports in parallel
        results = await asyncio.gather(
            self.scan_ollama(),
            self.scan_llamafarm(),
            self.scan_vllm(port=8000),
            self.scan_vllm(port=8080),
            return_exceptions=True
        )
        
        for result in results:
            if isinstance(result, BackendInfo) and result.healthy:
                backends.append(result)
        
        return backends
    
    async def scan_all_ports(
        self,
        ports: Optional[List[int]] = None
    ) -> List[BackendInfo]:
        """Scan multiple ports for backends."""
        if ports is None:
            ports = [8000, 8080, 11434, 8888]
        
        backends = []
        
        for port in ports:
            # Try each backend type on each port
            for scan_func in [self.scan_ollama, self.scan_llamafarm, self.scan_vllm]:
                try:
                    result = await scan_func(port=port)
                    if result and result.healthy:
                        backends.append(result)
                        break  # Found something on this port
                except Exception:
                    continue
        
        return backends


async def scan_backends() -> List[BackendInfo]:
    """
    Convenience function to scan for backends.
    
    Usage:
        backends = await scan_backends()
        for b in backends:
            print(f"Found {b.type.value} with {len(b.models)} models")
    """
    scanner = Scanner()
    try:
        return await scanner.scan()
    finally:
        await scanner.close()
