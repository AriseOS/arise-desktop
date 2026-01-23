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

import uuid
from typing import Any, Dict, Optional

from src.cloud_backend.memgraph.memory.memory import Memory
from src.cloud_backend.memgraph.reasoner.cognitive_phrase_checker import CognitivePhraseChecker
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

        for task_id in topological_order:
            task_node = dag.nodes[task_id]
            task_target = task_node.get("target", task_node.get("description", ""))
            tool_type = dag.get_tool_type(task_id)
            tool_parameters = dag.get_tool_parameters(task_id)

            # Get tool from registry
            tool = self.get_tool(tool_type)
            if not tool:
                return WorkflowResult(
                    target=target,
                    success=False,
                    metadata={
                        "method": "task_dag",
                        "failed_task_id": task_id,
                        "error": f"Tool '{tool_type}' not found in registry",
                    },
                )

            # Execute tool (async)
            result = await tool.execute(task_target, tool_parameters)

            if not result.success:
                return WorkflowResult(
                    target=target,
                    success=False,
                    metadata={
                        "method": "task_dag",
                        "failed_task_id": task_id,
                        "reasoning": result.reasoning,
                    },
                )

            all_states.extend(result.states)
            all_actions.extend(result.actions)

        # Step 4: Convert to workflow
        workflow = self.workflow_converter.convert(target, all_states, all_actions)

        return WorkflowResult(
            target=target,
            success=True,
            workflow=workflow,
            states=all_states,
            actions=all_actions,
            metadata={
                "method": "task_dag",
                "num_tasks": len(topological_order),
                "num_states": len(all_states),
                "num_actions": len(all_actions),
                "dag_id": dag.dag_id,
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


__all__ = ["Reasoner"]
