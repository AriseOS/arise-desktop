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
from common.llm import OpenAIProvider, AnthropicProvider

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
    基于 browser-use 库的爬虫代理

    提取方法:
    1. script模式: 自动生成并缓存脚本，复用执行（支持 partial/full DOM）
    2. llm模式: 直接使用LLM提取数据（仅支持 partial DOM）

    特点:
    - 使用 browser-use 库进行真实浏览器操作
    - 支持复杂的页面交互（点击、滚动、输入等）
    - script模式自动检查KV缓存，无需手动区分初始化/执行阶段
    """
    
    SYSTEM_PROMPT = """你是网页数据提取专家。根据提供的三步指导，分析DOM结构生成提取脚本。只返回Python代码，不要解释。"""
    
    def __init__(self,
                 config_service=None,
                 metadata: Optional[AgentMetadata] = None,
                 extraction_method: str = 'llm',  # 默认值
                 dom_scope: str = 'partial',      # 默认值
                 debug_mode: bool = False         # 默认值
):
        """初始化，保留默认配置，运行时可覆盖

        Args:
            config_service: 配置服务（用于获取路径等）
            metadata: Agent元数据
            extraction_method: 默认提取方法 ('script' or 'llm')
            dom_scope: 默认DOM范围 ('partial' or 'full')
            debug_mode: 默认调试模式
        """
        if not BROWSER_USE_AVAILABLE:
            raise ImportError("browser-use 库未安装，请先安装: pip install browser-use")

        if metadata is None:
            metadata = AgentMetadata(
                name="scraper_agent",
                description="基于 browser-use 库的通用爬虫生成和执行代理"
            )
        super().__init__(metadata)

        # 保存配置服务
        self.config_service = config_service

        # 默认配置（运行时可覆盖）
        self.extraction_method = extraction_method
        self.dom_scope = dom_scope
        self.debug_mode = debug_mode

        # 会话管理相关
        self._session_manager = None
        self._session_id = None
        self._is_shared_session = False

        # browser-use 组件将在initialize时设置
        self.browser_session = None
        self.controller = None

        # Provider will be set in initialize
        self.provider = None

    async def initialize(self, context: AgentContext) -> bool:
        """初始化Agent，从context获取浏览器会话和provider"""
        try:
            # 从context获取浏览器会话（懒加载）
            session_info = await context.get_browser_session()

            # 设置browser-use组件
            self.browser_session = session_info.session
            self.controller = session_info.controller

            # Get provider from context.agent_instance (BaseAgent)
            if context.agent_instance and hasattr(context.agent_instance, 'provider'):
                self.provider = context.agent_instance.provider
                logger.info(f"ScraperAgent got provider from BaseAgent: {type(self.provider).__name__}")
            else:
                logger.warning("ScraperAgent: No provider available from context, will fail if LLM is needed")

            # 标记已初始化
            self.is_initialized = True

            logger.info(f"ScraperAgent初始化成功，使用workflow {context.workflow_id} 的共享会话")
            return True

        except Exception as e:
            logger.error(f"ScraperAgent初始化失败: {e}")
            return False

    def _parse_runtime_config(self, input_data: Dict) -> Dict:
        """解析运行时配置

        Args:
            input_data: 输入数据字典

        Returns:
            配置字典，包含extraction_method, dom_scope, debug_mode等
        """
        config = {}

        # 提取配置参数（支持从顶层或options中获取）
        options = input_data.get('options', {})

        # extraction_method - 默认使用 llm 避免 memory 依赖
        config['extraction_method'] = (
            input_data.get('extraction_method') or
            options.get('extraction_method') or
            'llm'
        )

        # dom_scope - 默认 partial
        config['dom_scope'] = (
            input_data.get('dom_scope') or
            options.get('dom_scope') or
            'partial'
        )

        # debug_mode - 默认 False
        config['debug_mode'] = (
            input_data.get('debug_mode') or
            options.get('debug_mode') or
            False
        )

        # max_items - 默认为 0 表示无限制（提取全部）
        # 只有当用户明确指定数量时才设置限制
        max_items_raw = input_data.get('max_items') or options.get('max_items')
        
        if max_items_raw is not None:
            # 强制转换为整数，防止变量替换失败导致字符串传入
            try:
                config['max_items'] = int(max_items_raw)
            except (ValueError, TypeError):
                logger.warning(f"max_items 转换失败: {max_items_raw}，将提取全部数据")
                config['max_items'] = 0
        else:
            # 用户未指定，默认提取全部
            config['max_items'] = 0

        config['timeout'] = (
            input_data.get('timeout') or
            options.get('timeout') or
            30
        )

        # 验证配置值
        if config['extraction_method'] not in ['script', 'llm']:
            raise ValueError(f"不支持的提取方法: {config['extraction_method']}，请使用 'script' 或 'llm'")

        # LLM 模式只支持 partial DOM
        if config['extraction_method'] == 'llm' and config['dom_scope'] != 'partial':
            logger.warning(f"LLM模式只支持partial DOM，已自动调整")
            config['dom_scope'] = 'partial'

        if config['dom_scope'] not in ['partial', 'full']:
            raise ValueError(f"不支持的DOM范围: {config['dom_scope']}，请使用 'partial' 或 'full'")

        logger.debug(f"运行时配置: {config}")
        return config
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        # Handle AgentInput type from workflow engine
        from ..core.schemas import AgentInput

        if isinstance(input_data, AgentInput):
            actual_data = input_data.data
        elif isinstance(input_data, dict):
            actual_data = input_data
        else:
            return False

        # 必需字段
        required_fields = ['target_path', 'data_requirements']
        return all(field in actual_data for field in required_fields)
    
    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """执行代理任务"""
        if not self.is_initialized:
            raise RuntimeError("代理未初始化")

        # Handle AgentInput type from workflow engine
        from ..core.schemas import AgentInput, AgentOutput

        if isinstance(input_data, AgentInput):
            actual_data = input_data.data
        else:
            actual_data = input_data

        # 从输入数据中提取配置（运行时决定所有行为）
        config = self._parse_runtime_config(actual_data)

        # 运行时覆盖实例变量
        self.extraction_method = config['extraction_method']
        self.dom_scope = config['dom_scope']
        self.debug_mode = config['debug_mode']

        # 执行数据提取
        result = await self._handle_scrape(actual_data, context, config)

        # Wrap result in AgentOutput for workflow engine
        if isinstance(input_data, AgentInput):
            return AgentOutput(
                success=result.get('success', False),
                data=result,
                message=result.get('message', '')
            )
        else:
            return result


    async def _handle_scrape(self, input_data: Dict, context: AgentContext, config: Dict) -> Dict:
        """统一的数据提取处理"""
        target_path = input_data['target_path']
        data_requirements = input_data['data_requirements']
        interaction_steps = input_data.get('interaction_steps', [])

        try:
            # 使用config中的参数
            max_items = config['max_items']
            timeout = config['timeout']

            # 导航到目标页面并执行交互
            navigate_result = await self._navigate_to_pages(target_path, interaction_steps)

            if navigate_result.success is False:
                return self._create_response(
                    False,
                    f'页面导航失败: {navigate_result.error}'
                )

            # 提取数据
            extraction_result = await self._extract_data_from_current_page(
                data_requirements,
                max_items,
                timeout,
                context=context,
                config=config
            )

            # 返回结果
            if extraction_result["success"]:
                # Log extraction results in one line
                data_preview = extraction_result["data"][:2] if extraction_result["total_count"] > 0 else []
                preview_str = f"{data_preview[0]}" if len(data_preview) > 0 else "[]"
                logger.info(f"✅ Extracted {extraction_result['total_count']} items using {config['extraction_method']} | Preview: {preview_str}")

                return self._create_response(
                    True,
                    f'成功提取{extraction_result["total_count"]}条数据',
                    extraction_method=config['extraction_method'],
                    extracted_data=extraction_result["data"],
                    metadata={
                        'total_items': extraction_result["total_count"],
                        'target_path': target_path,
                        'extraction_method': config['extraction_method'],
                        'execution_time': datetime.now().isoformat()
                    }
                )
            else:
                logger.error(f"❌ Data extraction failed: {extraction_result.get('error', 'Unknown error')}")
                return self._create_response(
                    False,
                    f'数据提取失败',
                    extraction_method=config['extraction_method'],
                    error=extraction_result["error"]
                )

        except Exception as e:
            logger.error(f"数据提取执行失败: {e}")
            return self._create_response(
                False,
                '数据提取失败',
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
                await asyncio.sleep(5)  # browser-use already waits for page load via _wait_for_stable_network()

                # Check for explicit failure
                if result.success is False:
                    return result

                last_result = result

                # Add natural delay between navigations
                # if i < len(urls) - 1:
                #     await asyncio.sleep(random.uniform(3, 5))  # browser-use already handles page load timing
            
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

    
    async def _get_current_page_dom(self) -> tuple:
        """Get DOM from current page with stability check

        Returns:
            tuple: (target_dom, dom_dict, llm_view)
        """
        from browser_use.browser.events import BrowserStateRequestEvent
        from ..tools.browser_use.dom_extractor import extract_dom_dict, extract_llm_view, DOMExtractor

        # Wait for page stability
        logger.debug("Dispatching BrowserStateRequestEvent to ensure page stability...")
        event = self.browser_session.event_bus.dispatch(
            BrowserStateRequestEvent(
                include_dom=True,
                include_screenshot=False,
                include_recent_events=False
            )
        )
        browser_state = await event.event_result(raise_if_any=True, raise_if_none=False)
        logger.debug("Page stability wait completed, DOM is ready")

        # Get enhanced DOM from cache
        enhanced_dom = self.browser_session._dom_watchdog.enhanced_dom_tree
        if enhanced_dom is None:
            logger.warning("⚠️  DOM tree is None after BrowserStateRequestEvent - page may not be fully loaded, will retry")
            # Return minimal DOM to trigger retry logic in caller
            return "", {}, "[]"

        # Extract DOM based on scope
        extractor = DOMExtractor()
        if self.dom_scope == "full":
            target_dom, _ = extractor.serialize_accessible_elements_custom(
                enhanced_dom, include_non_visible=True
            )
        else:
            target_dom, _ = extractor.serialize_accessible_elements_custom(
                enhanced_dom, include_non_visible=False
            )

        # Convert to DOM structures
        dom_dict = extract_dom_dict(target_dom)
        include_xpath = (self.extraction_method == 'script')
        llm_view = extract_llm_view(dom_dict, include_xpath=include_xpath)

        return target_dom, dom_dict, llm_view

    async def _extract_data_from_current_page(
        self,
        data_requirements: str,
        max_items: int,
        timeout: int,
        context: Optional[AgentContext] = None,
        config: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Extract data from current page"""

        try:
            # Get DOM from current page
            target_dom, dom_dict, llm_view = await self._get_current_page_dom()

            # Check if DOM is too small and retry if needed
            if len(llm_view) <= 100:
                logger.warning("⚠️  DOM appears too small - page may not be fully loaded")
                logger.warning(f"    LLM view length: {len(llm_view)} chars")
                logger.warning(f"    LLM view content: {llm_view}")
                logger.warning(f"    DOM dict tag: {dom_dict.get('tag')}")
                logger.warning(f"    Waiting 2 seconds and retrying DOM extraction...")

                # Wait for page to fully load
                await asyncio.sleep(2)

                # Retry DOM extraction
                logger.info("Retrying DOM extraction after wait...")
                target_dom, dom_dict, llm_view = await self._get_current_page_dom()

                logger.info(f"    After retry - LLM view length: {len(llm_view)} chars")
                if len(llm_view) <= 100:
                    logger.error("⚠️  DOM still too small after retry - proceeding anyway")

            logger.info(f"    Final LLM view length: {len(llm_view)} chars")
            logger.info(f"    Final LLM view content: {llm_view[:100]}...")

            # 调试模式: 保存DOM结构
            if self.debug_mode:
                logger.info("=== DOM 结构分析 ===")
                logger.info(f"DOM范围: {self.dom_scope}")
                logger.info(f"DOM元素总数: {len(target_dom.selector_map) if hasattr(target_dom, 'selector_map') else '未知'}")
                logger.info(f"有意义元素数: {len(json.loads(llm_view)) if llm_view != '[]' else 0}")

                # 保存DOM到文件
                import time
                debug_key = f"extraction_{self.extraction_method}_{self.dom_scope}_{int(time.time())}"

                # 使用人类可读的JSON格式保存到文件
                dom_representation = json.dumps(dom_dict, indent=2, ensure_ascii=False)

                await self._save_dom_to_file(dom_representation, debug_key)

            # 根据配置的提取方法调用对应函数
            if self.extraction_method == 'script':
                return await self._extract_with_script(
                    target_dom, dom_dict, llm_view, data_requirements, max_items, timeout, context
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
        data_requirements: Dict,
        max_items: int,
        timeout: int,
        context: Optional[AgentContext] = None
    ) -> Dict[str, Any]:
        """Extract data using script mode - file-based caching with Claude SDK"""
        from pathlib import Path

        try:
            # Generate script key and workspace path
            script_key = self._generate_script_key(data_requirements)

            if not self.config_service:
                raise RuntimeError("ConfigService required for file-based script storage")

            scripts_root = self.config_service.get_path("data.scripts")
            script_workspace = scripts_root / script_key
            script_file = script_workspace / "extraction_script.py"

            # Check if script already exists (file-based cache)
            generated_script = None

            if script_file.exists():
                # Load cached script from file
                script_content = script_file.read_text(encoding='utf-8')
                logger.info(f"✅ Loaded cached script from {script_file}")
                logger.info(f"   Script size: {len(script_content)} chars")

                # Wrap the script with execution wrapper (same as fresh generation)
                generated_script = self._extract_and_wrap_code(script_content)
            else:
                # Generate new script using Claude SDK
                logger.info(f"📝 Script not found at {script_file}")
                logger.info(f"   Generating new script with Claude SDK...")
                logger.info(f"   Using partial DOM to save tokens during generation")

                # Temporarily switch to partial scope for script generation
                original_scope = self.dom_scope
                self.dom_scope = 'partial'

                # Get DOM for script generation
                partial_dom, partial_dict, partial_llm_view = await self._get_current_page_dom()

                # Restore original scope
                self.dom_scope = original_scope

                # Build DOM analysis data with PARTIAL DOM
                dom_analysis = {
                    'serialized_dom': partial_dom,
                    'dom_dict': partial_dict,
                    'llm_view': partial_llm_view,
                    'dom_config': {
                        'dom_scope': 'partial'  # Always partial for generation
                    }
                }

                # Generate script using Claude SDK
                generated_script = await self._generate_extraction_script_with_llm(
                    dom_analysis, data_requirements, [], None
                )

                logger.info(f"✅ Script generated successfully by Claude SDK")
                logger.info(f"   Script workspace: {script_workspace}")
                logger.info(f"   Script file: {script_file}")
                logger.info(f"   Generated using: partial DOM (token optimization)")
                logger.info(f"   Execution will use: {self.dom_scope} DOM")

            # Execute script with user-specified DOM scope (target_dom is already scoped)
            logger.info(f"Executing script with {self.dom_scope} DOM scope")
            return await self._execute_generated_script_direct(
                generated_script, target_dom, dom_dict, max_items
            )

        except Exception as e:
            logger.error(f"脚本模式提取失败: {e}")
            return self._create_error_result(str(e))
    
    def _parse_llm_json(self, text: str) -> Optional[List[Dict]]:
        """Parse JSON from LLM response - simple and robust"""
        import re

        if not text:
            return None

        # Step 1: Extract JSON array (handle markdown blocks)
        text = text.strip()
        if '```' in text:
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1).strip()

        # Find array pattern
        match = re.search(r'(\[.*\])', text, re.DOTALL)
        if not match:
            return None

        json_str = match.group(1)

        # Step 2: Normalize Chinese punctuation
        cn_to_en = {
            '"': '"', '"': '"',  # Chinese quotes
            ''': "'", ''': "'",  # Chinese apostrophes
            '，': ',', '：': ':',  # Chinese comma/colon
            '；': ';',            # Chinese semicolon
        }
        for cn, en in cn_to_en.items():
            json_str = json_str.replace(cn, en)

        # Step 3: Try parse directly
        try:
            data = json.loads(json_str)
            return data if isinstance(data, list) else None
        except json.JSONDecodeError:
            pass

        # Step 4: Fallback - clean nested quotes in values
        # Remove any quotes inside string values
        def clean_value(match):
            value = match.group(1)
            # Remove all quotes and apostrophes from value
            value = value.replace('"', '').replace("'", '')
            return f'"{value}"'

        json_str = re.sub(r'"([^"]*)"(?=[,\}\]])', clean_value, json_str)

        # Final attempt
        try:
            data = json.loads(json_str)
            return data if isinstance(data, list) else None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            logger.debug(f"Problematic JSON: {json_str[:200]}...")
            return None

    def _build_extraction_prompt(self, llm_view: str, requirements: Dict, max_items: int, max_dom_chars: int = 250000) -> str:
        """Build extraction prompt from requirements

        Args:
            llm_view: LLM view of DOM to include in prompt
            requirements: Data requirements
            max_items: Maximum items to extract
            max_dom_chars: Maximum DOM characters to prevent token overflow (default: 250k chars ≈ 140k tokens)
        """
        user_desc = requirements.get('user_description', '')
        output_format = requirements.get('output_format', {})
        sample_data = requirements.get('sample_data', [])

        # Truncate DOM if too large to prevent token overflow
        if len(llm_view) > max_dom_chars:
            logger.warning(f"DOM truncated from {len(llm_view)} to {max_dom_chars} chars to prevent token overflow")
            llm_view = llm_view[:max_dom_chars] + '\n... [DOM TRUNCATED]'

        # Format field descriptions
        fields = "\n".join([
            f"- {name}: {desc}"
            for name, desc in output_format.items()
        ])

        # Format sample if provided
        sample = ""
        if sample_data:
            sample = f"\n\nSample output:\n{json.dumps(sample_data, indent=2, ensure_ascii=False)}"

        return f"""Extract data from HTML DOM:

Requirement: {user_desc}
Fields:
{fields}

Max items: {max_items}
DOM scope: {self.dom_scope}{sample}

HTML DOM:
{llm_view}

CRITICAL RULES:
1. Return JSON array ONLY, no other text
2. NO markdown blocks (no ```)
3. NO quotes or apostrophes inside field values
4. Replace ALL quotes in values with spaces or dashes
5. Example: Change "User's comment" to "User comment"
6. Example: Change 'Product "ABC"' to 'Product ABC'

CORRECT format:
[{{"text": "Hot topic about technology"}}, {{"text": "User comment on product"}}]

WRONG format:
[{{"text": "User said 'hello'"}}, {{"text": "Product "ABC" review"}}]

Extract data now:"""

    async def _extract_with_llm(
        self,
        dom_dict: Dict,
        llm_view: str,
        data_requirements: Dict,
        max_items: int,
        timeout: int
    ) -> Dict[str, Any]:
        """Extract data using LLM with simplified logic"""
        try:
            # Debug logging before building prompt
            logger.info(f"📊 Debug: llm_view length = {len(llm_view)} chars")
            logger.info(f"📊 Debug: llm_view preview = {llm_view[:200]}...")

            # Build extraction prompt
            prompt = self._build_extraction_prompt(
                llm_view,
                data_requirements,
                max_items
            )

            logger.info(f"📊 Debug: final prompt length = {len(prompt)} chars")

            # Get LLM response using provider from context
            if not self.provider:
                raise RuntimeError("No LLM provider available. ScraperAgent must be initialized with context.")

            response = await self.provider.generate_response(
                system_prompt="You are a data extraction expert. Return only JSON array, no markdown, no explanations.",
                user_prompt=prompt
            )

            # Enhanced logging for debugging
            logger.info(f"LLM response length: {len(response)}")
            logger.info(f"LLM response preview: {response[:500]}...")

            # Parse response
            extracted_data = self._parse_llm_json(response)

            # Log parsing result
            if extracted_data:
                logger.info(f"Successfully parsed {len(extracted_data)} items")
            else:
                logger.warning(f"Failed to parse LLM response")
                logger.info(f"Full LLM response: {response}")

            if extracted_data:
                # Limit results if needed
                if max_items > 0:
                    extracted_data = extracted_data[:max_items]

                return {
                    "success": True,
                    "data": extracted_data,
                    "total_count": len(extracted_data),
                    "dom_config": {"dom_scope": self.dom_scope},
                    "error": None
                }

            logger.warning("No valid data extracted from LLM response")
            return self._create_error_result("Failed to extract valid JSON from LLM")

        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
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
                                                 example_data: Optional[str] = None,
                                                 max_dom_chars: int = 250000) -> str:
        """Generate data extraction script using Claude Agent SDK with iterative refinement

        Args:
            dom_analysis: DOM analysis data containing dom_dict and llm_view
            data_requirements: Data requirements dictionary
            interaction_steps: Interaction steps (unused in Claude SDK mode)
            example_data: Example data (unused in Claude SDK mode)
            max_dom_chars: Maximum DOM characters (unused - Claude can grep the file)

        Returns:
            Generated script content as string

        Raises:
            RuntimeError: If Claude SDK script generation fails
        """
        from common.llm import ClaudeAgentProvider
        from pathlib import Path

        try:
            # 1. Create working directory for this script
            script_key = self._generate_script_key(data_requirements)

            if not self.config_service:
                raise RuntimeError("ConfigService not available - required for Claude SDK integration")

            scripts_root = self.config_service.get_path("data.scripts")
            working_dir = scripts_root / script_key
            working_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Claude SDK workspace created: {working_dir}")

            # 2. Save input files for Claude to read
            # Save data requirements
            requirement_file = working_dir / "requirement.json"
            requirement_file.write_text(
                json.dumps(data_requirements, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            # Save DOM data (dom_dict, not llm_view - Claude can grep it)
            dom_file = working_dir / "dom_data.json"
            dom_dict = dom_analysis.get('dom_dict', {})
            dom_file.write_text(
                json.dumps(dom_dict, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            logger.info(f"Input files saved: requirement.json ({requirement_file.stat().st_size} bytes), "
                       f"dom_data.json ({dom_file.stat().st_size} bytes)")

            # 3. Build Claude SDK prompt
            user_description = data_requirements.get('user_description', '')
            output_format = data_requirements.get('output_format', {})
            sample_data = data_requirements.get('sample_data', [])
            xpath_hints = data_requirements.get('xpath_hints', {})

            # Build field descriptions
            fields_description = "\n".join([f"- {name}: {desc}" for name, desc in output_format.items()])

            # Build sample data description
            sample_description = ""
            if sample_data:
                sample_description = f"\n\nExpected output example:\n{json.dumps(sample_data, indent=2, ensure_ascii=False)}"

            # Build xpath hints
            xpath_hints_description = ""
            if xpath_hints:
                hints_list = "\n".join([f"- {name}: {xpath}" for name, xpath in xpath_hints.items()])
                xpath_hints_description = f"\n\nXPath hints from user demo (reference only):\n{hints_list}"

            # Build Claude SDK prompt
            prompt = f"""# Web Scraping Script Generation Task

## Working Directory Structure

You are working in: `{working_dir}`

**Files available:**
- `requirement.json` - Data extraction requirements
- `dom_data.json` - DOM structure of the webpage (JSON format)

**Files to create:**
- `extraction_script.py` - Main extraction script

## Task Overview

Generate a Python script that extracts data from a webpage DOM structure according to user requirements.

## Step 1: Read Input Files

First, read the input files to understand the requirements:
- Read `requirement.json` to see what data needs to be extracted
- Read `dom_data.json` to understand the webpage structure (use Grep/Read tools to explore)

## Step 2: Understand DOM Structure

The DOM data is in JSON format with this structure:
```python
{{
    "tag": "div",           # HTML tag name
    "text": "content",      # Text content
    "class": "item",        # CSS class
    "href": "url",          # Link URL
    "xpath": "/html/...",   # XPath location
    "children": [...]       # Nested children
}}
```

Use Grep to search for specific patterns in dom_data.json, for example:
- Search for class names: grep -i '"class".*product' dom_data.json
- Search for specific tags: grep -i '"tag".*"h2"' dom_data.json

## Step 3: Data Extraction Requirements

**User Description:** {user_description}

**Fields to extract:**
{fields_description}{sample_description}{xpath_hints_description}

## Step 4: Generate extraction_script.py

Create a file named `extraction_script.py` with this function:

```python
def extract_data_from_page(serialized_dom, dom_dict) -> List[Dict[str, Any]]:
    \"\"\"
    Extract data from DOM structure

    Args:
        serialized_dom: SerializedDOMTree object (browser-use library)
        dom_dict: DOM structure as nested dictionary

    Returns:
        List of dictionaries, each containing extracted fields
    \"\"\"
    # Your implementation here
    pass
```

**Requirements:**
1. Function must be named `extract_data_from_page`
2. Parameters: `serialized_dom` and `dom_dict`
3. Return type: `List[Dict[str, Any]]`
4. Include proper error handling
5. Use recursive traversal of dom_dict to find target elements
6. Handle cases where elements might not exist

**Common patterns:**
- For list extraction: Find repeating container elements, extract fields from each
- For single item: Navigate to specific element and extract fields
- Use XPath hints as reference, but adapt to actual DOM structure

## Step 5: Test and Validate

After generating the script:
1. Create a test file `test_script.py` that:
   - Loads dom_data.json
   - Calls extract_data_from_page() with the DOM data
   - Validates output format matches requirements
   - Prints extracted data

2. Run the test: `python test_script.py`

3. If errors occur:
   - Analyze the error message
   - Fix the extraction_script.py
   - Re-run the test
   - Repeat until test passes

## Step 6: Final Verification

Ensure:
- extraction_script.py exists and is syntactically correct
- Test passes without errors
- Output data matches expected format from requirement.json

---

**Important Notes:**
- This is a sample page - the script should work on pages with similar structure but different content
- Use flexible selectors (class names, patterns) rather than hardcoded values
- Handle missing elements gracefully (return empty list or skip items)
- The DOM structure in dom_data.json represents the actual webpage HTML structure

Start by reading requirement.json and dom_data.json to understand the task!
"""

            # 4. Initialize Claude Agent Provider
            claude_provider = ClaudeAgentProvider(config_service=self.config_service)
            logger.info("Claude Agent Provider initialized")

            # 5. Run Claude SDK to generate and test script
            max_iterations = self.config_service.get("claude_agent.default_max_iterations", 50)

            logger.info(f"Starting Claude SDK task with max_iterations={max_iterations}")
            result = await claude_provider.run_task(
                prompt=prompt,
                working_dir=working_dir,
                max_iterations=max_iterations
            )

            # 6. Check result
            if not result.success:
                error_msg = f"Claude SDK script generation failed after {result.iterations} iterations: {result.error}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            logger.info(f"Claude SDK completed successfully in {result.iterations} iterations")

            # 7. Read generated script
            script_file = working_dir / "extraction_script.py"
            if not script_file.exists():
                raise FileNotFoundError(
                    f"extraction_script.py not found in {working_dir}. "
                    f"Claude SDK completed but did not create the expected file."
                )

            script_content = script_file.read_text(encoding='utf-8')
            logger.info(f"Script loaded from {script_file} ({len(script_content)} chars)")

            # 8. Wrap script with execution wrapper (same as before)
            return self._extract_and_wrap_code(script_content)
            
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

    def _generate_script_key(self, data_requirements: Dict) -> str:
        """Generate script storage key based on data requirements only

        Note: dom_scope is NOT included in key because:
        - Script generation always uses partial DOM (to save tokens)
        - Generated script is generic and can work with both partial/full DOM during execution
        """
        # 使用用户描述和字段名生成key (不包含dom_scope)
        user_desc = data_requirements.get('user_description', '')
        fields = list(data_requirements.get('output_format', {}).keys())
        content = f"script_{user_desc}_{','.join(fields)}"
        hash_suffix = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"scraper_script_{hash_suffix}"
    
    def _create_error_result(self, error_msg: str) -> Dict[str, Any]:
        return {
            "success": False,
            "data": [],
            "total_count": 0,
            "error": error_msg
        }
    
    def _create_response(self, success: bool, message: str = "", **kwargs) -> Dict[str, Any]:
        response = {
            'success': success,
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

    # cleanup 方法不再需要，由context统一管理浏览器会话生命周期

