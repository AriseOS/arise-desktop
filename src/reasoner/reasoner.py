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
from typing import Dict, Optional

from src.memory.memory import Memory
from src.reasoner.cognitive_phrase_checker import CognitivePhraseChecker
from src.reasoner.prompts.task_decomposition_prompt import (
    TaskDecompositionInput,
    TaskDecompositionPrompt,
    ToolInfo,
)
from src.reasoner.retrieval_result import WorkflowResult
from src.reasoner.task_dag import TaskDAG
from src.reasoner.tools.retrieval_tool import RetrievalTool
from src.reasoner.tools.task_tool import TaskTool
from src.reasoner.workflow_converter import WorkflowConverter
from src.services.llm import LLMClient, LLMMessage


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
        llm_client: Optional[LLMClient] = None,
        embedding_service=None,
        max_depth: int = 3,
    ):
        """Initialize Reasoner.

        Args:
            memory: Memory instance.
            llm_client: LLM client for various LLM operations.
            embedding_service: Embedding service for vector search.
            max_depth: Maximum neighbor exploration depth.
        """
        self.memory = memory
        self.llm_client = llm_client
        self.embedding_service = embedding_service
        self.max_depth = max_depth

        # Initialize components
        self.phrase_checker = CognitivePhraseChecker(memory, llm_client)
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
            self.llm_client,
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

    def plan(self, target: str) -> WorkflowResult:
        """Plan and retrieve workflow for target.

        This is the main entry point.

        Args:
            target: Target description (natural language).

        Returns:
            WorkflowResult with workflow JSON if successful.
        """
        # Step 1: Check cognitive phrases
        can_satisfy, phrases, reasoning = self.phrase_checker.check(target)

        if can_satisfy and phrases:
            # Direct match found
            states = []
            actions = []
            for phrase in phrases:
                states.extend(phrase.states)
                actions.extend(phrase.actions)

            workflow = self.workflow_converter.convert(target, states, actions, phrases)

            return WorkflowResult(
                target=target,
                success=True,
                workflow=workflow,
                metadata={
                    "method": "cognitive_phrase_match",
                    "reasoning": reasoning,
                    "num_phrases": len(phrases),
                },
            )

        # Step 2: Decompose into TaskDAG
        dag = self._decompose_target(target)

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

            # Execute tool
            result = tool.execute(task_target, tool_parameters)

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
            metadata={
                "method": "task_dag",
                "num_tasks": len(topological_order),
                "dag_id": dag.dag_id,
            },
        )

    def _decompose_target(self, target: str) -> TaskDAG:
        """Decompose target into TaskDAG using LLM.

        Args:
            target: Target description.

        Returns:
            TaskDAG with atomic tasks.
        """
        if not self.llm_client:
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

            # Call LLM
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=prompt_text),
            ]

            response = self.llm_client.generate(messages=messages, temperature=0.1)

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
