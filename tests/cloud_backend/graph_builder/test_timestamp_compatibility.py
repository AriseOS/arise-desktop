"""Test timestamp format compatibility with user recordings.

This test verifies that Graph Builder can handle timestamp formats
from actual user recordings (string format from CDPRecorder).
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.cloud_backend.graph_builder.graph_builder import GraphBuilder


def test_string_timestamp_format() -> None:
    """Test that string timestamps from CDPRecorder are handled correctly."""
    # This is the actual format from user recordings
    operations = [
        {
            "type": "navigate",
            "timestamp": "2025-01-09 12:00:00",  # String format!
            "url": "https://example.com",
            "page_title": "Example Page",
            "element": {},
            "data": {}
        },
        {
            "type": "click",
            "timestamp": "2025-01-09 12:00:05",  # String format!
            "url": "https://example.com",
            "page_title": "Example Page",
            "element": {
                "tagName": "button",
                "textContent": "Submit",
                "role": "button"
            },
            "data": {}
        }
    ]

    builder = GraphBuilder()

    try:
        graph = builder.build(operations)
        assert len(graph.states) > 0, "Graph should have states"
        assert len(graph.edges) > 0, "Graph should have edges"
        print("✓ String timestamp format test passed")
    except Exception as e:
        print(f"✗ String timestamp format test failed: {e}")
        raise


def test_int_timestamp_format() -> None:
    """Test that int timestamps still work (backward compatibility)."""
    operations = [
        {
            "type": "navigate",
            "timestamp": 1704798000000,  # Int format (milliseconds)
            "url": "https://example.com",
            "element": {}
        },
        {
            "type": "click",
            "timestamp": 1704798005000,  # Int format
            "url": "https://example.com",
            "element": {
                "tagName": "button",
                "textContent": "Submit"
            }
        }
    ]

    builder = GraphBuilder()
    graph = builder.build(operations)

    assert len(graph.states) > 0
    assert len(graph.edges) > 0
    print("✓ Int timestamp format test passed")


def test_mixed_timestamp_formats() -> None:
    """Test mixing string and int timestamps."""
    operations = [
        {
            "type": "navigate",
            "timestamp": "2025-01-09 12:00:00",  # String
            "url": "https://example.com",
            "element": {}
        },
        {
            "type": "click",
            "timestamp": 1704798005000,  # Int
            "url": "https://example.com",
            "element": {"tagName": "button"}
        },
        {
            "type": "input",
            "timestamp": "2025-01-09 12:00:10",  # String
            "url": "https://example.com",
            "element": {"tagName": "input"},
            "data": {"value": "test"}
        }
    ]

    builder = GraphBuilder()
    graph = builder.build(operations)

    assert len(graph.states) > 0
    assert len(graph.edges) > 0
    print("✓ Mixed timestamp format test passed")


def test_iso_timestamp_format() -> None:
    """Test ISO 8601 timestamp format."""
    operations = [
        {
            "type": "navigate",
            "timestamp": "2025-01-09T12:00:00Z",  # ISO format
            "url": "https://example.com",
            "element": {}
        },
        {
            "type": "click",
            "timestamp": "2025-01-09T12:00:05+00:00",  # ISO with timezone
            "url": "https://example.com",
            "element": {"tagName": "button"}
        }
    ]

    builder = GraphBuilder()
    graph = builder.build(operations)

    assert len(graph.states) > 0
    assert len(graph.edges) > 0
    print("✓ ISO timestamp format test passed")


def run_all_tests() -> None:
    """Run all timestamp compatibility tests."""
    print("="*70)
    print("Timestamp Format Compatibility Tests")
    print("="*70)

    try:
        test_string_timestamp_format()
        test_int_timestamp_format()
        test_mixed_timestamp_formats()
        test_iso_timestamp_format()

        print("="*70)
        print("All timestamp tests passed ✓")
        print("="*70)
    except AssertionError as e:
        print(f"✗ Test failed: {e}")
        raise
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()
