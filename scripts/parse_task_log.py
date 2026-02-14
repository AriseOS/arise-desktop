#!/usr/bin/env python3
"""Parse Ami task logs to show AI execution trace.

Supports both the legacy Python daemon JSON format and the new TS daemon Pino format.

Shows: User request → Decomposition → Memory → Subtask execution → Tool calls → Summary

Usage:
    python scripts/parse_task_log.py              # Latest task
    python scripts/parse_task_log.py --list       # List recent tasks
    python scripts/parse_task_log.py --task-id X  # Specific task
    python scripts/parse_task_log.py --full       # Show full content (not truncated)
    python scripts/parse_task_log.py -v           # Verbose: include debug-level LLM I/O
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

# Pino log levels
PINO_LEVELS = {10: "TRACE", 20: "DEBUG", 30: "INFO", 40: "WARN", 50: "ERROR", 60: "FATAL"}


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


def normalize_entry(raw_json: dict) -> dict:
    """Normalize a log entry to a common schema regardless of format.

    Returns dict with: timestamp (str), level (str), module (str), msg (str),
    plus any extra structured fields from Pino.
    """
    # Detect format: Pino has numeric "level" + "time"; Python has string "level" + "timestamp"
    if "time" in raw_json and isinstance(raw_json.get("level"), int):
        # Pino (TS daemon) format
        ts_ms = raw_json["time"]
        try:
            ts = datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%dT%H:%M:%S")
        except (OSError, ValueError):
            ts = ""
        level_int = raw_json.get("level", 30)
        level = PINO_LEVELS.get(level_int, "INFO")
        module = raw_json.get("module", "")
        msg = raw_json.get("msg", "")
        return {**raw_json, "timestamp": ts, "level": level, "module": module, "msg": msg}
    else:
        # Python daemon format
        ts = raw_json.get("timestamp", "")
        level = raw_json.get("level", "INFO")
        module = raw_json.get("module", "")
        msg = raw_json.get("message", raw_json.get("msg", ""))
        return {**raw_json, "timestamp": ts, "level": level, "module": module, "msg": msg}


def find_task_id_from_logs(log_files) -> Optional[str]:
    """Find the most recent task ID from logs."""
    for log_file in reversed(log_files):
        last_task_id = None
        with open(log_file, "r") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                entry = normalize_entry(entry)
                msg = entry["msg"]
                # TS daemon: "decompose_task triggered" with task field
                if "decompose_task triggered" in msg:
                    task = entry.get("task", "")
                    # The task_id comes from orchestrator context, look for executorId
                    continue
                # TS daemon: "Spawned background plan+execute" has executorId
                if "Spawned background plan+execute" in msg:
                    eid = entry.get("executorId", "")
                    if eid:
                        last_task_id = eid[:8] if len(eid) > 8 else eid
                    continue
                # TS daemon: "AMITaskExecutor initialized" has taskId
                if "AMITaskExecutor initialized" in msg:
                    tid = entry.get("taskId", "")
                    if tid:
                        last_task_id = tid[:8] if len(tid) > 8 else tid
                    continue
                # TS daemon: "AMITaskPlanner initialized" has taskId
                if "AMITaskPlanner initialized" in msg:
                    tid = entry.get("taskId", "")
                    if tid:
                        last_task_id = tid[:8] if len(tid) > 8 else tid
                    continue
                # Python daemon fallback
                m = re.search(r"Task submitted.*?(\w{8})", msg)
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
                    entry = normalize_entry(json.loads(raw))
                except json.JSONDecodeError:
                    continue
                msg = entry["msg"]
                ts = entry["timestamp"]

                # TS daemon: task start via planner init
                if "AMITaskPlanner initialized" in msg:
                    task_id = entry.get("taskId", "")
                    if task_id:
                        tid = task_id[:8] if len(task_id) > 8 else task_id
                        tasks[tid] = TaskInfo(task_id=tid, timestamp=ts[:19], status="running")
                    continue

                # TS daemon: "Calling orchestrator agent" has message field
                if "Calling orchestrator agent" in msg:
                    user_msg = entry.get("message", "")
                    if user_msg:
                        for task_id in reversed(list(tasks.keys())):
                            if not tasks[task_id].user_request:
                                tasks[task_id].user_request = user_msg[:80]
                                break
                    continue

                # TS daemon: "Memory-First decomposing task" has task field
                if "Memory-First decomposing task" in msg:
                    task_text = entry.get("task", "")
                    if task_text:
                        for task_id in reversed(list(tasks.keys())):
                            if not tasks[task_id].user_request:
                                tasks[task_id].user_request = task_text[:80]
                                break
                    continue

                # TS daemon: execution finished
                if "Execution finished" in msg:
                    for task_id in reversed(list(tasks.keys())):
                        if tasks[task_id].status == "running":
                            tasks[task_id].status = "completed"
                            break
                    continue

                # TS daemon: session ending
                if "Session ending" in msg:
                    for task_id in reversed(list(tasks.keys())):
                        if tasks[task_id].status == "running":
                            tasks[task_id].status = "completed"
                            break
                    continue

                # Python daemon fallback
                m = re.search(r"Task submitted.*?(\w{8})", msg)
                if m:
                    task_id = m.group(1)
                    tasks[task_id] = TaskInfo(task_id=task_id, timestamp=ts[:19], status="running")
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
    cache_read: int = 0
    errors: int = 0


def get_task_output_files(task_id: str) -> list:
    output_files = []
    for users_dir in AMI_DIR.glob("users/*/projects/*/tasks"):
        # Try both full task_id and short prefix match
        for task_dir_parent in [users_dir]:
            for candidate in task_dir_parent.iterdir():
                if candidate.name.startswith(task_id) and candidate.is_dir():
                    ws = candidate / "workspace"
                    if ws.exists():
                        for f in ws.iterdir():
                            if f.is_file() and not f.name.startswith('.'):
                                size = f.stat().st_size
                                if size < 1024:
                                    sz = f"{size}B"
                                elif size < 1024 * 1024:
                                    sz = f"{size / 1024:.1f}KB"
                                else:
                                    sz = f"{size / (1024 * 1024):.1f}MB"
                                output_files.append({"name": f.name, "size": sz})
                        return output_files
    return output_files


def _entry_matches_task(entry: dict, task_id: str) -> bool:
    """Check if a log entry is related to the given task_id."""
    msg = entry.get("msg", "")
    # Check structured fields
    for key in ("taskId", "executorId", "task_id"):
        val = str(entry.get(key, ""))
        if val and (val == task_id or val.startswith(task_id)):
            return True
    # Check message text
    if task_id in msg:
        return True
    return False


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
                try:
                    raw_json = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                entry = normalize_entry(raw_json)
                msg = entry["msg"]

                # TS daemon: detect task start
                if not started:
                    # AMITaskPlanner or AMITaskExecutor initialized with matching taskId
                    tid = str(entry.get("taskId", ""))
                    if tid and tid.startswith(task_id) and ("initialized" in msg):
                        started = True
                    # Python daemon fallback
                    elif "Task submitted" in msg and task_id in msg:
                        started = True
                    # decompose_task triggered (orchestrator)
                    elif "decompose_task triggered" in msg and _entry_matches_task(entry, task_id):
                        started = True
                    if not started:
                        continue

                # Stop at next task start (different task)
                if started:
                    if ("AMITaskPlanner initialized" in msg or "AMITaskExecutor initialized" in msg):
                        tid = str(entry.get("taskId", ""))
                        if tid and not tid.startswith(task_id) and tid != task_id:
                            break
                    elif "Task submitted" in msg and task_id not in msg:
                        break

                entries.append(entry)

    current_subtask_id = ""
    current_agent = "orchestrator"

    for entry in entries:
        ts_raw = entry.get("timestamp", "")
        ts = ts_raw[11:19] if len(ts_raw) >= 19 else ts_raw  # HH:MM:SS
        msg = entry["msg"]
        level = entry["level"]
        module = entry.get("module", "")

        if not trace.start_time and ts:
            trace.start_time = ts
        if ts:
            trace.end_time = ts

        # ═══════════════════════════════════════════════════════════════════
        # TS DAEMON (Pino) PATTERNS — structured fields in entry
        # ═══════════════════════════════════════════════════════════════════

        # ─── Orchestrator: calling agent ──────────────────────────────────
        if "Calling orchestrator agent" in msg and module == "orchestrator":
            user_msg = entry.get("message", "")
            if user_msg:
                trace.user_request = user_msg
                trace.events.append(Event(ts, "user_request", truncate(user_msg, tl)))
            continue

        # ─── decompose_task triggered ─────────────────────────────────────
        if "decompose_task triggered" in msg:
            task_desc = entry.get("task", "")
            trace.events.append(Event(ts, "decompose_start", f"decompose_task: {truncate(task_desc, ts_short)}", agent="orchestrator"))
            if task_desc and not trace.user_request:
                trace.user_request = task_desc
            continue

        # ─── Memory-First decomposing ─────────────────────────────────────
        if "Memory-First decomposing task" in msg:
            task_desc = entry.get("task", "")
            trace.events.append(Event(ts, "memory_query", f"Memory-First decomposing: {truncate(task_desc, ts_short)}"))
            if task_desc and not trace.user_request:
                trace.user_request = task_desc
            continue

        # ─── L1 Planner memory context built ──────────────────────────────
        if "L1 Planner memory context built" in msg:
            coverage = entry.get("coverage", "")
            steps = entry.get("stepsCount", 0)
            prefs = entry.get("preferencesCount", 0)
            ctx_len = entry.get("contextLen", 0)
            # Determine memory level from coverage
            trace.memory_detail = f"coverage={coverage}, steps={steps}, prefs={prefs}, ctx={ctx_len} chars"
            trace.events.append(Event(ts, "memory_result", f"Memory context: {trace.memory_detail}"))
            continue

        # ─── Memory query timeout/failure ─────────────────────────────────
        if "L1 Planner memory query timed out" in msg:
            trace.memory_level = "timeout"
            trace.events.append(Event(ts, "memory_result", "Memory query TIMED OUT"))
            continue

        if "L1 Planner memory query failed" in msg:
            trace.memory_level = "failed"
            trace.events.append(Event(ts, "memory_result", "Memory query FAILED"))
            continue

        # ─── Decompose prompt built ───────────────────────────────────────
        if "Decompose prompt built" in msg:
            prompt_len = entry.get("promptLen", 0)
            trace.events.append(Event(ts, "decompose_prompt", f"Decompose prompt built ({prompt_len} chars)"))
            continue

        # ─── Decompose raw response received ──────────────────────────────
        if "Decompose raw response received" in msg:
            resp_len = entry.get("responseLen", 0)
            trace.events.append(Event(ts, "decompose_response", f"Decompose response received ({resp_len} chars)"))
            continue

        # ─── Subtask parsed (from planner) ────────────────────────────────
        if "Subtask parsed" in msg:
            st_id = str(entry.get("id", ""))
            st_type = entry.get("type", "")
            st_deps = entry.get("deps", [])
            st_content = entry.get("content", "")
            st = SubtaskInfo(
                id=st_id,
                agent_type=st_type,
                content=st_content,
                depends_on=st_deps if st_deps else [],
            )
            if not any(s.id == st.id for s in trace.subtasks):
                trace.subtasks.append(st)
            continue

        # ─── Fine-grained decomposition complete ──────────────────────────
        if "Fine-grained decomposition complete" in msg:
            count = entry.get("count", 0)
            types = entry.get("types", {})
            trace.events.append(Event(ts, "decompose_done", f"Decomposed into {count} subtasks: {types}"))
            continue

        # ─── Subtask queued (from executor) ───────────────────────────────
        if "Subtask queued" in msg:
            st_id = str(entry.get("id", ""))
            st_type = entry.get("type", "")
            st_deps = entry.get("deps", [])
            st_content = entry.get("content", "")
            st = SubtaskInfo(
                id=st_id,
                agent_type=st_type,
                content=st_content,
                depends_on=st_deps if st_deps else [],
            )
            if not any(s.id == st.id for s in trace.subtasks):
                trace.subtasks.append(st)
            continue

        # ─── Dispatching parallel batch ───────────────────────────────────
        if "Dispatching parallel batch" in msg:
            batch_size = entry.get("batchSize", 0)
            ids = entry.get("ids", [])
            trace.events.append(Event(ts, "batch_dispatch", f"Dispatching batch: {batch_size} subtasks {ids}"))
            continue

        # ─── Borrowed session for browser subtask ─────────────────────────
        if "Borrowed session for browser subtask" in msg:
            sid = entry.get("subtaskId", "")
            session_id = entry.get("sessionId", "")
            if verbose:
                trace.events.append(Event(ts, "session_borrow", f"Subtask {sid} borrowed session {session_id[:16]}...", subtask_id=str(sid)))
            continue

        # ─── Executing subtask ────────────────────────────────────────────
        if "Executing subtask" in msg and module == "task-executor":
            sid = str(entry.get("subtaskId", ""))
            attempt = entry.get("attempt", 1)
            max_attempts = entry.get("maxAttempts", 1)
            current_subtask_id = sid
            st_content = ""
            for st in trace.subtasks:
                if st.id == sid:
                    st_content = st.content
                    st.status = "running"
                    current_agent = st.agent_type
                    break
            trace.events.append(Event(
                ts, "subtask_start",
                f"Subtask {sid} (attempt {attempt}/{max_attempts}): {truncate(st_content, ts_short)}",
                subtask_id=sid,
            ))
            continue

        # ─── Subtask completed ────────────────────────────────────────────
        if "Subtask completed" in msg and module == "task-executor":
            sid = str(entry.get("subtaskId", ""))
            result_len = entry.get("resultLen", 0)
            for st in trace.subtasks:
                if st.id == sid:
                    st.status = "done"
                    break
            trace.events.append(Event(
                ts, "subtask_done",
                f"Subtask {sid} DONE ({result_len} chars)",
                subtask_id=sid,
            ))
            continue

        # ─── Subtask failed ───────────────────────────────────────────────
        if "Subtask failed" in msg and module == "task-executor":
            sid = str(entry.get("subtaskId", ""))
            attempt = entry.get("attempt", 0)
            error = entry.get("error", "")
            for st in trace.subtasks:
                if st.id == sid:
                    st.status = "failed"
                    break
            trace.events.append(Event(
                ts, "subtask_failed",
                f"Subtask {sid} FAILED (attempt {attempt})",
                subtask_id=sid,
                extra=truncate(error, ts_short),
            ))
            continue

        # ─── Agent exceeded max turns ─────────────────────────────────────
        if "Agent exceeded max turns" in msg:
            sid = str(entry.get("subtaskId", ""))
            turn_count = entry.get("turnCount", 0)
            trace.events.append(Event(ts, "warning", f"Subtask {sid} exceeded max turns ({turn_count})", subtask_id=sid))
            continue

        # ─── Execution finished ───────────────────────────────────────────
        if "Execution finished" in msg and module == "task-executor":
            completed = entry.get("completed", 0)
            failed = entry.get("failed", 0)
            total = entry.get("total", 0)
            stopped = entry.get("stopped", False)
            trace.events.append(Event(
                ts, "execution_done",
                f"Execution finished: {completed}/{total} completed, {failed} failed" + (" (STOPPED)" if stopped else ""),
            ))
            continue

        # ─── Bridge: Agent thinking before tool call ──────────────────────
        if "Agent thinking before tool call" in msg:
            agent_name = entry.get("agent", current_agent)
            thinking = entry.get("thinking", "")
            if thinking:
                trace.events.append(Event(
                    ts, "llm_thinks",
                    truncate(thinking, tl),
                    agent=agent_name,
                    subtask_id=current_subtask_id,
                ))
            continue

        # ─── Bridge: Agent final response ─────────────────────────────────
        if "Agent final response" in msg:
            agent_name = entry.get("agent", current_agent)
            thinking = entry.get("thinking", "")
            if thinking:
                trace.events.append(Event(
                    ts, "llm_thinks",
                    truncate(thinking, tl),
                    agent=agent_name,
                    subtask_id=current_subtask_id,
                ))
            continue

        # ─── Bridge: Tool call started ────────────────────────────────────
        if "Tool call started" in msg and module == "bridge":
            agent_name = entry.get("agent", current_agent)
            tool = entry.get("tool", "")
            trace.events.append(Event(
                ts, "llm_calls_tool",
                tool,
                agent=agent_name,
                subtask_id=current_subtask_id,
            ))
            continue

        # ─── Bridge: Tool call ended ──────────────────────────────────────
        if "Tool call ended" in msg and module == "bridge":
            agent_name = entry.get("agent", current_agent)
            tool = entry.get("tool", "")
            success = entry.get("success", True)
            if not success:
                trace.events.append(Event(
                    ts, "warning",
                    f"Tool {tool} FAILED",
                    agent=agent_name,
                    subtask_id=current_subtask_id,
                ))
            continue

        # ─── Bridge: LLM OUTPUT (debug mode) ─────────────────────────────
        if "<<< LLM OUTPUT:" in msg and module == "bridge":
            agent_name = entry.get("agent", current_agent)
            usage = entry.get("usage", {})
            if usage:
                tok_in = usage.get("input", 0)
                tok_out = usage.get("output", 0)
                cache = usage.get("cacheRead", 0)
                trace.tokens_in += tok_in
                trace.tokens_out += tok_out
                trace.cache_read += cache
                trace.llm_calls += 1
            if verbose:
                # Extract summary from msg
                content = msg.split("<<< LLM OUTPUT:\n", 1)[-1] if "<<< LLM OUTPUT:\n" in msg else ""
                trace.events.append(Event(
                    ts, "llm_response",
                    f"LLM ({agent_name}): {truncate(content, tl)}",
                    agent=agent_name,
                    subtask_id=current_subtask_id,
                    extra=f"tokens: in={tok_in} out={tok_out} cache={cache}" if usage else "",
                ))
            continue

        # ─── Online Learning events ───────────────────────────────────────
        if "[OnlineLearning]" in msg:
            if "Recorder started" in msg:
                if verbose:
                    trace.events.append(Event(ts, "learning", "Behavior recorder started"))
                continue
            if "Recorder stopped" in msg:
                if verbose:
                    trace.events.append(Event(ts, "learning", "Behavior recorder stopped"))
                continue
            if "Memory save result" in msg:
                result = entry.get("result", {})
                states = result.get("states_added", 0)
                actions = result.get("actions_added", 0)
                trace.events.append(Event(ts, "learning", f"Memory saved: {states} states, {actions} actions"))
                continue
            if "Failed to save to memory" in msg:
                trace.events.append(Event(ts, "warning", "Online learning: failed to save to memory"))
                continue
            if "Saving operations to memory" in msg:
                op_count = entry.get("operationCount", 0)
                sid = str(entry.get("subtaskId", ""))
                trace.events.append(Event(ts, "learning", f"Saving {op_count} operations (subtask {sid})"))
                continue
            continue

        # ─── Post-execution learning ──────────────────────────────────────
        if "Triggering post-execution learning" in msg:
            count = entry.get("subtasksCollected", 0)
            trace.events.append(Event(ts, "learning", f"Post-execution learning: {count} subtasks collected"))
            continue

        if "Post-execution learning result" in msg:
            created = entry.get("phraseCreated", False)
            phrase_id = entry.get("phraseId", "")
            trace.events.append(Event(ts, "learning", f"Learning result: phrase_created={created}" + (f" id={phrase_id}" if phrase_id else "")))
            continue

        # ─── Circular dependency detection ────────────────────────────────
        if "Subtasks stuck PENDING" in msg:
            stuck_ids = entry.get("stuckIds", [])
            trace.events.append(Event(ts, "error", f"Circular dependency detected: {stuck_ids}"))
            trace.errors += 1
            continue

        # ─── Spawned background plan+execute ──────────────────────────────
        if "Spawned background plan+execute" in msg:
            eid = entry.get("executorId", "")
            trace.events.append(Event(ts, "orchestrator", f"Spawned plan+execute (executor: {eid[:8]}...)", agent="orchestrator"))
            continue

        # ─── Resuming from snapshot ───────────────────────────────────────
        if "Resuming from snapshot" in msg:
            resume_id = entry.get("resumeTaskId", "")
            count = entry.get("resumeCount", 0)
            trace.events.append(Event(ts, "orchestrator", f"Resuming from {resume_id[:8]}... ({count} subtasks)", agent="orchestrator"))
            continue

        # ═══════════════════════════════════════════════════════════════════
        # PYTHON DAEMON FALLBACK PATTERNS (message string parsing)
        # ═══════════════════════════════════════════════════════════════════

        # ─── User Request (Python) ────────────────────────────────────────
        m = re.search(r"Running Orchestrator for: (.+)", msg)
        if m:
            trace.user_request = m.group(1)
            trace.events.append(Event(ts, "user_request", truncate(m.group(1), tl)))
            continue

        # ─── LLM Response blocks (Python) ─────────────────────────────────
        if "[LLM Response] Block" in msg and "text:" in msg:
            m = re.search(r"Block \d+ text: (.+)", msg)
            if m:
                text = m.group(1)
                if len(text) > 15 and not text.startswith("```json"):
                    trace.events.append(Event(
                        ts, "llm_thinks", truncate(text, tl),
                        agent=current_agent, subtask_id=current_subtask_id,
                    ))
            continue

        if "[LLM Response] Block" in msg and "tool_use:" in msg:
            m = re.search(r"tool_use: (\w+)\((.+)\)", msg)
            if m:
                tool_name = m.group(1)
                input_display = truncate(m.group(2), ts_short)
                trace.events.append(Event(
                    ts, "llm_calls_tool", tool_name,
                    agent=current_agent, subtask_id=current_subtask_id,
                    extra=input_display,
                ))
            continue

        # ─── Token usage (Python) ─────────────────────────────────────────
        if "Token usage:" in msg:
            m = re.search(r"in=(\d+), out=(\d+)", msg)
            if m:
                trace.tokens_in += int(m.group(1))
                trace.tokens_out += int(m.group(2))
                trace.llm_calls += 1
            m_cache = re.search(r"cache_read=(\d+)", msg)
            if m_cache:
                trace.cache_read += int(m_cache.group(1))
            continue

        # ─── Subtask patterns (Python) ────────────────────────────────────
        if ("[AMITaskPlanner] Subtask" in msg or "[AMITaskExecutor] Subtask" in msg) and re.search(r"Subtask \d+ \(", msg):
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

        if "[AMITaskExecutor] Executing subtask" in msg:
            m = re.search(r"Executing subtask (\S+)\s*\(attempt (\d+)", msg)
            if m:
                current_subtask_id = m.group(1)
                current_agent = "browser"
                attempt = m.group(2)
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

        if "[AMITaskExecutor] Subtask" in msg and "completed" in msg:
            m = re.search(r"Subtask (\S+) completed(?:: (.+))?", msg)
            if m:
                sid = m.group(1)
                result = truncate(m.group(2) or "", ts_short)
                for st in trace.subtasks:
                    if st.id == sid:
                        st.status = "done"
                        break
                trace.events.append(Event(ts, "subtask_done", f"Subtask {sid} DONE", subtask_id=sid, extra=result))
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

        if "[AMITaskExecutor] Execution finished:" in msg:
            m = re.search(r"Execution finished: (.+)", msg)
            if m:
                trace.events.append(Event(ts, "execution_done", f"Execution result: {m.group(1)}"))
            continue

        # ─── Screenshot failed ────────────────────────────────────────────
        if "Screenshot failed" in msg:
            if verbose:
                trace.events.append(Event(ts, "warning", "Screenshot capture failed (timeout)"))
            continue

        # ─── Browser navigation (Python) ──────────────────────────────────
        if "URL changed:" in msg:
            m = re.search(r"URL changed: .+ -> (.+)", msg)
            if m:
                trace.events.append(Event(
                    ts, "browser_nav", f"Page: {truncate(m.group(1), 80)}",
                    agent="browser", subtask_id=current_subtask_id,
                ))
            continue

        # ─── Task cancelled ───────────────────────────────────────────────
        if "Task cancelled" in msg:
            trace.events.append(Event(ts, "cancelled", "TASK CANCELLED"))
            continue

        # ─── Session ending ───────────────────────────────────────────────
        if "Session ending" in msg:
            trace.events.append(Event(ts, "execution_done", "Session ending"))
            continue

        # ─── Errors ───────────────────────────────────────────────────────
        if level == "ERROR" or level == "FATAL":
            trace.events.append(Event(ts, "error", truncate(msg, tl)))
            trace.errors += 1
            continue

        # ─── Important warnings ───────────────────────────────────────────
        if level == "WARN" and any(kw in msg for kw in ["Failed", "Error", "timeout", "closed", "stuck", "error"]):
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

    cache_str = f"  |  Cache read: {trace.cache_read:,}" if trace.cache_read else ""
    lines.append(f"  Duration: {duration}  |  LLM calls: {trace.llm_calls}  |  "
                 f"Tokens: {trace.tokens_in:,} in / {trace.tokens_out:,} out{cache_str}  |  "
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
            deps = f" (after: {','.join(str(d) for d in st.depends_on)})" if st.depends_on else ""
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
            "user_request":     "REQ",
            "orchestrator":     "ORC",
            "decompose_start":  "DEC",
            "memory_query":     "MEM",
            "memory_result":    "MEM",
            "decompose_prompt": "DEC",
            "decompose_response": "DEC",
            "decompose_done":   "DEC",
            "batch_dispatch":   "PAR",
            "session_borrow":   "SES",
            "subtask_start":    ">>>",
            "subtask_done":     " OK",
            "subtask_failed":   "ERR",
            "execution_done":   "END",
            "llm_thinks":       "  .",
            "llm_calls_tool":   " ->",
            "llm_response":     "LLM",
            "summarization":    "!!!",
            "truncation":       " ~~",
            "browser_nav":      "NAV",
            "page_memory":      "MEM",
            "file_saved":       "SAV",
            "search":           "SRC",
            "learning":         "LRN",
            "cancelled":        "XXX",
            "error":            "ERR",
            "warning":          "WRN",
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
    parser.add_argument("-v", "--verbose", action="store_true", help="Include debug-level events (LLM I/O, sessions)")
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
