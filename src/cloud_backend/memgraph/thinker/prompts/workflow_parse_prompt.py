"""Workflow Parse Prompt - Parse and optimize workflow data.

This prompt analyzes raw workflow operation sequences and transforms them into
optimized, robust workflow JSON with intelligent waiting and selector optimization.
"""

import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from src.cloud_backend.memgraph.services.prompt_base import BasePrompt


class WorkflowParseInput(BaseModel):
    """Input for workflow parsing and optimization.

    Attributes:
        workflow_data: Raw workflow operation sequence (JSON string or dict).
    """

    workflow_data: str = Field(..., description="Raw workflow operation sequence")


class WorkflowParseOutput(BaseModel):
    """Output from workflow parsing.

    Attributes:
        business_intent: Core business intent summarized in one sentence.
        selector_optimization: Selector optimization recommendations.
        optimized_events: Optimized workflow events with smart waiting.
    """

    business_intent: str = Field(..., description="Core business intent")
    selector_optimization: Dict[str, Any] = Field(
        default_factory=dict, description="Selector optimization details"
    )
    optimized_events: List[Dict[str, Any]] = Field(
        ..., description="Optimized workflow events"
    )


class WorkflowParsePrompt(BasePrompt[WorkflowParseInput, WorkflowParseOutput]):
    """Prompt for parsing and optimizing workflow data."""

    def __init__(self):
        """Initialize the prompt."""
        super().__init__(prompt_name="workflow_parse", version="1.0")

    def get_system_prompt(self) -> str:
        """Get system prompt for workflow parsing.

        Returns:
            System prompt string.
        """
        return """你是一个专业的工作流分析和优化专家。你的任务是分析用户的操作序列，理解其核心业务意图，并生成优化的、健壮的工作流JSON。

你需要严格按照以下三步执行：

## 第一步：解析与抽象
分析操作序列，用**一句话**总结核心业务意图。
- 关注用户的最终目标，而不是具体的技术操作
- 使用业务语言描述（例如："用户登录后，在商品页将第一个商品加入购物车"）
- 保持简洁清晰，突出关键步骤

## 第二步：选择器优化
评估并建议最稳定、优先级的元素选择器策略。

**选择器优先级（从高到低）：**
1. `data-testid` - 最稳定，专门为测试设计
2. `role` + 文本内容 - 语义化，可访问性好
3. 语义化属性（`name`, `aria-label`, `placeholder`等）
4. CSS选择器（`id`, `class`）- 可能变化

**优化原则：**
- 为每个选择器评估稳定性
- 建议替代选择器（如果有更好的选项）
- 标记可能不稳定的选择器
- 考虑使用多重选择器策略作为后备

## 第三步：JSON生成
生成包含**智能等待、状态断言和必要容错**的完整JSON。

**增强功能：**
1. **智能等待**：
   - 在页面导航后添加等待（wait for networkidle）
   - 在交互操作前确保元素可见和可交互
   - 在动态内容加载时添加适当的等待

2. **状态断言**：
   - 验证关键操作的结果（例如：登录成功、商品已添加）
   - 检查页面状态（URL变化、元素出现/消失）
   - 确认数据正确性

3. **容错处理**：
   - 为不稳定的操作添加重试逻辑（通过timeout和wait_for）
   - 提供降级选择器
   - 处理可能的异常情况

**输出格式：**
每个event必须包含以下字段：
```json
{
  "action": "操作类型（navigate/click/type/wait/等）",
  "selector": "元素选择器（如果适用）",
  "value": "操作值（如果适用）",
  "url": "目标URL（如果是导航）",
  "wait_for": "等待条件（可选）",
  "timeout": 超时时间毫秒（可选）,
  "fallback_selectors": ["备用选择器1", "备用选择器2"],
  "validation": {
    "type": "验证类型",
    "condition": "验证条件"
  }
}
```

请严格使用JSON格式输出，不要添加任何前言、解释或代码块标记。"""

    def build_prompt(self, input_data: WorkflowParseInput) -> str:
        """Build the prompt for workflow parsing.

        Args:
            input_data: Input data containing raw workflow.

        Returns:
            Formatted prompt string.
        """
        prompt = f"""## 原始工作流数据

{input_data.workflow_data}

## 任务

请分析上述工作流操作序列，按照三步流程执行：

1. **解析与抽象**：用一句话总结核心业务意图
2. **选择器优化**：评估选择器稳定性并提供优化建议
3. **JSON生成**：生成包含智能等待、状态断言和容错的优化JSON

## 输出格式要求

请严格按照以下JSON格式输出（不要添加任何前言或解释）：

```json
{{
  "business_intent": "用一句话描述的核心业务意图",
  "selector_optimization": {{
    "评估的选择器": {{
      "stability": "稳定性评级（high/medium/low）",
      "current_priority": "当前优先级类型",
      "recommended": "推荐的选择器",
      "reasoning": "优化原因"
    }}
  }},
  "optimized_events": [
    {{
      "action": "操作类型",
      "selector": "优化后的选择器",
      "value": "操作值",
      "url": "URL",
      "wait_for": "等待条件",
      "timeout": 超时时间,
      "fallback_selectors": ["备用选择器"],
      "validation": {{
        "type": "验证类型",
        "condition": "验证条件"
      }}
    }}
  ]
}}
```

请立即输出JSON，不要添加任何其他文本。"""

        return prompt

    def parse_response(self, response: str) -> WorkflowParseOutput:
        """Parse LLM response into structured output.

        Args:
            response: Raw LLM response text.

        Returns:
            Parsed WorkflowParseOutput.

        Raises:
            ValueError: If response cannot be parsed.
        """
        try:
            # Remove markdown code blocks if present
            response = response.strip()
            if response.startswith('```'):
                # Extract content between ``` markers
                lines = response.split('\n')
                json_lines = []
                in_code_block = False
                for line in lines:
                    if line.strip().startswith('```'):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block or not line.strip().startswith('```'):
                        json_lines.append(line)
                response = '\n'.join(json_lines)

            # Parse JSON
            data = json.loads(response)

            if not isinstance(data, dict):
                raise ValueError("Response is not a JSON object")

            if 'business_intent' not in data:
                raise ValueError("Response missing 'business_intent' field")

            if 'optimized_events' not in data:
                raise ValueError("Response missing 'optimized_events' field")

            return WorkflowParseOutput(
                business_intent=data['business_intent'],
                selector_optimization=data.get('selector_optimization', {}),
                optimized_events=data['optimized_events']
            )

        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse response as JSON: {e}\nResponse: {response}")
        except Exception as e:
            raise ValueError(f"Error parsing response: {e}")

    def validate_input(self, input_data: WorkflowParseInput) -> bool:
        """Validate input data.

        Args:
            input_data: Input data to validate.

        Returns:
            True if input is valid, False otherwise.
        """
        if not isinstance(input_data, WorkflowParseInput):
            return False

        if not input_data.workflow_data:
            return False

        return True

    def validate_output(self, output_data: WorkflowParseOutput) -> bool:
        """Validate output data.

        Args:
            output_data: Output data to validate.

        Returns:
            True if output is valid, False otherwise.
        """
        if not isinstance(output_data, WorkflowParseOutput):
            return False

        if not output_data.business_intent:
            return False

        if not isinstance(output_data.optimized_events, list):
            return False

        if not output_data.optimized_events:
            return False

        # Validate each event has required fields
        for event in output_data.optimized_events:
            if not isinstance(event, dict):
                return False
            if 'action' not in event:
                return False

        return True


__all__ = [
    'WorkflowParsePrompt',
    'WorkflowParseInput',
    'WorkflowParseOutput',
]
