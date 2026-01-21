# Memory Graph Ontology Design

> 本文档记录 Memory 系统图本体模型的设计讨论（2026-01-21）

## 1. 背景与目标

### 1.1 核心目标

建立一个网站/软件操作逻辑的知识库，能够：
1. 从用户操作中学习
2. 回答用户查询（如"怎么通过榜单查看产品团队信息"）
3. 支持操作重放

### 1.2 当前问题

现有设计按 URL 区分 State，导致：
- 100 个产品详情页 = 100 个 State 节点（节点爆炸）
- 无法识别"同一类页面"
- 查询时难以找到正确的操作路径

---

## 2. 核心概念

### 2.1 层次结构

```
AbstractState（抽象状态，图的节点）
    │
    ├── 代表一类页面（如"产品详情页"）
    ├── intents: 页面内的操作记录
    ├── embedding_vector: 用于语义检索
    │
    └── PageInstance（具体页面实例）
            ├── url: producthunt.com/products/noodle-seed
            ├── url: producthunt.com/products/other-product
            └── ...
```

### 2.2 概念定义

| 概念 | 定义 | 在图中的角色 |
|------|------|--------------|
| **AbstractState** | 一类页面的抽象（如"产品详情页"） | **图的节点** |
| **PageInstance** | 具体的页面 URL 实例 | AbstractState 的属性 |
| **Action** | AbstractState 之间的跳转 | **图的边** |
| **Intent** | 页面内的操作记录（用于重放） | AbstractState 的属性 |

### 2.3 图结构

```
AbstractState ──Action──▶ AbstractState ──Action──▶ AbstractState
  (首页)        点击榜单      (榜单页)      点击产品     (详情页)
    │                          │                         │
    └── instances: [...]       └── instances: [...]      └── instances: [url1, url2, ...]
    └── intents: [...]         └── intents: [...]        └── intents: [...]
```

---

## 3. AbstractState 合并逻辑

### 3.1 合并条件

**两个 AbstractState 应该合并，当它们有相同的 PageInstance（URL 相同）**

```
例子：

AbstractState A（从榜单路径学到的）
    └── instances: [producthunt.com/products/noodle-seed]

AbstractState B（从搜索路径学到的）
    └── instances: [producthunt.com/products/noodle-seed]

因为 instances 有交集 → A 和 B 是同一个 AbstractState → 合并
```

### 3.2 合并效果

| 场景 | 之前（按 URL） | 之后（AbstractState） |
|------|----------------|----------------------|
| 100 个产品详情页 | 100 个节点 | 1 个节点 + 100 个 instances |
| 100 个团队页 | 100 个节点 | 1 个节点 + 100 个 instances |

**图的节点数大幅减少，但保留了具体实例信息。**

### 3.3 合并时机

新的 PageInstance 进来时：
1. 检查是否已有 AbstractState 包含相同 URL
2. 如果有 → 复用该 AbstractState，添加 instance
3. 如果没有 → 创建新 AbstractState

---

## 4. 查询流程

### 4.1 查询场景

```
用户查询: "通过榜单查看产品团队信息"
```

### 4.2 查询步骤

```
Step 1: 语义检索
    - embed("榜单") → 找到 AbstractState(榜单页)
    - embed("团队") → 找到 AbstractState(团队页)

Step 2: 最短路径分析
    - 在 AbstractState 图上搜索：榜单页 → ... → 团队页

Step 3: 返回路径
    - 首页 → [点击Launches] → 榜单页 → [点击产品] → 详情页 → [点击Team] → 团队页
```

---

## 5. 数据结构设计

### 5.1 AbstractState

```python
class AbstractState:
    id: str                      # 确定性 ID，用于合并判断
    description: str             # 语义描述（如"ProductHunt 产品详情页"）
    embedding_vector: List[float] # 用于语义检索

    # 实例列表
    instances: List[PageInstance]

    # 页面内操作（合并自所有实例）
    intents: List[Intent]
```

### 5.2 PageInstance

```python
class PageInstance:
    url: str                     # 具体 URL
    page_title: str              # 页面标题
    timestamp: int               # 访问时间
    dom_snapshot_id: str         # DOM 快照（可选）
```

### 5.3 Action

```python
class Action:
    source: str                  # 来源 AbstractState ID
    target: str                  # 目标 AbstractState ID
    type: str                    # 跳转类型
    description: str             # 语义描述（如"点击 Team 按钮"）
    element_pattern: dict        # 元素模式（用于匹配不同实例）
```

### 5.4 Intent

```python
class Intent:
    type: str                    # 操作类型（ClickElement, TypeText...）
    description: str             # 语义描述
    embedding_vector: List[float]

    # 元素定位信息（用于重放）
    element_id: str
    xpath: str
    css_selector: str
    text: str
    value: str
```

### 5.5 IntentSequence（操作序列）

AbstractState.intents 是操作序列的列表，而不是扁平的 Intent 列表：

```python
class AbstractState:
    # 不是 List[Intent]，而是 List[IntentSequence]
    intent_sequences: List[IntentSequence]

class IntentSequence:
    id: str                      # 唯一标识
    session_id: str              # 来自哪个 session
    timestamp: int               # 序列开始时间

    # 语义检索（关键！）
    description: str             # "输入用户名密码并点击登录"
    embedding_vector: List[float]

    # 操作列表
    intents: List[Intent]        # 有序的操作列表
```

示例：
```
AbstractState(登录页)
    └── intent_sequences: [
            IntentSequence(
                description="输入用户名密码并点击登录",
                intents=[点击用户名, 输入admin, 点击密码, 输入123, 点击登录]
            ),
            IntentSequence(
                description="使用测试账号登录",
                intents=[点击用户名, 输入test, 点击密码, 输入456, 点击登录]
            ),
            IntentSequence(
                description="找回密码",
                intents=[点击忘记密码]
            ),
        ]
```

**好处**：
- 保留操作顺序
- 区分不同的操作流程
- 重放时可选择某个完整序列执行
- **支持语义检索**：可以通过 description + embedding 找到最匹配的操作序列

### 5.6 检索流程

```
用户查询: "登录系统"

Step 1: AbstractState 检索
    embed("登录") → 找到 AbstractState(登录页)

Step 2: IntentSequence 检索
    embed("输入账号密码登录") → 在 AbstractState(登录页).intent_sequences 中检索
    → 找到最匹配的 IntentSequence(description="输入用户名密码并点击登录")

Step 3: 返回结果
    返回该 IntentSequence 的 intents 列表用于重放
```

---

## 6. 与现有代码的对应关系

| 现有代码 | 新设计 | 变化 |
|----------|--------|------|
| State | AbstractState | ID 改为确定性生成，增加 instances 列表 |
| - | PageInstance | 新增，存储具体 URL |
| Action | Action | 基本不变 |
| Intent | Intent | 基本不变，挂在 AbstractState 下 |

---

## 7. 待实现功能

| 功能 | 说明 | 优先级 |
|------|------|--------|
| PageInstance 数据结构 | 新增，存储具体 URL 实例 | P0 |
| AbstractState.instances 字段 | State 增加实例列表 | P0 |
| IntentSequence 数据结构 | 新增，将 intents 改为 List[IntentSequence] | P0 |
| URL 索引 | 快速查找 URL 属于哪个 AbstractState | P0 |
| 合并逻辑 | 写入时检查 URL 是否已存在，复用 AbstractState | P0 |
| 最短路径搜索 | `find_path(from_state, to_state)` | P1 |

---

## 8. 设计决策

### 8.1 Intent 不需要合并

Intent 代表不同实例上的不同操作，直接 append 到 AbstractState.intents 列表即可。

```python
abstract_state.intents.append(new_intent)  # 不去重，直接追加
```

### 8.2 Action 的 element_pattern

包含两部分：
- **语义描述**：描述做了什么（如"点击产品列表项"）
- **xpath hints**：提供定位参考

```python
class Action:
    description: str      # "点击产品列表项进入详情页"
    xpath_hints: str      # "//*[@class='product-item']" 或类似模式
```

### 8.3 AbstractState ID 生成与合并

**ID 生成**：随机 UUID（因为 URL 和路径都不是唯一标识）

**合并依据**：
- URL 通过 PageInstance 记录
- 路径通过 incoming Actions 记录（哪些 Action 指向这个 State）

**合并逻辑**：
```
写入新 PageInstance 时：
    1. 检查是否已有 AbstractState 包含相同 URL
    2. 如果有 → 复用该 AbstractState（使用已有 ID）
    3. 如果没有 → 创建新 AbstractState（新 UUID）
```

```python
class AbstractState:
    id: str                       # UUID，随机生成
    instances: List[PageInstance] # URL 在这里记录
    # incoming_actions 由图结构隐式记录（哪些 Action.target == this.id）
```

### 8.4 URL 索引实现

**决策**：使用内存 Dict 实现 URL 到 State 的快速查找。

```python
class URLIndex:
    # url -> state_id
    _url_to_state: Dict[str, str]

    def find_state_by_url(self, url: str) -> Optional[str]
    def add_url(self, url: str, state_id: str)
    def build_from_graph(self, graph: GraphStore)
```

**原因**：
- 查询 O(1)，快速
- 方便 debug
- 启动时从图加载构建索引

### 8.5 State 实时合并

**决策**：写入时检测 URL，直接复用已有 State，不产生新 State。

**流程**：
```
新 PageInstance 进来：
    1. 查 URL 索引
    2. 如果存在 → 复用已有 State，添加 instance
    3. 如果不存在 → 创建新 State
```

**好处**：不会产生需要后续合并的冗余 State。

### 8.6 IntentSequence 按 description 去重

**决策**：相同 description 的 IntentSequence 只保留一个。

**原因**：
- 避免完全重复的操作序列
- 节省存储空间
- 保留不同操作方式（description 不同则保留）

### 8.7 Domain 保留

**决策**：保留 Domain 概念，代表 baseurl 或某个 app。

**关系**：
```
Domain (taobao.com)
    └── State (首页)
    └── State (搜索结果页)
    └── State (商品详情页)
```

### 8.8 URL 精确匹配（含参数）

**决策**：URL 匹配包含 query 参数，不同参数视为不同 State。

**原因**：
```
s.taobao.com/search?q=咖啡机   → State A
s.taobao.com/search?q=手机     → State B

amazon.com/best-sellers        → State C
amazon.com/top-rated           → State D
```

不同参数可能代表完全不同的语义（如 best seller vs top comment）。

### 8.9 空 IntentSequence 不创建

**决策**：如果 Segment 没有任何操作（只有 navigate），不创建 IntentSequence。

**原因**：
- 空序列没有语义价值
- 减少无用数据

### 8.10 Action 不自动合并

**设计决策**：Action 不通过起点+终点自动合并。

**原因**：从 A 到 B 可能存在多种不同的方式：
- 点击不同的按钮
- 不同的菜单路径
- 快捷键 vs 鼠标操作

每种方式都是有意义的操作路径，应该保留。

```
例子：
首页 → 产品详情页 可能有多条 Action：
    - Action 1: "点击搜索结果中的产品"
    - Action 2: "点击首页推荐的产品"
    - Action 3: "点击收藏夹中的产品"

这三条 Action 都是有效的，不应合并。
```

---

## 9. 操作序列处理流程

### 9.1 输入数据格式

用户操作序列（来自浏览器录制）：

```python
events = [
    {"type": "navigate", "url": "https://example.com", "title": "首页", "timestamp": 1000},
    {"type": "click", "element": {...}, "url": "https://example.com", "timestamp": 1001},
    {"type": "input", "value": "搜索词", "url": "https://example.com", "timestamp": 1002},
    {"type": "navigate", "url": "https://example.com/search", "title": "搜索结果", "timestamp": 1003},
    {"type": "click", "element": {...}, "url": "https://example.com/search", "timestamp": 1004},
    {"type": "navigate", "url": "https://example.com/product/123", "title": "商品详情", "timestamp": 1005},
]
```

### 9.2 处理步骤

```
Step 1: 按 URL 分段
    将事件序列按 navigate 事件分割成多个段落，每段对应一个页面：

    Segment 1: url="https://example.com"
        events: [click, input]

    Segment 2: url="https://example.com/search"
        events: [click]

    Segment 3: url="https://example.com/product/123"
        events: []

Step 2: 处理每个段落
    对于每个 Segment：

    2.1 查找或创建 AbstractState
        - 检查 URL 是否已存在于某个 AbstractState 的 instances 中
        - 如果存在 → 复用该 AbstractState
        - 如果不存在 → 创建新 AbstractState

    2.2 添加 PageInstance
        - 创建新的 PageInstance（url, title, timestamp）
        - 添加到 AbstractState.instances

    2.3 创建 IntentSequence
        - 将 Segment 中的 events 转换为 Intent 列表
        - 创建 IntentSequence（包含 description + embedding）
        - 添加到 AbstractState.intent_sequences

Step 3: 创建 Action（边）
    对于相邻的两个 Segment：

    - source = Segment[i] 的 AbstractState
    - target = Segment[i+1] 的 AbstractState
    - 创建 Action（source → target）
    - Action 的 description 由 LLM 生成（如"点击搜索按钮跳转到搜索结果页"）

Step 4: 生成 Embedding
    - AbstractState.embedding_vector = embed(description)
    - IntentSequence.embedding_vector = embed(description)
    - （可选）Intent.embedding_vector = embed(description)
```

### 9.3 LLM 调用时机

以下内容需要 LLM 生成 description：

| 对象 | 何时调用 LLM | 生成内容 |
|------|-------------|----------|
| AbstractState | 创建新 State 时 | 页面语义描述（如"ProductHunt 产品详情页"） |
| Action | 创建新 Action 时 | 跳转描述（如"点击产品列表项进入详情页"） |
| IntentSequence | 创建新序列时 | 操作序列描述（如"输入搜索词并点击搜索"） |

**注意**：复用已有 AbstractState 时，不需要重新调用 LLM 生成 description。

### 9.4 完整流程图

```
用户操作序列
      │
      ▼
┌─────────────────┐
│ 1. 按 URL 分段   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ 2. 对每个 Segment：                              │
│    ┌─────────────────────────────────────────┐  │
│    │ 2.1 URL 在现有 AbstractState 中？        │  │
│    │     - 是 → 复用 AbstractState            │  │
│    │     - 否 → 创建新 AbstractState + LLM    │  │
│    └─────────────────────────────────────────┘  │
│    ┌─────────────────────────────────────────┐  │
│    │ 2.2 添加 PageInstance                    │  │
│    └─────────────────────────────────────────┘  │
│    ┌─────────────────────────────────────────┐  │
│    │ 2.3 创建 IntentSequence + LLM + Embed   │  │
│    └─────────────────────────────────────────┘  │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ 3. 创建 Action（相邻 Segment 之间）+ LLM        │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│ 4. 批量生成 Embedding                           │
│    - AbstractState.embedding_vector             │
│    - IntentSequence.embedding_vector            │
└────────┬────────────────────────────────────────┘
         │
         ▼
     存储到图
```

### 9.5 示例

输入：淘宝搜索咖啡机的操作序列

```
events = [
    navigate → taobao.com
    click → 搜索框
    input → "咖啡机"
    click → 搜索按钮
    navigate → s.taobao.com/search?q=咖啡机
    click → 商品列表项
    navigate → detail.taobao.com/item.htm?id=123
]
```

处理结果：

```
AbstractState 节点：
    AS1: "淘宝首页"
        instances: [taobao.com]
        intent_sequences: [
            IntentSequence("在搜索框输入咖啡机并点击搜索", [click, input, click])
        ]

    AS2: "淘宝搜索结果页"
        instances: [s.taobao.com/search?q=咖啡机]
        intent_sequences: [
            IntentSequence("点击商品列表项", [click])
        ]

    AS3: "淘宝商品详情页"
        instances: [detail.taobao.com/item.htm?id=123]
        intent_sequences: []

Action 边：
    AS1 → AS2: "点击搜索按钮跳转到搜索结果"
    AS2 → AS3: "点击商品列表项进入商品详情"
```

---

## 10. 性能分析

### 10.1 模型调用清单

处理单次操作序列时的模型调用：

| 调用类型 | 数量 | 触发条件 | 单次耗时 |
|----------|------|----------|----------|
| LLM: State description | 0~N | 仅新 State 需要 | 1-2s |
| LLM: Action description | N-1 | 每条边 1 次 | 1-2s |
| LLM: IntentSequence description | 0~N | 非空 Segment | 1-2s |
| Embedding: State | 0~N | 仅新 State | 0.1-0.3s |
| Embedding: IntentSequence | 0~N | 非空 Segment | 0.1-0.3s |

（N = Segment 数量，即页面数量）

### 10.2 耗时估算

以 3 个页面的操作序列为例：

| 场景 | LLM 调用 | Embedding 调用 | 串行耗时 |
|------|----------|----------------|----------|
| 全新页面 | 3+2+2=7 次 | 3+2=5 次 | ~11.5s |
| 部分复用（1新2旧） | 1+2+2=5 次 | 1+2=3 次 | ~8s |
| 全复用 | 0+2+2=4 次 | 0+2=2 次 | ~6.4s |

### 10.3 优化方案

| 方案 | 说明 | 效果 |
|------|------|------|
| **批量 LLM** | 合并多个 description 生成为一次调用 | 7次 → 1-2次，~10s → ~3s |
| **批量 Embedding** | `embed_batch()` 一次处理多个文本 | 5次 → 1次，~1s → ~0.3s |
| **异步处理** | 用户提交后立即返回，后台构建 | 用户等待 0s |
| **延迟 Embedding** | 先存储，查询时再生成 | 写入更快 |

### 10.4 实现阶段

| 阶段 | 方案 | 预期耗时 |
|------|------|----------|
| MVP | 串行调用 + 同步等待 | ~10s |
| 优化 1 | 批量 LLM + 批量 Embedding | ~3-4s |
| 优化 2 | 异步处理 | 用户无感知 |
