"""
Autonomous Browser Agent - 自主浏览器 Agent
"""
import logging
from typing import Any, Dict

from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext, AgentInput, AgentOutput

logger = logging.getLogger(__name__)


class AutonomousBrowserAgent(BaseStepAgent):
    """
    自主浏览器 Agent

    这是一个专门用于自主浏览器操作的 Agent，它实际上是对 ToolAgent + AutonomousBrowserTool 的封装。
    在 Workflow 中使用 autonomous_browser_agent 类型时，会调用此 Agent。
    """

    INPUT_SCHEMA = InputSchema(
        description="Autonomous browser agent that can explore and interact with web pages using natural language instructions",
        fields={
            "task": FieldSchema(
                type="str",
                required=True,
                description="Task description in natural language"
            ),
            "max_actions": FieldSchema(
                type="int",
                required=False,
                default=20,
                description="Maximum number of actions the agent can take"
            ),
        },
        examples=[
            {
                "task": "Go to google.com and search for 'Python tutorials'",
                "max_actions": 10
            },
            {
                "task": "Navigate to the login page and fill in the credentials",
                "max_actions": 15
            }
        ]
    )

    def __init__(self):
        metadata = AgentMetadata(
            name="autonomous_browser_agent",
            description="自主浏览器 Agent，支持通过自然语言指令进行网页探索和操作",
            version="1.0.0",
            tags=["browser", "autonomous", "web"],
        )
        super().__init__(metadata)
        self.tool = None
        self.browser_session = None
        self.llm = None
        self.llm_model = None
        
    async def initialize(self, context: AgentContext) -> bool:
        """初始化 Agent"""
        try:
            import os
            from browser_use.llm import ChatAnthropic
            from ..tools.browser_use.no_cache_anthropic import NoCacheChatAnthropic

            # Get shared browser session from context
            session_info = await context.get_browser_session()
            self.browser_session = session_info.session
            logger.info(f"AutonomousBrowserAgent using shared browser session")

            # Get LLM config from context.agent_instance.provider
            llm_api_key = None
            self.llm_model = "claude-sonnet-4-5-20250929"

            if context.agent_instance and hasattr(context.agent_instance, 'provider'):
                provider = context.agent_instance.provider
                if hasattr(provider, 'api_key') and provider.api_key:
                    llm_api_key = provider.api_key
                    logger.info(f"AutonomousBrowserAgent got API key from provider")
                if hasattr(provider, 'model_name') and provider.model_name:
                    self.llm_model = provider.model_name
                    logger.info(f"AutonomousBrowserAgent using model: {self.llm_model}")
            else:
                logger.warning("AutonomousBrowserAgent: No provider in context, will use env var ANTHROPIC_API_KEY")

            # Check if using custom Anthropic proxy (which may have stricter cache_control limits)
            base_url = os.environ.get("ANTHROPIC_BASE_URL")
            use_no_cache = base_url and "tun.agenticos.net" in base_url

            if use_no_cache:
                logger.info(f"Detected custom Anthropic proxy: {base_url}")
                logger.info("Using NoCacheChatAnthropic to avoid cache_control limit issues")

            # Initialize LLM - use NoCacheChatAnthropic for custom proxy to avoid cache_control errors
            LLMClass = NoCacheChatAnthropic if use_no_cache else ChatAnthropic

            if llm_api_key:
                self.llm = LLMClass(model=self.llm_model, api_key=llm_api_key)
            else:
                self.llm = LLMClass(model=self.llm_model)

            logger.info(f"AutonomousBrowserAgent initialized with model: {self.llm_model}, LLM class: {LLMClass.__name__}")

            self.is_initialized = True
            return True
        except Exception as e:
            import traceback
            logger.error(f"AutonomousBrowserAgent initialization failed: {str(e)}")
            logger.error(traceback.format_exc())
            return False
            
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入"""
        if isinstance(input_data, (dict, AgentInput)):
            return True
        return False
        
    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """执行任务"""
        try:
            from browser_use import Agent

            # 解析输入
            task = ""
            max_actions = 20

            if isinstance(input_data, AgentInput):
                # Get task from data field (resolved_input from workflow)
                if input_data.data:
                    task = input_data.data.get("task", "")
                    max_actions = input_data.data.get("max_actions", 20)
            elif isinstance(input_data, dict):
                task = input_data.get("task", "")
                max_actions = input_data.get("max_actions", 20)

            logger.info(f"AutonomousBrowserAgent executing task: {task[:100] if task else 'EMPTY'}...")

            if not task:
                logger.error("Missing task description")
                return AgentOutput(
                    success=False,
                    message="Missing task description",
                    data={}
                )

            logger.info(f"AutonomousBrowserAgent calling browser-use Agent with max_steps={max_actions}")

            # Create browser-use Agent with shared browser session
            agent = Agent(
                task=task,
                llm=self.llm,
                browser_session=self.browser_session,
                use_vision=True
            )

            # Execute task with max_steps parameter
            logger.info("Starting browser-use Agent execution...")
            result = await agent.run(max_steps=max_actions)
            logger.info(f"browser-use Agent execution completed, result length: {len(str(result))}")

            return AgentOutput(
                success=True,
                data={
                    "result": str(result),
                    "task": task,
                    "max_actions": max_actions
                },
                message=f"Task completed: {task[:100]}"
            )

        except Exception as e:
            import traceback
            error_msg = f"AutonomousBrowserAgent execution failed: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return AgentOutput(
                success=False,
                message=error_msg,
                data={}
            )
            
    async def cleanup(self, context: AgentContext):
        """清理资源"""
        # Browser session is shared and managed by context, no need to cleanup here
        pass
