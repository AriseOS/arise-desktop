# Intent Builder

Intent Builder 模块负责将 MetaFlow（用户意图的中间表示）转换为可执行的 BaseAgent Workflow YAML。

## 架构

```
intent_builder/
├── core/                    # 核心数据结构
│   ├── metaflow.py         # MetaFlow Pydantic models
│   └── __init__.py
├── generators/              # 生成器组件
│   ├── workflow_generator.py   # 主生成器
│   ├── prompt_builder.py       # 提示词构建
│   ├── llm_service.py          # LLM API 调用
│   └── __init__.py
├── validators/              # 验证器
│   ├── yaml_validator.py       # Workflow YAML 验证
│   └── __init__.py
└── tests/                   # 测试
    ├── test_generator.py       # 生成器测试
    └── __init__.py
```

## 使用方法

### 基本使用

```python
import asyncio
from intent_builder import MetaFlow, WorkflowGenerator

# 从 YAML 文件加载 MetaFlow
metaflow = MetaFlow.from_yaml_file("path/to/metaflow.yaml")

# 创建生成器
generator = WorkflowGenerator()

# 生成 Workflow YAML
workflow_yaml = await generator.generate(metaflow)

# 保存到文件
with open("output_workflow.yaml", "w") as f:
    f.write(workflow_yaml)
```

### 自定义配置

```python
from intent_builder.generators import WorkflowGenerator, LLMService, PromptBuilder
from intent_builder.validators import WorkflowYAMLValidator

# 自定义 LLM 服务（默认使用 Claude）
llm_service = LLMService(
    provider="anthropic",  # or "openai"
    model="claude-sonnet-4-20250514",
    temperature=0.0,
    max_tokens=8000
)

# 自定义提示词构建器
prompt_builder = PromptBuilder()

# 自定义验证器
validator = WorkflowYAMLValidator()

# 创建生成器
generator = WorkflowGenerator(
    llm_service=llm_service,
    prompt_builder=prompt_builder,
    validator=validator,
    max_retries=3
)

# 生成
workflow_yaml = await generator.generate(metaflow)
```

## 环境配置

需要配置 LLM API 密钥：

```bash
# Anthropic Claude
export ANTHROPIC_API_KEY="your-api-key"

# 或者 OpenAI
export OPENAI_API_KEY="your-api-key"
```

## 测试

### 运行组件测试

```bash
cd intent_builder
python tests/test_generator.py components
```

### 运行完整测试（需要 API key）

```bash
python tests/test_generator.py
```

这将使用 `docs/intent_builder/examples/coffee_collection_metaflow.yaml` 作为输入，生成完整的 workflow。

## 生成流程

1. **输入**: MetaFlow YAML（用户意图的中间表示）
2. **Prompt 构建**: PromptBuilder 构建包含规范、示例和转换规则的完整提示词
3. **LLM 生成**: LLMService 调用 LLM API 生成 Workflow YAML
4. **验证**: WorkflowYAMLValidator 验证生成的 YAML 是否合法
5. **重试**: 如果验证失败，将错误反馈加入提示词重试（最多 3 次）
6. **输出**: 有效的 Workflow YAML

## MetaFlow 格式

MetaFlow 包含用户意图的完整信息，包括：

- **task_description**: 任务描述
- **nodes**: 意图节点列表，每个节点包含：
  - intent_id, intent_name, intent_description: 意图的基本信息
  - operations: 操作列表（navigate, click, extract, store 等）
  - inputs/outputs: 显式的数据流定义
- **loop nodes**: 循环节点，包含 source, item_var, children

详细规范见：`docs/intent_builder/metaflow_specification.md`

## 生成策略

使用纯 LLM 生成方式：

- **优势**: 灵活性高，可以推断隐式数据流和变量管理
- **提示词设计**: 包含完整的 Workflow 规范、转换规则、示例
- **LLM 负责推断**:
  - 变量初始化和管理（init-vars, save-urls, append 等）
  - Agent 类型选择（tool_agent, scraper_agent, storage_agent）
  - extraction_method 选择（script vs llm）
  - Step 拆分（一个意图可能生成多个 step）
  - 完整数据流（变量引用、输入输出）

## 依赖

- **base_app**: 依赖 base_app.base_agent.core.schemas 中的 Workflow 定义
- **LLM Provider**: anthropic 或 openai SDK
- **Pydantic**: 数据验证
- **PyYAML**: YAML 解析

## 开发计划

当前实现为 MVP 版本，未来可能扩展：

- [ ] 支持更多 agent 类型
- [ ] 支持条件分支和复杂控制流
- [ ] 优化 prompt 模板
- [ ] 增加更多验证规则
- [ ] 支持增量生成和修改
