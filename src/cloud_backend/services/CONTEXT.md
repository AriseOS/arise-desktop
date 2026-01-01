# cloud_backend/services/

Business logic services for the cloud backend.

## Files

| File | Purpose |
|------|---------|
| `recording_analysis_service.py` | Analyzes browser recording sessions |
| `storage_service.py` | Data persistence and retrieval |

## Architecture

Workflow generation has moved to `intent_builder/services/WorkflowService`.

The new architecture uses:
- Claude Agent SDK for workflow generation
- Skills for specifications and optimization rules
- No more MetaFlow intermediate layer

## RecordingAnalysisService

Processes browser recording sessions:
- Parses operation sequences
- Identifies task boundaries
- Prepares data for intent extraction

## StorageService

Data persistence layer:
- Intent graph persistence (JSON files)
- Workflow storage
- User session management
