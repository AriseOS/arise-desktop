# 统一使用 task_id 作为执行标识符

## 状态：已实现 ✅

## 背景

当前系统中存在两个用于标识 workflow 执行的 ID：

| ID | 格式 | 生成位置 | 存储 | 用途 |
|-----|------|---------|------|------|
| `task_id` | `task_{workflow_id}_{8字符随机}` | `workflow_executor.py` | 内存 | WebSocket、停止操作、状态查询 |
| `run_id` / `execution_id` | UUID | `workflow_history.py` | 文件系统 | 历史记录、持久化 |

**问题**：
1. 概念冗余：一次执行有两个 ID
2. 需要 `_task_context` 映射表关联两者
3. 历史记录返回 `run_id`，但 WebSocket 需要 `task_id`，导致无法从历史跳转到 LivePage

**解决方案**：统一使用 `task_id`，废弃 `run_id` / `execution_id`。

---

## 为什么选择保留 task_id 而非 run_id

| 考虑因素 | 保留 task_id | 保留 run_id |
|---------|-------------|-------------|
| ID 生成依赖 | 无依赖，直接生成 | 依赖 history_manager 可用 |
| 改动范围 | history 模块接收外部 ID | executor 核心逻辑改动 |
| Fallback | 天然支持（无 history 时仍可运行） | 需要额外 fallback 逻辑 |
| 现有 API | 保持不变 | 全部改名 |

**结论**：保留 `task_id` 改动更小、更安全。

---

## 改动概览

### 核心改动

1. **`workflow_history.py`**：`create_run()` 接收外部传入的 `task_id`
2. **`workflow_executor.py`**：移除 `_task_context` 映射，直接用 `task_id` 调用 history 方法
3. **历史 API**：返回字段从 `run_id` 改为 `task_id`
4. **前端**：历史列表中的 `running` 状态执行可直接跳转 LivePage

---

## 详细改动

### 1. `ami_daemon/services/workflow_history.py`

#### 1.1 `WorkflowRunMeta` 数据类

```python
# 改动前
@dataclass
class WorkflowRunMeta:
    run_id: str  # UUID
    ...

# 改动后
@dataclass
class WorkflowRunMeta:
    task_id: str  # 统一使用 task_id
    ...
```

#### 1.2 `create_run()` 方法

```python
# 改动前
def create_run(
    self,
    user_id: str,
    workflow_id: str,
    workflow_name: str,
    workflow_yaml: str,
    total_steps: int,
) -> str:
    # 内部生成 UUID
    execution_id = str(uuid.uuid4())
    ...
    meta = WorkflowRunMeta(
        run_id=execution_id,
        ...
    )
    return execution_id

# 改动后
def create_run(
    self,
    task_id: str,  # 新增：外部传入
    user_id: str,
    workflow_id: str,
    workflow_name: str,
    workflow_yaml: str,
    total_steps: int,
) -> str:
    # 使用外部传入的 task_id
    exec_path = self._get_execution_path(user_id, workflow_id, task_id)
    exec_path.mkdir(parents=True, exist_ok=True)

    meta = WorkflowRunMeta(
        task_id=task_id,  # 使用 task_id
        ...
    )
    return task_id
```

#### 1.3 其他方法参数名更新

所有使用 `execution_id` 或 `run_id` 作为参数的方法，统一改为 `task_id`：

- `log_step(user_id, workflow_id, task_id, ...)`
- `update_run_status(user_id, workflow_id, task_id, ...)`
- `mark_as_uploaded(user_id, workflow_id, task_id)`
- `get_run_meta(user_id, workflow_id, task_id)`
- `get_run_logs(user_id, workflow_id, task_id)`
- `get_run_for_upload(user_id, workflow_id, task_id)`
- `_get_execution_path(user_id, workflow_id, task_id)`
- `_find_execution_by_task_id(task_id)` (原 `_find_execution_by_run_id`)
- `get_run_meta_by_id(task_id)` (原 `get_run_meta_by_id(run_id)`)
- `get_run_logs_by_id(task_id)`
- `get_run_workflow_yaml_by_id(task_id)`
- `get_run_for_upload_by_id(task_id)`

#### 1.4 文件存储路径

```
# 改动前
~/.ami/users/{user_id}/workflows/{workflow_id}/executions/{uuid}/

# 改动后
~/.ami/users/{user_id}/workflows/{workflow_id}/executions/{task_id}/
# 例如: executions/task_workflow_abc123_def456/
```

---

### 2. `ami_daemon/services/workflow_executor.py`

#### 2.1 移除 `_task_context` 映射

```python
# 改动前
class WorkflowExecutor:
    def __init__(self, ...):
        self.tasks: Dict[str, ExecutionTask] = {}
        self._task_context: Dict[str, tuple[str, str, str]] = {}  # 移除
        ...

# 改动后
class WorkflowExecutor:
    def __init__(self, ...):
        self.tasks: Dict[str, ExecutionTask] = {}
        # _task_context 已移除，不再需要映射
        ...
```

#### 2.2 `execute_workflow_async()` 简化

```python
# 改动前
async def execute_workflow_async(self, ...):
    task_id = f"task_{workflow_id}_{uuid.uuid4().hex[:8]}"
    ...
    if self.history:
        execution_id = self.history.create_run(
            user_id=user_id,
            workflow_id=workflow_id,
            ...
        )
        self._task_context[task_id] = (user_id, workflow_id, execution_id)
    ...

# 改动后
async def execute_workflow_async(self, ...):
    task_id = f"task_{workflow_id}_{uuid.uuid4().hex[:8]}"
    ...
    if self.history:
        self.history.create_run(
            task_id=task_id,  # 直接传入 task_id
            user_id=user_id,
            workflow_id=workflow_id,
            ...
        )
    # 不再需要 _task_context 映射
    ...
```

#### 2.3 `_execute_workflow()` 中的 history 调用简化

```python
# 改动前
history_context = self._task_context.get(task_id)
...
if history_context and self.history:
    ctx_user_id, ctx_workflow_id, ctx_execution_id = history_context
    self.history.log_step(
        user_id=ctx_user_id,
        workflow_id=ctx_workflow_id,
        execution_id=ctx_execution_id,
        ...
    )

# 改动后
if self.history:
    self.history.log_step(
        user_id=user_id,
        workflow_id=task.workflow_id,
        task_id=task_id,  # 直接使用 task_id
        ...
    )
```

#### 2.4 `_cleanup_task_resources()` 简化

```python
# 改动前
def _cleanup_task_resources(self, task_id: str):
    if task_id in self.stop_signals:
        del self.stop_signals[task_id]
    if task_id in self.task_handles:
        del self.task_handles[task_id]
    if task_id in self._task_context:  # 移除
        del self._task_context[task_id]

# 改动后
def _cleanup_task_resources(self, task_id: str):
    if task_id in self.stop_signals:
        del self.stop_signals[task_id]
    if task_id in self.task_handles:
        del self.task_handles[task_id]
    # _task_context 已移除
```

---

### 3. `ami_daemon/daemon.py`

#### 3.1 API 模型更新

```python
# 改动前
class WorkflowHistoryEntry(BaseModel):
    run_id: str
    workflow_id: str
    ...

class WorkflowRunDetail(BaseModel):
    run_id: str
    ...

# 改动后
class WorkflowHistoryEntry(BaseModel):
    task_id: str  # 改名
    workflow_id: str
    ...

class WorkflowRunDetail(BaseModel):
    task_id: str  # 改名
    ...
```

#### 3.2 历史 API 端点更新

```python
# 改动前
@app.get("/api/v1/workflows/{workflow_id}/history/{run_id}")
async def get_workflow_run_detail(workflow_id: str, run_id: str, user_id: str):
    meta = history_manager.get_run_meta(user_id, workflow_id, run_id)
    ...
    return WorkflowRunDetailResponse(
        meta=WorkflowRunDetail(
            run_id=meta.run_id,
            ...
        ),
        ...
    )

# 改动后
@app.get("/api/v1/workflows/{workflow_id}/history/{task_id}")
async def get_workflow_run_detail(workflow_id: str, task_id: str, user_id: str):
    meta = history_manager.get_run_meta(user_id, workflow_id, task_id)
    ...
    return WorkflowRunDetailResponse(
        meta=WorkflowRunDetail(
            task_id=meta.task_id,
            ...
        ),
        ...
    )
```

#### 3.3 列表 API 响应更新

```python
# list_workflow_history 端点
return WorkflowHistoryListResponse(
    runs=[
        WorkflowHistoryEntry(
            task_id=r.task_id,  # 改名
            workflow_id=r.workflow_id,
            ...
        )
        for r in runs
    ],
    ...
)
```

---

### 4. 前端改动

#### 4.1 `src/pages/WorkflowDetailPage.jsx`

在 History tab 中，对 `running` 状态的执行添加"查看实时进度"按钮：

```jsx
// 在 execution-list 渲染中
{executions.map((execution) => (
  <div
    key={execution.task_id}  // 改用 task_id
    className={`execution-item ${getStatusClass(execution.status)}`}
    onClick={() => handleViewExecution(execution)}
  >
    <div className="execution-status">
      {getStatusIcon(execution.status)}
    </div>
    <div className="execution-info">
      <div className="execution-time">{formatTime(execution.started_at)}</div>
      <div className="execution-meta">
        <span className={`status-text ${getStatusClass(execution.status)}`}>
          {execution.status}
        </span>
      </div>
    </div>

    {/* 新增：运行中的执行显示 View Live 按钮 */}
    {execution.status === 'running' && (
      <button
        className="btn-view-live"
        onClick={(e) => {
          e.stopPropagation();
          onNavigate('workflow-execution-live', {
            taskId: execution.task_id,  // 直接使用 task_id
            workflowName: execution.workflow_name
          });
        }}
      >
        <Icon icon="eye" size={14} />
        View Live
      </button>
    )}

    <div className="execution-arrow">
      <Icon icon="chevronRight" size={16} />
    </div>
  </div>
))}
```

#### 4.2 `fetchExecutionDetail` 更新

```javascript
// 改动前
const fetchExecutionDetail = async (runId) => {
  const url = `/api/v1/workflows/${workflowId}/history/${runId}?user_id=${userId}`
  ...
}

// 改动后
const fetchExecutionDetail = async (taskId) => {
  const url = `/api/v1/workflows/${workflowId}/history/${taskId}?user_id=${userId}`
  ...
}
```

#### 4.3 CSS 样式（新增）

```css
/* 在 WorkflowDetailPage.css 中添加 */
.btn-view-live {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: var(--color-primary-500);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  margin-left: auto;
  margin-right: 8px;
}

.btn-view-live:hover {
  background: var(--color-primary-600);
}
```

---

## 实施步骤

### Phase 1: 后端 History 模块

1. 修改 `workflow_history.py`
   - `WorkflowRunMeta.run_id` -> `task_id`
   - `create_run()` 接收 `task_id` 参数
   - 所有方法的 `execution_id` / `run_id` 参数 -> `task_id`

### Phase 2: 后端 Executor 模块

2. 修改 `workflow_executor.py`
   - 移除 `_task_context` 映射
   - 调整 `create_run()` 调用，传入 `task_id`
   - 简化所有 history 调用

### Phase 3: 后端 API 层

3. 修改 `daemon.py`
   - `WorkflowHistoryEntry.run_id` -> `task_id`
   - `WorkflowRunDetail.run_id` -> `task_id`
   - 历史 API 路径参数 `run_id` -> `task_id`

### Phase 4: 前端

4. 修改 `WorkflowDetailPage.jsx`
   - 历史列表使用 `execution.task_id`
   - 添加 "View Live" 按钮
   - 添加相应 CSS 样式

### Phase 5: 测试

5. 测试场景
   - 新建执行，验证历史记录使用 task_id 存储
   - 从历史列表点击 "View Live" 跳转到 LivePage
   - 停止运行中的执行
   - 查看已完成执行的详情

---

## 兼容性考虑

### 旧数据迁移

现有历史记录使用 UUID 作为 `run_id`，存储在：
```
~/.ami/users/{user_id}/workflows/{workflow_id}/executions/{uuid}/
```

**处理方案**：
- 旧数据保持不变，仍可查看
- 新执行使用 `task_id` 格式
- `_find_execution_by_task_id()` 方法已支持按目录名查找，无需迁移

### API 向后兼容

如需保持旧 API 兼容，可以：
1. 在响应中同时返回 `run_id` 和 `task_id`（值相同）
2. 或保持 `run_id` 字段名，但值为 `task_id`

**建议**：直接改为 `task_id`，因为这是内部系统，无外部依赖。

---

## 收益总结

1. **概念统一**：一次执行 = 一个 ID (`task_id`)
2. **代码简化**：移除 `_task_context` 映射表
3. **功能启用**：历史记录可直接跳转 LivePage
4. **架构清晰**：`task_id` 贯穿整个执行生命周期
