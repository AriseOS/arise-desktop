# Workflow 系统重构计划

## 1. 问题背景

### 1.1 循环依赖问题

当前代码存在潜在的循环导入问题：

```
core/__init__.py
  → base_agent.py (import AgentWorkflowEngine)
    → agent_workflow_engine.py (import BaseStepAgent)
      → agents/base_agent.py (import AgentContext from core.schemas)
        → 如果 core.schemas 导入了其他 core 模块 → 循环!
```

**当前的临时解决方案：**
- `base_agent.py:111` 使用函数内延迟导入
- `agent_workflow_engine.py:34-54` 使用 `_load_agent_types()` 延迟加载

这种方案虽然能工作，但增加了代码复杂度和维护成本。

### 1.2 代码臃肿问题

| 文件 | 行数 | 问题 |
|------|------|------|
| `core/base_agent.py` | 999 | 包含大量未使用的工具创建方法 |
| `core/workflow_builder.py` | 426 | 整个文件几乎未使用 |
| `core/agent_workflow_engine.py` | 988 | 核心文件，但职责过多 |

### 1.3 架构问题

1. **BaseAgent 职责过多**: 既是 Agent 框架，又包含工具注册、Provider 管理、工作流执行
2. **命名混乱**: `agents/base_agent.py` (BaseStepAgent) vs `core/base_agent.py` (BaseAgent)
3. **模块边界不清**: workflow 执行逻辑分散在多个文件

## 2. 重构目标

### 2.1 核心目标

1. **消除循环依赖**: 通过清晰的模块分层，从根本上避免循环导入
2. **简化代码**: 删除未使用的代码，将 ~3000 行精简到 ~1500 行
3. **明确职责**: 每个模块有单一、清晰的职责

### 2.2 设计原则

1. **依赖方向单一**: 上层依赖下层，下层不依赖上层
2. **数据类独立**: schemas.py 不依赖任何本地模块
3. **延迟加载最小化**: 只在必要时使用，不作为常规手段

## 3. 目标架构

### 3.1 模块分层

```
Layer 0 (无依赖):
  └── core/schemas.py          # 纯数据类定义

Layer 1 (只依赖 Layer 0):
  └── agents/base_agent.py     # BaseStepAgent 抽象基类

Layer 2 (依赖 Layer 0-1):
  ├── agents/*_agent.py        # 具体 Agent 实现
  └── workflows/loader.py      # YAML 加载器

Layer 3 (依赖 Layer 0-2):
  └── core/workflow_engine.py  # 工作流执行引擎

Layer 4 (依赖 Layer 0-3):
  └── core/base_agent.py       # BaseAgent 框架 (简化版)
```

### 3.2 目标文件结构

```
base_agent/
├── core/
│   ├── __init__.py              # 只导出必要的类
│   ├── schemas.py               # 数据结构 (保持不变)
│   ├── workflow_engine.py       # 工作流引擎 (从 agent_workflow_engine.py 重命名)
│   └── base_agent.py            # BaseAgent 框架 (大幅简化)
│
├── agents/
│   ├── __init__.py              # 导出所有 Agent
│   ├── base_agent.py            # BaseStepAgent 基类 (保持不变)
│   ├── text_agent.py
│   ├── browser_agent.py
│   ├── scraper_agent.py
│   ├── storage_agent.py
│   ├── variable_agent.py
│   └── autonomous_browser_agent.py
│
├── workflows/
│   ├── __init__.py
│   └── loader.py                # 从 workflow_loader.py 重命名
│
├── tools/                       # 保持不变
├── memory/                      # 保持不变
└── CONTEXT.md                   # 更新文档
```

### 3.3 删除的文件

| 文件 | 原因 |
|------|------|
| `core/workflow_builder.py` | 未使用，用户通过 YAML 定义 workflow |
| `core/state_manager.py` | 已删除 (git status 显示) |

## 4. 具体变更

### 4.1 core/schemas.py (保持不变)

- 453 行，纯数据类定义
- 无需修改，已经是最底层

### 4.2 agents/base_agent.py (保持不变)

- 41 行，BaseStepAgent 抽象基类
- 只依赖 `core.schemas.AgentContext`
- 无需修改

### 4.3 core/workflow_engine.py (重命名 + 优化)

**从 `agent_workflow_engine.py` 重命名为 `workflow_engine.py`**

变更：
1. 重命名类：`AgentWorkflowEngine` → `WorkflowEngine`
2. 简化 Agent 类型加载逻辑
3. 移除调试代码和过度日志

保留的核心功能：
- `execute_workflow()` - 执行工作流
- `_execute_agent_step()` - 执行单个 Agent 步骤
- `_execute_if_step()`, `_execute_while_step()`, `_execute_foreach_step()` - 控制流
- 变量解析 `_resolve_*` 方法
- 条件评估

### 4.4 core/base_agent.py (大幅简化)

**从 999 行简化到约 350 行**

#### 删除的代码：

```python
# 删除：未使用的工具创建方法 (~300 行)
def _create_browser_tool(self) -> Optional[BaseTool]
def _create_android_tool(self) -> Optional[BaseTool]
def _create_memory_tool(self) -> Optional[BaseTool]
def _create_llm_extract_tool(self) -> Optional[BaseTool]
def _create_wechat_tool(self) -> Optional[BaseTool]
def _create_file_manager_tool(self) -> Optional[BaseTool]
def _create_web_search_tool(self) -> Optional[BaseTool]
def _create_data_processor_tool(self) -> Optional[BaseTool]
def _create_email_sender_tool(self) -> Optional[BaseTool]
def _auto_register_tools(self) -> None
def _create_tool_instance(self, tool_name: str) -> Optional[BaseTool]

# 删除：未使用的自定义 Agent 方法 (~50 行)
def create_custom_text_agent(...)
def register_custom_agent(...)

# 删除：未使用的快捷方法 (~50 行)
def create_quick_qa_workflow(...)

# 删除：已废弃的方法 (~20 行)
def process_user_input(...)  # 标记为 DEPRECATED

# 删除：未实际实现的持久化方法 (~40 行)
def save_checkpoint(...)
def restore_checkpoint(...)

# 删除：很少使用的导入导出 (~80 行)
def export_workflow(...)
def import_workflow(...)

# 删除：WorkflowBuilder 相关 (~30 行)
def create_workflow_builder(...)
```

#### 保留的核心功能：

```python
class BaseAgent:
    def __init__(...)           # 初始化 (简化)
    async def execute(...)      # 主执行入口 (抽象)
    async def initialize(...)   # 初始化
    async def cleanup(...)      # 清理资源

    # 工作流接口
    async def run_workflow(...)  # 执行工作流

    # Provider 管理
    def _initialize_provider(...)
    async def initialize_provider_async(...)
    def get_provider_info(...)

    # 工具调用 (简化)
    async def use_tool(...)
    def register_tool(...)
    def get_registered_tools(...)

    # 状态查询
    def get_status(...)
    async def health_check(...)
    def list_available_agents(...)
    def get_agent_info(...)
```

### 4.5 core/__init__.py (精简导出)

```python
"""BaseAgent 核心模块"""

from .schemas import (
    # Agent 相关
    AgentConfig, AgentResult, AgentState, AgentStatus,
    AgentContext, AgentInput, AgentOutput,
    # 工作流相关
    AgentWorkflowStep, Workflow, WorkflowResult,
    StepResult, StepType,
)
from .base_agent import BaseAgent
from .workflow_engine import WorkflowEngine

__all__ = [
    "BaseAgent",
    "WorkflowEngine",
    "AgentConfig",
    "AgentResult",
    "AgentState",
    "AgentStatus",
    "AgentContext",
    "AgentInput",
    "AgentOutput",
    "AgentWorkflowStep",
    "Workflow",
    "WorkflowResult",
    "StepResult",
    "StepType",
]
```

### 4.6 workflows/loader.py (重命名)

从 `workflow_loader.py` 重命名为 `loader.py`，内容基本保持不变。

## 5. 执行步骤

### Phase 1: 准备工作
- [x] 创建重构计划文档
- [ ] 备份当前代码状态

### Phase 2: 重命名和移动
- [ ] `agent_workflow_engine.py` → `workflow_engine.py`
- [ ] `workflow_loader.py` → `loader.py`
- [ ] 更新所有 import 语句

### Phase 3: 简化 base_agent.py
- [ ] 删除未使用的工具创建方法
- [ ] 删除未使用的自定义 Agent 方法
- [ ] 删除已废弃的方法
- [ ] 删除未实现的持久化方法
- [ ] 删除 WorkflowBuilder 相关代码

### Phase 4: 删除未使用文件
- [ ] 删除 `workflow_builder.py`

### Phase 5: 更新导入和导出
- [ ] 更新 `core/__init__.py`
- [ ] 更新 `agents/__init__.py`
- [ ] 更新 `workflows/__init__.py`
- [ ] 搜索并更新所有外部引用

### Phase 6: 验证
- [ ] 运行现有代码确保功能正常
- [ ] 验证循环依赖已消除

## 6. 风险和注意事项

### 6.1 风险

1. **外部引用**: 可能有其他代码引用了要删除的类/方法
2. **隐式依赖**: 某些代码可能通过字符串或反射使用这些功能

### 6.2 缓解措施

1. 使用 `grep` 搜索所有引用点
2. 保留兼容别名一段时间（如果需要）
3. 分步执行，每步后验证

### 6.3 不变的部分

以下部分保持不变，不在本次重构范围内：
- `tools/` 目录
- `memory/` 目录
- `agents/*_agent.py` (除 base_agent.py 外)
- `schemas.py` 数据结构定义

## 7. 实际结果

| 指标 | 重构前 | 重构后 | 状态 |
|------|--------|--------|------|
| `base_agent.py` 行数 | 999 | 521 | DONE |
| `workflow_engine.py` 行数 | 988 | 794 | DONE |
| `loader.py` 行数 | 668 | 544 | DONE |
| `workflow_builder.py` | 426 | 删除 | DONE |
| 总核心代码行数 | ~3081 | ~1859 | -40% |
| 循环依赖风险 | 中 | 无 | DONE |
| 延迟导入数量 | 3 | 1 | DONE |

## 8. 重构完成总结

### 8.1 已完成的工作

1. **文件重命名**:
   - `agent_workflow_engine.py` -> `workflow_engine.py`
   - `workflow_loader.py` -> `loader.py`

2. **类重命名**:
   - `AgentWorkflowEngine` -> `WorkflowEngine` (无向后兼容别名)

3. **删除的文件**:
   - `core/workflow_builder.py` (426 行)
   - `core/state_manager.py` (已在 git 中标记为删除)

4. **简化 base_agent.py**:
   - 删除了未使用的工具创建方法 (11 个 `_create_*_tool` 方法)
   - 删除了 `_auto_register_tools`, `_create_tool_instance` 方法
   - 删除了 `process_user_input` (已废弃)
   - 删除了 `save_checkpoint`, `restore_checkpoint`
   - 删除了 `export_workflow`, `import_workflow`
   - 删除了 `create_workflow_builder`, `create_quick_qa_workflow`
   - 从 999 行减少到 521 行 (-48%)

5. **更新导入/导出**:
   - 更新了 `core/__init__.py`
   - 创建了 `workflows/__init__.py`
   - 更新了外部引用 (`workflow_executor.py`)

### 8.2 循环依赖测试通过

```bash
$ python -c "
# Test 1: Import core module
from src.clients.desktop_app.ami_daemon.base_agent.core import BaseAgent, WorkflowEngine
# OK

# Test 2: Import workflows module
from src.clients.desktop_app.ami_daemon.base_agent.workflows import WorkflowConfigLoader
# OK

# Test 3: Import agents module
from src.clients.desktop_app.ami_daemon.base_agent.agents import BaseStepAgent
# OK

# Test 4: Cross-module imports (circular dependency test)
from src.clients.desktop_app.ami_daemon.base_agent.core.schemas import AgentContext
from src.clients.desktop_app.ami_daemon.base_agent.agents.base_agent import BaseStepAgent
from src.clients.desktop_app.ami_daemon.base_agent.core.workflow_engine import WorkflowEngine
from src.clients.desktop_app.ami_daemon.base_agent.core.base_agent import BaseAgent
# OK - No circular dependency error!

# Test 5: Instantiate WorkflowEngine
engine = WorkflowEngine(agent_instance=None)
print(engine.AGENT_TYPES.keys())
# ['text_agent', 'variable', 'scraper_agent', 'storage_agent', 'browser_agent', 'autonomous_browser_agent']
"
```

### 8.3 重构后的模块依赖结构

```
Layer 0 (无依赖):
  └── core/schemas.py              # 纯数据类

Layer 1 (只依赖 Layer 0):
  └── agents/base_agent.py         # BaseStepAgent

Layer 2 (依赖 Layer 0-1):
  ├── agents/*_agent.py            # 具体 Agent 实现
  └── workflows/loader.py          # YAML 加载器

Layer 3 (依赖 Layer 0-2):
  └── core/workflow_engine.py      # WorkflowEngine (延迟加载 agents)

Layer 4 (依赖 Layer 0-3):
  └── core/base_agent.py           # BaseAgent (延迟导入 workflow_engine)
```

**关键设计决策：**
1. `schemas.py` 不导入任何本地模块，是最底层
2. `workflow_engine.py` 使用 `_load_agent_types()` 延迟加载具体 Agent 类
3. `base_agent.py` 在 `__init__` 中延迟导入 `WorkflowEngine`
4. 只保留 1 处延迟导入（之前有 3 处）

### 8.4 Git 变更摘要

```
 M src/clients/desktop_app/ami_daemon/base_agent/core/__init__.py
 D src/clients/desktop_app/ami_daemon/base_agent/core/agent_workflow_engine.py
 M src/clients/desktop_app/ami_daemon/base_agent/core/base_agent.py
 D src/clients/desktop_app/ami_daemon/base_agent/core/state_manager.py
 D src/clients/desktop_app/ami_daemon/base_agent/core/workflow_builder.py
 D src/clients/desktop_app/ami_daemon/base_agent/workflows/workflow_loader.py
 M src/clients/desktop_app/ami_daemon/services/workflow_executor.py
?? src/clients/desktop_app/ami_daemon/base_agent/core/workflow_engine.py
?? src/clients/desktop_app/ami_daemon/base_agent/workflows/__init__.py
?? src/clients/desktop_app/ami_daemon/base_agent/workflows/loader.py
```

## 9. 错误传递修复 (2025-01-09)

### 9.1 问题描述

Workflow 执行错误未被正确传递，主要问题：

1. `StepResult.error` 字段未被填充 - 只保存了 `str(e)` 消息，丢失了完整堆栈
2. Step 失败时 `WorkflowResult.success` 仍返回 `True`
3. `WorkflowResult.error_message` 未被填充

### 9.2 修复内容

**`_execute_agent_step` (第 269-280 行):**
```python
except Exception as e:
    error_traceback = traceback.format_exc()
    logger.error(f"Agent step failed [...]: {str(e)}\n{error_traceback}")
    return StepResult(
        step_id=step.id,
        success=False,
        data=None,
        message=str(e),
        error=error_traceback,  # ✓ 完整堆栈
        execution_time=...
    )
```

**`execute_workflow` (第 149-211 行):**
```python
workflow_success = True
failed_step_error = None
# ...
if not step_result.success:
    workflow_success = False
    failed_step_error = f"Step '{step.name}' failed: {step_result.message}"
# ...
return WorkflowResult(
    success=workflow_success,  # ✓ 正确反映失败
    error_message=failed_step_error,  # ✓ 包含错误信息
    # ...
)
```

**控制流步骤 (`if/while/foreach`):**
- 同样添加了 `error=traceback.format_exc()` 到所有 except 块

### 9.3 错误传递链

```
Agent.execute() raises Exception
  ↓
_execute_agent() catches and re-raises
  ↓
_execute_agent_step() catches, logs, returns StepResult(success=False, error=traceback)
  ↓
execute_workflow() checks step_result.success
  - Sets workflow_success=False
  - Sets failed_step_error with step details
  - Breaks loop
  ↓
Returns WorkflowResult(success=False, error_message=..., steps=[...with failed step])
```

### 9.4 获取错误信息

调用方可以从以下位置获取错误详情：

1. `WorkflowResult.success` - 整体是否成功
2. `WorkflowResult.error_message` - 简短错误消息
3. `WorkflowResult.steps[-1].error` - 失败步骤的完整堆栈 (如果最后一步失败)
4. 遍历 `WorkflowResult.steps` 找到 `success=False` 的步骤获取其 `error` 字段
