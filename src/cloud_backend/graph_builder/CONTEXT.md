# graph_builder

LLM-free Recording to State/Action Graph conversion using **unified memgraph ontology**.

## Purpose

Convert raw browser recordings into structured State/Action Graphs using purely deterministic rules (NO LLM).

**UPDATED**: Now uses `memgraph.ontology` for unified data model:
- States contain Intents (operations within state)
- Actions represent state transitions only (no self-loops)
- Direct compatibility with `WorkflowMemory` storage

## Design Principles

1. **100% Deterministic** - Same recording always produces identical graph
2. **Rule-based Only** - No AI/LLM, no semantic understanding
3. **No Business Logic** - Pure structural compression
4. **Unified Ontology** - Uses `memgraph.ontology.{State, Intent, Action}`
5. **Acceptance Criteria**:
   - Same recording → 100% identical graph
   - No loss of click/navigation events
   - All operations preserved as Intents or Actions

## Pipeline

```
Raw Operations
  ↓
EventNormalizer (normalizer.py)
  ↓
NoiseReducer (noise_reducer.py)
  ↓
PhaseSegmenter (phase_segmenter.py)
  ↓
EpisodeSegmenter (episode_segmenter.py)
  ↓
GraphBuilder (graph_builder.py)
  ↓
StateActionGraph
```

## Key Files

- `models.py` - Data structures (Event, Phase, Episode, StateActionGraph) + imports memgraph.ontology.{State, Intent, Action}
- `normalizer.py` - Convert raw operations to normalized Events
- `noise_reducer.py` - Filter and merge redundant events
- `phase_segmenter.py` - Macro-level segmentation (URL/page changes)
- `episode_segmenter.py` - Medium-level segmentation (click/nav boundaries)
- `graph_builder.py` - Main orchestrator, builds graph with Intents and Actions

## Data Flow

### 1. Event Normalization

Raw operations (various formats) → Normalized Event schema

Event schema:
```python
Event(
    timestamp: int,
    type: "click" | "input" | "scroll" | "navigation",
    url: str,
    page_root: "main" | "iframe" | "modal",
    target: EventTarget,
    dom_hash: str,
    data: dict
)
```

### 2. Noise Reduction

Rules:
- Merge consecutive hovers (keep last)
- Merge consecutive scrolls within 500ms window
- Deduplicate rapid inputs (keep final value)
- Remove standalone hovers
- Remove dataload events (system events)

### 3. Phase Segmentation

Split signals:
- **Strong** (must split): URL path change, page_root change
- **Weak** (≥2 required): idle timeout (3s), operation type change, URL params change

### 4. Episode Segmentation

Rules:
- click/navigation → Episode boundary
- Consecutive inputs → Merge
- Filter noise episodes (scroll-only, hover-only)

### 5. Graph Construction

Build State/Action Graph using memgraph ontology:
- **States**: Unique (URL, page_root) combinations (memgraph.ontology.State)
  - Each State contains **Intents** (operations within that state)
- **Actions**: State transitions only (memgraph.ontology.Action)
  - NO self-loops (operations within same state are Intents)
- **Phases**: Macro-level segments (internal processing)
- **Episodes**: Medium-level segments (internal processing)

**Key difference from old version:**
- OLD: All operations → ActionEdge (including self-loops)
- NEW: Self-loop operations → Intent (in State.intents), State transitions → Action

## Usage

```python
from src.cloud_backend.graph_builder import GraphBuilder

# Initialize with user/session IDs (optional)
builder = GraphBuilder(
    user_id="user_123",
    session_id="session_456"
)

# Build graph from raw recording
operations = [...]  # Raw operations from recording
graph = builder.build(operations)

# Access graph components
print(f"States: {len(graph.states)}")
print(f"Actions: {len(graph.actions)}")  # UPDATED: actions instead of edges
print(f"Phases: {len(graph.phases)}")
print(f"Episodes: {len(graph.episodes)}")

# Access States with Intents
for state_id, state in graph.states.items():
    print(f"State {state_id}: {state.page_url}")
    print(f"  Intents: {len(state.intents)}")
    for intent in state.intents:
        print(f"    - {intent.type}: {intent.text or intent.value}")

# Access Actions (state transitions only)
for action in graph.actions:
    print(f"Action: {action.source} → {action.target} ({action.type})")

# Export to dict
graph_dict = graph.to_dict()
```

### Direct Storage to WorkflowMemory

```python
from src.cloud_backend.memgraph.memory.workflow_memory import WorkflowMemory
from src.cloud_backend.memgraph.graphstore.networkx_graph import NetworkXGraph

# Create memory
graph_store = NetworkXGraph()
memory = WorkflowMemory(graph_store)

# Store graph (no adapter needed!)
for state in graph.states.values():
    memory.create_state(state)  # State already contains Intents

for action in graph.actions:
    memory.create_action(action)  # Actions are already memgraph.Action

# Query
states = memory.list_states(session_id="session_456")
actions = memory.list_actions(user_id="user_123")
```

## Configuration

Tunable parameters in `GraphBuilder`:
- `idle_threshold_ms` - Idle duration for phase boundary (default: 3000)
- `scroll_merge_window_ms` - Scroll merge window (default: 500)
- `input_debounce_ms` - Input debounce window (default: 500)
- `hover_merge_window_ms` - Hover merge window (default: 200)

## Constraints

- **No LLM** - All processing is rule-based
- **No Semantic Understanding** - Pure structural analysis
- **Deterministic** - Must be reproducible
- **Complete** - Cannot lose click/navigation events

## Integration

Used by cloud_backend APIs:
- `POST /api/v1/recordings` - Upload recording, build graph
- `GET /api/v1/recordings/{id}` - Return recording with graph

## Testing

Test for determinism:
```python
graph1 = builder.build(operations)
graph2 = builder.build(operations)
assert graph1.to_dict() == graph2.to_dict()  # Must be identical
```
