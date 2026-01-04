# Variable Agent

**Agent Type**: `variable`

## What It Does

Combines, filters, or slices data without LLM. Use for data transformation between steps.

**IMPORTANT**: All operations use `data` as the unified input field.

## Operations

### set - Combine Data

```yaml
- id: "combine-data"
  agent_type: "variable"
  inputs:
    operation: "set"
    data:
      url: "{{product.url}}"
      name: "{{details.0.name}}"
      price: "{{details.0.price}}"
  outputs:
    result: "complete_product"
```

### filter - Filter List

```yaml
- id: "filter-products"
  agent_type: "variable"
  inputs:
    operation: "filter"
    data: "{{all_products}}"
    field: "category"
    contains: "electronics"   # OR equals: "exact_value"
  outputs:
    result: "filtered_products"
```

### slice - Slice List

```yaml
# Get first N items (start=0, end=N)
- id: "get-first-10"
  agent_type: "variable"
  inputs:
    operation: "slice"
    data: "{{all_items}}"
    start: 0
    end: 10
  outputs:
    result: "first_10_items"

# Skip first N items (start=N)
- id: "skip-first-10"
  agent_type: "variable"
  inputs:
    operation: "slice"
    data: "{{all_items}}"
    start: 10
  outputs:
    result: "remaining_items"

# By matching value
- id: "start-from-item"
  agent_type: "variable"
  inputs:
    operation: "slice"
    data: "{{all_items}}"
    start_value: "https://example.com/target"
    match_field: "url"
  outputs:
    result: "items_from_target"
```

## Output

**Always outputs to `result` key**. Use `outputs.result` to capture:

```yaml
outputs:
  result: "variable_name"
```

## Common Patterns

### Merge data from foreach loop

```yaml
# In foreach loop, combine item URL with extracted details
- id: "merge-product-data"
  agent_type: "variable"
  inputs:
    operation: "set"
    data:
      url: "{{product.url}}"           # From foreach item
      name: "{{product_details.0.name}}"  # From scraper
      price: "{{product_details.0.price}}"
  outputs:
    result: "complete_product"
```

### Filter before foreach

```yaml
# Filter list before looping
- id: "filter-active"
  agent_type: "variable"
  inputs:
    operation: "filter"
    data: "{{all_items}}"
    field: "status"
    equals: "active"
  outputs:
    result: "active_items"

- id: "process-active"
  agent_type: "foreach"
  source: "{{active_items}}"
  ...
```
