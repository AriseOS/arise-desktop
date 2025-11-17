# 讨论记录 03 - MetaFlow → Workflow 生成

**日期**: 2025-10-07
**状态**: 已确定

---

## 讨论背景

在确定了 MetaFlow 的格式后，需要明确如何将 MetaFlow 转换为可执行的 YAML Workflow。

核心问题：
- LLM 需要哪些输入信息？
- LLM 要做哪些决策？
- 如何设计 Prompt 和执行框架？

---

## 关键讨论点

### 问题 1: Operations 格式是否足够清晰？

**初始疑虑**：
- Operations 是否包含足够的信息供 LLM 推断 Agent 类型？
- 是否需要额外的 selector、target、output_var 等字段？

**用户反馈**：
> "我认为 Operations 的格式非常清楚记录了用户做了啥，加上意图的描述，可以很清晰的让大模型知道选用哪个 Agent 来完成用户的任务。"

**参考数据**: `tests/sample_data/browser-user-operation-tracker-example.json`

实际的 operation 包含：
```json
{
  "type": "click",
  "timestamp": 1757730780902,
  "url": "https://allegro.pl/",
  "page_title": "Allegro - atrakcyjne ceny - Strona Główna",
  "element": {
    "xpath": "//div[2]/div[1]/.../li[1]/a",
    "tagName": "A",
    "className": "mgn2_14 mp0t_0a mgmw_wo mqu1_21 ...",
    "textContent": "Kawy",
    "href": "https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030"
  },
  "data": {
    "button": 0,
    "clientX": 433,
    "clientY": 260
  }
}
```

**结论**: Operations 已经包含了非常详细的信息（xpath, 元素属性, textContent, href 等），足够 LLM 理解用户操作的语义。

---

### 问题 2: 数据流推断策略

**讨论内容**：
- LLM 如何判断一个 Intent 是否产生输出？
- 如何推断变量命名（product_list, page_state 等）？
- 如何推断意图之间的数据依赖关系？
- 循环中如何引用变量？

**示例场景**：
```yaml
# Intent 2: ExtractProductList
operations:
  - type: extract
    element: {...}
    # LLM 需要推断输出变量名为 product_list

# Intent 3 (loop): ExtractProductPrice
description: "遍历产品列表，逐个提取价格"
# LLM 需要推断：
#   - source: "{{product_list}}" （来自 Intent 2）
#   - item_var: current_product
```

**用户决策**：
> "我认为数据流的正确维护很重要，当前阶段我也没有考虑好具体的方法，我觉得可以先让大模型来做。"

**结论**:
- 数据流推断完全由 LLM 负责
- 不在 MetaFlow 中增加数据流提示（outputs_hint, source_hint）
- 相信 LLM 可以从 operations 和 description 中推断出数据流

---

### 问题 3: 循环结构生成策略

**讨论内容**：
- 如何从自然语言 description 推断循环来源（source）？
- 循环变量名（item_var）的命名规则？
- max_iterations 如何确定？

**用户决策**：
> "也是依赖大模型"

**结论**:
- 循环的所有细节（source, item_var, max_iterations）由 LLM 推断
- MetaFlow 只提供自然语言 description
- LLM 根据 description 的关键词和上下文推断循环结构

---

### 问题 4: Step 拆分策略

**讨论内容**：
- 一个 Intent 的多个 operations 如何拆分成多个 step？
- 什么时候合并，什么时候拆分？

**示例**：
```yaml
# 一个 Intent
operations:
  - type: click
    element: {textContent: "Kawy"}
  - type: wait
    duration: 2000

# 可能生成 1 个 step（合并）或 2 个 step（拆分）？
```

**用户决策**：
> "Step 的拆分应该以 Step Agent 为最小单元。"

**理解**：
- 每个 step 必须是一个完整的 agent（tool_agent, scraper_agent 等）
- 不能有比 agent 更小的执行单元
- 具体是一对一还是一对多，由 LLM 根据语义复杂度决定

**结论**:
- LLM 根据 operations 的语义复杂度自主决定拆分策略
- 约束：每个 step 必须是一个完整的 agent

---

### 问题 5: Prompt 设计方案

**讨论的选项**：

**Q1: 是否包含完整的 workflow_specification.md？**
- 选项 A: 完整规范（~500 行）
- 选项 B: 精简规范（~50 行）
- 选项 C: 只提供示例

**Q2: Few-shot 示例数量？**
- 1 个：咖啡采集
- 2 个：咖啡采集 + 其他
- 3+ 个：更多场景

**Q3: 是否分步骤生成？**
- 选项 A: 一次性生成完整 YAML
- 选项 B: 分步骤（先数据流，再 YAML）

**Q4: 验证和错误处理？**
- 选项 A: YAML parser 验证 + 重试
- 选项 B: Pydantic 验证
- 选项 C: 两者结合

**用户决策**：
> "提示词由你来决定"

**初步方案**（基于 MVP 原则）：
- Q1 → 选项 B: 精简规范（减少 token）
- Q2 → 1 个完整示例
- Q3 → 选项 A: 一次性生成
- Q4 → 选项 A: YAML parser + 重试（最多 3 次）

---

## 关键设计结论

### 1. Operations 格式已足够

- 用户操作数据包含详细的 DOM 信息（xpath, textContent, href 等）
- 配合意图的 description，足够 LLM 理解操作语义
- 不需要在 MetaFlow 中增加额外的字段

### 2. 数据流推断由 LLM 负责

- 不在 MetaFlow 中增加数据流信息
- LLM 根据 operations（特别是 extract 类型）推断输出
- LLM 自动推断意图之间的数据依赖关系
- LLM 负责变量命名（语义化）

### 3. 循环生成由 LLM 负责

- MetaFlow 循环节点只有自然语言 description
- LLM 推断 source（循环来源）
- LLM 推断 item_var（循环变量名）
- LLM 决定 max_iterations

### 4. Step 拆分原则

- **最小单元**: Step Agent（tool_agent, scraper_agent 等）
- 拆分策略由 LLM 根据语义复杂度决定
- 可以是一对一，也可以是一对多

### 5. Prompt 设计策略（待实现）

- 精简的 workflow 规范
- 1 个完整示例（咖啡采集）
- 一次性生成完整 YAML
- YAML 格式验证 + 重试机制

---

## 下一步

1. 创建 WorkflowGenerator 设计文档
2. 明确输入输出定义
3. 设计 Prompt 模板和执行框架
4. 编写完整的咖啡采集示例作为 few-shot 参考

---

## 关键修正（查看真实 Workflow 后更新）

在查看真实 workflow 样例（`paginated-scraper-workflow.yaml`）后，发现并修正了关键理解问题：

### 修正 1: Operations 的本质

**正确理解**: Operations = 用户实际操作的详细记录，告诉 LLM "如何完成意图"

Operations 不是抽象的操作描述，而是必须包含：
- 具体的 DOM 定位信息（xpath, selector）
- 元素的详细属性（tagName, className, textContent, href）
- 用户交互的数据（selectedText, copiedText, input value）
- 页面上下文（url, page_title, timestamp）

**为什么？** 因为这些信息 LLM 无法自己推断，必须从用户操作记录中获取。

例如：LLM 需要知道标题在哪个 xpath、文本内容是什么，才能生成正确的 `data_requirements` 和 `sample_data`。

### 修正 2: 变量管理完全由 LLM 推断

MetaFlow **不需要**包含变量管理的意图（初始化、赋值、追加）。

LLM 会从 MetaFlow 自动推断并生成：
- `init-vars` step（看到 loop + store → 初始化列表）
- `save-urls` step（看到循环前提取 URLs → 保存列表）
- `append` operation（看到循环内 store → 追加数据）

用户不关心变量，这是系统实现细节。

### 修正 3: Store 作为独立 Operation

**设计决策**: Store 必须与 extract 分开（提供更强的表示能力）

```yaml
operations:
  - type: select
  - type: copy_action
  - type: store  # 明确的存储语义
    params:
      collection: "daily_products"
      fields:
        - name: "title"
        - name: "price"
```

这样可以支持：临时提取（不存储）、单个存储、批量存储等多种场景。

### LLM 推断边界总结

**LLM 负责推断**（从 MetaFlow）：
1. 变量初始化、聚合、完整的数据流
2. 数据结构（从 operations 实际数据推断 output_format + sample_data）
3. extraction_method（根据规则：优先 script，语义理解用 llm）
4. 循环配置（index_var, loop_timeout）
5. intent_description（从 intent_description 扩展）
6. agent_type 选择（根据 operations 组合判断）

**MetaFlow 必须提供**：
1. 用户意图的语义（intent_description）
2. 详细的用户操作记录（operations，包含完整的 DOM 信息）
3. 存储语义（store operation）
4. 循环描述（loop.description）

### extraction_method 判断规则

提供给 LLM 的指导：
1. 默认优先使用 "script" 方法（更快、更稳定）
2. 全页面信息提取 → 必须用 "script"
3. 需要语义理解 → 用 "llm"
4. MVP 阶段可以都用 "llm"
5. 有精确 xpath → 优先 "script"
