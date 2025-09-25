"""ScraperAgent - 基于 browser-use 库的通用爬虫生成代理"""
import asyncio
import json
import hashlib
import random
import logging
from typing import Any, Dict, Optional, Union, List
from datetime import datetime

from .base_agent import BaseStepAgent, AgentMetadata
from ..core.schemas import AgentContext
from ..providers.openai_provider import OpenAIProvider
from ..providers.anthropic_provider import AnthropicProvider

try:
    from browser_use import Tools
    from browser_use.browser.session import BrowserSession
    from browser_use.browser.profile import BrowserProfile
    from browser_use.dom.service import DomService
    from browser_use.tools.views import *
    from browser_use.agent.views import ActionResult, ActionModel
    BROWSER_USE_AVAILABLE = True
    # Backward compatibility
    Controller = Tools
except ImportError:
    BROWSER_USE_AVAILABLE = False
    Tools = None
    Controller = None
    BrowserSession = None
    BrowserProfile = None
    DomService = None
    ActionResult = None
    ActionModel = None

logger = logging.getLogger(__name__)


class ScraperAgent(BaseStepAgent):
    """
    基于 browser-use 库的爬虫生成代理
    
    两种工作模式:
    1. initialize模式: 使用 browser-use 分析样本页面，生成数据提取脚本
    2. execute模式: 执行生成的脚本进行数据提取
    
    两种提取方法:
    1. script模式: Plan-Generate-Exec模式，生成脚本并缓存
    2. llm模式: 直接使用LLM提取数据
    
    DOM配置选项:
    - dom_scope: 'partial'(可见DOM) | 'full'(完整DOM含隐藏元素)
    
    特点:
    - 使用 browser-use 库进行真实浏览器操作
    - 支持复杂的页面交互（点击、滚动、输入等）
    - 基于 DOM 结构和 LLM 生成智能提取脚本
    - 支持多种DOM视图和输出格式配置
    """
    
    SYSTEM_PROMPT = """你是专业的网页数据提取代码生成专家。基于 browser-use 库生成高效、稳定的数据提取脚本。

重要原则:
1. 使用 browser-use 的官方 API，不要自己封装
2. 根据元素的 index 进行交互和数据提取
3. 充分利用 DOM 结构信息生成稳定的选择器
4. 包含完整的异常处理
5. 只返回 Python 代码，不要其他说明文字"""
    
    def __init__(self,
                 metadata: Optional[AgentMetadata] = None,
                 browser_session: Optional[BrowserSession] = None,
                 controller: Optional[Controller] = None,
                 debug_mode: bool = False,
                 extraction_method: str = 'script',
                 dom_scope: str = 'partial',
                 config_service=None
):
        if not BROWSER_USE_AVAILABLE:
            raise ImportError("browser-use 库未安装，请先安装: pip install browser-use")

        if metadata is None:
            metadata = AgentMetadata(
                name="ScraperAgent",
                description="基于 browser-use 库的通用爬虫生成和执行代理"
            )
        super().__init__(metadata)

        # 保存配置服务
        self.config_service = config_service

        # 配置参数
        self.debug_mode = debug_mode
        self.extraction_method = extraction_method
        self.dom_scope = dom_scope

        # 验证提取方法
        if extraction_method not in ['script', 'llm']:
            raise ValueError(f"不支持的提取方法: {extraction_method}，请使用 'script' 或 'llm'")

        # 验证DOM范围
        if dom_scope not in ['partial', 'full']:
            raise ValueError(f"不支持的DOM范围: {dom_scope}，请使用 'partial' 或 'full'")


        # 直接使用 browser-use 核心组件
        self.browser_session = browser_session or self._create_browser_session()
        self.controller = controller or Controller()
        self.dom_service = DomService(self.browser_session)
        
    def _create_browser_session(self) -> BrowserSession:
        # 从配置获取用户数据目录
        if self.config_service:
            user_data_dir = str(self.config_service.get_path("data.browser_data"))
        else:
            raise ValueError("必须提供 config_service 来配置浏览器数据目录")

        profile = BrowserProfile(
            headless=False,
            user_data_dir=user_data_dir,  # 使用配置的用户数据目录
            keep_alive=True,  # 保持浏览器运行
        )
        return BrowserSession(browser_profile=profile)
    
    async def initialize(self, context: AgentContext) -> bool:
        # 启动浏览器会话
        try:
            await self.browser_session.start()
            self.is_initialized = True
            return True
        except Exception as e:
            logger.error(f"浏览器会话启动失败: {e}")
            return False
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if not isinstance(input_data, dict):
            return False
        
        mode = input_data.get('mode')
        if mode not in ['initialize', 'execute']:
            return False
        
        if mode == 'initialize':
            required_fields = ['sample_path', 'data_requirements']
            return all(field in input_data for field in required_fields)
        
        elif mode == 'execute':
            required_fields = ['target_path', 'data_requirements']
            return all(field in input_data for field in required_fields)
        
        return False
    
    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """执行代理任务"""
        if not self.is_initialized:
            raise RuntimeError("代理未初始化")
        
        mode = input_data.get('mode')
        
        if mode == 'initialize':
            return await self._handle_initialize(input_data, context)
        elif mode == 'execute':
            return await self._handle_execute(input_data, context)
        else:
            raise ValueError(f"不支持的模式: {mode}")
    
    async def _handle_initialize(self, input_data: Dict, context: AgentContext) -> Dict:
        """初始化模式: 访问样本页面并使用配置的方法提取数据"""
        sample_path = input_data['sample_path']
        data_requirements = input_data['data_requirements']
        interaction_steps = input_data.get('interaction_steps', [])
        
        try:
            # 执行页面导航和交互
            navigate_result = await self._navigate_to_pages(sample_path, interaction_steps)
            logger.info(f"Navigation result: {navigate_result}")
            
            if navigate_result.success is False:
                return self._create_response(
                    False, 'initialize', '页面导航失败',
                    error=navigate_result.error
                )
            
            # 获取DOM数据并调用对应的提取方法
            extraction_result = await self._extract_data_from_current_page(
                data_requirements, 
                max_items=10,  # 初始化阶段只测试提取少量数据
                timeout=30,
                context=context,
                is_initialize=True
            )
            
            # 返回结果
            if extraction_result["success"]:
                return self._create_response(
                    True, 'initialize', 
                    f'初始化成功，使用{self.extraction_method}模式提取了{extraction_result["total_count"]}条测试数据',
                    extraction_method=self.extraction_method,
                    test_data=extraction_result["data"],
                    total_count=extraction_result["total_count"]
                )
            else:
                return self._create_response(
                    False, 'initialize', f'初始化失败，{self.extraction_method}模式提取数据失败',
                    extraction_method=self.extraction_method,
                    error=extraction_result["error"]
                )
            
        except Exception as e:
            logger.error(f"Initialize 模式执行失败: {e}")
            return self._create_response(
                False, 'initialize', '脚本生成失败',
                error=str(e)
            )
    
    async def _navigate_to_pages(self, 
                               path: Union[str, List[str]], 
                               interaction_steps: List[Dict]) -> ActionResult:
        """Execute sequential page navigation in the same tab."""
        try:
            # Convert single path to list for unified processing
            urls = path if isinstance(path, list) else [path]
            last_result = None
            
            # Navigate through all URLs in the same tab
            for i, url in enumerate(urls):
                # Create ActionModel
                class GoToUrlActionModel(ActionModel):
                    go_to_url: GoToUrlAction | None = None
                
                # All navigation happens in the same tab
                action_data = {'go_to_url': GoToUrlAction(url=url, new_tab=False)}
                result = await self.controller.act(GoToUrlActionModel(**action_data), self.browser_session)
                
                # Check for explicit failure
                if result.success is False:
                    return result
                
                last_result = result
                
                # Add natural delay between navigations
                if i < len(urls) - 1:
                    await asyncio.sleep(random.uniform(3, 5))
            
            # Return the last result (which should have success=None for successful navigation)
            return last_result if last_result else ActionResult(extracted_content="No navigation performed")
                
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return ActionResult(success=False, error=str(e))

    async def _execute_interaction_step(self, step_config: Dict) -> ActionResult:
        """执行单个交互步骤"""
        try:
            action_type = step_config['action_type']
            parameters = step_config.get('parameters', {})
            
            if action_type == 'click':
                class ClickActionModel(ActionModel):
                    click_element_by_index: ClickElementAction | None = None
                
                action_data = {'click_element_by_index': ClickElementAction(
                    index=parameters['index'],
                    while_holding_ctrl=parameters.get('while_holding_ctrl', False)
                )}
                result = await self.controller.act(ClickActionModel(**action_data), self.browser_session)
                
            elif action_type == 'scroll':
                class ScrollActionModel(ActionModel):
                    scroll: ScrollAction | None = None
                
                action_data = {'scroll': ScrollAction(
                    down=parameters.get('down', True),
                    num_pages=parameters.get('num_pages', 1.0),
                    frame_element_index=parameters.get('frame_element_index')
                )}
                result = await self.controller.act(ScrollActionModel(**action_data), self.browser_session)
                
            elif action_type == 'input':
                class InputActionModel(ActionModel):
                    input_text: InputTextAction | None = None
                
                action_data = {'input_text': InputTextAction(
                    index=parameters['index'],
                    text=parameters['text'],
                    clear_existing=parameters.get('clear_existing', True)
                )}
                result = await self.controller.act(InputActionModel(**action_data), self.browser_session)
                
            elif action_type == 'wait':
                await asyncio.sleep(parameters.get('seconds', 2))
                return ActionResult(success=True)
            else:
                return ActionResult(success=False, error=f"不支持的交互类型: {action_type}")
            
            return result
        except Exception as e:
            logger.error(f"交互步骤执行失败: {e}")
            return ActionResult(success=False, error=str(e))

    async def _handle_execute(self, input_data: Dict, context: AgentContext) -> Dict:
        """执行模式: 访问目标页面并使用配置的方法提取数据"""
        target_path = input_data['target_path']
        data_requirements = input_data['data_requirements']
        interaction_steps = input_data.get('interaction_steps', [])
        
        try:
            # 提取执行参数
            options = input_data.get('options', {})
            max_items = options.get('max_items', 100)
            timeout = options.get('timeout', 90)
            
            # 导航到目标页面并执行交互
            navigate_result = await self._navigate_to_pages(target_path, interaction_steps)
            
            if navigate_result.success is False:
                return self._create_response(
                    False, 'execute', '无法访问目标页面',
                    error=f'页面导航失败: {navigate_result.error}'
                )
            
            # 获取DOM数据并调用对应的提取方法
            extraction_result = await self._extract_data_from_current_page(
                data_requirements, 
                max_items,
                timeout,
                context=context,
                is_initialize=False
            )
            
            # 返回执行结果
            if extraction_result["success"]:
                return self._create_response(
                    True, 'execute', 
                    f'成功提取{extraction_result["total_count"]}条数据，使用{self.extraction_method}模式',
                    extraction_method=self.extraction_method,
                    extracted_data=extraction_result["data"],
                    metadata={
                        'total_items': extraction_result["total_count"],
                        'target_path': target_path,
                        'extraction_method': self.extraction_method,
                        'execution_time': datetime.now().isoformat()
                    }
                )
            else:
                return self._create_response(
                    False, 'execute', f'数据提取失败，{self.extraction_method}模式',
                    extraction_method=self.extraction_method, 
                    error=extraction_result["error"]
                )
                
        except Exception as e:
            logger.error(f"Execute 模式执行失败: {e}")
            return self._create_response(
                False, 'execute', '数据提取失败',
                error=str(e)
            )
    
    async def _extract_data_from_current_page(
        self, 
        data_requirements: str, 
        max_items: int,
        timeout: int,
        context: Optional[AgentContext] = None,
        is_initialize: bool = False
    ) -> Dict[str, Any]:
        """从当前页面提取数据的统一入口"""
        
        try:
            # 根据配置决定DOM范围，初始化阶段强制使用partial
            effective_dom_scope = "partial" if is_initialize else self.dom_scope
            
            # 获取基础DOM
            serialized_dom, enhanced_dom, timing = await self.dom_service.get_serialized_dom_tree()
            
            # 使用新的DOM API
            from ..tools.browser_use.dom_extractor import extract_dom_dict, extract_llm_view, DOMExtractor
            
            extractor = DOMExtractor()
            # 根据配置选择目标DOM
            if effective_dom_scope == "full":
                target_dom, _ = extractor.serialize_accessible_elements_custom(
                    enhanced_dom, include_non_visible=True
                )
            else:
                target_dom, _ = extractor.serialize_accessible_elements_custom(
                    enhanced_dom, include_non_visible=False
                )
            
            # 转换为DOM字典结构
            dom_dict = extract_dom_dict(target_dom)
            llm_view = extract_llm_view(dom_dict)
            
            # 调试模式: 保存DOM结构
            if self.debug_mode:
                logger.info("=== DOM 结构分析 ===")
                logger.info(f"DOM范围: {effective_dom_scope}")
                logger.info(f"DOM元素总数: {len(target_dom.selector_map) if hasattr(target_dom, 'selector_map') else '未知'}")
                logger.info(f"有意义元素数: {len(json.loads(llm_view)) if llm_view != '[]' else 0}")
                
                # 保存DOM到文件
                import time
                debug_key = f"extraction_{self.extraction_method}_{effective_dom_scope}_{int(time.time())}"
                
                # 使用人类可读的JSON格式保存到文件
                dom_representation = json.dumps(dom_dict, indent=2, ensure_ascii=False)
                
                await self._save_dom_to_file(dom_representation, debug_key)
            
            # 根据配置的提取方法调用对应函数
            if self.extraction_method == 'script':
                return await self._extract_with_script(
                    target_dom, dom_dict, llm_view, data_requirements, max_items, timeout, context, is_initialize
                )
            else:
                return await self._extract_with_llm(
                    dom_dict, llm_view, data_requirements, max_items, timeout
                )
                
        except Exception as e:
            logger.error(f"数据提取失败: {e}")
            return self._create_error_result(str(e))
    
    async def _extract_with_script(
        self,
        target_dom,
        dom_dict: Dict,
        llm_view: str,
        data_requirements: Dict,  # 改为字典格式
        max_items: int,
        timeout: int,
        context: Optional[AgentContext] = None,
        is_initialize: bool = False
    ) -> Dict[str, Any]:
        """使用脚本模式提取数据"""
        try:
            # Generate script key including DOM configuration
            script_key = self._generate_script_key(data_requirements)
            
            if is_initialize:
                # init阶段：使用LLM视图生成脚本
                # 构建DOM分析数据
                dom_analysis = {
                    'serialized_dom': target_dom,
                    'dom_dict': dom_dict,
                    'llm_view': llm_view,
                    'dom_config': {
                        'dom_scope': self.dom_scope
                    }
                }
                
                generated_script = await self._generate_extraction_script_with_llm(
                    dom_analysis, data_requirements, [], None
                )
                
                # 存储脚本和配置到KV
                if context and context.memory_manager:
                    script_data = {
                        "script_content": generated_script,
                        "data_requirements": data_requirements,
                        "dom_config": {
                            "dom_scope": self.dom_scope
                        },
                        "created_at": datetime.now().isoformat(),
                        "version": "6.0"
                    }
                    await context.memory_manager.set_data(script_key, script_data)
                    logger.info(f"脚本已存储到KV，键值: {script_key}，配置: dom_scope={self.dom_scope}")
                
                # 调试模式: 保存到文件
                if self.debug_mode:
                    logger.info("=== init阶段生成脚本 ===")
                    logger.info(f"脚本长度: {len(generated_script)} 字符")
                    logger.info(f"DOM配置: dom_scope={self.dom_scope}")
                    await self._save_script_to_file(generated_script, script_key)
                
                # init阶段也执行一次测试
                return await self._execute_generated_script_direct(
                    generated_script, target_dom, dom_dict, max_items
                )
                
            else:
                # exec阶段：从KV获取脚本执行
                if context and context.memory_manager:
                    script_data = await context.memory_manager.get_data(script_key)
                    if script_data and 'script_content' in script_data:
                        generated_script = script_data['script_content']
                        stored_config = script_data.get('dom_config', {})
                        logger.info(f"exec阶段从KV加载脚本，键值: {script_key}")
                        logger.info(f"存储的配置: {stored_config}")
                        logger.info(f"当前配置: dom_scope={self.dom_scope}")
                        
                        return await self._execute_generated_script_direct(
                            generated_script, target_dom, dom_dict, max_items
                        )
                    else:
                        return self._create_error_result(f"未找到脚本: {script_key}，请先运行init阶段")
                else:
                    return self._create_error_result("无法访问KV存储")
            
        except Exception as e:
            logger.error(f"脚本模式提取失败: {e}")
            return self._create_error_result(str(e))
    
    async def _extract_with_llm(
        self,
        dom_dict: Dict,
        llm_view: str,
        data_requirements: Dict,  # 改为字典格式
        max_items: int,
        timeout: int
    ) -> Dict[str, Any]:
        """使用大模型直接提取数据"""
        try:
            # 使用LLM视图作为DOM文本
            dom_text = llm_view
            
            # 解析新的data_requirements格式
            user_description = data_requirements.get('user_description', '')
            output_format = data_requirements.get('output_format', {})
            sample_data = data_requirements.get('sample_data', [])
            
            # 构建字段说明
            fields_description = ""
            for field_name, field_desc in output_format.items():
                fields_description += f"- {field_name}: {field_desc}\n"
            
            # 构建样例说明
            sample_description = ""
            if sample_data and len(sample_data) > 0:
                sample_description = f"\n\n参考样例数据：\n{json.dumps(sample_data, indent=2, ensure_ascii=False)}"
            
            # 准备大模型提取的提示
            prompt = f"""
从以下HTML DOM结构中提取数据：

用户需求：{user_description}

输出字段说明：
{fields_description}
最大数量: {max_items}
DOM范围: {self.dom_scope}{sample_description}

HTML DOM结构（简化视图）:
{dom_text}

请严格按照输出字段说明提取数据，以JSON数组格式返回。每个对象包含指定的字段。
只返回JSON数组，不要其他文字。
"""
            
            llm_provider = AnthropicProvider()
            response = await llm_provider.generate_response(
                system_prompt="你是数据提取专家，从HTML中提取结构化数据并返回有效的JSON格式。",
                user_prompt=prompt
            )
            
            # 解析JSON响应
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                try:
                    extracted_data = json.loads(json_match.group())
                    if isinstance(extracted_data, list):
                        limited_data = extracted_data[:max_items] if max_items > 0 else extracted_data
                        return {
                            "success": True,
                            "data": limited_data,
                            "total_count": len(limited_data),
                            "dom_config": {
                                "dom_scope": self.dom_scope
                            },
                            "error": None
                        }
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {e}")
                    
            # 备用方案：尝试解析整个响应
            try:
                extracted_data = json.loads(response.strip())
                if isinstance(extracted_data, list):
                    limited_data = extracted_data[:max_items] if max_items > 0 else extracted_data
                    return {
                        "success": True,
                        "data": limited_data,
                        "total_count": len(limited_data),
                        "dom_config": {
                            "dom_scope": self.dom_scope
                        },
                        "error": None
                    }
            except json.JSONDecodeError:
                pass
                
            return self._create_error_result("LLM未返回有效的JSON格式")
            
        except Exception as e:
            logger.error(f"LLM模式提取失败: {e}")
            return self._create_error_result(str(e))
    
    async def _execute_generated_script_direct(
        self,
        script_content: str,
        serialized_dom,
        dom_dict: Dict,
        max_items: int
    ) -> Dict[str, Any]:
        """直接执行生成的脚本，使用提供的DOM数据"""
        
        try:
            # 准备脚本执行环境
            execution_env = {
                'max_items': max_items,
                # 导入必要的模块
                'json': json,
                'logging': logging,
                'logger': logging.getLogger(__name__),
                'List': List,
                'Dict': Dict,
                'Any': Any,
            }
            
            # 执行脚本
            exec(script_content, execution_env, execution_env)
            
            # 获取执行函数
            execute_func = execution_env.get('execute_extraction')
            if not execute_func:
                return self._create_error_result("脚本缺少 execute_extraction 函数")
            
            # 使用提供的DOM数据执行提取
            result = execute_func(serialized_dom, dom_dict, max_items)
            return result
            
        except Exception as e:
            logger.error(f"脚本执行失败: {e}")
            return self._create_error_result(str(e))
    
    
    async def _generate_extraction_script_with_llm(self, 
                                                 dom_analysis: Dict, 
                                                 data_requirements: Dict,
                                                 interaction_steps: List[Dict],
                                                 example_data: Optional[str] = None) -> str:
        """Generate data extraction script using LLM with enhanced strategy guidance"""
        
        try:
            llm_view = dom_analysis['llm_view']
            
            # Parse data_requirements format
            user_description = data_requirements.get('user_description', '')
            output_format = data_requirements.get('output_format', {})
            sample_data = data_requirements.get('sample_data', [])
            
            # Build field descriptions
            fields_description = ""
            for field_name, field_desc in output_format.items():
                fields_description += f"- {field_name}: {field_desc}\n"
            
            # Build sample descriptions
            sample_description = ""
            if sample_data and len(sample_data) > 0:
                sample_description = f"\n\n参考样例数据，用户给出的当前页面期望的结果：\n{json.dumps(sample_data, indent=2, ensure_ascii=False)}"
            
            # Simplified scraper prompt - clear instructions with minimal examples
            prompt = f"""
## 第一步：理解DOM遍历
DOM是嵌套字典结构，每个元素包含：
- tag: HTML标签名
- text: 文本内容
- class: CSS类名 
- href: 链接地址
- structural_path: 结构化路径（如 html>body>div.container>h1.title）
- xpath: XPath路径
- children: 子元素数组

遍历方法：递归访问 node.get('children', [])

## 第二步：任务分析和策略选择
判断任务类型：
- **精准提取**：提取特定字段（如商品详情页的标题、价格）
- **模式提取**：提取重复数据（如搜索结果列表、商品列表）

定位策略（优先级）：
1. **Class定位**（首选）- 通过CSS类名，灵活适应单个/多个元素
2. **Structural Path定位** - 结构路径精确定位
3. **内容特征定位** - 通过href/text等内容匹配

**跨DOM数据提取策略**：当数据分散在多个相邻元素中时：
1. 先定位到任意一个目标数据元素（通过class或内容）
2. 向上查找该元素的父容器
3. 遍历父容器的所有子元素，收集并组合数据

关键函数示例：
```python
def find_parent_container(node, target_level=1):
    # 根据structural_path向上查找父容器
    path = node.get('structural_path', '')
    parts = path.split('>')
    if len(parts) > target_level:
        parent_path = '>'.join(parts[:-target_level])
        return find_by_path(dom_dict, parent_path)
    return None

def collect_scattered_data(container_node):
    # 在容器内收集所有子元素的文本
    texts = []
    if container_node and 'children' in container_node:
        for child in container_node.get('children', []):
            if isinstance(child, dict):
                text = child.get('text', '').strip()
                if text:
                    texts.append(text)
    return ''.join(texts)
```

## 第三步：理解具体需求
用户需求：{user_description}

输出字段说明：
{fields_description}{sample_description}

**重要**：这是样例页面，生成的脚本要能适用于内容不同但结构相似的其他页面。

## DOM结构：
{llm_view}

## 要求：
请生成 extract_data_from_page(serialized_dom, dom_dict) 函数：
- 返回: List[Dict[str, Any]]
- 包含错误处理
- 只返回Python代码，不要解释文字
- 根据DOM结构和用户需求选择最合适的策略
"""
            llm_provider = AnthropicProvider()
            response = await llm_provider.generate_response(
                system_prompt="""你是网页数据提取专家。根据提供的三步指导，分析DOM结构生成提取脚本。优先使用Class定位，确保跨页面兼容性。只返回Python代码，不要解释。""",
                user_prompt=prompt
            )
            
            return self._extract_and_wrap_code(response)
            
        except Exception as e:
            logger.error(f"LLM script generation failed: {e}")
            raise Exception(f"LLM script generation failed: {e}")
    
    def _extract_and_wrap_code(self, response: str) -> str:
        """提取并包装数据提取代码"""
        # 提取代码块
        if "```python" in response:
            start = response.find("```python") + 9
            end = response.find("```", start)
            code = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            code = response[start:end].strip()
        else:
            code = response.strip()
        
        # 包装执行结构
        return f'''
import json
import logging
from typing import List, Dict, Any

{code}

def execute_extraction(serialized_dom, dom_dict, max_items: int = 100):
    """Execute data extraction wrapper function"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Extract all available data
        all_data = extract_data_from_page(serialized_dom, dom_dict)
        
        # Apply quantity limit at wrapper level
        if isinstance(all_data, list):
            limited_data = all_data[:max_items] if max_items > 0 else all_data
            return {{
                "success": True,
                "data": limited_data,
                "total_count": len(limited_data),
                "error": None
            }}
        else:
            return {{
                "success": True,
                "data": all_data,
                "total_count": 1 if all_data else 0,
                "error": None
            }}
    except Exception as e:
        logger.error("Data extraction failed: " + str(e))
        return {{
            "success": False,
            "data": [],
            "total_count": 0,
            "error": str(e)
        }}
'''
    
    async def _execute_generated_script(
        self, 
        script_content: str, 
        max_items: int,
        timeout: int
    ) -> Dict[str, Any]:
        """Execute generated DOM extraction script"""
        
        try:
            # Get current page DOM structure
            serialized_dom, enhanced_dom, timing = await self.dom_service.get_serialized_dom_tree()
            
            # Prepare script execution environment
            execution_env = {
                'max_items': max_items,
                'timeout': timeout,
                # Import necessary modules
                'json': json,
                'logging': logging,
                'logger': logging.getLogger(__name__),  # Provide logger instance
                'List': List,
                'Dict': Dict,
                'Any': Any,
            }
            
            # Execute the script
            exec(script_content, execution_env, execution_env)
            
            # Get execution function
            execute_func = execution_env.get('execute_extraction')
            if not execute_func:
                return self._create_error_result("Script missing execute_extraction function")
            
            # Execute data extraction with DOM
            result = execute_func(serialized_dom, enhanced_dom, max_items)
            return result
            
        except Exception as e:
            logger.error(f"Script execution failed: {e}")
            return self._create_error_result(str(e))
    
    def _generate_script_key(self, data_requirements: Dict) -> str:
        """Generate script storage key with DOM configuration"""
        # 使用用户描述和字段名生成key
        user_desc = data_requirements.get('user_description', '')
        fields = list(data_requirements.get('output_format', {}).keys())
        content = f"script_{user_desc}_{','.join(fields)}_{self.dom_scope}"
        hash_suffix = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"scraper_script_{hash_suffix}"
    
    def _create_error_result(self, error_msg: str) -> Dict[str, Any]:
        return {
            "success": False,
            "data": [],
            "total_count": 0,
            "error": error_msg
        }
    
    def _create_response(self, success: bool, mode: str, message: str = "", **kwargs) -> Dict[str, Any]:
        response = {
            'success': success,
            'mode': mode,
            'message': message
        }
        response.update(kwargs)
        return response
    
    async def _save_dom_to_file(self, dom_content: str, script_key: str) -> None:
        """保存DOM内容到文件用于调试"""
        if not self.config_service:
            logger.warning("无法保存DOM文件: 缺少配置服务")
            return

        debug_dir = self.config_service.get_path("data.debug")
        
        dom_file = debug_dir / f"{script_key}_dom.txt"
        try:
            with open(dom_file, 'w', encoding='utf-8') as f:
                f.write(f"=== DOM 结构 ({script_key}) ===\n")
                f.write(f"生成时间: {datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                f.write(dom_content)
            logger.info(f"DOM结构已保存到: {dom_file}")
        except Exception as e:
            logger.warning(f"保存DOM文件失败: {e}")
    
    async def _save_script_to_file(self, script_content: str, script_key: str) -> None:
        """保存生成的脚本到文件用于调试"""
        if not self.config_service:
            logger.warning("无法保存脚本文件: 缺少配置服务")
            return

        debug_dir = self.config_service.get_path("data.debug")
        
        script_file = debug_dir / f"{script_key}_script.py"
        try:
            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(f"# 生成的脚本 ({script_key})\n")
                f.write(f"# 生成时间: {datetime.now().isoformat()}\n")
                f.write("#" + "=" * 50 + "\n\n")
                f.write(script_content)
            logger.info(f"生成的脚本已保存到: {script_file}")
        except Exception as e:
            logger.warning(f"保存脚本文件失败: {e}")
    
