# Conversation Memory System Design

基于 OpenClaw 记忆系统的设计，为 2ami 实现会话历史存储和检索系统。

## 设计目标

1. **持久化会话历史** - 解决当前 APP 重启后消息丢失的问题
2. **Agent 可检索** - 让 Agent 能够通过工具主动检索历史会话
3. **简单易调试** - 使用 JSONL 格式，人类可读，便于开发调试
4. **渐进式增强** - 先实现关键词搜索，后续可加向量搜索

## 核心设计理念

### 学习 OpenClaw 的触发式检索

**不是**一开始就把所有历史消息注入上下文，而是：

1. **System Prompt 告诉 Agent 什么时候应该检索**
2. **Agent 自己判断是否需要调用检索工具**
3. **检索结果作为工具返回值注入上下文**

```
用户: "上次我们讨论了什么？"
      ↓
Agent 根据 System Prompt 判断: 这是关于过去的问题
      ↓
Agent 调用: search_conversations("上次讨论")
      ↓
返回相关会话摘要和片段
      ↓
Agent 基于检索结果回答
```

## 文件结构

```
~/.ami/
├── conversations/                      # 会话存储根目录
│   ├── index.json                     # 全局会话索引
│   └── {user_id}/                     # 按用户隔离
│       └── {conversation_id}.jsonl    # 会话转录文件
│
├── memory/                             # 长期记忆 (Phase 2)
│   ├── MEMORY.md                      # 核心长期记忆
│   └── YYYY-MM-DD.md                  # 每日记忆日志
│
└── users/{user_id}/                    # 已有的用户目录
    └── projects/.../tasks/...         # 任务工作目录
```

## 数据模型

### 1. ConversationEntry (会话索引条目)

存储在 `index.json` 中，包含会话的摘要信息：

```python
@dataclass
class ConversationEntry:
    conversation_id: str      # 唯一会话 ID
    user_id: str              # 用户 ID

    # 时间戳
    created_at: str           # 创建时间 (ISO format)
    updated_at: str           # 最后更新时间

    # 显示信息
    title: str                # 会话标题 (可从首条消息自动生成)
    summary: str              # 会话摘要 (可由 LLM 生成)

    # 状态
    status: str               # active/completed/failed/cancelled

    # 计数
    message_count: int        # 总消息数
    user_message_count: int   # 用户消息数
    assistant_message_count: int  # 助手消息数

    # Token 使用
    total_input_tokens: int
    total_output_tokens: int

    # 关联
    task_ids: List[str]       # 关联的任务 ID
    tags: List[str]           # 标签
    memory_level: str         # L1/L2/L3

    # 文件引用
    transcript_file: str      # 转录文件相对路径

    # 预览
    first_message_preview: str  # 首条用户消息预览
    last_message_preview: str   # 最后消息预览
```

### 2. JSONL 转录文件格式

每个会话一个 `.jsonl` 文件，每行一个 JSON 对象：

```jsonl
{"type":"header","version":1,"conversation_id":"conv_abc123","user_id":"user1","created_at":"2026-02-03T10:00:00Z","title":"在 PH 找 AI 产品"}
{"type":"message","id":"msg_001","role":"user","content":"帮我在 Product Hunt 找今天最热门的 3 个 AI 产品","timestamp":"2026-02-03T10:00:01Z"}
{"type":"message","id":"msg_002","role":"assistant","content":"好的，我来帮你查找...","timestamp":"2026-02-03T10:00:05Z","agent_id":"browser_agent"}
{"type":"event","event_type":"task_started","task_id":"task_001","timestamp":"2026-02-03T10:00:06Z"}
{"type":"event","event_type":"browser_navigated","url":"https://www.producthunt.com","timestamp":"2026-02-03T10:00:10Z"}
{"type":"message","id":"msg_003","role":"assistant","content":"我找到了以下产品...","timestamp":"2026-02-03T10:05:00Z","input_tokens":1500,"output_tokens":800}
{"type":"event","event_type":"task_completed","task_id":"task_001","result":"success","timestamp":"2026-02-03T10:05:01Z"}
```

### 3. ConversationMessage

```python
@dataclass
class ConversationMessage:
    id: str                   # 消息 ID
    role: str                 # user/assistant/system
    content: str              # 消息内容
    timestamp: str            # 时间戳

    # 可选字段
    agent_id: Optional[str]   # 生成消息的 Agent ID
    attachments: List[MessageAttachment]  # 附件
    metadata: Dict[str, Any]  # 元数据
    input_tokens: Optional[int]   # Token 使用
    output_tokens: Optional[int]
```

### 4. ConversationEvent

```python
@dataclass
class ConversationEvent:
    event_type: str           # task_started/browser_navigated/tool_called/etc
    timestamp: str            # 时间戳
    data: Dict[str, Any]      # 事件数据
```

## 核心组件

### 1. ConversationStore

管理会话索引 (`index.json`)：

```python
class ConversationStore:
    """
    会话存储管理器

    职责:
    - 管理 index.json 索引文件
    - 创建/更新/删除会话条目
    - 列出和搜索会话
    - 缓存机制防止频繁 IO
    """

    def __init__(self, base_path: Path = None):
        self.base_path = base_path or Path.home() / ".ami" / "conversations"
        self.index_path = self.base_path / "index.json"

    # 写操作
    def create_conversation(user_id, title, task_id, tags) -> ConversationEntry
    def update_conversation(conversation_id, **updates) -> ConversationEntry
    def delete_conversation(conversation_id) -> bool

    # 读操作
    def get_conversation(conversation_id) -> Optional[ConversationEntry]
    def list_conversations(user_id, limit, offset, status) -> List[ConversationEntry]

    # 搜索
    def search_by_title(query, user_id, limit) -> List[ConversationEntry]
    def search_by_content(query, user_id, limit) -> List[ConversationSearchResult]
```

### 2. TranscriptManager

管理单个会话的 JSONL 转录文件：

```python
class TranscriptManager:
    """
    会话转录管理器

    职责:
    - 追加消息和事件到 JSONL 文件
    - 流式读取大文件
    - 内容搜索
    - 统计计算
    """

    def __init__(self, transcript_path: Path):
        self.path = transcript_path

    # 写操作 (追加)
    def write_header(conversation_id, user_id, title) -> ConversationHeader
    def append_message(message_id, role, content, **kwargs) -> ConversationMessage
    def append_event(event_type, **data) -> ConversationEvent

    # 读操作
    def read_header() -> Optional[ConversationHeader]
    def read_messages() -> List[ConversationMessage]
    def read_recent_messages(limit) -> List[ConversationMessage]
    def stream_records() -> Generator[Dict]

    # 统计
    def get_message_count() -> int
    def get_role_counts() -> Dict[str, int]
    def get_token_totals() -> Tuple[int, int]

    # 搜索
    def search_content(query, max_results) -> List[Tuple[Message, snippet, line]]
```

### 3. ConversationMemoryToolkit

Agent 可调用的工具包：

```python
class ConversationMemoryToolkit(BaseToolkit):
    """
    会话记忆工具包 - Agent 通过这些工具检索历史

    参考 OpenClaw 的 memory_search 和 memory_get 工具设计
    """

    def search_conversations(
        self,
        query: str,
        max_results: int = 5,
    ) -> str:
        """
        搜索历史会话

        Agent 在回答关于过去任务/决策/偏好的问题前必须调用此工具。

        Args:
            query: 搜索关键词 (如 "Product Hunt", "AI产品")
            max_results: 最大返回结果数

        Returns:
            JSON 格式的搜索结果，包含匹配的会话摘要和片段
        """

    def get_conversation_messages(
        self,
        conversation_id: str,
        from_line: Optional[int] = None,
        lines: int = 20,
    ) -> str:
        """
        获取指定会话的消息

        在 search_conversations 找到相关会话后调用此工具获取详情。

        Args:
            conversation_id: 会话 ID
            from_line: 起始行号 (可选)
            lines: 读取行数

        Returns:
            JSON 格式的会话消息列表
        """

    def get_recent_conversations(
        self,
        limit: int = 10,
    ) -> str:
        """
        获取最近的会话列表

        用于回答 "最近做了什么" 类型的问题。

        Args:
            limit: 返回数量

        Returns:
            JSON 格式的最近会话摘要列表
        """
```

## System Prompt 设计

在 Agent 的 System Prompt 中添加记忆检索指导：

```python
CONVERSATION_MEMORY_SECTION = """
## Conversation Memory

Before answering questions about:
- Previous tasks or conversations ("上次", "之前", "last time")
- User preferences or habits ("我喜欢", "我通常")
- Past decisions or outcomes ("之前决定", "上次结果")
- Anything the user mentioned "before"

**You MUST first search memory:**

1. Call `search_conversations(query)` to find relevant past conversations
2. If results found, call `get_conversation_messages(conversation_id)` for details
3. Then answer based on the retrieved context

If no relevant memory found after search, acknowledge that you checked but found nothing.

**Available memory tools:**
- `search_conversations(query)` - Search past conversations by keyword
- `get_conversation_messages(conversation_id)` - Get messages from a conversation
- `get_recent_conversations()` - List recent conversations

Example usage:
- User asks "上次在哪个网站找的产品" → search_conversations("产品")
- User asks "继续之前的任务" → get_recent_conversations() then get details
"""
```

## API 设计

### 后端 API (用于前端持久化)

```python
# POST /api/v1/conversations
# 创建新会话
{
    "user_id": "user_001",
    "title": "在 PH 找 AI 产品",
    "task_id": "task_abc",
    "tags": ["browser", "research"]
}
# Response: {"conversation_id": "conv_xyz"}

# POST /api/v1/conversations/{conversation_id}/messages
# 追加消息
{
    "role": "user",
    "content": "帮我找...",
    "attachments": []
}
# Response: {"message_id": "msg_001"}

# GET /api/v1/conversations
# 列出会话
# Query: ?user_id=user_001&limit=20&status=active
# Response: {"conversations": [...]}

# GET /api/v1/conversations/{conversation_id}/messages
# 获取会话消息
# Query: ?limit=50
# Response: {"messages": [...]}

# DELETE /api/v1/conversations/{conversation_id}
# 删除会话
```

## 实现阶段

### Phase 1: 核心存储 (当前)

- [x] `conversation_types.py` - 类型定义
- [x] `transcript_manager.py` - JSONL 转录管理
- [x] `conversation_store.py` - 会话索引管理
- [x] `conversation_memory_toolkit.py` - Agent 工具包
- [x] System Prompt 集成
- [x] 后端 API (`routers/conversations.py`)
- [x] 前端 chatStore 集成
  - [x] `api.js` - Conversation Memory API 方法
  - [x] `chatStore.js` - 集成会话持久化
    - [x] createTask 时创建会话
    - [x] addMessage 时持久化消息
    - [x] setTaskStatus 时更新会话状态
    - [x] setSummaryTask 时更新会话标题
    - [x] loadConversation 加载历史会话
    - [x] listRecentConversations 列出最近会话
    - [x] searchConversations 搜索会话

### Phase 2: 搜索增强

- [x] SQLite FTS 索引 (全文搜索)
  - [x] `conversation_index.py` - FTS5 索引管理
  - [x] 自动同步: append_message 时更新索引
  - [x] BM25 排序支持
  - [x] 中英文混合搜索支持
- [ ] 向量索引 (语义搜索)
- [x] 自动会话摘要生成
  - [x] `conversation_summarizer.py` - 摘要生成器
  - [x] LLM 摘要生成 (可选)
  - [x] 简单提取回退 (无 LLM)
  - [x] API: POST /conversations/{id}/generate-summary

### Phase 3: 长期记忆

- [x] MEMORY.md 长期记忆文件
  - [x] `long_term_memory.py` - 长期记忆管理器
  - [x] 按用户隔离: ~/.ami/memory/{user_id}/
  - [x] 分区存储: preferences, decisions, facts, context, notes
- [x] 每日记忆日志 (memory/YYYY-MM-DD.md)
  - [x] 自动时间戳
  - [x] 获取最近N天日志
- [x] 记忆提取 (从会话中提取要点)
  - [x] 关键词检测 (remember, 记住, preference, etc.)
  - [x] 简单摘要提取
- [x] 记忆搜索工具
  - [x] `LongTermMemoryToolkit` - Agent 工具包
  - [x] remember_fact() - 存储到 MEMORY.md
  - [x] add_daily_note() - 添加到每日日志
  - [x] search_memory() - 搜索记忆
  - [x] get_memory_context() - 获取记忆上下文

## 与现有系统的集成

### 与 MemoryManager 的关系

```
MemoryManager (已有)
├── Layer 1: Variables (内存临时存储)
├── Layer 2: KV Storage (SQLite 持久化)
└── Layer 3: Long-term Memory (mem0, 未启用)

ConversationStore (新增)
├── 会话历史存储
├── JSONL 转录文件
└── Agent 检索工具
```

ConversationStore 与 MemoryManager 是并行的系统：
- MemoryManager: 存储配置、脚本缓存、临时变量
- ConversationStore: 存储会话历史、支持检索

### 与前端的集成

```javascript
// chatStore.js 修改

// 创建任务时同步创建会话
createTask: async (taskId) => {
    const conversationId = await api.createConversation({
        task_id: taskId,
        user_id: getCurrentUserId(),
    });
    // 存储 conversationId 与 taskId 的映射
}

// 发送消息时持久化
addMessage: async (taskId, message) => {
    // ... 现有逻辑

    // 异步持久化
    const conversationId = getConversationId(taskId);
    if (conversationId) {
        api.appendMessage(conversationId, message);
    }
}
```

## 参考实现

### OpenClaw 相关文件

- `third-party/openclaw/src/config/sessions/types.ts` - 会话类型定义
- `third-party/openclaw/src/config/sessions/store.ts` - 会话存储
- `third-party/openclaw/src/config/sessions/transcript.ts` - 转录管理
- `third-party/openclaw/src/agents/tools/memory-tool.ts` - 记忆工具
- `third-party/openclaw/src/agents/system-prompt.ts` - System Prompt 构建
- `third-party/openclaw/src/memory/manager.ts` - 记忆索引管理
- `third-party/openclaw/docs/concepts/memory.md` - 记忆概念文档

### 关键设计决策

1. **JSONL 格式**: 简单、追加友好、人类可读、易于调试
2. **工具触发式检索**: Agent 主动调用，而不是自动注入
3. **索引分离**: index.json 存摘要，.jsonl 存详情
4. **用户隔离**: 按 user_id 隔离数据
5. **渐进增强**: 先关键词搜索，后向量搜索
