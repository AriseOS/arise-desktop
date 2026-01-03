# StorageAgent Specification

**Agent Type**: `storage_agent`

## Purpose
Persistent data storage with LLM-generated SQL. Supports store, query, and export operations.

## Operations

### Store
```yaml
- id: store-product
  agent: storage_agent
  inputs:
    operation: store
    collection: products          # Table name (suffixed with user_id)
    data: "{{product_detail}}"    # Object or list to store
    upsert_key: url               # Optional: update if exists
  outputs:
    message: store_message
    rows_stored: rows_count
```

### Query
```yaml
- id: query-products
  agent: storage_agent
  inputs:
    operation: query
    collection: products
    query_requirements:
      description: "Get products with price < 100"
      limit: 20
  outputs:
    query_result: filtered_products
```

### Export
```yaml
- id: export-data
  agent: storage_agent
  inputs:
    operation: export
    collection: products
    export_format: csv            # csv | excel | json
    output_path: "/tmp/products.csv"
  outputs:
    export_path: csv_path
```

## Input Parameters

### Store Operation
```yaml
inputs:
  operation: store                # Required
  collection: "collection_name"   # Required: Table name
  data: "{{variable}}"            # Required: Data to store
  upsert_key: "field_name"        # Optional: Unique key for upsert
```

### Query Operation
```yaml
inputs:
  operation: query                # Required
  collection: "collection_name"   # Required
  query_requirements:
    description: "Query description"
    filters: {}                   # Optional
    limit: 10                     # Optional
```

### Export Operation
```yaml
inputs:
  operation: export               # Required
  collection: "collection_name"   # Required
  export_format: "csv"            # csv | excel | json
  output_path: "/path/to/file"    # Optional
```

## Output
```yaml
outputs:
  message: "variable_name"        # Operation status message
  rows_stored: "count_var"        # Number of rows stored (store)
  query_result: "result_var"      # Query results (query)
  export_path: "path_var"         # Export file path (export)
```

## Upsert Behavior

When `upsert_key` is specified:
1. Creates UNIQUE index on the specified field
2. Uses SQLite `INSERT OR REPLACE`
3. Updates existing records with same key value
4. Inserts new records if key not found

**When to use `upsert_key`**:
- Scraping products and want to update without duplicates
- Tracking items by unique identifier (URL, product_id)
- Re-running workflow should update existing data

**How to choose `upsert_key`** (priority order):
1. `url` - Best choice, page URL is always unique
2. `id`, `product_id`, `sku` - Explicit ID fields
3. `name` - Names are usually unique within a collection
4. **If none of the above exist, or unsure → DO NOT add upsert_key**

**NEVER use as upsert_key**:
- `handle`, `author`, `creator` - Multiple items can have same author
- `category`, `tag`, `type` - Definitely not unique
- Any field you're not 100% sure is unique

## Complete Examples (v2 Format)

### Store with Upsert
```yaml
- id: store-product
  agent: storage_agent
  inputs:
    operation: store
    collection: products
    data: "{{product_detail}}"
    upsert_key: url              # Update if same URL exists
  outputs:
    message: store_result
```

### Store in Loop
```yaml
- foreach: "{{products}}"
  as: product
  do:
    - id: store-product
      agent: storage_agent
      inputs:
        operation: store
        collection: products
        data: "{{product}}"
        upsert_key: url
```

### Query and Export
```yaml
steps:
  - id: query-recent
    agent: storage_agent
    inputs:
      operation: query
      collection: products
      query_requirements:
        description: "Get all products added today"
    outputs:
      query_result: todays_products

  - id: export-csv
    agent: storage_agent
    inputs:
      operation: export
      collection: products
      export_format: csv
    outputs:
      export_path: csv_file
```

## How It Works

- Uses LLM to generate SQL based on data structure
- Caches SQL scripts in KV storage
- Auto-creates tables on first store
- **Data Isolation**: Table name = `{collection}_{user_id}_{workflow_id}`
  - Each user + workflow combination has separate data
  - Re-running same workflow updates/appends to existing data
  - Different workflows don't share data
