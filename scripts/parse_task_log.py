#!/usr/bin/env python3
"""Parse Ami task logs to show AI execution trace.

Shows: User request → Decomposition → Memory → Subtask execution → Tool calls → Summary

Usage:
    python scripts/parse_task_log.py              # Latest task
    python scripts/parse_task_log.py --list       # List recent tasks
    python scripts/parse_task_log.py --task-id X  # Specific task
    python scripts/parse_task_log.py --full       # Show full content (not truncated)
    python scripts/parse_task_log.py -v           # Verbose: include all LLM responses
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
TRUNC_SHORT = 120
TRUNC_MEDIUM = 300
TRUNC_LONG = 800


def truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    text = text.strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def find_log_files() -> list:
    files = []
    for i in range(10, 0, -1):
        p = LOG_DIR / f"app.log.{i}"
        if p.exists():
            files.append(p)
    base = LOG_DIR / "app.log"
    if base.exists():
        files.append(base)
    return files


def find_task_id_from_logs(log_files) -> Optional[str]:
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


@dataclass
class TaskInfo:
    task_id: str
    timestamp: str
    user_request: str = ""
    duration_secs: int = 0
    status: str = "unknown"


def list_recent_tasks(log_files, limit=10):
    tasks = {}
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

                m = re.search(r"Task submitted.*?(\w{8})", msg)
                if m:
                    task_id = m.group(1)
                    tasks[task_id] = TaskInfo(
                        task_id=task_id,
                        timestamp=ts[:19] if ts else "",
                        status="running",
                    )
                    continue

                m = re.search(r"Running Orchestrator for: (.+)", msg)
                if m:
                    for task_id in reversed(list(tasks.keys())):
                        if not tasks[task_id].user_request:
                            tasks[task_id].user_request = m.group(1)[:80]
                            break
                    continue

                if "SSE stream cancelled" in msg or "Multi-turn session ended" in msg:
                    m2 = re.search(r"task (\w{8})", msg)
                    tid = m2.group(1) if m2 else None
                    if tid and tid in tasks:
                        tasks[tid].status = "completed"
                    elif not tid:
                        for task_id in reversed(list(tasks.keys())):
                            if tasks[task_id].status == "running":
                                tasks[task_id].status = "completed"
                                break

    task_list = list(tasks.values())
    return task_list[-limit:][::-1]


def format_task_list(tasks):
    lines = ["", "RECENT TASKS", "=" * 80, ""]
    lines.append(f"{'ID':<10} {'TIME':<20} {'STATUS':<12} REQUEST")
    lines.append("-" * 80)
    for task in tasks:
        time_str = task.timestamp[5:16].replace("T", " ") if task.timestamp else ""
        status_icon = {"completed": "[done]", "running": "[run]", "failed": "[fail]"}.get(task.status, "[?]")
        request = truncate(task.user_request, 45) if task.user_request else "(no request)"
        lines.append(f"{task.task_id:<10} {time_str:<20} {status_icon:<12} {request}")
    lines.append("")
    lines.append("Usage: python scripts/parse_task_log.py --task-id <ID>")
    lines.append("=" * 80)
    return "\n".join(lines)


# ─── Trace data structures ────────────────────────────────────────────────────

@dataclass
class Event:
    """A single event in the execution trace."""
    timestamp: str  # HH:MM:SS
    event_type: str
    content: str
    agent: str = ""
    subtask_id: str = ""
    extra: str = ""  # additional detail line


@dataclass
class SubtaskInfo:
    id: str
    agent_type: str
    content: str
    depends_on: list = field(default_factory=list)
    memory_level: str = ""
    status: str = "pending"


@dataclass
class Trace:
    task_id: str
    user_request: str = ""
    start_time: str = ""
    end_time: str = ""

    # Decomposition
    subtasks: list = field(default_factory=list)  # List[SubtaskInfo]
    memory_level: str = ""
    memory_detail: str = ""

    # Timeline events
    events: list = field(default_factory=list)  # List[Event]

    # Stats
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    errors: int = 0


def get_task_output_files(task_id: str) -> list:
    output_files = []
    for users_dir in AMI_DIR.glob("users/*/projects/*/tasks"):
        task_dir = users_dir / task_id / "workspace"
        if task_dir.exists():
            for f in task_dir.iterdir():
                if f.is_file() and not f.name.startswith('.'):
                    size = f.stat().st_size
                    if size < 1024:
                        sz = f"{size}B"
                    elif size < 1024 * 1024:
                        sz = f"{size / 1024:.1f}KB"
                    else:
                        sz = f"{size / (1024 * 1024):.1f}MB"
                    output_files.append({"name": f.name, "size": sz})
            break
    return output_files


def parse_task_logs(log_files, task_id: str, full: bool = False, verbose: bool = False) -> Trace:
    trace = Trace(task_id=task_id)
    tl = TRUNC_LONG if full else TRUNC_MEDIUM
    ts_short = TRUNC_MEDIUM if full else TRUNC_SHORT

    # Collect all entries for this task
    entries = []
    started = False
    for log_file in log_files:
        with open(log_file, "r") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                if f"Task submitted" in raw and task_id in raw:
                    started = True
                elif started and "Task submitted" in raw and task_id not in raw:
                    break
                if not started:
                    continue
                try:
                    entries.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue

    current_subtask_id = ""
    current_agent = "orchestrator"  # Starts with orchestrator

    for entry in entries:
        ts_raw = entry.get("timestamp", "")
        ts = ts_raw[11:19] if len(ts_raw) >= 19 else ts_raw  # HH:MM:SS
        msg = entry.get("message", "")
        level = entry.get("level", "")
        module = entry.get("module", "")

        if not trace.start_time and ts:
            trace.start_time = ts
        if ts:
            trace.end_time = ts

        # ─── User Request ─────────────────────────────────────────────
        m = re.search(r"Running Orchestrator for: (.+)", msg)
        if m:
            trace.user_request = m.group(1)
            trace.events.append(Event(ts, "user_request", truncate(m.group(1), tl)))
            continue

        # ─── Orchestrator Decision ────────────────────────────────────
        if "Orchestrator response:" in msg:
            m = re.search(r"Orchestrator response: (.+?)(\.\.\.|$)", msg)
            if m:
                trace.events.append(Event(ts, "orchestrator", truncate(m.group(1), ts_short), agent="orchestrator"))
            continue

        if "decompose_task triggered" in msg:
            trace.events.append(Event(ts, "decompose_start", "Orchestrator decided: decompose_task", agent="orchestrator"))
            continue

        # ─── Memory Query ─────────────────────────────────────────────
        if "[AMITaskPlanner] Querying Memory for whole task:" in msg:
            m = re.search(r"Querying Memory for whole task: (.+)", msg)
            query_text = truncate(m.group(1), ts_short) if m else ""
            trace.events.append(Event(ts, "memory_query", f"Memory query: {query_text}"))
            continue

        if "[AMITaskPlanner] Memory L1 match:" in msg:
            trace.memory_level = "L1"
            trace.memory_detail = msg.split("Memory L1 match: ")[-1]
            trace.events.append(Event(ts, "memory_result", f"Memory L1 (exact): {trace.memory_detail}"))
            continue

        if "[AMITaskPlanner] Memory L2 match:" in msg:
            trace.memory_level = "L2"
            trace.memory_detail = msg.split("Memory L2 match: ")[-1]
            trace.events.append(Event(ts, "memory_result", f"Memory L2 (composed): {trace.memory_detail}"))
            continue

        if "[AMITaskPlanner] Memory L3:" in msg:
            trace.memory_level = "L3"
            trace.events.append(Event(ts, "memory_result", "Memory L3: no match"))
            continue

        # Memory context content
        if "[AMITaskPlanner] Memory context for decompose:" in msg:
            m = re.search(r"Memory context for decompose: (.+)", msg)
            if m:
                trace.events.append(Event(ts, "memory_result", f"Memory context: {truncate(m.group(1), tl)}"))
            continue

        # Workflow guide assigned
        if "[AMITaskPlanner] Assigned" in msg and "workflow_guide" in msg:
            m = re.search(r"Assigned (\S+) workflow_guide \((\d+) chars\) to (\d+)/(\d+) browser subtasks: (.+)", msg)
            if m:
                trace.events.append(Event(
                    ts, "memory_result",
                    f"Workflow guide ({m.group(1)}, {m.group(2)} chars) -> {m.group(3)}/{m.group(4)} browser subtasks",
                    extra=truncate(m.group(5), ts_short),
                ))
            continue

        # ─── Task Decomposition Result ────────────────────────────────
        if "[AMITaskPlanner] Subtask" in msg and re.search(r"Subtask \d+ \(", msg):
            m = re.search(r"Subtask (\d+) \((\w+)\): (.+)", msg)
            if m:
                st = SubtaskInfo(
                    id=m.group(1),
                    agent_type=m.group(2),
                    content=m.group(3).split(" depends_on=")[0].split(" guide=")[0].strip(),
                )
                deps_m = re.search(r"depends_on=\[([^\]]*)\]", msg)
                if deps_m and deps_m.group(1):
                    st.depends_on = [d.strip().strip("'\"") for d in deps_m.group(1).split(",")]
                guide_m = re.search(r"guide=(L\d)", msg)
                if guide_m:
                    st.memory_level = guide_m.group(1)
                if not any(s.id == st.id for s in trace.subtasks):
                    trace.subtasks.append(st)
            continue

        # Also parse from AMITaskExecutor subtask listing
        if "[AMITaskExecutor] Subtask" in msg and re.search(r"Subtask \d+ \(", msg):
            m = re.search(r"Subtask (\d+) \((\w+)\): (.+)", msg)
            if m:
                st = SubtaskInfo(
                    id=m.group(1),
                    agent_type=m.group(2),
                    content=m.group(3).split(" depends_on=")[0].split(" guide=")[0].strip(),
                )
                deps_m = re.search(r"depends_on=\[([^\]]*)\]", msg)
                if deps_m and deps_m.group(1):
                    st.depends_on = [d.strip().strip("'\"") for d in deps_m.group(1).split(",")]
                guide_m = re.search(r"guide=(L\d)", msg)
                if guide_m:
                    st.memory_level = guide_m.group(1)
                if not any(s.id == st.id for s in trace.subtasks):
                    trace.subtasks.append(st)
            continue

        if "Fine-grained decomposition complete:" in msg:
            m = re.search(r"(\d+) subtasks \(types: ({.+})\)", msg)
            if m:
                trace.events.append(Event(ts, "decompose_done", f"Decomposed into {m.group(1)} subtasks: {m.group(2)}"))
            continue

        # ─── Subtask Execution Start ──────────────────────────────────
        if "[AMITaskExecutor] Executing subtask" in msg:
            m = re.search(r"Executing subtask (\S+)\s*\(attempt (\d+)", msg)
            if m:
                current_subtask_id = m.group(1)
                current_agent = "browser"  # Subtask execution = agent mode
                attempt = m.group(2)
                # Find subtask content and agent type
                st_content = ""
                for st in trace.subtasks:
                    if st.id == current_subtask_id:
                        st_content = st.content
                        st.status = "running"
                        current_agent = st.agent_type
                        break
                trace.events.append(Event(
                    ts, "subtask_start",
                    f"Subtask {current_subtask_id} (attempt {attempt}): {truncate(st_content, ts_short)}",
                    subtask_id=current_subtask_id,
                ))
            continue

        # ─── Subtask Completion ───────────────────────────────────────
        if "[AMITaskExecutor] Subtask" in msg and "completed" in msg:
            m = re.search(r"Subtask (\S+) completed(?:: (.+))?", msg)
            if m:
                sid = m.group(1)
                result = truncate(m.group(2) or "", ts_short)
                for st in trace.subtasks:
                    if st.id == sid:
                        st.status = "done"
                        break
                trace.events.append(Event(
                    ts, "subtask_done",
                    f"Subtask {sid} DONE",
                    subtask_id=sid,
                    extra=result if result else "",
                ))
            continue

        if "[AMITaskExecutor] Subtask" in msg and "failed" in msg:
            m = re.search(r"Subtask (\S+) failed", msg)
            if m:
                sid = m.group(1)
                for st in trace.subtasks:
                    if st.id == sid:
                        st.status = "failed"
                        break
                trace.events.append(Event(ts, "subtask_failed", f"Subtask {sid} FAILED", subtask_id=sid))
            continue

        # ─── Execution finished ───────────────────────────────────────
        if "[AMITaskExecutor] Execution finished:" in msg:
            m = re.search(r"Execution finished: (.+)", msg)
            if m:
                trace.events.append(Event(ts, "execution_done", f"Execution result: {m.group(1)}"))
            continue

        # ─── LLM Thinking (text response) ─────────────────────────────
        if "[LLM Response] Block" in msg and "text:" in msg:
            m = re.search(r"Block \d+ text: (.+)", msg)
            if m:
                text = m.group(1)
                if len(text) > 15 and not text.startswith("```json"):
                    trace.events.append(Event(
                        ts, "llm_thinks",
                        truncate(text, tl),
                        agent=current_agent,
                        subtask_id=current_subtask_id,
                    ))
            continue

        # ─── LLM Tool Call Decision ───────────────────────────────────
        if "[LLM Response] Block" in msg and "tool_use:" in msg:
            m = re.search(r"tool_use: (\w+)\((.+)\)", msg)
            if m:
                tool_name = m.group(1)
                tool_input = m.group(2)
                # Simplify common tool inputs
                input_display = truncate(tool_input, ts_short)
                trace.events.append(Event(
                    ts, "llm_calls_tool",
                    f"{tool_name}",
                    agent=current_agent,
                    subtask_id=current_subtask_id,
                    extra=input_display,
                ))
            continue

        # ─── Context Summarization (CAMEL) ────────────────────────────
        if "Triggering summarization" in msg:
            m = re.search(r"Token count \((\d+)\) exceed threshold \((\d+)\)", msg)
            if m:
                trace.events.append(Event(
                    ts, "summarization",
                    f"CONTEXT OVERFLOW: {m.group(1)} tokens > threshold {m.group(2)}, triggering summarization",
                    subtask_id=current_subtask_id,
                ))
            continue

        if "Tool 'browser" in msg and "truncated" in msg:
            m = re.search(r"Tool '(\w+)' result truncated: (\d+) -> ~(\d+) tokens", msg)
            if m:
                trace.events.append(Event(
                    ts, "truncation",
                    f"Tool {m.group(1)} result truncated: {m.group(2)} -> ~{m.group(3)} tokens",
                    subtask_id=current_subtask_id,
                ))
            continue

        # ─── Page-level Memory (runtime L2) ───────────────────────────
        if "[Memory] Found" in msg and "listen_browser" in module:
            m = re.search(r"\[Memory\] Found (.+)", msg)
            if m and verbose:
                trace.events.append(Event(
                    ts, "page_memory",
                    f"Page memory: {m.group(1)}",
                    agent="browser",
                    subtask_id=current_subtask_id,
                ))
            continue

        # ─── Browser Navigation ───────────────────────────────────────
        if "URL changed:" in msg:
            m = re.search(r"URL changed: .+ -> (.+)", msg)
            if m:
                trace.events.append(Event(
                    ts, "browser_nav",
                    f"Page: {truncate(m.group(1), 80)}",
                    agent="browser",
                    subtask_id=current_subtask_id,
                ))
            continue

        # ─── Notes ────────────────────────────────────────────────────
        if "Note created:" in msg:
            m = re.search(r"Note created: (\S+)", msg)
            if m:
                trace.events.append(Event(ts, "note", f"Note created: {m.group(1)}", subtask_id=current_subtask_id))
            continue

        # ─── Search ───────────────────────────────────────────────────
        if "search for" in msg and "returned" in msg:
            m = re.search(r"search for '(.+?)' returned (\d+) results", msg)
            if m:
                trace.events.append(Event(ts, "search", f"Search: '{m.group(1)}' -> {m.group(2)} results"))
            continue

        # ─── Agent tracking ───────────────────────────────────────────
        if "ListenChatAgent" in msg and "executing async tool:" in msg:
            m = re.search(r"\] (\w+) executing async tool: (\w+)", msg)
            if m:
                current_agent = m.group(1).replace("_agent", "")
            continue

        if "ListenBrowserAgent" in msg and "Starting" in msg:
            current_agent = "browser"
            continue

        # ─── Token usage ──────────────────────────────────────────────
        if "Token usage:" in msg:
            m = re.search(r"in=(\d+), out=(\d+)", msg)
            if m:
                trace.tokens_in += int(m.group(1))
                trace.tokens_out += int(m.group(2))
                trace.llm_calls += 1
            continue

        # ─── Task cancelled ───────────────────────────────────────────
        if "Task cancelled" in msg:
            trace.events.append(Event(ts, "cancelled", "TASK CANCELLED"))
            continue

        # ─── Errors ───────────────────────────────────────────────────
        if level == "ERROR":
            trace.events.append(Event(ts, "error", truncate(msg, tl)))
            trace.errors += 1
            continue

        # ─── Important warnings ───────────────────────────────────────
        if level == "WARNING" and any(kw in msg for kw in ["Failed", "Error", "timeout", "closed"]):
            trace.events.append(Event(ts, "warning", truncate(msg, ts_short)))
            continue

    return trace


def format_trace(trace: Trace) -> str:
    lines = []
    W = 90

    # ─── Header ───────────────────────────────────────────────────────
    lines.append("=" * W)
    lines.append(f"  TASK TRACE: {trace.task_id}")
    lines.append("=" * W)

    # Duration
    duration = ""
    if trace.start_time and trace.end_time:
        try:
            fmt = "%H:%M:%S"
            t0 = datetime.strptime(trace.start_time, fmt)
            t1 = datetime.strptime(trace.end_time, fmt)
            secs = (t1 - t0).total_seconds()
            if secs < 0:
                secs += 86400
            duration = f"{int(secs // 60)}m{int(secs % 60)}s"
        except Exception:
            pass

    lines.append(f"  Duration: {duration}  |  LLM calls: {trace.llm_calls}  |  "
                 f"Tokens: {trace.tokens_in:,} in / {trace.tokens_out:,} out  |  "
                 f"Errors: {trace.errors}")
    if trace.memory_level:
        lines.append(f"  Memory: {trace.memory_level} - {trace.memory_detail}")
    lines.append("")

    # ─── User Request ─────────────────────────────────────────────────
    if trace.user_request:
        lines.append(f"  REQUEST: {trace.user_request}")
        lines.append("")

    # ─── Subtask Plan ─────────────────────────────────────────────────
    if trace.subtasks:
        lines.append("-" * W)
        lines.append("  SUBTASK PLAN")
        lines.append("-" * W)
        for st in trace.subtasks:
            status = {"pending": "[ ]", "running": "[>]", "done": "[v]", "failed": "[x]"}.get(st.status, "[?]")
            deps = f" (after: {','.join(st.depends_on)})" if st.depends_on else ""
            mem = f" [{st.memory_level}]" if st.memory_level else ""
            lines.append(f"  {status} {st.id}. [{st.agent_type}] {st.content}{deps}{mem}")
        lines.append("")

    # ─── Output Files ─────────────────────────────────────────────────
    output_files = get_task_output_files(trace.task_id)
    if output_files:
        lines.append("-" * W)
        lines.append("  OUTPUT FILES")
        lines.append("-" * W)
        for f in output_files:
            lines.append(f"  - {f['name']} ({f['size']})")
        lines.append("")

    # ─── Timeline ─────────────────────────────────────────────────────
    lines.append("=" * W)
    lines.append("  EXECUTION TIMELINE")
    lines.append("=" * W)

    current_subtask = ""
    for ev in trace.events:
        # Subtask boundary markers
        if ev.event_type == "subtask_start" and ev.subtask_id != current_subtask:
            current_subtask = ev.subtask_id
            lines.append("")
            lines.append(f"  {'─' * (W - 4)}")
            lines.append(f"  >>> SUBTASK {ev.subtask_id}")
            lines.append(f"  {'─' * (W - 4)}")

        # Format by type
        icon = {
            "user_request":   "REQ",
            "orchestrator":   "ORC",
            "decompose_start": "DEC",
            "memory_query":   "MEM",
            "memory_result":  "MEM",
            "decompose_done": "DEC",
            "subtask_start":  ">>>",
            "subtask_done":   " OK",
            "subtask_failed": "ERR",
            "execution_done": "END",
            "llm_thinks":     "  .",
            "llm_calls_tool": " ->",
            "summarization":  "!!!",
            "truncation":     " ~~",
            "browser_nav":    "NAV",
            "page_memory":    "MEM",
            "note":           "NOT",
            "search":         "SRC",
            "cancelled":      "XXX",
            "error":          "ERR",
            "warning":        "WRN",
        }.get(ev.event_type, "   ")

        line = f"  [{ev.timestamp}] {icon}  {ev.content}"
        lines.append(line)

        if ev.extra:
            lines.append(f"               {'':>4}  {ev.extra}")

    lines.append("")
    lines.append("=" * W)

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parse Ami task execution trace")
    parser.add_argument("--task-id", type=str, help="Task ID (default: latest)")
    parser.add_argument("--list", "-l", action="store_true", help="List recent tasks")
    parser.add_argument("-o", "--output", type=Path, help="Output to file")
    parser.add_argument("--full", action="store_true", help="No truncation")
    parser.add_argument("-v", "--verbose", action="store_true", help="Include page-level memory events")
    args = parser.parse_args()

    log_files = find_log_files()
    if not log_files:
        print("No log files found in ~/.ami/logs/", file=sys.stderr)
        sys.exit(1)

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
            print("No task found. Use --list to see tasks.", file=sys.stderr)
            sys.exit(1)
        print(f"Task: {task_id}", file=sys.stderr)

    trace = parse_task_logs(log_files, task_id, full=args.full, verbose=args.verbose)
    output = format_trace(trace)

    if args.output:
        args.output.write_text(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
