"""
LongTermMemoryToolkit - Agent tools for long-term memory operations.

Provides tools for Agent to:
- Read and write to MEMORY.md (long-term preferences/decisions)
- Append to daily logs
- Search memory
- Get memory context

Design principle (from OpenClaw):
- Memory files are plain Markdown
- Agent writes memory explicitly when asked to "remember"
- MEMORY.md for durable facts, daily logs for running context

References:
- OpenClaw: third-party/openclaw/docs/concepts/memory.md
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base_toolkit import BaseToolkit, FunctionTool

from ...memory.long_term_memory import (
    LongTermMemory,
    get_long_term_memory,
    MEMORY_SECTIONS,
)


logger = logging.getLogger(__name__)


class LongTermMemoryToolkit(BaseToolkit):
    """
    Toolkit for long-term memory operations.

    Provides tools for Agent to manage persistent memory:
    - remember_fact: Store a fact/preference in MEMORY.md
    - add_daily_note: Add a note to today's log
    - search_memory: Search memory files
    - get_memory_context: Get recent memory for context

    Example usage in Agent:
    ```
    User: "Remember that I prefer dark mode"
    Agent: [calls remember_fact("User prefers dark mode", section="preferences")]
    Agent: "I've noted your preference for dark mode."
    ```
    """

    agent_name: str = "long_term_memory"

    def __init__(
        self,
        user_id: str,
        base_path: Optional[Union[str, Path]] = None,
        timeout: Optional[float] = 30.0,
    ):
        """
        Initialize LongTermMemoryToolkit.

        Args:
            user_id: User ID for data isolation
            base_path: Optional custom base path for memory files
            timeout: Tool operation timeout in seconds
        """
        super().__init__(timeout=timeout)
        self._user_id = user_id
        self._memory = LongTermMemory(
            base_path=base_path,
            user_id=user_id,
        )

        logger.info(
            f"LongTermMemoryToolkit initialized "
            f"(user_id={user_id}, base_path={self._memory.base_path})"
        )

    @property
    def memory(self) -> LongTermMemory:
        """Get the LongTermMemory instance."""
        return self._memory

    # =========================================================================
    # Tool Methods (exposed to LLM)
    # =========================================================================

    def remember_fact(
        self,
        fact: str,
        section: str = "notes",
    ) -> str:
        """
        Store a fact, preference, or decision in long-term memory (MEMORY.md).

        Use this when the user explicitly asks you to "remember" something,
        or when you learn an important preference or decision that should
        persist across conversations.

        **When to use:**
        - User says "remember that..." or "don't forget..."
        - User states a preference ("I prefer...", "I like...", "I always...")
        - An important decision is made that affects future interactions

        Args:
            fact: The fact/preference/decision to remember.
                  Should be a clear, concise statement.
                  Examples:
                  - "User prefers dark mode in all applications"
                  - "Project deadline is March 15, 2026"
                  - "User's timezone is Asia/Shanghai"

            section: Which section to store under. Options:
                    - "preferences" - User preferences and habits
                    - "decisions" - Important decisions made
                    - "facts" - Key facts and information
                    - "context" - Background context
                    - "notes" - General notes (default)

        Returns:
            Confirmation message
        """
        logger.info(f"[LongTermMemory] remember_fact: {fact[:50]}...")

        # Validate section
        valid_sections = list(MEMORY_SECTIONS.keys())
        if section not in valid_sections:
            return json.dumps({
                "success": False,
                "error": f"Invalid section. Use one of: {valid_sections}",
            }, ensure_ascii=False)

        # Format the fact with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        formatted_fact = f"- [{timestamp}] {fact}"

        # Append to MEMORY.md
        success = self._memory.append_to_memory(formatted_fact, section=section)

        if success:
            return json.dumps({
                "success": True,
                "message": f"Stored in MEMORY.md under {section}",
                "fact": fact,
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "success": False,
                "error": "Failed to write to MEMORY.md",
            }, ensure_ascii=False)

    def add_daily_note(
        self,
        note: str,
    ) -> str:
        """
        Add a note to today's daily log.

        Use this for day-to-day running context that doesn't need
        to persist permanently. Good for:
        - Tasks completed today
        - Temporary context
        - Meeting notes
        - Progress updates

        Args:
            note: The note to add. Will be timestamped automatically.

        Returns:
            Confirmation message
        """
        logger.info(f"[LongTermMemory] add_daily_note: {note[:50]}...")

        success = self._memory.append_to_daily_log(note, timestamp=True)

        if success:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return json.dumps({
                "success": True,
                "message": f"Added to daily log ({date})",
                "note": note,
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "success": False,
                "error": "Failed to write to daily log",
            }, ensure_ascii=False)

    def search_memory(
        self,
        query: str,
        include_daily_logs: bool = True,
    ) -> str:
        """
        Search long-term memory for a query.

        Use this when:
        - User asks about something they told you before
        - You need to recall a preference or decision
        - Looking for context from previous interactions

        Args:
            query: Search query (keyword search)
            include_daily_logs: Whether to also search recent daily logs

        Returns:
            JSON with search results
        """
        logger.info(f"[LongTermMemory] search_memory: {query}")

        results = self._memory.search_memory(
            query=query,
            include_daily_logs=include_daily_logs,
            max_daily_logs=7,
        )

        return json.dumps({
            "query": query,
            "results": results,
            "total_found": len(results),
        }, ensure_ascii=False, indent=2)

    def get_memory_context(
        self,
        include_memory_md: bool = True,
        include_daily_logs: int = 2,
    ) -> str:
        """
        Get recent memory context.

        Use this at the start of a conversation or when you need
        to refresh your understanding of user preferences and recent activity.

        Args:
            include_memory_md: Whether to include MEMORY.md content
            include_daily_logs: Number of recent daily logs to include (0-7)

        Returns:
            Memory context as formatted text
        """
        logger.info(f"[LongTermMemory] get_memory_context")

        context = self._memory.get_memory_context(
            include_memory_md=include_memory_md,
            include_daily_logs=min(include_daily_logs, 7),
            max_length=4000,
        )

        if not context:
            return json.dumps({
                "message": "No memory context found",
                "context": "",
            }, ensure_ascii=False)

        return json.dumps({
            "message": "Memory context retrieved",
            "context": context,
        }, ensure_ascii=False, indent=2)

    def read_memory_section(
        self,
        section: str,
    ) -> str:
        """
        Read a specific section from MEMORY.md.

        Args:
            section: Section to read (preferences, decisions, facts, context, notes)

        Returns:
            Section content
        """
        logger.info(f"[LongTermMemory] read_memory_section: {section}")

        content = self._memory.get_memory_section(section)

        return json.dumps({
            "section": section,
            "content": content if content else "(empty)",
        }, ensure_ascii=False, indent=2)

    # =========================================================================
    # BaseToolkit Interface
    # =========================================================================

    def get_tools(self) -> List[FunctionTool]:
        """Return FunctionTool objects for LLM tool-use.

        Exposes:
        - remember_fact: Store in MEMORY.md
        - add_daily_note: Add to daily log
        - search_memory: Search memory files
        - get_memory_context: Get recent memory context
        """
        return [
            FunctionTool(self.remember_fact),
            FunctionTool(self.add_daily_note),
            FunctionTool(self.search_memory),
            FunctionTool(self.get_memory_context),
            FunctionTool(self.read_memory_section),
        ]

    def is_available(self) -> bool:
        """Check if long-term memory is available."""
        return True

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "LongTermMemory"


# =============================================================================
# System Prompt Section for Agent
# =============================================================================

LONG_TERM_MEMORY_PROMPT_SECTION = """
## Long-term Memory

You have access to persistent memory that survives across conversations:

**MEMORY.md** - Long-term storage for:
- User preferences and habits
- Important decisions
- Key facts and context

**Daily logs** - Day-to-day notes and running context

**When to use memory:**
- User says "remember..." or "don't forget..." → Call `remember_fact()`
- User states a preference → Call `remember_fact(fact, section="preferences")`
- You need to note something for today → Call `add_daily_note()`
- Looking up past information → Call `search_memory()`
- Starting a conversation → Consider `get_memory_context()` for context

**Available tools:**
- `remember_fact(fact, section)` - Store in MEMORY.md
- `add_daily_note(note)` - Add to today's log
- `search_memory(query)` - Search memory files
- `get_memory_context()` - Get recent memory
- `read_memory_section(section)` - Read specific section

**Example:**
User: "Remember that I prefer Python over JavaScript"
→ Call remember_fact("User prefers Python over JavaScript for coding tasks", section="preferences")
"""


def get_long_term_memory_prompt() -> str:
    """Get the long-term memory section for System Prompt."""
    return LONG_TERM_MEMORY_PROMPT_SECTION


# =============================================================================
# Exported Symbols
# =============================================================================

__all__ = [
    "LongTermMemoryToolkit",
    "LONG_TERM_MEMORY_PROMPT_SECTION",
    "get_long_term_memory_prompt",
]
