#!/usr/bin/env python3
"""Parse Ami task logs to show AI execution trace.

Shows: User request → LLM thinking → Tool calls → Results → Final output

Usage:
    python scripts/parse_task_log.py              # Latest task
    python scripts/parse_task_log.py --list       # List recent tasks
    python scripts/parse_task_log.py --task-id X  # Specific task
    python scripts/parse_task_log.py --full       # Show full content (not truncated)
    python scripts/parse_task_log.py --stats      # Show detailed statistics
    python scripts/parse_task_log.py -o trace.md  # Output to file
"""

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

LOG_DIR = Path.home() / ".ami" / "logs"
AMI_DIR = Path.home() / ".ami"

# Truncation limits
MAX_CONTENT_LEN = 500
MAX_TOOL_INPUT_LEN = 200
MAX_TOOL_RESULT_LEN = 300


@dataclass
class LLMCall:
    """A single LLM request-response pair."""
    timestamp: str
    agent: str  # orchestrator, browser, document, etc.

    # Request
    system_prompt_preview: str = ""
    user_message: str = ""
    tool_results_in: list = field(default_factory=list)  # Tool results sent to LLM

    # Response
    thinking: str = ""  # LLM's text response (reasoning)
    tool_calls: list = field(default_factory=list)  # Tools LLM decided to call

    # Metadata
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class ToolExecution:
    """A tool execution with input and result."""
    timestamp: str
    tool_name: str
    tool_input: dict
    result: str = ""
    success: bool = True
    duration_ms: int = 0


@dataclass
class Step:
    """A step in the execution trace."""
    step_num: int
    timestamp: str
    step_type: str  # "user_request", "orchestrator", "agent_task", "tool", "summary"
    agent: str = ""

    # Content varies by type
    content: str = ""
    thinking: str = ""
    decision: str = ""

    # For tool steps
    tool_name: str = ""
    tool_input: str = ""
    tool_result: str = ""
    tool_success: bool = True

    # For agent_task steps
    subtask_id: str = ""
    subtask_content: str = ""


@dataclass
class Subtask:
    """A subtask in the task decomposition."""
    id: str
    type: str  # browser, code, document
    content: str
    depends_on: list = field(default_factory=list)
    memory_level: str = ""  # L1, L2, L3
    memory_states: int = 0
    status: str = "pending"  # pending, running, done, failed


@dataclass
class PhaseStats:
    """Statistics for a phase of execution."""
    name: str
    start_time: str = ""
    end_time: str = ""
    duration_secs: float = 0
    llm_calls: int = 0
    tool_calls: int = 0


@dataclass
class ExecutionTrace:
    """Complete execution trace for a task."""
    task_id: str
    user_request: str = ""
    start_time: str = ""
    end_time: str = ""

    steps: list = field(default_factory=list)

    # Task decomposition
    subtasks: list = field(default_factory=list)  # List of Subtask
    coarse_decomposition_time: str = ""
    memory_query_time: str = ""

    # Memory stats
    memory_l1: int = 0
    memory_l2: int = 0
    memory_l3: int = 0

    # Phase stats
    phases: list = field(default_factory=list)  # List of PhaseStats

    # LLM call timestamps (for frequency analysis)
    llm_call_times: list = field(default_factory=list)

    # Stats
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: int = 0
    errors: int = 0
    warnings: int = 0

    # Output files
    output_files: list = field(default_factory=list)


def find_log_files() -> list[Path]:
    """Find all app.log files sorted by age (oldest first)."""
    files = []
    base = LOG_DIR / "app.log"
    for i in range(10, 0, -1):
        p = LOG_DIR / f"app.log.{i}"
        if p.exists():
            files.append(p)
    if base.exists():
        files.append(base)
    return files


def find_task_id_from_logs(log_files: list[Path]) -> Optional[str]:
    """Find the latest task ID from log files."""
    for log_file in reversed(log_files):
        last_task_id = None
        with open(log_file, "r") as f:
            for line in f:
                m = re.search(r"Task submitted.*?(\w{8})", line)
                if m:
                    last_task_id = m.group(1)
        if last_task_id:
            return last_task_id
    return None


def get_task_output_files(task_id: str) -> list[dict]:
    """Get output files from task workspace."""
    output_files = []

    # Find task workspace (search in common user directories)
    for users_dir in AMI_DIR.glob("users/*/projects/*/tasks"):
        task_dir = users_dir / task_id / "workspace"
        if task_dir.exists():
            for f in task_dir.iterdir():
                if f.is_file() and not f.name.startswith('.'):
                    output_files.append({
                        "name": f.name,
                        "size": f.stat().st_size,
                        "mtime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%H:%M:%S"),
                    })
            break

    # Sort by modification time
    output_files.sort(key=lambda x: x["mtime"])
    return output_files


def format_file_size(size: int) -> str:
    """Format file size in human readable format."""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / (1024 * 1024):.1f}MB"


@dataclass
class TaskInfo:
    """Brief info about a task."""
    task_id: str
    timestamp: str
    user_request: str = ""
    duration_secs: int = 0
    status: str = "unknown"  # running, completed, failed


def list_recent_tasks(log_files: list[Path], limit: int = 10) -> list[TaskInfo]:
    """List recent tasks from log files."""
    tasks = {}  # task_id -> TaskInfo

    for log_file in log_files:
        with open(log_file, "r") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue

                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg = entry.get("message", "")
                ts = entry.get("timestamp", "")

                # Task start
                m = re.search(r"Task submitted.*?(\w{8})", msg)
                if m:
                    task_id = m.group(1)
                    tasks[task_id] = TaskInfo(
                        task_id=task_id,
                        timestamp=ts[:19] if ts else "",
                        status="running",
                    )
                    continue

                # User request
                m = re.search(r"Running Orchestrator for: (.+)", msg)
                if m:
                    # Find the most recent task
                    for task_id in reversed(list(tasks.keys())):
                        if not tasks[task_id].user_request:
                            tasks[task_id].user_request = m.group(1)[:80]
                            break
                    continue

                # Task completion markers
                if "SSE stream cancelled" in msg:
                    # Extract task_id from message
                    m2 = re.search(r"task (\w{8})", msg)
                    if m2:
                        tid = m2.group(1)
                        if tid in tasks and tasks[tid].status == "running":
                            tasks[tid].status = "completed"
                            try:
                                start = datetime.fromisoformat(tasks[tid].timestamp.replace("T", " "))
                                end = datetime.fromisoformat(ts[:19].replace("T", " "))
                                tasks[tid].duration_secs = int((end - start).total_seconds())
                            except:
                                pass
                    continue

                if "Workforce completed" in msg or "Multi-turn session ended" in msg:
                    for task_id in reversed(list(tasks.keys())):
                        if tasks[task_id].status == "running":
                            tasks[task_id].status = "completed"
                            # Calculate duration
                            try:
                                start = datetime.fromisoformat(tasks[task_id].timestamp.replace("T", " "))
                                end = datetime.fromisoformat(ts[:19].replace("T", " "))
                                tasks[task_id].duration_secs = int((end - start).total_seconds())
                            except:
                                pass
                            break
                    continue

                # Error markers
                if entry.get("level") == "ERROR" and any(tid in msg for tid in tasks):
                    for task_id in tasks:
                        if task_id in msg and tasks[task_id].status == "running":
                            tasks[task_id].status = "failed"
                            break

    # Return most recent tasks
    task_list = list(tasks.values())
    return task_list[-limit:][::-1]  # Most recent first


def format_task_list(tasks: list[TaskInfo]) -> str:
    """Format task list for display."""
    lines = []
    lines.append("=" * 80)
    lines.append("RECENT TASKS")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"{'ID':<10} {'TIME':<20} {'STATUS':<10} {'DUR':<8} REQUEST")
    lines.append("-" * 80)

    for task in tasks:
        time_str = task.timestamp[5:16].replace("T", " ") if task.timestamp else ""
        dur_str = f"{task.duration_secs // 60}m{task.duration_secs % 60}s" if task.duration_secs else "-"
        status_icon = {
            "completed": "✅",
            "running": "🔄",
            "failed": "❌",
        }.get(task.status, "❓")
        request = truncate(task.user_request, 35) if task.user_request else "(no request captured)"
        lines.append(f"{task.task_id:<10} {time_str:<20} {status_icon:<2} {task.status:<7} {dur_str:<8} {request}")

    lines.append("")
    lines.append("Use: python scripts/parse_task_log.py --task-id <ID>")
    lines.append("=" * 80)

    return "\n".join(lines)


def truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def parse_task_logs(log_files: list[Path], task_id: str, full_content: bool = False) -> ExecutionTrace:
    """Parse logs and extract execution trace."""
    trace = ExecutionTrace(task_id=task_id)

    # Collect all relevant log entries
    entries = []
    started = False

    for log_file in log_files:
        with open(log_file, "r") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue

                # Task boundaries
                if f"Task submitted" in raw and task_id in raw:
                    started = True
                elif started and "Task submitted" in raw and task_id not in raw:
                    break

                if not started:
                    continue

                # Skip debug logs (but keep some important ones)
                if '"level": "DEBUG"' in raw and task_id not in raw:
                    continue

                try:
                    entry = json.loads(raw)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

    # Content length limits
    content_len = 10000 if full_content else MAX_CONTENT_LEN
    input_len = 10000 if full_content else MAX_TOOL_INPUT_LEN
    result_len = 10000 if full_content else MAX_TOOL_RESULT_LEN

    # Process entries to build trace
    step_num = 0
    current_agent = "orchestrator"
    current_phase = None
    pending_tool_calls = []  # Track tool calls waiting for results

    for entry in entries:
        ts = entry.get("timestamp", "")[:19]  # Trim to seconds
        msg = entry.get("message", "")
        level = entry.get("level", "")

        # Track timestamps
        if not trace.start_time and ts:
            trace.start_time = ts
        if ts:
            trace.end_time = ts

        # === Task Decomposition (AMITaskPlanner) ===
        if "[AMITaskPlanner] Decomposing task:" in msg:
            trace.coarse_decomposition_time = ts
            if not current_phase:
                current_phase = PhaseStats(name="decomposition", start_time=ts)

        # Parse coarse decomposition result
        elif "[AMITaskPlanner] Coarse decomposition complete:" in msg:
            m = re.search(r"(\d+) subtasks \(types: ({.+})\)", msg)
            if m:
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="decomposition",
                    content=f"Task decomposed into {m.group(1)} subtasks: {m.group(2)}",
                ))

        # Parse coarse decomposition raw JSON response
        elif "[AMITaskPlanner] Coarse decompose raw response:" in msg:
            # Extract subtasks from JSON
            try:
                json_match = re.search(r'```json\s*(\{.+)', msg, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    # Find the complete JSON (may be truncated in log)
                    if '"subtasks"' in json_str:
                        # Try to parse partial JSON
                        pass  # Will be handled by LLM Response parsing
            except:
                pass

        # Parse subtask from LLM Response
        elif "[LLM Response]" in msg and '"subtasks"' in msg:
            # Extract subtasks array from response
            try:
                subtasks_match = re.search(r'"subtasks":\s*\[(.+?)\]', msg, re.DOTALL)
                if subtasks_match:
                    # Parse individual subtasks
                    subtask_pattern = r'\{"id":\s*"(\d+)",\s*"type":\s*"(\w+)",\s*"content":\s*"([^"]+)"'
                    for m in re.finditer(subtask_pattern, msg):
                        subtask = Subtask(
                            id=m.group(1),
                            type=m.group(2),
                            content=m.group(3)[:100],
                        )
                        # Avoid duplicates
                        if not any(s.id == subtask.id for s in trace.subtasks):
                            trace.subtasks.append(subtask)
            except:
                pass

        # Memory query for subtask
        elif "[AMITaskPlanner] Querying Memory for subtask" in msg:
            m = re.search(r"subtask (\d+):", msg)
            if m:
                subtask_id = m.group(1)

        # Memory query result
        elif "[AMITaskPlanner] Subtask" in msg and "match with" in msg:
            m = re.search(r"Subtask (\d+): (L\d) match with (\d+) states", msg)
            if m:
                subtask_id, level, states = m.group(1), m.group(2), int(m.group(3))
                # Update subtask
                for subtask in trace.subtasks:
                    if subtask.id == subtask_id:
                        subtask.memory_level = level
                        subtask.memory_states = states
                        break
                # Update stats
                if level == "L1":
                    trace.memory_l1 += 1
                elif level == "L2":
                    trace.memory_l2 += 1
                elif level == "L3":
                    trace.memory_l3 += 1

        # Memory query complete
        elif "[AMITaskPlanner] Memory queries complete:" in msg:
            m = re.search(r"L1=(\d+), L2=(\d+), L3=(\d+)", msg)
            if m:
                trace.memory_l1 = int(m.group(1))
                trace.memory_l2 = int(m.group(2))
                trace.memory_l3 = int(m.group(3))
                trace.memory_query_time = ts
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="memory_complete",
                    content=f"Memory queries complete: L1={m.group(1)}, L2={m.group(2)}, L3={m.group(3)}",
                ))
                if current_phase and current_phase.name == "decomposition":
                    current_phase.end_time = ts
                    trace.phases.append(current_phase)
                    current_phase = None

        # Task plan confirmed
        elif "plan confirmed with" in msg:
            m = re.search(r"plan confirmed with (\d+) subtasks", msg)
            if m:
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="plan_confirmed",
                    content=f"Plan confirmed with {m.group(1)} subtasks",
                ))

        # === Track LLM calls for frequency analysis ===
        elif "[LLM Request]" in msg or "[LLM Response]" in msg:
            trace.llm_call_times.append(ts)

        # === Replan task (dynamic adjustment) ===
        elif "replan_task" in msg and "new_subtasks" in msg:
            m = re.search(r'reason["\']:\s*["\']([^"\']+)', msg)
            reason = m.group(1) if m else "Dynamic replanning"
            step_num += 1
            trace.steps.append(Step(
                step_num=step_num,
                timestamp=ts,
                step_type="replan",
                content=f"Replan: {truncate(reason, content_len)}",
            ))

        # === User Request ===
        elif "Running Orchestrator for:" in msg:
            m = re.search(r"Running Orchestrator for: (.+)", msg)
            if m:
                trace.user_request = m.group(1)
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="user_request",
                    content=truncate(trace.user_request, content_len),
                ))

        # === decompose_task triggered ===
        elif "decompose_task triggered" in msg:
            step_num += 1
            trace.steps.append(Step(
                step_num=step_num,
                timestamp=ts,
                step_type="decompose",
                agent="orchestrator",
                content="Task decomposed, starting agent execution",
            ))

        # === Orchestrator Response ===
        elif "Orchestrator response:" in msg:
            m = re.search(r"Orchestrator response: (.+)", msg)
            if m:
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="orchestrator_response",
                    agent="orchestrator",
                    content=truncate(m.group(1), content_len),
                ))

        # === Agent Task Start ===
        elif "[ListenBrowserAgent] Starting task:" in msg:
            m = re.search(r"Starting task: (.+)", msg)
            if m:
                current_agent = "browser"
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="agent_task",
                    agent="browser",
                    subtask_content=truncate(m.group(1), content_len),
                ))

        # === LLM Thinking/Reasoning ===
        elif "[LLM Reasoning]" in msg:
            m = re.search(r"\[LLM Reasoning\] (.+)", msg)
            if m:
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="thinking",
                    agent=current_agent,
                    thinking=truncate(m.group(1), content_len),
                ))

        # === LLM Response with Tool Call ===
        elif "[LLM Response] Block" in msg and "tool_use:" in msg:
            m = re.search(r"tool_use: (\w+)\((.+)\)", msg)
            if m:
                tool_name = m.group(1)
                tool_input = m.group(2)
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="llm_tool_decision",
                    agent=current_agent,
                    tool_name=tool_name,
                    tool_input=truncate(tool_input, input_len),
                ))
                pending_tool_calls.append(tool_name)
                trace.tool_calls += 1

        # === LLM Response with Text ===
        elif "[LLM Response] Block" in msg and "text:" in msg:
            m = re.search(r"text: (.+)", msg)
            if m:
                text = m.group(1)
                # Only add if substantial content
                if len(text) > 20 and not text.startswith("```json"):
                    step_num += 1
                    trace.steps.append(Step(
                        step_num=step_num,
                        timestamp=ts,
                        step_type="llm_response",
                        agent=current_agent,
                        content=truncate(text, content_len),
                    ))

        # === Tool Call (from agent) ===
        elif "[Tool Call]" in msg:
            m = re.search(r"\[Tool Call\] (\w+): (.+)", msg)
            if m:
                tool_name = m.group(1)
                try:
                    tool_input = json.loads(m.group(2))
                    tool_input_str = json.dumps(tool_input, ensure_ascii=False)
                except:
                    tool_input_str = m.group(2)
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="tool_call",
                    agent=current_agent,
                    tool_name=tool_name,
                    tool_input=truncate(tool_input_str, input_len),
                ))
                trace.tool_calls += 1

        # === Tool Results (in LLM request) ===
        elif "[LLM Request]" in msg and "tool_result" in msg:
            # Extract tool results being sent to LLM
            m = re.search(r"'content': ['\"](.+?)['\"]", msg)
            if m:
                result_preview = m.group(1)
                # Find matching tool call
                if trace.steps and trace.steps[-1].step_type in ("tool_call", "llm_tool_decision"):
                    trace.steps[-1].tool_result = truncate(result_preview, result_len)

        # === Browser Events ===
        elif "Browser session initialized" in msg:
            step_num += 1
            trace.steps.append(Step(
                step_num=step_num,
                timestamp=ts,
                step_type="browser_event",
                agent="browser",
                content="Browser session initialized",
            ))

        elif "Navigated to" in msg:
            m = re.search(r"Navigated to (https?://[^\s]+)", msg)
            if m:
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="browser_event",
                    agent="browser",
                    content=f"Navigated to: {truncate(m.group(1), 100)}",
                ))

        # === Search Results ===
        elif "DuckDuckGo" in msg and "returned" in msg:
            m = re.search(r"DuckDuckGo.*search for '(.+?)' returned (\d+) results", msg)
            if m:
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="search",
                    agent=current_agent,
                    content=f"Search: '{m.group(1)}' → {m.group(2)} results",
                ))

        # === Notes ===
        elif "Note created:" in msg:
            m = re.search(r"Note created: (\w+)", msg)
            if m:
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="note",
                    agent=current_agent,
                    content=f"Created note: {m.group(1)}",
                ))

        # === Memory ===
        elif "[Memory] Task query:" in msg:
            m = re.search(r"\[Memory\] Task query: (.+)", msg)
            if m:
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="memory_query",
                    content=truncate(m.group(1), content_len),
                ))

        elif "[Memory] Found" in msg:
            m = re.search(r"\[Memory\] Found (.+)", msg)
            if m:
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="memory_result",
                    content=m.group(1),
                ))

        # === Token Usage ===
        elif "Token usage:" in msg:
            m = re.search(r"in=(\d+), out=(\d+)", msg)
            if m:
                trace.tokens_in += int(m.group(1))
                trace.tokens_out += int(m.group(2))
                trace.llm_calls += 1

        # === Errors and Warnings ===
        elif level == "ERROR":
            step_num += 1
            trace.steps.append(Step(
                step_num=step_num,
                timestamp=ts,
                step_type="error",
                content=truncate(msg, content_len),
            ))
            trace.errors += 1

        elif level == "WARNING":
            # Only include important warnings
            if any(kw in msg for kw in ["Invalid", "Failed", "Error", "timeout"]):
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="warning",
                    content=truncate(msg, content_len),
                ))
                trace.warnings += 1

        # === Subtask Completion (from LLM calling complete_subtask tool) ===
        elif "[LLM Response]" in msg and "complete_subtask" in msg:
            # Extract from: [LLM Response] Block X tool_use: complete_subtask({"subtask_id": "1.1", ...})
            m = re.search(r'complete_subtask\(\{["\']subtask_id["\']: ["\']([^"\']+)["\']', msg)
            if m:
                subtask_id = m.group(1)
                # Deduplicate
                if not any(s.step_type == "subtask_done" and s.subtask_id == subtask_id
                          for s in trace.steps[-10:]):
                    step_num += 1
                    trace.steps.append(Step(
                        step_num=step_num,
                        timestamp=ts,
                        step_type="subtask_done",
                        subtask_id=subtask_id,
                        content="Subtask completed",
                    ))

        # === Subtask Completion (from tool_result in LLM request) ===
        # Match tool_result with "Subtask 'X' completed" - this is the actual completion event
        elif "tool_result" in msg and "Subtask" in msg and "completed" in msg:
            # Extract from tool_result content: "Subtask '1.1' completed"
            m = re.search(r"Subtask '?([\d.]+)'? completed", msg)
            if m:
                subtask_id = m.group(1)
                # Deduplicate: only add if not already added for this subtask
                if not any(s.step_type == "subtask_done" and s.subtask_id == subtask_id
                          for s in trace.steps[-5:]):  # Check last 5 steps
                    step_num += 1
                    trace.steps.append(Step(
                        step_num=step_num,
                        timestamp=ts,
                        step_type="subtask_done",
                        subtask_id=subtask_id,
                        content="Subtask completed",
                    ))

        # === Agent Completion ===
        elif "completed, tokens=" in msg:
            m = re.search(r"(\w+) completed", msg)
            if m:
                step_num += 1
                trace.steps.append(Step(
                    step_num=step_num,
                    timestamp=ts,
                    step_type="agent_done",
                    agent=m.group(1).replace("_agent", ""),
                    content="Agent completed",
                ))

    return trace


def format_trace(trace: ExecutionTrace, show_stats: bool = False) -> str:
    """Format trace as readable output."""
    lines = []

    # Header
    lines.append("=" * 80)
    lines.append(f"TASK EXECUTION TRACE: {trace.task_id}")
    lines.append("-" * 80)

    # Stats
    duration = ""
    duration_secs = 0
    if trace.start_time and trace.end_time:
        try:
            t0 = datetime.fromisoformat(trace.start_time.replace("T", " "))
            t1 = datetime.fromisoformat(trace.end_time.replace("T", " "))
            duration_secs = (t1 - t0).total_seconds()
            duration = f"{int(duration_secs // 60)}m{int(duration_secs % 60)}s"
        except:
            pass

    lines.append(f"Duration: {duration}  |  LLM calls: {trace.llm_calls}  |  "
                 f"Tokens: {trace.tokens_in:,} in / {trace.tokens_out:,} out")
    lines.append(f"Tool calls: {trace.tool_calls}  |  Errors: {trace.errors}  |  Warnings: {trace.warnings}")

    # Memory stats
    if trace.memory_l1 or trace.memory_l2 or trace.memory_l3:
        lines.append(f"Memory: L1={trace.memory_l1} (exact), L2={trace.memory_l2} (partial), L3={trace.memory_l3} (none)")

    lines.append("=" * 80)
    lines.append("")

    # User request
    if trace.user_request:
        lines.append("📋 USER REQUEST:")
        lines.append(f"   {trace.user_request}")
        lines.append("")

    # Task decomposition
    if trace.subtasks:
        lines.append("📊 TASK DECOMPOSITION:")
        lines.append("-" * 40)
        for subtask in trace.subtasks:
            memory_info = ""
            if subtask.memory_level:
                memory_info = f" [{subtask.memory_level}, {subtask.memory_states} states]"
            status_icon = {
                "pending": "⏳",
                "running": "🔄",
                "done": "✅",
                "failed": "❌",
            }.get(subtask.status, "❓")
            lines.append(f"  {status_icon} [{subtask.id}] ({subtask.type}) {subtask.content}{memory_info}")
        lines.append("")

    # LLM call frequency analysis
    if show_stats and trace.llm_call_times:
        lines.append("📈 LLM CALL FREQUENCY:")
        lines.append("-" * 40)

        # Calculate intervals
        intervals = []
        for i in range(1, len(trace.llm_call_times)):
            try:
                t0 = datetime.fromisoformat(trace.llm_call_times[i-1].replace("T", " "))
                t1 = datetime.fromisoformat(trace.llm_call_times[i].replace("T", " "))
                intervals.append((t1 - t0).total_seconds())
            except:
                pass

        if intervals:
            avg_interval = sum(intervals) / len(intervals)
            min_interval = min(intervals)
            max_interval = max(intervals)
            lines.append(f"  Total LLM calls: {len(trace.llm_call_times)}")
            lines.append(f"  Average interval: {avg_interval:.1f}s")
            lines.append(f"  Min/Max interval: {min_interval:.1f}s / {max_interval:.1f}s")

            # Calls per minute
            if duration_secs > 0:
                calls_per_min = len(trace.llm_call_times) / (duration_secs / 60)
                lines.append(f"  Calls per minute: {calls_per_min:.1f}")
        lines.append("")

    # Output files
    output_files = get_task_output_files(trace.task_id)
    if output_files:
        lines.append("📁 OUTPUT FILES:")
        lines.append("-" * 40)
        total_size = 0
        for f in output_files:
            total_size += f["size"]
            lines.append(f"  [{f['mtime']}] {f['name']:<40} {format_file_size(f['size']):>10}")
        lines.append(f"  {'─' * 50}")
        lines.append(f"  Total: {len(output_files)} files, {format_file_size(total_size)}")
        lines.append("")

    # Steps
    current_agent = ""
    for step in trace.steps:
        ts = step.timestamp[11:19] if len(step.timestamp) >= 19 else step.timestamp

        # Agent header
        if step.agent and step.agent != current_agent:
            current_agent = step.agent
            lines.append("")
            lines.append(f"{'─' * 40}")
            agent_label = {
                "orchestrator": "🎯 ORCHESTRATOR",
                "browser": "🌐 BROWSER AGENT",
                "document": "📄 DOCUMENT AGENT",
                "code": "💻 CODE AGENT",
            }.get(current_agent, f"🤖 {current_agent.upper()}")
            lines.append(f"{agent_label}")
            lines.append(f"{'─' * 40}")

        # Format by step type
        if step.step_type == "user_request":
            continue  # Already shown above

        elif step.step_type == "decomposition":
            lines.append(f"[{ts}] 📊 {step.content}")

        elif step.step_type == "memory_complete":
            lines.append(f"[{ts}] 🧠 {step.content}")

        elif step.step_type == "plan_confirmed":
            lines.append(f"[{ts}] ✅ {step.content}")

        elif step.step_type == "replan":
            lines.append(f"[{ts}] 🔄 {step.content}")

        elif step.step_type == "decompose":
            lines.append(f"[{ts}] 🔀 {step.content}")

        elif step.step_type == "orchestrator_response":
            lines.append(f"[{ts}] 💬 Response: {step.content}")

        elif step.step_type == "agent_task":
            lines.append(f"[{ts}] 📌 Task: {step.subtask_content}")

        elif step.step_type == "thinking":
            lines.append(f"[{ts}] 💭 Thinking: {step.thinking}")

        elif step.step_type == "llm_tool_decision":
            lines.append(f"[{ts}] 🔧 Decides to call: {step.tool_name}")
            if step.tool_input:
                lines.append(f"         Input: {step.tool_input}")

        elif step.step_type == "llm_response":
            lines.append(f"[{ts}] 💬 Says: {step.content}")

        elif step.step_type == "tool_call":
            lines.append(f"[{ts}] ▶️  {step.tool_name}")
            if step.tool_input:
                lines.append(f"         Input: {step.tool_input}")
            if step.tool_result:
                lines.append(f"         Result: {step.tool_result}")

        elif step.step_type == "browser_event":
            lines.append(f"[{ts}] 🌐 {step.content}")

        elif step.step_type == "search":
            lines.append(f"[{ts}] 🔍 {step.content}")

        elif step.step_type == "note":
            lines.append(f"[{ts}] 📝 {step.content}")

        elif step.step_type == "memory_query":
            lines.append(f"[{ts}] 🧠 Memory query: {step.content}")

        elif step.step_type == "memory_result":
            lines.append(f"[{ts}] 🧠 Memory found: {step.content}")

        elif step.step_type == "subtask_done":
            lines.append(f"[{ts}] ✅ Subtask {step.subtask_id} completed")

        elif step.step_type == "agent_done":
            lines.append(f"[{ts}] ✅ {step.agent} agent completed")

        elif step.step_type == "error":
            lines.append(f"[{ts}] ❌ ERROR: {step.content}")

        elif step.step_type == "warning":
            lines.append(f"[{ts}] ⚠️  WARNING: {step.content}")

    lines.append("")
    lines.append("=" * 80)

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parse Ami task execution trace")
    parser.add_argument("--task-id", type=str, help="Task ID (default: latest)")
    parser.add_argument("--list", "-l", action="store_true", help="List recent tasks")
    parser.add_argument("-o", "--output", type=Path, help="Output file")
    parser.add_argument("--full", action="store_true", help="Show full content (no truncation)")
    parser.add_argument("--stats", "-s", action="store_true", help="Show detailed statistics (LLM frequency, etc.)")
    args = parser.parse_args()

    log_files = find_log_files()
    if not log_files:
        print("No log files found in ~/.ami/logs/", file=sys.stderr)
        sys.exit(1)

    # List mode
    if args.list:
        tasks = list_recent_tasks(log_files)
        if not tasks:
            print("No tasks found in logs", file=sys.stderr)
            sys.exit(1)
        print(format_task_list(tasks))
        return

    task_id = args.task_id
    if not task_id:
        task_id = find_task_id_from_logs(log_files)
        if not task_id:
            print("No task found in logs. Use --list to see available tasks.", file=sys.stderr)
            sys.exit(1)
        print(f"Auto-detected task: {task_id}", file=sys.stderr)

    trace = parse_task_logs(log_files, task_id, full_content=args.full)
    output = format_trace(trace, show_stats=args.stats)

    if args.output:
        args.output.write_text(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
