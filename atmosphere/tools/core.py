"""
Core tools for Atmosphere.

These are the built-in tools available on every node.
"""

import asyncio
import logging
import platform
import time
from typing import Any, Dict, List, Optional

import psutil

from .base import Tool, ToolSpec, ParamSpec, ToolResult, ToolContext

logger = logging.getLogger(__name__)


# === Health Tool ===

class HealthTool(Tool):
    """
    Check node health and system status.
    
    Returns system information and resource usage.
    """
    
    spec = ToolSpec(
        name="health",
        namespace="core",
        description="Check node health and system status",
        parameters=[
            ParamSpec("detailed", "boolean", "Include detailed metrics", required=False, default=False),
        ],
        category="system",
        tags=["health", "monitoring", "system"],
    )
    
    async def execute(self, detailed: bool = False, **kwargs) -> Dict[str, Any]:
        """Get health information."""
        result = {
            "status": "healthy",
            "timestamp": time.time(),
            "node": {
                "hostname": platform.node(),
                "platform": platform.system(),
                "architecture": platform.machine(),
            },
        }
        
        try:
            # Basic metrics
            result["cpu"] = {
                "percent": psutil.cpu_percent(interval=0.1),
                "count": psutil.cpu_count(),
            }
            
            mem = psutil.virtual_memory()
            result["memory"] = {
                "total_gb": round(mem.total / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
                "percent": mem.percent,
            }
            
            if detailed:
                # Detailed metrics
                disk = psutil.disk_usage('/')
                result["disk"] = {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "percent": disk.percent,
                }
                
                result["uptime_seconds"] = time.time() - psutil.boot_time()
                
        except Exception as e:
            logger.warning(f"Could not get system metrics: {e}")
            result["metrics_error"] = str(e)
        
        return result


# === Notify Tool ===

class NotifyTool(Tool):
    """
    Send a notification.
    
    Routes to available notification channels (log, console, etc.)
    """
    
    spec = ToolSpec(
        name="notify",
        namespace="core",
        description="Send a notification to a recipient or channel",
        parameters=[
            ParamSpec("message", "string", "The notification message"),
            ParamSpec("recipient", "string", "Recipient (email, @handle, #channel)", required=False),
            ParamSpec("urgency", "string", "Urgency level", required=False, default="medium",
                     enum=["low", "medium", "high", "critical"]),
            ParamSpec("title", "string", "Notification title", required=False),
        ],
        permissions_required=["notify:send"],
        category="communication",
        tags=["notification", "messaging", "alert"],
    )
    
    async def execute(
        self,
        message: str,
        recipient: Optional[str] = None,
        urgency: str = "medium",
        title: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send notification."""
        # Log the notification
        urgency_upper = urgency.upper()
        log_message = f"[{urgency_upper}] {title + ': ' if title else ''}{message}"
        
        if urgency == "critical":
            logger.critical(log_message)
        elif urgency == "high":
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        # In a real implementation, this would route to actual channels
        return {
            "sent": True,
            "message": message,
            "recipient": recipient or "default",
            "urgency": urgency,
            "timestamp": time.time(),
            "channels": ["log"],
        }


# === Echo Tool (for testing) ===

class EchoTool(Tool):
    """
    Echo back the input parameters.
    
    Useful for testing tool invocation.
    """
    
    spec = ToolSpec(
        name="echo",
        namespace="core",
        description="Echo back input parameters (for testing)",
        parameters=[
            ParamSpec("message", "string", "Message to echo", required=False, default=""),
            ParamSpec("data", "object", "Data to echo", required=False),
        ],
        category="testing",
        tags=["test", "debug", "echo"],
    )
    
    async def execute(
        self,
        message: str = "",
        data: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Echo parameters."""
        return {
            "echo": True,
            "message": message,
            "data": data,
            "extra": kwargs,
            "timestamp": time.time(),
        }


# === Route Tool ===

class RouteTool(Tool):
    """
    Route an intent to the best capable node.
    
    This tool invokes the semantic router to find and execute on the best node.
    """
    
    spec = ToolSpec(
        name="route",
        namespace="core",
        description="Route an intent to the best capable node in the mesh",
        parameters=[
            ParamSpec("intent", "string", "The intent to route"),
            ParamSpec("args", "object", "Arguments for the intent", required=False),
            ParamSpec("timeout_ms", "integer", "Timeout in milliseconds", required=False, default=30000),
        ],
        capabilities_required=["routing"],
        category="mesh",
        tags=["routing", "intent", "mesh"],
    )
    
    async def execute(
        self,
        intent: str,
        args: Optional[Dict] = None,
        timeout_ms: int = 30000,
        **kwargs
    ) -> Dict[str, Any]:
        """Route an intent."""
        # This would use the semantic router
        # For now, return a placeholder
        return {
            "routed": True,
            "intent": intent,
            "args": args,
            "status": "routing_not_implemented",
            "message": "Semantic routing not yet integrated with tool executor",
        }


# === LLM Tool ===

class LLMTool(Tool):
    """
    Generate text using a language model.
    
    Routes to available LLM backends (Ollama, LlamaFarm, etc.)
    """
    
    spec = ToolSpec(
        name="llm",
        namespace="core",
        description="Generate text using a language model",
        parameters=[
            ParamSpec("prompt", "string", "The prompt to send to the LLM"),
            ParamSpec("system", "string", "System prompt", required=False),
            ParamSpec("model", "string", "Model to use (auto-select if omitted)", required=False),
            ParamSpec("max_tokens", "integer", "Maximum tokens to generate", required=False, default=1024),
            ParamSpec("temperature", "number", "Sampling temperature", required=False, default=0.7),
        ],
        capabilities_required=["llm"],
        category="ai",
        tags=["llm", "generation", "ai"],
        timeout_ms=120000,  # 2 minutes for LLM
    )
    
    async def execute(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate text with LLM."""
        # This would integrate with LlamaFarm/Ollama
        # For now, return a placeholder
        return {
            "generated": False,
            "prompt": prompt,
            "model": model or "not_configured",
            "status": "llm_not_configured",
            "message": "LLM backend not configured. Set up LlamaFarm or Ollama.",
        }


# === Embed Tool ===

class EmbedTool(Tool):
    """
    Generate embeddings for text.
    
    Returns vector embeddings for semantic similarity and search.
    """
    
    spec = ToolSpec(
        name="embed",
        namespace="core",
        description="Generate vector embeddings for text",
        parameters=[
            ParamSpec("text", "string", "Text to embed"),
            ParamSpec("texts", "array", "Multiple texts to embed", required=False),
            ParamSpec("model", "string", "Embedding model", required=False),
        ],
        capabilities_required=["embeddings"],
        category="ai",
        tags=["embeddings", "vectors", "ai"],
    )
    
    async def execute(
        self,
        text: Optional[str] = None,
        texts: Optional[List[str]] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate embeddings."""
        # This would integrate with embedding models
        # For now, return a placeholder
        input_texts = texts or ([text] if text else [])
        
        return {
            "generated": False,
            "input_count": len(input_texts),
            "model": model or "not_configured",
            "status": "embeddings_not_configured",
            "message": "Embedding backend not configured.",
        }


# === Store Tool ===

class StoreTool(Tool):
    """
    Store key-value data.
    
    Provides persistent storage for agents and tools.
    """
    
    spec = ToolSpec(
        name="store",
        namespace="core",
        description="Store key-value data persistently",
        parameters=[
            ParamSpec("key", "string", "Storage key"),
            ParamSpec("value", "object", "Value to store (any JSON type)", required=False),
            ParamSpec("action", "string", "Action: get, set, delete", required=False, default="get",
                     enum=["get", "set", "delete"]),
            ParamSpec("ttl_seconds", "integer", "Time-to-live in seconds", required=False),
        ],
        permissions_required=["storage:read", "storage:write"],
        category="storage",
        tags=["storage", "persistence", "data"],
    )
    
    # Simple in-memory storage (would be persistent in real implementation)
    _store: Dict[str, Any] = {}
    
    async def execute(
        self,
        key: str,
        value: Any = None,
        action: str = "get",
        ttl_seconds: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute storage operation."""
        if action == "get":
            if key in self._store:
                return {
                    "success": True,
                    "key": key,
                    "value": self._store[key],
                    "exists": True,
                }
            return {
                "success": True,
                "key": key,
                "value": None,
                "exists": False,
            }
        
        elif action == "set":
            self._store[key] = value
            return {
                "success": True,
                "key": key,
                "action": "set",
            }
        
        elif action == "delete":
            existed = key in self._store
            self._store.pop(key, None)
            return {
                "success": True,
                "key": key,
                "action": "delete",
                "existed": existed,
            }
        
        return {
            "success": False,
            "error": f"Unknown action: {action}",
        }


# === Registry of core tools ===

CORE_TOOLS = {
    "health": HealthTool,
    "notify": NotifyTool,
    "echo": EchoTool,
    "route": RouteTool,
    "llm": LLMTool,
    "embed": EmbedTool,
    "store": StoreTool,
}


def register_core_tools(registry) -> int:
    """
    Register all core tools with a registry.
    
    Returns the number of tools registered.
    """
    count = 0
    for name, tool_class in CORE_TOOLS.items():
        try:
            registry.register(tool_class(registry=registry))
            count += 1
        except Exception as e:
            logger.error(f"Failed to register core tool {name}: {e}")
    
    return count
