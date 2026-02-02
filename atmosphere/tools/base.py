"""
Base classes for the Atmosphere Tool System.

Tools are typed, invocable functions with:
- Input parameters (validated via JSON schema)
- Output type
- Required capabilities
- Execution constraints
- Permission requirements
"""

import asyncio
import functools
import inspect
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union, get_type_hints

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Base exception for tool errors."""
    
    def __init__(self, message: str, code: str = "TOOL_ERROR", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class PermissionDeniedError(ToolError):
    """Raised when caller lacks required permissions."""
    
    def __init__(self, required: List[str], actual: List[str]):
        super().__init__(
            f"Permission denied. Required: {required}, actual: {actual}",
            code="PERMISSION_DENIED",
            retryable=False
        )
        self.required = required
        self.actual = actual


class ToolNotFoundError(ToolError):
    """Raised when a tool is not found."""
    
    def __init__(self, tool_name: str):
        super().__init__(f"Tool not found: {tool_name}", code="TOOL_NOT_FOUND")
        self.tool_name = tool_name


class ValidationError(ToolError):
    """Raised when tool parameters fail validation."""
    
    def __init__(self, message: str, param: Optional[str] = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.param = param


@dataclass
class ToolContext:
    """Context passed to tool handlers during execution."""
    
    # Identity
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    node_id: Optional[str] = None
    
    # Permissions
    permissions: List[str] = field(default_factory=list)
    
    # Execution
    timeout_ms: int = 30000
    priority: int = 5
    
    # Metadata
    timestamp: float = field(default_factory=time.time)
    
    def has_permission(self, required: str) -> bool:
        """Check if context has a required permission."""
        for perm in self.permissions:
            if self._permission_matches(perm, required):
                return True
        return False
    
    def _permission_matches(self, granted: str, required: str) -> bool:
        """Check if granted permission covers required."""
        granted_parts = granted.split(":")
        required_parts = required.split(":")
        
        for g, r in zip(granted_parts, required_parts):
            if g == "*":
                return True
            if g != r:
                return False
        
        return len(granted_parts) >= len(required_parts)


@dataclass
class ToolResult:
    """Standard result wrapper for tool execution."""
    
    success: bool
    result: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    # Execution metadata
    duration_ms: float = 0
    node_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "error_code": self.error_code,
            "duration_ms": self.duration_ms,
            "node_id": self.node_id,
        }
    
    @classmethod
    def ok(cls, result: Any, **kwargs) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, result=result, **kwargs)
    
    @classmethod
    def fail(cls, error: str, code: str = "ERROR", **kwargs) -> "ToolResult":
        """Create a failed result."""
        return cls(success=False, error=error, error_code=code, **kwargs)


@dataclass
class ParamSpec:
    """Specification for a tool parameter."""
    
    name: str
    type: str  # "string", "integer", "number", "boolean", "array", "object"
    description: str = ""
    required: bool = True
    default: Any = None
    
    # Constraints
    enum: Optional[List[Any]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    
    def to_json_schema(self) -> dict:
        """Convert to JSON Schema format."""
        schema = {"type": self.type}
        
        if self.description:
            schema["description"] = self.description
        if self.default is not None:
            schema["default"] = self.default
        if self.enum:
            schema["enum"] = self.enum
        if self.min_value is not None:
            schema["minimum"] = self.min_value
        if self.max_value is not None:
            schema["maximum"] = self.max_value
        if self.min_length is not None:
            schema["minLength"] = self.min_length
        if self.max_length is not None:
            schema["maxLength"] = self.max_length
        if self.pattern:
            schema["pattern"] = self.pattern
        
        return schema


@dataclass
class ToolSpec:
    """
    Complete specification for a tool.
    
    This defines everything about a tool: its parameters, return type,
    requirements, and execution constraints.
    """
    
    # Identity
    name: str
    namespace: str = "core"
    version: str = "1.0.0"
    description: str = ""
    
    # Parameters
    parameters: List[ParamSpec] = field(default_factory=list)
    
    # Requirements
    capabilities_required: List[str] = field(default_factory=list)
    permissions_required: List[str] = field(default_factory=list)
    
    # Execution
    timeout_ms: int = 30000
    retries: int = 0
    idempotent: bool = False
    async_allowed: bool = True
    
    # Routing hints
    prefer_local: bool = True
    node_affinity: List[str] = field(default_factory=list)
    hop_limit: int = 3
    
    # Metadata
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    
    @property
    def full_name(self) -> str:
        """Get full namespaced name."""
        return f"{self.namespace}:{self.name}"
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "namespace": self.namespace,
            "version": self.version,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                }
                for p in self.parameters
            ],
            "capabilities_required": self.capabilities_required,
            "permissions_required": self.permissions_required,
            "timeout_ms": self.timeout_ms,
            "category": self.category,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ToolSpec":
        """Deserialize from dictionary."""
        params = [
            ParamSpec(
                name=p["name"],
                type=p.get("type", "string"),
                description=p.get("description", ""),
                required=p.get("required", True),
            )
            for p in data.get("parameters", [])
        ]
        
        return cls(
            name=data["name"],
            namespace=data.get("namespace", "core"),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            parameters=params,
            capabilities_required=data.get("capabilities_required", []),
            permissions_required=data.get("permissions_required", []),
            timeout_ms=data.get("timeout_ms", 30000),
            category=data.get("category", "general"),
            tags=data.get("tags", []),
        )
    
    def to_json_schema(self) -> dict:
        """Generate JSON Schema for parameters."""
        required = [p.name for p in self.parameters if p.required]
        properties = {p.name: p.to_json_schema() for p in self.parameters}
        
        return {
            "type": "object",
            "required": required,
            "properties": properties,
        }


class Tool(ABC):
    """
    Base class for tools.
    
    Subclass this to create custom tools. Override:
    - execute() for the tool implementation
    - Optionally override validate() for custom validation
    
    Example:
        class NotifyTool(Tool):
            spec = ToolSpec(
                name="notify",
                description="Send a notification",
                parameters=[
                    ParamSpec("message", "string", "Message to send"),
                    ParamSpec("recipient", "string", "Recipient"),
                ],
            )
            
            async def execute(self, message: str, recipient: str, **kwargs) -> Any:
                # Send notification...
                return {"sent": True}
    """
    
    spec: ToolSpec  # Subclasses must define this
    
    def __init__(self, registry: Optional[Any] = None):
        self.registry = registry
    
    @property
    def name(self) -> str:
        return self.spec.name
    
    @property
    def full_name(self) -> str:
        return self.spec.full_name
    
    @property
    def description(self) -> str:
        return self.spec.description
    
    def validate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and normalize parameters.
        
        Returns validated params (with defaults filled in).
        Raises ValidationError if validation fails.
        """
        result = {}
        
        for param_spec in self.spec.parameters:
            name = param_spec.name
            
            if name in params:
                value = params[name]
                # Type coercion could go here
                result[name] = value
            elif param_spec.default is not None:
                result[name] = param_spec.default
            elif param_spec.required:
                raise ValidationError(f"Missing required parameter: {name}", param=name)
        
        return result
    
    def check_permissions(self, context: ToolContext) -> None:
        """Check if context has required permissions."""
        for required in self.spec.permissions_required:
            if not context.has_permission(required):
                raise PermissionDeniedError(
                    required=self.spec.permissions_required,
                    actual=context.permissions
                )
    
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        Execute the tool with validated parameters.
        
        Override this in subclasses to implement tool logic.
        """
        raise NotImplementedError
    
    async def run(
        self,
        params: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        """
        Run the tool with full validation and error handling.
        
        This is the main entry point for tool execution.
        """
        context = context or ToolContext()
        start_time = time.time()
        
        try:
            # Check permissions
            self.check_permissions(context)
            
            # Validate parameters
            validated = self.validate(params)
            
            # Execute with timeout
            if self.spec.timeout_ms:
                result = await asyncio.wait_for(
                    self.execute(**validated),
                    timeout=self.spec.timeout_ms / 1000.0
                )
            else:
                result = await self.execute(**validated)
            
            duration = (time.time() - start_time) * 1000
            return ToolResult.ok(result, duration_ms=duration, node_id=context.node_id)
            
        except asyncio.TimeoutError:
            duration = (time.time() - start_time) * 1000
            return ToolResult.fail(
                f"Tool execution timed out after {self.spec.timeout_ms}ms",
                code="TIMEOUT",
                duration_ms=duration
            )
        except ToolError as e:
            duration = (time.time() - start_time) * 1000
            return ToolResult.fail(str(e), code=e.code, duration_ms=duration)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(f"Tool {self.name} failed: {e}")
            return ToolResult.fail(str(e), code="INTERNAL_ERROR", duration_ms=duration)


# === Decorator-based tool definition ===

def param(
    description: str = "",
    type: str = "string",
    required: bool = True,
    default: Any = None,
    enum: Optional[List[Any]] = None,
    **kwargs
) -> ParamSpec:
    """
    Decorator helper for defining tool parameters.
    
    Usage:
        @tool(name="notify")
        async def notify(
            message: str = param("The message to send"),
            recipient: str = param("The recipient", required=True),
        ):
            ...
    """
    # This returns a ParamSpec but we use it with a sentinel
    # The actual integration happens in the @tool decorator
    return ParamSpec(
        name="",  # Will be filled in by @tool
        type=type,
        description=description,
        required=required,
        default=default,
        enum=enum,
        **kwargs
    )


def tool(
    name: str,
    namespace: str = "core",
    description: str = "",
    capabilities: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    **spec_kwargs
) -> Callable:
    """
    Decorator to create a tool from a function.
    
    Usage:
        @tool(name="notify", description="Send a notification")
        async def notify(message: str, recipient: str) -> dict:
            return {"sent": True}
    """
    def decorator(func: Callable) -> Type[Tool]:
        # Extract parameters from function signature
        sig = inspect.signature(func)
        params = []
        
        for param_name, param_obj in sig.parameters.items():
            if param_name in ("self", "kwargs", "context"):
                continue
            
            # Check if default is a ParamSpec
            if isinstance(param_obj.default, ParamSpec):
                ps = param_obj.default
                ps.name = param_name
                params.append(ps)
            else:
                # Infer from type hints
                type_hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
                param_type = "string"
                
                if param_name in type_hints:
                    hint = type_hints[param_name]
                    if hint == int:
                        param_type = "integer"
                    elif hint == float:
                        param_type = "number"
                    elif hint == bool:
                        param_type = "boolean"
                    elif hint == list:
                        param_type = "array"
                    elif hint == dict:
                        param_type = "object"
                
                has_default = param_obj.default != inspect.Parameter.empty
                params.append(ParamSpec(
                    name=param_name,
                    type=param_type,
                    required=not has_default,
                    default=param_obj.default if has_default else None,
                ))
        
        # Create spec
        spec = ToolSpec(
            name=name,
            namespace=namespace,
            description=description or func.__doc__ or "",
            parameters=params,
            capabilities_required=capabilities or [],
            permissions_required=permissions or [],
            **spec_kwargs
        )
        
        # Create tool class with execute method
        if inspect.iscoroutinefunction(func):
            class DecoratedTool(Tool):
                async def execute(self, **kwargs):
                    return await func(**kwargs)
        else:
            class DecoratedTool(Tool):
                async def execute(self, **kwargs):
                    return func(**kwargs)
        
        DecoratedTool.spec = spec
        DecoratedTool.__name__ = f"{name.title().replace('_', '')}Tool"
        DecoratedTool.__doc__ = description or func.__doc__
        
        return DecoratedTool
    
    return decorator
