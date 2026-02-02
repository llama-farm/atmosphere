"""
Atmosphere Tool System.

Tools are typed, invocable functions that agents can use to take actions.
They are discoverable across the mesh via gossip-synced registries.
"""

from .base import (
    Tool,
    ToolSpec,
    ToolResult,
    ToolContext,
    ToolError,
    ValidationError,
    PermissionDeniedError,
    ToolNotFoundError,
    ParamSpec,
    tool,
    param,
)
from .registry import (
    ToolRegistry,
    ToolInfo,
    get_registry,
    set_registry,
)
from .executor import ToolExecutor
from .core import (
    HealthTool,
    NotifyTool,
    EchoTool,
    RouteTool,
    LLMTool,
    EmbedTool,
    StoreTool,
    CORE_TOOLS,
    register_core_tools,
)

__all__ = [
    # Base
    "Tool",
    "ToolSpec",
    "ToolResult",
    "ToolContext",
    "ToolError",
    "ValidationError",
    "PermissionDeniedError",
    "ToolNotFoundError",
    "ParamSpec",
    "tool",
    "param",
    # Registry
    "ToolRegistry",
    "ToolInfo",
    "get_registry",
    "set_registry",
    # Executor
    "ToolExecutor",
    # Core tools
    "HealthTool",
    "NotifyTool",
    "EchoTool",
    "RouteTool",
    "LLMTool",
    "EmbedTool",
    "StoreTool",
    "CORE_TOOLS",
    "register_core_tools",
]
