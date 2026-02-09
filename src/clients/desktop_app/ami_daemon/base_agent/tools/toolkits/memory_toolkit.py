"""
MemoryToolkit - Query Ami's Workflow Memory for task guidance (V2).

Provides three query interfaces matching the three-level query model:
1. query_task(task) - Task level: Get complete workflow for a task
2. query_navigation(start, end) - Navigation level: Get path between pages
3. query_actions(state, target?) - Action level: Get available operations on a page

Design principle: Memory is a tool, Agent is the decision maker.

Architecture:
- MemoryToolkit only uses HTTP to call Memory API
- Memory API can be local (Daemon) or remote (Cloud Backend)
- Both backends use common/memory for business logic
"""

import logging
import re
from datetime import datetime
from pathlib import Path as FsPath
from urllib.parse import urlsplit, urlunsplit
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from .base_toolkit import BaseToolkit, FunctionTool
from ...workspace import get_current_manager

logger = logging.getLogger(__name__)

# Log-sanitization settings (avoid leaking sensitive info)
_MAX_LOG_STEPS = 8
_MAX_TEXT_LEN = 160
_MAX_SELECTOR_LEN = 120
_MAX_GUIDE_SEQUENCES = 3
_MAX_GUIDE_INTENTS = 20


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


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class Intent:
    """Single user operation (click, type, scroll, etc.)."""
    type: str
    element_ref: Optional[str] = None
    element_role: Optional[str] = None
    text: Optional[str] = None
    value: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "Intent":
        return cls(
            type=data.get("type", ""),
            element_ref=data.get("element_ref") or data.get("ref"),
            element_role=data.get("element_role"),
            text=data.get("text"),
            value=data.get("value"),
            attributes=data.get("attributes"),
        )


@dataclass
class IntentSequence:
    """Sequence of operations on a page."""
    id: str
    description: Optional[str]
    intents: List[Intent]
    causes_navigation: bool = False
    navigation_target_state_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "IntentSequence":
        intents = []
        for i in data.get("intents", []):
            if isinstance(i, dict):
                intents.append(Intent.from_dict(i))
        return cls(
            id=data.get("id", ""),
            description=data.get("description"),
            intents=intents,
            causes_navigation=data.get("causes_navigation", False),
            navigation_target_state_id=data.get("navigation_target_state_id"),
        )


@dataclass
class State:
    """Page state (abstraction of a page type)."""
    id: str
    description: str
    page_url: str
    page_title: str
    domain: Optional[str] = None
    intent_sequences: List["IntentSequence"] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> "State":
        intent_seqs = []
        for seq in data.get("intent_sequences", []):
            if isinstance(seq, dict):
                intent_seqs.append(IntentSequence.from_dict(seq))
        return cls(
            id=data.get("id", ""),
            description=data.get("description", ""),
            page_url=data.get("page_url", ""),
            page_title=data.get("page_title", ""),
            domain=data.get("domain"),
            intent_sequences=intent_seqs,
        )


@dataclass
class Action:
    """Navigation action between states."""
    id: str
    source_id: str
    target_id: str
    action_type: str
    description: Optional[str] = None
    trigger: Optional[Dict[str, Any]] = None  # {ref, text, role}
    trigger_sequence_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "Action":
        return cls(
            id=data.get("id", ""),
            source_id=data.get("source", data.get("source_id", "")),
            target_id=data.get("target", data.get("target_id", "")),
            action_type=data.get("type", data.get("action_type", "")),
            description=data.get("description"),
            trigger=data.get("trigger"),
            trigger_sequence_id=data.get("trigger_sequence_id"),
        )


@dataclass
class ExecutionStep:
    """Single step in an execution plan."""
    index: int
    state_id: str
    in_page_sequence_ids: List[str] = field(default_factory=list)
    navigation_action_id: Optional[str] = None
    navigation_sequence_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "ExecutionStep":
        return cls(
            index=data.get("index", 0),
            state_id=data.get("state_id", ""),
            in_page_sequence_ids=data.get("in_page_sequence_ids", []),
            navigation_action_id=data.get("navigation_action_id"),
            navigation_sequence_id=data.get("navigation_sequence_id"),
        )


@dataclass
class CognitivePhrase:
    """User-recorded complete workflow with execution plan."""
    id: str
    description: str
    states: List[State]
    actions: List[Action]
    execution_plan: List[ExecutionStep] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict) -> "CognitivePhrase":
        states = [State.from_dict(s) for s in data.get("states", [])]
        actions = [Action.from_dict(a) for a in data.get("actions", [])]
        execution_plan = [
            ExecutionStep.from_dict(step)
            for step in data.get("execution_plan", [])
        ]
        return cls(
            id=data.get("id", ""),
            description=data.get("description", ""),
            states=states,
            actions=actions,
            execution_plan=execution_plan,
        )


class QueryType(str, Enum):
    """Query result type."""
    TASK = "task"
    NAVIGATION = "navigation"
    ACTION = "action"


@dataclass
class SubTaskResult:
    """Result for a single subtask from task decomposition."""
    task_id: str
    target: str
    path_state_indices: List[int] = field(default_factory=list)
    found: bool = False

    @classmethod
    def from_dict(cls, data: Dict) -> "SubTaskResult":
        return cls(
            task_id=data.get("task_id", ""),
            target=data.get("target", ""),
            path_state_indices=data.get("path_state_indices", []),
            found=data.get("found", False),
        )


@dataclass
class QueryResult:
    """Unified query result from V2 API."""
    success: bool
    query_type: QueryType
    # Task/Navigation results
    states: List[State] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    # Task-specific
    cognitive_phrase: Optional[CognitivePhrase] = None
    execution_plan: List[ExecutionStep] = field(default_factory=list)
    subtasks: List[SubTaskResult] = field(default_factory=list)
    # Action-specific
    intent_sequences: List[IntentSequence] = field(default_factory=list)
    outgoing_actions: List[Action] = field(default_factory=list)
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @classmethod
    def from_api_response(cls, data: Dict) -> "QueryResult":
        """Parse V2 API response into QueryResult."""
        query_type = QueryType(data.get("query_type", "task"))

        states = [State.from_dict(s) for s in data.get("states", [])]
        actions = [Action.from_dict(a) for a in data.get("actions", [])]

        cognitive_phrase = None
        if data.get("cognitive_phrase"):
            # Server returns state_path/action_path in cognitive_phrase,
            # but full states/actions at top level. Merge them.
            phrase_data = data["cognitive_phrase"].copy()
            # If cognitive_phrase doesn't have states/actions, use top-level ones
            if not phrase_data.get("states") and states:
                phrase_data["states"] = [
                    {"id": s.id, "description": s.description,
                     "page_url": s.page_url, "page_title": s.page_title,
                     "domain": s.domain}
                    for s in states
                ]
            if not phrase_data.get("actions") and actions:
                phrase_data["actions"] = [
                    {"id": a.id, "source": a.source_id, "target": a.target_id,
                     "type": a.action_type, "description": a.description,
                     "trigger": a.trigger, "trigger_sequence_id": a.trigger_sequence_id}
                    for a in actions
                ]
            cognitive_phrase = CognitivePhrase.from_dict(phrase_data)

        execution_plan = [
            ExecutionStep.from_dict(step)
            for step in data.get("execution_plan", [])
        ]

        intent_sequences = [
            IntentSequence.from_dict(seq)
            for seq in data.get("intent_sequences", [])
        ]

        outgoing_actions = [
            Action.from_dict(a)
            for a in data.get("outgoing_actions", [])
        ]

        subtasks = [
            SubTaskResult.from_dict(st)
            for st in data.get("subtasks", [])
        ]

        return cls(
            success=data.get("success", False),
            query_type=query_type,
            states=states,
            actions=actions,
            cognitive_phrase=cognitive_phrase,
            execution_plan=execution_plan,
            subtasks=subtasks,
            intent_sequences=intent_sequences,
            outgoing_actions=outgoing_actions,
            metadata=data.get("metadata", {}),
            error=data.get("metadata", {}).get("error"),
        )


class MemoryToolkit(BaseToolkit):
    """Toolkit for querying workflow memory (V2).

    Provides three interfaces matching the three-level query model:
    - query_task(task): Task level - Get complete workflow for a task
    - query_navigation(start, end): Navigation level - Get path between pages
    - query_actions(state, target?): Action level - Get available operations

    Supports two memory backends:
    - Public Memory: Cloud Backend via HTTP (memory_api_base_url)
    - Local Memory: SurrealDB via direct call (use_local_memory=True)

    Design: Memory is a tool, Agent is the decision maker.
    """

    agent_name: str = "memory_agent"

    def __init__(
        self,
        memory_api_base_url: str,
        ami_api_key: str,
        user_id: str,
        timeout: Optional[float] = 180.0,
        agent: Optional[Any] = None,  # AMIBrowserAgent for page operations caching
        use_local_memory: bool = False,  # Use local SurrealDB instead of HTTP
    ) -> None:
        """Initialize MemoryToolkit.

        Args:
            memory_api_base_url: Base URL of Ami's cloud backend.
            ami_api_key: User's Ami API key for authentication.
            user_id: User ID for memory isolation.
            timeout: HTTP request timeout in seconds.
            agent: Optional AMIBrowserAgent for caching page operations.
                When provided, query_page_operations results will be cached
                in the agent for injection into subsequent LLM calls.
            use_local_memory: If True, use local SurrealDB directly instead of HTTP.
        """
        super().__init__(timeout=timeout)
        self._memory_api_base_url = memory_api_base_url.rstrip("/") if memory_api_base_url else ""
        self._ami_api_key = ami_api_key
        self._user_id = user_id
        self._agent = agent
        self._use_local_memory = use_local_memory

        mode = "local (SurrealDB)" if use_local_memory else f"public ({memory_api_base_url})"
        logger.info(
            f"MemoryToolkit initialized (user_id={user_id}, mode={mode})"
        )

    def set_agent(self, agent: Any) -> None:
        """Set the agent reference for page operations caching.

        This enables page operations cache management in AMIBrowserAgent.
        When query_page_operations returns results, they will be cached
        in the agent for injection into subsequent LLM calls.

        Args:
            agent: AMIBrowserAgent instance with cache_page_operations() method.
        """
        self._agent = agent
        logger.debug("MemoryToolkit: agent reference set for page operations caching")

    def _write_query_path_report(self, task: str, result: Dict[str, Any]) -> Optional[str]:
        def _clean_inline(value: Any) -> str:
            if value is None:
                return ""
            text = str(value).replace("\r", " ")
            text = " ".join(text.splitlines())
            return text.strip()

        def _format_state_line(state: Dict[str, Any]) -> str:
            desc = _clean_inline(state.get("description") or state.get("page_title") or state.get("page_url"))
            url = _clean_inline(state.get("page_url"))
            state_id = _clean_inline(state.get("id"))
            parts = [p for p in [desc, url] if p]
            if state_id:
                parts.append(f"id={state_id}")
            return " | ".join(parts) if parts else "N/A"

        def _to_float(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        def _to_int(value: Any) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        manager = get_current_manager()
        task_id = "unknown"
        project_id = None
        output_dir: Optional[FsPath] = None

        if manager:
            output_dir = FsPath(manager.output_dir)
            task_id = getattr(manager, "task_id", task_id)
            project_id = getattr(manager, "project_id", None)
        else:
            task_state = self.get_task_state()
            if task_state and hasattr(task_state, "dir_manager"):
                output_dir = FsPath(task_state.dir_manager.output_dir)
                task_id = getattr(task_state, "task_id", task_id)
                project_id = getattr(task_state, "project_id", None)

        if output_dir is None:
            output_dir = FsPath.cwd()

        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now()
        filename = f"query_path_{timestamp.strftime('%Y%m%d_%H%M%S')}_{task_id}.txt"
        file_path = output_dir / filename

        decomposed = result.get("decomposed") or {}
        target_query = decomposed.get("target_query", result.get("query", ""))
        key_queries = decomposed.get("key_queries") or []

        candidate_states = result.get("candidate_states") or {}
        target_candidates = candidate_states.get("target_states") or []
        key_candidates_by_type = candidate_states.get("key_states_by_type") or {}

        score_weights = result.get("score_weights") or {"target_weight": 1.0, "key_weight": 0.3}
        score_formula = result.get(
            "score_formula",
            "score = has_target * target_weight * target_score + key_type_coverage * key_weight",
        )

        lines: List[str] = []
        lines.append("=== Memory Query Path Report ===")
        lines.append(f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Task: {_clean_inline(task)}")
        lines.append(f"Query: {_clean_inline(result.get('query', task))}")
        lines.append(f"User ID: {_clean_inline(self._user_id)}")
        lines.append(f"Task ID: {_clean_inline(task_id)}")
        if project_id:
            lines.append(f"Project ID: {_clean_inline(project_id)}")
        lines.append(f"API Base URL: {_clean_inline(self._memory_api_base_url)}")
        lines.append("")

        lines.append("[Decomposed Query]")
        lines.append(f"target_query: {_clean_inline(target_query)}")
        if key_queries:
            lines.append("key_queries:")
            for idx, kq in enumerate(key_queries, 1):
                lines.append(f"  {idx}. {_clean_inline(kq)}")
        else:
            lines.append("key_queries: (none)")
        lines.append("")

        lines.append("[Candidate Target States]")
        if target_candidates:
            for item in target_candidates:
                score = _to_float(item.get("similarity_score"))
                state = item.get("state") or {}
                lines.append(f"- ({score:.4f}) {_format_state_line(state)}")
        else:
            lines.append("(none)")
        lines.append("")

        lines.append("[Candidate Key States]")
        if key_candidates_by_type:
            for kq, items in key_candidates_by_type.items():
                lines.append(f"- key_query: {_clean_inline(kq)}")
                for item in items or []:
                    score = _to_float(item.get("similarity_score"))
                    state = item.get("state") or {}
                    lines.append(f"  - ({score:.4f}) {_format_state_line(state)}")
        else:
            lines.append("(none)")
        lines.append("")

        lines.append("[Score Weights]")
        lines.append(f"target_weight: {_to_float(score_weights.get('target_weight')):.4f}")
        lines.append(f"key_weight: {_to_float(score_weights.get('key_weight')):.4f}")
        lines.append(f"formula: {_clean_inline(score_formula)}")
        lines.append("")

        paths = result.get("paths") or []
        paths_sorted = sorted(paths, key=lambda p: _to_float(p.get("score")), reverse=True)

        lines.append("[Paths] (sorted by score desc)")
        if not paths_sorted:
            lines.append("(none)")
        for idx, path in enumerate(paths_sorted, 1):
            score = _to_float(path.get("score"))
            path_length = _to_int(path.get("path_length"))
            has_target = _to_float(path.get("has_target"))
            target_score = _to_float(path.get("target_score"))
            key_types_hit = _to_int(path.get("key_types_hit"))
            key_types_total = _to_int(path.get("key_types_total"))
            key_coverage = _to_float(path.get("key_type_coverage"))
            target_weight = _to_float(score_weights.get("target_weight"))
            key_weight = _to_float(score_weights.get("key_weight"))
            target_component = has_target * target_weight * target_score
            key_component = key_coverage * key_weight

            lines.append(
                f"{idx}) score={score:.4f} | length={path_length} | "
                f"has_target={int(has_target)} | target_score={target_score:.4f} | "
                f"key_coverage={key_coverage:.4f} ({key_types_hit}/{key_types_total})"
            )
            lines.append(
                f"   score_components: target={target_component:.4f} | key={key_component:.4f} | total={score:.4f}"
            )
            if path.get("description"):
                lines.append(f"   description: {_clean_inline(path.get('description'))}")
            if path.get("start_url"):
                lines.append(f"   start_url: {_clean_inline(path.get('start_url'))}")

            steps = path.get("steps") or []
            lines.append("   path_chain:")
            if steps:
                for step_idx, step in enumerate(steps, 1):
                    state = step.get("state") or {}
                    lines.append(f"     {step_idx}. {_format_state_line(state)}")
            else:
                lines.append("     (none)")

            lines.append("   steps:")
            if steps:
                for step_idx, step in enumerate(steps, 1):
                    state = step.get("state") or {}
                    action = step.get("action") or {}
                    intent_seq = step.get("intent_sequence") or {}

                    lines.append(f"     step {step_idx}:")
                    lines.append(f"       state: {_format_state_line(state)}")

                    if action:
                        action_desc = _clean_inline(action.get("description"))
                        action_type = _clean_inline(action.get("type"))
                        action_line = action_desc or "N/A"
                        if action_type:
                            action_line += f" | type={action_type}"
                        lines.append(f"       action: {action_line}")

                        trigger = action.get("trigger_intent") or {}
                        if trigger:
                            trig_text = _clean_inline(trigger.get("text"))
                            trig_selector = _clean_inline(trigger.get("css_selector") or trigger.get("xpath"))
                            trig_desc = _clean_inline(trigger.get("description"))
                            trig_parts = []
                            if trig_text:
                                trig_parts.append(f"text={trig_text}")
                            if trig_selector:
                                trig_parts.append(f"selector={trig_selector}")
                            if trig_desc:
                                trig_parts.append(f"desc={trig_desc}")
                            if trig_parts:
                                lines.append(f"       trigger: {' | '.join(trig_parts)}")

                    if intent_seq:
                        seq_desc = _clean_inline(intent_seq.get("description"))
                        lines.append(f"       intent_sequence: {seq_desc or 'N/A'}")
                        intents = intent_seq.get("intents") or []
                        if intents:
                            lines.append("       intents:")
                            for intent in intents:
                                intent_type = _clean_inline(intent.get("type"))
                                intent_text = _clean_inline(intent.get("text"))
                                intent_value = _clean_inline(intent.get("value"))
                                parts = []
                                if intent_type:
                                    parts.append(f"type={intent_type}")
                                if intent_text:
                                    parts.append(f"text={intent_text}")
                                if intent_value:
                                    parts.append(f"value={intent_value}")
                                lines.append(f"         - {' | '.join(parts) if parts else 'N/A'}")
                        else:
                            lines.append("       intents: (none)")

            lines.append("")

        file_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"[Memory] query_path report written: {file_path}")
        return str(file_path)

    # =========================================================================
    # V2 Three-Level Query Methods
    # =========================================================================

    async def _call_local_query(self, payload: Dict[str, Any]) -> QueryResult:
        """Call local Memory Service directly (SurrealDB).

        Args:
            payload: Request payload for memory query

        Returns:
            QueryResult parsed from direct call response
        """
        try:
            from src.common.memory import get_local_memory_service

            memory_service = get_local_memory_service()
            if not memory_service:
                return QueryResult(
                    success=False,
                    query_type=QueryType.TASK,
                    error="Local Memory Service not initialized",
                )

            # Call MemoryService.query() directly
            data = await memory_service.query(
                query=payload.get("target", ""),
                current_state=payload.get("current_state"),
                start_state=payload.get("start_state"),
                end_state=payload.get("end_state"),
            )

            result = QueryResult.from_api_response(data)
            logger.info(
                f"[Memory] Local query result: "
                f"type={result.query_type.value}, success={result.success}, "
                f"states={len(result.states)}, actions={len(result.actions)}, "
                f"intent_sequences={len(result.intent_sequences)}, "
                f"outgoing_actions={len(result.outgoing_actions)}"
            )
            return result

        except Exception as e:
            logger.warning(f"[Memory] Local query failed: {e}")
            return QueryResult(
                success=False,
                query_type=QueryType.TASK,
                error=str(e),
            )

    async def _call_http_query(self, payload: Dict[str, Any]) -> QueryResult:
        """Call Memory API via HTTP (Cloud Backend).

        Args:
            payload: Request payload for /api/v1/memory/query

        Returns:
            QueryResult parsed from API response
        """
        try:
            # Ensure user_id is always in the payload for user-scoped queries
            if "user_id" not in payload and self._user_id:
                payload["user_id"] = self._user_id

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._memory_api_base_url}/api/v1/memory/query",
                    json=payload,
                    headers={"X-Ami-API-Key": self._ami_api_key},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()

            result = QueryResult.from_api_response(data)
            logger.info(
                f"[Memory] HTTP query result: "
                f"type={result.query_type.value}, success={result.success}, "
                f"states={len(result.states)}, actions={len(result.actions)}, "
                f"intent_sequences={len(result.intent_sequences)}, "
                f"outgoing_actions={len(result.outgoing_actions)}"
            )
            return result

        except httpx.HTTPStatusError as e:
            logger.warning(f"[Memory] HTTP error: {e.response.status_code} - {e.response.text}")
            return QueryResult(
                success=False,
                query_type=QueryType.TASK,
                error=f"HTTP {e.response.status_code}: {e.response.text}",
            )
        except httpx.RequestError as e:
            logger.warning(f"[Memory] Request error: {e}")
            return QueryResult(
                success=False,
                query_type=QueryType.TASK,
                error=f"Request failed: {str(e)}",
            )
        except Exception as e:
            logger.warning(f"[Memory] HTTP query failed: {e}")
            return QueryResult(
                success=False,
                query_type=QueryType.TASK,
                error=str(e),
            )

    async def _call_v2_query(self, payload: Dict[str, Any]) -> QueryResult:
        """Call Memory API - local or HTTP based on configuration.

        Args:
            payload: Request payload for memory query

        Returns:
            QueryResult parsed from response
        """
        if not self.is_available():
            return QueryResult(
                success=False,
                query_type=QueryType.TASK,
                error="Memory toolkit not available",
            )

        # Use local memory if configured
        if self._use_local_memory:
            logger.info("[Memory] Using local memory (SurrealDB)")
            return await self._call_local_query(payload)

        # Otherwise use HTTP to Cloud Backend
        logger.info(f"[Memory] Using public memory ({self._memory_api_base_url})")
        return await self._call_http_query(payload)

    async def query_task(self, task: str) -> QueryResult:
        """Task-level query: Get complete workflow for a task.

        Use when starting a new task without knowing current state.
        Returns CognitivePhrase (if exact match) or composed path.

        Args:
            task: Natural language task description
                  e.g., "在 Product Hunt 查看团队信息"

        Returns:
            QueryResult with:
            - cognitive_phrase: If exact user-recorded workflow found
            - execution_plan: Step-by-step execution plan
            - states/actions: Path components if composed
        """
        logger.info(f"[Memory] Task query: {task[:50]}...")

        result = await self._call_v2_query({"target": task})

        if result.success:
            if result.cognitive_phrase:
                logger.info(
                    f"[Memory] Found CognitivePhrase: {result.cognitive_phrase.id}"
                )
            else:
                logger.info(
                    f"[Memory] Found composed path: {len(result.states)} states"
                )
        else:
            logger.info(f"[Memory] No task result for: {task[:30]}...")

        return result

    async def query_navigation(
        self,
        start_state: str,
        end_state: str,
    ) -> QueryResult:
        """Navigation-level query: Get path between two states.

        Use when you know current state and want to reach a target state.
        Both start and end can be state IDs or semantic descriptions.

        Args:
            start_state: Starting state ID or description
                         e.g., "state_123" or "Product Hunt 首页"
            end_state: Target state ID or description
                       e.g., "state_456" or "产品详情页"

        Returns:
            QueryResult with states and actions forming the shortest path
        """
        logger.info(
            f"[Memory] Navigation query: {start_state[:30]}... -> {end_state[:30]}..."
        )

        result = await self._call_v2_query({
            "start_state": start_state,
            "end_state": end_state,
        })

        if result.success:
            logger.info(
                f"[Memory] Found path: {len(result.states)} states, "
                f"{len(result.actions)} actions"
            )
        else:
            logger.info(f"[Memory] No navigation path found")

        return result

    async def query_actions(
        self,
        current_state: str,
        target: Optional[str] = None,
    ) -> QueryResult:
        """Action-level query: Get available operations on current page.

        Use when on a specific page and need to know what can be done.

        Args:
            current_state: Current state ID or description
                           e.g., "state_123" or "产品详情页"
            target: Optional target action description
                    e.g., "查看团队" or None for exploring all options

        Returns:
            QueryResult with:
            - intent_sequences: Available operations on this page
            - outgoing_actions: Navigation actions to other pages
        """
        if target:
            logger.info(
                f"[Memory] Action query: {target[:30]}... on {current_state[:30]}..."
            )
        else:
            logger.info(f"[Memory] Explore query: {current_state[:30]}...")

        payload = {"current_state": current_state}
        if target:
            payload["target"] = target

        result = await self._call_v2_query(payload)

        if result.success:
            logger.info(
                f"[Memory] Found {len(result.intent_sequences)} sequences, "
                f"{len(result.outgoing_actions)} outgoing actions"
            )
        else:
            logger.info(f"[Memory] No actions found")

        return result

    async def query_page_operations(self, url: str) -> str:
        """Query available operations for the current page from memory.

        Use this tool when you're on a complex page and want to know what
        operations users have performed here before. This helps you understand
        what actions are possible on this page.

        When an agent reference is set, successful query results are cached
        in the agent for injection into subsequent LLM calls (avoiding
        repeated queries for the same page).

        Args:
            url: Current page URL (e.g., "https://producthunt.com/products/xxx")

        Returns:
            Formatted string describing available operations on this page.
            Returns empty message if no recorded operations found.
        """
        logger.info(f"[Memory] query_page_operations: {url[:80]}...")

        result = await self._call_v2_query({
            "current_state": url,
            "target": "",
        })

        if result.success and (result.intent_sequences or result.outgoing_actions):
            logger.info(
                f"[Memory] Found {len(result.intent_sequences)} operations, "
                f"{len(result.outgoing_actions)} navigation actions"
            )
            formatted_result = self.format_page_operations(
                result.intent_sequences, result.outgoing_actions
            )
            logger.debug(
                "[Memory] page_operations formatted "
                f"(intent_sequences={len(result.intent_sequences)}, "
                f"outgoing_actions={len(result.outgoing_actions)}, "
                f"length={len(formatted_result)})"
            )

            # Cache in agent for subsequent LLM calls
            if self._agent and hasattr(self._agent, 'cache_page_operations'):
                try:
                    intent_sequence_ids = [
                        seq.id for seq in result.intent_sequences if seq.id
                    ]
                    self._agent.cache_page_operations(
                        url,
                        formatted_result,
                        intent_sequence_ids=intent_sequence_ids,
                    )
                    logger.debug(
                        f"[Memory] Cached page operations in agent for: {url[:50]}..."
                    )
                except Exception as e:
                    logger.debug(f"[Memory] Failed to cache page operations: {e}")

            return formatted_result

        logger.info(f"[Memory] No recorded operations for this page")
        if result.success:
            logger.debug(
                "[Memory] page_operations empty "
                f"(intent_sequences={len(result.intent_sequences)}, "
                f"outgoing_actions={len(result.outgoing_actions)})"
            )
        return ""

    # =========================================================================
    # Context Formatters (V2)
    # =========================================================================

    @staticmethod
    def format_task_result(result: QueryResult) -> str:
        """Format task query result for LLM context.

        Both L1 (CognitivePhrase) and L2 (composed path) use the same concise
        navigation-path format. The detailed intent_sequences / trigger info
        from CognitivePhrase is only needed at runtime (workflow_guide), not
        during task decomposition.
        """
        if not result.success:
            return ""

        if result.states:
            return MemoryToolkit.format_navigation_path(result.states, result.actions)
        return ""

    @staticmethod
    def _format_intent_brief(intent: Intent) -> str:
        line = MemoryToolkit._format_intent_compact(intent)
        if not line:
            line = MemoryToolkit._format_intent(intent)
        if line.startswith("- "):
            return line[2:]
        return line

    @staticmethod
    def _format_action_trigger(action: Action) -> str:
        if not action.trigger:
            return ""
        trigger = action.trigger
        text = trigger.get("text")
        role = trigger.get("role") or trigger.get("element_role")
        ref = trigger.get("ref") or trigger.get("element_ref")
        parts = []
        if text:
            parts.append(f'text="{text}"')
        if role:
            parts.append(f"role={role}")
        if ref:
            parts.append(f"ref={ref}")
        return ", ".join(parts)

    @staticmethod
    def _append_intent_sequences(
        lines: List[str],
        intent_sequences: List[IntentSequence],
        indent: str = "  ",
    ) -> None:
        if not intent_sequences:
            return
        lines.append(f"{indent}Intent sequences:")
        for idx, seq in enumerate(intent_sequences[:_MAX_GUIDE_SEQUENCES], 1):
            desc = seq.description or "Operation"
            seq_id = seq.id or ""
            label = f"{idx}. {desc}"
            if seq_id:
                label += f" (id: {seq_id})"
            lines.append(f"{indent}  {label}")

            if seq.causes_navigation and seq.navigation_target_state_id:
                lines.append(f"{indent}     navigates_to: {seq.navigation_target_state_id}")

            if seq.intents:
                lines.append(f"{indent}     intents:")
                for intent in seq.intents[:_MAX_GUIDE_INTENTS]:
                    intent_line = MemoryToolkit._format_intent_brief(intent)
                    if intent_line:
                        lines.append(f"{indent}       - {intent_line}")
            else:
                lines.append(f"{indent}     intents: (none)")

        remaining = len(intent_sequences) - _MAX_GUIDE_SEQUENCES
        if remaining > 0:
            lines.append(f"{indent}  ... ({remaining} more sequences)")

    @staticmethod
    def format_cognitive_phrase(phrase: CognitivePhrase) -> str:
        """Format CognitivePhrase for LLM context.

        Note: This is reference information. Pages may have changed.
        """
        lines = [f"**Workflow**: {phrase.description}\n"]

        # Use execution_plan if available for structured steps
        if phrase.execution_plan:
            state_map = {s.id: s for s in phrase.states}
            action_map = {a.id: a for a in phrase.actions}
            # Fallback: lookup by state pair (source_id, target_id) since
            # action IDs in execution_plan may be stale after edge upserts
            action_by_pair = {
                (a.source_id, a.target_id): a for a in phrase.actions
            }

            for step_idx, step in enumerate(phrase.execution_plan):
                state = state_map.get(step.state_id)
                if not state:
                    continue

                lines.append(f"Step {step.index}: {state.description}")
                if state.page_url:
                    lines.append(f"  URL: {state.page_url}")
                if state.intent_sequences:
                    MemoryToolkit._append_intent_sequences(
                        lines, state.intent_sequences, indent="  "
                    )

                # Navigation to next
                if step.navigation_action_id:
                    action = action_map.get(step.navigation_action_id)
                    # Fallback: match by state pair if ID lookup fails
                    if not action:
                        next_step_idx = step_idx + 1
                        if next_step_idx < len(phrase.execution_plan):
                            next_state_id = phrase.execution_plan[next_step_idx].state_id
                            action = action_by_pair.get(
                                (step.state_id, next_state_id)
                            )
                    if action:
                        nav_desc = action.description or "next"
                        if action.trigger and action.trigger.get("text"):
                            nav_desc += f" (click \"{action.trigger['text']}\")"
                        lines.append(f"  -> {nav_desc}")
                        trigger_line = MemoryToolkit._format_action_trigger(action)
                        if trigger_line:
                            lines.append(f"     trigger: {trigger_line}")
                        if action.trigger_sequence_id:
                            lines.append(
                                f"     trigger_sequence_id: {action.trigger_sequence_id}"
                            )
        else:
            # Fallback: list states and actions
            for i, state in enumerate(phrase.states, 1):
                lines.append(f"Step {i}: {state.description}")
                if state.page_url:
                    lines.append(f"  URL: {state.page_url}")
                if state.intent_sequences:
                    MemoryToolkit._append_intent_sequences(
                        lines, state.intent_sequences, indent="  "
                    )

                if i <= len(phrase.actions):
                    action = phrase.actions[i - 1]
                    nav_desc = action.description or "Next"
                    if action.trigger and action.trigger.get("text"):
                        nav_desc += f" (click \"{action.trigger['text']}\")"
                    lines.append(f"  -> {nav_desc}")
                    trigger_line = MemoryToolkit._format_action_trigger(action)
                    if trigger_line:
                        lines.append(f"     trigger: {trigger_line}")
                    if action.trigger_sequence_id:
                        lines.append(
                            f"     trigger_sequence_id: {action.trigger_sequence_id}"
                        )

        return "\n".join(lines)

    @staticmethod
    def format_navigation_path(states: List[State], actions: List[Action]) -> str:
        """Format navigation path for LLM context.

        Shows route between states with actions as transitions.
        Note: This is reference information. Pages may have changed.
        """
        if not states:
            return ""

        lines = ["**Navigation Path**:\n"]

        for i, state in enumerate(states, 1):
            lines.append(f"Step {i}: {state.description}")
            if state.page_url:
                lines.append(f"  URL: {state.page_url}")
            if state.intent_sequences:
                MemoryToolkit._append_intent_sequences(
                    lines, state.intent_sequences, indent="  "
                )

            # Show action to next state
            if i <= len(actions):
                action = actions[i - 1]
                nav_desc = action.description or "next"
                if action.trigger and action.trigger.get("text"):
                    nav_desc += f" (click \"{action.trigger['text']}\")"
                lines.append(f"  -> {nav_desc}")
                trigger_line = MemoryToolkit._format_action_trigger(action)
                if trigger_line:
                    lines.append(f"     trigger: {trigger_line}")
                if action.trigger_sequence_id:
                    lines.append(
                        f"     trigger_sequence_id: {action.trigger_sequence_id}"
                    )

        return "\n".join(lines)

    @staticmethod
    def format_action_result(result: QueryResult) -> str:
        """Format action query result for LLM context.

        Shows available operations on current page.
        """
        if not result.success:
            return ""

        lines = ["## AVAILABLE ACTIONS ON CURRENT PAGE\n"]

        # In-page operations (IntentSequences)
        if result.intent_sequences:
            lines.append("**Operations you can perform:**")
            for seq in result.intent_sequences:
                lines.append(f"\n- **{seq.description or 'Operation'}**")
                lines.append(f"  sequence_id: {seq.id}")
                if seq.causes_navigation:
                    lines.append(f"  (navigates to: {seq.navigation_target_state_id})")

                # Show intents
                for intent in seq.intents[:3]:
                    intent_desc = MemoryToolkit._format_intent(intent)
                    if intent_desc:
                        lines.append(f"    {intent_desc}")

        # Outgoing navigation actions
        if result.outgoing_actions:
            lines.append("\n**Navigation to other pages:**")
            for action in result.outgoing_actions:
                lines.append(f"\n- {action.description or 'Navigate'}")
                lines.append(f"  target: {action.target_id}")
                if action.trigger:
                    trigger = action.trigger
                    if trigger.get("text"):
                        lines.append(f"  Click: \"{trigger['text']}\"")

        if not result.intent_sequences and not result.outgoing_actions:
            lines.append("No recorded operations found for this page.")

        return "\n".join(lines)

    @staticmethod
    def format_page_operations(
        intent_sequences: List[IntentSequence],
        outgoing_actions: List[Action],
    ) -> str:
        """Format page operations for LLM context (simplified format).

        This format is designed for the query_page_operations tool,
        providing concise, actionable information.

        Args:
            intent_sequences: List of IntentSequence objects.
            outgoing_actions: List of Action objects for navigation.

        Returns:
            Formatted string for LLM consumption.
        """
        total_count = len(intent_sequences) + len(outgoing_actions)
        lines = [f"## Page Operations ({total_count} recorded)\n"]

        # Collect user interests (select_text) separately
        user_interests: List[str] = []

        # In-page operations
        for i, seq in enumerate(intent_sequences, 1):
            nav_marker = " → navigates" if seq.causes_navigation else ""
            lines.append(f"{i}. \"{seq.description or 'Operation'}\"{nav_marker}")

            # Show intents with actionable info
            for intent in seq.intents:
                if intent.type.lower() == "selecttext" and intent.text:
                    # SelectText = user interest signal, not an executable action
                    snippet = intent.text[:100]
                    if len(intent.text) > 100:
                        snippet += "..."
                    user_interests.append(snippet)
                    continue
                intent_line = MemoryToolkit._format_intent_compact(intent)
                if intent_line:
                    lines.append(f"   {intent_line}")

        # Navigation actions
        if outgoing_actions:
            if intent_sequences:
                lines.append("")
            lines.append("**Navigation options:**")
            for action in outgoing_actions:
                desc = action.description or "Navigate"
                trigger_text = ""
                if action.trigger and action.trigger.get("text"):
                    trigger_text = f" (click \"{action.trigger['text']}\")"
                lines.append(f"- {desc}{trigger_text}")

        # User interests from text selections
        if user_interests:
            lines.append("")
            lines.append("**User interests on this page:**")
            for interest in user_interests:
                lines.append(f"- \"{interest}\"")

        return "\n".join(lines)

    @staticmethod
    def _format_intent_compact(intent: Intent) -> str:
        """Format single intent in compact form for page operations display."""
        intent_type = intent.type.lower()
        role = intent.element_role or ""
        text = intent.text or ""
        attrs = intent.attributes if isinstance(intent.attributes, dict) else {}

        if intent_type in ["click", "clickelement"]:
            if role and text:
                return f"- click {role} \"{text}\""
            elif text:
                return f"- click \"{text}\""
            elif role:
                return f"- click {role}"
        elif intent_type in ["type", "input", "typetext"]:
            target = text or role or "field"
            return f"- type in {target}"
        elif intent_type in ["scroll", "scrolldown", "scrollup"]:
            direction = attrs.get("scroll_direction") or (
                "down" if "down" in intent_type else "up" if "up" in intent_type else ""
            )
            distance = attrs.get("scroll_distance")
            if distance is not None and str(distance) != "":
                distance_str = str(distance)
                if distance_str.isdigit():
                    distance_str = f"{distance_str}px"
                return f"- scroll {direction} {distance_str}".strip()
            return f"- scroll {direction}".strip()

        return ""

    @staticmethod
    def _format_intent(intent: Intent) -> str:
        """Format single intent for display."""
        intent_type = intent.type.lower()
        attrs = intent.attributes if isinstance(intent.attributes, dict) else {}

        if intent_type in ["click", "clickelement"]:
            if intent.text:
                return f"- Click: \"{intent.text}\""
            elif intent.element_ref:
                return f"- Click element: {intent.element_ref}"
        elif intent_type in ["type", "input", "typetext"]:
            return f"- Type: \"{intent.value or intent.text or ''}\""
        elif intent_type in ["scroll", "scrolldown", "scrollup"]:
            direction = attrs.get("scroll_direction") or (
                "down" if "down" in intent_type else "up" if "up" in intent_type else ""
            )
            distance = attrs.get("scroll_distance")
            if distance is not None and str(distance) != "":
                distance_str = str(distance)
                if distance_str.isdigit():
                    distance_str = f"{distance_str}px"
                return f"- Scroll: {direction} {distance_str}".strip()
            if direction:
                return f"- Scroll: {direction}"
            return "- Scroll"
        elif intent_type in ["navigate", "goto"]:
            return f"- Navigate: {intent.value or intent.text or ''}"
        elif intent_type == "selecttext":
            snippet = (intent.text or "")[:100]
            if len(intent.text or "") > 100:
                snippet += "..."
            return f"- [User interest]: \"{snippet}\""
        else:
            if intent.text or intent.value:
                return f"- {intent_type}: {intent.text or intent.value}"

        return ""

    @staticmethod
    def format_result(result: QueryResult) -> str:
        """Format any QueryResult based on its type."""
        if not result.success:
            return ""

        if result.query_type == QueryType.TASK:
            return MemoryToolkit.format_task_result(result)
        elif result.query_type == QueryType.NAVIGATION:
            return MemoryToolkit.format_navigation_path(result.states, result.actions)
        elif result.query_type == QueryType.ACTION:
            return MemoryToolkit.format_action_result(result)
        return ""

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def is_available(self) -> bool:
        """Check if memory functionality is available.

        Returns True if:
        - Local mode: local memory service is initialized
        - HTTP mode: httpx is available and API is configured
        """
        if self._use_local_memory:
            # Check if local memory service is available
            try:
                from src.common.memory import get_local_memory_service
                return get_local_memory_service() is not None
            except ImportError:
                return False

        # HTTP mode: check httpx and config
        return HTTPX_AVAILABLE and bool(
            self._memory_api_base_url and self._ami_api_key
        )

    def get_tools(self) -> List[FunctionTool]:
        """Return FunctionTool objects for LLM tool-use.

        Exposes query_page_operations as an LLM-callable tool.
        Other query methods (query_task, query_navigation, query_actions)
        are called by the agent framework directly.
        """
        # query_page_operations has a proper docstring that CAMEL will extract
        return [FunctionTool(self.query_page_operations)]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Memory Toolkit"


# =============================================================================
# Exported Symbols
# =============================================================================

__all__ = [
    # Data models
    "Intent",
    "IntentSequence",
    "State",
    "Action",
    "ExecutionStep",
    "CognitivePhrase",
    "QueryType",
    "SubTaskResult",
    "QueryResult",
    # Toolkit
    "MemoryToolkit",
]
