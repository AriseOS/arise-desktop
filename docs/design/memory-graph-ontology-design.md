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

### 4.1 核心思路：从终点往回找起点

用户查询描述的是"想做什么"，通常终点（目标页面）比较明确，但起点不确定。

**关键洞察**：
- 终点容易通过语义检索找到
- 起点需要从终点往回追溯
- 好的起点 = 用户可以直接访问的稳定 URL

### 4.2 起点的判断标准

| 优先级 | 起点类型 | 判断条件 | 说明 |
|--------|----------|----------|------|
| 1 | 无入边的 State | `incoming_actions = 0` | 用户手动输入的 URL，最可靠 |
| 2 | Domain 首页 | `url = domain.com/` | 最保守的起点 |
| 3 | 多实例稳定 URL | 多个 PageInstance 且 URL 相同 | URL 被多次访问且不变 |
| 4 | 单实例 URL | 只有 1 个 PageInstance | 暂时当作稳定，以后会学到更多 |

**特殊情况**：用户手动输入子路径（如 `github.com/trending`）
- 这个 State 没有入边（没有从其他页面跳转过来）
- 说明用户认为这是一个"已知的"、可直接访问的入口
- 应该作为起点，不需要再往前追溯到 `github.com/`

### 4.3 关键节点匹配（重要设计）

**问题**：用户查询可能涉及多个关键概念，如"周榜的产品团队页面"包含"周榜"和"团队"两个概念。

**解决方案**：
1. 检索到的高分 State 都是"关键节点"
2. 路径得分不仅看终点分数，还要看路径中包含了多少关键节点
3. 包含更多关键节点的路径得分更高

**关键节点判定**：
```
检索结果中 score > min_score 的 State 都是关键节点

例：query = "周榜的产品团队页面"
    State(周榜页) score=0.85 ✓ 关键节点
    State(团队页) score=0.82 ✓ 关键节点
    State(详情页) score=0.65 ✓ 关键节点
    State(首页)   score=0.45 ✗ 不是关键节点
```

**路径得分计算**：
```
path_score = has_target * target_weight * target_score
           + key_type_coverage * key_weight

其中:
    - has_target: 路径终点是否匹配 target_query 检索到的 State（0 或 1）
    - target_weight: 终点权重（1.0，最重要）
    - target_score: 终点的 embedding 相似度分数（0.0-1.0）
    - key_type_coverage: 覆盖的 key 类型数 / 总 key 类型数
      注意：同一类型的多个节点只算一次！
    - key_weight: 中间节点权重（0.3）
```

**核心思想**：
1. **终点最重要**：没有匹配到终点的路径，分数为 0 或很低
2. **按类型计算覆盖**：key_queries 中每种类型只计算一次，避免同类型节点重复加分
3. **不考虑路径长度**：长短交给模型最终判断，我们只按分数排序

**排序规则**：
```
paths.sort(key=lambda x: -x["score"])  # 只按分数排序
```

**示例**：
```
target_query = "团队成员信息页面"
key_queries = ["周榜页面", "产品详情页"]，共 2 种类型

路径 1: 周榜页A → 详情页A → 团队页
        has_target = 1, target_score = 0.85
        覆盖类型: 周榜页面✓ 产品详情页✓ = 2/2 = 1.0
        得分 = 1 * 1.0 * 0.85 + 1.0 * 0.3 = 1.15

路径 2: 周榜页A → 周榜页B → 团队页
        has_target = 1, target_score = 0.85
        覆盖类型: 周榜页面✓ = 1/2 = 0.5（两个周榜页只算一种类型）
        得分 = 1 * 1.0 * 0.85 + 0.5 * 0.3 = 1.0

路径 3: 首页 → 搜索页 → 详情页A（终点不是团队页）
        has_target = 0
        得分 = 0 + 0.5 * 0.3 = 0.15

路径 1 得分最高 ✓
```

### 4.4 Query 分解（重要设计）

**问题**：用户 query 是任务意图，State description 是页面内容描述，语义空间不同。

```
Query: "收集产品信息，判断有没有中国人"  → 任务意图
State: "展示创建团队成员和员工信息"      → 页面内容描述

直接 embedding 匹配效果差：
- "团队页面" 明明最相关，但只有 0.616 分
- "周榜页面" 反而排第一，因为包含"产品"关键词
```

**解决方案**：用 LLM 从 query 中提取页面概念

**核心原则**：只提取用户 query 中**已经描述**的页面概念，不要让模型"推理"或"补充"用户没提到的中间步骤。

```
用户 Query: "收集 Product hunt 周榜上的产品信息，并且根据团队信息判断是不是有中国人"

LLM 分解结果:
{
    "target_query": "产品团队成员信息页面",     // 单个，最终目标页面
    "key_queries": ["周榜页面", "产品详情页"]   // 列表，用户提到的中间页面类型
}
```

**注意**：
- `target_query` 是单个字符串，代表最终目标
- `key_queries` 是列表，每个元素代表一种中间页面类型
- 只提取用户明确提到的概念，不补充推测

**LLM Prompt**：
```
你是一个网页导航专家。用户想要完成一个任务，我需要用 embedding 搜索找到相关的网页。
请从用户的描述中提取页面概念。

用户任务: {query}

请返回 JSON 格式：
{
    "target_query": "最终需要到达的页面的内容描述",
    "key_queries": ["用户描述中提到的中间页面类型"]
}

注意：
- 用页面展示的内容来描述，不要用动作词（如"查看"、"点击"）
- 只提取用户明确提到的页面概念，不要补充或推测
- 如果用户没有提到中间步骤，key_queries 为空数组
- 描述要简洁，便于语义匹配
```

### 4.5 查询步骤

```
用户查询: "收集周榜产品的团队信息"

Step 1: LLM 分解 Query
    decomposed = llm_decompose(query)
    → target_pages: ["团队成员页面"]
    → key_pages: ["周榜页面", "产品详情页"]
    → entry_pages: ["Product Hunt 首页"]

Step 2: 分别检索各类页面
    target_states = search("团队成员页面") → [(团队页, 0.85)]
    key_states = search("周榜页面") → [(周榜页, 0.82)]
                 search("产品详情页") → [(详情页, 0.78)]
    entry_states = search("首页") → [(首页, 0.90)]

Step 3: 从 target_states 往回搜索路径
    - 遍历入边，递归找所有路径
    - 停止条件: 无入边 / Domain 首页 / max_depth

Step 4: 计算路径得分
    对每条路径:
        key_node_hits = count(路径中的 State ∩ key_states)
        path_score = target_score + (key_node_hits / len(key_states)) * 0.3

Step 5: 排序并返回
    - 主排序: 关键节点覆盖率（高 → 低）
    - 次排序: 路径长度（短 → 长）
    - 返回 top_k 条路径
```

### 4.6 停止条件（什么时候不用往前追了）

1. **到达无入边的 State** — 天然起点，用户手动输入的入口
2. **到达 Domain 首页** — 最保守的起点
3. **到达 max_depth** — 防止无限搜索

### 4.7 示例

```
用户查询: "周榜的产品团队页面"

Step 1: 找关键节点
    embed(query) →
        State(周榜页) score=0.85 ✓
        State(团队页) score=0.82 ✓
        State(详情页) score=0.65 ✓
    关键节点集合 = {周榜页, 团队页, 详情页}

Step 2: 选择终点
    团队页有入边，作为终点往回找

Step 3: 往回搜索
    路径 1: 周榜页 → 详情页 → 团队页
            起点: 周榜页（无入边，用户手动输入）
            命中关键节点: 3/3

    路径 2: 首页 → 搜索页 → 详情页 → 团队页
            起点: 首页（无入边）
            命中关键节点: 2/3（详情页、团队页）

Step 4: 计算得分
    路径 1: 0.82 + (3/3) * 0.3 = 1.12 ✓ 最高
    路径 2: 0.82 + (2/3) * 0.3 = 1.02

Step 5: 返回
    {
        "paths": [{
            "score": 1.12,
            "key_nodes_hit": 3,
            "key_nodes_total": 3,
            "start_url": "https://producthunt.com/leaderboard/weekly",
            "steps": [
                {state: 周榜页, action: 点击产品, intent_sequence: 浏览榜单},
                {state: 详情页, action: 点击Team, intent_sequence: 查看产品信息},
                {state: 团队页, action: null, intent_sequence: 查看团队成员}
            ]
        }]
    }
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
| Action/IntentSequence 检索 | Query 时同时搜索 Action 和 IntentSequence 的 embedding，提高匹配准确度 | P2 |

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
