# GraphStore Module

Graph storage abstraction layer for the Memory system.

## Purpose

Provides a unified interface (`GraphStore`) for graph data storage with multiple backend implementations, enabling the Memory system to switch between in-memory storage (development) and persistent storage (production).

## Architecture

```
GraphStore (Abstract)
    ├── NetworkXGraph    - In-memory, NetworkX-based (default)
    ├── Neo4jGraphStore  - Persistent, Neo4j-based (production)
    └── MemoryGraph      - Simple dict-based storage
```

## Key Files

| File | Purpose |
|------|---------|
| `graph_store.py` | Abstract interface definition |
| `networkx_graph.py` | In-memory implementation using NetworkX |
| `neo4j_graph.py` | Neo4j persistent storage implementation |
| `neo4j_config.py` | Neo4j connection configuration |
| `memory_graph.py` | Simple dict-based storage |
| `vector_index.py` | In-memory vector index |
| `mvcc_graph.py` | Experimental MVCC support |

## Usage

```python
from src.cloud_backend.memgraph.graphstore import create_graph_store

# Development (in-memory)
store = create_graph_store("networkx")

# Production (Neo4j)
store = create_graph_store("neo4j")

# With explicit config
store = create_graph_store(
    "neo4j",
    uri="neo4j://localhost:7687",
    user="neo4j",
    password="password",
)
```

## Neo4j Configuration

Environment variables:
- `NEO4J_URI` - Connection URI (default: `neo4j://localhost:7687`)
- `NEO4J_USER` - Username (default: `neo4j`)
- `NEO4J_PASSWORD` - Password (required)
- `NEO4J_DATABASE` - Database name (default: `neo4j`)
- `NEO4J_VECTOR_DIMENSIONS` - Default vector size (default: `768`)

## Key Interfaces

### Node Operations
- `upsert_node()`, `get_node()`, `delete_node()`, `query_nodes()`
- `upsert_nodes()`, `delete_nodes()` (batch)

### Relationship Operations
- `upsert_relationship()`, `delete_relationship()`, `query_relationships()`

### Index Operations
- `create_index()`, `create_text_index()`, `create_vector_index()`
- `text_search()`, `vector_search()`

### Graph Algorithms
- `execute_pagerank()`, `get_pagerank_scores()`

## Data Serialization

Complex properties (lists, dicts) are serialized to JSON for Neo4j storage:
- `instances`, `intent_sequences`, `intents` → `*_json` columns
- `embedding_vector` → stored as native float array

## Design Decisions

1. **Interface Compatibility**: Neo4jGraphStore implements all GraphStore methods
2. **Automatic Serialization**: Complex types handled transparently
3. **Transaction Safety**: Uses managed transactions with auto-retry
4. **Lazy Index**: PageRank re-executed on demand after graph changes
