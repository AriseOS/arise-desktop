# intent_builder/generators/

LLM-based generation of MetaFlow and Workflow from intents.

## Files

| File | Purpose |
|------|---------|
| `metaflow_generator.py` | Generates MetaFlow from IntentMemoryGraph |
| `workflow_generator.py` | Converts MetaFlow to BaseAgent Workflow YAML |
| `prompt_builder.py` | Builds comprehensive prompts for LLM generation |

## Generation Pipeline

```
IntentMemoryGraph + User Query
        ↓
   MetaFlowGenerator (LLM)
        ↓
     MetaFlow
        ↓
   WorkflowGenerator (LLM)
        ↓
   Workflow YAML
```

## MetaFlowGenerator

Takes graph structure and user query, generates MetaFlow.

```python
generator = MetaFlowGenerator(llm_provider)
metaflow = await generator.generate(
    graph=intent_graph,
    task_description="Collect coffee product info",
    user_query="Collect all coffee products"
)
```

**LLM Responsibilities:**
- Path selection: Choose relevant branch from graph
- Loop detection: Identify "foreach" patterns from keywords ("all", "every")
- Implicit node generation: Add missing nodes (e.g., ExtractList before loop)
- Data flow inference: Connect variable references

## WorkflowGenerator

Converts MetaFlow to executable BaseAgent Workflow.

```python
generator = WorkflowGenerator(llm_provider)
workflow_yaml = await generator.generate(metaflow)
```

## PromptBuilder

Constructs detailed prompts with:
- Intent descriptions and operations
- Graph structure (nodes + edges)
- User query and task description
- Output format specifications
