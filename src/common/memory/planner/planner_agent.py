"""Planner Agent - Memory-Powered task analysis via LLM Agent loop.

Uses AMIAgent's tool-calling loop with 3 Memory tools to:
1. recall_phrases — Recall relevant CognitivePhrases (L1)
2. search_states — Search individual page nodes
3. explore_graph — BFS path finding for uncovered parts (L2)

4-step workflow: Recall → Judge Coverage → Graph Exploration → Output <memory_plan>

The PlannerAgent only handles Memory-layer concerns.
Subtask decomposition is done by AMITaskPlanner.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .models import PlanStep, MemoryPlan, PlanResult
from .prompts import PLANNER_SYSTEM_PROMPT
from .tools import PlannerTools

logger = logging.getLogger(__name__)


class PlannerAgent:
    """Memory-Powered Planner Agent.

    Based on AMIAgent's Agent Loop, registered with Memory tools.
    Located in Memory module, directly accesses Memory interfaces.
    Called by AMITaskPlanner via Cloud Backend API.

    Outputs MemoryPlan (coverage + preferences + uncovered),
    NOT subtasks with agent_type/depends_on.
    """

    def __init__(
        self,
        memory,
        llm_provider,
        embedding_service,
        task_state=None,
        public_memory=None,
    ):
        """Initialize PlannerAgent.

        Args:
            memory: WorkflowMemory instance (private user memory).
            llm_provider: AnthropicProvider for LLM calls.
            embedding_service: EmbeddingService for query encoding.
            task_state: TaskState for SSE events (optional, uses DummyTaskState if None).
            public_memory: Optional WorkflowMemory instance (public/shared memory).
        """
        from src.common.agent.ami_agent import (
            AMIAgent,
        )
        from src.common.agent.ami_tool import (
            AMITool,
        )

        # Create PlannerTools instance
        self._tools_impl = PlannerTools(memory, embedding_service, public_memory)

        # Wrap as AMITool list
        tools = [
            AMITool(self._tools_impl.recall_phrases),
            AMITool(self._tools_impl.search_states),
            AMITool(self._tools_impl.explore_graph),
        ]

        # Use DummyTaskState if none provided
        if task_state is None:
            task_state = _DummyTaskState()

        # Create internal AMIAgent
        self._agent = AMIAgent(
            task_state=task_state,
            agent_name="PlannerAgent",
            provider=llm_provider,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            tools=tools,
            max_iterations=8,
        )

    async def plan(self, task: str) -> PlanResult:
        """Create a memory-powered analysis for the given task.

        Agent Loop flow:
        1. astep(task) starts the loop
        2. LLM sees system prompt + user task
        3. LLM calls recall_phrases → analyzes results
        4. LLM decides whether to explore graph further
        5. LLM outputs <memory_plan> XML
        6. stop_reason = "end_turn" → loop ends
        7. Parse final output into PlanResult with MemoryPlan

        Args:
            task: User's task description.

        Returns:
            PlanResult with MemoryPlan (coverage + preferences + uncovered).
        """
        self._agent.reset()
        response = await self._agent.astep(task)
        return self._parse_plan_output(response.text)

    def _parse_plan_output(self, text: str) -> PlanResult:
        """Parse the LLM's <memory_plan> XML output into PlanResult.

        Args:
            text: LLM's final text output.

        Returns:
            PlanResult with MemoryPlan.
        """
        # Extract <memory_plan>...</memory_plan> content
        plan_match = re.search(r"<memory_plan>(.*?)</memory_plan>", text, re.DOTALL)
        if not plan_match:
            logger.warning(
                "PlannerAgent output contained no <memory_plan>. "
                "Treating full output as a single uncovered step."
            )
            fallback_plan = MemoryPlan(steps=[
                PlanStep(index=1, content=text.strip()[:2000], source="none"),
            ])
            return PlanResult(
                memory_plan=fallback_plan,
                debug_trace=self._build_debug_trace(fallback_plan),
            )

        plan_content = plan_match.group(1)

        # Parse <steps> section
        plan_steps = self._parse_steps(plan_content)

        # Parse <preferences> section
        preferences = []
        prefs_match = re.search(
            r"<preferences>(.*?)</preferences>", plan_content, re.DOTALL
        )
        if prefs_match:
            prefs_text = prefs_match.group(1).strip()
            for line in prefs_text.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    preferences.append(line[2:].strip())
                elif line:
                    preferences.append(line)

        memory_plan = MemoryPlan(
            steps=plan_steps,
            preferences=preferences,
        )

        # Fill workflow_guide for steps with Memory backing
        self._fill_workflow_guides(memory_plan.steps)

        return PlanResult(
            memory_plan=memory_plan,
            debug_trace=self._build_debug_trace(memory_plan),
        )

    def _parse_steps(self, plan_content: str) -> List[PlanStep]:
        """Parse <steps>/<step> elements into PlanStep list."""
        items = []

        # Extract <steps>...</steps> block
        steps_match = re.search(
            r"<steps>(.*?)</steps>", plan_content, re.DOTALL
        )
        if not steps_match:
            return items

        steps_content = steps_match.group(1)

        # Find all <step ...>...</step> elements
        step_pattern = re.compile(
            r'<step\s*([^>]*)>(.*?)</step>',
            re.DOTALL,
        )

        for match in step_pattern.finditer(steps_content):
            attrs_str = match.group(1)
            content = match.group(2).strip()

            source = _extract_attr(attrs_str, "source") or "none"
            phrase_id = _extract_attr(attrs_str, "phrase_id")
            index_str = _extract_attr(attrs_str, "index") or str(len(items) + 1)
            state_ids_str = _extract_attr(attrs_str, "state_ids") or ""
            state_ids = [
                s.strip() for s in state_ids_str.split(",") if s.strip()
            ]

            try:
                index = int(index_str)
            except ValueError:
                index = len(items) + 1

            items.append(PlanStep(
                index=index,
                content=content,
                source=source,
                phrase_id=phrase_id,
                state_ids=state_ids,
                workflow_guide="",  # Filled by _fill_workflow_guides
            ))

        return items

    def _fill_workflow_guides(self, plan_steps: List[PlanStep]) -> None:
        """Fill workflow_guide for plan steps with Memory backing.

        Handles both sources:
        - source="phrase": extracts from recall_phrases tool results (EnrichedPhrase JSON)
        - source="graph": extracts from explore_graph tool results (paths with steps)
        - source="none": no Memory, leave workflow_guide empty
        """
        tool_data = self._extract_tool_result_data()
        enriched_phrases = tool_data["phrases"]
        graph_paths = tool_data["graph_paths"]

        for step in plan_steps:
            if step.source == "phrase" and step.phrase_id:
                step.workflow_guide = self._build_phrase_guide(
                    step, enriched_phrases
                )
            elif step.source == "graph" and step.state_ids:
                step.workflow_guide = self._build_graph_guide(
                    step, graph_paths
                )

    @staticmethod
    def _build_phrase_guide(
        plan_step: PlanStep, enriched_phrases: Dict
    ) -> str:
        """Build workflow_guide for a phrase-based plan step.

        Only includes phrase steps whose state_id is in plan_step.state_ids,
        avoiding duplication of the entire workflow into every plan step.
        Falls back to all phrase steps if no state_ids filter is provided.
        """
        phrase_data = enriched_phrases.get(plan_step.phrase_id)
        if not phrase_data:
            return ""

        all_steps = phrase_data.get("steps", [])

        # Filter to only the steps relevant to this plan step
        if plan_step.state_ids:
            state_id_set = set(plan_step.state_ids)
            filtered_steps = [
                s for s in all_steps
                if s.get("state", {}).get("id") in state_id_set
                or s.get("state_id") in state_id_set
            ]
            # Fall back to all steps if filter matched nothing
            if not filtered_steps:
                filtered_steps = all_steps
        else:
            filtered_steps = all_steps

        guide_lines = []
        for phrase_step in filtered_steps:
            state = phrase_step.get("state", {})
            guide_lines.append(
                f"Step {phrase_step['index']}: {state.get('description', '')}"
            )
            if state.get("page_url"):
                guide_lines.append(f"  URL: {state['page_url']}")

            # In-page operations
            for op in phrase_step.get("in_page_operations", []):
                if op.get("description"):
                    guide_lines.append(f"  Operation: {op['description']}")
                for intent in op.get("intents", [])[:10]:
                    intent_type = intent.get("type", "")
                    intent_text = intent.get("text", "")
                    if intent_type:
                        line = f"    - {intent_type}"
                        if intent_text:
                            line += f": {intent_text[:100]}"
                        guide_lines.append(line)

            # Navigation
            nav = phrase_step.get("navigation")
            if nav:
                desc = nav.get("description", "next")
                trigger = nav.get("trigger", {})
                if trigger and trigger.get("text"):
                    desc += f' (click "{trigger["text"]}")'
                guide_lines.append(f"  -> {desc}")

            # Navigation sequence (detailed intent-level navigation steps)
            nav_seq = phrase_step.get("navigation_sequence")
            if nav_seq:
                if nav_seq.get("description"):
                    guide_lines.append(
                        f"  Navigation: {nav_seq['description']}"
                    )
                for intent in nav_seq.get("intents", [])[:10]:
                    intent_type = intent.get("type", "")
                    intent_text = intent.get("text", "")
                    if intent_type:
                        line = f"    - {intent_type}"
                        if intent_text:
                            line += f": {intent_text[:100]}"
                        guide_lines.append(line)

        return "\n".join(guide_lines)

    @staticmethod
    def _build_graph_guide(
        plan_step: PlanStep,
        graph_paths: List[Dict],
    ) -> str:
        """Build workflow_guide for a graph-based plan step.

        Finds the matching explore_graph path by checking if the path's
        state IDs overlap with the plan_step's state_ids, then formats
        only the matching steps into a navigation guide.
        """
        # Find the best matching path from explore_graph results
        item_state_set = set(plan_step.state_ids)
        best_path = None
        best_overlap = 0
        for path in graph_paths:
            path_state_ids = {
                s.get("state_id") for s in path.get("steps", [])
            }
            overlap = len(item_state_set & path_state_ids)
            if overlap > best_overlap:
                best_overlap = overlap
                best_path = path

        if not best_path:
            return ""

        # Filter to only steps matching this plan step's state_ids
        all_path_steps = best_path.get("steps", [])
        if item_state_set:
            filtered_steps = [
                s for s in all_path_steps
                if s.get("state_id") in item_state_set
            ]
            if not filtered_steps:
                filtered_steps = all_path_steps
        else:
            filtered_steps = all_path_steps

        guide_lines = ["**Navigation Path (from graph exploration)**:\n"]

        for i, path_step in enumerate(filtered_steps, 1):
            desc = path_step.get("description") or path_step.get("page_title") or path_step.get("state_id", "")
            guide_lines.append(f"Step {i}: {desc}")
            if path_step.get("page_url"):
                guide_lines.append(f"  URL: {path_step['page_url']}")

            # Operations (capabilities) included in explore_graph results
            for op in path_step.get("operations", []):
                if op.get("description"):
                    guide_lines.append(f"  Operation: {op['description']}")
                for intent_desc in op.get("intents", [])[:5]:
                    guide_lines.append(f"    - {intent_desc}")

            # Navigation action to next step
            next_action = path_step.get("next_action")
            if next_action:
                action_desc = next_action.get("description") or "Navigate"
                trigger = next_action.get("trigger")
                if isinstance(trigger, dict) and trigger.get("text"):
                    action_desc += f' (click "{trigger["text"]}")'
                guide_lines.append(f"  -> {action_desc}")

        if len(guide_lines) <= 1:
            return ""
        return "\n".join(guide_lines)

    def _build_debug_trace(self, memory_plan: MemoryPlan) -> Dict[str, Any]:
        """Build side-channel debug trace for PlannerAgent reporting."""
        selected_phrase_ids = sorted({
            step.phrase_id
            for step in (memory_plan.steps or [])
            if step.source == "phrase" and step.phrase_id
        })

        recall_calls = self._extract_recall_tool_calls()
        recall_debug_items: List[Dict[str, Any]] = []

        for call_index, call in enumerate(recall_calls, start=1):
            query = call.get("query", "")
            top_k = call.get("top_k", 5)
            tool_result_phrases = call.get("phrases", [])

            scored_candidates = []
            if query:
                scored_candidates = self._tools_impl.get_phrase_recall_candidates(
                    query=query,
                    top_k=top_k,
                )

            scored_by_phrase_id: Dict[str, Dict[str, Any]] = {}
            for candidate in scored_candidates:
                phrase_id = candidate.get("phrase_id")
                if phrase_id:
                    scored_by_phrase_id[phrase_id] = candidate

            merged_phrases: List[Dict[str, Any]] = []
            for result_rank, phrase_data in enumerate(tool_result_phrases, start=1):
                phrase_id = phrase_data.get("id")
                score_item = scored_by_phrase_id.get(phrase_id, {})
                fallback_url, fallback_domain = self._extract_primary_url_domain(
                    phrase_data
                )
                merged_phrases.append({
                    "result_rank": result_rank,
                    "phrase_id": phrase_id,
                    "label": phrase_data.get("label", ""),
                    "description": phrase_data.get("description", ""),
                    "similarity_score": score_item.get("similarity_score"),
                    "candidate_rank": score_item.get("rank"),
                    "memory_source": score_item.get("source", ""),
                    "domain": score_item.get("domain") or fallback_domain,
                    "page_url": score_item.get("page_url") or fallback_url,
                    "selected_in_plan": phrase_id in selected_phrase_ids if phrase_id else False,
                })

            item: Dict[str, Any] = {
                "call_index": call_index,
                "tool_use_id": call.get("tool_use_id"),
                "query": query,
                "top_k": top_k,
                "result_count": len(tool_result_phrases),
                "scored_candidates": scored_candidates,
                "tool_result_phrases": merged_phrases,
            }
            if call.get("parse_error"):
                item["parse_error"] = call["parse_error"]
            recall_debug_items.append(item)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "selected_phrase_ids": selected_phrase_ids,
            "recall_phrases_calls": recall_debug_items,
        }

    def _extract_recall_tool_calls(self) -> List[Dict[str, Any]]:
        """Extract recall_phrases tool calls + their tool_result payloads."""
        ordered_calls: List[Dict[str, Any]] = []
        tool_results: Dict[str, str] = {}

        for msg in self._agent.get_messages():
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "tool_use" and block.get("name") == "recall_phrases":
                    tool_input = block.get("input", {})
                    if not isinstance(tool_input, dict):
                        tool_input = {}
                    query = str(tool_input.get("query", "") or "")
                    raw_top_k = tool_input.get("top_k", 5)
                    try:
                        top_k = int(raw_top_k)
                    except (TypeError, ValueError):
                        top_k = 5
                    ordered_calls.append({
                        "tool_use_id": block.get("id"),
                        "query": query,
                        "top_k": top_k,
                    })
                    continue
                if block_type == "tool_result":
                    tool_use_id = block.get("tool_use_id")
                    block_content = block.get("content", "")
                    if isinstance(tool_use_id, str) and isinstance(block_content, str):
                        tool_results[tool_use_id] = block_content

        extracted_calls: List[Dict[str, Any]] = []
        for call in ordered_calls:
            tool_use_id = call.get("tool_use_id")
            raw_content = tool_results.get(tool_use_id, "")
            phrases, parse_error = self._extract_recall_phrases_from_result(raw_content)
            item = dict(call)
            item["phrases"] = phrases
            if parse_error:
                item["parse_error"] = parse_error
            extracted_calls.append(item)
        return extracted_calls

    @staticmethod
    def _extract_recall_phrases_from_result(
        raw_content: str,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Parse recall_phrases tool_result content."""
        if not raw_content:
            return [], ""
        try:
            data = json.loads(raw_content)
        except (json.JSONDecodeError, TypeError):
            return [], "tool_result is not valid JSON (possibly truncated)"

        phrases = data.get("phrases", [])
        if not isinstance(phrases, list):
            return [], "tool_result JSON missing list field: phrases"

        normalized: List[Dict[str, Any]] = []
        for phrase in phrases:
            if isinstance(phrase, dict):
                normalized.append(phrase)
        return normalized, ""

    @staticmethod
    def _extract_primary_url_domain(phrase_data: Dict[str, Any]) -> Tuple[str, str]:
        """Extract first URL/domain from EnrichedPhrase dict."""
        steps = phrase_data.get("steps", [])
        if not isinstance(steps, list):
            return "", ""

        for step in steps:
            if not isinstance(step, dict):
                continue
            state = step.get("state", {})
            if not isinstance(state, dict):
                continue
            page_url = state.get("page_url", "") or ""
            if not page_url:
                continue
            domain = state.get("domain") or PlannerAgent._derive_domain(page_url)
            return page_url, domain
        return "", ""

    @staticmethod
    def _derive_domain(page_url: str) -> str:
        if not page_url:
            return ""
        try:
            return urlparse(page_url).netloc
        except Exception:
            return ""

    def _extract_tool_result_data(self) -> Dict[str, Any]:
        """Extract all useful data from the agent's tool result history.

        Scans conversation messages for tool results from all tools
        and indexes them for _fill_workflow_guides to use.

        Returns:
            Dict with keys:
            - "phrases": {phrase_id: phrase_dict} from recall_phrases
            - "states": {state_id: state_dict} from search_states
            - "graph_paths": List[Dict] from explore_graph (each has steps with capabilities)
        """
        phrases: Dict[str, Dict] = {}
        states: Dict[str, Dict] = {}
        graph_paths: List[Dict] = []

        for msg in self._agent.get_messages():
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue
                block_content = block.get("content", "")
                if not isinstance(block_content, str) or not block_content:
                    continue
                try:
                    data = json.loads(block_content)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "[PlannerAgent] Failed to parse tool result JSON "
                        "(%d chars, possibly truncated)",
                        len(block_content),
                    )
                    continue

                # recall_phrases results: {"phrases": [...]}
                for phrase_data in data.get("phrases", []):
                    phrase_id = phrase_data.get("id")
                    if phrase_id:
                        phrases[phrase_id] = phrase_data

                # search_states results: {"states": [...]}
                for state_data in data.get("states", []):
                    sid = state_data.get("id")
                    if sid:
                        states[sid] = state_data

                # explore_graph results: {"paths": [...]}
                for path_data in data.get("paths", []):
                    graph_paths.append(path_data)
                    # Also index states from path steps
                    for step in path_data.get("steps", []):
                        sid = step.get("state_id")
                        if sid:
                            states[sid] = step

        return {
            "phrases": phrases,
            "states": states,
            "graph_paths": graph_paths,
        }


def _extract_attr(attrs_str: str, attr_name: str) -> Optional[str]:
    """Extract an attribute value from an XML-like attribute string."""
    # Try double quotes
    match = re.search(rf'{attr_name}\s*=\s*"([^"]*)"', attrs_str)
    if match:
        return match.group(1)
    # Try single quotes
    match = re.search(rf"{attr_name}\s*=\s*'([^']*)'", attrs_str)
    if match:
        return match.group(1)
    # Try no quotes (for simple values)
    match = re.search(rf'{attr_name}\s*=\s*(\S+)', attrs_str)
    if match:
        return match.group(1)
    return None


class _DummyTaskState:
    """Minimal TaskState for PlannerAgent when no real TaskState is provided."""

    def __init__(self):
        self.task_id = "planner"

    async def put_event(self, event):
        pass
