"""Path-Based Decomposition Prompt - L3a prompt for decomposing target with navigation path context.

Given a task target and a known navigation path (sequence of pages),
this prompt asks the LLM to break the target into ordered subtasks
and map each subtask to relevant path pages.
"""

import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from src.cloud_backend.memgraph.services.prompt_base import BasePrompt


class PathDecompositionInput(BaseModel):
    """Input for path-based decomposition."""

    target: str = Field(..., description="Original task target")
    path_states: List[Dict[str, Any]] = Field(
        ..., description="Ordered path states with index, page_url, page_title, description"
    )
    path_actions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Actions connecting path states"
    )


class PathDecompositionOutput(BaseModel):
    """Output from path-based decomposition."""

    subtasks: List[Dict[str, Any]] = Field(..., description="Ordered subtasks")
    reasoning: str = Field(default="", description="Explanation")


class PathBasedDecompositionPrompt(BasePrompt[PathDecompositionInput, PathDecompositionOutput]):
    """Prompt for L3a: decompose target given a navigation path."""

    def __init__(self):
        super().__init__(prompt_name="path_based_decomposition", version="1.0")

    def get_system_prompt(self) -> str:
        return """你是一个任务分解专家。你有一个用户任务和一条已知的导航路径（页面序列）。

你的任务：
1. 将用户任务分解为有序的子任务
2. 为每个子任务标注它需要用到的路径页面（用索引）
3. 有些子任务可能不需要路径中的页面（索引为空）

要求：
- 子任务按执行顺序排列
- 每个子任务要简洁、可执行
- path_state_indices 引用路径页面的索引号"""

    def build_prompt(self, input_data: PathDecompositionInput) -> str:
        # Format path states
        path_desc = ""
        for i, s in enumerate(input_data.path_states):
            title = s.get("page_title", "")
            url = s.get("page_url", "")
            desc = s.get("description", "")
            path_desc += f"  [{i}] {title} ({url})\n"
            if desc:
                path_desc += f"      {desc}\n"

        return f"""## 用户任务
{input_data.target}

## 已知导航路径
{path_desc}
## 输出格式
返回 JSON：
{{
  "subtasks": [
    {{"task_id": "task_1", "target": "子任务描述", "path_state_indices": [0, 1]}},
    {{"task_id": "task_2", "target": "子任务描述", "path_state_indices": [2]}},
    {{"task_id": "task_3", "target": "子任务描述", "path_state_indices": []}}
  ],
  "reasoning": "分解理由"
}}"""

    def parse_response(self, llm_response: str) -> PathDecompositionOutput:
        try:
            data = self.parse_json_response(llm_response)
            return PathDecompositionOutput(
                subtasks=data.get("subtasks", []),
                reasoning=data.get("reasoning", ""),
            )
        except Exception as exc:
            return PathDecompositionOutput(
                subtasks=[{"task_id": "task_1", "target": llm_response[:200], "path_state_indices": []}],
                reasoning=f"Failed to parse: {exc}",
            )

    def validate_input(self, input_data: PathDecompositionInput) -> bool:
        return bool(input_data.target) and len(input_data.path_states) > 0

    def validate_output(self, output_data: PathDecompositionOutput) -> bool:
        return len(output_data.subtasks) > 0


__all__ = [
    "PathDecompositionInput",
    "PathDecompositionOutput",
    "PathBasedDecompositionPrompt",
]
