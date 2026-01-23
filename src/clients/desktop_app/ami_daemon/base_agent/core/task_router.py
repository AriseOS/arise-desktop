"""
Task Router Module

Routes tasks to appropriate specialized agents based on task analysis.
Based on Eigent's multi-agent architecture where different task types
are handled by specialized agents.

References:
- Eigent: third-party/eigent/backend/app/utils/workforce.py
- Eigent: third-party/eigent/backend/app/service/task.py
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .agent_registry import AgentType, get_registry

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    """Result of task routing analysis."""
    agent_type: str
    confidence: float  # 0.0-1.0
    reasoning: str
    requires_confirmation: bool = False
    suggested_subtasks: List[str] = field(default_factory=list)
    alternative_agents: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_type": self.agent_type,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "requires_confirmation": self.requires_confirmation,
            "suggested_subtasks": self.suggested_subtasks,
            "alternative_agents": self.alternative_agents,
        }


# Keywords and patterns for rule-based routing
ROUTING_PATTERNS: Dict[str, Dict[str, Any]] = {
    AgentType.BROWSER.value: {
        "keywords": [
            "search", "find", "look up", "research", "browse", "navigate",
            "website", "web page", "url", "link", "click", "scroll",
            "extract", "scrape", "download", "online", "internet",
            "google", "bing", "amazon", "youtube", "twitter", "facebook",
        ],
        "patterns": [
            r"search\s+for",
            r"find\s+.*\s+on\s+the\s+web",
            r"go\s+to\s+(http|www)",
            r"open\s+.*\s+(website|page)",
        ],
        "priority": 10,
    },
    AgentType.DEVELOPER.value: {
        "keywords": [
            "code", "coding", "programming", "debug", "fix", "bug",
            "implement", "function", "class", "module", "test",
            "git", "commit", "push", "pull", "branch", "merge",
            "npm", "pip", "install", "build", "compile", "run",
            "python", "javascript", "typescript", "java", "rust",
            "error", "exception", "stack trace", "refactor",
        ],
        "patterns": [
            r"write\s+.*\s+code",
            r"fix\s+.*\s+(bug|error|issue)",
            r"create\s+.*\s+(function|class|module)",
            r"git\s+(commit|push|pull)",
        ],
        "priority": 10,
    },
    AgentType.DOCUMENT.value: {
        "keywords": [
            "document", "doc", "file", "folder", "create", "write",
            "notion", "google drive", "gdrive", "notes", "markdown",
            "pdf", "docx", "spreadsheet", "format", "organize",
            "template", "report", "summary", "documentation",
        ],
        "patterns": [
            r"create\s+.*\s+(document|file|note)",
            r"write\s+.*\s+to\s+.*\s+(notion|drive)",
            r"organize\s+.*\s+files",
        ],
        "priority": 8,
    },
    AgentType.SOCIAL_MEDIUM.value: {
        "keywords": [
            "email", "mail", "send", "inbox", "gmail", "outlook",
            "calendar", "schedule", "meeting", "event", "appointment",
            "social", "message", "post", "reply", "forward",
        ],
        "patterns": [
            r"send\s+.*\s+email",
            r"schedule\s+.*\s+meeting",
            r"check\s+.*\s+(email|calendar)",
            r"reply\s+to",
        ],
        "priority": 8,
    },
    AgentType.QUESTION_CONFIRM.value: {
        "keywords": [
            "confirm", "verify", "clarify", "ask", "question",
            "approve", "decide", "choose", "option", "preference",
        ],
        "patterns": [
            r"confirm\s+(before|that)",
            r"ask\s+.*\s+about",
            r"need\s+.*\s+clarification",
        ],
        "priority": 5,
    },
}


class TaskRouter:
    """Routes tasks to appropriate specialized agents.

    Uses a combination of:
    1. Keyword matching
    2. Pattern matching
    3. LLM-based classification (when available)

    Similar to Eigent's task routing in workforce.py.
    """

    def __init__(self, use_llm: bool = False, llm_provider=None):
        """Initialize task router.

        Args:
            use_llm: Whether to use LLM for routing (more accurate but slower)
            llm_provider: LLM provider instance for LLM-based routing
        """
        self.use_llm = use_llm
        self.llm_provider = llm_provider
        self._registry = get_registry()

    def route(self, task: str, context: Optional[Dict[str, Any]] = None) -> RoutingResult:
        """Route a task to the appropriate agent.

        Args:
            task: The task description
            context: Optional context information

        Returns:
            RoutingResult with agent selection and reasoning
        """
        context = context or {}

        # Try rule-based routing first
        result = self._rule_based_route(task, context)

        # If confidence is low and LLM is available, use LLM routing
        if self.use_llm and self.llm_provider and result.confidence < 0.7:
            llm_result = self._llm_route(task, context)
            if llm_result.confidence > result.confidence:
                result = llm_result

        return result

    def _rule_based_route(
        self,
        task: str,
        context: Dict[str, Any]
    ) -> RoutingResult:
        """Route using keyword and pattern matching.

        Args:
            task: The task description
            context: Context information

        Returns:
            RoutingResult from rule-based analysis
        """
        import re

        task_lower = task.lower()
        scores: Dict[str, float] = {}

        for agent_type, patterns in ROUTING_PATTERNS.items():
            score = 0.0

            # Keyword matching
            keywords = patterns.get("keywords", [])
            keyword_matches = sum(1 for kw in keywords if kw in task_lower)
            if keywords:
                score += (keyword_matches / len(keywords)) * 0.6

            # Pattern matching
            regex_patterns = patterns.get("patterns", [])
            pattern_matches = sum(
                1 for p in regex_patterns if re.search(p, task_lower)
            )
            if regex_patterns:
                score += (pattern_matches / len(regex_patterns)) * 0.4

            # Apply priority weight
            priority = patterns.get("priority", 5) / 10.0
            scores[agent_type] = score * priority

        # Find best match
        if not scores:
            return RoutingResult(
                agent_type=AgentType.BROWSER.value,
                confidence=0.3,
                reasoning="No specific patterns matched, defaulting to browser agent",
                alternative_agents=[AgentType.QUESTION_CONFIRM.value],
            )

        best_agent = max(scores, key=scores.get)
        best_score = scores[best_agent]

        # Find alternatives (agents with score > 0.3 * best_score)
        alternatives = [
            agent for agent, score in scores.items()
            if agent != best_agent and score > best_score * 0.3
        ]

        # Build reasoning
        matched_keywords = []
        for kw in ROUTING_PATTERNS.get(best_agent, {}).get("keywords", []):
            if kw in task_lower:
                matched_keywords.append(kw)

        reasoning = f"Matched keywords: {matched_keywords[:5]}" if matched_keywords else "Pattern-based match"

        return RoutingResult(
            agent_type=best_agent,
            confidence=min(best_score, 1.0),
            reasoning=reasoning,
            requires_confirmation=best_score < 0.5,
            alternative_agents=alternatives[:3],
        )

    def _llm_route(
        self,
        task: str,
        context: Dict[str, Any]
    ) -> RoutingResult:
        """Route using LLM classification.

        Args:
            task: The task description
            context: Context information

        Returns:
            RoutingResult from LLM analysis
        """
        if not self.llm_provider:
            return RoutingResult(
                agent_type=AgentType.BROWSER.value,
                confidence=0.3,
                reasoning="LLM not available, using default",
            )

        # Build available agents description
        available_agents = []
        for agent_type in AgentType:
            info = self._registry.get(agent_type.value)
            if info:
                available_agents.append(
                    f"- {agent_type.value}: {info.description}"
                )
            else:
                # Use default descriptions for unregistered agents
                descriptions = {
                    AgentType.BROWSER: "Web automation, research, data collection",
                    AgentType.DEVELOPER: "Coding, debugging, git operations",
                    AgentType.DOCUMENT: "Document creation, Google Drive, Notion",
                    AgentType.SOCIAL_MEDIUM: "Email, calendar, communication",
                    AgentType.QUESTION_CONFIRM: "User confirmations and Q&A",
                }
                available_agents.append(
                    f"- {agent_type.value}: {descriptions.get(agent_type, 'General tasks')}"
                )

        # This would typically call the LLM
        # For now, return a placeholder that falls back to rule-based
        logger.debug("LLM routing not fully implemented, using rule-based")
        return self._rule_based_route(task, context)

    def suggest_subtasks(self, task: str) -> List[str]:
        """Suggest how to break down a complex task.

        Args:
            task: The task description

        Returns:
            List of suggested subtask descriptions
        """
        # Simple heuristics for common patterns
        task_lower = task.lower()
        subtasks = []

        # Research + action pattern
        if "research" in task_lower and ("then" in task_lower or "and" in task_lower):
            subtasks.append("Research and gather information")
            subtasks.append("Analyze and document findings")
            subtasks.append("Execute required actions")

        # Multi-step web task
        elif any(kw in task_lower for kw in ["multiple", "several", "all", "each"]):
            subtasks.append("Identify all targets/items")
            subtasks.append("Process each item systematically")
            subtasks.append("Compile and verify results")

        # Create/build pattern
        elif any(kw in task_lower for kw in ["create", "build", "implement", "develop"]):
            subtasks.append("Understand requirements")
            subtasks.append("Design/plan the implementation")
            subtasks.append("Execute the implementation")
            subtasks.append("Verify and test")

        return subtasks

    def analyze_complexity(self, task: str) -> Dict[str, Any]:
        """Analyze task complexity for planning.

        Args:
            task: The task description

        Returns:
            Complexity analysis with estimated effort
        """
        task_lower = task.lower()

        # Count complexity indicators
        multi_step = any(
            kw in task_lower
            for kw in ["then", "after", "first", "next", "finally", "multiple", "several", "all"]
        )
        research_needed = any(
            kw in task_lower
            for kw in ["find", "search", "research", "look up", "discover"]
        )
        code_involved = any(
            kw in task_lower
            for kw in ["code", "implement", "debug", "fix", "build"]
        )
        document_output = any(
            kw in task_lower
            for kw in ["document", "report", "summary", "save", "export"]
        )

        # Estimate complexity
        complexity_score = sum([
            multi_step * 2,
            research_needed * 1,
            code_involved * 2,
            document_output * 1,
        ])

        if complexity_score >= 4:
            complexity = "high"
        elif complexity_score >= 2:
            complexity = "medium"
        else:
            complexity = "low"

        return {
            "complexity": complexity,
            "complexity_score": complexity_score,
            "is_multi_step": multi_step,
            "requires_research": research_needed,
            "involves_code": code_involved,
            "requires_documentation": document_output,
            "suggested_subtasks": self.suggest_subtasks(task) if multi_step else [],
            "estimated_agents_needed": self._estimate_agents_needed(task),
        }

    def _estimate_agents_needed(self, task: str) -> List[str]:
        """Estimate which agents might be needed for a task.

        Args:
            task: The task description

        Returns:
            List of agent types that might be needed
        """
        task_lower = task.lower()
        agents_needed = set()

        for agent_type, patterns in ROUTING_PATTERNS.items():
            keywords = patterns.get("keywords", [])
            if any(kw in task_lower for kw in keywords):
                agents_needed.add(agent_type)

        return list(agents_needed) or [AgentType.BROWSER.value]


# Global router instance
_default_router: Optional[TaskRouter] = None


def get_router(use_llm: bool = False) -> TaskRouter:
    """Get the default task router.

    Args:
        use_llm: Whether to enable LLM routing

    Returns:
        TaskRouter instance
    """
    global _default_router
    if _default_router is None:
        _default_router = TaskRouter(use_llm=use_llm)
    return _default_router


def route_task(task: str, context: Optional[Dict[str, Any]] = None) -> RoutingResult:
    """Route a task using the default router.

    Convenience function for task routing.

    Args:
        task: The task description
        context: Optional context

    Returns:
        RoutingResult
    """
    return get_router().route(task, context)
