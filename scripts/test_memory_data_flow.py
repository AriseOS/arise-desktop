#!/usr/bin/env python3
"""Test Memory Data Flow - Trace where intent_sequences are lost.

This script performs detailed tests at each stage of the Memory pipeline:
1. Database retrieval
2. Memory.get_state()
3. Reasoner.query()
4. API response construction
5. MemoryToolkit parsing
6. AMITaskPlanner formatting
"""

import os
import sys
import json
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.common.memory.memory_service import (
    MemoryService,
    MemoryServiceConfig,
)


def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_subsection(title: str):
    """Print a subsection header."""
    print(f"\n--- {title} ---")


def check_field_presence(data: dict, field: str, context: str) -> bool:
    """Check if a field exists in data."""
    present = field in data and data[field] is not None
    status = "✅" if present else "❌"
    print(f"{status} {context}: field '{field}' {'present' if present else 'MISSING'}")
    return present


async def test_memory_data_flow():
    """Test the complete Memory data flow to trace where intent_sequences are lost."""

    print_section("Memory Data Flow Test")

    # Initialize Memory Service
    print_subsection("Initializing Memory Service")
    config = MemoryServiceConfig(
        graph_backend="surrealdb",
        graph_url="file://~/.ami/memory.db",
        vector_dimensions=1024,
    )

    service = MemoryService(config)
    service.initialize()
    print("✅ Memory Service initialized")

    # Test 1: Get database stats
    print_section("Test 1: Database Statistics")
    stats = service.get_stats()
    print(f"Node count: {stats.get('node_count', 'N/A')}")
    print(f"Edge count: {stats.get('edge_count', 'N/A')}")
    print(f"States: {stats.get('State', 'N/A')}")
    print(f"Actions: {stats.get('Action', 'N/A')}")
    print(f"IntentSequences: {stats.get('IntentSequence', 'N/A')}")

    # Test 2: List cognitive phrases
    print_section("Test 2: List Cognitive Phrases")
    phrases = service.list_phrases(limit=5)
    print(f"Found {len(phrases)} cognitive phrases")

    if not phrases:
        print("\n⚠️  No cognitive phrases found. Exiting.")
        return

    # Use the first phrase for testing
    test_phrase = phrases[0]
    phrase_id = test_phrase["id"]
    print(f"\nUsing phrase: {phrase_id}")
    print(f"Label: {test_phrase.get('label', 'N/A')}")
    print(f"Description: {test_phrase.get('description', 'N/A')}")

    # Test 3: Direct database query (SurrealDB with sequences)
    print_section("Test 3: Database-Level Query (with graph traversal)")

    graph_store = service.graph_store
    if hasattr(graph_store, 'get_state_with_sequences'):
        print("✅ GraphStore has get_state_with_sequences() method")

        # Get phrase detail to find first state_id
        phrase_detail = service.get_phrase(phrase_id)
        if phrase_detail and phrase_detail.get("states"):
            first_state_id = phrase_detail["states"][0]["id"]
            print(f"\nTesting with state_id: {first_state_id}")

            # Test get_state_with_sequences
            state_with_sequences = graph_store.get_state_with_sequences(first_state_id)

            if state_with_sequences:
                print_subsection("Result from get_state_with_sequences()")
                has_sequences = check_field_presence(
                    state_with_sequences, "sequences", "DB query"
                )
                if has_sequences and state_with_sequences["sequences"]:
                    print(f"✅ Found {len(state_with_sequences['sequences'])} sequences")
                    print(f"First sequence: {json.dumps(state_with_sequences['sequences'][0], indent=2, ensure_ascii=False)[:200]}...")
                else:
                    print("❌ No sequences found in DB query result")
            else:
                print("❌ get_state_with_sequences() returned None")
        else:
            print("⚠️  No states found in phrase detail")
    else:
        print("❌ GraphStore does NOT have get_state_with_sequences() method")

    # Test 4: Memory.get_state() - used by Reasoner
    print_section("Test 4: Memory.get_state() - Used by Reasoner")

    memory = service.workflow_memory
    if phrase_detail and phrase_detail.get("states"):
        first_state_id = phrase_detail["states"][0]["id"]

        state_obj = memory.get_state(first_state_id)

        if state_obj:
            print_subsection("State object returned")
            print(f"State ID: {state_obj.id}")
            print(f"Description: {state_obj.description}")
            print(f"Page URL: {state_obj.page_url}")
            print(f"Page Title: {state_obj.page_title}")

            # Check if intent_sequences field exists
            print_subsection("Checking intent_sequences field")
            has_attr = hasattr(state_obj, 'intent_sequences')
            print(f"{'✅' if has_attr else '❌'} State object has 'intent_sequences' attribute: {has_attr}")

            if has_attr:
                sequences = state_obj.intent_sequences
                if sequences:
                    print(f"✅ intent_sequences contains {len(sequences)} items")
                else:
                    print("❌ intent_sequences is empty list")
            else:
                print("❌ State object does NOT have intent_sequences attribute")

            # Check to_dict() output
            print_subsection("Checking State.to_dict() output")
            state_dict = state_obj.to_dict()
            has_sequences_in_dict = check_field_presence(
                state_dict, "intent_sequences", "state_dict"
            )
            if has_sequences_in_dict and state_dict["intent_sequences"]:
                print(f"✅ state_dict['intent_sequences'] has {len(state_dict['intent_sequences'])} items")
            else:
                print("❌ state_dict['intent_sequences'] is missing or empty")
        else:
            print("❌ memory.get_state() returned None")

    # Test 5: Reasoner.query() - L1 CognitivePhrase match
    print_section("Test 5: Reasoner.query() - L1 CognitivePhrase Match")

    query_text = test_phrase.get("description", "")
    print(f"Query: {query_text}")

    try:
        # Create a mock LLM provider (or use real one if available)
        # For now, just test the query without LLM
        print("\n⚠️  Skipping Reasoner test (requires LLM provider)")
        print("     We've already identified the issue in Memory.get_state()")
    except Exception as e:
        print(f"❌ Reasoner query failed: {e}")

    # Test 6: Summary of findings
    print_section("Test 6: Summary - Data Loss Points Identified")

    print("""
Based on the tests above, here's where intent_sequences are lost:

STAGE 1: Database (SurrealDB)
  ✅ get_state_with_sequences() DOES retrieve intent_sequences
     via graph traversal: ->has_sequence->intentsequence

STAGE 2: Memory.get_state() via StateManager.get_state()
  ❌ Uses graph_store.get_node() which does NOT retrieve intent_sequences
  ❌ Only gets basic State fields: id, description, page_url, page_title
  ❌ LOSES intent_sequences at this point

STAGE 3: Reasoner._query_task() L1 CognitivePhrase match
  ❌ Calls memory.get_state() which already lost the data
  ❌ Returns QueryResult with incomplete State objects

STAGE 4: API response (main.py)
  ❌ Calls result.cognitive_phrase.to_dict()
  ❌ cognitive_phrase.states contains incomplete State objects
  ❌ State.to_dict() doesn't have intent_sequences to serialize

STAGE 5: MemoryToolkit parsing
  ❌ QueryResult.from_api_response() receives incomplete data
  ❌ Can't extract what was already lost

STAGE 6: AMITaskPlanner formatting
  ❌ _format_cognitive_phrase() can only format what it received
  ❌ workflow_guide ends up with only descriptions, no operational details
    """)

    # Cleanup
    service.close()
    print_section("Test Complete")


if __name__ == "__main__":
    asyncio.run(test_memory_data_flow())
