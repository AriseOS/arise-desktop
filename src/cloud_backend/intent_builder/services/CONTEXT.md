# intent_builder/services/

API service layer for workflow generation and dialogue.

## Overview

Provides the main entry points for:
1. Generating workflows from recordings/intents
2. Interactive dialogue for workflow understanding and modification
3. Streaming progress updates for frontend display

## Files

| File | Purpose |
|------|---------|
| `workflow_service.py` | WorkflowService - unified API |

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
