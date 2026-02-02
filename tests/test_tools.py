"""
Tests for the Atmosphere Tool System.
"""

import asyncio
import pytest
from typing import Dict, Any

from atmosphere.tools.base import (
    Tool, ToolSpec, ToolResult, ToolContext, ParamSpec,
    ToolError, ValidationError, PermissionDeniedError,
    tool, param,
)
from atmosphere.tools.registry import ToolRegistry, ToolInfo
from atmosphere.tools.executor import ToolExecutor
from atmosphere.tools.core import (
    HealthTool, NotifyTool, EchoTool, StoreTool,
    CORE_TOOLS, register_core_tools,
)


class TestToolSpec:
    """Tests for ToolSpec."""
    
    def test_create_spec(self):
        """Test creating a tool spec."""
        spec = ToolSpec(
            name="test_tool",
            namespace="testing",
            description="A test tool",
            parameters=[
                ParamSpec("arg1", "string", "First argument"),
                ParamSpec("arg2", "integer", "Second argument", required=False, default=42),
            ],
        )
        
        assert spec.name == "test_tool"
        assert spec.full_name == "testing:test_tool"
        assert len(spec.parameters) == 2
    
    def test_spec_serialization(self):
        """Test spec serialization."""
        spec = ToolSpec(
            name="test",
            description="Test tool",
            parameters=[ParamSpec("x", "string")],
        )
        
        data = spec.to_dict()
        restored = ToolSpec.from_dict(data)
        
        assert restored.name == spec.name
        assert len(restored.parameters) == 1
    
    def test_json_schema(self):
        """Test JSON Schema generation."""
        spec = ToolSpec(
            name="test",
            parameters=[
                ParamSpec("required_arg", "string"),
                ParamSpec("optional_arg", "integer", required=False, default=10),
            ],
        )
        
        schema = spec.to_json_schema()
        
        assert schema["type"] == "object"
        assert "required_arg" in schema["required"]
        assert "optional_arg" not in schema["required"]
        assert schema["properties"]["optional_arg"]["default"] == 10


class TestToolResult:
    """Tests for ToolResult."""
    
    def test_ok_result(self):
        """Test successful result."""
        result = ToolResult.ok({"data": 42})
        
        assert result.success is True
        assert result.result == {"data": 42}
        assert result.error is None
    
    def test_fail_result(self):
        """Test failed result."""
        result = ToolResult.fail("Something went wrong", code="TEST_ERROR")
        
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.error_code == "TEST_ERROR"
    
    def test_result_serialization(self):
        """Test result serialization."""
        result = ToolResult.ok({"value": 123}, duration_ms=50.5)
        data = result.to_dict()
        
        assert data["success"] is True
        assert data["result"]["value"] == 123
        assert data["duration_ms"] == 50.5


class TestToolContext:
    """Tests for ToolContext."""
    
    def test_permission_check(self):
        """Test permission checking."""
        context = ToolContext(
            permissions=["notify:send", "storage:*", "admin:read:config"]
        )
        
        # Exact match
        assert context.has_permission("notify:send") is True
        
        # Wildcard match
        assert context.has_permission("storage:read") is True
        assert context.has_permission("storage:write") is True
        
        # Partial match
        assert context.has_permission("admin:read:config") is True
        
        # No match
        assert context.has_permission("delete:all") is False
        assert context.has_permission("notify:delete") is False


class TestTool:
    """Tests for Tool base class."""
    
    @pytest.mark.asyncio
    async def test_custom_tool(self):
        """Test creating and running a custom tool."""
        
        class AddTool(Tool):
            spec = ToolSpec(
                name="add",
                description="Add two numbers",
                parameters=[
                    ParamSpec("a", "number"),
                    ParamSpec("b", "number"),
                ],
            )
            
            async def execute(self, a: float, b: float, **kwargs) -> float:
                return a + b
        
        tool = AddTool()
        result = await tool.run({"a": 5, "b": 3})
        
        assert result.success is True
        assert result.result == 8
    
    @pytest.mark.asyncio
    async def test_validation_error(self):
        """Test parameter validation."""
        
        class RequiredParamTool(Tool):
            spec = ToolSpec(
                name="required_test",
                parameters=[ParamSpec("required_arg", "string")],
            )
            
            async def execute(self, required_arg: str, **kwargs) -> str:
                return required_arg
        
        tool = RequiredParamTool()
        result = await tool.run({})  # Missing required param
        
        assert result.success is False
        assert "required" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_permission_denied(self):
        """Test permission checking."""
        
        class ProtectedTool(Tool):
            spec = ToolSpec(
                name="protected",
                permissions_required=["admin:write"],
            )
            
            async def execute(self, **kwargs) -> str:
                return "secret"
        
        tool = ProtectedTool()
        
        # No permissions
        result = await tool.run({}, ToolContext(permissions=[]))
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        
        # With permission
        result = await tool.run({}, ToolContext(permissions=["admin:write"]))
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_timeout(self):
        """Test execution timeout."""
        
        class SlowTool(Tool):
            spec = ToolSpec(
                name="slow",
                timeout_ms=100,  # 100ms timeout
            )
            
            async def execute(self, **kwargs):
                await asyncio.sleep(1.0)  # Sleep 1 second
                return "done"
        
        tool = SlowTool()
        result = await tool.run({})
        
        assert result.success is False
        assert result.error_code == "TIMEOUT"


class TestToolDecorator:
    """Tests for @tool decorator."""
    
    @pytest.mark.asyncio
    async def test_decorator_basic(self):
        """Test basic decorator usage."""
        
        @tool(name="greet", description="Greet someone")
        async def greet(name: str) -> str:
            return f"Hello, {name}!"
        
        # greet is now a Tool class
        tool_instance = greet()
        result = await tool_instance.run({"name": "World"})
        
        assert result.success is True
        assert result.result == "Hello, World!"
    
    @pytest.mark.asyncio
    async def test_decorator_with_defaults(self):
        """Test decorator with default values."""
        
        @tool(name="power", namespace="math")
        async def power(base: float, exponent: float = 2.0) -> float:
            return base ** exponent
        
        tool_instance = power()
        
        # Without default
        result = await tool_instance.run({"base": 3, "exponent": 3})
        assert result.result == 27
        
        # With default
        result = await tool_instance.run({"base": 5})
        assert result.result == 25


class TestToolRegistry:
    """Tests for ToolRegistry."""
    
    def test_register_tool(self):
        """Test registering a tool."""
        registry = ToolRegistry(node_id="test-node")
        registry.register(EchoTool())
        
        assert registry.get("echo") is not None
        assert len(registry.list_local()) == 1
    
    def test_get_by_name(self):
        """Test getting tool by various name formats."""
        registry = ToolRegistry(node_id="test-node")
        registry.register(HealthTool())
        
        # Full name
        assert registry.get("core:health") is not None
        
        # Short name
        assert registry.get("health") is not None
    
    def test_list_names(self):
        """Test listing tool names."""
        registry = ToolRegistry(node_id="test-node")
        register_core_tools(registry)
        
        names = registry.list_names()
        
        assert "core:health" in names
        assert "core:notify" in names
        assert "core:echo" in names
    
    @pytest.mark.asyncio
    async def test_execute_via_registry(self):
        """Test executing tool via registry."""
        registry = ToolRegistry(node_id="test-node")
        registry.register(EchoTool())
        
        result = await registry.execute("echo", {"message": "test"})
        
        assert result.success is True
        assert result.result["message"] == "test"
    
    def test_find_by_category(self):
        """Test finding tools by category."""
        registry = ToolRegistry(node_id="test-node")
        register_core_tools(registry)
        
        ai_tools = registry.find_by_category("ai")
        assert len(ai_tools) >= 2  # llm, embed
    
    def test_tool_info(self):
        """Test ToolInfo creation."""
        tool = HealthTool()
        info = ToolInfo.from_tool(tool, "node-1")
        
        assert info.name == "health"
        assert info.node_id == "node-1"
        assert info.category == "system"


class TestToolExecutor:
    """Tests for ToolExecutor."""
    
    @pytest.mark.asyncio
    async def test_execute_local(self):
        """Test local execution via executor."""
        registry = ToolRegistry(node_id="test-node")
        registry.register(EchoTool())
        
        executor = ToolExecutor(registry)
        result = await executor.execute("echo", {"message": "hello"})
        
        assert result.success is True
        assert result.result["message"] == "hello"
    
    @pytest.mark.asyncio
    async def test_execute_not_found(self):
        """Test executing non-existent tool."""
        registry = ToolRegistry(node_id="test-node")
        executor = ToolExecutor(registry)
        
        result = await executor.execute("nonexistent", {})
        
        assert result.success is False
        assert result.error_code == "TOOL_NOT_FOUND"
    
    @pytest.mark.asyncio
    async def test_execute_batch(self):
        """Test batch execution."""
        registry = ToolRegistry(node_id="test-node")
        registry.register(EchoTool())
        
        executor = ToolExecutor(registry)
        results = await executor.execute_batch([
            {"tool": "echo", "params": {"message": "one"}},
            {"tool": "echo", "params": {"message": "two"}},
            {"tool": "echo", "params": {"message": "three"}},
        ])
        
        assert len(results) == 3
        assert all(r.success for r in results)
        assert results[0].result["message"] == "one"
        assert results[1].result["message"] == "two"
    
    def test_executor_stats(self):
        """Test executor statistics."""
        registry = ToolRegistry(node_id="test-node")
        executor = ToolExecutor(registry)
        
        stats = executor.stats()
        assert "executions" in stats
        assert "successes" in stats


class TestCoreTools:
    """Tests for core tool implementations."""
    
    @pytest.mark.asyncio
    async def test_health_tool(self):
        """Test health tool."""
        tool = HealthTool()
        result = await tool.run({})
        
        assert result.success is True
        assert result.result["status"] == "healthy"
        assert "cpu" in result.result
        assert "memory" in result.result
    
    @pytest.mark.asyncio
    async def test_health_tool_detailed(self):
        """Test health tool with detailed metrics."""
        tool = HealthTool()
        result = await tool.run({"detailed": True})
        
        assert result.success is True
        assert "disk" in result.result
    
    @pytest.mark.asyncio
    async def test_notify_tool(self):
        """Test notify tool."""
        tool = NotifyTool()
        context = ToolContext(permissions=["notify:send"])
        
        result = await tool.run({
            "message": "Test notification",
            "urgency": "high"
        }, context)
        
        assert result.success is True
        assert result.result["sent"] is True
        assert result.result["urgency"] == "high"
    
    @pytest.mark.asyncio
    async def test_echo_tool(self):
        """Test echo tool."""
        tool = EchoTool()
        result = await tool.run({
            "message": "Hello",
            "data": {"key": "value"}
        })
        
        assert result.success is True
        assert result.result["message"] == "Hello"
        assert result.result["data"]["key"] == "value"
    
    @pytest.mark.asyncio
    async def test_store_tool(self):
        """Test store tool."""
        tool = StoreTool()
        context = ToolContext(permissions=["storage:read", "storage:write"])
        
        # Set
        result = await tool.run({
            "key": "test_key",
            "value": {"data": 123},
            "action": "set"
        }, context)
        assert result.success is True
        
        # Get
        result = await tool.run({
            "key": "test_key",
            "action": "get"
        }, context)
        assert result.success is True
        assert result.result["value"]["data"] == 123
        
        # Delete
        result = await tool.run({
            "key": "test_key",
            "action": "delete"
        }, context)
        assert result.success is True
        assert result.result["existed"] is True
    
    def test_register_core_tools(self):
        """Test registering all core tools."""
        registry = ToolRegistry(node_id="test-node")
        count = register_core_tools(registry)
        
        assert count == len(CORE_TOOLS)
        assert len(registry.list_local()) == len(CORE_TOOLS)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
