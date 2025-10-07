# Intent-Based AgentBuilder - 系统设计

**更新日期**: 2025-10-07
**状态**: 设计阶段

---

## 1. 目标

将用户的浏览器操作记录转换为可执行的 Workflow。

```
输入: 用户操作 JSON + 自然语言任务描述
输出: 可执行的 YAML Workflow
```

---

## 2. 核心设计思想

### 意图 + 记忆图架构

不是每次从操作直接生成 workflow，而是：

1. **提取意图**：把操作序列抽象成"要做什么"
2. **记住意图**：构建意图图，记录连接关系和使用频率
3. **重用意图**：新任务时从记忆检索相关意图，组合成新 workflow

```
学习阶段:
用户操作 → 意图提取 → 意图图（记忆系统）

生成阶段:
用户描述 → 意图检索 → MetaFlow → YAML Workflow → 执行
```

---

## 3. 核心概念

### 3.1 意图（Intent）

**定义**：完成某个子任务的操作单元（粗粒度）

**示例**：
```python
# 操作序列
operations = [navigate, click(menu), click(coffee), wait]

# 抽象成意图
intent = Intent(
    label="EnterCoffeeCategory",
    description="通过菜单进入咖啡分类页面",
    atomic_intents=[...],  # 具体操作
    outputs={"category_page": "PageState"}
)
```

**粒度原则**：基于页面状态变化切分
- URL 变化 → 新意图
- 在同一页面完成一个语义完整的子任务 → 一个意图

### 3.2 意图图（Intent Graph）

**定义**：记录意图之间的连接关系和使用频率

```
用户操作 1: Navigate → EnterCategory → ExtractData
用户操作 2: Navigate → EnterCategory → ExtractReviews

意图图:
                    ┌→ ExtractData (freq=1)
[Navigate] → [EnterCategory] ┤
                    └→ ExtractReviews (freq=1)

连线记录频率，高频路径 = 常用模式
```

**存储**：MVP 使用内存（Python 字典或图库如 NetworkX）

### 3.3 MetaFlow

**定义**：意图的组合和编排，描述完成任务的逻辑

**🔴 格式待定** - 这是最关键的设计决策

### 3.4 Workflow

**定义**：最终的 YAML 文件，BaseAgent 可执行

已有标准，参考 `docs/baseagent/workflow_specification.md`

---

## 4. 系统架构

### 4.1 分层架构

```
输入层
  ↓
语义分析层（IntentExtractor + IntentMemoryGraph）
  ↓
工作流生成层（IntentRetriever + MetaFlowGenerator + WorkflowGenerator）
  ↓
执行层（BaseAgent）
```

### 4.2 数据流

**学习阶段**:
```
user_operations.json
  ↓ IntentExtractor
List[Intent]
  ↓ IntentMemoryGraph.add_intents()
Intent Graph (in memory)
```

**生成阶段**:
```
user_description: str
  ↓ IntentRetriever
List[Intent]
  ↓ MetaFlowGenerator
MetaFlow
  ↓ WorkflowGenerator
workflow.yaml
  ↓ BaseAgent
result
```

---

## 5. 核心组件

### 5.1 IntentExtractor
- 从操作序列提取意图
- 基于页面状态变化切分
- 使用 LLM 生成语义信息（label、tags）

### 5.2 IntentMemoryGraph
- 存储意图节点
- 记录意图连线和频率
- 支持标签检索

### 5.3 IntentRetriever
- 根据用户描述检索相关意图
- MVP: 标签匹配 + 频率排序

### 5.4 MetaFlowGenerator
- 将检索到的意图组装成 MetaFlow
- MVP: 线性排列 + 从用户描述推断循环

### 5.5 WorkflowGenerator
- 将 MetaFlow 转换为 YAML
- 策略待定（模板 vs LLM vs 混合）

---

## 6. MVP 范围

### ✅ 包含

1. 意图提取（粗粒度，基于页面状态）
2. 意图记忆图（内存存储）
3. 意图检索（标签匹配）
4. 线性 MetaFlow 生成（+ 简单循环）
5. YAML 生成和执行

### ❌ 不包含

1. 意图多版本（只保留第一版）
2. 交互式修改 MetaFlow
3. 从意图连线自动推断循环
4. 复杂控制流（条件分支、嵌套循环）
5. 向量检索（只用标签）
6. 持久化存储

---

## 7. 已确定的设计决策

| 问题 | 决策 | 说明 |
|-----|------|------|
| 意图粒度 | 粗粒度 | 基于页面状态变化切分 |
| 循环推断 | 用户描述关键词 | 检测"所有"、"每个"等关键词 |
| 意图版本 | 只保留第一版 | MVP 不考虑多版本优化 |
| 存储方案 | 内存 | Python 字典或图库 |
| 用户交互 | 无 | MVP 自动生成，未来支持修改 |

---

## 8. 待讨论的关键问题

### 🔴 优先级 P0（必须明确）

1. **MetaFlow 的数据结构**
   - 用什么格式表示？（列表、树、图？）
   - 如何表示数据流？
   - 如何表示循环？

2. **MetaFlow → YAML 的生成策略**
   - 模板生成 vs LLM 生成 vs 混合？
   - 如果用 LLM，提示词如何设计？

### 🟡 优先级 P1

3. **意图切分的具体规则**
   - 只基于 URL 变化吗？
   - 还需要考虑其他因素吗？（DOM 变化、用户停留时间？）

4. **循环推断的具体实现**
   - 关键词列表是什么？
   - 如何确定循环的范围（哪些意图在循环内）？

---

## 9. 示例场景

基于 `tests/sample_data/browser-user-operation-tracker-example.json`

### 输入
```json
{
  "operations": [...],  // 咖啡采集操作记录
  "user_description": "从 Allegro 采集所有咖啡产品的价格"
}
```

### 学习阶段输出
```python
intents = [
    Intent(label="NavigateToAllegro"),
    Intent(label="EnterCoffeeCategory"),
    Intent(label="ExtractProductInfo", outputs={"price": "string", ...})
]

# 意图图
graph.add_edge("NavigateToAllegro", "EnterCoffeeCategory")
graph.add_edge("EnterCoffeeCategory", "ExtractProductInfo")
```

### 生成阶段输出
```python
# 检索
retrieved_intents = [NavigateToAllegro, EnterCoffeeCategory, ExtractProductInfo]

# 生成 MetaFlow（格式待定）
metaflow = ...

# 生成 YAML
workflow.yaml  # BaseAgent 可执行
```

---

## 10. 下一步

1. **讨论 MetaFlow 格式** → `metaflow_design.md`
2. **确定 WorkflowGenerator 策略**
3. 细化各组件设计 → `component_design.md`
4. 定义数据结构 → `data_structures.md`
5. 制定实施计划 → `implementation_plan.md`

---

## 参考资料

- 用户操作示例: `tests/sample_data/browser-user-operation-tracker-example.json`
- BaseAgent 架构: `docs/baseagent/ARCHITECTURE.md`
- Workflow 规范: `docs/baseagent/workflow_specification.md`
