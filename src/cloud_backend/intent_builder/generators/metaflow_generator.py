"""
MetaFlowGenerator - Generate MetaFlow from IntentMemoryGraph

Based on: docs/intent_builder/07_metaflow_generator_design.md
"""
import json
import re
import logging
from typing import List, Tuple

from src.cloud_backend.intent_builder.core.intent import Intent
from src.cloud_backend.intent_builder.core.intent_memory_graph import IntentMemoryGraph
from src.cloud_backend.intent_builder.core.metaflow import MetaFlow
from src.common.llm import BaseProvider

logger = logging.getLogger(__name__)


class MetaFlowGenerator:
    """Generate MetaFlow from IntentMemoryGraph

    Takes a graph structure (nodes + edges) and user query,
    uses LLM to select relevant path and generate MetaFlow YAML.

    Example:
        >>> from src.common.llm import AnthropicProvider
        >>> # With API Proxy (recommended)
        >>> llm_provider = AnthropicProvider(
        ...     api_key="ami_user123",
        ...     base_url="http://localhost:8080"
        ... )
        >>> # Or without API Proxy (direct Anthropic)
        >>> llm_provider = AnthropicProvider(api_key="sk-ant-...")
        >>>
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
                         Should be initialized with appropriate api_key and base_url
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

        # 5. Parse YAML to dict
        try:
            import yaml
            metaflow_dict = yaml.safe_load(metaflow_yaml)
        except Exception as e:
            logger.error(f"Failed to parse YAML: {e}")
            logger.error("=" * 80)
            logger.error("FAILED YAML CONTENT:")
            logger.error(metaflow_yaml)
            logger.error("=" * 80)
            raise

        # 6. Fill operations in dict before creating MetaFlow object
        self._fill_operations_in_dict(metaflow_dict, graph)

        # 7. Create MetaFlow object from filled dict
        try:
            metaflow_yaml_filled = yaml.dump(metaflow_dict, allow_unicode=True, sort_keys=False)
            metaflow = MetaFlow.from_yaml(metaflow_yaml_filled)
        except Exception as e:
            logger.error(f"Failed to create MetaFlow object: {e}")
            logger.error("=" * 80)
            logger.error("FAILED YAML CONTENT (after filling):")
            logger.error(metaflow_yaml_filled)
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

        # Format intent list - only send id and description (not operations)
        # Operations will be filled automatically after MetaFlow generation
        intent_descriptions = []
        for intent in intents:
            # Only send operation types as summary (not full details)
            operation_types = [op.type for op in intent.operations]

            intent_descriptions.append({
                "id": intent.id,
                "description": intent.description,
                "operation_types": operation_types  # Only types, not full operations
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

**CRITICAL**: Every MetaFlowNode MUST have an "operations" field (required by schema).

### For Regular Nodes (from Intent Graph):
- Include the "operations" field (will be automatically filled with actual Intent operations later)
- You can use placeholder operations if needed:
  ```yaml
  operations:
    - type: placeholder
  ```

### For Implicit/Inferred Nodes:
- MUST include "operations" field with appropriate operation type
- For implicit navigation nodes:
  ```yaml
  operations:
    - type: navigate
      url: "<PLACEHOLDER>"
  ```
- For implicit extract nodes:
  ```yaml
  operations:
    - type: extract
      target: "<field_name>"
      element:
        xpath: "<PLACEHOLDER>"
        tagName: "A"
      value: []
  ```

### Format Requirements:
- Output the YAML in a markdown code block using ```yaml
- Do not add any explanations outside the code block
- Ensure YAML format is correct and parsable
- **Every node MUST have "operations" field** (this is non-negotiable)

### Notes:
- **Path Filtering**: Only include Intents related to user query, ignore irrelevant branches in the graph
- If loop is needed, detect keywords in user query ("all", "every", etc.)
- If loop needs list data but not provided in Intent, insert implicit ExtractList node with operations field
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
  operations: [...]  # Full copy
```

## 2. Inferred Node Generation (Gap Analysis)

### Core Principle

The recorded operations represent what the user demonstrated (the "how").
The user_query represents what the user wants to achieve (the "what").

**Your task**: Analyze if there's a gap between what was demonstrated and what is expected.

Gap = Expected Result (from user_query) - Demonstrated Capability (from operations)

If a gap exists, you must generate inferred nodes to bridge it.

### Analysis Process

1. **Identify what the recorded operations produce**:
   - What is the final output? (e.g., raw product data in English)
   - What form is the data in?

2. **Identify what the user_query expects**:
   - What does the user want as the end result? (e.g., translated product data)
   - Is there any transformation implied?

3. **Identify any sub-goals without recorded steps**:
   - Does the user_query mention a task that has no corresponding operations?
   - Would this task require exploratory actions?

4. **Generate inferred nodes for each gap**:
   - Mark them with `(Inferred)` in intent_description
   - Use appropriate operation types

### Types of Gaps and Inferred Nodes

**A. Data Transformation Gap**

The user_query implies that extracted data needs semantic-level processing that requires language understanding.

Signs of this gap:
- The recorded operations extract data, but the query expects transformed data
- The transformation requires understanding meaning (not just reformatting)

Generate a text processing node:
```yaml
- id: node_inferred_process
  intent_id: inferred_text_process
  intent_name: "ProcessData"
  intent_description: "Process extracted data as specified (Inferred)"
  operations:
    - type: text_process
      params:
        source: "{{extracted_data}}"
  outputs:
    processed_data: "processed_data"
```

**B. Unrecorded Sub-goal Gap**

The user_query describes a sub-goal that has no corresponding recorded operations.

Signs of this gap:
- A task is mentioned but there are no operations showing how to do it
- The task would require exploring/searching on web pages
- Cannot be done with fixed URLs or xpaths from the recording

Generate an autonomous task node:
```yaml
- id: node_inferred_autonomous
  intent_id: inferred_autonomous
  intent_name: "CompleteTask"
  intent_description: "Achieve the unrecorded goal (Inferred)"
  operations:
    - type: autonomous_task
      params:
        goal: "description of what to achieve"
  outputs:
    result: "task_result"
```

### Examples

**Example 1: Translation Gap**
```
Recorded: navigate → extract product data
Query: "Collect products and translate to Chinese"

Analysis:
- Output of operations: English product data
- Expected result: Chinese product data
- Gap: Translation needed (semantic transformation)
- Action: Add text processing node after extraction
```

**Example 2: Analysis Gap**
```
Recorded: navigate → loop → extract prices
Query: "Get prices and analyze the distribution"

Analysis:
- Output of operations: List of prices
- Expected result: Analysis of price patterns
- Gap: Analysis needed (requires understanding data patterns)
- Action: Add text processing node for analysis
```

**Example 3: Unrecorded Task**
```
Recorded: navigate to company page → extract info
Query: "Get company info and find CEO's LinkedIn"

Analysis:
- Recorded operations only cover company info
- "Find CEO LinkedIn" has no recorded steps
- Gap: Exploration task needed
- Action: Add autonomous task node
```

**Example 4: No Gap**
```
Recorded: navigate → extract → store
Query: "Collect products and save"

Analysis:
- Output: Data saved
- Expected: Data saved
- Gap: None
- Action: No inferred nodes needed
```

### Important Notes

- Only add inferred nodes when there is a genuine gap
- If the recorded operations already achieve the goal, do not add extra nodes
- Always mark inferred nodes with `(Inferred)` suffix in intent_description
- The `(Inferred)` marker tells WorkflowGenerator to use appropriate agent types

## 3. Loop Detection and Generation

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
- Inferred nodes inserted at appropriate positions (after data extraction for processing, at the end for autonomous tasks)
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

    def _fill_operations_in_dict(self, metaflow_dict: dict, graph: IntentMemoryGraph):
        """
        Fill operations in dict before creating MetaFlow object

        Args:
            metaflow_dict: MetaFlow data as dict (from YAML)
            graph: Intent Graph (source of truth for operations)
        """
        logger.info("Filling operations from Intent Graph...")

        filled_count = 0
        nodes = metaflow_dict.get('nodes', [])

        for node in nodes:
            # Handle regular nodes
            if 'intent_id' in node:
                intent_id = node['intent_id']

                # Skip inferred/implicit nodes (they have placeholders, not from graph)
                if intent_id.startswith('implicit_') or intent_id.startswith('inferred_'):
                    logger.debug(f"Skipping inferred/implicit node: {node.get('id', 'unknown')}")
                    continue

                # Find corresponding Intent
                intent = graph.get_intent(intent_id)
                if intent:
                    # Fill operations from Intent (convert to dict)
                    operations_list = []
                    for op in intent.operations:
                        op_dict = op.model_dump(by_alias=True, exclude_none=True)
                        operations_list.append(op_dict)

                    node['operations'] = operations_list
                    filled_count += 1
                    logger.debug(f"✓ Filled operations for node {node.get('id', 'unknown')} from intent {intent_id}")
                else:
                    logger.warning(f"⚠️  Intent {intent_id} not found in graph for node {node.get('id', 'unknown')}")

            # Handle loop nodes (recursively fill children)
            if 'children' in node and node['children']:
                for child in node['children']:
                    if 'intent_id' in child:
                        child_intent_id = child['intent_id']

                        # Skip inferred/implicit nodes
                        if child_intent_id.startswith('implicit_') or child_intent_id.startswith('inferred_'):
                            logger.debug(f"Skipping inferred/implicit child node: {child.get('id', 'unknown')}")
                            continue

                        intent = graph.get_intent(child_intent_id)
                        if intent:
                            # Fill operations from Intent
                            operations_list = []
                            for op in intent.operations:
                                op_dict = op.model_dump(by_alias=True, exclude_none=True)
                                operations_list.append(op_dict)

                            child['operations'] = operations_list
                            filled_count += 1
                            logger.debug(f"✓ Filled operations for child node {child.get('id', 'unknown')} from intent {child_intent_id}")
                        else:
                            logger.warning(f"⚠️  Intent {child_intent_id} not found in graph for child node {child.get('id', 'unknown')}")

        logger.info(f"✓ Filled operations for {filled_count} nodes from Intent Graph")
