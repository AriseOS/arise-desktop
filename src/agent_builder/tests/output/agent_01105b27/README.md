# agentbuilder_workflow_build_01

AgentBuilder自动生成的工作流，包含3个步骤

## 概述

这是一个由AgentBuilder自动生成的智能Agent，基于BaseAgent框架构建。

## 功能特性

- 工具调用: browser_use
- 自然语言理解与生成
- 工具调用: android_use


## 需要的工具

- **android_use**: BaseAgent自动管理的工具
- **browser_use**: BaseAgent自动管理的工具


## 工作流步骤

1. **收集Wiki活动数据** (tool): 使用browser_use工具自动化浏览器操作，导航到用户的Wiki页面，提取每日活动数据。
2. **生成工作报告** (text): 使用llm_extract工具，对收集的Wiki活动数据进行分析和摘要，生成每日工作报告。
3. **通过微信发送报告** (tool): 使用android_use工具，通过自动化操作在微信上发送生成的工作报告给指定联系人。


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
from agent import Agent_01105b27
from base_app.base_agent.core.schemas import AgentConfig

async def main():
    config = AgentConfig(
        name="agentbuilder_workflow_build_01",
        llm_provider="openai",
        api_key="your-api-key"
    )
    
    agent = Agent_01105b27(config)
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

- **生成时间**: 2025-07-22 00:22:10
- **AgentBuilder版本**: 1.0.0
- **工作流复杂度**: 未评估

## 支持与反馈

如有问题或建议，请联系AgentBuilder开发团队。
