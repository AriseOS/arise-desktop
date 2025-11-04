# BrowserAgent 集成讨论记录

**日期**: 2025-11-02
**参与者**: 用户, Claude Code
**主题**: 引入 BrowserAgent 处理纯导航意图，解决工作流生成中的导航步骤优化问题

---

## 一、问题背景

### 1.1 当前行为

Intent Builder 管道在生成工作流时存在一个问题：**初始导航步骤被优化掉了**。

**完整流程**：

1. **IntentExtractor** 正确捕获所有用户操作：
   - Intent 1: "Navigate to Allegro homepage"
   - Intent 2: "Navigate to coffee category through menu"（包含点击操作）
   - Intent 3: "Extract product URLs"

2. **MetaFlowGenerator** 在 MetaFlow 中保留这些 Intent

3. **WorkflowGenerator** 优化掉中间导航：
   - ❌ 跳过首页导航
   - ❌ 跳过分类页导航（通过菜单点击）
   - ✅ 直接生成：`scraper_agent` with `target_path: "category_page_url"`

### 1.2 问题影响

这种优化会导致：

| 问题 | 说明 |
|------|------|
| **触发反爬机制** | 直接访问子页面，没有访问首页，容易被识别为爬虫 |
| **缺少会话建立** | 跳过 Cookie/Session 初始化过程 |
| **缺少必要状态** | 某些网站要求先访问首页才能访问分类页 |

### 1.3 实际案例

```yaml
# 用户演示操作：
1. 访问 https://allegro.pl/
2. 点击菜单按钮
3. 点击 "咖啡" 分类
4. 导航到 https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030
5. 提取产品链接

# 当前生成的 Workflow（错误）：
steps:
  - id: extract-products
    agent_type: scraper_agent
    inputs:
      target_path: "https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030"  # 直接跳转！

# 期望生成的 Workflow（正确）：
steps:
  - id: navigate-homepage
    agent_type: browser_agent
    inputs:
      target_url: "https://allegro.pl/"

  - id: navigate-category
    agent_type: browser_agent
    inputs:
      target_url: "https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030"

  - id: extract-products
    agent_type: scraper_agent
    inputs:
      use_current_page: true
      data_requirements: {...}
```

### 1.4 根本原因

在 `prompt_builder.py:374-389` 中，有一段"优化"规则：

```python
**IMPORTANT Optimization**:
If MetaFlow contains multiple click/navigate operations but the intent is just to reach a final URL:
→ Skip intermediate clicks, use **scraper_agent** with the final URL directly!
```

这个规则导致 LLM 在生成 Workflow 时优化掉了初始导航步骤。

---

## 二、解决方案讨论

### 2.1 Agent 职责分离

**问题**: 是否需要创建专门的导航 Agent？

**决策**: ✅ 是，创建 BrowserAgent

**理由**:
- ScraperAgent 的逻辑很清晰：在页面内操作，操作是为了抓数据
- ScraperAgent 一定会提取数据
- 纯导航意图需要专门的 Agent 来承接
- 职责分离：导航 vs 数据提取

**架构设计**:
```
BaseStepAgent
├── BrowserAgent (新建) - 导航 + 滚动（不提取数据）
└── ScraperAgent (现有，不改动) - 导航 + 交互 + 数据提取
```

### 2.2 Intent 到 Agent 的映射

**问题**: 如何判断使用 BrowserAgent 还是 ScraperAgent？

**决策**: ✅ 通过 WorkflowGenerator 的 LLM 根据 intent description 关键词决定

**理由**:
- 不能单纯用规则映射（太简单，容易出错）
- LLM 可以理解语义含义
- 关键词如 "navigate", "enter", "go to" → BrowserAgent
- 关键词如 "extract", "collect", "scrape" → ScraperAgent

### 2.3 操作的"后果"处理

**核心原则**: **语义化操作，而非复刻操作**

**分层讨论**:

#### 第一层：Intent 划分
- 交给 LLM 决定（IntentExtractor 阶段）
- 通常来说：`scroll → extract` = 一个 Intent（scroll 是为了抓数据）
- 单纯的 `scroll` 没有后续操作 = 可能被过滤或保留为独立 Intent

#### 第二层：操作保留策略

不同场景的处理方式：

| 场景 | 用户操作 | Intent 划分 | 映射 Agent | 实现方式 |
|------|---------|------------|-----------|---------|
| **A: scroll + extract** | 滚动加载 → 提取数据 | 1个 Intent | ScraperAgent | scroll 作为 `interaction_steps` |
| **B: 单纯 scroll** | 只滚动，没有提取 | 如果 Intent 有意义则保留 | BrowserAgent | scroll 作为 `interaction_steps` |
| **C: click 展开 + extract** | 点击展开 → 提取数据 | 1个 Intent | ScraperAgent | ❌ 当前阶段不支持 click |
| **D: 多次 click 导航** | 首页 → 点击菜单 → 分类页 | 1个 Intent | BrowserAgent | **不保留点击序列**，直接导航到目标 URL |

**关键决策**:

**场景 D 详解** - 多次 click 导航的处理：

```yaml
# 用户操作序列：
operations:
  - type: navigate
    url: "https://example.com/"
  - type: click
    element: {xpath: "//button[@class='menu']"}
  - type: click
    element: {xpath: "//a[@href='/category/coffee']"}
  - type: navigate
    url: "https://example.com/category/coffee"

# Intent 提取：
intent_description: "Navigate to coffee category page through menu"

# Workflow 生成（不保留点击序列）：
- id: navigate-category
  agent_type: browser_agent
  inputs:
    target_url: "https://example.com/category/coffee"  # 直接导航到目标 URL
    # description: "通过菜单导航" - 这个语义信息丢失，但可接受
```

**可接受的权衡**:
- ✅ 完全可以接受丢失 "through menu" 的语义信息
- ✅ 直接导航到目标 URL 对大多数情况足够
- ✅ 如果后续出现反爬问题，可以再增强

### 2.4 BrowserAgent 的能力范围

**问题**: BrowserAgent 应该接受什么输入？

**决策**: ✅ 采用最简单的方案（当前阶段）

**输入格式**:
```yaml
inputs:
  target_url: "https://..."           # 必需：目标 URL
  interaction_steps: []               # 可选：只支持 scroll
    - action_type: "scroll"
      parameters:
        down: true
        num_pages: 2
```

**输出格式**:
```yaml
outputs:
  success: true
  current_url: "https://..."
  message: "Successfully navigated to ..."
```

**当前阶段不支持**:
- ❌ click 操作
- ❌ input 操作
- ❌ 复杂交互序列

**确认的问答**:

| 问题 | 答案 |
|------|------|
| QB.1: ScraperAgent 需要支持 click 吗？ | ❌ 不需要 |
| QB.2: 需要支持其他 interaction 吗？ | ❌ 暂时不需要（input/wait/hover） |
| QA.2: 可以接受丢失 "through menu" 信息吗？ | ✅ 完全可以接受 |

### 2.5 浏览器会话共享

**问题**: BrowserAgent 和 ScraperAgent 如何共享浏览器会话？

**决策**: ✅ 通过 AgentContext 共享（已实现）

**实现方式**:
- 两个 Agent 都调用 `context.get_browser_session()`
- 返回同一个 workflow 的会话实例
- BrowserAgent 导航后，ScraperAgent 使用当前页面

**数据流**:
```yaml
- id: step1
  agent_type: browser_agent
  inputs:
    target_url: "https://example.com/category"
  # 浏览器停留在分类页

- id: step2
  agent_type: scraper_agent
  inputs:
    use_current_page: true  # 不导航，直接使用当前页面
    data_requirements: {...}
```

**ScraperAgent 的导航行为**:
- 如果指定 `target_path` → ScraperAgent 会重新导航
- 如果设置 `use_current_page: true` → 使用前一步的页面
- ✅ 允许 ScraperAgent 随时重新导航（QD.2）

**确认的问答**:

| 问题 | 答案 |
|------|------|
| QD.1: ScraperAgent 如何获取当前页面 URL？ | ❌ 不需要获取，browser-use 库应该有提供 |
| QD.2: 允许 ScraperAgent 随时重新导航吗？ | ✅ 允许，不需要限制 |

### 2.6 现有组件的修改

**IntentExtractor（intent_builder/extractors/）**:
- ❌ **不需要修改**
- 继续过滤无用操作，提取有意义的 Intent
- Intent 结构不变（description + operations）
- Agent 类型由 WorkflowGenerator 决定

**确认**: QC.1, QC.2

| 问题 | 答案 |
|------|------|
| QC.1: BrowserAgent 需要从 operations 提取 selector 吗？ | ✅ 可能需要，但这是 WorkflowGenerator 自然会做的（信息已在 prompt 中） |
| QC.2: MetaFlowGenerator 需要传递完整 operations 吗？ | ❌ MetaFlow 生成不需要，但 Workflow 生成需要（已经这么做了） |

**MetaFlowGenerator（intent_builder/generators/metaflow_generator.py）**:
- ❌ **不需要修改**
- 当前只传递 `operation_types` 给 LLM（足够生成 MetaFlow）
- 完整的 operations 已经在 MetaFlow YAML 结构中
- WorkflowGenerator 可以从 MetaFlow YAML 中读取完整 operations

**WorkflowGenerator + PromptBuilder（intent_builder/generators/）**:
- ✅ **需要修改**
- 修改 1：添加 BrowserAgent 的介绍
- 修改 2：删除"优化"规则（跳过中间导航）
- 修改 3：添加 Agent 选择规则（何时用 BrowserAgent vs ScraperAgent）
- 修改 4：说明何时使用 `use_current_page: true`

**确认**: QE.1, QE.2

| 问题 | 答案 |
|------|------|
| QE.1: Prompt 需要哪些关键信息？ | ✅ 目前的已经够了，除了我们正在讨论的功能要修改 |
| QE.2: 需要传递 operations 信息给 LLM 吗？ | ✅ WorkflowGenerator 需要，而且已经这么做了 |

**ScraperAgent（base_app/base_agent/agents/scraper_agent.py）**:
- ❌ **完全不需要修改**
- 保持现有所有功能
- `interaction_steps` 已经支持 scroll
- `use_current_page` 参数已经支持

### 2.7 架构重构方式

**问题**: 是否创建 BrowserBaseAgent 并重构 ScraperAgent？

**决策**: ❌ 不，采用最小改动方案（方案 1）

**理由**:
- ScraperAgent 代码稳定且运行良好
- 避免不必要的重构风险
- BrowserAgent 可以复制 ScraperAgent 的必要代码
- 未来如果需要可以再重构

**实现方式**:
```python
# 新建 BrowserAgent - 复制浏览器会话管理代码
class BrowserAgent(BaseStepAgent):
    # 从 ScraperAgent 复制：
    # - initialize() - 浏览器会话管理
    # - _navigate_to_pages() - 导航逻辑
    # - _execute_interaction_step() - 只保留 scroll 部分

# 保持不变：ScraperAgent 保留所有现有代码
class ScraperAgent(BaseStepAgent):
    # 不需要任何修改
```

**确认**: QF.1, QF.2

| 问题 | 答案 |
|------|------|
| QF.1: 重构方案选择 | ✅ 方案 1 - 最小改动 |
| QF.2: 是否可接受重构 ScraperAgent 代码结构 | ❌ 不需要，ScraperAgent 不修改 |

---

## 三、决策汇总

| 主题 | 决策 | 理由 |
|------|------|------|
| **Agent 架构** | 创建独立的 BrowserAgent | 职责清晰分离：导航 vs 数据提取 |
| **Intent 映射** | LLM 基于关键词决定 | 语义理解 intent description |
| **操作语义化** | 保留意图，不保留点击序列 | "通过菜单导航" → 直接 URL 导航 |
| **BrowserAgent 能力** | 只支持导航 + 滚动 | 当前阶段最小范围 |
| **click 操作** | 暂不支持 | 后续根据需要添加 |
| **会话共享** | 通过 AgentContext | 已实现，无需改动 |
| **IntentExtractor** | 不修改 | 已经处理得很好 |
| **MetaFlowGenerator** | 不修改 | 当前结构足够 |
| **重构方式** | 最小改动，复制代码 | 不重构 ScraperAgent |
| **导航保留** | 保留所有导航 Intent | 防止触发反爬机制 |

---

## 四、改动范围

### 4.1 Part 1: Intent Builder 修改

**文件**: `src/intent_builder/generators/prompt_builder.py`

**修改点**:

1. **加载 BrowserAgent 规范** (L27-56)
2. **添加 BrowserAgent 到 workflow spec** (L168-319)
3. **修改 "Operations → Agent Type" 规则** (L360-400)
   - 删除优化规则
   - 添加 BrowserAgent vs ScraperAgent 选择规则
   - 强调保留导航路径
4. **更新示例** (L510-721)

### 4.2 Part 2: BaseAgent 新增

**新建文件**:
- `src/base_app/base_app/base_agent/agents/browser_agent.py`
- `docs/baseagent/browser_agent_spec.md`（供 LLM prompt 使用）

**BrowserAgent 功能**:
- ✅ 导航到 URL
- ✅ 执行 scroll 操作
- ✅ 共享浏览器会话
- ❌ click 操作（暂不支持）
- ❌ input 操作（暂不支持）

**复用 ScraperAgent 代码**:
- `initialize()` - 浏览器会话管理
- `_navigate_to_pages()` - 导航逻辑
- `_execute_interaction_step()` - scroll 部分

---

## 五、实现计划

### 阶段 1: 文档准备
- [x] 讨论记录文档（本文档）
- [ ] BrowserAgent 需求文档
- [ ] BrowserAgent 设计文档

### 阶段 2: BrowserAgent 实现
- [ ] 创建 BrowserAgent 类
- [ ] 实现导航功能
- [ ] 实现 scroll 功能
- [ ] 测试浏览器会话共享

### 阶段 3: Intent Builder 修改
- [ ] 创建 BrowserAgent 规范文档
- [ ] 修改 PromptBuilder
- [ ] 测试 Workflow 生成

### 阶段 4: 集成测试
- [ ] BrowserAgent 单独测试
- [ ] BrowserAgent + ScraperAgent 协作测试
- [ ] 多步导航测试（首页 → 分类页 → 详情页）
- [ ] 验证导航步骤不被优化掉

---

## 六、参考资料

### 相关代码位置

| 组件 | 文件路径 | 行号/说明 |
|------|---------|---------|
| 当前问题示例 | `tests/test_data/coffee_allegro/output/workflow.yaml` | L46-68（直接跳转到分类页） |
| ScraperAgent 实现 | `src/base_app/base_app/base_agent/agents/scraper_agent.py` | 完整实现 |
| 优化规则（需删除） | `src/intent_builder/generators/prompt_builder.py` | L374-389 |
| IntentExtractor | `src/intent_builder/extractors/intent_extractor.py` | 完整实现 |
| MetaFlowGenerator | `src/intent_builder/generators/metaflow_generator.py` | L132-143（只传 operation_types） |
| WorkflowGenerator | `src/intent_builder/generators/workflow_generator.py` | 使用 PromptBuilder |

### 测试数据

- `tests/test_data/coffee_allegro/` - Allegro 咖啡产品抓取示例
- `tests/test_data/coffee_amazon/` - Amazon 咖啡产品抓取示例

---

**文档版本**: 1.0
**最后更新**: 2025-11-02
