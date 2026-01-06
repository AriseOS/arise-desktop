"""ScraperAgent - 基于 browser-use 库的通用爬虫生成代理"""
import asyncio
import json
import hashlib
import random
import logging
from typing import Any, Dict, Optional, Union, List
from datetime import datetime
from pathlib import Path

from .base_agent import BaseStepAgent, AgentMetadata
from ..core.schemas import AgentContext
from src.common.llm import OpenAIProvider, AnthropicProvider

# Import script templates from common module (for consistency with Cloud Backend)
from src.common.script_generation.templates import SCRAPER_AGENT_PROMPT

# Import dom_tools for script execution (PyInstaller will auto-detect this)
from lib import dom_tools

try:
    from browser_use import Tools
    from browser_use.browser.session import BrowserSession
    from browser_use.browser.profile import BrowserProfile
    from browser_use.dom.service import DomService
    from browser_use.browser.events import NavigateToUrlEvent, ScrollEvent
    from browser_use.agent.views import ActionResult
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

        # Initialize ResourceManager for workflow resource sync
        self.resource_manager = None
        if config_service:
            from src.common.services.resource_manager import ResourceManager
            self.resource_manager = ResourceManager(config_service)
            logger.info("ResourceManager initialized for workflow resource sync")

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

    def _configure_cdp_logging(self):
        """Configure CDP logging to reduce noise from non-fatal iframe errors"""
        import logging
        # Reduce CDP error logging for known non-fatal issues
        # "Command can only be executed on top-level targets" errors are caught and handled
        cdp_logger = logging.getLogger('cdp_use.client')
        # Only show CRITICAL CDP errors, suppress ERROR level
        cdp_logger.setLevel(logging.CRITICAL)

    async def initialize(self, context: AgentContext) -> bool:
        """初始化Agent，从context获取浏览器会话和provider"""
        try:
            # Configure CDP logging to suppress non-fatal iframe errors
            self._configure_cdp_logging()

            # Save context for later use (e.g., in _generate_script_key)
            self._context = context

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

        # data_requirements 是必需的
        # target_path 是可选的 - 如果为空或不存在，使用当前页面
        return 'data_requirements' in actual_data
    
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
        target_path = input_data.get('target_path')  # 可选，如果为空则使用当前页面
        data_requirements = input_data['data_requirements']
        interaction_steps = input_data.get('interaction_steps', [])

        if target_path:
            logger.info(f"📄 Starting scrape with target_path: {target_path}")
        else:
            logger.info(f"📄 Starting scrape on current page")
        logger.debug(f"   config: {config}")

        try:
            # 使用config中的参数
            max_items = config['max_items']
            timeout = config['timeout']

            # 如果有 target_path，导航到目标页面并执行交互
            # 如果没有 target_path，直接使用当前页面
            if target_path:
                navigate_result = await self._navigate_to_pages(target_path, interaction_steps)

                if navigate_result.success is False:
                    return self._create_response(
                        False,
                        f'页面导航失败: {navigate_result.error}'
                    )
            else:
                # 没有 target_path，使用当前页面，但可能还有 interaction_steps (如 scroll)
                if interaction_steps:
                    logger.info(f"🎯 Executing {len(interaction_steps)} interaction steps on current page...")
                    for idx, step in enumerate(interaction_steps):
                        action_type = step.get('action_type', 'unknown')
                        logger.info(f"   Step {idx + 1}/{len(interaction_steps)}: {action_type}")

                        interaction_result = await self._execute_interaction_step(step)

                        if interaction_result.success is False:
                            return self._create_response(
                                False,
                                f'交互步骤 {idx + 1} 失败: {interaction_result.error}'
                            )

                    logger.info(f"✅ All interaction steps completed successfully")
                    await asyncio.sleep(3)  # Wait for content stability

            # 提取数据
            extraction_result = await self._extract_data_from_current_page(
                data_requirements,
                max_items,
                timeout,
                context=context,
                config=config
            )

            # Anti-bot random behavior after extraction
            await self._perform_anti_bot_behavior()

            # 返回结果
            if extraction_result["success"]:
                # Log extraction results in one line
                data_preview = extraction_result["data"][:2] if extraction_result["total_count"] > 0 else []
                preview_str = f"{data_preview[0]}" if len(data_preview) > 0 else "[]"
                logger.info(f"✅ Extracted {extraction_result['total_count']} items using {config['extraction_method']} | Preview: {preview_str}")

                # Log full output for debugging
                logger.info(f"📦 Full extracted_data output (type={type(extraction_result['data'])}, length={len(extraction_result['data'])}): {extraction_result['data']}")

                # Send extraction results to frontend
                if context and context.log_callback:
                    try:
                        await context.log_callback(
                            "success",
                            f"✅ Extracted {extraction_result['total_count']} items successfully",
                            {
                                "extraction_method": config['extraction_method'],
                                "total_items": extraction_result['total_count'],
                                "extracted_data": extraction_result['data']  # Send all data
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send log callback: {e}")

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
                logger.info(f"🔗 Attempting to navigate to: {url}")

                # Use event system directly (v0.9+ recommended approach)
                event = self.browser_session.event_bus.dispatch(
                    NavigateToUrlEvent(url=url, new_tab=False)
                )
                await event
                result = await event.event_result(raise_if_any=False, raise_if_none=False)
                await asyncio.sleep(5)  # browser-use already waits for page load via _wait_for_stable_network()

                # Check for explicit failure
                if result and hasattr(result, 'success') and result.success is False:
                    logger.error(f"❌ Navigation failed for URL: {url}, error: {result.error}")
                    return result

                last_result = result

                # Add natural delay between navigations
                # if i < len(urls) - 1:
                #     await asyncio.sleep(random.uniform(3, 5))  # browser-use already handles page load timing

            # Execute interaction steps after navigation (if provided)
            if interaction_steps:
                logger.info(f"🎯 Executing {len(interaction_steps)} interaction steps...")
                for idx, step in enumerate(interaction_steps):
                    action_type = step.get('action_type', 'unknown')
                    logger.info(f"   Step {idx + 1}/{len(interaction_steps)}: {action_type}")

                    interaction_result = await self._execute_interaction_step(step)

                    # Check if interaction failed
                    if interaction_result and hasattr(interaction_result, 'success') and interaction_result.success is False:
                        logger.error(f"❌ Interaction step {idx + 1} failed: {interaction_result.error}")
                        return interaction_result

                    # Add small delay between interactions for stability
                    await asyncio.sleep(0.5)

                logger.info(f"✅ All interaction steps completed successfully")

                # Wait 3 seconds after all interaction steps to ensure content is loaded
                await asyncio.sleep(3)

            # Return the last result (which should have success=None for successful navigation)
            return last_result if last_result else ActionResult(extracted_content="No navigation performed")
                
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return ActionResult(success=False, error=str(e))

    async def _execute_interaction_step(self, step_config: Dict) -> ActionResult:
        """Execute single interaction step (currently only supports scroll)"""
        try:
            action_type = step_config['action_type']
            parameters = step_config.get('parameters', {})

            if action_type == 'scroll':
                # Use event system directly (v0.9+ recommended approach)
                scroll_down = parameters.get('down', True)
                amount = int(parameters.get('num_pages', 1.0) * 500)  # Convert pages to pixels
                direction = "down" if scroll_down else "up"

                logger.debug(f"Scrolling: direction={direction}, amount={amount}px")

                event = self.browser_session.event_bus.dispatch(
                    ScrollEvent(direction=direction, amount=amount)
                )
                await event
                result = await event.event_result(raise_if_any=False, raise_if_none=False)

                # Wait for page to stabilize after scroll
                await asyncio.sleep(1)

                return ActionResult(extracted_content=f"Scrolled {direction} {amount}px")
            else:
                logger.warning(f"Unsupported action type: {action_type}. Currently only 'scroll' is supported.")
                return ActionResult(success=False, error=f"Unsupported action type: {action_type}. Only 'scroll' is currently supported.")

        except Exception as e:
            logger.error(f"Interaction step failed: {e}")
            return ActionResult(success=False, error=str(e))

    async def _perform_anti_bot_behavior(self) -> None:
        """Perform random scrolling and sleep to avoid anti-bot detection"""
        try:
            # Random number of scroll actions (1-3 times)
            num_scrolls = random.randint(1, 3)
            logger.info(f"🤖 Performing anti-bot behavior: {num_scrolls} random scrolls")

            for i in range(num_scrolls):
                # Random scroll direction and distance
                scroll_down = random.choice([True, False])
                scroll_pages = random.uniform(0.3, 1.0)  # 0.3 to 1 page
                direction = "down" if scroll_down else "up"
                amount = int(scroll_pages * 500)  # Convert to pixels

                logger.debug(f"   Scroll {i+1}/{num_scrolls}: {direction} {amount}px")

                # Use event system directly
                event = self.browser_session.event_bus.dispatch(
                    ScrollEvent(direction=direction, amount=amount)
                )
                await event
                await event.event_result(raise_if_any=False, raise_if_none=False)

                # Random sleep between scrolls (1-3 seconds)
                sleep_time = random.uniform(1, 3)
                await asyncio.sleep(sleep_time)

            # Final random sleep (2-5 seconds)
            final_sleep = random.uniform(2, 5)
            logger.info(f"   Final sleep: {final_sleep:.2f} seconds")
            await asyncio.sleep(final_sleep)

            logger.info(f"✅ Anti-bot behavior completed")

        except Exception as e:
            # Don't fail the entire scraping if anti-bot behavior fails
            logger.warning(f"Anti-bot behavior failed (non-critical): {e}")


    def _generate_url_hash(self, url: str) -> str:
        """Generate hash for URL to use as storage key

        Args:
            url: The webpage URL

        Returns:
            8-character hash string
        """
        return hashlib.md5(url.encode()).hexdigest()[:8]


    async def _save_dom_snapshot(self, url: str, dom_dict: Dict) -> None:
        """Save full DOM snapshot for a specific URL to script workspace directory

        Args:
            url: The webpage URL
            dom_dict: DOM dictionary to save (should be full DOM)
        """
        if not url:
            logger.warning("⚠️  No URL provided, skipping DOM snapshot save")
            return

        if not self.config_service:
            logger.warning("⚠️  Cannot save DOM snapshot: ConfigService not available")
            return

        # Use cached script_key (set in _extract_data_from_current_page)
        if not hasattr(self, '_current_script_key') or not self._current_script_key:
            logger.warning("⚠️  No script key available, skipping DOM snapshot save")
            return

        try:
            scripts_root = self.config_service.get_path("data.scripts")
            script_workspace = scripts_root / self._current_script_key

            # Save in script workspace: dom_snapshots/{url_hash}/
            url_hash = self._generate_url_hash(url)
            snapshot_dir = script_workspace / "dom_snapshots" / url_hash
            snapshot_dir.mkdir(parents=True, exist_ok=True)

            # Save metadata
            metadata_file = snapshot_dir / "metadata.json"
            metadata = {
                "url": url,
                "url_hash": url_hash,
                "timestamp": datetime.now().isoformat()
            }
            metadata_file.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            # Save full DOM dict
            dom_file = snapshot_dir / "dom_data.json"
            dom_file.write_text(
                json.dumps(dom_dict, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            # Update URL index file for fast lookup
            dom_snapshots_dir = script_workspace / "dom_snapshots"
            index_file = dom_snapshots_dir / "url_index.json"

            # Load existing index
            url_index = {}
            if index_file.exists():
                try:
                    url_index = json.loads(index_file.read_text(encoding='utf-8'))
                except Exception as e:
                    logger.warning(f"Failed to load URL index, creating new one: {e}")

            # Update index
            url_index[url] = {
                "hash": url_hash,
                "timestamp": datetime.now().isoformat()
            }

            # Save index
            index_file.write_text(
                json.dumps(url_index, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            logger.info(f"✅ DOM snapshot saved to: {snapshot_dir}")
            logger.info(f"   URL: {url}")
            logger.info(f"   Hash: {url_hash}")
            logger.info(f"   DOM size: {dom_file.stat().st_size} bytes")

        except Exception as e:
            logger.warning(f"⚠️  Failed to save DOM snapshot: {e}")

    async def _get_current_page_dom(self) -> tuple:
        """Get DOM from current page with stability check

        Returns:
            tuple: (target_dom, dom_dict, llm_view)
        """
        from browser_use.browser.events import BrowserStateRequestEvent
        from ..tools.browser_use.dom_extractor import extract_dom_dict, extract_llm_view, DOMExtractor

        if not self.browser_session:
            raise RuntimeError("Browser session is None")

        # Wait 3 seconds for page to fully load before getting DOM
        logger.info("Waiting 3 seconds for page to fully load...")
        await asyncio.sleep(3)

        # Wait for page stability
        event = self.browser_session.event_bus.dispatch(
            BrowserStateRequestEvent(
                include_dom=True,
                include_screenshot=False,
                include_recent_events=False
            )
        )
        await event.event_result(raise_if_any=True, raise_if_none=False)

        # Get enhanced DOM from cache
        enhanced_dom = self.browser_session._dom_watchdog.enhanced_dom_tree
        if enhanced_dom is None:
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

        # Convert to DOM structures - reuse the same extractor instance to preserve include_non_visible setting
        dom_dict = extractor.extract_dom_dict(target_dom)
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
        """Extract data from current page

        Args:
            data_requirements: Data requirements specification
            max_items: Maximum number of items to extract
            timeout: Timeout in seconds
            context: Agent context
            config: Configuration dict
        """

        try:
            # Cache script key for this extraction (used by _save_dom_snapshot)
            self._current_script_key = self._generate_script_key(data_requirements)

            # Get DOM from current page
            target_dom, dom_dict, llm_view = await self._get_current_page_dom()

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
            # Use cached script key (set in _extract_data_from_current_page)
            script_key = self._current_script_key

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

                # Send status to frontend (without script content)
                if context and context.log_callback:
                    try:
                        await context.log_callback(
                            "info",
                            f"✅ Using cached extraction script",
                            {"cache_path": str(script_file)}
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send log callback: {e}", exc_info=True)

                # Wrap the script with execution wrapper (same as fresh generation)
                generated_script = self._extract_and_wrap_code(script_content)
            else:
                # Generate new script using Claude SDK
                logger.info(f"📝 Script not found at {script_file}")
                logger.info(f"   Generating new script with Claude SDK...")
                logger.info(f"   Using full DOM for script generation (ensures all fields are captured)")

                # Send log to frontend
                if context and context.log_callback:
                    try:
                        await context.log_callback(
                            "info",
                            "📝 No cached script found, generating new script with Claude SDK...",
                            {"script_path": str(script_file)}
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send log callback: {e}")

                # Get current page URL for script generation
                page_url = None
                if self.browser_session:
                    try:
                        page_url = await self.browser_session.get_current_page_url()
                        logger.info(f"📍 Page URL for script generation: {page_url}")
                    except Exception as e:
                        logger.warning(f"⚠️  Could not get page URL: {e}")

                # Force full DOM for script generation to capture all page content
                # This ensures the script can extract fields even if they're below the fold
                original_scope = self.dom_scope
                self.dom_scope = 'full'

                # Get full DOM for script generation
                generation_dom, generation_dict, generation_llm_view = await self._get_current_page_dom()

                # Restore original scope
                self.dom_scope = original_scope

                # Build DOM analysis data with FULL DOM
                dom_analysis = {
                    'serialized_dom': generation_dom,
                    'dom_dict': generation_dict,
                    'llm_view': generation_llm_view,
                    'dom_config': {
                        'dom_scope': 'full'  # Always full for generation
                    },
                    'page_url': page_url  # Include page URL for base URL inference
                }

                # Generate script using Claude SDK
                generated_script = await self._generate_extraction_script_with_llm(
                    dom_analysis, data_requirements, [], None, context=context
                )

                logger.info(f"✅ Script generated successfully by Claude SDK")
                logger.info(f"   Script workspace: {script_workspace}")
                logger.info(f"   Script file: {script_file}")
                logger.info(f"   Generated using: full DOM (captures all page content)")
                logger.info(f"   Execution will use: {self.dom_scope} DOM")

            # Script mode always uses full DOM for execution
            # Get full DOM if not already using full scope
            if self.dom_scope != 'full':
                logger.info(f"Script mode: switching from {self.dom_scope} to full DOM for execution")
                original_scope = self.dom_scope
                self.dom_scope = 'full'
                execution_dom, execution_dict, _ = await self._get_current_page_dom()
                self.dom_scope = original_scope
            else:
                execution_dom = target_dom
                execution_dict = dom_dict

            result = await self._execute_generated_script_direct(
                generated_script, execution_dict, max_items
            )

            # Note: DOM snapshot is now stored in cloud during script generation
            # No need to save locally

            return result

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
        xpath_hints = requirements.get('xpath_hints', {})

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

        # Format xpath hints if provided
        xpath_hints_text = ""
        if xpath_hints:
            hints_list = "\n".join([f"- {name}: {xpath}" for name, xpath in xpath_hints.items()])
            xpath_hints_text = f"\n\nXPath hints (reference for element locations):\n{hints_list}\n\nNote: These XPath hints are REFERENCE ONLY from user demonstrations. Use them to understand which elements to extract, but adapt to the actual DOM structure if needed."

        return f"""Extract data from HTML DOM:

Requirement: {user_desc}
Fields:
{fields}

Max items: {max_items}
DOM scope: {self.dom_scope}{sample}{xpath_hints_text}

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
        dom_dict: Dict,
        max_items: int
    ) -> Dict[str, Any]:
        """直接执行生成的脚本，使用提供的DOM数据（dom_dict 是嵌套字典，不是 HTML）"""

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
                # Inject dom_tools module for script execution
                'dom_tools': dom_tools,
            }

            # 执行脚本
            exec(script_content, execution_env, execution_env)
            
            # 获取执行函数
            execute_func = execution_env.get('execute_extraction')
            if not execute_func:
                return self._create_error_result("脚本缺少 execute_extraction 函数")
            
            # 使用提供的DOM数据执行提取 (只传 dom_dict，不需要 serialized_dom)
            result = execute_func(dom_dict, max_items)
            return result
            
        except Exception as e:
            logger.error(f"脚本执行失败: {e}")
            return self._create_error_result(str(e))
    
    
    async def _generate_extraction_script_with_llm(self,
                                                 dom_analysis: Dict,
                                                 data_requirements: Dict,
                                                 interaction_steps: List[Dict],
                                                 example_data: Optional[str] = None,
                                                 max_dom_chars: int = 250000,
                                                 context: Optional[AgentContext] = None) -> str:
        """Generate data extraction script using Cloud API

        Script generation is delegated to the cloud backend, which:
        1. Stores DOM snapshot in workflow directory
        2. Generates script using Claude Agent SDK
        3. Returns script content

        Args:
            dom_analysis: DOM analysis data containing dom_dict and page_url
            data_requirements: Data requirements dictionary
            interaction_steps: Interaction steps (unused)
            example_data: Example data (unused)
            max_dom_chars: Maximum DOM characters (unused)
            context: Agent context for progress reporting

        Returns:
            Generated script content as string

        Raises:
            RuntimeError: If cloud script generation fails
        """
        from pathlib import Path

        try:
            # 1. Get context info
            if not hasattr(self, '_context') or not self._context:
                raise RuntimeError("Agent context not available")

            user_id = getattr(self._context, 'user_id', 'default_user')
            workflow_id = getattr(self._context, 'workflow_id', None)
            step_id = getattr(self._context, 'step_id', None)

            if not workflow_id or not step_id:
                raise RuntimeError(f"workflow_id ({workflow_id}) and step_id ({step_id}) required for cloud script generation")

            # 2. Get cloud client from context
            cloud_client = None
            if self._context.agent_instance and hasattr(self._context.agent_instance, 'cloud_client'):
                cloud_client = self._context.agent_instance.cloud_client

            if not cloud_client:
                raise RuntimeError("CloudClient not available in agent context")

            # 3. Get API key from provider (same pattern as other agents)
            api_key = None
            if self.provider and hasattr(self.provider, 'api_key') and self.provider.api_key:
                api_key = self.provider.api_key
                logger.info(f"Got API key from provider for cloud script generation")
            else:
                logger.warning("No API key available from provider for cloud script generation")

            # 4. Get page URL and DOM data from dom_analysis
            page_url = dom_analysis.get('page_url', '')
            dom_dict = dom_analysis.get('dom_dict', {})

            logger.info(f"Requesting cloud script generation: workflow={workflow_id}, step={step_id}")
            logger.info(f"  Page URL: {page_url}")
            logger.info(f"  DOM size: {len(json.dumps(dom_dict))} chars")

            # Send progress update to frontend
            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "info",
                        "📡 Requesting script generation from cloud...",
                        {"workflow_id": workflow_id, "step_id": step_id}
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            # 5. Call cloud API to generate script with SSE streaming
            # Progress callback to forward progress to frontend
            async def script_progress_callback(level: str, message: str, data: dict):
                if context and context.log_callback:
                    try:
                        turn = data.get("turn", 0)
                        tool_name = data.get("tool_name")
                        progress_msg = f"🔧 Generating script (turn {turn})"
                        if tool_name:
                            progress_msg += f" - using {tool_name}"
                        await context.log_callback(level, progress_msg, data)
                    except Exception as e:
                        logger.warning(f"Failed to send progress callback: {e}")

            result = await cloud_client.generate_script_stream(
                workflow_id=workflow_id,
                step_id=step_id,
                script_type="scraper",
                page_url=page_url,
                user_id=user_id,
                dom_data=dom_dict,  # Upload current page DOM
                api_key=api_key,
                progress_callback=script_progress_callback
            )

            if not result.get('success'):
                error_msg = result.get('error', 'Unknown error')
                raise RuntimeError(f"Cloud script generation failed: {error_msg}")

            script_content = result.get('script_content', '')
            script_path = result.get('script_path', '')
            script_key = result.get('script_key', '')
            turns = result.get('turns', 0)

            logger.info(f"✅ Cloud script generation completed in {turns} turns")
            logger.info(f"   Script path: {script_path}")
            logger.info(f"   Script key: {script_key}")
            logger.info(f"   Script size: {len(script_content)} chars")

            # 5. Save script to local cache
            if self.config_service and script_key:
                scripts_root = self.config_service.get_path("data.scripts")
                # Build local cache path matching cloud structure
                local_script_dir = scripts_root / f"users/{user_id}/workflows/{workflow_id}/{step_id}/{script_key}"
                local_script_dir.mkdir(parents=True, exist_ok=True)

                local_script_file = local_script_dir / "extraction_script.py"
                local_script_file.write_text(script_content, encoding='utf-8')
                logger.info(f"   Saved to local cache: {local_script_file}")

                # Also save requirement.json for reference
                requirement_file = local_script_dir / "requirement.json"
                requirement_file.write_text(
                    json.dumps(data_requirements, indent=2, ensure_ascii=False),
                    encoding='utf-8'
                )

            # Send completion update to frontend
            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "success",
                        f"✅ Script generated by cloud in {turns} turns",
                        {"script_path": script_path, "turns": turns}
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            # 6. Wrap script with execution wrapper
            return self._extract_and_wrap_code(script_content)

        except Exception as e:
            logger.error(f"Cloud script generation failed: {e}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Cloud script generation failed: {e}")
    
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

def execute_extraction(dom_dict, max_items: int = 100):
    """Execute data extraction wrapper function"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Extract all available data (dom_dict is a nested dictionary, NOT HTML)
        all_data = extract_data_from_page(dom_dict)
        
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
        """Generate script storage path relative to data.root

        Path structure: users/{user_id}/workflows/{workflow_id}/{step_id}/{hash_based_key}
        Full path will be: {data.root}/users/{user_id}/workflows/{workflow_id}/{step_id}/{script_key}

        This allows:
        - Organizing scripts by user and workflow
        - Organizing by step within workflow
        - Caching/reusing scripts with same requirements within a step

        Args:
            data_requirements: Dict containing user_description and output_format

        Returns:
            Relative path like: users/default_user/workflows/producthunt-daily-top10/extract-daily-link/scraper_script_a1b2c3d4
            Which resolves to: ~/.ami/users/default_user/workflows/producthunt-daily-top10/extract-daily-link/scraper_script_a1b2c3d4/
        """
        # Get context information
        user_id = "default_user"
        workflow_id = "default_workflow"
        step_id = "default_step"

        if hasattr(self, '_context') and self._context:
            user_id = getattr(self._context, 'user_id', user_id)
            workflow_id = getattr(self._context, 'workflow_id', workflow_id)
            step_id = getattr(self._context, 'step_id', step_id)
            logger.info(f"ScraperAgent context info - user_id: {user_id}, workflow_id: {workflow_id}, step_id: {step_id}")
        else:
            logger.warning("ScraperAgent: No context available, using default values for script path")

        # Generate hash-based key using data requirements
        # IMPORTANT: Must match cloud_backend/intent_builder/services/script_pregeneration_service.py
        user_desc = data_requirements.get('user_description', '')
        output_format = data_requirements.get('output_format', {})
        content = f"scraper:{user_desc}:{json.dumps(output_format, sort_keys=True)}"
        hash_suffix = hashlib.md5(content.encode()).hexdigest()[:8]
        script_key = f"scraper_script_{hash_suffix}"

        # Build relative path (will be prefixed with data.root by config_service)
        script_path = f"users/{user_id}/workflows/{workflow_id}/{step_id}/{script_key}"
        logger.info(f"Generated script path: {script_path}")
        return script_path
    
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

