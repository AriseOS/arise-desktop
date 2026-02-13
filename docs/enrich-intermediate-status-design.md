# Enrich Intermediate Status Messages

## Problem

Users currently see sparse, uninformative messages during complex task execution:

```
这是一个复杂任务，正在拆解为子任务...     ← 然后沉默
开始执行 3 个子任务...                    ← 又沉默
正在执行: Visit producthunt.com...        ← 不知道进度
✓ 完成: Visit producthunt.com...
执行完成：3 成功，0 失败                  ← 终于结束了
```

用户在等待过程中不知道：
1. 系统是否找到了历史工作流记忆（Memory L1/L2/L3）
2. 任务被拆解成了哪些子任务
3. Agent 在思考什么（thinking 内容只在有 tool call 时才显示）
4. 当前执行到第几个子任务了

## Solution

通过现有的 `agent_report` SSE 事件，在关键节点发送更丰富的中间状态消息。使用 Markdown + `<details>/<summary>` HTML 实现渐进式展开（先摘要，点击展开详情）。

### New Message Timeline

| # | When | Message | report_type |
|---|------|---------|-------------|
| 1 | 任务确认为复杂任务 | "这是一个复杂任务，正在拆解为子任务..." | thinking |
| 2 | **Memory 查询完成** | **"找到完整工作流记忆 (L1 精确匹配)..."** + 可展开步骤列表 | info |
| 3 | **分解完成** | **"任务已拆解为 3 个子任务"** + 可展开子任务详情 | info |
| 4 | 开始执行 | "开始执行 3 个子任务..." | info |
| 5 | 子任务开始 | **"[1/3]** 正在执行: Visit producthunt.com..." | info |
| 6 | Agent 思考 (tool call) | "I'll navigate to the leaderboard..." | thinking |
| 7 | 子任务完成 | **"✓ [1/3]** 完成: Visit producthunt.com..." | success |
| 8 | 子任务开始 | **"[2/3]** 正在执行: Extract products..." | info |
| ... | ... | ... | ... |
| N | 全部完成 | "全部 3 个子任务执行完成！" | success |

**加粗** 部分为新增/修改的内容。

## Implementation

### Backend Changes

#### 1. Memory Query Result Message

**File**: `src/clients/desktop_app/ami_daemon/base_agent/core/ami_task_planner.py`
**Location**: `_query_task_memory()` method, after `MemoryLevelData` emission

在 Memory 查询完成后，向用户发送一条包含查询结果的消息：

```python
# L1: 完整工作流匹配
memory_summary = "**找到完整工作流记忆** (L1 精确匹配)\n\n"
memory_summary += "系统在记忆中找到了与此任务匹配的完整工作流\n\n"
memory_summary += "<details>\n<summary>查看工作流步骤</summary>\n\n"
for i, state in enumerate(cognitive_phrase.states, 1):
    memory_summary += f"{i}. {state.description or state.page_url}\n"
memory_summary += "\n</details>"

# L2: 部分路径匹配
memory_summary = f"**找到部分导航记忆** (L2 路径匹配)\n\n"
memory_summary += f"系统在记忆中找到了 {len(result.states)} 个相关页面状态"

# L3: 无匹配
memory_summary = "**未找到历史工作流记忆** (L3)\n\n系统将通过实时探索完成任务"

await self._emit_event(AgentReportData(
    task_id=self.task_id,
    message=memory_summary,
    report_type="info",
))
```

#### 2. Subtask Decomposition Message

**File**: `src/clients/desktop_app/ami_daemon/services/quick_task_service.py`
**Location**: After `TaskDecomposedData` emission (~line 1829)

```python
agent_type_labels = {
    "browser": "浏览器", "document": "文档",
    "code": "开发", "multi_modal": "多媒体",
}
subtask_lines = []
for st in subtasks:
    label = agent_type_labels.get(st.agent_type, st.agent_type)
    preview = st.content[:100] + ("..." if len(st.content) > 100 else "")
    deps = f" (依赖: {', '.join(st.depends_on)})" if st.depends_on else ""
    subtask_lines.append(f"{st.id}. **[{label}]** {preview}{deps}")

message = (
    f"**任务已拆解为 {len(subtasks)} 个子任务**\n\n"
    f"<details>\n<summary>查看子任务详情</summary>\n\n"
    f"{chr(10).join(subtask_lines)}\n\n</details>"
)

await state.put_event(AgentReportData(
    task_id=task_id, message=message, report_type="info",
))
```

#### 3. Subtask Progress Counters

**File**: `src/clients/desktop_app/ami_daemon/base_agent/core/ami_task_executor.py`

`_emit_subtask_running()`:
```python
# Before:
message=f"正在执行: {content_preview}"
# After:
done = sum(1 for s in self._subtasks if s.state == SubtaskState.DONE)
total = len(self._subtasks)
message=f"[{done + 1}/{total}] 正在执行: {content_preview}"
```

`_emit_subtask_state()` (DONE):
```python
# Before:
message=f"✓ 完成: {content_preview}"
# After:
done = sum(1 for s in self._subtasks if s.state == SubtaskState.DONE)
total = len(self._subtasks)
message=f"✓ [{done}/{total}] 完成: {content_preview}"
```

`_emit_subtask_state()` (FAILED):
```python
# Before:
message=f"✗ 失败: {content_preview}"
# After:
finished = sum(1 for s in self._subtasks if s.state in (SubtaskState.DONE, SubtaskState.FAILED))
total = len(self._subtasks)
message=f"✗ [{finished}/{total}] 失败: {content_preview}"
```

### Frontend Changes

#### 4. Enable `<details>` HTML Rendering

**Problem**: ReactMarkdown sanitizes HTML by default, `<details>/<summary>` won't render.
**Solution**: Add `rehype-raw` plugin.

```bash
cd src/clients/desktop_app && npm install rehype-raw
```

**Files to modify**:

`src/clients/desktop_app/src/pages/HomePage.jsx`:
```jsx
import rehypeRaw from 'rehype-raw';
// ...
<ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
  {message.content}
</ReactMarkdown>
```

`src/clients/desktop_app/src/components/ChatBox/MessageItem/AgentMessage.jsx`:
```jsx
import rehypeRaw from 'rehype-raw';
// ...
<ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
  {content}
</ReactMarkdown>
```

#### 5. CSS for Progressive Disclosure

**File**: `src/clients/desktop_app/src/styles/HomePage.css` (after report type styles)

```css
/* Progressive disclosure: <details>/<summary> */
.message.agent .message-bubble details {
  margin: 8px 0 4px 0;
  border: 1px solid var(--border-subtle, #e5e7eb);
  border-radius: 6px;
  overflow: hidden;
}

.message.agent .message-bubble details summary {
  padding: 6px 10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary, #666);
  cursor: pointer;
  background: var(--bg-secondary, #f9fafb);
  user-select: none;
}

.message.agent .message-bubble details summary:hover {
  background: var(--bg-hover, #f3f4f6);
}

.message.agent .message-bubble details[open] summary {
  border-bottom: 1px solid var(--border-subtle, #e5e7eb);
}

.message.agent .message-bubble details > :not(summary) {
  padding: 8px 10px;
  font-size: 13px;
  line-height: 1.6;
}
```

## Architecture

No new event types or data models needed. All changes use existing `AgentReportData`:

```
AgentReportData(
    task_id: str,
    message: str,      # Markdown + <details> HTML
    report_type: str,   # "info" | "thinking" | "success" | ...
)
```

SSE event flow remains unchanged:

```
Python Backend                  Frontend
─────────────────               ──────────────────
AgentReportData  ──SSE──>  agentStore.js
                            case 'agent_report':
                              addMessage('agent', message, {reportType})
                                    │
                                    ▼
                            MessageList.jsx / HomePage.jsx
                              ReactMarkdown + rehypeRaw
                              renders Markdown + <details>
```

## Files Modified

| File | Change |
|------|--------|
| `ami_task_planner.py` | Add Memory summary `AgentReportData` after query |
| `quick_task_service.py` | Add subtask list `AgentReportData` after decomposition |
| `ami_task_executor.py` | Add `[N/M]` progress counters to running/done/failed messages |
| `HomePage.jsx` | Add `rehype-raw` plugin to ReactMarkdown |
| `AgentMessage.jsx` | Add `rehype-raw` plugin to ReactMarkdown |
| `HomePage.css` | Add `<details>/<summary>` CSS |

## Security Note

`rehype-raw` allows raw HTML in Markdown. Since all `agent_report` messages are generated by our backend code (not user input), XSS risk is minimal. If needed, `rehype-sanitize` can whitelist only `details` and `summary` tags.
