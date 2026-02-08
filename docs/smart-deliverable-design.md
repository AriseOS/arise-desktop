# Smart Deliverable: Task Output Format & File Selection

## Problem

Task completion sends ALL workspace files to the user, including intermediate research notes (.md), temporary data files, etc. Users receive a messy pile of files instead of clean, well-formatted deliverables.

## Goals

1. Task Planner gives principled guidance on output format (not rigid rules)
2. Final deliverables use visual-friendly formats (HTML, CSV, Excel, Word), not .md
3. Summary Agent decides which files to deliver to user (not code logic)

## Current Flow

```
Planner → Subtasks → Agents Execute → Summary Agent (text only) → Scan ALL files → Send everything
```

## New Flow

```
Planner → Subtasks → Agents Execute → Summary Agent (text + file selection) → Send selected files only
```

## Changes

### Change 1: Task Planner Prompt — Add Deliverable Principles

**File**: `ami_task_planner.py` — `FINE_GRAINED_DECOMPOSE_PROMPT`

Add a principle about output format to the decompose prompt. This is **principled guidance**, not a rigid rule table. Let the LLM decide based on context.

**Add principle 7** (after principle 6, before LANGUAGE POLICY):

```
7. **Deliverable Format**: The final task should produce a well-formatted deliverable for the user.
   - Use visual-friendly formats: HTML, CSV, Excel (.xlsx), Word (.docx), PowerPoint (.pptx)
   - Markdown (.md) is for intermediate notes only, NEVER as a final deliverable
   - If the user's request is a simple question with a short answer, no file is needed — a text reply is sufficient
   - If the user specifies a format, use that format
   - Choose the format that best serves the content: tabular data suits spreadsheets, rich reports suit HTML, formal documents suit Word
```

Update the XML example to reflect this (the existing example already uses HTML for the final task, which is good — just make sure both examples are consistent).

### Change 2: Summary Agent Upgrade — Text + File Selection

**File**: `agent_factories.py` — `TASK_SUMMARY_AGENT_SYSTEM_PROMPT` and `summarize_subtasks_results()`

Currently the Summary Agent only generates a text summary. Upgrade it to also select which files to deliver.

#### 2a. Update System Prompt

Replace `TASK_SUMMARY_AGENT_SYSTEM_PROMPT` with an upgraded version that includes file selection responsibility:

```
You are a task completion assistant. After a task finishes, you review the results and decide what to present to the user.

You have TWO responsibilities:

1. **Text Summary**: Write a concise summary of what was accomplished.
2. **File Selection**: From the list of workspace files, select ONLY the key deliverable files to send to the user.

Guidelines for text summary:
- Be concise but comprehensive
- Use bullet points or sections for clarity
- Highlight key findings or outputs
- DO NOT repeat the task description — focus on results
- Keep it professional but conversational

Guidelines for file selection:
- Select only the FINAL deliverable files that the user actually needs
- DO NOT select intermediate files: research notes, raw data dumps, temporary files
- Prefer well-formatted files (HTML, CSV, Excel, Word) over plain text/markdown
- If the task result is a simple text answer, select NO files
- When in doubt, fewer files is better than too many

**CRITICAL Language Policy**:
- Write the summary in the same language as the user's original request.

**Output format** (respond in valid JSON):
{
  "summary": "Your text summary here...",
  "selected_files": ["report.html", "data.xlsx"]
}

If no files should be delivered:
{
  "summary": "Your text summary here...",
  "selected_files": []
}
```

#### 2b. Update `summarize_subtasks_results()` Function

**Current signature**:
```python
async def summarize_subtasks_results(
    provider, main_task, subtasks
) -> str
```

**New signature**:
```python
async def summarize_subtasks_results(
    provider, main_task, subtasks, workspace_files: List[str]
) -> dict  # {"summary": str, "selected_files": List[str]}
```

Changes:
- Accept `workspace_files` parameter: list of filenames available in workspace
- Include file list in the prompt sent to LLM
- Parse JSON response to extract both `summary` and `selected_files`
- Return a dict instead of a plain string

**Prompt addition** (append to existing prompt):

```
Available files in workspace:
{file_list}

Based on the task results and the available files, select which files should be delivered to the user.
Respond in JSON format: {"summary": "...", "selected_files": ["file1.html", ...]}
```

### Change 3: File Collection — LLM-Driven Selection

**File**: `quick_task_service.py` — `_aggregate_ami_results()` and the call site (lines 1897-1929)

#### Current flow (lines 1897-1903):
```python
final_output = await self._aggregate_ami_results(task_id, state, subtasks, result, duration)
attachments = await self._collect_file_attachments(task_id, state)
```

Summary and file collection are independent. All files are collected.

#### New flow:

```python
# Step 1: Scan workspace for candidate files (same as before, returns file paths)
all_files = await self._collect_candidate_files(task_id, state)

# Step 2: Summary Agent decides text + which files to deliver
summary_result = await self._aggregate_ami_results(
    task_id, state, subtasks, result, duration,
    candidate_files=[f.file_name for f in all_files]  # pass filenames to LLM
)
# summary_result = {"summary": "...", "selected_files": ["report.html"]}

final_output = summary_result["summary"]

# Step 3: Filter attachments to only selected files
selected_names = set(summary_result.get("selected_files", []))
if selected_names:
    attachments = [f for f in all_files if f.file_name in selected_names]
else:
    attachments = []  # LLM decided no files needed
```

Key changes:
- Rename `_collect_file_attachments` → `_collect_candidate_files` (semantic clarity: these are candidates, not final)
- `_aggregate_ami_results` now receives the candidate file list and passes it to Summary Agent
- `_aggregate_ami_results` returns a dict `{summary, selected_files}` instead of a plain string
- File filtering is a simple set intersection on filenames

## Files Modified

| File | What Changes |
|------|-------------|
| `ami_task_planner.py` | Add principle 7 (deliverable format) to `FINE_GRAINED_DECOMPOSE_PROMPT` |
| `agent_factories.py` | Upgrade `TASK_SUMMARY_AGENT_SYSTEM_PROMPT`; update `summarize_subtasks_results()` to accept file list, return dict with summary + selected_files |
| `quick_task_service.py` | Wire up: scan candidates → pass to summary agent → filter by selection |

## What Does NOT Change

- `AMISubtask` data model — no new fields needed
- XML task format — no new attributes
- `_collect_file_attachments` scan logic — same scan, just renamed and used as candidate list
- `FileAttachment` / `WaitConfirmData` data structures
- Agent toolkits (NoteTakingToolkit, FileToolkit)

## Edge Cases

| Case | Behavior |
|------|----------|
| LLM returns invalid JSON | Fallback: use raw response as summary text, attach all candidate files |
| LLM selects a filename that doesn't exist | Ignore it, log warning |
| Single subtask (no summary needed) | Still run file selection with single subtask result |
| No files in workspace | selected_files = [], no attachments |
| LLM returns empty selected_files | No attachments sent (this is intentional for simple Q&A tasks) |
