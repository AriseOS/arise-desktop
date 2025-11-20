"""
Browser 工具实现
基于 browser-use 库的浏览器自动化工具
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from browser_use import Agent
from browser_use.llm import ChatOpenAI
from ..base_tool import BaseTool, ToolMetadata, ToolResult, ToolStatus, ToolConfig

try:
    from .enhanced_browser_use import SimpleBrowserUseTool
    SIMPLE_MONITORING_AVAILABLE = True
except ImportError:
    SIMPLE_MONITORING_AVAILABLE = False

logger = logging.getLogger(__name__)


class BrowserConfig(ToolConfig):
    """浏览器工具配置"""
    headless: bool = Field(default=True, description="是否无头模式")
    browser_type: str = Field(default="chromium", description="浏览器类型")
    viewport_width: int = Field(default=1920, description="视窗宽度")
    viewport_height: int = Field(default=1080, description="视窗高度")
    user_agent: Optional[str] = Field(default=None, description="用户代理")
    proxy: Optional[str] = Field(default=None, description="代理设置")

    # LLM 配置
    llm_model: str = Field(default="gpt-4o", description="LLM 模型")
    llm_api_key: Optional[str] = Field(default=None, description="LLM API Key")
    llm_base_url: Optional[str] = Field(default=None, description="LLM Base URL")



class AutonomousBrowserTool(BaseTool):
    """
    自主浏览器工具 (Autonomous Browser Tool)
    支持通过自然语言描述执行复杂的浏览器操作，具有自主探索能力
    """
    
    def __init__(self, config: Optional[BrowserConfig] = None):
        self.browser_config = config or BrowserConfig()
        super().__init__(self.browser_config)
        self.llm = None
        self.current_agent = None
        
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="autonomous_browser",
            description="基于AI的自主浏览器工具，支持自然语言驱动的网页操作和探索",
            version="1.0.0",
            author="AgentCrafter",
            tags=["browser", "automation", "web", "ai", "autonomous"],
            category="automation"
        )
    
    def get_available_actions(self) -> List[str]:
        """获取支持的动作列表"""
        return ["execute"]
    
    def _get_use_cases(self) -> List[str]:
        """工具适用场景"""
        return [
            "网页信息查询",
            "在线表单操作", 
            "电商数据抓取",
            "网站自动化测试",
            "天气股价等实时数据获取"
        ]
        
    def _get_api_description(self, action: str) -> str:
        """API具体描述"""
        if action == "execute":
            return "通过自然语言指令执行复杂的浏览器操作序列，包括导航、点击、填写表单、数据提取等"
        return f"不支持的操作: {action}"
        
    def _get_api_parameters(self, action: str) -> Dict[str, Any]:
        """API参数说明"""
        if action == "execute":
            return {
                "task": {
                    "type": "string",
                    "required": True,
                    "description": "自然语言任务描述，如'查询北京明天天气'"
                },
                "max_actions": {
                    "type": "integer", 
                    "required": False,
                    "default": 20,
                    "description": "最大执行步数"
                },
                "use_vision": {
                    "type": "boolean",
                    "required": False, 
                    "default": True,
                    "description": "是否使用视觉理解"
                }
            }
        return {}
        
    def _get_api_examples(self, action: str) -> List[Dict[str, Any]]:
        """API使用示例"""
        if action == "execute":
            return [
                {
                    "scenario": "天气查询",
                    "params": {
                        "task": "访问天气网站，查询巴厘岛明天天气并提供穿衣建议"
                    }
                },
                {
                    "scenario": "信息搜索",
                    "params": {
                        "task": "在百度搜索'Python机器学习教程'，点击第一个结果，提取文章标题和主要内容"
                    }
                },
                {
                    "scenario": "电商操作", 
                    "params": {
                        "task": "在淘宝搜索'iPhone 15'，找到评分最高的商品，提取商品信息",
                        "max_actions": 30
                    }
                }
            ]
        return []
    
    async def _initialize(self) -> bool:
        """初始化浏览器工具"""
        try:
            # 初始化 LLM
            if self.browser_config.llm_api_key:
                self.llm = ChatOpenAI(
                    model=self.browser_config.llm_model,
                    api_key=self.browser_config.llm_api_key,
                    base_url=self.browser_config.llm_base_url
                )
            else:
                # 使用环境变量中的API Key
                self.llm = ChatOpenAI(model=self.browser_config.llm_model)
            
            logger.info(f"Browser工具初始化成功，使用模型: {self.browser_config.llm_model}")
            return True
            
        except Exception as e:
            logger.error(f"Browser工具初始化失败: {e}")
            return False
    
    async def _cleanup(self) -> bool:
        """清理资源"""
        try:
            if self.current_agent:
                # browser-use Agent 会自动清理浏览器资源
                self.current_agent = None
            return True
        except Exception as e:
            logger.error(f"Browser工具清理失败: {e}")
            return False
    
    async def validate_params(self, action: str, params: Dict[str, Any]) -> bool:
        """验证参数"""
        if action != "execute":
            return False
        
        # 检查必需参数
        if "task" not in params:
            logger.error("缺少必需参数: task")
            return False
        
        return True
    
    async def execute(self, action: str, params: Dict[str, Any], **kwargs) -> ToolResult:
        """执行浏览器操作"""
        if not await self.validate_params(action, params):
            return ToolResult(
                success=False,
                message=f"参数验证失败: {action}",
                status=ToolStatus.ERROR
            )
        
        try:
            self.status = ToolStatus.RUNNING
            
            if action == "execute":
                result = await self._execute_browser_task(params)
            else:
                return ToolResult(
                    success=False,
                    message=f"不支持的操作: {action}",
                    status=ToolStatus.ERROR
                )
            
            self.status = ToolStatus.SUCCESS if result.success else ToolStatus.ERROR
            return result
            
        except Exception as e:
            logger.error(f"执行浏览器操作失败: {action}, 错误: {e}")
            self.status = ToolStatus.ERROR
            return ToolResult(
                success=False,
                message=f"执行失败: {str(e)}",
                status=ToolStatus.ERROR
            )
    
    async def _execute_browser_task(self, params: Dict[str, Any]) -> ToolResult:
        """执行浏览器自动化任务 - 直接对接 browser-use Agent"""
        task = params["task"]
        max_actions = params.get("max_actions", 20)
        use_vision = params.get("use_vision", True)
        context = params.get("context", {})

        try:
            # 确保LLM已初始化
            if self.llm is None:
                await self._initialize()
                if self.llm is None:
                    raise RuntimeError("LLM初始化失败")

            # 创建新的 browser-use Agent 实例，参数直接对齐
            self.current_agent = Agent(
                task=task,
                llm=self.llm,
                max_actions=max_actions,
                use_vision=use_vision
            )

            # 执行任务
            result = await self.current_agent.run()

            return ToolResult(
                success=True,
                data={
                    "result": str(result),
                    "task": task,
                    "max_actions": max_actions,
                    "use_vision": use_vision,
                    "context": context
                },
                message=f"任务执行完成: {task}",
                status=ToolStatus.SUCCESS
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            return ToolResult(
                success=False,
                message=f"任务执行失败: {str(e)}",
                status=ToolStatus.ERROR
            )
    
    @classmethod
    def create_with_monitoring(cls, **kwargs):
        """Create tool with user behavior monitoring"""
        if not SIMPLE_MONITORING_AVAILABLE:
            raise ImportError("Simple monitoring features not available")
        return SimpleBrowserUseTool(enable_behavior_monitoring=True, **kwargs)
    
