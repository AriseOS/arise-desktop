"""State Generation Prompt - Prompt for generating semantic states from intents.

This prompt helps transform atomic intents into semantic states and transition edges.
"""

import json
from typing import Any, Dict, List, Tuple

from src.ontology.action import TransitionEdge
from src.ontology.intent import AtomicIntent
from src.ontology.state import SemanticState, SemanticStateType
from src.services.prompt_base import BasePrompt


class StateGenerationPrompt(BasePrompt[Dict[str, Any], Tuple[List[SemanticState], List[TransitionEdge]]]):
    """Prompt for generating semantic states and transition edges from atomic intents."""

    def __init__(self):
        """Initialize state generation prompt."""
        super().__init__("state_generator", "1.0")

    def build_prompt(self, input_data: Dict[str, Any]) -> str:
        """Build LLM prompt for state generation.

        Args:
            input_data: Dictionary containing 'atomic_intents' and optional 'context'

        Returns:
            Formatted prompt string
        """
        atomic_intents = input_data.get("atomic_intents", [])
        context = input_data.get("context")

        # Format intents
        intents_description = self._format_atomic_intents(atomic_intents)

        # Format context
        context_text = ""
        if context:
            context_text = f"\n\n## 额外上下文信息\n\n{json.dumps(context, ensure_ascii=False, indent=2)}"

        prompt = f'''你是一个专业的用户行为语义分析专家，擅长将原子意图聚合为高层语义状态。

你的任务是：分析原子意图序列，识别出语义状态（Semantic States）和状态转换边（Transition Edges）。

## 输入数据

{intents_description}{context_text}

## 语义状态类型定义

可用的语义状态类型：

### 浏览类（Browsing）
- **BrowseCatalog**: 浏览产品目录/分类
- **BrowseProduct**: 浏览单个产品
- **BrowseSearchResults**: 浏览搜索结果

### 信息提取类（Information Extraction）
- **InspectProductPrice**: 检查产品价格
- **InspectProductDetails**: 检查产品详情
- **ExtractProductInfo**: 提取产品信息

### 比较决策类（Comparison & Decision）
- **CompareProducts**: 比较多个产品
- **ComparePrices**: 比较价格
- **EvaluateOptions**: 评估选项

### 搜索类（Search）
- **SearchProducts**: 搜索产品
- **FilterResults**: 过滤结果
- **SortResults**: 排序结果

### 选择操作类（Selection & Action）
- **SelectProduct**: 选择产品
- **AddToCart**: 添加到购物车
- **AddToWishlist**: 添加到收藏夹

### 导航类（Navigation）
- **NavigateCategory**: 导航到分类
- **NavigateToPage**: 导航到页面
- **GoToHomepage**: 返回首页

### 其他类型
- **UNKNOWN**: 未知行为
- **LLM_GENERATED**: LLM生成的自定义类型

## 分析任务

请分析原子意图序列，识别出语义状态和状态转换：

### 1. 识别语义状态

将相关的原子意图聚合为一个语义状态。每个语义状态应该：
- 代表一个完整的用户行为意图
- 包含一批相关的原子意图
- 有明确的语义标签

### 2. 构建状态转换边

识别状态之间的转换关系：
- source: 源状态ID
- target: 目标状态ID
- type: 转换类型（user_action, navigation, automatic等）

## 输出格式

请严格按照以下JSON格式输出分析结果：

```json
{{
  "semantic_states": [
    {{
      "label": "SearchProducts",
      "type": "SearchProducts",
      "timestamp": 1234567890000,
      "end_timestamp": 1234567895000,
      "duration": 5000,
      "page_url": "https://example.com/search",
      "page_title": "Search Results",
      "user_id": "user123",
      "session_id": "session456",
      "goal_id": null,
      "atomic_intent_ids": ["intent_1", "intent_2", "intent_3"],
      "attributes": {{
        "query": "premium coffee",
        "result_count": 25
      }}
    }}
  ],
  "transition_edges": [
    {{
      "source_id": "state_0",
      "target_id": "state_1",
      "timestamp": 1234567896000,
      "type": "user_action",
      "duration": 1000,
      "user_id": "user123",
      "session_id": "session456",
      "confidence": 0.95,
      "attributes": {{
        "trigger": "click_product_link"
      }}
    }}
  ],
  "generation_metadata": {{
    "total_states": 1,
    "total_edges": 1,
    "state_type_distribution": {{"SearchProducts": 1}},
    "generation_method": "llm_semantic_analysis",
    "confidence_score": 0.92,
    "notes": "分析说明"
  }}
}}
```

## 注意事项

1. **聚合原则**：将语义相关的原子意图聚合为一个状态
2. **时序性**：保持状态的时间顺序
3. **完整性**：确保所有原子意图都被分配到某个状态
4. **语义性**：选择最合适的语义状态类型
5. **转换边**：明确标注状态之间的转换关系
6. **格式**：严格遵循JSON格式

请开始分析并输出结果。
'''
        return prompt

    def _format_atomic_intents(self, atomic_intents: List[AtomicIntent]) -> str:
        """Format atomic intents for prompt.

        Args:
            atomic_intents: List of AtomicIntent objects

        Returns:
            Formatted string
        """
        lines = []
        lines.append("### 原子意图序列")
        lines.append(f"总数: {len(atomic_intents)}")
        lines.append("")

        for i, intent in enumerate(atomic_intents, 1):
            lines.append(f"原子意图 #{i} (ID: {intent.id}):")
            lines.append(f"  类型: {intent.type.value}")
            lines.append(f"  时间戳: {intent.timestamp}")
            lines.append(f"  页面: {intent.page_url}")

            if intent.page_title:
                lines.append(f"  页面标题: {intent.page_title}")

            if intent.element_id:
                lines.append(f"  元素ID: {intent.element_id}")

            if intent.text:
                lines.append(f"  文本: {intent.text}")

            if intent.value:
                lines.append(f"  值: {intent.value}")

            lines.append("")

        return "\n".join(lines)

    def parse_response(
        self,
        llm_response: str
    ) -> Tuple[List[SemanticState], List[TransitionEdge], Dict[str, Any]]:
        """Parse LLM response to extract states, edges, and metadata.

        Args:
            llm_response: Raw LLM response

        Returns:
            Tuple of (states list, edges list, metadata dict)

        Raises:
            ValueError: If response cannot be parsed
        """
        # Parse JSON
        data = self.parse_json_response(llm_response)

        # Extract data
        states_data = data.get("semantic_states", [])
        edges_data = data.get("transition_edges", [])
        metadata = data.get("generation_metadata", {})

        # Note: States and edges creation requires intent_map and state_id_map
        # which are provided by the caller
        return states_data, edges_data, metadata

    def create_semantic_state(
        self,
        state_data: Dict[str, Any],
        intent_map: Dict[str, AtomicIntent]
    ) -> SemanticState:
        """Create SemanticState object from parsed data.

        Args:
            state_data: State data dictionary
            intent_map: Mapping from intent IDs to AtomicIntent objects

        Returns:
            SemanticState object

        Raises:
            ValueError: If state cannot be created
        """
        try:
            # Parse state type
            state_type_str = state_data.get("type")
            try:
                state_type = SemanticStateType(state_type_str)
            except ValueError:
                # If unknown type, use LLM_GENERATED
                state_type = SemanticStateType.LLM_GENERATED

            # Get associated atomic intents
            intent_ids = state_data.get("atomic_intent_ids", [])
            atomic_intents = [intent_map[iid] for iid in intent_ids if iid in intent_map]

            # Create SemanticState object
            state = SemanticState(
                label=state_data.get("label", "UnknownState"),
                type=state_type,
                timestamp=state_data.get("timestamp"),
                end_timestamp=state_data.get("end_timestamp"),
                duration=state_data.get("duration"),
                page_url=state_data.get("page_url"),
                page_title=state_data.get("page_title"),
                user_id=state_data.get("user_id"),
                session_id=state_data.get("session_id"),
                goal_id=state_data.get("goal_id"),
                attributes=state_data.get("attributes", {}),
                atomic_intents=atomic_intents
            )

            return state

        except Exception as e:
            raise ValueError(f"Failed to create semantic state: {str(e)}") from e

    def create_transition_edge(
        self,
        edge_data: Dict[str, Any],
        state_id_map: Dict[str, str]
    ) -> TransitionEdge:
        """Create TransitionEdge object from parsed data.

        Args:
            edge_data: Edge data dictionary
            state_id_map: Mapping from temporary IDs to real state IDs

        Returns:
            TransitionEdge object

        Raises:
            ValueError: If edge cannot be created
        """
        try:
            # Parse source and target IDs
            source_temp_id = edge_data.get("source_id")
            target_temp_id = edge_data.get("target_id")

            source_id = state_id_map.get(source_temp_id, source_temp_id)
            target_id = state_id_map.get(target_temp_id, target_temp_id)

            # Create TransitionEdge object
            edge = TransitionEdge(
                source=source_id,
                target=target_id,
                timestamp=edge_data.get("timestamp"),
                type=edge_data.get("type", "user_action"),
                duration=edge_data.get("duration"),
                user_id=edge_data.get("user_id"),
                session_id=edge_data.get("session_id"),
                confidence=edge_data.get("confidence", 1.0),
                attributes=edge_data.get("attributes", {})
            )

            return edge

        except Exception as e:
            raise ValueError(f"Failed to create transition edge: {str(e)}") from e

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input data.

        Args:
            input_data: Input dictionary

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(input_data, dict):
            return False

        atomic_intents = input_data.get("atomic_intents", [])
        if not atomic_intents or not isinstance(atomic_intents, list):
            return False

        return True

    def validate_output(
        self,
        output_data: Tuple[List[SemanticState], List[TransitionEdge]]
    ) -> bool:
        """Validate output data.

        Args:
            output_data: Tuple of (states list, edges list)

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(output_data, tuple) or len(output_data) != 2:
            return False

        states, _ = output_data
        if not states or not isinstance(states, list):
            return False

        for state in states:
            if not state.label or not state.timestamp:
                return False

        return True

    def get_system_prompt(self) -> str:
        """Get system prompt.

        Returns:
            System prompt string
        """
        return ("你是一个专业的用户行为语义分析专家，擅长将原子意图聚合为高层语义状态。"
                "请只输出有效的JSON格式。")


__all__ = ["StateGenerationPrompt"]