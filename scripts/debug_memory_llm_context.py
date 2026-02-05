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
API_KEY = ""  # User's Ami/CRS API key (X-Ami-API-Key)
USER_ID = "shenyouren"  # User id / username


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
    if result.cognitive_phrase:
        print(f"cognitive_phrase.id: {result.cognitive_phrase.id}")
        print(f"cognitive_phrase.description: {result.cognitive_phrase.description}")
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
    example_task = "在亚马逊上搜索 AI 智能戒指并总结价格信息"
    example_url = "https://www.amazon.com/"

    await debug_task_query(example_task)
    await debug_page_operations(example_url)


if __name__ == "__main__":
    asyncio.run(main())

