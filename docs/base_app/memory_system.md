# BaseAgent Memory System

BaseAgent 的 Memory 系统提供三层存储架构，满足不同场景的数据存储需求。

## 架构概述

### 三层存储架构

```
MemoryManager
├── Layer 1: Variables (临时内存)
│   ├── 实现：Python 字典
│   ├── 生命周期：进程内存
│   └── 用途：Workflow 变量传递
│
├── Layer 2: KV Storage (持久化键值存储)
│   ├── 实现：SQLite 数据库
│   ├── 生命周期：磁盘持久化
│   └── 用途：脚本缓存、配置存储
│
└── Layer 3: Long-term Memory (智能语义记忆)
    ├── 实现：mem0 + ChromaDB
    ├── 生命周期：磁盘持久化
    └── 状态：待启用 (TODO)
```

### 设计原则

1. **分层存储，各司其职** - 不同层次解决不同问题
2. **自动初始化，无需配置** - 开箱即用，降低使用门槛
3. **用户隔离，数据安全** - 基于 user_id 的数据隔离
4. **Memory 属于用户，不属于 Agent 实例** - BaseAgent 是无状态容器，Memory 绑定到用户

---

## Layer 1: Variables (临时内存)

### 特性

- **存储方式**: Python 字典 `Dict[str, Any]`
- **生命周期**: 进程内存，重启后清空
- **用途**: Workflow 执行过程中的变量传递

### 使用场景

- Workflow 步骤间的数据传递
- 临时计算结果存储
- 会话期间的状态维护

### API 示例

```python
from base_app.base_agent.memory import MemoryManager

# 创建 MemoryManager（Variables 层始终可用）
memory = MemoryManager(user_id="user123")

# 存储临时变量
await memory.store_memory("current_step", "processing")
await memory.store_memory("temp_result", {"status": "ok", "data": [1, 2, 3]})

# 读取临时变量
step = await memory.get_memory("current_step")  # "processing"
result = await memory.get_memory("temp_result")  # {"status": "ok", ...}
not_exist = await memory.get_memory("missing", default="N/A")  # "N/A"

# 检查和删除
if memory.has_key("temp_result"):
    await memory.delete_memory("temp_result")

# 列出所有变量
keys = memory.list_keys()  # {"current_step", ...}

# 清空所有变量
await memory.clear_memory()
```

### 在 Workflow 中使用

```python
# AgentContext 包含 variables
context = AgentContext(
    workflow_id="wf_001",
    variables={
        "user_input": "查询天气",
        "intent": "weather_query"
    },
    memory_manager=memory
)

# Step Agent 访问变量
user_input = context.variables.get("user_input")
```

---

## Layer 2: KV Storage (SQLite 持久化存储)

### 特性

- **存储方式**: SQLite 数据库
- **生命周期**: 磁盘持久化，进程重启后保留
- **自动初始化**: 首次访问时自动创建表
- **用户隔离**: 基于 `(key, user_id)` 复合主键

### 数据库表结构

```sql
CREATE TABLE IF NOT EXISTS kv_storage (
    key TEXT NOT NULL,                    -- 存储键
    user_id TEXT NOT NULL DEFAULT 'default',  -- 用户ID（数据隔离）
    value TEXT NOT NULL,                  -- JSON 序列化的值
    created_at TEXT NOT NULL,             -- 创建时间（ISO格式）
    updated_at TEXT NOT NULL,             -- 更新时间（ISO格式）
    PRIMARY KEY (key, user_id)            -- 复合主键
);

CREATE INDEX IF NOT EXISTS idx_kv_user_id ON kv_storage(user_id);
```

### 自动初始化机制

KV Storage 采用**懒初始化**策略：

```python
async def _ensure_table_exists(self, db):
    """每次数据库操作前调用，确保表存在"""
    await db.execute("CREATE TABLE IF NOT EXISTS kv_storage (...)")
    await db.commit()

async def get(self, key, user_id, default):
    async with aiosqlite.connect(self.database_path) as db:
        await self._ensure_table_exists(db)  # 自动创建表
        # ... 查询数据
```

**优势**:
- ✅ 无需显式调用 `initialize()`
- ✅ `CREATE TABLE IF NOT EXISTS` 保证幂等性
- ✅ 适配 Step Agent 的轻量级架构

### 使用场景

- **ScraperAgent 脚本缓存** - 存储生成的提取脚本
- **工具配置持久化** - 保存工具运行时配置
- **Agent 状态保存** - 存储 Agent 的持久化状态

### API 示例

```python
from base_app.base_agent.memory import MemoryManager
from base_app.server.core.config_service import ConfigService

# 创建 MemoryManager（需要 config_service 启用 KV Storage）
config_service = ConfigService()
memory = MemoryManager(
    user_id="user123",
    config_service=config_service
)

# 存储数据（自动 JSON 序列化）
await memory.set_data("api_config", {
    "endpoint": "https://api.example.com",
    "timeout": 30,
    "retry": 3
})

await memory.set_data("cache_v1", {"data": [1, 2, 3]})

# 读取数据（自动 JSON 反序列化）
config = await memory.get_data("api_config")
# 返回: {"endpoint": "https://...", "timeout": 30, "retry": 3}

missing = await memory.get_data("not_exist", default={})
# 返回: {}

# 列出所有键
keys = await memory.list_data_keys()
# 返回: ["api_config", "cache_v1"]

# 删除数据
await memory.delete_data("cache_v1")

# 清空所有数据
count = await memory.clear_all_data()
# 返回: 删除的键数量
```

### 用户隔离示例

```python
# 不同用户的数据互不影响
memory_user1 = MemoryManager(user_id="user1", config_service=config)
memory_user2 = MemoryManager(user_id="user2", config_service=config)

await memory_user1.set_data("pref", {"theme": "dark"})
await memory_user2.set_data("pref", {"theme": "light"})

pref1 = await memory_user1.get_data("pref")  # {"theme": "dark"}
pref2 = await memory_user2.get_data("pref")  # {"theme": "light"}
```

### 配置路径

KV Storage 的数据库路径由 `config_service` 提供：

```yaml
# baseapp.yaml
data:
  databases:
    kv: "./data/kv_storage.db"  # SQLite 文件路径
```

```python
# 代码中获取路径
db_path = config_service.get_path("data.databases.kv")
# 返回: "/path/to/data/kv_storage.db"
```

---

## Layer 3: Long-term Memory (智能语义记忆)

### 特性

- **存储方式**: mem0 + ChromaDB 向量数据库
- **生命周期**: 磁盘持久化
- **能力**: 语义搜索、智能记忆管理
- **状态**: ⏳ **暂未启用**（代码中 `self.long_term_memory = None`）

### 计划功能

```python
# 添加语义记忆（计划）
await memory.add_long_term_memory("用户喜欢喝咖啡")

# 语义搜索（计划）
memories = await memory.search_long_term_memory("饮品偏好")
# 返回与"饮品偏好"相关的记忆

# 获取所有记忆（计划）
all_memories = await memory.get_all_long_term_memories()
```

### 为什么暂未启用？

1. **依赖外部服务** - 需要 OpenAI API 用于嵌入和记忆处理
2. **增加复杂度** - 需要管理 ChromaDB 向量数据库
3. **优先级** - 当前 Variables + KV Storage 已满足主要需求

---

## 实际应用案例：ScraperAgent 脚本缓存

### 缓存策略

ScraperAgent 使用 KV Storage 缓存生成的数据提取脚本，避免重复调用 LLM。

**Script Key 生成**:
```python
def _generate_script_key(self, data_requirements: Dict) -> str:
    user_desc = data_requirements.get('user_description', '')
    fields = list(data_requirements.get('output_format', {}).keys())

    # Key = MD5(user_description + output_format.keys())
    content = f"script_{user_desc}_{','.join(fields)}"
    hash_suffix = hashlib.md5(content.encode()).hexdigest()[:8]

    return f"scraper_script_{hash_suffix}"
```

**注意**: Script Key **不包含** `dom_scope` 或 `url`，因为脚本是通用的，可以在不同 DOM 配置下复用。

### 完整流程

```python
async def _extract_with_script(self, ...):
    # 1. 生成缓存 Key
    script_key = self._generate_script_key(data_requirements)

    # 2. 尝试从 KV 加载缓存脚本
    script_data = await context.memory_manager.get_data(script_key)
    if script_data and 'script_content' in script_data:
        generated_script = script_data['script_content']
        logger.info(f"使用缓存的脚本: {script_key}")
    else:
        # 3. 未命中缓存，生成新脚本（使用 partial DOM 节省 token）
        logger.info(f"脚本不存在，自动生成: {script_key}")

        partial_dom, _ = extractor.serialize_accessible_elements_custom(
            enhanced_dom, include_non_visible=False
        )

        generated_script = await self._generate_extraction_script_with_llm(
            partial_dom, data_requirements, ...
        )

        # 4. 存储到 KV
        script_data = {
            "script_content": generated_script,
            "data_requirements": data_requirements,
            "dom_config": {
                "generation_dom_scope": "partial",
                "execution_dom_scope": self.dom_scope
            },
            "created_at": datetime.now().isoformat(),
            "version": "7.1"
        }
        await context.memory_manager.set_data(script_key, script_data)
        logger.info(f"脚本已存储到KV: {script_key}")

    # 5. 执行脚本（可使用 full DOM）
    return await self._execute_generated_script_direct(
        generated_script, target_dom, dom_dict, max_items
    )
```

### Token 优化策略

- **生成时**: 使用 partial DOM（只包含可见元素）→ 节省 50-80% token
- **执行时**: 可使用 full DOM（包含隐藏元素）→ 访问更多数据
- **脚本通用性**: 脚本不依赖特定 DOM scope，可跨场景复用

---

## 初始化和配置

### 创建 MemoryManager

```python
from base_app.base_agent.memory import MemoryManager
from base_app.server.core.config_service import ConfigService

# 仅使用 Variables（无需 config_service）
memory = MemoryManager(user_id="user123")

# 启用 KV Storage（需要 config_service）
config_service = ConfigService()
memory = MemoryManager(
    user_id="user123",
    config_service=config_service
)
```

### 在 BaseAgent 中使用

```python
from base_app.base_agent.core.base_agent import BaseAgent

# BaseAgent 自动创建 MemoryManager
agent = BaseAgent(
    config=agent_config,
    config_service=config_service
)

# memory_manager 自动初始化并启用
# - Variables: 始终可用
# - KV Storage: 如果提供了 config_service 则自动启用
assert agent.memory_manager is not None
```

### 在 Workflow 中访问

```python
# AgentWorkflowEngine 创建 AgentContext
context = AgentContext(
    workflow_id=workflow_id,
    variables=input_data or {},
    memory_manager=self.agent.memory_manager  # 从 BaseAgent 传递
)

# Step Agent 通过 context 访问
class ScraperAgent(BaseStepAgent):
    async def execute(self, input_data, context):
        # 访问 KV Storage
        script = await context.memory_manager.get_data("script_key")
```

---

## API 参考

### MemoryManager 初始化

```python
MemoryManager(
    user_id: Optional[str] = None,      # 用户ID，默认 "default"
    config_service = None               # 配置服务，提供 KV Storage 路径
)
```

### Variables API

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `store_memory(key, value)` | 存储临时变量 | None |
| `get_memory(key, default=None)` | 获取临时变量 | Any |
| `delete_memory(key)` | 删除临时变量 | bool |
| `clear_memory()` | 清空所有临时变量 | None |
| `has_key(key)` | 检查变量是否存在 | bool |
| `list_keys()` | 列出所有变量键 | Set[str] |

### KV Storage API

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `set_data(key, value, user_id=None)` | 存储持久化数据 | bool |
| `get_data(key, default=None, user_id=None)` | 获取持久化数据 | Any |
| `delete_data(key, user_id=None)` | 删除持久化数据 | bool |
| `clear_all_data(user_id=None)` | 清空用户所有数据 | int |
| `list_data_keys(user_id=None)` | 列出用户所有键 | List[str] |

### 状态检查 API

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `is_kv_storage_enabled()` | 检查 KV Storage 是否启用 | bool |
| `is_long_term_memory_enabled()` | 检查 Long-term Memory 是否启用 | bool |
| `get_memory_stats()` | 获取内存统计信息 | Dict |

### 统计信息示例

```python
stats = memory.get_memory_stats()
# 返回:
{
    "variables_count": 5,
    "long_term_memory_enabled": False,
    "kv_storage_enabled": True
}
```

---

## 最佳实践

### 1. 选择合适的存储层

```python
# ❌ 错误：使用 Variables 存储持久化数据
await memory.store_memory("user_config", config)  # 进程重启后丢失

# ✅ 正确：使用 KV Storage 存储持久化数据
await memory.set_data("user_config", config)  # 进程重启后保留
```

### 2. 正确使用 user_id 实现数据隔离

**核心原则**：Memory 绑定到用户，不绑定到 BaseAgent 实例

```python
# ❌ 错误：每次创建 BaseAgent 时不指定 user_id（会生成随机 user_id）
agent1 = BaseAgent(config, config_service=config)  # agent_xxx-uuid1
agent2 = BaseAgent(config, config_service=config)  # agent_xxx-uuid2
# agent1 和 agent2 无法共享 memory！

# ✅ 正确：为同一用户的多个 BaseAgent 实例指定相同的 user_id
agent1 = BaseAgent(config, config_service=config, user_id="user123")
agent2 = BaseAgent(config, config_service=config, user_id="user123")
# agent1 和 agent2 共享同一用户的 memory

# ✅ 正确：不同用户使用不同的 user_id
user1_agent = BaseAgent(config, config_service=config, user_id="user1")
user2_agent = BaseAgent(config, config_service=config, user_id="user2")
# 两个用户的 memory 相互隔离

# ✅ 正确：直接创建 MemoryManager 时也要指定 user_id
memory1 = MemoryManager(user_id="user1", config_service=config)
memory2 = MemoryManager(user_id="user2", config_service=config)
await memory1.set_data("config", user1_config)
await memory2.set_data("config", user2_config)
```

**使用场景说明**：

1. **测试/开发环境**：使用固定的 `user_id="test_user"` 方便调试和缓存复用
2. **生产环境**：使用真实用户的唯一标识（如 user_id, username, email）
3. **独立模式**：不传 `user_id` 时，每个 BaseAgent 实例拥有独立的 memory 命名空间（不推荐）

### 3. 合理命名 Key

```python
# ❌ 错误：Key 命名不清晰
await memory.set_data("data", some_data)
await memory.set_data("cache", other_data)

# ✅ 正确：使用描述性的 Key 名称
await memory.set_data("scraper_script_e78c5581", script_data)
await memory.set_data("api_config_v2", api_config)
await memory.set_data("user_preferences", preferences)
```

### 4. 处理缓存未命中

```python
# ✅ 推荐模式：检查缓存 → 生成 → 存储 → 返回
cached_data = await memory.get_data(cache_key)
if cached_data:
    logger.info(f"缓存命中: {cache_key}")
    return cached_data

# 缓存未命中，生成新数据
new_data = await expensive_operation()

# 存储到缓存
await memory.set_data(cache_key, new_data)
logger.info(f"已缓存: {cache_key}")

return new_data
```

---

## 故障排查

### KV Storage 不可用

**症状**: 调用 `set_data()` 返回 False，日志显示 "KV storage not enabled"

**原因**: MemoryManager 创建时未提供 `config_service`

**解决**:
```python
# ❌ 错误
memory = MemoryManager(user_id="user123")  # KV Storage 未启用

# ✅ 正确
from base_app.server.core.config_service import ConfigService
config_service = ConfigService()
memory = MemoryManager(user_id="user123", config_service=config_service)
```

### 数据丢失或缓存失效

**症状 1**: 存储的数据在进程重启后消失

**原因**: 使用了 Variables 而非 KV Storage

**解决**:
```python
# ❌ 错误：使用 Variables（临时存储）
await memory.store_memory("important_data", data)

# ✅ 正确：使用 KV Storage（持久化存储）
await memory.set_data("important_data", data)
```

**症状 2**: 每次运行都提示"脚本不存在，自动生成"，缓存从未命中

**原因**: 每次创建 BaseAgent 时未指定 user_id，导致使用随机的 `agent_xxx` 作为 user_id

**诊断**:
```bash
# 查看数据库中的 user_id
python tests/debug/inspect_kv_storage.py --db ~/.local/share/baseapp/agent_kv.db

# 如果看到多个 agent_xxx-uuid 格式的 user_id，说明有问题
```

**解决**:
```python
# ❌ 错误：不指定 user_id
agent = BaseAgent(config, config_service=config)
# 每次运行生成新的 agent_xxx-uuid，无法访问之前的缓存

# ✅ 正确：指定固定的 user_id
agent = BaseAgent(config, config_service=config, user_id="test_user")
# 多次运行使用同一个 user_id，可以访问之前的缓存

# 或者在测试脚本中
runner = WorkflowTestRunner(user_id="test_user")  # 指定固定 user_id
await runner.initialize()
```

### JSON 序列化错误

**症状**: `set_data()` 失败，日志显示 JSON 序列化错误

**原因**: 存储的对象不可 JSON 序列化

**解决**:
```python
# ❌ 错误：存储不可序列化的对象
await memory.set_data("key", datetime.now())  # datetime 不可 JSON 序列化

# ✅ 正确：转换为可序列化的格式
await memory.set_data("key", datetime.now().isoformat())  # 转为字符串
await memory.set_data("key", {"timestamp": time.time()})  # 使用基础类型
```

---

## 版本历史

### v3.0 (当前版本) - 三层架构

- ✅ **Variables**: 临时变量存储
- ✅ **KV Storage**: SQLite 持久化存储（自动初始化）
- ⏳ **Long-term Memory**: mem0 智能记忆（待启用）

**关键改进**:
- 移除了 `enable_memory`, `enable_kv_storage` 等配置开关
- KV Storage 自动初始化，无需显式调用 `initialize()`
- 简化了 API，提供了 config_service 即可启用

### v2.0 - 双层架构（已废弃）

- Variables + Long-term Memory
- **问题**: 缺少中间层的持久化 KV 存储

### v1.0 - 单层架构（已废弃）

- 仅 Variables
- **问题**: 无持久化能力

---

## 相关文档

- [BaseAgent 架构](ARCHITECTURE.md) - BaseAgent 整体架构
- [Workflow 规范](workflow_specification.md) - Workflow 中的变量传递
- [ScraperAgent 设计](agents/scraper_agent_design.md) - ScraperAgent 脚本缓存实现
- [配置系统](../platform/config_design.md) - ConfigService 使用说明

---

**最后更新**: 2025-10-01
