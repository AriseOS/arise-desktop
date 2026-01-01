# StorageAgent Specification

**Agent Type**: `storage_agent`

## Purpose
Persistent data storage with LLM-generated SQL. Supports store, query, and export operations.

## Input Parameters

### Store Operation
```yaml
inputs:
  operation: "store"                  # Required: Operation type
  collection: "collection_name"       # Required: Table/collection name (suffixed with user_id)
  data: {}                            # Required: Data to store (object or list)
  upsert_key: "field_name"            # Optional: Field to use as unique key for upsert
                                      # If specified and record with same key exists, update it
                                      # If not specified, always insert new record
```

### Query Operation
```yaml
inputs:
  operation: "query"
  collection: "collection_name"
  query_requirements:                 # Natural language query description
    description: "Query description"
    filters: {}                       # Optional: Filter conditions
    limit: 10                         # Optional: Result limit
```

### Export Operation
```yaml
inputs:
  operation: "export"
  collection: "collection_name"
  export_format: "csv"               # "csv" | "excel" | "json"
  output_path: "/path/to/output"     # Optional: Export file path
```

## Output
```yaml
outputs:
  message: "variable_name"           # Operation status message
  rows_stored: "count_var"           # Number of rows stored (store)
  query_result: "result_var"         # Query results (query)
  export_path: "path_var"            # Export file path (export)
```

## Examples

### Store Data (Insert Only)
```yaml
- id: "store-product"
  agent_type: "storage_agent"
  inputs:
    operation: "store"
    collection: "products"           # Becomes "products_<user_id>"
    data: "{{product_detail}}"       # Single object or list
  outputs:
    message: "store_message"
    rows_stored: "rows_count"
```

### Store Data with Upsert (Update if Exists)
```yaml
- id: "store-product"
  agent_type: "storage_agent"
  inputs:
    operation: "store"
    collection: "products"
    data: "{{product_detail}}"
    upsert_key: "url"                # If product with same URL exists, update it
  outputs:
    message: "store_message"
    rows_stored: "rows_count"
```

### Query Data
```yaml
- id: "query-products"
  agent_type: "storage_agent"
  inputs:
    operation: "query"
    collection: "products"
    query_requirements:
      description: "Get products with price < 100 and rating > 4"
      limit: 20
  outputs:
    query_result: "filtered_products"
```

### Export Data
```yaml
- id: "export-data"
  agent_type: "storage_agent"
  inputs:
    operation: "export"
    collection: "products"
    export_format: "csv"
    output_path: "/tmp/products.csv"
  outputs:
    export_path: "csv_path"
```

## How It Works

- Uses LLM to generate SQL based on data structure
- Caches SQL scripts in KV storage (keyed by collection + schema)
- Auto-creates tables on first store
- Isolates data by user_id (table name: `collection_userid`)

## Upsert Behavior

When `upsert_key` is specified:
1. Creates UNIQUE index on the specified field (if not exists)
2. Uses SQLite `INSERT OR REPLACE` to update existing records
3. If record with same key value exists, all fields are updated
4. If record doesn't exist, inserts new record

**When to use `upsert_key`**:
- Scraping products and want to update prices without duplicates
- Tracking items by unique identifier (URL, product_id, etc.)
- Re-running workflow should update existing data, not create duplicates

**How to choose `upsert_key`**:
- Look for fields that uniquely identify a record (URL, ID, SKU)
- Consider the semantic meaning: "same product" = same URL/ID
- If scraping from a list page, the detail page URL is often a good key
