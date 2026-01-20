"""Action Extraction Prompt - LLM prompt for extracting actions (state transitions).

This prompt is used to identify Actions that represent navigation events causing state transitions.
"""

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.cloud_backend.memgraph.services.prompt_base import BasePrompt


class ActionExtractionInput(BaseModel):
    """Input for action extraction."""

    states_summary: str = Field(..., description="Formatted summary of state sequence")


class ActionData(BaseModel):
    """Extracted action data."""

    source_index: int = Field(..., description="Index of source state (0-based)")
    target_index: int = Field(..., description="Index of target state (0-based)")
    type: str = Field(..., description="Action type (PascalCase, e.g., ClickLink)")
    timestamp: Optional[int] = Field(default=None, description="When transition occurred (milliseconds)")
    trigger_intent_id: Optional[str] = Field(
        default=None, description="ID of intent that triggered this action"
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict, description="Additional attributes"
    )


class ActionExtractionOutput(BaseModel):
    """Output from action extraction."""

    actions: List[ActionData] = Field(..., description="List of extracted actions")


class ActionExtractionPrompt(BasePrompt[ActionExtractionInput, ActionExtractionOutput]):
    """Prompt for action extraction from state sequences."""

    def __init__(self):
        """Initialize the prompt."""
        super().__init__(prompt_name="action_extraction", version="1.0")

    def get_system_prompt(self) -> str:
        """Get system prompt."""
        return """你是一个专业的状态转换分析专家，擅长识别用户在不同页面/状态之间的导航行为。
你需要准确识别哪些操作导致了页面跳转（状态转换），并构建状态转换图。
记住：Action必须连接两个不同的State，代表导致页面变化的导航操作。"""

    def build_prompt(self, input_data: ActionExtractionInput) -> str:
        """Build the prompt."""
        prompt = f'''分析以下State序列，识别导致页面跳转的Action（状态转换）。

## State序列
{input_data.states_summary}

## 任务要求

### 1. 识别Action（状态转换）
- **Action定义**：连接两个不同State的导航操作，代表页面跳转
- **Action特征**：
  - 连接源State（source）和目标State（target）
  - source和target必须是不同的State
  - 代表导致页面变化的操作（点击链接、提交表单、浏览器导航等）
  - 有明确的发生时间（通常是目标State的进入时间）

### 2. Action类型示例
- ClickLink: 点击链接跳转
- SubmitForm: 提交表单跳转
- NavigateBack: 浏览器后退
- NavigateForward: 浏览器前进
- RedirectAutomatic: 自动重定向
- OpenNewTab: 打开新标签页

### 3. 识别规则
- 按时间顺序分析State序列
- 相邻State之间通常存在Action
- 不相邻的State之间也可能存在Action（如标签页切换）
- 同一State不能有指向自己的Action

## 输出格式

请严格按照JSON数组格式输出：

```json
{{
  "actions": [
    {{
      "source_index": 0,
      "target_index": 1,
      "type": "ClickLink",
      "timestamp": 1000000005000,
      "trigger_intent_id": "intent_abc123",
      "attributes": {{
        "link_text": "查看详情",
        "navigation_type": "same_tab"
      }}
    }}
  ]
}}
```

## 字段说明
- **source_index**: 源State在序列中的索引（从0开始）
- **target_index**: 目标State在序列中的索引
- **type**: Action类型（参考上述类型示例）
- **timestamp**: 转换发生的时间（通常是target_state的timestamp）
- **trigger_intent_id**: 触发此转换的Intent ID（可选）
- **attributes**: 额外属性（可选）

## 注意事项

1. **必须不同**：source_index和target_index必须不同
2. **时序性**：Action的timestamp应该合理（在source和target的时间范围内）
3. **完整性**：识别所有可能的状态转换
4. **准确性**：type字段应准确描述转换类型
5. **格式**：严格遵循JSON格式

请开始分析并输出结果。
'''
        return prompt

    def parse_response(self, llm_response: str) -> ActionExtractionOutput:
        """Parse LLM response into structured output."""
        # Extract JSON from response
        start_idx = llm_response.find('{')
        end_idx = llm_response.rfind('}') + 1

        if start_idx == -1 or end_idx == 0:
            raise ValueError("No JSON found in LLM response")

        json_str = llm_response[start_idx:end_idx]
        data = json.loads(json_str)

        # Parse into Pydantic model
        return ActionExtractionOutput(**data)

    def validate_input(self, input_data: ActionExtractionInput) -> bool:
        """Validate input data."""
        return bool(input_data.states_summary)

    def validate_output(self, output_data: ActionExtractionOutput) -> bool:
        """Validate output data."""
        # Actions can be empty (no transitions), so this is always valid
        return True


__all__ = [
    "ActionExtractionPrompt",
    "ActionExtractionInput",
    "ActionExtractionOutput",
    "ActionData",
]
