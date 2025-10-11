#!/usr/bin/env python3
"""
Generated Agent - 由AgentBuilder自动生成
可以独立运行的Agent实现
"""

import sys
import os
import asyncio
import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

# 添加BaseApp路径到系统路径
current_dir = Path(__file__).parent
base_app_path = current_dir.parent.parent / "base_app"
sys.path.insert(0, str(base_app_path))

# BaseAgent核心导入
from base_app.base_agent.core.base_agent import BaseAgent
from base_app.base_agent.core.schemas import AgentConfig, AgentResult

class Agent_Generated(BaseAgent):
    """
    自动生成的Agent
    
    需要的工具: ['browser_use']
    这些工具会通过config.tools自动注册到Agent中
    """
    def __init__(self, config: AgentConfig):
        super().__init__(config)  # BaseAgent会根据config.tools自动注册工具
        self.workflow = None
        self.workflow_name = "custom_workflow"
    
    async def initialize(self):
        """初始化Agent和工作流"""
        await super().initialize()  # 这里会初始化所有工具
        await self._setup_workflow()
    
    async def _setup_workflow(self):
        """设置工作流"""
        # 创建工作流构建器
        builder = self.create_workflow_builder("agentbuilder_workflow_build_58", "AgentBuilder自动生成的工作流，包含3个步骤")
        
        # 添加步骤 1: 用户意图分析
        builder.add_text_step(
            name="用户意图分析",
            instruction="使用意图识别模型分析用户输入，提取用户意图和相关语义上下文。",
            description="分析用户输入，识别具体意图和需要的处理方式。",
            inputs={'user_input': '{{user_input}}'},
            outputs={'intent_data': 'step1_output', 'context_metadata': 'step1_metadata'},
            constraints=['输入必须是文本或截图内容'],
            response_style="professional",
            max_length=500,
            timeout=30,
            retry_count=3,
        )
        
        # 添加步骤 2: 信息提取
        builder.add_text_step(
            name="信息提取",
            instruction="使用llm_extract工具从用户输入中提取会议时间和参与者信息。",
            description="从用户输入中提取会议时间和参与者信息。",
            inputs={'user_input': '{{step1_output}}'},
            outputs={'extracted_info': 'step2_output'},
            constraints=['必须准确提取会议时间格式', '参与者信息需包含姓名'],
            response_style="professional",
            max_length=150,
            timeout=30,
            retry_count=1,
        )
        
        # 添加步骤 3: 企业微信会议预约
        builder.add_tool_step(
            name="企业微信会议预约",
            instruction="使用企业微信的会议插件，根据提供的信息自动预约会议。",
            tools=['browser_use'],
            description="使用企业微信的会议插件，自动预约会议。",
            inputs={'meeting_details': '{{step2_output}}'},
            outputs={'booking_confirmation': 'step3_output'},
            confidence_threshold=0.8,
            timeout=60,
            retry_count=3,
        )
        
        # 构建工作流
        self.workflow = builder.build()
    
    async def execute(self, input_data: Any) -> AgentResult:
        """执行Agent"""
        if not self.workflow:
            await self._setup_workflow()
        
        # 运行工作流
        # 将input_data包装为字典格式，因为BaseAgent的run_workflow期望Dict[str, Any]
        workflow_input = {"user_input": input_data} if not isinstance(input_data, dict) else input_data
        result = await self.run_workflow(self.workflow, workflow_input)
        
        return AgentResult(
            success=True,
            data=result,
            agent_name=self.config.name,
            execution_time=0.0
        )

def main():
    parser = argparse.ArgumentParser(description="Generated Agent")
    parser.add_argument('--input', help='输入数据')
    parser.add_argument('--interactive', action='store_true', help='交互模式')
    parser.add_argument('--api-key', help='API密钥')
    parser.add_argument('--config', help='配置文件路径')
    
    args = parser.parse_args()
    
    # 加载配置
    config_file = Path(__file__).parent / "config.json"
    if config_file.exists() and not args.config:
        with open(config_file, 'r') as f:
            config_data = json.load(f)
            config = AgentConfig(
                name=config_data.get('name', 'Generated Agent'),
                llm_provider=config_data.get('llm_provider', 'openai'),
                llm_model=config_data.get('llm_model', 'gpt-4o'),
                api_key=args.api_key or config_data.get('api_key') or os.getenv('OPENAI_API_KEY'),
                tools=config_data.get('tools', ['browser_use'])  # 需要的工具: ['browser_use']
            )
    else:
        config = AgentConfig(
            name="Generated Agent",
            llm_provider="openai",
            llm_model="gpt-4o",
            api_key=args.api_key or os.getenv("OPENAI_API_KEY"),
            tools=['browser_use']  # 需要的工具: ['browser_use']
        )
    
    agent = Agent_Generated(config)
    
    if args.interactive:
        print("Agent 交互模式启动")
        while True:
            try:
                user_input = input("输入: ")
                if user_input.lower() in ['quit', 'exit']:
                    break
                agent_result = asyncio.run(agent.execute(user_input))
                print(f"结果: {agent_result}")
            except KeyboardInterrupt:
                break
    else:
        if args.input:
            agent_result = asyncio.run(agent.execute(args.input))
            # 使用model_dump而不是dict()，并处理datetime序列化
            result_dict = agent_result.model_dump() if hasattr(agent_result, 'model_dump') else agent_result.dict()
            print(json.dumps(result_dict, indent=2, ensure_ascii=False, default=str))
        else:
            print("请提供--input参数或使用--interactive模式")

if __name__ == "__main__":
    main()