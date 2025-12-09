# Variable Agent Specification

**Purpose**: Initialize, set, append, or manipulate workflow variables

**When to use**:
- Initialize variables at workflow start
- Accumulate results (append to list)
- Set or update variable values
- Simple counter operations

**When NOT to use**:
- Semantic text processing → Use `text_agent`
- Complex data transformation → Use `code_agent`
- Data persistence → Use `storage_agent`

---

## Basic Usage

```yaml
- id: "step-id"
  agent_type: "variable"
  name: "Set variable"
  description: "Initialize or update variables"
  inputs:
    operation: "set"
    data:
      my_variable: "value"
  outputs:
    my_variable: "my_variable"
  timeout: 10
```

---

## Operations

### 1. Set Operation

Initialize or overwrite variables.

```yaml
- id: "init-vars"
  agent_type: "variable"
  inputs:
    operation: "set"
    data:
      all_products: []
      count: 0
      status: "running"
  outputs:
    all_products: "all_products"
    count: "count"
    status: "status"
```

### 2. Append Operation

Add an item to a list.

```yaml
- id: "append-item"
  agent_type: "variable"
  inputs:
    operation: "append"
    source: "{{all_products}}"
    data: "{{current_product}}"
  outputs:
    result: "all_products"
```

### 3. Increment Operation

Increase a counter by 1.

```yaml
- id: "increment-count"
  agent_type: "variable"
  inputs:
    operation: "increment"
    source: "{{count}}"
  outputs:
    result: "count"
```

### 4. Decrement Operation

Decrease a counter by 1.

```yaml
- id: "decrement-count"
  agent_type: "variable"
  inputs:
    operation: "decrement"
    source: "{{count}}"
  outputs:
    result: "count"
```

### 5. Slice Operation

Extract a subset of a list from a starting index or value.

```yaml
# Slice from index 10 onwards
- id: "slice-by-index"
  agent_type: "variable"
  inputs:
    operation: "slice"
    source: "{{all_items}}"
    start: 10
  outputs:
    result: "filtered_items"

# Slice from matching item onwards
- id: "slice-from-product"
  agent_type: "variable"
  inputs:
    operation: "slice"
    source: "{{product_urls}}"
    start_value: "https://example.com/products/target-product"
    match_field: "url"
  outputs:
    result: "filtered_urls"
```

### 6. Filter Operation

Filter list items by matching criteria.

```yaml
# Filter by exact match
- id: "filter-exact"
  agent_type: "variable"
  inputs:
    operation: "filter"
    source: "{{all_items}}"
    field: "status"
    equals: "active"
  outputs:
    result: "active_items"

# Filter by substring
- id: "filter-contains"
  agent_type: "variable"
  inputs:
    operation: "filter"
    source: "{{product_urls}}"
    field: "url"
    contains: "electronics"
  outputs:
    result: "electronics_urls"
```

---

## Input Parameters

### For `set` operation

| Parameter | Type | Description |
|-----------|------|-------------|
| `operation` | string | Must be `"set"` |
| `data` | object | Key-value pairs to set |

### For `append` operation

| Parameter | Type | Description |
|-----------|------|-------------|
| `operation` | string | Must be `"append"` |
| `source` | string | Source list variable (e.g., `"{{my_list}}"`) |
| `data` | any | Item to append |

### For `increment`/`decrement` operations

| Parameter | Type | Description |
|-----------|------|-------------|
| `operation` | string | `"increment"` or `"decrement"` |
| `source` | string | Source counter variable (e.g., `"{{count}}"`) |
| `value` | number | (Optional) Amount to increment/decrement, default: 1 |

### For `slice` operation

| Parameter | Type | Description |
|-----------|------|-------------|
| `operation` | string | Must be `"slice"` |
| `source` | string | Source list variable (e.g., `"{{my_list}}"`) |
| `start` | number | (Option 1) Start index (0-based) |
| `start_value` | string | (Option 2) Value to match for start position |
| `match_field` | string | Field name to match (required with `start_value`) |

### For `filter` operation

| Parameter | Type | Description |
|-----------|------|-------------|
| `operation` | string | Must be `"filter"` |
| `source` | string | Source list variable (e.g., `"{{my_list}}"`) |
| `field` | string | Field name to check |
| `equals` | string | (Option 1) Exact value to match |
| `contains` | string | (Option 2) Substring to search for |

---

## Usage Scenarios

### Scenario 1: Initialize Workflow Variables

**Purpose**: Set up variables at the start of workflow

```yaml
- id: "init-vars"
  agent_type: "variable"
  name: "Initialize variables"
  description: "Set up collection variables"
  inputs:
    operation: "set"
    data:
      all_product_urls: []
      all_product_details: []
      processed_count: 0
  outputs:
    all_product_urls: "all_product_urls"
    all_product_details: "all_product_details"
    processed_count: "processed_count"
  timeout: 10
```

### Scenario 2: Collect Results in Loop

**Purpose**: Accumulate extracted data inside a foreach loop

```yaml
- id: "collect-items"
  agent_type: "foreach"
  source: "{{item_urls}}"
  item_var: "current_item"
  steps:
    - id: "extract"
      agent_type: "scraper_agent"
      outputs:
        extracted_data: "item_data"

    - id: "append-to-list"
      agent_type: "variable"
      inputs:
        operation: "append"
        source: "{{all_items}}"
        data: "{{item_data}}"
      outputs:
        result: "all_items"
```

### Scenario 3: Save Extracted URLs

**Purpose**: Store extracted URLs in a variable for later use

```yaml
- id: "save-urls"
  agent_type: "variable"
  name: "Save URLs"
  description: "Store extracted URLs in variable"
  inputs:
    operation: "set"
    data:
      product_urls: "{{extracted_urls}}"
  outputs:
    product_urls: "product_urls"
  timeout: 10
```

### Scenario 4: Prepare Final Output

**Purpose**: Set the final_response at the end of workflow

```yaml
- id: "prepare-output"
  agent_type: "variable"
  name: "Prepare output"
  description: "Set final workflow output"
  inputs:
    operation: "set"
    data:
      product_details: "{{all_product_details}}"
      final_response: "Successfully collected {{processed_count}} products"
  outputs:
    product_details: "product_details"
    final_response: "final_response"
  timeout: 10
```

### Scenario 5: Track Progress

**Purpose**: Count processed items

```yaml
- id: "loop"
  agent_type: "foreach"
  source: "{{items}}"
  item_var: "item"
  steps:
    - id: "process"
      # ... process item

    - id: "update-count"
      agent_type: "variable"
      inputs:
        operation: "increment"
        source: "{{processed_count}}"
      outputs:
        result: "processed_count"
```

---

## Common Patterns

### Initialize → Loop → Output

```yaml
steps:
  # Initialize
  - id: "init"
    agent_type: "variable"
    inputs:
      operation: "set"
      data:
        results: []

  # Loop and collect
  - id: "loop"
    agent_type: "foreach"
    steps:
      - id: "extract"
        # ... extract data
        outputs:
          extracted_data: "item"

      - id: "collect"
        agent_type: "variable"
        inputs:
          operation: "append"
          source: "{{results}}"
          data: "{{item}}"
        outputs:
          result: "results"

  # Output
  - id: "output"
    agent_type: "variable"
    inputs:
      operation: "set"
      data:
        final_response: "Collected {{results.length}} items"
    outputs:
      final_response: "final_response"
```

### Copy/Transform Variable

```yaml
- id: "copy-data"
  agent_type: "variable"
  inputs:
    operation: "set"
    data:
      backup: "{{original_data}}"
      filtered: "{{original_data}}"  # Can be same or transformed
  outputs:
    backup: "backup"
    filtered: "filtered"
```

---

## Output Format

**Set operation**:
```yaml
{
  "all_products": [],
  "count": 0
}
```

**Append operation**:
```yaml
{
  "result": [... existing items ..., new_item]
}
```

**Increment operation**:
```yaml
{
  "result": 1  # Previous value + 1
}
```

---

## Best Practices

### 1. Initialize at Start

Always initialize list variables before appending:

```yaml
# First step
- id: "init"
  inputs:
    operation: "set"
    data:
      my_list: []  # Initialize as empty list
```

### 2. Use Meaningful Variable Names

```yaml
data:
  all_product_urls: []      # Good
  all_product_details: []   # Good
  x: []                     # Bad - not descriptive
```

### 3. Set Timeout Appropriately

Variable operations are fast, use short timeouts:

```yaml
timeout: 10  # 10 seconds is usually enough
```

### 4. Always Declare Outputs

```yaml
outputs:
  my_variable: "my_variable"  # Make it available for later steps
```

---

## Additional Scenarios

### Scenario 6: Slice List from Specific Item

**Purpose**: Keep only items from a specific point onwards

```yaml
- id: "slice-from-target"
  agent_type: "variable"
  inputs:
    operation: "slice"
    source: "{{all_urls}}"
    start_value: "https://example.com/target"
    match_field: "url"
  outputs:
    result: "filtered_urls"
```

### Scenario 7: Filter Items by Criteria

**Purpose**: Keep only items matching a condition

```yaml
- id: "filter-active"
  agent_type: "variable"
  inputs:
    operation: "filter"
    source: "{{all_items}}"
    field: "status"
    equals: "active"
  outputs:
    result: "active_items"
```

---

## Limitations

- **Simple matching only**: `filter` and `slice` use exact or substring matching
- **No transformations**: Cannot map or modify items, only select them
- **No external access**: Cannot fetch URLs or access files

For complex data manipulation, use `code_agent`.

---

**Version**: 1.1
**Last Updated**: 2025-12-09
**Changes**: Added `slice` and `filter` operations
