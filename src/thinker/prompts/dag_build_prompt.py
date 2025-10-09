"""DAG Build Prompt - Prompt for building Intent DAG."""

from typing import List

from src.ontology.intent import Intent
from src.services.prompt_base import BasePrompt
from src.thinker.intent_dag_builder import IntentDAG


class DAGBuildPrompt(BasePrompt[List[Intent], IntentDAG]):
    """Prompt for building Intent DAG from Intent list."""

    def __init__(self):
        """Initialize DAG build prompt."""
        super().__init__("intent_dag_builder", "1.0")

    def build_prompt(self, input_data: List[Intent]) -> str:
        """Build LLM prompt for DAG construction.

        Args:
            input_data: List of Intent objects

        Returns:
            Formatted prompt string
        """
        # Format intents
        intents_text = self._format_intents(input_data)

        prompt = f'''你是一个专业的用户行为分析专家，擅长使用语言学中的Logical Form方法分析意图序列之间的依赖关系。

你的任务是：分析给定的原子意图（Intent）序列，构建一个有向无环图（DAG），表示意图之间的依赖和因果关系。

## 输入数据

{intents_text}

## Logical Form 分析方法

使用语言学的Logical Form方法，分析意图之间的逻辑关系：

1. **时序关系（Temporal）**：A 在 B 之前发生
2. **因果关系（Causal）**：A 导致 B 发生
3. **条件关系（Conditional）**：A 是 B 的前提条件
4. **并行关系（Parallel）**：A 和 B 可以同时进行
5. **从属关系（Subordinate）**：A 从属于 B

## DAG 构建规则

1. **节点（Node）**：每个Intent作为一个节点
2. **边（Edge）**：意图之间存在依赖关系时建立边
3. **无环性**：确保图中不存在环路
4. **传递性**：考虑间接依赖关系

## 边的类型（Edge Types）

- `temporal`: 时序关系
- `causal`: 因果关系
- `conditional`: 条件关系
- `parallel`: 并行关系
- `subordinate`: 从属关系

## 输出格式

请严格按照以下JSON格式输出DAG结构：

```json
{{
  "edges": [
    {{
      "source_id": "intent_1_id",
      "target_id": "intent_2_id",
      "edge_type": "causal",
      "properties": {{
        "strength": 0.95,
        "reason": "用户输入搜索词后点击搜索按钮，存在明显的因果关系"
      }}
    }},
    {{
      "source_id": "intent_2_id",
      "target_id": "intent_3_id",
      "edge_type": "temporal",
      "properties": {{
        "strength": 0.85,
        "reason": "浏览搜索结果在点击产品链接之前"
      }}
    }}
  ],
  "metadata": {{
    "total_edges": 2,
    "edge_type_distribution": {{
      "causal": 1,
      "temporal": 1
    }},
    "analysis_method": "logical_form",
    "confidence_score": 0.90,
    "notes": "用户执行搜索流程，意图之间存在清晰的因果和时序关系"
  }}
}}
```

## 注意事项

1. **准确性**：仔细分析每对意图之间的关系
2. **完整性**：识别所有重要的依赖关系
3. **简洁性**：避免冗余的边（传递闭包）
4. **逻辑性**：确保DAG结构符合逻辑和时序规则
5. **格式**：严格遵循JSON格式

请开始分析并输出DAG结构。
'''
        return prompt

    def _format_intents(self, intents: List[Intent]) -> str:
        """Format intents for prompt.

        Args:
            intents: List of Intent objects

        Returns:
            Formatted string representation
        """
        lines = []
        lines.append("### 原子意图列表")
        lines.append(f"总数: {len(intents)}")
        lines.append("")

        for i, intent in enumerate(intents, 1):
            lines.append(f"Intent #{i} (ID: {intent.id}):")
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

    def parse_response(self, llm_response: str) -> IntentDAG:
        """Parse LLM response to IntentDAG.

        Args:
            llm_response: LLM response string

        Returns:
            IntentDAG object

        Raises:
            NotImplementedError: This method should not be called directly
        """
        # This method should not be called directly
        # Use IntentDAGBuilder.build_dag instead
        raise NotImplementedError("Use IntentDAGBuilder.build_dag instead")

    def validate_input(self, input_data: List[Intent]) -> bool:
        """Validate input intents.

        Args:
            input_data: List of Intent objects

        Returns:
            True if valid, False otherwise
        """
        if not input_data:
            return False

        # Check all intents have IDs
        for intent in input_data:
            if not hasattr(intent, 'id') or not intent.id:
                return False

        return True

    def validate_output(self, output_data: IntentDAG) -> bool:
        """Validate output DAG.

        Args:
            output_data: IntentDAG object

        Returns:
            True if valid, False otherwise
        """
        # Check basic structure
        if not output_data.intents or not isinstance(output_data.edges, list):
            return False

        # Check for cycles using topological sort
        return self._check_acyclic(output_data)

    def _check_acyclic(self, dag: IntentDAG) -> bool:
        """Check if DAG is acyclic.

        Args:
            dag: IntentDAG object

        Returns:
            True if acyclic, False otherwise
        """
        # Build adjacency list
        adj = {}
        for source, target, _, _ in dag.edges:
            if source not in adj:
                adj[source] = []
            adj[source].append(target)

        # Track visited and recursion stack
        visited = set()
        rec_stack = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        # Check all nodes
        for intent in dag.intents:
            if intent.id not in visited:
                if has_cycle(intent.id):
                    return False

        return True

    def get_system_prompt(self) -> str:
        """Get system prompt.

        Returns:
            System prompt string
        """
        return "你是一个专业的用户行为分析专家，擅长使用语言学Logical Form方法分析意图依赖关系。请只输出有效的JSON格式。"


__all__ = ["DAGBuildPrompt"]