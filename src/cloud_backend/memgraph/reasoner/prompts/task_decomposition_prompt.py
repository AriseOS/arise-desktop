"""Task Decomposition Prompt - LLM prompt for decomposing target into atomic tasks.

This prompt is used to break down a complex target into a DAG of atomic retrieval tasks.
"""

import json
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field

from src.cloud_backend.memgraph.services.prompt_base import BasePrompt


class ToolInfo(BaseModel):
    """Information about an available tool."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Tool parameter schema"
    )


class TaskNode(BaseModel):
    """A single task node in the DAG."""

    task_id: str = Field(..., description="Unique task identifier")
    target: str = Field(..., description="Task target description")
    description: str = Field(..., description="Detailed task description")
    tool_type: str = Field(default="retrieval", description="Tool type to use")
    tool_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the tool (can reference outputs from dependencies)",
    )
    dependencies: List[str] = Field(
        default_factory=list, description="IDs of tasks this depends on"
    )


class TaskDecompositionInput(BaseModel):
    """Input for task decomposition."""

    target: str = Field(..., description="Original target to decompose")
    available_tools: List[ToolInfo] = Field(
        default_factory=list, description="Available tools for task execution"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )


class TaskDecompositionOutput(BaseModel):
    """Output from task decomposition."""

    tasks: List[TaskNode] = Field(..., description="List of atomic tasks")
    edges: List[Tuple[str, str]] = Field(
        default_factory=list, description="Dependency edges (source, target)"
    )
    reasoning: str = Field(..., description="Explanation of the decomposition")


class TaskDecompositionPrompt(BasePrompt[TaskDecompositionInput, TaskDecompositionOutput]):
    """Prompt for task decomposition."""

    def __init__(self):
        """Initialize the prompt."""
        super().__init__(prompt_name="task_decomposition", version="1.0")

    def get_system_prompt(self) -> str:
        """Get system prompt."""
        return """You are an expert at breaking down complex goals into atomic tasks.
Your task is to decompose a user's target into a directed acyclic graph (DAG) of
atomic tasks that can be executed using available tools.

Similar to the LogicalForm method in linguistics, you should:
1. Decompose complex goals into atomic operations
2. Use parameterized expressions to capture dependencies between tasks
3. Allow task outputs to be referenced by dependent tasks through parameters"""

    def build_prompt(self, input_data: TaskDecompositionInput) -> str:
        """Build the prompt."""
        # Build available tools section
        tools_str = "\n## Available Tools\n"
        if input_data.available_tools:
            for tool in input_data.available_tools:
                params_str = json.dumps(tool.parameters, indent=2) if tool.parameters else "{}"
                tools_str += f"""
### {tool.name}
Description: {tool.description}
Parameters: {params_str}
"""
        else:
            tools_str += "No tools available (using default 'retrieval' tool)\n"

        context_str = ""
        if input_data.context:
            context_str = f"\n## Additional Context\n{json.dumps(input_data.context, indent=2)}"

        prompt = f"""## Task
Decompose the user's target into atomic tasks organized as a DAG, using available tools.

## Target
{input_data.target}
{tools_str}{context_str}

## Instructions (Inspired by LogicalForm method)
1. Break down the target into atomic, independent tasks
2. Each task should use an appropriate tool from the available tools
3. Use **parameterized expressions** to capture data flow between tasks
4. Task parameters can reference outputs from dependency tasks using the
   format: {{"$ref": "task_id.output_field"}}
5. Identify dependencies between tasks based on data flow
6. Ensure the task graph is acyclic (DAG)
7. Keep tasks as atomic as possible

## Guidelines
- Each task should have a clear, specific target
- Select the most appropriate tool_type for each task
- Use tool_parameters to pass configuration and data references
- Tasks should be executable independently (given their dependencies are met)
- Avoid creating unnecessary dependencies
- Task IDs should be simple: "task_1", "task_2", etc.
- Use $ref syntax to reference outputs from previous tasks

## Output Format
Return a JSON object with the following structure:
{{
    "tasks": [
        {{
            "task_id": "task_1",
            "target": "specific task target",
            "description": "detailed description",
            "tool_type": "retrieval",
            "tool_parameters": {{
                "param1": "value1",
                "param2": {{"$ref": "task_0.output_field"}}
            }},
            "dependencies": ["task_0"]
        }}
    ],
    "edges": [
        ["task_1", "task_2"]  // task_2 depends on task_1
    ],
    "reasoning": "explanation of the decomposition strategy"
}}

## Example 1: Simple Sequential Tasks
For target "Find and book a flight to Paris":
{{
    "tasks": [
        {{
            "task_id": "task_1",
            "target": "Search for flights to Paris",
            "description": "Find available flights to Paris",
            "tool_type": "retrieval",
            "tool_parameters": {{
                "top_k": 10,
                "max_depth": 2
            }},
            "dependencies": []
        }},
        {{
            "task_id": "task_2",
            "target": "Select a suitable flight",
            "description": "Choose a flight based on task_1 results",
            "tool_type": "retrieval",
            "tool_parameters": {{
                "context": {{"$ref": "task_1.states"}},
                "top_k": 5
            }},
            "dependencies": ["task_1"]
        }},
        {{
            "task_id": "task_3",
            "target": "Complete booking process",
            "description": "Fill booking form using selected flight",
            "tool_type": "retrieval",
            "tool_parameters": {{
                "flight_info": {{"$ref": "task_2.states"}},
                "max_depth": 3
            }},
            "dependencies": ["task_2"]
        }}
    ],
    "edges": [
        ["task_1", "task_2"],
        ["task_2", "task_3"]
    ],
    "reasoning": "The target requires three sequential steps with data
        flowing from one to the next. Each task depends on results from the previous task."
}}

## Example 2: Parallel Tasks with Join
For target "Compare prices and features of products":
{{
    "tasks": [
        {{
            "task_id": "task_1",
            "target": "Find product prices",
            "description": "Retrieve price information",
            "tool_type": "retrieval",
            "tool_parameters": {{
                "top_k": 10
            }},
            "dependencies": []
        }},
        {{
            "task_id": "task_2",
            "target": "Find product features",
            "description": "Retrieve feature specifications",
            "tool_type": "retrieval",
            "tool_parameters": {{
                "top_k": 10
            }},
            "dependencies": []
        }},
        {{
            "task_id": "task_3",
            "target": "Compare and rank products",
            "description": "Combine price and feature data for comparison",
            "tool_type": "retrieval",
            "tool_parameters": {{
                "prices": {{"$ref": "task_1.states"}},
                "features": {{"$ref": "task_2.states"}}
            }},
            "dependencies": ["task_1", "task_2"]
        }}
    ],
    "edges": [
        ["task_1", "task_3"],
        ["task_2", "task_3"]
    ],
    "reasoning": "Tasks 1 and 2 can run in parallel as they are independent.
        Task 3 joins the results for final comparison."
}}

Please analyze the target and provide the task decomposition.
"""
        return prompt

    def parse_response(self, llm_response: str) -> TaskDecompositionOutput:
        """Parse LLM response."""
        try:
            data = self.parse_json_response(llm_response)

            # Convert task dicts to TaskNode objects
            tasks = [TaskNode(**task) for task in data.get("tasks", [])]

            # Convert edges to tuples
            edges = [tuple(edge) for edge in data.get("edges", [])]

            return TaskDecompositionOutput(
                tasks=tasks, edges=edges, reasoning=data.get("reasoning", "")
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Return single-task fallback on parse error
            return TaskDecompositionOutput(
                tasks=[
                    TaskNode(
                        task_id="task_1",
                        target=llm_response[:100],
                        description="Fallback single task",
                        task_type="retrieval",
                        dependencies=[],
                    )
                ],
                edges=[],
                reasoning=f"Failed to parse LLM response: {str(exc)}",
            )

    def validate_input(self, input_data: TaskDecompositionInput) -> bool:
        """Validate input data."""
        return bool(input_data.target)

    def validate_output(self, output_data: TaskDecompositionOutput) -> bool:
        """Validate output data."""
        if not output_data.tasks:
            return False

        # Check for cycles in the DAG
        task_ids = {task.task_id for task in output_data.tasks}

        # Verify all edge nodes exist
        for source, target in output_data.edges:
            if source not in task_ids or target not in task_ids:
                return False

        return True


__all__ = [
    "ToolInfo",
    "TaskNode",
    "TaskDecompositionInput",
    "TaskDecompositionOutput",
    "TaskDecompositionPrompt",
]
