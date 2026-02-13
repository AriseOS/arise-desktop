"""Reasoner - Main entry point for workflow retrieval.

The Reasoner is responsible for orchestrating the entire retrieval process:
1. Check cognitive_phrases for direct/combinable matches using LLM
2. If no match, decompose target into TaskDAG
3. Execute tasks in topological order (retrieval tasks)
4. For each retrieval task:
   a. Use embedding to find states in memory
   b. Use LLM to check if state satisfies target
   c. If not, explore neighbors (states + actions) up to max depth
   d. Use LLM to evaluate if satisfied
5. Convert results to workflow JSON
"""

import asyncio
from difflib import SequenceMatcher
import logging
import json
import re
import uuid
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

from src.common.memory.memory.memory import Memory
from src.common.memory.ontology.action import Action
from src.common.memory.ontology.domain import normalize_domain_url
from src.common.memory.ontology.intent_sequence import IntentSequence
from src.common.memory.ontology.query_result import QueryResult, SubTaskResult
from src.common.memory.ontology.state import State
from src.common.memory.reasoner.cognitive_phrase_checker import CognitivePhraseChecker
from src.common.memory.reasoner.prompts.path_based_decomposition_prompt import (
    PathBasedDecompositionPrompt,
    PathDecompositionInput,
)
from src.common.memory.reasoner.prompts.path_planning_prompt import (
    PATH_PLANNING_SYSTEM_PROMPT,
    build_path_planning_replan_user_prompt,
    build_path_planning_user_prompt,
)
from src.common.memory.reasoner.prompts.task_decomposition_prompt import (
    TaskDecompositionInput,
    TaskDecompositionPrompt,
    ToolInfo,
)
from src.common.memory.reasoner.retrieval_result import WorkflowResult
from src.common.memory.reasoner.task_dag import TaskDAG
from src.common.memory.reasoner.tools.retrieval_tool import RetrievalTool
from src.common.memory.reasoner.tools.task_tool import TaskTool
from src.common.memory.reasoner.workflow_converter import WorkflowConverter
from src.common.memory.services.embedding_service import EmbeddingService


class Reasoner:
    """Main reasoner for workflow retrieval.

    The Reasoner orchestrates the entire retrieval process:
    1. Check cognitive_phrases
    2. Decompose into TaskDAG if needed
    3. Execute tasks in topological order using registered tools
    4. Convert results to workflow
    """

    # Default similarity thresholds
    DEFAULT_STATE_RESOLUTION_THRESHOLD = 0.5
    DEFAULT_PATH_FINDING_THRESHOLD = 0.3
    DEFAULT_PATH_PLANNING_TOP_K = 20
    DEFAULT_PATH_PLANNING_MIN_SCORE = 0.15
    DEFAULT_PATH_PLANNING_MAX_STATES = 20
    DEFAULT_PATH_PLANNING_MAX_ACTIONS = 50
    DEFAULT_PATH_PLANNING_DOMAIN_PREFILTER_ENABLED = True
    DEFAULT_PATH_PLANNING_DOMAIN_MATCH_THRESHOLD = 0.45
    DEFAULT_PATH_PLANNING_DOMAIN_MIN_CANDIDATES = 3
    DEFAULT_PATH_PLANNING_DOMAIN_FALLBACK_TO_FULL_GRAPH = True

    def __init__(
        self,
        memory: Memory,
        llm_provider: Optional[Any] = None,
        embedding_service=None,
        max_depth: int = 3,
        similarity_thresholds: Optional[Dict[str, float]] = None,
        public_memory: Optional[Memory] = None,
        path_planning_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize Reasoner.

        Args:
            memory: Memory instance (private).
            llm_provider: LLM provider (AnthropicProvider) for various LLM operations.
            embedding_service: Embedding service for vector search.
            max_depth: Maximum neighbor exploration depth.
            similarity_thresholds: Optional dict with threshold values:
                - state_resolution: Minimum score for state resolution (default 0.5)
                - path_finding: Minimum score for path finding (default 0.3)
            public_memory: Optional public Memory instance for merged queries.
            path_planning_config: Optional dict for L2 planning:
                - candidate_top_k: Candidate states recalled by embedding (default 20)
                - min_score: Minimum embedding score for candidates (default 0.15)
                - max_states: Maximum states sent to LLM (default 20)
                - max_actions: Maximum actions sent to LLM (default 50)
                - domain_prefilter_enabled: Enable domain fuzzy prefilter (default True)
                - domain_match_threshold: Minimum score to accept matched domain (default 0.45)
                - domain_min_candidates: Min candidates after domain filter (default 3)
                - domain_fallback_to_full_graph: Retry once with full candidates (default True)
        """
        self.memory = memory
        self.public_memory = public_memory
        self.llm_provider = llm_provider
        self.embedding_service = embedding_service
        self.max_depth = max_depth

        # Similarity thresholds from config
        thresholds = similarity_thresholds or {}
        self.state_resolution_threshold = thresholds.get(
            "state_resolution", self.DEFAULT_STATE_RESOLUTION_THRESHOLD
        )
        self.path_finding_threshold = thresholds.get(
            "path_finding", self.DEFAULT_PATH_FINDING_THRESHOLD
        )
        planning_config = path_planning_config or {}
        self.path_planning_top_k = max(
            1, int(planning_config.get("candidate_top_k", self.DEFAULT_PATH_PLANNING_TOP_K))
        )
        self.path_planning_min_score = float(
            planning_config.get("min_score", self.DEFAULT_PATH_PLANNING_MIN_SCORE)
        )
        self.path_planning_max_states = max(
            1, int(planning_config.get("max_states", self.DEFAULT_PATH_PLANNING_MAX_STATES))
        )
        self.path_planning_max_actions = max(
            1, int(planning_config.get("max_actions", self.DEFAULT_PATH_PLANNING_MAX_ACTIONS))
        )
        self.path_planning_domain_prefilter_enabled = bool(
            planning_config.get(
                "domain_prefilter_enabled",
                self.DEFAULT_PATH_PLANNING_DOMAIN_PREFILTER_ENABLED,
            )
        )
        self.path_planning_domain_match_threshold = float(
            planning_config.get(
                "domain_match_threshold",
                self.DEFAULT_PATH_PLANNING_DOMAIN_MATCH_THRESHOLD,
            )
        )
        self.path_planning_domain_min_candidates = max(
            1,
            int(
                planning_config.get(
                    "domain_min_candidates",
                    self.DEFAULT_PATH_PLANNING_DOMAIN_MIN_CANDIDATES,
                )
            ),
        )
        self.path_planning_domain_fallback_to_full_graph = bool(
            planning_config.get(
                "domain_fallback_to_full_graph",
                self.DEFAULT_PATH_PLANNING_DOMAIN_FALLBACK_TO_FULL_GRAPH,
            )
        )

        # Initialize components
        self.phrase_checker = CognitivePhraseChecker(memory, llm_provider)
        self.workflow_converter = WorkflowConverter()
        self.decomposition_prompt = TaskDecompositionPrompt()
        self.path_decomposition_prompt = PathBasedDecompositionPrompt()

        # Initialize tool registry
        self.tools: Dict[str, TaskTool] = {}
        self._register_tools()

    def _register_tools(self):
        """Register available tools."""
        # Register retrieval tool
        retrieval_tool = RetrievalTool(
            self.memory,
            self.llm_provider,
            self.embedding_service,
            self.max_depth,
        )
        self.tools[retrieval_tool.name] = retrieval_tool

    def _gather_state_sequences(self, state_ids: list) -> Dict[str, list]:
        """Gather IntentSequences for each state from memory.

        Args:
            state_ids: List of state IDs to gather sequences for.

        Returns:
            Mapping of state_id -> List[IntentSequence].
        """
        result = {}
        if not self.memory.intent_sequence_manager:
            return result
        for state_id in state_ids:
            try:
                sequences = self.memory.intent_sequence_manager.list_by_state(state_id)
                if sequences:
                    result[state_id] = sequences
            except Exception:
                continue
        return result

    @staticmethod
    def _safe_text(value: Any) -> str:
        """Normalize any value to a stripped string."""
        return str(value or "").strip()

    @classmethod
    def _normalize_domain_match_text(cls, value: Any) -> str:
        """Normalize free text for lightweight fuzzy domain matching."""
        text = cls._safe_text(value).lower()
        if not text:
            return ""
        text = re.sub(r"[^\w\u4e00-\u9fff\.\-]+", " ", text)
        return " ".join(text.split())

    @classmethod
    def _extract_domain_from_state(cls, state: State) -> str:
        """Extract normalized domain key from a state."""
        state_domain = cls._safe_text(state.domain)
        if state_domain:
            return cls._safe_text(normalize_domain_url(state_domain, "website"))

        page_url = cls._safe_text(state.page_url)
        if not page_url:
            return ""

        try:
            parsed = urlparse(page_url)
            host = cls._safe_text(parsed.hostname or parsed.netloc)
            if not host and parsed.path:
                host = cls._safe_text(parsed.path.split("/")[0])
            if host:
                return cls._safe_text(normalize_domain_url(host, "website"))
        except Exception:
            pass

        return cls._safe_text(normalize_domain_url(page_url, "website"))

    @classmethod
    def _build_domain_terms(cls, domain_url: str, domain_name: str) -> List[str]:
        """Build a compact list of terms used for fuzzy domain scoring."""
        terms: List[str] = []
        url_norm = cls._normalize_domain_match_text(domain_url)
        name_norm = cls._normalize_domain_match_text(domain_name)

        if url_norm:
            terms.append(url_norm)
            host = url_norm.split(":")[0]
            if host.startswith("www."):
                host = host[4:]
            if host:
                terms.append(host)
                primary = host.split(".")[0]
                if primary and len(primary) >= 2:
                    terms.append(primary)

        if name_norm:
            terms.append(name_norm)

        deduped: List[str] = []
        seen = set()
        for term in terms:
            if term and term not in seen:
                seen.add(term)
                deduped.append(term)
        return deduped

    @classmethod
    def _score_task_domain_match(
        cls,
        task_text: str,
        domain_url: str,
        domain_name: str,
    ) -> float:
        """Score domain relevance using lightweight string similarity."""
        task_norm = cls._normalize_domain_match_text(task_text)
        if not task_norm:
            return 0.0

        terms = cls._build_domain_terms(domain_url, domain_name)
        if not terms:
            return 0.0

        contains_score = 0.0
        for term in terms:
            if len(term) < 2:
                continue
            if term in task_norm:
                contains_score = max(contains_score, 1.0)

        ratio_score = 0.0
        for term in terms:
            if len(term) < 2:
                continue
            ratio_score = max(
                ratio_score,
                SequenceMatcher(None, task_norm, term).ratio(),
            )

        return max(contains_score, ratio_score)

    def _select_best_domain_for_task(
        self,
        target: str,
        memory: Memory,
    ) -> Tuple[Optional[str], float, List[Dict[str, Any]]]:
        """Pick the best matched domain from memory for the given task."""
        try:
            domains = memory.domain_manager.list_domains(limit=None)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(f"[L2] Failed to list domains for prefilter: {exc}")
            return None, 0.0, []

        if not domains:
            return None, 0.0, []

        scored_domains: List[Dict[str, Any]] = []
        for domain in domains:
            domain_url = self._safe_text(getattr(domain, "domain_url", ""))
            domain_name = self._safe_text(getattr(domain, "domain_name", ""))
            domain_type = self._safe_text(
                getattr(domain, "domain_type", "website")
            ) or "website"
            normalized_url = self._safe_text(
                normalize_domain_url(domain_url, domain_type)
            ) if domain_url else ""
            if not normalized_url and not domain_name:
                continue

            score = self._score_task_domain_match(
                task_text=target,
                domain_url=normalized_url,
                domain_name=domain_name,
            )
            scored_domains.append({
                "domain": normalized_url or domain_url,
                "domain_name": domain_name,
                "score": float(score),
            })

        if not scored_domains:
            return None, 0.0, []

        scored_domains.sort(key=lambda item: item["score"], reverse=True)
        best = scored_domains[0]
        debug_top = scored_domains[:5]
        best_domain = self._safe_text(best.get("domain")) or None
        best_score = float(best.get("score", 0.0))
        return best_domain, best_score, debug_top

    def _apply_domain_prefilter(
        self,
        target: str,
        scored_candidates: List[Tuple[State, float]],
        memory: Memory,
    ) -> Tuple[List[Tuple[State, float]], Optional[str], Dict[str, Any]]:
        """Apply optional domain prefilter to recalled candidates."""
        debug_info: Dict[str, Any] = {
            "enabled": self.path_planning_domain_prefilter_enabled,
            "threshold": float(self.path_planning_domain_match_threshold),
            "min_candidates": int(self.path_planning_domain_min_candidates),
            "candidate_count_before": len(scored_candidates),
            "applied": False,
            "selected_domain": None,
            "selected_score": 0.0,
            "reason": "disabled",
            "top_domain_matches": [],
        }

        if (
            not self.path_planning_domain_prefilter_enabled
            or not scored_candidates
        ):
            if scored_candidates:
                debug_info["reason"] = "disabled"
            else:
                debug_info["reason"] = "empty_candidates"
            return scored_candidates, None, debug_info

        matched_domain, matched_score, top_matches = self._select_best_domain_for_task(
            target=target,
            memory=memory,
        )
        debug_info["top_domain_matches"] = top_matches
        debug_info["selected_domain"] = matched_domain
        debug_info["selected_score"] = float(matched_score)

        if not matched_domain:
            debug_info["reason"] = "no_domain_found"
            return scored_candidates, None, debug_info

        if matched_score < self.path_planning_domain_match_threshold:
            debug_info["reason"] = "below_threshold"
            return scored_candidates, None, debug_info

        filtered_candidates = [
            (state, score)
            for state, score in scored_candidates
            if self._extract_domain_from_state(state) == matched_domain
        ]
        debug_info["candidate_count_after"] = len(filtered_candidates)

        if len(filtered_candidates) < self.path_planning_domain_min_candidates:
            debug_info["reason"] = "filtered_too_small"
            return scored_candidates, None, debug_info

        debug_info["applied"] = True
        debug_info["reason"] = "matched"
        return filtered_candidates, matched_domain, debug_info

    @classmethod
    def _get_state_reasoning_text(cls, state: State) -> str:
        """Get stable state text for reasoning prompts.

        Preference:
        1. attributes.semantic_v1.retrieval_text
        2. attributes.semantic_v1.description
        3. state.description
        4. page_title
        5. page_url
        """
        attrs = state.attributes if isinstance(state.attributes, dict) else {}
        semantic = attrs.get("semantic_v1")
        if isinstance(semantic, dict):
            retrieval_text = cls._safe_text(semantic.get("retrieval_text"))
            if retrieval_text:
                return retrieval_text
            semantic_desc = cls._safe_text(semantic.get("description"))
            if semantic_desc:
                return semantic_desc

        description = cls._safe_text(state.description)
        if description:
            return description

        page_title = cls._safe_text(state.page_title)
        if page_title:
            return page_title

        return cls._safe_text(state.page_url)

    def register_tool(self, tool: TaskTool):
        """Register a custom tool.

        Args:
            tool: TaskTool instance to register.
        """
        self.tools[tool.name] = tool

    def get_tool(self, tool_type: str) -> Optional[TaskTool]:
        """Get tool by type.

        Args:
            tool_type: Tool type name.

        Returns:
            TaskTool instance or None if not found.
        """
        return self.tools.get(tool_type)

    def get_by_phrase_id(self, phrase_id: str) -> WorkflowResult:
        """Retrieve workflow by cognitive phrase ID.

        Args:
            phrase_id: Cognitive phrase identifier.

        Returns:
            WorkflowResult with workflow JSON if phrase found.
        """
        # Get the cognitive phrase by ID
        # Note: memory.get_phrase() already calls record_access()
        phrase = self.memory.get_phrase(phrase_id)

        if not phrase:
            return WorkflowResult(
                target=f"phrase_id:{phrase_id}",
                success=False,
                metadata={
                    "method": "phrase_id_retrieval",
                    "error": f"Cognitive phrase '{phrase_id}' not found"
                }
            )

        # Retrieve actual State and Action objects using the paths
        states = []
        for state_id in phrase.state_path:
            state = self.memory.get_state(state_id)
            if state:
                states.append(state)
            else:
                logger.warning(f"State '{state_id}' not found in memory")

        # Retrieve actions based on state transitions
        actions = []
        for i in range(len(phrase.state_path) - 1):
            source_id = phrase.state_path[i]
            target_id = phrase.state_path[i + 1]

            # Try to get the action directly
            found_action = self.memory.get_action(source_id, target_id)

            if found_action:
                actions.append(found_action)
            else:
                logger.warning(f"Action from '{source_id}' to '{target_id}' not found")

        if not states:
            return WorkflowResult(
                target=phrase.description,
                success=False,
                metadata={
                    "method": "phrase_id_retrieval",
                    "phrase_id": phrase_id,
                    "error": "No valid states found for this phrase"
                }
            )

        # Gather IntentSequences for each state
        state_sequences = self._gather_state_sequences([s.id for s in states])

        # Convert to workflow
        workflow = self.workflow_converter.convert(
            phrase.description,
            states,
            actions,
            [phrase],
            state_sequences=state_sequences,
        )

        return WorkflowResult(
            target=phrase.description,
            success=True,
            workflow=workflow,
            states=states,
            actions=actions,
            metadata={
                "method": "phrase_id_retrieval",
                "phrase_id": phrase_id,
                "num_states": len(states),
                "num_actions": len(actions),
                "access_count": phrase.access_count,
                "cognitive_phrases": [phrase],
            }
        )

    async def plan(
        self, target: str,
    ) -> WorkflowResult:
        """Plan and retrieve workflow for target.

        This is the main entry point.

        Args:
            target: Target description (natural language).

        Returns:
            WorkflowResult with workflow JSON if successful.
        """
        # Step 1: Check cognitive phrases
        can_satisfy, phrases, reasoning = await self.phrase_checker.check(target)

        if can_satisfy and phrases:
            # Direct match found - retrieve actual State and Action objects from memory
            # Use ordered dict to preserve order while deduplicating by ID
            states_by_id = {}
            actions_by_key = {}  # key = (source_id, target_id)

            for phrase in phrases:
                # Retrieve states from state_path (deduplicate by ID)
                for state_id in phrase.state_path:
                    if state_id not in states_by_id:
                        state = self.memory.get_state(state_id)
                        if state:
                            states_by_id[state_id] = state
                        else:
                            logger.warning(f"State '{state_id}' not found in phrase {phrase.id}")

                # Retrieve actions based on state transitions (deduplicate by source+target)
                for i in range(len(phrase.state_path) - 1):
                    source_id = phrase.state_path[i]
                    target_id = phrase.state_path[i + 1]
                    action_key = (source_id, target_id)

                    if action_key not in actions_by_key:
                        action = self.memory.get_action(source_id, target_id)
                        if action:
                            actions_by_key[action_key] = action
                        else:
                            logger.warning(f"Action from '{source_id}' to '{target_id}' not found in phrase {phrase.id}")

            # Convert back to lists
            states = list(states_by_id.values())
            actions = list(actions_by_key.values())

            if not states:
                # No valid states found, fall back to task decomposition
                logger.warning("No valid states found in cognitive phrases, falling back to task decomposition")
            else:
                state_sequences = self._gather_state_sequences([s.id for s in states])
                workflow = self.workflow_converter.convert(target, states, actions, phrases, state_sequences=state_sequences)

                return WorkflowResult(
                    target=target,
                    success=True,
                    workflow=workflow,
                    states=states,
                    actions=actions,
                    metadata={
                        "method": "cognitive_phrase_match",
                        "reasoning": reasoning,
                        "num_phrases": len(phrases),
                        "num_states": len(states),
                        "num_actions": len(actions),
                        "cognitive_phrases": phrases,
                    },
                )

        # Step 2: Decompose into TaskDAG
        dag = await self._decompose_target(target)

        # Step 3: Execute tasks in topological order
        topological_order = dag.topological_order()

        if not topological_order:
            return WorkflowResult(
                target=target,
                success=False,
                metadata={"method": "task_dag", "error": "Invalid DAG structure"},
            )

        all_states = []
        all_actions = []
        subtask_results = []

        for task_id in topological_order:
            task_node = dag.nodes[task_id]
            task_target = task_node.get("target", task_node.get("description", ""))
            tool_type = dag.get_tool_type(task_id)
            tool_parameters = dag.get_tool_parameters(task_id)

            # Get tool from registry
            tool = self.get_tool(tool_type)
            if not tool:
                subtask_results.append({
                    "task_id": task_id,
                    "target": task_target,
                    "states": [],
                    "actions": [],
                    "found": False,
                    "error": f"Tool '{tool_type}' not found in registry",
                })
                continue

            # Execute tool (async)
            result = await tool.execute(task_target, tool_parameters)

            if result.success:
                all_states.extend(result.states)
                all_actions.extend(result.actions)
                subtask_results.append({
                    "task_id": task_id,
                    "target": task_target,
                    "states": result.states,
                    "actions": result.actions,
                    "found": True,
                })
            else:
                subtask_results.append({
                    "task_id": task_id,
                    "target": task_target,
                    "states": [],
                    "actions": [],
                    "found": False,
                    "reasoning": result.reasoning,
                })

        # Success if at least some states were found
        has_results = len(all_states) > 0

        # Step 4: Convert to workflow (only if we have states)
        state_sequences = self._gather_state_sequences([s.id for s in all_states]) if has_results else None
        workflow = self.workflow_converter.convert(target, all_states, all_actions, state_sequences=state_sequences) if has_results else None

        return WorkflowResult(
            target=target,
            success=has_results,
            workflow=workflow,
            states=all_states,
            actions=all_actions,
            metadata={
                "method": "task_dag",
                "num_tasks": len(topological_order),
                "num_states": len(all_states),
                "num_actions": len(all_actions),
                "dag_id": dag.dag_id,
                "subtask_results": subtask_results,
            },
        )

    async def _decompose_target(self, target: str) -> TaskDAG:
        """Decompose target into TaskDAG using LLM.

        Args:
            target: Target description.

        Returns:
            TaskDAG with atomic tasks.
        """
        if not self.llm_provider:
            # Fallback: create simple single-task DAG
            return self._create_simple_dag(target)

        try:
            # Build available tools information
            available_tools = []
            for tool_name, tool in self.tools.items():
                tool_info = ToolInfo(
                    name=tool_name,
                    description=tool.description,
                    parameters=tool.get_optional_parameters(),
                )
                available_tools.append(tool_info)

            # Prepare input
            input_data = TaskDecompositionInput(
                target=target, available_tools=available_tools
            )

            # Build prompt
            prompt_text = self.decomposition_prompt.build_prompt(input_data)
            system_prompt = self.decomposition_prompt.get_system_prompt()

            # Call LLM using AnthropicProvider
            response = await self.llm_provider.generate_response(
                system_prompt=system_prompt,
                user_prompt=prompt_text
            )

            # Log raw LLM response for debugging
            logger.debug(
                "TASK DECOMPOSITION - RAW LLM RESPONSE:\n%s",
                response
            )

            # Parse response
            output = self.decomposition_prompt.parse_response(response)

            # Convert to TaskDAG format
            dag_id = str(uuid.uuid4())
            nodes = {}
            for task in output.tasks:
                nodes[task.task_id] = {
                    "target": task.target,
                    "description": task.description,
                    "tool_type": task.tool_type,
                    "tool_parameters": task.tool_parameters,
                    "dependencies": task.dependencies,
                }

            return TaskDAG(
                dag_id=dag_id,
                original_target=target,
                nodes=nodes,
                edges=output.edges,
            )

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error(f"LLM task decomposition failed: {exc}")
            return self._create_simple_dag(target)

    def _create_simple_dag(self, target: str) -> TaskDAG:
        """Create simple single-task DAG as fallback."""
        dag_id = str(uuid.uuid4())
        nodes = {
            "task_1": {
                "target": target,
                "description": target,
                "tool_type": "retrieval",
                "tool_parameters": {},
                "dependencies": [],
            }
        }
        edges = []

        return TaskDAG(
            dag_id=dag_id,
            original_target=target,
            nodes=nodes,
            edges=edges,
        )

    # ============ V2 Query Interface ============

    async def query(
        self,
        target: str,
        current_state: Optional[str] = None,
        start_state: Optional[str] = None,
        end_state: Optional[str] = None,
        as_type: Optional[Literal["task", "navigation", "action"]] = None,
        top_k: int = 10,
    ) -> QueryResult:
        """Unified query entry point with automatic type inference (v2).

        Intelligently routes to the appropriate query type based on parameters:
        - If start_state and end_state provided: navigation query
        - If current_state provided: action query
        - Otherwise: task query

        Args:
            target: Query description or target text.
            current_state: Current state ID for action queries.
            start_state: Start state description/ID for navigation queries.
            end_state: End state description/ID for navigation queries.
            as_type: Explicit query type override.
            top_k: Number of top results to return.

        Returns:
            QueryResult with query type-specific results.
        """
        # Determine query type
        query_type = as_type or self._infer_query_type(
            target, current_state, start_state, end_state
        )

        # Route to appropriate handler
        if query_type == "navigation":
            return await self._query_navigation(
                target=target,
                start_state=start_state or "",
                end_state=end_state or "",
            )
        elif query_type == "action":
            return await self._query_action(
                target=target,
                current_state=current_state or "",
                top_k=top_k,
            )
        else:  # "task"
            return await self._query_task(target=target)

    async def navigate(
        self,
        start_state: str,
        end_state: str,
    ) -> QueryResult:
        """Convenience method for navigation queries (v2).

        Args:
            start_state: Start state description or ID.
            end_state: End state description or ID.

        Returns:
            QueryResult with navigation path.
        """
        return await self._query_navigation(
            target="",
            start_state=start_state,
            end_state=end_state,
        )

    def _infer_query_type(
        self,
        target: str,
        current_state: Optional[str],
        start_state: Optional[str],
        end_state: Optional[str],
    ) -> Literal["task", "navigation", "action"]:
        """Infer query type from parameters.

        Args:
            target: Query target text.
            current_state: Current state ID.
            start_state: Start state description/ID.
            end_state: End state description/ID.

        Returns:
            Inferred query type.
        """
        # Rule 1: Both start and end state -> navigation
        if start_state and end_state:
            return "navigation"

        # Rule 2: Current state provided -> action
        if current_state:
            return "action"

        # Rule 3: Contains navigation patterns in Chinese
        if "从" in target and "到" in target:
            return "navigation"

        # Default: task query
        return "task"

    async def _query_task(
        self,
        target: str,
    ) -> QueryResult:
        """Execute task-level query using 3-layer architecture (v2).

        L1: CognitivePhrase match (fast, exact)
        L2: LLM-guided path planning (embedding recall + subgraph planning)
        L3a/L3b: Task decomposition with or without path context

        Args:
            target: Task description.

        Returns:
            QueryResult with task workflow.
        """
        # === L1: CognitivePhrase match ===
        l1_result = await self._l1_phrase_match(target)
        if l1_result:
            return l1_result

        # === L2: Path retrieval (private + public in parallel) ===
        path_result, path_source = await self._l2_path_retrieval(target)

        # === L3: Task decomposition ===
        global_states: List[State] = []
        global_actions: List[Action] = []

        if path_result and path_result["paths"]:
            best_path = path_result["paths"][0]
            global_states = best_path["states"]   # L2 global path
            global_actions = best_path["actions"]
            subtasks = await self._decompose_with_path(target, best_path)
            method = "path_decomposition"
        else:
            subtasks = await self._decompose_without_path(target)
            method = "direct_decomposition"

        has_global_path = len(global_states) > 0
        memory_hit = has_global_path
        memory_level = "L2" if has_global_path else "L3"
        metadata: Dict[str, Any] = {
            "method": method,
            "decompose_mode": method,
            "has_global_path": has_global_path,
            "memory_hit": memory_hit,
            "memory_level": memory_level,
            "source": path_source,
        }
        if path_result and isinstance(path_result.get("debug"), dict):
            metadata["path_planning_debug"] = path_result["debug"]

        if has_global_path or subtasks:
            return QueryResult.task_success(
                states=global_states,    # L2 global path (single copy)
                actions=global_actions,  # L2 global path (single copy)
                subtasks=subtasks,       # subtasks with path_state_indices only
                metadata=metadata,
            )
        else:
            return QueryResult(
                query_type="task",
                success=False,
                subtasks=subtasks,
                metadata={**metadata, "error": "No navigation info found"},
            )

    async def _l1_phrase_match(self, target: str) -> Optional[QueryResult]:
        """L1: CognitivePhrase match across private + public memory.

        When public_memory is available, merges phrases from both sources
        and lets LLM pick the best match in a single call.

        Returns:
            QueryResult if a phrase match was found, None otherwise.
        """
        if self.public_memory:
            private_phrases = self.memory.phrase_manager.list_phrases()
            public_phrases = self.public_memory.phrase_manager.list_phrases()
            can_satisfy, phrases, reasoning, source = (
                await self.phrase_checker.check_merged(
                    target, private_phrases, public_phrases
                )
            )
        else:
            can_satisfy, phrases, reasoning = await self.phrase_checker.check(target)
            source = "private"

        if not can_satisfy or not phrases:
            return None

        best_phrase = phrases[0]

        # Resolve states/actions from the correct memory source
        mem = self.public_memory if source == "public" and self.public_memory else self.memory

        states = []
        for state_id in best_phrase.state_path:
            state = mem.get_state(state_id)
            if state:
                states.append(state)

        actions = []
        for i in range(len(best_phrase.state_path) - 1):
            source_id = best_phrase.state_path[i]
            target_id = best_phrase.state_path[i + 1]
            action = mem.get_action(source_id, target_id)
            if action:
                actions.append(action)

        return QueryResult.task_success(
            states=states,
            actions=actions,
            execution_plan=best_phrase.execution_plan,
            cognitive_phrase=best_phrase,
            metadata={
                "method": "cognitive_phrase_match",
                "decompose_mode": "cognitive_phrase_match",
                "memory_hit": True,
                "memory_level": "L1",
                "reasoning": reasoning,
                "num_phrases": len(phrases),
                "source": source,
            },
        )

    async def _l2_path_retrieval(
        self, target: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """L2: Path retrieval across private + public memory.

        When public_memory is available, runs L2 planning on both memories
        in parallel, then selects the better path.

        Returns:
            (path_result, source) where source is "private" or "public".
        """
        if not self.public_memory:
            result = await self._find_navigation_path(target, memory=self.memory)
            return result, "private"

        if not self.llm_provider or not self.embedding_service:
            return None, "private"

        private_result, public_result = await asyncio.gather(
            self._find_navigation_path(target, memory=self.memory),
            self._find_navigation_path(target, memory=self.public_memory),
        )

        return await self._select_best_path(target, private_result, public_result)

    async def _select_best_path(
        self,
        target: str,
        private_result: Optional[Dict[str, Any]],
        public_result: Optional[Dict[str, Any]],
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Select best path result from private/public candidates.

        Preference order:
        1. Any non-empty path over empty result
        2. Higher path score
        3. Longer state coverage
        4. Private memory (tie-break)
        """
        _ = target  # Keep signature stable for callsites using semantic target.

        def _best_path(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            if not result:
                return None
            paths = result.get("paths") if isinstance(result, dict) else None
            if not paths or not isinstance(paths, list):
                return None
            first = paths[0]
            return first if isinstance(first, dict) else None

        priv_best = _best_path(private_result)
        pub_best = _best_path(public_result)

        if priv_best and not pub_best:
            return private_result, "private"
        if pub_best and not priv_best:
            return public_result, "public"
        if not priv_best and not pub_best:
            return None, "private"

        priv_score = float(priv_best.get("score", 0.0))
        pub_score = float(pub_best.get("score", 0.0))
        if pub_score > priv_score:
            return public_result, "public"
        if priv_score > pub_score:
            return private_result, "private"

        priv_steps = len(priv_best.get("states", []) or [])
        pub_steps = len(pub_best.get("states", []) or [])
        if pub_steps > priv_steps:
            return public_result, "public"
        return private_result, "private"

    async def _find_navigation_path(
        self,
        target: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        memory: Optional[Memory] = None,
    ) -> Optional[Dict[str, Any]]:
        """L2 compatibility wrapper for legacy callsites.

        The implementation is now delegated to `_plan_path_with_llm()`.
        """
        effective_top_k = top_k if top_k and top_k > 0 else self.path_planning_top_k
        effective_min_score = (
            float(min_score) if min_score is not None else self.path_planning_min_score
        )
        return await self._plan_path_with_llm(
            target=target,
            top_k=effective_top_k,
            min_score=effective_min_score,
            memory=memory,
        )

    async def _plan_path_with_llm(
        self,
        target: str,
        top_k: int,
        min_score: float,
        memory: Optional[Memory] = None,
        allow_domain_prefilter: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """L2: plan navigation path with LLM over a recalled subgraph."""
        if not self.llm_provider or not self.embedding_service:
            return None

        memory = memory or self.memory

        try:
            query_vector = await self.embedding_service.encode_async(target)
            if not query_vector:
                logger.info("[L2] Empty embedding for target, skip planning")
                return None

            raw_candidates = memory.state_manager.search_states_by_embedding(
                query_vector=query_vector,
                top_k=max(1, top_k),
            )
            scored_candidates = [
                (state, score)
                for state, score in raw_candidates
                if score >= min_score
            ]
            if not scored_candidates:
                logger.info(
                    f"[L2] No candidate states above threshold: min_score={min_score:.3f}"
                )
                return None

            planning_candidates = scored_candidates
            selected_domain: Optional[str] = None
            domain_prefilter_debug: Dict[str, Any] = {
                "enabled": self.path_planning_domain_prefilter_enabled,
                "applied": False,
                "reason": "prefilter_not_attempted",
                "candidate_count_before": len(scored_candidates),
                "candidate_count_after": len(scored_candidates),
            }

            if allow_domain_prefilter:
                planning_candidates, selected_domain, domain_prefilter_debug = (
                    self._apply_domain_prefilter(
                        target=target,
                        scored_candidates=scored_candidates,
                        memory=memory,
                    )
                )
                if "candidate_count_after" not in domain_prefilter_debug:
                    domain_prefilter_debug["candidate_count_after"] = len(planning_candidates)
            else:
                domain_prefilter_debug.update({
                    "reason": "prefilter_bypassed_for_fallback",
                })

            candidate_states, subgraph_actions, score_by_state_id = self._build_path_planning_subgraph(
                scored_candidates=planning_candidates,
                max_states=self.path_planning_max_states,
                max_actions=self.path_planning_max_actions,
                memory=memory,
                restrict_domain=(
                    selected_domain
                    if domain_prefilter_debug.get("applied") else None
                ),
            )
            if not candidate_states:
                if (
                    allow_domain_prefilter
                    and domain_prefilter_debug.get("applied")
                    and self.path_planning_domain_fallback_to_full_graph
                ):
                    logger.info(
                        "[L2] Domain prefilter produced empty subgraph, retrying full candidates"
                    )
                    fallback_result = await self._plan_path_with_llm(
                        target=target,
                        top_k=top_k,
                        min_score=min_score,
                        memory=memory,
                        allow_domain_prefilter=False,
                    )
                    if isinstance(fallback_result, dict):
                        fallback_debug = fallback_result.get("debug")
                        if isinstance(fallback_debug, dict):
                            fallback_debug["domain_prefilter_fallback"] = {
                                "triggered": True,
                                "reason": "empty_subgraph_after_prefilter",
                                "selected_domain": selected_domain,
                                "selected_score": domain_prefilter_debug.get("selected_score", 0.0),
                            }
                    return fallback_result
                return None

            state_map = {state.id: state for state in candidate_states}
            alias_by_id = {
                state.id: f"s{idx + 1}" for idx, state in enumerate(candidate_states)
            }
            id_by_alias = {alias: state_id for state_id, alias in alias_by_id.items()}

            action_by_pair: Dict[tuple[str, str], Action] = {}
            for action in subgraph_actions:
                if action.source and action.target:
                    action_by_pair[(action.source, action.target)] = action

            states_text = self._format_path_planning_states_text(
                states=candidate_states,
                alias_by_id=alias_by_id,
            )
            actions_text = self._format_path_planning_actions_text(
                actions=subgraph_actions,
                alias_by_id=alias_by_id,
            )

            base_user_prompt = build_path_planning_user_prompt(
                task=target,
                states_text=states_text,
                actions_text=actions_text,
            )
            outgoing_by_source_id: Dict[str, List[Action]] = {}
            for action in subgraph_actions:
                if action.source and action.target:
                    outgoing_by_source_id.setdefault(action.source, []).append(action)

            attempt_records: List[Dict[str, Any]] = []
            replan_feedback: Optional[Dict[str, Any]] = None
            previous_invalid_signature: Optional[str] = None
            final_user_prompt = base_user_prompt
            final_planner_result: Dict[str, Any] = {}
            stop_reason = "unknown"
            planned_state_ids: List[str] = []
            planned_actions: List[Action] = []

            while True:
                if replan_feedback is None:
                    user_prompt = base_user_prompt
                else:
                    user_prompt = build_path_planning_replan_user_prompt(
                        base_user_prompt=base_user_prompt,
                        previous_result=replan_feedback["previous_result"],
                        failure_feedback=replan_feedback["failure_feedback"],
                        neighbor_hints=replan_feedback["neighbor_hints"],
                    )
                final_user_prompt = user_prompt

                raw_result = await self.llm_provider.generate_json_response(
                    system_prompt=PATH_PLANNING_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                )
                planner_result = raw_result if isinstance(raw_result, dict) else {
                    "answer": raw_result
                }
                final_planner_result = planner_result

                attempt_no = len(attempt_records) + 1
                attempt_record: Dict[str, Any] = {
                    "attempt": attempt_no,
                    "user_prompt": user_prompt,
                    "raw_result": planner_result,
                }

                if not self._planner_can_plan(planner_result):
                    stop_reason = "can_plan_false"
                    attempt_record["status"] = stop_reason
                    attempt_records.append(attempt_record)
                    break

                resolved_state_ids, resolve_failure = self._resolve_planned_path_ids_with_error(
                    planner_result=planner_result,
                    id_by_alias=id_by_alias,
                    state_map=state_map,
                )
                if not resolved_state_ids:
                    failure_feedback = (
                        resolve_failure
                        or "系统无法从上一次输出中解析出有效路径；若确实无法规划，请返回 can_plan=false。"
                    )
                    attempt_record["status"] = "invalid_path"
                    attempt_record["failure_feedback"] = failure_feedback
                    attempt_records.append(attempt_record)

                    invalid_signature = self._build_invalid_planner_signature(
                        planner_result=planner_result,
                        failure_feedback=failure_feedback,
                        failed_edge=None,
                    )
                    if previous_invalid_signature == invalid_signature:
                        stop_reason = "stalled_same_invalid_path"
                        break
                    previous_invalid_signature = invalid_signature

                    replan_feedback = {
                        "previous_result": planner_result,
                        "failure_feedback": failure_feedback,
                        "neighbor_hints": "(本轮无可用断边线索)",
                    }
                    continue

                validated_actions, disconnected_edge = self._validate_planned_path_with_error(
                    state_ids=resolved_state_ids,
                    action_by_pair=action_by_pair,
                    memory=memory,
                )
                if validated_actions is None:
                    source_id = disconnected_edge[0] if disconnected_edge else ""
                    target_id = disconnected_edge[1] if disconnected_edge else ""
                    source_alias = alias_by_id.get(source_id, source_id)
                    target_alias = alias_by_id.get(target_id, target_id)

                    failure_feedback = (
                        "系统硬校验失败：路径不连通。"
                        f"断边为 {source_alias}({source_id}) -> {target_alias}({target_id})。"
                        "请基于已知连通边重新规划；若无法满足，请返回 can_plan=false。"
                    )
                    neighbor_hints = self._build_neighbor_hints_for_source(
                        source_id=source_id,
                        alias_by_id=alias_by_id,
                        outgoing_actions=outgoing_by_source_id.get(source_id, []),
                    )

                    attempt_record["status"] = "disconnected_path"
                    attempt_record["failure_feedback"] = failure_feedback
                    attempt_record["failed_edge"] = {
                        "source_id": source_id,
                        "source_alias": source_alias,
                        "target_id": target_id,
                        "target_alias": target_alias,
                    }
                    attempt_records.append(attempt_record)

                    invalid_signature = self._build_invalid_planner_signature(
                        planner_result=planner_result,
                        failure_feedback=failure_feedback,
                        failed_edge=disconnected_edge,
                    )
                    if previous_invalid_signature == invalid_signature:
                        stop_reason = "stalled_same_invalid_path"
                        break
                    previous_invalid_signature = invalid_signature

                    replan_feedback = {
                        "previous_result": planner_result,
                        "failure_feedback": failure_feedback,
                        "neighbor_hints": neighbor_hints,
                    }
                    continue

                planned_state_ids = resolved_state_ids
                planned_actions = validated_actions
                stop_reason = "success"
                attempt_record["status"] = stop_reason
                attempt_records.append(attempt_record)
                break

            reasoning = self._safe_text(final_planner_result.get("reasoning"))
            embedding_candidates_debug = []
            for idx, (state, score) in enumerate(planning_candidates, 1):
                embedding_candidates_debug.append({
                    "rank": idx,
                    "state": {
                        "id": state.id,
                        "description": self._get_state_reasoning_text(state),
                        "page_title": state.page_title or "",
                        "page_url": state.page_url or "",
                    },
                    "score": float(score),
                })

            candidate_states_debug = []
            for idx, state in enumerate(candidate_states, 1):
                state_id = state.id
                candidate_states_debug.append({
                    "rank": idx,
                    "alias": alias_by_id.get(state_id, state_id),
                    "id": state_id,
                    "description": self._get_state_reasoning_text(state),
                    "page_title": state.page_title or "",
                    "page_url": state.page_url or "",
                    "score": float(score_by_state_id.get(state_id, 0.0)),
                })

            subgraph_actions_debug = []
            for idx, action in enumerate(subgraph_actions, 1):
                trigger = action.trigger if isinstance(action.trigger, dict) else {}
                subgraph_actions_debug.append({
                    "rank": idx,
                    "id": action.id,
                    "source_id": action.source,
                    "source_alias": alias_by_id.get(action.source, action.source),
                    "target_id": action.target,
                    "target_alias": alias_by_id.get(action.target, action.target),
                    "description": action.description or "",
                    "type": action.type or "",
                    "trigger": {
                        "text": self._safe_text(trigger.get("text")),
                        "role": self._safe_text(
                            trigger.get("role") or trigger.get("element_role")
                        ),
                        "ref": self._safe_text(
                            trigger.get("ref") or trigger.get("element_ref")
                        ),
                    },
                })

            resolved_states_debug = []
            for idx, state_id in enumerate(planned_state_ids, 1):
                state = state_map[state_id]
                resolved_states_debug.append({
                    "index": idx,
                    "alias": alias_by_id.get(state_id, state_id),
                    "id": state_id,
                    "description": self._get_state_reasoning_text(state),
                    "page_title": state.page_title or "",
                    "page_url": state.page_url or "",
                    "score": float(score_by_state_id.get(state_id, 0.0)),
                })

            resolved_actions_debug = []
            for idx, action in enumerate(planned_actions, 1):
                resolved_actions_debug.append({
                    "index": idx,
                    "id": action.id,
                    "source_id": action.source,
                    "source_alias": alias_by_id.get(action.source, action.source),
                    "target_id": action.target,
                    "target_alias": alias_by_id.get(action.target, action.target),
                    "description": action.description or "",
                    "type": action.type or "",
                })

            debug_payload: Dict[str, Any] = {
                "task": target,
                "config": {
                    "candidate_top_k": int(top_k),
                    "min_score": float(min_score),
                    "max_states": int(self.path_planning_max_states),
                    "max_actions": int(self.path_planning_max_actions),
                    "domain_prefilter_enabled": bool(
                        self.path_planning_domain_prefilter_enabled
                    ),
                    "domain_match_threshold": float(
                        self.path_planning_domain_match_threshold
                    ),
                    "domain_min_candidates": int(
                        self.path_planning_domain_min_candidates
                    ),
                    "domain_fallback_to_full_graph": bool(
                        self.path_planning_domain_fallback_to_full_graph
                    ),
                },
                "domain_prefilter": domain_prefilter_debug,
                "embedding_candidates": embedding_candidates_debug,
                "subgraph": {
                    "states": candidate_states_debug,
                    "actions": subgraph_actions_debug,
                    "states_text": states_text,
                    "actions_text": actions_text,
                },
                "llm": {
                    "system_prompt": PATH_PLANNING_SYSTEM_PROMPT,
                    "user_prompt": final_user_prompt,
                    "raw_result": final_planner_result,
                    "attempts": attempt_records,
                    "stop_reason": stop_reason,
                },
                "resolved_path": {
                    "state_ids": planned_state_ids,
                    "states": resolved_states_debug,
                    "actions": resolved_actions_debug,
                    "reasoning": reasoning,
                },
            }

            if stop_reason == "success" and planned_state_ids:
                planned_states = [state_map[state_id] for state_id in planned_state_ids]
                path = {
                    "score": 1.0,
                    "states": planned_states,
                    "actions": planned_actions,
                    "reasoning": reasoning,
                    "planner": "llm_subgraph_planning",
                    "candidate_state_count": len(candidate_states),
                    "candidate_action_count": len(subgraph_actions),
                }
                logger.info(
                    "[L2] Planned path: states=%s actions=%s ids=%s",
                    len(planned_states),
                    len(planned_actions),
                    [sid[:8] for sid in planned_state_ids],
                )
                return {
                    "target_query": target,
                    "key_queries": [],
                    "paths": [path],
                    "planner_result": final_planner_result,
                    "debug": debug_payload,
                }

            logger.info(
                "[L2] No valid connected path after replanning (stop_reason=%s)",
                stop_reason,
            )
            empty_result = {
                "target_query": target,
                "key_queries": [],
                "paths": [],
                "planner_result": final_planner_result,
                "debug": debug_payload,
            }

            if (
                allow_domain_prefilter
                and domain_prefilter_debug.get("applied")
                and self.path_planning_domain_fallback_to_full_graph
            ):
                logger.info(
                    "[L2] Domain prefilter planning failed (stop_reason=%s), retrying full candidates",
                    stop_reason,
                )
                fallback_result = await self._plan_path_with_llm(
                    target=target,
                    top_k=top_k,
                    min_score=min_score,
                    memory=memory,
                    allow_domain_prefilter=False,
                )
                if isinstance(fallback_result, dict):
                    fallback_debug = fallback_result.get("debug")
                    if isinstance(fallback_debug, dict):
                        fallback_debug["domain_prefilter_fallback"] = {
                            "triggered": True,
                            "reason": "no_valid_path_after_prefilter",
                            "stop_reason": stop_reason,
                            "selected_domain": selected_domain,
                            "selected_score": domain_prefilter_debug.get(
                                "selected_score", 0.0
                            ),
                        }
                return fallback_result

            return empty_result
        except Exception as exc:
            logger.error(f"[L2] Path planning failed: {exc}")
            import traceback
            traceback.print_exc()
            return None

    def _build_path_planning_subgraph(
        self,
        scored_candidates: List[tuple[State, float]],
        max_states: int,
        max_actions: int,
        memory: Optional[Memory] = None,
        restrict_domain: Optional[str] = None,
    ) -> tuple[List[State], List[Action], Dict[str, float]]:
        """Build a bounded state/action subgraph for LLM planning."""
        memory = memory or self.memory

        candidate_states: List[State] = []
        score_by_state_id: Dict[str, float] = {}
        normalized_restrict_domain = self._safe_text(restrict_domain)

        def _state_allowed(state: State) -> bool:
            if not normalized_restrict_domain:
                return True
            return self._extract_domain_from_state(state) == normalized_restrict_domain

        # Seed states from embedding recall (already sorted by score desc).
        for state, score in scored_candidates:
            if not _state_allowed(state):
                continue
            if state.id in score_by_state_id:
                if score > score_by_state_id[state.id]:
                    score_by_state_id[state.id] = float(score)
                continue
            candidate_states.append(state)
            score_by_state_id[state.id] = float(score)
            if len(candidate_states) >= max_states:
                break

        # Expand one-hop outgoing neighbors as bridge states.
        for state in list(candidate_states):
            if len(candidate_states) >= max_states:
                break
            outgoing_actions = memory.state_manager.get_connected_actions(
                state.id,
                direction="outgoing",
            )
            for action in outgoing_actions:
                target_id = action.target
                if not target_id or target_id in score_by_state_id:
                    continue
                bridge_state = memory.get_state(target_id)
                if not bridge_state:
                    continue
                if not _state_allowed(bridge_state):
                    continue
                candidate_states.append(bridge_state)
                parent_score = score_by_state_id.get(state.id, 0.0)
                score_by_state_id[target_id] = max(parent_score * 0.95, 0.0)
                if len(candidate_states) >= max_states:
                    break

        state_ids = {state.id for state in candidate_states}
        action_by_pair: Dict[tuple[str, str], Action] = {}
        for state in candidate_states:
            outgoing_actions = memory.state_manager.get_connected_actions(
                state.id,
                direction="outgoing",
            )
            for action in outgoing_actions:
                if action.source in state_ids and action.target in state_ids:
                    pair = (action.source, action.target)
                    if pair not in action_by_pair:
                        action_by_pair[pair] = action
                if len(action_by_pair) >= max_actions:
                    break
            if len(action_by_pair) >= max_actions:
                break

        return candidate_states, list(action_by_pair.values()), score_by_state_id

    def _format_path_planning_states_text(
        self,
        states: List[State],
        alias_by_id: Dict[str, str],
    ) -> str:
        lines: List[str] = []
        for idx, state in enumerate(states, 1):
            state_alias = alias_by_id.get(state.id, state.id)
            description = self._safe_text(self._get_state_reasoning_text(state))
            if not description:
                description = self._safe_text(state.page_title) or self._safe_text(state.id)
            lines.append(f"{idx}. [{state_alias}] {description}")
            if state.page_url:
                lines.append(f"   URL: {state.page_url}")
        return "\n".join(lines)

    def _format_path_planning_actions_text(
        self,
        actions: List[Action],
        alias_by_id: Dict[str, str],
    ) -> str:
        if not actions:
            return "(无已知导航关系)"

        lines: List[str] = []
        for action in actions:
            source_alias = alias_by_id.get(action.source, action.source)
            target_alias = alias_by_id.get(action.target, action.target)
            action_desc = self._safe_text(action.description) or "点击页面元素导航"

            trigger = action.trigger if isinstance(action.trigger, dict) else {}
            trigger_parts: List[str] = []
            trigger_text = self._safe_text(trigger.get("text"))
            if trigger_text:
                trigger_parts.append(f'text="{trigger_text}"')
            trigger_role = self._safe_text(trigger.get("role") or trigger.get("element_role"))
            if trigger_role:
                trigger_parts.append(f"role={trigger_role}")
            if trigger_parts:
                action_desc = f"{action_desc} ({', '.join(trigger_parts)})"

            lines.append(f"- {source_alias} -> {target_alias}: {action_desc}")
        return "\n".join(lines)

    def _planner_can_plan(self, planner_result: Dict[str, Any]) -> bool:
        """Check whether planner explicitly indicates it can produce a path."""
        can_plan = planner_result.get("can_plan")
        if isinstance(can_plan, str):
            can_plan = can_plan.strip().lower() == "true"
        return can_plan is True

    def _resolve_planned_path_ids_with_error(
        self,
        planner_result: Dict[str, Any],
        id_by_alias: Dict[str, str],
        state_map: Dict[str, State],
    ) -> tuple[List[str], Optional[str]]:
        """Resolve planner path IDs and return parse failure reason when invalid."""
        if not self._planner_can_plan(planner_result):
            return [], "模型判断无法规划（can_plan=false）。"

        raw_path = planner_result.get("path")
        if not isinstance(raw_path, list) or not raw_path:
            return [], "模型返回了空路径；若无法规划请直接返回 can_plan=false。"

        resolved_state_ids: List[str] = []
        for raw_id in raw_path:
            state_ref = self._safe_text(raw_id)
            if not state_ref:
                continue
            state_id = id_by_alias.get(state_ref, state_ref)
            if state_id not in state_map:
                return [], (
                    f"模型返回了未知状态 {state_ref}，该状态不在当前可选页面子图中。"
                )
            if not resolved_state_ids or resolved_state_ids[-1] != state_id:
                resolved_state_ids.append(state_id)

        if not resolved_state_ids:
            return [], "模型路径在去重后为空；若无法规划请返回 can_plan=false。"

        return resolved_state_ids, None

    def _validate_planned_path_with_error(
        self,
        state_ids: List[str],
        action_by_pair: Dict[tuple[str, str], Action],
        memory: Optional[Memory] = None,
    ) -> tuple[Optional[List[Action]], Optional[tuple[str, str]]]:
        """Validate path connectivity and return first disconnected edge when invalid."""
        memory = memory or self.memory

        if len(state_ids) <= 1:
            return [], None

        planned_actions: List[Action] = []
        for idx in range(len(state_ids) - 1):
            source_id = state_ids[idx]
            target_id = state_ids[idx + 1]
            action = action_by_pair.get((source_id, target_id))
            if not action:
                action = memory.get_action(source_id, target_id)
                if action:
                    action_by_pair[(source_id, target_id)] = action

            if not action:
                logger.warning(
                    "[L2] Planner produced disconnected path edge: %s -> %s",
                    source_id[:8],
                    target_id[:8],
                )
                return None, (source_id, target_id)
            planned_actions.append(action)

        return planned_actions, None

    def _build_neighbor_hints_for_source(
        self,
        source_id: str,
        alias_by_id: Dict[str, str],
        outgoing_actions: List[Action],
    ) -> str:
        """Build neighbor hints for a disconnected source node."""
        if not source_id:
            return "(无可用断边线索)"

        source_alias = alias_by_id.get(source_id, source_id)
        if not outgoing_actions:
            return (
                f"断边起点 {source_alias}({source_id}) 在当前子图中没有已知 outgoing 导航边。"
            )

        lines = [
            f"断边起点 {source_alias}({source_id}) 的可达邻居如下（仅这些边可直接前进）："
        ]
        seen_pairs: set[tuple[str, str]] = set()
        for action in outgoing_actions:
            if not action.target:
                continue
            pair = (action.source or "", action.target)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            target_alias = alias_by_id.get(action.target, action.target)
            action_desc = self._safe_text(action.description) or "点击页面元素导航"
            lines.append(
                f"- {source_alias} -> {target_alias} "
                f"({pair[0]} -> {pair[1]}): {action_desc}"
            )
        return "\n".join(lines) if len(lines) > 1 else (
            f"断边起点 {source_alias}({source_id}) 在当前子图中没有可用邻居。"
        )

    def _build_invalid_planner_signature(
        self,
        planner_result: Dict[str, Any],
        failure_feedback: str,
        failed_edge: Optional[tuple[str, str]],
    ) -> str:
        """Build signature for invalid planner outputs to avoid endless identical retries."""
        signature_payload = {
            "can_plan": planner_result.get("can_plan"),
            "path": planner_result.get("path"),
            "failure_feedback": failure_feedback,
            "failed_edge": list(failed_edge) if failed_edge else None,
        }
        try:
            return json.dumps(signature_payload, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(signature_payload)

    def _resolve_planned_path_ids(
        self,
        planner_result: Dict[str, Any],
        id_by_alias: Dict[str, str],
        state_map: Dict[str, State],
    ) -> List[str]:
        """Backward-compatible resolver returning empty list on invalid output."""
        resolved_state_ids, _ = self._resolve_planned_path_ids_with_error(
            planner_result=planner_result,
            id_by_alias=id_by_alias,
            state_map=state_map,
        )
        return resolved_state_ids

    def _validate_planned_path(
        self,
        state_ids: List[str],
        action_by_pair: Dict[tuple[str, str], Action],
        memory: Optional[Memory] = None,
    ) -> Optional[List[Action]]:
        """Backward-compatible validator returning None on disconnected path."""
        planned_actions, _ = self._validate_planned_path_with_error(
            state_ids=state_ids,
            action_by_pair=action_by_pair,
            memory=memory,
        )
        return planned_actions

    async def _decompose_with_path(
        self, target: str, path: Dict[str, Any]
    ) -> List[SubTaskResult]:
        """L3a: Decompose target into subtasks using path as navigation context."""
        path_states: List[State] = path["states"]

        # Build input for prompt
        path_state_dicts = []
        for i, state in enumerate(path_states):
            state_text = self._get_state_reasoning_text(state)
            path_state_dicts.append({
                "index": i,
                "page_url": state.page_url or "",
                "page_title": state.page_title or "",
                "description": state_text,
            })

        input_data = PathDecompositionInput(
            target=target,
            path_states=path_state_dicts,
        )

        try:
            prompt_text = self.path_decomposition_prompt.build_prompt(input_data)
            system_prompt = self.path_decomposition_prompt.get_system_prompt()

            response = await self.llm_provider.generate_response(
                system_prompt=system_prompt,
                user_prompt=prompt_text,
            )

            logger.info(f"[L3a] Path decomposition response: {response[:200]}...")

            output = self.path_decomposition_prompt.parse_response(response)

            subtasks: List[SubTaskResult] = []
            for st_data in output.subtasks:
                indices = st_data.get("path_state_indices", [])
                # Only store indices, not full path - global path is in QueryResult.states/actions
                subtasks.append(SubTaskResult(
                    task_id=st_data.get("task_id", f"task_{len(subtasks)+1}"),
                    target=st_data.get("target", ""),
                    path_state_indices=indices,
                    found=len(indices) > 0,
                ))

            return subtasks

        except Exception as exc:
            logger.error(f"[L3a] Path decomposition failed: {exc}")
            # Fallback: single subtask covering all path states
            all_indices = list(range(len(path_states)))
            return [SubTaskResult(
                task_id="task_1",
                target=target,
                path_state_indices=all_indices,
                found=len(all_indices) > 0,
            )]

    async def _decompose_without_path(self, target: str) -> List[SubTaskResult]:
        """L3b: Decompose target into subtasks without navigation context.

        Uses existing TaskDecompositionPrompt but does NOT execute retrieval per subtask.
        Returns subtasks with found=False so the agent navigates on its own.
        """
        try:
            dag = await self._decompose_target(target)
            order = dag.topological_order()

            subtasks: List[SubTaskResult] = []
            for task_id in order:
                node = dag.nodes[task_id]
                subtasks.append(SubTaskResult(
                    task_id=task_id,
                    target=node.get("target", node.get("description", "")),
                    path_state_indices=[],  # No path info
                    found=False,
                ))

            return subtasks

        except Exception as exc:
            logger.error(f"[L3b] Decomposition failed: {exc}")
            return [SubTaskResult(
                task_id="task_1",
                target=target,
                path_state_indices=[],
                found=False,
            )]

    async def _query_navigation(
        self,
        target: str,
        start_state: str,
        end_state: str,
    ) -> QueryResult:
        """Execute navigation-level query (v2).

        Finds the shortest path between two states across private + public memory.
        Both start_state and end_state can be either exact state IDs or semantic
        descriptions (will use embedding search to resolve).

        Args:
            target: Optional target description (unused, kept for interface consistency).
            start_state: Start state ID or description.
            end_state: End state ID or description.

        Returns:
            QueryResult with navigation path.
        """
        # Try private memory
        priv_path = await self._find_shortest_path_in_memory(
            start_state, end_state, self.memory
        )

        # Try public memory
        pub_path = None
        if self.public_memory:
            pub_path = await self._find_shortest_path_in_memory(
                start_state, end_state, self.public_memory
            )

        if not priv_path and not pub_path:
            return QueryResult.navigation_failure(
                error=f"No path found from {start_state} to {end_state}",
            )

        # If only one has result, use it
        if priv_path and not pub_path:
            states, actions = priv_path
            source = "private"
        elif pub_path and not priv_path:
            states, actions = pub_path
            source = "public"
        else:
            # Both have results — use LLM to select via _select_best_path
            priv_states, priv_actions = priv_path
            pub_states, pub_actions = pub_path

            priv_dict = {"paths": [{"score": 1.0, "states": priv_states, "actions": priv_actions}]}
            pub_dict = {"paths": [{"score": 1.0, "states": pub_states, "actions": pub_actions}]}

            nav_target = target or f"{start_state} -> {end_state}"
            _, source = await self._select_best_path(nav_target, priv_dict, pub_dict)

            if source == "public":
                states, actions = pub_states, pub_actions
            else:
                states, actions = priv_states, priv_actions

        return QueryResult.navigation_success(
            states=states,
            actions=actions,
            metadata={"source": source},
        )

    async def _find_shortest_path_in_memory(
        self,
        start_state: str,
        end_state: str,
        memory: Memory,
    ) -> Optional[Tuple[List[State], List[Action]]]:
        """Resolve states and find shortest path within a single memory.

        Returns:
            (states, actions) tuple or None if not found.
        """
        start_id = await self._resolve_state_id(start_state, memory=memory)
        end_id = await self._resolve_state_id(end_state, memory=memory)

        if not start_id or not end_id:
            return None

        path_result = memory.action_manager.find_shortest_path(
            source_id=start_id,
            target_id=end_id,
            state_manager=memory.state_manager,
        )
        return path_result

    async def _query_action(
        self,
        target: str,
        current_state: str,
        top_k: int = 10,
    ) -> QueryResult:
        """Execute action-level query across private + public memory.

        Finds available IntentSequences in the current state from both memories,
        merges and deduplicates results.

        Args:
            target: Action description to search for (empty for exploration).
            current_state: State ID, URL, or semantic description.
            top_k: Number of top results to return.

        Returns:
            QueryResult with matching IntentSequences.
        """
        # If target is empty, return exploration result
        if not target.strip():
            return await self._get_page_capabilities(current_state)

        # Gather sequences from both memories
        all_sequences: List[IntentSequence] = []
        query_vector = await self.embedding_service.encode_async(target) if self.embedding_service else None

        for mem in self._active_memories():
            state_id = await self._resolve_state_id(current_state, memory=mem)
            if not state_id or not mem.intent_sequence_manager:
                continue

            if query_vector is not None:
                results = mem.intent_sequence_manager.search_by_embedding(
                    query_vector=query_vector,
                    state_id=state_id,
                    top_k=top_k,
                )
                if results:
                    all_sequences.extend(seq for seq, _ in results)
                    continue

            # Fallback: list all sequences for the state
            sequences = mem.intent_sequence_manager.list_by_state(state_id)
            all_sequences.extend(sequences)

        if not all_sequences:
            return QueryResult.action_failure(
                error=f"No actions found for state: {current_state}",
            )

        # Deduplicate by description (keep first occurrence = private priority)
        deduped = self._deduplicate_sequences(all_sequences)
        return QueryResult.action_success(
            intent_sequences=deduped,
            metadata={
                "method": "merged_search",
                "num_results": len(deduped),
                "source": "merged" if self.public_memory else "private",
            },
        )

    async def _get_page_capabilities(self, current_state: str) -> QueryResult:
        """Get all available actions/navigations for a state (exploration query).

        Merges results from both private and public memory.

        Args:
            current_state: State ID, URL, or semantic description.

        Returns:
            QueryResult with all available actions.
        """
        all_sequences: List[IntentSequence] = []
        all_outgoing: List[Action] = []

        for mem in self._active_memories():
            state_id = await self._resolve_state_id(current_state, memory=mem)
            if not state_id:
                continue

            if mem.intent_sequence_manager:
                sequences = mem.intent_sequence_manager.list_by_state(state_id)
                all_sequences.extend(sequences)

            outgoing = mem.action_manager.list_outgoing_actions(state_id)
            all_outgoing.extend(outgoing)

        deduped_sequences = self._deduplicate_sequences(all_sequences)

        return QueryResult(
            query_type="action",
            success=True,
            intent_sequences=deduped_sequences,
            actions=all_outgoing,
            metadata={
                "method": "exploration",
                "num_sequences": len(deduped_sequences),
                "num_outgoing_actions": len(all_outgoing),
                "source": "merged" if self.public_memory else "private",
            },
        )

    def _active_memories(self) -> List[Memory]:
        """Return list of active memory instances (private + public if available)."""
        memories = [self.memory]
        if self.public_memory:
            memories.append(self.public_memory)
        return memories

    @staticmethod
    def _deduplicate_sequences(
        sequences: List[IntentSequence],
    ) -> List[IntentSequence]:
        """Deduplicate IntentSequences by description text.

        Keeps first occurrence (private comes first, so private is preferred).
        """
        seen_descriptions: set = set()
        deduped: List[IntentSequence] = []
        for seq in sequences:
            desc = (seq.description or "").strip().lower()
            if desc and desc in seen_descriptions:
                continue
            if desc:
                seen_descriptions.add(desc)
            deduped.append(seq)
        return deduped

    async def _resolve_state_id(
        self,
        state_ref: str,
        memory: Optional[Memory] = None,
    ) -> Optional[str]:
        """Resolve a state reference (ID, URL, or description) to an actual state ID.

        Resolution order:
        1. Direct ID lookup
        2. URL lookup (if state_ref starts with http)
        3. Embedding semantic search (with similarity threshold)

        Args:
            state_ref: State ID, URL, or semantic description.
            memory: Memory instance to search. Defaults to self.memory.

        Returns:
            State ID if found and above similarity threshold, None otherwise.
        """
        memory = memory or self.memory
        logger.info(f"[_resolve_state_id] Resolving state_ref: '{state_ref[:100]}...'")

        # 1. Direct ID lookup
        state = memory.get_state(state_ref)
        if state:
            logger.info(f"[_resolve_state_id] Direct lookup found: {state.id}")
            return state.id

        # 2. URL lookup
        if state_ref.startswith("http://") or state_ref.startswith("https://"):
            logger.info(f"[_resolve_state_id] Trying URL lookup...")
            state = memory.find_state_by_url(state_ref)
            if state:
                logger.info(f"[_resolve_state_id] URL lookup found: {state.id}")
                return state.id
            logger.info(f"[_resolve_state_id] URL lookup failed")

        # 3. Embedding semantic search
        logger.info(f"[_resolve_state_id] Trying embedding search...")
        if not self.embedding_service:
            logger.error("[_resolve_state_id] embedding_service is None")
            return None

        try:
            query_vector = await self.embedding_service.encode_async(state_ref)
            if query_vector is None:
                logger.error("[_resolve_state_id] encode_async() returned None")
                return None

            results = memory.state_manager.search_states_by_embedding(
                query_vector, top_k=1
            )

            if results:
                first_result = results[0]
                if isinstance(first_result, tuple):
                    state_obj, score = first_result
                    # Apply similarity threshold
                    if score >= self.state_resolution_threshold:
                        logger.info(
                            f"[_resolve_state_id] Embedding search found: {state_obj.id} "
                            f"(score={score:.3f} >= threshold={self.state_resolution_threshold})"
                        )
                        return state_obj.id
                    else:
                        logger.info(
                            f"[_resolve_state_id] Embedding search result below threshold: "
                            f"{state_obj.id} (score={score:.3f} < threshold={self.state_resolution_threshold})"
                        )
                        return None
                else:
                    # Legacy format without score - accept it
                    logger.info(f"[_resolve_state_id] Embedding search found: {first_result.id}")
                    return first_result.id

            logger.info("[_resolve_state_id] No embedding search results")

        except Exception as e:
            logger.error(f"[_resolve_state_id] Embedding search failed: {e}")

        return None


__all__ = ["Reasoner"]


