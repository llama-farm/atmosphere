"""
Capability Announcement Schema

The core data structure gossiped across the mesh.
Every node announces its capabilities; other nodes use this for routing.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# Re-use existing cost factors
from ..cost.collector import NodeCostFactors


class ModelTier(Enum):
    """Model capability tier based on parameter count."""
    TINY = "tiny"      # < 2B params
    SMALL = "small"    # 2-4B params
    MEDIUM = "medium"  # 7-14B params
    LARGE = "large"    # 30-34B params
    XL = "xl"          # 70B+ params
    
    @classmethod
    def from_params(cls, params_billions: float) -> "ModelTier":
        """Determine tier from parameter count."""
        if params_billions < 2:
            return cls.TINY
        elif params_billions < 5:
            return cls.SMALL
        elif params_billions < 20:
            return cls.MEDIUM
        elif params_billions < 50:
            return cls.LARGE
        else:
            return cls.XL
    
    @classmethod
    def from_model_name(cls, model_name: str) -> "ModelTier":
        """
        Extract tier from model name.
        
        Examples:
        - "unsloth/Qwen3-1.7B-GGUF" → TINY
        - "llama3-8b" → MEDIUM
        - "mistral-7b-instruct" → MEDIUM
        - "llama3-70b" → XL
        """
        name_lower = model_name.lower()
        
        # Extract parameter count from name
        patterns = [
            (r'(\d+\.?\d*)b', 1.0),      # "7b", "1.7b"
            (r'(\d+)m', 0.001),           # "350m" = 0.35B
        ]
        
        for pattern, multiplier in patterns:
            match = re.search(pattern, name_lower)
            if match:
                params = float(match.group(1)) * multiplier
                return cls.from_params(params)
        
        # Fallback heuristics
        if any(x in name_lower for x in ['tiny', 'mini', 'small']):
            return cls.TINY
        elif any(x in name_lower for x in ['medium', 'base']):
            return cls.MEDIUM
        elif any(x in name_lower for x in ['large', 'xl', 'xxl']):
            return cls.LARGE
        
        return cls.MEDIUM  # Default assumption


class CapabilityType(Enum):
    """Capability categories."""
    # Language
    LLM_CHAT = "llm/chat"
    LLM_COMPLETE = "llm/complete"
    LLM_EMBED = "llm/embed"
    
    # Audio
    AUDIO_TRANSCRIBE = "audio/transcribe"
    AUDIO_GENERATE = "audio/generate"
    
    # Vision
    VISION_ANALYZE = "vision/analyze"
    VISION_GENERATE = "vision/generate"
    SENSOR_CAMERA = "sensor/camera"
    
    # IoT
    IOT_SENSOR = "iot/sensor"
    IOT_ACTUATOR = "iot/actuator"
    
    # Agents
    AGENT_TASK = "agent/task"
    AGENT_TOOL = "agent/tool"
    
    # Actions
    ACTION_NOTIFY = "action/notify"
    ACTION_STORE = "action/store"


# Good-for / Not-good-for task categories
TASK_CATEGORIES = {
    "simple_qa": "Simple question answering",
    "classification": "Text classification, sentiment",
    "extraction": "Entity extraction, parsing",
    "summarization": "Text summarization",
    "translation": "Language translation",
    "code_simple": "Simple code completion",
    "code_complex": "Complex code generation",
    "reasoning": "Multi-step reasoning",
    "math": "Mathematical computation",
    "agents": "Agentic tool use",
    "creative": "Creative writing",
    "analysis": "Deep analysis",
    "rag": "Knowledge retrieval QA",
}


@dataclass
class CapabilityAnnouncement:
    """
    Complete capability description for mesh routing.
    
    This is what gets gossiped between nodes.
    """
    
    # === IDENTITY ===
    node_id: str                    # Ed25519 public key hash
    node_name: str                  # Human-readable name
    capability_id: str              # Unique: "{node_id}:{project_path}:{model_alias}"
    
    # === PROJECT ROUTING ===
    project_path: str               # "llamafarm/discoverable/llama-expert-14"
    model_alias: str                # "default" - what API calls use
    
    # === MODEL METADATA ===
    model_actual: str               # "unsloth/Qwen3-1.7B-GGUF:Q4_K_M"
    model_family: str               # "qwen3", "llama3", "mistral"
    model_params_b: float           # Parameter count in billions
    model_quantization: str         # "Q4_K_M", "fp16", "int8"
    model_tier: ModelTier           # Derived from params
    
    # === CAPABILITY TYPE ===
    capability_type: CapabilityType
    triggers: List[str] = field(default_factory=list)  # Events this emits
    tools: List[str] = field(default_factory=list)     # Functions to call
    
    # === SEMANTIC MATCHING ===
    label: str = ""                 # Human-readable label
    description: str = ""           # Description for embedding
    embedding: Optional[List[float]] = None  # 384-dim vector
    embedding_hash: int = 0         # 64-bit SimHash for cross-platform matching
    keywords: List[str] = field(default_factory=list)
    
    # === INTELLIGENCE PROFILE ===
    good_for: List[str] = field(default_factory=list)     # Task categories
    not_good_for: List[str] = field(default_factory=list)
    has_rag: bool = False
    has_vision: bool = False
    has_tools: bool = False
    has_streaming: bool = True
    context_length: int = 4096
    specializations: List[str] = field(default_factory=list)
    
    # === COST FACTORS ===
    cost_factors: Optional[NodeCostFactors] = None
    estimated_latency_ms: float = 100.0
    tokens_per_second: float = 50.0
    api_cost_per_1k_tokens: float = 0.0  # 0 = local/free
    
    # === ROUTING METADATA ===
    hops: int = 0                   # 0 = local
    via_node: Optional[str] = None
    ttl: int = 10
    timestamp: float = field(default_factory=time.time)
    expires_at: float = 0.0         # Set on creation
    
    # === SECURITY ===
    signature: str = ""             # Ed25519 signature
    
    def __post_init__(self):
        """Compute derived fields."""
        # Set expiry (5 minutes)
        if self.expires_at == 0.0:
            self.expires_at = self.timestamp + 300
        
        # Extract keywords from description if not provided
        if not self.keywords and self.description:
            self.keywords = self._extract_keywords()
        
        # Compute SimHash from description/keywords (not embeddings)
        # SimHash is used for cross-platform capability matching
        if self.embedding_hash == 0 and (self.description or self.keywords or self.label):
            self.embedding_hash = self._compute_simhash()
        
        # Derive good_for/not_good_for from tier if not set
        if not self.good_for:
            self._set_tier_defaults()
    
    def _compute_simhash(self) -> int:
        """
        Compute 64-bit SimHash for cross-platform capability matching.
        
        Uses the unified SimHash algorithm that produces identical results
        on Python and Kotlin/Android. SimHash is locality-sensitive, meaning
        similar descriptions produce hashes with high Hamming similarity.
        
        Falls back to keywords if no description is available.
        """
        # Import here to avoid circular dependency
        from ..router.simhash import compute_simhash, compute_simhash_from_tokens
        
        # Prefer description for SimHash (richer text)
        if self.description:
            return compute_simhash(f"{self.label} {self.description}")
        
        # Fall back to keywords
        if self.keywords:
            return compute_simhash_from_tokens(self.keywords)
        
        # Fall back to label only
        if self.label:
            return compute_simhash(self.label)
        
        return 0
    
    def _extract_keywords(self) -> List[str]:
        """Extract keywords from description."""
        # Simple keyword extraction
        text = f"{self.label} {self.description}".lower()
        # Remove common words
        stopwords = {'the', 'a', 'an', 'is', 'are', 'and', 'or', 'for', 'to', 'of', 'in', 'on', 'with'}
        words = re.findall(r'\b[a-z]{3,}\b', text)
        keywords = [w for w in words if w not in stopwords]
        # Return unique, sorted
        return sorted(set(keywords))[:20]
    
    def _set_tier_defaults(self):
        """Set good_for/not_good_for based on model tier."""
        tier_capabilities = {
            ModelTier.TINY: {
                "good_for": ["simple_qa", "classification", "extraction"],
                "not_good_for": ["reasoning", "agents", "code_complex", "analysis"],
            },
            ModelTier.SMALL: {
                "good_for": ["simple_qa", "classification", "extraction", "summarization"],
                "not_good_for": ["reasoning", "agents", "code_complex"],
            },
            ModelTier.MEDIUM: {
                "good_for": ["simple_qa", "classification", "extraction", "summarization", 
                            "translation", "code_simple", "rag"],
                "not_good_for": ["reasoning", "analysis"],
            },
            ModelTier.LARGE: {
                "good_for": ["simple_qa", "classification", "extraction", "summarization",
                            "translation", "code_simple", "code_complex", "rag", "agents"],
                "not_good_for": [],
            },
            ModelTier.XL: {
                "good_for": list(TASK_CATEGORIES.keys()),  # Everything
                "not_good_for": [],
            },
        }
        
        defaults = tier_capabilities.get(self.model_tier, {})
        self.good_for = defaults.get("good_for", [])
        self.not_good_for = defaults.get("not_good_for", [])
    
    def is_expired(self) -> bool:
        """Check if this capability has expired."""
        return time.time() > self.expires_at
    
    def similarity_hash(self, other_hash: int) -> float:
        """
        Compute Hamming similarity between SimHashes.
        
        SimHash is locality-sensitive, so similar texts produce hashes
        with high Hamming similarity (few differing bits).
        
        Returns value in [0, 1] where:
        - 1.0 = identical hashes (0 bits differ)
        - 0.0 = completely different (64 bits differ)
        
        Typical thresholds:
        - >= 0.70: Similar (19 or fewer bits differ)
        - >= 0.85: Very similar (9 or fewer bits differ)
        - >= 0.95: Nearly identical (3 or fewer bits differ)
        """
        from ..router.simhash import simhash_similarity
        return simhash_similarity(self.embedding_hash, other_hash)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON/gossip."""
        return {
            # Identity
            "node_id": self.node_id,
            "node_name": self.node_name,
            "capability_id": self.capability_id,
            
            # Project
            "project_path": self.project_path,
            "model_alias": self.model_alias,
            
            # Model
            "model_actual": self.model_actual,
            "model_family": self.model_family,
            "model_params_b": self.model_params_b,
            "model_quantization": self.model_quantization,
            "model_tier": self.model_tier.value,
            
            # Type
            "capability_type": self.capability_type.value,
            "triggers": self.triggers,
            "tools": self.tools,
            
            # Semantic
            "label": self.label,
            "description": self.description,
            "embedding": self.embedding,
            "embedding_hash": self.embedding_hash,
            "keywords": self.keywords,
            
            # Intelligence
            "good_for": self.good_for,
            "not_good_for": self.not_good_for,
            "has_rag": self.has_rag,
            "has_vision": self.has_vision,
            "has_tools": self.has_tools,
            "has_streaming": self.has_streaming,
            "context_length": self.context_length,
            "specializations": self.specializations,
            
            # Cost
            "cost_factors": self.cost_factors.to_dict() if self.cost_factors else None,
            "estimated_latency_ms": self.estimated_latency_ms,
            "tokens_per_second": self.tokens_per_second,
            "api_cost_per_1k_tokens": self.api_cost_per_1k_tokens,
            
            # Routing
            "hops": self.hops,
            "via_node": self.via_node,
            "ttl": self.ttl,
            "timestamp": self.timestamp,
            "expires_at": self.expires_at,
            
            # Security
            "signature": self.signature,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityAnnouncement":
        """Deserialize from JSON/gossip."""
        cost_factors = None
        if data.get("cost_factors"):
            cost_factors = NodeCostFactors.from_dict(data["cost_factors"])
        
        return cls(
            # Identity
            node_id=data["node_id"],
            node_name=data["node_name"],
            capability_id=data["capability_id"],
            
            # Project
            project_path=data["project_path"],
            model_alias=data["model_alias"],
            
            # Model
            model_actual=data["model_actual"],
            model_family=data["model_family"],
            model_params_b=data["model_params_b"],
            model_quantization=data.get("model_quantization", ""),
            model_tier=ModelTier(data["model_tier"]),
            
            # Type
            capability_type=CapabilityType(data["capability_type"]),
            triggers=data.get("triggers", []),
            tools=data.get("tools", []),
            
            # Semantic
            label=data.get("label", ""),
            description=data.get("description", ""),
            embedding=data.get("embedding"),
            embedding_hash=data.get("embedding_hash", 0),
            keywords=data.get("keywords", []),
            
            # Intelligence
            good_for=data.get("good_for", []),
            not_good_for=data.get("not_good_for", []),
            has_rag=data.get("has_rag", False),
            has_vision=data.get("has_vision", False),
            has_tools=data.get("has_tools", False),
            has_streaming=data.get("has_streaming", True),
            context_length=data.get("context_length", 4096),
            specializations=data.get("specializations", []),
            
            # Cost
            cost_factors=cost_factors,
            estimated_latency_ms=data.get("estimated_latency_ms", 100.0),
            tokens_per_second=data.get("tokens_per_second", 50.0),
            api_cost_per_1k_tokens=data.get("api_cost_per_1k_tokens", 0.0),
            
            # Routing
            hops=data.get("hops", 0),
            via_node=data.get("via_node"),
            ttl=data.get("ttl", 10),
            timestamp=data.get("timestamp", time.time()),
            expires_at=data.get("expires_at", 0.0),
            
            # Security
            signature=data.get("signature", ""),
        )
    
    @classmethod
    def from_llamafarm_project(
        cls,
        node_id: str,
        node_name: str,
        namespace: str,
        project_name: str,
        project_config: Dict[str, Any],
        cost_factors: Optional[NodeCostFactors] = None,
    ) -> List["CapabilityAnnouncement"]:
        """
        Create capability announcements from a LlamaFarm project config.
        
        Returns one announcement per model in the project.
        """
        announcements = []
        
        project_path = f"llamafarm/{namespace}/{project_name}"
        # Check project description first, then fall back to model descriptions
        description = project_config.get("description", "")
        topics = project_config.get("topics", [])
        
        # Check for RAG
        has_rag = bool(project_config.get("rag") or project_config.get("retrieval"))
        
        runtime = project_config.get("runtime", {})
        models = runtime.get("models", [])
        
        for model_cfg in models:
            model_alias = model_cfg.get("name", "default")
            model_actual = model_cfg.get("model", "")
            
            # Extract model family and params
            model_family = cls._extract_model_family(model_actual)
            model_tier = ModelTier.from_model_name(model_actual)
            model_params = cls._extract_params(model_actual)
            
            # Extract quantization
            quant = ""
            if ":" in model_actual:
                parts = model_actual.split(":")
                if len(parts) > 1:
                    quant = parts[-1]
            
            capability_id = f"{node_id}:{project_path}:{model_alias}"
            
            # Use model description if project description is empty
            model_description = model_cfg.get("description", "")
            effective_description = description or model_description
            
            # Generate keywords from various sources
            generated_keywords = list(topics) if topics else []
            
            # Add model family
            if model_family:
                generated_keywords.append(model_family.lower())
            
            # Add keywords from project name (split on - and _)
            for word in project_name.replace("-", " ").replace("_", " ").split():
                if len(word) > 2 and word.lower() not in generated_keywords:
                    generated_keywords.append(word.lower())
            
            # Extract domain-specific keywords from model description
            # This is critical for routing differentiation
            if effective_description:
                desc_stopwords = {
                    'the', 'a', 'an', 'is', 'are', 'and', 'or', 'for', 'to',
                    'of', 'in', 'on', 'with', 'that', 'this', 'from', 'by',
                    'as', 'at', 'be', 'has', 'had', 'have', 'was', 'were',
                    'will', 'can', 'may', 'its', 'all', 'but', 'not', 'use',
                    'using', 'used', 'about', 'such', 'than', 'also', 'into',
                    'over', 'after', 'before', 'between', 'through', 'during',
                    'expert', 'specializing', 'assistant', 'model', 'general',
                    'purpose', 'best',
                }
                desc_words = re.findall(r'\b[a-zA-Z]{3,}\b', effective_description.lower())
                for w in desc_words:
                    if w not in desc_stopwords and w not in generated_keywords:
                        generated_keywords.append(w)
            
            # Add general capability keywords (at the end, lower priority)
            generated_keywords.extend(["llm", "chat", "ai"])
            if has_rag:
                generated_keywords.extend(["rag", "retrieval", "knowledge"])
            
            # Generate description if empty
            generated_description = effective_description or f"LLM capability: {project_name} using {model_family} ({model_tier.value})"
            
            ann = cls(
                node_id=node_id,
                node_name=node_name,
                capability_id=capability_id,
                project_path=project_path,
                model_alias=model_alias,
                model_actual=model_actual,
                model_family=model_family,
                model_params_b=model_params,
                model_quantization=quant,
                model_tier=model_tier,
                capability_type=CapabilityType.LLM_CHAT,
                label=f"{project_name} ({model_alias})",
                description=generated_description,
                keywords=generated_keywords,
                has_rag=has_rag,
                has_streaming=True,
                context_length=model_cfg.get("context_length", 4096),
                specializations=topics,
                cost_factors=cost_factors,
                tokens_per_second=model_cfg.get("tokens_per_second", 50.0),
            )
            
            announcements.append(ann)
        
        return announcements
    
    @staticmethod
    def _extract_model_family(model_name: str) -> str:
        """Extract model family from name."""
        name_lower = model_name.lower()
        
        families = [
            "qwen", "llama", "mistral", "phi", "gemma", "mixtral",
            "whisper", "stable-diffusion", "flux", "claude", "gpt",
        ]
        
        for family in families:
            if family in name_lower:
                # Get version if present (e.g., qwen3, llama3)
                match = re.search(rf'{family}(\d*)', name_lower)
                if match and match.group(1):
                    return f"{family}{match.group(1)}"
                return family
        
        return "unknown"
    
    @staticmethod
    def _extract_params(model_name: str) -> float:
        """Extract parameter count in billions from model name."""
        name_lower = model_name.lower()
        
        # Try to find "XB" pattern
        match = re.search(r'(\d+\.?\d*)b', name_lower)
        if match:
            return float(match.group(1))
        
        # Try "XM" pattern (millions)
        match = re.search(r'(\d+)m', name_lower)
        if match:
            return float(match.group(1)) / 1000
        
        return 7.0  # Default assumption
