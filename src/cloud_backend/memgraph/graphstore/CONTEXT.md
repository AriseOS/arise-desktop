# GraphStore Module

Graph storage abstraction layer for the Memory system.

## Purpose

Provides a unified interface (`GraphStore`) for graph data storage with multiple backend implementations, enabling the Memory system to switch between backends via configuration.

## Architecture

```
GraphStore (Abstract)
    ├── NetworkXGraph       - In-memory, NetworkX-based (development)
    ├── Neo4jGraphStore     - Persistent, Neo4j (production option 1)
    ├── SurrealDBGraphStore - Persistent, SurrealDB (production option 2)
    └── MemoryGraph         - Simple dict-based storage
```

## Key Files

| File | Purpose |
|------|---------|
| `graph_store.py` | Abstract interface definition |
| `networkx_graph.py` | In-memory implementation using NetworkX |
| `neo4j_graph.py` | Neo4j persistent storage implementation |
| `neo4j_config.py` | Neo4j connection configuration |
| `surrealdb_graph.py` | SurrealDB persistent storage implementation |
| `surrealdb_config.py` | SurrealDB connection configuration |
| `memory_graph.py` | Simple dict-based storage |
| `vector_index.py` | In-memory vector index |
| `mvcc_graph.py` | Experimental MVCC support |

## API Reference

See `docs/surrealdb-api-reference.md` for detailed SurrealDB syntax and usage.

## Usage

```python
from src.cloud_backend.memgraph.graphstore import create_graph_store

# Development (in-memory)
store = create_graph_store("networkx")

# Production - Neo4j
store = create_graph_store("neo4j", uri="neo4j://localhost:7687", ...)

# Production - SurrealDB
store = create_graph_store("surrealdb", url="ws://localhost:8000/rpc", ...)
```

## Configuration

### Neo4j

```yaml
graph_store:
  backend: neo4j
  uri: neo4j://localhost:7687
  user: neo4j
  password: your_password
  database: neo4j
```

Environment variables: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`

### SurrealDB

```yaml
graph_store:
  backend: surrealdb
  url: ws://localhost:8000/rpc
  namespace: ami
  database: memory
  username: root
  password: your_password
  vector_dimensions: 1024
```

Environment variables: `SURREALDB_URL`, `SURREALDB_NAMESPACE`, `SURREALDB_DATABASE`, `SURREALDB_USER`, `SURREALDB_PASSWORD`

## Key Interfaces

### Node Operations
- `upsert_node()`, `get_node()`, `delete_node()`, `query_nodes()`
- `upsert_nodes()`, `delete_nodes()` (batch)

### Relationship Operations
- `upsert_relationship()`, `delete_relationship()`, `query_relationships()`
- `upsert_relationships()`, `delete_relationships()` (batch)

### Index Operations
- `create_index()`, `create_text_index()`, `create_vector_index()`
- `text_search()`, `vector_search()`

### Utility Operations
- `initialize_schema()`, `close()`, `clear()`
- `get_statistics()`, `get_all_entity_labels()`, `run_script()`

## Backend Comparison

| Feature | Neo4j | SurrealDB |
|---------|-------|-----------|
| Maturity | Very mature | Newer |
| Query Language | Cypher | SurrealQL |
| Vector Search | 5.11+ | Native HNSW |
| Complex Types | JSON serialization | Native |
| PageRank | GDS library | Not supported |

## Design Decisions

1. **Interface Compatibility**: Both backends implement all GraphStore methods
2. **Configuration-based**: Backend selected via `cloud-backend.yaml`
3. **No runtime switching**: Choose one backend, stick with it (data not shared)
