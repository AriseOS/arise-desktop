# 前端 SSE 事件增强指南

## 背景

### 为什么需要这个文档？

后端已完成 Phase 3 和 Phase 5 的能力迁移（参考 `docs/eigent-capability-migration-plan.md`）：

- **Phase 3**: 增强失败处理 - 静默重试，只在最终失败时通知用户
- **Phase 5**: 增强 SSE 事件 - 新增 `assign_task` 和 `decompose_progress` 事件

这些后端能力需要前端配合才能完整展现给用户。本文档指导前端开发者如何修改代码以支持这些新能力。

### 用户体验提升

| 场景 | 修改前 | 修改后 |
|-----|-------|-------|
| 任务分配 | 直接显示"运行中" | 先显示"等待中"⏳，再变为"运行中"🔄 |
| 任务分解 | 只有流式文本 | 显示进度条 0% → 100%，带阶段描述 |
| 失败重试 | 每次失败都通知 | 静默重试，只在最终失败时显示 |
| 多 Agent 结果 | 显示最后一个结果 | 显示聚合摘要，可展开查看各 Agent 贡献 |

---

## 一、概述

本文档描述了为支持后端新增的 SSE 事件，前端需要进行的修改。这些修改将使前端能够：

1. **更细粒度地展示任务分配状态**：从单一状态升级为两阶段状态（waiting → running）
2. **显示任务分解进度**：实时展示 0-100% 的分解进度条
3. **更好地向用户传递多 Agent 协作的过程和结果**

---

## 二、新增后端事件

### 2.1 `assign_task` 事件（两阶段状态）

**用途**：任务分配给 Worker 时的状态追踪

**数据格式**：
```typescript
interface AssignTaskData {
  action: "assign_task";
  task_id: string;           // 主任务 ID
  assignee_id: string;       // Worker/Agent ID
  subtask_id: string;        // 子任务 ID
  content: string;           // 任务内容
  state: "waiting" | "running";  // 两阶段状态
  failure_count: number;     // 失败重试次数
  timestamp: string;
}
```

**两阶段说明**：
- **Phase 1 (`state: "waiting"`)**：任务已分配给 Worker，在队列中等待执行
- **Phase 2 (`state: "running"`)**：任务开始实际执行

### 2.2 `decompose_progress` 事件

**用途**：任务分解过程中的进度追踪

**数据格式**：
```typescript
interface DecomposeProgressData {
  action: "decompose_progress";
  task_id: string;
  progress: number;          // 0.0 到 1.0
  message: string;           // 进度消息，如 "Analyzing task complexity..."
  sub_tasks?: Array<{        // 仅在 is_final=true 时包含
    id: string;
    content: string;
    status: string;
  }>;
  is_final: boolean;         // 是否为最终状态
  timestamp: string;
}
```

**进度阶段**：
| 进度 | 消息 | 说明 |
|-----|------|------|
| 0% | "Starting task decomposition..." | 开始分解 |
| 20% | "Analyzing task complexity..." | 分析任务 |
| 50-80% | "Generating subtasks..." | 生成子任务（动态） |
| 100% | "Decomposition complete" | 分解完成 |

---

## 三、前端修改

### 3.1 agentStore.js - 状态初始化

**文件**：`src/clients/desktop_app/src/store/agentStore.js`

**修改位置**：`createInitialTaskState` 函数（约 line 57）

```javascript
const createInitialTaskState = (taskDescription = '', type = 'normal') => ({
  // ... 现有字段保持不变 ...

  // ===== 新增：任务分解进度状态 =====
  decompositionProgress: 0,        // 0-100 百分比
  decompositionMessage: '',        // 当前分解阶段描述
  decompositionStatus: 'pending',  // pending | decomposing | completed
});
```

### 3.2 agentStore.js - 更新 `assign_task` 处理

**修改位置**：`handleSSEEvent` 函数中的 `case 'assign_task'`（约 line 988）

**替换为**：

```javascript
// Eigent: assign_task event with two-phase state (waiting -> running)
case 'assign_task':
  {
    // 新字段来自后端: assignee_id, subtask_id, content, state, failure_count
    const {
      assignee_id,      // 后端新增
      subtask_id,       // 后端新增
      content,          // 后端新增
      state: taskState, // 后端新增: "waiting" | "running"
      failure_count = 0,
      // 兼容旧格式
      agent_id,
      task_id: assignedTaskId
    } = event.data || event;

    const actualAgentId = assignee_id || agent_id;
    const actualTaskId = subtask_id || assignedTaskId;

    if (!actualAgentId || !actualTaskId) break;

    const currentTask = store.tasks[taskId];
    if (!currentTask) break;

    let updatedTaskAssigning = [...(currentTask.taskAssigning || [])];
    let updatedTaskRunning = [...(currentTask.taskRunning || [])];

    const agentIndex = updatedTaskAssigning.findIndex(a => a.agent_id === actualAgentId);

    // Phase 1: waiting - 任务已分配，等待执行
    if (taskState === 'waiting') {
      if (agentIndex !== -1) {
        const existingTaskIndex = updatedTaskAssigning[agentIndex].tasks?.findIndex(
          t => t.id === actualTaskId
        );
        if (existingTaskIndex === -1 || existingTaskIndex === undefined) {
          updatedTaskAssigning[agentIndex] = {
            ...updatedTaskAssigning[agentIndex],
            tasks: [...(updatedTaskAssigning[agentIndex].tasks || []), {
              id: actualTaskId,
              content: content || '',
              status: 'waiting',
              failure_count
            }],
          };
        }
      }

      // 更新 taskRunning 状态为 waiting
      const taskExists = updatedTaskRunning.some(t => t.id === actualTaskId);
      if (taskExists) {
        updatedTaskRunning = updatedTaskRunning.map(t =>
          t.id === actualTaskId ? { ...t, status: 'waiting' } : t
        );
      }
    }
    // Phase 2: running - 任务正在执行
    else if (taskState === 'running' || !taskState) {
      if (agentIndex !== -1) {
        const existingTaskIndex = updatedTaskAssigning[agentIndex].tasks?.findIndex(
          t => t.id === actualTaskId
        );
        if (existingTaskIndex !== -1 && existingTaskIndex !== undefined) {
          // 更新现有任务状态为 running
          updatedTaskAssigning[agentIndex].tasks[existingTaskIndex] = {
            ...updatedTaskAssigning[agentIndex].tasks[existingTaskIndex],
            status: 'running',
            failure_count,
          };
        } else {
          // 添加新任务
          updatedTaskAssigning[agentIndex] = {
            ...updatedTaskAssigning[agentIndex],
            tasks: [...(updatedTaskAssigning[agentIndex].tasks || []), {
              id: actualTaskId,
              content: content || '',
              status: 'running',
              failure_count
            }],
          };
        }
      }

      // 更新 taskRunning 状态为 running
      updatedTaskRunning = updatedTaskRunning.map(t =>
        t.id === actualTaskId ? { ...t, status: 'running' } : t
      );
    }

    updateTask({
      taskRunning: updatedTaskRunning,
      taskAssigning: updatedTaskAssigning,
    });
  }
  break;
```

### 3.3 agentStore.js - 添加 `decompose_progress` 处理

**修改位置**：在 `handleSSEEvent` 的 switch 语句中，`case 'streaming_decompose'` 之后添加

```javascript
// 任务分解进度事件
case 'decompose_progress':
  {
    const { progress, message, sub_tasks, is_final } = event.data || event;

    const progressPercent = Math.round((progress || 0) * 100);

    updateTask({
      decompositionProgress: progressPercent,
      decompositionMessage: message || '',
      decompositionStatus: is_final ? 'completed' : 'decomposing',
    });

    // 如果是最终状态且有子任务，更新 taskInfo
    if (is_final && sub_tasks && Array.isArray(sub_tasks)) {
      updateTask({
        taskInfo: sub_tasks,
      });
    }

    console.log(`[SSE] decompose_progress: ${progressPercent}% - ${message}`);
  }
  break;
```

---

## 四、UI 组件修改

### 4.1 TaskCard.jsx - 分解进度条

**文件**：`src/clients/desktop_app/src/components/TaskBox/TaskCard.jsx`

**添加位置**：在任务分解显示区域（约 line 168 附近）

```jsx
{/* 任务分解进度条 */}
{task?.decompositionStatus === 'decomposing' && (
  <div className="decomposition-progress-container">
    <div className="decomposition-progress-bar">
      <div
        className="decomposition-progress-fill"
        style={{ width: `${task.decompositionProgress || 0}%` }}
      />
    </div>
    <div className="decomposition-progress-text">
      <span className="progress-message">
        {task.decompositionMessage || 'Decomposing...'}
      </span>
      <span className="progress-percent">
        {task.decompositionProgress || 0}%
      </span>
    </div>
  </div>
)}
```

**CSS 样式**（添加到对应的 CSS 文件）：

```css
.decomposition-progress-container {
  margin: 8px 0;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.decomposition-progress-bar {
  height: 4px;
  background: var(--border-color);
  border-radius: 2px;
  overflow: hidden;
}

.decomposition-progress-fill {
  height: 100%;
  background: var(--primary-color);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.decomposition-progress-text {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.progress-message {
  flex: 1;
}

.progress-percent {
  font-weight: 500;
  color: var(--primary-color);
}
```

### 4.2 TaskCard.jsx - 任务状态图标

**修改位置**：任务列表状态显示（约 line 222 附近）

**更新状态图标函数**：

```jsx
// 获取任务状态图标
const getStatusIcon = (status) => {
  switch (status) {
    case 'completed':
    case 'done':
      return <span className="status-icon completed">✓</span>;
    case 'failed':
      return <span className="status-icon failed">✗</span>;
    case 'running':
      return <Spinner size="sm" className="status-icon running" />;
    case 'waiting':
      return <span className="status-icon waiting">⏳</span>;
    case 'pending':
    case 'open':
      return <span className="status-icon pending">○</span>;
    case 'blocked':
      return <span className="status-icon blocked">⚠</span>;
    default:
      return <span className="status-icon pending">○</span>;
  }
};

// 获取状态标签文字
const getStatusLabel = (status) => {
  switch (status) {
    case 'waiting': return 'Waiting';
    case 'running': return 'Running';
    case 'completed':
    case 'done': return 'Done';
    case 'failed': return 'Failed';
    case 'pending':
    case 'open': return 'Pending';
    default: return status;
  }
};
```

**任务列表项显示**：

```jsx
{/* 任务项 */}
<div className={`task-item task-status-${task.status}`}>
  <div className="task-status-icon">
    {getStatusIcon(task.status)}
  </div>
  <div className="task-content">
    {task.content}
  </div>
  {task.failure_count > 0 && (
    <span className="retry-badge" title={`Retried ${task.failure_count} times`}>
      ↻{task.failure_count}
    </span>
  )}
</div>
```

---

## 五、状态流转图

### 5.1 任务分配状态流转

```
┌─────────────────────────────────────────────────────────┐
│                    assign_task 事件                      │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
         ┌────────────────────────────────┐
         │   state: "waiting"             │
         │   - 任务已分配给 Worker         │
         │   - 显示 ⏳ 等待图标           │
         │   - 任务在队列中等待           │
         └────────────────────────────────┘
                          │
                          ▼
         ┌────────────────────────────────┐
         │   state: "running"             │
         │   - 任务开始执行               │
         │   - 显示 🔄 旋转动画           │
         │   - Worker 正在处理            │
         └────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
    ┌──────────────────┐    ┌──────────────────┐
    │ subtask_state:   │    │ subtask_state:   │
    │ DONE             │    │ FAILED           │
    │ - 显示 ✓         │    │ - 显示 ✗         │
    └──────────────────┘    └──────────────────┘
```

### 5.2 任务分解进度流转

```
┌─────────────────────────────────────────────────────────┐
│                 decompose_progress 事件                  │
└─────────────────────────────────────────────────────────┘
                          │
    ┌─────────────────────┼─────────────────────┐
    ▼                     ▼                     ▼
┌──────────┐        ┌──────────┐        ┌──────────┐
│ 0%       │   →    │ 20%      │   →    │ 50-80%   │
│ Starting │        │ Analyzing│        │ Generating│
└──────────┘        └──────────┘        └──────────┘
                                              │
                                              ▼
                                        ┌──────────┐
                                        │ 100%     │
                                        │ Complete │
                                        │ is_final │
                                        └──────────┘
                                              │
                                              ▼
                                        ┌──────────┐
                                        │ task_    │
                                        │ decomposed│
                                        │ 事件      │
                                        └──────────┘
```

---

## 六、结果传递给用户

### 6.1 当前流程（无需修改）

1. **后端发送** `task_completed` 事件：
   ```json
   {
     "action": "task_completed",
     "task_id": "abc12345",
     "output": "任务执行结果...",
     "notes": "执行笔记...",
     "tools_called": [...],
     "duration_seconds": 45.2
   }
   ```

2. **agentStore.js 处理**：
   - 更新 `status: 'completed'`
   - 存储 `result: event.output`
   - 调用 `addMessage('assistant', event.output)`

3. **MessageList.jsx 显示**：
   - 渲染助手消息
   - 支持 Markdown 格式

### 6.2 多 Agent 协作结果增强（可选）

对于涉及多个 Agent 的任务，后端的 `TaskSummaryAgent` 会生成聚合摘要。前端可以选择性地展示更多细节：

```jsx
{/* 多 Agent 结果摘要 */}
{task?.taskAssigning?.length > 1 && task?.status === 'completed' && (
  <div className="multi-agent-summary">
    <div className="summary-header">
      <span>Task completed by {task.taskAssigning.length} agents</span>
      <button onClick={() => toggleDetails()}>
        {showDetails ? 'Hide Details' : 'Show Details'}
      </button>
    </div>

    {showDetails && (
      <div className="agent-contributions">
        {task.taskAssigning.map(agent => (
          <div key={agent.agent_id} className="agent-contribution">
            <div className="agent-name">{agent.name}</div>
            <div className="tasks-completed">
              {agent.tasks.filter(t => t.status === 'completed').length} tasks completed
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
)}
```

---

## 七、测试场景

### 7.1 assign_task 两阶段状态

**测试步骤**：
1. 提交一个需要分解的复杂任务
2. 观察子任务被分配时的状态变化
3. 验证 ⏳ (waiting) → 🔄 (running) → ✓/✗ (done/failed) 的流转

**预期结果**：
- 任务分配后先显示 ⏳ 等待图标
- 任务开始执行后显示旋转动画
- 完成后显示对应状态图标

### 7.2 decompose_progress 进度条

**测试步骤**：
1. 提交一个复杂任务
2. 观察任务分解过程中的进度条
3. 验证进度从 0% → 100% 的变化

**预期结果**：
- 显示进度条和百分比
- 显示当前阶段描述文字
- 分解完成后进度条消失，显示子任务列表

---

## 八、兼容性说明

### 8.1 后端兼容

新事件与现有事件并行发送：
- `assign_task` 与 `worker_assigned` 同时发送
- `decompose_progress` 与 `streaming_decompose` 同时发送

前端可以根据需要选择性处理。

### 8.2 前端兼容

代码保持向后兼容：
- `assign_task` 处理同时支持新旧字段格式
- 缺少 `state` 字段时默认为 `running`

---

## 九、文件修改清单

| 文件 | 修改内容 | 优先级 |
|-----|---------|-------|
| `src/store/agentStore.js` | 添加 `decompositionProgress` 等状态字段 | P0 |
| `src/store/agentStore.js` | 更新 `assign_task` 事件处理 | P0 |
| `src/store/agentStore.js` | 添加 `decompose_progress` 事件处理 | P0 |
| `src/components/TaskBox/TaskCard.jsx` | 添加分解进度条 UI | P1 |
| `src/components/TaskBox/TaskCard.jsx` | 更新状态图标（waiting） | P1 |
| `src/components/TaskBox/TaskCard.css` | 添加进度条样式 | P1 |

---

## 十、参考

- 后端事件定义：`src/clients/desktop_app/ami_daemon/base_agent/events/action_types.py`
- 后端事件发送：`src/clients/desktop_app/ami_daemon/base_agent/core/ami_workforce.py`
- Eigent 前端参考：`third-party/eigent/src/store/chatStore.ts`
