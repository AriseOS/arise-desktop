# Memory Module - Local Mem0 Integration

本模块集成了mem0开源版本，提供本地部署的长期记忆功能。

## 特性

### 简化的双层存储架构
1. **Variables**: 临时变量（会话内存储，进程重启后丢失）
2. **Long-term Memory**: 智能记忆（mem0本地版，真正的持久化存储，语义搜索）

### Mem0本地部署
- 使用mem0开源版本，无需API密钥
- 本地存储，数据隐私安全
- 支持语义搜索和智能记忆管理

## 安装依赖

```bash
pip install mem0ai
pip install chromadb  # 用于向量存储
```

## 环境配置

需要设置OpenAI API密钥（mem0需要LLM进行记忆处理）：

```bash
export OPENAI_API_KEY=your_openai_api_key
```

## 使用示例

### 基本使用

```python
from base_app.base_agent.memory import MemoryManager

# 启用长期记忆
memory_manager = MemoryManager(
    enable_long_term_memory=True,
    user_id="user123"
)

# 临时变量存储
await memory_manager.store_memory("temp_key", "temporary_value")
temp_value = await memory_manager.get_memory("temp_key")

# 长期记忆存储
await memory_manager.add_long_term_memory("用户喜欢喝咖啡")

# 搜索相关记忆
memories = await memory_manager.search_long_term_memory("饮品偏好")
```

### 自定义配置

```python
# 自定义mem0配置
mem0_config = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "my_memories",
            "path": "./my_chroma_db"
        }
    },
    "llm": {
        "provider": "openai",
        "config": {
            "model": "gpt-4o-mini"
        }
    }
}

memory_manager = MemoryManager(
    enable_long_term_memory=True,
    user_id="user123",
    mem0_config=mem0_config
)
```

## 默认配置

默认使用以下配置：
- **向量存储**: ChromaDB (本地存储在 `./chroma_db`)
- **LLM**: OpenAI gpt-4o-mini
- **嵌入模型**: OpenAI text-embedding-3-small

## 方法说明

### 临时变量操作

- `store_memory(key, value)` - 存储临时变量
- `get_memory(key, default=None)` - 获取临时变量
- `delete_memory(key)` - 删除临时变量
- `clear_memory()` - 清空所有临时变量
- `has_key(key)` - 检查临时变量是否存在
- `list_keys()` - 列出所有临时变量键

### 长期记忆操作

- `add_long_term_memory(content, user_id=None)` - 添加长期记忆
- `search_long_term_memory(query, user_id=None, limit=5)` - 搜索记忆
- `get_all_long_term_memories(user_id=None)` - 获取所有记忆
- `delete_long_term_memory(memory_id)` - 删除特定记忆
- `clear_long_term_memory(user_id=None)` - 清空所有记忆

### 状态检查

- `is_long_term_memory_enabled()` - 检查是否启用长期记忆
- `set_user_id(user_id)` - 设置用户ID
- `get_user_id()` - 获取当前用户ID
- `get_memory_stats()` - 获取内存使用统计

## 数据存储

- ChromaDB数据存储在本地 `./chroma_db` 目录
- 支持用户隔离，不同用户的记忆相互独立
- 所有数据保持本地，无需担心隐私问题

## 重要变更说明

### v2.0 架构简化
- **移除了"持久化内存"**：原来的memory字典实际上也是内存存储，容易造成混淆
- **简化为双层架构**：临时变量 + 真正的持久化存储（mem0）
- **接口保持兼容**：`store_memory()`现在只存储临时变量，移除了`persistent`参数
- **清晰的职责分工**：临时数据用variables，持久化数据用long_term_memory

### 迁移指南
如果之前使用了`store_memory(key, value, persistent=True)`，请改为：
```python
# 旧方式
await memory_manager.store_memory("key", "value", persistent=True)

# 新方式
await memory_manager.add_long_term_memory("contextual description of the data")
```

## 注意事项

1. 临时变量在进程重启后会丢失，这是设计行为
2. 首次使用长期记忆会自动创建本地数据库文件
3. 确保有足够的磁盘空间存储向量数据
4. OpenAI API调用仅用于记忆处理，不会发送原始数据
5. 可以通过自定义配置使用其他LLM提供商