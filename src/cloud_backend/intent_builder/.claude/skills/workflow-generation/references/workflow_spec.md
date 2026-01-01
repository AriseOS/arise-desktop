# BaseAgent Workflow Specification

**Version**: v2.0
**Last Updated**: 2025-10-08

## Overview

BaseAgent Workflow is a YAML-based declarative workflow definition system for orchestrating multi-agent collaboration with control flow and data flow capabilities.

## Workflow Structure

### Basic Format

```yaml
apiVersion: "ami.io/v1"
kind: "Workflow"

metadata:
  name: "workflow-name"
  description: "Workflow description"
  version: "1.0.0"
  author: "Author name"
  tags: ["tag1", "tag2"]

inputs:
  <input_definitions>

outputs:
  <output_definitions>

config:
  <workflow_config>

steps:
  <step_definitions>
```

## Metadata Section

```yaml
metadata:
  name: "my-workflow"              # Required: Workflow name (lowercase-with-dashes)
  description: "What this workflow does"  # Required: Brief description
  version: "1.0.0"                 # Required: Semantic version
  author: "Your Name"              # Optional: Author name
  tags: ["scraper", "automation"]  # Optional: Tags for categorization
```

## Inputs/Outputs

### Input Definition
```yaml
inputs:
  user_input:
    type: "string"              # string | integer | boolean | array | object
    description: "User input message"
    required: true              # Optional, default: false
    default: "Hello"            # Optional: Default value
```

### Output Definition
```yaml
outputs:
  final_result:
    type: "string"
    description: "Final workflow result"
```

## Configuration

```yaml
config:
  max_execution_time: 3600       # Max workflow execution time (seconds)
  enable_parallel: false         # Enable parallel step execution
  enable_cache: true             # Enable step result caching
  timeout_strategy: "fail"       # fail | continue | continue_on_error
```

## Steps

### Supported Agent Types

1. **scraper_agent** - Web scraping with browser automation
2. **tool_agent** - Tool calling with confidence-based selection
3. **storage_agent** - Data persistence (store/query/export)
4. **text_agent** - Text generation
5. **code_agent** - Code execution
6. **variable_agent** - Variable manipulation
7. **foreach** - List iteration (control flow)
8. **if/while** - Conditional execution (control flow)

### Step Structure

```yaml
- id: "step-id"                    # Required: Unique step identifier
  name: "Step Name"                # Required: Human-readable name
  agent_type: "scraper_agent"      # Required: Agent type
  description: "What this step does"  # Optional: Step description

    Natural language instruction for the agent

  inputs:                          # Optional: Step inputs
    <key>: <value_or_variable>

  outputs:                         # Optional: Step outputs
    <output_key>: <variable_name>

  condition: "{{variable}} == true"  # Optional: Conditional execution
  depends_on: ["step-id"]          # Optional: Step dependencies
  timeout: 60                      # Optional: Step timeout (seconds)
  retry_count: 1                   # Optional: Retry attempts
```

## Variable System

### Variable Reference Syntax
```yaml
"{{variable_name}}"              # Reference variable in context
"{{object.field}}"               # Access object field
"{{array[0]}}"                   # Access array element
```

### Variable Scope
- **Global Scope**: Variables set in step outputs are available to all subsequent steps
- **Loop Scope**: Loop variables (`item_var`, `index_var`) are only available within loop body
- **Input Scope**: Workflow inputs are available to all steps

### Setting Variables
```yaml
- id: "set-var"
  agent_type: "variable"
  inputs:
    operation: "set"
    data:
      my_var: "value"
      another_var: 123
  outputs:
    my_var: "my_var"
    another_var: "another_var"
```

## Control Flow

### Conditional Execution

**Simple Condition** (on any step):
```yaml
- id: "conditional-step"
  agent_type: "tool_agent"
  condition: "{{task_type}} == 'browser'"  # Only execute if condition is true
```

**If-Else Branch**:
```yaml
- id: "if-branch"
  control_type: "if"
  condition: "{{has_task}} == true"
  then_steps:
    - id: "handle-task"
      agent_type: "tool_agent"
  else_steps:
    - id: "no-task"
      agent_type: "text_agent"
```

### Loop Control

**Foreach Loop** (iterate over list):
```yaml
- id: "process-items"
  agent_type: "foreach"
  source: "{{product_list}}"      # Required: List variable to iterate
  item_var: "current_item"        # Optional: Current item variable (default: "item")
  index_var: "item_index"         # Optional: Current index variable (default: "index")
  max_iterations: 100             # Optional: Max iterations (default: 100)
  loop_timeout: 600               # Optional: Total loop timeout in seconds (default: 600)

  steps:
    - id: "process-item"
      agent_type: "scraper_agent"
      inputs:
        target_path: "{{current_item.url}}"  # Access item fields
        index: "{{item_index}}"              # Access current index
```

**While Loop** (condition-based):
```yaml
- id: "conversation-loop"
  control_type: "while"
  condition: "{{continue_chat}} == true"
  max_iterations: 10
  loop_timeout: 300
  then_steps:
    - id: "chat-turn"
      agent_type: "interactive_agent"
```

## Agent-Specific Specifications

### text_agent

For text generation tasks (summarization, translation, Q&A):

```yaml
- id: "generate-summary"
  agent_type: "text_agent"
  inputs:
    instruction: "Summarize the following content in Chinese"  # Required
    content: "{{extracted_text}}"  # Input data to process
  outputs:
    result: "summary"  # Output variable
```

**Required fields:**
- `instruction`: The task instruction for the LLM

For detailed agent-specific input/output formats and configurations, see:
- [ScraperAgent Specification](./scraper_agent_spec.md)
- [ToolAgent Specification](./tool_agent_spec.md)
- [StorageAgent Specification](./storage_agent_spec.md)

## Complete Workflow Example

```yaml
apiVersion: "ami.io/v1"
kind: "Workflow"

metadata:
  name: "product-scraper"
  description: "Scrape product list and details, then store to database"
  version: "1.0.0"
  tags: ["scraper", "ecommerce"]

inputs:
  category_url:
    type: "string"
    description: "Product category URL"
    required: true

outputs:
  products:
    type: "array"
    description: "Scraped product list"
  summary:
    type: "string"
    description: "Scraping summary"

config:
  max_execution_time: 1800
  enable_cache: true

steps:
  # Step 1: Scrape product URLs from list page
  - id: "scrape-urls"
    name: "Scrape Product URLs"
    agent_type: "scraper_agent"

    inputs:
      target_path: "{{category_url}}"
      extraction_method: "script"
      dom_scope: "full"
      data_requirements:
        user_description: "Extract product URLs"
        output_format:
          url: "Product detail page URL"
        sample_data:
          - url: "https://example.com/product/123"

    outputs:
      extracted_data: "product_urls"

    timeout: 60

  # Step 2: Initialize results array
  - id: "init-results"
    name: "Initialize Results"
    agent_type: "variable"

    inputs:
      operation: "set"
      data:
        all_products: []

    outputs:
      all_products: "all_products"

  # Step 3: Loop through URLs and scrape details
  - id: "scrape-details"
    name: "Scrape Product Details"
    agent_type: "foreach"
    source: "{{product_urls}}"
    item_var: "product"
    index_var: "index"
    max_iterations: 10

    steps:
      # 3.1: Scrape product details
      - id: "scrape-detail"
        name: "Scrape Product Info"
        agent_type: "scraper_agent"

        inputs:
          target_path: "{{product.url}}"
          extraction_method: "llm"
          data_requirements:
            user_description: "Extract product information"
            output_format:
              name: "Product name"
              price: "Product price"
              rating: "Product rating"
            sample_data:
              - name: "Example Product"
                price: "99.99"
                rating: "4.5"

        outputs:
          extracted_data: "product_detail"

      # 3.2: Append to results
      - id: "append-result"
        name: "Append Result"
        agent_type: "variable"

        inputs:
          operation: "append"
          source: "{{all_products}}"
          data: "{{product_detail}}"

        outputs:
          result: "all_products"

      # 3.3: Store to database
      - id: "store-product"
        name: "Store Product"
        agent_type: "storage_agent"

        inputs:
          operation: "store"
          collection: "products"
          data: "{{product_detail}}"

        outputs:
          message: "store_message"

  # Step 4: Prepare final output
  - id: "prepare-output"
    name: "Prepare Output"
    agent_type: "variable"

    inputs:
      operation: "set"
      data:
        products: "{{all_products}}"
        summary: "Successfully scraped {{index}} products"

    outputs:
      products: "products"
      summary: "summary"
```

## Best Practices

### 1. Variable Management
- Use descriptive variable names (`product_urls` not `urls`)
- Initialize arrays/objects before appending
- Clean up temporary variables when done

### 2. Error Handling
- Set appropriate timeouts for each step
- Use retry_count for unstable operations
- Use condition to skip steps when data is missing

### 3. Performance
- Use `extraction_method: "script"` for repeated scraping (faster)
- Enable caching for idempotent operations
- Set reasonable max_iterations for loops

### 4. Maintainability
- Add clear descriptions to steps
- Use meaningful step IDs
- Group related operations in foreach loops

## Execution Order

1. Steps execute in the order defined in `steps` array
2. Steps with `condition` are evaluated before execution (skip if false)
3. Steps with `depends_on` wait for dependency completion
4. Control flow steps (if/while/foreach) manage their own sub-steps
5. Variables are updated after each step's `outputs` are processed

## Limitations

1. **No nested foreach**: foreach cannot be nested (use sequential foreach instead)
2. **No parallel execution**: Steps execute sequentially (unless `enable_parallel: true`)
3. **Variable immutability**: Variables cannot be modified in-place (use variable agent)
4. **No function calls**: No user-defined functions (use separate workflow steps)
