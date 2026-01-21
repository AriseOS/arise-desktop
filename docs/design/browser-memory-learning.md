# 浏览器操作记忆学习与检索设计

## 概述

本文档描述浏览器自动化系统的学习和检索能力设计。目标是：

1. **学习**：当用户录制浏览器操作时，将其存储到记忆中作为可复用的知识
2. **检索**：当用户发起新任务时，检索相似的历史路径，用于改进 plan 生成

## 现有架构分析

### 录制流程（现有）

```
用户点击 "Record" → CDP Recorder 捕获操作 → 用户点击 "Stop"
    → 用户点击 "Upload to Cloud"
    → POST /api/v1/recordings (Cloud Backend)
```

**Cloud Backend 处理流程 (main.py):**

| 步骤 | 组件 | 说明 |
|------|------|------|
| 1 | GraphBuilder.build() | 确定性（无 LLM）将操作转换为 State/Action 图 |
| 2 | workflow_memory.create_state() | 将 State 存入内存 |
| 3 | workflow_memory.create_action() | 将 Action 存入内存 |
| 4 | storage_service.save_recording() | 保存到文件系统 |
| 5 | add_intents_to_user_graph_background() | 异步：用 LLM 提取 intents |

### 记忆系统 (memgraph/)

**本体模型：**

| 模型 | 说明 | 当前使用情况 |
|------|------|-------------|
| `Domain` | 网站/应用标识（如 taobao.com） | ❌ 未创建 |
| `State` | 页面状态（URL + 标题 + intents） | ✅ 从 GraphBuilder 创建 |
| `Intent` | 页面内操作（click, type, scroll） | ✅ 嵌入在 State.intents 中 |
| `Action` | 页面跳转（State A → State B） | ✅ 从 GraphBuilder 创建 |
| `CognitivePhrase` | 完整任务路径（描述 + state_path + action_path） | ❌ 未创建 |
| `Manage` | Domain → State 关系 | ❌ 未创建 |

**存储：**

| 方面 | 当前状态 | 问题 |
|------|---------|------|
| 后端 | NetworkXGraph（内存） | 重启后丢失 |
| 持久化 | 无 | 需要磁盘存储 |
| 用户隔离 | 无 | 所有用户共享一个 memory |

### Quick Task 流程（现有）

```
用户输入任务 → EigentBrowserAgent.execute()
    → 获取页面快照
    → LLM 生成 plan + action
    → 执行 action，循环
```

**当前 LLM Prompt (eigent_browser_agent.py):**
- 任务描述
- 当前页面快照
- 执行历史（执行过程中）
- ❌ 无历史参考路径

## 设计方案

### 1. 增强的学习流程

当录制上传时，应创建完整的记忆结构：

```
POST /api/v1/recordings
    ↓
GraphBuilder.build() → states, actions
    ↓
┌─────────────────────────────────────────┐
│ 增强的记忆创建：                          │
│                                         │
│ 1. 创建 Domain                          │
│    - 从 URL 提取域名                     │
│    - 例如从 "https://www.taobao.com/search" │
│      提取 "taobao.com"                  │
│                                         │
│ 2. 创建 States（现有）                   │
│    - 页面 URL、标题、intents             │
│                                         │
│ 3. 创建 Actions（现有）                  │
│    - 页面跳转                           │
│                                         │
│ 4. 创建 Manage 边                       │
│    - 连接 Domain → States               │
│    - 记录访问次数                        │
│                                         │
│ 5. 创建 CognitivePhrase（新增）          │
│    - task_description                   │
│    - state_path: [state_id1, state_id2] │
│    - action_path: [action_type1, ...]   │
│    - user_id, session_id                │
│    - 时间戳                             │
└─────────────────────────────────────────┘
    ↓
持久化到磁盘
```

**CognitivePhrase 结构：**

```python
CognitivePhrase(
    id="phrase_xxx",
    description="在淘宝搜索商品并查看详情",  # 来自 task_description
    user_id="user123",
    session_id="recording_xxx",
    start_timestamp=1704067200000,
    end_timestamp=1704067500000,
    duration=300000,
    state_path=["state_1", "state_2", "state_3"],  # 有序的 state ID 列表
    action_path=["navigate", "click", "type", "click"],  # action 类型列表
    embedding_vector=[...],  # 用于语义搜索（可选）
    access_count=0,
    created_at=1704067200000
)
```

### 2. 记忆持久化

**存储位置：**
```
~/ami-server/users/{user_id}/memory/
├── workflow_memory.json      # 主记忆导出
└── memory_index.json         # 元数据（最后更新时间、统计）
```

**持久化策略：**

| 事件 | 动作 |
|------|------|
| 服务器启动 | 从磁盘加载所有用户记忆 |
| 录制上传 | 学习后保存用户记忆 |
| 定期（每 5 分钟） | 自动保存所有修改的记忆 |
| 服务器关闭 | 保存所有记忆 |

**记忆导出格式 (workflow_memory.json):**
```json
{
  "version": "1.0",
  "user_id": "user123",
  "exported_at": "2025-01-20T10:00:00Z",
  "states": [
    {
      "id": "state_xxx",
      "page_url": "https://taobao.com",
      "page_title": "淘宝",
      "intents": [...],
      ...
    }
  ],
  "actions": [
    {
      "source": "state_1",
      "target": "state_2",
      "type": "click",
      ...
    }
  ],
  "domains": [
    {
      "id": "domain_xxx",
      "domain_url": "taobao.com",
      "domain_name": "淘宝",
      ...
    }
  ],
  "manages": [...],
  "phrases": [
    {
      "id": "phrase_xxx",
      "description": "在淘宝搜索商品",
      "state_path": ["state_1", "state_2"],
      "action_path": ["navigate", "click"],
      ...
    }
  ]
}
```

### 3. 检索 API

**新端点：**

```
POST /api/v1/memory/retrieve
```

**请求：**
```json
{
  "task_description": "帮我在淘宝搜索 iPhone 16",
  "start_url": "https://taobao.com",  // 可选
  "user_id": "user123",
  "top_k": 3
}
```

**响应：**
```json
{
  "paths": [
    {
      "phrase_id": "phrase_xxx",
      "description": "在淘宝搜索商品并查看详情",
      "similarity": 0.85,
      "domain": "taobao.com",
      "steps": [
        {
          "state": {
            "page_url": "https://taobao.com",
            "page_title": "淘宝首页"
          },
          "intents": [
            {"type": "click", "element": "搜索框"},
            {"type": "type", "text": "商品名称"}
          ],
          "action_to_next": "click"
        },
        {
          "state": {
            "page_url": "https://s.taobao.com/search",
            "page_title": "搜索结果"
          },
          "intents": [
            {"type": "click", "element": "商品链接"}
          ],
          "action_to_next": "click"
        }
      ]
    }
  ]
}
```

**检索算法：**

```python
def retrieve_relevant_paths(task_description, start_url, user_id, top_k):
    # 1. 语义搜索：通过描述找相似的 CognitivePhrase
    similar_phrases = memory.phrase_manager.search_phrases_by_embedding(
        query_vector=embed(task_description),
        top_k=top_k * 2  # 获取更多候选
    )

    # 2. 域名匹配：对匹配域名的 phrase 加分
    if start_url:
        domain = extract_domain(start_url)
        for phrase in similar_phrases:
            if phrase_has_domain(phrase, domain):
                phrase.similarity *= 1.5  # 提升分数

    # 3. 时间权重：优先最近访问的 phrase
    for phrase in similar_phrases:
        recency_factor = compute_recency(phrase.last_access_time)
        phrase.similarity *= recency_factor

    # 4. 排序并返回 top_k
    similar_phrases.sort(key=lambda p: p.similarity, reverse=True)
    return similar_phrases[:top_k]
```

### 4. Agent 集成

**修改后的 EigentBrowserAgent.execute():**

```python
async def execute(self, input_data, context):
    task = input_data.data.get("task")
    start_url = input_data.data.get("start_url")

    # 新增：从记忆中检索历史路径
    historical_paths = await self._retrieve_historical_paths(
        task_description=task,
        start_url=start_url,
        user_id=context.user_id
    )

    # 初始化浏览器，导航到 start_url
    await self._session.visit(start_url)

    # 获取初始快照
    snapshot = await self._session.get_snapshot()

    # 使用历史上下文生成 plan
    plan_response = self._llm_call(
        prompt=task,
        snapshot=snapshot,
        historical_paths=historical_paths,  # 新增
        is_initial=True
    )

    # ... 后续执行循环
```

**增强的 LLM System Prompt:**

```python
SYSTEM_PROMPT = """你是一个浏览器自动化代理...

{historical_context}  # 新增部分

当前页面快照：
{snapshot}

任务：{task}
"""

def build_historical_context(paths):
    if not paths:
        return ""

    context = "## 参考：之前完成的类似任务\n\n"
    for i, path in enumerate(paths):
        context += f"### 路径 {i+1}：{path['description']}\n"
        context += f"相似度：{path['similarity']:.0%}\n"
        context += "步骤：\n"
        for j, step in enumerate(path['steps']):
            context += f"  {j+1}. 页面：{step['state']['page_title']}\n"
            for intent in step['intents']:
                context += f"     - {intent['type']}：{intent.get('element', intent.get('text', ''))}\n"
        context += "\n"

    context += "请参考这些路径，但要根据当前页面状态进行调整。\n\n"
    return context
```

## 实现计划

### 阶段 1：增强学习

**需要修改的文件：**
- `src/cloud_backend/main.py` - 添加 Domain 和 CognitivePhrase 创建
- `src/cloud_backend/memgraph/memory/workflow_memory.py` - 验证 create 方法

**任务：**
1. 从录制 URL 中提取域名
2. 创建 Domain 实体
3. 创建 Manage 边（Domain → State）
4. 从录制创建 CognitivePhrase

### 阶段 2：记忆持久化

**需要创建/修改的文件：**
- `src/cloud_backend/services/memory_persistence_service.py` - 新建
- `src/cloud_backend/main.py` - 添加加载/保存钩子

**任务：**
1. 实现 save_user_memory(user_id)
2. 实现 load_user_memory(user_id)
3. 添加启动时加载
4. 添加定期自动保存
5. 添加关闭时保存

### 阶段 3：检索 API

**需要创建/修改的文件：**
- `src/cloud_backend/routers/memory.py` - 新建路由
- `src/cloud_backend/services/memory_retrieval_service.py` - 新建服务
- `src/cloud_backend/main.py` - 注册路由

**任务：**
1. 实现 CognitivePhrase 语义搜索
2. 实现域名匹配加分
3. 实现时间权重
4. 创建 REST API 端点
5. 格式化响应（包含完整路径详情）

### 阶段 4：Agent 集成

**需要修改的文件：**
- `src/clients/desktop_app/ami_daemon/services/quick_task_service.py` - 添加记忆检索调用
- `src/clients/desktop_app/ami_daemon/agents/eigent_browser_agent.py` - 注入历史上下文

**任务：**
1. 执行前调用 Cloud Backend 检索 API
2. 构建历史上下文字符串
3. 注入到 LLM system prompt
4. 处理无历史路径的情况

## 设计分析：为什么这样存储数据

### 核心问题

在设计 Memory 系统之前，需要回答几个关键问题：

1. **存储什么？** - 哪些数据值得保存
2. **为什么存储？** - 这些数据未来怎么用
3. **怎么检索？** - 用户需求如何匹配到历史数据

### 当前设计的目标

```
用户录制了一次"在淘宝搜索 iPhone"的操作
                    ↓
              保存到 Memory
                    ↓
下次用户说"帮我在淘宝搜索 AirPods"时
                    ↓
        检索到相似的历史路径，指导 Agent 执行
```

**核心假设**：相似的任务有相似的操作路径

### 为什么需要这六个模型？

| 模型 | 为什么需要 | 不存会怎样 |
|------|-----------|-----------|
| **State** | 记录"在哪个页面" | 无法知道任务涉及哪些页面 |
| **Intent** | 记录"在页面上做什么" | 只知道去了哪些页面，不知道具体操作 |
| **Action** | 记录"页面间如何跳转" | 无法构建导航路径图 |
| **Domain** | 按网站分组 | 无法快速筛选"淘宝相关"的路径 |
| **Manage** | 统计访问频率 | 无法区分常用页面和偶尔访问的页面 |
| **CognitivePhrase** | 任务级别的完整路径 | 只有碎片化的状态，无法匹配"任务" |

### 检索场景分析

**场景 1：语义匹配**
```
用户："帮我在京东买个耳机"
         ↓
需要匹配："在京东购买商品"的历史路径
         ↓
匹配目标：CognitivePhrase.description
```
→ 需要：`CognitivePhrase` + `embedding_vector`

**场景 2：域名过滤**
```
用户："帮我在淘宝搜索 iPhone"
         ↓
优先返回：淘宝相关的历史路径
         ↓
过滤条件：Domain.domain_url = "taobao.com"
```
→ 需要：`Domain` + `Manage`（关联 State）

**场景 3：获取具体操作**
```
找到匹配的 CognitivePhrase 后
         ↓
需要知道：每个页面上具体做什么
         ↓
查询：State.intents
```
→ 需要：`State` + `Intent`

**场景 4：路径导航**
```
Agent 当前在页面 A
         ↓
目标是到达页面 C
         ↓
查询：从 A 到 C 的可能路径
```
→ 需要：`Action`（图的边）

### 当前设计的问题

#### 问题 1：State 粒度太粗

```
当前：一个 URL = 一个 State

问题：同一个 URL 可能有不同的页面状态
- taobao.com/search?q=iPhone  (搜索 iPhone)
- taobao.com/search?q=AirPods (搜索 AirPods)
→ 被认为是同一个 State？还是不同的 State？

当前实现：query string 不同 = 不同的 URL = 不同的 State
```

#### 问题 2：Intent 缺乏语义

```
当前 Intent 保存：
- type: "click"
- text: "搜索"
- xpath: "//button[@class='search-btn']"

问题：xpath 在不同网站上不通用
- 淘宝的搜索按钮 xpath 和京东的不同
- 无法泛化到"点击搜索按钮"这个语义

需要：Intent 也应该有语义描述/embedding
```

#### 问题 3：CognitivePhrase 太依赖精确匹配

```
当前检索逻辑：
1. 用户输入 → embedding
2. 与 CognitivePhrase.embedding_vector 计算相似度
3. 返回最相似的路径

问题：
- "在淘宝搜索 iPhone" 和 "在京东搜索耳机" 语义相似
- 但操作路径完全不同（不同网站）
- 返回淘宝的路径对京东任务没用

需要：结合域名、操作模式等多维度匹配
```

#### 问题 4：缺乏操作模式抽象

```
理想情况：
"电商搜索" 模式 = [
    1. 找到搜索框
    2. 输入关键词
    3. 点击搜索
    4. 浏览结果
]

这个模式应该可以应用到：淘宝、京东、亚马逊...

当前问题：每个网站的路径独立存储，无法抽象出通用模式
```

### 改进方向

#### 方向 1：增加 Intent 语义

```python
Intent(
    type="click",
    text="搜索",
    xpath="//button[@class='search-btn']",

    # 新增：语义标签
    semantic_role="search_button",  # 语义角色
    description="点击搜索按钮提交搜索",
    embedding_vector=[...]  # Intent 级别的 embedding
)
```

#### 方向 2：操作模式模板

```python
OperationPattern(
    name="电商搜索",
    description="在电商网站搜索商品",
    steps=[
        {"role": "search_input", "action": "click"},
        {"role": "search_input", "action": "type", "param": "{keyword}"},
        {"role": "search_button", "action": "click"},
    ],
    applicable_domains=["taobao.com", "jd.com", "amazon.com"]
)
```

#### 方向 3：多维度检索

```python
def retrieve(task_description, start_url):
    # 1. 语义相似度
    semantic_candidates = search_by_embedding(task_description)

    # 2. 域名匹配
    domain = extract_domain(start_url)
    domain_candidates = filter_by_domain(semantic_candidates, domain)

    # 3. 操作模式匹配
    task_pattern = extract_pattern(task_description)  # "搜索" → search_pattern
    pattern_candidates = filter_by_pattern(domain_candidates, task_pattern)

    # 4. 综合排序
    return rank_candidates(pattern_candidates, [
        ("semantic_similarity", 0.4),
        ("domain_match", 0.3),
        ("pattern_match", 0.2),
        ("recency", 0.1)
    ])
```

### 数据使用场景总结

| 使用场景 | 需要的数据 | 当前支持 | 缺失 |
|---------|-----------|---------|------|
| 语义搜索任务 | CognitivePhrase.embedding | ⚠️ 接口有，未生成 | embedding 生成 |
| 按网站筛选 | Domain, Manage | ⚠️ 模型有，未创建 | 创建逻辑 |
| 获取具体操作 | State.intents | ✅ 已实现 | - |
| 路径导航 | Action | ✅ 已实现 | - |
| 操作泛化 | Intent.semantic_role | ❌ 无 | 语义角色 |
| 模式复用 | OperationPattern | ❌ 无 | 模式抽象 |

### 最小可行方案（MVP）

考虑到当前的实现状态，建议先实现一个最小可行方案：

```
Phase 1: 基础学习与检索（当前目标）
├── 创建 CognitivePhrase（来自 task_description）
├── 生成 embedding（用于语义搜索）
├── 创建 Domain（用于域名过滤）
└── 实现基础检索 API

Phase 2: 增强检索
├── 多维度排序（语义 + 域名 + 时间）
├── Intent 语义标签
└── 访问频率权重

Phase 3: 模式抽象（未来）
├── 操作模式识别
├── 跨网站模式复用
└── 模式学习与优化
```

---

## 本体论详解：数据模型与提取逻辑

### 概念关系图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           用户浏览器操作                                  │
│                                                                         │
│  用户在淘宝搜索 iPhone：                                                  │
│  1. 打开 taobao.com                                                     │
│  2. 点击搜索框                                                          │
│  3. 输入 "iPhone 16"                                                    │
│  4. 点击搜索按钮                                                         │
│  5. 页面跳转到搜索结果                                                    │
│  6. 点击第一个商品                                                        │
│  7. 页面跳转到商品详情                                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        GraphBuilder 提取（无 LLM）                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                             本体论模型                                   │
│                                                                         │
│  ┌─────────────┐                                                        │
│  │   Domain    │  ← 网站：taobao.com                                    │
│  └──────┬──────┘                                                        │
│         │ [MANAGES]                                                     │
│         ▼                                                               │
│  ┌─────────────┐     [ACTION]      ┌─────────────┐     [ACTION]        │
│  │   State 1   │ ─────────────────→│   State 2   │─────────────────→   │
│  │  (首页)     │                   │ (搜索结果)   │                     │
│  │             │                   │             │                     │
│  │ Intents:    │                   │ Intents:    │                     │
│  │ - click     │                   │ - click     │                     │
│  │ - type      │                   │   商品链接   │                     │
│  │ - click     │                   │             │                     │
│  └─────────────┘                   └─────────────┘                     │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ CognitivePhrase: "在淘宝搜索商品并查看详情"                        │   │
│  │ state_path: [State1, State2, State3]                            │   │
│  │ action_path: [Navigate, Navigate]                               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1. State（页面状态）

**定义**：用户当前所在的页面/屏幕位置

**保存的数据**：
| 字段 | 类型 | 说明 | 用途 |
|------|------|------|------|
| `id` | string | 唯一标识符 | 图中节点 ID |
| `page_url` | string | 页面 URL | **核心**：标识用户位置 |
| `page_title` | string | 页面标题 | 辅助识别页面 |
| `timestamp` | int | 进入时间（毫秒） | 时序分析 |
| `end_timestamp` | int | 离开时间 | 计算停留时长 |
| `duration` | int | 停留时长 | 行为分析 |
| `intents` | List[Intent] | 页面内的操作列表 | **核心**：记录用户做了什么 |
| `user_id` | string | 用户 ID | 用户隔离 |
| `session_id` | string | 会话 ID | 录制批次区分 |
| `embedding_vector` | List[float] | 语义向量 | **检索**：语义搜索 |
| `description` | string | 自然语言描述 | 可读性、搜索 |

**提取规则**（100% 规则，无 LLM）：
```python
# State 由 (URL, page_root) 元组唯一确定
state_key = hash(f"{event.url}|{event.page_root}")

# page_root 取值：
# - "main"   → 普通页面
# - "iframe" → URL 包含 "iframe"
# - "modal"  → page_title 包含 "modal"

# 新 State 创建条件：
# 1. URL 路径变化
# 2. page_root 变化（如从主页面进入 iframe）
```

**示例**：
```python
# 输入：用户在登录页的操作
[
    {"type": "click", "url": "https://taobao.com/login", "element": {"text": "用户名输入框"}},
    {"type": "input", "url": "https://taobao.com/login", "data": {"value": "user123"}},
    {"type": "click", "url": "https://taobao.com/login", "element": {"text": "登录按钮"}},
]

# 输出：一个 State（因为 URL 没变）
State {
    id: "state_001",
    page_url: "https://taobao.com/login",
    page_title: "淘宝登录",
    intents: [
        Intent(type="click", text="用户名输入框"),
        Intent(type="input", value="user123"),
        Intent(type="click", text="登录按钮")
    ]
}
```

---

### 2. Intent（页面内操作）

**定义**：在某个 State（页面）内执行的原子操作，**不会导致页面跳转**

**保存的数据**：
| 字段 | 类型 | 说明 | 用途 |
|------|------|------|------|
| `id` | string | 唯一标识符 | 引用 |
| `state_id` | string | 所属 State ID | **核心**：关联到页面 |
| `type` | string | 操作类型 | click/input/scroll 等 |
| `timestamp` | int | 操作时间 | 时序分析 |
| `page_url` | string | 操作所在页面 | 冗余，便于查询 |
| `element_id` | string | 元素 ID | 定位元素 |
| `element_tag` | string | 元素标签 | button/input/a 等 |
| `xpath` | string | XPath | **重放**：精确定位元素 |
| `css_selector` | string | CSS 选择器 | 备选定位方式 |
| `text` | string | 元素文本 | **可读**：描述点击了什么 |
| `value` | string | 输入值 | **重放**：知道输入了什么 |
| `coordinates` | {x, y} | 坐标 | 备选定位方式 |

**提取规则**：
```python
# 所有不导致 State 变化的事件 → Intent
if event.type in ["click", "input", "scroll", "hover"]:
    if next_event.url == event.url and next_event.page_root == event.page_root:
        # 没有跳转，创建 Intent
        intent = Intent(
            type=event.type,
            state_id=current_state.id,
            text=event.element.text,
            value=event.data.get("value"),
            xpath=event.element.xpath
        )
        current_state.intents.append(intent)
```

**用途**：
1. **记录操作细节**：知道用户在页面上具体做了什么
2. **重放参考**：Agent 可以参考 xpath、text 来定位元素
3. **行为分析**：分析用户习惯（先点哪里、输入什么）

---

### 3. Action（页面跳转）

**定义**：从一个 State 到另一个 State 的**跳转/导航**

**保存的数据**：
| 字段 | 类型 | 说明 | 用途 |
|------|------|------|------|
| `source` | string | 来源 State ID | **核心**：从哪里来 |
| `target` | string | 目标 State ID | **核心**：到哪里去 |
| `type` | string | 跳转类型 | Navigate/ClickLink/SubmitForm |
| `timestamp` | int | 跳转时间 | 时序分析 |
| `trigger_intent_id` | string | 触发的 Intent | 哪个操作导致了跳转 |
| `weight` | float | 边权重 | 图算法（PageRank 等） |

**约束**：`source ≠ target`（必须是不同的页面）

**提取规则**：
```python
# Action 只在 State 变化时创建
if next_event.url != event.url or next_event.page_root != event.page_root:
    # 发生了页面跳转，创建 Action
    action = Action(
        source=current_state.id,
        target=new_state.id,
        type=classify_action_type(event),  # Navigate/ClickLink/SubmitForm
        trigger_intent_id=last_intent.id
    )

# Action 类型分类（规则）：
def classify_action_type(event):
    if event.type == "navigate":
        return "Navigate"
    if event.element.tag == "a":
        return "ClickLink"
    if "submit" in event.element.text.lower():
        return "SubmitForm"
    if "search" in event.element.text.lower():
        return "Search"
    return "ClickButton"
```

**用途**：
1. **路径图**：构建页面之间的导航关系图
2. **路径检索**：找到从 A 到 B 的所有可能路径
3. **图遍历**：K-hop 邻居查询、PageRank 等

---

### 4. Domain（网站/应用）

**定义**：整个网站或应用的顶层节点

**保存的数据**：
| 字段 | 类型 | 说明 | 用途 |
|------|------|------|------|
| `id` | string | 唯一标识符 | 节点 ID |
| `domain_url` | string | 域名 | taobao.com |
| `domain_name` | string | 名称 | 淘宝 |
| `domain_type` | string | 类型 | website/app |
| `created_at` | int | 首次发现时间 | 统计 |
| `user_id` | string | 用户 ID | 隔离 |

**提取规则**：
```python
# 从 URL 提取域名
from urllib.parse import urlparse
domain_url = urlparse(state.page_url).netloc  # "www.taobao.com" → "taobao.com"
```

**用途**：
1. **网站分组**：按网站组织所有页面
2. **域名过滤**：检索时按域名筛选
3. **统计**：用户访问了哪些网站

---

### 5. Manage（Domain → State 关联）

**定义**：记录 Domain（网站）与 State（页面）的访问关系

**保存的数据**：
| 字段 | 类型 | 说明 | 用途 |
|------|------|------|------|
| `domain_id` | string | 网站 ID | 来源 |
| `state_id` | string | 页面 ID | 目标 |
| `visit_count` | int | 访问次数 | **热度**：常用页面 |
| `first_visit` | int | 首次访问 | 统计 |
| `last_visit` | int | 最近访问 | **时间衰减** |
| `total_duration` | int | 总停留时间 | 重要性分析 |

**用途**：
1. **访问统计**：哪些页面被频繁访问
2. **时间衰减**：最近访问的权重更高
3. **热门路径**：发现用户常走的路线

---

### 6. CognitivePhrase（认知短语/完整任务路径）

**定义**：一次完整任务的操作路径，**是检索的核心**

**保存的数据**：
| 字段 | 类型 | 说明 | 用途 |
|------|------|------|------|
| `id` | string | 唯一标识符 | 引用 |
| `description` | string | 任务描述 | **核心**：语义搜索的目标 |
| `user_id` | string | 用户 ID | 隔离 |
| `session_id` | string | 录制会话 ID | 关联到原始录制 |
| `state_path` | List[string] | State ID 序列 | **核心**：经过了哪些页面 |
| `action_path` | List[string] | Action 类型序列 | 每一步的跳转类型 |
| `start_timestamp` | int | 开始时间 | 时间范围 |
| `end_timestamp` | int | 结束时间 | 时间范围 |
| `duration` | int | 总时长 | 任务复杂度估计 |
| `embedding_vector` | List[float] | 语义向量 | **检索**：语义相似度 |
| `access_count` | int | 访问次数 | **热度**：常用路径优先 |
| `last_access_time` | int | 最近访问 | **时间衰减** |

**创建方式**：
```python
# 从录制的轨迹创建
phrase = workflow_memory.create_phrase_from_trajectory(
    session_id="recording_001",
    label="搜索商品",
    description="在淘宝搜索 iPhone 并查看商品详情"  # 来自 task_description
)

# 内部逻辑：
# 1. 获取该 session 的所有 states（按时间排序）
# 2. 提取 state_path = [state1.id, state2.id, ...]
# 3. 获取相邻 states 之间的 actions
# 4. 提取 action_path = [action1.type, action2.type, ...]
# 5. 计算时间范围和 duration
```

**用途**：
1. **语义搜索**：用户说"搜索商品"，找到相似的历史路径
2. **路径推荐**：返回完整的操作步骤供 Agent 参考
3. **热门路径**：access_count 高的路径更可靠

---

### 完整数据流示例

**输入：用户录制的原始操作**
```json
[
    {"type": "navigate", "timestamp": 1000, "url": "https://taobao.com"},
    {"type": "click", "timestamp": 2000, "url": "https://taobao.com",
     "element": {"tagName": "input", "text": "搜索框"}},
    {"type": "input", "timestamp": 3000, "url": "https://taobao.com",
     "data": {"value": "iPhone 16"}},
    {"type": "click", "timestamp": 4000, "url": "https://taobao.com",
     "element": {"tagName": "button", "text": "搜索"}},
    {"type": "navigate", "timestamp": 5000, "url": "https://s.taobao.com/search?q=iPhone"},
    {"type": "click", "timestamp": 6000, "url": "https://s.taobao.com/search?q=iPhone",
     "element": {"tagName": "a", "text": "iPhone 16 Pro Max", "href": "/item/123"}},
    {"type": "navigate", "timestamp": 7000, "url": "https://item.taobao.com/item/123"}
]
```

**GraphBuilder 处理后：**

```python
# Domain
Domain(id="domain_tb", domain_url="taobao.com", domain_name="淘宝")

# States
State_1 = State(
    id="S1",
    page_url="https://taobao.com",
    page_title="淘宝首页",
    intents=[
        Intent(type="click", text="搜索框", xpath="//input[@id='search']"),
        Intent(type="input", value="iPhone 16"),
        Intent(type="click", text="搜索", xpath="//button[@class='search-btn']")
    ]
)

State_2 = State(
    id="S2",
    page_url="https://s.taobao.com/search?q=iPhone",
    page_title="搜索结果",
    intents=[
        Intent(type="click", text="iPhone 16 Pro Max", xpath="//a[@href='/item/123']")
    ]
)

State_3 = State(
    id="S3",
    page_url="https://item.taobao.com/item/123",
    page_title="商品详情",
    intents=[]
)

# Actions
Action_1 = Action(source="S1", target="S2", type="Search")
Action_2 = Action(source="S2", target="S3", type="ClickLink")

# CognitivePhrase（如果创建）
CognitivePhrase(
    id="phrase_001",
    description="在淘宝搜索 iPhone 并查看商品详情",
    state_path=["S1", "S2", "S3"],
    action_path=["Search", "ClickLink"],
    duration=6000
)
```

---

### 数据用途总结

| 模型 | 核心用途 | 检索时的作用 |
|------|---------|-------------|
| **State** | 记录页面位置 | 知道要去哪些页面 |
| **Intent** | 记录页面内操作 | 知道在页面上做什么 |
| **Action** | 记录页面跳转 | 知道如何从 A 到 B |
| **Domain** | 网站分组 | 按域名筛选路径 |
| **Manage** | 访问统计 | 热门页面优先 |
| **CognitivePhrase** | 完整任务路径 | **检索入口**：语义匹配 |

### 检索流程

```
用户输入："帮我在淘宝搜索 iPhone"
              │
              ▼
    ┌─────────────────────────────────┐
    │  1. 语义搜索 CognitivePhrase     │
    │     - 将输入转为 embedding        │
    │     - 与所有 phrase 计算相似度    │
    │     - 返回 top-k 相似的 phrase   │
    └─────────────────────────────────┘
              │
              ▼
    ┌─────────────────────────────────┐
    │  2. 获取完整路径                 │
    │     - phrase.state_path → States│
    │     - 每个 State 包含 Intents    │
    │     - phrase.action_path → 跳转  │
    └─────────────────────────────────┘
              │
              ▼
    ┌─────────────────────────────────┐
    │  3. 构建参考上下文               │
    │     "历史上你完成过类似任务：      │
    │      1. 在淘宝首页点击搜索框      │
    │      2. 输入 'iPhone 16'         │
    │      3. 点击搜索按钮             │
    │      4. 页面跳转到搜索结果        │
    │      ..."                        │
    └─────────────────────────────────┘
              │
              ▼
      注入到 Agent 的 LLM Prompt

## 待确定问题

1. **Embedding 模型**：使用哪个 embedding 模型做语义搜索？
   - 方案 A：OpenAI text-embedding-3-small
   - 方案 B：本地模型（sentence-transformers）
   - 方案 C：用 LLM 做相似度评分（较慢但无需额外模型）

2. **记忆隔离**：记忆是否仅限于单用户，还是允许共享？
   - 方案 A：严格单用户（隐私）
   - 方案 B：单用户但可选共享
   - 方案 C：全局知识库 + 用户偏好

3. **记忆限制**：如何处理记忆增长？
   - LRU 淘汰旧的、未使用的 phrase
   - 合并相似的 phrase
   - 归档旧数据

4. **反馈循环**：如何从 agent 执行中改进？
   - 方案 A：自动从成功的 Quick Task 执行中学习
   - 方案 B：用户确认"这很有帮助"来提升 phrase 权重
   - 方案 C：仅手动（当前录制方式）

## Memory 内部原理

### 架构层次

```
┌─────────────────────────────────────────────────────────────────────┐
│                        WorkflowMemory                                │
│  (高级接口：add_workflow_step, get_trajectory, export/import)        │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ DomainMgr   │ │ StateMgr    │ │ ActionMgr   │ │ ManageMgr   │   │
│  │ (节点)      │ │ (节点)      │ │ (边)        │ │ (边)        │   │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘   │
│         │               │               │               │           │
│         └───────────────┴───────────────┴───────────────┘           │
│                                 │                                   │
│                    ┌────────────┴────────────┐                      │
│                    │       GraphStore        │                      │
│                    │   (图存储抽象层)         │                      │
│                    └────────────┬────────────┘                      │
├─────────────────────────────────┼───────────────────────────────────┤
│                    ┌────────────┴────────────┐                      │
│                    │     NetworkXGraph       │                      │
│                    │   (NetworkX DiGraph)    │                      │
│                    └─────────────────────────┘                      │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  InMemoryCognitivePhraseManager (独立存储，不在图中)          │   │
│  │  phrases: Dict[str, CognitivePhrase]                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 数据在图中的存储结构

**NetworkXGraph 内部数据结构：**

```python
# 1. 主图结构 (NetworkX DiGraph)
self._graph = nx.DiGraph()

# 2. 索引结构（加速查询）
self._node_index: Dict[(label, id_value), node_key]  # 节点快速查找
self._label_index: Dict[label, Set[node_keys]]       # 按标签分组
self._text_indexes: Dict[index_name, Set[property_keys]]  # 文本搜索索引
self._vector_indexes: Dict[index_name, property_key]      # 向量搜索索引
```

### 数据流转过程

#### 1. 创建 State（页面）

```python
# 输入：State 对象
state = State(
    id="state_abc123",
    page_url="https://taobao.com/search",
    page_title="搜索结果",
    timestamp=1704067200000,
    intents=[Intent(...), Intent(...)],  # 页面内操作
    user_id="user123",
    session_id="recording_001"
)

# workflow_memory.create_state(state) 调用链：
#   ↓
# GraphStateManager.create_state()
#   ↓
# graph_store.upsert_node(label="State", properties={...}, id_key="id")
#   ↓
# NetworkXGraph.upsert_node()
```

**存储后的图结构：**

```
节点 key: "State:state_abc123"

节点数据 (NetworkX node attributes):
{
    '_label': 'State',           # 内部元数据
    '_id_key': 'id',             # 内部元数据
    '_id_value': 'state_abc123', # 内部元数据

    # 实际属性（来自 state.to_dict()）
    'id': 'state_abc123',
    'page_url': 'https://taobao.com/search',
    'page_title': '搜索结果',
    'timestamp': 1704067200000,
    'intents': [                  # 嵌套的 Intent 列表
        {
            'id': 'intent_001',
            'type': 'click',
            'element_id': 'search-btn',
            ...
        },
        {
            'id': 'intent_002',
            'type': 'type',
            'text': 'iPhone 16',
            ...
        }
    ],
    'user_id': 'user123',
    'session_id': 'recording_001',
    'embedding_vector': null      # 可选，用于语义搜索
}

索引更新:
  _node_index[('State', 'state_abc123')] = 'State:state_abc123'
  _label_index['State'].add('State:state_abc123')
```

#### 2. 创建 Action（页面跳转）

```python
# 输入：Action 对象
action = Action(
    source="state_abc123",    # 来源页面
    target="state_def456",    # 目标页面
    type="click_link",        # 跳转类型
    timestamp=1704067210000,
    trigger_intent_id="intent_001"
)

# workflow_memory.create_action(action) 调用链：
#   ↓
# GraphActionManager.create_action()
#   ↓
# graph_store.upsert_relationship(
#     start_node_label="State", start_node_id_value="state_abc123",
#     end_node_label="State", end_node_id_value="state_def456",
#     rel_type="ACTION_CLICK_LINK",
#     properties={...}
# )
```

**存储后的图结构：**

```
边: State:state_abc123 --[ACTION_CLICK_LINK]--> State:state_def456

边数据 (NetworkX edge attributes):
{
    '_rel_type': 'ACTION_CLICK_LINK',    # 内部元数据
    '_start_label': 'State',
    '_end_label': 'State',

    # 实际属性
    'source': 'state_abc123',
    'target': 'state_def456',
    'type': 'click_link',
    'timestamp': 1704067210000,
    'trigger_intent_id': 'intent_001',
    'weight': 1.0
}
```

#### 3. 创建 Domain 和 Manage（网站与页面关联）

```python
# Domain（网站节点）
domain = Domain(
    id="domain_taobao",
    domain_url="taobao.com",
    domain_name="淘宝",
    domain_type="website"
)

# 存储为：
节点 key: "Domain:domain_taobao"
节点数据: {
    '_label': 'Domain',
    'id': 'domain_taobao',
    'domain_url': 'taobao.com',
    'domain_name': '淘宝',
    'domain_type': 'website'
}

# Manage（访问关系边）
manage = Manage(
    domain_id="domain_taobao",
    state_id="state_abc123",
    visit_count=1,
    first_visit=1704067200000,
    last_visit=1704067200000
)

# 存储为：
边: Domain:domain_taobao --[MANAGES]--> State:state_abc123
边数据: {
    '_rel_type': 'MANAGES',
    'domain_id': 'domain_taobao',
    'state_id': 'state_abc123',
    'visit_count': 1,
    'first_visit': 1704067200000,
    'last_visit': 1704067200000
}
```

#### 4. CognitivePhrase（独立存储，不在图中）

```python
# CognitivePhrase 存储在独立的字典中，不是图的一部分
phrase = CognitivePhrase(
    id="phrase_001",
    description="在淘宝搜索商品并查看详情",
    user_id="user123",
    session_id="recording_001",
    state_path=["state_abc123", "state_def456", "state_ghi789"],
    action_path=["click_link", "click"],
    embedding_vector=[0.1, 0.2, ...]
)

# 存储位置：
InMemoryCognitivePhraseManager.phrases = {
    "phrase_001": CognitivePhrase(...)
}
```

### 完整的图结构示例

```
用户录制了一次 "在淘宝搜索 iPhone" 的操作后，图结构如下：

                    ┌──────────────────┐
                    │     Domain       │
                    │  id: domain_tb   │
                    │  url: taobao.com │
                    └────────┬─────────┘
                             │
                    [MANAGES] │ [MANAGES]
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│     State 1     │  │     State 2     │  │     State 3     │
│ url: taobao.com │  │ url: s.taobao.. │  │ url: item.taob..│
│ title: 首页     │  │ title: 搜索结果  │  │ title: 商品详情  │
│                 │  │                 │  │                 │
│ intents:        │  │ intents:        │  │ intents:        │
│  - click 搜索框  │  │  - click 商品    │  │  - scroll      │
│  - type iPhone  │  │                 │  │  - click 加购   │
│  - click 搜索   │  │                 │  │                 │
└────────┬────────┘  └────────┬────────┘  └─────────────────┘
         │                    │
         │ [ACTION_CLICK]     │ [ACTION_CLICK]
         └────────────────────┴───────────────────────────────→

CognitivePhrase (独立存储):
{
    id: "phrase_001",
    description: "在淘宝搜索商品并查看详情",
    state_path: ["state_1", "state_2", "state_3"],
    action_path: ["click", "click"]
}
```

### 查询数据的过程

#### 1. 按 session 获取工作流轨迹

```python
trajectory = workflow_memory.get_workflow_trajectory(session_id="recording_001")

# 内部执行：
# 1. list_states(session_id="recording_001")
#    → 查询所有 session_id 匹配的 State 节点
#    → 按 timestamp 排序
#
# 2. 对于每对相邻 state，查询 Action 边
#    → query_relationships(start=state_i, end=state_i+1)
#
# 返回：
{
    "session_id": "recording_001",
    "states": [State1, State2, State3],
    "actions": [Action1, Action2],
    "metadata": {
        "state_count": 3,
        "action_count": 2,
        "start_time": 1704067200000,
        "end_time": 1704067500000
    }
}
```

#### 2. 语义搜索相似 State

```python
similar_states = state_manager.search_states_by_embedding(
    query_vector=[0.1, 0.2, ...],
    top_k=5
)

# 内部执行：
# 1. 尝试调用 graph_store.vector_search()
# 2. 如果失败，fallback 到 _fallback_embedding_search()
#    → 获取所有 states
#    → 计算每个 state.embedding_vector 与 query_vector 的余弦相似度
#    → 排序返回 top_k
```

#### 3. K-hop 邻居查询

```python
neighbors = state_manager.get_k_hop_neighbors(
    state_id="state_1",
    k=2,
    direction="outgoing"
)

# 内部执行（BFS）：
# Level 0: {state_1}
# Level 1: 获取 state_1 的所有出边目标 → {state_2}
# Level 2: 获取 state_2 的所有出边目标 → {state_3}
# 返回 Level 2 的状态
```

### 导出与持久化

```python
# export_memory() 返回：
{
    "states": [
        {"id": "state_1", "page_url": "...", "intents": [...], ...},
        {"id": "state_2", ...},
        ...
    ],
    "actions": [
        {"source": "state_1", "target": "state_2", "type": "click", ...},
        ...
    ],
    "phrases": [
        {"id": "phrase_001", "description": "...", "state_path": [...], ...},
        ...
    ],
    "metadata": {
        "state_count": 10,
        "action_count": 9,
        "phrase_count": 1
    }
}

# ⚠️ 注意：当前实现缺失 domains 和 manages 的导出！
```

### 当前实现的局限性

| 问题 | 说明 |
|------|------|
| **无持久化** | `export_memory()` 只返回 dict，没有写入磁盘 |
| **纯内存** | 服务器重启后数据丢失 |
| **无用户隔离** | 全局共享一个 `workflow_memory` 实例 |
| **CognitivePhrase 独立** | 不在图中，无法利用图算法 |
| **导出不完整** | 缺少 Domain 和 Manage 的导出 |
| **无 embedding 生成** | 字段存在但没有自动生成逻辑 |

## 相关代码参考

- GraphBuilder: `src/cloud_backend/memgraph/graph_builder/`
- WorkflowMemory: `src/cloud_backend/memgraph/memory/workflow_memory.py`
- NetworkXGraph: `src/cloud_backend/memgraph/graphstore/networkx_graph.py`
- CognitivePhrase: `src/cloud_backend/memgraph/ontology/cognitive_phrase.py`
- EigentBrowserAgent: `src/clients/desktop_app/ami_daemon/base_agent/agents/eigent_browser_agent.py`
- 录制上传: `src/cloud_backend/main.py` (POST /api/v1/recordings)
