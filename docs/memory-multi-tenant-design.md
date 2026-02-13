# Memory Multi-Tenant Design: Private + Public Memory

## 1. Background

### Current State

The Memory system currently has **no effective user isolation**:

- All ontology classes (State, Action, IntentSequence, CognitivePhrase, Domain) have `user_id: Optional[str]` fields
- WorkflowProcessor **explicitly disables** user_id on all created objects (comments: `user_id=None, # user isolation disabled`)
- Vector search (`vector_search()`) has **no user_id filtering** — results come from all users
- Reasoner accepts `user_id` parameter but **never uses it** (docstring: "not yet implemented")
- SurrealDB creates `user_id` indexes but they are unused
- All users share one SurrealDB namespace/database: `ami/memory`

### Existing Abstraction Layer

`memory_service.py` already defines `_local_memory_service` and `_public_memory_service` global instances with `get_local_memory_service()` / `get_public_memory_service()` accessors. These are currently unused — only `get_memory_service()` (which returns the public instance) is called.

---

## 2. Design Goals

1. **Each user has a private Memory** — isolated at SurrealDB database level
2. **A shared Public Memory** — users can share workflows to it
3. **Contributor tracking** — Public data records who contributed it
4. **Usage tracking + token reward** — use_count / upvote triggers token for contributor
5. **Phase 1 all-cloud; Phase 2 local-private** — architecture must not block local deployment

---

## 3. Storage Topology

### Phase 1: All-Cloud

```
Cloud SurrealDB Server (ws://host:port)
  namespace: ami
    ├── database: private_{user_id}     ← Per-user Private Memory
    │     ├── state
    │     ├── intentsequence
    │     ├── cognitivephrase
    │     ├── action              (TYPE RELATION)
    │     ├── has_sequence         (TYPE RELATION)
    │     ├── manages              (TYPE RELATION)
    │     └── domain
    │
    └── database: public                ← Shared Public Memory
          ├── state
          ├── intentsequence
          ├── cognitivephrase           ← + contributor fields
          ├── action              (TYPE RELATION)
          ├── has_sequence         (TYPE RELATION)
          ├── manages              (TYPE RELATION)
          └── domain
```

**Key property**: Each database has independent tables, indexes, and vector indexes. Vector search within `private_alice` only returns Alice's data — **zero filtering needed**.

### Phase 2: Local Private (Future)

```
Desktop App (file://~/.ami/memory.db)
  namespace: ami
    └── database: private              ← Local, single-user, physically isolated

Cloud SurrealDB Server
  namespace: ami
    └── database: public               ← Shared (queried via HTTP API)
```

Only change: `url` switches from `ws://cloud:8000` to `file://~/.ami/memory.db`. GraphStore interface unchanged.

---

## 4. Data Model Changes

### 4.1 Remove user_id from Ontology Classes

Since isolation is at the **database level**, individual records no longer need `user_id`. Each private database belongs to exactly one user.

**Files to modify:**

| File | Change |
|------|--------|
| `ontology/state.py` | Remove `user_id` field (line 77) |
| `ontology/action.py` | Remove `user_id` field (line 80) |
| `ontology/intent_sequence.py` | Remove `user_id` field (line 82) |
| `ontology/cognitive_phrase.py` | Remove `user_id` field (line 98) |
| `ontology/domain.py` | Remove `user_id` field (line 109) |
| `ontology/domain.py` (Manage) | Remove `user_id` field (line 214) |

**Rationale**: With database-level isolation, `user_id` on every record is redundant. It adds complexity (must be set, must be filtered) for zero benefit. The database name **is** the user identity.

### 4.2 Remove user_id from WorkflowProcessor

**File**: `thinker/workflow_processor.py`

All the `user_id=None, # user isolation disabled` comments and dead parameters can be cleaned up:

- Remove `user_id` parameter from `process_workflow()` (line 180)
- Remove all `user_id=None` assignments on State, Action, IntentSequence, CognitivePhrase creation (~15 locations)
- Remove `user_id` parameter from `find_or_create_state()` in workflow_memory.py

### 4.3 Remove user_id from WorkflowMemory Query Methods

**File**: `memory/workflow_memory.py`

Remove `user_id` parameter from:
- `list_states()` (line 445)
- `list_actions()` (line 877)
- `list_phrases()` (line 1363)
- `list_domains()` (line 124)
- `list_manages()` (line 291)
- `find_or_create_state()` (line 2208)

These methods no longer need filtering — they always operate within a single-user database.

### 4.4 Remove user_id from Reasoner

**File**: `reasoner/reasoner.py`

- Remove `user_id` and `session_id` parameters from `plan()` (line 273)
- Remove the "not yet implemented" dead code paths

### 4.5 Remove user_id Indexes from Schema

**File**: `graphstore/surrealdb_graph.py` (initialize_schema)

Remove user_id indexes (lines 418-425):
```python
# REMOVE these:
("state", "user_id"),
("domain", "user_id"),
("cognitivephrase", "user_id"),
```

**File**: `graphstore/neo4j_graph.py` (initialize_schema)

Remove user_id indexes (lines 130-134):
```python
# REMOVE these:
state_user_id, domain_user_id, phrase_user_id
```

### 4.6 Public Memory: Contributor Fields on CognitivePhrase

For the **Public** database only, CognitivePhrase needs additional fields to track contribution:

```python
class CognitivePhrase(BaseModel):
    # ... existing fields ...

    # Contributor tracking (only populated in Public Memory)
    contributor_id: Optional[str] = Field(
        default=None,
        description="User ID of the contributor (who shared this workflow)"
    )
    contributed_at: Optional[int] = Field(
        default=None,
        description="When this workflow was shared to public (milliseconds)"
    )
    source_phrase_id: Optional[str] = Field(
        default=None,
        description="Original phrase ID in contributor's private memory"
    )

    # Usage tracking (only populated in Public Memory)
    use_count: int = Field(
        default=0,
        description="Number of times this workflow was used by others"
    )
    upvote_count: int = Field(
        default=0,
        description="Number of positive ratings from users"
    )
```

These fields are Optional, defaulting to None/0. In Private databases they are simply unused. SurrealDB is SCHEMALESS — extra fields have zero cost.

---

## 5. MemoryService Redesign

### 5.1 Current Design (Single-Instance)

```python
_local_memory_service: Optional[MemoryService] = None    # unused
_public_memory_service: Optional[MemoryService] = None    # the only one used
```

### 5.2 New Design (Per-User Private + Shared Public)

```python
# Per-user private memory instances (lazy-initialized, cached)
_private_stores: Dict[str, MemoryService] = {}

# Shared public memory (single instance)
_public_memory_service: Optional[MemoryService] = None

# Base config (shared SurrealDB connection settings)
_base_config: Optional[MemoryServiceConfig] = None


def get_private_memory(user_id: str) -> MemoryService:
    """Get or create a private MemoryService for the given user.

    Creates a new SurrealDB database `private_{user_id}` on first access.
    Subsequent calls return the cached instance.
    """
    if user_id not in _private_stores:
        config = MemoryServiceConfig(
            graph_backend=_base_config.graph_backend,
            graph_url=_base_config.graph_url,
            graph_namespace=_base_config.graph_namespace,
            graph_database=f"private_{user_id}",   # per-user database
            graph_username=_base_config.graph_username,
            graph_password=_base_config.graph_password,
            vector_dimensions=_base_config.vector_dimensions,
        )
        service = MemoryService(config)
        service.initialize()   # creates database + schema + indexes if not exist
        _private_stores[user_id] = service
    return _private_stores[user_id]


def get_public_memory() -> MemoryService:
    """Get the shared public MemoryService."""
    return _public_memory_service


def init_memory_services(base_config: MemoryServiceConfig) -> None:
    """Initialize the memory service infrastructure.

    Sets up:
    - Base config for creating per-user private instances
    - Public memory service (database: "public")
    """
    global _base_config, _public_memory_service
    _base_config = base_config

    public_config = MemoryServiceConfig(
        graph_backend=base_config.graph_backend,
        graph_url=base_config.graph_url,
        graph_namespace=base_config.graph_namespace,
        graph_database="public",
        graph_username=base_config.graph_username,
        graph_password=base_config.graph_password,
        vector_dimensions=base_config.vector_dimensions,
    )
    _public_memory_service = MemoryService(public_config)
    _public_memory_service.initialize()
```

### 5.3 Cache Eviction

For production with many users, private stores need eviction:

```python
from collections import OrderedDict

MAX_CACHED_PRIVATE_STORES = 100

_private_stores: OrderedDict[str, MemoryService] = OrderedDict()

def get_private_memory(user_id: str) -> MemoryService:
    if user_id in _private_stores:
        _private_stores.move_to_end(user_id)
        return _private_stores[user_id]

    # Evict oldest if at capacity
    if len(_private_stores) >= MAX_CACHED_PRIVATE_STORES:
        _, old_service = _private_stores.popitem(last=False)
        old_service.close()

    # Create new
    service = _create_private_service(user_id)
    _private_stores[user_id] = service
    return service
```

Note: SurrealDB database itself persists. Eviction only closes the Python GraphStore connection — data is not lost.

---

## 6. Query Flow

### 6.1 User Query (Private + Public Merge)

When an Agent queries Memory, it should search both Private and Public:

```
Agent: query("在 PH 查看团队信息")
  │
  ├── Concurrent
  │   ├── get_private_memory(user_id).query(target) → results_private
  │   └── get_public_memory().query(target)          → results_public
  │
  ├── Merge
  │   ├── Private results first (user's own experience takes priority)
  │   ├── Deduplicate by source_phrase_id (don't show same workflow twice)
  │   └── Return merged list
  │
  └── If public result used → increment use_count on that CognitivePhrase
```

### 6.2 Implementation in MemoryService

Add a top-level query method that merges:

```python
async def query_merged(
    user_id: str,
    target: str,
    top_k: int = 5,
    **kwargs,
) -> Dict[str, Any]:
    """Query both private and public memory, merge results.

    Private results are prioritized. Public results are deduplicated
    against private results.

    Returns:
        Merged query result with source annotation (private/public).
    """
    private_service = get_private_memory(user_id)
    public_service = get_public_memory()

    # Concurrent queries
    private_result, public_result = await asyncio.gather(
        private_service.query(target, top_k=top_k, **kwargs),
        public_service.query(target, top_k=top_k, **kwargs),
    )

    # Merge: private first, then public (deduplicated)
    merged = _merge_results(private_result, public_result)
    return merged
```

### 6.3 API Endpoint Changes

**File**: `cloud_backend/main.py`

All memory endpoints need to route to the correct database:

| Endpoint | Current | New |
|----------|---------|-----|
| `POST /api/v1/memory/add` | Writes to shared `memory` db | Writes to `private_{user_id}` |
| `POST /api/v1/memory/query` | Searches shared `memory` db | Searches `private_{user_id}` + `public`, merges |
| `POST /api/v1/memory/v2/query` | Same | Same |
| `GET /api/v1/memory/stats` | Stats for shared db | Stats for `private_{user_id}` |
| `DELETE /api/v1/memory` | Clears shared db | Clears `private_{user_id}` only |
| `GET /api/v1/memory/phrases` | Lists all phrases | Lists from `private_{user_id}` |
| `POST /api/v1/memory/share` | N/A (new) | Copies phrase from private to public |

---

## 7. Share Flow

### 7.1 Share Operation

When a user shares a CognitivePhrase to Public:

```
POST /api/v1/memory/share
{
    "user_id": "alice",
    "phrase_id": "phrase_xxx"
}

Steps:
  1. Read CognitivePhrase from private_alice
  2. Read all referenced entities:
     - States referenced in execution_plan[].state_id
     - Actions referenced in execution_plan[].navigation_action_id
     - IntentSequences referenced in execution_plan[].in_page_sequence_ids
       and execution_plan[].navigation_sequence_id
     - Domain(s) referenced by States
  3. Deep-copy all entities to public database:
     - Generate new IDs for all entities (avoid cross-user ID collision)
     - Update all internal references (state_id, action source/target, etc.)
     - Set contributor fields on CognitivePhrase
  4. Return the new public phrase ID
```

### 7.2 ID Remapping

All entity IDs in the original Private database are UUIDs. When copying to Public, generate new UUIDs and maintain a mapping:

```python
async def share_phrase(user_id: str, phrase_id: str) -> str:
    """Copy a CognitivePhrase and its dependencies to public memory.

    Returns:
        New phrase ID in public database.
    """
    private = get_private_memory(user_id)
    public = get_public_memory()

    # 1. Load phrase and dependencies
    phrase = private.workflow_memory.phrase_manager.get_phrase(phrase_id)
    if not phrase:
        raise ValueError(f"Phrase {phrase_id} not found")

    # 2. Collect all referenced entity IDs
    state_ids = set()
    action_ids = set()
    sequence_ids = set()
    for step in phrase.execution_plan:
        state_ids.add(step.state_id)
        if step.navigation_action_id:
            action_ids.add(step.navigation_action_id)
        sequence_ids.update(step.in_page_sequence_ids)
        if step.navigation_sequence_id:
            sequence_ids.add(step.navigation_sequence_id)

    # 3. Load all entities
    states = {sid: private.workflow_memory.state_manager.get_state(sid) for sid in state_ids}
    actions = {aid: private.workflow_memory.action_manager.get_action_by_id(aid) for aid in action_ids}
    sequences = {seqid: private.workflow_memory.intent_sequence_manager.get_intent_sequence(seqid) for seqid in sequence_ids}

    # 4. Generate new IDs (old_id → new_id mapping)
    id_map = {}
    for old_id in list(state_ids) + list(action_ids) + list(sequence_ids) + [phrase_id]:
        id_map[old_id] = str(uuid.uuid4())

    # 5. Deep-copy with remapped IDs to public database
    # ... (remap all internal references using id_map)

    # 6. Set contributor fields on new phrase
    new_phrase = phrase.model_copy(deep=True)
    new_phrase.id = id_map[phrase_id]
    new_phrase.contributor_id = user_id
    new_phrase.contributed_at = int(time.time() * 1000)
    new_phrase.source_phrase_id = phrase_id
    new_phrase.use_count = 0
    new_phrase.upvote_count = 0

    # 7. Store to public database
    # ... (upsert all remapped entities)

    return new_phrase.id
```

---

## 8. Token Incentive Mechanism

### 8.1 Trigger Conditions

| Event | Action |
|-------|--------|
| Agent uses a Public CognitivePhrase in task execution | `use_count += 1` |
| User explicitly upvotes after successful task | `upvote_count += 1`, trigger token reward |

### 8.2 Token Tracking

Token rewards are tracked separately from Memory (not in the graph database):

```
Token ledger (in main database, e.g., SQLite/PostgreSQL):
  ├── user_id
  ├── event_type: "share_upvote"
  ├── phrase_id: (public phrase ID)
  ├── amount: token amount
  └── timestamp
```

Token calculation:
- Each upvote = base_token_amount (configurable)
- Future: weighted by use_count, complexity, etc.

### 8.3 Implementation Sequence

Token mechanism can be implemented independently from storage isolation:
1. **Phase 1a**: Private/Public isolation (this document)
2. **Phase 1b**: Share flow (copy to public with contributor tracking)
3. **Phase 1c**: use_count / upvote_count tracking
4. **Phase 1d**: Token ledger + reward logic

---

## 9. SurrealDB Specifics

### 9.1 Database Auto-Creation

SurrealDB's `DEFINE DATABASE IF NOT EXISTS` in the `_connect()` method (surrealdb_graph.py line 303) already handles automatic database creation. When `get_private_memory("alice")` creates a store with `database="private_alice"`, the connection flow:

```
1. DEFINE NAMESPACE IF NOT EXISTS ami;
2. USE NS ami;
3. DEFINE DATABASE IF NOT EXISTS private_alice;
4. USE NS ami DB private_alice;
5. initialize_schema()   ← creates tables + indexes
```

No manual database creation step needed.

### 9.2 Database Naming Convention

```
private_{user_id}    ← user's private memory
public               ← shared public memory
```

`user_id` must be sanitized for SurrealDB identifiers:
- Replace non-alphanumeric characters with `_`
- Ensure it doesn't start with a digit
- Or: use a hash/UUID as database suffix if user_id format is unpredictable

### 9.3 Schema Consistency

`initialize_schema()` is called once per database when the MemoryService is first created for that database. The schema (tables, indexes, vector indexes) is identical for Private and Public databases. The only difference is in the data stored (Public has contributor fields populated).

### 9.4 Connection Pooling

Each MemoryService → SurrealDBGraphStore has its own connection(s). With the LRU cache (MAX_CACHED_PRIVATE_STORES = 100), at most 100 concurrent connections to SurrealDB for private databases + 1 for public.

SurrealDB WebSocket connections are lightweight. For embedded mode (Phase 2), each file-based connection is even lighter.

---

## 10. Migration Plan

### 10.1 Steps

Since the current system stores all data with `user_id=None` and no real isolation exists, migration is straightforward:

1. **Create Public database**: Move all existing data from `memory` database to `public` database
2. **No Private migration needed**: Private databases start empty; users re-record or existing data goes to Public
3. **Remove user_id fields**: Clean up ontology classes
4. **Update API endpoints**: Route to correct database based on user_id
5. **Deploy**: SurrealDB server continues running; only database routing changes

### 10.2 Backward Compatibility

- Old API clients still send `user_id` in request body → used to route to correct private database
- Old data (with `user_id=None`) stays in legacy `memory` database or moves to `public`
- No client-side changes needed (API contract stays the same, just routing changes server-side)

---

## 11. Files to Modify

### Ontology (remove user_id)
- `src/common/memory/ontology/state.py`
- `src/common/memory/ontology/action.py`
- `src/common/memory/ontology/intent_sequence.py`
- `src/common/memory/ontology/cognitive_phrase.py` (remove user_id; add contributor fields)
- `src/common/memory/ontology/domain.py` (State and Manage classes)

### WorkflowProcessor (remove user_id dead code)
- `src/common/memory/thinker/workflow_processor.py` (~15 locations)

### WorkflowMemory (remove user_id from query methods)
- `src/common/memory/memory/workflow_memory.py`

### Reasoner (remove user_id parameter)
- `src/common/memory/reasoner/reasoner.py`

### GraphStore Schema (remove user_id indexes)
- `src/common/memory/graphstore/surrealdb_graph.py`
- `src/common/memory/graphstore/neo4j_graph.py`

### MemoryService (per-user private + shared public)
- `src/common/memory/memory_service.py` (major rewrite)

### Cloud Backend (route to correct database)
- `src/cloud_backend/main.py` (all memory endpoints)

### New Files
- Share endpoint logic (in main.py or new module)
- Token tracking (separate from memory, in cloud_backend)

---

## 12. Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Isolation** | None (shared database, user_id=None) | SurrealDB database-level per user |
| **user_id on records** | Optional field, never set | Removed (database = identity) |
| **Vector search isolation** | None (global search) | Natural (per-database index) |
| **Public sharing** | N/A | Copy phrase + dependencies to `public` db |
| **Contributor tracking** | N/A | `contributor_id` on Public CognitivePhrase |
| **Token incentive** | N/A | use_count + upvote → token reward |
| **Phase 1** | All-cloud | All-cloud (ws:// to SurrealDB server) |
| **Phase 2** | N/A | Private → local file://, Public → cloud API |
| **GraphStore interface** | Unchanged | Unchanged |
| **MemoryService** | Single global instance | Per-user private + shared public |
