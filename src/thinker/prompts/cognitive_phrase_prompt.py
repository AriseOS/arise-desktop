"""Cognitive Phrase Prompt - Prompt for generating cognitive phrases."""

import json
from typing import Any, Dict, List

from src.ontology.action import Action
from src.ontology.cognitive_phrase import CognitivePhrase
from src.ontology.state import State
from src.services.prompt_base import BasePrompt


class CognitivePhrasePrompt(BasePrompt[Dict[str, Any], List[CognitivePhrase]]):
    """Prompt for generating cognitive phrases."""

    def __init__(self):
        """Initialize cognitive phrase prompt."""
        super().__init__("cognitive_phrase_generator", "1.0")

    def build_prompt(self, input_data: Dict[str, Any]) -> str:
        """Build LLM prompt for cognitive phrase generation.

        Args:
            input_data: Dictionary containing 'states' and 'actions'

        Returns:
            Formatted prompt string
        """
        states = input_data.get("states", [])
        actions = input_data.get("actions", [])

        # Format states
        states_text = self._format_states(states)

        # Format actions
        actions_text = self._format_actions(actions)

        prompt = f'''你是一个专业的认知行为分析专家，擅长从语义状态和动作序列中提炼出高层次的认知短语（Cognitive Phrases）。

你的任务是：分析给定的语义状态（States）和动作（Actions），识别并生成代表完整用户任务或目标的认知短语。

## 输入数据

### 语义状态（States）

{states_text}

### 动作（Actions）

{actions_text}

## 认知短语（Cognitive Phrase）定义

认知短语是对用户完整任务或目标的高层次抽象，它：

1. **整合多个状态**：将相关的语义状态组合成一个有意义的任务
2. **表达用户意图**：清晰描述用户想要完成什么
3. **具有时序性**：有明确的开始和结束时间
4. **语义完整**：代表一个完整的认知过程或决策流程

## 识别原则

### 1. 任务边界识别
- **开始标志**：新的搜索、导航到新页面、开始新的交互流程
- **结束标志**：完成购买、退出页面、任务目标达成

### 2. 语义聚合规则
- 将目标一致的状态聚合为一个短语
- 考虑用户的潜在意图和动机
- 识别任务的层次结构

### 3. 典型认知短语类型
- **信息查找**：搜索并浏览相关信息
- **商品选购**：浏览、比较、选择商品
- **决策制定**：评估选项、比较价格、做出决定
- **任务执行**：完成购买、提交表单、操作执行

## 输出格式

请严格按照以下JSON格式输出认知短语：

```json
{{
  "cognitive_phrases": [
    {{
      "label": "搜索并比较咖啡产品",
      "description": "用户搜索premium coffee关键词，浏览搜索结果，并比较多个产品的价格和详情",
      "start_timestamp": 1234567890000,
      "end_timestamp": 1234567900000,
      "duration": 10000,
      "user_id": "user123",
      "session_id": "session456",
      "goal_id": "find_premium_coffee",
      "goal_description": "找到性价比高的优质咖啡产品",
      "state_ids": ["state_1", "state_2", "state_3"],
      "attributes": {{
        "task_type": "product_search_and_compare",
        "domain": "e-commerce",
        "complexity": "medium",
        "completion_status": "completed"
      }}
    }},
    {{
      "label": "评估并选择目标产品",
      "description": "用户仔细评估选中的产品详情，检查价格和评论，最终将产品添加到购物车",
      "start_timestamp": 1234567901000,
      "end_timestamp": 1234567910000,
      "user_id": "user123",
      "session_id": "session456",
      "state_ids": ["state_4", "state_5"],
      "attributes": {{
        "task_type": "product_evaluation_and_selection",
        "decision_made": true
      }}
    }}
  ],
  "metadata": {{
    "total_phrases": 2,
    "phrase_types": ["product_search_and_compare", "product_evaluation_and_selection"],
    "generation_method": "llm_cognitive_analysis",
    "confidence_score": 0.92,
    "notes": "用户执行了完整的商品搜索和购买决策流程"
  }}
}}
```

## 注意事项

1. **语义完整性**：每个认知短语应代表一个完整的认知任务
2. **层次性**：识别任务的层次结构，区分主任务和子任务
3. **时序性**：确保短语的时间范围准确反映任务执行过程
4. **关联性**：正确关联相关的状态ID
5. **描述性**：label简洁，description详细
6. **格式**：严格遵循JSON格式

请开始分析并输出认知短语。
'''
        return prompt

    def _format_states(self, states: List[State]) -> str:
        """Format states for prompt.

        Args:
            states: List of State objects

        Returns:
            Formatted string
        """
        if not states:
            return "无"

        lines = []
        for i, state in enumerate(states, 1):
            lines.append(f"State #{i} (ID: {state.id}):")
            lines.append(f"  标签: {state.label}")
            lines.append(f"  类型: {state.type.value}")
            lines.append(f"  时间戳: {state.timestamp}")
            lines.append(f"  页面: {state.page_url}")

            if state.attributes:
                lines.append(f"  属性: {json.dumps(state.attributes, ensure_ascii=False)}")

            lines.append("")

        return "\n".join(lines)

    def _format_actions(self, actions: List[Action]) -> str:
        """Format actions for prompt.

        Args:
            actions: List of Action objects

        Returns:
            Formatted string
        """
        if not actions:
            return "无"

        lines = []
        for i, action in enumerate(actions, 1):
            lines.append(f"Action #{i}:")
            lines.append(f"  源状态: {action.source}")
            lines.append(f"  目标状态: {action.target}")
            lines.append(f"  类型: {action.type}")

            if action.timestamp:
                lines.append(f"  时间戳: {action.timestamp}")

            if action.attributes:
                lines.append(f"  属性: {json.dumps(action.attributes, ensure_ascii=False)}")

            lines.append("")

        return "\n".join(lines)

    def parse_response(self, llm_response: str) -> List[CognitivePhrase]:
        """Parse LLM response to CognitivePhrase list.

        Args:
            llm_response: LLM response string

        Returns:
            List of CognitivePhrase objects

        Raises:
            ValueError: If response cannot be parsed
        """
        # Parse JSON
        data = self.parse_json_response(llm_response)

        phrases_data = data.get("cognitive_phrases", [])

        phrases = []
        for phrase_data in phrases_data:
            phrase = CognitivePhrase(
                label=phrase_data.get("label", "Unknown Task"),
                description=phrase_data.get("description"),
                start_timestamp=phrase_data.get("start_timestamp"),
                end_timestamp=phrase_data.get("end_timestamp"),
                duration=phrase_data.get("duration"),
                user_id=phrase_data.get("user_id"),
                session_id=phrase_data.get("session_id"),
                goal_id=phrase_data.get("goal_id"),
                goal_description=phrase_data.get("goal_description"),
                state_ids=phrase_data.get("state_ids", []),
                attributes=phrase_data.get("attributes", {}),
                llm_generated=True
            )
            phrases.append(phrase)

        return phrases

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input data.

        Args:
            input_data: Input dictionary

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(input_data, dict):
            return False

        states = input_data.get("states", [])
        if not states or not isinstance(states, list):
            return False

        return True

    def validate_output(self, output_data: List[CognitivePhrase]) -> bool:
        """Validate output phrases.

        Args:
            output_data: List of CognitivePhrase objects

        Returns:
            True if valid, False otherwise
        """
        if not output_data:
            return False

        for phrase in output_data:
            if not phrase.label or not phrase.start_timestamp:
                return False

        return True

    def get_system_prompt(self) -> str:
        """Get system prompt.

        Returns:
            System prompt string
        """
        return "你是一个专业的认知行为分析专家，擅长从语义状态和动作中提炼认知短语。请只输出有效的JSON格式。"


__all__ = ["CognitivePhrasePrompt"]