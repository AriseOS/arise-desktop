# Workflow Generation Strategy - 从用户行为复现到优化

## 整体架构

### 层次1：基础层 - 忠实复现用户行为

**目标**：生成的 workflow 能够准确重现用户演示的每一个操作。

**原则**：
- 保守、可靠
- 1:1 映射用户操作到 workflow steps
- 不做任何假设和优化
- 直接模仿用户的原始操作：click、input、scroll、navigate、extract等

**示例**：
```
用户操作：navigate → click → scroll → extract
Workflow：
  - navigate step (browser_agent with target_url)
  - click step (browser_agent with action=click, xpath=...)
  - scroll step (browser_agent with action=scroll)
  - extract step (scraper_agent)
```

**注意**：
- 这个层次**不包含任何优化**
- 用户点击了什么，就生成click操作
- 用户滚动了，就生成scroll操作
- 用户输入了，就生成input操作

---

### 层次2：优化层 - 双向演进

在基础层之上，同时发展两个方向的优化：

#### 方向A：基于用户描述的任务泛化

**驱动力**：用户的 query 和 task description

**核心问题**：用户演示了具体案例，但实际意图可能更广泛

**泛化类型**：

1. **数量泛化（Loop）**
   ```
   用户演示：处理了 2 个商品
   用户描述：query="collect all products"
   泛化：生成循环，处理所有商品
   ```

2. **时间泛化**
   ```
   用户演示：访问了 2025年10月29日 的页面
   用户描述：query="get today's leaderboard"
   泛化：intent 描述中用 "current day's" 而不是具体日期
   ```

3. **数据范围泛化**
   ```
   用户演示：提取了前10条数据
   用户描述：query="get top 50 products"
   泛化：生成 max_items: 50
   ```

**实现位置**：
- IntentExtractor：泛化 intent 描述
- MetaFlowGenerator：检测循环模式、生成循环节点

---

#### 方向B：基于操作模式的步骤优化

**驱动力**：用户操作序列的模式

**核心问题**：某些操作序列虽然能"复现"，但存在可靠性/效率问题，需要转换为更好的实现方式

**重要说明**：
- 这些优化是对"层次1基础层"的**改进**，不是替代
- 如果没有优化，应该严格按照层次1生成workflow

**优化类型**：

1. **Click → Navigate 模式优化**
   ```
   基础层(层次1)：
     - browser_agent: click (xpath=...)
     - browser_agent: navigate (target_url=固定URL)

   问题：
     - 固定URL可能包含动态参数(日期、session ID等)
     - 未来执行时URL失效

   优化后(层次2):
     - scraper_agent: extract link (xpath_hints from click操作)
     - browser_agent: navigate (target_url={{extracted_link}})
   ```

2. **Scroll 模式优化**
   ```
   基础层(层次1)：
     - browser_agent: scroll
     - browser_agent: scroll
     - browser_agent: scroll
     - scraper_agent: extract

   问题：
     - 滚动次数固定，数据量变化时不适用

   优化后(层次2):
     - browser_agent: scroll_until_no_new_content
     - scraper_agent: extract
   ```

3. **Sequential Navigation 优化**
   ```
   基础层(层次1)：
     - browser_agent: navigate(A)
     - browser_agent: click(B)
     - browser_agent: navigate(B)
     - scraper_agent: extract

   可能优化(层次2):
     - browser_agent: navigate(A)
     - scraper_agent: extract link + extract data from B
     (合并导航和提取，减少页面访问)
   ```

**实现位置**：
- WorkflowGenerator：检测操作模式，应用优化规则

---

## 三层架构图

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: 优化层（Optimization Layer）                        │
│  ┌──────────────────────┐  ┌───────────────────────────┐   │
│  │  方向A: 任务泛化       │  │  方向B: 操作优化           │   │
│  │  - Loop 生成          │  │  - Click→Navigate优化      │   │
│  │  - 时间泛化           │  │  - Scroll 优化             │   │
│  │  - 数据范围泛化       │  │  - Navigation 合并         │   │
│  └──────────────────────┘  └───────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: 语义层（Semantic Layer）                            │
│  IntentMemoryGraph + MetaFlow                               │
│  - Intent 提取和存储                                          │
│  - 执行顺序建模                                               │
└─────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: 基础层（Base Layer）                                │
│  User Operations Recording                                  │
│  - 1:1 记录用户操作                                           │
│  - 保留所有细节（xpath, url, value, etc）                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 当前实施状态

### ✅ 已完成

**基础层**：
- ✅ User Operations 录制

**方向A - 任务泛化**：
- ✅ Intent 描述时间泛化（IntentExtractor）
- ✅ Loop 检测和生成（MetaFlowGenerator）

**方向B - 操作优化**：
- ✅ Click → Navigate 优化（WorkflowGenerator）

### 🚧 进行中

**方向B - 操作优化**：
- 🚧 测试 Click → Navigate 优化效果
- 🚧 验证在 ProductHunt、Allegro 等场景的表现

### 📋 待实施

**方向A - 任务泛化**：
- ⏸️ 数据范围泛化（从 query 中提取 max_items）
- ⏸️ 参数化支持（搜索词、日期范围等）

**方向B - 操作优化**：
- ⏸️ Scroll 模式识别和优化
- ⏸️ Sequential Navigation 合并优化
- ⏸️ Input/Click（非导航）操作支持

---

## 用户操作模式分析

### 1. Click → Navigate 模式

**用户行为**：
```
用户在页面A点击某个链接 → 浏览器导航到页面B
```

**记录的 Operations**：
```yaml
- type: click
  url: "https://site.com/pageA"          # 当前页面
  element:
    xpath: "//a[@class='link']"
    href: "https://site.com/pageB"        # 目标URL（可能动态）
- type: navigate
  url: "https://site.com/pageB"
```

**复现策略**：

#### 基础复现(层次1)：直接模仿用户操作

```yaml
- agent_type: "browser_agent"
  inputs:
    action: "click"
    xpath: "//a[@class='link']"
  # Browser Agent执行click后，会自动导航到pageB
```

**优点**：
- ✅ 最接近用户原始操作
- ✅ 忠实复现用户行为

**缺点/问题**：
- ❌ 需要 Browser Agent 支持 click 操作
- ❌ 可能不稳定（元素加载时机、可见性等）
- ❌ 如果URL包含动态参数，这个方案虽能工作，但不够可靠

---

#### 优化方案(层次2)：提取链接 + 导航

**触发条件**：
- 检测到 click → navigate 模式
- 目标URL可能包含动态部分（日期、session ID、商品ID等）

**实现**：
```yaml
# 注意: browser_agent必须先导航到pageA
# 然后scraper_agent从当前页面提取链接

# Step 1: 提取链接（从当前页面）
- agent_type: "scraper_agent"
  inputs:
    # 不需要target_path，scraper_agent从当前页面提取
    extraction_method: "script"
    data_requirements:
      xpath_hints:
        target_url: "//a[@class='link']"      # 用户点击的元素
  outputs:
    extracted_data: "link_data"

# Step 2: 导航
- agent_type: "browser_agent"
  inputs:
    target_url: "{{link_data.target_url}}"    # 使用提取的URL
```

**重要变更（2025-01）**：
- scraper_agent **不再有导航能力**（移除了 `target_path` 参数）
- scraper_agent 只能从**当前页面**提取数据
- 如需导航，必须先用 browser_agent

**优点**：
- ✅ 适用于所有情况（固定URL、动态URL）
- ✅ 使用用户实际点击的元素（xpath准确）
- ✅ 不需要判断URL是否动态
- ✅ 更可靠（不依赖页面交互）
- ✅ 职责清晰：browser导航，scraper提取

**缺点**：
- ⚠️ 不是严格的"复现"用户操作

**当前决策**：默认使用优化方案，因为可靠性更重要

---

### 2. Navigate（单纯导航）

**用户行为**：
```
用户直接输入URL或从书签访问 → 浏览器导航到页面
```

**记录的 Operations**：
```yaml
- type: navigate
  url: "https://site.com/page"
```

**复现策略**：
```yaml
- agent_type: "browser_agent"
  inputs:
    target_url: "https://site.com/page"
```

**简单直接，无需特殊处理**

---

### 3. Scroll 模式

**用户行为**：
```
用户滚动页面查看内容
```

**问题**：
- 滚动是为了**浏览**（无意义），还是为了**加载数据**（关键操作）？

**场景分析**：

**场景A：无限滚动加载**
```
用户演示：scroll down → scroll down → scroll down → extract
意图：加载所有数据后提取
```

**复现策略**：
```yaml
- agent_type: "browser_agent"
  inputs:
    action: "scroll"
    strategy: "until_no_new_content"  # 滚动直到没有新内容
```

**场景B：浏览式滚动**
```
用户演示：scroll down → scroll up （查看页面内容）
意图：无特殊意图，只是浏览
```

**复现策略**：
```yaml
# 忽略这些滚动操作
```

**判断依据**：
- 滚动后是否有提取操作 → 有则保留，无则忽略
- 多次同向滚动 → 可能是加载数据

**当前问题**：
- IntentExtractor 可能把滚动识别为独立 intent
- 需要在 intent 提取时就判断滚动的意图

---

### 4. Extract（数据提取）

**用户行为**：
```
用户选择文本/复制内容
```

**记录的 Operations**：
```yaml
- type: select
  element:
    xpath: "//h1[@class='title']"
    textContent: "Product Name"
- type: copy_action
  data:
    selectedText: "Product Name"
```

**复现策略**：
```yaml
- agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements:
      xpath_hints:
        title: "//h1[@class='title']"
      sample_data:
        title: "Product Name"
```

**简单直接，已有良好支持**

---

### 5. Input（表单输入）

**用户行为**：
```
用户在输入框输入文本
```

**记录的 Operations**：
```yaml
- type: input
  element:
    xpath: "//input[@name='search']"
  data:
    inputValue: "coffee"
```

**问题**：
- 输入的值是固定的（如 "coffee"），还是应该参数化？

**复现策略**：

**场景A：固定值搜索**
```yaml
- agent_type: "browser_agent"
  inputs:
    action: "input"
    xpath: "//input[@name='search']"
    value: "coffee"
```

**场景B：参数化搜索**
```yaml
# 在 workflow inputs 中定义
inputs:
  search_term:
    type: "string"
    default: "coffee"

# 在 step 中使用
- agent_type: "browser_agent"
  inputs:
    action: "input"
    xpath: "//input[@name='search']"
    value: "{{search_term}}"
```

**当前决策**：默认使用固定值，未来支持参数化

---

### 6. Click（非导航点击）

**用户行为**：
```
点击按钮展开内容、点击选项卡切换、点击checkbox等
```

**场景A：展开/收起内容**
```yaml
- type: click
  element:
    xpath: "//button[@class='expand']"
# （页面内容改变，但不导航）
```

**复现策略**：
```yaml
- agent_type: "browser_agent"
  inputs:
    action: "click"
    xpath: "//button[@class='expand']"
```

**场景B：选项卡切换**
```yaml
- type: click
  element:
    xpath: "//div[@role='tab'][text()='Reviews']"
```

**问题**：
- 需要 Browser Agent 支持 click 操作
- 目前 Browser Agent 可能不支持

---

### 7. Loop（循环遍历）

**用户行为**：
```
用户点击第一个商品 → 提取信息 → 返回 → 点击第二个商品 → 提取信息...
```

**问题**：
- 用户只演示了1-2次，但实际需要处理所有商品
- 如何识别这是循环模式？

**识别方式**：
1. **User query 包含关键词**："all", "every", "each", "所有"
2. **MetaFlowGenerator 检测循环模式**（已实现）

**复现策略**：
```yaml
# Step 1: 提取列表
- agent_type: "scraper_agent"
  inputs:
    data_requirements:
      output_format:
        url: "Item URL"
  outputs:
    extracted_data: "item_urls"

# Step 2: 循环处理
- agent_type: "foreach"
  source: "{{item_urls}}"
  item_var: "current_item"
  steps:
    - agent_type: "scraper_agent"
      inputs:
        target_path: "{{current_item.url}}"
```

**已有良好支持**

---

## 操作模式处理矩阵

| 用户操作模式 | 层次1：基础复现 | 层次2：优化方案 | 问题 | 优先级 |
|------------|---------------|---------------|------|--------|
| **click → navigate** | `browser_agent: click` | `scraper: extract link` + `browser: navigate` | 动态URL失效 | 🔥 P0 |
| **单纯navigate** | `browser_agent: navigate` | 无需优化 | - | ✅ OK |
| **scroll（加载数据）** | `browser_agent: scroll` × N | `browser_agent: scroll_until_no_new_content` | 次数不确定 | ⚠️ P1 |
| **scroll（浏览）** | `browser_agent: scroll` × N | 识别并移除 | 无意义操作 | ⚠️ P2 |
| **extract** | `scraper_agent: extract` | 无需优化 | - | ✅ OK |
| **input** | `browser_agent: input` | 参数化支持 | Browser Agent需支持 | ⚠️ P1 |
| **click（非导航）** | `browser_agent: click` | 无需优化 | Browser Agent需支持 | ⚠️ P2 |
| **loop** | 复现1-2次演示 | `foreach` 循环生成 | 需从query识别 | ✅ OK |

**说明**：
- **层次1（基础复现）**：严格1:1映射用户操作，不做任何优化
- **层次2（优化）**：在基础复现的基础上，应用操作模式优化和任务泛化

---

## 实施路线图

### Phase 0: 建立基础架构理解（已完成）

**目标**：明确两层架构 - 基础复现 + 优化

**产出**：
- ✅ 文档：`workflow_generation_strategy.md`
- ✅ 明确了层次1（基础复现）vs 层次2（优化）的区别
- ✅ 明确了两个优化方向：任务泛化(方向A) + 操作优化(方向B)

---

### Phase 1: 优化 Click → Navigate（层次2-方向B，已完成）

**层次**：层次2 - 操作模式优化

**目标**：click → navigate 模式生成 "提取链接 + 导航" 两步

**修改位置**：
- `src/intent_builder/generators/prompt_builder.py`
- 添加了 "## 3. Click → Navigate Pattern Handling"
- 添加了 "## 2. Core Workflow Logic - Step Relationships"

**预期效果**：
- ✅ ProductHunt daily/weekly 场景正确生成
- ✅ 所有动态链接场景使用变量引用而非固定URL
- ✅ Workflow步骤之间保持数据一致性

**状态**：✅ 已完成，待测试验证

---

### Phase 2: Intent 描述时间泛化（层次2-方向A，已完成）

**层次**：层次2 - 任务泛化

**目标**：Intent 描述不包含具体日期/时间

**修改位置**：
- `src/intent_builder/extractors/intent_extractor.py`
- 添加了 "CRITICAL - Generalize Time-Specific Descriptions"

**预期效果**：
- ✅ Intent: "Navigate to current week's leaderboard"
- ❌ 不要: "Navigate to week 44, 2025"

**状态**：✅ 已完成，待测试验证

---

### Phase 3: 滚动操作优化（层次2-方向B，未来）

**层次**：层次2 - 操作模式优化

**目标**：
1. 识别"加载数据"的滚动 → 保留并优化为 `scroll_until_no_new_content`
2. 识别"浏览"的滚动 → 移除（无意义操作）

**实施方式**：
- 在 IntentExtractor 中，检测滚动后是否有提取操作
- 在 WorkflowGenerator 中，合并多次滚动为单次滚动策略

**状态**：⏸️ 待实施

---

### Phase 4: Browser Agent 基础操作支持（层次1，未来）

**层次**：层次1 - 基础复现能力

**目标**：支持用户的基础交互操作
- click（非导航点击）
- input（表单输入）
- select（下拉框选择）

**前置条件**：
- Browser Agent 需要实现这些操作

**状态**：⏸️ 待实施（依赖Browser Agent开发）

---

### Phase 5: 参数化支持（层次2-方向A，未来）

**层次**：层次2 - 任务泛化

**目标**：某些值可以参数化（如搜索关键词、日期范围）

**示例**：
```yaml
inputs:
  search_term:
    type: "string"
    default: "coffee"

steps:
  - agent_type: "browser_agent"
    inputs:
      action: "input"
      value: "{{search_term}}"
```

**实施方式**：
- 在 Workflow 的 inputs 中定义参数
- 在 steps 中使用变量引用

**状态**：⏸️ 待实施

---

## 测试场景清单

### 必须通过的场景

1. ✅ **Allegro Coffee**：固定类别导航 + 商品列表循环
2. 🔥 **ProductHunt Weekly**：时间相关动态导航（daily → weekly）
3. ❓ **Kickstarter**：（待确认场景）
4. ❓ **Amazon Coffee**：（待确认场景）

### 关键测试点

- [ ] Click → Navigate 生成 extract + navigate
- [ ] Intent 描述不包含具体日期
- [ ] 循环正确识别和生成
- [ ] XPath hints 正确提取
- [ ] 变量传递正确

---

## 未来讨论议题

1. **Browser Agent 能力边界**
   - 哪些操作必须用 Browser Agent？
   - 哪些可以用 Scraper Agent 替代？

2. **优化策略**
   - 何时合并步骤（如：navigate + extract）？
   - 何时分离步骤（如：click → navigate）？

3. **错误处理**
   - Workflow 执行失败时如何自动修复？
   - 如何区分"页面缺数据"vs"脚本失效"？

4. **性能优化**
   - 减少不必要的页面访问
   - 并行执行独立步骤

---

## 参考文档

- [Intent Builder Architecture](./ARCHITECTURE.md)
- [Workflow Specification](../base_app/workflow_specification.md)
- [ScraperAgent Spec](../baseagent/scraper_agent_spec.md)
- [BrowserAgent Spec](../baseagent/browser_agent_spec.md)
