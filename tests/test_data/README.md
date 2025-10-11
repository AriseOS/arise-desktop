# Test Data

This directory contains test data for Intent Builder integration tests.

## Directory Structure

```
test_data/
└── {test_scenario}/              # Each test scenario has its own directory
    ├── fixtures/                 # Input data (read-only)
    │   └── user_operations.json  # Raw user operations from browser
    ├── expected/                 # Expected outputs (for validation)
    │   ├── intents.json         # Expected extracted intents
    │   ├── intent_graph.json    # Expected intent graph structure
    │   ├── metaflow.yaml        # Expected metaflow
    │   └── workflow.yaml        # Expected workflow
    └── output/                   # Actual generated outputs (test runtime)
        ├── intents.json
        ├── intent_graph.json
        ├── metaflow.yaml
        └── workflow.yaml
```

## Test Scenarios

### coffee_allegro

**Description**: Collect coffee product information from Allegro e-commerce site

**Pipeline**:
1. User Operations (16 operations) → IntentExtractor → 4 Intents
2. Intents → IntentMemoryGraph → Graph with 4 nodes, 3 edges
3. Graph + User Query → MetaFlowGenerator → MetaFlow with loop
4. MetaFlow → WorkflowGenerator → Executable Workflow

**Files**:
- `fixtures/user_operations.json` - Browser operations from Allegro coffee collection
- `expected/intents.json` - 4 semantic intents (navigate, category, product detail, extract)
- `expected/metaflow.yaml` - MetaFlow with loop and implicit ExtractList node
- `expected/workflow.yaml` - Complete workflow with foreach loop

## Adding New Test Scenarios

1. Create new directory: `test_data/{scenario_name}/`
2. Add subdirectories: `fixtures/`, `expected/`, `output/`
3. Place input data in `fixtures/`
4. Place expected outputs in `expected/`
5. Create integration test in `tests/integration/intent_builder/`

## Notes

- `fixtures/` and `expected/` are version controlled
- `output/` is generated at runtime and should be in `.gitignore`
- Each test scenario is independent and isolated
