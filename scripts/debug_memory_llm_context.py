#!/usr/bin/env python3
"""Debug script: test PlannerAgent's Memory analysis pipeline.

Tests the /api/v1/memory/plan endpoint which runs PlannerAgent server-side.
Shows every piece of data returned:

1. Coverage items (phrase/graph) with full workflow_guide
2. Uncovered parts
3. User preferences

This lets you see exactly what the PlannerAgent produces before
AMITaskPlanner does subtask decomposition.

Configure API_BASE_URL, API_KEY, USER_ID below, then run:

    python scripts/debug_memory_llm_context.py
    python scripts/debug_memory_llm_context.py "your task here"

Make sure the Cloud Backend is running (port 9000 by default).
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

# Ensure src/ is on sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# =============================================================================
# Configuration (edit these for your environment)
# =============================================================================

API_BASE_URL = os.environ.get("AMI_API_BASE_URL", "http://localhost:9000")
API_KEY = os.environ.get("AMI_API_KEY", "")
USER_ID = os.environ.get("AMI_USER_ID", "shenyouren")

DEFAULT_TASK = "收集 Amazon 上卖的最好的 10 款眼镜"


# =============================================================================
# HTTP helpers
# =============================================================================

async def _post(endpoint: str, payload: dict, timeout: float = 300.0) -> dict:
    """POST to Cloud Backend and return JSON response."""
    url = f"{API_BASE_URL}{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"X-Ami-API-Key": API_KEY},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()


def _print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def _print_section(title: str) -> None:
    print(f"\n--- {title} ---")


# =============================================================================
# PlannerAgent test
# =============================================================================

async def test_planner_agent(task: str) -> dict:
    """Call /api/v1/memory/plan and display the full MemoryPlan."""
    _print_header(f"PlannerAgent: Memory Analysis\n  Task: {task}")

    print("\nCalling PlannerAgent (this may take 10-30s)...")
    data = await _post("/api/v1/memory/plan", {
        "user_id": USER_ID,
        "task": task,
    })

    success = data.get("success", False)
    print(f"\nsuccess: {success}")

    memory_plan = data.get("memory_plan", {})
    plan_steps = memory_plan.get("steps", [])
    preferences = memory_plan.get("preferences", [])

    # --- Plan Steps ---
    _print_section(f"Plan Steps ({len(plan_steps)})")
    if not plan_steps:
        print("  (none — L3, no Memory match)")
    for step in plan_steps:
        index = step.get("index", "?")
        source = step.get("source", "none")
        content = step.get("content", "")
        phrase_id = step.get("phrase_id")
        state_ids = step.get("state_ids", [])
        workflow_guide = step.get("workflow_guide", "")

        source_label = {"phrase": "from Memory", "graph": "from graph", "none": "no Memory"}.get(source, source)
        print(f"\n  [Step {index}] ({source_label})")
        print(f"      Content:    {content}")
        if phrase_id:
            print(f"      Phrase ID:  {phrase_id}")
        if state_ids:
            print(f"      State IDs:  {', '.join(state_ids)}")

        if workflow_guide:
            print(f"      Workflow Guide ({len(workflow_guide)} chars):")
            for line in workflow_guide.split("\n"):
                print(f"        {line}")
        else:
            print("      Workflow Guide: (empty)")

    # --- Preferences ---
    _print_section(f"User Preferences ({len(preferences)})")
    if not preferences:
        print("  (none detected)")
    for pref in preferences:
        print(f"  - {pref}")

    # --- Summary ---
    _print_section("Summary")
    has_phrase = any(
        s.get("source") == "phrase" and s.get("phrase_id")
        for s in plan_steps
    )
    has_graph = any(s.get("source") == "graph" for s in plan_steps)
    if has_phrase:
        level = "L1 (phrase match)"
    elif has_graph:
        level = "L2 (graph exploration)"
    else:
        level = "L3 (no match)"
    print(f"  Memory Level: {level}")
    guide_total = sum(len(s.get("workflow_guide", "")) for s in plan_steps)
    print(f"  Total workflow_guide chars: {guide_total}")

    # --- Raw JSON ---
    _print_section("Raw Response (JSON)")
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))

    return data


# =============================================================================
# Main
# =============================================================================

async def main() -> None:
    task = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TASK

    if not API_KEY or not API_KEY.strip():
        print("Error: AMI_API_KEY is empty.")
        print("  Set via: export AMI_API_KEY='your-key'")
        sys.exit(1)

    print(f"Cloud Backend: {API_BASE_URL}")
    print(f"User ID:       {USER_ID}")
    print(f"Task:          {task}")

    await test_planner_agent(task)

    print("\n" + "=" * 80)
    print("  Done.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
