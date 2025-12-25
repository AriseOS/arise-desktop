# src/cloud_backend/intent_builder/

Intent-based workflow generation system. Converts user operations into executable workflows.

## Pipeline

```
User Operations JSON → IntentExtractor → Intent Graph → MetaFlowGenerator → MetaFlow → WorkflowGenerator → Workflow YAML
```

## Directories (see each CONTEXT.md for details)

- `core/` - Data structures (Intent, IntentMemoryGraph, MetaFlow, Operation)
- `extractors/` - Intent extraction from user operations
- `generators/` - MetaFlow and Workflow generation
- `agent/` - Intent builder agent (LLM-based)
- `validators/` - YAML validation
- `storage/` - In-memory storage

## Key Concepts

**Intent**: Semantic abstraction of user operations
```python
Intent(id, description, operations, created_at, source_session_id)
```

**IntentMemoryGraph**: Graph of intents with temporal edges
- Nodes: Intent instances
- Edges: Temporal ordering (not causal)
- Retrieval: Semantic similarity via embeddings

**MetaFlow**: Intermediate representation between Intent and Workflow
- Contains implicit nodes (LLM-inferred)
- Contains control flow (loops)
- Contains data flow (variable passing)

## Generation Strategy

1. **Intent Extraction**: Rule-based URL segmentation + LLM semantic understanding
2. **MetaFlow Generation**: LLM infers loops, implicit nodes, data flow
3. **Workflow Generation**: Convert MetaFlow to BaseAgent YAML format

## Constraints

- MVP: No intent deduplication
- MVP: Only simple loops (foreach), no conditionals
- MVP: JSON file storage (not database)
