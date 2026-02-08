"""
Intent Classification for Semantic Router v2.

Classifies user intents into complexity levels and task types
to enable optimal model selection and routing.

This runs ON-DEVICE (<2ms) before any network calls.
"""
import re
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Set

logger = logging.getLogger(__name__)


class Complexity(Enum):
    """Complexity levels determine model size needed."""
    TRIVIAL = 1    # <1B params - math, greetings, simple facts
    SIMPLE = 2     # 1-3B params - single-step questions
    MODERATE = 3   # 3-7B params - explanations, comparisons
    COMPLEX = 4    # 7-14B params - analysis, creative, code
    EXPERT = 5     # 14B+ or agent - research, multi-step


class TaskType(Enum):
    """Task types determine capability requirements."""
    QA = "qa"                  # Simple question answering
    CHAT = "chat"              # Conversational
    REASONING = "reasoning"    # Multi-step reasoning
    RESEARCH = "research"      # Deep research, multiple sources
    AGENTIC = "agentic"        # Requires tools/actions
    CODE = "code"              # Code generation/execution
    CREATIVE = "creative"      # Creative writing
    VISION = "vision"          # Image understanding
    AUDIO = "audio"            # Audio/speech tasks


class Domain(Enum):
    """Domain specializations for targeted routing."""
    GENERAL = "general"
    MEDICAL = "medical"
    LEGAL = "legal"
    TECHNICAL = "technical"
    FINANCIAL = "financial"
    SCIENTIFIC = "scientific"
    CREATIVE = "creative"


@dataclass
class IntentClassification:
    """Result of intent classification."""
    complexity: Complexity
    task_type: TaskType
    domain: Domain = Domain.GENERAL
    
    # Requirements
    needs_tools: bool = False
    needs_rag: bool = False
    needs_vision: bool = False
    needs_code: bool = False
    needs_streaming: bool = False
    
    # Expected characteristics
    expected_length: str = "medium"  # short, medium, long, unlimited
    confidence: float = 0.8
    
    # Debug info
    matched_patterns: List[str] = None
    
    def __post_init__(self):
        if self.matched_patterns is None:
            self.matched_patterns = []
    
    def to_dict(self) -> dict:
        return {
            "complexity": self.complexity.name,
            "complexity_value": self.complexity.value,
            "task_type": self.task_type.value,
            "domain": self.domain.value,
            "needs_tools": self.needs_tools,
            "needs_rag": self.needs_rag,
            "needs_vision": self.needs_vision,
            "needs_code": self.needs_code,
            "needs_streaming": self.needs_streaming,
            "expected_length": self.expected_length,
            "confidence": self.confidence,
            "matched_patterns": self.matched_patterns,
        }
    
    @property
    def recommended_model_size(self) -> str:
        """Map complexity to recommended model size."""
        return {
            Complexity.TRIVIAL: "tiny (<1B)",
            Complexity.SIMPLE: "small (1-3B)",
            Complexity.MODERATE: "medium (3-7B)",
            Complexity.COMPLEX: "large (7-14B)",
            Complexity.EXPERT: "xlarge (14B+) or agent",
        }[self.complexity]


class IntentClassifier:
    """
    Fast, on-device intent classifier.
    
    Uses a hybrid approach:
    1. Regex patterns for instant matching (~0.1ms)
    2. Keyword analysis for complexity/type detection (~0.5ms)
    3. Optional embedding similarity for uncertain cases (~1ms)
    
    Total: <2ms for most inputs
    """
    
    def __init__(self):
        # === TRIVIAL PATTERNS (instant match) ===
        self.trivial_patterns = [
            # Math expressions
            (r'^\d+\s*[\+\-\*\/\^]\s*\d+[\s\?]*$', "math_simple"),
            (r'^what\s+is\s+\d+\s*[\+\-\*\/]\s*\d+', "math_question"),
            (r'^(sqrt|square root|cube root)\s*\(?(\d+)\)?', "math_function"),
            
            # Greetings
            (r'^(hi|hello|hey|howdy|greetings|yo)\s*[!?.]*$', "greeting"),
            (r'^good\s+(morning|afternoon|evening|night)\s*[!?.]*$', "greeting"),
            
            # Simple facts (single word answers expected)
            (r'^what\s+(color|colour)\s+is\s+the\s+sky', "trivial_fact"),
            (r'^how\s+many\s+(days|months)\s+in\s+a\s+(year|week)', "trivial_fact"),
            (r'^what\s+is\s+the\s+capital\s+of\s+\w+', "simple_fact"),
        ]
        
        # === COMPLEXITY KEYWORDS ===
        self.complexity_keywords = {
            Complexity.TRIVIAL: {
                'hi', 'hello', 'hey', 'thanks', 'thank you', 'bye', 'goodbye',
                'yes', 'no', 'sure', 'yeah'
                # Note: 'ok' and 'okay' removed - too common in other contexts
            },
            Complexity.SIMPLE: {
                'what is', 'who is', 'when is', 'where is', 'how many',
                'define', 'meaning of', 'translate', 'convert'
            },
            Complexity.MODERATE: {
                'explain', 'describe', 'how does', 'why does', 'what happens',
                'compare', 'difference between', 'summarize', 'list'
            },
            Complexity.COMPLEX: {
                'analyze', 'evaluate', 'design', 'create', 'write',
                'develop', 'implement', 'build', 'generate', 'compose'
            },
            Complexity.EXPERT: {
                'research', 'investigate', 'comprehensive', 'in-depth',
                'multi-step', 'plan for', 'strategy', 'architecture'
            }
        }
        
        # === TASK TYPE INDICATORS ===
        self.task_indicators = {
            TaskType.CODE: {
                'code', 'function', 'script', 'program', 'debug', 'fix bug',
                'python', 'javascript', 'java', 'sql', 'html', 'css',
                'algorithm', 'implement', 'refactor', 'optimize code'
            },
            TaskType.CREATIVE: {
                'poem', 'story', 'write a', 'compose', 'creative',
                'song', 'lyrics', 'fiction', 'haiku', 'limerick',
                'narrative', 'essay', 'blog post'
            },
            TaskType.RESEARCH: {
                'research', 'investigate', 'find sources', 'academic',
                'paper', 'study', 'literature review', 'cite'
            },
            TaskType.AGENTIC: {
                'book', 'schedule', 'send', 'email', 'call', 'order',
                'buy', 'purchase', 'reserve', 'search for', 'find me',
                'set reminder', 'create event', 'add to'
            },
            TaskType.REASONING: {
                'why', 'how come', 'reason', 'logic', 'deduce',
                'infer', 'conclude', 'prove', 'solve', 'figure out'
            },
        }
        
        # === TOOL REQUIREMENTS ===
        self.tool_keywords = {
            'book', 'schedule', 'send', 'email', 'call', 'search',
            'find', 'look up', 'check', 'order', 'buy', 'weather',
            'calculate', 'convert', 'translate'
        }
        
        # === RAG REQUIREMENTS ===
        self.rag_keywords = {
            'document', 'pdf', 'file', 'article', 'paper', 'report',
            'attached', 'upload', 'this file', 'the document'
        }
        
        # Phrases that indicate RAG (checked separately)
        self.rag_phrases = [
            'based on', 'according to', 'in the document', 'from the file',
            'attached document', 'uploaded file', 'this pdf'
        ]
        
        # === DOMAIN INDICATORS ===
        self.domain_keywords = {
            Domain.MEDICAL: {
                'medical', 'health', 'symptom', 'symptoms', 'diagnosis', 'treatment',
                'medicine', 'doctor', 'patient', 'disease', 'clinical', 'diabetes',
                'cancer', 'heart', 'blood', 'pain', 'fever', 'infection', 'therapy',
                'prescription', 'hospital', 'nurse', 'surgery', 'vaccine'
            },
            Domain.LEGAL: {
                'legal', 'law', 'court', 'attorney', 'lawsuit', 'contract',
                'liability', 'compliance', 'regulation', 'rights'
            },
            Domain.TECHNICAL: {
                'technical', 'engineering', 'software', 'hardware', 'system',
                'api', 'database', 'server', 'network', 'infrastructure'
            },
            Domain.FINANCIAL: {
                'financial', 'money', 'investment', 'stock', 'market',
                'budget', 'tax', 'accounting', 'profit', 'revenue'
            },
            Domain.SCIENTIFIC: {
                'scientific', 'experiment', 'hypothesis', 'data', 'analysis',
                'physics', 'chemistry', 'biology', 'research', 'theory'
            },
        }
        
        # Compile regex patterns
        self._compiled_trivial = [
            (re.compile(pattern, re.IGNORECASE), name)
            for pattern, name in self.trivial_patterns
        ]
    
    def classify(self, message: str) -> IntentClassification:
        """
        Classify the intent of a message.
        
        Args:
            message: User's input message
            
        Returns:
            IntentClassification with complexity, task type, and requirements
        """
        message_lower = message.lower().strip()
        words = set(message_lower.split())
        matched_patterns = []
        
        # === Phase 1: Trivial pattern matching (instant) ===
        for pattern, name in self._compiled_trivial:
            if pattern.match(message_lower):
                matched_patterns.append(f"trivial:{name}")
                return IntentClassification(
                    complexity=Complexity.TRIVIAL,
                    task_type=TaskType.QA,
                    expected_length="short",
                    confidence=0.95,
                    matched_patterns=matched_patterns
                )
        
        # === Phase 2: Keyword analysis ===
        
        # Detect complexity
        complexity = self._detect_complexity(message_lower, words, matched_patterns)
        
        # Detect task type
        task_type = self._detect_task_type(message_lower, words, matched_patterns)
        
        # Detect domain
        domain = self._detect_domain(words, matched_patterns)
        
        # Detect requirements
        needs_tools = bool(words & self.tool_keywords)
        needs_rag = bool(words & self.rag_keywords) or any(
            phrase in message_lower for phrase in self.rag_phrases
        )
        needs_code = task_type == TaskType.CODE
        
        if needs_tools:
            matched_patterns.append("req:tools")
        if needs_rag:
            matched_patterns.append("req:rag")
        
        # Estimate expected length
        expected_length = self._estimate_length(complexity, task_type, message)
        
        # Calculate confidence based on pattern matches
        confidence = min(0.6 + 0.1 * len(matched_patterns), 0.95)
        
        return IntentClassification(
            complexity=complexity,
            task_type=task_type,
            domain=domain,
            needs_tools=needs_tools,
            needs_rag=needs_rag,
            needs_code=needs_code,
            expected_length=expected_length,
            confidence=confidence,
            matched_patterns=matched_patterns
        )
    
    def _detect_complexity(
        self, 
        message: str, 
        words: Set[str],
        matched: List[str]
    ) -> Complexity:
        """Detect complexity level from message."""
        
        # Check from most specific (EXPERT) to least (TRIVIAL)
        for complexity in [Complexity.EXPERT, Complexity.COMPLEX, 
                          Complexity.MODERATE, Complexity.SIMPLE, Complexity.TRIVIAL]:
            keywords = self.complexity_keywords[complexity]
            
            # Check for keyword phrases
            for kw in keywords:
                if kw in message:
                    matched.append(f"complexity:{complexity.name}:{kw}")
                    return complexity
        
        # Default based on message length
        if len(message) < 20:
            return Complexity.SIMPLE
        elif len(message) < 50:
            return Complexity.MODERATE
        else:
            return Complexity.COMPLEX
    
    def _detect_task_type(
        self,
        message: str,
        words: Set[str],
        matched: List[str]
    ) -> TaskType:
        """Detect task type from message."""
        
        for task_type, indicators in self.task_indicators.items():
            for indicator in indicators:
                if indicator in message:
                    matched.append(f"task:{task_type.value}:{indicator}")
                    return task_type
        
        # Default to QA for questions, CHAT for statements
        if '?' in message or message.startswith(('what', 'who', 'when', 'where', 'why', 'how')):
            return TaskType.QA
        
        return TaskType.CHAT
    
    def _detect_domain(
        self,
        words: Set[str],
        matched: List[str]
    ) -> Domain:
        """Detect domain specialization from message."""
        
        best_domain = Domain.GENERAL
        best_score = 0
        
        for domain, keywords in self.domain_keywords.items():
            score = len(words & keywords)
            if score > best_score:
                best_score = score
                best_domain = domain
        
        if best_score > 0:
            matched.append(f"domain:{best_domain.value}")
        
        return best_domain
    
    def _estimate_length(
        self,
        complexity: Complexity,
        task_type: TaskType,
        message: str
    ) -> str:
        """Estimate expected response length."""
        
        # Creative and research tasks tend to be long
        if task_type in [TaskType.CREATIVE, TaskType.RESEARCH]:
            return "long"
        
        # Code can be any length
        if task_type == TaskType.CODE:
            return "medium" if len(message) < 100 else "long"
        
        # Map complexity to length
        return {
            Complexity.TRIVIAL: "short",
            Complexity.SIMPLE: "short",
            Complexity.MODERATE: "medium",
            Complexity.COMPLEX: "long",
            Complexity.EXPERT: "long",
        }[complexity]


# Global classifier instance
_classifier: Optional[IntentClassifier] = None


def get_classifier() -> IntentClassifier:
    """Get or create the global classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier


def classify_intent(message: str) -> IntentClassification:
    """Convenience function to classify a message."""
    return get_classifier().classify(message)


# === CLI for testing ===
if __name__ == "__main__":
    import json
    import sys
    
    classifier = IntentClassifier()
    
    test_messages = [
        "hi",
        "What is 2+2?",
        "Tell me a joke",
        "Explain quantum entanglement",
        "Write a Python function to sort a list",
        "Research the impact of AI on healthcare and summarize key findings",
        "Book me a flight to New York next Tuesday",
        "Based on the attached document, what are the main points?",
        "What are the symptoms of diabetes?",
        "Draft a legal contract for a software license",
    ]
    
    # Use CLI args if provided
    if len(sys.argv) > 1:
        test_messages = [" ".join(sys.argv[1:])]
    
    print("=" * 60)
    print("INTENT CLASSIFICATION TEST")
    print("=" * 60)
    
    for msg in test_messages:
        result = classifier.classify(msg)
        print(f"\nMessage: \"{msg}\"")
        print(f"  Complexity: {result.complexity.name} → {result.recommended_model_size}")
        print(f"  Task Type: {result.task_type.value}")
        print(f"  Domain: {result.domain.value}")
        print(f"  Needs Tools: {result.needs_tools}")
        print(f"  Needs RAG: {result.needs_rag}")
        print(f"  Expected Length: {result.expected_length}")
        print(f"  Confidence: {result.confidence:.0%}")
        print(f"  Patterns: {result.matched_patterns}")
