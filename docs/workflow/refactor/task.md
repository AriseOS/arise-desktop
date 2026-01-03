# Workflow Engine Refactor Tasks

> 跨上下文工作追踪文件
> 每次新上下文读取此文件继续工作

## 当前状态

**已完成**: 所有 Phase 任务 + Intent Builder 更新 + DOM Capture 基础设施 + Script Generation 模块提取

**已完成**: Phase 6.4 + Phase 7 全部完成

---

## Phase 1: Schema 简化

- [x] **1.1 移除 CodeAgent 相关字段**
- [x] **1.2 简化 Workflow 顶层结构**
- [x] **1.3 `final_response` 改为可选**
- [x] **1.4 `agent_type` 重命名为 `agent`**
- [x] **1.5 删除 `workflows/builtin/` 目录**

## Phase 2: 控制流与代码简化

- [x] **2.1 控制流独立语法** (`foreach:`, `if:`, `while:`)
- [x] **2.2 移除 Agent 注册机制**
- [x] **2.3 Variable Agent 移除 `condition_check`**
- [x] **2.4 简化 condition 表达式**

## Phase 3: Agent inputs 扁平化

- [x] **跳过** - 保持当前 inputs/outputs 数据管道设计

## Phase 4: 单步执行支持

- [x] **4.1 实现 `execute_step()` 接口**
- [x] **4.2 实现 `execute_workflow_from()` 方法**
- [x] **4.3 实现 `find_step_by_id()` 辅助方法**

## Phase 5: 文档更新

- [x] **5.1 更新 CONTEXT.md 文件**

---

## Intent Builder 更新 (v2 支持)

- [x] **更新 workflow_spec.md** - v2 格式规范
- [x] **更新 agent-specs/SKILL.md** - Agent 类型和控制流语法
- [x] **更新 browser_agent.md** - v2 示例
- [x] **更新 scraper_agent.md** - v2 示例
- [x] **更新 storage_agent.md** - v2 示例
- [x] **更新 workflow-generation/SKILL.md** - 生成指南
- [x] **更新 workflow-validation/SKILL.md** - 验证说明
- [x] **更新 .claude/skills/.../validate.py** - 验证脚本 v2 支持
- [x] **更新 agents/tools/validate.py** - Python 验证模块 v2 支持

---

## 关键文件路径

### BaseApp (已更新)
```
src/clients/desktop_app/ami_daemon/base_app/base_app/base_agent/
├── core/
│   ├── schemas.py
│   ├── agent_workflow_engine.py
│   └── workflow_builder.py
├── agents/
│   └── variable_agent.py
└── workflows/
    └── workflow_loader.py
```

### Intent Builder (已更新)
```
src/cloud_backend/intent_builder/
├── .claude/skills/
│   ├── workflow-generation/
│   │   ├── SKILL.md
│   │   └── references/workflow_spec.md
│   ├── workflow-validation/
│   │   ├── SKILL.md
│   │   └── scripts/validate.py
│   └── agent-specs/
│       ├── SKILL.md
│       └── references/
│           ├── browser_agent.md
│           ├── scraper_agent.md
│           └── storage_agent.md
└── agents/tools/validate.py
```

---

## v2 格式关键变化

| v1 | v2 |
|----|----|
| `kind: Workflow` + `metadata:` | 直接 `name:` 在顶层 |
| `agent_type: foreach` | `foreach: "{{list}}"` |
| `agent_type: if` + `condition:` | `if: "{{condition}}"` |
| `agent_type: while` + `condition:` | `while: "{{condition}}"` |
| `source:` + `item_var:` | `as:` + `do:` |
| `then_steps:` | `then:` |
| `steps:` (控制流内) | `do:` |

---

## 新增 API

### AgentWorkflowEngine

```python
# 执行单个步骤
async def execute_step(
    step: AgentWorkflowStep,
    variables: Dict[str, Any],
    workflow_id: str = None,
    log_callback: Optional[Any] = None
) -> StepResult

# 从指定步骤开始执行工作流
async def execute_workflow_from(
    steps: List[AgentWorkflowStep],
    start_from: str,
    variables: Dict[str, Any],
    workflow_id: str = None,
    step_callback: Optional[Any] = None,
    log_callback: Optional[Any] = None
) -> WorkflowResult

# 查找步骤（支持嵌套）
def find_step_by_id(
    steps: List[AgentWorkflowStep],
    step_id: str
) -> Optional[AgentWorkflowStep]
```

---

## 完成记录

| 任务 | 完成时间 | 备注 |
|------|----------|------|
| Phase 1.1-1.5 | Session 1 | Schema 简化 |
| Phase 2.1-2.2 | Session 1 | 控制流和注册机制 |
| Phase 2.3-2.4 | Session 2 | ConditionEvaluator 清理 |
| Phase 4 | Session 2 | 单步执行 API |
| Phase 5 | Session 2 | 文档更新 |
| Intent Builder | Session 2 | Skills + validate.py 更新 |

---

## Phase 6: Recording-time DOM Capture

**目标**: 在录制时捕获 DOM，上传到 Intent Builder，生成 workflow 时预生成脚本

### 已完成

- [x] **6.1 monitor.py 添加 DOM 捕获能力**
  - `enable_dom_capture()` 开启 DOM 捕获
  - `capture_dom_snapshot(url)` 手动捕获当前页面 DOM
  - `get_dom_snapshots()` 获取所有已捕获的 DOM
  - Navigate 事件自动触发 DOM 捕获（当 enabled）

- [x] **6.2 cloud_client.py 支持上传 DOM snapshots**
  - `upload_recording()` 新增 `dom_snapshots` 参数

- [x] **6.3 Cloud Backend 存储 DOM snapshots**
  - `storage_service.save_recording()` 支持保存 DOM snapshots
  - `storage_service.get_recording_dom_snapshots()` 读取 DOM snapshots
  - 存储路径: `recordings/{recording_id}/dom_snapshots/{url_hash}.json`

### 已完成

- [x] **6.4 Workflow 生成时预生成脚本**
  - `ScriptPregenerationService` - 解析 workflow 识别需要脚本的 steps
  - 自动匹配 step URL → DOM snapshot
  - 调用 `BrowserScriptGenerator` / `ScraperScriptGenerator`
  - 后台异步生成，保存到 workflow 目录结构
  - 更新 workflow metadata 记录生成状态

---

## Phase 7: Script Generation 模块提取

**目标**: 将脚本生成逻辑从 BaseApp agents 提取到 common/ 模块，供 BaseApp 和 Cloud Backend 共用

### 已完成

- [x] **7.1 创建 src/common/script_generation/ 模块**
  - `types.py` - ScriptGenerationResult, BrowserTask, ScraperRequirement
  - `templates.py` - 脚本模板和 Claude Agent prompts
  - `browser_script_generator.py` - 生成 find_element.py
  - `scraper_script_generator.py` - 生成 extraction_script.py
  - `CONTEXT.md` - 模块文档

- [x] **7.2 更新 browser_agent.py 使用新模块**
  - 导入 common 模块的模板
  - 保留本地模板用于向后兼容

- [x] **7.3 更新 scraper_agent.py 使用新模块**
  - 导入 `SCRAPER_AGENT_PROMPT` 从 common 模块

- [x] **7.4 集成到 Cloud Backend workflow 生成流程**
  - `ScriptPregenerationService` 在 workflow 生成后异步调用
  - `_pregenerate_scripts_background()` 后台任务
  - 更新 workflow metadata 记录脚本生成状态

---

## 关键 API

### SimpleUserBehaviorMonitor (monitor.py)

```python
# 开启 DOM 捕获
monitor.enable_dom_capture(enabled=True)

# 获取所有 DOM 快照
dom_snapshots = monitor.get_dom_snapshots()
# Returns: Dict[str, dict]  # URL -> DOM dict

# 手动捕获（通常自动触发）
await monitor.capture_dom_snapshot(url)
```

### StorageService (storage_service.py)

```python
# 保存 recording（包含 DOM）
storage.save_recording(
    user_id, recording_id, operations,
    dom_snapshots={"https://...": {...dom_dict...}}
)

# 读取 DOM snapshots
dom_snapshots = storage.get_recording_dom_snapshots(user_id, recording_id)
```

---

## 后续工作

- [ ] 自动化测试基础设施
- [ ] 端到端测试：Recording with DOM → Workflow → Script Pre-generation
