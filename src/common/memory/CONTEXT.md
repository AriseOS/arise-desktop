# Memory Graph

> 公共库，供 Desktop App 和 Cloud Backend 共同使用

用户操作知识库系统，支持从录制和任务执行中自动学习，提供自然语言查询和任务规划。

## 使用方式

```python
from src.common.memory import WorkflowMemory, Reasoner, WorkflowProcessor
from src.common.memory.ontology import State, Action, IntentSequence, CognitivePhrase
from src.common.memory.graphstore import create_graph_store
from src.common.memory.services import EmbeddingService
from src.common.memory.planner import PlannerAgent
from src.common.memory.learner import LearnerAgent, TaskExecutionData
```

## 核心功能

1. **学习**: 从 Recording 和任务执行中提取操作路径存入图（两种途径）
2. **规划**: PlannerAgent 在任务前查询 Memory，输出 MemoryPlan 辅助分解
3. **检索**: 用自然语言查询，返回相关操作路径
4. **重放**: 提供具体操作步骤供 Agent 执行

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

支持多种后端：SurrealKV (Desktop App 本地), RocksDB (Cloud Backend), Memory (测试), WebSocket (远程)。详见 `graphstore/CONTEXT.md`。

## 目录结构

- `ontology/` - 数据模型定义（State, Action, IntentSequence, CognitivePhrase 等）
- `graphstore/` - 图存储抽象层（SurrealDB / NetworkX）
- `memory/` - WorkflowMemory 核心实现 + MemoryService 高级接口
- `services/` - 服务层（EmbeddingService 等）
- `thinker/` - Recording 解析器（WorkflowProcessor，将 operations 转为图实体）
- `reasoner/` - 图推理和查询接口
- `planner/` - PlannerAgent（任务前读 Memory，输出 MemoryPlan）
- `learner/` - LearnerAgent（任务后分析执行数据，自动生成 CognitivePhrase）

## Online Learning 系统

Agent 执行任务时自动学习，分两层：

### Layer 1: Runtime Learning（实时）

执行 browser 子任务时，BehaviorRecorder (CDP) 捕获所有操作事件。每个子任务完成后，operations 经 WorkflowProcessor 写入 Memory 图（State/Action/IntentSequence）。后续子任务访问相同页面时，Layer 2 Runtime 自动查到新写入的 page operations。

```
BehaviorRecorder → operations → WorkflowProcessor → State/Action/IntentSequence
```

### Layer 2: Post-Execution Learning（任务后）

所有子任务完成后，ExecutionDataCollector 从 agent messages 中提取 tool use + thinking，压缩为 TaskExecutionData。LearnerAgent (LLM) 分析执行数据，判断 Memory 中是否已有覆盖，对未覆盖的部分自动生成 CognitivePhrase。

```
ExecutionDataCollector → TaskExecutionData → LearnerAgent → CognitivePhrase
```

### 对称的 Planner/Learner 架构

| | PlannerAgent | LearnerAgent |
|---|---|---|
| 时机 | 任务开始前 | 任务完成后 |
| 输入 | 用户请求文本 | TaskExecutionData |
| 输出 | MemoryPlan（读取建议） | LearnResult（写入结果） |
| LLM 工具 | recall_phrases, search_states, explore_graph | recall_phrases, find_states_by_urls, get_state_sequences, verify_action |
| 最终动作 | 返回 workflow_guide | 创建 CognitivePhrase |

### 数据流

```
任务开始
  → PlannerAgent.plan(task) → MemoryPlan → workflow_guide 注入
  → AMITaskExecutor 执行子任务
     → BehaviorRecorder 录制 → WorkflowProcessor → 图实体（实时写入）
     → ExecutionDataCollector 收集 tool records
  → LearnerAgent.learn(TaskExecutionData) → CognitivePhrase（任务后写入）
     → auto-share to public memory
下次类似任务
  → PlannerAgent recall 命中 CognitivePhrase → L1 级规划 → 更快完成
```


## API 接口

所有接口定义在 Cloud Backend `main.py`。

### POST /api/v1/memory/add

添加 Recording / Operations 到 Memory 图。

### POST /api/v1/memory/plan

任务规划（PlannerAgent 查询 Memory）。

### POST /api/v1/memory/learn

从任务执行数据中学习，自动生成 CognitivePhrase。

```json
// 请求
{
    "user_id": "user123",
    "execution_data": {
        "task_id": "xxx",
        "user_request": "帮我看亚马逊上卖的最好的 AI 眼镜",
        "subtasks": [...],
        "completed_count": 3,
        "total_count": 3
    }
}

// 响应
{
    "success": true,
    "phrase_created": true,
    "phrase_ids": ["phrase_xxx"],
    "shared_phrase_ids": ["public_xxx"],
    "reason": "New workflow for Amazon search"
}
```

### POST /api/v1/memory/v2/query (V2 统一查询)

统一查询接口，支持 task / navigation / action 三种查询类型（自动推断）。

### GET /api/v1/memory/stats

获取 Memory 统计信息。

### DELETE /api/v1/memory

清空用户的 Memory。

## 典型使用流程

```
录制写入: Recording → POST /memory/add → WorkflowProcessor → Memory 图
任务规划: POST /memory/plan → PlannerAgent → MemoryPlan → workflow_guide
任务执行: Agent 执行 → BehaviorRecorder → POST /memory/add → 实时写入图
执行学习: Agent 完成 → POST /memory/learn → LearnerAgent → CognitivePhrase
```

## 关键文件

- `memory/workflow_memory.py` - WorkflowMemory 类，管理用户图
- `memory/memory.py` - Memory 抽象接口和 Manager 定义
- `memory/memory_service.py` - MemoryService 高级接口（learn, plan 等）
- `thinker/workflow_processor.py` - 解析 Recording/Operations 生成图数据
- `reasoner/reasoner.py` - Reasoner 查询接口（query, navigate, plan）
- `planner/planner_agent.py` - PlannerAgent（任务前规划，输出 MemoryPlan）
- `planner/tools.py` - PlannerTools（recall_phrases, search_states, explore_graph）
- `planner/models.py` - CoverageItem, MemoryPlan, PlanResult
- `learner/learner_agent.py` - LearnerAgent（任务后学习，生成 CognitivePhrase）
- `learner/tools.py` - LearnerTools（recall_phrases, find_states_by_urls, get_state_sequences, verify_action）
- `learner/models.py` - TaskExecutionData, ToolUseRecord, LearnResult, LearningPlan
- `learner/prompts.py` - LearnerAgent 系统提示（Recall-First 工作流）
- `services/embedding_service.py` - Embedding 生成与检索
- `ontology/cognitive_phrase.py` - CognitivePhrase/ExecutionStep 定义
- `ontology/state.py` - State/PageInstance 定义
- `ontology/action.py` - Action 定义
- `ontology/intent_sequence.py` - IntentSequence 定义

## Private + Public 并行查询

Reasoner 支持 `public_memory` 参数，所有查询层同时查 Private + Public：

| 查询层 | 融合方式 |
|--------|---------|
| L1 CognitivePhrase | 合并 phrases 列表，单次 LLM 调用选最佳 |
| L2 Path Retrieval | 两边并行跑 embedding+BFS，LLM 选一条路径 |
| Navigation | 两边各跑 shortest path，LLM 选一条 |
| Action | 合并去重 IntentSequences（不用 LLM） |

QueryResult 包含 `source` 字段标识结果来源（"private"/"public"/"merged"）。

## 设计文档

- `docs/online-learning-design.md` - Runtime Learning（BehaviorRecorder → Memory）
- `docs/online-learning-cognitive-phrase-design.md` - Post-Execution Learning（LearnerAgent → CognitivePhrase）
- `docs/memory-planner-agent-design.md` - PlannerAgent 设计
- `docs/memory-graph-redesign-v2.md` - V2 重新设计
- `docs/memory-merge-private-public-design.md` - Private + Public 并行查询设计
- `docs/design/browser-memory-learning.md` - 完整 Memory 系统设计（本体、存储、检索）
