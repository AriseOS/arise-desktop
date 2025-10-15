"""
MetaFlowGenerator - Generate MetaFlow from IntentMemoryGraph

Based on: docs/intent_builder/07_metaflow_generator_design.md
"""
import json
import re
import logging
from typing import List, Tuple

from src.intent_builder.core.intent import Intent
from src.intent_builder.core.intent_memory_graph import IntentMemoryGraph
from src.intent_builder.core.metaflow import MetaFlow
from src.common.llm import BaseProvider

logger = logging.getLogger(__name__)


class MetaFlowGenerator:
    """Generate MetaFlow from IntentMemoryGraph

    Takes a graph structure (nodes + edges) and user query,
    uses LLM to select relevant path and generate MetaFlow YAML.

    Example:
        >>> generator = MetaFlowGenerator(llm_provider)
        >>> metaflow = await generator.generate(
        ...     graph=intent_graph,
        ...     task_description="Collect coffee product info",
        ...     user_query="Collect all coffee products"
        ... )
    """

    def __init__(self, llm_provider: BaseProvider):
        """Initialize MetaFlowGenerator

        Args:
            llm_provider: LLM service provider (Anthropic, OpenAI, etc.)
        """
        self.llm = llm_provider

    async def generate(
        self,
        graph: IntentMemoryGraph,
        task_description: str,
        user_query: str
    ) -> MetaFlow:
        """Generate MetaFlow from IntentMemoryGraph

        Args:
            graph: IntentMemoryGraph object (contains nodes and edges)
            task_description: Detailed task description
            user_query: User query (for path selection, loop detection, etc.)

        Returns:
            MetaFlow object

        Note:
            - graph contains complete graph structure (may have multiple branches)
            - LLM selects relevant path based on user_query
            - Example: Graph has coffee and book branches, user_query="collect coffee info"
                      LLM automatically selects coffee branch, filters out book branch
        """
        # 1. Extract intents and edges from graph
        intents = graph.get_all_intents()
        edges = graph.get_edges()  # List[Tuple[str, str]]

        logger.info(f"Generating MetaFlow from graph: {len(intents)} intents, {len(edges)} edges")

        # 2. Build prompt (includes graph structure)
        prompt = self._build_prompt(intents, edges, task_description, user_query)

        # 3. Call LLM to generate MetaFlow YAML (LLM handles path selection)
        logger.info("Calling LLM to generate MetaFlow...")
        response = await self.llm.generate_response("", prompt)

        # 4. Extract YAML (from markdown code block)
        logger.info("=" * 80)
        logger.info("Step 4: Extracting YAML from LLM response")
        logger.info(f"Raw response length: {len(response)} chars")
        logger.info("FULL RAW RESPONSE:")
        logger.info(response)
        logger.info("=" * 80)

        metaflow_yaml = self._extract_yaml(response)

        logger.info("After extraction:")
        logger.info(f"Extracted YAML length: {len(metaflow_yaml)} chars")
        logger.info(f"Extracted YAML first 200 chars:\n{metaflow_yaml[:200]}")
        logger.info("=" * 80)

        # 5. Parse and validate
        try:
            metaflow = MetaFlow.from_yaml(metaflow_yaml)
        except Exception as e:
            logger.error(f"Failed to parse MetaFlow YAML: {e}")
            logger.error("=" * 80)
            logger.error("FAILED YAML CONTENT:")
            logger.error(metaflow_yaml)
            logger.error("=" * 80)
            raise

        logger.info(f"✓ MetaFlow generated: {len(metaflow.nodes)} nodes")

        return metaflow

    def _build_prompt(
        self,
        intents: List[Intent],
        edges: List[Tuple[str, str]],
        task_desc: str,
        user_query: str
    ) -> str:
        """Build MetaFlow generation prompt (includes graph structure)"""

        # Format intent list
        intent_descriptions = []
        for intent in intents:
            # Convert operations to dict format - PRESERVE ALL FIELDS
            operations_list = []
            for op in intent.operations:
                # Pydantic Operation has model_dump() method - use it directly
                op_dict = op.model_dump(by_alias=True, exclude_none=True)
                operations_list.append(op_dict)

            intent_descriptions.append({
                "id": intent.id,
                "description": intent.description,
                "operations": operations_list
            })

        # Format edges
        edges_formatted = [
            {"from": from_id, "to": to_id}
            for from_id, to_id in edges
        ]

        return f"""Convert the following Intent graph structure to MetaFlow YAML.

## Task Description
{task_desc}

## User Query
{user_query}

## Intent Graph Structure

### Nodes (Intents)
{json.dumps(intent_descriptions, indent=2, ensure_ascii=False)}

### Edges (Intent Execution Order)
{json.dumps(edges_formatted, indent=2, ensure_ascii=False)}

**IMPORTANT - Path Selection**:
- The graph may contain multiple branch paths (e.g., coffee branch, book branch, etc.)
- You need to select relevant paths based on "User Query"
- Only use Intents related to the user query, ignore irrelevant branches
- Example: If user query is "collect coffee info", only select coffee-related Intents, ignore book-related Intents

---

{self._get_metaflow_spec()}

---

{self._get_conversion_rules()}

---

## Output Requirements

Output complete MetaFlow YAML (conforming to above specification).

Notes:
- **Path Filtering**: Only include Intents related to user query, ignore irrelevant branches in the graph
- Only output pure YAML content, DO NOT wrap in markdown code blocks (```yaml), no explanations
- Ensure YAML format is correct and parsable
- If loop is needed, detect keywords in user query ("all", "every", etc.)
- If loop needs list data but not provided in Intent, insert implicit ExtractList node
"""

    def _get_metaflow_spec(self) -> str:
        """Get MetaFlow specification"""
        return """# MetaFlow Specification

## Basic Structure

```yaml
version: "1.0"
task_description: "Task description"

nodes:
  # Regular node
  - id: node_1
    intent_id: intent_xxx
    intent_name: "NavigateToSite"
    intent_description: "Navigate to website"
    operations:
      - type: navigate
        url: "https://example.com"
        element: {}
    outputs:  # Optional: if this node produces output
      output_key: "variable_name"

  # Loop node
  - id: node_2
    type: loop
    description: "Iterate through list, process each item"
    source: "{{list_variable}}"
    item_var: "current_item"
    children:
      - id: node_2_1
        intent_id: intent_yyy
        intent_name: "ProcessItem"
        intent_description: "Process single item"
        operations: [...]
        inputs:  # Optional: use loop variable
          item_url: "{{current_item.url}}"
        outputs:
          result: "item_result"
```

## Key Points

1. **Regular Node**: Direct mapping from Intent
   - `intent_id`: Intent ID
   - `intent_name`: Simplified name (PascalCase)
   - `intent_description`: Intent description
   - `operations`: Intent operations (full copy)

2. **outputs**: If node produces data (especially extract operations)
   - Format: `{output_key: "variable_name"}`
   - Example: `{"product_urls": "product_urls"}`

3. **Loop Node**: For iterating over lists
   - `type: loop`
   - `description`: Natural language description of loop
   - `source`: Data source (reference previous node's output)
   - `item_var`: Loop variable name
   - `children`: Loop body (list of child nodes)

4. **Data Flow**: Use `{{variable_name}}` to reference variables
   - Previous node's output can be referenced by later nodes
   - Loop variable available in children: `{{current_item.field}}`
"""

    def _get_conversion_rules(self) -> str:
        """Get conversion rules"""
        return """# Conversion Rules

## 1. Intent → MetaFlowNode Mapping

Each Intent generates one MetaFlowNode:

```yaml
# Intent
Intent(
  id="intent_a3f5b2c1",
  description="Navigate to Allegro homepage",
  operations=[...]
)

# MetaFlowNode
- id: node_1
  intent_id: intent_a3f5b2c1
  intent_name: "NavigateToAllegro"  # Extracted from description
  intent_description: "Navigate to Allegro homepage"
  operations: [...]  # Full copy
```

## 2. Loop Detection and Generation

**Detection Keywords**: "all", "every", "each", "所有", "全部", "每个", "遍历"

**Generate Loop Structure**:
1. Detect loop keywords
2. Identify Intent that needs iteration (usually extract detail Intent)
3. Check if there's a list extraction node
4. If not → Insert implicit node

**Example**:
```yaml
# User query: "Collect all coffee product info"
# Intent list: [NavigateToCategory, ExtractProductDetail]

# Generated result:
nodes:
  - id: node_1
    # NavigateToCategory
    ...

  - id: node_2  # Implicit node (inferred)
    intent_id: implicit_extract_list
    intent_name: "ExtractProductList"
    intent_description: "Extract product list (inferred node)"
    operations:
      - type: extract
        target: "product_urls"
        element:
          xpath: "<PLACEHOLDER>"  # Placeholder, filled by WorkflowGenerator
          tagName: "A"
        value: []  # Indicates list
    outputs:
      product_urls: "product_urls"

  - id: node_3  # Loop node
    type: loop
    description: "Iterate through product list, extract detailed info"
    source: "{{product_urls}}"
    item_var: "current_product"
    children:
      - id: node_3_1
        # ExtractProductDetail
        inputs:
          product_url: "{{current_product.url}}"
        ...
```

## 3. Implicit Node Generation Rules

**Trigger Condition**:
- Loop requirement detected
- No list extraction node in Intent list

**Generated Content**:
```yaml
- id: node_implicit
  intent_id: implicit_extract_list
  intent_name: "ExtractProductList"
  intent_description: "Extract product list (inferred node)"
  operations:
    - type: extract
      target: "product_urls"  # Inferred from semantics
      element:
        xpath: "<PLACEHOLDER>"  # Use placeholder
        tagName: "A"
      value: []  # List type
  outputs:
    product_urls: "product_urls"
```

**Note**:
- `xpath` uses placeholder `<PLACEHOLDER>`
- Filled by subsequent WorkflowGenerator
- `target` and `outputs` inferred from context

## 4. Data Flow Connection Rules

**outputs Inference**:
- If operations contain `extract` operation → generate outputs
- `extract.target` as output key
- Example: `extract(target="price")` → `outputs: {price: "price"}`

**inputs Reference**:
- Nodes inside loop need to reference loop variable
- Format: `{{item_var.field}}`
- Example: `{{current_product.url}}`

**Variable Naming**:
- List variables: `product_urls`, `all_products`, `item_list`
- Loop variables: `current_product`, `current_item`, `item`
- Result variables: `product_info`, `item_data`, `result`

## 5. intent_name Generation Rules

Extract key verbs and nouns from `intent_description`, generate PascalCase name:

- "Navigate to Allegro homepage" → "NavigateToAllegro"
- "Enter coffee category page" → "EnterCoffeeCategory"
- "Extract product info" → "ExtractProductInfo"

## 6. Node Order

Arrange by Intent order, but:
- Implicit nodes inserted before loop nodes
- Loop nodes contain child nodes (children)
"""

    def _extract_yaml(self, llm_response: str) -> str:
        """Extract YAML from LLM response"""
        # Debug: Log raw LLM response
        logger.debug("=" * 80)
        logger.debug("Raw LLM Response:")
        logger.debug(f"Length: {len(llm_response)} characters")
        logger.debug(f"First 200 chars: {repr(llm_response[:200])}")
        logger.debug(f"Last 100 chars: {repr(llm_response[-100:])}")
        logger.debug("=" * 80)

        # Try to extract ```yaml ... ``` code block (with or without newline)
        match = re.search(r'```yaml\s*(.*?)```', llm_response, re.DOTALL)
        if match:
            logger.debug("✓ Matched with ```yaml pattern")
            return match.group(1).strip()

        # Try without yaml marker
        match = re.search(r'```\s*(.*?)```', llm_response, re.DOTALL)
        if match:
            logger.debug("✓ Matched with ``` pattern (no yaml marker)")
            return match.group(1).strip()

        # If no code block, assume entire response is YAML
        logger.debug("⚠️  No markdown code block found, using entire response")
        return llm_response.strip()
