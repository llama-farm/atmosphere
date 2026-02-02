"""
Semantic routing for Atmosphere.

Routes intents to the best available capability using
embedding-based similarity matching.

Also provides:
- FastProjectRouter for sub-millisecond project routing
- OpenAI-compatible API endpoints
- Gossip integration for distributed routing tables
"""

from .semantic import SemanticRouter, RouteResult
from .gradient import GradientTable, GradientEntry
from .embeddings import EmbeddingEngine
from .executor import Executor, ExecutionResult
from .fast_router import FastProjectRouter, ProjectEntry, RouteResult as FastRouteResult, get_fast_router
from .openai_compat import openai_router

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
    # OpenAI-compatible API router
    "openai_router",
]
