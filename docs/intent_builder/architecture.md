# Intent Builder 架构设计

**版本**: v0.4.0 (Skills-based Architecture)
**更新日期**: 2025-01

## 1. 概述

Intent Builder 将用户的浏览器录制转换为可执行的 Workflow YAML。

### 核心流程

```
Recording (JSON) → IntentExtractor → Intent Sequence → WorkflowBuilder → Workflow YAML
                                                              ↓
                                                    Claude Agent + Skills
                                                              ↓
                                                        Validator
                                                              ↓
                                                     Workflow (v2 format)
```

### 设计原则

1. **Skills 驱动**: Agent 通过 Skills 获取规格和最佳实践
2. **对话式**: 支持多轮对话修改 Workflow
3. **验证驱动**: 规则验证 + 语义验证确保正确性

## 2. 核心组件

### 2.1 IntentExtractor

**位置**: `extractors/intent_extractor.py`

从用户操作序列提取语义化的 Intent。

```python
@dataclass
class Intent:
    id: str                          # 唯一标识
    description: str                 # 语义描述
    operations: List[Operation]      # 原始操作序列
    created_at: datetime
    source_session_id: str
```

**提取策略**:
- 基于 URL 变化切分操作序列
- LLM 生成语义描述

### 2.2 WorkflowBuilder

**位置**: `agents/workflow_builder.py`

基于 Claude Agent SDK 的 Workflow 生成器。

**类**:
- `WorkflowBuilder`: 一次性生成
- `WorkflowBuilderSession`: 交互式对话

**工作流程**:
1. 接收 Intent 序列和任务描述
2. Claude Agent 调用 Skills 获取规格
3. 生成 Workflow YAML (v2 format)
4. 验证并迭代修复

### 2.3 Skills

**位置**: `.claude/skills/`

Agent 的知识库，包含:

| Skill | 内容 |
|-------|------|
| `workflow-generation` | 生成流程、v2 格式规范 |
| `agent-specs` | browser_agent, scraper_agent 等规格 |
| `workflow-validation` | 验证脚本 |
| `workflow-optimizations` | 优化模式 (click-to-navigate 等) |

### 2.4 WorkflowValidator

**位置**: `validators/`

两层验证:

1. **RuleValidator**: 快速结构检查
   - 必需字段
   - Agent 类型
   - 变量引用
   - Step ID 唯一性

2. **SemanticValidator**: LLM 语义检查
   - 任务完整性
   - 数据流正确性

### 2.5 WorkflowService

**位置**: `services/workflow_service.py`

统一 API 入口:
- `generate()`: 一次性生成
- `generate_stream()`: 流式生成 (SSE)
- `chat()`: 对话修改

## 3. Workflow v2 格式

```yaml
apiVersion: "ami.io/v2"
name: workflow-name
description: "Workflow description"

input: url   # 或 inputs: {...}

steps:
  - id: navigate
    agent: browser_agent
    inputs:
      target_url: "{{url}}"

  - id: extract
    agent: scraper_agent
    inputs:
      extraction_method: script
      data_requirements:
        output_format:
          name: "Product name"
    outputs:
      extracted_data: products

  - id: process
    foreach: "{{products}}"
    as: product
    do:
      - id: store
        agent: storage_agent
        inputs:
          operation: store
          data: "{{product}}"
```

**v2 与 v1 区别**:
- 移除 `kind: "Workflow"`
- `metadata.name` → `name` (顶层)
- `agent_type` → `agent`
- 控制流用专用键: `foreach:`, `if:`, `while:`
- 循环体用 `do:` (不是 `steps:`)
- 循环变量用 `as:` (不是 `item_var:`)

## 4. API 端点

### 生成

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/workflows/generate` | POST | 直接生成 |
| `/api/v1/workflows/generate-stream` | POST | 流式生成 (SSE) |

### 对话

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/workflow-sessions` | POST | 创建对话会话 |
| `/api/v1/workflow-sessions/{id}/chat` | POST | 发送消息 |
| `/api/v1/workflow-sessions/{id}` | DELETE | 关闭会话 |

## 5. 使用示例

### 一次性生成

```python
from intent_builder.services import WorkflowService

service = WorkflowService(api_key="...", base_url="...")
response = await service.generate(
    task_description="Extract products from Allegro",
    intent_sequence=[
        {"description": "Navigate to category", "operations": [...]},
        {"description": "Extract product list", "operations": [...]}
    ]
)

if response.success:
    print(response.workflow_yaml)
```

### 流式生成

```python
async for event in service.generate_stream(request):
    # PENDING → ANALYZING → UNDERSTANDING → GENERATING → VALIDATING → COMPLETED
    print(f"{event.status}: {event.progress}%")
```

### 交互式对话

```python
# 创建会话
response = await service.generate(task_description="...", ...)

# 对话修改
chat = await service.chat(
    session_id=response.session_id,
    message="Add pagination support"
)

if chat.workflow_updated:
    print(chat.workflow_yaml)
```

## 6. 目录结构

```
src/cloud_backend/intent_builder/
├── agents/
│   ├── workflow_builder.py      # Claude Agent
│   └── tools/                   # Agent 工具
├── extractors/
│   └── intent_extractor.py      # Intent 提取
├── validators/
│   ├── rule_validator.py        # 规则验证
│   └── semantic_validator.py    # 语义验证
├── services/
│   └── workflow_service.py      # API 服务
├── core/
│   ├── intent.py                # Intent 数据结构
│   └── schemas.py               # Pydantic schemas
├── storage/                     # 会话存储
└── .claude/skills/              # Skills 目录
```

## 7. 历史架构

### v0.3.0 - MetaFlow (已废弃)

```
Recording → IntentExtractor → MetaFlowGenerator → MetaFlow → WorkflowGenerator → Workflow
```

MetaFlow 是一个中间表示层，后来被认为是不必要的复杂度，被 Skills-based 架构取代。

### v0.2.0 - Rule-based (已废弃)

基于规则的生成器，无 LLM 推理能力。
