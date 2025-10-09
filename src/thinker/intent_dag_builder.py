"""Intent DAG Builder - Complete pipeline from events to Intent DAG.

This module provides end-to-end functionality:
1. Extract atomic intents from browser events using LogicalForm analysis
2. Build Directed Acyclic Graph from intent list
3. Complete pipeline: events -> intents -> DAG
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.ontology.intent import AtomicIntent, AtomicIntentType, Intent
from src.thinker.json_processor import BrowserEvent, JSONInputBatch, JsonProcessor
from src.services.llm import LLMClient, LLMMessage, LLMResponse
from src.thinker.prompts.dag_build_prompt import DAGBuildPrompt


class IntentAnalysisResult:
    """Result of intent extraction from events.

    Attributes:
        atomic_intents: List of extracted AtomicIntent objects
        analysis_metadata: Metadata about the analysis process
        llm_response: Raw LLM response (if LLM was used)
        timestamp: Time when analysis was performed
    """

    def __init__(
        self,
        atomic_intents: List[AtomicIntent],
        analysis_metadata: Dict[str, Any],
        llm_response: str
    ):
        """Initialize intent analysis result.

        Args:
            atomic_intents: List of extracted intents
            analysis_metadata: Analysis metadata
            llm_response: Raw LLM response
        """
        self.atomic_intents = atomic_intents
        self.analysis_metadata = analysis_metadata
        self.llm_response = llm_response
        self.timestamp = datetime.now()

    def get_intent_count(self) -> int:
        """Get number of intents extracted.

        Returns:
            Number of intents
        """
        return len(self.atomic_intents)

    def get_intent_types(self) -> List[str]:
        """Get all intent types present.

        Returns:
            List of unique intent type values
        """
        return list(set(intent.type.value for intent in self.atomic_intents))


class IntentDAG:
    """Directed Acyclic Graph representation of Intents.

    Attributes:
        intents: List of Intent nodes
        edges: List of edges (source_id, target_id, edge_type, properties)
        metadata: Additional DAG metadata
    """

    def __init__(
        self,
        intents: List[Intent],
        edges: List[Tuple[str, str, str, Dict[str, Any]]],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Initialize IntentDAG.

        Args:
            intents: List of Intent objects
            edges: List of edge tuples (source_id, target_id, edge_type, properties)
            metadata: Optional metadata dictionary
        """
        self.intents = intents
        self.edges = edges
        self.metadata = metadata or {}

        # Build adjacency map for quick lookups
        self.adj_map: Dict[str, List[str]] = {}
        for source_id, target_id, _, _ in edges:
            if source_id not in self.adj_map:
                self.adj_map[source_id] = []
            self.adj_map[source_id].append(target_id)

    def get_root_intents(self) -> List[Intent]:
        """Get root intents (no incoming edges).

        Returns:
            List of root Intent objects
        """
        target_ids = {edge[1] for edge in self.edges}
        return [intent for intent in self.intents if intent.id not in target_ids]

    def get_leaf_intents(self) -> List[Intent]:
        """Get leaf intents (no outgoing edges).

        Returns:
            List of leaf Intent objects
        """
        source_ids = {edge[0] for edge in self.edges}
        return [intent for intent in self.intents if intent.id not in source_ids]

    def get_successors(self, intent_id: str) -> List[Intent]:
        """Get successor intents for a given intent.

        Args:
            intent_id: Intent ID

        Returns:
            List of successor Intent objects
        """
        if intent_id not in self.adj_map:
            return []

        intent_map = {intent.id: intent for intent in self.intents}
        return [intent_map[succ_id] for succ_id in self.adj_map[intent_id]
                if succ_id in intent_map]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary representation of the DAG
        """
        return {
            "intents": [intent.to_dict() for intent in self.intents],
            "edges": [
                {
                    "source": edge[0],
                    "target": edge[1],
                    "type": edge[2],
                    "properties": edge[3]
                }
                for edge in self.edges
            ],
            "metadata": self.metadata
        }


class IntentDAGBuilder:
    """Builder for complete intent analysis and DAG construction pipeline.

    Provides:
    1. Event analysis: Extract intents from browser events
    2. DAG construction: Build DAG from intent list
    3. Complete pipeline: events -> intents -> DAG

    Uses LLM and LogicalForm analysis with rule-based fallback.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        model_name: str = "gpt-4"
    ):
        """Initialize IntentDAGBuilder.

        Args:
            llm_client: LLM client for analysis (optional)
            model_name: Name of LLM model to use (default: gpt-4)
        """
        self.llm_client = llm_client
        self.model_name = model_name
        self.dag_prompt = DAGBuildPrompt()
        self.analysis_cache: Dict[str, IntentAnalysisResult] = {}

    # ==================== Complete Pipeline ====================

    def build_dag_from_events(
        self,
        batch: JSONInputBatch,
        use_llm: bool = True
    ) -> Tuple[IntentAnalysisResult, IntentDAG]:
        """Complete pipeline: Extract intents from events and build DAG.

        Args:
            batch: JSON input batch containing browser events
            use_llm: Whether to use LLM for analysis (default: True)

        Returns:
            Tuple of (IntentAnalysisResult, IntentDAG)
        """
        # Step 1: Extract intents from events
        analysis_result = self.analyze_events_to_intents(batch, use_llm=use_llm)

        # Step 2: Build DAG from intents
        dag = self.build_dag(analysis_result.atomic_intents, use_llm=use_llm)

        return analysis_result, dag

    # ==================== Event Analysis (Step 1) ====================

    def analyze_events_to_intents(
        self,
        batch: JSONInputBatch,
        use_llm: bool = True
    ) -> IntentAnalysisResult:
        """Extract atomic intents from browser events using LogicalForm analysis.

        Args:
            batch: JSON input batch containing events
            use_llm: Whether to use LLM for analysis

        Returns:
            IntentAnalysisResult containing extracted intents
        """
        if use_llm and self.llm_client:
            return self._analyze_events_with_llm(batch)

        return self._analyze_events_rule_based(batch)

    def _analyze_events_with_llm(self, batch: JSONInputBatch) -> IntentAnalysisResult:
        """Extract intents using LLM analysis.

        Args:
            batch: JSON input batch

        Returns:
            IntentAnalysisResult
        """
        try:
            # Build prompt
            user_prompt = self._build_intent_extraction_prompt(batch)
            system_prompt = ("你是一个专业的用户行为分析专家，擅长使用logical form方法"
                           "分析浏览器操作序列。请只输出有效的JSON格式。")

            # Call LLM
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt)
            ]
            response: LLMResponse = self.llm_client.generate(
                messages,
                temperature=0.1,
                max_tokens=4000
            )

            # Parse response
            atomic_intents, metadata = self._parse_intent_extraction_response(
                response.content, batch
            )

            # Create result
            result = IntentAnalysisResult(
                atomic_intents=atomic_intents,
                analysis_metadata=metadata,
                llm_response=response.content
            )

            # Cache result
            self.analysis_cache[batch.batch_id] = result

            return result

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Intentionally catch all exceptions for fallback
            print(f"LLM intent extraction failed, falling back to rule-based: {str(e)}")
            return self._analyze_events_rule_based(batch)

    def _analyze_events_rule_based(self, batch: JSONInputBatch) -> IntentAnalysisResult:
        """Extract intents using rule-based approach.

        Args:
            batch: JSON input batch

        Returns:
            IntentAnalysisResult
        """
        atomic_intents = []

        for event in batch.events:
            intent = self._event_to_intent(event, batch)
            if intent:
                atomic_intents.append(intent)

        # Build metadata
        intent_type_distribution = {}
        for intent in atomic_intents:
            intent_type = intent.type.value
            intent_type_distribution[intent_type] = \
                intent_type_distribution.get(intent_type, 0) + 1

        metadata = {
            "total_intents": len(atomic_intents),
            "intent_type_distribution": intent_type_distribution,
            "analysis_method": "rule_based",
            "confidence_score": 0.7,
            "notes": "Rule-based intent extraction (LLM fallback)"
        }

        return IntentAnalysisResult(
            atomic_intents=atomic_intents,
            analysis_metadata=metadata,
            llm_response="rule_based_fallback"
        )

    def _build_intent_extraction_prompt(self, batch: JSONInputBatch) -> str:
        """Build LLM prompt for intent extraction.

        Args:
            batch: JSON input batch

        Returns:
            Formatted prompt string
        """
        # Format events
        processor = JsonProcessor()
        events_description = processor.export_to_llm_format(batch)

        prompt = f'''你是一个专业的用户行为分析专家，擅长使用语言学中的logical form方法分析用户操作序列。

你的任务是：将浏览器事件序列转换为结构化的原子意图（Atomic Intents）列表。

## 输入数据

{events_description}

## 原子意图类型定义

可用的原子意图类型：

1. **ClickElement** - 点击元素
2. **TypeText** - 输入文本
3. **SelectOption** - 选择选项
4. **ScrollPage** - 滚动页面
5. **NavigatePage** - 页面导航
6. **HoverElement** - 悬停元素
7. **CopyText** - 复制文本
8. **PasteText** - 粘贴文本

## 输出格式

请严格按照以下JSON格式输出分析结果：

```json
{{
  "atomic_intents": [
    {{
      "intent_type": "ClickElement",
      "timestamp": 1234567890000,
      "page_url": "https://example.com",
      "page_title": "Example Page",
      "element_id": "submit-button",
      "element_tag": "button",
      "xpath": "//button[@id='submit-button']",
      "text": "Submit",
      "coordinates": {{"x": 100, "y": 200}},
      "attributes": {{}}
    }}
  ],
  "analysis_metadata": {{
    "total_intents": 1,
    "intent_type_distribution": {{"ClickElement": 1}},
    "analysis_method": "logical_form",
    "confidence_score": 0.95,
    "notes": "分析说明"
  }}
}}
```

请开始分析并输出结果。
'''
        return prompt

    def _parse_intent_extraction_response(
        self,
        llm_response: str,
        batch: JSONInputBatch
    ) -> Tuple[List[AtomicIntent], Dict[str, Any]]:
        """Parse LLM response for intent extraction.

        Args:
            llm_response: Raw LLM response
            batch: Original batch for context

        Returns:
            Tuple of (intents list, metadata dict)
        """
        # Clean response
        llm_response = self._clean_json_response(llm_response)

        # Parse JSON
        try:
            response_data = json.loads(llm_response)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON parsing failed: {str(e)}") from e

        # Extract data
        intents_data = response_data.get("atomic_intents", [])
        metadata = response_data.get("analysis_metadata", {})

        # Build AtomicIntent objects
        atomic_intents = []
        for intent_data in intents_data:
            intent = self._create_atomic_intent(intent_data, batch)
            if intent:
                atomic_intents.append(intent)

        return atomic_intents, metadata

    def _create_atomic_intent(
        self,
        intent_data: Dict[str, Any],
        batch: JSONInputBatch
    ) -> Optional[AtomicIntent]:
        """Create AtomicIntent object from parsed data.

        Args:
            intent_data: Intent data dictionary
            batch: Original batch for context

        Returns:
            AtomicIntent object or None if creation failed
        """
        try:
            # Parse intent type
            intent_type_str = intent_data.get("intent_type")
            intent_type = AtomicIntentType(intent_type_str)

            # Create AtomicIntent
            intent = AtomicIntent(
                type=intent_type,
                timestamp=intent_data.get("timestamp"),
                page_url=intent_data.get("page_url"),
                page_title=intent_data.get("page_title"),
                element_id=intent_data.get("element_id"),
                element_tag=intent_data.get("element_tag"),
                xpath=intent_data.get("xpath"),
                text=intent_data.get("text"),
                value=intent_data.get("value"),
                coordinates=intent_data.get("coordinates"),
                user_id=batch.context.user_id,
                session_id=batch.context.session_id,
                attributes=intent_data.get("attributes", {})
            )

            return intent

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Intentionally catch all exceptions to skip invalid intents
            print(f"Failed to create atomic intent: {str(e)}")
            return None

    def _event_to_intent(
        self,
        event: BrowserEvent,
        batch: JSONInputBatch
    ) -> Optional[AtomicIntent]:
        """Convert event to intent using rule-based mapping.

        Args:
            event: Browser event
            batch: Original batch for context

        Returns:
            AtomicIntent object or None
        """
        # Event type to intent type mapping
        type_mapping = {
            "click": AtomicIntentType.CLICK_ELEMENT,
            "input": AtomicIntentType.TYPE_TEXT,
            "change": AtomicIntentType.SELECT_OPTION,
            "scroll": AtomicIntentType.SCROLL_PAGE,
            "navigation": AtomicIntentType.NAVIGATE_PAGE,
            "hover": AtomicIntentType.HOVER_ELEMENT,
            "copy": AtomicIntentType.COPY_TEXT,
            "paste": AtomicIntentType.PASTE_TEXT
        }

        intent_type = type_mapping.get(event.event_type.lower())
        if not intent_type:
            return None

        return AtomicIntent(
            type=intent_type,
            timestamp=event.timestamp,
            page_url=event.page_url,
            page_title=event.page_title,
            element_id=event.element_id,
            element_tag=event.element_tag,
            xpath=event.xpath,
            text=event.text,
            value=event.value,
            coordinates=event.coordinates,
            user_id=batch.context.user_id,
            session_id=batch.context.session_id,
            attributes=event.attributes
        )

    def _clean_json_response(self, response: str) -> str:
        """Clean LLM JSON response.

        Args:
            response: Raw response

        Returns:
            Cleaned JSON string
        """
        response = response.strip()

        # Remove markdown code blocks
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end != -1:
                response = response[start:end].strip()

        # Extract JSON object
        start_idx = response.find('{')
        end_idx = response.rfind('}')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            response = response[start_idx:end_idx + 1]

        return response

    # ==================== DAG Construction (Step 2) ====================

    def build_dag(
        self,
        intents: List[Intent],
        use_llm: bool = True
    ) -> IntentDAG:
        """Build DAG from intent list.

        Args:
            intents: List of Intent objects
            use_llm: Whether to use LLM for analysis (default: True)

        Returns:
            IntentDAG object

        Raises:
            ValueError: If intents are invalid
        """
        if not self.dag_prompt.validate_input(intents):
            raise ValueError("Invalid intent list")

        # Sort intents by timestamp
        sorted_intents = sorted(intents, key=lambda x: x.timestamp)

        if use_llm and self.llm_client:
            return self._build_dag_with_llm(sorted_intents)

        return self._build_dag_rule_based(sorted_intents)

    def _build_dag_with_llm(self, intents: List[Intent]) -> IntentDAG:
        """Build DAG using LLM analysis.

        Args:
            intents: Sorted list of Intent objects

        Returns:
            IntentDAG object
        """
        try:
            # Build prompt
            user_prompt = self.dag_prompt.build_prompt(intents)
            system_prompt = self.dag_prompt.get_system_prompt()

            # Call LLM
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt)
            ]
            response: LLMResponse = self.llm_client.generate(
                messages,
                temperature=0.1,
                max_tokens=4000
            )

            # Parse response
            dag_data = self.dag_prompt.parse_json_response(response.content)

            # Extract edges
            edges_data = dag_data.get("edges", [])
            edges = [
                (
                    edge["source_id"],
                    edge["target_id"],
                    edge.get("edge_type", "temporal"),
                    edge.get("properties", {})
                )
                for edge in edges_data
            ]

            # Create DAG
            dag = IntentDAG(
                intents=intents,
                edges=edges,
                metadata=dag_data.get("metadata", {})
            )

            return dag

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Intentionally catch all exceptions for fallback to rule-based method
            print(f"LLM DAG building failed, falling back to rule-based: {str(e)}")
            return self._build_dag_rule_based(intents)

    def _build_dag_rule_based(self, intents: List[Intent]) -> IntentDAG:
        """Build DAG using rule-based approach.

        Creates simple temporal edges between consecutive intents.

        Args:
            intents: Sorted list of Intent objects

        Returns:
            IntentDAG object
        """
        edges = []

        # Create temporal edges between consecutive intents
        for i in range(len(intents) - 1):
            source = intents[i]
            target = intents[i + 1]

            # Calculate time difference
            time_diff = target.timestamp - source.timestamp

            edges.append((
                source.id,
                target.id,
                "temporal",
                {
                    "time_diff_ms": time_diff,
                    "strength": 0.7,
                    "reason": "Temporal sequence (rule-based)"
                }
            ))

        metadata = {
            "total_edges": len(edges),
            "edge_type_distribution": {"temporal": len(edges)},
            "analysis_method": "rule_based",
            "confidence_score": 0.7,
            "notes": "Simple temporal DAG based on chronological order"
        }

        return IntentDAG(
            intents=intents,
            edges=edges,
            metadata=metadata
        )

    # ==================== Utility Methods ====================

    def get_analysis_statistics(self) -> Dict[str, Any]:
        """Get statistics about cached intent analyses.

        Returns:
            Dictionary with analysis statistics
        """
        total_analyses = len(self.analysis_cache)
        total_intents = sum(
            result.get_intent_count()
            for result in self.analysis_cache.values()
        )

        intent_type_counts = {}
        for result in self.analysis_cache.values():
            for intent_type in result.get_intent_types():
                intent_type_counts[intent_type] = \
                    intent_type_counts.get(intent_type, 0) + 1

        return {
            "total_analyses": total_analyses,
            "total_intents": total_intents,
            "intent_type_distribution": intent_type_counts,
            "analyses": [
                {
                    "batch_id": batch_id,
                    "intent_count": result.get_intent_count(),
                    "intent_types": result.get_intent_types(),
                    "timestamp": result.timestamp.isoformat()
                }
                for batch_id, result in self.analysis_cache.items()
            ]
        }


__all__ = [
    "IntentAnalysisResult",
    "IntentDAG",
    "IntentDAGBuilder",
]