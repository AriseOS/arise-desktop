#!/usr/bin/env python3
"""Debug script: test private+public memory merge across all query types.

Tests 4 query endpoints to verify the private+public merge logic:

1. POST /api/v1/memory/phrase/query  — L1 merged phrase match
2. POST /api/v1/memory/query (task)  — L1→L2→L3 full pipeline
3. POST /api/v1/memory/query (action) — merged action/page-operations query
4. POST /api/v1/memory/state          — merged state-by-URL query

Each test prints the `source` field to verify private/public selection.

Configure API_BASE_URL, API_KEY, USER_ID below, then run:

    python scripts/debug_memory_llm_context.py

Make sure the Cloud Backend is running (port 9000 by default).
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

# Ensure src/ is on sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# =============================================================================
# Configuration (edit these for your environment)
# =============================================================================

API_BASE_URL = "http://localhost:9000"
API_KEY = "ami_32b02bf612c46de5abb4b4fdcf9cdedfc08734e8c2da7c90da7683e6c4d90a3a"
USER_ID = "shenyouren"

# Test data — edit to match your actual recordings/memory
EXAMPLE_TASK = "收集 Amazon 上卖的最好的 10 款眼镜"
EXAMPLE_URL = "https://www.amazon.com/"


# =============================================================================
# HTTP helpers
# =============================================================================

async def _post(endpoint: str, payload: dict) -> dict:
    """POST to Cloud Backend and return JSON response."""
    url = f"{API_BASE_URL}{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"X-Ami-API-Key": API_KEY},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()


def _print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


# =============================================================================
# Test 1: CognitivePhrase query (L1 merged)
# =============================================================================

async def test_phrase_query(task: str) -> None:
    _print_header(f"Test 1: CognitivePhrase Query (L1 merged)\n  Task: {task}")

    data = await _post("/api/v1/memory/phrase/query", {
        "user_id": USER_ID,
        "query": task,
    })

    source = data.get("source", "?")
    success = data.get("success", False)
    phrase = data.get("phrase")
    reasoning = data.get("reasoning", "")

    print(f"\nsuccess: {success}")
    print(f"source:  {source}")
    print(f"reasoning: {reasoning[:200]}")

    if phrase:
        print(f"\nMatched phrase:")
        print(f"  id:          {phrase.get('id', '?')}")
        print(f"  label:       {phrase.get('label', '?')}")
        print(f"  description: {phrase.get('description', '?')[:120]}")
        print(f"  states:      {len(phrase.get('states', []))}")
        print(f"  actions:     {len(phrase.get('actions', []))}")

        # Show state URLs
        for i, state in enumerate(phrase.get("states", []), 1):
            url = state.get("page_url", "?")
            print(f"    State {i}: {url[:100]}")
    else:
        print("\nNo matching phrase found.")


# =============================================================================
# Test 2: Unified query (task type — L1→L2→L3 pipeline)
# =============================================================================

async def test_task_query(task: str) -> None:
    _print_header(f"Test 2: Unified Task Query (L1→L2→L3)\n  Task: {task}")

    data = await _post("/api/v1/memory/query", {
        "user_id": USER_ID,
        "target": task,
    })

    source = data.get("source", "?")
    success = data.get("success", False)
    query_type = data.get("query_type", "?")
    metadata = data.get("metadata", {})
    method = metadata.get("method", "?")

    print(f"\nsuccess:    {success}")
    print(f"query_type: {query_type}")
    print(f"source:     {source}")
    print(f"method:     {method}")

    # States
    states = data.get("states", [])
    if states:
        print(f"\nPath ({len(states)} states):")
        for i, s in enumerate(states, 1):
            url = s.get("page_url", "?")
            desc = s.get("description", "")[:80]
            print(f"  {i}. {url[:80]}")
            if desc:
                print(f"     {desc}")

    # CognitivePhrase
    cp = data.get("cognitive_phrase")
    if cp:
        print(f"\nCognitivePhrase: {cp.get('id', '?')}")
        print(f"  label: {cp.get('label', '?')}")

    # Subtasks
    subtasks = data.get("subtasks", [])
    if subtasks:
        print(f"\nSubtasks ({len(subtasks)}):")
        for st in subtasks:
            found = st.get("found", False)
            print(f"  [{st.get('task_id')}] {st.get('target', '?')[:80]}  (found={found})")

    # Metadata
    print(f"\nMetadata: {json.dumps(metadata, ensure_ascii=False, default=str)}")


# =============================================================================
# Test 3: Unified query (action type — page operations, merged)
# =============================================================================

async def test_action_query(url: str) -> None:
    _print_header(f"Test 3: Action/Page-Operations Query (merged)\n  URL: {url}")

    # Exploration query (empty target)
    data = await _post("/api/v1/memory/query", {
        "user_id": USER_ID,
        "target": "",
        "current_state": url,
    })

    source = data.get("source", "?")
    success = data.get("success", False)
    query_type = data.get("query_type", "?")
    metadata = data.get("metadata", {})

    print(f"\nsuccess:    {success}")
    print(f"query_type: {query_type}")
    print(f"source:     {source}")
    print(f"method:     {metadata.get('method', '?')}")

    # IntentSequences
    sequences = data.get("intent_sequences", [])
    if sequences:
        print(f"\nIntentSequences ({len(sequences)}):")
        for i, seq in enumerate(sequences[:10], 1):
            desc = seq.get("description", "?")[:100]
            print(f"  {i}. {desc}")
        if len(sequences) > 10:
            print(f"  ... and {len(sequences) - 10} more")
    else:
        print("\nNo IntentSequences found.")

    # Outgoing actions
    actions = data.get("outgoing_actions", [])
    if actions:
        print(f"\nOutgoing Actions ({len(actions)}):")
        for i, a in enumerate(actions[:5], 1):
            target = a.get("target", "?")[:8]
            atype = a.get("action_type", "?")
            print(f"  {i}. -> {target}... ({atype})")


# =============================================================================
# Test 4: State-by-URL query (merged)
# =============================================================================

async def test_state_query(url: str) -> None:
    _print_header(f"Test 4: State-by-URL Query (merged)\n  URL: {url}")

    data = await _post("/api/v1/memory/state", {
        "user_id": USER_ID,
        "url": url,
    })

    source = data.get("source", "?")
    success = data.get("success", False)
    state = data.get("state")

    print(f"\nsuccess: {success}")
    print(f"source:  {source}")

    if state:
        print(f"\nState:")
        print(f"  id:          {state.get('id', '?')[:16]}...")
        print(f"  page_url:    {state.get('page_url', '?')[:100]}")
        print(f"  page_title:  {state.get('page_title', '?')}")
        print(f"  description: {state.get('description', '?')[:120]}")

    sequences = data.get("intent_sequences", [])
    if sequences:
        print(f"\nIntentSequences ({len(sequences)}):")
        for i, seq in enumerate(sequences[:10], 1):
            desc = seq.get("description", "?")[:100]
            print(f"  {i}. {desc}")
    else:
        print("\nNo IntentSequences found.")


# =============================================================================
# Main
# =============================================================================

async def main() -> None:
    if not API_KEY or not API_KEY.strip():
        print("Error: API_KEY is empty. Edit this script and set a valid key.")
        sys.exit(1)

    print(f"Cloud Backend: {API_BASE_URL}")
    print(f"User ID:       {USER_ID}")
    print(f"Task:          {EXAMPLE_TASK}")
    print(f"URL:           {EXAMPLE_URL}")

    # Run all 4 tests
    # Test 1 & 2 both test task queries (phrase-only vs full pipeline)
    await test_phrase_query(EXAMPLE_TASK)
    await test_task_query(EXAMPLE_TASK)

    # Test 3 & 4 both test URL-based queries
    await test_action_query(EXAMPLE_URL)
    await test_state_query(EXAMPLE_URL)

    print("\n" + "=" * 80)
    print("  All tests completed.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
