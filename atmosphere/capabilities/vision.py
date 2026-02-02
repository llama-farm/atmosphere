"""
Vision capability handler.
"""

import logging
from typing import Any, Dict, Optional

from .base import CapabilityHandler
from ..discovery.llamafarm import LlamaFarmBackend, LlamaFarmConfig

logger = logging.getLogger(__name__)


class VisionCapability(CapabilityHandler):
    """
    Vision capability for image and video analysis.
    
    Supports:
    - Image description
    - Object detection
    - Scene understanding
    - OCR / text extraction
    - Visual Q&A
    """
    
    def __init__(self, config: Optional[LlamaFarmConfig] = None):
        self._config = config or LlamaFarmConfig()
        self._backend: Optional[LlamaFarmBackend] = None
    
    @property
    def capability_type(self) -> str:
        return "vision"
    
    @property
    def description(self) -> str:
        return (
            "Vision model for image analysis, object detection, scene understanding, "
            "visual question answering, and image description"
        )
    
    async def _get_backend(self) -> LlamaFarmBackend:
        if self._backend is None:
            self._backend = LlamaFarmBackend(self._config)
        return self._backend
    
    async def health_check(self) -> bool:
        try:
            backend = await self._get_backend()
            return await backend.health_check()
        except Exception:
            return False
    
    async def execute(self, **kwargs) -> Any:
        """
        Execute vision capability.
        
        Supported kwargs:
        - image: Image URL or base64 data
        - prompt: Question or instruction about the image
        - model: Model to use
        """
        backend = await self._get_backend()
        
        image = kwargs.get("image")
        if not image:
            raise ValueError("'image' is required")
        
        prompt = kwargs.get("prompt", "Describe this image in detail")
        model = kwargs.get("model", "default")
        
        return await backend.vision_analyze(
            image_url=image,
            prompt=prompt,
            model=model
        )
    
    async def close(self) -> None:
        if self._backend:
            await self._backend.close()
