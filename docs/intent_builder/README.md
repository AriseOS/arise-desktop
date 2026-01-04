# Intent Builder

将用户的浏览器录制转换为可执行的 Workflow YAML。

## 当前架构 (v0.4.0)

**Skills-based Architecture**: 使用 Claude Agent SDK + Skills 替代了之前的 MetaFlow 中间层。

```
Recording → IntentExtractor → WorkflowBuilder (Claude Agent + Skills) → Validator → Workflow
                                    ↑
                           User Dialogue (optional)
```

## 核心组件

| 组件 | 位置 | 职责 |
|------|------|------|
| IntentExtractor | `extractors/` | 从操作序列提取语义 Intent |
| WorkflowBuilder | `agents/workflow_builder.py` | Claude Agent 生成 Workflow |
| WorkflowValidator | `validators/` | 规则验证 + 语义验证 |
| WorkflowService | `services/workflow_service.py` | 统一 API 入口 |
| Skills | `.claude/skills/` | Agent 的知识库 |

## Skills 架构

```
.claude/skills/
├── workflow-generation/     # 主要生成流程
├── workflow-validation/     # 验证规则和脚本
├── agent-specs/             # Agent 规格说明
└── workflow-optimizations/  # 优化模式
```

详细说明见 `src/cloud_backend/intent_builder/CONTEXT.md`

## API 使用

### 一次性生成

```python
from intent_builder.services import WorkflowService

service = WorkflowService(api_key="...", base_url="...")
response = await service.generate(
    task_description="Extract products from website",
    intent_sequence=[...]
)
```

### 流式生成

```python
async for event in service.generate_stream(request):
    print(f"Stage: {event.status}, Progress: {event.progress}%")
```

### 交互式对话

```python
chat_response = await service.chat(
    session_id=response.session_id,
    message="Why did you use browser_agent here?"
)
```

## 文档

- `architecture.md` - 系统架构设计
- `examples/` - 示例文件

## 历史变更

- **v0.4.0** (2025-01): Skills-based 架构，移除 MetaFlow
- **v0.3.0**: MetaFlow 中间层（已废弃）
- **v0.2.0**: 基于规则的生成器（已废弃）
