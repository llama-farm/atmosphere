"""
Tool Executor for Atmosphere Capabilities.

Handles the PULL side of capabilities - executing tools with:
- Parameter validation
- Timeout handling
- Automatic failover to alternative capabilities
- Result caching (optional)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from .registry import (
    CapabilityRegistry, 
    Capability, 
    Tool, 
    CapabilityType,
    get_registry
)

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """Base exception for tool execution errors."""
    pass


class ToolNotFoundError(ExecutionError):
    """Tool not found in capability."""
    pass


class CapabilityNotFoundError(ExecutionError):
    """Capability not found in registry."""
    pass


class CapabilityOfflineError(ExecutionError):
    """Capability is offline."""
    pass


class ValidationError(ExecutionError):
    """Parameter validation failed."""
    pass


class TimeoutError(ExecutionError):
    """Tool execution timed out."""
    pass


class ExecutionStatus(Enum):
    """Status of a tool execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRYING = "retrying"


@dataclass
class ExecutionResult:
    """Result of a tool execution."""
    capability_id: str
    tool_name: str
    status: ExecutionStatus
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    attempts: int = 1
    used_fallback: bool = False
    fallback_capability_id: Optional[str] = None


@dataclass
class ExecutionOptions:
    """Options for tool execution."""
    timeout_ms: int = 30000
    retry_count: int = 2
    retry_delay_ms: int = 1000
    allow_fallback: bool = True
    validate_params: bool = True
    cache_result: bool = False
    cache_ttl_ms: int = 60000


class ToolExecutor:
    """
    Executes tools on capabilities with validation, timeout, and failover.
    
    Usage:
        executor = ToolExecutor(registry)
        result = await executor.call_tool("camera-1", "get_frame", {})
    """
    
    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        self.registry = registry or get_registry()
        self._cache: Dict[str, tuple] = {}  # key -> (result, timestamp)
        self._in_flight: Dict[str, asyncio.Future] = {}
    
    async def call_tool(
        self,
        capability_id: str,
        tool_name: str,
        params: Dict[str, Any],
        options: Optional[ExecutionOptions] = None
    ) -> ExecutionResult:
        """
        Execute a tool on a capability.
        
        Args:
            capability_id: The capability to call
            tool_name: Name of the tool to execute
            params: Parameters for the tool
            options: Execution options (timeout, retry, etc.)
        
        Returns:
            ExecutionResult with status and result/error
        """
        options = options or ExecutionOptions()
        start_time = time.time()
        
        # Check cache
        if options.cache_result:
            cache_key = f"{capability_id}:{tool_name}:{hash(frozenset(params.items()))}"
            cached = self._get_cached(cache_key, options.cache_ttl_ms)
            if cached is not None:
                return ExecutionResult(
                    capability_id=capability_id,
                    tool_name=tool_name,
                    status=ExecutionStatus.SUCCESS,
                    result=cached,
                    duration_ms=0,
                )
        
        # Get capability
        capability = self.registry.get(capability_id)
        if not capability:
            # Try to find an alternative
            if options.allow_fallback:
                alternative = await self._find_alternative(capability_id, tool_name)
                if alternative:
                    logger.info(f"Using fallback capability {alternative.id} for {capability_id}")
                    result = await self._execute_with_retry(
                        alternative, tool_name, params, options
                    )
                    result.used_fallback = True
                    result.fallback_capability_id = alternative.id
                    return result
            
            return ExecutionResult(
                capability_id=capability_id,
                tool_name=tool_name,
                status=ExecutionStatus.FAILED,
                error=f"Capability not found: {capability_id}",
                duration_ms=(time.time() - start_time) * 1000,
            )
        
        # Check if capability is healthy
        if not capability.is_healthy():
            if options.allow_fallback:
                alternative = await self._find_alternative(capability_id, tool_name)
                if alternative:
                    logger.info(f"Capability {capability_id} offline, using {alternative.id}")
                    result = await self._execute_with_retry(
                        alternative, tool_name, params, options
                    )
                    result.used_fallback = True
                    result.fallback_capability_id = alternative.id
                    return result
            
            return ExecutionResult(
                capability_id=capability_id,
                tool_name=tool_name,
                status=ExecutionStatus.FAILED,
                error=f"Capability offline: {capability_id}",
                duration_ms=(time.time() - start_time) * 1000,
            )
        
        # Execute with retry
        result = await self._execute_with_retry(capability, tool_name, params, options)
        
        # Cache successful results
        if result.status == ExecutionStatus.SUCCESS and options.cache_result:
            self._cache[cache_key] = (result.result, time.time())
        
        return result
    
    async def _execute_with_retry(
        self,
        capability: Capability,
        tool_name: str,
        params: Dict[str, Any],
        options: ExecutionOptions
    ) -> ExecutionResult:
        """Execute a tool with retry logic."""
        last_error = None
        attempts = 0
        
        for attempt in range(options.retry_count + 1):
            attempts = attempt + 1
            try:
                result = await self._execute_once(
                    capability, tool_name, params, options
                )
                result.attempts = attempts
                return result
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Tool execution failed (attempt {attempts}): {e}"
                )
                if attempt < options.retry_count:
                    await asyncio.sleep(options.retry_delay_ms / 1000)
        
        return ExecutionResult(
            capability_id=capability.id,
            tool_name=tool_name,
            status=ExecutionStatus.FAILED,
            error=last_error,
            attempts=attempts,
        )
    
    async def _execute_once(
        self,
        capability: Capability,
        tool_name: str,
        params: Dict[str, Any],
        options: ExecutionOptions
    ) -> ExecutionResult:
        """Execute a tool once."""
        start_time = time.time()
        
        # Get tool definition
        tool = capability.get_tool(tool_name)
        if not tool:
            raise ToolNotFoundError(f"Tool {tool_name} not found in {capability.id}")
        
        # Validate parameters
        if options.validate_params:
            errors = tool.validate_params(params)
            if errors:
                raise ValidationError(f"Validation failed: {', '.join(errors)}")
        
        # Get handler
        handler = self.registry.get_handler(capability.id, tool_name)
        if not handler:
            raise ExecutionError(f"No handler registered for {capability.id}:{tool_name}")
        
        # Execute with timeout
        timeout_sec = (options.timeout_ms or tool.timeout_ms) / 1000
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await asyncio.wait_for(
                    handler(**params),
                    timeout=timeout_sec
                )
            else:
                # Run sync handler in thread pool
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: handler(**params)),
                    timeout=timeout_sec
                )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Tool execution timed out after {timeout_sec}s")
        
        duration_ms = (time.time() - start_time) * 1000
        
        return ExecutionResult(
            capability_id=capability.id,
            tool_name=tool_name,
            status=ExecutionStatus.SUCCESS,
            result=result,
            duration_ms=duration_ms,
        )
    
    async def _find_alternative(
        self,
        original_capability_id: str,
        tool_name: str
    ) -> Optional[Capability]:
        """Find an alternative capability that has the same tool."""
        alternatives = self.registry.find_by_tool(tool_name, healthy_only=True)
        
        for cap in alternatives:
            if cap.id != original_capability_id:
                return cap
        
        return None
    
    def _get_cached(self, key: str, ttl_ms: int) -> Optional[Any]:
        """Get a cached result if not expired."""
        if key not in self._cache:
            return None
        
        result, timestamp = self._cache[key]
        if (time.time() - timestamp) * 1000 > ttl_ms:
            del self._cache[key]
            return None
        
        return result
    
    async def batch_call(
        self,
        calls: List[tuple],  # [(capability_id, tool_name, params), ...]
        options: Optional[ExecutionOptions] = None
    ) -> List[ExecutionResult]:
        """Execute multiple tool calls concurrently."""
        tasks = [
            self.call_tool(cap_id, tool_name, params, options)
            for cap_id, tool_name, params in calls
        ]
        return await asyncio.gather(*tasks)
    
    async def call_any(
        self,
        tool_name: str,
        params: Dict[str, Any],
        cap_type: Optional[CapabilityType] = None,
        options: Optional[ExecutionOptions] = None
    ) -> ExecutionResult:
        """
        Call a tool on any capable capability.
        
        Useful when you don't care which specific capability handles the request.
        """
        if cap_type:
            capabilities = self.registry.find_by_type(cap_type, healthy_only=True)
            capabilities = [c for c in capabilities if c.get_tool(tool_name)]
        else:
            capabilities = self.registry.find_by_tool(tool_name, healthy_only=True)
        
        if not capabilities:
            return ExecutionResult(
                capability_id="unknown",
                tool_name=tool_name,
                status=ExecutionStatus.FAILED,
                error=f"No capability found with tool: {tool_name}",
            )
        
        # Pick the first healthy one (could be smarter - load balancing, etc.)
        capability = capabilities[0]
        return await self.call_tool(capability.id, tool_name, params, options)
    
    def clear_cache(self) -> None:
        """Clear the result cache."""
        self._cache.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Get executor statistics."""
        return {
            "cache_entries": len(self._cache),
            "in_flight": len(self._in_flight),
        }


# Convenience function
async def call_tool(
    capability_id: str,
    tool_name: str,
    params: Dict[str, Any],
    **kwargs
) -> ExecutionResult:
    """Convenience function to call a tool."""
    executor = ToolExecutor()
    options = ExecutionOptions(**kwargs) if kwargs else None
    return await executor.call_tool(capability_id, tool_name, params, options)
