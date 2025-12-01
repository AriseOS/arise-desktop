# Intent Builder 快速开始

## 安装依赖

```bash
# 从项目根目录安装所有依赖
pip install -r requirements.txt

# 或者只安装 intent_builder 必需的依赖
pip install -r intent_builder/requirements.txt
```

## 配置 API Key

```bash
# 使用 Anthropic Claude (推荐)
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# 或者使用 OpenAI
export OPENAI_API_KEY="your-openai-api-key"
```

## 快速测试

### 1. 测试组件

测试各个组件是否正常工作：

```bash
PYTHONPATH=. python intent_builder/tests/test_generator.py components
```

这将测试：
- PromptBuilder 是否能正确构建提示词
- LLMService 是否能正确初始化
- WorkflowYAMLValidator 是否能正确验证 YAML

### 2. 生成 Workflow

使用示例 MetaFlow 生成完整的 Workflow：

```bash
PYTHONPATH=. python intent_builder/generate_workflow.py \
    docs/intent_builder/examples/coffee_collection_metaflow.yaml \
    output_workflow.yaml
```

这将：
1. 加载 coffee_collection_metaflow.yaml
2. 调用 LLM 生成 Workflow YAML
3. 验证生成的 YAML
4. 保存到 output_workflow.yaml
5. 在终端打印生成的内容

### 3. 完整测试（需要 API key）

运行完整的端到端测试：

```bash
PYTHONPATH=. python intent_builder/tests/test_generator.py
```

## 编程使用

### 基本使用

```python
import asyncio
from intent_builder import MetaFlow, WorkflowGenerator

async def main():
    # 从 YAML 文件加载 MetaFlow
    metaflow = MetaFlow.from_yaml_file("path/to/metaflow.yaml")

    # 创建生成器
    generator = WorkflowGenerator()

    # 生成 Workflow YAML
    workflow_yaml = await generator.generate(metaflow)

    # 保存到文件
    with open("output_workflow.yaml", "w") as f:
        f.write(workflow_yaml)

    print("Workflow generated successfully!")

asyncio.run(main())
```

### 自定义 LLM 服务

```python
from intent_builder.generators import LLMService, WorkflowGenerator

# 使用 Claude
llm_service = LLMService(
    provider="anthropic",
    model="claude-sonnet-4-20250514",
    temperature=0.0
)

# 或使用 GPT-4
llm_service = LLMService(
    provider="openai",
    model="gpt-4-turbo-preview",
    temperature=0.0
)

generator = WorkflowGenerator(llm_service=llm_service)
workflow_yaml = await generator.generate(metaflow)
```

### 自定义重试次数

```python
generator = WorkflowGenerator(max_retries=5)
workflow_yaml = await generator.generate(metaflow)
```

## 常见问题

### 1. ModuleNotFoundError: No module named 'intent_builder'

确保使用 `PYTHONPATH=.` 运行脚本：

```bash
PYTHONPATH=. python intent_builder/generate_workflow.py ...
```

### 2. ModuleNotFoundError: No module named 'base_app'

确保 base_app 目录存在且结构正确：

```
ami/
├── base_app/
│   └── base_app/
│       └── base_agent/
│           └── core/
│               └── schemas.py
└── intent_builder/
```

### 3. API key 未设置

确保环境变量已设置：

```bash
# 检查环境变量
echo $ANTHROPIC_API_KEY
echo $OPENAI_API_KEY
```

### 4. Pydantic 版本警告

如果看到 Pydantic 版本警告，确保使用 Pydantic v2：

```bash
pip install "pydantic>=2.0"
```

## 示例输出

成功运行后，你应该看到类似输出：

```
2025-10-07 17:00:00 - INFO - Loading MetaFlow from: docs/intent_builder/examples/coffee_collection_metaflow.yaml
2025-10-07 17:00:00 - INFO - Task: 采集咖啡商品信息
2025-10-07 17:00:00 - INFO - Nodes: 3
2025-10-07 17:00:00 - INFO - Starting workflow generation...
2025-10-07 17:00:00 - INFO - Initialized LLM service: anthropic/claude-sonnet-4-20250514
2025-10-07 17:00:01 - INFO - Generation attempt 1/3
2025-10-07 17:00:05 - INFO - Generated 5000 chars response
2025-10-07 17:00:05 - INFO - Workflow validation passed
2025-10-07 17:00:05 - INFO - Workflow generation successful
================================================================================
Generated Workflow:
================================================================================
apiVersion: "ami.io/v1"
kind: "Workflow"
metadata:
  name: "coffee-collection-workflow"
  ...
================================================================================
2025-10-07 17:00:05 - INFO - Saved to: output_workflow.yaml
```

## 下一步

- 查看生成的 workflow YAML 文件
- 尝试修改 MetaFlow 示例
- 创建你自己的 MetaFlow
- 阅读 `intent_builder/README.md` 了解更多细节
