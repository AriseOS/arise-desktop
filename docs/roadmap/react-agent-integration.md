# ReAct Agent 集成方案

## 背景与核心思考

### 问题：Workflow vs ReAct

**当前 Workflow 模式的局限：**

1. Workflow 本身不可能一次就生成成功
2. 在这种情况下生成的 Workflow，本身就不是可靠的

**Workflow 应该是什么：**

1. 有大量数据或者经验积累以后，生成的 Workflow
2. 需要长时间运行、反复运行的任务，通过 Workflow 来保证正确性和节约 token

**ReAct 模式的价值：**

用户说一句话，要做某件事：
1. 从 Memory 中获取相关的步骤，写一个 Plan，然后让 Agent 用 ReAct 的方式执行 Plan
2. 当 Plan 出现差错、意外的时候，调用 Memory 看有没有相关处理办法，没有就找用户解决，或者让大模型自己猜怎么解决
3. 大量执行过的任务，后台去总结，看能不能生成 Workflow

### 核心理念

> **All agent needs is context**

- Context 来自 Memory（历史经验）
- Context 来自当前页面（PageSnapshot）
- Context 来自用户反馈

> **Workflow 是结果，不是起点**

---

## 实施路线图

```
Phase 1 (当前)          Phase 2              Phase 3              Phase 4
     │                      │                    │                    │
     ▼                      ▼                    ▼                    ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ 独立的      │      │ + Memory    │      │ + Memory    │      │ Workflow    │
│ BrowserAgent│ ───► │   生成 Plan │ ───► │   纠错能力  │ ───► │ 失败时调用  │
│ (自主执行)  │      │             │      │             │      │ BrowserAgent│
└─────────────┘      └─────────────┘      └─────────────┘      └─────────────┘
```

### Phase 1：独立的自主 BrowserAgent

**目标：** 给 AMI 加上自主执行的能力

- 接受文字描述的任务
- 调用大模型拆分任务生成 Plan
- ReAct 模式逐步执行
- 与现有 Workflow 完全分开

### Phase 2：Memory 生成 Plan

**目标：** 从 Memory 中获取相关经验来辅助 Plan 生成

- 相似任务的执行经验
- 网站交互模式记录
- 常见问题解决方案

### Phase 3：Memory 纠错能力

**目标：** 出错时查找 Memory 寻求解决方案

- 执行失败时查询相似错误的处理方式
- 没有相关记录时询问用户或 LLM 猜测
- 解决方案存入 Memory 供后续使用

### Phase 4：Workflow 协作

**目标：** Workflow 执行出问题时，调用 BrowserAgent 来纠错

- Workflow 步骤失败时触发 BrowserAgent
- BrowserAgent 尝试完成该步骤
- 成功后继续 Workflow 执行

---

## Phase 1 详细设计

### 产品形态

```
┌─────────────────────────────────────────────────────────────┐
│                      AMI Desktop App                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────┐    ┌─────────────────────┐         │
│  │                     │    │                     │         │
│  │   My Workflows      │    │   ★ Quick Task ★   │  ← 新增  │
│  │   (现有功能)         │    │   (自主执行)        │         │
│  │                     │    │                     │         │
│  │   • 录制生成        │    │   直接输入任务描述   │         │
│  │   • YAML 工作流     │    │   Agent 自主完成    │         │
│  │   • 精确执行        │    │                     │         │
│  │                     │    │                     │         │
│  └─────────────────────┘    └─────────────────────┘         │
│                                                              │
│           两个入口，完全独立，互不影响                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 用户体验流程

```
用户点击 "Quick Task"
    │
    ▼
┌─────────────────────────────────────────┐
│                                         │
│  📝 描述你想完成的任务:                  │
│  ┌─────────────────────────────────┐   │
│  │ 在 Amazon 上搜索 100 美元以下的   │   │
│  │ 无线耳机，找出评分最高的 5 款，   │   │
│  │ 整理成表格                       │   │
│  └─────────────────────────────────┘   │
│                                         │
│            [ 开始执行 ]                  │
│                                         │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  执行中...                               │
│                                         │
│  📋 Plan:                               │
│  ├─ 1. 打开 Amazon.com           ✅     │
│  ├─ 2. 搜索 "wireless headphones" 🔄    │
│  ├─ 3. 筛选价格 < $100           ⏳     │
│  ├─ 4. 按评分排序                ⏳     │
│  └─ 5. 提取前 5 款产品信息        ⏳     │
│                                         │
│  🔄 当前: 正在执行步骤 2...              │
│  ┌─────────────────────────────────┐   │
│  │        [浏览器实时画面]          │   │
│  └─────────────────────────────────┘   │
│                                         │
└─────────────────────────────────────────┘
```

### 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Quick Task 模块                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  前端 (新增页面)                                             │
│  └── QuickTaskPage.jsx                                      │
│      ├── 任务输入框                                          │
│      ├── Plan 展示                                          │
│      ├── 执行状态/浏览器画面                                 │
│      └── 结果展示                                            │
│                                                              │
│  后端 API (新增路由)                                         │
│  └── /api/v1/quick-task/                                    │
│      ├── POST /execute     # 执行任务                       │
│      ├── GET /status/{id}  # 查询状态                       │
│      └── WS /ws/{id}       # 实时进度                       │
│                                                              │
│  核心 Agent (从 Eigent 移植)                                 │
│  └── AutonomousBrowserAgent                                 │
│      ├── 任务理解 & Plan 生成                                │
│      ├── ReAct 执行循环                                     │
│      ├── PageSnapshot (页面理解)                            │
│      └── 结果提取 & 整理                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 与现有系统的关系

```
┌─────────────────────────────────────────────────────────────┐
│                        AMI 系统                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │              现有 Workflow 系统                       │   │
│   │                                                      │   │
│   │   • 录制 → 生成 YAML → 执行                          │   │
│   │   • BrowserAgent (xpath 定位)                        │   │
│   │   • ScraperAgent                                     │   │
│   │   • StorageAgent                                     │   │
│   │                                                      │   │
│   │   完全保持不变                                        │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │           ★ 新增: Quick Task 系统 ★                  │   │
│   │                                                      │   │
│   │   • 文字任务 → Plan → ReAct 执行                     │   │
│   │   • AutonomousBrowserAgent (ref 定位)                │   │
│   │   • PageSnapshot (Eigent 移植)                       │   │
│   │   • ActionExecutor (Eigent 移植)                     │   │
│   │                                                      │   │
│   │   独立入口，独立执行                                  │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                共享基础设施                           │   │
│   │                                                      │   │
│   │   • BrowserManager (浏览器会话)                       │   │
│   │   • LLM Client                                       │   │
│   │   • 存储系统                                          │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 从 Eigent 移植的核心能力

### 为什么选择 Eigent

Eigent 是一个成熟的 Computer Use 项目，其 Browser Agent 具备：

1. **PageSnapshot** - LLM 友好的页面描述格式
2. **基于 ref 的元素定位** - 比 xpath 更灵活
3. **自主执行能力** - ReAct 模式
4. **笔记系统** - 记录执行过程中的发现

### 移植组件清单

| 组件 | 来源 | 用途 |
|------|------|------|
| PageSnapshot | Eigent | 将页面 DOM 转换为 LLM 易理解的文本 |
| ActionExecutor | Eigent | 基于元素引用 [n] 执行点击、输入等操作 |
| ReAct Loop | Eigent | Think → Action → Observe 循环 |

### PageSnapshot 示例

输入：复杂的页面 DOM

输出：
```
Page: Amazon.com - Shopping
URL: https://www.amazon.com/s?k=headphones

Interactive Elements:
[1] <input type="text" placeholder="Search Amazon">
[2] <button>Search</button>
[3] <a href="/dp/B08...">Sony WH-1000XM4 - $248.00</a>
[4] <a href="/dp/B09...">Apple AirPods Pro - $189.99</a>
...
```

LLM 可以直接理解并决定操作：
- "点击 [1] 输入搜索词"
- "点击 [3] 查看产品详情"

---

## 文件结构

### 新增文件

```
src/clients/desktop_app/ami_daemon/
├── base_agent/
│   ├── agents/
│   │   └── autonomous_browser_agent.py   # ★ 核心: 自主浏览器 Agent
│   │
│   └── tools/
│       └── eigent_browser/               # ★ 从 Eigent 移植
│           ├── __init__.py
│           ├── page_snapshot.py          # 页面快照
│           ├── action_executor.py        # 动作执行
│           └── element_finder.py         # 元素定位
│
├── routers/
│   └── quick_task.py                     # ★ 新增 API 路由
│
└── services/
    └── quick_task_service.py             # ★ 任务执行服务

src/clients/desktop_app/src/
└── pages/
    └── QuickTaskPage.jsx                 # ★ 新增前端页面
```

---

## 实施清单

### Phase 1 任务列表

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| **后端** |
| 1 | 创建 AutonomousBrowserAgent | `agents/autonomous_browser_agent.py` | 核心自主执行逻辑 |
| 2 | 移植 PageSnapshot | `tools/eigent_browser/page_snapshot.py` | 页面快照 |
| 3 | 移植 ActionExecutor | `tools/eigent_browser/action_executor.py` | 动作执行 |
| 4 | 创建 QuickTaskService | `services/quick_task_service.py` | 任务管理服务 |
| 5 | 创建 API 路由 | `routers/quick_task.py` | REST + WebSocket |
| 6 | 注册路由 | `daemon.py` | 添加新路由 |
| **前端** |
| 7 | 创建页面 | `pages/QuickTaskPage.jsx` | 任务输入和执行展示 |
| 8 | 添加导航 | `App.jsx` 或 `Sidebar` | 添加 Quick Task 入口 |
| **测试** |
| 9 | 端到端测试 | - | 完整流程验证 |

---

## 后续演进

### Phase 2: Memory 生成 Plan

```python
async def _generate_plan(self, task: str) -> List[PlanStep]:
    # 1. 查询 Memory 获取相关经验
    relevant_experiences = await self.memory.search(task)

    # 2. 将经验作为 context 传给 LLM
    prompt = self.PLANNING_PROMPT.format(
        task=task,
        experiences=self._format_experiences(relevant_experiences)
    )

    # 3. 生成更准确的 Plan
    response = await self.llm.complete(prompt)
    return self._parse_plan(response)
```

### Phase 3: Memory 纠错

```python
async def _execute_step(self, task: str, step: PlanStep) -> Any:
    try:
        result = await self._do_execute(step)
        # 成功 → 记录到 Memory
        await self.memory.record_success(step, result)
        return result

    except Exception as e:
        # 失败 → 查 Memory 找解决方案
        solution = await self.memory.find_solution(e, self.current_state)

        if solution:
            return await self._apply_solution(solution)
        else:
            # 问用户或 LLM 猜测
            result = await self._handle_unknown_error(e)
            # 记录新方案
            await self.memory.record_solution(e, result)
            return result
```

### Phase 4: Workflow 协作

```python
# 在 WorkflowExecutor 中

async def _execute_step(self, step: WorkflowStep) -> Any:
    try:
        return await self._run_agent(step)

    except StepExecutionError as e:
        # Workflow 步骤失败 → 调用 AutonomousBrowserAgent
        logger.info(f"Step {step.id} failed, trying autonomous recovery")

        autonomous_agent = AutonomousBrowserAgent(...)
        recovery_result = await autonomous_agent.execute(
            task=f"Complete this step: {step.description}",
            context=self._get_current_context()
        )

        if recovery_result.success:
            return recovery_result.output
        else:
            raise e
```

---

## 参考资料

- Eigent 项目: https://github.com/eigent-ai/eigent
- Eigent Browser Agent 实现: `third-party/eigent/backend/app/utils/toolkit/hybrid_browser_python_toolkit.py`
- Eigent PageSnapshot: `third-party/eigent/backend/app/utils/toolkit/` (CAMEL 框架内)
- ReAct 论文: https://arxiv.org/abs/2210.03629
