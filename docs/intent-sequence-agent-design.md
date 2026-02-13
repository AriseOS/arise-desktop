# IntentSequence Agent 使用设计

## 1. 背景

### 1.1 当前状态

Agent 执行任务时，会在任务开始前查询 Memory 获取工作流指导（CognitivePhrase 或 Path）。但在执行过程中，Agent 遇到复杂页面时缺乏针对当前页面的操作指导。

### 1.2 问题

- Agent 知道当前 URL，但不知道这个页面上"历史上用户做过什么操作"
- IntentSequence 记录了用户在每个 State（页面）上的操作序列，但 Agent 没有利用
- `query_actions` 接口已定义但从未被调用，且内部实现不支持 URL 查询

### 1.3 目标

让 Agent 能够在执行过程中，根据当前 URL 查询该页面的历史操作记录（IntentSequence），作为参考信息辅助决策。

---

## 2. 核心概念

### 2.1 IntentSequence

一个 IntentSequence 代表用户在某个页面上完成的一组相关操作：

```
State: "Product Hunt 产品详情页"
├── IntentSequence: "查看团队成员"
│   ├── Intent: click link "Team"
│   └── Intent: scroll down
├── IntentSequence: "收藏产品"
│   └── Intent: click button "Upvote"
└── IntentSequence: "查看评论" → 导航到评论页
    ├── Intent: scroll to bottom
    └── Intent: click link "Comments"
```

### 2.2 Intent

单个原子操作：

```python
Intent:
    type: str           # "click", "type", "scroll"
    element_role: str   # "button", "link", "textbox"
    text: str           # 元素文本，如 "Submit", "Login"
    value: str          # 输入值（type 操作时）
```

### 2.3 关系

```
URL → State → [IntentSequence] → [Intent]
```

---

## 3. 设计决策

### 3.1 触发方式：Tool（LLM 主动调用）

**决策**：做成 Tool，让 LLM 自己决定是否调用。

**理由**：
- 简单页面不需要查询，LLM 看 snapshot 就够
- 复杂页面 LLM 可以主动调用获取帮助
- 避免每次导航都查询的性能开销

**否决的方案**：
- 每次导航自动注入：token 浪费，很多页面不需要
- 关键词触发：不够规范，容易误触发

### 3.2 IS 的角色：参考信息，非执行脚本

**决策**：IS 只作为 LLM 的参考信息，不自动执行。

**理由**：
- LLM 是决策者，IS 是辅助信息
- 页面可能已变化，盲目执行可能失败
- 失败处理逻辑简单：LLM 自己看 snapshot 调整

**流程**：
```
1. LLM 觉得页面复杂，调用 query_page_operations(url)
2. 返回该页面的历史操作列表（简化格式）
3. LLM 参考这些信息，决定具体执行什么操作
4. LLM 调用 browser_click / browser_type 等工具执行
5. 如果失败，LLM 看新 snapshot 自己调整
```

### 3.3 IS 缓存机制

**问题**：一个 IS 可能有多个步骤，LLM 每轮只执行一个操作。如果不缓存，下一轮 IS 信息可能被上下文截断丢失。

```
IS: "用户名密码登录"
   step 1: click textbox "Username"
   step 2: type "admin"
   step 3: click textbox "Password"
   step 4: type "123456"
   step 5: click button "Login"

Loop 1: LLM 调用 query_page_operations → 拿到 IS
Loop 2: LLM 执行 step 1
Loop 3: LLM 执行 step 2（IS 可能已不在上下文中）
```

**决策**：Agent 端缓存当前 IS，每轮自动注入。

**缓存内容**：
```python
self._cached_intent_sequences: Optional[List[IntentSequence]] = None
self._cached_intent_sequences_url: Optional[str] = None  # 缓存对应的 URL
```

**记住 IS 的时机**：
- LLM 调用 `query_page_operations(url)` 成功返回时

**忘掉 IS 的时机**：
- **URL 变化**：每轮 loop 开始时检测，如果 URL 变了就清除缓存
- **查询新页面**：调用 `query_page_operations` 时会覆盖旧缓存
- **无结果**：查询返回空时清除缓存

**注入方式**：
- 每轮 loop 开始时，如果有缓存的 IS 且当前 URL 匹配，自动注入到 LLM 消息中
- 注入格式与 Tool 返回格式一致

**不跟踪执行进度**：
- 不跟踪 LLM 执行到了第几步
- IS 是参考信息，LLM 可能跳步、部分执行、或完全忽略
- 保持简单，避免复杂的状态同步

---

## 4. 接口设计

### 4.1 Agent 端：新增 Tool

```python
# MemoryToolkit 中新增方法，暴露为 Tool

async def query_page_operations(self, url: str) -> str:
    """Query available operations for the current page from memory.

    Use this when you're on a complex page and want to know what
    operations users have performed here before.

    Args:
        url: Current page URL

    Returns:
        Formatted string describing available operations on this page.
        Returns empty message if no recorded operations found.
    """
```

### 4.2 返回格式（给 LLM 看）

```markdown
## 当前页面历史操作 (3 条记录)

1. "查看团队成员"
   - click link "Team"
   - scroll down

2. "收藏产品"
   - click button "Upvote"

3. "查看评论" → 导航到评论页
   - scroll to bottom
   - click link "Comments"
```

格式原则：
- 简洁：只保留 LLM 需要的信息
- 可操作：包含元素类型（button/link）和文本
- 标注导航：明确哪些操作会跳转页面

### 4.3 后端：修改 `_query_action`

```python
async def _query_action(self, target: str, current_state: str, top_k: int):
    # 1. 解析 current_state（支持 URL、state_id、语义描述）
    state_id = await self._resolve_state_id(current_state)
    if not state_id:
        return QueryResult.action_failure(error=f"State not found: {current_state}")

    # 2. 查询 IntentSequences（现有逻辑）
    ...
```

### 4.4 后端：修改 `_resolve_state_id`

```python
async def _resolve_state_id(self, state_ref: str) -> Optional[str]:
    # 1. 直接 ID 查找
    state = self.memory.get_state(state_ref)
    if state:
        return state.id

    # 2. URL 查找（新增）
    if state_ref.startswith("http"):
        state = self.memory.find_state_by_url(state_ref)
        if state:
            return state.id

    # 3. Embedding 语义搜索（fallback）
    query_vector = self.embedding_service.encode(state_ref)
    results = self.memory.state_manager.search_states_by_embedding(query_vector, top_k=1)
    if results:
        return results[0][0].id

    return None
```

---

## 5. 数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Loop                                │
│                                                                  │
│  1. LLM 看到复杂页面，决定调用 query_page_operations            │
│                              ↓                                   │
│  2. Tool 调用: query_page_operations(url="https://...")         │
└──────────────────────────────┬──────────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────────┐
│                      MemoryToolkit                                │
│                                                                   │
│  3. 调用后端 API: POST /api/v1/memory/query                      │
│     {current_state: "https://...", target: ""}                   │
└──────────────────────────────┬───────────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────────┐
│                      Cloud Backend                                │
│                                                                   │
│  4. Reasoner._query_action()                                     │
│     ├── _resolve_state_id(url) → state_id                        │
│     └── intent_sequence_manager.list_by_state(state_id)          │
│                              ↓                                    │
│  5. 返回 IntentSequence 列表                                     │
└──────────────────────────────┬───────────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────────┐
│                      MemoryToolkit                                │
│                                                                   │
│  6. 格式化为 LLM 可读的文本                                       │
└──────────────────────────────┬───────────────────────────────────┘
                               ↓
┌──────────────────────────────────────────────────────────────────┐
│                        Agent Loop                                 │
│                                                                   │
│  7. LLM 收到历史操作列表，参考后决定具体操作                      │
│  8. LLM 调用 browser_click("button", "Upvote") 等执行            │
└───────────────────────────────────────────────────────────────────┘
```

---

## 6. 实现任务

### 6.1 后端改动

1. **修改 `_resolve_state_id`**：增加 URL 查找支持
2. **修改 `_query_action`**：调用 `_resolve_state_id` 解析 current_state

文件：`src/cloud_backend/memgraph/reasoner/reasoner.py`

### 6.2 Agent 端改动

**MemoryToolkit** (`memory_toolkit.py`):
1. **新增 Tool**：`query_page_operations(url)`
2. **格式化方法**：将 IntentSequence 列表转为 LLM 可读格式

**EigentStyleBrowserAgent** (`eigent_style_browser_agent.py`):
1. **新增缓存字段**：
   ```python
   self._cached_intent_sequences: Optional[List[IntentSequence]] = None
   self._cached_intent_sequences_url: Optional[str] = None
   ```
2. **缓存管理**：在 `query_page_operations` Tool 执行时更新缓存
3. **URL 变化检测**：每轮 loop 开始时检查 URL，变化则清除缓存
4. **自动注入**：每轮 loop 开始时，如有缓存 IS 且 URL 匹配，注入到消息中

### 6.3 不需要改动

- API 接口不变（复用 `/api/v1/memory/query`）

---

## 7. 示例场景

### 场景 1：单次查询使用

```
Loop 1:
  LLM: 我在产品详情页，页面比较复杂，查询一下历史操作
  Tool: query_page_operations("https://producthunt.com/products/xxx")

  返回 + 缓存:
  ## 当前页面历史操作 (2 条记录)
  1. "查看团队成员"
     - click link "Team"
  2. "收藏产品"
     - click button "Upvote"

Loop 2:
  [自动注入缓存的 IS 信息]
  LLM: 根据历史记录，我需要点击 "Team" 链接
  Tool: browser_click("link", "Team")

  结果: 导航到团队页面
  [URL 变化，清除缓存]

Loop 3:
  LLM: 现在在团队页面，我可以看到团队成员信息...
```

### 场景 2：多步操作使用缓存

```
Loop 1:
  LLM: 登录页面，查询历史操作
  Tool: query_page_operations("https://example.com/login")

  返回 + 缓存:
  ## 当前页面历史操作 (1 条记录)
  1. "用户名密码登录"
     - click textbox "Username"
     - type [用户名]
     - click textbox "Password"
     - type [密码]
     - click button "Login"

Loop 2:
  [自动注入缓存的 IS]
  LLM: 按照历史操作，先点击用户名输入框
  Tool: browser_click("textbox", "Username")

Loop 3:
  [URL 未变，继续注入缓存的 IS]
  LLM: 输入用户名
  Tool: browser_type("admin@example.com")

Loop 4:
  [URL 未变，继续注入缓存的 IS]
  LLM: 点击密码输入框
  Tool: browser_click("textbox", "Password")

Loop 5:
  [URL 未变，继续注入缓存的 IS]
  LLM: 输入密码
  Tool: browser_type("password123")

Loop 6:
  [URL 未变，继续注入缓存的 IS]
  LLM: 点击登录按钮
  Tool: browser_click("button", "Login")

  结果: 导航到首页
  [URL 变化，清除缓存]
```

---

## 8. 未来扩展

### 8.1 智能触发提示

可以在 snapshot 中元素数量超过阈值时，提示 LLM 可以调用 `query_page_operations`：

```
[Page has 50+ interactive elements. Consider using query_page_operations() for guidance.]
```

### 8.2 IS 执行验证

未来可以添加执行后验证：
- 检查是否触发了预期的导航
- 检查页面状态是否符合预期

### 8.3 IS 质量反馈

收集 LLM 使用 IS 的效果，用于优化 IS 的生成和存储。
