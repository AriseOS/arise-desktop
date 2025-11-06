# Workflow 管理系统 - 需求分析

## 文档信息
- **版本**: 1.0
- **日期**: 2025-11-04
- **状态**: 草稿

---

## 1. 背景

AgentCrafter 需要实现从用户行为录制到 workflow 执行的完整闭环。当前系统已经实现了录制功能，但缺少从录制数据生成可执行 workflow 的完整流程。

---

## 2. 核心设计理念

### 2.1 学习阶段 vs 生成产物

系统将数据分为两类：

**学习阶段（临时数据）**
- Recording（操作录制）
- Intent（意图提取）
- MetaFlow（中间表示）
- 用户学习和调试过程中产生的临时数据
- 用户手动清理

**生成产物（持久数据）**
- Workflow（可执行的工作流）
- 最终产物，需要长期保存
- 可以被多次执行

### 2.2 完整流程

```
1. 录制操作 (Recording)
   ↓
2. 提取意图 (Intent Extraction)
   ↓
3. 生成 MetaFlow (Intent Graph → MetaFlow)
   ↓
4. 生成 Workflow (MetaFlow → Workflow)
   ↓
5. 执行 Workflow (Execute)
```

---

## 3. 功能需求

### 3.1 录制阶段（已实现）

- 用户通过 Chrome 插件开始/停止录制
- 系统捕获用户操作（点击、输入、导航等）
- 用户输入 title 和 description

### 3.2 Intent 提取

**功能**：从录制的 operations 中提取语义化的意图

**输入**：`session_id`（对应的录制会话）

**处理**：
- 读取 operations.json
- 调用 IntentExtractor 提取意图
- 保存 intents.json

**输出**：
```json
{
  "success": true,
  "session_id": "rec_abc123",
  "intents": [
    {
      "id": "intent_0",
      "description": "Navigate to Amazon homepage",
      "operation_indices": [0, 1, 2]
    }
  ],
  "intents_count": 5
}
```

### 3.3 MetaFlow 生成

**功能**：从 intents 生成 MetaFlow YAML

**输入**：`session_id`

**处理**：
- 读取 intents.json
- 构建 Intent Memory Graph
- 生成 MetaFlow YAML
- 保存 metaflow.yaml

**输出**：
```json
{
  "success": true,
  "session_id": "rec_abc123",
  "metaflow_yaml": "...",
  "nodes_count": 5
}
```

### 3.4 Workflow 生成

**功能**：从 MetaFlow 生成可执行的 Workflow

**输入**：`session_id`

**处理**：
- 读取 metaflow.yaml
- 调用 WorkflowGenerator 生成 workflow YAML
- 验证 workflow 格式
- 保存到 `workflows/{workflow_name}/workflow.yaml`
- workflow_name 从 recording title 自动转换

**输出**：
```json
{
  "success": true,
  "workflow_name": "collect-amazon-prices",
  "workflow_yaml": "...",
  "overwritten": false
}
```

**Workflow 命名规则**：
- 从 recording 的 title 自动转换
- 转小写，空格变连字符
- 例如："Collect Amazon Prices" → "collect-amazon-prices"

**同名处理**：
- 如果已存在同名 workflow，直接覆盖
- 不保留版本

### 3.5 Learning Session 管理

**查看 session 列表**：
- 列出用户所有的 learning sessions
- 显示 session_id、title、status、operations_count、created_at
- 按创建时间倒序排列

**查看 session 详情**：
- 显示完整的 metadata
- 包含 operations_count、intents_count、has_metaflow、workflow_generated 等信息

**删除 session**：
- 用户手动删除 learning session
- 删除所有相关数据（operations、intents、metaflow）
- 不影响已生成的 workflow

### 3.6 Workflow 管理

**查看 workflow 列表**：
- 列出用户所有保存的 workflows
- 显示 workflow_name、description、execution_count、last_executed_at
- 按更新时间倒序排列

**查看 workflow 详情**：
- 返回 workflow.yaml 内容
- 返回 metadata（来源 session_id、执行统计等）

**删除 workflow**：
- 删除 workflow 及其所有执行记录

### 3.7 Workflow 执行

**执行 workflow**：
- 输入：workflow_name
- 创建异步执行任务
- 返回 task_id
- 使用 BaseAgent 执行 workflow
- 更新 workflow 执行统计（execution_count、last_executed_at）

**查询执行状态**：
- 输入：task_id
- 返回：status（running/completed/failed）、progress、current_step
- 如果失败，返回 error_message 和 failed_step

**查看执行历史**：
- 输入：workflow_name
- 返回该 workflow 的所有执行记录
- 只保留最近 50 次执行

**执行记录清理**：
- 自动清理，每个 workflow 只保留最近 50 次执行记录

---

## 4. 数据存储

### 4.1 存储方案

使用纯文件系统，不修改数据库。

**目录结构**：
```
storage/users/{user_id}/
  ├── learning/                    # 学习阶段（临时）
  │   └── {session_id}/
  │       ├── operations.json      # 录制的操作
  │       ├── intents.json         # 提取的意图
  │       ├── metaflow.yaml        # 生成的 MetaFlow
  │       └── metadata.json        # 元数据
  │
  └── workflows/                   # 生成产物（持久）
      └── {workflow_name}/
          ├── workflow.yaml        # 可执行的 workflow
          ├── metadata.json        # 元数据
          └── executions/          # 执行记录
              └── {task_id}.json
```

### 4.2 数据格式

**learning session metadata.json**：
```json
{
  "session_id": "rec_abc123",
  "title": "Collect Amazon Prices",
  "description": "...",
  "status": "recording|stopped|intent_extracted|metaflow_generated|workflow_generated",
  "operations_count": 42,
  "workflow_generated": false,
  "generated_workflow_name": null,
  "created_at": "2024-11-04T12:00:00Z",
  "stopped_at": "2024-11-04T12:05:00Z"
}
```

**workflow metadata.json**：
```json
{
  "workflow_name": "collect-amazon-prices",
  "description": "...",
  "source_session_id": "rec_abc123",
  "execution_count": 5,
  "last_executed_at": "2024-11-04T15:00:00Z",
  "created_at": "2024-11-04T12:00:00Z",
  "updated_at": "2024-11-04T12:00:00Z"
}
```

**execution {task_id}.json**：
```json
{
  "task_id": "task_xxx",
  "workflow_name": "collect-amazon-prices",
  "status": "running|completed|failed",
  "progress": 100,
  "current_step": "step_3",
  "result": {...},
  "execution_time_ms": 5432,
  "error_message": null,
  "failed_step": null,
  "started_at": "2024-11-04T15:00:00Z",
  "completed_at": "2024-11-04T15:00:05Z"
}
```

---

## 5. API 设计

### 5.1 Learning Phase APIs

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/learning/extract-intents` | POST | 提取 intents |
| `/api/learning/generate-metaflow` | POST | 生成 MetaFlow |
| `/api/learning/sessions` | GET | 列出所有 learning sessions |
| `/api/learning/sessions/{session_id}` | GET | 获取 session 详情 |
| `/api/learning/sessions/{session_id}` | DELETE | 删除 session |

### 5.2 Workflow APIs

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/workflows/generate` | POST | 从 MetaFlow 生成 workflow |
| `/api/workflows` | GET | 列出所有 workflows |
| `/api/workflows/{workflow_name}` | GET | 获取 workflow 详情 |
| `/api/workflows/{workflow_name}` | DELETE | 删除 workflow |

### 5.3 Execution APIs

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/workflows/{workflow_name}/execute` | POST | 执行 workflow |
| `/api/workflows/executions/{task_id}` | GET | 查询执行状态 |
| `/api/workflows/{workflow_name}/executions` | GET | 查看执行历史 |

---

## 6. 设计决策

### 6.1 接口模式
- **早期版本使用同步接口**：Intent 提取、MetaFlow 生成、Workflow 生成都是同步的
- 前端可能需要等待 30s-2min，但实现简单

### 6.2 数据清理
- **Learning session**：用户手动清理
- **Execution 记录**：自动清理，只保留最近 50 次

### 6.3 Workflow 覆盖
- 同名 workflow 直接覆盖
- 不支持版本控制（未来版本可能添加）

### 6.4 Workflow 参数
- 暂不支持 workflow 的 input 参数
- 未来版本再添加

### 6.5 实时进度
- 暂不支持实时进度推送（WebSocket/SSE）
- 使用轮询查询执行状态

---

## 7. 限制和约束

### 7.1 当前版本限制

- 不修改数据库（纯文件系统）
- 同步接口（可能等待较长时间）
- 不支持 workflow 参数
- 不支持实时进度
- 不支持 workflow 版本控制
- 不支持批量生成 workflow

### 7.2 假设

- 用户数量 < 1000（文件系统足够）
- LLM API 调用在合理时间内完成（< 60s）
- 用户理解同名 workflow 会覆盖
- 用户会手动清理 learning sessions
- 50 次执行记录足够

---

## 8. 插件端调用流程

```javascript
// 1. 录制
const {session_id} = await POST('/api/recording/start', {title, description})
// ... 用户操作 ...
await POST('/api/recording/stop', {session_id})

// 2. 提取 Intent
await POST('/api/learning/extract-intents', {session_id})

// 3. 生成 MetaFlow
await POST('/api/learning/generate-metaflow', {session_id})

// 4. 生成 Workflow
const {workflow_name} = await POST('/api/workflows/generate', {session_id})

// 5. 可选：清理学习数据
await DELETE(`/api/learning/sessions/${session_id}`)

// 6. 执行 Workflow
const {task_id} = await POST(`/api/workflows/${workflow_name}/execute`)

// 7. 查询执行状态（轮询）
const status = await GET(`/api/workflows/executions/${task_id}`)

// 8. 查看执行历史
const history = await GET(`/api/workflows/${workflow_name}/executions`)
```

---

## 9. 未来版本功能（不在当前范围）

- Workflow 版本控制
- 实时执行进度推送（WebSocket/SSE）
- Workflow 输入参数支持
- 批量生成 workflow
- Learning session 自动清理策略
- 数据库索引（提升查询性能）
- Workflow 共享
- 定时执行 workflow
