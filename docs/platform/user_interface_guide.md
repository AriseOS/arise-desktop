# BaseAgent 用户自定义接口使用指南

## 概述

BaseAgent 用户自定义接口提供了一套简单易用的 Python API，让用户能够轻松创建自定义工作流、Agent 和复杂的处理逻辑，而无需深入了解底层技术细节。

## 快速开始

### 1. 基本设置

```python
from base_app.base_agent.core.base_agent import BaseAgent
from base_app.base_agent.core.schemas import AgentConfig

# 创建配置
config = AgentConfig(
    name="我的智能助手",
    llm_provider="openai",  # 或 "anthropic"
    llm_model="gpt-4o",
    api_key="your-api-key-here"
)

# 创建Agent实例
agent = BaseAgent(config)
await agent.initialize()
```

### 2. 创建简单工作流

```python
# 方法1: 使用内置模板
workflow = agent.create_quick_qa_workflow("智能助手", "你是一个友好的AI助手")

# 方法2: 使用构建器
builder = agent.create_workflow_builder("问答流程", "用于回答用户问题")
builder.add_text_step("理解问题", "分析用户问题的意图")
builder.add_text_step("生成回答", "生成准确有用的回答")

workflow = builder.build()
```

### 3. 执行工作流

```python
result = await agent.run_custom_workflow(workflow, {
    "user_input": "什么是人工智能？"
})
print(result.final_result)
```

## 核心功能

### 1. 工作流构建器 (WorkflowBuilder)

工作流构建器提供链式 API 来创建复杂的工作流：

```python
builder = agent.create_workflow_builder("数据分析", "完整的数据分析流程")

# 添加文本处理步骤
builder.add_text_step(
    name="需求分析",
    instruction="分析用户的数据分析需求",
    response_style="professional",
    max_length=500
)

# 添加工具使用步骤
builder.add_tool_step(
    name="数据读取",
    instruction="读取和预处理数据",
    tools=["file_reader", "data_processor"],
    confidence_threshold=0.8
)

# 添加代码生成步骤
builder.add_code_step(
    name="分析代码",
    instruction="生成数据分析代码",
    language="python",
    libraries=["pandas", "numpy", "matplotlib"]
)

# 添加条件执行
builder.add_text_step(
    name="生成报告",
    instruction="生成分析报告",
    condition="{{step_results.数据读取.success}} == true"
)

workflow = builder.build()
```

#### 支持的步骤类型

- **`add_text_step()`**: 文本生成和处理
- **`add_tool_step()`**: 工具调用和执行
- **`add_code_step()`**: 代码生成和执行
- **`add_custom_step()`**: 自定义Agent步骤

#### 高级功能

```python
# 设置输入输出模式
builder.set_input_schema({
    "user_input": {"type": "string", "required": True},
    "context": {"type": "object", "required": False}
})

builder.set_output_schema({
    "result": {"type": "string", "description": "处理结果"},
    "confidence": {"type": "number", "description": "置信度"}
})

# 验证工作流
errors = builder.validate()
if errors:
    print(f"验证错误: {errors}")

# 获取工作流信息
print(f"步骤数: {builder.get_step_count()}")
print(f"步骤名称: {builder.get_step_names()}")
```

### 2. 自定义Agent

#### 创建自定义文本Agent

```python
# 创建专业翻译Agent
translator = agent.create_custom_text_agent(
    name="专业翻译员",
    system_prompt="你是一个专业的中英文翻译员，请提供准确、流畅的翻译。",
    response_style="professional",
    max_length=1000,
    temperature=0.3
)

# 注册Agent
agent.register_custom_agent(translator)

# 使用自定义Agent
builder.add_custom_step(
    name="翻译",
    agent_name="专业翻译员",
    instruction="翻译用户输入的文本"
)
```

#### 创建自定义工具Agent

```python
# 创建数据处理Agent
data_processor = agent.create_custom_tool_agent(
    name="数据处理专家",
    available_tools=["excel_reader", "csv_processor", "data_validator"],
    tool_selection_strategy="best_match",
    confidence_threshold=0.8,
    max_tool_calls=3
)

agent.register_custom_agent(data_processor)

# 使用自定义工具Agent
builder.add_custom_step(
    name="数据处理",
    agent_name="数据处理专家",
    instruction="处理用户上传的数据文件"
)
```

#### 创建自定义代码Agent

```python
# 创建Python分析师
code_analyst = agent.create_custom_code_agent(
    name="Python分析师",
    language="python",
    allowed_libraries=["pandas", "numpy", "matplotlib", "seaborn"],
    code_template="""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 数据分析代码
""",
    execution_timeout=60
)

agent.register_custom_agent(code_analyst)

# 使用自定义代码Agent
builder.add_custom_step(
    name="生成分析代码",
    agent_name="Python分析师",
    instruction="生成数据分析和可视化代码"
)
```

### 3. 条件执行

支持基于前一步结果的条件执行：

```python
# 意图分析
builder.add_text_step(
    name="意图分析",
    instruction="分析用户意图：chat/translate/code/search"
)

# 条件执行不同分支
builder.add_text_step(
    name="聊天处理",
    instruction="进行友好对话",
    condition="{{step_results.意图分析.answer}} == 'chat'"
)

builder.add_custom_step(
    name="翻译处理",
    agent_name="专业翻译员",
    instruction="翻译文本",
    condition="{{step_results.意图分析.answer}} == 'translate'"
)
```

### 4. 工作流管理

#### 导出和导入工作流

```python
# 导出工作流
json_str = agent.export_workflow(workflow, "my_workflow.json")

# 导入工作流
imported_workflow = agent.import_workflow(file_path="my_workflow.json")

# 从JSON字符串导入
imported_workflow = agent.import_workflow(json_str=json_str)
```

#### 工作流验证

```python
# 验证工作流配置
errors = agent.validate_workflow(workflow)
if errors:
    print(f"验证失败: {errors}")
else:
    print("工作流验证通过")
```

#### 获取Agent信息

```python
# 列出所有可用Agent
available_agents = agent.list_available_agents()
print(f"可用Agent: {available_agents}")

# 获取特定Agent信息
agent_info = agent.get_agent_info("text_agent")
print(f"Agent信息: {agent_info}")
```

## 实用示例

### 示例1: 智能客服工作流

```python
# 创建客服工作流
builder = agent.create_workflow_builder("智能客服", "自动客服系统")

# 创建专业客服Agent
customer_service = agent.create_custom_text_agent(
    name="客服专员",
    system_prompt="""你是一个专业的客服代表，请：
1. 友好地回答用户问题
2. 提供准确的信息
3. 如果不确定，请说明会转给人工客服
4. 保持专业和礼貌的态度""",
    response_style="friendly"
)
agent.register_custom_agent(customer_service)

# 构建工作流
builder.add_text_step(
    name="问题分类",
    instruction="分析用户问题类型：技术问题/账户问题/产品咨询/投诉"
).add_tool_step(
    name="搜索知识库",
    instruction="搜索相关的FAQ和知识库",
    tools=["knowledge_search", "faq_search"]
).add_custom_step(
    name="生成回复",
    agent_name="客服专员",
    instruction="基于问题分类和知识库搜索结果生成专业回复"
)

customer_service_workflow = builder.build()
```

### 示例2: 代码审查工作流

```python
# 创建代码审查工作流
builder = agent.create_workflow_builder("代码审查", "自动代码审查系统")

# 创建代码审查专家
code_reviewer = agent.create_custom_text_agent(
    name="代码审查专家",
    system_prompt="""你是一个资深的代码审查专家，请：
1. 检查代码的正确性和安全性
2. 提出改进建议
3. 评估代码质量
4. 指出潜在问题""",
    response_style="technical"
)
agent.register_custom_agent(code_reviewer)

# 构建工作流
builder.add_text_step(
    name="代码解析",
    instruction="分析代码结构和主要功能"
).add_custom_step(
    name="安全检查",
    agent_name="代码审查专家",
    instruction="检查代码安全性和潜在漏洞"
).add_custom_step(
    name="质量评估",
    agent_name="代码审查专家",
    instruction="评估代码质量和可维护性"
).add_text_step(
    name="生成报告",
    instruction="生成详细的代码审查报告",
    response_style="professional"
)

code_review_workflow = builder.build()
```

### 示例3: 文档生成工作流

```python
# 创建文档生成工作流
builder = agent.create_workflow_builder("文档生成", "自动生成技术文档")

# 创建技术写作专家
tech_writer = agent.create_custom_text_agent(
    name="技术写作专家",
    system_prompt="""你是一个专业的技术写作专家，请：
1. 创建清晰、结构化的技术文档
2. 使用适当的技术术语
3. 提供实用的示例
4. 确保文档的可读性""",
    response_style="professional"
)
agent.register_custom_agent(tech_writer)

# 构建工作流
builder.add_text_step(
    name="需求分析",
    instruction="分析文档需求和目标读者"
).add_custom_step(
    name="大纲生成",
    agent_name="技术写作专家",
    instruction="生成文档大纲和结构"
).add_custom_step(
    name="内容编写",
    agent_name="技术写作专家",
    instruction="编写详细的技术文档内容"
).add_text_step(
    name="格式化",
    instruction="格式化文档并添加必要的标记",
    response_style="technical"
)

doc_generation_workflow = builder.build()
```

## 最佳实践

### 1. Agent设计原则

- **单一职责**: 每个自定义Agent应专注于特定任务
- **清晰指令**: 系统提示词应该清晰、具体
- **适当温度**: 根据任务调整temperature参数
- **合理限制**: 设置适当的max_length和timeout

### 2. 工作流设计

- **逻辑清晰**: 步骤之间应有清晰的逻辑关系
- **错误处理**: 使用条件执行处理异常情况
- **模块化**: 将复杂流程分解为简单步骤
- **可测试**: 每个步骤都应该可以独立测试

### 3. 性能优化

- **并行执行**: 对于独立步骤，考虑并行执行
- **缓存结果**: 复用中间结果避免重复计算
- **合理超时**: 设置适当的超时时间
- **资源管理**: 注意内存和计算资源使用

### 4. 安全考虑

- **输入验证**: 始终验证用户输入
- **权限控制**: 限制Agent的访问权限
- **代码安全**: 对生成的代码进行安全检查
- **数据保护**: 保护敏感信息不被泄露

## 故障排除

### 常见问题

1. **Agent注册失败**
   - 检查Agent名称是否重复
   - 确保Agent实现了必要的接口
   - 验证系统提示词格式

2. **工作流验证失败**
   - 检查步骤名称是否重复
   - 确保引用的Agent存在
   - 验证条件表达式语法

3. **执行超时**
   - 增加timeout参数
   - 优化Agent逻辑
   - 检查网络连接

4. **内存不足**
   - 减少并行步骤数量
   - 优化数据处理逻辑
   - 增加系统内存

### 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 检查Agent状态
print(f"可用Agent: {agent.list_available_agents()}")
print(f"Agent信息: {agent.get_agent_info('agent_name')}")

# 验证工作流
errors = agent.validate_workflow(workflow)
if errors:
    print(f"验证错误: {errors}")

# 导出工作流检查配置
json_str = agent.export_workflow(workflow)
print(json_str)
```

## 更多资源

- [设计文档](baseagent_user_customization_design.md)
- [API参考](USER_INTERFACE_GUIDE.md)
- [示例代码](examples/user_interface_examples.py)
- [测试用例](test_user_interface.py)

## 贡献

欢迎贡献代码和建议！请查看项目的贡献指南。

## 许可证

本项目采用 MIT 许可证。