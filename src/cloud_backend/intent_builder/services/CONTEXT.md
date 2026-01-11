# intent_builder/services/

API service layer for workflow generation and dialogue.

## Overview

Provides the main entry points for:
1. Generating workflows from recordings/intents
2. Interactive dialogue for workflow understanding and modification
3. Streaming progress updates for frontend display
4. **Script pre-generation** from recorded DOM snapshots

## Files

| File | Purpose |
|------|---------|
| `workflow_service.py` | WorkflowService - unified API for workflow generation |
| `script_pregeneration_service.py` | Pre-generates scripts using DOM snapshots from recording |
| `scraper_context_service.py` | Pre-computes diagnostic context for scraper fix sessions |

## WorkflowService

Main service class that orchestrates:
- Intent extraction (if needed)
- Workflow generation
- Validation with retry loop
- Session management for dialogue

### One-shot Generation

```python
service = WorkflowService(api_key="...")
response = await service.generate(GenerationRequest(
    task_description="Extract products",
    intent_sequence=[...]
))

if response.success:
    workflow = response.workflow
    session_id = response.session_id  # For dialogue
```

### Streaming Generation (Lovable-style)

```python
async for progress in service.generate_stream(request):
    print(f"{progress.status}: {progress.progress}% - {progress.message}")
```

Progress states: PENDING → ANALYZING → UNDERSTANDING → GENERATING → VALIDATING → COMPLETED

### Dialogue

```python
chat_response = await service.chat(ChatRequest(
    session_id=response.session_id,
    message="Why browser_agent here?"
))

if chat_response.workflow_updated:
    new_workflow = chat_response.workflow
```

## Data Types

```python
@dataclass
class GenerationRequest:
    recording_id: Optional[str]
    task_description: str
    intent_sequence: Optional[List[Dict]]
    operations: Optional[List[Dict]]  # Raw operations
    enable_semantic_validation: bool = True

@dataclass
class GenerationResponse:
    success: bool
    workflow_id: Optional[str]
    workflow: Optional[Dict]
    workflow_yaml: Optional[str]
    session_id: Optional[str]  # For dialogue
    error: Optional[str]
    validation_result: Optional[FullValidationResult]

@dataclass
class ChatRequest:
    session_id: str
    message: str

@dataclass
class ChatResponse:
    reply: str
    workflow_updated: bool
    workflow: Optional[Dict]
    workflow_yaml: Optional[str]
```

## ScriptPregenerationService

Pre-generates scripts for workflow steps using DOM snapshots captured during recording.

### Purpose

When users record browser actions, DOM snapshots are captured at each navigation.
After workflow generation, this service uses those snapshots to pre-generate:
- `find_element.py` for browser_agent click/fill operations
- `extraction_script.py` for scraper_agent data extraction

This eliminates the need to generate scripts during first execution.

### Usage

```python
from src.cloud_backend.intent_builder.services import ScriptPregenerationService

service = ScriptPregenerationService(
    config_service=config_service,
    api_key="sk-...",
    base_url="https://api.anthropic.com"
)

result = await service.pregenerate_scripts(
    workflow_yaml=workflow_yaml,
    dom_snapshots={"https://example.com": {...dom_dict...}},
    workflow_dir=Path("/path/to/workflow")
)

# Result:
# {
#     "success": True,
#     "total_steps": 3,
#     "generated": 2,
#     "skipped": 1,
#     "failed": 0,
#     "details": [...]
# }
```

### Integration

Called **synchronously** after workflow is saved in `main.py`:
```python
# Scripts are generated before returning completion to user
script_gen_result = await _generate_scripts_sync(
    workflow_yaml=response.workflow_yaml,
    dom_snapshots=dom_snapshots,
    workflow_dir=workflow_dir,
    api_key=x_ami_api_key
)
```

This ensures scripts are ready immediately after workflow generation, rather than
being generated in the background or on first execution.

## ScraperContextService

Pre-computes diagnostic context for workflow modification sessions to optimize
scraper fix workflows. Eliminates the need for Claude to explore directory
structure or read files to understand the problem context.

### Purpose

When users report extraction issues ("抓不到数据", "数据错误"), the service
pre-computes and injects into the system prompt:

1. **Directory structure** - All scraper step locations
2. **Requirement.json content** - Expected fields and xpath hints
3. **Pre-run script output** - Current extraction results or errors
4. **URL index** - Which step handles which page

### Usage

```python
from src.cloud_backend.intent_builder.services.scraper_context_service import (
    generate_scraper_context_markdown
)

# Generate context for injection into system prompt
context_md = generate_scraper_context_markdown(
    session_dir=Path("/path/to/session"),
    workflow_yaml=workflow_yaml,
    pre_run_scripts=True,  # Run scripts to get current output
    dom_snapshots=None     # Optional: provide DOM for testing
)

# Returns markdown like:
# ## Workflow Context (Pre-computed)
# **Workflow**: product-extraction
#
# ### Directory Structure
# ...
#
# ### Scraper Steps
# #### Step 1: extract-product-list
# - **Script Directory**: extract-product-list/
# - **Requirement**: 提取产品列表
# - **Current Script Output**: ⚠️ Empty list `[]`
# ...
```

### Integration

Automatically called by `WorkflowModificationSession._build_system_prompt()`.
The context is injected into the system prompt so Claude can immediately
understand the problem without exploration.
