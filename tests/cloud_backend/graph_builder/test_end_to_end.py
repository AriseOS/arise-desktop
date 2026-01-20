"""End-to-end test with realistic user recording data.

This test simulates a complete user recording session and validates
the entire Graph Builder pipeline with real-world data format.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.cloud_backend.graph_builder.graph_builder import GraphBuilder


def get_realistic_recording_data():
    """Generate realistic recording data matching CDPRecorder format.

    This simulates a user performing:
    1. Navigate to Google
    2. Type search query
    3. Scroll down
    4. Click on a result
    5. Navigate to result page
    6. Copy some text
    """
    return [
        # Step 1: Navigate to Google
        {
            "type": "navigate",
            "timestamp": "2025-01-09 14:30:00",
            "url": "https://www.google.com",
            "page_title": "Google",
            "element": {},
            "data": {
                "frame_id": "frame_001",
                "navigation_type": "main_frame",
                "is_user_initiated": True
            }
        },
        # Step 2: Click on search box
        {
            "type": "click",
            "timestamp": "2025-01-09 14:30:02",
            "url": "https://www.google.com",
            "page_title": "Google",
            "element": {
                "tagName": "input",
                "textContent": "",
                "role": "searchbox",
                "className": "gLFyf",
                "ariaLabel": "Search"
            },
            "data": {
                "clickType": "left",
                "coordinates": {"x": 500, "y": 300}
            }
        },
        # Step 3: Type "best coffee shops" (multiple input events)
        {
            "type": "input",
            "timestamp": "2025-01-09 14:30:03",
            "url": "https://www.google.com",
            "page_title": "Google",
            "element": {
                "tagName": "input",
                "role": "searchbox",
                "className": "gLFyf"
            },
            "data": {
                "value": "b",
                "inputType": "text",
                "fieldType": "search"
            }
        },
        {
            "type": "input",
            "timestamp": "2025-01-09 14:30:03",
            "url": "https://www.google.com",
            "page_title": "Google",
            "element": {
                "tagName": "input",
                "role": "searchbox",
                "className": "gLFyf"
            },
            "data": {
                "value": "be",
                "inputType": "text",
                "fieldType": "search"
            }
        },
        {
            "type": "input",
            "timestamp": "2025-01-09 14:30:04",
            "url": "https://www.google.com",
            "page_title": "Google",
            "element": {
                "tagName": "input",
                "role": "searchbox",
                "className": "gLFyf"
            },
            "data": {
                "value": "best coffee shops",
                "inputType": "text",
                "fieldType": "search"
            }
        },
        # Step 4: Hover over search button (noise - will be filtered)
        {
            "type": "hover",
            "timestamp": "2025-01-09 14:30:05",
            "url": "https://www.google.com",
            "page_title": "Google",
            "element": {
                "tagName": "button",
                "textContent": "Google Search",
                "role": "button"
            },
            "data": {}
        },
        # Step 5: Click search button
        {
            "type": "click",
            "timestamp": "2025-01-09 14:30:06",
            "url": "https://www.google.com",
            "page_title": "Google",
            "element": {
                "tagName": "button",
                "textContent": "Google Search",
                "role": "button",
                "className": "gNO89b"
            },
            "data": {
                "clickType": "left"
            }
        },
        # Step 6: Navigation to search results (automatic)
        {
            "type": "navigate",
            "timestamp": "2025-01-09 14:30:07",
            "url": "https://www.google.com/search?q=best+coffee+shops",
            "page_title": "best coffee shops - Google Search",
            "element": {},
            "data": {
                "frame_id": "frame_001",
                "navigation_type": "main_frame",
                "is_user_initiated": False
            }
        },
        # Step 7: Multiple scrolls (will be merged)
        {
            "type": "scroll",
            "timestamp": "2025-01-09 14:30:08",
            "url": "https://www.google.com/search?q=best+coffee+shops",
            "page_title": "best coffee shops - Google Search",
            "element": {},
            "data": {
                "direction": "down",
                "distance": 300,
                "scrollTop": 300
            }
        },
        {
            "type": "scroll",
            "timestamp": "2025-01-09 14:30:08",
            "url": "https://www.google.com/search?q=best+coffee+shops",
            "page_title": "best coffee shops - Google Search",
            "element": {},
            "data": {
                "direction": "down",
                "distance": 200,
                "scrollTop": 500
            }
        },
        {
            "type": "scroll",
            "timestamp": "2025-01-09 14:30:09",
            "url": "https://www.google.com/search?q=best+coffee+shops",
            "page_title": "best coffee shops - Google Search",
            "element": {},
            "data": {
                "direction": "down",
                "distance": 150,
                "scrollTop": 650
            }
        },
        # Step 8: Dataload event (system event - will be filtered)
        {
            "type": "dataload",
            "timestamp": "2025-01-09 14:30:10",
            "url": "https://www.google.com/search?q=best+coffee+shops",
            "page_title": "best coffee shops - Google Search",
            "element": {},
            "data": {
                "added_elements_count": 15,
                "data_elements_count": 8,
                "height_change": 500
            }
        },
        # Step 9: Click on first result
        {
            "type": "click",
            "timestamp": "2025-01-09 14:30:12",
            "url": "https://www.google.com/search?q=best+coffee+shops",
            "page_title": "best coffee shops - Google Search",
            "element": {
                "tagName": "a",
                "textContent": "Top 10 Coffee Shops in NYC",
                "role": "link",
                "href": "https://example.com/coffee-shops",
                "className": "result-link"
            },
            "data": {
                "clickType": "left"
            }
        },
        # Step 10: Navigate to result page
        {
            "type": "navigate",
            "timestamp": "2025-01-09 14:30:13",
            "url": "https://example.com/coffee-shops",
            "page_title": "Top 10 Coffee Shops in NYC",
            "element": {},
            "data": {
                "frame_id": "frame_001",
                "navigation_type": "main_frame",
                "is_user_initiated": False
            }
        },
        # Step 11: Select text to copy
        {
            "type": "select",
            "timestamp": "2025-01-09 14:30:15",
            "url": "https://example.com/coffee-shops",
            "page_title": "Top 10 Coffee Shops in NYC",
            "element": {
                "tagName": "p",
                "textContent": "Blue Bottle Coffee is located at...",
                "className": "description"
            },
            "data": {
                "selectedText": "Blue Bottle Coffee is located at 123 Main St"
            }
        },
        # Step 12: Copy action
        {
            "type": "copy_action",
            "timestamp": "2025-01-09 14:30:16",
            "url": "https://example.com/coffee-shops",
            "page_title": "Top 10 Coffee Shops in NYC",
            "element": {},
            "data": {
                "copiedText": "Blue Bottle Coffee is located at 123 Main St"
            }
        },
        # Step 13: Idle period (3+ seconds gap to test phase segmentation)
        # ... time gap ...
        # Step 14: Navigate to another page after idle
        {
            "type": "navigate",
            "timestamp": "2025-01-09 14:30:20",  # 4 seconds gap
            "url": "https://example.com/contact",
            "page_title": "Contact Us",
            "element": {},
            "data": {
                "frame_id": "frame_001",
                "navigation_type": "main_frame",
                "is_user_initiated": True
            }
        }
    ]


def test_end_to_end_realistic_data() -> None:
    """End-to-end test with realistic user recording data."""
    print("\n" + "="*70)
    print("END-TO-END TEST: Realistic User Recording")
    print("="*70)

    # Get realistic recording data
    operations = get_realistic_recording_data()
    print(f"\n📊 Input: {len(operations)} operations")
    print(f"   - Types: {set(op['type'] for op in operations)}")

    # Build graph
    builder = GraphBuilder()
    graph = builder.build(operations)

    print(f"\n📈 Graph Statistics:")
    print(f"   States: {len(graph.states)}")
    print(f"   Edges: {len(graph.edges)}")
    print(f"   Phases: {len(graph.phases)}")
    print(f"   Episodes: {len(graph.episodes)}")

    # Detailed analysis
    print(f"\n🔍 States Detail:")
    for state_id, state in graph.states.items():
        print(f"   {state_id}: {state.url}")

    print(f"\n🔗 Edges Detail:")
    for edge in graph.edges:
        print(f"   {edge.edge_id}: {edge.from_state} -> {edge.to_state} ({edge.action_type})")

    print(f"\n📦 Phases Detail:")
    for phase in graph.phases:
        print(f"   {phase.phase_id}: {len(phase.events)} events")
        print(f"      URL: {phase.start_url}")
        if phase.start_url != phase.end_url:
            print(f"      → {phase.end_url}")

    print(f"\n🎬 Episodes Detail:")
    for episode in graph.episodes:
        print(f"   {episode.episode_id}: {episode.event_types}")

    # Validation assertions
    print(f"\n✅ Validations:")

    # Should have at least 3 states (google, search results, example.com)
    assert len(graph.states) >= 3, f"Expected >= 3 states, got {len(graph.states)}"
    print(f"   ✓ States count: {len(graph.states)} >= 3")

    # Should have multiple edges
    assert len(graph.edges) > 5, f"Expected > 5 edges, got {len(graph.edges)}"
    print(f"   ✓ Edges count: {len(graph.edges)} > 5")

    # Should have multiple phases (URL changes)
    assert len(graph.phases) >= 2, f"Expected >= 2 phases, got {len(graph.phases)}"
    print(f"   ✓ Phases count: {len(graph.phases)} >= 2")

    # Should have multiple episodes
    assert len(graph.episodes) >= 5, f"Expected >= 5 episodes, got {len(graph.episodes)}"
    print(f"   ✓ Episodes count: {len(graph.episodes)} >= 5")

    # Check that clicks are preserved
    click_edges = [e for e in graph.edges if e.action_type == "click"]
    assert len(click_edges) >= 3, f"Expected >= 3 click edges, got {len(click_edges)}"
    print(f"   ✓ Click edges preserved: {len(click_edges)}")

    # Check that navigations are preserved
    nav_edges = [e for e in graph.edges if e.action_type == "navigation"]
    assert len(nav_edges) >= 3, f"Expected >= 3 nav edges, got {len(nav_edges)}"
    print(f"   ✓ Navigation edges preserved: {len(nav_edges)}")

    # Check that inputs are merged (should be 1 input edge, not 3)
    input_edges = [e for e in graph.edges if e.action_type == "input"]
    assert len(input_edges) <= 2, f"Expected inputs to be merged, got {len(input_edges)}"
    print(f"   ✓ Inputs merged: {len(input_edges)} edges")

    # Check that scrolls are merged
    scroll_edges = [e for e in graph.edges if e.action_type == "scroll"]
    assert len(scroll_edges) <= 2, f"Expected scrolls to be merged, got {len(scroll_edges)}"
    print(f"   ✓ Scrolls merged: {len(scroll_edges)} edges")

    # Check that hover is filtered out (no hover edges)
    hover_edges = [e for e in graph.edges if e.action_type == "hover"]
    assert len(hover_edges) == 0, f"Expected hovers to be filtered, got {len(hover_edges)}"
    print(f"   ✓ Hovers filtered out: {len(hover_edges)} edges")

    # Check that dataload is filtered out
    dataload_edges = [e for e in graph.edges if e.action_type == "dataload"]
    assert len(dataload_edges) == 0, f"Expected dataload to be filtered, got {len(dataload_edges)}"
    print(f"   ✓ Dataload filtered out: {len(dataload_edges)} edges")

    print(f"\n{'='*70}")
    print("✅ END-TO-END TEST PASSED")
    print("="*70)


def test_determinism_with_realistic_data() -> None:
    """Test determinism with realistic data."""
    print("\n" + "="*70)
    print("DETERMINISM TEST: Realistic Data")
    print("="*70)

    operations = get_realistic_recording_data()
    builder = GraphBuilder()

    # Build graph 5 times
    graphs = [builder.build(operations) for _ in range(5)]
    dicts = [g.to_dict() for g in graphs]

    # Verify all identical
    for i in range(1, len(dicts)):
        assert dicts[0] == dicts[i], f"Graph {i} differs from graph 0"

    print(f"\n✅ Built graph 5 times - all identical")
    print(f"   States: {len(graphs[0].states)}")
    print(f"   Edges: {len(graphs[0].edges)}")
    print(f"   Phases: {len(graphs[0].phases)}")
    print(f"   Episodes: {len(graphs[0].episodes)}")
    print(f"\n{'='*70}")
    print("✅ DETERMINISM TEST PASSED")
    print("="*70)


def run_all_tests() -> None:
    """Run all end-to-end tests."""
    try:
        test_end_to_end_realistic_data()
        test_determinism_with_realistic_data()

        print("\n" + "="*70)
        print("🎉 ALL END-TO-END TESTS PASSED")
        print("="*70)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    run_all_tests()
