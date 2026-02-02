"""
Tests for the Atmosphere Agent System.
"""

import asyncio
import pytest
import tempfile
from pathlib import Path

from atmosphere.agents.base import (
    Agent, AgentState, AgentMessage, MessageType,
    AgentSpec, ReactiveAgent
)
from atmosphere.agents.registry import AgentRegistry, AgentInfo
from atmosphere.agents.loader import (
    load_spec_from_yaml, SpecAgent, EchoAgent, NotifierAgent,
    BUILTIN_AGENTS
)


class TestAgentMessage:
    """Tests for AgentMessage."""
    
    def test_intent_message(self):
        """Test creating an intent message."""
        msg = AgentMessage.intent(
            from_agent="agent-1",
            to_agent="agent-2",
            intent="analyze_image",
            args={"image_url": "http://example.com/img.png"}
        )
        
        assert msg.type == MessageType.INTENT
        assert msg.from_agent == "agent-1"
        assert msg.to_agent == "agent-2"
        assert msg.payload["intent"] == "analyze_image"
        assert msg.payload["args"]["image_url"] == "http://example.com/img.png"
    
    def test_result_message(self):
        """Test creating a result message."""
        msg = AgentMessage.result(
            from_agent="agent-2",
            to_agent="agent-1",
            request_id="req-123",
            status="success",
            data={"objects_detected": 3}
        )
        
        assert msg.type == MessageType.RESULT
        assert msg.payload["status"] == "success"
        assert msg.payload["data"]["objects_detected"] == 3
    
    def test_serialization(self):
        """Test message serialization."""
        msg = AgentMessage.intent(
            from_agent="a",
            to_agent="b",
            intent="test",
        )
        
        data = msg.to_dict()
        restored = AgentMessage.from_dict(data)
        
        assert restored.id == msg.id
        assert restored.type == msg.type
        assert restored.payload == msg.payload


class TestAgentSpec:
    """Tests for AgentSpec."""
    
    def test_from_dict(self):
        """Test creating spec from dict."""
        spec = AgentSpec.from_dict({
            "id": "test_agent",
            "type": "reactive",
            "version": "1.0",
            "description": "A test agent",
            "triggers": [{"name": "test_trigger"}],
            "tools_required": ["tool1"],
        })
        
        assert spec.id == "test_agent"
        assert spec.type == "reactive"
        assert len(spec.triggers) == 1
        assert "tool1" in spec.tools_required
    
    def test_serialization(self):
        """Test spec serialization."""
        spec = AgentSpec(
            id="test",
            type="deliberative",
            version="2.0",
            description="Test",
            triggers=[{"name": "trigger1"}],
        )
        
        data = spec.to_dict()
        restored = AgentSpec.from_dict(data)
        
        assert restored.id == spec.id
        assert restored.type == spec.type


class TestAgent:
    """Tests for base Agent class."""
    
    @pytest.mark.asyncio
    async def test_agent_lifecycle(self):
        """Test agent start/stop lifecycle."""
        
        class SimpleAgent(Agent):
            async def handle_intent(self, intent, args):
                return {"handled": intent}
        
        agent = SimpleAgent(agent_id="test-1")
        
        assert agent.state == AgentState.CREATED
        
        await agent.start()
        assert agent.state == AgentState.RUNNING
        assert agent.started_at is not None
        
        await agent.stop("test stop")
        assert agent.state == AgentState.TERMINATED
        assert agent.stopped_at is not None
    
    @pytest.mark.asyncio
    async def test_agent_receive_message(self):
        """Test agent receiving and handling messages."""
        
        handled = []
        
        class TrackingAgent(Agent):
            async def handle_intent(self, intent, args):
                handled.append((intent, args))
                return {"ok": True}
        
        agent = TrackingAgent(agent_id="test-2")
        await agent.start()
        
        # Send a message
        msg = AgentMessage.intent(
            from_agent="test",
            to_agent="test-2",
            intent="do_something",
            args={"value": 42}
        )
        await agent.receive(msg)
        
        # Give time to process
        await asyncio.sleep(0.1)
        
        assert len(handled) == 1
        assert handled[0][0] == "do_something"
        assert handled[0][1]["value"] == 42
        
        await agent.stop()
    
    @pytest.mark.asyncio
    async def test_agent_suspend_resume(self):
        """Test agent suspend and resume."""
        
        class StatefulAgent(Agent):
            async def handle_intent(self, intent, args):
                self.context["counter"] = self.context.get("counter", 0) + 1
                return {"counter": self.context["counter"]}
        
        agent = StatefulAgent(agent_id="test-3")
        agent.context["counter"] = 5
        
        await agent.start()
        
        # Suspend
        state = await agent.suspend()
        assert agent.state == AgentState.SUSPENDED
        assert state["context"]["counter"] == 5
        
        # Resume
        await agent.resume(state)
        assert agent.state == AgentState.RUNNING
        assert agent.context["counter"] == 5
        
        await agent.stop()


class TestReactiveAgent:
    """Tests for ReactiveAgent."""
    
    @pytest.mark.asyncio
    async def test_rule_handling(self):
        """Test reactive agent with rules."""
        
        agent = ReactiveAgent(agent_id="reactive-1")
        
        # Add rules
        agent.add_rule("greet", lambda args: f"Hello, {args.get('name', 'world')}!")
        agent.add_rule("add", lambda args: args.get("a", 0) + args.get("b", 0))
        
        await agent.start()
        
        # Test rules via direct call (bypass message queue)
        result = await agent.handle_intent("greet", {"name": "Alice"})
        assert result == "Hello, Alice!"
        
        result = await agent.handle_intent("add", {"a": 5, "b": 3})
        assert result == 8
        
        await agent.stop()
    
    @pytest.mark.asyncio
    async def test_async_rule(self):
        """Test reactive agent with async rule."""
        
        agent = ReactiveAgent(agent_id="reactive-2")
        
        async def async_handler(args):
            await asyncio.sleep(0.01)
            return args.get("value", 0) * 2
        
        agent.add_rule("double", async_handler)
        
        await agent.start()
        
        result = await agent.handle_intent("double", {"value": 21})
        assert result == 42
        
        await agent.stop()


class TestAgentRegistry:
    """Tests for AgentRegistry."""
    
    @pytest.mark.asyncio
    async def test_register_agent(self):
        """Test registering an agent."""
        registry = AgentRegistry(node_id="test-node")
        agent = EchoAgent(agent_id="echo-1")
        
        await registry.register(agent)
        
        assert registry.get("echo-1") is agent
        assert len(registry.list_local()) == 1
    
    @pytest.mark.asyncio
    async def test_spawn_agent(self):
        """Test spawning an agent from factory."""
        registry = AgentRegistry(node_id="test-node")
        registry.register_factory("echo", EchoAgent)
        
        agent_id = await registry.spawn("echo")
        
        agent = registry.get(agent_id)
        assert agent is not None
        assert agent.is_running
        
        await registry.terminate(agent_id)
    
    @pytest.mark.asyncio
    async def test_spawn_from_spec(self):
        """Test spawning an agent from spec."""
        registry = AgentRegistry(node_id="test-node")
        
        spec = AgentSpec(
            id="test_spec",
            type="reactive",
            version="1.0",
            description="Test spec agent",
            triggers=[{"name": "test_trigger"}],
        )
        registry.register_spec(spec)
        
        agent_id = await registry.spawn("test_spec")
        
        agent = registry.get(agent_id)
        assert agent is not None
        assert isinstance(agent, SpecAgent)
        
        await registry.terminate(agent_id)
    
    @pytest.mark.asyncio
    async def test_sleep_wake(self):
        """Test sleep and wake functionality with spec-based agent."""
        registry = AgentRegistry(node_id="test-node")
        
        # Register a spec so the agent can be woken
        spec = AgentSpec(
            id="sleepy_agent",
            type="reactive",
            version="1.0",
            description="An agent that can sleep",
            triggers=[{"name": "wake_up"}],
        )
        registry.register_spec(spec)
        
        agent_id = await registry.spawn("sleepy_agent")
        agent = registry.get(agent_id)
        agent.context["important"] = "data"
        
        # Sleep
        assert await registry.sleep(agent_id)
        assert agent_id not in [a.id for a in registry.list_local()]
        assert agent_id in registry.list_sleeping()
        
        # Wake
        assert await registry.wake(agent_id)
        woken = registry.get(agent_id)
        assert woken is not None
        assert woken.context.get("important") == "data"
        
        await registry.terminate(agent_id)
    
    def test_find_for_intent(self):
        """Test finding agents for an intent."""
        registry = AgentRegistry(node_id="test-node")
        
        spec = AgentSpec(
            id="image_analyzer",
            type="reactive",
            version="1.0",
            description="Analyzes images for objects and content",
            triggers=[
                {"name": "analyze_image"},
                {"name": "detect_objects"},
            ],
        )
        registry.register_spec(spec)
        
        # Add fake agent info
        info = AgentInfo(
            id="analyzer-1",
            agent_type="image_analyzer",
            node_id="test-node",
            state="running",
            description="Analyzes images for objects and content",
            triggers=["analyze_image", "detect_objects"],
        )
        registry._remote_agents["analyzer-1"] = info
        
        # Find by trigger name
        matches = registry.find_for_intent("analyze_image")
        assert len(matches) > 0
        
        # Find by description match
        matches = registry.find_for_intent("image analysis")
        assert len(matches) > 0
    
    def test_list_types(self):
        """Test listing available agent types."""
        registry = AgentRegistry(node_id="test-node")
        registry.register_factory("echo", EchoAgent)
        
        spec = AgentSpec(id="spec_agent", type="reactive", version="1.0", description="")
        registry.register_spec(spec)
        
        types = registry.list_types()
        assert "echo" in types
        assert "spec_agent" in types
    
    def test_persistence(self):
        """Test saving and loading registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "registry.json"
            
            # Create and populate registry
            registry1 = AgentRegistry(node_id="test-node")
            spec = AgentSpec(
                id="test_agent",
                type="reactive",
                version="1.0",
                description="Test",
            )
            registry1.register_spec(spec)
            registry1.save(path)
            
            # Load into new registry
            registry2 = AgentRegistry.load(path, "test-node")
            
            assert "test_agent" in registry2.list_types()
            assert registry2.get_spec("test_agent") is not None


class TestSpecLoader:
    """Tests for spec loading from YAML."""
    
    def test_load_spec_from_yaml(self):
        """Test loading a spec from YAML."""
        yaml_content = """
agent:
  id: my_agent
  version: "1.0"
  type: reactive
  description: |
    A test agent for unit testing.
  triggers:
    - name: test_trigger
      description: Fires on test events
      params:
        value: integer
  tools:
    required:
      - query_sensor
    optional:
      - notify
  default_params:
    threshold: 0.5
  instructions: |
    When triggered, check the value and notify if above threshold.
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            path = Path(f.name)
        
        try:
            spec = load_spec_from_yaml(path)
            
            assert spec.id == "my_agent"
            assert spec.version == "1.0"
            assert spec.type == "reactive"
            assert "test agent" in spec.description.lower()
            assert len(spec.triggers) == 1
            assert spec.triggers[0]["name"] == "test_trigger"
            assert "query_sensor" in spec.tools_required
            assert "notify" in spec.tools_optional
            assert spec.default_params["threshold"] == 0.5
        finally:
            path.unlink()


class TestEchoAgent:
    """Tests for EchoAgent."""
    
    @pytest.mark.asyncio
    async def test_echo(self):
        """Test echo agent returns intent."""
        agent = EchoAgent(agent_id="echo-test")
        await agent.start()
        
        result = await agent.handle_intent("test_intent", {"key": "value"})
        
        assert result["echo"] is True
        assert result["intent"] == "test_intent"
        assert result["args"]["key"] == "value"
        assert result["agent_id"] == "echo-test"
        
        await agent.stop()


class TestNotifierAgent:
    """Tests for NotifierAgent."""
    
    @pytest.mark.asyncio
    async def test_notify(self):
        """Test notifier agent sends notification."""
        agent = NotifierAgent(agent_id="notifier-test", channels=["log"])
        await agent.start()
        
        result = await agent.handle_intent("notify", {
            "message": "Test notification",
            "recipient": "test@example.com",
            "urgency": "high"
        })
        
        assert result["sent"] is True
        assert result["message"] == "Test notification"
        assert result["urgency"] == "high"
        assert "log" in result["channels"]
        
        await agent.stop()


class TestAgentInfo:
    """Tests for AgentInfo."""
    
    def test_from_agent(self):
        """Test creating AgentInfo from agent."""
        agent = EchoAgent(agent_id="info-test")
        info = AgentInfo.from_agent(agent, "node-1")
        
        assert info.id == "info-test"
        assert info.node_id == "node-1"
        assert info.state == AgentState.CREATED.value
    
    def test_serialization(self):
        """Test AgentInfo serialization."""
        info = AgentInfo(
            id="test-1",
            agent_type="echo",
            node_id="node-1",
            state="running",
            description="Test agent",
            triggers=["trigger1"],
        )
        
        data = info.to_dict()
        restored = AgentInfo.from_dict(data)
        
        assert restored.id == info.id
        assert restored.triggers == info.triggers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
