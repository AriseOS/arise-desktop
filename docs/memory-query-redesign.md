# Memory Query 重设计

## 一、设计思路

### 服务端逻辑

```
任务查询 (query_task)
    │
    ▼
[L1] CognitivePhrase 匹配 (LLM 判断是否可以 replay)
    │
    ├─ 命中 → 返回 cognitive_phrase + states + actions
    │
    ▼ 未命中
[L2] 路径检索 (embedding + BFS 反向遍历)
    │
    ├─ 找到路径 → 记录为 global_path
    │              │
    │              ▼
    │         [L3a] 用 global_path 分解子任务
    │              │
    │              ▼
    │         返回: global_path (states/actions) + subtasks
    │
    ▼ 未找到路径
[L3b] 直接分解子任务 (无路径上下文)
    │
    ▼
返回: subtasks (无 global_path)
```

**关键点：**
1. L2 的路径作为**全局参考路径** (global_path)，独立返回
2. subtasks 不再每个都携带完整路径，只携带 `path_state_indices` 引用
3. 返回结构清晰：`global_path` + `subtasks` 是两个独立的字段

### 客户端逻辑

```
收到 query_task 结果
    │
    ├─ 有 cognitive_phrase → replay (暂不实现)
    │
    ├─ 有 subtasks
    │      │
    │      ├─ 有 global_path → 作为 workflow_guide 参考
    │      │
    │      └─ 无 global_path → 也没关系，继续执行
    │
    ▼
执行每个 subtask
    │
    ▼
[每个 subtask 开始时]
    │
    ├─ 参考 global_path (如果有)
    │
    └─ 根据当前 URL 查询 navigation (query_navigation)
       - start_state: 当前页面 URL 或 state_id
       - end_state: subtask 对应的 target_state_id (来自 path_state_indices)
```

**关键点：**
1. global_path 是高层参考，不是每个 subtask 都执行完整路径
2. 每个 subtask 执行时，根据**当前实际位置**查询到目标的路径
3. subtask 的 end_state 应该用 state_id（来自 path_state_indices），而不是任务描述

---

## 二、当前代码问题

### 问题 1: 服务端 L3a 重复存储路径

**文件**: `src/cloud_backend/memgraph/reasoner/reasoner.py`

**当前代码 (L920-931)**:
```python
subtasks: List[SubTaskResult] = []
for st_data in output.subtasks:
    indices = st_data.get("path_state_indices", [])
    # Every subtask carries the full path as navigation context.
    # path_state_indices only marks where on the path this subtask operates.
    subtasks.append(SubTaskResult(
        task_id=st_data.get("task_id", f"task_{len(subtasks)+1}"),
        target=st_data.get("target", ""),
        states=path_states,      # ❌ 每个 subtask 都存完整路径
        actions=path_actions,    # ❌ 每个 subtask 都存完整路径
        found=len(indices) > 0,
    ))
```

**当前代码 (L647-663)**:
```python
# Collect states/actions from subtasks that have navigation info
all_states: List[State] = []
all_actions: List[Action] = []
for st in subtasks:
    if st.found:
        all_states.extend(st.states)   # ❌ 合并 N 份重复路径
        all_actions.extend(st.actions) # ❌ 合并 N 份重复路径

# ...
return QueryResult.task_success(
    states=all_states,      # ❌ 返回 N 倍重复的路径
    actions=all_actions,    # ❌ 返回 N 倍重复的路径
    subtasks=subtasks,
    metadata={"method": method},
)
```

**问题**:
- 每个 subtask 都存储完整路径，浪费空间
- 合并后返回 N 倍重复的 states/actions
- 客户端无法区分 global_path 和 subtask 的路径

### 问题 2: SubTaskResult 模型缺少 path_state_indices

**文件**: `src/cloud_backend/memgraph/ontology/query_result.py`

**当前代码 (L20-27)**:
```python
class SubTaskResult(BaseModel):
    """Result for a single subtask from task decomposition."""

    task_id: str = Field(..., description="Subtask identifier")
    target: str = Field(..., description="Subtask target description")
    states: List[State] = Field(default_factory=list)  # ❌ 存完整路径
    actions: List[Action] = Field(default_factory=list) # ❌ 存完整路径
    found: bool = Field(default=False)
```

**问题**: 没有 `path_state_indices` 字段来引用全局路径中的位置

### 问题 3: 客户端用任务描述查 navigation

**文件**: `src/clients/desktop_app/ami_daemon/base_agent/agents/eigent_style_browser_agent.py`

**当前代码 (L2044-2049)**:
```python
page_title = await self._browser_toolkit.get_page_title()
if page_title:
    nav_result = await self._memory_toolkit.query_navigation(
        start_state=page_title,              # 当前页面标题
        end_state=current_subtask.content,   # ❌ 任务描述，不是 state
    )
```

**问题**:
- `end_state` 用的是任务描述（如 "Execute a search on Amazon..."）
- 服务端用这个描述去匹配 state，大概率匹配不上
- 应该用 subtask 对应的 target_state_id

---

## 三、修复方案

### 3.1 修改 SubTaskResult 模型

**文件**: `src/cloud_backend/memgraph/ontology/query_result.py`

```python
class SubTaskResult(BaseModel):
    """Result for a single subtask from task decomposition."""

    task_id: str = Field(..., description="Subtask identifier")
    target: str = Field(..., description="Subtask target description")

    # 引用全局路径中的位置，而不是存储完整路径
    path_state_indices: List[int] = Field(
        default_factory=list,
        description="Indices into global path states that this subtask operates on"
    )

    # 保留 found 字段
    found: bool = Field(
        default=False,
        description="Whether this subtask has navigation info (path_state_indices non-empty)"
    )

    # 删除 states 和 actions 字段，改用 path_state_indices 引用
```

### 3.2 修改 _query_task 返回逻辑

**文件**: `src/cloud_backend/memgraph/reasoner/reasoner.py`

```python
async def _query_task(self, target: str) -> QueryResult:
    # === L1: CognitivePhrase match ===
    can_satisfy, phrases, reasoning = await self.phrase_checker.check(target)
    if can_satisfy and phrases:
        # ... 保持不变 ...
        pass

    # === L2: Path retrieval ===
    path_result = await self._find_navigation_path(target)

    # === L3: Task decomposition ===
    global_states: List[State] = []
    global_actions: List[Action] = []

    if path_result and path_result["paths"]:
        best_path = path_result["paths"][0]
        global_states = best_path["states"]   # L2 的全局路径
        global_actions = best_path["actions"]
        subtasks = await self._decompose_with_path(target, best_path)
        method = "path_decomposition"
    else:
        subtasks = await self._decompose_without_path(target)
        method = "direct_decomposition"

    has_global_path = len(global_states) > 0

    return QueryResult.task_success(
        states=global_states,    # L2 的全局路径 (不重复)
        actions=global_actions,  # L2 的全局路径 (不重复)
        subtasks=subtasks,       # subtasks 只包含 path_state_indices
        metadata={
            "method": method,
            "has_global_path": has_global_path,
        },
    )
```

### 3.3 修改 _decompose_with_path

**文件**: `src/cloud_backend/memgraph/reasoner/reasoner.py`

```python
async def _decompose_with_path(
    self, target: str, path: Dict[str, Any]
) -> List[SubTaskResult]:
    """L3a: Decompose target into subtasks using path as navigation context."""
    path_states: List[State] = path["states"]

    # ... LLM 分解逻辑保持不变 ...

    subtasks: List[SubTaskResult] = []
    for st_data in output.subtasks:
        indices = st_data.get("path_state_indices", [])
        subtasks.append(SubTaskResult(
            task_id=st_data.get("task_id", f"task_{len(subtasks)+1}"),
            target=st_data.get("target", ""),
            path_state_indices=indices,  # 只存索引，不存完整路径
            found=len(indices) > 0,
        ))

    return subtasks
```

### 3.4 修改客户端处理逻辑

**文件**: `src/clients/desktop_app/ami_daemon/base_agent/agents/eigent_style_browser_agent.py`

```python
# 处理 memory_result
if memory_result.subtasks:
    # 保存全局路径
    self._global_path_states = memory_result.states   # L2 的全局路径
    self._global_path_actions = memory_result.actions

    # 构建 subtask 到 target_state 的映射
    self._subtask_target_states = {}
    for st in memory_result.subtasks:
        if st.path_state_indices:
            # 取该 subtask 涉及的最后一个 state 作为 target
            last_idx = st.path_state_indices[-1]
            if last_idx < len(memory_result.states):
                self._subtask_target_states[st.task_id] = memory_result.states[last_idx]

# 每个 subtask 执行时查询 navigation
if current_subtask:
    # 获取当前页面 URL
    current_url = await self._browser_toolkit.get_current_url()

    # 获取该 subtask 的 target state
    target_state = self._subtask_target_states.get(current_subtask.id)

    if target_state:
        nav_result = await self._memory_toolkit.query_navigation(
            start_state=current_url,           # 当前 URL
            end_state=target_state.id,         # target state ID
        )
```

---

## 四、数据流示例

### 查询: "在亚马逊搜索 AI 眼镜"

**L2 找到全局路径:**
```
global_path:
  states: [
    State(id="s1", page_title="Amazon 首页"),
    State(id="s2", page_title="搜索结果页"),
    State(id="s3", page_title="产品详情页"),
  ]
  actions: [
    Action(s1 -> s2, "搜索"),
    Action(s2 -> s3, "点击产品"),
  ]
```

**L3a 分解子任务:**
```
subtasks: [
  SubTaskResult(
    task_id="task_1",
    target="打开亚马逊首页",
    path_state_indices=[0],    # 引用 states[0]
    found=True
  ),
  SubTaskResult(
    task_id="task_2",
    target="搜索 AI 眼镜",
    path_state_indices=[0, 1], # 操作范围: states[0] -> states[1]
    found=True
  ),
  SubTaskResult(
    task_id="task_3",
    target="查看产品详情",
    path_state_indices=[1, 2], # 操作范围: states[1] -> states[2]
    found=True
  ),
]
```

**返回给客户端:**
```json
{
  "query_type": "task",
  "success": true,
  "states": [State(s1), State(s2), State(s3)],  // 全局路径，只有一份
  "actions": [Action(s1->s2), Action(s2->s3)],  // 全局路径，只有一份
  "subtasks": [
    {"task_id": "task_1", "target": "...", "path_state_indices": [0], "found": true},
    {"task_id": "task_2", "target": "...", "path_state_indices": [0, 1], "found": true},
    {"task_id": "task_3", "target": "...", "path_state_indices": [1, 2], "found": true}
  ],
  "metadata": {"method": "path_decomposition", "has_global_path": true}
}
```

**客户端执行 task_2 时:**
```python
# task_2 的 path_state_indices = [0, 1]
# target_state = states[1] = State(id="s2", page_title="搜索结果页")

current_url = "https://amazon.com/"  # 当前在首页

nav_result = query_navigation(
    start_state=current_url,    # 或用 current state_id
    end_state="s2"              # target state ID
)
# 返回: states[s1] -> states[s2], action: 搜索
```
