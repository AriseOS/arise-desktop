# Memory Graph System Testing Guide

> Human Testing Guide for URL-based Workflow Processing (memory-graph-ontology-design.md)

## Quick Start

### 1. Run Quick Tests (No API Keys Required)

```bash
cd /Users/shenyouren/workspace/2ami
python -m src.cloud_backend.memgraph.tests.test_memory_workflow --quick
```

This tests all new data structures without LLM/Embedding:
- URLIndex
- PageInstance
- IntentSequence
- State with new fields
- WorkflowMemory methods
- URLSegment

### 2. Run Full Tests (Requires API Keys)

```bash
# Set environment variables first
export ANTHROPIC_API_KEY=your_key
# or
export OPENAI_API_KEY=your_key

# Optional: for embedding
export SILICONFLOW_API_KEY=your_key

# Run full test
python -m src.cloud_backend.memgraph.tests.test_memory_workflow --full
```

---

## Manual Testing Scenarios

### Scenario 1: URL Index Lookup (O(1) Performance)

**Purpose**: Verify URL to State mapping works correctly.

```python
from src.cloud_backend.memgraph.memory.url_index import URLIndex

# Create index
url_index = URLIndex()

# Add URLs
url_index.add_url("https://example.com/page1", "state-1")
url_index.add_url("https://example.com/page2", "state-2")
url_index.add_url("https://example.com/page1?ref=email", "state-1")

# Test lookup
assert url_index.find_state_by_url("https://example.com/page1") == "state-1"
assert url_index.find_state_by_url("https://example.com/unknown") is None

# URL exact match (with query params)
assert url_index.find_state_by_url("https://example.com/page1") != \
       url_index.find_state_by_url("https://example.com/page1?ref=email")

print("URL Index tests passed!")
```

**Expected**: URL lookup is O(1), exact matching includes query parameters.

---

### Scenario 2: State Reuse (Real-time Merge)

**Purpose**: Same URL should reuse existing State, not create new one.

```python
from src.cloud_backend.memgraph.graphstore.networkx_graph import NetworkXGraph
from src.cloud_backend.memgraph.memory.workflow_memory import WorkflowMemory

graph = NetworkXGraph()
memory = WorkflowMemory(graph)

# First visit
state1, is_new1 = memory.find_or_create_state(
    url="https://example.com/home",
    page_title="Home Page",
    timestamp=1705000000000,
)
print(f"First visit: is_new={is_new1}")  # Should be True

# Second visit (same URL, different session)
state2, is_new2 = memory.find_or_create_state(
    url="https://example.com/home",
    page_title="Home Page",
    timestamp=1705001000000,
)
print(f"Second visit: is_new={is_new2}")  # Should be False
print(f"Same State: {state1.id == state2.id}")  # Should be True
```

**Expected**: Second call returns existing State (is_new=False), same State ID.

---

### Scenario 3: PageInstance Collection

**Purpose**: Multiple URL visits should create multiple PageInstances in the same State.

```python
from src.cloud_backend.memgraph.ontology.page_instance import PageInstance

# After Scenario 2, add instances
instance1 = PageInstance(
    url="https://example.com/home",
    timestamp=1705000000000,
)
instance2 = PageInstance(
    url="https://example.com/home",
    timestamp=1705001000000,
)

memory.add_page_instance(state1.id, instance1)
memory.add_page_instance(state1.id, instance2)

# Verify
retrieved = memory.get_state(state1.id)
print(f"PageInstances count: {len(retrieved.instances)}")  # Should be 2
```

**Expected**: One State with multiple PageInstances.

---

### Scenario 4: IntentSequence Deduplication

**Purpose**: Same description should not create duplicate IntentSequence.

```python
from src.cloud_backend.memgraph.ontology.intent_sequence import IntentSequence
from src.cloud_backend.memgraph.ontology.intent import Intent

seq1 = IntentSequence(
    timestamp=1705000001000,
    intents=[Intent(type="ClickElement", timestamp=1705000001000, text="Login")],
    description="User login",
)

seq2 = IntentSequence(
    timestamp=1705001001000,
    intents=[Intent(type="ClickElement", timestamp=1705001001000, text="Login")],
    description="User login",  # Same description
)

seq3 = IntentSequence(
    timestamp=1705002001000,
    intents=[],
    description="Different action",  # Different description
)

memory.add_intent_sequence(state1.id, seq1)
memory.add_intent_sequence(state1.id, seq2)  # Should be rejected
memory.add_intent_sequence(state1.id, seq3)

retrieved = memory.get_state(state1.id)
print(f"IntentSequences count: {len(retrieved.intent_sequences)}")  # Should be 2
```

**Expected**: Duplicate description rejected, different descriptions kept.

---

### Scenario 5: Workflow Processing Pipeline

**Purpose**: Complete workflow should be processed correctly.

```python
from src.cloud_backend.memgraph.thinker.workflow_processor import WorkflowProcessor
from src.cloud_backend.memgraph.services import MockLLMClient

# Setup
graph = NetworkXGraph()
memory = WorkflowMemory(graph)
llm = MockLLMClient()
processor = WorkflowProcessor(llm_client=llm, memory=memory)

# Sample workflow
workflow = [
    {"type": "navigate", "url": "https://example.com/home", "title": "Home", "timestamp": 1705000000000},
    {"type": "click", "element_tag": "input", "text": "", "timestamp": 1705000001000},
    {"type": "input", "value": "test", "timestamp": 1705000002000},
    {"type": "navigate", "url": "https://example.com/search", "title": "Search", "timestamp": 1705000003000},
    {"type": "click", "element_tag": "a", "text": "Result 1", "timestamp": 1705000004000},
    {"type": "navigate", "url": "https://example.com/detail", "title": "Detail", "timestamp": 1705000005000},
]

result = processor.process_workflow(
    workflow_data=workflow,
    user_id="test_user",
    session_id="test_session",
    store_to_memory=True,
)

print(f"States created: {result.metadata['new_states']}")  # Should be 3
print(f"PageInstances: {len(result.page_instances)}")  # Should be 3
print(f"IntentSequences: {len(result.intent_sequences)}")  # Should be 2 (last segment has no events)
print(f"Actions: {len(result.actions)}")  # Should be 2

# Test State reuse with same workflow
result2 = processor.process_workflow(
    workflow_data=workflow,
    user_id="test_user",
    session_id="session_2",
)

print(f"Second run - Reused States: {result2.metadata['reused_states']}")  # Should be 3
print(f"Second run - New States: {result2.metadata['new_states']}")  # Should be 0
```

**Expected**:
- First run: 3 new States, 3 PageInstances, 2 IntentSequences, 2 Actions
- Second run: 3 reused States, 0 new States

---

### Scenario 6: Path Finding

**Purpose**: Find shortest path between States.

```python
# After Scenario 5
states = memory.state_manager.list_states()
home_state = memory.find_state_by_url("https://example.com/home")
detail_state = memory.find_state_by_url("https://example.com/detail")

path = memory.find_path(home_state.id, detail_state.id)

if path:
    print("Path found:")
    for state, action in path:
        action_str = f" --[{action.type}]--> " if action else ""
        print(f"  {state.page_title}{action_str}")
else:
    print("No path found")
```

**Expected**: Path from Home -> Search -> Detail

---

### Scenario 7: Semantic Search on IntentSequences

**Purpose**: Find similar operation sequences by embedding.

```python
# Requires embedding service
from src.cloud_backend.memgraph.services import EmbeddingService

# Configure embedding (example with SiliconFlow)
EmbeddingService.configure(
    provider="openai",
    model="BAAI/bge-m3",
    dimension=1024,
    api_url="https://api.siliconflow.cn/v1",
    api_key=os.getenv("SILICONFLOW_API_KEY"),
)

# Search
query = "input text and submit"
query_embedding = EmbeddingService.embed(query)

results = memory.search_intent_sequences_by_embedding(
    query_vector=query_embedding,
    top_k=5,
)

print(f"Found {len(results)} matching sequences:")
for seq, state, score in results:
    print(f"  [{score:.3f}] {seq.description} (in {state.page_title})")
```

**Expected**: Returns IntentSequences sorted by similarity score.

---

## Verification Checklist

### Core Functionality

| Feature | How to Verify | Expected |
|---------|--------------|----------|
| URL Index O(1) | Lookup 10,000 URLs | < 1ms per lookup |
| State Reuse | Same URL twice | Same State ID |
| PageInstance | Visit same URL | 2 PageInstances in 1 State |
| IntentSequence Dedup | Same description | Only 1 kept |
| Empty Segment | Navigate-only segment | No IntentSequence created |
| Path Finding | find_path(A, B) | Returns correct path |
| Semantic Search | search by embedding | Sorted by similarity |

### Data Structure Integrity

| Check | Command | Expected |
|-------|---------|----------|
| State has instances | `state.instances` | List of PageInstance |
| State has intent_sequences | `state.intent_sequences` | List of IntentSequence |
| IntentSequence has intents | `seq.intents` | List of Intent |
| URL Index consistent | `memory.url_index.get_stats()` | Matches actual State count |

### Serialization

| Object | Test | Command |
|--------|------|---------|
| PageInstance | Round-trip | `PageInstance.from_dict(instance.to_dict())` |
| IntentSequence | Round-trip | `IntentSequence.from_dict(seq.to_dict())` |
| State | Round-trip | `State.from_dict(state.to_dict())` |

---

## Common Issues

### Issue 1: URL Index Not Updated

**Symptom**: State reuse not working, always creates new States.

**Check**:
```python
print(memory.url_index.get_stats())
# Should show correct URL count
```

**Fix**: Call `memory.rebuild_url_index()` after bulk operations.

### Issue 2: Empty IntentSequences

**Symptom**: IntentSequences with no intents in State.

**Check**: Per design, empty IntentSequences should not be created.

**Verify**:
```python
for state in memory.state_manager.list_states():
    for seq in state.intent_sequences:
        assert len(seq.intents) > 0, f"Empty IntentSequence found in {state.id}"
```

### Issue 3: Duplicate IntentSequences

**Symptom**: Same description appears multiple times.

**Check**: Deduplication should work by description.

**Verify**:
```python
for state in memory.state_manager.list_states():
    descriptions = [seq.description for seq in state.intent_sequences]
    assert len(descriptions) == len(set(descriptions)), f"Duplicates in {state.id}"
```

---

## Performance Benchmarks

### Expected Performance

| Operation | Target | Actual |
|-----------|--------|--------|
| URL lookup | < 1ms | |
| State creation | < 10ms | |
| Workflow processing (3 pages, no LLM) | < 100ms | |
| Workflow processing (3 pages, with LLM) | < 10s | |

### How to Measure

```python
import time

start = time.time()
# ... operation ...
elapsed = (time.time() - start) * 1000
print(f"Elapsed: {elapsed:.2f}ms")
```

---

## Environment Setup

### Required Dependencies

```bash
pip install pydantic networkx
```

### Optional (for full tests)

```bash
pip install anthropic openai
```

### Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| ANTHROPIC_API_KEY | Claude API | For LLM |
| OPENAI_API_KEY | OpenAI API | Alternative LLM |
| SILICONFLOW_API_KEY | Embedding | For semantic search |

---

## Summary

The new Memory Graph system implements:

1. **AbstractState (State)**: Graph nodes representing page types, not specific URLs
2. **PageInstance**: Concrete URL visits stored within States
3. **IntentSequence**: Ordered operation sequences with semantic description
4. **URLIndex**: O(1) URL to State lookup for real-time merge
5. **Path Finding**: BFS shortest path between States
6. **Semantic Search**: Embedding-based search on IntentSequences

Key behaviors:
- Same URL → Same State (real-time merge)
- Different query params → Different States (exact URL match)
- Same description → Deduplicated IntentSequence
- Empty segment → No IntentSequence created
