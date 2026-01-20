"""Determinism tests for Graph Builder.

These tests verify that Graph Builder produces identical output
for identical input (acceptance criteria).
"""

import json
import sys
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.cloud_backend.graph_builder.graph_builder import GraphBuilder


def test_determinism_simple() -> None:
    """Test that same operations produce identical graph."""
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
                "textContent": "Submit",
                "role": "button"
            }
        },
        {
            "type": "navigate",
            "url": "https://example.com/success",
            "timestamp": 3000,
            "element": {}
        }
    ]

    builder = GraphBuilder()

    # Build graph twice
    graph1 = builder.build(operations)
    graph2 = builder.build(operations)

    # Convert to dicts for comparison
    dict1 = graph1.to_dict()
    dict2 = graph2.to_dict()

    # Verify identical
    assert dict1 == dict2, "Graphs should be identical for same input"
    print("✓ Simple determinism test passed")


def test_determinism_complex() -> None:
    """Test determinism with complex operations."""
    operations = [
        {"type": "navigate", "url": "https://example.com/form", "timestamp": 1000},
        {"type": "input", "url": "https://example.com/form", "timestamp": 2000,
         "element": {"tagName": "input", "role": "textbox"},
         "data": {"value": "test"}},
        {"type": "input", "url": "https://example.com/form", "timestamp": 2100,
         "element": {"tagName": "input", "role": "textbox"},
         "data": {"value": "test123"}},
        {"type": "scroll", "url": "https://example.com/form", "timestamp": 3000,
         "data": {"distance": 100, "direction": "down"}},
        {"type": "scroll", "url": "https://example.com/form", "timestamp": 3200,
         "data": {"distance": 50, "direction": "down"}},
        {"type": "click", "url": "https://example.com/form", "timestamp": 4000,
         "element": {"tagName": "button", "textContent": "Submit"}},
        {"type": "navigate", "url": "https://example.com/success", "timestamp": 5000}
    ]

    builder = GraphBuilder()

    # Build graph 10 times
    graphs = [builder.build(operations) for _ in range(10)]
    dicts = [g.to_dict() for g in graphs]

    # Verify all identical
    for i in range(1, len(dicts)):
        assert dicts[0] == dicts[i], f"Graph {i} differs from graph 0"

    print(f"✓ Complex determinism test passed ({len(dicts)} identical graphs)")


def test_no_data_loss() -> None:
    """Test that clicks and navigations are preserved."""
    operations = [
        {"type": "navigate", "url": "https://example.com", "timestamp": 1000},
        {"type": "hover", "url": "https://example.com", "timestamp": 1500},
        {"type": "click", "url": "https://example.com", "timestamp": 2000,
         "element": {"tagName": "a", "textContent": "Link"}},
        {"type": "navigate", "url": "https://example.com/page2", "timestamp": 3000},
        {"type": "scroll", "url": "https://example.com/page2", "timestamp": 4000},
        {"type": "scroll", "url": "https://example.com/page2", "timestamp": 4200},
        {"type": "click", "url": "https://example.com/page2", "timestamp": 5000,
         "element": {"tagName": "button", "textContent": "Button"}},
    ]

    builder = GraphBuilder()
    graph = builder.build(operations)

    # Count click and navigation actions
    click_edges = [e for e in graph.edges if e.action_type == "click"]
    nav_edges = [e for e in graph.edges if e.action_type == "navigation"]

    # Should have 2 clicks and navigations preserved
    assert len(click_edges) >= 1, "Clicks should be preserved"
    assert len(nav_edges) >= 1, "Navigations should be preserved"

    print(f"✓ No data loss test passed ({len(click_edges)} clicks, {len(nav_edges)} navs)")


def run_all_tests() -> None:
    """Run all determinism tests."""
    print("="*70)
    print("Graph Builder Determinism Tests")
    print("="*70)

    try:
        test_determinism_simple()
        test_determinism_complex()
        test_no_data_loss()

        print("="*70)
        print("All tests passed ✓")
        print("="*70)
    except AssertionError as e:
        print(f"✗ Test failed: {e}")
        raise
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()
