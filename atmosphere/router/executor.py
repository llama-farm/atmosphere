"""
Execution engine for routing decisions.

Executes capabilities locally or forwards to remote nodes.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp

from .semantic import SemanticRouter, RouteResult, RouteAction
from ..discovery.ollama import OllamaBackend, OllamaConfig
from ..discovery.llamafarm import LlamaFarmBackend, LlamaFarmConfig

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of capability execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0
    node_id: Optional[str] = None
    hops: int = 0
    capability: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "node_id": self.node_id,
            "hops": self.hops,
            "capability": self.capability
        }


class Executor:
    """
    Executes routing decisions.
    
    Handles both local execution and forwarding to remote nodes.
    
    Usage:
        executor = Executor(router, node_id="my-node")
        
        # Execute an intent
        result = await executor.execute("summarize this document", document=doc)
        
        # Direct execute with a specific capability
        result = await executor.execute_capability("llm", prompt="Hello!")
    """

    def __init__(
        self,
        router: SemanticRouter,
        node_id: str,
        port: int = 11434
    ):
        self.router = router
        self.node_id = node_id
        self.port = port
        
        # Backends
        self._ollama: Optional[OllamaBackend] = None
        self._llamafarm: Optional[LlamaFarmBackend] = None
        
        # Peer connections
        self._peer_sessions: Dict[str, aiohttp.ClientSession] = {}
        
        # Execution handlers
        self._handlers: Dict[str, callable] = {}
    
    async def initialize(self) -> None:
        """Initialize execution backends."""
        # Try Ollama
        self._ollama = OllamaBackend()
        if not await self._ollama.health_check():
            self._ollama = None
        
        # Try LlamaFarm
        self._llamafarm = LlamaFarmBackend()
        if not await self._llamafarm.health_check():
            self._llamafarm = None
        
        logger.info(
            f"Executor initialized: ollama={self._ollama is not None}, "
            f"llamafarm={self._llamafarm is not None}"
        )
    
    async def close(self) -> None:
        """Close all connections."""
        if self._ollama:
            await self._ollama.close()
        if self._llamafarm:
            await self._llamafarm.close()
        
        for session in self._peer_sessions.values():
            if not session.closed:
                await session.close()
    
    def register_handler(self, capability: str, handler: callable) -> None:
        """Register a custom handler for a capability."""
        self._handlers[capability] = handler
    
    async def execute(
        self,
        intent: str,
        **kwargs
    ) -> ExecutionResult:
        """
        Execute an intent, routing to the best capability.
        
        Args:
            intent: What to do
            **kwargs: Arguments for the capability
            
        Returns:
            ExecutionResult with the result
        """
        start_time = time.time()
        
        # Route the intent
        route = await self.router.route(intent)
        
        if route.action == RouteAction.NO_MATCH:
            return ExecutionResult(
                success=False,
                error=f"No capability found for: {intent}",
                execution_time_ms=(time.time() - start_time) * 1000
            )
        
        if route.action == RouteAction.PROCESS_LOCAL:
            result = await self._execute_local(route, intent, **kwargs)
        else:
            result = await self._execute_remote(route, intent, **kwargs)
        
        result.execution_time_ms = (time.time() - start_time) * 1000
        return result
    
    async def execute_capability(
        self,
        capability: str,
        **kwargs
    ) -> ExecutionResult:
        """
        Execute a specific capability directly.
        
        Args:
            capability: Capability label (e.g., "llm", "embeddings")
            **kwargs: Arguments for the capability
            
        Returns:
            ExecutionResult
        """
        start_time = time.time()
        
        # Check for custom handler
        if capability in self._handlers:
            try:
                result = await self._handlers[capability](**kwargs)
                return ExecutionResult(
                    success=True,
                    data=result,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    node_id=self.node_id,
                    capability=capability
                )
            except Exception as e:
                return ExecutionResult(
                    success=False,
                    error=str(e),
                    execution_time_ms=(time.time() - start_time) * 1000
                )
        
        # Built-in capabilities
        if capability == "llm":
            return await self._execute_llm(**kwargs)
        elif capability == "embeddings":
            return await self._execute_embeddings(**kwargs)
        elif capability == "chat":
            return await self._execute_chat(**kwargs)
        elif capability == "anomaly_detection":
            return await self._execute_anomaly_detection(**kwargs)
        elif capability == "classification":
            return await self._execute_classification(**kwargs)
        
        return ExecutionResult(
            success=False,
            error=f"Unknown capability: {capability}",
            execution_time_ms=(time.time() - start_time) * 1000
        )
    
    async def _execute_local(
        self,
        route: RouteResult,
        intent: str,
        **kwargs
    ) -> ExecutionResult:
        """Execute locally using the matched capability."""
        cap = route.capability
        if not cap:
            return ExecutionResult(success=False, error="No capability in route")
        
        logger.debug(f"Executing locally: {cap.label}")
        
        # Dispatch based on capability label
        if cap.label in ["llm", "language model", "text generation"]:
            return await self._execute_llm(prompt=kwargs.get("prompt", intent), **kwargs)
        
        elif cap.label in ["embeddings", "text embeddings"]:
            return await self._execute_embeddings(
                text=kwargs.get("text", intent), **kwargs
            )
        
        elif cap.label in ["chat", "conversation"]:
            return await self._execute_chat(
                messages=kwargs.get("messages", [{"role": "user", "content": intent}]),
                **kwargs
            )
        
        elif cap.label in ["vision", "image analysis"]:
            return await self._execute_vision(**kwargs)
        
        elif cap.label in ["anomaly detection", "outlier detection", "anomaly"]:
            return await self._execute_anomaly_detection(**kwargs)
        
        elif cap.label in ["classification", "classifier", "categorize"]:
            return await self._execute_classification(**kwargs)
        
        # Try custom handler
        if cap.handler in self._handlers:
            try:
                result = await self._handlers[cap.handler](intent=intent, **kwargs)
                return ExecutionResult(
                    success=True,
                    data=result,
                    node_id=self.node_id,
                    capability=cap.label
                )
            except Exception as e:
                return ExecutionResult(success=False, error=str(e))
        
        return ExecutionResult(
            success=False,
            error=f"No handler for capability: {cap.label}",
            node_id=self.node_id
        )
    
    async def _execute_remote(
        self,
        route: RouteResult,
        intent: str,
        **kwargs
    ) -> ExecutionResult:
        """Forward execution to a remote node."""
        if not route.next_hop:
            return ExecutionResult(success=False, error="No next hop in route")
        
        logger.debug(f"Forwarding to {route.next_hop}")
        
        # Get or create session for peer
        session = await self._get_peer_session(route.next_hop)
        
        try:
            payload = {
                "intent": intent,
                "kwargs": kwargs,
                "origin": self.node_id,
                "hops": route.hops
            }
            
            async with session.post(
                f"http://{route.next_hop}/v1/execute",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120.0)
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return ExecutionResult(success=False, error=f"Remote error: {error}")
                
                data = await resp.json()
                return ExecutionResult(
                    success=data.get("success", False),
                    data=data.get("data"),
                    error=data.get("error"),
                    node_id=route.via_node,
                    hops=route.hops,
                    capability=data.get("capability")
                )
                
        except aiohttp.ClientError as e:
            return ExecutionResult(
                success=False,
                error=f"Connection failed: {e}"
            )
    
    async def _get_peer_session(self, peer: str) -> aiohttp.ClientSession:
        """Get or create a session for a peer."""
        if peer not in self._peer_sessions or self._peer_sessions[peer].closed:
            self._peer_sessions[peer] = aiohttp.ClientSession()
        return self._peer_sessions[peer]
    
    async def _execute_llm(self, **kwargs) -> ExecutionResult:
        """Execute LLM generation."""
        prompt = kwargs.get("prompt", "")
        model = kwargs.get("model")
        
        # Try LlamaFarm first (more advanced)
        if self._llamafarm:
            try:
                result = await self._llamafarm.generate(prompt, model=model or "default")
                return ExecutionResult(
                    success=True,
                    data=result,
                    node_id=self.node_id,
                    capability="llm"
                )
            except Exception as e:
                logger.warning(f"LlamaFarm generation failed: {e}, trying Ollama")
        
        # Fallback to Ollama
        if self._ollama:
            try:
                result = await self._ollama.generate(prompt, model=model)
                return ExecutionResult(
                    success=True,
                    data=result,
                    node_id=self.node_id,
                    capability="llm"
                )
            except Exception as e:
                return ExecutionResult(success=False, error=str(e))
        
        return ExecutionResult(success=False, error="No LLM backend available")
    
    async def _execute_chat(self, **kwargs) -> ExecutionResult:
        """Execute chat completion."""
        messages = kwargs.get("messages", [])
        model = kwargs.get("model")
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens")
        
        # Try LlamaFarm first (more advanced, 26 models)
        if self._llamafarm:
            try:
                result = await self._llamafarm.chat(
                    messages, 
                    model=model or "default",
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return ExecutionResult(
                    success=True,
                    data=result,
                    node_id=self.node_id,
                    capability="chat"
                )
            except Exception as e:
                logger.warning(f"LlamaFarm chat failed: {e}, trying Ollama")
        
        # Fallback to Ollama
        if self._ollama:
            try:
                result = await self._ollama.chat(messages, model=model)
                return ExecutionResult(
                    success=True,
                    data=result,
                    node_id=self.node_id,
                    capability="chat"
                )
            except Exception as e:
                return ExecutionResult(success=False, error=str(e))
        
        return ExecutionResult(success=False, error="No chat backend available")
    
    async def _execute_embeddings(self, **kwargs) -> ExecutionResult:
        """Execute embedding generation."""
        text = kwargs.get("text", "")
        model = kwargs.get("model")
        
        # Try LlamaFarm first
        if self._llamafarm:
            try:
                result = await self._llamafarm.embed(text, model=model or "default")
                return ExecutionResult(
                    success=True,
                    data=result,
                    node_id=self.node_id,
                    capability="embeddings"
                )
            except Exception as e:
                logger.warning(f"LlamaFarm embeddings failed: {e}, trying Ollama")
        
        # Fallback to Ollama
        if self._ollama:
            try:
                result = await self._ollama.embed(text, model=model)
                return ExecutionResult(
                    success=True,
                    data=result,
                    node_id=self.node_id,
                    capability="embeddings"
                )
            except Exception as e:
                return ExecutionResult(success=False, error=str(e))
        
        return ExecutionResult(success=False, error="No embedding backend available")
    
    async def _execute_vision(self, **kwargs) -> ExecutionResult:
        """Execute vision analysis."""
        image = kwargs.get("image")
        prompt = kwargs.get("prompt", "Describe this image")
        
        if self._llamafarm:
            try:
                result = await self._llamafarm.vision_analyze(image, prompt)
                return ExecutionResult(
                    success=True,
                    data=result,
                    node_id=self.node_id,
                    capability="vision"
                )
            except Exception as e:
                return ExecutionResult(success=False, error=str(e))
        
        return ExecutionResult(success=False, error="No vision backend available")
    
    async def _execute_anomaly_detection(self, **kwargs) -> ExecutionResult:
        """Execute anomaly detection."""
        model = kwargs.get("model", "default")
        data = kwargs.get("data", [])
        action = kwargs.get("action", "detect")  # detect, fit, score
        
        if not self._llamafarm:
            return ExecutionResult(success=False, error="No anomaly detection backend available")
        
        try:
            from ..adapters.llamafarm import LlamaFarmExecutor
            executor = LlamaFarmExecutor(self._llamafarm.config.base_url)
            
            if action == "detect":
                result = await executor.detect_anomaly(model, data)
            elif action == "fit":
                result = await executor.fit_anomaly_detector(model, data, **kwargs)
            elif action == "score":
                result = await executor.score_anomaly(model, data)
            elif action == "list":
                result = await executor.list_anomaly_models()
            else:
                return ExecutionResult(
                    success=False,
                    error=f"Unknown anomaly detection action: {action}"
                )
            
            await executor.close()
            
            return ExecutionResult(
                success=True,
                data=result,
                node_id=self.node_id,
                capability="anomaly_detection"
            )
        except Exception as e:
            logger.error(f"Anomaly detection failed: {e}")
            return ExecutionResult(success=False, error=str(e))
    
    async def _execute_classification(self, **kwargs) -> ExecutionResult:
        """Execute classification."""
        model = kwargs.get("model", "default")
        data = kwargs.get("data", [])
        action = kwargs.get("action", "predict")  # predict, fit, list
        
        if not self._llamafarm:
            return ExecutionResult(success=False, error="No classification backend available")
        
        try:
            from ..adapters.llamafarm import LlamaFarmExecutor
            executor = LlamaFarmExecutor(self._llamafarm.config.base_url)
            
            if action == "predict":
                result = await executor.classify(model, data)
            elif action == "fit":
                X = kwargs.get("X", data)
                y = kwargs.get("y", [])
                result = await executor.fit_classifier(model, X, y, **kwargs)
            elif action == "list":
                result = await executor.list_classifiers()
            else:
                return ExecutionResult(
                    success=False,
                    error=f"Unknown classification action: {action}"
                )
            
            await executor.close()
            
            return ExecutionResult(
                success=True,
                data=result,
                node_id=self.node_id,
                capability="classification"
            )
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return ExecutionResult(success=False, error=str(e))
