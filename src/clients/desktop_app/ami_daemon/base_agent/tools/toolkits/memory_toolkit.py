"""
MemoryToolkit - Query Ami's Workflow Memory for task guidance.

Provides three simple query interfaces:
1. query_cognitive_phrase() - Get user-recorded complete workflow
2. query_path() - Get retrieved navigation path
3. query_states() - Get related page states with operations

Design principle: Memory is a tool, Agent is the decision maker.
"""

import logging
import re
from urllib.parse import urlsplit, urlunsplit
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base_toolkit import BaseToolkit, FunctionTool

logger = logging.getLogger(__name__)

# Log-sanitization settings (avoid leaking sensitive info)
_MAX_LOG_STEPS = 8
_MAX_TEXT_LEN = 160
_MAX_SELECTOR_LEN = 120


def _truncate_text(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    if max_len <= 15:
        return value[:max_len]
    return value[: max_len - 14] + "...(truncated)"


def _sanitize_text(value: Optional[str], max_len: int = _MAX_TEXT_LEN) -> str:
    if not value:
        return ""
    text = str(value)
    # Redact emails
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<redacted_email>", text)
    # Redact phone-like numbers
    text = re.sub(r"\+?\d[\d\-\s\(\)]{7,}\d", "<redacted_phone>", text)
    # Redact long tokens
    text = re.sub(r"\b[a-zA-Z0-9_\-]{20,}\b", "<redacted_token>", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return _truncate_text(text, max_len)


def _sanitize_url(url: Optional[str]) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        netloc = parts.netloc.split("@")[-1]
        cleaned = urlunsplit((parts.scheme, netloc, parts.path, "", ""))
        return _sanitize_text(cleaned, max_len=_MAX_TEXT_LEN)
    except Exception:
        return _sanitize_text(url, max_len=_MAX_TEXT_LEN)


def _format_intents_for_log(intents: List[Dict[str, Any]]) -> str:
    if not intents:
        return ""
    items = []
    for intent in intents[:2]:
        if isinstance(intent, dict):
            intent_type = _sanitize_text(intent.get("type"), max_len=40)
            intent_text = _sanitize_text(intent.get("text"), max_len=60)
        else:
            intent_type = _sanitize_text(getattr(intent, "type", ""), max_len=40)
            intent_text = _sanitize_text(getattr(intent, "text", ""), max_len=60)
        if intent_type or intent_text:
            items.append(f"{intent_type}:{intent_text}")
    return ", ".join(items)


def _log_cognitive_phrase_summary(phrase: "CognitivePhrase") -> None:
    try:
        logger.info(
            "[Memory] cognitive_phrase summary: id=%s desc=%s states=%d actions=%d",
            _sanitize_text(phrase.id, max_len=40),
            _sanitize_text(phrase.description, max_len=120),
            len(phrase.states),
            len(phrase.actions),
        )
        for i, state in enumerate(phrase.states[:_MAX_LOG_STEPS]):
            state_desc = _sanitize_text(state.description, max_len=120)
            state_url = _sanitize_url(state.page_url)
            logger.info(
                "[Memory] phrase step %d: state=%s url=%s",
                i + 1,
                state_desc or "N/A",
                state_url or "N/A",
            )
            if state.intent_sequences:
                seq = state.intent_sequences[0]
                seq_desc = _sanitize_text(seq.description, max_len=120)
                seq_intents = _format_intents_for_log(seq.intents)
                if seq_desc or seq_intents:
                    logger.info(
                        "[Memory] phrase step %d intents: %s | %s",
                        i + 1,
                        seq_desc or "N/A",
                        seq_intents or "N/A",
                    )
            if i < len(phrase.actions):
                action = phrase.actions[i]
                action_desc = _sanitize_text(action.description, max_len=120)
                action_text = _sanitize_text(action.element_text, max_len=60)
                action_selector = _sanitize_text(action.element_selector, max_len=_MAX_SELECTOR_LEN)
                logger.info(
                    "[Memory] phrase step %d action: %s | text=%s | selector=%s",
                    i + 1,
                    action_desc or "N/A",
                    action_text or "N/A",
                    action_selector or "N/A",
                )
    except Exception as e:
        logger.debug(f"[Memory] Failed to log cognitive_phrase summary: {e}")


def _log_path_summary(best_path: Dict[str, Any], steps: List[Dict[str, Any]]) -> None:
    try:
        logger.info(
            "[Memory] path summary: desc=%s score=%s steps=%d",
            _sanitize_text(best_path.get("description"), max_len=120),
            best_path.get("score", 0),
            len(steps),
        )
        for i, step in enumerate(steps[:_MAX_LOG_STEPS]):
            state_data = step.get("state") or {}
            action_data = step.get("action") or {}
            intent_seq = step.get("intent_sequence") or {}

            state_desc = _sanitize_text(
                state_data.get("description")
                or state_data.get("page_title")
                or state_data.get("page_url"),
                max_len=120,
            )
            state_url = _sanitize_url(state_data.get("page_url"))

            action_desc = _sanitize_text(action_data.get("description"), max_len=120)
            action_text = _sanitize_text(action_data.get("trigger_intent", {}).get("text"), max_len=60)
            action_selector = _sanitize_text(
                action_data.get("trigger_intent", {}).get("css_selector")
                or action_data.get("trigger_intent", {}).get("xpath"),
                max_len=_MAX_SELECTOR_LEN,
            )

            intent_desc = _sanitize_text(intent_seq.get("description"), max_len=120)
            intents_list = intent_seq.get("intents") or []
            intents_summary = _format_intents_for_log(intents_list) if isinstance(intents_list, list) else ""

            logger.info(
                "[Memory] path step %d: state=%s url=%s | action=%s | text=%s | selector=%s | intents=%s | %s",
                i + 1,
                state_desc or "N/A",
                state_url or "N/A",
                action_desc or "N/A",
                action_text or "N/A",
                action_selector or "N/A",
                intent_desc or "N/A",
                intents_summary or "N/A",
            )
    except Exception as e:
        logger.debug(f"[Memory] Failed to log path summary: {e}")

# Try to import httpx for async HTTP requests
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not available, MemoryToolkit will have limited functionality")


@dataclass
class IntentSequence:
    """Represents an operation that can be performed on a page."""
    description: str
    intents: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> "IntentSequence":
        return cls(
            description=data.get("description", ""),
            intents=data.get("intents", []),
        )


@dataclass
class State:
    """Page state with available operations."""
    id: str
    description: str
    page_url: str
    page_title: str
    intent_sequences: List[IntentSequence] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> "State":
        intent_seqs = [
            IntentSequence.from_dict(seq)
            for seq in data.get("intent_sequences", [])
        ]
        return cls(
            id=data.get("id", ""),
            description=data.get("description", ""),
            page_url=data.get("page_url", ""),
            page_title=data.get("page_title", ""),
            intent_sequences=intent_seqs,
        )


@dataclass
class Action:
    """Navigation action between states."""
    source_id: str
    target_id: str
    action_type: str
    description: str
    element_text: Optional[str] = None
    element_selector: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "Action":
        # Extract element info from attributes or trigger_intent
        attrs = data.get("attributes", {})
        trigger_intent = data.get("trigger_intent", {})

        element_text = (
            attrs.get("element_text") or
            trigger_intent.get("text") or
            None
        )
        element_selector = (
            attrs.get("element_selector") or
            trigger_intent.get("css_selector") or
            trigger_intent.get("xpath") or
            None
        )

        return cls(
            source_id=data.get("source", data.get("source_id", "")),
            target_id=data.get("target", data.get("target_id", "")),
            action_type=data.get("type", data.get("action_type", "")),
            description=data.get("description", ""),
            element_text=element_text,
            element_selector=element_selector,
        )


@dataclass
class CognitivePhrase:
    """User-recorded complete workflow."""
    id: str
    description: str
    states: List[State]
    actions: List[Action]

    @classmethod
    def from_dict(cls, data: Dict) -> "CognitivePhrase":
        states = [State.from_dict(s) for s in data.get("states", [])]
        actions = [Action.from_dict(a) for a in data.get("actions", [])]
        return cls(
            id=data.get("id", ""),
            description=data.get("description", ""),
            states=states,
            actions=actions,
        )


@dataclass
class Path:
    """Retrieved navigation path."""
    states: List[State]
    actions: List[Action]

    @classmethod
    def from_dict(cls, data: Dict) -> "Path":
        states = [State.from_dict(s) for s in data.get("states", [])]
        actions = [Action.from_dict(a) for a in data.get("actions", [])]
        return cls(states=states, actions=actions)


class MemoryToolkit(BaseToolkit):
    """Toolkit for querying workflow memory.

    Provides three simple interfaces:
    - query_cognitive_phrase(): Get user-recorded complete workflow
    - query_path(): Get retrieved navigation path
    - query_states(): Get related page states

    Design: Memory is a tool, Agent is the decision maker.
    """

    agent_name: str = "memory_agent"

    def __init__(
        self,
        memory_api_base_url: str,
        ami_api_key: str,
        user_id: str,
        timeout: Optional[float] = 30.0,
    ) -> None:
        """Initialize MemoryToolkit.

        Args:
            memory_api_base_url: Base URL of Ami's cloud backend.
            ami_api_key: User's Ami API key for authentication.
            user_id: User ID for memory isolation.
            timeout: HTTP request timeout in seconds.
        """
        super().__init__(timeout=timeout)
        self._memory_api_base_url = memory_api_base_url.rstrip("/")
        self._ami_api_key = ami_api_key
        self._user_id = user_id

        logger.info(
            f"MemoryToolkit initialized (user_id={user_id}, "
            f"api_base_url={memory_api_base_url})"
        )

    # =========================================================================
    # Three Core Query Methods
    # =========================================================================

    async def query_cognitive_phrase(self, task: str) -> Optional[CognitivePhrase]:
        """Query for user-recorded complete workflow.

        Use at task/subtask START to get complete navigation guidance.

        Args:
            task: Task description

        Returns:
            CognitivePhrase if found, None otherwise
        """
        if not self.is_available():
            return None

        logger.info(f"[Memory] Querying cognitive_phrase: {task[:50]}...")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._memory_api_base_url}/api/v1/memory/phrase/query",
                    json={
                        "user_id": self._user_id,
                        "query": task,
                    },
                    headers={"X-Ami-API-Key": self._ami_api_key},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()

            if not result.get("success") or not result.get("phrase"):
                logger.info(f"[Memory] No cognitive_phrase found for: {task[:30]}...")
                return None

            phrase = CognitivePhrase.from_dict(result["phrase"])
            logger.info(
                f"[Memory] Found cognitive_phrase: {phrase.id} "
                f"with {len(phrase.states)} states"
            )
            _log_cognitive_phrase_summary(phrase)
            return phrase

        except Exception as e:
            logger.warning(f"[Memory] cognitive_phrase query failed: {e}")
            return None

    async def query_path(self, task: str) -> Optional[Path]:
        """Query for a navigation path to the goal.

        Use at task/subtask START when no cognitive_phrase is found.
        Calls /api/v1/memory/query which returns paths found via:
        1. Decompose query into target_query + key_queries
        2. Embedding search for target and key states
        3. BFS reverse traversal to find paths reaching these nodes
        4. Score paths by key node coverage

        Args:
            task: Task description

        Returns:
            Path (states + actions) if found, None otherwise
        """
        if not self.is_available():
            return None

        logger.info(f"[Memory] Querying path: {task[:50]}...")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._memory_api_base_url}/api/v1/memory/query",
                    json={
                        "user_id": self._user_id,
                        "query": task,
                    },
                    headers={"X-Ami-API-Key": self._ami_api_key},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()

            if not result.get("success"):
                logger.info(f"[Memory] No path found for: {task[:30]}...")
                return None

            # Response contains scored paths with steps array
            # Each path: {score, path_length, description, steps: [{state, action, intent_sequence}, ...]}
            paths = result.get("paths", [])
            if not paths:
                logger.info(f"[Memory] No paths found for: {task[:30]}...")
                return None

            # Use the best path (highest score, already sorted by server)
            best_path = paths[0]
            steps = best_path.get("steps", [])

            if not steps:
                logger.info(f"[Memory] Best path has no steps for: {task[:30]}...")
                return None

            # Extract states and actions from steps
            states = []
            actions = []
            for step in steps:
                state_data = step.get("state")
                action_data = step.get("action")

                if state_data:
                    states.append(State.from_dict(state_data))
                if action_data and action_data.get("source_id"):  # Has valid action
                    actions.append(Action.from_dict(action_data))

            if not states:
                logger.info(f"[Memory] Path has no states for: {task[:30]}...")
                return None

            path = Path(states=states, actions=actions)
            logger.info(
                f"[Memory] Found path: {best_path.get('description', '')} "
                f"({len(path.states)} states, {len(path.actions)} actions, "
                f"score={best_path.get('score', 0)})"
            )
            _log_path_summary(best_path, steps)
            return path

        except Exception as e:
            logger.warning(f"[Memory] path query failed: {e}")
            return None

    async def query_states(self, task: str) -> List[State]:
        """Query for related page states.

        Use during agent loop to find page-specific operations.

        Args:
            task: Task/page description

        Returns:
            List of relevant State objects (may be empty)
        """
        if not self.is_available():
            return []

        logger.info(f"[Memory] Querying states: {task[:50]}...")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._memory_api_base_url}/api/v1/memory/query",
                    json={
                        "user_id": self._user_id,
                        "query": task,
                    },
                    headers={"X-Ami-API-Key": self._ami_api_key},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()

            if not result.get("success"):
                logger.info(f"[Memory] No states found for: {task[:30]}...")
                return []

            paths = result.get("paths", [])
            states = []
            for path in paths:
                state_data = path.get("state", path)
                if state_data:
                    states.append(State.from_dict(state_data))

            logger.info(f"[Memory] Found {len(states)} states")
            return states

        except Exception as e:
            logger.warning(f"[Memory] states query failed: {e}")
            return []

    # =========================================================================
    # Context Formatters
    # =========================================================================

    @staticmethod
    def format_cognitive_phrase(phrase: CognitivePhrase) -> str:
        """Format CognitivePhrase for LLM context."""
        lines = ["## 🧠 MEMORY: VERIFIED WORKFLOW (MUST FOLLOW)\n"]
        lines.append(f"**Description**: {phrase.description}\n")
        lines.append("⚠️ **CRITICAL**: This workflow has been verified by the user. You MUST follow these exact steps.\n")
        lines.append("**Navigation Steps**:")

        for i, state in enumerate(phrase.states, 1):
            lines.append(f"\n### Step {i}: {state.description}")
            if state.page_url:
                lines.append(f"   📍 URL: {state.page_url}")

            # Show key operations
            if state.intent_sequences:
                lines.append("   🔧 Operations on this page:")
                for seq in state.intent_sequences[:3]:
                    lines.append(f"      • {seq.description}")
                    for intent in seq.intents[:2]:
                        selector = intent.get("css_selector") or intent.get("xpath", "")
                        if selector:
                            lines.append(f"        Selector: `{selector}`")

            # Show action to next state
            if i <= len(phrase.actions):
                action = phrase.actions[i - 1]
                lines.append(f"   ➡️ **ACTION TO NEXT STEP**: {action.description}")

        lines.append("\n" + "=" * 60)
        lines.append("⚠️ **IMPORTANT**: This is a user-verified workflow.")
        lines.append("   - Follow these steps IN ORDER")
        lines.append("   - Use the provided URLs and selectors")
        lines.append("   - Do NOT deviate unless the page has changed")
        lines.append("=" * 60)
        return "\n".join(lines)

    @staticmethod
    def format_path(path: Path) -> str:
        """Format retrieved path for LLM context.

        Path from /api/v1/memory/query is a Navigation Map showing:
        - Page TYPES (States) - not fixed URLs, but categories of pages
        - How to navigate between page types (Actions)
        """
        has_actions = len(path.actions) > 0

        lines = ["## 🗺️ NAVIGATION MAP\n"]
        lines.append("This map shows a verified route to reach certain **page types**.\n")
        lines.append("**IMPORTANT**: URLs are REFERENCE EXAMPLES, not fixed targets.")
        lines.append("The same page type may have different URLs (e.g., /weekly/2026/3 vs /weekly/2026/4).\n")

        lines.append("**Route Steps**:")

        for i, state in enumerate(path.states, 1):
            lines.append(f"\n### Step {i}: Page Type = \"{state.description}\"")
            if state.page_url:
                lines.append(f"   📍 Reference URL: `{state.page_url}`")
                lines.append(f"      (This is an example - actual URL may vary)")

            # Show key operations available on this page type
            if state.intent_sequences:
                lines.append("   🔧 **Available operations on this page**:")
                for seq in state.intent_sequences[:3]:  # Show up to 3 sequences
                    lines.append(f"      • {seq.description}")
                    # Show intent details
                    for intent in seq.intents[:3]:  # Show up to 3 intents per sequence
                        intent_type = intent.get("type", "")
                        intent_text = intent.get("text", "")
                        selector = intent.get("css_selector") or intent.get("xpath", "")

                        # Format based on intent type
                        if intent_type.lower() in ["scroll", "scrolldown", "scrollup"]:
                            lines.append(f"        - Scroll: {intent_text or 'page scroll'}")
                        elif intent_type.lower() in ["dataload", "load", "loadmore"]:
                            lines.append(f"        - Load more data: {intent_text or 'trigger data loading'}")
                        elif intent_type.lower() in ["click", "clickelement"]:
                            if intent_text:
                                lines.append(f"        - Click: \"{intent_text}\"")
                            if selector:
                                lines.append(f"          Selector: `{selector}`")
                        elif intent_type.lower() in ["type", "input", "typetext"]:
                            lines.append(f"        - Input: {intent_text or 'text input'}")
                            if selector:
                                lines.append(f"          Selector: `{selector}`")
                        else:
                            # Generic format for other types
                            if intent_text or selector:
                                lines.append(f"        - {intent_type}: {intent_text or ''}")
                                if selector:
                                    lines.append(f"          Selector: `{selector}`")

            # Show action to next state if available
            if i <= len(path.actions):
                action = path.actions[i - 1]
                lines.append(f"   ➡️ **To reach next page type**:")
                if action.description:
                    lines.append(f"      Action: {action.description}")
                if action.element_text:
                    lines.append(f"      Click element: \"{action.element_text}\"")
                if action.element_selector:
                    lines.append(f"      Selector: `{action.element_selector}`")

        lines.append("\n" + "-" * 60)
        lines.append("📋 **HOW TO USE THIS MAP**:")
        lines.append("   1. Use this route to navigate to your target page type")
        lines.append("   2. URLs are references - adapt to current context if needed")
        lines.append("   3. Actions show HOW to move between page types")
        lines.append("   4. Once at target page, focus on completing the USER'S TASK")
        lines.append("   5. If you need to process multiple items, use replan_task")
        lines.append("-" * 60)
        return "\n".join(lines)

    @staticmethod
    def format_states(states: List[State]) -> str:
        """Format scattered states for LLM context."""
        if not states:
            return ""

        lines = ["## Memory: Related Pages\n"]

        for state in states[:5]:
            lines.append(f"- **{state.description}**")
            if state.page_url:
                lines.append(f"  URL: {state.page_url}")

            for seq in state.intent_sequences[:3]:
                lines.append(f"  - {seq.description}")
                for intent in seq.intents[:1]:
                    selector = intent.get("css_selector") or intent.get("xpath", "")
                    if selector:
                        lines.append(f"    Selector: {selector}")

        return "\n".join(lines)

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def is_available(self) -> bool:
        """Check if memory functionality is available."""
        return HTTPX_AVAILABLE and bool(
            self._memory_api_base_url and self._ami_api_key
        )

    def get_tools(self) -> List[FunctionTool]:
        """Return FunctionTool objects for LLM tool-use.

        Note: The three query methods (query_cognitive_phrase, query_path,
        query_states) are called by the agent framework, not exposed as
        LLM-callable tools.
        """
        # Memory queries are called by framework, not LLM
        return []

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Memory Toolkit"
