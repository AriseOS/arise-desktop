# Memory Graph (memgraph)

用户操作知识库系统，从浏览器操作录制中学习，支持自然语言查询操作路径。

## 核心功能

1. **学习**: 从 Recording 中提取操作路径存入图
2. **检索**: 用自然语言查询，返回相关操作路径
3. **重放**: 提供具体操作步骤供 Agent 执行

## 核心概念

| 概念 | 说明 | 图中角色 |
|------|------|----------|
| **State** | 一类页面的抽象（如"产品详情页"） | 节点 |
| **PageInstance** | 具体页面 URL 实例 | State 属性 |
| **Action** | State 之间的跳转 | 边 |
| **IntentSequence** | 页面内的操作序列（点击、输入等） | State 属性 |

## 目录结构

- `memory/` - WorkflowMemory 核心实现，管理用户的操作图
- `ontology/` - 数据模型定义（State, Action, Intent 等）
- `graphstore/` - 图存储抽象层
- `services/` - 服务层（EmbeddingService 等）
- `thinker/` - Recording 解析器（WorkflowProcessor）
- `reasoner/` - 图推理（路径查找等）
- `agent/` - Agent 集成接口

## API 接口

所有接口定义在 `main.py`，前端调用方法在 `api.js`。

### POST /api/v1/memory/add

添加 Recording 到 Memory 图。

```json
// 请求
{
    "user_id": "user123",
    "recording_id": "session_xxx",
    "generate_embeddings": true  // 查询需要设为 true
}

// 响应
{
    "success": true,
    "states_added": 3,
    "states_merged": 1,
    "intent_sequences_added": 5
}
```

### POST /api/v1/memory/query

自然语言查询操作路径。

```json
// 请求
{
    "user_id": "user123",
    "query": "通过 Product Hunt 周榜查看产品团队成员",
    "top_k": 3,
    "min_score": 0.5
}

// 响应
{
    "success": true,
    "paths": [
        {
            "score": 0.85,
            "steps": [
                {
                    "state": {"description": "周榜页", "page_url": "..."},
                    "action": {"description": "点击产品"},
                    "intent_sequence": {"intents": [...]}
                }
            ]
        }
    ]
}
```

**查询处理流程**:
1. LLM 重写 query → target_query + key_queries
2. Embedding 检索 → 匹配 State
3. 图路径搜索 → 起点到目标的路径
4. 评分排序 → 返回最佳路径

### GET /api/v1/memory/stats

获取 Memory 统计信息。

### DELETE /api/v1/memory

清空用户的 Memory。

## 前端调用

```javascript
// 添加到 Memory
await api.addToMemory(userId, {
    recordingId: sessionId,
    generateEmbeddings: true
});

// 查询 Memory
const result = await api.queryMemory(userId, "通过榜单查看团队信息");

// 获取统计
const stats = await api.getMemoryStats(userId);

// 清空
await api.clearMemory(userId);
```

## 典型使用流程

```
Recording → POST /recordings → POST /memory/add → Memory 图
                                                      ↓
用户查询 → POST /memory/query → 操作路径 → Agent 执行
```

## 关键文件

- `memory/workflow_memory.py` - WorkflowMemory 类，管理用户图
- `thinker/workflow_processor.py` - 解析 Recording 生成图数据
- `services/embedding_service.py` - Embedding 生成与检索
- `ontology/state.py` - State/PageInstance 定义
- `ontology/action.py` - Action 定义
- `ontology/intent.py` - Intent/IntentSequence 定义

## 设计文档

详细设计见 `docs/design/memory-graph-ontology-design.md`
