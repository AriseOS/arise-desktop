# cloud_backend/services/

Business logic services for the cloud backend.

## Files

| File | Purpose |
|------|---------|
| `learning_service.py` | Learning from user demonstrations |
| `recording_analysis_service.py` | Analyzes browser recording sessions |
| `storage_service.py` | Data persistence and retrieval |
| `workflow_generation_service.py` | Orchestrates workflow generation pipeline |

## WorkflowGenerationService

Main entry point for workflow generation. Orchestrates:
1. Intent extraction from recordings
2. IntentMemoryGraph construction
3. MetaFlow generation
4. Workflow YAML generation

```python
service = WorkflowGenerationService(llm_provider)
workflow = await service.generate_workflow(
    recording_data=recording,
    user_query="Collect all products"
)
```

## RecordingAnalysisService

Processes browser recording sessions:
- Parses operation sequences
- Identifies task boundaries
- Prepares data for intent extraction

## LearningService

Handles learning from user demonstrations:
- Stores successful workflows
- Updates IntentMemoryGraph with new intents
- Manages intent deduplication (future)

## StorageService

Data persistence layer:
- Intent graph persistence (JSON files)
- Workflow storage
- User session management
