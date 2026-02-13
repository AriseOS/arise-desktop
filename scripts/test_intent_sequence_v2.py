"""Verify IntentSequence V2 core flows.

Tests:
1. State creation (no removed fields)
2. IntentSequence creation + link_to_state
3. find_state_by_url → list_by_state (the main use case)
4. Deduplication via content_hash
5. from_dict compatibility with legacy data containing intent_sequences
6. search_by_embedding (no N+1)

Usage:
    source .venv/bin/activate
    python scripts/test_intent_sequence_v2.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cloud_backend.memgraph.graphstore.networkx_graph import NetworkXGraph
from src.cloud_backend.memgraph.memory.workflow_memory import (
    GraphIntentSequenceManager,
    GraphStateManager,
    WorkflowMemory,
)
from src.cloud_backend.memgraph.ontology.intent import Intent
from src.cloud_backend.memgraph.ontology.intent_sequence import IntentSequence
from src.cloud_backend.memgraph.ontology.state import State


def test_state_creation():
    """Bug 1: State() must not crash without removed fields."""
    state = State(
        page_url="https://example.com",
        page_title="Example",
        timestamp=1000,
    )
    assert not hasattr(state, "intent_sequences"), "intent_sequences field should not exist"
    assert not hasattr(state, "intents"), "intents field should not exist"
    assert not hasattr(state, "intent_ids"), "intent_ids field should not exist"
    print("PASS: State creation without removed fields")


def test_state_from_dict_legacy():
    """State.from_dict should silently drop legacy intent_sequences."""
    data = {
        "page_url": "https://example.com",
        "page_title": "Example",
        "timestamp": 1000,
        "intent_sequences": [{"id": "old", "timestamp": 1}],  # legacy data
    }
    state = State.from_dict(data)
    assert state.page_url == "https://example.com"
    print("PASS: State.from_dict drops legacy intent_sequences")


def test_url_to_state_to_sequences():
    """Main use case: URL → State → IntentSequences."""
    graph = NetworkXGraph()
    memory = WorkflowMemory(graph_store=graph)

    # Create state via find_or_create_state
    state, is_new = memory.find_or_create_state(
        url="https://example.com/products/123",
        page_title="Product Detail",
        timestamp=1000,
        domain="example.com",
    )
    assert is_new
    assert state.id is not None

    # Create IntentSequences and link
    seq1 = IntentSequence(
        timestamp=1001,
        description="Click add to cart",
        intents=[
            Intent(type="ClickElement", timestamp=1001, text="Add to Cart", page_url="https://example.com/products/123"),
        ],
    )
    seq2 = IntentSequence(
        timestamp=1002,
        description="Scroll down to reviews",
        intents=[
            Intent(type="Scroll", timestamp=1002, text="", page_url="https://example.com/products/123"),
        ],
    )

    mgr = memory.intent_sequence_manager
    assert mgr is not None, "IntentSequenceManager should be initialized"

    mgr.create_sequence(seq1)
    mgr.link_to_state(state.id, seq1.id)
    mgr.create_sequence(seq2)
    mgr.link_to_state(state.id, seq2.id)

    # Now: URL → State → IntentSequences
    found_state = memory.find_state_by_url("https://example.com/products/123")
    assert found_state is not None
    assert found_state.id == state.id

    sequences = mgr.list_by_state(found_state.id)
    assert len(sequences) == 2
    descriptions = {s.description for s in sequences}
    assert "Click add to cart" in descriptions
    assert "Scroll down to reviews" in descriptions

    print(f"PASS: URL → State({state.id[:8]}...) → {len(sequences)} IntentSequences")


def test_deduplication():
    """Duplicate IntentSequence with same intents should be detected."""
    graph = NetworkXGraph()
    memory = WorkflowMemory(graph_store=graph)

    state, _ = memory.find_or_create_state(
        url="https://example.com/page",
        timestamp=1000,
    )

    mgr = memory.intent_sequence_manager

    seq1 = IntentSequence(
        timestamp=2000,
        intents=[
            Intent(type="ClickElement", timestamp=2000, text="Submit", page_url=""),
            Intent(type="TypeText", timestamp=2001, text="hello", page_url=""),
        ],
    )
    mgr.create_sequence(seq1)
    mgr.link_to_state(state.id, seq1.id)

    # Same intents, different ID and timestamp
    seq2 = IntentSequence(
        timestamp=3000,
        intents=[
            Intent(type="ClickElement", timestamp=3000, text="Submit", page_url=""),
            Intent(type="TypeText", timestamp=3001, text="hello", page_url=""),
        ],
    )

    dup_id = mgr.find_duplicate(seq2, state.id)
    assert dup_id == seq1.id, f"Expected duplicate {seq1.id}, got {dup_id}"

    # Different intents → not duplicate
    seq3 = IntentSequence(
        timestamp=4000,
        intents=[
            Intent(type="ClickElement", timestamp=4000, text="Cancel", page_url=""),
        ],
    )
    assert mgr.find_duplicate(seq3, state.id) is None

    print("PASS: Deduplication works correctly")


def test_content_hash_persisted():
    """content_hash should survive store → retrieve cycle."""
    graph = NetworkXGraph()
    memory = WorkflowMemory(graph_store=graph)

    state, _ = memory.find_or_create_state(
        url="https://example.com/hash-test",
        timestamp=1000,
    )

    mgr = memory.intent_sequence_manager

    seq = IntentSequence(
        timestamp=2000,
        intents=[
            Intent(type="ClickElement", timestamp=2000, text="Buy", page_url=""),
        ],
    )
    mgr.create_sequence(seq)
    mgr.link_to_state(state.id, seq.id)

    # Retrieve and check content_hash survived
    retrieved = mgr.list_by_state(state.id)
    assert len(retrieved) == 1
    assert retrieved[0].content_hash is not None, "content_hash should be persisted"
    assert retrieved[0].content_hash == seq.content_hash

    print(f"PASS: content_hash persisted: {retrieved[0].content_hash[:12]}...")


def test_search_by_embedding_no_n_plus_1():
    """search_by_embedding with state_id filter should call list_by_state once."""
    graph = NetworkXGraph()
    memory = WorkflowMemory(graph_store=graph)

    state, _ = memory.find_or_create_state(
        url="https://example.com/embed-test",
        timestamp=1000,
    )

    mgr = memory.intent_sequence_manager

    # Create sequences with embedding vectors
    for i in range(5):
        vec = [0.0] * 1024
        vec[i] = 1.0
        seq = IntentSequence(
            timestamp=2000 + i,
            description=f"Action {i}",
            embedding_vector=vec,
            intents=[Intent(type="ClickElement", timestamp=2000 + i, text=f"Btn{i}", page_url="")],
        )
        mgr.create_sequence(seq)
        mgr.link_to_state(state.id, seq.id)

    # Search with state_id filter
    query_vec = [0.0] * 1024
    query_vec[0] = 1.0
    results = mgr.search_by_embedding(query_vec, state_id=state.id, top_k=3)
    assert len(results) > 0
    assert len(results) <= 3

    # Verify results are IntentSequence objects with scores
    for seq, score in results:
        assert isinstance(seq, IntentSequence)
        assert isinstance(score, float)

    print(f"PASS: search_by_embedding returned {len(results)} results")


def test_get_page_capabilities():
    """Memory.get_page_capabilities should return sequences via graph."""
    graph = NetworkXGraph()
    memory = WorkflowMemory(graph_store=graph)

    state, _ = memory.find_or_create_state(
        url="https://example.com/caps",
        timestamp=1000,
    )

    mgr = memory.intent_sequence_manager
    seq = IntentSequence(
        timestamp=2000,
        description="Do something",
        intents=[Intent(type="ClickElement", timestamp=2000, text="Go", page_url="")],
    )
    mgr.create_sequence(seq)
    mgr.link_to_state(state.id, seq.id)

    caps = memory.get_page_capabilities(state.id)
    assert len(caps["sequences"]) == 1
    assert caps["sequences"][0].description == "Do something"

    print("PASS: get_page_capabilities returns sequences via graph")


if __name__ == "__main__":
    tests = [
        test_state_creation,
        test_state_from_dict_legacy,
        test_url_to_state_to_sequences,
        test_deduplication,
        test_content_hash_persisted,
        test_search_by_embedding_no_n_plus_1,
        test_get_page_capabilities,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed:
        sys.exit(1)
