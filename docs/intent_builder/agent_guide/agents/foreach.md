# Foreach Agent Specification

**Purpose**: Loop over a list and execute steps for each item

**When to use**:
- Process multiple items (products, URLs, records)
- Iterate through extracted list data
- Collect data from multiple pages

---

## Basic Usage

```yaml
- id: "step-id"
  agent_type: "foreach"
  description: "Process each item in list"
  source: "{{item_list}}"
  item_var: "current_item"
  index_var: "item_index"
  max_iterations: 50
  loop_timeout: 900
  steps:
    - id: "process-item"
      agent_type: "scraper_agent"
      inputs:
        # Use item_var to access current item
        target_path: "{{current_item.url}}"
```

---

## Parameters

### Required

| Parameter | Type | Description |
|-----------|------|-------------|
| `source` | string | Source list variable (e.g., `"{{product_urls}}"`) |
| `item_var` | string | Name of loop variable for current item |
| `steps` | array | List of steps to execute for each item |

### Optional

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `index_var` | string | - | Variable for current index (0-based) |
| `max_iterations` | integer | 50 | Maximum items to process |
| `loop_timeout` | integer | 600 | Total timeout for all iterations (seconds) |

---

## Variable Scope

### Loop-local Variables

`item_var` and `index_var` are **only available inside the loop**:

```yaml
- id: "loop"
  agent_type: "foreach"
  source: "{{urls}}"
  item_var: "current_item"
  index_var: "idx"
  steps:
    - id: "use-item"
      inputs:
        url: "{{current_item.url}}"   # ✅ Valid - inside loop
        index: "{{idx}}"               # ✅ Valid - inside loop

- id: "after-loop"
  inputs:
    url: "{{current_item.url}}"       # ❌ INVALID - outside loop
```

### Persisting Data

To keep data after the loop, use `variable` agent to append to a global list:

```yaml
steps:
  # Initialize before loop
  - id: "init"
    agent_type: "variable"
    inputs:
      operation: "set"
      data:
        all_results: []  # Global variable
    outputs:
      all_results: "all_results"

  # Loop
  - id: "loop"
    agent_type: "foreach"
    source: "{{items}}"
    item_var: "item"
    steps:
      - id: "extract"
        agent_type: "scraper_agent"
        outputs:
          extracted_data: "item_data"

      - id: "save"
        agent_type: "variable"
        inputs:
          operation: "append"
          source: "{{all_results}}"
          data: "{{item_data}}"
        outputs:
          result: "all_results"  # Updates global variable

  # Use results after loop
  - id: "process-all"
    inputs:
      data: "{{all_results}}"  # ✅ Available - global variable
```

---

## Usage Scenarios

### Scenario 1: Extract Data from Multiple Pages

```yaml
- id: "init"
  agent_type: "variable"
  inputs:
    operation: "set"
    data:
      all_products: []

- id: "extract-urls"
  agent_type: "scraper_agent"
  outputs:
    extracted_data: "product_urls"

- id: "collect-details"
  agent_type: "foreach"
  description: "Visit each product page and extract details"
  source: "{{product_urls}}"
  item_var: "product"
  index_var: "idx"
  max_iterations: 20
  loop_timeout: 600
  steps:
    - id: "navigate"
      agent_type: "browser_agent"
      inputs:
        target_url: "{{product.url}}"

    - id: "extract"
      agent_type: "scraper_agent"
      inputs:
        extraction_method: "script"
        data_requirements:
          output_format:
            title: "Product title"
            price: "Product price"
      outputs:
        extracted_data: "product_info"

    - id: "append"
      agent_type: "variable"
      inputs:
        operation: "append"
        source: "{{all_products}}"
        data: "{{product_info}}"
      outputs:
        result: "all_products"
```

### Scenario 2: Process and Store Each Item

```yaml
- id: "process-items"
  agent_type: "foreach"
  source: "{{items}}"
  item_var: "item"
  steps:
    - id: "navigate"
      agent_type: "browser_agent"
      inputs:
        target_url: "{{item.url}}"

    - id: "extract"
      agent_type: "scraper_agent"
      outputs:
        extracted_data: "item_data"

    - id: "store"
      agent_type: "storage_agent"
      inputs:
        operation: "store"
        collection: "products"
        data: "{{item_data}}"
```

### Scenario 3: With Translation

```yaml
- id: "process-and-translate"
  agent_type: "foreach"
  source: "{{products}}"
  item_var: "product"
  steps:
    - id: "extract"
      agent_type: "scraper_agent"
      outputs:
        extracted_data: "raw_data"

    - id: "translate"
      agent_type: "text_agent"
      inputs:
        instruction: "Translate to Chinese"
        data:
          content: "{{raw_data}}"
      outputs:
        result: "translated_data"

    - id: "save"
      agent_type: "variable"
      inputs:
        operation: "append"
        source: "{{all_translated}}"
        data: "{{translated_data}}"
      outputs:
        result: "all_translated"
```

---

## Accessing Item Fields

If your source list contains objects:

```yaml
# Source: [{url: "...", title: "..."}, ...]

item_var: "product"

# Access fields:
inputs:
  url: "{{product.url}}"
  title: "{{product.title}}"
```

If your source list contains simple values:

```yaml
# Source: ["url1", "url2", ...]

item_var: "url"

# Use directly:
inputs:
  target_url: "{{url}}"
```

---

## Best Practices

### 1. Set Reasonable max_iterations

Don't process too many items - it wastes time and resources:

```yaml
max_iterations: 20   # Good for most cases
max_iterations: 1000 # Too many - will take forever
```

### 2. Set Appropriate loop_timeout

Calculate based on expected time per item:

```yaml
# If each iteration takes ~30 seconds
# For 20 items: 20 * 30 = 600 seconds
loop_timeout: 600
```

### 3. Initialize Collection Variables Before Loop

```yaml
- id: "init"
  agent_type: "variable"
  inputs:
    operation: "set"
    data:
      results: []  # Must initialize before append
```

### 4. Use Descriptive Variable Names

```yaml
item_var: "current_product"  # Good
item_var: "x"                # Bad

index_var: "product_index"   # Good
index_var: "i"               # Acceptable but less clear
```

---

## Error Handling

### Iteration Failure

If a step inside the loop fails, the loop continues with the next item by default.

### Timeout

If `loop_timeout` is exceeded, the loop stops and returns collected results.

### Empty Source

If source list is empty, the loop completes immediately without executing steps.

---

## Output

The foreach step itself doesn't produce direct output. Use `variable` agent inside the loop to collect results.

```yaml
# After loop completes:
# {{all_results}} contains all collected items
```

---

## Common Mistakes

### 1. Forgetting to Initialize

```yaml
# ❌ Wrong - appending to undefined variable
- id: "loop"
  steps:
    - id: "append"
      inputs:
        source: "{{results}}"  # Not initialized!
```

### 2. Using Loop Variables Outside

```yaml
# ❌ Wrong - item_var not available outside loop
- id: "after-loop"
  inputs:
    data: "{{current_item}}"  # Not available!
```

### 3. Not Persisting Results

```yaml
# ❌ Wrong - no append, data is lost after each iteration
- id: "loop"
  steps:
    - id: "extract"
      outputs:
        extracted_data: "item_data"  # Overwritten each iteration
```

---

**Version**: 1.0
**Last Updated**: 2025-11-20
