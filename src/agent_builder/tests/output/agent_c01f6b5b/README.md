# agentbuilder_workflow_build_c0

AgentBuilder自动生成的工作流，包含3个步骤

## 概述

这是一个由AgentBuilder自动生成的智能Agent，基于BaseAgent框架构建。

## 功能特性

- 自然语言理解与生成
- 工具调用: browser_use


## 需要的工具

- **browser_use**: BaseAgent自动管理的工具


## 工作流步骤

1. **收集Wiki活动数据** (tool): 使用browser_use工具自动导航到用户的Wiki页面，提取当天的活动数据。输入为Wiki URL，输出为活动数据的文本格式。
2. **生成工作报告** (text): 利用llm_extract工具对收集到的活动数据进行摘要和重组，生成格式化的工作报告。输入为活动数据文本，输出为报告文本。
3. **发送报告至微信** (tool): 通过调用微信API或使用browser_use工具模拟网页操作，将生成的报告发送给指定的领导。输入为报告文本，输出为发送成功的确认。


## 安装和使用

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API密钥

编辑代码中的API密钥配置：

设置环境变量：

```bash
export OPENAI_API_KEY="your-api-key-here"
```

或者编辑 config.json 文件中的 api_key 字段
```

### 3. 运行Agent

```bash
python agent.py --interactive
```

### 4. 编程方式使用

```python
import asyncio
from agent import Agent_c01f6b5b
from base_app.base_agent.core.schemas import AgentConfig

async def main():
    config = AgentConfig(
        name="agentbuilder_workflow_build_c0",
        llm_provider="openai",
        api_key="your-api-key"
    )
    
    agent = Agent_c01f6b5b(config)
    result = await agent.execute("你的输入")
    print(result.data)

if __name__ == "__main__":
    asyncio.run(main())
```

## 实现成本分析

低成本 - 主要使用现有功能

## 技术架构

- **基础框架**: BaseAgent
- **工作流引擎**: Agent Workflow Engine
- **LLM提供商**: openai
- **模型**: gpt-4o

## 文件说明

- `agent.py` - 主Agent实现代码
- `config.json` - Agent配置文件
- `workflow.yaml` - 工作流配置文件
- `metadata.json` - Agent元数据
- `requirements.txt` - Python依赖包
- `README.md` - 本说明文档

## 生成信息

- **生成时间**: 2025-07-22 10:11:18
- **AgentBuilder版本**: 1.0.0
- **工作流复杂度**: 未评估

## 支持与反馈

如有问题或建议，请联系AgentBuilder开发团队。
