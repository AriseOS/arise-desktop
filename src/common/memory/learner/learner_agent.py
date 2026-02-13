"""Learner Agent - Post-execution CognitivePhrase generation via LLM Agent loop.

Uses AMIAgent's tool-calling loop with 4 Memory tools to:
1. recall_phrases — Search existing phrases (recall-first dedup)
2. find_states_by_urls — Look up States by URLs
3. get_state_sequences — Get IntentSequences for a State
4. verify_action — Check navigation edges between States

Recall-First workflow: check existing phrases BEFORE analyzing execution
trace. LLM judges coverage (no hard similarity threshold).
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional

from src.common.memory.ontology.cognitive_phrase import CognitivePhrase, ExecutionStep

from .models import LearnResult, LearningPlan, PhraseCandidate, TaskExecutionData
from .prompts import LEARNER_SYSTEM_PROMPT
from .tools import LearnerTools

logger = logging.getLogger(__name__)


class LearnerAgent:
    """Post-execution Learner Agent.

    Analyzes task execution data and creates CognitivePhrases for
    successful workflows. Uses recall-first workflow: check existing
    phrases before analyzing, LLM judges coverage.

    Located in Memory module, directly accesses Memory interfaces.
    Called by MemoryService.learn() via Cloud Backend API.
    """

    def __init__(
        self,
        memory,
        llm_provider,
        embedding_service,
        task_state=None,
    ):
        """Initialize LearnerAgent.

        Args:
            memory: WorkflowMemory instance (private user memory).
            llm_provider: AnthropicProvider for LLM calls.
            embedding_service: EmbeddingService for query encoding.
            task_state: TaskState for SSE events (optional).
        """
        from src.clients.desktop_app.ami_daemon.base_agent.core.ami_agent import (
            AMIAgent,
        )
        from src.clients.desktop_app.ami_daemon.base_agent.core.ami_tool import (
            AMITool,
        )

        self._memory = memory
        self._embedding_service = embedding_service

        # Create LearnerTools instance
        self._tools_impl = LearnerTools(memory, embedding_service)

        # Wrap as AMITool list
        tools = [
            AMITool(self._tools_impl.recall_phrases),
            AMITool(self._tools_impl.find_states_by_urls),
            AMITool(self._tools_impl.get_state_sequences),
            AMITool(self._tools_impl.verify_action),
        ]

        # Use DummyTaskState if none provided
        if task_state is None:
            task_state = _DummyTaskState()

        # Create internal AMIAgent
        self._agent = AMIAgent(
            task_state=task_state,
            agent_name="LearnerAgent",
            provider=llm_provider,
            system_prompt=LEARNER_SYSTEM_PROMPT,
            tools=tools,
            max_iterations=8,
        )

    async def learn(self, execution_data: TaskExecutionData) -> LearnResult:
        """Analyze execution data and optionally create CognitivePhrases.

        Recall-First flow:
        1. Format execution data as text prompt
        2. astep(prompt) starts the agent loop
        3. LLM recalls existing phrases, judges coverage, analyzes new parts
        4. LLM outputs <learning_plan> XML with coverage_judgment + candidates
        5. Parse XML into LearningPlan
        6. For each candidate with should_create → _create_phrase()
        7. Return LearnResult with all created phrase IDs

        Args:
            execution_data: Complete task execution data.

        Returns:
            LearnResult with phrase creation status and debug info.
        """
        self._agent.reset()

        # Format execution data as prompt
        prompt = self._format_execution_data(execution_data)

        # Run agent loop
        response = await self._agent.astep(prompt)

        # Parse learning plan from output
        learning_plan = self._parse_learning_plan(response.text)

        # Create phrases for each candidate that should be created
        phrase_ids = []
        for candidate in learning_plan.phrase_candidates:
            if candidate.should_create:
                pid = self._create_phrase(candidate)
                if pid:
                    phrase_ids.append(pid)

        return LearnResult(
            phrase_created=len(phrase_ids) > 0,
            phrase_id=phrase_ids[0] if phrase_ids else None,
            phrase_ids=phrase_ids,
            learning_plan=learning_plan,
            debug_trace={
                "agent_messages_count": len(self._agent.get_messages()),
                "execution_subtasks": len(execution_data.subtasks),
                "candidates_count": len(learning_plan.phrase_candidates),
                "phrases_created": len(phrase_ids),
            },
        )

    def _format_execution_data(self, data: TaskExecutionData) -> str:
        """Format TaskExecutionData as a text prompt for the LLM.

        Args:
            data: Complete task execution data.

        Returns:
            Formatted string for the agent prompt.
        """
        parts = [
            f"## Task Execution Data",
            f"",
            f"**Task ID**: {data.task_id}",
            f"**User Request**: {data.user_request}",
            f"**Results**: {data.completed_count} completed, "
            f"{data.failed_count} failed, {data.total_count} total",
            f"",
        ]

        for i, subtask in enumerate(data.subtasks, 1):
            parts.append(f"### Subtask {i}: {subtask.subtask_id}")
            parts.append(f"- **Type**: {subtask.agent_type}")
            parts.append(f"- **Content**: {subtask.content}")
            parts.append(f"- **State**: {subtask.state}")
            if subtask.depends_on:
                parts.append(f"- **Depends on**: {', '.join(subtask.depends_on)}")
            if subtask.result_summary:
                parts.append(f"- **Result**: {subtask.result_summary}")
            parts.append(f"")

            if subtask.tool_records:
                parts.append(f"**Tool Records** ({len(subtask.tool_records)} calls):")
                for j, record in enumerate(subtask.tool_records, 1):
                    parts.append(f"")
                    parts.append(f"  {j}. **{record.tool_name}**")
                    if record.current_url:
                        parts.append(f"     URL: {record.current_url}")
                    if record.thinking:
                        parts.append(f"     Thinking: {record.thinking[:200]}")
                    if record.input_summary:
                        parts.append(f"     Input: {record.input_summary}")
                    parts.append(f"     Success: {record.success}")
                    if record.result_summary:
                        parts.append(f"     Result: {record.result_summary[:200]}")
                    if record.judgment:
                        parts.append(f"     Judgment: {record.judgment[:200]}")
                parts.append(f"")

        parts.append(
            "Analyze this execution following the workflow in your system prompt. "
            "Start by recalling existing phrases."
        )

        return "\n".join(parts)

    def _parse_learning_plan(self, text: str) -> LearningPlan:
        """Parse the LLM's <learning_plan> XML output.

        Supports the new format with <coverage_judgment> and 0..N <phrase_candidate> blocks.

        Args:
            text: LLM's final text output.

        Returns:
            LearningPlan with parsed fields.
        """
        plan_match = re.search(
            r"<learning_plan>(.*?)</learning_plan>", text, re.DOTALL
        )
        if not plan_match:
            logger.warning(
                "LearnerAgent output contained no <learning_plan>. "
                "Defaulting to empty candidates."
            )
            return LearningPlan(
                coverage_judgment="No <learning_plan> found in LLM output",
            )

        content = plan_match.group(1)

        # Parse coverage_judgment
        coverage_judgment = ""
        cj_match = re.search(
            r"<coverage_judgment>(.*?)</coverage_judgment>", content, re.DOTALL
        )
        if cj_match:
            coverage_judgment = cj_match.group(1).strip()

        # Parse all phrase_candidate blocks
        candidates = []
        candidate_pattern = re.compile(
            r"<phrase_candidate>(.*?)</phrase_candidate>", re.DOTALL
        )
        for cm in candidate_pattern.finditer(content):
            candidate_content = cm.group(1)
            candidate = self._parse_phrase_candidate(candidate_content)
            candidates.append(candidate)

        return LearningPlan(
            coverage_judgment=coverage_judgment,
            phrase_candidates=candidates,
        )

    @staticmethod
    def _parse_phrase_candidate(content: str) -> PhraseCandidate:
        """Parse a single <phrase_candidate> block.

        Args:
            content: Inner XML of a <phrase_candidate> block.

        Returns:
            PhraseCandidate with parsed fields.
        """
        # Parse should_create
        should_create = True
        create_match = re.search(
            r"<should_create>\s*(true|false)\s*</should_create>",
            content,
            re.IGNORECASE,
        )
        if create_match:
            should_create = create_match.group(1).lower() == "true"

        # Parse description
        description = ""
        desc_match = re.search(
            r"<description>(.*?)</description>", content, re.DOTALL
        )
        if desc_match:
            description = desc_match.group(1).strip()

        # Parse label
        label = ""
        label_match = re.search(
            r"<label>(.*?)</label>", content, re.DOTALL
        )
        if label_match:
            label = label_match.group(1).strip()

        # Parse effective_path state IDs
        state_ids = []
        path_match = re.search(
            r"<effective_path>(.*?)</effective_path>", content, re.DOTALL
        )
        if path_match:
            state_pattern = re.compile(r'state_id\s*=\s*"([^"]*)"')
            for m in state_pattern.finditer(path_match.group(1)):
                state_ids.append(m.group(1))

        # Parse reason
        reason = ""
        reason_match = re.search(
            r"<reason>(.*?)</reason>", content, re.DOTALL
        )
        if reason_match:
            reason = reason_match.group(1).strip()

        return PhraseCandidate(
            should_create=should_create,
            description=description,
            label=label,
            effective_state_ids=state_ids,
            reason=reason,
        )

    def _create_phrase(self, candidate: PhraseCandidate) -> Optional[str]:
        """Create a CognitivePhrase from a phrase candidate.

        This is code logic (not LLM), responsible for:
        1. Resolving State objects from effective_state_ids
        2. Finding Actions between consecutive States
        3. Getting IntentSequences for each State
        4. Building ExecutionSteps
        5. Generating embedding
        6. Saving to Memory

        Args:
            candidate: Parsed PhraseCandidate from LLM.

        Returns:
            Phrase ID if created, None on failure.
        """
        if len(candidate.effective_state_ids) < 2:
            logger.warning(
                "[LearnerAgent] Cannot create phrase: fewer than 2 states"
            )
            return None

        # 1. Resolve States
        states = []
        for state_id in candidate.effective_state_ids:
            state = self._memory.state_manager.get_state(state_id)
            if state:
                states.append(state)
            else:
                logger.warning(
                    f"[LearnerAgent] State {state_id} not found in memory, "
                    f"skipping phrase creation"
                )
                return None

        # 2. Find Actions between consecutive States
        actions = []
        for i in range(len(states) - 1):
            action = self._memory.get_action(states[i].id, states[i + 1].id)
            if action:
                actions.append(action)
            else:
                logger.warning(
                    f"[LearnerAgent] No action found between "
                    f"{states[i].id} -> {states[i+1].id}, "
                    f"skipping phrase creation"
                )
                return None

        # 3. Get IntentSequences for each State
        all_sequences = []
        seq_by_state: Dict[str, list] = {}
        if self._memory.intent_sequence_manager:
            for state in states:
                seqs = self._memory.intent_sequence_manager.list_by_state(state.id)
                seq_by_state[state.id] = seqs
                all_sequences.extend(seqs)

        # 4. Build ExecutionSteps
        execution_plan = self._build_execution_plan(states, actions, seq_by_state)

        # 5. Build state_path and action_path
        state_path = [s.id for s in states]
        action_path = [a.type if a.type else "navigate" for a in actions]

        # 6. Calculate timestamps
        current_time = int(time.time() * 1000)
        start_timestamp = getattr(states[0], "timestamp", current_time)
        end_timestamp = getattr(states[-1], "end_timestamp", None) or getattr(
            states[-1], "timestamp", current_time
        )
        duration = end_timestamp - start_timestamp if end_timestamp > start_timestamp else 0

        # 7. Create CognitivePhrase
        phrase = CognitivePhrase(
            label=candidate.label,
            description=candidate.description,
            semantic={},
            session_id=f"learner_{current_time}",
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            duration=duration,
            state_path=state_path,
            action_path=action_path,
            execution_plan=execution_plan,
            created_at=current_time,
        )

        # 8. Generate embedding
        embedding_text = candidate.description[:280] if candidate.description else (candidate.label[:120] if candidate.label else "")
        if self._embedding_service and embedding_text:
            try:
                embedding = self._embedding_service.embed(embedding_text)
                if embedding:
                    phrase.embedding_vector = embedding
            except Exception as e:
                logger.warning(f"[LearnerAgent] Failed to generate phrase embedding: {e}")

        # 9. Save to Memory
        try:
            success = self._memory.create_phrase(phrase)
            if success:
                logger.info(
                    f"[LearnerAgent] Created CognitivePhrase: id={phrase.id}, "
                    f"label={phrase.label}, states={len(states)}"
                )
                return phrase.id
            else:
                logger.warning("[LearnerAgent] create_phrase returned False")
                return None
        except Exception as e:
            logger.error(f"[LearnerAgent] Failed to save phrase: {e}")
            return None

    @staticmethod
    def _build_execution_plan(
        states: list,
        actions: list,
        seq_by_state: Dict[str, list],
    ) -> List[ExecutionStep]:
        """Build ExecutionSteps from resolved States, Actions, and sequences.

        Mirrors workflow_processor._build_execution_plan logic but uses
        pre-resolved data instead of querying memory.

        Args:
            states: Ordered list of State objects.
            actions: Actions between consecutive states.
            seq_by_state: state_id -> List[IntentSequence] mapping.

        Returns:
            List of ExecutionStep objects.
        """
        # Build action lookup: source_state_id -> Action
        action_by_source: Dict[str, Any] = {}
        for action in actions:
            action_by_source[action.source] = action

        execution_plan = []
        for i, state in enumerate(states):
            sequences = seq_by_state.get(state.id, [])

            # Separate in-page vs navigation sequences
            in_page_sequence_ids = []
            navigation_sequence_id = None
            for seq in sequences:
                causes_nav = getattr(seq, "causes_navigation", False)
                if causes_nav:
                    navigation_sequence_id = seq.id
                else:
                    in_page_sequence_ids.append(seq.id)

            # Get navigation action (if not last state)
            navigation_action_id = None
            if i < len(states) - 1:
                action = action_by_source.get(state.id)
                if action:
                    navigation_action_id = action.id

            step = ExecutionStep(
                index=i + 1,
                state_id=state.id,
                in_page_sequence_ids=in_page_sequence_ids,
                navigation_action_id=navigation_action_id,
                navigation_sequence_id=navigation_sequence_id,
            )
            execution_plan.append(step)

        return execution_plan


class _DummyTaskState:
    """Minimal TaskState for LearnerAgent when no real TaskState is provided."""

    def __init__(self):
        self.task_id = "learner"

    async def put_event(self, event):
        pass
