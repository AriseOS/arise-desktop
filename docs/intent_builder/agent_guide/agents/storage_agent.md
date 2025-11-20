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

### Store Data
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
