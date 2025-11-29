# Intent Builder - Storage Architecture and Data Flow Requirements

## Document Overview

**Version**: 1.0
**Date**: 2025-11-28
**Status**: Confirmed Requirements

This document defines the storage architecture, data flow, and file lifecycle management for the Intent Builder system.

---

## 1. System Architecture Overview

### 1.1 Core Data Flow

```
User Recording → Intent Graph → MetaFlow → Workflow
                     ↓              ↓          ↓
                Accumulative   Intermediate  Executable
                 Knowledge      Design       Process
```

### 1.2 Storage Structure

**Cloud Backend (Primary Storage): `~/ami-server/users/{user_id}/`**

```
~/ami-server/users/{user_id}/
├── recordings/                      # Original recordings (immutable)
│   └── {recording_id}/
│       ├── operations.json         # Recording data
│       └── metadata.json           # Links: metaflow_id
│
├── intent_graph.json               # User's cumulative Intent Memory Graph
│
├── metaflows/                      # Generated MetaFlows
│   └── {metaflow_id}/
│       ├── metaflow.yaml          # MetaFlow definition
│       └── metadata.json          # Links: workflow_id, source_recording_id
│
├── workflows/                      # Generated Workflows
│   └── {workflow_id}/
│       ├── workflow.yaml          # Executable workflow
│       └── metadata.json          # Links: source_metaflow_id, source_recording_id
│
└── intent_builder/                 # Claude Agent working directories (temporary)
    └── {session_id}/
        ├── metaflow.yaml          # Work-in-progress files
        ├── workflow.yaml
        └── .last_modified         # Timestamp for cleanup
```

**App Backend (Local Cache): `~/.ami/users/{user_id}/`**

```
~/.ami/users/{user_id}/
├── recordings/                     # Local recording copies
├── metaflows/                      # Downloaded from cloud (read-only)
└── workflows/                      # Downloaded from cloud (for execution)
```

---

## 2. Core Requirements

### 2.1 User Workflow Patterns

**Primary Pattern: Quick Iteration + Knowledge Accumulation (Scenario A + C)**

```
┌─────────────────────────────────────────────────────────────┐
│ Quick Iteration Loop                                        │
├─────────────────────────────────────────────────────────────┤
│ Recording → MetaFlow → Workflow → Test → Modify → Test     │
│                                              ↑         ↓     │
│                                              └─────────┘     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Knowledge Accumulation                                      │
├─────────────────────────────────────────────────────────────┤
│ Recording 1 ┐                                               │
│ Recording 2 ├─→ Intent Graph → Generate Generic Workflow   │
│ Recording N ┘                                               │
└─────────────────────────────────────────────────────────────┘
```

**Key Characteristics:**
- MetaFlow is an intermediate artifact, not for manual editing
- Focus on final Workflow usability
- Intent Graph continuously accumulates knowledge
- Users primarily interact through Claude Agent, not direct file editing

---

## 3. Version Management Strategy

### 3.1 Overwrite Mode (No Version History)

**Principle**: Only keep the latest version, simplicity over history.

**File Modification Strategy**: **In-Place Updates**

```python
# When modifying existing MetaFlow/Workflow
# DO NOT create new IDs, overwrite existing files

# Example: User wants to improve workflow_xyz
workflow_path = "~/ami-server/users/user123/workflows/workflow_xyz/workflow.yaml"

# Agent modifies this file directly (in-place)
# workflow_xyz ID remains unchanged
# File content is overwritten
```

### 3.2 Recording → MetaFlow Relationship

**Rule**: 1 Recording → 1 MetaFlow (Overwrite on Regeneration)

```
# First generation
recording_001 → metaflow_abc
recording_001/metadata.json = {"metaflow_id": "metaflow_abc"}

# User wants to regenerate
# DELETE old metaflow_abc directory
# CREATE new metaflow_def directory
recording_001/metadata.json = {"metaflow_id": "metaflow_def"}
```

**Implementation:**
- Check if `recording.metadata.metaflow_id` exists
- If exists, delete the old MetaFlow directory before generating new one
- Update Recording metadata with new MetaFlow ID

### 3.3 MetaFlow ↔ Workflow Independence

**Rule**: MetaFlow and Workflow are independent after creation.

```
Scenario: User modifies MetaFlow after Workflow is generated

metaflow_abc (modified) ←─ No automatic sync ─→ workflow_xyz (unchanged)

Result:
- workflow_xyz continues to exist and function
- No automatic deletion or regeneration
- User can manually regenerate Workflow if needed
```

**Rationale:**
- Avoid cascading deletions
- Users may want to experiment with MetaFlow without affecting working Workflows
- Explicit user action required to regenerate Workflow from modified MetaFlow

---

## 4. Agent Session Management

### 4.1 Multi-Turn Conversation Support

**Scenario:**
```
User enters Intent Builder page
  ↓
Start Agent Session (session_001)
  ↓
Turn 1: "Generate MetaFlow from recording"
  ← Agent generates metaflow.yaml
  ↓
Turn 2: "Change step 3 to click button instead"
  ← Agent modifies metaflow.yaml in same directory
  ↓
Turn 3: "Optimize the workflow"
  ← Agent continues working in same directory
  ↓
User leaves page OR session timeout
  ↓
Cleanup session_001 directory
```

### 4.2 Session Lifecycle

**Session States:**
```python
class SessionStatus:
    ACTIVE = "active"      # Currently in use
    IDLE = "idle"          # No activity, but not expired
    EXPIRED = "expired"    # Ready for cleanup
```

**Lifecycle Flow:**
```
CREATE Session
  ↓
  last_modified = now()
  ↓
Each Agent interaction
  ↓
  Update last_modified = now()
  ↓
No activity for 30 minutes
  ↓
  Status → EXPIRED
  ↓
Background cleanup task
  ↓
  DELETE session directory
```

### 4.3 Session Cleanup Strategy

**Requirement: Timeout-Based Automatic Cleanup**

**Configuration:**
```yaml
# Session cleanup settings
session_timeout_minutes: 30        # Inactivity timeout
cleanup_interval_minutes: 5        # Background task frequency
```

**Cleanup Mechanism: Filesystem-Based (No Database)**

```python
# Background task (runs every 5 minutes)
def cleanup_expired_sessions():
    """
    Scan intent_builder/ directory and remove expired sessions
    """
    intent_builder_root = "~/ami-server/users/*/intent_builder/"

    for session_dir in glob(f"{intent_builder_root}/*/"):
        # Check directory last modified time
        last_modified = os.path.getmtime(session_dir)
        age_minutes = (now() - last_modified) / 60

        if age_minutes > 30:
            # Remove entire session directory
            shutil.rmtree(session_dir)
            logger.info(f"Cleaned up expired session: {session_dir}")
```

**Implementation Details:**
- **No Database Required**: Use filesystem modification timestamps
- **Simple Scanning**: Check `intent_builder/{session_id}/` directories
- **Safe Deletion**: Only delete if last_modified > 30 minutes
- **Idempotent**: Safe to run multiple times

**Session History: Not Supported**
- Each page visit creates a new session
- Previous sessions are cleaned up
- No "resume previous session" functionality
- Users must complete work within session timeout window

### 4.4 Session Save and Finalize

**When Agent Completes Task:**

```python
# Agent finishes generating/modifying MetaFlow
session_dir = "~/ami-server/users/user123/intent_builder/session_abc/"
metaflow_yaml = read_file(f"{session_dir}/metaflow.yaml")

# Save to permanent location (in-place if modifying existing)
if modifying_existing:
    # Overwrite existing MetaFlow file
    target_path = "~/ami-server/users/user123/metaflows/metaflow_xyz/metaflow.yaml"
    write_file(target_path, metaflow_yaml)
else:
    # Create new MetaFlow
    new_metaflow_id = generate_id()
    target_dir = f"~/ami-server/users/user123/metaflows/{new_metaflow_id}/"
    os.makedirs(target_dir)
    write_file(f"{target_dir}/metaflow.yaml", metaflow_yaml)
    write_metadata(f"{target_dir}/metadata.json", {...})

# Session directory remains (will be cleaned by timeout)
# User may continue conversation in same session
```

**Key Points:**
- Results are saved immediately after Agent completion
- Session directory is NOT deleted after saving (multi-turn support)
- Cleanup only happens via timeout mechanism
- Session files remain accessible during active conversation

---

## 5. Intent Graph Management

### 5.1 Automatic Accumulation

**Rule**: All Recordings automatically add intents to Intent Graph (No filtering).

```python
# After Recording upload
async def process_recording_upload(recording_data):
    # 1. Save recording
    save_recording(recording_data)

    # 2. Background task: Extract and add intents
    await extract_and_add_intents(
        recording_id=recording_data.recording_id,
        user_id=recording_data.user_id
    )
    # Automatically appends to intent_graph.json
```

**No Deduplication or Merging (Current Implementation Unchanged)**
- Intents are directly appended to `intent_graph.json`
- No similarity checking
- No automatic merging of similar intents
- Graph may grow large over time (acceptable for now)

### 5.2 Intent Graph Structure

**File**: `~/ami-server/users/{user_id}/intent_graph.json`

```json
{
  "user_id": "user123",
  "intents": [
    {
      "intent_id": "intent_001",
      "source_recording_id": "session_20251128_092504",
      "intent_type": "search",
      "description": "Search for products on e-commerce site",
      "operations": [...],
      "created_at": "2025-11-28T09:25:04Z"
    },
    {
      "intent_id": "intent_002",
      "source_recording_id": "session_20251128_103015",
      "intent_type": "data_extraction",
      "description": "Extract product details from page",
      "operations": [...],
      "created_at": "2025-11-28T10:30:15Z"
    }
  ],
  "updated_at": "2025-11-28T10:30:15Z"
}
```

**Usage Scenarios:**
1. **Generate from Intent Graph**: Use all accumulated intents to create generic workflows
2. **Generate from Recording**: Use only that recording's intents (doesn't read Intent Graph)

### 5.3 Intent Graph Growth Management

**Current Strategy**: Unlimited growth (no management).

**Future Considerations** (Not in current requirements):
- Manual cleanup UI
- Automatic pruning based on age or usage
- Intent similarity detection and merging

---

## 6. Storage Implementation

### 6.1 Storage Backend: Filesystem Only

**No Database for Metadata** (Keep Current Implementation)

**Rationale:**
- Simple and easy to debug
- Suitable for current scale
- File-based relationships via `metadata.json`
- Version control friendly (YAML + JSON)

### 6.2 Metadata Schema

**Recording Metadata**
```json
{
  "recording_id": "session_20251128_092504",
  "user_id": "user123",
  "task_description": "Search for coffee on Google",
  "user_query": "Extract all search results",
  "metaflow_id": "metaflow_abc123",
  "created_at": "2025-11-28T09:25:04Z",
  "updated_at": "2025-11-28T09:30:12Z"
}
```

**MetaFlow Metadata**
```json
{
  "metaflow_id": "metaflow_abc123",
  "user_id": "user123",
  "workflow_id": "workflow_xyz789",
  "source_recording_id": "session_20251128_092504",
  "source_type": "from_recording",  // or "from_intent_graph"
  "created_at": "2025-11-28T09:30:12Z",
  "updated_at": "2025-11-28T09:45:30Z"
}
```

**Workflow Metadata**
```json
{
  "workflow_id": "workflow_xyz789",
  "workflow_name": "search_and_extract_workflow",
  "user_id": "user123",
  "source_metaflow_id": "metaflow_abc123",
  "source_recording_id": "session_20251128_092504",
  "created_at": "2025-11-28T09:45:30Z",
  "updated_at": "2025-11-28T10:15:20Z"
}
```

### 6.3 Relationship Tracking

**Forward Relationships** (stored in metadata):
```
Recording.metaflow_id → MetaFlow
MetaFlow.workflow_id → Workflow
```

**Reverse Traceability** (stored in metadata):
```
Workflow.source_metaflow_id → MetaFlow
Workflow.source_recording_id → Recording
MetaFlow.source_recording_id → Recording
```

**Query Examples:**
```python
# Find all artifacts from a Recording
recording = load_recording("session_20251128_092504")
metaflow_id = recording.metadata["metaflow_id"]
metaflow = load_metaflow(metaflow_id)
workflow_id = metaflow.metadata["workflow_id"]
workflow = load_workflow(workflow_id)

# Reverse trace: Find source Recording from Workflow
workflow = load_workflow("workflow_xyz789")
source_recording_id = workflow.metadata["source_recording_id"]
original_recording = load_recording(source_recording_id)
```

---

## 7. Cloud vs Local Storage

### 7.1 Architecture: Cloud-Primary

**Cloud Backend (`~/ami-server/`)**: Primary storage and AI processing center
- All persistent data
- AI/LLM processing
- Single source of truth
- Multi-user management

**App Backend (`~/.ami/`)**: Local cache only
- Temporary recording copies (before upload)
- Downloaded Workflows for execution
- Browser profile data
- Local KV database

### 7.2 Data Flow

**Upload Flow (Local → Cloud):**
```
User records operation (App Backend)
  ↓
Save to ~/.ami/users/{user_id}/recordings/{recording_id}/
  ↓
Upload to Cloud Backend API
  ↓
Save to ~/ami-server/users/{user_id}/recordings/{recording_id}/
  ↓
Background tasks: AI analysis, Intent extraction
```

**Download Flow (Cloud → Local):**
```
User wants to execute Workflow
  ↓
App Backend checks local cache
  ↓
If not found, download from Cloud Backend API
  ↓
Save to ~/.ami/users/{user_id}/workflows/{workflow_id}/
  ↓
Execute locally
```

### 7.3 Sync Strategy

**No Automatic Sync**
- Local cache is transient
- Always fetch latest from Cloud Backend when needed
- No offline mode support (current requirements)
- No conflict resolution needed

---

## 8. File Lifecycle Summary

### 8.1 Recording

```
┌─────────────────────────────────────────────────────────┐
│ RECORDING LIFECYCLE                                     │
├─────────────────────────────────────────────────────────┤
│ Created: On user recording upload                       │
│ Modified: Never (immutable)                             │
│ Deleted: Manual user action only                        │
│ Metadata Updated: When MetaFlow is generated            │
└─────────────────────────────────────────────────────────┘
```

### 8.2 Intent Graph

```
┌─────────────────────────────────────────────────────────┐
│ INTENT GRAPH LIFECYCLE                                  │
├─────────────────────────────────────────────────────────┤
│ Created: First recording upload                         │
│ Modified: Append new intents after each recording       │
│ Deleted: Never (grows indefinitely)                     │
│ Cleanup: Not implemented (future consideration)         │
└─────────────────────────────────────────────────────────┘
```

### 8.3 MetaFlow

```
┌─────────────────────────────────────────────────────────┐
│ METAFLOW LIFECYCLE                                      │
├─────────────────────────────────────────────────────────┤
│ Created: User triggers generation from Recording/Graph  │
│ Modified: Claude Agent in-place edits (overwrites)      │
│ Deleted: When user regenerates from Recording           │
│ Metadata Updated: When Workflow is generated            │
│ Independence: Modification does NOT affect Workflow     │
└─────────────────────────────────────────────────────────┘
```

### 8.4 Workflow

```
┌─────────────────────────────────────────────────────────┐
│ WORKFLOW LIFECYCLE                                      │
├─────────────────────────────────────────────────────────┤
│ Created: User triggers generation from MetaFlow         │
│ Modified: Claude Agent in-place edits (overwrites)      │
│ Deleted: Manual user action only                        │
│ Metadata Updated: Never after creation                  │
│ Independence: Modification of source MetaFlow has no    │
│               automatic effect on this Workflow         │
└─────────────────────────────────────────────────────────┘
```

### 8.5 Agent Session

```
┌─────────────────────────────────────────────────────────┐
│ AGENT SESSION LIFECYCLE                                 │
├─────────────────────────────────────────────────────────┤
│ Created: User starts Intent Builder interaction         │
│ Active: During multi-turn conversation                  │
│ Updated: Every Agent interaction updates timestamp      │
│ Expired: 30 minutes of inactivity                       │
│ Deleted: Background cleanup task (every 5 minutes)      │
│ History: Not preserved, no session resumption           │
└─────────────────────────────────────────────────────────┘
```

---

## 9. Implementation Checklist

### 9.1 Current Implementation Status

✅ **Already Implemented (No Changes Needed):**
- Recording upload and storage
- Intent extraction and graph accumulation
- MetaFlow generation (from Recording and Intent Graph)
- Workflow generation from MetaFlow
- Claude Agent integration
- Filesystem-based storage with metadata.json
- Cloud-primary architecture

### 9.2 Required Changes

🔧 **Modifications Needed:**

#### A. In-Place Modification Support
```python
# Current: Always creates new IDs
# Required: Check if modifying existing, then overwrite

def generate_metaflow(user_id, recording_id, existing_metaflow_id=None):
    if existing_metaflow_id:
        # Overwrite existing
        metaflow_path = get_metaflow_path(user_id, existing_metaflow_id)
        # Generate and save to same path
    else:
        # Create new
        new_metaflow_id = generate_id()
        # Create new directory and save
```

#### B. Recording → MetaFlow Overwrite on Regeneration
```python
# When regenerating MetaFlow from Recording
def regenerate_metaflow_from_recording(user_id, recording_id):
    recording_metadata = load_recording_metadata(recording_id)

    # Check if MetaFlow already exists
    if "metaflow_id" in recording_metadata:
        old_metaflow_id = recording_metadata["metaflow_id"]

        # Delete old MetaFlow directory
        old_metaflow_dir = get_metaflow_path(user_id, old_metaflow_id)
        shutil.rmtree(old_metaflow_dir)

    # Generate new MetaFlow
    new_metaflow_id = generate_id()
    # ... generate and save

    # Update Recording metadata
    recording_metadata["metaflow_id"] = new_metaflow_id
    save_recording_metadata(recording_id, recording_metadata)
```

#### C. Session Cleanup Implementation
```python
# New background task
from apscheduler.schedulers.background import BackgroundScheduler

def start_session_cleanup_task():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=cleanup_expired_sessions,
        trigger="interval",
        minutes=5
    )
    scheduler.start()

def cleanup_expired_sessions():
    timeout_minutes = 30
    intent_builder_root = Path("~/ami-server/users")

    for user_dir in intent_builder_root.glob("*/"):
        intent_builder_dir = user_dir / "intent_builder"
        if not intent_builder_dir.exists():
            continue

        for session_dir in intent_builder_dir.glob("*/"):
            last_modified = datetime.fromtimestamp(
                session_dir.stat().st_mtime
            )
            age_minutes = (datetime.now() - last_modified).total_seconds() / 60

            if age_minutes > timeout_minutes:
                shutil.rmtree(session_dir)
                logger.info(f"Cleaned up session: {session_dir}")
```

#### D. MetaFlow ↔ Workflow Independence Enforcement
```python
# Ensure modifying MetaFlow does NOT trigger Workflow actions
def modify_metaflow(metaflow_id, new_content):
    metaflow_path = get_metaflow_path(metaflow_id)

    # Save modified MetaFlow
    save_yaml(metaflow_path, new_content)

    # Update metadata timestamp
    metadata = load_metadata(metaflow_id)
    metadata["updated_at"] = datetime.now().isoformat()
    save_metadata(metaflow_id, metadata)

    # DO NOT touch related Workflow
    # No deletion, no notification, no automatic regeneration
```

### 9.3 API Endpoint Requirements

**New/Modified Endpoints:**

```python
# Modified: Support in-place modification
POST /api/metaflows/{metaflow_id}/modify
Request:
{
    "user_query": "Change step 3 to click button",
    "session_id": "session_abc123"  # Existing session
}
Response:
{
    "metaflow_id": "metaflow_abc123",  # Same ID
    "updated_yaml": "...",
    "updated_at": "2025-11-28T10:30:00Z"
}

# Modified: Support overwrite on regeneration
POST /api/recordings/{recording_id}/regenerate_metaflow
Request:
{
    "task_description": "Updated description",
    "user_query": "New query"
}
Response:
{
    "old_metaflow_id": "metaflow_old123",  # Deleted
    "new_metaflow_id": "metaflow_new456",  # Created
    "message": "Old MetaFlow deleted, new one generated"
}

# New: Session management
POST /api/intent-builder/sessions
Response:
{
    "session_id": "session_abc123",
    "working_dir": "~/ami-server/users/user123/intent_builder/session_abc123/",
    "expires_at": "2025-11-28T11:00:00Z"
}

GET /api/intent-builder/sessions/{session_id}/status
Response:
{
    "session_id": "session_abc123",
    "status": "active",
    "last_active_at": "2025-11-28T10:25:00Z",
    "minutes_until_expiry": 25
}
```

---

## 10. Configuration

### 10.1 Cloud Backend Configuration

**File**: `src/cloud_backend/config/cloud-backend.yaml`

```yaml
storage:
  type: filesystem
  base_path: ~/ami-server

session:
  timeout_minutes: 30           # Session inactivity timeout
  cleanup_interval_minutes: 5   # Background cleanup frequency

intent_graph:
  auto_accumulate: true         # Automatically add intents from recordings
  deduplication: false          # No deduplication (keep all intents)
```

### 10.2 App Backend Configuration

**File**: `src/app_backend/config/app-backend.yaml`

```yaml
storage:
  base_path: auto  # Resolves to ~/.ami
  cache_workflows: true
  cache_metaflows: true

cloud:
  backend_url: http://localhost:8000
  sync_strategy: on_demand  # Download from cloud when needed
```

---

## 11. Future Considerations (Out of Scope)

The following are NOT part of current requirements but may be considered later:

### 11.1 Version History
- Keep multiple versions of MetaFlow/Workflow
- UI to compare versions
- Rollback functionality

### 11.2 Intent Graph Management
- Deduplication and similarity detection
- Manual intent editing UI
- Automatic pruning based on age/usage

### 11.3 Session History
- Resume previous sessions
- Session replay for debugging
- Session search and filtering

### 11.4 Database Migration
- Move metadata to relational database
- Advanced querying and indexing
- Better relationship management

### 11.5 Offline Support
- Bidirectional sync between cloud and local
- Conflict resolution
- Local-first workflow execution

---

## 12. Code Reference

**Key Implementation Files:**

| Component | File Path |
|-----------|-----------|
| Storage Service | `src/cloud_backend/services/storage_service.py` |
| Workflow Generation | `src/cloud_backend/services/workflow_generation_service.py` |
| Intent Builder Agent | `src/intent_builder/agent/intent_builder_agent.py` |
| API Endpoints | `src/cloud_backend/main.py` |
| Configuration | `src/cloud_backend/config/cloud-backend.yaml` |

**Critical Functions:**

| Function | Location | Line |
|----------|----------|------|
| `save_recording()` | storage_service.py | 84 |
| `save_metaflow()` | storage_service.py | 239 |
| `save_workflow()` | storage_service.py | 385 |
| `add_intents_to_graph()` | workflow_generation_service.py | 58 |
| `generate_metaflow_from_recording()` | workflow_generation_service.py | 224 |
| `generate_workflow_from_metaflow()` | workflow_generation_service.py | 191 |

---

## Appendix A: Directory Structure Examples

### Example 1: Complete Flow

```
~/ami-server/users/user123/
├── recordings/
│   └── session_20251128_092504/
│       ├── operations.json
│       └── metadata.json
│           {
│             "recording_id": "session_20251128_092504",
│             "metaflow_id": "metaflow_a4dcd97a343c",
│             "created_at": "2025-11-28T09:25:04Z",
│             "updated_at": "2025-11-28T09:30:12Z"
│           }
│
├── intent_graph.json
│   {
│     "intents": [
│       {
│         "intent_id": "intent_001",
│         "source_recording_id": "session_20251128_092504",
│         "description": "Search for products"
│       }
│     ]
│   }
│
├── metaflows/
│   └── metaflow_a4dcd97a343c/
│       ├── metaflow.yaml
│       └── metadata.json
│           {
│             "metaflow_id": "metaflow_a4dcd97a343c",
│             "workflow_id": "workflow_0c11d77f9472",
│             "source_recording_id": "session_20251128_092504",
│             "created_at": "2025-11-28T09:30:12Z",
│             "updated_at": "2025-11-28T09:35:00Z"
│           }
│
├── workflows/
│   └── workflow_0c11d77f9472/
│       ├── workflow.yaml
│       └── metadata.json
│           {
│             "workflow_id": "workflow_0c11d77f9472",
│             "source_metaflow_id": "metaflow_a4dcd97a343c",
│             "source_recording_id": "session_20251128_092504",
│             "created_at": "2025-11-28T09:35:00Z"
│           }
│
└── intent_builder/
    └── session_ib_abc123/
        ├── metaflow.yaml        # Currently editing
        └── .last_modified       # 2025-11-28 10:00:00
```

### Example 2: After Timeout Cleanup

```
# Before cleanup (10:00 AM - session active)
intent_builder/
├── session_ib_abc123/          # last_modified: 09:30 AM
│   └── metaflow.yaml
└── session_ib_xyz789/          # last_modified: 09:55 AM
    └── workflow.yaml

# After cleanup runs (10:05 AM)
intent_builder/
└── session_ib_xyz789/          # Kept (only 10 minutes old)
    └── workflow.yaml
# session_ib_abc123 deleted (35 minutes old, > 30 min threshold)
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-28 | Discussion with User | Initial requirements confirmed |

---

**End of Document**
