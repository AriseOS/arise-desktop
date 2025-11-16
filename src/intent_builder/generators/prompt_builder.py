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

        # Load browser_agent spec
        browser_spec_file = specs_dir / "browser_agent_spec.md"
        if browser_spec_file.exists():
            with open(browser_spec_file, 'r', encoding='utf-8') as f:
                self.browser_agent_spec = f.read()
        else:
            # Fallback to basic inline spec if file not found
            print(f"Warning: browser_agent_spec.md not found at {browser_spec_file}, using fallback")
            self.browser_agent_spec = """**Purpose**: Navigate to pages and perform scrolling without data extraction

**When to use**:
- Intent is pure navigation (no data extraction)
- Intent description contains: "navigate", "enter", "visit", "go to"

**Example**:
```yaml
- agent_type: "browser_agent"
  inputs:
    target_url: "https://example.com/page"
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

# CRITICAL - XPath Hints Generation

**IMPORTANT**: When generating scraper_agent steps, you MUST extract xpath information from the MetaFlow operations and provide xpath_hints.

**How to generate xpath_hints**:
1. **Read task_description** from MetaFlow (first field in YAML above) - it describes what user demonstrated
2. **Read operations** in each MetaFlow node - they contain element.xpath from user's actual browser actions
3. **Map xpath to field names**: For each extract operation, create xpath_hints mapping:
   ```yaml
   # MetaFlow operation:
   operations:
     - type: extract
       target: "product_name"
       element:
         xpath: "//h1[@class='product-title']"

   # Workflow xpath_hints:
   xpath_hints:
     product_name: "//h1[@class='product-title']"
   ```

4. **Combine multiple extracts from same page**: If multiple extract operations target the same page, combine their xpaths into one scraper_agent step's xpath_hints

**Example**:
```yaml
# MetaFlow has 3 extract operations on product page:
operations:
  - type: extract
    target: "name"
    element: {{xpath: "//h1[@class='title']"}}
  - type: extract
    target: "price"
    element: {{xpath: "//span[@class='price']"}}
  - type: extract
    target: "rating"
    element: {{xpath: "//div[@class='rating']"}}

# Workflow should generate ONE scraper_agent with:
- agent_type: "scraper_agent"
  inputs:
    data_requirements:
      xpath_hints:
        name: "//h1[@class='title']"
        price: "//span[@class='price']"
        rating: "//div[@class='rating']"
```

**WHY this is CRITICAL**:
- XPath hints come from user's actual demonstrated actions
- They provide exact DOM selectors, dramatically improving scraper accuracy
- Without xpath_hints, scraper_agent must guess element locations

# Output Requirements

- Output the workflow YAML in a markdown code block using ```yaml
- Do not add any explanations outside the code block
- Ensure the YAML is valid and can be parsed
- Follow the workflow specification exactly
- Include all necessary fields (apiVersion, kind, metadata, steps, etc.)
- **MUST include xpath_hints in scraper_agent steps** when extract operations have xpath data

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
2. Infer appropriate agent types (browser_agent, scraper_agent, variable, storage_agent, etc.)
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

### 2. browser_agent - Browser Navigation

{browser_agent_spec}

### 3. scraper_agent - Web Data Extraction

{scraper_agent_spec}

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

### 6. foreach - List Iteration
**Purpose**: Loop over a list and execute steps for each item

**IMPORTANT - Variable Scope**:
- `item_var` and `index_var` are ONLY available inside the foreach loop
- These variables are automatically cleaned up after the loop completes
- They CANNOT be accessed in steps after the foreach step
- If you need data from the loop, use variable agent to append to a global list

```yaml
- id: "step-id"
  agent_type: "foreach"
  description: "Loop description"
  source: "{{list_variable}}"       # List to iterate
  item_var: "current_item"          # Loop-local variable for current item
  index_var: "item_index"           # Loop-local variable for current index
  max_iterations: 50
  loop_timeout: 600
  steps:
    - id: "substep"
      agent_type: "scraper_agent"
      inputs:
        target_path: "{{current_item.url}}"  # Valid inside loop
      outputs:
        extracted_data: "product_info"

    - id: "save-to-global"
      agent_type: "variable"
      agent_instruction: "Save to global variable"
      inputs:
        operation: "append"
        source: "{{all_products}}"  # Global variable
        data: "{{product_info}}"    # This becomes global
      outputs:
        result: "all_products"      # Global variable persists

# After foreach completes:
# {{current_item}} is NOT available (cleaned up)
# {{item_index}} is NOT available (cleaned up)
# {{all_products}} IS available (global variable)
```

## Variable References

- Use `{{variable_name}}` to reference variables
- Access object fields: `{{object.field}}`
- Access array elements: `{{array[0]}}`
- Available in: inputs, agent_instruction, condition fields"""

        # Replace agent spec placeholders with loaded specs
        spec = spec.replace("{browser_agent_spec}", self.browser_agent_spec)
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

## 2. Core Workflow Logic - Step Relationships

**CRITICAL**: Understand the execution flow and data dependencies between steps.

### Basic Rule: Each step builds on previous steps

When generating workflow steps, always ask:
1. **Where is the browser currently?** (which page was accessed in previous step)
2. **What data is available?** (what was extracted/generated in previous steps)
3. **What does this step need?** (where to operate, what data to use)

### Key Principle: Separation of Concerns

**IMPORTANT**:
- `browser_agent`: ONLY for navigation (no data extraction)
- `scraper_agent`: ONLY for data extraction from **current page** (no navigation)

**scraper_agent does NOT have navigation capability**:
- It always extracts from the current page that browser is on
- If you need to extract from a different page, use browser_agent to navigate first

### Common Pattern: Navigate → Extract

```
Step 1: browser_agent - Navigate to page A
Step 2: scraper_agent - Extract data from page A (current page)
Step 3: browser_agent - Navigate to page B
Step 4: scraper_agent - Extract data from page B (current page)
```

### Example: ProductHunt Daily → Weekly

```yaml
# Step 1: Navigate to homepage
- id: "navigate-to-homepage"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://www.producthunt.com/"

# Step 2: Extract daily link from homepage (current page)
- id: "extract-daily-link"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements:
      xpath_hints:
        daily_url: "//a[text()='Launch archive']"
  outputs:
    extracted_data: "daily_link"

# Step 3: Navigate to daily page
- id: "navigate-to-daily"
  agent_type: "browser_agent"
  inputs:
    target_url: "{{daily_link.daily_url}}"

# Step 4: Extract weekly link from daily page (current page)
- id: "extract-weekly-link"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements:
      xpath_hints:
        weekly_url: "//a[text()='Weekly']"
  outputs:
    extracted_data: "weekly_link"

# Step 5: Navigate to weekly page
- id: "navigate-to-weekly"
  agent_type: "browser_agent"
  inputs:
    target_url: "{{weekly_link.weekly_url}}"
```

**Why this approach is better**:
- ✅ Clear separation: browser navigates, scraper extracts
- ✅ No confusion about which URL to use (scraper always uses current page)
- ✅ Easier to understand and maintain

---

## 3. Click → Navigate Pattern Handling

**When MetaFlow contains `click → navigate` operations, generate TWO steps:**

This pattern appears when user clicks a link to navigate to another page. Since the link URL may contain dynamic parts (dates, IDs, etc.), we extract it first then navigate.

### Pattern Recognition

```yaml
# MetaFlow shows:
operations:
  - type: click
    url: "https://site.com/current-page"  # Browser is on this page
    element:
      xpath: "//a[@class='link']"
      href: "https://site.com/target-page?date=2025-10-29"  # May be dynamic
  - type: navigate
    url: "https://site.com/target-page?date=2025-10-29"
```

### Generated Workflow Steps

**Step 1: Extract the link (scraper_agent)**

Extract the URL from the element that was clicked. The browser is already on the page from previous navigation.

```yaml
- id: "extract-{target}-link"
  agent_type: "scraper_agent"
  agent_instruction: "Extract the {target} link from the current page"
  inputs:
    extraction_method: "script"
    data_requirements:
      user_description: "Extract the {target} link"
      output_format:
        target_url: "{Target} page URL"
      xpath_hints:
        target_url: "{xpath}"  # From click operation's element.xpath
  outputs:
    extracted_data: "{target}_link"
```

**Step 2: Navigate (browser_agent)**

Navigate to the extracted URL.

```yaml
- id: "navigate-to-{target}"
  agent_type: "browser_agent"
  agent_instruction: "Navigate to the {target} page"
  inputs:
    target_url: "{{{target}_link.target_url}}"  # Reference extracted URL
```

### Complete Example

```yaml
# MetaFlow input:
# (Assume browser is already on daily page from previous step)
node_3:
  intent_description: "Navigate to the current week's leaderboard"
  operations:
    - type: click
      url: "https://www.producthunt.com/leaderboard/daily/2025/10/29"  # Current page
      element:
        xpath: "//a[contains(text(), 'Weekly')]"
        textContent: "Weekly"
        href: "https://www.producthunt.com/leaderboard/weekly/2025/44"
    - type: navigate
      url: "https://www.producthunt.com/leaderboard/weekly/2025/44"

# Generated workflow:
# Step 1: Extract link from current page
- id: "extract-weekly-link"
  agent_type: "scraper_agent"
  agent_instruction: "Extract the Weekly leaderboard link from the current page"
  inputs:
    extraction_method: "script"
    data_requirements:
      user_description: "Extract the Weekly leaderboard link"
      output_format:
        weekly_url: "Weekly leaderboard page URL"
      xpath_hints:
        weekly_url: "//a[contains(text(), 'Weekly')]"
  outputs:
    extracted_data: "weekly_link"
  timeout: 30

# Step 2: Navigate to extracted URL
- id: "navigate-to-weekly"
  agent_type: "browser_agent"
  agent_instruction: "Navigate to the weekly leaderboard page"
  inputs:
    target_url: "{{weekly_link.weekly_url}}"
  timeout: 30
```

**Why this approach:**
- ✅ scraper_agent extracts from current page (no navigation needed)
- ✅ Extracts the actual current link from the page (not hardcoded)
- ✅ Works regardless of date/time changes in URL
- ✅ Uses xpath from user's actual click operation
- ✅ Clear separation of concerns

## 3. Operations → Agent Type

### When to Use browser_agent vs scraper_agent

**CRITICAL - Clear Separation of Concerns:**

**browser_agent**: ONLY for navigation
- Use when intent is to navigate to a page
- Intent description contains: "navigate", "enter", "visit", "go to"
- Has `navigate` operations in MetaFlow
- NO data extraction capability
- Example: "Navigate to coffee category page"
```yaml
- agent_type: "browser_agent"
  inputs:
    target_url: "https://site.com/category"
```

**scraper_agent**: ONLY for data extraction from current page
- Use when intent is to extract/collect data
- Intent has `extract` operations in MetaFlow
- Extracts from the page browser is currently on
- NO navigation capability (no `target_path` parameter)
- Example: "Extract product information"
```yaml
# Browser must be on the target page already
- agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements:
      output_format:
        title: "Product title"
```

**CRITICAL - Navigation Must Come First:**
If MetaFlow has both navigate and extract operations:
1. Generate browser_agent step for navigation
2. Then generate scraper_agent step for extraction

```yaml
# MetaFlow: navigate + extract
operations:
  - type: navigate
    url: "https://site.com/page"
  - type: extract
    target: "data"

# Workflow: TWO steps
- id: "navigate-to-page"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://site.com/page"

- id: "extract-data"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    # No target_path! Uses current page from browser_agent
```

**CRITICAL - Preserve Navigation Paths**:
- **DO NOT** skip navigation steps
- Each navigation intent generates a browser_agent step
- This prevents anti-bot detection and maintains proper session flow

### Core Principles - How to Choose Agent Type

**Choose agent based on the Intent's semantic goal**:

1. **If the intent goal is to NAVIGATE to a page** → Use **browser_agent**
   - Example: "Navigate to coffee category page"
   - Example: "Go to homepage"

2. **If the intent goal is to SCROLL for loading more content** → Use **browser_agent**
   - Example: "Scroll down to load more products"
   - Note: Scroll for browsing/viewing is usually filtered out in intent extraction phase

3. **If the intent goal is to EXTRACT/COLLECT data** → Use **scraper_agent**
   - Example: "Extract product information"
   - Example: "Get all product URLs from the list"

**Agent Capabilities**:
- **browser_agent**: Navigation and page interactions (navigate to URL, scroll)
- **scraper_agent**: Data extraction from current page only

**extract operations**
→ **scraper_agent** with:
- extraction_method: "script" (DEFAULT - prefer script unless explicitly need LLM)
- data_requirements:
  - user_description: from intent_description + include website name from context (URL domain or intent prefix)
  - output_format: combine ALL extract targets from same page into ONE output_format
  - sample_data: use extract.value as examples (format depends on extraction type - see below)
  - xpath_hints: Extract xpath from operation.element.xpath and map to field names
    ```yaml
    # Extract xpath from MetaFlow operations:
    xpath_hints:
      target_field: "operation.element.xpath"

    # Example:
    # MetaFlow operation: {type: extract, target: "url", element: {xpath: "//a[@class='link']"}}
    # → xpath_hints: {url: "//a[@class='link']"}
    ```

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

**CRITICAL - Always prefer "script" method by default!**

Use "script" method when (DEFAULT):
- MetaFlow operations contain xpath/selectors (MUST use script!)
- Extracting list data (URLs, items, etc.)
- Extracting detail page fields (title, price, rating, etc.)
- Any structured data extraction with known fields

Only use "llm" method when:
- User explicitly requests semantic understanding
- Extremely complex/unstructured data that cannot be scripted
- When there's no consistent DOM pattern to follow

**Rule**: If MetaFlow extract operation has `element.xpath`, MUST use `extraction_method: "script"`

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
          xpath: "//article//a[@class='product-link']"
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
            element:
              xpath: "//h1[@class='product-title']"
            value: "Product Title"
          - type: extract
            target: "price"
            element:
              xpath: "//span[@class='price']"
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

  # Navigate first, then extract
  - id: "navigate-to-coffee"
    name: "Navigate to coffee category"
    agent_type: "browser_agent"
    description: "Navigate to coffee category page"
    agent_instruction: "Navigate to coffee category page"
    inputs:
      target_url: "https://example.com/coffee"
    timeout: 30

  - id: "extract-product-urls"
    name: "Extract product URLs"
    agent_type: "scraper_agent"
    description: "Extract all product URLs from current page"
    agent_instruction: "Extract all product URLs from the coffee category page"
    inputs:
      extraction_method: "script"
      data_requirements:
        user_description: "Extract all product URLs"
        output_format:
          url: "Product URL"
        xpath_hints:
          url: "//article//a[@class='product-link']"
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
      - id: "navigate-to-product"
        name: "Navigate to product page"
        agent_type: "browser_agent"
        description: "Navigate to product detail page"
        agent_instruction: "Navigate to product detail page"
        inputs:
          target_url: "{{current_product.url}}"
        timeout: 30

      - id: "scrape-product"
        name: "Scrape product information"
        agent_type: "scraper_agent"
        description: "Extract product details from current page"
        agent_instruction: "Extract product title and price from the current page"
        inputs:
          extraction_method: "script"
          data_requirements:
            user_description: "Extract product title and price"
            output_format:
              title: "Product title"
              price: "Product price"
            sample_data:
              title: "Product Title"
              price: "19.99"
            xpath_hints:
              title: "//h1[@class='product-title']"
              price: "//span[@class='price']"
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
