# Replan Toolkit 设计：Agent 主动发起的动态任务拆分

## 1. 需求分析

### 1.1 核心问题

LLM Agent 在执行包含大量条目的任务时倾向于"偷懒"——提取几条数据后就草草收场，用类似"我已经收集了足够数据，让我来整理结果"的话术提前结束。这是 LLM 的普遍行为模式，不是 bug。

**典型场景**：用户要求"从 ProductHunt 提取排名前 19 的产品"，Agent 的实际行为：
1. 提取了 5 个产品
2. 说"考虑到产品数量较多，让我先整理已收集的信息"
3. 返回不完整的结果，状态标记为 "DONE"

### 1.2 当前架构为什么无法解决

AMI 的任务执行管线：

```
AMITaskPlanner → [子任务 1, 2, 3, ...] → AMITaskExecutor → 顺序执行
                  ↑ 规划时固定                ↑ 执行中不可修改
```

**根本原因**：子任务列表在规划阶段就已冻结。一旦 `AMITaskExecutor.execute()` 开始运行，无法添加、删除或修改任何子任务。Agent 没有机制表达"这个任务太大了，让我拆分一下"。

问题发生在**单个子任务的执行过程中**，而非子任务之间。子任务以不完整的结果"成功完成"——没有失败发生，因此不会触发 retry/replan。

### 1.3 Eigent 的做法（以及为什么不够）

Eigent（我们在 `third-party/eigent/` 中的参考项目）有两种 replan 机制：

| 机制 | 触发方式 | 工作原理 |
|------|----------|----------|
| 前端任务修改 | 用户点击 添加/删除/编辑 | HTTP 接口 → `workforce.add_task()` / `remove_task()` |
| CAMEL FailureHandlingConfig | 任务执行**失败**后 | LLM 分析失败原因 → retry / replan / decompose / reassign |

**为什么 Eigent 的方案解决不了我们的问题**：
- 前端修改需要用户手动干预——违背自动化初衷
- FailureHandlingConfig 只在**失败**时触发——而我们的问题是"偷懒但标记成功"
- 两者都依赖 CAMEL Workforce（约 6000 行代码）——我们已经弃用 CAMEL

## 2. 方案设计：Agent 主动发起的 Replan 工具

### 2.1 核心思路

给正在执行的 Agent 提供一个**工具**，让它可以动态地向 executor 的队列中追加子任务。Agent 可以自组织：当它感知到任务涉及大量条目时，先处理一批，然后为剩余部分追加后续任务。

```
Agent 正在执行 "提取 19 个产品"
  → 提取了产品 1-5
  → 调用 replan_review_context() 查看全局状态
  → 调用 replan_split_and_handoff(
      summary="产品 1-5: [数据]",
      tasks=[
        {"content": "提取产品 6-10", "agent_type": "browser"},
        {"content": "提取产品 11-15", "agent_type": "browser"},
        {"content": "提取产品 16-19", "agent_type": "browser"},
      ]
    )
  → Executor 追加 3 个新子任务（自动 depends_on 当前子任务）
  → 当前子任务标记为 DONE，结果为部分数据
  → Executor 继续执行下一个子任务 → "提取产品 6-10"
  → ... 循环直到全部完成
```

### 2.2 关键设计决策

**决策 1：Agent 主动发起，而非系统自动检测**

我们把工具交给 Agent，让 LLM 自行判断何时使用，通过 prompt 指令引导。我们**不**自动检测"偷懒完成"——那需要结果质量评估，容易误判且过度工程化。

**决策 2：工具在 executor 层面，而非 planner 层面**

Replan 发生在执行时，而非规划时。AMITaskPlanner 的分解逻辑保持不变。动态任务在 `AMITaskExecutor.execute()` 过程中追加。

**决策 3：新任务始终依赖当前子任务**

当 Agent 追加后续任务时，这些任务自动 `depends_on` 当前正在执行的子任务。这确保了：
- 当前子任务先完成（其结果可供后续任务使用）
- 不会产生循环依赖
- Executor 现有的依赖解析逻辑天然适用

**决策 4：参数使用 JSON 字符串，而非复杂类型**

工具参数使用 `str`（JSON 字符串）而非 `List[Dict]`。部分 API 代理会错误序列化复杂类型。`str` + `json.loads()` 在不同 LLM 提供商之间更稳健。

## 3. 场景评估

### 3.1 主路径：大量数据提取

**任务**："从 Amazon 提取 20 款 AI 眼镜"

**无 replan 工具（当前行为）**：
```
子任务: "提取 20 款 AI 眼镜"
  → Agent 提取了 5-8 款
  → Agent: "我已经收集了足够数据..."
  → 结果: 只有 5-8 款，而非 20 款
```

**有 replan 工具**：
```
子任务: "提取 20 款 AI 眼镜"
  → Agent 提取了 5 款
  → Agent 调用 replan_review_context() 查看全局状态
  → Agent 调用 replan_split_and_handoff(
      summary="第 1-5 款: [数据]",
      tasks=[{"content": "提取第 6-10 款", "agent_type": "browser"}, ...]
    )
  → 创建 3 个新子任务
  → 每个后续子任务接续前一个的进度
  → 最终结果: 4 个子任务共完成 20 款
```

### 3.2 小任务：无需 Replan

**任务**："查一下北京天气"

Agent 一次性完成任务。Replan 工具可用但不会被调用。无额外开销。

### 3.3 多步工作流：Agent 发现额外工作

**任务**："对比 iPhone 16 在 5 个电商平台的价格"

```
子任务 1: "访问 Amazon 获取 iPhone 16 价格"  → DONE
子任务 2: "访问 eBay 获取 iPhone 16 价格"    → DONE
子任务 3: "整理对比报告"
  → Agent 意识到还需要运费信息
  → 调用 replan_review_context() 查看已有结果
  → 调用 replan_split_and_handoff(
      summary="已整理 Amazon 和 eBay 价格对比，但缺少运费",
      tasks=[
        {"content": "获取 Amazon iPhone 16 运费", "agent_type": "browser"},
        {"content": "获取 eBay iPhone 16 运费", "agent_type": "browser"},
      ]
    )
  → 创建 2 个新子任务, depends_on 子任务 3
  → 新子任务执行 → 结果可供最终汇总使用
```

### 3.4 边界情况：Agent 不调用 Replan 工具

**场景**：尽管有 replan 工具，Agent 仍然做了 5/19 就开始总结。

这种情况可能发生——工具是建议性的，不是强制性的。缓解措施：
- Prompt 工程：用 "CRITICAL RULE" 明确指令，处理超过 5 个条目时必须使用 replan
- 这是 prompt 质量问题，不是架构问题——可以迭代优化

### 3.5 边界情况：非浏览器任务

**场景**：文档 Agent 创建一份 50 页的报告。

Replan 工具适用于**所有** Agent 类型，不仅限于浏览器。文档 Agent 也可以拆分：
- "撰写第 1-3 节" → split_and_handoff → "撰写第 4-6 节", "撰写第 7-9 节"

### 3.6 边界情况：动态追加的任务本身也需要拆分

**场景**："提取第 6-10 款"本身仍然太多（比如每款需要浏览 3 个页面）。

动态子任务同样会被注入 replan 工具。它可以递归拆分：
- "提取第 6-10 款" → split_and_handoff → "提取第 6-8 款", "提取第 9-10 款"

## 4. 优缺点分析

### 4.1 优点

| 优势 | 说明 |
|------|------|
| **直击核心问题** | Agent 可以自组织大任务，而非偷工减料 |
| **零前端改动** | `DynamicTasksAddedData` SSE 事件已定义并处理 |
| **轻量级** | 约 150 行新代码（toolkit）+ 约 80 行 executor 改动 |
| **无 CAMEL 依赖** | 纯 AMI 实现，无框架耦合 |
| **向后兼容** | 现有任务不受影响；replan 工具是纯增量 |
| **可观测** | 每次动态添加任务都会发送 SSE 事件 → 前端实时更新 |
| **Agent 类型无关** | 适用于 browser、document、code、multi_modal 所有 Agent |

### 4.2 缺点

| 缺点 | 说明 | 缓解措施 |
|------|------|----------|
| **依赖 LLM 遵从性** | Agent 可能仍然不使用该工具 | Prompt 工程 + 迭代优化 |
| **额外 token 开销** | 工具定义 + 指令每个子任务增加约 500 tokens | 边际成本 vs 收益可接受 |
| **可能的碎片化** | 过多小子任务 = 每次 agent.reset() 的开销 | Prompt 引导合理的批次大小 |
| **结果聚合** | 拆分的结果需要由下游任务合并 | 依赖结果已通过 prompt 注入 |
| **浏览器状态连续性** | 每个新子任务从当前 URL 开始，但不了解详细页面状态 | 浏览器上下文（URL + 标题）会被捕获并注入 |
| **无质量校验** | 不校验 Agent 的部分结果是否正确 | 超出本次范围；后续可按需添加 |

### 4.3 替代方案对比

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| **Agent 主动 replan 工具（本方案）** | 主动式、轻量级、无框架依赖 | 依赖 LLM 遵从性 | **采纳** |
| **自动结果校验** | 事后捕获偷懒完成 | 难以定义"足够"；误报多；过度工程化 | 否决 |
| **规划时强制拆分** | 在分解阶段拆分；覆盖有保障 | Planner 无法预测精确数量；过于死板 | 否决 |
| **前端发起（Eigent 模式）** | 用户拥有完全控制权 | 需要手动干预；违背自动化 | 否决 |
| **CAMEL FailureHandlingConfig** | 久经验证；策略丰富 | 仅在失败时触发；重度 CAMEL 依赖 | 否决 |
| **完成后 LLM 审核** | 由另一个 LLM 检查完整性 | 每个子任务额外 API 调用；延迟；成本 | 否决 |

## 5. 实现规划

### 5.1 文件变更总览

| 文件 | 操作 | 变更内容 |
|------|------|----------|
| `base_agent/tools/toolkits/replan_toolkit.py` | **新建** | ReplanToolkit 类，包含 2 个工具（replan_review_context, replan_split_and_handoff） |
| `base_agent/core/ami_task_executor.py` | **修改** | `add_subtasks()`，注入/移除 replan 工具，prompt 指令 |
| `base_agent/core/ami_agent.py` | **修改** | 添加 `remove_tool()` 方法（2 行） |
| `base_agent/tools/toolkits/__init__.py` | **修改** | 导出 ReplanToolkit |

### 5.2 ReplanToolkit — 2 工具（重构后）

**路径**：`src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/replan_toolkit.py`

继承 `BaseToolkit`，持有 `AMITaskExecutor` 的实时引用和当前子任务 ID。

从 4 个工具精简为 2 个，强制"先看再分"的两步流程：

```python
class ReplanToolkit(BaseToolkit):
    """Agent 主动发起的执行时动态任务拆分。两步协议：先 review 再 split。"""

    def __init__(self, executor, current_subtask_id: str, agent):
        self._executor = executor          # AMITaskExecutor 实时引用
        self._current_subtask_id = current_subtask_id
        self._agent = agent                # 用于早期停止信号
        self._handoff_result = None        # 由 split_and_handoff 设置

    async def replan_review_context(self) -> str:
        """查看完整执行上下文：已完成任务结果摘要、当前任务、待执行任务、workspace 文件列表。
        无参数。MUST call before split_and_handoff。"""

    async def replan_split_and_handoff(self, summary: str, tasks: str) -> str:
        """保存当前进度并拆分剩余工作。
        summary 成为当前子任务的 result。
        tasks: JSON 字符串 [{"content": "...", "agent_type": "browser"}, ...]
        总是停止 agent。不再有"加了任务但不停"的场景。"""

    async def _create_and_add_subtasks(self, tasks: str) -> str:
        """内部方法：解析 JSON、校验、创建 AMISubtask、调用 executor.add_subtasks_async()。"""
```

**已删除的工具**：
- `replan_get_subtask_list` → 被 `replan_review_context` 替代（增强：展示结果摘要 + workspace 文件）
- `replan_report_progress` → 删除（跟 replan 无关，用处有限）
- `replan_add_tasks` → 合并到 `replan_split_and_handoff`
- `replan_complete_and_handoff` → 合并到 `replan_split_and_handoff`

### 5.3 AMITaskExecutor — 核心改动

**(a) 新增 `add_subtasks()` 方法：**
- 为每个新子任务生成唯一 ID：`"{after_id}_dyn_{i}"`
- 设置 `depends_on=[after_subtask_id]`
- 从父子任务继承 `workflow_guide` / `memory_level`
- 插入到 `self._subtasks` 列表中父子任务之后的位置
- 更新 `self._subtask_map`
- 发送 `DynamicTasksAddedData` 和 `AgentReportData` SSE 事件

**(b) 新增 `_inject_replan_tools()` / `_remove_replan_tools()`：**
- 在执行前创建 ReplanToolkit，将工具注入 agent
- 在子任务完成后移除工具

**(c) 修改 `_execute_subtask()`：**
- 在 `agent.reset()` 之后注入 replan 工具
- 在 `astep()` 返回后检查 toolkit 的 `_handoff_result`——若已设置，用它覆盖 `subtask.result`
- 在 finally 块中移除工具

**(d) 修改 `_build_prompt()`：**
- 新增 replan 指令段（任务拆分规则）

### 5.4 AMIAgent — 微改

添加 `remove_tool(name: str)` 方法——一行代码：`self._tools.pop(name, None)`

### 5.5 实现顺序

1. `ami_agent.py`：添加 `remove_tool()` — 极小改动，无风险
2. `replan_toolkit.py`：创建新文件 — 独立模块，不影响现有代码
3. `ami_task_executor.py`：添加 `add_subtasks()` — 新增方法，不改变现有行为
4. `ami_task_executor.py`：在 `_execute_subtask()` 中添加注入/移除 — 对现有流程的最小侵入
5. `ami_task_executor.py`：在 `_build_prompt()` 中添加 replan 指令 — 增量式 prompt 变更
6. `toolkits/__init__.py`：导出 — 一行代码

### 5.6 验证方式

1. **单元验证**：编写脚本实例化 executor + toolkit，调用 `replan_split_and_handoff()`，验证子任务列表正确增长
2. **集成测试**：运行真实任务如"从 ProductHunt 提取前 10 个产品"，观察 Agent 是否使用 replan 工具
3. **SSE 验证**：检查 `dynamic_tasks_added` 事件是否到达前端并正确渲染
4. **递归拆分测试**：验证动态追加的子任务本身也能继续使用 replan 工具拆分
