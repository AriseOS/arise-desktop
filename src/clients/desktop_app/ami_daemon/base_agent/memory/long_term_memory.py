"""
Long-term Memory Manager

Manages long-term memory files based on OpenClaw's design:
- MEMORY.md: Curated long-term memory (decisions, preferences, facts)
- memory/YYYY-MM-DD.md: Daily memory logs (running context, notes)

References:
- OpenClaw: third-party/openclaw/docs/concepts/memory.md
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


# Default memory directory
DEFAULT_MEMORY_PATH = Path.home() / ".ami" / "memory"

# Memory file names
MEMORY_FILE = "MEMORY.md"
DAILY_LOG_FORMAT = "%Y-%m-%d.md"

# Memory section headers
MEMORY_SECTIONS = {
    "preferences": "## User Preferences",
    "decisions": "## Important Decisions",
    "facts": "## Key Facts",
    "context": "## Context",
    "notes": "## Notes",
}

# Daily log template
DAILY_LOG_TEMPLATE = """# Memory Log - {date}

## Today's Notes

"""


class LongTermMemory:
    """
    Long-term memory manager.

    Manages two types of memory files:
    1. MEMORY.md - Curated long-term memory
       - User preferences
       - Important decisions
       - Durable facts
    2. memory/YYYY-MM-DD.md - Daily logs
       - Running context
       - Day-to-day notes

    Design principle (from OpenClaw):
    - Memory files are plain Markdown
    - Files are the source of truth
    - Agent writes memory explicitly when needed
    """

    def __init__(
        self,
        base_path: Optional[Union[str, Path]] = None,
        user_id: Optional[str] = None,
        auto_create: bool = True,
    ):
        """
        Initialize long-term memory manager.

        Args:
            base_path: Base directory for memory files.
                      Defaults to ~/.ami/memory/ or ~/.ami/memory/{user_id}/
            user_id: Optional user ID for data isolation
            auto_create: Whether to create directories if not exist
        """
        if base_path:
            self.base_path = Path(base_path)
        elif user_id:
            self.base_path = DEFAULT_MEMORY_PATH / user_id
        else:
            self.base_path = DEFAULT_MEMORY_PATH

        self.user_id = user_id
        self._memory_file = self.base_path / MEMORY_FILE
        self._daily_logs_dir = self.base_path

        if auto_create:
            self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Ensure memory directories exist."""
        self.base_path.mkdir(parents=True, exist_ok=True)

    @property
    def memory_file_path(self) -> Path:
        """Path to MEMORY.md file."""
        return self._memory_file

    @property
    def daily_logs_dir(self) -> Path:
        """Path to daily logs directory."""
        return self._daily_logs_dir

    # ==================== MEMORY.md Operations ====================

    def read_memory(self) -> str:
        """
        Read the entire MEMORY.md content.

        Returns:
            Memory file content or empty string if not exists
        """
        if not self._memory_file.exists():
            return ""

        try:
            return self._memory_file.read_text(encoding="utf-8")
        except IOError as e:
            logger.error(f"Failed to read MEMORY.md: {e}")
            return ""

    def write_memory(self, content: str) -> bool:
        """
        Write content to MEMORY.md (overwrites).

        Args:
            content: Full content to write

        Returns:
            True if written successfully
        """
        try:
            self._ensure_directories()
            self._memory_file.write_text(content, encoding="utf-8")
            logger.info(f"Updated MEMORY.md ({len(content)} chars)")
            return True
        except IOError as e:
            logger.error(f"Failed to write MEMORY.md: {e}")
            return False

    def append_to_memory(
        self,
        content: str,
        section: Optional[str] = None,
    ) -> bool:
        """
        Append content to MEMORY.md.

        Args:
            content: Content to append
            section: Optional section header to append under
                    (preferences, decisions, facts, context, notes)

        Returns:
            True if appended successfully
        """
        current = self.read_memory()

        if section and section in MEMORY_SECTIONS:
            header = MEMORY_SECTIONS[section]
            if header in current:
                # Append under existing section
                parts = current.split(header)
                if len(parts) == 2:
                    # Find next section or end
                    section_content = parts[1]
                    next_section_pos = float('inf')
                    for other_section in MEMORY_SECTIONS.values():
                        if other_section != header:
                            pos = section_content.find(other_section)
                            if pos != -1 and pos < next_section_pos:
                                next_section_pos = pos

                    if next_section_pos == float('inf'):
                        # No next section, append to end
                        new_content = current + "\n" + content
                    else:
                        # Insert before next section
                        insert_pos = len(parts[0]) + len(header) + next_section_pos
                        new_content = current[:insert_pos] + "\n" + content + "\n" + current[insert_pos:]
                else:
                    new_content = current + "\n" + content
            else:
                # Add new section
                new_content = current + f"\n\n{header}\n\n{content}"
        else:
            # Simple append
            new_content = current + "\n" + content if current else content

        return self.write_memory(new_content)

    def get_memory_section(self, section: str) -> str:
        """
        Get content of a specific section from MEMORY.md.

        Args:
            section: Section name (preferences, decisions, facts, context, notes)

        Returns:
            Section content or empty string
        """
        if section not in MEMORY_SECTIONS:
            return ""

        content = self.read_memory()
        header = MEMORY_SECTIONS[section]

        if header not in content:
            return ""

        # Extract section content
        parts = content.split(header)
        if len(parts) < 2:
            return ""

        section_content = parts[1]

        # Find next section
        for other_section in MEMORY_SECTIONS.values():
            if other_section != header:
                pos = section_content.find(other_section)
                if pos != -1:
                    section_content = section_content[:pos]
                    break

        return section_content.strip()

    def memory_exists(self) -> bool:
        """Check if MEMORY.md exists."""
        return self._memory_file.exists()

    # ==================== Daily Log Operations ====================

    def get_daily_log_path(self, date: Optional[datetime] = None) -> Path:
        """
        Get path to daily log file for a date.

        Args:
            date: Date (defaults to today)

        Returns:
            Path to daily log file
        """
        if date is None:
            date = datetime.utcnow()
        filename = date.strftime(DAILY_LOG_FORMAT)
        return self._daily_logs_dir / filename

    def read_daily_log(self, date: Optional[datetime] = None) -> str:
        """
        Read daily log for a date.

        Args:
            date: Date (defaults to today)

        Returns:
            Log content or empty string
        """
        log_path = self.get_daily_log_path(date)

        if not log_path.exists():
            return ""

        try:
            return log_path.read_text(encoding="utf-8")
        except IOError as e:
            logger.error(f"Failed to read daily log: {e}")
            return ""

    def write_daily_log(
        self,
        content: str,
        date: Optional[datetime] = None,
    ) -> bool:
        """
        Write daily log for a date (overwrites).

        Args:
            content: Content to write
            date: Date (defaults to today)

        Returns:
            True if written successfully
        """
        log_path = self.get_daily_log_path(date)

        try:
            self._ensure_directories()
            log_path.write_text(content, encoding="utf-8")
            logger.info(f"Updated daily log: {log_path.name}")
            return True
        except IOError as e:
            logger.error(f"Failed to write daily log: {e}")
            return False

    def append_to_daily_log(
        self,
        content: str,
        date: Optional[datetime] = None,
        timestamp: bool = True,
    ) -> bool:
        """
        Append to daily log.

        Args:
            content: Content to append
            date: Date (defaults to today)
            timestamp: Whether to add timestamp prefix

        Returns:
            True if appended successfully
        """
        if date is None:
            date = datetime.utcnow()

        log_path = self.get_daily_log_path(date)

        # Read existing or create new
        if log_path.exists():
            current = self.read_daily_log(date)
        else:
            current = DAILY_LOG_TEMPLATE.format(
                date=date.strftime("%Y-%m-%d")
            )

        # Add timestamp if requested
        if timestamp:
            ts = datetime.utcnow().strftime("%H:%M")
            content = f"- [{ts}] {content}"

        new_content = current + "\n" + content

        return self.write_daily_log(new_content, date)

    def get_recent_daily_logs(
        self,
        days: int = 2,
    ) -> List[Tuple[datetime, str]]:
        """
        Get recent daily logs.

        Args:
            days: Number of days to retrieve (default: 2 = today + yesterday)

        Returns:
            List of (date, content) tuples, newest first
        """
        results = []
        today = datetime.utcnow()

        for i in range(days):
            date = today - timedelta(days=i)
            content = self.read_daily_log(date)
            if content:
                results.append((date, content))

        return results

    def list_daily_logs(
        self,
        limit: int = 30,
    ) -> List[Path]:
        """
        List available daily log files.

        Args:
            limit: Maximum number of files to return

        Returns:
            List of log file paths, newest first
        """
        if not self._daily_logs_dir.exists():
            return []

        logs = []
        for path in self._daily_logs_dir.glob("????-??-??.md"):
            logs.append(path)

        # Sort by filename (date) descending
        logs.sort(key=lambda p: p.name, reverse=True)

        return logs[:limit]

    # ==================== Memory Extraction ====================

    def extract_memory_from_conversation(
        self,
        messages: List[dict],
        conversation_summary: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Extract memory items from a conversation.

        This is a simple extraction that looks for explicit memory markers.
        For more sophisticated extraction, use LLM-based analysis.

        Args:
            messages: List of message dicts with 'role' and 'content'
            conversation_summary: Optional conversation summary

        Returns:
            Dict with extracted items:
            {
                "daily_notes": [...],  # Items for daily log
                "long_term": [...],    # Items for MEMORY.md
            }
        """
        daily_notes = []
        long_term = []

        # Keywords that suggest something should be remembered
        remember_keywords = [
            "remember", "记住", "don't forget", "别忘了",
            "important", "重要", "note that", "注意",
            "preference", "偏好", "always", "总是",
            "never", "从不", "i like", "我喜欢",
            "i prefer", "我更喜欢",
        ]

        for msg in messages:
            content = msg.get("content", "").lower()
            original_content = msg.get("content", "")

            # Check for explicit memory requests
            for keyword in remember_keywords:
                if keyword in content:
                    # Extract the relevant sentence/phrase
                    note = self._extract_memory_snippet(original_content, keyword)
                    if note:
                        if any(k in content for k in ["preference", "偏好", "always", "总是", "never", "从不", "i like", "我喜欢", "i prefer", "我更喜欢"]):
                            long_term.append(note)
                        else:
                            daily_notes.append(note)
                    break

        # Add conversation summary to daily notes
        if conversation_summary:
            daily_notes.append(f"Conversation: {conversation_summary}")

        return {
            "daily_notes": daily_notes,
            "long_term": long_term,
        }

    def _extract_memory_snippet(
        self,
        text: str,
        keyword: str,
        max_length: int = 200,
    ) -> str:
        """Extract a memory snippet around a keyword."""
        text_lower = text.lower()
        pos = text_lower.find(keyword.lower())

        if pos == -1:
            return ""

        # Find sentence boundaries
        start = text.rfind(".", 0, pos)
        start = start + 1 if start != -1 else 0

        end = text.find(".", pos)
        end = end + 1 if end != -1 else len(text)

        snippet = text[start:end].strip()

        if len(snippet) > max_length:
            snippet = snippet[:max_length - 3] + "..."

        return snippet

    # ==================== Search Operations ====================

    def search_memory(
        self,
        query: str,
        include_daily_logs: bool = True,
        max_daily_logs: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Search memory files for a query.

        Simple keyword search. For semantic search, use vector index.

        Args:
            query: Search query
            include_daily_logs: Whether to search daily logs
            max_daily_logs: Maximum daily logs to search

        Returns:
            List of search results with source and content
        """
        results = []
        query_lower = query.lower()

        # Search MEMORY.md
        memory_content = self.read_memory()
        if query_lower in memory_content.lower():
            # Find matching lines
            for i, line in enumerate(memory_content.split("\n")):
                if query_lower in line.lower():
                    results.append({
                        "source": "MEMORY.md",
                        "line": i + 1,
                        "content": line.strip(),
                    })

        # Search daily logs
        if include_daily_logs:
            logs = self.list_daily_logs(limit=max_daily_logs)
            for log_path in logs:
                try:
                    content = log_path.read_text(encoding="utf-8")
                    if query_lower in content.lower():
                        for i, line in enumerate(content.split("\n")):
                            if query_lower in line.lower():
                                results.append({
                                    "source": log_path.name,
                                    "line": i + 1,
                                    "content": line.strip(),
                                })
                except IOError:
                    continue

        return results

    # ==================== Context for Agent ====================

    def get_memory_context(
        self,
        include_memory_md: bool = True,
        include_daily_logs: int = 2,
        max_length: int = 4000,
    ) -> str:
        """
        Get memory context for injecting into agent prompt.

        Args:
            include_memory_md: Whether to include MEMORY.md
            include_daily_logs: Number of recent daily logs to include
            max_length: Maximum total context length

        Returns:
            Formatted memory context string
        """
        parts = []

        # Add MEMORY.md
        if include_memory_md:
            memory = self.read_memory()
            if memory:
                parts.append("## Long-term Memory (MEMORY.md)\n\n" + memory)

        # Add recent daily logs
        if include_daily_logs > 0:
            logs = self.get_recent_daily_logs(days=include_daily_logs)
            for date, content in logs:
                date_str = date.strftime("%Y-%m-%d")
                parts.append(f"## Daily Log ({date_str})\n\n{content}")

        # Join and truncate if needed
        context = "\n\n---\n\n".join(parts)

        if len(context) > max_length:
            context = context[:max_length - 3] + "..."

        return context


# =============================================================================
# Utility Functions
# =============================================================================

def get_long_term_memory(
    user_id: Optional[str] = None,
    base_path: Optional[Union[str, Path]] = None,
) -> LongTermMemory:
    """
    Get a LongTermMemory instance.

    Args:
        user_id: Optional user ID for data isolation
        base_path: Optional custom base path

    Returns:
        LongTermMemory instance
    """
    return LongTermMemory(base_path=base_path, user_id=user_id)


# =============================================================================
# Exported Symbols
# =============================================================================

__all__ = [
    "LongTermMemory",
    "get_long_term_memory",
    "DEFAULT_MEMORY_PATH",
    "MEMORY_FILE",
    "DAILY_LOG_FORMAT",
    "MEMORY_SECTIONS",
]
