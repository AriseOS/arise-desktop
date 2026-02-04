"""
AMI Task Planner - Lightweight task decomposition and Memory integration.

This module replaces CAMEL Workforce's task decomposition with a simpler system:
- Coarse-grained decomposition by agent type (browser, document, code)
- Memory query for each subtask to get workflow guidance
- Returns AMISubtask objects ready for AMITaskExecutor

No CAMEL Workforce dependencies - just uses ChatAgent for LLM calls.
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from camel.agents import ChatAgent
    from ..tools.toolkits import MemoryToolkit, QueryResult

from src.common.llm import parse_json_with_repair
from .ami_task_executor import AMISubtask, SubtaskState
from ..events import (
    DecomposeProgressData,
    MemoryLevelData,
    NoticeData,
)

logger = logging.getLogger(__name__)

_MAX_GUIDE_SEQUENCES = 3
_MAX_GUIDE_INTENTS = 20


# =============================================================================
# Prompts for Task Decomposition
# =============================================================================

# Coarse-grained decomposition prompt - splits by agent type
COARSE_DECOMPOSE_PROMPT = """Split the task by work type. Keep related operations of the same type together.

Types:
- browser: Web browsing, research, online operations
- document: Writing reports, creating files
- code: Programming, terminal commands

Output JSON:
{{
    "subtasks": [
        {{"id": "1", "type": "browser", "content": "...", "depends_on": []}},
        {{"id": "2", "type": "document", "content": "...", "depends_on": ["1"]}}
    ]
}}

Task: {task}"""


class AMITaskPlanner:
    """
    Task planner that replaces CAMEL Workforce's decomposition logic.

    Key features:
    - Coarse-grained decomposition by agent type
    - Memory query for each subtask
    - Returns AMISubtask objects with workflow_guide
    - SSE events for real-time UI updates

    Unlike CAMEL Workforce:
    - No coordinator agent complexity
    - No task tree management
    - Direct LLM calls for decomposition
    - ~400 lines vs ~1700 lines
    """

    def __init__(
        self,
        task_id: str,
        task_state: Any,  # TaskState for SSE events
        task_agent: "ChatAgent",  # LLM agent for decomposition
        memory_toolkit: Optional["MemoryToolkit"] = None,
    ):
        """
        Initialize the task planner.

        Args:
            task_id: Unique task identifier for events.
            task_state: TaskState instance for SSE event emission.
            task_agent: ChatAgent instance for LLM calls.
            memory_toolkit: Optional MemoryToolkit for workflow guidance.
        """
        self.task_id = task_id
        self._task_state = task_state
        self._task_agent = task_agent
        self._memory_toolkit = memory_toolkit

        logger.info(
            f"[AMITaskPlanner] Initialized for task {task_id}, "
            f"memory_toolkit={'available' if memory_toolkit else 'not available'}"
        )

    async def _emit_event(self, event: Any) -> None:
        """Emit an event to the task's event queue."""
        if self._task_state and hasattr(self._task_state, 'put_event'):
            await self._task_state.put_event(event)

    async def decompose_and_query_memory(self, task: str) -> List[AMISubtask]:
        """
        Decompose task and query Memory for each subtask.

        This is the main entry point that combines:
        1. Coarse-grained decomposition by agent type
        2. Memory query for each subtask
        3. Returns AMISubtask objects with workflow_guide

        Args:
            task: The original task description from user.

        Returns:
            List of AMISubtask objects ready for execution.
        """
        logger.info(f"[AMITaskPlanner] Decomposing task: {task[:100]}...")

        # Step 1: Coarse decomposition
        subtasks = await self._coarse_decompose(task)

        # Step 2: Query Memory for each subtask
        await self._query_memory_for_subtasks(subtasks)

        # Emit final decomposition event
        subtasks_data = [
            {
                "id": st.id,
                "content": st.content,
                "state": st.state.value,
                "agent_type": st.agent_type,
                "memory_level": st.memory_level,
            }
            for st in subtasks
        ]

        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=1.0,
            message="Decomposition complete",
            sub_tasks=subtasks_data,
            is_final=True,
        ))

        return subtasks

    async def _coarse_decompose(self, task: str) -> List[AMISubtask]:
        """
        Coarse-grained task decomposition - split task by agent type.

        Args:
            task: The original task description.

        Returns:
            List of AMISubtask objects (without Memory context yet).

        Raises:
            ValueError: If LLM response cannot be parsed.
        """
        logger.info(f"[AMITaskPlanner] Coarse decomposing task...")

        # Emit progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.1,
            message="Analyzing task types...",
            is_final=False,
        ))

        # Build the prompt
        prompt = COARSE_DECOMPOSE_PROMPT.format(task=task)

        # Call LLM for coarse decomposition
        self._task_agent.reset()
        response = self._task_agent.step(prompt)

        if not response or not response.msg:
            raise ValueError("Coarse decomposition returned empty response")

        response_text = response.msg.content
        logger.debug(f"[AMITaskPlanner] Coarse decompose raw response: {response_text[:500]}...")

        # Parse the JSON response
        subtasks = self._parse_coarse_subtasks(response_text)

        # Log summary
        type_counts: Dict[str, int] = {}
        for st in subtasks:
            type_counts[st.agent_type] = type_counts.get(st.agent_type, 0) + 1
        logger.info(
            f"[AMITaskPlanner] Coarse decomposition complete: {len(subtasks)} subtasks "
            f"(types: {type_counts})"
        )

        # Emit progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.3,
            message=f"Identified {len(subtasks)} subtasks",
            is_final=False,
        ))

        return subtasks

    def _parse_coarse_subtasks(self, response_text: str) -> List[AMISubtask]:
        """
        Parse LLM response into AMISubtask objects.

        Args:
            response_text: Raw LLM response text.

        Returns:
            List of parsed AMISubtask objects.

        Raises:
            ValueError: If response cannot be parsed or is missing required fields.
        """
        # Use common JSON parsing with repair
        data = parse_json_with_repair(response_text)

        # Check for fallback (parsing failed completely)
        if "answer" in data and "subtasks" not in data:
            logger.error(f"[AMITaskPlanner] JSON parsing failed, got fallback: {response_text[:500]}")
            raise ValueError("Invalid JSON in coarse decomposition response")

        # Validate structure
        if "subtasks" not in data:
            raise ValueError("Coarse decomposition response missing 'subtasks' field")

        subtasks = []
        for item in data["subtasks"]:
            # Validate required fields
            if "id" not in item or "type" not in item or "content" not in item:
                logger.warning(f"[AMITaskPlanner] Skipping invalid subtask: {item}")
                continue

            # Validate agent type
            agent_type = item["type"].lower()
            if agent_type not in ("browser", "document", "code"):
                logger.warning(
                    f"[AMITaskPlanner] Unknown agent type '{agent_type}', defaulting to 'browser'"
                )
                agent_type = "browser"

            subtask = AMISubtask(
                id=str(item["id"]),
                content=item["content"],
                agent_type=agent_type,
                depends_on=item.get("depends_on", []),
            )
            subtasks.append(subtask)

        if not subtasks:
            raise ValueError("Coarse decomposition produced no valid subtasks")

        return subtasks

    async def _query_memory_for_subtasks(self, subtasks: List[AMISubtask]) -> None:
        """
        Query Memory for each subtask.

        This method iterates over all subtasks and queries Memory for each one.
        Results are stored in the AMISubtask objects:
        - memory_level: L1/L2/L3 based on match quality
        - workflow_guide: Formatted guidance text for injection

        Args:
            subtasks: List of AMISubtask objects to query Memory for.
        """
        if not self._memory_toolkit:
            logger.info("[AMITaskPlanner] Memory toolkit not configured, skipping queries")
            return

        if not self._memory_toolkit.is_available():
            logger.info("[AMITaskPlanner] Memory service not available, skipping queries")
            return

        logger.info(f"[AMITaskPlanner] Querying Memory for {len(subtasks)} subtasks...")

        # Emit progress event
        await self._emit_event(DecomposeProgressData(
            task_id=self.task_id,
            progress=0.4,
            message="Querying Memory for each subtask...",
            is_final=False,
        ))

        for i, subtask in enumerate(subtasks):
            try:
                logger.info(
                    f"[AMITaskPlanner] Querying Memory for subtask {subtask.id}: "
                    f"{subtask.content[:50]}..."
                )

                result = await self._memory_toolkit.query_task(subtask.content)

                # Determine memory level and format guide
                if result.cognitive_phrase:
                    # L1: Complete workflow match
                    subtask.memory_level = "L1"
                    subtask.workflow_guide = self._format_cognitive_phrase(result.cognitive_phrase)
                    states_count = len(result.cognitive_phrase.states) if hasattr(result.cognitive_phrase, 'states') else 0
                    logger.info(
                        f"[AMITaskPlanner] Subtask {subtask.id}: L1 match with "
                        f"{states_count} states"
                    )
                    logger.debug(
                        f"[AMITaskPlanner] Subtask {subtask.id}: "
                        f"workflow_guide_len={len(subtask.workflow_guide or '')}"
                    )

                elif result.states:
                    # L2: Partial path match
                    subtask.memory_level = "L2"
                    subtask.workflow_guide = self._format_navigation_path(
                        result.states, result.actions or []
                    )
                    logger.info(
                        f"[AMITaskPlanner] Subtask {subtask.id}: L2 match with "
                        f"{len(result.states)} states"
                    )
                    logger.debug(
                        f"[AMITaskPlanner] Subtask {subtask.id}: "
                        f"workflow_guide_len={len(subtask.workflow_guide or '')}"
                    )

                else:
                    # L3: No match
                    subtask.memory_level = "L3"
                    logger.info(f"[AMITaskPlanner] Subtask {subtask.id}: L3 (no match)")
                    logger.debug(
                        f"[AMITaskPlanner] Subtask {subtask.id}: workflow_guide_len=0"
                    )

                # Emit memory level event for this subtask
                await self._emit_event(MemoryLevelData(
                    task_id=self.task_id,
                    level=subtask.memory_level,
                    reason=f"Memory query for subtask {subtask.id}",
                    states_count=len(result.states) if result.states else 0,
                    method="ami_task_planner",
                ))

            except Exception as e:
                logger.warning(
                    f"[AMITaskPlanner] Memory query failed for subtask {subtask.id}: {e}"
                )
                subtask.memory_level = "L3"

            # Update progress
            progress = 0.4 + (0.5 * (i + 1) / len(subtasks))
            await self._emit_event(DecomposeProgressData(
                task_id=self.task_id,
                progress=progress,
                message=f"Memory query {i + 1}/{len(subtasks)} complete",
                is_final=False,
            ))

        # Log summary
        level_counts = {"L1": 0, "L2": 0, "L3": 0}
        for st in subtasks:
            level_counts[st.memory_level] = level_counts.get(st.memory_level, 0) + 1
        logger.info(
            f"[AMITaskPlanner] Memory queries complete: L1={level_counts['L1']}, "
            f"L2={level_counts['L2']}, L3={level_counts['L3']}"
        )

    @staticmethod
    def _format_intent_for_guide(intent: Any) -> str:
        intent_type = str(getattr(intent, "type", "") or "").lower()
        element_role = getattr(intent, "element_role", None) or getattr(intent, "role", None)
        element_ref = getattr(intent, "element_ref", None) or getattr(intent, "ref", None)
        text = getattr(intent, "text", None)
        value = getattr(intent, "value", None)
        attributes = getattr(intent, "attributes", None)
        attrs = attributes if isinstance(attributes, dict) else {}

        if intent_type in ("click", "clickelement"):
            if text:
                return f"click \"{text}\""
            if element_role:
                return f"click {element_role}"
            if element_ref:
                return f"click element {element_ref}"
        elif intent_type in ("type", "input", "typetext"):
            target = text or element_role or "field"
            if value:
                return f"type \"{value}\" in {target}"
            return f"type in {target}"
        elif intent_type in ("scroll", "scrolldown", "scrollup"):
            direction = attrs.get("scroll_direction") or (
                "down" if "down" in intent_type else "up" if "up" in intent_type else ""
            )
            distance = attrs.get("scroll_distance")
            if distance is not None and str(distance) != "":
                distance_str = str(distance)
                if distance_str.isdigit():
                    distance_str = f"{distance_str}px"
                return f"scroll {direction} {distance_str}".strip()
            return f"scroll {direction}".strip()
        elif intent_type in ("navigate", "goto"):
            if value or text:
                return f"navigate to {value or text}"

        if text or value:
            return f"{intent_type or 'intent'}: {text or value}"
        return intent_type or ""

    @staticmethod
    def _append_intent_sequences(
        lines: List[str],
        intent_sequences: List[Any],
        indent: str = "    ",
    ) -> None:
        if not intent_sequences:
            return

        lines.append(f"{indent}Intent sequences (from memory):")
        for idx, seq in enumerate(intent_sequences[:_MAX_GUIDE_SEQUENCES], 1):
            desc = getattr(seq, "description", None) or "Operation"
            seq_id = getattr(seq, "id", "") or ""
            label = f"{idx}. {desc}"
            if seq_id:
                label += f" (id: {seq_id})"
            lines.append(f"{indent}  {label}")

            causes_nav = getattr(seq, "causes_navigation", False)
            nav_target = getattr(seq, "navigation_target_state_id", None)
            if causes_nav and nav_target:
                lines.append(f"{indent}     navigates_to: {nav_target}")

            intents = getattr(seq, "intents", None)
            if intents:
                lines.append(f"{indent}     intents:")
                for intent in intents[:_MAX_GUIDE_INTENTS]:
                    intent_line = AMITaskPlanner._format_intent_for_guide(intent)
                    if intent_line:
                        lines.append(f"{indent}       - {intent_line}")
            else:
                lines.append(f"{indent}     intents: (none)")

        remaining = len(intent_sequences) - _MAX_GUIDE_SEQUENCES
        if remaining > 0:
            lines.append(f"{indent}  ... ({remaining} more sequences)")

    @staticmethod
    def _format_action_trigger(action: Any) -> Optional[str]:
        trigger = getattr(action, "trigger", None)
        if not isinstance(trigger, dict):
            return None

        parts = []
        text = trigger.get("text")
        role = trigger.get("role") or trigger.get("element_role")
        ref = trigger.get("ref") or trigger.get("element_ref")
        if text:
            parts.append(f"text=\"{text}\"")
        if role:
            parts.append(f"role={role}")
        if ref:
            parts.append(f"ref={ref}")
        if not parts:
            return None
        return ", ".join(parts)

    @staticmethod
    def _format_cognitive_phrase(cognitive_phrase: Any) -> str:
        """
        Format a cognitive phrase into a workflow guide.

        This method converts Memory's cognitive_phrase object into a
        human-readable workflow guide that can be injected into prompts.

        Args:
            cognitive_phrase: CognitivePhrase object from Memory.

        Returns:
            Formatted workflow guide string.
        """
        if not cognitive_phrase:
            return ""

        lines = []
        lines.append("## Historical Workflow Guide")
        lines.append("")

        # Add task description if available
        if hasattr(cognitive_phrase, 'task') and cognitive_phrase.task:
            lines.append(f"**Original Task**: {cognitive_phrase.task}")
            lines.append("")

        # Add states as steps
        if hasattr(cognitive_phrase, 'states') and cognitive_phrase.states:
            lines.append("**Steps to follow**:")
            for i, state in enumerate(cognitive_phrase.states, 1):
                # Extract state description
                if hasattr(state, 'description'):
                    desc = state.description
                elif hasattr(state, 'url') and hasattr(state, 'title'):
                    desc = f"{state.title} ({state.url})"
                elif hasattr(state, 'content'):
                    desc = state.content[:200]
                else:
                    desc = str(state)[:200]
                lines.append(f"  Step {i}: {desc}")

                # Add intent sequences if available
                intent_sequences = getattr(state, "intent_sequences", None)
                if intent_sequences:
                    AMITaskPlanner._append_intent_sequences(
                        lines, intent_sequences, indent="    "
                    )

                # Add action if available
                if hasattr(cognitive_phrase, 'actions') and i <= len(cognitive_phrase.actions):
                    action = cognitive_phrase.actions[i - 1]
                    if hasattr(action, 'description'):
                        lines.append(f"    Action: {action.description}")
                    elif hasattr(action, 'action_type'):
                        lines.append(f"    Action: {action.action_type}")

                    trigger_line = AMITaskPlanner._format_action_trigger(action)
                    if trigger_line:
                        lines.append(f"      Trigger: {trigger_line}")
                    trigger_sequence_id = getattr(action, "trigger_sequence_id", None)
                    if trigger_sequence_id:
                        lines.append(f"      Trigger sequence: {trigger_sequence_id}")

        return "\n".join(lines)

    @staticmethod
    def _format_navigation_path(states: List[Any], actions: List[Any]) -> str:
        """
        Format a navigation path into a workflow guide.

        This method converts Memory's states and actions into a
        human-readable navigation guide.

        Args:
            states: List of State objects from Memory.
            actions: List of Action objects from Memory.

        Returns:
            Formatted navigation guide string.
        """
        if not states:
            return ""

        lines = []
        lines.append("## Navigation Path Guide")
        lines.append("")
        lines.append("**Pages to visit**:")

        for i, state in enumerate(states, 1):
            # Extract state description
            if hasattr(state, 'url') and hasattr(state, 'title'):
                desc = f"{state.title} - {state.url}"
            elif hasattr(state, 'description'):
                desc = state.description
            elif hasattr(state, 'content'):
                desc = state.content[:200]
            else:
                desc = str(state)[:200]
            lines.append(f"  {i}. {desc}")

            # Add intent sequences if available
            intent_sequences = getattr(state, "intent_sequences", None)
            if intent_sequences:
                AMITaskPlanner._append_intent_sequences(
                    lines, intent_sequences, indent="    "
                )

            # Add action if available
            if i <= len(actions):
                action = actions[i - 1]
                if hasattr(action, 'description'):
                    lines.append(f"     Then: {action.description}")
                elif hasattr(action, 'action_type') and hasattr(action, 'target'):
                    lines.append(f"     Then: {action.action_type} on {action.target}")

                trigger_line = AMITaskPlanner._format_action_trigger(action)
                if trigger_line:
                    lines.append(f"       Trigger: {trigger_line}")
                trigger_sequence_id = getattr(action, "trigger_sequence_id", None)
                if trigger_sequence_id:
                    lines.append(f"       Trigger sequence: {trigger_sequence_id}")

        return "\n".join(lines)

    # =========================================================================
    # Simple decomposition (without Memory)
    # =========================================================================

    async def simple_decompose(self, task: str) -> List[AMISubtask]:
        """
        Simple decomposition without Memory query.

        Use this when Memory is not available or not needed.

        Args:
            task: The original task description.

        Returns:
            List of AMISubtask objects.
        """
        return await self._coarse_decompose(task)
