#!/usr/bin/env python3
"""Parse Ami task logs and extract key events for a task execution.

Usage:
    # Auto-detect latest task from all log files
    python scripts/parse_task_log.py

    # Specify task ID
    python scripts/parse_task_log.py --task-id 80ff4669

    # Output to file
    python scripts/parse_task_log.py -o summary.txt
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

LOG_DIR = Path.home() / ".ami" / "logs"


def find_log_files() -> list[Path]:
    """Find all app.log files sorted by age (oldest first)."""
    files = []
    base = LOG_DIR / "app.log"
    # app.log.5, app.log.4, ... app.log.1, app.log (oldest to newest)
    for i in range(10, 0, -1):
        p = LOG_DIR / f"app.log.{i}"
        if p.exists():
            files.append(p)
    if base.exists():
        files.append(base)
    return files


def find_task_id_from_logs(log_files: list[Path]) -> str | None:
    """Find the latest task ID from log files (scan from newest)."""
    for log_file in reversed(log_files):
        last_task_id = None
        with open(log_file, "r") as f:
            for line in f:
                m = re.search(r"Task submitted: (\w+)", line)
                if m:
                    last_task_id = m.group(1)
        if last_task_id:
            return last_task_id
    return None


def iter_task_lines(log_files: list[Path], task_id: str):
    """Iterate log lines that belong to a specific task.

    Strategy: find "Task submitted: {task_id}" as start marker,
    then collect all lines until we see another "Task submitted:" with
    a different ID (or EOF). Non-task-tagged lines between task start
    and end are included (agent loop, LLM, tool calls share the same
    execution flow).
    """
    started = False
    for log_file in log_files:
        with open(log_file, "r") as f:
            for line_no, line in enumerate(f, 1):
                raw = line.strip()
                if not raw:
                    continue

                # Detect task boundaries
                if f"Task submitted: {task_id}" in raw:
                    started = True
                elif started and "Task submitted:" in raw and task_id not in raw:
                    # A different task started — stop
                    return

                if started:
                    yield log_file.name, line_no, raw


# What to extract
KEY_PATTERNS = [
    # Task lifecycle
    (r"Task submitted:", "TASK_INIT"),
    (r"_execute_task started", "TASK_INIT"),
    (r"TaskRouter:", "TASK_INIT"),
    (r"EigentStyleBrowserAgent initialized", "TASK_INIT"),
    (r"Initialized \d+ tools from", "TASK_INIT"),
    (r"executing task:", "TASK_START"),
    (r"Subtasks confirmed", "TASK_PLAN"),
    (r"Task decomposed into", "TASK_PLAN"),
    (r"\[LLM\] Decomposition:", "TASK_PLAN"),
    (r"Waiting for subtask confirmation", "TASK_PLAN"),
    (r"Subtask confirmation received", "TASK_PLAN"),
    (r"user-edited subtasks", "TASK_PLAN"),

    # Subtask state changes
    (r"Subtask [\d.]+ marked as", "SUBTASK_STATE"),
    (r"\[Agent Loop\] Started subtask", "SUBTASK_START"),
    (r"\[Tool Call\] complete_subtask", "SUBTASK_DONE"),
    (r"\[Tool Call\] replan_task", "REPLAN"),

    # Memory
    (r"\[Memory\] Task query:", "MEMORY"),
    (r"\[Memory\] Found (composed path|subtask plan)", "MEMORY"),
    (r"\[Memory\] path step", "MEMORY"),
    (r"\[Memory\] Navigation query:", "MEMORY"),
    (r"\[Memory\] (Found path|No navigation path)", "MEMORY"),
    (r"\[Memory\] Navigation guide saved", "MEMORY"),

    # LLM calls - only the summary token line
    (r"Token usage: in=", "TOKEN"),

    # LLM reasoning
    (r"\[LLM Reasoning\]", "THINK"),

    # Tool calls (but not complete_subtask, already captured)
    (r"\[Tool Call\] (?!complete_subtask)", "TOOL"),

    # Context management
    (r"\[Snapshot Clean\]", "CONTEXT"),
    (r"\[_call_llm\] Calling LLM with \d+ messages", "LLM_CALL"),

    # Agent loop events
    (r"\[Agent Loop\] LLM stopped but subtasks remain", "AGENT_STUCK"),
    (r"\[Agent Loop\] INITIAL MESSAGE TO LLM", "AGENT_INIT"),

    # Browser events
    (r"browser_visit_page error:", "BROWSER_ERR"),
    (r"Browser session initialized", "BROWSER"),

    # Notes
    (r"Note created:", "NOTE"),

    # Search
    (r"DuckDuckGo.*returned \d+ results", "SEARCH"),
]


def classify(entry: dict) -> str | None:
    level = entry.get("level", "")
    msg = entry.get("message", "")

    if level == "ERROR":
        return "ERROR"
    if level == "WARNING":
        return "WARNING"

    for pattern, category in KEY_PATTERNS:
        if re.search(pattern, msg):
            return category
    return None


def parse_task(log_files: list[Path], task_id: str) -> list[dict]:
    events = []
    total_in = 0
    total_out = 0
    llm_calls = 0
    errors = 0
    warnings = 0
    tool_calls = 0
    subtasks_done = 0
    first_ts = None
    last_ts = None

    for fname, line_no, raw in iter_task_lines(log_files, task_id):
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue

        cat = classify(entry)
        if cat is None:
            continue

        msg = entry.get("message", "")
        ts = entry.get("timestamp", "")

        if not first_ts and ts:
            first_ts = ts
        if ts:
            last_ts = ts

        # Stats
        if cat == "TOKEN":
            m = re.search(r"in=(\d+), out=(\d+)", msg)
            if m:
                total_in += int(m.group(1))
                total_out += int(m.group(2))
                llm_calls += 1
        if cat == "ERROR":
            errors += 1
        if cat == "WARNING":
            warnings += 1
        if cat in ("TOOL", "SUBTASK_DONE"):
            tool_calls += 1
        if cat == "SUBTASK_DONE":
            subtasks_done += 1

        display = msg[:300] + "..." if len(msg) > 300 else msg
        events.append({
            "file": fname,
            "line": line_no,
            "ts": ts,
            "level": entry.get("level", ""),
            "cat": cat,
            "msg": display,
        })

    # Duration
    duration = ""
    if first_ts and last_ts:
        try:
            t0 = datetime.fromisoformat(first_ts)
            t1 = datetime.fromisoformat(last_ts)
            secs = (t1 - t0).total_seconds()
            mins = int(secs // 60)
            secs = int(secs % 60)
            duration = f"{mins}m{secs}s"
        except Exception:
            pass

    stats = {
        "task_id": task_id,
        "duration": duration,
        "llm_calls": llm_calls,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "tool_calls": tool_calls,
        "subtasks_done": subtasks_done,
        "errors": errors,
        "warnings": warnings,
    }

    return events, stats


PREFIX = {
    "TASK_INIT":    "** INIT",
    "TASK_START":   "** START",
    "TASK_PLAN":    "** PLAN",
    "SUBTASK_STATE":">> STATE",
    "SUBTASK_START":">> SUB",
    "SUBTASK_DONE": ">> DONE",
    "REPLAN":       ">> REPLAN",
    "MEMORY":       "   MEM",
    "TOKEN":        "   TOKEN",
    "THINK":        "   THINK",
    "TOOL":         "   TOOL",
    "CONTEXT":      "   CTX",
    "LLM_CALL":     "   LLM",
    "AGENT_STUCK":  "!  STUCK",
    "AGENT_INIT":   "** AGENT",
    "BROWSER":      "   BROWSER",
    "BROWSER_ERR":  "!! BROWSER",
    "NOTE":         "   NOTE",
    "SEARCH":       "   SEARCH",
    "ERROR":        "!! ERROR",
    "WARNING":      "!  WARN",
}


def format_output(events: list[dict], stats: dict) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append(f"TASK LOG SUMMARY: {stats['task_id']}")
    lines.append(f"Duration: {stats['duration']}  |  LLM calls: {stats['llm_calls']}  |  "
                 f"Tokens: {stats['total_input_tokens']:,} in / {stats['total_output_tokens']:,} out")
    lines.append(f"Tool calls: {stats['tool_calls']}  |  Subtasks done: {stats['subtasks_done']}  |  "
                 f"Errors: {stats['errors']}  |  Warnings: {stats['warnings']}")
    lines.append("=" * 80)

    prev_cat = None
    for ev in events:
        cat = ev["cat"]
        ts = ev["ts"]
        short_ts = ts[11:19] if len(ts) >= 19 else ts

        # Separator before new subtask
        if cat == "SUBTASK_START" and prev_cat != "SUBTASK_START":
            lines.append("-" * 60)

        prefix = PREFIX.get(cat, f"   {cat[:6]}")
        lines.append(f"[{short_ts}] {prefix:>10} | {ev['msg']}")
        prev_cat = cat

    lines.append("=" * 80)
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parse Ami task logs")
    parser.add_argument("--task-id", type=str, default=None,
                        help="Task ID to extract (default: latest task)")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Output file (default: stdout)")
    args = parser.parse_args()

    log_files = find_log_files()
    if not log_files:
        print("No log files found in ~/.ami/logs/", file=sys.stderr)
        sys.exit(1)

    task_id = args.task_id
    if not task_id:
        task_id = find_task_id_from_logs(log_files)
        if not task_id:
            print("No task found in logs", file=sys.stderr)
            sys.exit(1)
        print(f"Auto-detected task: {task_id}", file=sys.stderr)

    events, stats = parse_task(log_files, task_id)
    output = format_output(events, stats)

    if args.output:
        args.output.write_text(output)
        print(f"Written to {args.output} ({len(events)} key events)", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
