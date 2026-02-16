# src/cloud_backend/intent_builder/

Intent-based workflow generation system. Converts user recordings into executable workflows.

## Pipeline (v0.4.0 - Skills-based Architecture)

```
Recording → IntentExtractor → WorkflowBuilder (Claude Agent + Skills) → Validator → Workflow
                                    ↑
                           User Dialogue (optional)
```

**Key changes from v0.3:**
- Skills-based architecture for workflow generation
- Agent specs and optimization rules as Skills
- Removed MetaFlow intermediate layer completely
- Removed deprecated generators directory

## Directories

- `core/` - Data structures (Intent, IntentMemoryGraph, Operation)
- `extractors/` - Intent extraction from user operations
- `agents/` - Claude Agent SDK based workflow generation
  - `workflow_builder.py` - WorkflowBuilder and WorkflowBuilderSession
  - `tools/` - Agent tools (validate)
- `validators/` - Two-layer validation
  - `RuleValidator` - Fast deterministic checks
  - `SemanticValidator` - LLM-based task completeness checks
  - `WorkflowValidator` - Unified validator combining both
- `services/` - API service layer
  - `WorkflowService` - Main entry point for generation and dialogue
- `.claude/skills/` - Skills for Claude Agent
  - `workflow-generation/` - Main generation process
  - `workflow-validation/` - Validation with script
  - `agent-specs/` - Agent specifications
  - `workflow-optimizations/` - Optimization rules
- `storage/` - In-memory storage

## Skills Architecture

```
.claude/skills/
├── workflow-generation/          # Main Skill: generation process
│   ├── SKILL.md                  # Layer 1/Layer 2 workflow
│   └── references/
│       ├── workflow_spec.md      # YAML specification
│       └── loop_detection.md     # Loop pattern detection
│
├── workflow-validation/          # Validation Skill
│   ├── SKILL.md
│   └── scripts/
│       └── validate.py           # Validation script
│
├── agent-specs/                  # Agent specifications
│   ├── SKILL.md
│   └── references/
│       ├── browser_agent.md
│       ├── scraper_agent.md
│       └── storage_agent.md
│
└── workflow-optimizations/       # Layer 2 optimizations
    ├── SKILL.md
    └── references/
        ├── click_to_navigate.md
        └── scroll_optimization.md
```

## Key Concepts

**Intent**: Semantic abstraction of user operations
```python
Intent(id, description, operations, created_at, source_session_id)
```

**WorkflowBuilderSession**: Interactive session for workflow generation
- Maintains Claude Agent context for multi-turn dialogue
- Users can ask questions and request modifications
- Workflow updated in real-time based on user feedback
- Can be created from existing Workflow via `set_existing_workflow()`

**WorkflowValidator**: Two-layer validation
- Rule validation: YAML format, required fields, variable references, agent types
- Semantic validation: Task completeness, data flow correctness

## API Endpoints

### Workflow Generation
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/workflows/generate` | POST | Direct Workflow generation |
| `/api/v1/workflows/generate-stream` | POST | Streaming generation (SSE) |

### Workflow Dialogue
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/workflow-sessions` | POST | Create dialogue session |
| `/api/v1/workflow-sessions/{id}/chat` | POST | Send dialogue message |
| `/api/v1/workflow-sessions/{id}` | DELETE | Close session |

## Main Entry Points

```python
# One-shot generation
from intent_builder.services import WorkflowService

service = WorkflowService(api_key="...", base_url="...")
response = await service.generate(
    task_description="Extract products from website",
    intent_sequence=[...],
    enable_semantic_validation=True
)

# Streaming generation
async for event in service.generate_stream(...):
    print(f"Stage: {event.status}, Progress: {event.progress}%")

# Interactive dialogue
chat_response = await service.chat(
    session_id=response.session_id,
    message="Why did you use browser_agent here?"
)

# Add intents to user's graph
await service.add_intents_to_graph(
    operations=[...],
    graph_filepath="path/to/intent_graph.json",
    task_description="User's task"
)
```

## Constraints

- MVP: No intent deduplication
- MVP: Only simple loops (foreach), no conditionals

## Skills Maintenance

Skills are located in `.claude/skills/` and must stay in sync with source code.

### Skill Dependencies

| Skill | When to Update |
|-------|----------------|
| `agent-specs/references/browser_agent.md` | Browser agent behavior changes |
| `agent-specs/references/scraper_agent.md` | Scraper agent behavior changes |
| `agent-specs/references/storage_agent.md` | Storage agent behavior changes |
| `workflow-generation/references/workflow_spec.md` | Workflow YAML structure changes |
| `workflow-validation/scripts/validate.py` | Validation rules change |
| `workflow-optimizations/references/*.md` | New optimization patterns |

### Update Process

1. Update content in the corresponding Skill `references/` files
2. Update `SKILL.md` if the description or usage changes
