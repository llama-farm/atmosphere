"""
Agent loader for Atmosphere.

Loads agent definitions from YAML files and creates runnable agents.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from .base import Agent, AgentSpec, AgentState
from .registry import AgentRegistry

logger = logging.getLogger(__name__)


def load_spec_from_yaml(path: Path) -> AgentSpec:
    """
    Load an agent spec from a YAML file.
    
    Expected format:
        agent:
          id: my_agent
          version: "1.0"
          type: reactive
          description: |
            Description of what this agent does.
          triggers:
            - name: trigger_name
              description: When this trigger fires
              params:
                param1: type
          tools:
            required:
              - tool_name
            optional:
              - other_tool
          default_params:
            threshold: 0.5
          instructions: |
            How the agent should behave.
    """
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
    
    agent_data = data.get("agent", data)
    
    # Extract tools
    tools = agent_data.get("tools", {})
    tools_required = tools.get("required", [])
    tools_optional = tools.get("optional", [])
    
    return AgentSpec(
        id=agent_data["id"],
        type=agent_data.get("type", "reactive"),
        version=agent_data.get("version", "1.0"),
        description=agent_data.get("description", ""),
        triggers=agent_data.get("triggers", []),
        tools_required=tools_required,
        tools_optional=tools_optional,
        default_params=agent_data.get("default_params", {}),
        instructions=agent_data.get("instructions", ""),
        resource_profile=agent_data.get("resource_profile", {}),
    )


def load_specs_from_directory(directory: Path) -> List[AgentSpec]:
    """Load all agent specs from a directory."""
    specs = []
    
    for path in directory.glob("*.yaml"):
        try:
            spec = load_spec_from_yaml(path)
            specs.append(spec)
            logger.info(f"Loaded agent spec: {spec.id} from {path.name}")
        except Exception as e:
            logger.error(f"Failed to load spec from {path}: {e}")
    
    return specs


class SpecAgent(Agent):
    """
    An agent that runs from a YAML specification.
    
    This is the runtime for spec-defined agents. It interprets the
    spec's triggers and instructions to handle intents.
    
    For simple specs, it uses rule-based handling. For complex specs
    with LLM instructions, it delegates to an LLM for reasoning.
    """
    
    def __init__(
        self,
        spec: AgentSpec,
        llm_handler: Optional[Any] = None,
        tool_executor: Optional[Any] = None,
        **kwargs
    ):
        super().__init__(spec=spec, **kwargs)
        self.llm_handler = llm_handler
        self.tool_executor = tool_executor
        
        # Initialize params from defaults
        self.params = dict(spec.default_params)
        
        # Build trigger index for fast lookup
        self._trigger_index: Dict[str, Dict] = {}
        for trigger in spec.triggers:
            name = trigger.get("name", "")
            self._trigger_index[name] = trigger
    
    async def handle_intent(self, intent: str, args: Dict[str, Any]) -> Any:
        """
        Handle an intent using the spec definition.
        
        Flow:
        1. Match intent to trigger
        2. Validate args against trigger params
        3. If instructions exist, use LLM reasoning
        4. Otherwise, execute tools directly
        """
        # Find matching trigger
        trigger = self._trigger_index.get(intent)
        
        if not trigger:
            # Try fuzzy match
            trigger = self._fuzzy_match_trigger(intent)
        
        if not trigger:
            raise ValueError(f"Agent {self.id} cannot handle intent: {intent}")
        
        # Validate args
        args = self._validate_and_fill_args(trigger, args)
        
        # Store in context for tool access
        self.context["current_intent"] = intent
        self.context["current_args"] = args
        self.context["current_trigger"] = trigger
        
        # Execute based on spec type
        if self.spec.instructions and self.llm_handler:
            # Use LLM-based execution
            return await self._execute_with_llm(trigger, args)
        else:
            # Use simple rule-based execution
            return await self._execute_simple(trigger, args)
    
    def _fuzzy_match_trigger(self, intent: str) -> Optional[Dict]:
        """Try to match intent to a trigger by description."""
        intent_lower = intent.lower().replace("_", " ")
        
        for trigger in self.spec.triggers:
            desc = trigger.get("description", "").lower()
            name = trigger.get("name", "").lower().replace("_", " ")
            
            # Check if intent words appear in trigger
            if intent_lower in desc or intent_lower in name:
                return trigger
            
            # Check reverse
            if name in intent_lower:
                return trigger
        
        return None
    
    def _validate_and_fill_args(
        self,
        trigger: Dict,
        args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and fill default values for args."""
        params = trigger.get("params", {})
        result = dict(args)
        
        for param_name, param_spec in params.items():
            if param_name not in result:
                # Check for default
                if isinstance(param_spec, dict):
                    if "default" in param_spec:
                        result[param_name] = param_spec["default"]
                    elif param_spec.get("required", True):
                        # Use param default from spec
                        if param_name in self.params:
                            result[param_name] = self.params[param_name]
        
        return result
    
    async def _execute_simple(
        self,
        trigger: Dict,
        args: Dict[str, Any]
    ) -> Any:
        """Execute trigger with simple rule-based logic."""
        # For simple triggers, just invoke required tools in order
        results = {}
        
        for tool_name in self.spec.tools_required:
            if self.tool_executor:
                result = await self.tool_executor.execute(
                    tool_name,
                    **args
                )
                results[tool_name] = result
            else:
                # Try to invoke through mesh
                result = await self.invoke(
                    f"tool:{tool_name}",
                    args
                )
                results[tool_name] = result
        
        # Return combined results
        if len(results) == 1:
            return list(results.values())[0]
        return results
    
    async def _execute_with_llm(
        self,
        trigger: Dict,
        args: Dict[str, Any]
    ) -> Any:
        """Execute trigger with LLM-based reasoning."""
        # Build prompt from instructions
        prompt = self._build_llm_prompt(trigger, args)
        
        # Get LLM response
        response = await self.llm_handler.generate(
            prompt=prompt,
            system=self._build_system_prompt(),
        )
        
        # Parse response for tool calls
        tool_calls = self._parse_tool_calls(response)
        
        if tool_calls:
            # Execute tool calls
            results = []
            for tool_call in tool_calls:
                result = await self._execute_tool_call(tool_call)
                results.append(result)
            
            # Continue reasoning with results
            return await self._continue_reasoning(prompt, results)
        
        # No tool calls - return response as-is
        return response
    
    def _build_system_prompt(self) -> str:
        """Build system prompt from spec."""
        tools_desc = ", ".join(
            self.spec.tools_required + self.spec.tools_optional
        )
        
        return f"""You are {self.spec.id}, an Atmosphere agent.

{self.spec.description}

Available tools: {tools_desc}

{self.spec.instructions}

When you need to use a tool, respond with:
<tool>tool_name</tool>
<args>
  param1: value1
  param2: value2
</args>

After receiving tool results, continue reasoning to complete the task."""
    
    def _build_llm_prompt(self, trigger: Dict, args: Dict[str, Any]) -> str:
        """Build LLM prompt for a trigger."""
        trigger_name = trigger.get("name", "unknown")
        trigger_desc = trigger.get("description", "")
        
        args_str = "\n".join(f"  {k}: {v}" for k, v in args.items())
        
        return f"""Handle the following request:

Trigger: {trigger_name}
Description: {trigger_desc}

Arguments:
{args_str}

Context:
{self._format_context()}

What actions should I take?"""
    
    def _format_context(self) -> str:
        """Format context for LLM prompt."""
        if not self.context:
            return "No additional context."
        
        lines = []
        for key, value in self.context.items():
            if not key.startswith("current_"):
                lines.append(f"  {key}: {value}")
        
        return "\n".join(lines) if lines else "No additional context."
    
    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Parse tool calls from LLM response."""
        calls = []
        
        # Look for <tool>...</tool> patterns
        tool_pattern = r'<tool>(.*?)</tool>'
        args_pattern = r'<args>(.*?)</args>'
        
        tool_matches = re.findall(tool_pattern, response, re.DOTALL)
        args_matches = re.findall(args_pattern, response, re.DOTALL)
        
        for i, tool_name in enumerate(tool_matches):
            call = {"tool": tool_name.strip()}
            
            if i < len(args_matches):
                # Parse YAML-like args
                try:
                    args_text = args_matches[i].strip()
                    args = yaml.safe_load(args_text)
                    call["args"] = args if isinstance(args, dict) else {}
                except:
                    call["args"] = {}
            else:
                call["args"] = {}
            
            calls.append(call)
        
        return calls
    
    async def _execute_tool_call(self, tool_call: Dict[str, Any]) -> Any:
        """Execute a tool call."""
        tool_name = tool_call["tool"]
        args = tool_call.get("args", {})
        
        if self.tool_executor:
            return await self.tool_executor.execute(tool_name, **args)
        else:
            return await self.invoke(f"tool:{tool_name}", args)
    
    async def _continue_reasoning(
        self,
        original_prompt: str,
        tool_results: List[Any]
    ) -> Any:
        """Continue LLM reasoning with tool results."""
        if not self.llm_handler:
            return tool_results
        
        results_str = "\n".join(
            f"Tool result {i+1}: {r}"
            for i, r in enumerate(tool_results)
        )
        
        continuation = f"""{original_prompt}

Tool execution results:
{results_str}

Based on these results, provide your final response."""
        
        return await self.llm_handler.generate(
            prompt=continuation,
            system=self._build_system_prompt(),
        )


def load_agents_into_registry(
    directory: Path,
    registry: AgentRegistry
) -> int:
    """
    Load all agent specs from a directory into a registry.
    
    Returns the number of specs loaded.
    """
    specs = load_specs_from_directory(directory)
    
    for spec in specs:
        registry.register_spec(spec)
    
    return len(specs)


# === Built-in Agent Types ===

class EchoAgent(Agent):
    """Simple agent that echoes back intents. Useful for testing."""
    
    async def handle_intent(self, intent: str, args: Dict[str, Any]) -> Any:
        return {
            "echo": True,
            "intent": intent,
            "args": args,
            "agent_id": self.id,
        }


class ForwarderAgent(Agent):
    """Agent that forwards intents to another target. Useful for routing."""
    
    def __init__(self, target: str = "*", **kwargs):
        super().__init__(**kwargs)
        self.target = target
    
    async def handle_intent(self, intent: str, args: Dict[str, Any]) -> Any:
        return await self.invoke(intent, args)


class NotifierAgent(Agent):
    """
    Agent that sends notifications through available channels.
    
    This is one of the MVP agents - routes alerts to appropriate channels.
    """
    
    def __init__(self, channels: Optional[List[str]] = None, **kwargs):
        super().__init__(**kwargs)
        self.channels = channels or ["log"]
    
    async def handle_intent(self, intent: str, args: Dict[str, Any]) -> Any:
        if intent in ("notify", "send_notification", "alert"):
            return await self._send_notification(args)
        
        raise ValueError(f"Unknown intent: {intent}")
    
    async def _send_notification(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Send a notification."""
        message = args.get("message", "")
        recipient = args.get("recipient", "default")
        urgency = args.get("urgency", "medium")
        
        results = {}
        
        for channel in self.channels:
            if channel == "log":
                logger.info(f"[NOTIFICATION] {urgency.upper()}: {message} -> {recipient}")
                results["log"] = True
            elif channel == "console":
                print(f"📢 [{urgency}] {message}")
                results["console"] = True
            else:
                # Try to invoke channel-specific tool
                try:
                    result = await self.invoke(
                        f"send_{channel}",
                        {"message": message, "recipient": recipient}
                    )
                    results[channel] = result
                except Exception as e:
                    results[channel] = {"error": str(e)}
        
        return {
            "sent": True,
            "message": message,
            "recipient": recipient,
            "urgency": urgency,
            "channels": results,
        }


# Register built-in types
BUILTIN_AGENTS = {
    "echo": EchoAgent,
    "forwarder": ForwarderAgent,
    "notifier": NotifierAgent,
}
