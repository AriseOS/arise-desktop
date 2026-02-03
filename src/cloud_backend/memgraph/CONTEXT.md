# Memory Graph (memgraph)

用户操作知识库系统，从浏览器操作录制中学习，支持自然语言查询操作路径。

## 核心功能

1. **学习**: 从 Recording 中提取操作路径存入图
2. **检索**: 用自然语言查询，返回相关操作路径
3. **重放**: 提供具体操作步骤供 Agent 执行

## 核心概念 (V2)

| 概念 | 说明 | 图中角色 |
|------|------|----------|
| **State** | 一类页面的抽象（如"产品详情页"） | 节点 |
| **PageInstance** | 具体页面 URL 实例 | State 属性 |
| **Action** | State 之间的跳转 | 边 |
| **IntentSequence** | 页面内的操作序列（V2: 独立节点） | 节点，通过 HAS_SEQUENCE 关联 State |
| **CognitivePhrase** | 任务工作流（包含 execution_plan） | 节点 |
| **QueryResult** | 统一查询结果（task/navigation/action） | 数据模型 |

### V2 关键变更

- **IntentSequence 独立节点**: 支持向量索引直接查询
- **导航标记**: `causes_navigation` + `navigation_target_state_id`
- **执行计划**: CognitivePhrase 包含结构化 `execution_plan`
- **统一查询**: Reasoner.query() 自动判断类型

## 存储后端

默认使用 **SurrealDB** 持久化存储，支持：
- 持久化（重启不丢数据）
- 向量索引（语义搜索）
- 图查询（关系遍历）
- 原生复杂类型存储（无需 JSON 序列化）

配置见 `cloud-backend.yaml`:
```yaml
graph_store:
  backend: surrealdb  # 或 networkx (内存，重启丢失)
  url: ws://localhost:8000/rpc
  namespace: ami
  database: memory
  username: root
  password: your_password
```

## 目录结构

- `memory/` - WorkflowMemory 核心实现，管理用户的操作图
- `ontology/` - 数据模型定义（State, Action, IntentSequence, QueryResult 等）
- `graphstore/` - 图存储抽象层（SurrealDB / NetworkX）
- `services/` - 服务层（EmbeddingService 等）
- `thinker/` - Recording 解析器（WorkflowProcessor）
- `reasoner/` - 图推理和查询接口（query, navigate, plan）
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

### POST /api/v1/memory/v2/query (V2 统一查询)

统一查询接口，支持三种查询类型：

**查询类型自动推断**:
- `start_state` + `end_state` → **navigation** 查询
- `current_state` → **action** 查询
- 否则 → **task** 查询

```json
// 任务查询
{"target": "在 Product Hunt 查看团队信息"}

// 导航查询
{"start_state": "首页", "end_state": "团队页"}

// 操作查询
{"target": "查看团队", "current_state": "state_123"}

// 探索查询（当前页面能做什么）
{"target": "", "current_state": "state_123"}

// 响应
{
    "success": true,
    "query_type": "task|navigation|action",
    "states": [...],           // task/navigation
    "actions": [...],          // task/navigation
    "intent_sequences": [...], // action
    "cognitive_phrase": {...}, // task (如果匹配)
    "execution_plan": [...],   // task (如果匹配)
    "metadata": {...}
}
```

### POST /api/v1/memory/query (旧版，路径搜索)

自然语言查询操作路径（embedding-based）。

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
    "paths": [...]
}
```

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
- `memory/memory.py` - Memory 抽象接口和 Manager 定义
- `thinker/workflow_processor.py` - 解析 Recording 生成图数据
- `reasoner/reasoner.py` - Reasoner 查询接口（query, navigate, plan）
- `services/embedding_service.py` - Embedding 生成与检索
- `ontology/state.py` - State/PageInstance 定义
- `ontology/action.py` - Action 定义
- `ontology/intent_sequence.py` - IntentSequence 定义
- `ontology/cognitive_phrase.py` - CognitivePhrase/ExecutionStep 定义
- `ontology/query_result.py` - QueryResult 统一查询结果（V2）

## 设计文档

- `docs/memory-graph-redesign-v2.md` - V2 重新设计
- `docs/design/memory-graph-ontology-design.md` - 原有设计思路
