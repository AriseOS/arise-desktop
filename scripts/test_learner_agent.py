#!/usr/bin/env python3
"""Test script: verify Online Learning (LearnerAgent) feature.

3 layers of verification:
1. API test: POST synthetic execution data to /api/v1/memory/learn
2. Dedup test: Send same data again → should NOT create duplicate phrase
3. Recall test: PlannerAgent should recall the newly created phrase (L1 hit)

Usage:
    python scripts/test_learner_agent.py                  # run all 3 layers
    python scripts/test_learner_agent.py --api-only        # only API test
    python scripts/test_learner_agent.py --task "your task" # custom task text

Requires:
- Cloud Backend running (port 9090)
- Environment: AMI_API_KEY, AMI_USER_ID
- Memory with some existing States (from prior browser sessions)
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import httpx

# Ensure src/ is on sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = os.environ.get("AMI_API_BASE_URL", "http://localhost:9090")
API_KEY = os.environ.get("AMI_API_KEY", "")
USER_ID = os.environ.get("AMI_USER_ID", "shenyouren")


# =============================================================================
# Display helpers
# =============================================================================

def _header(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _info(msg: str) -> None:
    print(f"  [INFO] {msg}")


# =============================================================================
# Build synthetic execution data
# =============================================================================

def build_synthetic_execution_data(user_request: str) -> dict:
    """Build a realistic TaskExecutionData dict for testing.

    Simulates a 3-subtask browser workflow:
    1. Navigate to ProductHunt
    2. Browse top products
    3. Take notes on findings

    Uses real-looking tool records so the LearnerAgent
    can analyze the "effective path".
    """
    return {
        "task_id": "test-learn-001",
        "user_request": user_request,
        "subtasks": [
            {
                "subtask_id": "sub_1",
                "content": "Open ProductHunt and navigate to the homepage",
                "agent_type": "browser",
                "depends_on": [],
                "state": "DONE",
                "result_summary": "Successfully navigated to ProductHunt homepage.",
                "tool_records": [
                    {
                        "thinking": "I need to navigate to ProductHunt to start browsing products.",
                        "tool_name": "browser_navigate",
                        "input_summary": "{'url': 'https://www.producthunt.com'}",
                        "success": True,
                        "result_summary": "**Current Page:** Product Hunt - The best new products in tech\n**URL:** https://www.producthunt.com/\nPage loaded successfully.",
                        "judgment": "Good, ProductHunt homepage loaded. I can see today's top products listed.",
                        "current_url": "https://www.producthunt.com/",
                    },
                ],
            },
            {
                "subtask_id": "sub_2",
                "content": "Browse the leaderboard page to see top ranked products",
                "agent_type": "browser",
                "depends_on": ["sub_1"],
                "state": "DONE",
                "result_summary": "Opened the leaderboard and found top 10 products.",
                "tool_records": [
                    {
                        "thinking": "I need to click on the leaderboard link to see top products.",
                        "tool_name": "browser_click",
                        "input_summary": "{'coordinate': [245, 89], 'element_description': 'Leaderboard link'}",
                        "success": True,
                        "result_summary": "**Current Page:** Leaderboard - Product Hunt\n**URL:** https://www.producthunt.com/leaderboard/daily/2026/2/13\nClicked leaderboard link.",
                        "judgment": "The leaderboard page shows today's top products. I can see rankings.",
                        "current_url": "https://www.producthunt.com/leaderboard/daily/2026/2/13",
                    },
                    {
                        "thinking": "Let me scroll down to see more products on the leaderboard.",
                        "tool_name": "browser_scroll",
                        "input_summary": "{'coordinate': [512, 400], 'direction': 'down'}",
                        "success": True,
                        "result_summary": "**Current Page:** Leaderboard - Product Hunt\n**URL:** https://www.producthunt.com/leaderboard/daily/2026/2/13\nScrolled down to see more products.",
                        "judgment": "Now I can see products ranked 5-10. I have all the data I need.",
                        "current_url": "https://www.producthunt.com/leaderboard/daily/2026/2/13",
                    },
                ],
            },
            {
                "subtask_id": "sub_3",
                "content": "Take notes on the top products found",
                "agent_type": "browser",
                "depends_on": ["sub_2"],
                "state": "DONE",
                "result_summary": "Noted down all top 10 products with descriptions.",
                "tool_records": [
                    {
                        "thinking": "I should take notes on what I found for the user.",
                        "tool_name": "take_note",
                        "input_summary": "{'content': 'Top 10 products from PH leaderboard: 1. AI Tool...'}",
                        "success": True,
                        "result_summary": "Note saved successfully.",
                        "judgment": "Notes saved. Task complete.",
                        "current_url": "",
                    },
                ],
            },
        ],
        "completed_count": 3,
        "failed_count": 0,
        "total_count": 3,
    }


# =============================================================================
# Layer 1: API Test
# =============================================================================

async def test_api(user_request: str) -> dict | None:
    """Send execution data to /api/v1/memory/learn and check response."""
    _header("Layer 1: API Test — POST /api/v1/memory/learn")

    execution_data = build_synthetic_execution_data(user_request)

    _info(f"user_request: {user_request}")
    _info(f"subtasks: {len(execution_data['subtasks'])} ({execution_data['completed_count']} completed)")
    _info(f"total tool_records: {sum(len(s['tool_records']) for s in execution_data['subtasks'])}")

    payload = {
        "user_id": USER_ID,
        "execution_data": execution_data,
    }
    headers = {"X-Ami-API-Key": API_KEY}

    _info(f"Sending to {API_BASE_URL}/api/v1/memory/learn ...")
    _info("(This may take 30-60s due to LLM calls)")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/memory/learn",
                json=payload,
                headers=headers,
                timeout=300.0,
            )
        except httpx.ConnectError:
            _fail(f"Cannot connect to {API_BASE_URL}. Is the Cloud Backend running?")
            return None

    print(f"\n  Status: {response.status_code}")

    if response.status_code != 200:
        _fail(f"HTTP {response.status_code}: {response.text[:500]}")
        return None

    result = response.json()
    print(f"  Response: {json.dumps(result, indent=2, ensure_ascii=False)}")

    if result.get("success"):
        _ok("API call succeeded")
    else:
        _fail("API returned success=false")

    if result.get("phrase_created"):
        _ok(f"CognitivePhrase created: {result.get('phrase_id')}")
    else:
        _info(f"No phrase created. Reason: {result.get('reason', 'unknown')}")
        _info("(This is normal if States don't exist in Memory yet — "
              "the LearnerAgent won't create a phrase without real States)")

    return result


# =============================================================================
# Layer 2: Dedup Test
# =============================================================================

async def test_dedup(user_request: str, first_result: dict | None) -> None:
    """Send same data again — should NOT create a duplicate phrase."""
    _header("Layer 2: Dedup Test — Same Data, No Duplicate")

    if first_result is None:
        _info("Skipping — first API call failed")
        return

    if not first_result.get("phrase_created"):
        _info("Skipping — first call didn't create a phrase (nothing to dedup)")
        return

    _info("Sending identical execution data again...")

    execution_data = build_synthetic_execution_data(user_request)
    payload = {
        "user_id": USER_ID,
        "execution_data": execution_data,
    }
    headers = {"X-Ami-API-Key": API_KEY}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/api/v1/memory/learn",
            json=payload,
            headers=headers,
            timeout=300.0,
        )

    result = response.json()
    print(f"  Response: {json.dumps(result, indent=2, ensure_ascii=False)}")

    if not result.get("phrase_created"):
        _ok("Dedup works — no duplicate phrase created")
        _info(f"Reason: {result.get('reason', 'unknown')}")
    else:
        _fail("Duplicate phrase created! Dedup may not be working.")
        _info(f"Second phrase_id: {result.get('phrase_id')}")


# =============================================================================
# Layer 3: Recall Test (PlannerAgent)
# =============================================================================

async def test_recall(user_request: str, first_result: dict | None) -> None:
    """Check if PlannerAgent can recall the newly created phrase (L1 hit)."""
    _header("Layer 3: Recall Test — PlannerAgent Should Find New Phrase")

    if first_result is None or not first_result.get("phrase_created"):
        _info("Skipping — no phrase was created to recall")
        return

    phrase_id = first_result["phrase_id"]
    _info(f"Testing if PlannerAgent recalls phrase: {phrase_id}")

    # Use the memory/plan endpoint to test recall
    payload = {
        "user_id": USER_ID,
        "task": user_request,
    }
    headers = {"X-Ami-API-Key": API_KEY}

    _info(f"Sending to {API_BASE_URL}/api/v1/memory/plan ...")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/memory/plan",
                json=payload,
                headers=headers,
                timeout=300.0,
            )
        except httpx.ConnectError:
            _fail("Cannot connect to Cloud Backend")
            return

    if response.status_code != 200:
        _fail(f"HTTP {response.status_code}: {response.text[:300]}")
        return

    result = response.json()

    # Check if the phrase_id appears in the plan's coverage
    plan_str = json.dumps(result, ensure_ascii=False)
    if phrase_id in plan_str:
        _ok(f"PlannerAgent recalled the new phrase ({phrase_id})!")
        _info("The learning loop is complete: learn → recall → faster execution")
    else:
        _info(f"Phrase {phrase_id} not found in PlannerAgent response")
        _info("This may be normal if the planner chose a different strategy")

    # Show coverage items
    memory_plan = result.get("memory_plan", {})
    coverage = memory_plan.get("coverage_items", [])
    if coverage:
        _info(f"Coverage items found: {len(coverage)}")
        for item in coverage:
            src = item.get("source", "?")
            summary = item.get("summary", "")[:100]
            pid = item.get("phrase_id", "")
            print(f"    [{src}] {summary}  (phrase_id={pid})")
    else:
        _info("No coverage items in plan response")


# =============================================================================
# Main
# =============================================================================

async def main() -> None:
    if not API_KEY:
        print("Error: AMI_API_KEY is empty. Set via: export AMI_API_KEY='...'")
        sys.exit(1)

    print(f"Cloud Backend:  {API_BASE_URL}")
    print(f"User ID:        {USER_ID}")
    print(f"API Key:        {API_KEY[:8]}...")

    api_only = "--api-only" in sys.argv

    # Get custom task or use default
    user_request = "去 ProductHunt 看看今天排行榜上 top 10 的产品"
    for i, arg in enumerate(sys.argv):
        if arg == "--task" and i + 1 < len(sys.argv):
            user_request = sys.argv[i + 1]
            break

    # Layer 1: API test
    result = await test_api(user_request)

    if api_only:
        print("\n(--api-only mode, skipping dedup and recall tests)")
        return

    # Layer 2: Dedup test
    await test_dedup(user_request, result)

    # Layer 3: Recall test
    await test_recall(user_request, result)

    # Summary
    _header("Summary")
    if result and result.get("success"):
        _ok("API endpoint works correctly")
        if result.get("phrase_created"):
            _ok("LearnerAgent created a CognitivePhrase from execution data")
            _info("The full learning loop is functional")
        else:
            _info("LearnerAgent analyzed data but decided not to create a phrase")
            _info(f"Reason: {result.get('reason', 'unknown')}")
            _info("This is expected if the URLs in test data don't match real States in Memory")
            _info("To test phrase creation, run a real browser task first, then trigger learning")
    else:
        _fail("API test failed — check Cloud Backend logs for details")

    print()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Show learner-related logs
    logging.getLogger("src.common.memory.learner").setLevel(logging.INFO)
    logging.getLogger("src.common.memory.memory_service").setLevel(logging.INFO)

    asyncio.run(main())
