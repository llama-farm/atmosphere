"""
Semantic routing for Atmosphere.

Routes intents to the best available capability using
embedding-based similarity matching.

Also provides:
- FastProjectRouter for sub-millisecond project routing
- OpenAI-compatible API endpoints
- TriggerRouter for event-driven capability routing
- Gossip integration for distributed routing tables
"""

from .semantic import SemanticRouter, RouteResult
from .gradient import GradientTable, GradientEntry
from .embeddings import EmbeddingEngine
from .executor import Executor, ExecutionResult
from .fast_router import FastProjectRouter, ProjectEntry, RouteResult as FastRouteResult, get_fast_router
from .openai_compat import openai_router
from .trigger_router import (
    TriggerRouter,
    TriggerPriority,
    Intent,
    TriggerResult,
    ThrottleTracker,
    get_trigger_router,
    reset_trigger_router,
    fire_trigger,
)

__all__ = [
    # Semantic routing (capability-based)
    "SemanticRouter",
    "RouteResult",
    "GradientTable",
    "GradientEntry",
    "EmbeddingEngine",
    "Executor",
    "ExecutionResult",
    # Fast project routing (LlamaFarm)
    "FastProjectRouter",
    "ProjectEntry",
    "FastRouteResult",
    "get_fast_router",
    # Trigger routing (event-driven)
    "TriggerRouter",
    "TriggerPriority",
    "Intent",
    "TriggerResult",
    "ThrottleTracker",
    "get_trigger_router",
    "reset_trigger_router",
    "fire_trigger",
    # OpenAI-compatible API router
    "openai_router",
]
