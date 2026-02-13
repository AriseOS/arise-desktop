"""Execution Data Collector - Extracts tool use and thinking from agent messages.

Collects execution data from agent conversations after each subtask completes.
Compresses tool inputs/outputs and extracts thinking/judgment for the LearnerAgent.

Data source: agent.get_messages() returns Anthropic-format messages.
"""

import logging
import re
from typing import Any, Dict, List

from src.common.memory.learner.models import (
    SubtaskExecutionData,
    TaskExecutionData,
    ToolUseRecord,
)

logger = logging.getLogger(__name__)

# Tools to skip - snapshot is too noisy, send_message/replan are meta
_SKIP_TOOLS = {
    "browser_get_page_snapshot",
    "send_message",
    "replan_review_context",
    "replan_split_and_handoff",
}

# Tool input compression rules per tool type
_INPUT_KEEP_FIELDS = {
    "browser_navigate": ["url"],
    "browser_click": ["coordinate", "element_description"],
    "browser_type": ["coordinate", "text", "element_description"],
    "browser_scroll": ["coordinate", "direction"],
    "browser_select_option": ["coordinate", "value"],
    "browser_switch_tab": ["tab_id"],
    "browser_close_tab": ["tab_id"],
    "search_google": ["query"],
    "take_note": ["content"],
    "read_note": [],
}


class ExecutionDataCollector:
    """Collects and compresses execution data from agent messages.

    Usage:
        collector = ExecutionDataCollector()
        # After each subtask completes:
        collector.collect_subtask_data(agent, subtask)
        # After all subtasks:
        task_data = collector.build_task_data(task_id, user_request, subtasks)
    """

    def __init__(self):
        self._subtask_data: List[SubtaskExecutionData] = []

    def collect_subtask_data(self, agent, subtask) -> None:
        """Extract and compress execution data from a completed subtask.

        Args:
            agent: AMIAgent instance with conversation history.
            subtask: AMISubtask that just completed.
        """
        messages = agent.get_messages()
        tool_records = self._extract_tool_records(messages)

        subtask_id = subtask.id

        # Truncate result summary
        result_summary = ""
        if subtask.result:
            result_summary = subtask.result[:500]

        data = SubtaskExecutionData(
            subtask_id=subtask_id,
            content=subtask.content,
            agent_type=subtask.agent_type,
            depends_on=subtask.depends_on,
            state=subtask.state.value,
            result_summary=result_summary,
            tool_records=tool_records,
        )
        self._subtask_data.append(data)

        logger.info(
            f"[ExecutionDataCollector] Collected {len(tool_records)} tool records "
            f"for subtask {subtask_id}"
        )

    def build_task_data(
        self,
        task_id: str,
        user_request: str,
        subtasks: list,
    ) -> TaskExecutionData:
        """Build complete TaskExecutionData from collected subtask data.

        Args:
            task_id: Task ID.
            user_request: User's original request.
            subtasks: List of AMISubtask objects (for counting).

        Returns:
            TaskExecutionData ready for LearnerAgent.
        """
        completed = sum(1 for s in subtasks if s.state.value == "DONE")
        failed = sum(1 for s in subtasks if s.state.value == "FAILED")

        return TaskExecutionData(
            task_id=task_id,
            user_request=user_request,
            subtasks=self._subtask_data,
            completed_count=completed,
            failed_count=failed,
            total_count=len(subtasks),
        )

    def _extract_tool_records(
        self, messages: List[Dict[str, Any]]
    ) -> List[ToolUseRecord]:
        """Parse Anthropic-format messages to extract tool use records.

        Message structure:
        - assistant message: [text_block, tool_use_block, ...]
        - user message: [tool_result_block, ...]
        - assistant message: [text_block (judgment), ...]

        The thinking is the text block BEFORE tool_use in the same assistant msg.
        The judgment is the text block in the NEXT assistant msg after tool_result.
        """
        records = []

        # First pass: collect tool_use blocks with their thinking
        tool_uses = []  # [(tool_use_block, thinking_text)]
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue

            # Collect text blocks and tool_use blocks in order
            current_text = ""
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    current_text = block.get("text", "")
                elif block.get("type") == "tool_use":
                    tool_name = block.get("name", "")
                    if tool_name in _SKIP_TOOLS:
                        continue
                    tool_uses.append({
                        "id": block.get("id", ""),
                        "name": tool_name,
                        "input": block.get("input", {}),
                        "thinking": current_text,
                    })
                    current_text = ""  # Reset for next tool

        # Second pass: collect tool_result blocks
        tool_results: Dict[str, Dict[str, Any]] = {}  # tool_use_id -> result info
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    tool_use_id = block.get("tool_use_id", "")
                    is_error = block.get("is_error", False)
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        # Extract text from content blocks
                        texts = []
                        for rb in result_content:
                            if isinstance(rb, dict) and rb.get("type") == "text":
                                texts.append(rb.get("text", ""))
                        result_content = "\n".join(texts)
                    tool_results[tool_use_id] = {
                        "content": str(result_content),
                        "is_error": is_error,
                    }

        # Third pass: collect judgment (text after tool_result)
        judgments: Dict[str, str] = {}  # tool_use_id -> judgment text
        # Build ordered list of (msg_index, tool_use_id) for tool results
        result_locations = []
        for i, msg in enumerate(messages):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    result_locations.append((i, block.get("tool_use_id", "")))

        for msg_idx, tool_use_id in result_locations:
            # Find next assistant message after this tool_result
            for j in range(msg_idx + 1, len(messages)):
                if messages[j].get("role") == "assistant":
                    content = messages[j].get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                judgments[tool_use_id] = block.get("text", "")
                                break
                    break

        # Build ToolUseRecords
        for tu in tool_uses:
            tool_use_id = tu["id"]
            tool_name = tu["name"]
            tool_input = tu["input"]

            # Compress input
            input_summary = self._compress_tool_input(tool_name, tool_input)

            # Get result info
            result_info = tool_results.get(tool_use_id, {})
            result_content = result_info.get("content", "")
            is_error = result_info.get("is_error", False)

            # Extract URL from result
            current_url = self._extract_current_url(result_content)

            # Compress result summary
            result_summary = result_content[:300] if result_content else ""

            # Get judgment
            judgment = judgments.get(tool_use_id, "")

            # Truncate thinking and judgment
            thinking = tu["thinking"][:500] if tu["thinking"] else ""
            judgment = judgment[:500] if judgment else ""

            records.append(ToolUseRecord(
                thinking=thinking,
                tool_name=tool_name,
                input_summary=input_summary,
                success=not is_error,
                result_summary=result_summary,
                judgment=judgment,
                current_url=current_url,
            ))

        return records

    @staticmethod
    def _compress_tool_input(
        tool_name: str, input_dict: Any
    ) -> str:
        """Compress tool input by keeping only relevant fields.

        Args:
            tool_name: Name of the tool.
            input_dict: Raw tool input dictionary.

        Returns:
            Compressed string representation.
        """
        if not isinstance(input_dict, dict):
            return str(input_dict)[:200]

        keep_fields = _INPUT_KEEP_FIELDS.get(tool_name)
        if keep_fields is not None:
            if not keep_fields:
                return ""
            filtered = {k: v for k, v in input_dict.items() if k in keep_fields}
            return str(filtered)[:300]

        # Default: keep all fields but truncate values
        compressed = {}
        for k, v in input_dict.items():
            sv = str(v)
            compressed[k] = sv[:100] if len(sv) > 100 else sv
        return str(compressed)[:300]

    @staticmethod
    def _extract_current_url(tool_result_text: str) -> str:
        """Extract URL from tool result text.

        Handles two formats from browser toolkit:
        - "- URL: https://..." (snapshot header)
        - "**URL:** https://..." (action result page context)

        Args:
            tool_result_text: Raw tool result text.

        Returns:
            Extracted URL or empty string.
        """
        if not tool_result_text:
            return ""
        # Match URL followed by http(s):// — avoids capturing markdown **
        match = re.search(r"URL:\*?\*?\s*(https?://\S+)", tool_result_text)
        if match:
            return match.group(1)
        return ""
