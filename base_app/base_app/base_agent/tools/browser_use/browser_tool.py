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


class BrowserAction(BaseModel):
    """浏览器动作定义"""
    name: str
    description: str
    params_schema: Dict[str, Any]
    required_params: List[str]


class BrowserTool(BaseTool):
    """
    浏览器自动化工具
    支持通过自然语言描述执行复杂的浏览器操作
    """
    
    def __init__(self, config: Optional[BrowserConfig] = None):
        self.browser_config = config or BrowserConfig()
        super().__init__(self.browser_config)
        self.llm = None
        self.current_agent = None
        
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="browser_use",
            description="基于AI的浏览器自动化工具，支持自然语言驱动的网页操作",
            version="1.0.0",
            author="AgentCrafter",
            tags=["browser", "automation", "web", "ai"],
            category="automation"
        )
    
    def get_available_actions(self) -> List[str]:
        """获取支持的动作列表"""
        return [
            "navigate",
            "click",
            "fill_form", 
            "extract_data",
            "screenshot",
            "wait_for_element",
            "scroll",
            "execute_task",
            "get_page_info"
        ]
    
    def _get_action_schema(self, action: str) -> BrowserAction:
        """获取动作的详细定义"""
        actions = {
            "navigate": BrowserAction(
                name="navigate",
                description="导航到指定URL",
                params_schema={
                    "url": {"type": "string", "description": "目标URL"},
                    "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle"], "default": "load"}
                },
                required_params=["url"]
            ),
            "click": BrowserAction(
                name="click",
                description="点击页面元素",
                params_schema={
                    "selector": {"type": "string", "description": "CSS选择器或元素描述"},
                    "description": {"type": "string", "description": "元素的自然语言描述"},
                    "wait_timeout": {"type": "number", "default": 10000}
                },
                required_params=[]
            ),
            "fill_form": BrowserAction(
                name="fill_form",
                description="填写表单",
                params_schema={
                    "form_data": {"type": "object", "description": "表单数据字典"},
                    "form_selector": {"type": "string", "description": "表单选择器"},
                    "submit": {"type": "boolean", "default": False, "description": "是否提交表单"}
                },
                required_params=["form_data"]
            ),
            "extract_data": BrowserAction(
                name="extract_data",
                description="从页面提取数据",
                params_schema={
                    "target": {"type": "string", "description": "要提取的数据描述"},
                    "selectors": {"type": "array", "items": {"type": "string"}, "description": "CSS选择器列表"},
                    "format": {"type": "string", "enum": ["json", "text", "html"], "default": "json"}
                },
                required_params=["target"]
            ),
            "screenshot": BrowserAction(
                name="screenshot",
                description="截取页面截图",
                params_schema={
                    "full_page": {"type": "boolean", "default": False},
                    "selector": {"type": "string", "description": "截取特定元素"},
                    "filename": {"type": "string", "description": "保存文件名"}
                },
                required_params=[]
            ),
            "wait_for_element": BrowserAction(
                name="wait_for_element",
                description="等待元素出现",
                params_schema={
                    "selector": {"type": "string", "description": "CSS选择器"},
                    "description": {"type": "string", "description": "元素描述"},
                    "timeout": {"type": "number", "default": 10000},
                    "state": {"type": "string", "enum": ["attached", "detached", "visible", "hidden"], "default": "visible"}
                },
                required_params=[]
            ),
            "scroll": BrowserAction(
                name="scroll",
                description="滚动页面",
                params_schema={
                    "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "default": "down"},
                    "amount": {"type": "number", "description": "滚动距离(像素)", "default": 500},
                    "to_element": {"type": "string", "description": "滚动到指定元素"}
                },
                required_params=[]
            ),
            "execute_task": BrowserAction(
                name="execute_task",
                description="执行复杂的自然语言任务",
                params_schema={
                    "task": {"type": "string", "description": "任务描述"},
                    "context": {"type": "object", "description": "任务上下文信息"},
                    "max_steps": {"type": "number", "default": 20, "description": "最大执行步数"}
                },
                required_params=["task"]
            ),
            "get_page_info": BrowserAction(
                name="get_page_info",
                description="获取页面信息",
                params_schema={
                    "info_type": {"type": "string", "enum": ["title", "url", "html", "text", "cookies"], "default": "title"}
                },
                required_params=[]
            )
        }
        return actions.get(action)
    
    def get_schema(self, action: str) -> Dict[str, Any]:
        """获取动作的JSON Schema"""
        action_def = self._get_action_schema(action)
        if not action_def:
            return super().get_schema(action)
        
        return {
            "type": "object",
            "description": action_def.description,
            "properties": action_def.params_schema,
            "required": action_def.required_params
        }
    
    def _get_action_description(self, action: str) -> str:
        """获取动作描述"""
        action_def = self._get_action_schema(action)
        if action_def:
            return action_def.description
        return super()._get_action_description(action)
    
    def _get_action_examples(self, action: str) -> List[Dict[str, Any]]:
        """获取动作使用示例"""
        examples = {
            "navigate": [
                {
                    "description": "导航到百度首页",
                    "params": {"url": "https://www.baidu.com"}
                },
                {
                    "description": "导航到页面并等待DOM加载完成",
                    "params": {"url": "https://example.com", "wait_until": "domcontentloaded"}
                }
            ],
            "click": [
                {
                    "description": "点击搜索按钮",
                    "params": {"description": "search button"}
                },
                {
                    "description": "点击指定选择器的元素",
                    "params": {"selector": "#submit-btn"}
                }
            ],
            "fill_form": [
                {
                    "description": "填写登录表单",
                    "params": {
                        "form_data": {"username": "user123", "password": "pass123"},
                        "submit": True
                    }
                }
            ],
            "extract_data": [
                {
                    "description": "提取页面标题",
                    "params": {"target": "page title", "format": "text"}
                },
                {
                    "description": "提取商品列表",
                    "params": {
                        "target": "product information including name and price",
                        "selectors": [".product-item", ".product-name", ".product-price"],
                        "format": "json"
                    }
                }
            ],
            "screenshot": [
                {
                    "description": "截取当前页面截图",
                    "params": {"filename": "current_page.png"}
                },
                {
                    "description": "截取整页截图",
                    "params": {"full_page": True, "filename": "full_page.png"}
                }
            ],
            "execute_task": [
                {
                    "description": "搜索关键词",
                    "params": {"task": "在百度搜索'人工智能'并点击第一个结果"}
                },
                {
                    "description": "填写并提交表单",
                    "params": {
                        "task": "填写联系表单，姓名为张三，邮箱为zhangsan@example.com，然后提交",
                        "max_steps": 10
                    }
                }
            ]
        }
        return examples.get(action, [])
    
    def _get_required_params(self, action: str) -> List[str]:
        """获取动作必需参数"""
        action_def = self._get_action_schema(action)
        if action_def:
            return action_def.required_params
        return super()._get_required_params(action)
    
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
        action_def = self._get_action_schema(action)
        if not action_def:
            return False
        
        # 检查必需参数
        for required_param in action_def.required_params:
            if required_param not in params:
                logger.error(f"缺少必需参数: {required_param}")
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
            
            if action == "execute_task":
                result = await self._execute_task(params)
            elif action == "navigate":
                result = await self._navigate(params)
            elif action == "extract_data":
                result = await self._extract_data(params)
            elif action == "fill_form":
                result = await self._fill_form(params)
            elif action == "screenshot":
                result = await self._screenshot(params)
            elif action == "get_page_info":
                result = await self._get_page_info(params)
            else:
                # 其他动作通过自然语言任务执行
                task_description = self._action_to_task(action, params)
                result = await self._execute_task({"task": task_description})
            
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
    
    async def _execute_task(self, params: Dict[str, Any]) -> ToolResult:
        """执行自然语言任务"""
        task = params["task"]
        context = params.get("context", {})
        max_steps = params.get("max_steps", 20)
        
        try:
            # 确保LLM已初始化
            if self.llm is None:
                await self._initialize()
                if self.llm is None:
                    raise RuntimeError("LLM初始化失败")
            
            # 创建新的 Agent 实例
            self.current_agent = Agent(
                task=task,
                llm=self.llm,
                max_actions=max_steps
            )
            
            # 执行任务
            result = await self.current_agent.run()
            
            return ToolResult(
                success=True,
                data={
                    "result": str(result),
                    "task": task,
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
    
    async def _navigate(self, params: Dict[str, Any]) -> ToolResult:
        """导航到URL"""
        url = params["url"]
        task = f"Navigate to {url}"

        return await self._execute_task({"task": task})
    
    async def _extract_data(self, params: Dict[str, Any]) -> ToolResult:
        """提取数据"""
        target = params["target"]
        format_type = params.get("format", "json")
        
        task = f"Extract {target} from the current page and return it in {format_type} format"
        
        return await self._execute_task({"task": task})
    
    async def _fill_form(self, params: Dict[str, Any]) -> ToolResult:
        """填写表单"""
        form_data = params["form_data"]
        submit = params.get("submit", False)
        
        form_str = json.dumps(form_data, ensure_ascii=False)
        task = f"Fill the form with the following data: {form_str}"
        
        if submit:
            task += " and submit the form"
        
        return await self._execute_task({"task": task})
    
    async def _screenshot(self, params: Dict[str, Any]) -> ToolResult:
        """截取截图"""
        full_page = params.get("full_page", False)
        selector = params.get("selector")
        
        if selector:
            task = f"Take a screenshot of element: {selector}"
        elif full_page:
            task = "Take a full page screenshot"
        else:
            task = "Take a screenshot of the current viewport"
        
        return await self._execute_task({"task": task})
    
    async def _get_page_info(self, params: Dict[str, Any]) -> ToolResult:
        """获取页面信息"""
        info_type = params.get("info_type", "title")
        
        task = f"Get the current page {info_type}"
        
        return await self._execute_task({"task": task})
    
    def _action_to_task(self, action: str, params: Dict[str, Any]) -> str:
        """将动作转换为自然语言任务描述"""
        if action == "click":
            selector = params.get("selector", "")
            description = params.get("description", "")
            if description:
                return f"Click on {description}"
            elif selector:
                return f"Click on element with selector: {selector}"
            else:
                return "Click on the appropriate element"
        
        elif action == "wait_for_element":
            selector = params.get("selector", "")
            description = params.get("description", "")
            state = params.get("state", "visible")
            
            if description:
                return f"Wait for {description} to be {state}"
            elif selector:
                return f"Wait for element {selector} to be {state}"
            else:
                return f"Wait for element to be {state}"
        
        elif action == "scroll":
            direction = params.get("direction", "down")
            amount = params.get("amount", 500)
            to_element = params.get("to_element")
            
            if to_element:
                return f"Scroll to element: {to_element}"
            else:
                return f"Scroll {direction} by {amount} pixels"
        
        return f"Execute {action} with parameters: {params}"