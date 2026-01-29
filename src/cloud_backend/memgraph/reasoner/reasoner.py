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

import logging
import uuid
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

from src.cloud_backend.memgraph.memory.memory import Memory
from src.cloud_backend.memgraph.ontology.action import Action
from src.cloud_backend.memgraph.ontology.intent_sequence import IntentSequence
from src.cloud_backend.memgraph.ontology.query_result import QueryResult, SubTaskResult
from src.cloud_backend.memgraph.ontology.state import State
from src.cloud_backend.memgraph.reasoner.cognitive_phrase_checker import CognitivePhraseChecker
from src.cloud_backend.memgraph.reasoner.prompts.path_based_decomposition_prompt import (
    PathBasedDecompositionPrompt,
    PathDecompositionInput,
)
from src.cloud_backend.memgraph.reasoner.prompts.task_decomposition_prompt import (
    TaskDecompositionInput,
    TaskDecompositionPrompt,
    ToolInfo,
)
from src.cloud_backend.memgraph.reasoner.retrieval_result import WorkflowResult
from src.cloud_backend.memgraph.reasoner.task_dag import TaskDAG
from src.cloud_backend.memgraph.reasoner.tools.retrieval_tool import RetrievalTool
from src.cloud_backend.memgraph.reasoner.tools.task_tool import TaskTool
from src.cloud_backend.memgraph.reasoner.workflow_converter import WorkflowConverter
from src.cloud_backend.memgraph.services.embedding_service import EmbeddingService


class Reasoner:
    """Main reasoner for workflow retrieval.

    The Reasoner orchestrates the entire retrieval process:
    1. Check cognitive_phrases
    2. Decompose into TaskDAG if needed
    3. Execute tasks in topological order using registered tools
    4. Convert results to workflow
    """

    def __init__(
        self,
        memory: Memory,
        llm_provider: Optional[Any] = None,
        embedding_service=None,
        max_depth: int = 3,
    ):
        """Initialize Reasoner.

        Args:
            memory: Memory instance.
            llm_provider: LLM provider (AnthropicProvider) for various LLM operations.
            embedding_service: Embedding service for vector search.
            max_depth: Maximum neighbor exploration depth.
        """
        self.memory = memory
        self.llm_provider = llm_provider
        self.embedding_service = embedding_service
        self.max_depth = max_depth

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
                print(f"Warning: State '{state_id}' not found in memory")

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
                print(f"Warning: Action from '{source_id}' to '{target_id}' not found")

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

        # Convert to workflow
        workflow = self.workflow_converter.convert(
            phrase.description,
            states,
            actions,
            [phrase]
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
        self, target: str, user_id: Optional[str] = None, session_id: Optional[str] = None
    ) -> WorkflowResult:
        """Plan and retrieve workflow for target.

        This is the main entry point.

        Args:
            target: Target description (natural language).
            user_id: Optional user ID for filtering (not yet implemented).
            session_id: Optional session ID for filtering (not yet implemented).

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
                            print(f"Warning: State '{state_id}' not found in phrase {phrase.id}")

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
                            print(f"Warning: Action from '{source_id}' to '{target_id}' not found in phrase {phrase.id}")

            # Convert back to lists
            states = list(states_by_id.values())
            actions = list(actions_by_key.values())

            if not states:
                # No valid states found, fall back to task decomposition
                print("Warning: No valid states found in cognitive phrases, falling back to task decomposition")
            else:
                workflow = self.workflow_converter.convert(target, states, actions, phrases)

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
        workflow = self.workflow_converter.convert(target, all_states, all_actions) if has_results else None

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

            # Print raw LLM response for debugging
            print("\n" + "=" * 80)
            print("TASK DECOMPOSITION - RAW LLM RESPONSE:")
            print("=" * 80)
            print(response)
            print("=" * 80 + "\n")

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
            print(f"LLM task decomposition failed: {exc}")
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
        can_satisfy, phrases, reasoning = await self.phrase_checker.check(target)

        if can_satisfy and phrases:
            best_phrase = phrases[0]

            states = []
            for state_id in best_phrase.state_path:
                state = self.memory.get_state(state_id)
                if state:
                    states.append(state)

            actions = []
            for i in range(len(best_phrase.state_path) - 1):
                source_id = best_phrase.state_path[i]
                target_id = best_phrase.state_path[i + 1]
                action = self.memory.get_action(source_id, target_id)
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
                },
            )

        # === L2: Path retrieval ===
        path_result = await self._find_navigation_path(target)

        # === L3: Task decomposition ===
        if path_result and path_result["paths"]:
            best_path = path_result["paths"][0]
            subtasks = await self._decompose_with_path(target, best_path)
        else:
            subtasks = await self._decompose_without_path(target)

        # Collect states/actions from subtasks that have navigation info
        all_states: List[State] = []
        all_actions: List[Action] = []
        for st in subtasks:
            if st.found:
                all_states.extend(st.states)
                all_actions.extend(st.actions)

        has_results = len(all_states) > 0
        method = "path_decomposition" if (path_result and path_result["paths"]) else "direct_decomposition"

        if has_results:
            return QueryResult.task_success(
                states=all_states,
                actions=all_actions,
                subtasks=subtasks,
                metadata={"method": method},
            )
        else:
            return QueryResult(
                query_type="task",
                success=False,
                subtasks=subtasks,
                metadata={"method": method, "error": "No navigation info found"},
            )

    async def _find_navigation_path(
        self, target: str, top_k: int = 10, min_score: float = 0.3
    ) -> Optional[Dict[str, Any]]:
        """L2: Find navigation path using embedding search + BFS reverse traversal.

        Args:
            target: Task target description.
            top_k: Number of top results.
            min_score: Minimum embedding similarity score.

        Returns:
            Dict with target_query, key_queries, and paths (sorted by score),
            or None if no paths found.
        """
        if not self.llm_provider or not self.embedding_service:
            return None

        try:
            # Step 1: LLM query decomposition
            decomposed = await self._decompose_query_for_path(target)
            target_query = decomposed.get("target_query", target)
            key_queries = decomposed.get("key_queries", [])

            # Step 2: Embedding search for target states
            target_states: List[tuple] = []
            target_state_ids: set = set()
            tq_embedding = self.embedding_service.encode(target_query)
            if tq_embedding:
                results = self.memory.state_manager.search_states_by_embedding(
                    query_vector=tq_embedding, top_k=top_k
                )
                for state, score in results:
                    if score >= min_score:
                        target_states.append((state, score))
                        target_state_ids.add(state.id)

            logger.info(f"[L2] Target states for '{target_query}': {len(target_states)}")

            if not target_states:
                return None

            # Step 3: Embedding search for key states
            key_states_by_type: Dict[str, List[tuple]] = {}
            key_type_state_ids: Dict[str, set] = {}
            for kq in key_queries:
                kq_embedding = self.embedding_service.encode(kq)
                if not kq_embedding:
                    continue
                results = self.memory.state_manager.search_states_by_embedding(
                    query_vector=kq_embedding, top_k=3
                )
                matched = [(s, sc) for s, sc in results if sc >= min_score]
                if matched:
                    key_states_by_type[kq] = matched
                    key_type_state_ids[kq] = {s.id for s, _ in matched}

            # Step 4: BFS reverse traversal from target states
            max_depth = self.max_depth
            seen_path_signatures: set = set()
            paths: List[Dict[str, Any]] = []

            key_type_count = len(key_queries)

            for target_state, target_score in target_states[:top_k]:
                all_paths = self._bfs_reverse_paths(target_state, max_depth)

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

        except Exception as exc:
            logger.error(f"[L2] Path retrieval failed: {exc}")
            import traceback
            traceback.print_exc()
            return None

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
        self, target_state: State, max_depth: int, max_paths: int = 10
    ) -> List[List[tuple]]:
        """BFS reverse traversal from target state to find paths.

        Returns list of paths, each path is [(state, action_to_next), ...]
        ending at target. The last element has action=None.
        """
        queue = [(target_state, [(target_state, None)], {target_state.id})]
        complete_paths: List[List[tuple]] = []

        while queue and len(complete_paths) < max_paths:
            current_state, path_so_far, visited = queue.pop(0)

            if len(path_so_far) > max_depth:
                complete_paths.append(path_so_far)
                continue

            incoming_actions = self.memory.state_manager.get_connected_actions(
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
                source_state = self.memory.get_state(action.source)
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
        path_actions: List[Action] = path["actions"]

        # Build input for prompt
        path_state_dicts = []
        for i, state in enumerate(path_states):
            path_state_dicts.append({
                "index": i,
                "page_url": state.page_url or "",
                "page_title": state.page_title or "",
                "description": state.description or "",
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
                # Every subtask carries the full path as navigation context.
                # path_state_indices only marks where on the path this subtask operates.
                subtasks.append(SubTaskResult(
                    task_id=st_data.get("task_id", f"task_{len(subtasks)+1}"),
                    target=st_data.get("target", ""),
                    states=path_states,
                    actions=path_actions,
                    found=len(indices) > 0,
                ))

            return subtasks

        except Exception as exc:
            logger.error(f"[L3a] Path decomposition failed: {exc}")
            # Fallback: single subtask with all path data
            return [SubTaskResult(
                task_id="task_1",
                target=target,
                states=path_states,
                actions=path_actions,
                found=True,
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
                    states=[],
                    actions=[],
                    found=False,
                ))

            return subtasks

        except Exception as exc:
            logger.error(f"[L3b] Decomposition failed: {exc}")
            return [SubTaskResult(
                task_id="task_1",
                target=target,
                states=[],
                actions=[],
                found=False,
            )]

    async def _query_navigation(
        self,
        target: str,
        start_state: str,
        end_state: str,
    ) -> QueryResult:
        """Execute navigation-level query (v2).

        Finds the shortest path between two states. Both start_state and end_state
        can be either exact state IDs or semantic descriptions (will use embedding
        search to resolve).

        Args:
            target: Optional target description (unused, kept for interface consistency).
            start_state: Start state ID or description.
            end_state: End state ID or description.

        Returns:
            QueryResult with navigation path.
        """
        # Resolve state IDs (supports both exact ID and semantic description)
        start_id = await self._resolve_state_id(start_state)
        end_id = await self._resolve_state_id(end_state)

        if not start_id:
            return QueryResult.navigation_failure(
                error=f"Could not find start state: {start_state}",
            )

        if not end_id:
            return QueryResult.navigation_failure(
                error=f"Could not find end state: {end_state}",
            )

        # Find shortest path
        path_result = self.memory.action_manager.find_shortest_path(
            source_id=start_id,
            target_id=end_id,
            state_manager=self.memory.state_manager,
        )

        if path_result is None:
            return QueryResult.navigation_failure(
                error=f"No path found from {start_state} to {end_state}",
            )

        states, actions = path_result
        return QueryResult.navigation_success(
            states=states,
            actions=actions,
            metadata={
                "start_state_id": start_id,
                "end_state_id": end_id,
            },
        )

    async def _query_action(
        self,
        target: str,
        current_state: str,
        top_k: int = 10,
    ) -> QueryResult:
        """Execute action-level query (v2).

        Finds available actions in the current state.

        Args:
            target: Action description to search for.
            current_state: Current state ID.
            top_k: Number of top results to return.

        Returns:
            QueryResult with matching IntentSequences.
        """
        # If target is empty, return exploration result (all possible actions)
        if not target.strip():
            return await self._get_page_capabilities(current_state)

        # Search IntentSequences by embedding
        if not self.memory.intent_sequence_manager:
            return QueryResult.action_failure(
                error="IntentSequenceManager not available",
            )

        if self.embedding_service:
            try:
                query_vector = self.embedding_service.encode(target)
                results = self.memory.intent_sequence_manager.search_by_embedding(
                    query_vector=query_vector,
                    state_id=current_state,
                    top_k=top_k,
                )

                if results:
                    sequences = [seq for seq, _ in results]
                    return QueryResult.action_success(
                        intent_sequences=sequences,
                        metadata={
                            "method": "embedding_search",
                            "state_id": current_state,
                            "num_results": len(sequences),
                        },
                    )
            except Exception as e:
                print(f"Embedding search failed: {e}")

        # Fallback: list all sequences for the state
        sequences = self.memory.intent_sequence_manager.list_by_state(current_state)

        if sequences:
            return QueryResult.action_success(
                intent_sequences=sequences,
                metadata={
                    "method": "list_by_state",
                    "state_id": current_state,
                },
            )

        return QueryResult.action_failure(
            error=f"No actions found in state: {current_state}",
        )

    async def _get_page_capabilities(self, state_id: str) -> QueryResult:
        """Get all available actions/navigations for a state (exploration query).

        Args:
            state_id: State ID to explore.

        Returns:
            QueryResult with all available actions.
        """
        sequences: List[IntentSequence] = []
        if self.memory.intent_sequence_manager:
            sequences = self.memory.intent_sequence_manager.list_by_state(state_id)

        outgoing_actions = self.memory.action_manager.list_outgoing_actions(state_id)

        return QueryResult(
            query_type="action",
            success=True,
            intent_sequences=sequences,
            actions=outgoing_actions,
            metadata={
                "method": "exploration",
                "state_id": state_id,
                "num_sequences": len(sequences),
                "num_outgoing_actions": len(outgoing_actions),
            },
        )

    async def _resolve_state_id(
        self,
        state_ref: str,
    ) -> Optional[str]:
        """Resolve a state reference (ID or description) to an actual state ID.

        Args:
            state_ref: State ID or description.

        Returns:
            State ID if found, None otherwise.
        """
        print(f"[_resolve_state_id] Resolving state_ref: '{state_ref}'")

        # First, try direct ID lookup
        state = self.memory.get_state(state_ref)
        if state:
            print(f"[_resolve_state_id] Direct lookup found: {state.id}")
            return state.id

        print(f"[_resolve_state_id] Direct lookup failed, trying embedding search...")

        # Try embedding search if available
        if not self.embedding_service:
            print("[_resolve_state_id] ERROR: embedding_service is None!")
            return None

        try:
            print(f"[_resolve_state_id] Encoding query: '{state_ref}'")
            query_vector = self.embedding_service.encode(state_ref)
            print(f"[_resolve_state_id] Got vector of length: {len(query_vector) if query_vector else 'None'}")

            if query_vector is None:
                print("[_resolve_state_id] ERROR: encode() returned None")
                return None

            print(f"[_resolve_state_id] Calling search_states_by_embedding...")
            results = self.memory.state_manager.search_states_by_embedding(
                query_vector, top_k=1
            )
            print(f"[_resolve_state_id] Search returned {len(results) if results else 0} results")

            if results:
                # results may be List[State] or List[Tuple[State, float]]
                first_result = results[0]
                if isinstance(first_result, tuple):
                    state_obj, score = first_result
                    print(f"[_resolve_state_id] Found state: {state_obj.id} (score={score})")
                    return state_obj.id
                else:
                    print(f"[_resolve_state_id] Found state: {first_result.id}")
                    return first_result.id
            else:
                print("[_resolve_state_id] No embedding search results")

        except Exception as e:
            import traceback
            print(f"[_resolve_state_id] State embedding search failed: {e}")
            print(f"[_resolve_state_id] Traceback: {traceback.format_exc()}")

        return None


__all__ = ["Reasoner"]

