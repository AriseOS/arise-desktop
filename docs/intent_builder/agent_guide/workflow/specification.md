# Workflow Specification

BaseAgent Workflow is the executable format that defines a sequence of agent steps to accomplish a task.

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
    inputs: {...}
    outputs: {...}
    timeout: 300
```

## Required Fields

### Top-level

| Field | Description | Required |
|-------|-------------|----------|
| `apiVersion` | API version, must be `"agentcrafter.io/v1"` | Yes |
| `kind` | Must be `"Workflow"` | Yes |
| `metadata` | Workflow metadata | Yes |
| `steps` | List of workflow steps | Yes |
| `inputs` | Workflow input parameters | No |
| `outputs` | Workflow output definitions | No |
| `config` | Execution configuration | No |

### Metadata

| Field | Description | Required |
|-------|-------------|----------|
| `name` | Workflow name (kebab-case) | Yes |
| `description` | Human-readable description | No |
| `version` | Semantic version | No |
| `tags` | List of tags for categorization | No |

### Step

| Field | Description | Required |
|-------|-------------|----------|
| `id` | Unique step identifier | Yes |
| `name` | Human-readable step name | Yes |
| `agent_type` | Type of agent to execute | Yes |
| `description` | Step description | No |
| `inputs` | Step input parameters | Depends on agent |
| `outputs` | Step output variables | No |
| `timeout` | Execution timeout in seconds | No |

## Agent Types

Available agent types:

| Agent Type | Purpose |
|------------|---------|
| `variable` | Variable management (set, append, increment) |
| `browser_agent` | Browser navigation and interactions |
| `scraper_agent` | Data extraction from web pages |
| `text_agent` | Text processing using LLM |
| `autonomous_browser_agent` | Autonomous web task execution |
| `storage_agent` | Data persistence |
| `code_agent` | Code execution |
| `foreach` | Loop iteration |

See `agents/*.md` for detailed documentation of each agent type.

## Variable References

Use `{{variable_name}}` syntax:

```yaml
inputs:
  target_url: "{{extracted_link.url}}"
  data:
    content: "{{product_info}}"
```

### Access Patterns

- Simple: `{{variable}}`
- Field access: `{{object.field}}`
- Nested: `{{object.nested.value}}`
- Array index: `{{array[0]}}`

## Step Examples

### Variable Step

```yaml
- id: "init-vars"
  name: "Initialize variables"
  agent_type: "variable"
  inputs:
    operation: "set"
    data:
      all_products: []
      count: 0
  outputs:
    all_products: "all_products"
    count: "count"
  timeout: 10
```

### Browser Agent Step

```yaml
- id: "navigate-to-site"
  name: "Navigate to website"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://example.com"
  timeout: 30
```

### Scraper Agent Step

```yaml
- id: "extract-products"
  name: "Extract product list"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements:
      user_description: "Extract all product URLs from the listing page"
      output_format:
        url: "Product URL"
      xpath_hints:
        url: "//article//a[@class='product-link']"
  outputs:
    extracted_data: "product_urls"
  timeout: 45
```

### Text Agent Step

```yaml
- id: "translate-content"
  name: "Translate to Chinese"
  agent_type: "text_agent"
  inputs:
    instruction: "Translate the following product information to Chinese"
    data:
      content: "{{product_info}}"
  outputs:
    result: "translated_info"
  timeout: 60
```

### Storage Agent Step

```yaml
- id: "store-product"
  name: "Store product data"
  agent_type: "storage_agent"
  inputs:
    operation: "store"
    collection: "products"
    data: "{{product_info}}"
  outputs:
    message: "store_message"
    rows_stored: "rows_count"
  timeout: 10
```

### Foreach Step

```yaml
- id: "process-all-products"
  name: "Process each product"
  agent_type: "foreach"
  description: "Iterate through products and collect details"
  source: "{{product_urls}}"
  item_var: "current_product"
  index_var: "product_index"
  max_iterations: 50
  loop_timeout: 900
  steps:
    - id: "navigate-to-product"
      agent_type: "browser_agent"
      inputs:
        target_url: "{{current_product.url}}"
      timeout: 30

    - id: "extract-details"
      agent_type: "scraper_agent"
      inputs:
        extraction_method: "script"
        data_requirements:
          output_format:
            title: "Product title"
            price: "Product price"
      outputs:
        extracted_data: "product_info"
      timeout: 45
```

## Data Flow Patterns

### Initialize → Extract → Process → Store

```yaml
steps:
  - id: "init"
    agent_type: "variable"
    inputs:
      operation: "set"
      data:
        results: []
    outputs:
      results: "results"

  - id: "navigate"
    agent_type: "browser_agent"
    inputs:
      target_url: "https://example.com"

  - id: "extract"
    agent_type: "scraper_agent"
    outputs:
      extracted_data: "raw_data"

  - id: "process"
    agent_type: "text_agent"
    inputs:
      data:
        content: "{{raw_data}}"
    outputs:
      result: "processed_data"

  - id: "store"
    agent_type: "storage_agent"
    inputs:
      data: "{{processed_data}}"
```

### Loop with Accumulation

```yaml
steps:
  - id: "init"
    agent_type: "variable"
    inputs:
      operation: "set"
      data:
        all_items: []

  - id: "extract-list"
    agent_type: "scraper_agent"
    outputs:
      extracted_data: "item_urls"

  - id: "loop"
    agent_type: "foreach"
    source: "{{item_urls}}"
    item_var: "item"
    steps:
      - id: "extract-item"
        agent_type: "scraper_agent"
        outputs:
          extracted_data: "item_data"

      - id: "append"
        agent_type: "variable"
        inputs:
          operation: "append"
          source: "{{all_items}}"
          data: "{{item_data}}"
        outputs:
          result: "all_items"
```

## Important Notes

### final_response

Workflow should output a variable called `final_response`:

```yaml
- id: "prepare-output"
  agent_type: "variable"
  inputs:
    operation: "set"
    data:
      final_response: "Successfully collected 10 products"
  outputs:
    final_response: "final_response"
```

### Variable Scope in Foreach

Loop variables (`item_var`, `index_var`) are only available inside the loop:

```yaml
- id: "loop"
  agent_type: "foreach"
  item_var: "current_item"  # Only available in nested steps
  steps:
    - id: "use-item"
      inputs:
        url: "{{current_item.url}}"  # Valid

- id: "after-loop"
  inputs:
    url: "{{current_item.url}}"  # INVALID - not available here
```

To persist data, use `variable` agent to append to a global list inside the loop.

### Timeout Values

Recommended timeout values:
- `variable`: 10 seconds
- `browser_agent`: 30-60 seconds
- `scraper_agent`: 30-60 seconds
- `text_agent`: 60-120 seconds
- `storage_agent`: 10-30 seconds
- `foreach`: Set `loop_timeout` (e.g., 900 seconds)

### Step Naming

Use descriptive kebab-case IDs:
- `navigate-to-homepage`
- `extract-product-list`
- `translate-content`
- `store-results`
