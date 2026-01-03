# Workflow Engine 重构计划

> 本文档记录 Workflow Engine 的重构目标和改动方向
> 基于 2026-01-02 的讨论
> **注意：不需要向后兼容，可以直接替换旧格式**

---

## 一、背景与使用场景

### 使用场景特点

1. **单一执行**：用户同时只会跑一个 workflow
2. **LLM 生成**：大模型生成 workflow，需要尽可能简单、好理解的 spec
3. **预定义 Agent**：Agent 类型由我们提供，用户不会自己创建
4. **CodeAgent 未使用**：暂时不需要 CodeAgent

### 当前问题

1. **Schema 过于复杂**：`AgentWorkflowStep` 包含所有 Agent 的配置字段，混在一起
2. **控制流概念混淆**：`if/while/foreach` 被当作 `agent_type` 处理
3. **Variable Agent 职责过多**：`condition_check` 与 `if` 控制流重叠
4. **Agent 注册机制冗余**：预定义 Agent 不需要动态注册

---

## 二、改进目标

1. **简化 LLM 生成难度**：减少 schema 复杂度，让 LLM 更容易生成正确的 workflow
2. **语义清晰**：控制流与 Agent 分离，概念更清晰
3. **代码简化**：移除不必要的抽象层

---

## 三、改动计划

### Phase 1: Schema 简化

#### 1.1 移除 CodeAgent 相关字段

**现状**：`AgentWorkflowStep` 包含未使用的 CodeAgent 配置

```python
# schemas.py - 需要移除
allowed_libraries: List[str]
expected_output_format: str
```

**改动**：
- 从 `AgentWorkflowStep` 移除这些字段
- 从 `agent_workflow_engine.py` 移除 CodeAgent 注册
- 从 `workflow_loader.py` 的验证器移除 `code_agent`

---

#### 1.2 简化 Workflow 顶层结构

**现状**：
```yaml
apiVersion: "ami.io/v1"
kind: "Workflow"

metadata:
  name: "product-scraper"
  description: "..."
  version: "1.0.0"
  author: "..."
  tags: [...]

inputs:
  url:
    type: string
    required: true

outputs:
  products:
    type: array

config:
  max_execution_time: 3600
  enable_cache: true

steps:
  - ...
```

**改进后**：
```yaml
apiVersion: "ami.io/v2"
name: product-scraper
description: "Scrape products from a URL"

input: url   # 简化的输入声明（单个输入时）
# 或
inputs:      # 多个输入时
  url: string
  max_items: number

steps:
  - ...
```

**改动**：
- 保留 `apiVersion`（方便未来版本升级），移除 `kind`
- 移除 `metadata` 嵌套，直接用 `name`, `description`
- 移除 `version`, `author`, `tags`（用户场景不需要）
- 简化 `inputs` 定义（不需要 `type`, `required` 嵌套）
- 移除 `config`（使用默认值，按需在 step 级别覆盖）
- 移除 `outputs` 顶层定义（从 step 的 outputs 自动推断）

---

#### 1.3 `final_response` 改为可选

**现状**：强制要求 workflow 必须有 `final_response` 输出

**问题**：数据采集场景不需要返回文本给用户

**改动**：
- 移除 `_validate_final_response_requirement` 验证

---

### Phase 2: 控制流与代码简化

#### 2.1 控制流独立语法

**现状**：
```yaml
- id: "loop"
  agent_type: foreach
  source: "{{urls}}"
  item_var: "url"
  steps: [...]
```

**改进后**：
```yaml
- foreach: "{{urls}}"
  as: url
  do:
    - agent: browser
      navigate: "{{url}}"
```

**改动**：
- 控制流不再使用 `agent_type` 字段
- 使用独立的顶级 key (`foreach`, `if`, `while`)
- `agent_workflow_engine.py` 更新识别逻辑

---

#### 2.2 移除 Agent 注册机制

**现状**：使用 `AgentRegistry` + `AgentRouter` + `AgentExecutor` 的插件式设计

**问题**：预定义 Agent 不需要动态注册

**改进后**：
```python
AGENTS = {
    "browser_agent": BrowserAgent,
    "scraper_agent": ScraperAgent,
    "storage_agent": StorageAgent,
    "variable": VariableAgent,
    "text_agent": TextAgent,
    "autonomous_browser_agent": AutonomousBrowserAgent,
}

def get_agent(agent_type: str):
    return AGENTS[agent_type]()
```

**改动**：
- 删除 `AgentRegistry`, `AgentRouter`, `AgentExecutor` 类
- 用简单的 dict 映射替代

---

#### 2.3 Variable Agent 移除 condition_check

**现状**：Variable Agent 有 `condition_check` operation

**问题**：与 `if` 控制流功能重叠

**改动**：
- 从 Variable Agent 移除 `condition_check` operation
- 使用 `if` 控制流代替

---

#### 2.4 简化 condition 表达式

**现状**：使用 Python `eval()` 执行条件

**改进**：定义简化 DSL，只支持基本操作符

```yaml
# 支持的表达式
condition: "{{count}} > 0"
condition: "{{status}} == 'done'"
condition: "{{has_next}} and {{count}} < 100"
```

支持的操作符：`==`, `!=`, `>`, `<`, `>=`, `<=`, `and`, `or`, `not`

---

### Phase 3: Agent inputs 扁平化

#### 3.1 扁平化 Agent inputs

**现状**：
```yaml
inputs:
  target_path: "{{url}}"
  extraction_method: llm
  data_requirements:
    user_description: "Extract products"
    output_format:
      name: string
      price: number
```

**改进后**：
```yaml
agent: scraper
url: "{{url}}"
method: llm
extract:
  description: "Extract products"
  fields:
    name: string
    price: number
output: products
```

---

#### 3.2 合并 sample_data 和 output_format

**现状**：
```yaml
data_requirements:
  user_description: "Extract products"
  output_format:
    name: "Product name"
    price: "Price"
  sample_data:
    - name: "Example"
      price: "$99"
```

**改进**：移除 sample_data，直接在 fields 中用示例值

```yaml
extract:
  description: "Extract products"
  fields:
    name: "Example Product"    # 字段名 + 示例值
    price: "$99.00"
```

---

### Phase 4: 文档更新

1. [ ] 更新 workflow_specification.md
2. [ ] 更新各 Agent spec 文档
3. [ ] 更新 Intent Builder 的 Skills

---

## 四、单步执行设计

### 需求

能够单独运行 workflow 中的某一个 step，用于调试或部分重试。

### 设计方案

#### 方案 A：通过 step_id 指定执行

```python
# 执行单个 step
result = await engine.execute_step(
    workflow=workflow,
    step_id="scrape",
    context=context  # 需要提供上下文变量
)

# 从某个 step 开始执行
result = await engine.execute_workflow(
    workflow=workflow,
    start_from="scrape",  # 从这个 step 开始
    context=context
)
```

**需要解决的问题**：
1. **上下文依赖** - step 可能依赖前面 step 的输出变量
2. **浏览器状态** - 如果是 browser_agent，页面状态可能不对

#### 方案 B：保存/恢复执行快照

```python
# 执行到某个 step 后暂停，保存快照
result = await engine.execute_workflow(
    workflow=workflow,
    pause_before="store",  # 在这个 step 前暂停
    save_snapshot=True
)
# 返回 snapshot_id

# 从快照恢复执行
result = await engine.resume_from_snapshot(
    snapshot_id="xxx",
    step_id="store"  # 从这个 step 继续
)
```

**快照内容**：
- `context.variables` - 所有变量
- 浏览器状态（可选，通过 CDP 保存）

#### 方案 C：简单方案 - 只支持无依赖的 step

只允许执行不依赖前序 step 输出的 step，或者手动提供变量：

```python
result = await engine.execute_step(
    workflow=workflow,
    step_id="scrape",
    variables={
        "category_url": "https://example.com/products"
    }
)
```

### 建议

**推荐方案 C**（简单方案）作为 MVP：
- 实现简单，不需要复杂的快照机制
- 用户手动提供变量，明确知道自己在做什么
- 适合调试场景

后续可以考虑方案 B（快照）来支持更复杂的场景。

### 实现要点

1. **Step 独立执行接口**
```python
async def execute_step(
    self,
    step: AgentWorkflowStep,
    variables: Dict[str, Any],
    browser_session: Optional[BrowserSession] = None
) -> StepResult:
    """执行单个 step"""
    context = AgentContext(
        workflow_id="single_step",
        step_id=step.id,
        variables=variables,
        ...
    )
    return await self._execute_agent_step(step, context)
```

2. **从指定 step 开始执行**
```python
async def execute_workflow(
    self,
    steps: List[AgentWorkflowStep],
    start_from: Optional[str] = None,  # step_id
    variables: Optional[Dict[str, Any]] = None,
    ...
) -> WorkflowResult:
    # 找到起始 step 的索引
    start_index = 0
    if start_from:
        for i, step in enumerate(steps):
            if step.id == start_from:
                start_index = i
                break

    # 从 start_index 开始执行
    for step in steps[start_index:]:
        ...
```

3. **CLI 支持**
```bash
# 执行单个 step
ami run-step workflow.yaml --step scrape --var category_url="https://..."

# 从某个 step 开始
ami run workflow.yaml --start-from scrape --var category_url="https://..."
```

---

## 五、暂不改动

以下内容暂时保持不变：

| 内容 | 原因 |
|------|------|
| Memory 系统 | storage_agent 依赖 |
| xpath_hints 是否可选 | 需要进一步评估 |
| 目录结构 | 非当前重点 |
| 各 Agent 的 output key | inputs/outputs 是设计好的数据链路 |

---

## 六、Variable Agent 保留的 Operations

| Operation | 用途 | 保留 |
|-----------|------|------|
| `set` | 初始化变量 | ✅ |
| `append` | 添加到列表 | ✅ |
| `increment` | 数字增加 | ✅ |
| `decrement` | 数字减少 | ✅ |
| `extract` | 提取字段 | ✅ |
| `merge` | 合并数组/对象 | ✅ |
| `calculate` | 计算表达式 | ✅ |
| `filter` | 过滤列表 | ✅ |
| `slice` | 列表切片 | ✅ |
| `update` | 更新对象字段 | ✅ |
| `condition_check` | 条件检查 | ❌ 移除，用 `if` 控制流代替 |

---

## 七、新旧格式对比

### 完整示例

**现在**（~70 行）：
```yaml
apiVersion: "ami.io/v1"
kind: "Workflow"

metadata:
  name: "product-scraper"
  description: "Scrape products from website"
  version: "1.0.0"
  author: "Ami"
  tags: ["scraper"]

inputs:
  category_url:
    type: "string"
    required: true

outputs:
  products:
    type: "array"

config:
  max_execution_time: 1800

steps:
  - id: "navigate"
    name: "Navigate to page"
    agent_type: "browser_agent"
    inputs:
      target_url: "{{category_url}}"
    outputs:
      result: "nav_result"

  - id: "scrape"
    name: "Scrape products"
    agent_type: "scraper_agent"
    inputs:
      extraction_method: "llm"
      data_requirements:
        user_description: "Extract product list"
        output_format:
          name: "Product name"
          price: "Price"
        sample_data:
          - name: "Example"
            price: "$99"
    outputs:
      extracted_data: "products"

  - id: "loop"
    name: "Process each product"
    agent_type: "foreach"
    source: "{{products}}"
    item_var: "product"
    steps:
      - id: "store"
        name: "Store product"
        agent_type: "storage_agent"
        inputs:
          operation: "store"
          collection: "products"
          data: "{{product}}"
        outputs:
          message: "store_result"

  - id: "output"
    name: "Set final response"
    agent_type: "variable"
    inputs:
      operation: "set"
      data:
        final_response: "Scraped {{products.length}} products"
    outputs:
      final_response: "final_response"
```

**改进后**（~25 行）：
```yaml
apiVersion: "ami.io/v2"
name: product-scraper
description: "Scrape products from website"

input: category_url

steps:
  - id: navigate
    agent: browser
    navigate: "{{category_url}}"

  - id: scrape
    agent: scraper
    method: llm
    extract:
      description: "Extract product list"
      fields:
        name: "Example Product"
        price: "$99"
    output: products

  - foreach: "{{products}}"
    as: product
    do:
      - id: store
        agent: storage
        store:
          collection: products
          data: "{{product}}"
```

**减少**：
- 行数：从 ~70 行减少到 ~25 行
- 嵌套层级：从 4-5 层减少到 2-3 层
- 必记字段：从 ~20 个减少到 ~10 个

---

## 八、实施清单

### Phase 1: Schema 简化
- [ ] 移除 CodeAgent 相关字段
- [ ] 简化 Workflow 顶层结构（apiVersion 改为 v2）
- [ ] `final_response` 改为可选
- [ ] `agent_type` 重命名为 `agent`
- [ ] 更新 `workflow_loader.py` 验证逻辑
- [ ] 删除 `workflows/builtin/` 目录

### Phase 2: 控制流与代码简化
- [ ] 控制流独立语法（`foreach:`/`if:`/`while:` 独立 key）
- [ ] 移除 Agent 注册机制（改用 dict 映射）
- [ ] Variable Agent 移除 `condition_check`
- [ ] 简化 condition 表达式

### Phase 3: Agent inputs 扁平化
- [ ] 扁平化各 Agent 的 inputs 结构
- [ ] 合并 sample_data 和 output_format

### Phase 4: 单步执行支持
- [ ] 实现 `execute_step()` 接口
- [ ] 实现 `start_from` 参数

### Phase 5: 文档更新
- [ ] 更新 workflow_specification.md
- [ ] 更新各 Agent spec 文档

### 后续（非主线）
- [ ] Intent Builder 配套修改
- [ ] 自动化测试基础设施（workflow 运行 + 环境还原）

---

## 九、相关文件

### 需要修改的核心文件

| 文件 | 改动内容 |
|------|----------|
| `base_agent/core/schemas.py` | 简化 `AgentWorkflowStep` |
| `base_agent/core/agent_workflow_engine.py` | 控制流识别、移除注册机制 |
| `base_agent/workflows/workflow_loader.py` | YAML 解析、验证逻辑 |
| `base_agent/agents/__init__.py` | 移除 AgentRegistry 等 |
| `base_agent/agents/variable_agent.py` | 移除 condition_check |
| `docs/base_app/workflow_specification.md` | 规范文档 |
| `intent_builder/.claude/skills/` | LLM 生成的 Skills |

### 参考文档

- Workflow 规范：`docs/base_app/workflow_specification.md`
- Intent Builder Skills：`src/cloud_backend/intent_builder/.claude/skills/`
