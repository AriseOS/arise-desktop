# agentbuilder_workflow_build_58

AgentBuilder自动生成的工作流，包含3个步骤

## 概述

这是一个由AgentBuilder自动生成的智能Agent，基于BaseAgent框架构建。

## 功能特性

- 自然语言理解与生成
- 工具调用: browser_use


## 需要的工具

- **browser_use**: BaseAgent自动管理的工具


## 工作流步骤

1. **用户意图分析** (text): 分析用户输入，识别具体意图和需要的处理方式。
2. **信息提取** (text): 从用户输入中提取会议时间和参与者信息。
3. **企业微信会议预约** (tool): 使用企业微信的会议插件，自动预约会议。


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
from agent import Agent_58ae70e5
from base_app.base_agent.core.schemas import AgentConfig

async def main():
    config = AgentConfig(
        name="agentbuilder_workflow_build_58",
        llm_provider="openai",
        api_key="your-api-key"
    )
    
    agent = Agent_58ae70e5(config)
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

- **生成时间**: 2025-07-22 10:37:16
- **AgentBuilder版本**: 1.0.0
- **工作流复杂度**: 未评估

## 支持与反馈

如有问题或建议，请联系AgentBuilder开发团队。
