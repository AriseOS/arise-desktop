# Orchestrator Document Toolkit Design

## Problem

Orchestrator Agent 缺少文档创建工具。当用户发送简单任务（如"查天气然后写个 PDF"），LLM 判断可以直接处理，但手里没有 `write_to_file` 等工具，只能调用 `decompose_task` 走 Executor 流水线。这导致：

1. 简单任务被不必要地分解为子任务
2. Orchestrator 回复"文档创建中"但子任务可能未启动或被取消
3. 用户体验差：本应秒出的文件需要等待整个编排流程

## Root Cause Analysis

以 task `7d74c9f8`（"查北京天气，输出 PDF 和 DOC"）为例：

```
[10:46:37] 用户请求
[10:46:46] Orchestrator → search_google("北京天气") ✅
[10:46:54] Orchestrator → search_google("北京今天天气") ✅
[10:47:08] Orchestrator → decompose_task（因为没有 write_to_file 工具）
[10:47:08] DecomposeTaskTool 返回 "Task delegated successfully"
[10:47:15] Orchestrator 回复 "文档创建中..." 并开始轮询文件系统
[10:48:21] 用户断开，任务取消。AMITaskPlanner/Executor 从未启动
```

Orchestrator 拥有的工具：`search_google`, `ask_human`, `send_message`, `shell_exec`, `query_page_operations`, `decompose_task`, `attach_file`

**缺少的工具**：`write_to_file`, `read_file`, `list_files`, `create_presentation`, Excel 操作等

## Solution

给 Orchestrator Agent 补齐 Document Agent 的核心工具集。不改变 `decompose_task` 的决策逻辑 —— LLM 自己判断何时直接处理、何时委派。

### 新增 Toolkits

| Toolkit | 提供的工具 | 用途 |
|---------|-----------|------|
| `FileToolkit` | `write_to_file`, `read_file`, `list_files` | 文件读写（PDF/DOCX/HTML/MD 等） |
| `PPTXToolkit` | `create_presentation` | PowerPoint 创建 |
| `ExcelToolkit` | Excel 系列操作 | Excel 读写 |
| `MarkItDownToolkit` | `read_files` | 读取各种文档格式（PDF、DOCX、EPUB 等） |

### Working Directory

Document toolkits 使用 **task workspace**（`working_directory` 参数，即 `{task_id}/workspace/`），不是 `user_workspace`（所有任务的父目录）。

当前 Orchestrator 的 `TerminalToolkit` 使用 `user_workspace`（用于跨任务查找文件），而新增的 document toolkits 需要写入当前任务的 workspace。两者共存，目的不同。

### System Prompt 更新

在 `ORCHESTRATOR_SYSTEM_PROMPT` 的 "Your Tools" 部分追加文档工具说明：

```
- write_to_file: Create files (PDF, DOCX, HTML, Markdown, etc.)
  - .docx: Write content in Markdown, auto-converted to Word format
  - .pdf: Write content in Markdown, auto-converted to PDF with CJK support
  - .html: Write HTML markup directly
- read_file / list_files: Read files and list directory contents
- create_presentation: Create PowerPoint presentations (content as JSON string)
- Excel tools: Create and manipulate Excel spreadsheets
- read_files: Read various document formats (PDF, DOCX, EPUB, images, etc.)
```

追加文件附件说明：
```
When you create files, ALWAYS use attach_file to attach them to your response
so the user can view/download them directly.
```

**不修改** `decompose_task` 的使用指导。LLM 有了文档工具后，自然会在简单场景直接创建文件，复杂场景仍然 decompose。

### Direct Response Path 自动收集文件

当前直接路径（`quick_task_service.py` line ~1981）只收集 `AttachFileTool` 手动附加的文件。新增逻辑：

1. Orchestrator 完成后，调用 `_collect_candidate_files()` 扫描 workspace
2. 与 `attach_tool.attached_files` 合并（去重）
3. 确保 `write_to_file` 创建的文件即使 LLM 忘记调用 `attach_file` 也能返回

```python
# Direct Response Path
else:
    # ... existing code ...

    # Auto-collect workspace files (covers write_to_file outputs)
    workspace_files = await self._collect_candidate_files(task_id, state)

    # Merge: attach_tool files + workspace scan (deduplicate)
    attached_paths = set(attached_files)  # from AttachFileTool
    for wf in workspace_files:
        abs_path = str(Path(state.working_directory) / wf.file_name)
        if abs_path not in attached_paths:
            attachments.append(wf)

    await state.put_event(WaitConfirmData(
        task_id=task_id,
        content=orchestrator_reply,
        question=current_question,
        context="initial",
        attachments=attachments if attachments else None,
    ))
```

## Files to Modify

1. **`src/clients/desktop_app/ami_daemon/base_agent/core/orchestrator_agent.py`**
   - `create_orchestrator_agent()`: 新增 4 个 toolkit 的 import、初始化、加入 tools 列表
   - `ORCHESTRATOR_SYSTEM_PROMPT`: 追加文档工具说明

2. **`src/clients/desktop_app/ami_daemon/services/quick_task_service.py`**
   - Direct Response Path (~line 1981-2006): 追加 workspace 文件自动收集 + 合并逻辑

## Expected Behavior After Change

### Simple Task（直接处理）
```
User: "帮我查一下北京的天气，然后输出一个 PDF 和一个 DOC 文档"

Orchestrator:
  1. search_google("北京天气") → 获取天气数据
  2. write_to_file("weather_report.pdf", markdown_content) → 创建 PDF
  3. write_to_file("weather_report.docx", markdown_content) → 创建 DOCX
  4. attach_file("weather_report.pdf")
  5. attach_file("weather_report.docx")
  6. 回复：天气信息 + 附件
```

### Complex Task（仍然 decompose）
```
User: "去 Product Hunt 收集本周产品信息，写一个投资报告"

Orchestrator:
  1. 判断需要浏览网站 + 多步操作
  2. decompose_task → AMITaskPlanner → AMITaskExecutor → 多 Agent 协作
```

决策由 LLM 自主完成，我们只补齐工具，不干涉判断逻辑。
