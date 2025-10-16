"""
Prompt Builder - Construct prompts for LLM to generate workflows

Builds comprehensive prompts including:
- System role and task description
- Workflow specification (simplified)
- Conversion requirements and rules
- Few-shot example
- MetaFlow input
"""
from pathlib import Path


class PromptBuilder:
    """Build prompts for workflow generation"""

    def __init__(self):
        """Initialize PromptBuilder"""
        # Load external specs first (needed by _get_workflow_spec)
        self._load_agent_specs()

        self.system_role = self._get_system_role()
        self.workflow_spec = self._get_workflow_spec()
        self.conversion_requirements = self._get_conversion_requirements()
        self.example = self._get_example()

    def _load_agent_specs(self):
        """Load agent specifications from external files"""
        # Find specs directory relative to this file
        # prompt_builder.py is at: intent_builder/generators/prompt_builder.py
        # specs are at: docs/baseagent/scraper_agent_spec.md
        project_root = Path(__file__).parent.parent.parent.parent
        specs_dir = project_root / "docs" / "baseagent"

        # Load scraper_agent spec
        scraper_spec_file = specs_dir / "scraper_agent_spec.md"
        if scraper_spec_file.exists():
            with open(scraper_spec_file, 'r', encoding='utf-8') as f:
                self.scraper_agent_spec = f.read()
        else:
            # Fallback to basic inline spec if file not found
            print(f"Warning: scraper_agent_spec.md not found at {scraper_spec_file}, using fallback")
            self.scraper_agent_spec = """**Purpose**: Extract structured data from web pages

**DOM Scope Rules**:
- Use "full" when user needs ALL matching elements (keywords: "所有", "列表", "all")
- Use "partial" for specific content extraction

**Example**:
```yaml
- agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    dom_scope: "full"  # Use "full" for lists, "partial" for details
```"""

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

- Output the workflow YAML in a markdown code block using ```yaml
- Do not add any explanations outside the code block
- Ensure the YAML is valid and can be parsed
- Follow the workflow specification exactly
- Include all necessary fields (apiVersion, kind, metadata, steps, etc.)

Example format:
```yaml
apiVersion: "agentcrafter.io/v1"
kind: "Workflow"
...
```
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
        """Get complete workflow specification with agent details"""
        spec = """# BaseAgent Workflow Specification

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
    type: <type>              # string | integer | boolean | array | object
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

## Agent Types & Specifications

### 1. variable - Variable Management
**Purpose**: Initialize, set, append, or manipulate variables

```yaml
- id: "step-id"
  agent_type: "variable"
  agent_instruction: "Initialize/set/append variables"
  inputs:
    operation: "set"          # set | append | increment | decrement
    data:                     # For set operation
      var_name: value
    source: "{{list_var}}"    # For append operation
    data: "{{item}}"          # Item to append
  outputs:
    result: "variable_name"
```

### 2. scraper_agent - Web Data Extraction

{scraper_agent_spec}

### 3. tool_agent - Browser Automation
**Purpose**: Execute browser operations (navigate, click, input, etc.)

```yaml
- id: "step-id"
  agent_type: "tool_agent"
  agent_instruction: "Navigate/click/input on page"
  inputs:
    task_description: "Specific task to accomplish"
    allowed_tools: ["browser_use"]
    confidence_threshold: 0.7
  outputs:
    result: "result_var"
    tool_used: "tool_var"
```

### 4. storage_agent - Data Persistence
**Purpose**: Store, query, or export data to database

```yaml
- id: "step-id"
  agent_type: "storage_agent"
  agent_instruction: "Store/query/export data"
  inputs:
    operation: "store"              # "store" | "query" | "export"
    collection: "collection_name"   # Table name (auto-suffixed with user_id)
    data: "{{variable}}"            # Data to store (for store operation)
  outputs:
    message: "message_var"
    rows_stored: "count_var"
```

### 5. foreach - List Iteration
**Purpose**: Loop over a list and execute steps for each item

```yaml
- id: "step-id"
  agent_type: "foreach"
  description: "Loop description"
  source: "{{list_variable}}"       # List to iterate
  item_var: "current_item"          # Variable name for current item
  index_var: "item_index"           # Variable name for current index
  max_iterations: 50
  loop_timeout: 600
  steps:
    - id: "substep"
      agent_type: "scraper_agent"
      inputs:
        target_path: "{{current_item.url}}"
      # ...
```

## Variable References

- Use `{{variable_name}}` to reference variables
- Access object fields: `{{object.field}}`
- Access array elements: `{{array[0]}}`
- Available in: inputs, agent_instruction, condition fields"""

        # Replace scraper_agent spec placeholder with loaded spec
        spec = spec.replace("{scraper_agent_spec}", self.scraper_agent_spec)

        return spec

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

### When to Use scraper_agent vs tool_agent

**scraper_agent**: For simple navigation + data extraction
- Can directly visit URL via `target_path` parameter
- Automatically handles page loading and extraction
- Use for: direct URL access → extract data

**tool_agent**: For complex browser interactions ONLY
- Use when: login, authentication, form submission, dynamic content waiting
- Use `allowed_tools: ["browser_use"]` for browser automation

**IMPORTANT Optimization**:
If MetaFlow contains multiple click/navigate operations but the intent is just to reach a final URL:
→ Skip intermediate clicks, use **scraper_agent** with the final URL directly!

Example:
```yaml
# MetaFlow: Multiple clicks to navigate
operations:
  - type: click  # Click menu button
  - type: click  # Click category link
  - type: navigate  # Final URL: https://site.com/category

# Optimized Workflow: Direct navigation
- agent_type: "scraper_agent"
  inputs:
    target_path: "https://site.com/category"  # Jump to final URL directly!
```

### Operation Mapping

**navigate operation (URL is known)**
→ **scraper_agent** with target_path (NO tool_agent needed!)

**Multiple clicks that end with navigate (navigation intent)**
→ Analyze: Is the real intent just to reach a URL?
→ YES: Use **scraper_agent** with final URL directly (skip clicks!)
→ NO (login/auth required): Use **tool_agent** with browser_use

**Complex interactions (login, form, dynamic content)**
→ **tool_agent** with tools: ["browser_use"]

**extract operations**
→ **scraper_agent** with:
- extraction_method: "script" (prefer) or "llm"
- data_requirements:
  - user_description: from intent_description
  - output_format: combine ALL extract targets from same page into ONE output_format
  - sample_data: use extract.value as examples (format depends on extraction type - see below)

**CRITICAL - sample_data Format Rules**:
- **Extracting a LIST of items** (value is []): sample_data MUST be a list
  ```yaml
  sample_data:
    - url: "https://example.com/product1"
    - url: "https://example.com/product2"
  ```
- **Extracting a SINGLE object** (multiple fields): sample_data MUST be a dict
  ```yaml
  sample_data:
    title: "Product Title"
    price: "19.99"
  ```

**Important - Multiple Extracts**:
If multiple extract operations target the same page, combine them into ONE scraper_agent with multiple fields in output_format.

```yaml
# MetaFlow: Multiple extracts
operations:
  - type: extract
    target: "title"
    value: "Coffee Maker"
  - type: extract
    target: "price"
    value: "$99.99"
  - type: extract
    target: "rating"
    value: "4.5"

# Workflow: ONE scraper_agent with all fields
- agent_type: "scraper_agent"
  inputs:
    data_requirements:
      output_format:
        title: "Product title"
        price: "Product price"
        rating: "Product rating"
      sample_data:
        title: "Coffee Maker"
        price: "$99.99"
        rating: "4.5"
  outputs:
    extracted_data: "product_info"  # Contains all fields
```

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

  # Simple URL access → scraper_agent handles it directly!
  - id: "extract-product-urls"
    name: "Extract product URLs"
    agent_type: "scraper_agent"
    description: "Navigate to coffee page and extract all product URLs"
    agent_instruction: "Visit coffee category page and extract all product URLs"
    inputs:
      target_path: "https://example.com/coffee"  # scraper_agent navigates automatically
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
              title: "Product Title"
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
