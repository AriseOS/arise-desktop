# Graph Builder

**LLM-free Recording → State/Action Graph Converter**

## Overview

The Graph Builder module converts raw browser recordings into structured State/Action Graphs using **purely deterministic rules** (NO LLM). This is the first stage in the workflow generation pipeline.

## Key Features

✅ **100% Deterministic** - Same recording always produces identical graph
✅ **No LLM** - All processing is rule-based
✅ **No Semantic Understanding** - Pure structural transformation
✅ **Complete** - No loss of click/navigation events
✅ **Google Style Guide Compliant** - Clean, well-documented code

## Architecture

```
Recording Operations (raw)
         ↓
┌────────────────────┐
│ EventNormalizer    │  Convert to normalized Event schema
└─────────┬──────────┘
          ↓
┌────────────────────┐
│ NoiseReducer       │  Merge hovers, scrolls, inputs
└─────────┬──────────┘
          ↓
┌────────────────────┐
│ PhaseSegmenter     │  Macro-level segmentation (URL changes)
└─────────┬──────────┘
          ↓
┌────────────────────┐
│ EpisodeSegmenter   │  Medium-level segmentation (click/nav boundaries)
└─────────┬──────────┘
          ↓
┌────────────────────┐
│ GraphBuilder       │  Build States + Edges
└─────────┬──────────┘
          ↓
   StateActionGraph
```

## Module Structure

```
graph_builder/
├── __init__.py              # Module exports
├── models.py                # Data structures (Event, State, ActionEdge, Graph)
├── normalizer.py            # Event normalization
├── noise_reducer.py         # Noise filtering & merging
├── phase_segmenter.py       # Phase segmentation
├── episode_segmenter.py     # Episode segmentation
├── graph_builder.py         # Main orchestrator
├── test_determinism.py      # Determinism tests
├── CONTEXT.md               # Module documentation
└── README.md                # This file
```

## Quick Start

```python
from graph_builder import GraphBuilder

# Initialize
builder = GraphBuilder()

# Build graph from raw operations
operations = [
    {
        "type": "navigate",
        "url": "https://example.com",
        "timestamp": 1000,
        "element": {}
    },
    {
        "type": "click",
        "url": "https://example.com",
        "timestamp": 2000,
        "element": {
            "tagName": "button",
            "textContent": "Submit"
        }
    }
]

graph = builder.build(operations)

# Access results
print(f"States: {len(graph.states)}")
print(f"Edges: {len(graph.edges)}")
print(f"Phases: {len(graph.phases)}")
print(f"Episodes: {len(graph.episodes)}")

# Export
graph_dict = graph.to_dict()
```

## API Integration

The Graph Builder is integrated into the Cloud Backend API:

### POST /api/v1/recordings

Uploads a recording and builds its graph:

```json
{
  "user_id": "user123",
  "user_api_key": "ami_xxx",
  "operations": [...]
}
```

**Returns:**

```json
{
  "recording_id": "rec_123",
  "graph": {
    "states": {...},
    "edges": [...],
    "phases": [...],
    "episodes": [...]
  }
}
```

### GET /api/v1/recordings/{recording_id}

Returns recording with its graph:

```json
{
  "recording_id": "rec_123",
  "operations": [...],
  "graph": {
    "states": {...},
    "edges": [...],
    "phases": [...],
    "episodes": [...]
  }
}
```

## Testing

Run determinism tests:

```bash
cd src/cloud_backend/graph_builder
python test_determinism.py
```

Expected output:
```
======================================================================
Graph Builder Determinism Tests
======================================================================
✓ Simple determinism test passed
✓ Complex determinism test passed (10 identical graphs)
✓ No data loss test passed (2 clicks, 2 navs)
======================================================================
All tests passed ✓
======================================================================
```

## Configuration

Tunable parameters:

```python
builder = GraphBuilder(
    idle_threshold_ms=3000,        # Idle duration for phase boundary
    scroll_merge_window_ms=500,    # Scroll merge window
    input_debounce_ms=500,         # Input debounce window
    hover_merge_window_ms=200      # Hover merge window
)
```

## Design Principles

1. **Determinism First** - Must be 100% reproducible
2. **No AI/LLM** - Only rule-based logic
3. **No Semantics** - No understanding of user intent
4. **Structural Only** - Pure data transformation
5. **Complete** - Cannot lose important events

## Data Models

### Event
Normalized browser event with timestamp, type, URL, target, and data.

### State
Page state identified by (URL, page_root) combination.

### ActionEdge
Action that transitions from one state to another.

### Phase
Macro-level segment (split by URL changes).

### Episode
Medium-level segment (split by click/navigation boundaries).

### StateActionGraph
Complete graph with states, edges, phases, and episodes.

## Next Steps

The State/Action Graph is consumed by the Workflow Generator (Agent) which:
1. Selects stable path from graph
2. Translates to YAML Workflow
3. Adds execution semantics

See: `intent_builder/agents/workflow_builder.py`

## License

Part of Ami platform.
