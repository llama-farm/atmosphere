"""
Tool Executor for Atmosphere.

Handles both local and remote tool execution with:
- Parameter validation
- Permission checking
- Timeout handling
- Retry logic
- Remote routing
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import Tool, ToolResult, ToolContext, ToolError, ToolNotFoundError
from .registry import ToolRegistry, ToolInfo

if TYPE_CHECKING:
    from ..mesh.gossip import GossipProtocol
    from ..router.semantic import SemanticRouter

logger = logging.getLogger(__name__)


@dataclass
class ExecutionRequest:
    """Request to execute a tool."""
    
    tool_name: str
    params: Dict[str, Any]
    context: ToolContext
    
    # Routing hints
    prefer_node: Optional[str] = None
    exclude_nodes: List[str] = None
    timeout_ms: int = 30000
    retries: int = 0
    
    # Tracking
    request_id: Optional[str] = None
    trace_id: Optional[str] = None


class ToolExecutor:
    """
    Executes tools locally or routes to remote nodes.
    
    The executor:
    1. Finds the best node for execution
    2. Validates parameters
    3. Checks permissions
    4. Executes (locally or remotely)
    5. Handles retries on failure
    
    Usage:
        executor = ToolExecutor(registry, router)
        
        result = await executor.execute(
            "notify",
            {"message": "Hello", "recipient": "user@example.com"}
        )
    """
    
    def __init__(
        self,
        registry: ToolRegistry,
        router: Optional["SemanticRouter"] = None,
        gossip: Optional["GossipProtocol"] = None,
    ):
        self.registry = registry
        self.router = router
        self.gossip = gossip
        
        # Metrics
        self._executions = 0
        self._successes = 0
        self._failures = 0
        self._remote_calls = 0
    
    async def execute(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[ToolContext] = None,
        **kwargs
    ) -> ToolResult:
        """
        Execute a tool with automatic routing.
        
        Args:
            tool_name: Name of the tool (with or without namespace)
            params: Tool parameters
            context: Execution context
            **kwargs: Additional execution options
            
        Returns:
            ToolResult with success/failure and result data
        """
        context = context or ToolContext(node_id=self.registry.node_id)
        self._executions += 1
        
        request = ExecutionRequest(
            tool_name=tool_name,
            params=params,
            context=context,
            timeout_ms=kwargs.get("timeout_ms", 30000),
            retries=kwargs.get("retries", 0),
            prefer_node=kwargs.get("prefer_node"),
            exclude_nodes=kwargs.get("exclude_nodes", []),
        )
        
        # Find best execution target
        target = self._find_execution_target(request)
        
        if target is None:
            self._failures += 1
            return ToolResult.fail(
                f"Tool not found: {tool_name}",
                code="TOOL_NOT_FOUND"
            )
        
        # Execute with retries
        last_error = None
        for attempt in range(request.retries + 1):
            try:
                if target.node_id == self.registry.node_id:
                    # Local execution
                    result = await self._execute_local(request, target)
                else:
                    # Remote execution
                    self._remote_calls += 1
                    result = await self._execute_remote(request, target)
                
                if result.success:
                    self._successes += 1
                    return result
                
                last_error = result.error
                
                # Don't retry non-retryable errors
                if result.error_code in ("PERMISSION_DENIED", "VALIDATION_ERROR"):
                    break
                    
            except Exception as e:
                last_error = str(e)
                logger.error(f"Tool execution failed (attempt {attempt + 1}): {e}")
        
        self._failures += 1
        return ToolResult.fail(
            last_error or "Unknown error",
            code="EXECUTION_FAILED"
        )
    
    def _find_execution_target(self, request: ExecutionRequest) -> Optional[ToolInfo]:
        """Find the best node to execute a tool."""
        tool_name = request.tool_name
        
        # Check local first (prefer local unless explicitly excluded)
        local_tool = self.registry.get(tool_name)
        if local_tool and self.registry.node_id not in (request.exclude_nodes or []):
            return ToolInfo.from_tool(local_tool, self.registry.node_id)
        
        # Check remote
        info = self.registry.get_info(tool_name)
        if info:
            # Apply exclusions
            if request.exclude_nodes and info.node_id in request.exclude_nodes:
                return None
            return info
        
        return None
    
    async def _execute_local(
        self,
        request: ExecutionRequest,
        target: ToolInfo,
    ) -> ToolResult:
        """Execute a tool locally."""
        tool = self.registry.get(request.tool_name)
        if not tool:
            return ToolResult.fail(
                f"Local tool not found: {request.tool_name}",
                code="TOOL_NOT_FOUND"
            )
        
        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                tool.run(request.params, request.context),
                timeout=request.timeout_ms / 1000.0
            )
            return result
        except asyncio.TimeoutError:
            return ToolResult.fail(
                f"Tool execution timed out after {request.timeout_ms}ms",
                code="TIMEOUT"
            )
    
    async def _execute_remote(
        self,
        request: ExecutionRequest,
        target: ToolInfo,
    ) -> ToolResult:
        """Execute a tool on a remote node."""
        # Build request message
        message = {
            "type": "tool_invoke",
            "tool": request.tool_name,
            "params": request.params,
            "context": {
                "agent_id": request.context.agent_id,
                "session_id": request.context.session_id,
                "trace_id": request.context.trace_id,
                "permissions": request.context.permissions,
            },
            "timeout_ms": request.timeout_ms,
        }
        
        # In a full implementation, this would:
        # 1. Serialize the request
        # 2. Route through the mesh to target.node_id
        # 3. Wait for response
        # 4. Deserialize result
        
        # For now, return not implemented
        return ToolResult.fail(
            f"Remote execution to {target.node_id} not yet implemented",
            code="NOT_IMPLEMENTED"
        )
    
    async def execute_batch(
        self,
        requests: List[Dict[str, Any]],
        context: Optional[ToolContext] = None,
        parallel: bool = True,
    ) -> List[ToolResult]:
        """
        Execute multiple tools, optionally in parallel.
        
        Args:
            requests: List of {"tool": name, "params": {...}}
            context: Shared execution context
            parallel: Execute in parallel if True
            
        Returns:
            List of ToolResults in same order as requests
        """
        context = context or ToolContext(node_id=self.registry.node_id)
        
        if parallel:
            tasks = [
                self.execute(
                    req["tool"],
                    req.get("params", {}),
                    context
                )
                for req in requests
            ]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for req in requests:
                result = await self.execute(
                    req["tool"],
                    req.get("params", {}),
                    context
                )
                results.append(result)
            return results
    
    def stats(self) -> dict:
        """Get executor statistics."""
        return {
            "executions": self._executions,
            "successes": self._successes,
            "failures": self._failures,
            "remote_calls": self._remote_calls,
            "success_rate": self._successes / self._executions if self._executions > 0 else 0,
        }
