"""
Prompt Builder - Construct prompts for LLM to generate workflows

Builds comprehensive prompts including:
- System role and task description
- Workflow specification (simplified)
- Conversion requirements and rules
- Few-shot example
- MetaFlow input
"""


class PromptBuilder:
    """Build prompts for workflow generation"""

    def __init__(self):
        """Initialize PromptBuilder"""
        self.system_role = self._get_system_role()
        self.workflow_spec = self._get_workflow_spec()
        self.conversion_requirements = self._get_conversion_requirements()
        self.example = self._get_example()

    def build(self, metaflow_yaml: str) -> str:
        """
        Build complete prompt for workflow generation

        Args:
            metaflow_yaml: MetaFlow in YAML format

        Returns:
            Complete prompt string
        """
        prompt = f"""{self.system_role}

{self.workflow_spec}

{self.conversion_requirements}

{self.example}

---

# Task

Please convert the following MetaFlow to BaseAgent Workflow YAML:

```yaml
{metaflow_yaml}
```

# Output Requirements

- Output ONLY the workflow YAML, no explanations
- Ensure the YAML is valid and can be parsed
- Follow the workflow specification exactly
- Include all necessary fields (apiVersion, kind, metadata, steps, etc.)
"""
        return prompt

    def _get_system_role(self) -> str:
        """Get system role description"""
        return """# System Role

You are a Workflow Generation Expert. Your task is to convert MetaFlow (intent-based workflow descriptions) into executable BaseAgent Workflow YAML files.

Your responsibilities:
1. Understand user intents from MetaFlow operations
2. Infer appropriate agent types (tool_agent, scraper_agent, variable, etc.)
3. Infer complete data flow (variables, inputs, outputs)
4. Generate loops (foreach) from loop descriptions
5. Produce valid, executable workflow YAML"""

    def _get_workflow_spec(self) -> str:
        """Get simplified workflow specification"""
        return """# BaseAgent Workflow Specification (Simplified)

## Basic Structure

```yaml
apiVersion: "agentcrafter.io/v1"
kind: "Workflow"

metadata:
  name: "workflow-name"
  description: "Workflow description"
  version: "1.0.0"
  tags: ["tag1", "tag2"]

inputs:
  <input_name>:
    type: <type>
    description: <description>
    required: <bool>
    default: <value>

outputs:
  <output_name>:
    type: <type>
    description: <description>

config:
  max_execution_time: 1800
  enable_parallel: false
  enable_cache: true

steps:
  - id: <step_id>
    name: <step_name>
    agent_type: <agent_type>
    description: <description>
    agent_instruction: <instruction>
    inputs: {...}
    outputs: {...}
    timeout: 300
```

## Agent Types

1. **variable**: Variable management (initialize, set, append, etc.)
   - Operations: set, append, increment, decrement, etc.

2. **tool_agent**: Browser automation using browser_use tool
   - For: navigate, click, input, wait, scroll

3. **scraper_agent**: Data extraction from web pages
   - extraction_method: "script" | "llm"
   - data_requirements with output_format and sample_data

4. **storage_agent**: Persist data to database
   - operation: "store"
   - collection: collection name

5. **foreach**: Loop over a list
   - source: "{{variable}}"
   - item_var: variable name for current item
   - steps: list of steps in loop body

## Key Fields

- **agent_instruction**: What the agent should do (human-readable)
- **inputs**: Input parameters, can reference variables with {{variable}}
- **outputs**: Map output fields to variable names
- **source**: For foreach, the list variable to iterate over
- **item_var**: For foreach, the variable name for current item"""

    def _get_conversion_requirements(self) -> str:
        """Get conversion requirements and rules"""
        return """# Conversion Requirements

## 1. Data Flow Inference

MetaFlow does NOT explicitly contain all data flow. You MUST infer:

### Variable Initialization
- When you see a loop + store → initialize list variables at the beginning
- Example: all_product_urls = [], all_product_details = []

### Extract → Output Variables
- extract operation with target="field_name" → generates output variable
- The target field name becomes the output variable name

### Loop → Foreach Structure
```yaml
# MetaFlow
type: loop
source: "{{product_urls}}"
item_var: "current_product"

# Workflow
agent_type: foreach
source: "{{all_product_urls}}"
item_var: "current_product"
index_var: "product_index"
max_iterations: 50
```

### Data Collection Pattern
When you see loop + extract + store:
1. **init-vars** step: Initialize lists
2. **scrape-urls** step: Extract the source list
3. **save-urls** step: Save to variable
4. **foreach** step: Loop and collect data
   - Inside loop: scraper_agent + variable (append) + storage_agent

## 2. Operations → Agent Type

### navigate, click, wait
→ **tool_agent** with tools: ["browser_use"]

### extract operations
→ **scraper_agent** with:
- extraction_method: "script" (prefer) or "llm"
- data_requirements:
  - user_description: from intent_description
  - output_format: infer from extract target fields
  - sample_data: use extract.value as examples

### store operation
→ **storage_agent** with:
- operation: "store"
- collection: from params.collection
- data: reference to the data variable

## 3. Step Splitting

One intent can generate multiple workflow steps:
- Separate navigation from extraction
- Separate extraction from storage
- Use variable agent to manage state between steps

## 4. extraction_method Selection

Prefer "script" method when:
- There are precise xpath/selectors in operations
- Extracting simple fields (title, price, etc.)

Use "llm" method when:
- Need semantic understanding
- Complex data extraction

## 5. Variable Naming

Use semantic variable names:
- product_list, product_urls, all_product_details
- current_product, product_info
- page_state, scrape_message

## 6. Final Response

Workflow MUST output a variable called "final_response" in one of the steps.
This is required by the workflow system."""

    def _get_example(self) -> str:
        """Get few-shot example"""
        return """# Example

## Input MetaFlow

```yaml
version: "1.0"
task_description: "Collect coffee product information from first page"

nodes:
  - id: node_1
    intent_name: "NavigateToSite"
    intent_description: "Navigate to e-commerce site"
    operations:
      - type: navigate
        url: "https://example.com/coffee"

  - id: node_2
    intent_name: "ExtractProductList"
    intent_description: "Extract all product URLs"
    operations:
      - type: extract
        target: "product_urls"
        element:
          xpath: "//article//a"
        value: []
    outputs:
      product_urls: "product_urls"

  - id: node_3
    type: loop
    source: "{{product_urls}}"
    item_var: "current_product"
    description: "Iterate through products and collect info"
    children:
      - id: node_3_1
        intent_name: "CollectProductInfo"
        intent_description: "Extract product title and price"
        operations:
          - type: navigate
            url: "{{current_product.url}}"
          - type: extract
            target: "title"
            value: "Product Title"
          - type: extract
            target: "price"
            value: "19.99"
          - type: store
            params:
              collection: "products"
              fields: ["title", "price"]
```

## Output Workflow

```yaml
apiVersion: "agentcrafter.io/v1"
kind: "Workflow"

metadata:
  name: "coffee-collection-workflow"
  description: "Collect coffee product information from first page"
  version: "1.0.0"
  tags: ["scraper", "coffee", "collection"]

inputs:
  max_products:
    type: "integer"
    description: "Maximum products to collect"
    required: false
    default: 10

outputs:
  product_details:
    type: "array"
    description: "Collected product information"
  final_response:
    type: "string"
    description: "Completion message"

config:
  max_execution_time: 1800
  enable_parallel: false
  enable_cache: true

steps:
  - id: "init-vars"
    name: "Initialize variables"
    agent_type: "variable"
    description: "Initialize data collection variables"
    agent_instruction: "Initialize product collection variables"
    inputs:
      operation: "set"
      data:
        all_product_urls: []
        all_product_details: []
    outputs:
      all_product_urls: "all_product_urls"
      all_product_details: "all_product_details"
    timeout: 10

  - id: "navigate-to-site"
    name: "Navigate to coffee page"
    agent_type: "tool_agent"
    description: "Open coffee products page"
    agent_instruction: "Navigate to https://example.com/coffee"
    inputs:
      tools: ["browser_use"]
    timeout: 30

  - id: "extract-product-urls"
    name: "Extract product URLs"
    agent_type: "scraper_agent"
    description: "Extract all product URLs from the page"
    agent_instruction: "Extract all product URLs from coffee page"
    inputs:
      extraction_method: "script"
      data_requirements:
        user_description: "Extract all product URLs"
        output_format:
          url: "Product URL"
    outputs:
      extracted_data: "product_urls"
    timeout: 30

  - id: "save-urls"
    name: "Save product URLs"
    agent_type: "variable"
    description: "Save extracted URLs to variable"
    agent_instruction: "Save product URLs"
    inputs:
      operation: "set"
      data:
        all_product_urls: "{{product_urls}}"
    outputs:
      all_product_urls: "all_product_urls"
    timeout: 10

  - id: "collect-product-details"
    name: "Collect product details"
    agent_type: "foreach"
    description: "Iterate through products and collect information"
    source: "{{all_product_urls}}"
    item_var: "current_product"
    index_var: "product_index"
    max_iterations: 10
    loop_timeout: 900
    steps:
      - id: "scrape-product"
        name: "Scrape product information"
        agent_type: "scraper_agent"
        description: "Extract product details"
        agent_instruction: "Visit product page and extract title and price"
        inputs:
          extraction_method: "script"
          target_path: "{{current_product.url}}"
          data_requirements:
            user_description: "Extract product title and price"
            output_format:
              title: "Product title"
              price: "Product price"
            sample_data:
              - title: "Product Title"
                price: "19.99"
        outputs:
          extracted_data: "product_info"
        timeout: 45

      - id: "append-product"
        name: "Add product to list"
        agent_type: "variable"
        description: "Append product info to collection"
        agent_instruction: "Add product to list"
        inputs:
          operation: "append"
          source: "{{all_product_details}}"
          data: "{{product_info}}"
        outputs:
          result: "all_product_details"
        timeout: 10

      - id: "store-product"
        name: "Store product to database"
        agent_type: "storage_agent"
        description: "Persist product information"
        agent_instruction: "Store product to database"
        inputs:
          operation: "store"
          collection: "products"
          data: "{{product_info}}"
        outputs:
          message: "store_message"
        timeout: 10

  - id: "prepare-output"
    name: "Prepare final output"
    agent_type: "variable"
    description: "Organize collection results"
    agent_instruction: "Prepare final output"
    inputs:
      operation: "set"
      data:
        product_details: "{{all_product_details}}"
        final_response: "Successfully collected {{product_index}} products"
    outputs:
      product_details: "product_details"
      final_response: "final_response"
    timeout: 10
```"""
