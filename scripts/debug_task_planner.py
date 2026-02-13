#!/usr/bin/env python3
"""Debug script: test AMITaskPlanner's full decomposition pipeline.

Shows end-to-end flow:
1. PlannerAgent returns MemoryPlan (via HTTP)
2. AMITaskPlanner formats memory_context for decomposer
3. Decomposer LLM splits into subtasks
4. Coverage guides assigned to browser subtasks

Usage:
    python scripts/debug_task_planner.py
    python scripts/debug_task_planner.py "your task here"
    python scripts/debug_task_planner.py --all  # run all test scenarios

Requires:
- Cloud Backend running (port 9000)
- Environment: AMI_API_KEY, AMI_USER_ID
- LLM calls go through CRS proxy (AMI_API_KEY used as LLM key)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, List, Optional

# Ensure src/ is on sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = os.environ.get("AMI_API_BASE_URL", "http://localhost:9000")
API_KEY = os.environ.get("AMI_API_KEY", "")
USER_ID = os.environ.get("AMI_USER_ID", "shenyouren")
# LLM_MODEL = os.environ.get("AMI_LLM_MODEL", "claude-sonnet-4-5-20250929")
LLM_MODEL = os.environ.get("AMI_LLM_MODEL", "glm-4.7")
# LLM calls go through CRS proxy using AMI_API_KEY
LLM_API_KEY = os.environ.get("AMI_LLM_API_KEY", "") or API_KEY
LLM_BASE_URL = os.environ.get("AMI_LLM_BASE_URL", "https://api.ariseos.com/api")

TEST_SCENARIOS = [
    {
        "name": "Amazon 泛化",
        "task": "收集 Amazon 上卖的最好的 10 款眼镜",
        "expect": "L1 phrase泛化, browser subtask with workflow_guide",
    },
    {
        "name": "ProductHunt 部分匹配",
        "task": "去 ProductHunt 看看本周有什么好的 AI 产品",
        "expect": "L1 partial match, AI filtering uncovered",
    },
    {
        "name": "混合覆盖",
        "task": "去 ProductHunt 看看本周排行榜 top 10，整理成 Excel 发邮件给老板",
        "expect": "L1 PH covered, Excel/email uncovered, multiple subtask types",
    },
    {
        "name": "完全无关",
        "task": "帮我订一张下周三从北京到上海的机票",
        "expect": "L3, no coverage, all subtasks without guide",
    },
    {
        "name": "模糊意图",
        "task": "帮我看看最近有什么好产品",
        "expect": "L1, inferred intent → ProductHunt",
    },
]


# =============================================================================
# Minimal TaskState stub (just collects events)
# =============================================================================

class StubTaskState:
    """Collects SSE events without sending them anywhere."""

    def __init__(self):
        self.events: list = []

    async def put_event(self, event: Any) -> None:
        self.events.append(event)


# =============================================================================
# Display helpers
# =============================================================================

def _header(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def _section(title: str) -> None:
    print(f"\n--- {title} ---")


def _print_subtask(st) -> None:
    deps = f"  depends_on={st.depends_on}" if st.depends_on else ""
    mem = f"  memory={st.memory_level}" if st.memory_level != "L3" else ""
    print(f"\n  [{st.id}] type={st.agent_type}{deps}{mem}")
    print(f"      content: {st.content[:200]}")
    if st.workflow_guide:
        guide_preview = st.workflow_guide[:300]
        if len(st.workflow_guide) > 300:
            guide_preview += "..."
        print(f"      workflow_guide ({len(st.workflow_guide)} chars):")
        for line in guide_preview.split("\n"):
            print(f"        {line}")
    else:
        print(f"      workflow_guide: (none)")


# =============================================================================
# Core test function
# =============================================================================

async def test_task_planner(task: str, scenario_name: str = "") -> None:
    """Run AMITaskPlanner.decompose_and_query_memory() and display results."""
    from src.clients.desktop_app.ami_daemon.base_agent.tools.toolkits.memory_toolkit import (
        MemoryToolkit,
    )
    from src.clients.desktop_app.ami_daemon.base_agent.core.ami_task_planner import (
        AMITaskPlanner,
    )
    from src.clients.desktop_app.ami_daemon.base_agent.core.agent_factories import (
        create_provider,
    )

    title = f"AMITaskPlanner: {scenario_name}" if scenario_name else "AMITaskPlanner"
    _header(f"{title}\n  Task: {task}")

    # Step 1: Create components
    memory_toolkit = MemoryToolkit(
        memory_api_base_url=API_BASE_URL,
        ami_api_key=API_KEY,
        user_id=USER_ID,
    )

    provider = create_provider(
        llm_api_key=LLM_API_KEY,
        llm_model=LLM_MODEL,
        llm_base_url=LLM_BASE_URL,
    )

    task_state = StubTaskState()
    task_id = "debug-test-001"

    planner = AMITaskPlanner(
        task_id=task_id,
        task_state=task_state,
        provider=provider,
        memory_toolkit=memory_toolkit,
    )

    # Step 2: Run decomposition
    print("\nRunning decompose_and_query_memory (PlannerAgent + Decomposer)...")
    try:
        subtasks = await planner.decompose_and_query_memory(task)
    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 3: Display MemoryPlan (from SSE events)
    _section("SSE Events Summary")
    for evt in task_state.events:
        cls_name = type(evt).__name__
        if cls_name == "MemoryLevelData":
            print(f"  MemoryLevel: {evt.level} (method={evt.method}, states={evt.states_count})")
        elif cls_name == "DecomposeProgressData":
            msg = evt.message[:80] if evt.message else ""
            n_sub = len(evt.sub_tasks) if evt.sub_tasks else 0
            if evt.is_final:
                print(f"  DecomposeProgress: FINAL — {n_sub} subtasks")
            else:
                print(f"  DecomposeProgress: {evt.progress:.0%} — {msg}")
        elif cls_name == "AgentReportData":
            preview = evt.message[:150] if evt.message else ""
            print(f"  AgentReport: {preview}...")

    # Step 4: Display subtasks
    _section(f"Subtasks ({len(subtasks)})")

    type_counts = {}
    guide_count = 0
    for st in subtasks:
        type_counts[st.agent_type] = type_counts.get(st.agent_type, 0) + 1
        if st.workflow_guide:
            guide_count += 1
        _print_subtask(st)

    # Step 5: Summary
    _section("Summary")
    print(f"  Total subtasks: {len(subtasks)}")
    print(f"  Types: {type_counts}")
    print(f"  With workflow_guide: {guide_count}/{len(subtasks)}")

    # Check memory levels
    levels = {}
    for st in subtasks:
        lvl = st.memory_level or "L3"
        levels[lvl] = levels.get(lvl, 0) + 1
    print(f"  Memory levels: {levels}")

    total_guide = sum(len(st.workflow_guide or "") for st in subtasks)
    print(f"  Total workflow_guide chars: {total_guide}")


# =============================================================================
# Main
# =============================================================================

async def main() -> None:
    # Validate config
    if not API_KEY:
        print("Error: AMI_API_KEY is empty. Set via: export AMI_API_KEY='...'")
        sys.exit(1)
    print(f"Cloud Backend:  {API_BASE_URL}")
    print(f"User ID:        {USER_ID}")
    print(f"LLM Model:      {LLM_MODEL}")
    print(f"LLM Base URL:   {LLM_BASE_URL}")

    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        # Run all test scenarios
        for scenario in TEST_SCENARIOS:
            print(f"\n\n{'#' * 80}")
            print(f"# Scenario: {scenario['name']}")
            print(f"# Expect: {scenario['expect']}")
            print(f"{'#' * 80}")
            await test_task_planner(scenario["task"], scenario["name"])
        print(f"\n\n{'=' * 80}")
        print(f"  All {len(TEST_SCENARIOS)} scenarios done.")
        print(f"{'=' * 80}")
    else:
        task = sys.argv[1] if len(sys.argv) > 1 else TEST_SCENARIOS[0]["task"]
        await test_task_planner(task)

    print("\nDone.")


if __name__ == "__main__":
    # Show timestamps in logs to analyze timing
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # AMITaskPlanner logs
    logging.getLogger("src.clients.desktop_app.ami_daemon.base_agent.core.ami_task_planner").setLevel(
        logging.INFO
    )
    # MemoryToolkit logs (HTTP calls)
    logging.getLogger("src.clients.desktop_app.ami_daemon.base_agent.tools.toolkits.memory_toolkit").setLevel(
        logging.INFO
    )
    # Memory service logs
    logging.getLogger("src.common.memory").setLevel(logging.INFO)
    # LLM provider logs
    logging.getLogger("src.common.llm").setLevel(logging.INFO)

    asyncio.run(main())
