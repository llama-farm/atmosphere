"""
Atmosphere Agent System.

Agents are stateful entities that receive intents, make decisions, and take actions.
They can be distributed across the mesh and communicate via gossip-synced registries.
"""

from .base import (
    Agent,
    AgentState,
    AgentMessage,
    MessageType,
    AgentSpec,
    ReactiveAgent,
    DelegatingAgent,
)
from .registry import (
    AgentRegistry,
    AgentInfo,
    AgentTypeInfo,
    get_registry,
    set_registry,
)
from .loader import (
    load_spec_from_yaml,
    load_specs_from_directory,
    load_agents_into_registry,
    SpecAgent,
    EchoAgent,
    NotifierAgent,
    ForwarderAgent,
    BUILTIN_AGENTS,
)
from .gossip import AgentGossip, AgentAnnouncement, integrate_with_gossip

__all__ = [
    # Base
    "Agent",
    "AgentState",
    "AgentMessage",
    "MessageType",
    "AgentSpec",
    "ReactiveAgent",
    "DelegatingAgent",
    # Registry
    "AgentRegistry",
    "AgentInfo",
    "AgentTypeInfo",
    "get_registry",
    "set_registry",
    # Loader
    "load_spec_from_yaml",
    "load_specs_from_directory",
    "load_agents_into_registry",
    "SpecAgent",
    "EchoAgent",
    "NotifierAgent",
    "ForwarderAgent",
    "BUILTIN_AGENTS",
    # Gossip
    "AgentGossip",
    "AgentAnnouncement",
    "integrate_with_gossip",
]
