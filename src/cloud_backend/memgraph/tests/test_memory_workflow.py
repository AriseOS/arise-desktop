"""Test script for Memory system with new URL-based workflow processing.

This script tests the complete flow based on memory-graph-ontology-design.md:
1. URL-based event segmentation
2. State deduplication via URL index (real-time merge)
3. PageInstance creation for concrete URL visits
4. IntentSequence creation from operations
5. Action creation between States
6. Semantic search on IntentSequences
7. Path finding between States

Usage:
    python -m src.cloud_backend.memgraph.tests.test_memory_workflow
    python -m src.cloud_backend.memgraph.tests.test_memory_workflow --quick
    python -m src.cloud_backend.memgraph.tests.test_memory_workflow --recording
"""

import json
import os
import sys
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))
sys.path.insert(0, project_root)

from src.cloud_backend.memgraph.graphstore.networkx_graph import NetworkXGraph
from src.cloud_backend.memgraph.memory.workflow_memory import WorkflowMemory
from src.cloud_backend.memgraph.memory.url_index import URLIndex
from src.cloud_backend.memgraph.ontology.intent_sequence import IntentSequence
from src.cloud_backend.memgraph.ontology.page_instance import PageInstance
from src.cloud_backend.memgraph.ontology.state import State
from src.cloud_backend.memgraph.ontology.intent import Intent
from src.cloud_backend.memgraph.services import EmbeddingService
from src.common.llm import AnthropicProvider
from src.cloud_backend.memgraph.thinker.workflow_processor import (
    WorkflowProcessor,
    URLSegment,
)

# Path to sample recording file
SAMPLE_RECORDING_PATH = Path(__file__).parent / "sample_recording.json"


def load_recording(path: Path = SAMPLE_RECORDING_PATH) -> Dict[str, Any]:
    """Load recording file.

    Args:
        path: Path to recording JSON file.

    Returns:
        Recording data dictionary.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Sample workflow with navigate events creating URL segments
# This simulates: Home -> Search -> Product Detail
SAMPLE_WORKFLOW = [
    # Segment 1: Home page
    {
        "type": "navigate",
        "url": "https://www.taobao.com",
        "title": "Taobao Home",
        "timestamp": 1705000000000,
    },
    {
        "type": "click",
        "element_tag": "input",
        "element_id": "q",
        "element_class": "search-input",
        "text": "",
        "url": "https://www.taobao.com",
        "title": "Taobao Home",
        "timestamp": 1705000001000,
    },
    {
        "type": "input",
        "element_tag": "input",
        "element_id": "q",
        "value": "coffee machine",
        "url": "https://www.taobao.com",
        "title": "Taobao Home",
        "timestamp": 1705000002000,
    },
    {
        "type": "click",
        "element_tag": "button",
        "element_class": "search-btn",
        "text": "Search",
        "url": "https://www.taobao.com",
        "title": "Taobao Home",
        "timestamp": 1705000003000,
    },
    # Segment 2: Search results
    {
        "type": "navigate",
        "url": "https://s.taobao.com/search?q=coffee+machine",
        "title": "Search Results",
        "timestamp": 1705000004000,
    },
    {
        "type": "click",
        "element_tag": "a",
        "element_class": "product-item",
        "text": "Delonghi Coffee Machine",
        "url": "https://s.taobao.com/search?q=coffee+machine",
        "title": "Search Results",
        "timestamp": 1705000010000,
    },
    # Segment 3: Product detail
    {
        "type": "navigate",
        "url": "https://detail.taobao.com/item.htm?id=123456",
        "title": "Product Detail",
        "timestamp": 1705000011000,
    },
    {
        "type": "click",
        "element_tag": "span",
        "element_class": "price",
        "text": "$299",
        "url": "https://detail.taobao.com/item.htm?id=123456",
        "title": "Product Detail",
        "timestamp": 1705000015000,
    },
    {
        "type": "copy",
        "value": "$299",
        "url": "https://detail.taobao.com/item.htm?id=123456",
        "title": "Product Detail",
        "timestamp": 1705000016000,
    },
]

# Second workflow that revisits the same URLs (for testing State reuse)
SECOND_WORKFLOW = [
    {
        "type": "navigate",
        "url": "https://www.taobao.com",
        "title": "Taobao Home",
        "timestamp": 1705001000000,
    },
    {
        "type": "click",
        "element_tag": "input",
        "element_id": "q",
        "value": "tea",
        "url": "https://www.taobao.com",
        "title": "Taobao Home",
        "timestamp": 1705001001000,
    },
    {
        "type": "navigate",
        "url": "https://s.taobao.com/search?q=tea",
        "title": "Tea Search Results",
        "timestamp": 1705001002000,
    },
]


def setup_embedding_service():
    """Configure the embedding service from environment or defaults."""
    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        print("Warning: SILICONFLOW_API_KEY not set, embedding will be disabled")
        return None

    EmbeddingService.configure(
        provider="openai",
        model="BAAI/bge-m3",
        dimension=1024,
        api_url="https://api.siliconflow.cn/v1",
        api_key=api_key,
    )

    if EmbeddingService.is_available():
        print("  Embedding service configured successfully")
        return EmbeddingService.get_model()
    else:
        print("Warning: Embedding service not available")
        return None


def setup_llm_provider() -> Optional[AnthropicProvider]:
    """Configure the LLM provider for description generation."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Warning: ANTHROPIC_API_KEY not set, LLM descriptions will be skipped")
        return None

    return AnthropicProvider(
        api_key=api_key,
        model_name="claude-sonnet-4-5-20250929",
    )


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_url_index():
    """Test URLIndex functionality."""
    print_section("Testing URLIndex")

    # Create URL index
    url_index = URLIndex()

    # Add URLs
    url_index.add_url("https://example.com/page1", "state-1")
    url_index.add_url("https://example.com/page2", "state-2")
    url_index.add_url("https://example.com/page3", "state-1")  # Same state

    # Test lookup
    print("URL Index Tests:")
    print(f"  find_state_by_url('https://example.com/page1'): {url_index.find_state_by_url('https://example.com/page1')}")
    print(f"  find_state_by_url('https://example.com/page2'): {url_index.find_state_by_url('https://example.com/page2')}")
    print(f"  find_state_by_url('https://example.com/unknown'): {url_index.find_state_by_url('https://example.com/unknown')}")
    print(f"  has_url('https://example.com/page1'): {url_index.has_url('https://example.com/page1')}")
    print(f"  get_all_urls_for_state('state-1'): {url_index.get_all_urls_for_state('state-1')}")
    print(f"  Stats: {url_index.get_stats()}")

    print("\n  URLIndex tests passed!")


def test_page_instance():
    """Test PageInstance creation."""
    print_section("Testing PageInstance")

    instance = PageInstance(
        url="https://example.com/product/123",
        page_title="Product 123",
        timestamp=1705000000000,
        session_id="session-001",
        user_id="user-001",
    )

    print("PageInstance Tests:")
    print(f"  ID: {instance.id}")
    print(f"  URL: {instance.url}")
    print(f"  Title: {instance.page_title}")
    print(f"  Timestamp: {instance.timestamp}")

    # Test serialization
    data = instance.to_dict()
    restored = PageInstance.from_dict(data)
    print(f"  Serialization round-trip: {'passed' if restored.url == instance.url else 'FAILED'}")

    print("\n  PageInstance tests passed!")


def test_intent_sequence():
    """Test IntentSequence creation."""
    print_section("Testing IntentSequence")

    # Create intents
    intents = [
        Intent(
            type="ClickElement",
            timestamp=1705000001000,
            page_url="https://example.com/search",
            text="Search",
        ),
        Intent(
            type="TypeText",
            timestamp=1705000002000,
            page_url="https://example.com/search",
            value="coffee machine",
        ),
    ]

    sequence = IntentSequence(
        timestamp=1705000001000,
        intents=intents,
        description="Search for coffee machine",
        session_id="session-001",
        user_id="user-001",
    )

    print("IntentSequence Tests:")
    print(f"  ID: {sequence.id}")
    print(f"  Description: {sequence.description}")
    print(f"  Intent count: {len(sequence.intents)}")

    # Test serialization
    data = sequence.to_dict()
    restored = IntentSequence.from_dict(data)
    print(f"  Serialization round-trip: {'passed' if len(restored.intents) == 2 else 'FAILED'}")

    print("\n  IntentSequence tests passed!")


def test_state_with_new_fields():
    """Test State with instances and intent_sequences."""
    print_section("Testing State with new fields")

    # Create PageInstance
    instance = PageInstance(
        url="https://example.com/search?q=coffee",
        page_title="Search Results",
        timestamp=1705000000000,
    )

    # Create IntentSequence
    sequence = IntentSequence(
        timestamp=1705000001000,
        intents=[
            Intent(type="ClickElement", timestamp=1705000001000, page_url="https://example.com/search", text="Filter"),
        ],
        description="Filter search results",
    )

    # Create State with new fields
    state = State(
        page_url="https://example.com/search?q=coffee",
        page_title="Search Results",
        timestamp=1705000000000,
        domain="example.com",
        instances=[instance],
        intent_sequences=[sequence],
    )

    print("State Tests:")
    print(f"  ID: {state.id}")
    print(f"  Domain: {state.domain}")
    print(f"  Instances count: {len(state.instances)}")
    print(f"  IntentSequences count: {len(state.intent_sequences)}")
    print(f"  get_all_urls(): {state.get_all_urls()}")
    print(f"  has_url('https://example.com/search?q=coffee'): {state.has_url('https://example.com/search?q=coffee')}")

    # Test add methods
    new_instance = PageInstance(
        url="https://example.com/search?q=tea",
        page_title="Tea Search",
        timestamp=1705000100000,
    )
    state.add_instance(new_instance)
    print(f"  After add_instance: {len(state.instances)} instances")

    # Test deduplication
    duplicate_sequence = IntentSequence(
        timestamp=1705000200000,
        intents=[],
        description="Filter search results",  # Same description
    )
    added = state.add_intent_sequence(duplicate_sequence)
    print(f"  Duplicate IntentSequence rejected: {'passed' if not added else 'FAILED'}")

    # Test serialization
    data = state.to_dict()
    restored = State.from_dict(data)
    print(f"  Serialization round-trip: {'passed' if len(restored.instances) == 2 else 'FAILED'}")

    print("\n  State tests passed!")


def test_workflow_memory_methods():
    """Test new WorkflowMemory methods."""
    print_section("Testing WorkflowMemory methods")

    # Setup
    graph_store = NetworkXGraph()
    memory = WorkflowMemory(graph_store)

    # Test find_or_create_state
    print("find_or_create_state Tests:")

    state1, is_new1 = memory.find_or_create_state(
        url="https://example.com/home",
        page_title="Home Page",
        timestamp=1705000000000,
        domain="example.com",
        user_id="user-001",
    )
    print(f"  First call: is_new={is_new1} (expected: True)")

    state2, is_new2 = memory.find_or_create_state(
        url="https://example.com/home",
        page_title="Home Page Updated",
        timestamp=1705000100000,
    )
    print(f"  Second call (same URL): is_new={is_new2} (expected: False)")
    print(f"  Same State ID: {state1.id == state2.id}")

    # Test add_page_instance
    print("\nadd_page_instance Tests:")
    instance = PageInstance(
        url="https://example.com/home?ref=email",
        page_title="Home from Email",
        timestamp=1705000200000,
    )
    success = memory.add_page_instance(state1.id, instance)
    print(f"  add_page_instance: {success}")

    # Verify
    retrieved = memory.get_state(state1.id)
    print(f"  State has {len(retrieved.instances)} instances")

    # Test add_intent_sequence
    print("\nadd_intent_sequence Tests:")
    sequence = IntentSequence(
        timestamp=1705000300000,
        intents=[Intent(type="ClickElement", timestamp=1705000300000, page_url="https://example.com/home", text="Login")],
        description="User login",
    )
    success = memory.add_intent_sequence(state1.id, sequence)
    print(f"  add_intent_sequence: {success}")

    # Test deduplication
    duplicate = IntentSequence(
        timestamp=1705000400000,
        intents=[],
        description="User login",  # Same description
    )
    success2 = memory.add_intent_sequence(state1.id, duplicate)
    retrieved = memory.get_state(state1.id)
    print(f"  Duplicate rejected: {len(retrieved.intent_sequences) == 1}")

    # Test find_path
    print("\nfind_path Tests:")

    # Create another state and action
    state3, _ = memory.find_or_create_state(
        url="https://example.com/products",
        page_title="Products",
        timestamp=1705000500000,
    )

    from src.cloud_backend.memgraph.ontology.action import Action
    action = Action(
        source=state1.id,
        target=state3.id,
        type="navigate",
        timestamp=1705000500000,
    )
    memory.create_action(action)

    path = memory.find_path(state1.id, state3.id)
    print(f"  Path found: {path is not None}")
    if path:
        print(f"  Path length: {len(path)} steps")

    # Test rebuild_url_index
    print("\nrebuild_url_index Tests:")
    url_count = memory.rebuild_url_index()
    print(f"  URLs indexed: {url_count}")

    print("\n  WorkflowMemory tests passed!")


def test_url_segment():
    """Test URLSegment functionality."""
    print_section("Testing URLSegment")

    segment = URLSegment(
        url="https://example.com/page",
        page_title="Test Page",
        timestamp=1705000000000,
    )

    # Add events
    segment.add_event({"type": "click", "text": "Button", "timestamp": 1705000001000})
    segment.add_event({"type": "input", "value": "text", "timestamp": 1705000002000})

    print("URLSegment Tests:")
    print(f"  URL: {segment.url}")
    print(f"  Event count: {len(segment.events)}")
    print(f"  Duration: {segment.get_duration()}ms")
    print(f"  End timestamp: {segment.end_timestamp}")

    print("\n  URLSegment tests passed!")


async def test_workflow_processing():
    """Test the complete workflow processing pipeline."""
    print_section("Full Workflow Processing Test")

    # Setup
    print("Setting up services...")
    embedding_model = setup_embedding_service()
    llm_provider = setup_llm_provider()
    print(f"  LLM provider: {type(llm_provider).__name__ if llm_provider else 'None'}")

    graph_store = NetworkXGraph()
    memory = WorkflowMemory(graph_store)
    print("  Memory system initialized")

    processor = WorkflowProcessor(
        llm_provider=llm_provider,
        memory=memory,
        embedding_model=embedding_model,
    )
    print("  WorkflowProcessor created")

    # Process first workflow
    print("\n--- Processing First Workflow ---")
    result1 = await processor.process_workflow(
        workflow_data=SAMPLE_WORKFLOW,
        user_id="test_user",
        session_id="session_001",
        store_to_memory=True,
    )

    print(f"\nFirst workflow results:")
    print(f"  New States: {result1.metadata.get('new_states', 0)}")
    print(f"  Reused States: {result1.metadata.get('reused_states', 0)}")
    print(f"  PageInstances: {len(result1.page_instances)}")
    print(f"  IntentSequences: {len(result1.intent_sequences)}")
    print(f"  Actions: {len(result1.actions)}")

    # Process second workflow (should reuse some States)
    print("\n--- Processing Second Workflow (State Reuse Test) ---")
    result2 = await processor.process_workflow(
        workflow_data=SECOND_WORKFLOW,
        user_id="test_user",
        session_id="session_002",
        store_to_memory=True,
    )

    print(f"\nSecond workflow results:")
    print(f"  New States: {result2.metadata.get('new_states', 0)}")
    print(f"  Reused States: {result2.metadata.get('reused_states', 0)}")

    # Verify State reuse
    home_url = "https://www.taobao.com"
    home_state = memory.find_state_by_url(home_url)
    if home_state:
        print(f"\nState Reuse Verification:")
        print(f"  Home page State ID: {home_state.id[:8]}...")
        print(f"  PageInstances in home State: {len(home_state.instances)}")
        print(f"  IntentSequences in home State: {len(home_state.intent_sequences)}")

    # Test semantic search on IntentSequences
    if embedding_model:
        print("\n--- Testing IntentSequence Semantic Search ---")
        query = "search product"
        query_embedding = EmbeddingService.embed(query)

        if query_embedding:
            results = memory.search_intent_sequences_by_embedding(
                query_vector=query_embedding,
                top_k=3,
            )
            print(f"Query: '{query}'")
            print(f"Results ({len(results)} found):")
            for seq, state, score in results:
                print(f"  - [{score:.3f}] {seq.description} (in {state.page_title})")

    # Test path finding
    print("\n--- Testing Path Finding ---")
    states = memory.state_manager.list_states()
    if len(states) >= 2:
        from_state = states[0]
        to_state = states[-1]
        path = memory.find_path(from_state.id, to_state.id)
        if path:
            print(f"Path from '{from_state.page_title}' to '{to_state.page_title}':")
            for state, action in path:
                action_str = f" --[{action.type}]--> " if action else ""
                print(f"  {state.page_title}{action_str}")
        else:
            print("No path found")

    # Summary
    print_section("Summary")
    print(f"Total States in memory: {len(memory.state_manager.list_states())}")
    print(f"URL Index stats: {memory.url_index.get_stats()}")

    all_states = memory.state_manager.list_states()
    total_instances = sum(len(s.instances) for s in all_states)
    total_sequences = sum(len(s.intent_sequences) for s in all_states)
    print(f"Total PageInstances: {total_instances}")
    print(f"Total IntentSequences: {total_sequences}")

    print("\n  Full workflow test completed!")
    return result1


def test_quick():
    """Quick test without LLM/embedding."""
    print_section("Quick Tests (No LLM/Embedding)")

    test_url_index()
    test_page_instance()
    test_intent_sequence()
    test_state_with_new_fields()
    test_workflow_memory_methods()
    test_url_segment()

    print_section("All Quick Tests Passed!")


async def test_recording_workflow():
    """Test workflow processing with real recording data."""
    print_section("Recording Workflow Test")

    # Load recording file
    if not SAMPLE_RECORDING_PATH.exists():
        print(f"ERROR: Recording file not found: {SAMPLE_RECORDING_PATH}")
        print("Please copy a recording file to the test directory first.")
        return None

    print(f"Loading recording from: {SAMPLE_RECORDING_PATH}")
    recording_data = load_recording()

    # Show recording info
    operations = recording_data.get("operations", [])
    session_id = recording_data.get("session_id", "unknown")
    print(f"  Session ID: {session_id}")
    print(f"  Total operations: {len(operations)}")

    # Show unique URLs
    urls = set()
    for op in operations:
        url = op.get("url") or op.get("page_url")
        if url:
            urls.add(url)
    print(f"  Unique URLs: {len(urls)}")
    for url in sorted(urls):
        print(f"    - {url[:80]}...")

    # Setup services
    print("\nSetting up services...")
    embedding_model = setup_embedding_service()
    llm_provider = setup_llm_provider()
    print(f"  LLM provider: {type(llm_provider).__name__ if llm_provider else 'None'}")

    graph_store = NetworkXGraph()
    memory = WorkflowMemory(graph_store)
    print("  Memory system initialized")

    processor = WorkflowProcessor(
        llm_provider=llm_provider,
        memory=memory,
        embedding_model=embedding_model,
    )
    print("  WorkflowProcessor created")

    # Process recording
    print("\n--- Processing Recording ---")
    result = await processor.process_workflow(
        workflow_data=recording_data,
        user_id="test_user",
        session_id=session_id,
        store_to_memory=True,
    )

    print(f"\nRecording workflow results:")
    print(f"  New States: {result.metadata.get('new_states', 0)}")
    print(f"  Reused States: {result.metadata.get('reused_states', 0)}")
    print(f"  PageInstances: {len(result.page_instances)}")
    print(f"  IntentSequences: {len(result.intent_sequences)}")
    print(f"  Actions: {len(result.actions)}")

    # Show States detail
    print("\n--- States Created ---")
    all_states = memory.state_manager.list_states()
    for state in all_states:
        print(f"\nState: {state.page_title or 'Untitled'}")
        print(f"  ID: {state.id[:8]}...")
        print(f"  URL: {state.page_url[:60]}...")
        print(f"  Domain: {state.domain}")
        print(f"  PageInstances: {len(state.instances)}")
        print(f"  IntentSequences: {len(state.intent_sequences)}")
        if state.description:
            print(f"  Description: {state.description[:100]}...")

    # Show IntentSequences
    print("\n--- IntentSequences ---")
    for seq in result.intent_sequences:
        desc = seq.description or "(no description)"
        print(f"  - {desc[:80]}...")
        if seq.intents:
            print(f"    Intents: {len(seq.intents)}")
            for intent in seq.intents[:3]:
                intent_type = intent.type if hasattr(intent, "type") else intent.get("type", "?")
                intent_text = intent.text if hasattr(intent, "text") else intent.get("text", "")
                print(f"      [{intent_type}] {intent_text[:40] if intent_text else ''}")
            if len(seq.intents) > 3:
                print(f"      ... and {len(seq.intents) - 3} more")

    # Summary
    print_section("Summary")
    print(f"Total States in memory: {len(all_states)}")
    print(f"URL Index stats: {memory.url_index.get_stats()}")

    total_instances = sum(len(s.instances) for s in all_states)
    total_sequences = sum(len(s.intent_sequences) for s in all_states)
    print(f"Total PageInstances: {total_instances}")
    print(f"Total IntentSequences: {total_sequences}")

    print("\n  Recording workflow test completed!")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Memory Workflow Processing")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick tests only (no LLM/embedding)"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full workflow test with LLM/embedding"
    )
    parser.add_argument(
        "--recording",
        action="store_true",
        help="Test with real recording file (sample_recording.json)"
    )
    args = parser.parse_args()

    if args.quick:
        test_quick()
    elif args.full:
        asyncio.run(test_workflow_processing())
    elif args.recording:
        asyncio.run(test_recording_workflow())
    else:
        # Default: run quick tests
        test_quick()
