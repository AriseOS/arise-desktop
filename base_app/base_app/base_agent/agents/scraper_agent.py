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
    
    特点:
    - 使用 browser-use 库进行真实浏览器操作
    - 支持复杂的页面交互（点击、滚动、输入等）
    - 基于 DOM 结构和 LLM 生成智能提取脚本
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
                 extraction_method: str = 'script'):
        if not BROWSER_USE_AVAILABLE:
            raise ImportError("browser-use 库未安装，请先安装: pip install browser-use")
            
        if metadata is None:
            metadata = AgentMetadata(
                name="ScraperAgent",
                description="基于 browser-use 库的通用爬虫生成和执行代理"
            )
        super().__init__(metadata)
        
        # 配置参数
        self.debug_mode = debug_mode
        self.extraction_method = extraction_method
        
        # 验证提取方法
        if extraction_method not in ['script', 'llm']:
            raise ValueError(f"不支持的提取方法: {extraction_method}，请使用 'script' 或 'llm'")
        
        # 直接使用 browser-use 核心组件
        self.browser_session = browser_session or self._create_browser_session()
        self.controller = controller or Controller()
        self.dom_service = DomService(self.browser_session)
        
    def _create_browser_session(self) -> BrowserSession:
        import os
        from pathlib import Path
        
        # 使用共同的用户数据目录
        user_data_dir = os.path.abspath("./data/test_browser_data")
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        
        profile = BrowserProfile(
            headless=False,  
            user_data_dir=user_data_dir,  # 使用持久化用户数据
            keep_alive=True,  # 保持浏览器运行
            chrome_instance_id="scraper_agent",  # 唯一实例ID
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

    async def _analyze_page_structure(self) -> Dict:
        """使用 DomService 分析当前页面结构"""
        try:
            serialized_dom, enhanced_dom, timing = await self.dom_service.get_serialized_dom_tree()
            
            return {
                'serialized_dom': serialized_dom,
                'enhanced_dom': enhanced_dom,
                'timing_info': timing
            }
        except Exception as e:
            logger.error(f"页面结构分析失败: {e}")
            raise

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
            # Get current page DOM structure
            serialized_dom, enhanced_dom, timing = await self.dom_service.get_serialized_dom_tree()
            
            # 调试模式: 保存DOM结构
            if self.debug_mode:
                logger.info("=== DOM 结构分析 ===")
                dom_representation = serialized_dom.llm_representation()
                logger.info(f"DOM元素总数: {len(serialized_dom.selector_map) if hasattr(serialized_dom, 'selector_map') else '未知'}")
                
                # 保存DOM到文件
                import time
                debug_key = f"extraction_{self.extraction_method}_{int(time.time())}"
                await self._save_dom_to_file(dom_representation, debug_key)
            
            # 根据配置的提取方法调用对应函数
            if self.extraction_method == 'script':
                # 脚本模式：根据阶段决定是生成还是加载脚本
                return await self._extract_with_script(
                    serialized_dom, enhanced_dom, data_requirements, max_items, timeout, context, is_initialize
                )
            else:
                # LLM模式：直接使用大模型提取
                return await self._extract_with_llm(
                    serialized_dom, enhanced_dom, data_requirements, max_items, timeout
                )
                
        except Exception as e:
            logger.error(f"数据提取失败: {e}")
            return self._create_error_result(str(e))
    
    async def _extract_with_script(
        self,
        serialized_dom,
        enhanced_dom, 
        data_requirements: str,
        max_items: int,
        timeout: int,
        context: Optional[AgentContext] = None,
        is_initialize: bool = False
    ) -> Dict[str, Any]:
        """使用脚本模式提取数据"""
        try:
            script_key = self._generate_script_key(data_requirements)
            
            if is_initialize:
                # init阶段：生成脚本并存储到KV
                dom_analysis = {
                    'serialized_dom': serialized_dom,
                    'enhanced_dom': enhanced_dom
                }
                
                generated_script = await self._generate_extraction_script_with_llm(
                    dom_analysis, data_requirements, [], None
                )
                
                # 存储脚本到KV
                if context and context.memory_manager:
                    script_data = {
                        "script_content": generated_script,
                        "data_requirements": data_requirements,
                        "created_at": datetime.now().isoformat(),
                        "version": "4.0"
                    }
                    await context.memory_manager.set_data(script_key, script_data)
                    logger.info(f"脚本已存储到KV，键值: {script_key}")
                
                # 调试模式: 保存到文件
                if self.debug_mode:
                    logger.info("=== init阶段生成脚本 ===")
                    logger.info(f"脚本长度: {len(generated_script)} 字符")
                    await self._save_script_to_file(generated_script, script_key)
                
                # init阶段也执行一次测试
                return await self._execute_generated_script_direct(
                    generated_script, serialized_dom, enhanced_dom, max_items
                )
                
            else:
                # exec阶段：从KV获取脚本执行
                if context and context.memory_manager:
                    script_data = await context.memory_manager.get_data(script_key)
                    if script_data and 'script_content' in script_data:
                        generated_script = script_data['script_content']
                        logger.info(f"exec阶段从KV加载脚本，键值: {script_key}")
                        
                        return await self._execute_generated_script_direct(
                            generated_script, serialized_dom, enhanced_dom, max_items
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
        serialized_dom,
        enhanced_dom,
        data_requirements: str,
        max_items: int,
        timeout: int
    ) -> Dict[str, Any]:
        """使用大模型直接提取数据"""
        try:
            dom_text = serialized_dom.llm_representation()
            
            # 准备大模型提取的提示
            prompt = f"""
从以下HTML DOM结构中提取数据：

数据要求: {data_requirements}
最大数量: {max_items}

HTML DOM结构:
{dom_text}

请提取符合要求的数据，以JSON数组格式返回，每个对象包含要求的字段。
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
        enhanced_dom,
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
            result = execute_func(serialized_dom, enhanced_dom, max_items)
            return result
            
        except Exception as e:
            logger.error(f"脚本执行失败: {e}")
            return self._create_error_result(str(e))
    
    
    async def _generate_extraction_script_with_llm(self, 
                                                 dom_analysis: Dict, 
                                                 data_requirements: str,
                                                 interaction_steps: List[Dict],
                                                 example_data: Optional[str] = None) -> str:
        """Generate data extraction script using LLM - simplified version"""
        
        try:
            serialized_dom = dom_analysis['serialized_dom']
            dom_text = serialized_dom.llm_representation()
            
            prompt = f"""
基于以下DOM结构生成数据提取脚本：

数据要求: {data_requirements}

DOM结构:
{dom_text}

生成一个完整的Python函数，要求：
1. 函数名为 extract_data_from_page(serialized_dom, enhanced_dom)
2. 返回 List[Dict[str, Any]] 格式的数据
3. 包含错误处理
4. 只返回Python代码，不要其他解释

示例模板：
```python
def extract_data_from_page(serialized_dom, enhanced_dom):
    import re
    from typing import List, Dict, Any
    
    dom_text = serialized_dom.llm_representation()
    lines = dom_text.split('\\n')
    results = []
    
    # 实现数据提取逻辑
    
    return results
```
"""
            
            llm_provider = AnthropicProvider()
            response = await llm_provider.generate_response(
                system_prompt="你是Python代码生成专家，生成高效的数据提取脚本。只返回代码，不要解释。",
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

def execute_extraction(serialized_dom, enhanced_dom, max_items: int = 100):
    """Execute data extraction wrapper function"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Extract all available data
        all_data = extract_data_from_page(serialized_dom, enhanced_dom)
        
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
    
    def _generate_script_key(self, data_requirements: str) -> str:
        """生成脚本存储键"""
        content = f"script_{data_requirements}"
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
        import os
        from pathlib import Path
        
        debug_dir = Path("./data/debug")
        debug_dir.mkdir(parents=True, exist_ok=True)
        
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
        import os
        from pathlib import Path
        
        debug_dir = Path("./data/debug")
        debug_dir.mkdir(parents=True, exist_ok=True)
        
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