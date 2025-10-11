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
    
    需要的工具: ['android_use', 'browser_use']
    这些工具会通过config.tools自动注册到Agent中
    """
    def __init__(self, config: AgentConfig):
        super().__init__(config)  # BaseAgent会根据config.tools自动注册工具
        self.workflow = None
        self.workflow_name = "agentbuilder_workflow_build_01"
    
    async def initialize(self):
        """初始化Agent和工作流"""
        await super().initialize()  # 这里会初始化所有工具
        await self._setup_workflow()
    
    async def _setup_workflow(self):
        """设置工作流"""
        # 创建工作流构建器
        builder = self.create_workflow_builder("agentbuilder_workflow_build_01", "AgentBuilder自动生成的工作流，包含3个步骤")
        
        # 步骤 1: 收集Wiki活动数据
        builder.add_tool_step(
            name="收集Wiki活动数据",
            instruction="自动化导航到用户的Wiki页面并提取每日活动数据。",
            tools=['browser_use'],
            description="使用browser_use工具自动化浏览器操作，导航到用户的Wiki页面，提取每日活动数据。",
            inputs={'user_question': '{{user_input}}'},
            outputs={'activity_data': 'step1_activity_data', 'metadata': 'step1_metadata'},
            constraints=['必须能够导航到用户指定的Wiki页面', '提取的数据应包含每日活动信息'],
            confidence_threshold=0.8,
            timeout=60,
            retry_count=3,
        )
        
        # 步骤 2: 生成工作报告
        builder.add_text_step(
            name="生成工作报告",
            instruction="分析结构化的活动数据，提取关键信息，生成简明的每日工作报告。",
            description="使用llm_extract工具，对收集的Wiki活动数据进行分析和摘要，生成每日工作报告。",
            inputs={'activity_data': '{{step1_activity_data}}'},
            outputs={'work_report': 'step2_output'},
            constraints=['使用llm_extract工具', '摘要长度适中', '涵盖多个分析维度'],
            response_style="professional",
            max_length=500,
            timeout=30,
            retry_count=3,
        )
        
        # 步骤 3: 通过微信发送报告
        builder.add_tool_step(
            name="通过微信发送报告",
            instruction="利用android_use工具，自动化地在微信上将报告发送给指定的联系人。",
            tools=['android_use'],
            description="使用android_use工具，通过自动化操作在微信上发送生成的工作报告给指定联系人。",
            inputs={'report_content': '{{step2_output}}'},
            outputs={'send_status': 'step3_send_status'},
            constraints=['必须在微信中找到指定联系人', '报告必须成功发送'],
            confidence_threshold=0.8,
            timeout=120,
            retry_count=3,
        )
        
        # 构建工作流
        self.workflow = builder.build()
    
    async def execute(self, input_data: Any) -> AgentResult:
        """执行Agent"""
        if not self.workflow:
            await self._setup_workflow()
        
        # 运行工作流
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
                tools=config_data.get('tools', ['android_use', 'browser_use'])
            )
    else:
        config = AgentConfig(
            name="Generated Agent",
            llm_provider="openai",
            llm_model="gpt-4o",
            api_key=args.api_key or os.getenv("OPENAI_API_KEY"),
            tools=['android_use', 'browser_use']
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
            result_dict = agent_result.model_dump() if hasattr(agent_result, 'model_dump') else agent_result.dict()
            print(json.dumps(result_dict, indent=2, ensure_ascii=False, default=str))
        else:
            print("请提供--input参数或使用--interactive模式")

if __name__ == "__main__":
    main()