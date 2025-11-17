# BrowserAgent 需求文档

**版本**: 1.0
**日期**: 2025-11-02
**状态**: 设计阶段

---

## 一、需求背景

### 1.1 问题描述

当前 Intent Builder 在生成 Workflow 时存在导航步骤被优化掉的问题：

- **用户演示**: 首页 → 点击菜单 → 进入分类页 → 提取数据
- **生成的 Workflow**: 直接导航到分类页 → 提取数据
- **结果**: 触发反爬机制，缺少必要的会话建立过程

### 1.2 根本原因

1. **ScraperAgent 职责不清**: ScraperAgent 既负责导航又负责数据提取，导致纯导航意图没有合适的 Agent 承接
2. **优化过度**: WorkflowGenerator 的 LLM prompt 中有"优化"规则，鼓励跳过中间导航步骤
3. **缺少专用 Agent**: 没有专门处理纯导航意图的 Agent

### 1.3 需求目标

创建 **BrowserAgent**，专门处理不需要提取数据的浏览器导航操作，确保：

1. ✅ 保留所有导航步骤（不被优化掉）
2. ✅ 建立正确的会话状态（Cookie/Session）
3. ✅ 避免触发反爬机制
4. ✅ 职责清晰分离（导航 vs 数据提取）

---

## 二、功能需求

### 2.1 核心功能

#### FR-1: 页面导航

**需求**: BrowserAgent 必须能够导航到指定 URL

**输入**:
```yaml
target_url: "https://example.com/page"
```

**输出**:
```yaml
success: true
current_url: "https://example.com/page"
message: "Successfully navigated to https://example.com/page"
```

**验收标准**:
- ✅ 能够导航到任何有效的 URL
- ✅ 等待页面完全加载（使用 browser-use 的 page load 机制）
- ✅ 返回导航是否成功的状态
- ✅ 发生错误时返回错误信息

#### FR-2: 滚动操作

**需求**: BrowserAgent 必须能够执行页面滚动操作（用于有意义的滚动，如触发懒加载）

**输入**:
```yaml
target_url: "https://example.com/page"
interaction_steps:
  - action_type: "scroll"
    parameters:
      down: true        # 向下滚动
      num_pages: 2.0    # 滚动 2 页
```

**输出**:
```yaml
success: true
current_url: "https://example.com/page"
message: "Successfully navigated and executed 1 interaction step"
```

**验收标准**:
- ✅ 支持向上/向下滚动
- ✅ 支持指定滚动页数（num_pages）
- ✅ 滚动后等待页面稳定
- ✅ 复用 ScraperAgent 的 scroll 实现逻辑

#### FR-3: 浏览器会话共享

**需求**: BrowserAgent 必须与其他 Agent 共享同一个浏览器会话

**实现方式**:
- 通过 `AgentContext.get_browser_session()` 获取共享会话
- 不创建新的浏览器实例
- 导航后页面状态保持，供后续 Agent 使用

**验收标准**:
- ✅ BrowserAgent 和 ScraperAgent 使用同一个浏览器 session
- ✅ BrowserAgent 导航后，ScraperAgent 可以直接在当前页面提取数据
- ✅ Cookie 和 Session 状态在 Agent 间共享

### 2.2 当前阶段不支持的功能

以下功能**暂不支持**（未来可以添加）：

| 功能 | 说明 | 优先级 |
|------|------|--------|
| click 操作 | 点击页面元素 | P2 |
| input 操作 | 输入表单内容 | P2 |
| hover 操作 | 鼠标悬停 | P3 |
| wait 操作 | 等待特定条件 | P2 |
| 复杂交互序列 | 多步骤交互（登录、表单提交等） | P3 |

### 2.3 非功能需求

#### NFR-1: 性能

- 导航操作应在 30 秒内完成（正常网络条件）
- 支持配置超时时间（timeout 参数）

#### NFR-2: 可靠性

- 导航失败时返回明确的错误信息
- 网络错误、超时等异常情况能被正确捕获和报告

#### NFR-3: 可扩展性

- 代码结构支持后续添加 click、input 等操作
- 与 ScraperAgent 的代码复用合理，便于维护

---

## 三、接口定义

### 3.1 输入接口

BrowserAgent 接受以下输入参数：

```python
class BrowserAgentInput:
    target_url: str                          # 必需：目标 URL
    interaction_steps: List[Dict] = []       # 可选：交互步骤列表
    timeout: int = 30                        # 可选：超时时间（秒）
```

**interaction_steps 格式**（当前只支持 scroll）:
```yaml
interaction_steps:
  - action_type: "scroll"
    parameters:
      down: bool              # true=向下, false=向上
      num_pages: float        # 滚动页数（如 2.0 表示2页）
      frame_element_index: Optional[int]  # 可选：iframe 索引
```

### 3.2 输出接口

```python
class BrowserAgentOutput:
    success: bool                # 是否成功
    current_url: str             # 当前页面 URL
    message: str                 # 执行消息
    error: Optional[str] = None  # 错误信息（如果失败）
```

### 3.3 Workflow YAML 示例

**示例 1: 简单导航**
```yaml
- id: navigate-homepage
  name: "Navigate to homepage"
  agent_type: browser_agent
  description: "Navigate to Allegro homepage"
  inputs:
    target_url: "https://allegro.pl/"
  outputs:
    result: "nav_result"
  timeout: 30
```

**示例 2: 导航 + 滚动**
```yaml
- id: navigate-and-scroll
  name: "Navigate and scroll to load content"
  agent_type: browser_agent
  description: "Navigate to category page and scroll to trigger lazy loading"
  inputs:
    target_url: "https://example.com/category"
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 2.0
  outputs:
    result: "nav_result"
  timeout: 45
```


---

## 四、使用场景

### 场景 1: 多步导航（防止反爬）

**用户意图**: 从首页进入分类页

**用户演示**:
1. 访问 `https://example.com/`
2. 点击菜单
3. 点击 "Coffee" 分类
4. 到达 `https://example.com/category/coffee`

**生成的 Workflow**:
```yaml
steps:
  - id: step1
    agent_type: browser_agent
    inputs:
      target_url: "https://example.com/"

  - id: step2
    agent_type: browser_agent
    inputs:
      target_url: "https://example.com/category/coffee"
```

**价值**: 保留首页访问，建立正确的 Cookie/Session，避免反爬

### 场景 2: 触发懒加载后提取数据

**用户意图**: 滚动加载更多商品，然后提取

**用户演示**:
1. 访问商品列表页
2. 向下滚动 2 次（触发懒加载）
3. 提取所有商品链接

**生成的 Workflow**:
```yaml
steps:
  - id: step1
    agent_type: scraper_agent
    inputs:
      target_url: "https://example.com/products"
      interaction_steps:
        - action_type: "scroll"
          parameters:
            down: true
            num_pages: 2.0
      data_requirements:
        user_description: "Extract all product URLs"
        output_format:
          url: "Product URL"
```

**说明**: 这种情况下使用 ScraperAgent（因为有数据提取），scroll 作为 `interaction_steps`

### 场景 3: 纯滚动（无数据提取）

**用户意图**: 只是浏览页面，滚动查看内容

**用户演示**:
1. 访问页面
2. 向下滚动查看
3. （没有后续操作）

**生成的 Workflow**:
```yaml
steps:
  - id: step1
    agent_type: browser_agent
    inputs:
      target_url: "https://example.com/page"
      interaction_steps:
        - action_type: "scroll"
          parameters:
            down: true
            num_pages: 1.0
```

**说明**: 如果 LLM 判断这个 scroll 有意义（比如 Intent description 说明需要滚动），则生成 BrowserAgent

---

## 五、与现有系统的集成

### 5.1 与 ScraperAgent 的关系

| 对比维度 | BrowserAgent | ScraperAgent |
|---------|-------------|--------------|
| **主要职责** | 页面导航 + 交互 | 页面导航 + 交互 + 数据提取 |
| **何时使用** | 纯导航意图（无数据提取） | 有数据提取的意图 |
| **支持操作** | navigate, scroll | navigate, scroll, extract |
| **输出内容** | 执行状态 | 提取的数据 |
| **会话共享** | 通过 AgentContext | 通过 AgentContext |

**选择规则**:
- Intent description 包含 "navigate", "enter", "visit" → BrowserAgent
- Intent description 包含 "extract", "collect", "scrape" → ScraperAgent

### 5.2 与 Intent Builder 的集成

**IntentExtractor**:
- ❌ 不需要修改
- 继续提取 Intent（description + operations）

**MetaFlowGenerator**:
- ❌ 不需要修改
- 继续生成 MetaFlow

**WorkflowGenerator**:
- ✅ 需要修改 PromptBuilder
- 添加 BrowserAgent 介绍
- 删除"优化"规则（跳过导航）
- 添加 Agent 选择规则

### 5.3 与 AgentContext 的集成

BrowserAgent 通过 `AgentContext` 获取浏览器会话：

```python
async def initialize(self, context: AgentContext) -> bool:
    # 从 context 获取共享的浏览器会话
    session_info = await context.get_browser_session()
    self.browser_session = session_info.session
    self.controller = session_info.controller
    return True
```

---

## 六、验收标准

### 6.1 功能验收

| 测试项 | 验收标准 |
|-------|---------|
| 基本导航 | ✅ 能导航到任意 URL，页面加载完成 |
| 滚动操作 | ✅ 能执行 scroll 操作，支持向上/向下，支持指定页数 |
| 会话共享 | ✅ 与 ScraperAgent 共享同一个浏览器会话 |
| 错误处理 | ✅ 导航失败时返回明确错误信息 |
| 超时处理 | ✅ 超时时返回错误，不卡死 |

### 6.2 集成验收

| 测试项 | 验收标准 |
|-------|---------|
| Workflow 生成 | ✅ IntentExtractor → MetaFlow → Workflow 能生成包含 BrowserAgent 的 workflow |
| 导航保留 | ✅ 首页 → 分类页等多步导航不被优化掉 |
| Agent 协作 | ✅ BrowserAgent 导航后，ScraperAgent 能在当前页面提取数据 |
| 端到端测试 | ✅ 完整的 Allegro 咖啡产品抓取流程能正常运行 |

---

## 七、实现约束

### 7.1 技术约束

- ✅ 基于 `browser-use` 库实现
- ✅ 继承 `BaseStepAgent`
- ✅ 复用 ScraperAgent 的浏览器会话管理代码
- ✅ 使用 `AgentContext` 获取共享会话

### 7.2 代码约束

- ✅ 最小改动原则：不修改 ScraperAgent 代码
- ✅ 复制复用：从 ScraperAgent 复制必要的代码
- ✅ 代码注释：所有注释和日志使用**英文**
- ✅ 异常处理：所有异常情况都要捕获和记录

### 7.3 兼容性约束

- ✅ 与现有 AgentContext 兼容
- ✅ 与现有 Workflow 引擎兼容
- ✅ 输入/输出格式遵循 AgentInput/AgentOutput 规范

---

## 八、优先级和里程碑

### Phase 1: MVP（当前阶段）

**目标**: 实现基本的导航和滚动功能

- [x] 文档准备（本文档 + 设计文档）
- [ ] 实现 BrowserAgent 类
  - [ ] 基本导航功能
  - [ ] 滚动功能
  - [ ] 会话管理
- [ ] 修改 PromptBuilder
- [ ] 测试验证

**交付物**:
- ✅ BrowserAgent 能导航到 URL
- ✅ BrowserAgent 能执行 scroll
- ✅ Workflow 生成不优化掉导航步骤

### Phase 2: 增强（未来）

**目标**: 增加更多交互操作

- [ ] 支持 click 操作
- [ ] 支持 input 操作
- [ ] 支持 wait 操作
- [ ] 支持复杂交互序列

### Phase 3: 优化（未来）

**目标**: 代码重构和优化

- [ ] 创建 BrowserBaseAgent 基类
- [ ] 重构 ScraperAgent 继承 BrowserBaseAgent
- [ ] 优化代码复用
- [ ] 性能优化

---

## 九、参考资料

### 相关文档
- [讨论记录](../../../intent_builder/discussions/05_browser_agent_integration.md)
- [ScraperAgent 需求文档](./scraper_agent_requirements.md)
- [ScraperAgent 设计文档](./scraper_agent_design.md)

### 相关代码
- ScraperAgent 实现: `src/base_app/base_app/base_agent/agents/scraper_agent.py`
- PromptBuilder: `src/intent_builder/generators/prompt_builder.py`
- AgentContext: `src/base_app/base_app/base_agent/core/schemas.py`

---

**文档版本**: 1.0
**最后更新**: 2025-11-02
**负责人**: Claude Code
