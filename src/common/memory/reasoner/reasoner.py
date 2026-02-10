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
import logging
import uuid
from typing import Any, Dict, List, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

from src.common.memory.memory.memory import Memory
from src.common.memory.ontology.action import Action
from src.common.memory.ontology.intent_sequence import IntentSequence
from src.common.memory.ontology.query_result import QueryResult, SubTaskResult
from src.common.memory.ontology.state import State
from src.common.memory.reasoner.cognitive_phrase_checker import CognitivePhraseChecker
from src.common.memory.reasoner.prompts.path_based_decomposition_prompt import (
    PathBasedDecompositionPrompt,
    PathDecompositionInput,
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

    def __init__(
        self,
        memory: Memory,
        llm_provider: Optional[Any] = None,
        embedding_service=None,
        max_depth: int = 3,
        similarity_thresholds: Optional[Dict[str, float]] = None,
        public_memory: Optional[Memory] = None,
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
        L2: Path retrieval (embedding + BFS)
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

        if has_global_path or subtasks:
            return QueryResult.task_success(
                states=global_states,    # L2 global path (single copy)
                actions=global_actions,  # L2 global path (single copy)
                subtasks=subtasks,       # subtasks with path_state_indices only
                metadata={
                    "method": method,
                    "has_global_path": has_global_path,
                    "source": path_source,
                },
            )
        else:
            return QueryResult(
                query_type="task",
                success=False,
                subtasks=subtasks,
                metadata={"method": method, "error": "No navigation info found"},
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
                "reasoning": reasoning,
                "num_phrases": len(phrases),
                "source": source,
            },
        )

    async def _l2_path_retrieval(
        self, target: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """L2: Path retrieval across private + public memory.

        When public_memory is available, runs embedding search + BFS on both
        in parallel, then uses LLM to select the best path.

        Returns:
            (path_result, source) where source is "private" or "public".
        """
        if not self.public_memory:
            result = await self._find_navigation_path(target, memory=self.memory)
            return result, "private"

        if not self.llm_provider or not self.embedding_service:
            return None, "private"

        # Share query decomposition across both memories (single LLM call)
        decomposed = await self._decompose_query_for_path(target)

        min_score = self.path_finding_threshold

        # Run embedding search + BFS on both memories in parallel
        private_result, public_result = await asyncio.gather(
            asyncio.to_thread(
                self._embedding_search_and_bfs, decomposed, self.memory, 10, min_score
            ),
            asyncio.to_thread(
                self._embedding_search_and_bfs, decomposed, self.public_memory, 10, min_score
            ),
        )

        return await self._select_best_path(target, private_result, public_result)

    async def _find_navigation_path(
        self, target: str, top_k: int = 10, min_score: Optional[float] = None,
        memory: Optional[Memory] = None,
    ) -> Optional[Dict[str, Any]]:
        """L2: Find navigation path using embedding search + BFS reverse traversal.

        Args:
            target: Task target description.
            top_k: Number of top results.
            min_score: Minimum embedding similarity score. If None, uses configured threshold.
            memory: Memory instance to search. Defaults to self.memory.

        Returns:
            Dict with target_query, key_queries, and paths (sorted by score),
            or None if no paths found.
        """
        if not self.llm_provider or not self.embedding_service:
            return None

        if min_score is None:
            min_score = self.path_finding_threshold

        memory = memory or self.memory

        try:
            decomposed = await self._decompose_query_for_path(target)
            return self._embedding_search_and_bfs(decomposed, memory, top_k, min_score)

        except Exception as exc:
            logger.error(f"[L2] Path retrieval failed: {exc}")
            import traceback
            traceback.print_exc()
            return None

    def _embedding_search_and_bfs(
        self,
        decomposed: Dict[str, Any],
        memory: Memory,
        top_k: int = 10,
        min_score: float = 0.3,
    ) -> Optional[Dict[str, Any]]:
        """Execute embedding search + BFS on a specific memory instance.

        Args:
            decomposed: Result from _decompose_query_for_path (target_query + key_queries).
            memory: Memory instance to search.
            top_k: Number of top results.
            min_score: Minimum embedding similarity score.

        Returns:
            Dict with target_query, key_queries, and paths, or None.
        """
        target_query = decomposed.get("target_query", "")
        key_queries = decomposed.get("key_queries", [])

        # Step 1: Embedding search for target states
        target_states: List[tuple] = []
        target_state_ids: set = set()
        tq_embedding = self.embedding_service.encode(target_query)
        if tq_embedding:
            results = memory.state_manager.search_states_by_embedding(
                query_vector=tq_embedding, top_k=top_k
            )
            for state, score in results:
                if score >= min_score:
                    target_states.append((state, score))
                    target_state_ids.add(state.id)

        logger.info(f"[L2] Target states for '{target_query}': {len(target_states)}")

        if not target_states:
            return None

        # Step 2: Embedding search for key states
        key_states_by_type: Dict[str, List[tuple]] = {}
        key_type_state_ids: Dict[str, set] = {}
        for kq in key_queries:
            kq_embedding = self.embedding_service.encode(kq)
            if not kq_embedding:
                continue
            results = memory.state_manager.search_states_by_embedding(
                query_vector=kq_embedding, top_k=3
            )
            matched = [(s, sc) for s, sc in results if sc >= min_score]
            if matched:
                key_states_by_type[kq] = matched
                key_type_state_ids[kq] = {s.id for s, _ in matched}

        # Step 3: BFS reverse traversal from target states
        max_depth = self.max_depth
        seen_path_signatures: set = set()
        paths: List[Dict[str, Any]] = []

        key_type_count = len(key_queries)

        for target_state, target_score in target_states[:top_k]:
            all_paths = self._bfs_reverse_paths(target_state, max_depth, memory=memory)

            for path in all_paths[:5]:
                sig = tuple(s.id for s, _ in path)
                if sig in seen_path_signatures:
                    continue
                seen_path_signatures.add(sig)

                path_states = [s for s, _ in path]
                path_actions = [a for _, a in path if a is not None]
                path_state_ids = {s.id for s in path_states}

                # Score: target match + key type coverage
                end_state = path[-1][0]
                has_target = 1 if end_state.id in target_state_ids else 0

                types_hit = 0
                if key_type_count > 0:
                    for kq, sids in key_type_state_ids.items():
                        if path_state_ids & sids:
                            types_hit += 1
                key_coverage = types_hit / key_type_count if key_type_count > 0 else 0.0
                path_score = has_target * 1.0 * target_score + key_coverage * 0.3

                paths.append({
                    "score": round(path_score, 4),
                    "states": path_states,
                    "actions": path_actions,
                    "target_score": round(target_score, 4),
                    "key_types_hit": types_hit,
                    "key_types_total": key_type_count,
                })

        # Sort by score descending
        paths.sort(key=lambda x: -x["score"])
        paths = paths[:top_k * 2]

        for i, p in enumerate(paths[:3]):
            logger.info(f"[L2] Path {i}: score={p['score']}, states={len(p['states'])}, actions={len(p['actions'])}, state_ids={[s.id[:8] for s in p['states']]}")
        logger.info(f"[L2] Found {len(paths)} paths")

        if not paths:
            return None

        return {
            "target_query": target_query,
            "key_queries": key_queries,
            "paths": paths,
        }

    async def _select_best_path(
        self,
        target: str,
        private_result: Optional[Dict[str, Any]],
        public_result: Optional[Dict[str, Any]],
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """LLM selects the best path from private and public candidates.

        Args:
            target: User task description.
            private_result: Path result from private memory (or None).
            public_result: Path result from public memory (or None).

        Returns:
            (best_path_result, source) where source is "private" or "public".
        """
        if private_result and not public_result:
            return private_result, "private"
        if public_result and not private_result:
            return public_result, "public"
        if not private_result and not public_result:
            return None, "private"

        # Both have results — LLM picks the best
        priv_best = private_result["paths"][0]
        pub_best = public_result["paths"][0]

        def _format_path(path_dict: Dict) -> str:
            lines = []
            for i, state in enumerate(path_dict["states"], 1):
                desc = self._get_state_reasoning_text(state)
                url = state.page_url or ""
                lines.append(f"  {i}. {url} - {desc}")
            return "\n".join(lines)

        system_prompt = """You compare two navigation paths and pick the one that provides better NAVIGATION CONTEXT for the user's task.

IMPORTANT: These paths are NOT expected to complete the task directly. They serve as a "map" showing which pages and page transitions are relevant. The task will be decomposed into subtasks later using this path as context.

Evaluation criteria (in order of importance):
1. Structural coverage: Does the path cover the right types of pages the task needs (e.g., search page → results page → detail page)?
2. Path length: A multi-step path with meaningful transitions is more useful than isolated single-page results.
3. Domain relevance: Pages should be from the correct website/domain for the task.

Path A comes from the user's own browsing history (private memory).
Path B comes from community-shared workflows (public memory).
When both paths are equally good, prefer Path A (private) as it better reflects the user's habits.

Return JSON: {"choice": "A" or "B", "reasoning": "brief explanation"}"""

        prompt = f"""User task: {target}

Path A (private, {len(priv_best['states'])} steps):
{_format_path(priv_best)}

Path B (public, {len(pub_best['states'])} steps):
{_format_path(pub_best)}"""

        try:
            result = await self.llm_provider.generate_json_response(
                system_prompt=system_prompt,
                user_prompt=prompt,
            )
            choice = result.get("choice", "A").upper()
            if choice == "B":
                logger.info(f"[L2] LLM selected public path: {result.get('reasoning', '')[:100]}")
                return public_result, "public"
            else:
                logger.info(f"[L2] LLM selected private path: {result.get('reasoning', '')[:100]}")
                return private_result, "private"
        except Exception as exc:
            logger.warning(f"[L2] Path selection LLM failed, using higher score: {exc}")
            if pub_best["score"] > priv_best["score"]:
                return public_result, "public"
            return private_result, "private"

    async def _decompose_query_for_path(self, query: str) -> Dict[str, Any]:
        """Use LLM to decompose query into target_query + key_queries for embedding search."""
        system_prompt = """我有一个页面库，需要用 embedding 检索页面。用户描述了一个任务。

你的任务：为用户的目标页面和途经页面，分别生成检索语句。

返回 JSON：
{
    "target_query": "目标页面的检索语句",
    "key_queries": ["途经页面的检索语句"]
}

要求：
- target_query：描述用户最终要到达的页面，保留完整上下文（如网站名、产品名）
- key_queries：用户明确提到的途经页面，没提到就是空数组
- 检索语句要像页面的内容描述，不要用动作词（查看、点击等）
- 保持简洁，便于 embedding 匹配

示例：
用户: "通过 Product Hunt 周榜查看团队成员国籍"
输出: {"target_query": "Product Hunt 产品团队成员", "key_queries": ["Product Hunt 周榜"]}"""

        try:
            result = await self.llm_provider.generate_json_response(
                system_prompt=system_prompt,
                user_prompt=f"用户任务: {query}",
            )
            if "target_query" not in result:
                result["target_query"] = query
            if "key_queries" not in result:
                result["key_queries"] = []
            logger.info(f"[L2] Query decomposed: {result}")
            return result
        except Exception as e:
            logger.warning(f"[L2] Query decomposition failed: {e}")
            return {"target_query": query, "key_queries": []}

    def _bfs_reverse_paths(
        self, target_state: State, max_depth: int, max_paths: int = 10,
        memory: Optional[Memory] = None,
    ) -> List[List[tuple]]:
        """BFS reverse traversal from target state to find paths.

        Args:
            target_state: State to start reverse traversal from.
            max_depth: Maximum traversal depth.
            max_paths: Maximum number of paths to return.
            memory: Memory instance to use. Defaults to self.memory.

        Returns:
            List of paths, each path is [(state, action_to_next), ...]
            ending at target. The last element has action=None.
        """
        memory = memory or self.memory
        queue = [(target_state, [(target_state, None)], {target_state.id})]
        complete_paths: List[List[tuple]] = []

        while queue and len(complete_paths) < max_paths:
            current_state, path_so_far, visited = queue.pop(0)

            if len(path_so_far) > max_depth:
                complete_paths.append(path_so_far)
                continue

            incoming_actions = memory.state_manager.get_connected_actions(
                current_state.id, direction="incoming"
            )
            logger.info(f"[BFS] State {current_state.id[:8]}: {len(incoming_actions)} incoming actions")
            for a in incoming_actions[:3]:
                logger.info(f"[BFS]   action: source={a.source[:8] if a.source else 'None'}, target={a.target[:8] if a.target else 'None'}, type={getattr(a, 'action_type', '?')}")

            if not incoming_actions:
                complete_paths.append(path_so_far)
                continue

            has_valid_predecessor = False

            for action in incoming_actions:
                source_state = memory.get_state(action.source)
                if not source_state:
                    continue
                if source_state.id in visited:
                    continue

                has_valid_predecessor = True
                new_path = [(source_state, action)] + path_so_far
                new_visited = visited | {source_state.id}
                queue.append((source_state, new_path, new_visited))

            if not has_valid_predecessor:
                complete_paths.append(path_so_far)

        if not complete_paths:
            complete_paths = [[(target_state, None)]]

        return complete_paths

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
        query_vector = self.embedding_service.encode(target) if self.embedding_service else None

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
            query_vector = self.embedding_service.encode(state_ref)
            if query_vector is None:
                logger.error("[_resolve_state_id] encode() returned None")
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

