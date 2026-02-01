#!/usr/bin/env python3
"""Parse Ami task logs and extract key events for a task execution.

Usage:
    # Auto-detect latest task from all log files
    python scripts/parse_task_log.py

    # Specify task ID
    python scripts/parse_task_log.py --task-id 80ff4669

    # Output to file
    python scripts/parse_task_log.py -o summary.txt

    # Verbose mode (show all events, not just key events)
    python scripts/parse_task_log.py -v
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
                # Match Workforce-style task start
                m = re.search(r"\[Task (\w+)\] Starting Orchestrator-based session", line)
                if m:
                    last_task_id = m.group(1)
                    continue
                # Match legacy format
                m = re.search(r"Task submitted(?: \(Workforce\))?: (\w+)", line)
                if m:
                    last_task_id = m.group(1)
        if last_task_id:
            return last_task_id
    return None


def iter_task_lines(log_files: list[Path], task_id: str):
    """Iterate log lines that belong to a specific task.

    Strategy: find task_id in log lines, collecting all related entries.
    """
    # Patterns that indicate task-related logs (either contain task_id or are global events during task)
    started = False
    for log_file in log_files:
        with open(log_file, "r") as f:
            for line_no, line in enumerate(f, 1):
                raw = line.strip()
                if not raw:
                    continue

                # Detect task boundaries
                if f"Task submitted" in raw and task_id in raw:
                    started = True
                elif f"Starting Orchestrator-based session" in raw and task_id in raw:
                    started = True
                elif started and "Task submitted" in raw and task_id not in raw:
                    # A different task started — stop
                    return
                elif started and "Starting Orchestrator-based session" in raw and task_id not in raw:
                    # A different task started — stop
                    return

                # Include lines that contain the task_id OR are general logs during task execution
                if started and (task_id in raw or _is_relevant_global_log(raw)):
                    # Skip noisy logs even if they contain task_id
                    if _is_noisy_log(raw):
                        continue
                    yield log_file.name, line_no, raw


def _is_noisy_log(raw: str) -> bool:
    """Check if a log line is too noisy and should be skipped."""
    # Skip debug level logs
    if '"level": "DEBUG"' in raw:
        return True
    # Skip LLM client request/response logs (contain full bodies with snapshots)
    if "Request options:" in raw:
        return True
    if "anthropic._" in raw:
        return True
    if "openai._" in raw:
        return True
    # Skip CAMEL model logs (contain full prompts)
    if '"module": "camel.camel.agents.chat_agent"' in raw:
        return True
    if '"module": "camel.agents.chat_agent"' in raw:
        return True
    if "Model glm" in raw or "Model claude" in raw:
        return True
    return False


def _is_relevant_global_log(raw: str) -> bool:
    """Check if a log line is relevant even without task_id."""
    # Skip noisy debug logs
    if '"level": "DEBUG"' in raw:
        return False
    # Skip anthropic client logs (contains full request/response bodies with snapshots)
    if "anthropic._base_client" in raw:
        return False
    if "anthropic._" in raw:
        return False
    # Skip CAMEL chat_agent model logging (contains full prompts)
    if '"module": "camel.camel.agents.chat_agent"' in raw:
        return False
    if '"module": "camel.agents.chat_agent"' in raw:
        return False
    # Skip request/response bodies
    if "Request options:" in raw:
        return False
    if "Model glm" in raw:
        return False
    if "Model claude" in raw:
        return False
    # Include Memory, Token, Tool, Browser, Workforce logs
    relevant_patterns = [
        "[Memory]",
        "Token usage:",
        "[Tool Call]",
        "browser_",
        "[AMIWorkforce]",
        "[AMISingleAgentWorker]",
        "[ListenChatAgent]",
        "DuckDuckGo",
        "Note created",
        "[LLM Reasoning]",
        "Worker node",
        "Coordinator",
        "Orchestrator",
        "decompose_task",
        "[Task ",  # Task lifecycle logs
        "[AgentFactory]",
    ]
    return any(p in raw for p in relevant_patterns)


# What to extract - updated for new Workforce log format
KEY_PATTERNS = [
    # ===== Orchestrator Phase =====
    (r"\[Task \w+\] Starting Orchestrator-based session", "ORCH_START"),
    (r"\[Task \w+\] Working directory:", "ORCH_INIT"),
    (r"\[Task \w+\] Orchestrator Agent created", "ORCH_INIT"),
    (r"\[Task \w+\] Running Orchestrator for:", "ORCH_RUN"),
    (r"\[Task \w+\] Orchestrator response:", "ORCH_REPLY"),
    (r"\[Task \w+\] Orchestrator handled directly", "ORCH_DIRECT"),
    (r"decompose_task triggered, starting Workforce", "ORCH_DECOMPOSE"),

    # ===== Workforce Initialization =====
    (r"\[AMIWorkforce\] Initializing for task_id=", "WF_INIT"),
    (r"\[AMIWorkforce\] Creating coordinator_agent", "WF_INIT"),
    (r"\[AMIWorkforce\] Creating task_agent", "WF_INIT"),
    (r"\[AMIWorkforce\] Initialization complete", "WF_INIT"),
    (r"\[Task \w+\] Creating agents\.\.\.", "WF_AGENTS"),
    (r"\[Task \w+\] Agents created: \d+/\d+ available", "WF_AGENTS"),
    (r"\[Task \w+\] MemoryToolkit created", "WF_MEMORY"),
    (r"\[Task \w+\] Added \d+ workers to Workforce", "WF_WORKERS"),
    (r"\[Task \w+\] Created new Workforce", "WF_READY"),

    # ===== Memory Integration =====
    (r"\[AMIWorkforce\] Querying memory for task:", "MEM_QUERY"),
    (r"\[AMIWorkforce\] Found subtasks with global path", "MEM_FOUND"),
    (r"\[AMIWorkforce\] Found cognitive_phrase", "MEM_FOUND"),
    (r"\[AMIWorkforce\] Found navigation path", "MEM_FOUND"),
    (r"\[AMIWorkforce\] No workflow found in memory", "MEM_MISS"),
    (r"\[AMIWorkforce\] Propagated workflow guide", "MEM_PROP"),
    (r"\[AMIWorkforce\] Workflow guide propagated to \d+ workers", "MEM_PROP"),
    (r"\[Task \w+\] Memory guidance active: level=", "MEM_LEVEL"),

    # ===== Task Decomposition =====
    (r"\[Task \w+\] Decomposing task via Workforce", "DECOMP_START"),
    (r"\[AMIWorkforce\] Decomposing task:", "DECOMP_RUN"),
    (r"\[AMIWorkforce\] Decomposed into \d+ subtasks", "DECOMP_DONE"),
    (r"\[Task \w+\] Waiting for confirmation from frontend", "DECOMP_WAIT"),
    (r"plan confirmed with \d+ subtasks", "DECOMP_CONFIRM"),
    (r"Subtasks confirmed for task \w+:", "DECOMP_CONFIRM"),

    # ===== Workforce Execution =====
    (r"\[Task \w+\] Starting Workforce execution with \d+ subtasks", "WF_EXEC_START"),
    (r"\[AMIWorkforce\] Starting execution with \d+ subtasks", "WF_EXEC_START"),
    (r"\[AMIWorkforce\] Coordinator assigned \d+ tasks:", "COORD_ASSIGN"),
    (r"  - task\.\d+ -> \w+:", "SUBTASK_ASSIGN"),
    (r"Worker node \w+ .* started", "WORKER_START"),
    (r"Response from Worker node", "WORKER_RESP"),

    # ===== Subtask Lifecycle =====
    (r"\[AMIWorkforce\] Task completed: task\.\d+", "SUBTASK_DONE"),
    (r"\[AMIWorkforce\] Task failed: task\.\d+", "SUBTASK_FAILED"),
    (r"\[AMISingleAgentWorker\] Processing task: task\.\d+", "SUBTASK_PROC"),
    (r"\[AMISingleAgentWorker\] Task task\.\d+ completed successfully", "SUBTASK_OK"),
    (r"\[AMISingleAgentWorker\] Task task\.\d+ error:", "SUBTASK_ERR"),
    (r"\[AMISingleAgentWorker\] Task task\.\d+ failed:", "SUBTASK_FAIL"),

    # ===== Workforce Completion =====
    (r"\[AMIWorkforce\] Stopping workforce", "WF_STOP"),
    (r"\[AMIWorkforce\] Worker cleanup completed", "WF_CLEANUP"),
    (r"\[AMIWorkforce\] Execution completed", "WF_DONE"),
    (r"\[Task \w+\] Generating summary for \d+ subtasks", "WF_SUMMARY"),
    (r"\[Task \w+\] Summary generated successfully", "WF_SUMMARY_OK"),
    (r"\[Task \w+\] Workforce completed, ready for multi-turn", "WF_MULTI_TURN"),
    (r"\[Task \w+\] Waiting for next user message", "WF_WAIT_USER"),
    (r"\[Task \w+\] Multi-turn session ended", "WF_SESSION_END"),

    # ===== Pause/Resume =====
    (r"\[AMIWorkforce\] Pausing workforce", "WF_PAUSE"),
    (r"\[AMIWorkforce\] Resuming workforce", "WF_RESUME"),

    # ===== Legacy patterns (for backward compatibility) =====
    (r"Task submitted \(Workforce\):", "TASK_INIT"),
    (r"Task submitted:", "TASK_INIT"),
    (r"Starting Workforce-based execution", "TASK_INIT"),
    (r"\[AgentFactory\] Creating", "TASK_INIT"),
    (r"All agents created successfully", "TASK_INIT"),
    (r"Classifying task:", "TASK_START"),
    (r"Complex task detected", "TASK_START"),
    (r"_execute_task started", "TASK_INIT"),
    (r"TaskRouter:", "TASK_INIT"),
    (r"EigentStyleBrowserAgent initialized", "TASK_INIT"),
    (r"Initialized \d+ tools from", "TASK_INIT"),
    (r"executing task:", "TASK_START"),
    (r"Subtasks confirmed", "TASK_PLAN"),
    (r"Task decomposed into", "TASK_PLAN"),
    (r"\[LLM\] Decomposition:", "TASK_PLAN"),
    (r"Waiting for subtask confirmation", "TASK_PLAN"),

    # ===== Subtask state changes (legacy) =====
    (r"Subtask [\d.]+ marked as", "SUBTASK_STATE"),
    (r"\[Agent Loop\] Started subtask", "SUBTASK_START"),
    (r"\[Tool Call\] complete_subtask", "SUBTASK_DONE"),
    (r"\[Tool Call\] replan_task", "REPLAN"),

    # ===== Memory (legacy) =====
    (r"\[Memory\] Task query:", "MEMORY"),
    (r"\[Memory\] Found (composed path|subtask plan)", "MEMORY"),
    (r"\[Memory\] path step", "MEMORY"),
    (r"\[Memory\] Navigation query:", "MEMORY"),
    (r"\[Memory\] (Found path|No navigation path)", "MEMORY"),
    (r"\[Memory\] Navigation guide saved", "MEMORY"),
    (r"Memory guidance active:", "MEMORY"),

    # ===== LLM calls =====
    (r"Token usage: in=", "TOKEN"),
    (r"\[LLM Reasoning\]", "THINK"),

    # ===== Tool calls =====
    (r"\[Tool Call\] (?!complete_subtask)", "TOOL"),

    # ===== Context management =====
    (r"\[Snapshot Clean\]", "CONTEXT"),
    (r"\[_call_llm\] Calling LLM with \d+ messages", "LLM_CALL"),
    (r"Snapshot saved:", "SNAPSHOT"),

    # ===== Agent loop events =====
    (r"\[Agent Loop\] LLM stopped but subtasks remain", "AGENT_STUCK"),
    (r"\[Agent Loop\] INITIAL MESSAGE TO LLM", "AGENT_INIT"),

    # ===== Browser events =====
    (r"browser_visit_page error:", "BROWSER_ERR"),
    (r"Browser session initialized", "BROWSER"),
    (r"BrowserToolkit initialized", "BROWSER"),
    (r"Created new browser session", "BROWSER"),
    (r"Browser process exited", "BROWSER_ERR"),
    (r"Failed to launch browser", "BROWSER_ERR"),

    # ===== Notes =====
    (r"Note created:", "NOTE"),
    (r"create_note|append_note", "NOTE"),

    # ===== Search =====
    (r"DuckDuckGo.*returned \d+ results", "SEARCH"),
    (r"search_google", "SEARCH"),

    # ===== SSE/Stream =====
    (r"SSE stream cancelled", "STREAM_END"),
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


def parse_task(log_files: list[Path], task_id: str, verbose: bool = False) -> list[dict]:
    events = []
    total_in = 0
    total_out = 0
    llm_calls = 0
    errors = 0
    warnings = 0
    tool_calls = 0
    subtasks_done = 0
    subtasks_total = 0
    workers_started = 0
    first_ts = None
    last_ts = None

    for fname, line_no, raw in iter_task_lines(log_files, task_id):
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue

        cat = classify(entry)
        if cat is None and not verbose:
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
        if cat in ("TOOL",):
            tool_calls += 1
        if cat in ("SUBTASK_DONE", "SUBTASK_OK"):
            subtasks_done += 1
        if cat == "DECOMP_DONE":
            m = re.search(r"Decomposed into (\d+) subtasks", msg)
            if m:
                subtasks_total = int(m.group(1))
        if cat == "WORKER_START":
            workers_started += 1

        # Skip certain verbose entries unless verbose mode
        if not verbose and cat in ("SNAPSHOT", "LLM_CALL", "CONTEXT"):
            continue

        display = msg[:300] + "..." if len(msg) > 300 else msg
        events.append({
            "file": fname,
            "line": line_no,
            "ts": ts,
            "level": entry.get("level", ""),
            "cat": cat or "OTHER",
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
        "subtasks_total": subtasks_total,
        "subtasks_done": subtasks_done,
        "workers_started": workers_started,
        "errors": errors,
        "warnings": warnings,
    }

    return events, stats


PREFIX = {
    # Orchestrator phase
    "ORCH_START":    "** ORCH",
    "ORCH_INIT":     "   ORCH",
    "ORCH_RUN":      ">> ORCH",
    "ORCH_REPLY":    "<< ORCH",
    "ORCH_DIRECT":   "<< DIRECT",
    "ORCH_DECOMPOSE":"** DECOMP",

    # Workforce init
    "WF_INIT":       "** WF",
    "WF_AGENTS":     "   AGENTS",
    "WF_MEMORY":     "   MEM",
    "WF_WORKERS":    "   WORKERS",
    "WF_READY":      "** READY",

    # Memory
    "MEM_QUERY":     "?? MEM",
    "MEM_FOUND":     "<< MEM",
    "MEM_MISS":      "!! MEM",
    "MEM_PROP":      ">> MEM",
    "MEM_LEVEL":     "   LEVEL",

    # Decomposition
    "DECOMP_START":  "** DECOMP",
    "DECOMP_RUN":    ">> DECOMP",
    "DECOMP_DONE":   "<< DECOMP",
    "DECOMP_WAIT":   ".. WAIT",
    "DECOMP_CONFIRM":"** CONFIRM",

    # Workforce execution
    "WF_EXEC_START": "** EXEC",
    "COORD_ASSIGN":  ">> COORD",
    "SUBTASK_ASSIGN":"   ASSIGN",
    "WORKER_START":  ">> WORKER",
    "WORKER_RESP":   "<< WORKER",

    # Subtask lifecycle
    "SUBTASK_DONE":  "<< DONE",
    "SUBTASK_FAILED":"!! FAILED",
    "SUBTASK_PROC":  ">> PROC",
    "SUBTASK_OK":    "<< OK",
    "SUBTASK_ERR":   "!! ERR",
    "SUBTASK_FAIL":  "!! FAIL",

    # Workforce completion
    "WF_STOP":       "** STOP",
    "WF_CLEANUP":    "   CLEAN",
    "WF_DONE":       "** DONE",
    "WF_SUMMARY":    ">> SUMMARY",
    "WF_SUMMARY_OK": "<< SUMMARY",
    "WF_MULTI_TURN": "** MULTI",
    "WF_WAIT_USER":  ".. WAIT",
    "WF_SESSION_END":"** END",

    # Pause/Resume
    "WF_PAUSE":      "|| PAUSE",
    "WF_RESUME":     "|> RESUME",

    # Legacy
    "TASK_INIT":     "** INIT",
    "TASK_START":    "** START",
    "TASK_PLAN":     "** PLAN",
    "TASK_ASSIGN":   ">> ASSIGN",
    "TASK_DONE":     ">> DONE",
    "TASK_FAILED":   "!! FAILED",
    "SUBTASK_STATE": ">> STATE",
    "SUBTASK_START": ">> SUB",
    "REPLAN":        ">> REPLAN",
    "MEMORY":        "   MEM",
    "TOKEN":         "   TOKEN",
    "THINK":         "   THINK",
    "TOOL":          "   TOOL",
    "CONTEXT":       "   CTX",
    "LLM_CALL":      "   LLM",
    "SNAPSHOT":      "   SNAP",
    "AGENT_STUCK":   "!  STUCK",
    "AGENT_INIT":    "** AGENT",
    "BROWSER":       "   BROWSER",
    "BROWSER_ERR":   "!! BROWSER",
    "NOTE":          "   NOTE",
    "SEARCH":        "   SEARCH",
    "STREAM_END":    "   STREAM",
    "ERROR":         "!! ERROR",
    "WARNING":       "!  WARN",
}


def format_output(events: list[dict], stats: dict) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append(f"TASK LOG SUMMARY: {stats['task_id']}")
    lines.append(f"Duration: {stats['duration']}  |  LLM calls: {stats['llm_calls']}  |  "
                 f"Tokens: {stats['total_input_tokens']:,} in / {stats['total_output_tokens']:,} out")
    lines.append(f"Subtasks: {stats['subtasks_done']}/{stats['subtasks_total']}  |  "
                 f"Workers: {stats['workers_started']}  |  Tool calls: {stats['tool_calls']}  |  "
                 f"Errors: {stats['errors']}  |  Warnings: {stats['warnings']}")
    lines.append("=" * 80)

    prev_cat = None
    for ev in events:
        cat = ev["cat"]
        ts = ev["ts"]
        short_ts = ts[11:19] if len(ts) >= 19 else ts

        # Separator before major phase changes
        phase_starters = (
            "ORCH_START", "WF_INIT", "DECOMP_START", "WF_EXEC_START",
            "WF_STOP", "SUBTASK_PROC", "WORKER_START"
        )
        if cat in phase_starters and prev_cat not in phase_starters:
            lines.append("-" * 60)

        prefix = PREFIX.get(cat, f"   {cat[:8]}")
        lines.append(f"[{short_ts}] {prefix:>12} | {ev['msg']}")
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
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show all events, not just key events")
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

    events, stats = parse_task(log_files, task_id, verbose=args.verbose)
    output = format_output(events, stats)

    if args.output:
        args.output.write_text(output)
        print(f"Written to {args.output} ({len(events)} key events)", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
