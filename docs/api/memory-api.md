# Memory API Documentation

This document describes the Memory API endpoints for managing user's Workflow Memory.

## Overview

The Memory API provides endpoints for:
- Adding recordings to workflow memory
- Querying memory using natural language (semantic search + path finding)
- Getting memory statistics
- Clearing memory

**Base URL**: `/api/v1/memory`

## Authentication

All endpoints require the `X-Ami-API-Key` header for operations that involve embedding generation.

```
X-Ami-API-Key: <user_api_key>
```

---

## Endpoints

### POST /api/v1/memory/add

Add a recording to the user's workflow memory.

#### Description

This endpoint processes a recording and adds its States, Actions, and IntentSequences to the user's workflow memory.

**Processing Pipeline:**
1. Parse recording operations
2. Segment by URL (each unique URL becomes a State)
3. Deduplicate States (same URL reuses existing State)
4. Create PageInstances for each URL visit
5. Create IntentSequences from operations within each State
6. Create Actions for state transitions
7. Optionally generate embeddings for semantic search

#### Request

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| Content-Type | Yes | `application/json` |
| X-Ami-API-Key | For embeddings | User's API key (required if `generate_embeddings: true`) |

**Body:**
```json
{
    "user_id": "user123",
    "recording_id": "recording_xxx",
    "operations": [...],
    "session_id": "session_xxx",
    "generate_embeddings": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | string | Yes | User identifier |
| recording_id | string | No* | Load operations from existing recording |
| operations | array | No* | Direct operations array |
| session_id | string | No | Session identifier |
| generate_embeddings | boolean | No | Generate embeddings for semantic search (default: false) |

*Either `recording_id` or `operations` must be provided.

#### Response

**Success (200):**
```json
{
    "success": true,
    "states_added": 3,
    "states_merged": 1,
    "page_instances_added": 4,
    "intent_sequences_added": 5,
    "actions_added": 2,
    "processing_time_ms": 150
}
```

---

### POST /api/v1/memory/query

Query the user's workflow memory using natural language.

#### Description

This endpoint performs intelligent semantic search on the user's workflow memory. The system automatically analyzes the query and returns the most relevant operation paths.

**Query Processing:**

The system handles two types of queries automatically:

1. **Path Query** (e.g., "通过榜单查看产品团队信息")
   - Identifies source concept ("榜单") and target concept ("团队")
   - Finds matching States using embedding similarity
   - Searches shortest path on graph
   - Returns complete operation path with IntentSequences

2. **Single-point Query** (e.g., "登录系统")
   - Finds matching State(s) using embedding similarity
   - Returns the State with its IntentSequences

**Search Process:**
```
Step 1: Semantic Retrieval
    - Generate embedding for query
    - Find matching State(s) by similarity

Step 2: Path Analysis (if multiple concepts detected)
    - Search shortest path between States on graph

Step 3: IntentSequence Matching
    - For each State in path, find relevant IntentSequences

Step 4: Return Results
    - Complete path with States, Actions, and IntentSequences
```

#### Request

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| Content-Type | Yes | `application/json` |
| X-Ami-API-Key | Yes | User's API key (required for embedding generation) |

**Body:**
```json
{
    "user_id": "user123",
    "query": "通过榜单查看产品团队信息",
    "top_k": 3,
    "min_score": 0.5,
    "domain": "producthunt.com",
    "debug": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| user_id | string | Yes | - | User identifier |
| query | string | Yes | - | Natural language query describing the task |
| top_k | integer | No | 3 | Number of paths to return |
| min_score | float | No | 0.5 | Minimum similarity score (0.0-1.0) |
| domain | string | No | - | Filter results by domain |
| debug | boolean | No | false | Include candidate states and score breakdown metadata |

#### Response

**Success (200):**
```json
{
    "success": true,
    "query": "通过榜单查看产品团队信息",
    "paths": [
        {
            "score": 0.85,
            "description": "从榜单页到团队页的操作路径",
            "steps": [
                {
                    "state": {
                        "id": "state_001",
                        "description": "ProductHunt Launches 榜单页",
                        "page_title": "Launches | Product Hunt",
                        "page_url": "https://www.producthunt.com/launches",
                        "domain": "producthunt.com"
                    },
                    "action": {
                        "id": "action_001",
                        "description": "点击产品列表项进入详情页",
                        "type": "navigate"
                    },
                    "intent_sequence": {
                        "id": "seq_001",
                        "description": "浏览榜单并选择产品",
                        "intents": [
                            {"type": "scroll", "text": null, "value": null},
                            {"type": "click", "text": "Noodle Seed", "value": null}
                        ]
                    }
                },
                {
                    "state": {
                        "id": "state_002",
                        "description": "ProductHunt 产品详情页",
                        "page_title": "Noodle Seed | Product Hunt",
                        "page_url": "https://www.producthunt.com/products/noodle-seed",
                        "domain": "producthunt.com"
                    },
                    "action": {
                        "id": "action_002",
                        "description": "点击 Team 标签查看团队",
                        "type": "navigate"
                    },
                    "intent_sequence": {
                        "id": "seq_002",
                        "description": "查看产品信息并导航到团队页",
                        "intents": [
                            {"type": "click", "text": "Team", "value": null}
                        ]
                    }
                },
                {
                    "state": {
                        "id": "state_003",
                        "description": "ProductHunt 团队页",
                        "page_title": "Team - Noodle Seed | Product Hunt",
                        "page_url": "https://www.producthunt.com/products/noodle-seed/team",
                        "domain": "producthunt.com"
                    },
                    "action": null,
                    "intent_sequence": {
                        "id": "seq_003",
                        "description": "查看团队成员信息",
                        "intents": [
                            {"type": "scroll", "text": null, "value": null}
                        ]
                    }
                }
            ]
        }
    ],
    "total_paths": 1
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| success | boolean | Operation success status |
| query | string | Original query |
| paths | array | List of matching operation paths |
| total_paths | integer | Number of paths returned |
| decomposed | object | Query decomposition with `target_query` and `key_queries` |
| candidate_states | object | (debug only) Candidate target/key states with similarity scores |
| score_weights | object | (debug only) Scoring weights used |
| score_formula | string | (debug only) Scoring formula string |

**Path Object:**

| Field | Type | Description |
|-------|------|-------------|
| score | float | Overall path relevance score (0.0-1.0) |
| description | string | Auto-generated path description |
| steps | array | Ordered list of steps in the path |

**Step Object:**

| Field | Type | Description |
|-------|------|-------------|
| state | object | The State (page) at this step |
| action | object/null | The Action to reach next step (null for last step) |
| intent_sequence | object/null | Most relevant IntentSequence for this State |

**Errors:**
| Status | Description |
|--------|-------------|
| 400 | Missing user_id or query |
| 503 | Memory service not initialized |
| 500 | Embedding service not available or query failed |

#### Example

```bash
curl -X POST http://localhost:9000/api/v1/memory/query \
    -H "Content-Type: application/json" \
    -H "X-Ami-API-Key: sk-ant-xxx" \
    -d '{
        "user_id": "user123",
        "query": "通过榜单查看产品团队信息"
    }'
```

---

### GET /api/v1/memory/stats

Get statistics about the user's workflow memory.

#### Request

**Query Parameters:**
| Parameter | Required | Description |
|-----------|----------|-------------|
| user_id | Yes | User identifier |

#### Response

**Success (200):**
```json
{
    "success": true,
    "user_id": "user123",
    "stats": {
        "total_states": 10,
        "total_intent_sequences": 25,
        "total_page_instances": 15,
        "total_actions": 8,
        "domains": ["producthunt.com", "google.com"],
        "url_index_size": 12
    }
}
```

---

### DELETE /api/v1/memory

Clear all data from the user's workflow memory.

#### Description

This endpoint deletes all States, Actions, and related data from the user's workflow memory. **This operation is irreversible.**

#### Request

**Query Parameters:**
| Parameter | Required | Description |
|-----------|----------|-------------|
| user_id | Yes | User identifier |

#### Response

**Success (200):**
```json
{
    "success": true,
    "deleted_states": 10,
    "deleted_actions": 8
}
```

---

## Usage Flow

### Typical Usage

1. **Record Browser Operations** (via desktop app)

2. **Upload Recording**:
   ```
   POST /api/v1/recordings
   ```

3. **Add to Memory with Embeddings**:
   ```
   POST /api/v1/memory/add
   {"user_id": "...", "recording_id": "...", "generate_embeddings": true}
   ```

4. **Query Memory** (later, when user needs help):
   ```
   POST /api/v1/memory/query
   {"user_id": "...", "query": "怎么通过榜单查看产品团队"}
   ```

5. **Agent Uses Path** for planning and execution

---

## Design Rationale

### Why Single Query Endpoint?

Users don't need to know internal data structures (State, IntentSequence, Action). They just want to ask "how to do X" and get a complete operation path.

The system automatically:
1. Understands the query intent
2. Finds relevant States using semantic search
3. Discovers paths between States
4. Returns actionable operation sequences

### Query Types Handled

| User Query | System Action |
|------------|---------------|
| "通过榜单查看团队" | Path query: 榜单页 → ... → 团队页 |
| "登录系统" | Single-point: Find login page + login operations |
| "搜索咖啡机" | Single-point: Find search page + search operations |
| "从首页到购物车结算" | Path query: 首页 → ... → 结算页 |
