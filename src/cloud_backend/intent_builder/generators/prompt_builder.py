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
        # prompt_builder.py is at: src/cloud_backend/intent_builder/generators/prompt_builder.py
        # specs are at: docs/base_app/scraper_agent_spec.md
        project_root = Path(__file__).parent.parent.parent.parent.parent
        specs_dir = project_root / "docs" / "base_app"

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

5. **CRITICAL - XPath hints for implicit/inferred extract nodes with PLACEHOLDER**:

   When you encounter an extract node with `xpath: <PLACEHOLDER>` that appears BEFORE a loop:
   - This node was inferred to extract a list for the loop to iterate over
   - Look at the **first child node inside the loop** that has a click/navigate operation
   - Use that child node's click xpath as the xpath_hint for the list extraction
   - The click xpath points to ONE item; for list extraction, use the same xpath to get ALL items

   **Example Pattern**:
   ```yaml
   # MetaFlow structure:
   - id: node_3
     intent_description: "Extract all product URLs (Inferred)"
     operations:
       - type: extract
         element:
           xpath: <PLACEHOLDER>  # ← Need to fill this
           tagName: A
         target: product_urls

   - id: node_4
     type: loop
     source: "{{product_urls}}"
     children:
       - id: node_4_1
         intent_description: "Navigate to product detail"
         operations:
           - type: click
             element:
               xpath: "//*[@id='list']/div[1]/a/span"  # ← Use this xpath!
               tagName: SPAN

   # Workflow generation:
   - id: "extract-product-urls"
     agent_type: "scraper_agent"
     inputs:
       extraction_method: "script"  # Use script since we have xpath_hint from loop child
       data_requirements:
         xpath_hints:
           url: "//*[@id='list']/div[1]/a/span"  # ← Copied from loop child's click xpath
         output_format:
           url: "Product URL from the list"
   ```

   **Why this works**:
   - The loop child's click xpath shows which element the user clicked (one item)
   - For list extraction, we use the same xpath pattern to extract all similar items
   - This provides a concrete xpath hint even when the implicit node had PLACEHOLDER
   - Since we have xpath_hint, use `extraction_method: "script"` (faster and more reliable)

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
apiVersion: "ami.io/v1"
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
apiVersion: "ami.io/v1"
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
  max_execution_time: 3600
  enable_parallel: false
  enable_cache: true

steps:
  - id: <step_id>
    name: <step_name>
    agent_type: <agent_type>
    description: <description>
    inputs: {...}  # Agent execution parameters
    outputs: {...}
    timeout: 300
```

## Agent Types & Specifications

### 1. variable - Variable Management
**Purpose**: Initialize, set, append, or manipulate variables

```yaml
- id: "step-id"
  agent_type: "variable"
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
  inputs:
    operation: "store"              # "store" | "query" | "export"
    collection: "collection_name"   # Table name (auto-suffixed with user_id)
    data: "{{variable}}"            # Data to store (for store operation)
  outputs:
    message: "message_var"
    rows_stored: "count_var"
```

### 5. text_agent - Text Generation & Processing
**Purpose**: Process text, summarize data, translate content, or generate new text using LLM.

```yaml
- id: "step-id"
  agent_type: "text_agent"
  inputs:
    instruction: "Summarize the following text"  # Task instruction
    data:                                        # Input data
      content: "{{variable_name}}"
  outputs:
    result: "summary_var"                       # Output variable
```

### 6. foreach - List Iteration
**Purpose**: Loop over a list and execute steps for each item

**IMPORTANT - Variable Scope**:
- `item_var` and `index_var` are ONLY available inside the foreach loop
- These variables are automatically cleaned up after the loop completes
- They CANNOT be accessed in steps after the foreach step
- If you need data from the loop, use variable agent to append to a global list

**IMPORTANT - Do NOT set max_iterations**:
- By default, foreach iterates over ALL items in the source list
- Do NOT add `max_iterations` field unless the user explicitly requests a limit
- The system will iterate through every item in the list automatically

```yaml
- id: "step-id"
  agent_type: "foreach"
  description: "Loop description"
  source: "{{list_variable}}"       # List to iterate
  item_var: "current_item"          # Loop-local variable for current item
  index_var: "item_index"           # Loop-local variable for current index
  loop_timeout: 600                 # Timeout in seconds
  steps:
    - id: "substep"
      agent_type: "scraper_agent"
      inputs:
        target_path: "{{current_item.url}}"  # Valid inside loop
      outputs:
        extracted_data: "product_info"

    - id: "save-to-global"
      agent_type: "variable"
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
- Available in: inputs, condition fields"""

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
loop_timeout: 600
# Do NOT add max_iterations - iterate all items by default
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

### CRITICAL Pattern: Scroll Operations

**When MetaFlow contains a scroll operation**:

```yaml
# MetaFlow scroll operation:
- type: scroll
  direction: "down"
  distance: 1000
```

**MUST generate browser_agent with interaction_steps**:

```yaml
# CORRECT ✅
- id: "scroll-to-load"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 5
  timeout: 60

# WRONG ❌ - Only target_url, no interaction_steps!
- id: "scroll-to-load"
  agent_type: "browser_agent"
  inputs:
    target_url: "{{some_url}}"  # ← This ONLY navigates, doesn't scroll!
  timeout: 60
```

**Key Rules**:
1. Scroll operations REQUIRE `interaction_steps` with `action_type: scroll`
2. If browser is already on the page, do NOT provide `target_url` (would reload page)
3. Calculate `num_pages` based on scroll distance: `num_pages = distance / 500` (approx)

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

**CRITICAL: Treat click + navigate as ONE user intent**

When MetaFlow contains sequential `click → navigate` operations, they represent ONE action: clicking a link to navigate.

**How to make the decision:**
- Look at the `navigate.url` to determine if the target URL is stable or dynamic
- The `click.element.href` may or may not be present - that's OK
- `navigate.url` is the authoritative source for the actual destination URL

**When MetaFlow contains `click → navigate` operations, choose ONE of these approaches:**

### Approach A: Direct Navigation (Preferred when URL is stable)

**Use direct navigation when navigate.url is:**
- A fixed, stable URL path (e.g., `/products`, `/about`, `/category/electronics`)
- Not containing dynamic date/time components (e.g., `2025/10/29`, `week=44`)
- Not containing session-specific parameters (e.g., `sessionid=`, `token=`)
- Not containing user-specific IDs that change per visit

**Pattern Recognition for Direct Navigation:**

```yaml
# MetaFlow shows:
operations:
  - type: click
    element:
      xpath: "//a[text()='Products']"
      # href may or may not exist - doesn't matter
  - type: navigate
    url: "https://site.com/products"  # ← Check this URL (stable, no dynamic parts)

# Generated workflow: Single step
- id: "navigate-to-products"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://site.com/products"  # Use navigate.url directly
  timeout: 30
```

**Examples of stable URLs that should use direct navigation:**
- `https://www.producthunt.com/leaderboard` (fixed path)
- `https://site.com/categories/electronics` (fixed category)
- `https://example.com/about` (static page)
- `https://app.com/settings/profile` (fixed settings path)

### Approach B: Extract then Navigate (When URL is dynamic)

**Use extraction when navigate.url contains:**
- Date components (e.g., `/2025/10/29`, `/weekly/2025/44`, `/daily/2025/11/27`)
- Query parameters that may change (e.g., `?date=today`, `?ref=header`)
- IDs that represent current state (e.g., `/post/12345` where ID changes)

**Pattern Recognition for Extraction:**

```yaml
# MetaFlow shows:
operations:
  - type: click
    url: "https://site.com/current-page"  # Browser is on this page
    element:
      xpath: "//a[text()='Weekly']"
      # href may or may not exist - doesn't matter
  - type: navigate
    url: "https://site.com/leaderboard/weekly/2025/48"  # ← Check this URL (contains dynamic week number!)
```

**Generated Workflow Steps:**

**Step 1: Extract the link (scraper_agent)**

```yaml
- id: "extract-{target}-link"
  agent_type: "scraper_agent"
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

```yaml
- id: "navigate-to-{target}"
  agent_type: "browser_agent"
  inputs:
    target_url: "{{{target}_link.target_url}}"  # Reference extracted URL
```

### Complete Examples

**Example 1: Direct Navigation (stable URL)**

```yaml
# MetaFlow input:
node_1:
  intent_description: "Navigate to the products page"
  operations:
    - type: click
      element:
        xpath: "//a[text()='Products']"
        textContent: "Products"
        # Note: href may or may not exist - doesn't matter
    - type: navigate
      url: "https://site.com/products"  # ← Decision point: stable URL, no dates/IDs

# Decision: navigate.url is stable → Use direct navigation
# Generated workflow: Single step
- id: "navigate-to-products"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://site.com/products"  # Use navigate.url directly
  timeout: 30
```

**Example 2: Extract then Navigate (dynamic URL with date)**

```yaml
# MetaFlow input:
node_2:
  intent_description: "Navigate to the daily leaderboard"
  operations:
    - type: click
      element:
        xpath: "//a[text()='Launch archive']"
        textContent: "Launch archive"
        # Note: href field is missing - that's OK!
    - type: navigate
      url: "https://www.producthunt.com/leaderboard/daily/2025/11/27"  # ← Decision point: contains date!

# Decision: navigate.url contains date (2025/11/27) → MUST extract
# Generated workflow: Two steps
- id: "extract-daily-link"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements:
      user_description: "Extract the daily leaderboard link"
      output_format:
        daily_url: "Daily leaderboard URL"
      xpath_hints:
        daily_url: "//a[text()='Launch archive']"  # From click.element.xpath
  outputs:
    extracted_data: "daily_link"
  timeout: 30

- id: "navigate-to-daily"
  agent_type: "browser_agent"
  inputs:
    target_url: "{{daily_link.daily_url}}"  # Use extracted URL (will get current date)
  timeout: 30
```

**Example 3: Extract then Navigate (dynamic URL with week number)**

```yaml
# MetaFlow input:
node_3:
  intent_description: "Navigate to the weekly leaderboard"
  operations:
    - type: click
      element:
        xpath: "//a[text()='Weekly']"
        textContent: "Weekly"
        href: "https://www.producthunt.com/leaderboard/weekly/2025/48"  # href exists
    - type: navigate
      url: "https://www.producthunt.com/leaderboard/weekly/2025/48"  # ← Decision point: contains week number!

# Decision: navigate.url contains week number (2025/48) → MUST extract
# Generated workflow: Two steps
- id: "extract-weekly-link"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements:
      user_description: "Extract the Weekly leaderboard link"
      output_format:
        weekly_url: "Weekly leaderboard page URL"
      xpath_hints:
        weekly_url: "//a[text()='Weekly']"
  outputs:
    extracted_data: "weekly_link"
  timeout: 30

- id: "navigate-to-weekly"
  agent_type: "browser_agent"
  inputs:
    target_url: "{{weekly_link.weekly_url}}"  # Use extracted URL (will get current week)
  timeout: 30
```

**Decision Guidelines:**
- **Always check `navigate.url`** to determine if URL is stable or dynamic
- `click.element.href` is optional - may or may not exist
- ✅ Use **direct navigation** for stable URLs → simpler, faster, more reliable
- ✅ Use **extraction** for dynamic URLs (with dates/IDs) → adapts to current page state
- ❌ **NEVER remove or modify parts of navigate.url** (e.g., removing `/daily/2025/11/27`)
- ⚠️ When in doubt, prefer extraction (safer but slower)

## Agent Type Selection - Core Principles

### Understanding Agent Capabilities

Each agent has specific capabilities. Choose based on **what the task fundamentally requires**, not based on keywords in the description.

**browser_agent** - Browser Control
- **Capability**: Control the browser to navigate to URLs and interact with pages (scroll, wait)
- **Cannot**: Extract or process data
- **Use when**: The task requires moving to a different page or triggering page interactions
- **Inputs**: `target_url` for navigation, `interaction_steps` for interactions like scroll

**scraper_agent** - Data Extraction
- **Capability**: Extract structured data from the current page using scripts or LLM
- **Cannot**: Navigate to other pages or perform interactions
- **Use when**: The task requires getting data from the page the browser is currently on
- **Inputs**: `data_requirements` with extraction specifications

**text_agent** - Semantic Text Processing
- **Capability**: Process text using LLM for tasks requiring language understanding
- **Cannot**: Access web pages or interact with browser
- **Use when**: The task requires transforming data in ways that need semantic understanding
  - The transformation cannot be done by simple code (not just reformatting or filtering)
  - Examples: translating between languages, summarizing content, analyzing patterns/sentiment, generating insights
- **Inputs**: `instruction` describing the processing task, `data` containing the content to process

**autonomous_browser_agent** - Exploratory Web Tasks
- **Capability**: Autonomously navigate and interact with web pages to achieve a goal
- **Cannot**: Work with pre-defined paths; it explores and decides actions itself
- **Use when**: The task requires exploration WITHOUT any concrete recorded operations
  - The MetaFlow node has `autonomous_task` operation type
  - OR the node is marked `(Inferred)` AND has NO standard operations (navigate/extract/scroll/etc.)
  - Examples: "Find CEO's LinkedIn profile" (no recorded steps), "Search for related products" (exploratory)
- **DO NOT use when**: The node has `extract`, `navigate`, `scroll`, or other concrete operations (even if marked as Inferred)
- **Inputs**: `task` describing the goal, `max_actions` limiting exploration steps

**storage_agent** - Data Persistence
- **Capability**: Store data to database or export to files
- **Cannot**: Process or transform data
- **Use when**: The task requires saving extracted data

**variable** - Variable Management
- **Capability**: Set, append, or manipulate workflow variables
- **Cannot**: Process data semantically or access external resources
- **Use when**: The task requires simple data operations (initialize lists, append items, set values)

### Decision Framework

When mapping a MetaFlow node to workflow steps, **follow this strict priority order**:

**Step 1: Check if the node has concrete operations** (highest priority)

If the node contains any of these operation types, use the corresponding agent **regardless of `(Inferred)` marker**:
- `navigate` operation → **browser_agent** for navigation
- `extract` operation → **scraper_agent** for extraction (use LLM mode if xpath is PLACEHOLDER)
- `scroll` operation → **browser_agent** with interaction_steps
- `store` operation → **storage_agent**
- `text_process` operation → **text_agent**

For nodes with multiple operation types (e.g., navigate + extract):
- Generate multiple steps in sequence
- Example: browser_agent for navigate, then scraper_agent for extract

**Step 2: Only if the node has NO concrete operations, check `(Inferred)` marker**

If the node is marked `(Inferred)` AND has placeholder/autonomous operations:
- `autonomous_task` operation → **autonomous_browser_agent**
- Text processing without concrete steps → **text_agent**

**Key Rule**: Operations type **always wins** over `(Inferred)` marker. The `(Inferred)` marker only indicates the node was inferred, not that it should use autonomous_browser_agent.

**Example - Inferred Extract Node**:
```yaml
# MetaFlow node (marked as Inferred with extract operation):
- id: node_3
  intent_id: implicit_extract_product_list
  intent_name: ExtractProductList
  intent_description: "Extract all product URLs from weekly leaderboard (Inferred)"
  operations:
    - type: extract
      element:
        xpath: <PLACEHOLDER>
        tagName: A
      target: product_urls
      value: []

# Workflow step: Use scraper_agent (NOT autonomous_browser_agent)
# Because the node HAS extract operation
- id: "extract-product-urls"
  agent_type: "scraper_agent"  # ✓ Correct - has extract operation
  inputs:
    extraction_method: "script"  # Use script (not llm) - see xpath hints section for PLACEHOLDER handling
    data_requirements:
      output_format:
        url: "Product URL"
      xpath_hints:
        url: "..."  # Will be filled from loop child's click xpath (see section 5 of xpath hints)
```

### Important Rules

**Separation of Concerns**:
- browser_agent handles navigation, scraper_agent handles extraction
- Never skip navigation steps - they maintain session state
- scraper_agent always works on the current page

**Scroll Operations**:
- Use browser_agent with `interaction_steps`, NOT just `target_url`
- If already on the page, do NOT provide `target_url` (would reload)
```yaml
# CORRECT - scroll on current page
inputs:
  interaction_steps:
    - action_type: "scroll"
      parameters:
        down: true
        num_pages: 5

# WRONG - this just navigates, doesn't scroll
inputs:
  target_url: "{{url}}"
```

**Navigation + Extraction Pattern**:
```yaml
# MetaFlow: navigate + extract
operations:
  - type: navigate
    url: "https://site.com/page"
  - type: extract
    target: "data"

# Workflow: TWO separate steps
- id: "navigate-to-page"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://site.com/page"

- id: "extract-data"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements: ...
```

**extract operations**
→ **scraper_agent** with:
- extraction_method: "script" (DEFAULT - prefer script unless explicitly need LLM)
- data_requirements:

  **CRITICAL - Field Coverage Rule**:
  - You MUST include ALL extract operations from MetaFlow in output_format
  - The operations represent what the user actually selected/demonstrated - do NOT skip any
  - Even if user_query only mentions some fields, you MUST extract ALL fields from operations
  - Missing fields will cause data loss and incomplete results

  user_description: from intent_description + include website name + CRITICAL: include SEMANTIC ANCHORS (e.g., "from container with header 'Top 10'", "from the 'Results' section"). Do not just say "Extract X", say "Extract X from [Semantic Container]"
  - output_format: combine ALL extract targets from same page into ONE output_format (MUST include every extract operation)
  - sample_data: use extract.value as examples (format depends on extraction type - see below)
  - xpath_hints: Extract xpath from operation.element.xpath and map to field names (MUST include xpath for every field)
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
If multiple extract operations target the same page, combine them into ONE scraper_agent with multiple fields in output_format. **You MUST include ALL extract operations - count the extracts in MetaFlow and ensure the same count appears in output_format.**

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
- Workflow has xpath_hints (even if MetaFlow xpath was PLACEHOLDER)
- Extracting list data (URLs, items, etc.)
- Extracting detail page fields (title, price, rating, etc.)
- Any structured data extraction with known fields

Only use "llm" method when:
- User explicitly requests semantic understanding
- Extremely complex/unstructured data that cannot be scripted
- When there's no consistent DOM pattern to follow
- **AND** no xpath_hints are available

**Decision Rules**:
1. If MetaFlow extract operation has real `element.xpath` (not PLACEHOLDER) → MUST use `extraction_method: "script"`
2. If you generated xpath_hints from any source (same node, loop child, etc.) → MUST use `extraction_method: "script"`
3. Only if no xpath data exists at all → consider "llm" (rare case)

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
apiVersion: "ami.io/v1"
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
  max_execution_time: 3600
  enable_parallel: false
  enable_cache: true

steps:
  - id: "init-vars"
    name: "Initialize variables"
    agent_type: "variable"
    description: "Initialize data collection variables"
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
    inputs:
      target_url: "https://example.com/coffee"
    timeout: 30

  # Scroll to load more products (if page has infinite scroll)
  - id: "scroll-to-load-all"
    name: "Load all products"
    agent_type: "browser_agent"
    description: "Scroll down to trigger infinite scroll and load all products"
    inputs:
      interaction_steps:
        - action_type: "scroll"
          parameters:
            down: true
            num_pages: 3
    timeout: 45

  - id: "extract-product-urls"
    name: "Extract product URLs"
    agent_type: "scraper_agent"
    description: "Extract all product URLs from current page"
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
    loop_timeout: 900
    steps:
      - id: "navigate-to-product"
        name: "Navigate to product page"
        agent_type: "browser_agent"
        description: "Navigate to product detail page"
        inputs:
          target_url: "{{current_product.url}}"
        timeout: 30

      - id: "scrape-product"
        name: "Scrape product information"
        agent_type: "scraper_agent"
        description: "Extract product details from current page"
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
    inputs:
      operation: "set"
      data:
        product_details: "{{all_product_details}}"
        final_response: "Successfully collected products"
    outputs:
      product_details: "product_details"
      final_response: "final_response"
    timeout: 10
```"""
