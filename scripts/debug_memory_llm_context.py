#!/usr/bin/env python3
"""Debug script: inspect Memory → LLM context strings.

This script mimics how the Agent uses MemoryToolkit:

1) Task-level query: query_task()
   - Shows how the memory result is formatted for LLM context
     via MemoryToolkit.format_task_result().

2) Page-level query: query_page_operations()
   - Shows the page-operations summary string that gets cached on the
     agent side and injected into subsequent LLM calls.

Configure the API base URL, user API key, and user_id below, then run:

    python scripts/debug_memory_llm_context.py

Make sure the Cloud Backend is running (port 9000 by default).
"""

import asyncio
import sys
from pathlib import Path


# Ensure src/ is on sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.clients.desktop_app.ami_daemon.base_agent.tools.toolkits.memory_toolkit import (  # noqa: E402
    MemoryToolkit,
    QueryResult,
)


# =============================================================================
# Configuration (edit these for your environment)
# =============================================================================

API_BASE_URL = "http://localhost:9000"  # Cloud Backend base URL
API_KEY = "ami_19f03b13b96dbfa078ef14a60fcb2e60003378e3a4af7c0bdad7aae0dd1c9803"  # User's Ami/CRS API key (X-Ami-API-Key)
USER_ID = "Primary"  # User id / username


async def debug_task_query(task: str) -> None:
    """Run a task-level memory query and print LLM context text."""

    print("=" * 80)
    print("Task-level Memory Query")
    print("=" * 80)
    print(f"Task: {task}\n")

    toolkit = MemoryToolkit(
        memory_api_base_url=API_BASE_URL,
        ami_api_key=API_KEY,
        user_id=USER_ID,
    )

    result: QueryResult = await toolkit.query_task(task)

    print("--- Raw summary ---")
    print(f"success: {result.success}")
    print(f"query_type: {result.query_type}")
    print(f"states: {len(result.states)} actions: {len(result.actions)}")

    # 打印原始 state 数据（检查是否包含 LLM 推理）
    print(f"\n--- Raw State Data (from API) ---")
    for i, state in enumerate(result.states, 1):
        desc = state.description
        print(f"\nState {i}:")
        print(f"  ID: {state.id[:16]}...")
        print(f"  Description length: {len(desc)}")
        if len(desc) > 300:
            print(f"  Description (first 300 chars): {desc[:300]}")
            print(f"  ...")
            print(f"  Description (last 200 chars): {desc[-200:]}")
        else:
            print(f"  Description: {desc}")

    if result.cognitive_phrase:
        print(f"cognitive_phrase.id: {result.cognitive_phrase.id}")
        print(f"cognitive_phrase.description: {result.cognitive_phrase.description}")

        # 打印所有属性
        print(f"\n--- cognitive_phrase attributes ---")
        phrase_dict = result.cognitive_phrase.model_dump() if hasattr(result.cognitive_phrase, 'model_dump') else result.cognitive_phrase.__dict__
        for key in phrase_dict.keys():
            if key == 'execution_plan':
                print(f"{key}: ({len(phrase_dict[key])} steps)")
            elif key == 'state_path':
                print(f"{key}: ({len(phrase_dict[key])} states)")
            else:
                val = str(phrase_dict[key])[:100] if phrase_dict[key] else 'None'
                print(f"{key}: {val}")

        # 打印 execution_plan
        print(f"\n--- execution_plan ({len(result.cognitive_phrase.execution_plan)} steps) ---")
        for step in result.cognitive_phrase.execution_plan:
            if hasattr(step, 'index'):
                state_id = step.state_id[:8] if step.state_id else 'None'
                nav_seq_id = step.navigation_sequence_id[:8] if step.navigation_sequence_id else 'None'
                nav_action_id = step.navigation_action_id[:8] if step.navigation_action_id else 'None'
                in_page_count = len(step.in_page_sequence_ids) if step.in_page_sequence_ids else 0
                print(f"  Step {step.index}: state_id={state_id}, nav_seq_id={nav_seq_id}, nav_action_id={nav_action_id}, in_page_seqs={in_page_count}")

        # 打印 result.states 的顺序
        print(f"\n--- result.states order ({len(result.states)} states) ---")
        for i, state in enumerate(result.states, 1):
            print(f"  {i}. {state.id[:8]}... : {state.page_url[:80]}")

        # 打印 workflow_guide 的详细信息
        if result.cognitive_phrase.execution_plan:
            print(f"\n--- Execution Plan ({len(result.cognitive_phrase.execution_plan)} steps) ---")
            for i, step in enumerate(result.cognitive_phrase.execution_plan, 1):
                if hasattr(step, 'index'):
                    state_id = step.state_id[:8] if step.state_id else 'None'
                    nav_seq_id = step.navigation_sequence_id[:8] if step.navigation_sequence_id else 'None'
                    nav_action_id = step.navigation_action_id[:8] if step.navigation_action_id else 'None'
                    in_page_count = len(step.in_page_sequence_ids) if step.in_page_sequence_ids else 0
                    print(f"  Step {i}: state_id={state_id}, nav_seq_id={nav_seq_id}, nav_action_id={nav_action_id}, in_page_seqs={in_page_count}")

            # 打印每个 step 对应的 state URL
            print(f"\n--- State URLs in Execution Plan (with timestamps) ---")
            for i, step in enumerate(result.cognitive_phrase.execution_plan, 1):
                if hasattr(step, 'state_id') and step.state_id:
                    # 找到对应的 state
                    for state in result.states:
                        if state.id == step.state_id:
                            from datetime import datetime
                            # Handle timestamp if available (may not be in toolkit State)
                            timestamp = getattr(state, 'timestamp', None)
                            if timestamp:
                                ts_str = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
                            else:
                                ts_str = 'None'
                            print(f"  Step {i}: {state.page_url[:100]}")
                            print(f"         timestamp={ts_str}, id={state.id[:8]}")
                            break
    print()

    print("--- LLM context (format_task_result) ---")
    context_text = MemoryToolkit.format_task_result(result)
    if context_text:
        print(context_text)
    else:
        print("(empty context)")


async def debug_page_operations(url: str) -> None:
    """Run a page-level memory query and print LLM context text.

    This uses query_page_operations(), which returns exactly the string
    that the agent caches and injects into LLM prompts.
    """

    print("\n" + "=" * 80)
    print("Page-level Memory Query (query_page_operations)")
    print("=" * 80)
    print(f"URL: {url}\n")

    toolkit = MemoryToolkit(
        memory_api_base_url=API_BASE_URL,
        ami_api_key=API_KEY,
        user_id=USER_ID,
    )

    context_text = await toolkit.query_page_operations(url)

    print("--- LLM context (page operations) ---")
    if context_text:
        print(context_text)
    else:
        print("(no recorded operations / empty context)")


async def main() -> None:
    # Validate API key
    if not API_KEY or not API_KEY.strip():
        print("❌ Error: API_KEY is empty or not set.")
        print("   Please edit this script and set a valid API_KEY.")
        print(f"   Current value: '{API_KEY}'")
        sys.exit(1)

    # Example task and URL – edit to match your recordings/memory
    example_task = "收集 Product HUnt 周榜产品信息"
    example_url = "https://www.amazon.com/"

    await debug_task_query(example_task)
    await debug_page_operations(example_url)


if __name__ == "__main__":
    asyncio.run(main())

