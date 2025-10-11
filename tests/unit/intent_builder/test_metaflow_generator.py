"""
Unit tests for MetaFlowGenerator

Tests the MetaFlowGenerator component with mocked dependencies.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.intent_builder.generators.metaflow_generator import MetaFlowGenerator
from src.intent_builder.core.intent import Intent
from src.intent_builder.core.intent_memory_graph import IntentMemoryGraph
from src.intent_builder.core.metaflow import MetaFlow
from src.intent_builder.core.operation import Operation, ElementInfo


class TestMetaFlowGenerator:
    """Unit tests for MetaFlowGenerator"""

    @pytest.fixture
    def mock_llm_provider(self):
        """Create mock LLM provider"""
        mock_llm = Mock()
        mock_llm.generate_response = AsyncMock()
        return mock_llm

    @pytest.fixture
    def sample_intents(self):
        """Create sample intents for testing"""
        return [
            Intent(
                id="intent_001",
                description="Navigate to Allegro homepage",
                operations=[
                    Operation(
                        type="navigate",
                        url="https://allegro.pl/",
                        timestamp="2025-10-10 16:00:00",
                        element=ElementInfo()
                    )
                ],
                created_at="2025-10-10T16:00:00",
                source_session_id="session_test"
            ),
            Intent(
                id="intent_002",
                description="Navigate to coffee category page",
                operations=[
                    Operation(
                        type="click",
                        timestamp="2025-10-10 16:00:01",
                        element=ElementInfo(textContent="Coffee", tagName="A")
                    ),
                    Operation(
                        type="navigate",
                        url="https://allegro.pl/coffee",
                        timestamp="2025-10-10 16:00:01"
                    )
                ],
                created_at="2025-10-10T16:00:01",
                source_session_id="session_test"
            ),
            Intent(
                id="intent_003",
                description="Extract coffee product information",
                operations=[
                    Operation(
                        type="navigate",
                        url="https://allegro.pl/coffee/product-1",
                        timestamp="2025-10-10 16:00:02"
                    ),
                    Operation(
                        type="extract",
                        target="product_info",
                        timestamp="2025-10-10 16:00:02",
                        element=ElementInfo(xpath="//div[@class='product']")
                    )
                ],
                created_at="2025-10-10T16:00:02",
                source_session_id="session_test"
            )
        ]

    @pytest.fixture
    def mock_graph(self, sample_intents):
        """Create mock IntentMemoryGraph"""
        mock_graph = Mock(spec=IntentMemoryGraph)
        mock_graph.get_all_intents.return_value = sample_intents
        mock_graph.get_edges.return_value = [
            ("intent_001", "intent_002"),
            ("intent_002", "intent_003")
        ]
        return mock_graph

    @pytest.fixture
    def sample_metaflow_yaml(self):
        """Sample MetaFlow YAML response from LLM"""
        return """```yaml
version: "1.0"
task_description: "Collect coffee product information"

nodes:
  - id: node_1
    intent_id: intent_001
    intent_name: "NavigateToAllegro"
    intent_description: "Navigate to Allegro homepage"
    operations:
      - type: navigate
        url: "https://allegro.pl/"
        element: {}

  - id: node_2
    intent_id: intent_002
    intent_name: "NavigateToCoffeeCategory"
    intent_description: "Navigate to coffee category page"
    operations:
      - type: click
        element:
          textContent: "Coffee"
          tagName: "A"
      - type: navigate
        url: "https://allegro.pl/coffee"

  - id: node_3
    intent_id: intent_003
    intent_name: "ExtractProductInfo"
    intent_description: "Extract coffee product information"
    operations:
      - type: navigate
        url: "https://allegro.pl/coffee/product-1"
      - type: extract
        target: "product_info"
        element:
          xpath: "//div[@class='product']"
    outputs:
      product_info: "product_info"
```"""

    def test_init(self, mock_llm_provider):
        """Test MetaFlowGenerator initialization"""
        generator = MetaFlowGenerator(mock_llm_provider)
        assert generator.llm == mock_llm_provider

    def test_build_prompt(self, mock_llm_provider, sample_intents):
        """Test _build_prompt method"""
        generator = MetaFlowGenerator(mock_llm_provider)

        edges = [("intent_001", "intent_002"), ("intent_002", "intent_003")]
        task_desc = "Collect coffee product information"
        user_query = "Collect all coffee products"

        prompt = generator._build_prompt(sample_intents, edges, task_desc, user_query)

        # Verify prompt contains key information
        assert task_desc in prompt
        assert user_query in prompt
        assert "intent_001" in prompt
        assert "intent_002" in prompt
        assert "intent_003" in prompt
        assert "Navigate to Allegro homepage" in prompt
        assert "Path Selection" in prompt or "Path Filtering" in prompt
        assert "MetaFlow Specification" in prompt or "MetaFlow" in prompt

    def test_extract_yaml_with_code_block(self, mock_llm_provider):
        """Test _extract_yaml with markdown code block"""
        generator = MetaFlowGenerator(mock_llm_provider)

        llm_response = """Here is the MetaFlow:

```yaml
version: "1.0"
task_description: "test"
nodes: []
```

Hope this helps!"""

        yaml_str = generator._extract_yaml(llm_response)

        assert "version:" in yaml_str
        assert "1.0" in yaml_str
        assert "task_description:" in yaml_str
        assert "nodes:" in yaml_str
        assert "```" not in yaml_str  # Code block markers removed

    def test_extract_yaml_without_code_block(self, mock_llm_provider):
        """Test _extract_yaml without markdown code block"""
        generator = MetaFlowGenerator(mock_llm_provider)

        llm_response = """version: "1.0"
task_description: "test"
nodes: []"""

        yaml_str = generator._extract_yaml(llm_response)

        assert yaml_str == llm_response

    @pytest.mark.asyncio
    async def test_generate_metaflow(
        self,
        mock_llm_provider,
        mock_graph,
        sample_metaflow_yaml
    ):
        """Test complete generate flow"""
        # Setup mock LLM response
        mock_llm_provider.generate_response.return_value = sample_metaflow_yaml

        generator = MetaFlowGenerator(mock_llm_provider)

        # Generate MetaFlow
        metaflow = await generator.generate(
            graph=mock_graph,
            task_description="Collect coffee product information",
            user_query="Collect all coffee products"
        )

        # Verify LLM was called
        mock_llm_provider.generate_response.assert_called_once()
        call_args = mock_llm_provider.generate_response.call_args
        assert "Collect coffee product information" in call_args[0][1]
        assert "Collect all coffee products" in call_args[0][1]

        # Verify MetaFlow structure
        assert isinstance(metaflow, MetaFlow)
        assert metaflow.version == "1.0"
        assert metaflow.task_description == "Collect coffee product information"
        assert len(metaflow.nodes) == 3

        # Verify nodes
        assert metaflow.nodes[0].intent_id == "intent_001"
        assert metaflow.nodes[0].intent_name == "NavigateToAllegro"
        assert metaflow.nodes[1].intent_id == "intent_002"
        assert metaflow.nodes[2].intent_id == "intent_003"

        # Verify operations
        assert len(metaflow.nodes[0].operations) == 1
        assert metaflow.nodes[0].operations[0].type == "navigate"

    @pytest.mark.asyncio
    async def test_generate_with_loop(self, mock_llm_provider, mock_graph):
        """Test generate with loop structure"""
        # Mock LLM response with loop
        loop_yaml = """```yaml
version: "1.0"
task_description: "Collect all coffee products"

nodes:
  - id: node_1
    intent_id: intent_001
    intent_name: "NavigateToAllegro"
    intent_description: "Navigate to Allegro homepage"
    operations:
      - type: navigate
        url: "https://allegro.pl/"
        element: {}

  - id: node_2
    intent_id: intent_002
    intent_name: "NavigateToCoffeeCategory"
    intent_description: "Navigate to coffee category page"
    operations:
      - type: click
        element:
          textContent: "Coffee"
      - type: navigate
        url: "https://allegro.pl/coffee"

  - id: node_3
    intent_id: implicit_extract_list
    intent_name: "ExtractProductList"
    intent_description: "Extract product list (inferred node)"
    operations:
      - type: extract
        target: "product_urls"
        element:
          xpath: "<PLACEHOLDER>"
          tagName: "A"
        value: []
    outputs:
      product_urls: "product_urls"

  - id: node_4
    type: loop
    description: "Iterate through product list"
    source: "{{product_urls}}"
    item_var: "current_product"
    children:
      - id: node_4_1
        intent_id: intent_003
        intent_name: "ExtractProductInfo"
        intent_description: "Extract coffee product information"
        inputs:
          product_url: "{{current_product.url}}"
        operations:
          - type: navigate
            url: "{{current_product.url}}"
          - type: extract
            target: "product_info"
            element:
              xpath: "//div[@class='product']"
        outputs:
          product_info: "product_info"
```"""

        mock_llm_provider.generate_response.return_value = loop_yaml

        generator = MetaFlowGenerator(mock_llm_provider)

        # Generate MetaFlow with loop query
        metaflow = await generator.generate(
            graph=mock_graph,
            task_description="Collect coffee product information",
            user_query="Collect all coffee products"
        )

        # Verify MetaFlow structure
        assert len(metaflow.nodes) == 4

        # Verify loop node
        loop_node = metaflow.nodes[3]
        assert loop_node.type == "loop"
        assert loop_node.source == "{{product_urls}}"
        assert loop_node.item_var == "current_product"
        assert len(loop_node.children) == 1

        # Verify child node in loop
        child_node = loop_node.children[0]
        assert child_node.intent_id == "intent_003"
        assert child_node.inputs is not None
        assert child_node.inputs["product_url"] == "{{current_product.url}}"

    def test_get_metaflow_spec(self, mock_llm_provider):
        """Test _get_metaflow_spec returns proper specification"""
        generator = MetaFlowGenerator(mock_llm_provider)
        spec = generator._get_metaflow_spec()

        assert "MetaFlow Specification" in spec
        assert "Regular node" in spec or "Regular Node" in spec
        assert "Loop node" in spec or "Loop Node" in spec
        assert "intent_id" in spec
        assert "operations" in spec
        assert "children" in spec

    def test_get_conversion_rules(self, mock_llm_provider):
        """Test _get_conversion_rules returns proper rules"""
        generator = MetaFlowGenerator(mock_llm_provider)
        rules = generator._get_conversion_rules()

        assert "Conversion Rules" in rules
        assert "Loop Detection" in rules
        assert "Implicit Node" in rules
        assert "Data Flow" in rules
        assert "intent_name" in rules
        assert "PLACEHOLDER" in rules
