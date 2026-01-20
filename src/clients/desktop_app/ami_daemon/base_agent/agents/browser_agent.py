"""BrowserAgent v3.0 - Intelligent browser interaction agent

Design:
- Claude Agent generates scripts to locate target elements
- BrowserAgent executes operations (click, fill, scroll, scroll_to_element)
- Multi-round interaction: Claude Agent generates → BrowserAgent executes → feedback loop
- Per-step caching: Each interaction_step has independent workspace and cached script

Supported Operations:
- click: Click on an element (Claude Agent finds interactive_index → selector_map → backend_node_id)
- fill: Fill text into an element (Claude Agent finds interactive_index → selector_map → backend_node_id)
- scroll: Scroll page up/down (direct execution, no element finding)
- scroll_to_element: Scroll to make element visible (Claude Agent finds xpath → CDP scroll)
  Note: scroll_to_element uses xpath instead of interactive_index because target
        elements may not be interactive (headings, sections, divs, etc.)

Workflow for click/fill:
1. Get DOM (dom_dict + selector_map with interactive elements)
2. Check cached find_element.py, if exists → execute directly
3. If no cache → Claude Agent generates find_element.py (returns interactive_index)
4. Convert interactive_index → backend_node_id via selector_map
5. Execute operation via Element API
6. If failed → update DOM, feedback to Claude Agent, retry

Workflow for scroll_to_element:
1. Get DOM with xpath information
2. Check cached scroll_xpath.txt, if exists → execute directly
3. If no cache → Claude Agent analyzes DOM and returns target xpath
4. Execute scroll via CDP DOM.performSearch + scrollIntoViewIfNeeded
5. Cache xpath for reuse

Key Files in Workspace:
- task.json: Task description with xpath hints
- dom_data.json: Current page DOM structure
- find_element.py: For click/fill (returns interactive_index)
- scroll_xpath.txt: For scroll_to_element (cached xpath)
"""
import asyncio
import json
import hashlib
import logging
from typing import Any, Dict, Optional, List
from pathlib import Path

from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext

# Import script templates from common module
from src.common.script_generation.templates import (
    BROWSER_TEST_OPERATION,
    BROWSER_FIND_ELEMENT_TEMPLATE,
    BROWSER_AGENT_PROMPT,
)

try:
    from browser_use import Tools
    from browser_use.browser.session import BrowserSession
    from browser_use.browser.events import NavigateToUrlEvent, ScrollEvent, SwitchTabEvent, CloseTabEvent
    from browser_use.agent.views import ActionResult
    from browser_use.actor.element import Element
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    Tools = None
    BrowserSession = None
    NavigateToUrlEvent = None
    ScrollEvent = None
    SwitchTabEvent = None
    CloseTabEvent = None
    ActionResult = None
    Element = None

logger = logging.getLogger(__name__)


class BrowserAgent(BaseStepAgent):
    """BrowserAgent v3.0 - Intelligent browser interaction agent

    Supported Operations:
    - click: Click on an element
    - fill: Fill text into an element
    - scroll: Scroll the page up/down

    Design:
    - Claude Agent generates find_element.py to locate target elements
    - BrowserAgent executes operations using browser-use Element API
    - Multi-round interaction with feedback loop for error recovery
    - Per-step caching for script reuse

    Flow:
    1. Get DOM (dom_dict + selector_map from browser-use)
    2. Check cached find_element.py, if exists → execute directly
    3. If no cache → Claude Agent generates find_element.py
    4. Execute find_element.py to get interactive_index
    5. Convert interactive_index → backend_node_id via selector_map
    6. Execute operation (click/fill/scroll) using Element API
    7. If failed → update DOM, feedback to Claude Agent, retry
    """

    INPUT_SCHEMA = InputSchema(
        description="Browser interaction agent for clicking, filling forms, and scrolling",
        fields={
            "target_url": FieldSchema(
                type="str",
                required=False,
                description="URL to navigate to before interaction (optional if already on target page)"
            ),
            "interaction_steps": FieldSchema(
                type="list",
                required=False,
                items_type="dict",
                description="List of interaction steps, each with 'task' and 'xpath_hints'"
            ),
            "timeout": FieldSchema(
                type="int",
                required=False,
                default=30,
                description="Execution timeout in seconds"
            ),
        },
        examples=[
            {
                "target_url": "https://example.com/login",
                "interaction_steps": [
                    {
                        "task": "Click the login button",
                        "xpath_hints": {"login_button": "//button[contains(text(), 'Login')]"}
                    }
                ]
            },
            {
                "interaction_steps": [
                    {
                        "task": "Fill the search box with 'python'",
                        "xpath_hints": {"search_input": "//input[@name='q']"},
                        "text": "python"
                    }
                ]
            }
        ]
    )

    # Templates are imported from src.common.script_generation.templates:
    # - BROWSER_TEST_OPERATION
    # - BROWSER_FIND_ELEMENT_TEMPLATE
    # - BROWSER_AGENT_PROMPT

    def __init__(self,
                 config_service=None,
                 metadata: Optional[AgentMetadata] = None):
        """Initialize BrowserAgent

        Args:
            config_service: Configuration service (optional)
            metadata: Agent metadata (optional)
        """
        if not BROWSER_USE_AVAILABLE:
            raise ImportError("browser-use library not installed. Please install: pip install browser-use")

        if metadata is None:
            metadata = AgentMetadata(
                name="browser_agent",
                description="Intelligent browser interaction agent with LLM-driven script generation"
            )
        super().__init__(metadata)

        # Save config service
        self.config_service = config_service

        # browser-use components (will be set in initialize)
        self.browser_session = None
        self.controller = None

        # Provider for LLM operations (will be set in initialize)
        self.provider = None

        # Context reference
        self._context = None

        # Tab management: track initial tabs for cleanup
        self._initial_tab_ids: set = set()

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize agent with browser session from context

        Gets the shared browser session from AgentContext, ensuring all agents
        in the workflow use the same browser instance.

        Args:
            context: Agent execution context

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Save context for later use
            self._context = context

            # Get browser session from context (shared across workflow)
            session_info = await context.get_browser_session()

            # Set browser-use components
            self.browser_session = session_info.session
            self.controller = session_info.controller

            # Get provider and config_service from context.agent_instance (BaseAgent)
            if context.agent_instance:
                if hasattr(context.agent_instance, 'provider'):
                    self.provider = context.agent_instance.provider
                    logger.info(f"BrowserAgent got provider from BaseAgent: {type(self.provider).__name__}")
                else:
                    logger.warning("BrowserAgent: No provider available from context, LLM operations will fail")

                if hasattr(context.agent_instance, 'config_service'):
                    self.config_service = context.agent_instance.config_service
                    logger.info("BrowserAgent got config_service from BaseAgent")
                else:
                    logger.warning("BrowserAgent: No config_service available, Claude Agent SDK will fail")

            # Mark as initialized
            self.is_initialized = True

            logger.info(f"BrowserAgent initialized successfully using workflow {context.workflow_id} shared session")
            return True

        except Exception as e:
            logger.error(f"BrowserAgent initialization failed: {e}")
            return False

    def _generate_script_key(self, task: str, xpath_hints: Dict[str, str]) -> str:
        """Generate script storage key for caching

        Similar to ScraperAgent, generates a unique key based on:
        - User ID and workflow context (if available)
        - Task description hash
        - XPath hints hash

        Path structure: users/{user_id}/workflows/{workflow_id}/{step_id}
        Scripts are stored directly in the step directory (no hash subdirectory).
        The hash is only used internally to detect if script regeneration is needed.

        Args:
            task: Task description
            xpath_hints: XPath hints for element location

        Returns:
            Relative path for script storage (step directory)
        """
        # Get context information
        user_id = "default_user"
        workflow_id = "default_workflow"
        step_id = "default_step"

        if hasattr(self, '_context') and self._context:
            user_id = getattr(self._context, 'user_id', user_id)
            workflow_id = getattr(self._context, 'workflow_id', workflow_id)
            step_id = getattr(self._context, 'step_id', step_id)
            logger.debug(f"BrowserAgent context info - user_id: {user_id}, workflow_id: {workflow_id}, step_id: {step_id}")

        # Generate hash for internal use (detecting if regeneration needed)
        # Note: Hash is no longer used in directory path
        content = f"browser_{task}_{json.dumps(xpath_hints, sort_keys=True)}"
        self._current_script_hash = hashlib.md5(content.encode()).hexdigest()[:8]

        # Build relative path - directly to step directory (no hash subdirectory)
        script_path = f"users/{user_id}/workflows/{workflow_id}/{step_id}"
        logger.debug(f"Generated script path: {script_path}")
        return script_path

    def _clear_fallback_mode(self, working_dir: Path) -> bool:
        """Clear .fallback_mode marker to force script regeneration.

        Use this when:
        - Page structure has changed and hint-based search might work now
        - User wants to retry script generation instead of LLM fallback

        Args:
            working_dir: Path to script directory (step directory)

        Returns:
            True if marker was cleared, False if it didn't exist
        """
        fallback_marker = working_dir / ".fallback_mode"
        if fallback_marker.exists():
            fallback_marker.unlink()
            logger.info(f"Cleared .fallback_mode marker in {working_dir}")
            return True
        return False

    def _is_cache_valid(self, working_dir: Path, task: str, xpath_hints: Dict[str, str]) -> bool:
        """Check if cached script is still valid.

        The cache is invalid if:
        1. task.json doesn't exist
        2. Task description differs (also clears .fallback_mode)
        3. xpath_hints KEYS differ (also clears .fallback_mode)
        4. .fallback_mode marker exists (LLM fallback required)

        Note: We only compare xpath_hints KEYS, not VALUES.
        This allows the same script to work with different xpath values
        in foreach loops where the xpath changes each iteration.

        When task or xpath_hints keys change, .fallback_mode is auto-cleared
        to give script generation a fresh chance.

        Args:
            working_dir: Path to script directory (step directory)
            task: Current task description
            xpath_hints: Current xpath hints

        Returns:
            True if cache is valid, False if regeneration needed
        """
        task_file = working_dir / "task.json"
        fallback_marker = working_dir / ".fallback_mode"

        if not task_file.exists():
            logger.debug("Cache invalid: task.json not found")
            # Clear fallback_mode for fresh start
            self._clear_fallback_mode(working_dir)
            return False

        try:
            saved_task = json.loads(task_file.read_text(encoding='utf-8'))

            # Compare task description
            saved_task_desc = saved_task.get('task', '')
            if task != saved_task_desc:
                logger.debug(f"Cache invalid: task changed")
                # Task changed - clear fallback_mode for fresh attempt
                self._clear_fallback_mode(working_dir)
                return False

            # Compare xpath_hints KEYS only (not values)
            # This allows same script to work with different xpath values in foreach
            saved_xpath_hints = saved_task.get('xpath_hints', {})
            current_keys = sorted(xpath_hints.keys())
            saved_keys = sorted(saved_xpath_hints.keys())

            if current_keys != saved_keys:
                logger.debug(f"Cache invalid: xpath_hints keys changed")
                # Keys changed - clear fallback_mode for fresh attempt
                self._clear_fallback_mode(working_dir)
                return False

            # Check fallback mode - if marked and task/keys unchanged, use LLM
            if fallback_marker.exists():
                logger.debug("Cache invalid: .fallback_mode marker exists (task unchanged)")
                return False

            return True

        except Exception as e:
            logger.warning(f"Cache validation failed: {e}")
            return False

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data

        New format (v2):
        - target_url: str (optional, if provided will navigate first)
        - interaction_steps: List[Dict] with task + xpath_hints
        - timeout: int (optional)

        Each interaction_step must have:
        - task: str (required) - Task description for LLM
        - xpath_hints: dict (required) - XPath hints to help locate element
        - text: str (optional) - Text for input operations

        Args:
            input_data: Input data (AgentInput or dict)

        Returns:
            bool: True if valid, False otherwise
        """
        from ..core.schemas import AgentInput

        if isinstance(input_data, AgentInput):
            actual_data = input_data.data
        elif isinstance(input_data, dict):
            actual_data = input_data
        else:
            logger.error("Validation failed: input_data must be AgentInput or dict")
            return False

        # At least one of target_url or interaction_steps must be present
        if 'target_url' not in actual_data and 'interaction_steps' not in actual_data:
            logger.error("Validation failed: must provide either 'target_url' or 'interaction_steps'")
            return False

        # Validate interaction_steps if present
        if 'interaction_steps' in actual_data:
            steps = actual_data['interaction_steps']
            if not isinstance(steps, list):
                logger.error("Validation failed: 'interaction_steps' must be a list")
                return False

            for idx, step in enumerate(steps):
                # Accept both new format (task + xpath_hints) and legacy format (action_type + parameters)
                has_new_format = 'task' in step
                has_legacy_format = 'action_type' in step

                if not has_new_format and not has_legacy_format:
                    logger.error(f"Validation failed: step {idx} must have either 'task' (new format) or 'action_type' (legacy format)")
                    return False

                # Validate new format
                if has_new_format:
                    if 'xpath_hints' not in step:
                        logger.error(f"Validation failed: step {idx} missing 'xpath_hints'")
                        return False

                    if not isinstance(step['xpath_hints'], dict):
                        logger.error(f"Validation failed: step {idx} 'xpath_hints' must be a dict")
                        return False

                # Legacy format will be converted in execute(), no additional validation needed

        return True

    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """Execute navigation and intelligent interactions

        Flow:
        1. Navigate to target_url (if provided)
        2. For each interaction_step:
           a. Get current DOM
           b. Generate operation script using LLM
           c. Execute the operation
           d. Get new DOM and verify success
        3. Return results

        Args:
            input_data: Input data (AgentInput or dict)
            context: Execution context

        Returns:
            AgentOutput with execution result
        """
        if not self.is_initialized:
            raise RuntimeError("BrowserAgent not initialized")

        from ..core.schemas import AgentInput, AgentOutput

        if isinstance(input_data, AgentInput):
            actual_data = input_data.data
        else:
            actual_data = input_data

        # Extract parameters
        target_url = actual_data.get('target_url')
        interaction_steps = actual_data.get('interaction_steps', [])
        timeout = actual_data.get('timeout', 60)

        logger.info(f"🌐 BrowserAgent executing: target_url={target_url}, "
                   f"interaction_steps={len(interaction_steps)}")

        try:
            steps_results = []

            # Track initial tabs for cleanup at end of workflow
            initial_tabs = await self._get_open_tabs()
            self._initial_tab_ids = {t['tab_id'] for t in initial_tabs}
            logger.info(f"📑 Initial tabs: {len(initial_tabs)} ({list(self._initial_tab_ids)})")

            # Step 1: Navigate to target URL if provided
            if target_url:
                nav_result = await self._navigate_to_url(target_url, context)
                if nav_result.get('success') is False:
                    return self._wrap_output(input_data, self._create_error_response(
                        f"Navigation failed: {nav_result.get('error')}"
                    ))

            # Step 2: Execute each interaction step
            for idx, step in enumerate(interaction_steps):
                # Handle legacy format (action_type + parameters) vs new format (task + xpath_hints)
                if 'action_type' in step:
                    # Legacy format - convert to new format
                    step = self._convert_legacy_step(step)

                task = step.get('task', '')
                xpath_hints = step.get('xpath_hints', {})
                text = step.get('text', '')
                action = step.get('action')  # Tab operations: new_tab, switch_tab, close_tab

                logger.info(f"📍 Step {idx + 1}/{len(interaction_steps)}: {task or action}")

                # Route tab operations via action field
                if action == 'new_tab':
                    url = step.get('url', '')
                    if not url:
                        step_result = {'success': False, 'error': 'new_tab action requires url'}
                    else:
                        step_result = await self._execute_new_tab(url, context)
                elif action == 'switch_tab':
                    tab_index = step.get('tab_index', 0)
                    step_result = await self._execute_switch_tab(tab_index, context)
                elif action == 'close_tab':
                    tab_index = step.get('tab_index')  # None = close current tab
                    step_result = await self._execute_close_tab(tab_index, context)
                else:
                    # Execute the intelligent interaction (click, fill, scroll, etc.)
                    step_result = await self._execute_intelligent_interaction(
                        task=task,
                        xpath_hints=xpath_hints,
                        text=text,
                        context=context,
                        max_retries=2
                    )

                step_info = {
                    'task': task,
                    'success': step_result['success'],
                    'verification': step_result.get('verification', ''),
                    'error': step_result.get('error', '')
                }
                # Include clipboard content if captured in this step
                if step_result.get('clipboard_content'):
                    step_info['clipboard_content'] = step_result['clipboard_content']
                steps_results.append(step_info)

                if not step_result['success']:
                    logger.error(f"❌ Step {idx + 1} failed: {step_result.get('error')}")
                    # Continue to next step or fail? For now, fail fast
                    return self._wrap_output(input_data, {
                        'success': False,
                        'message': f"Step {idx + 1} failed: {step_result.get('error')}",
                        'steps_results': steps_results,
                        'steps_executed': idx + 1
                    })

                logger.info(f"✅ Step {idx + 1} completed successfully")

                # Small delay between steps
                await asyncio.sleep(1)

            # Get current URL
            try:
                current_url = await self.browser_session.get_current_page_url() if self.browser_session else (target_url or "")
            except Exception:
                current_url = target_url or ""

            # Get current tab info for response
            current_tab_index = 0
            open_tabs_count = 1
            try:
                tabs = await self._get_open_tabs()
                open_tabs_count = len(tabs)
                # Find current tab index (the active one is typically the last accessed)
                if tabs:
                    current_page = await self.browser_session.get_current_page()
                    if current_page and hasattr(current_page, '_target_id'):
                        for i, tab in enumerate(tabs):
                            if tab['tab_id'] in current_page._target_id:
                                current_tab_index = i
                                break
            except Exception as e:
                logger.warning(f"Failed to get tab info: {e}")

            # Cleanup extra tabs (close tabs opened during workflow)
            try:
                await self._cleanup_extra_tabs()
            except Exception as e:
                logger.warning(f"Failed to cleanup extra tabs: {e}")

            # Success response
            message = f"All {len(interaction_steps)} interaction steps completed successfully"
            if target_url:
                message = f"Navigated to {target_url} and " + message.lower()

            logger.info(f"✅ {message}")

            return self._wrap_output(input_data, {
                'success': True,
                'message': message,
                'current_url': current_url,
                'steps_executed': len(interaction_steps),
                'steps_results': steps_results,
                'current_tab_index': current_tab_index,
                'open_tabs_count': open_tabs_count
            })

        except Exception as e:
            logger.error(f"❌ BrowserAgent execution failed: {e}")
            import traceback
            traceback.print_exc()

            return self._wrap_output(input_data, self._create_error_response(str(e)))

    async def _navigate_to_url(self, url: str, context: AgentContext) -> Dict:
        """Navigate to a URL

        Args:
            url: Target URL
            context: Agent context

        Returns:
            Dict with success status
        """
        try:
            logger.info(f"🔗 Navigating to: {url}")

            # Send log to frontend
            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "info",
                        f"🔗 Navigating to URL: {url}",
                        {"url": url}
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            # Use event system
            event = self.browser_session.event_bus.dispatch(
                NavigateToUrlEvent(url=url, new_tab=False)
            )
            await event
            result = await event.event_result(raise_if_any=False, raise_if_none=False)

            # Wait for page stability
            await asyncio.sleep(5)

            # Check for failure
            if result and hasattr(result, 'success') and result.success is False:
                logger.error(f"❌ Navigation failed: {result.error}")
                return {'success': False, 'error': result.error}

            logger.info(f"✅ Successfully navigated to {url}")
            return {'success': True}

        except Exception as e:
            logger.error(f"❌ Navigation failed: {e}")
            return {'success': False, 'error': str(e)}

    async def _execute_intelligent_interaction(
        self,
        task: str,
        xpath_hints: Dict[str, str],
        text: str,
        context: AgentContext,
        max_retries: int = 2
    ) -> Dict:
        """Execute an intelligent interaction with LLM-driven script generation

        Flow (v3.0 - simplified):
        1. Get current DOM and selector_map
        2. Call _generate_operation_script which handles:
           - Script generation/caching
           - Multi-round retry with Claude Agent feedback
           - Actual operation execution
        3. Return result

        Args:
            task: Task description
            xpath_hints: XPath hints for element location
            text: Text for input operations (optional)
            context: Agent context
            max_retries: Maximum retry attempts (used in _generate_and_execute_with_retry)

        Returns:
            Dict with success status and details
        """
        try:
            logger.info(f"🎯 Executing intelligent interaction: {task}")

            # Send log to frontend
            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "info",
                        f"🎯 Starting interaction: {task}",
                        {
                            "task": task,
                            "xpath_hints": xpath_hints,
                            "text": text[:50] if text else None
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            # Check if this is a simple scroll operation (doesn't need element finding)
            # vs scroll_to_element which needs Claude Agent to find element first
            task_lower = task.lower()
            is_scroll_keyword = any(word in task_lower for word in ['scroll', 'swipe', '滚动', '滑动'])
            is_scroll_to_element = any(phrase in task_lower for phrase in [
                'scroll to', 'scroll into', 'scroll until',
                '滚动到', '滑动到', '定位到'
            ]) and xpath_hints  # Has hints means we need to find element

            if is_scroll_keyword and not is_scroll_to_element:
                # Simple scroll - no element finding needed
                logger.info(f"📜 Detected simple scroll operation, executing directly...")
                op_result = await self._execute_scroll(text)
                if op_result.get('success'):
                    logger.info(f"⏳ Waiting 5 seconds for observation...")
                    await asyncio.sleep(5)
                return {
                    'success': op_result.get('success', False),
                    'error': op_result.get('error'),
                    'element_info': {'operation': 'scroll', 'direction': text}
                }

            # scroll_to_element - use Claude Agent to find xpath, then scroll
            # Different from click/fill which use interactive_index + selector_map
            if is_scroll_to_element:
                logger.info(f"📜 Detected scroll_to_element, using Claude Agent to find xpath...")
                op_result = await self._scroll_to_element_with_claude(task, xpath_hints, text, context)
                if op_result.get('success'):
                    logger.info(f"⏳ Waiting 5 seconds for observation...")
                    await asyncio.sleep(5)
                return {
                    'success': op_result.get('success', False),
                    'error': op_result.get('error'),
                    'element_info': op_result.get('element_info', {'operation': 'scroll_to_element'})
                }

            # Other operations (click, fill) continue to Claude Agent flow below

            # Step 1: Get current DOM and selector_map
            dom_dict, dom_llm, selector_map = await self._get_current_page_dom()

            if not dom_dict:
                return {'success': False, 'error': 'Failed to get DOM'}

            logger.info(f"📄 Got DOM: {len(selector_map)} interactive elements")

            # Step 2: Generate script and execute operation
            # This method handles everything:
            # - Caching check
            # - Claude Agent generation with multi-round feedback
            # - Operation execution
            result = await self._generate_operation_script(
                task=task,
                xpath_hints=xpath_hints,
                text=text,
                dom_dict=dom_dict,
                dom_llm=dom_llm,
                selector_map=selector_map,
                context=context
            )

            if result.get('success'):
                logger.info(f"✅ Interaction succeeded: {task}")
                response = {
                    'success': True,
                    'element_info': result.get('element_info', {}),
                    'interactive_index': result.get('interactive_index'),
                    'cached': result.get('cached', False),
                    'attempts': result.get('attempts', 1)
                }
                # Include clipboard content if captured
                if result.get('clipboard_content'):
                    response['clipboard_content'] = result['clipboard_content']
                return response
            else:
                logger.error(f"❌ Interaction failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown error'),
                    'element_info': result.get('element_info')
                }

        except Exception as e:
            logger.error(f"❌ Interaction exception: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    async def _get_current_page_dom(self) -> tuple:
        """Get DOM from current page

        Reuses ScraperAgent's DOM extraction logic.

        Returns:
            tuple: (dom_dict, llm_view, selector_map)
                - dom_dict: nested dictionary of DOM structure
                - llm_view: compact JSON string for LLM
                - selector_map: maps interactive_index -> EnhancedDOMTreeNode (for backend_node_id)
        """
        try:
            from browser_use.browser.events import BrowserStateRequestEvent
            from ..tools.browser_use.dom_extractor import DOMExtractor, extract_llm_view

            if not self.browser_session:
                raise RuntimeError("Browser session is None")

            # Wait for page stability
            logger.info("Waiting for page to stabilize...")
            await asyncio.sleep(3)

            # Request DOM
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
                logger.warning("Enhanced DOM is None")
                return {}, "", {}

            # Extract DOM using DOMExtractor
            extractor = DOMExtractor()
            serialized_dom, _ = extractor.serialize_accessible_elements_custom(
                enhanced_dom, include_non_visible=True
            )
            dom_dict = extractor.extract_dom_dict(serialized_dom)
            llm_view = extract_llm_view(dom_dict, include_xpath=True)

            # Get selector_map for interactive_index -> backend_node_id conversion
            selector_map = serialized_dom.selector_map

            logger.info(f"📄 Got DOM: {len(llm_view)} chars, {len(selector_map)} interactive elements")
            return dom_dict, llm_view, selector_map

        except Exception as e:
            logger.error(f"Failed to get DOM: {e}")
            import traceback
            traceback.print_exc()
            return {}, "", {}

    async def _save_dom_data(self, working_dir: Path, dom_dict: Dict) -> None:
        """Save DOM data to file in wrapped format.

        All DOM data is saved in wrapped format: {"url": "...", "dom": {...}}
        This is the standard format used throughout the codebase.

        Args:
            working_dir: Directory to save dom_data.json
            dom_dict: DOM dictionary to save
        """
        try:
            # Get current page URL
            page_url = "unknown"
            if self.browser_session:
                try:
                    page_url = await self.browser_session.get_current_page_url()
                except Exception:
                    pass

            # Wrap DOM in standard format
            wrapped_dom = {
                "url": page_url,
                "dom": dom_dict
            }

            dom_file = working_dir / "dom_data.json"
            dom_file.write_text(
                json.dumps(wrapped_dom, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception as e:
            logger.warning(f"Failed to save dom_data.json: {e}")

    async def _generate_operation_script(
        self,
        task: str,
        xpath_hints: Dict[str, str],
        text: str,
        dom_dict: Dict,
        dom_llm: str,
        selector_map: Dict = None,
        context: AgentContext = None
    ) -> Dict:
        """Generate operation script using Claude Agent SDK with file-based caching

        Similar to ScraperAgent:
        1. Check if cached script exists
        2. If cached, load and execute directly
        3. If not cached, generate with Claude Agent SDK
        4. Save script and selector_map for future reuse

        Args:
            task: Task description
            xpath_hints: XPath hints
            text: Text for input operations
            dom_dict: DOM dictionary
            dom_llm: LLM-friendly DOM representation (unused, Claude reads from file)
            selector_map: Maps interactive_index to EnhancedDOMTreeNode (for backend_node_id)
            context: Agent context for log_callback

        Returns:
            Dict with operation info including interactive_index
        """
        try:
            # Determine operation type from task
            # Note: scroll_to_element is handled separately in _execute_intelligent_interaction
            #       via _scroll_to_element_by_xpath (direct CDP, no Claude Agent)
            task_lower = task.lower()
            if any(word in task_lower for word in ['fill', 'input', 'type', 'enter', 'write']):
                operation = 'fill'
            elif any(word in task_lower for word in ['scroll', 'swipe', '滚动', '滑动']):
                operation = 'scroll'
            else:
                operation = 'click'

            # 1. Generate script key and create working directory
            if not self.config_service:
                raise RuntimeError("ConfigService not available - required for Ami Coder")

            script_key = self._generate_script_key(task, xpath_hints)
            scripts_root = self.config_service.get_path("data.scripts")
            working_dir = scripts_root / script_key
            working_dir.mkdir(parents=True, exist_ok=True)

            script_file = working_dir / "find_element.py"

            logger.info(f"BrowserAgent script workspace: {working_dir}")

            # 2. Check if cached script exists and is still valid BEFORE preparing workspace
            cache_valid = script_file.exists() and self._is_cache_valid(working_dir, task, xpath_hints)

            if cache_valid:
                # Cache hit: only update DOM, preserve task.json and templates
                logger.info(f"✅ Found cached script: {script_file}")
                script_content = script_file.read_text(encoding='utf-8')

                # Send cache hit log to frontend (like ScraperAgent)
                if context and context.log_callback:
                    try:
                        await context.log_callback(
                            "info",
                            f"✅ Using cached element finder script ({len(script_content)} chars)",
                            {
                                "cache_path": str(script_file),
                                "script_content": script_content,
                                "content_type": "code",
                                "language": "python"
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send log callback: {e}")

                # Only update DOM for current page (wrapped format), don't overwrite task.json
                await self._save_dom_data(working_dir, dom_dict)
            else:
                # Cache miss: prepare full workspace
                if script_file.exists():
                    logger.info(f"🔄 Cache invalidated: task or xpath_hints keys changed, regenerating script")
                await self._prepare_workspace(working_dir, task, operation, xpath_hints, text, dom_dict)

            if cache_valid:

                # Get xpath from xpath_hints for dynamic element finding
                runtime_xpath = list(xpath_hints.values())[0] if xpath_hints else ""

                # Try executing cached script with LLM fallback support
                find_result = await self._find_element_with_fallback(
                    script_content, dom_dict, runtime_xpath, task, working_dir
                )

                if find_result.get('success'):
                    interactive_index = find_result.get('interactive_index')
                    logger.info(f"📍 Cached script found element: interactive_index={interactive_index}")

                    # Convert and execute operation
                    original_node = selector_map.get(interactive_index)
                    if original_node:
                        backend_node_id = getattr(original_node, 'backend_node_id', None)
                        if backend_node_id:
                            logger.info(f"🎯 Executing cached operation: {operation}")
                            op_result = await self._execute_element_operation(
                                backend_node_id=backend_node_id,
                                operation=operation,
                                text=text,
                                context=context
                            )
                            if op_result.get('success'):
                                logger.info(f"⏳ Waiting 5 seconds for observation...")
                                await asyncio.sleep(5)
                                result = {
                                    'success': True,
                                    'interactive_index': interactive_index,
                                    'backend_node_id': backend_node_id,
                                    'element_info': find_result.get('element_info', {}),
                                    'cached': True
                                }
                                # Include clipboard content if captured
                                if op_result.get('clipboard_content'):
                                    result['clipboard_content'] = op_result['clipboard_content']
                                return result
                            else:
                                logger.warning(f"⚠️ Cached script operation failed: {op_result.get('error')}")
                        else:
                            logger.warning(f"⚠️ No backend_node_id for interactive_index {interactive_index}")
                    else:
                        logger.warning(f"⚠️ interactive_index {interactive_index} not in selector_map")

                # Cached script failed (find or execute), regenerate
                logger.info(f"   Cached script didn't work, regenerating with Claude Agent...")
                if context and context.log_callback:
                    try:
                        await context.log_callback(
                            "warning",
                            "⚠️ Cached script didn't work, regenerating with Ami Coder...",
                            {"reason": "cache_miss_or_failed"}
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send log callback: {e}")
            else:
                # No cached script found
                if context and context.log_callback:
                    try:
                        await context.log_callback(
                            "info",
                            "📝 No cached script found, generating new element finder script...",
                            {"script_path": str(script_file)}
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send log callback: {e}")

            # 4. Generate new script with multi-round interaction
            logger.info(f"📝 Generating find_element.py with Claude Agent...")

            result = await self._generate_and_execute_with_retry(
                working_dir=working_dir,
                task=task,
                operation=operation,
                text=text,
                selector_map=selector_map,
                max_attempts=3,
                context=context
            )

            return result

        except Exception as e:
            logger.error(f"Failed to generate operation script: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    async def _prepare_workspace(
        self,
        working_dir: Path,
        task: str,
        operation: str,
        xpath_hints: Dict[str, str],
        text: str,
        dom_dict: Dict
    ) -> None:
        """Prepare workspace with preset templates and input files

        Creates:
        - test_operation.py (preset template)
        - find_element_template.py (preset template)
        - task.json (task description)
        - dom_data.json (current page DOM)

        Args:
            working_dir: Working directory path
            task: Task description
            operation: Operation type (click/fill)
            xpath_hints: XPath hints
            text: Text for fill operation
            dom_dict: DOM dictionary
        """
        # 1. Save preset templates (imported from src.common.script_generation.templates)
        test_file = working_dir / "test_operation.py"
        test_file.write_text(BROWSER_TEST_OPERATION, encoding='utf-8')

        template_file = working_dir / "find_element_template.py"
        template_file.write_text(BROWSER_FIND_ELEMENT_TEMPLATE, encoding='utf-8')

        logger.debug(f"Preset templates saved: test_operation.py, find_element_template.py")

        # 2. Save task.json
        task_file = working_dir / "task.json"
        task_data = {
            "task": task,
            "operation": operation,
            "xpath_hints": xpath_hints,
            "text": text if text else None
        }
        task_file.write_text(
            json.dumps(task_data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

        # 3. Save dom_data.json (use _save_dom_data for consistent wrapped format)
        await self._save_dom_data(working_dir, dom_dict)

        # Note: .claude/skills is prepared by Cloud during script generation
        # element_tools.py is downloaded after script generation

        dom_file = working_dir / "dom_data.json"
        logger.info(f"Workspace prepared: task.json, dom_data.json ({dom_file.stat().st_size} bytes)")

    async def _generate_and_execute_with_retry(
        self,
        working_dir: Path,
        task: str,
        operation: str,
        text: str,
        selector_map: Dict,
        max_attempts: int = 3,
        context: AgentContext = None
    ) -> Dict:
        """Multi-round interaction: Claude Agent generates script, BrowserAgent executes, feedback loop

        Flow:
        1. Claude Agent generates find_element.py
        2. BrowserAgent executes the script to get interactive_index
        3. BrowserAgent converts to backend_node_id and executes click/fill
        4. If failed, update DOM and feedback to Claude Agent for retry
        5. Repeat until success or max_attempts reached

        Args:
            working_dir: Working directory with all files
            task: Task description
            operation: Operation type (click/fill)
            text: Text for fill operation
            selector_map: Maps interactive_index to backend_node_id
            max_attempts: Maximum retry attempts
            context: Agent context for log_callback

        Returns:
            Dict with success status and details
        """
        feedback = ""  # Feedback from previous round

        for attempt in range(max_attempts):
            logger.info(f"🔄 Attempt {attempt + 1}/{max_attempts} for task: {task}")

            try:
                # 1. Call Claude Agent to generate/fix find_element.py
                claude_result = await self._call_claude_for_find_element(
                    working_dir=working_dir,
                    task=task,
                    operation=operation,
                    text=text,
                    feedback=feedback,
                    context=context
                )

                if not claude_result.get('success'):
                    feedback = f"Ami Coder failed: {claude_result.get('error')}"
                    logger.warning(f"⚠️ {feedback}")
                    continue

                # 2. Read and execute find_element.py
                script_file = working_dir / "find_element.py"
                if not script_file.exists():
                    feedback = "find_element.py was not created"
                    logger.warning(f"⚠️ {feedback}")
                    continue

                script_content = script_file.read_text(encoding='utf-8')
                # DOM files use wrapped format: {"url": ..., "dom": {...}}
                dom_data = json.loads((working_dir / "dom_data.json").read_text(encoding='utf-8'))
                dom_dict = dom_data.get("dom", dom_data)  # Unwrap, fallback to direct format for compatibility

                # Get xpath from task.json for dynamic element finding
                task_data = json.loads((working_dir / "task.json").read_text(encoding='utf-8'))
                xpath_hints_from_file = task_data.get("xpath_hints", {})
                runtime_xpath = list(xpath_hints_from_file.values())[0] if xpath_hints_from_file else ""

                # Execute with LLM fallback support
                find_result = await self._find_element_with_fallback(
                    script_content, dom_dict, runtime_xpath, task, working_dir
                )

                if not find_result.get('success'):
                    feedback = f"find_element.py execution failed: {find_result.get('error')}"
                    logger.warning(f"⚠️ {feedback}")
                    continue

                interactive_index = find_result.get('interactive_index')
                logger.info(f"📍 Found element: interactive_index={interactive_index}")

                # 3. Convert interactive_index to backend_node_id
                original_node = selector_map.get(interactive_index)
                if not original_node:
                    feedback = f"interactive_index {interactive_index} not found in selector_map"
                    logger.warning(f"⚠️ {feedback}")
                    # Update DOM and retry
                    await self._refresh_dom_file(working_dir)
                    continue

                backend_node_id = getattr(original_node, 'backend_node_id', None)
                if not backend_node_id:
                    feedback = f"No backend_node_id for interactive_index {interactive_index}"
                    logger.warning(f"⚠️ {feedback}")
                    continue

                logger.info(f"🎯 Converted: interactive_index={interactive_index} → backend_node_id={backend_node_id}")

                # 4. Execute the actual browser operation
                op_result = await self._execute_element_operation(
                    backend_node_id=backend_node_id,
                    operation=operation,
                    text=text,
                    context=context
                )

                if op_result.get('success'):
                    logger.info(f"✅ Operation '{operation}' succeeded!")
                    logger.info(f"⏳ Waiting 5 seconds for observation...")
                    await asyncio.sleep(5)
                    result = {
                        'success': True,
                        'interactive_index': interactive_index,
                        'backend_node_id': backend_node_id,
                        'element_info': find_result.get('element_info', {}),
                        'attempts': attempt + 1
                    }
                    # Include clipboard content if captured
                    if op_result.get('clipboard_content'):
                        result['clipboard_content'] = op_result['clipboard_content']
                    return result

                # 5. Operation failed - refresh DOM and prepare feedback
                error_msg = op_result.get('error', 'Unknown error')
                logger.warning(f"⚠️ Operation failed: {error_msg}")

                # Refresh DOM file for next attempt
                new_dom, _, new_selector_map = await self._get_current_page_dom()
                selector_map = new_selector_map  # Update selector_map for next attempt

                await self._save_dom_data(working_dir, new_dom)

                feedback = f"""
## Previous Attempt Failed
- Found interactive_index: {interactive_index}
- Operation: {operation}
- Error: {error_msg}

The dom_data.json has been updated with the latest DOM after the failed operation.
Please analyze and fix find_element.py.
"""

            except Exception as e:
                feedback = f"Exception during attempt: {str(e)}"
                logger.error(f"❌ {feedback}")
                import traceback
                traceback.print_exc()

        return {
            'success': False,
            'error': f'Failed after {max_attempts} attempts. Last feedback: {feedback}'
        }

    async def _call_claude_for_find_element(
        self,
        working_dir: Path,
        task: str,
        operation: str,
        text: str,
        feedback: str = "",
        context: AgentContext = None
    ) -> Dict:
        """Call cloud API to generate find_element.py for click/fill operations

        Args:
            working_dir: Working directory
            task: Task description
            operation: Operation type
            text: Text for fill operation
            feedback: Feedback from previous attempt (if any)
            context: Agent context for log_callback

        Returns:
            Dict with success status
        """
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

            # 3. Get API key from provider
            api_key = None
            if self.provider and hasattr(self.provider, 'api_key') and self.provider.api_key:
                api_key = self.provider.api_key
                logger.info(f"Got API key from provider for cloud script generation")

            # 4. Read DOM data from working directory (wrapped format: {"url": ..., "dom": {...}})
            dom_file = working_dir / "dom_data.json"
            if not dom_file.exists():
                raise RuntimeError(f"dom_data.json not found in {working_dir}")

            dom_data = json.loads(dom_file.read_text(encoding='utf-8'))

            # 5. Get page URL from wrapped DOM format
            page_url = dom_data.get('url', '')

            logger.info(f"Requesting cloud browser script generation: workflow={workflow_id}, step={step_id}")
            logger.info(f"  Task: {task}")
            logger.info(f"  Operation: {operation}")

            # Progress update ID for dynamic log updates
            progress_update_id = f"browser_script_generation_{id(self)}_{task[:20]}"

            # Send initial log to frontend
            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "info",
                        f"📡 Requesting element finder script from cloud...",
                        {
                            "update_id": progress_update_id,
                            "task": task,
                            "operation": operation,
                            "workflow_id": workflow_id,
                            "step_id": step_id
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            # 6. Call cloud API to generate script with SSE streaming
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
                script_type="browser",
                page_url=page_url,
                user_id=user_id,
                api_key=api_key,
                dom_data=dom_data,  # Browser scripts need runtime DOM
                progress_callback=script_progress_callback
            )

            if not result.get('success'):
                error_msg = result.get('error', 'Unknown error')
                raise RuntimeError(f"Cloud script generation failed: {error_msg}")

            script_content = result.get('script_content', '')
            turns = result.get('turns', 0)

            logger.info(f"✅ Cloud browser script generation completed in {turns} turns")
            logger.info(f"   Script size: {len(script_content)} chars")

            # 7. Save script to working directory
            script_file = working_dir / "find_element.py"
            script_file.write_text(script_content, encoding='utf-8')
            logger.info(f"   Saved to: {script_file}")

            # 8. Download element_tools.py from cloud (required for script execution)
            try:
                element_tools_content = await cloud_client.download_workflow_file(
                    workflow_id=workflow_id,
                    file_path=f"{step_id}/element_tools.py",
                    user_id=user_id
                )
                element_tools_file = working_dir / "element_tools.py"
                element_tools_file.write_bytes(element_tools_content)
                logger.info(f"   Downloaded element_tools.py to: {element_tools_file}")
            except Exception as e:
                logger.warning(f"   Failed to download element_tools.py: {e}")

            # Send completion status
            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "success",
                        f"✅ Element finder script generated ({turns} turns)",
                        {
                            "update_id": progress_update_id,
                            "turn": turns,
                            "completed": True
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to send completion log: {e}")

            return {'success': True}

        except Exception as e:
            logger.error(f"Cloud script generation failed: {e}")
            return {'success': False, 'error': str(e)}

    async def _refresh_dom_file(self, working_dir: Path) -> Dict:
        """Refresh dom_data.json with current page DOM

        Args:
            working_dir: Working directory

        Returns:
            New selector_map
        """
        new_dom, _, new_selector_map = await self._get_current_page_dom()
        await self._save_dom_data(working_dir, new_dom)
        logger.info(f"📄 Refreshed dom_data.json")
        return new_selector_map

    def _execute_find_element_script(self, code: str, dom_dict: Dict, xpath: str = "", script_dir: Path = None) -> Dict:
        """Execute find_element.py to get target element info

        Args:
            code: Generated Python code
            dom_dict: DOM dictionary
            xpath: Runtime xpath from xpath_hints (for dynamic element finding)
            script_dir: Directory containing element_tools.py (synced from cloud)

        Returns:
            Dict with success, interactive_index, element_info
        """
        try:
            # Import analyze_xpath_hint from element_tools
            # element_tools.py is synced from cloud to script_dir
            import importlib.util
            import sys

            if not script_dir:
                return {'success': False, 'error': 'script_dir not provided'}

            element_tools_path = Path(script_dir) / "element_tools.py"
            if not element_tools_path.exists():
                return {'success': False, 'error': f'element_tools.py not found at {element_tools_path}'}

            spec = importlib.util.spec_from_file_location("element_tools", element_tools_path)
            element_tools = importlib.util.module_from_spec(spec)
            sys.modules["element_tools"] = element_tools
            spec.loader.exec_module(element_tools)
            analyze_xpath_hint = element_tools.analyze_xpath_hint

            # Create execution environment with injected functions
            exec_env = {
                'dom_dict': dom_dict,
                'xpath': xpath,
                'analyze_xpath_hint': analyze_xpath_hint,  # Inject for script use
                'json': json,
            }

            # Execute the code
            exec(code, exec_env, exec_env)

            # Call the function with xpath parameter
            find_target_element = exec_env.get('find_target_element')
            if not find_target_element:
                return {'success': False, 'error': 'Script missing find_target_element function'}

            # New signature: find_target_element(dom_dict, xpath)
            try:
                result = find_target_element(dom_dict, xpath)
            except TypeError as e:
                # Fallback for old signature without xpath parameter
                if "positional argument" in str(e) or "unexpected keyword" in str(e):
                    logger.warning(f"Script uses old signature, calling without xpath: {e}")
                    result = find_target_element(dom_dict)
                else:
                    raise

            return result

        except Exception as e:
            logger.error(f"Failed to execute find_element.py: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': f'Script execution failed: {str(e)}'}

    async def _llm_find_element(
        self,
        dom_dict: Dict,
        xpath: str,
        task: str,
        working_dir: Path = None
    ) -> Dict:
        """Use LLM to directly analyze DOM and find the target interactive element.

        This is the fallback method when hint-based script fails.
        It consumes LLM tokens on each call but can handle complex scenarios.

        Args:
            dom_dict: DOM dictionary
            xpath: XPath hint for the element
            task: Task description
            working_dir: Working directory (for creating .fallback_mode marker)

        Returns:
            Dict with success, interactive_index, element_info
        """
        try:
            if not self.provider:
                return {'success': False, 'error': 'No LLM provider available for fallback'}

            # Truncate DOM to avoid token limit
            dom_str = json.dumps(dom_dict, ensure_ascii=False)
            if len(dom_str) > 50000:
                dom_str = dom_str[:50000] + "\n... (truncated)"

            prompt = f"""# Find Interactive Element

## Task
{task}

## XPath Hint
{xpath}

## Instructions
Analyze the DOM below and find the target element that matches the task and xpath hint.
Return ONLY the interactive_index (integer) of the element to click/fill.

**CRITICAL**: Only elements with `interactive_index` can be clicked or filled.

Look for:
1. Element at or near the xpath hint location
2. Element matching the task description (text, aria-label, class, etc.)
3. Element with a valid `interactive_index`

## Response Format
Return a JSON object with:
- interactive_index: The integer index of the target element
- reason: Brief explanation of why this element was chosen

Example: {{"interactive_index": 42, "reason": "Button with text 'Submit' near the xpath hint"}}

## DOM Structure
{dom_str}
"""

            logger.info(f"🤖 LLM Fallback: Analyzing DOM for element (task={task[:50]}...)")

            response = await self.provider.generate_response(
                system_prompt="You are a DOM analysis expert. Find the target interactive element and return its interactive_index as JSON.",
                user_prompt=prompt
            )

            logger.info(f"🤖 LLM response: {response[:200]}...")

            # Parse response to extract interactive_index
            try:
                import re

                # Strategy 1: Try to parse JSON object with interactive_index
                json_match = re.search(r'\{[^}]+\}', response)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                        interactive_index = result.get('interactive_index')
                        reason = result.get('reason', '')

                        if interactive_index is not None and isinstance(interactive_index, int):
                            logger.info(f"🤖 LLM found element: interactive_index={interactive_index}, reason={reason}")
                            return {
                                'success': True,
                                'interactive_index': interactive_index,
                                'element_info': {
                                    'llm_reason': reason,
                                    'xpath_hint': xpath
                                }
                            }
                    except json.JSONDecodeError:
                        pass  # JSON parsing failed, try other strategies

                # Strategy 2: Look for explicit "interactive_index": <number> or "interactive_index: <number>" pattern
                # This is more reliable than grabbing any number
                index_pattern = re.search(r'interactive_index["\s:]+(\d+)', response, re.IGNORECASE)
                if index_pattern:
                    interactive_index = int(index_pattern.group(1))
                    logger.info(f"🤖 LLM: Found explicit interactive_index pattern: {interactive_index}")
                    return {
                        'success': True,
                        'interactive_index': interactive_index,
                        'element_info': {
                            'llm_raw_response': response[:200],
                            'xpath_hint': xpath
                        }
                    }

                # Strategy 3 (last resort): If response is very short and contains only a number
                # This handles cases where LLM just returns "42"
                stripped = response.strip()
                if stripped.isdigit() and len(stripped) <= 5:
                    interactive_index = int(stripped)
                    logger.warning(f"🤖 LLM: Response was just a number: {interactive_index}")
                    return {
                        'success': True,
                        'interactive_index': interactive_index,
                        'element_info': {
                            'llm_raw_response': response[:200],
                            'xpath_hint': xpath
                        }
                    }

                return {'success': False, 'error': f'LLM response did not contain valid interactive_index: {response[:200]}'}

            except Exception as parse_error:
                logger.error(f"Failed to parse LLM response: {parse_error}")
                return {'success': False, 'error': f'Failed to parse LLM response: {parse_error}'}

        except Exception as e:
            logger.error(f"LLM fallback failed: {e}")
            return {'success': False, 'error': f'LLM fallback failed: {str(e)}'}

    async def _find_element_with_fallback(
        self,
        script_content: str,
        dom_dict: Dict,
        xpath: str,
        task: str,
        working_dir: Path
    ) -> Dict:
        """Execute script with LLM fallback if script fails.

        Args:
            script_content: The find_element.py script content
            dom_dict: DOM dictionary
            xpath: XPath hint
            task: Task description
            working_dir: Working directory

        Returns:
            Dict with success, interactive_index, element_info
        """
        fallback_marker = working_dir / ".fallback_mode"

        # Check if already in fallback mode
        if fallback_marker.exists():
            logger.info(f"🤖 Fallback mode: Using LLM directly")
            return await self._llm_find_element(dom_dict, xpath, task, working_dir)

        # Try script first (working_dir contains element_tools.py synced from cloud)
        script_result = self._execute_find_element_script(script_content, dom_dict, xpath, script_dir=working_dir)

        if script_result.get('success'):
            return script_result

        # Check if script returned "fallback required" error
        error = script_result.get('error', '')
        if 'fallback' in error.lower():
            logger.info(f"🤖 Script returned fallback required, marking for LLM mode")
            # Create fallback marker
            fallback_marker.touch()
            # Use LLM fallback
            return await self._llm_find_element(dom_dict, xpath, task, working_dir)

        # Script failed but not fallback case - return the error
        return script_result

    def _find_xpath_by_interactive_index(self, dom_dict: Dict, target_index: int) -> Optional[str]:
        """Find xpath in dom_dict by interactive_index.

        Since selector_map nodes don't have xpath attribute, we need to search
        the dom_dict which contains xpath for each element.

        Args:
            dom_dict: DOM dictionary from _get_current_page_dom
            target_index: The interactive_index to find

        Returns:
            xpath string if found, None otherwise
        """
        def search_node(node: Dict) -> Optional[str]:
            if not isinstance(node, dict):
                return None

            # Check if this node has the target interactive_index
            if node.get('interactive_index') == target_index:
                return node.get('xpath')

            # Recursively search children
            children = node.get('children', [])
            if isinstance(children, list):
                for child in children:
                    result = search_node(child)
                    if result:
                        return result

            return None

        return search_node(dom_dict)

    async def _execute_element_operation(
        self,
        backend_node_id: int,
        operation: str,
        text: str = '',
        context: AgentContext = None
    ) -> Dict:
        """Execute an operation on an element

        Supported operations:
        - click: Click the element
        - fill: Fill text into the element
        - scroll: Scroll page (no element needed)

        Note: scroll_to_element is handled separately via _scroll_to_element_by_xpath
              because it may target non-interactive elements.

        Args:
            backend_node_id: CDP backend node ID
            operation: Operation type ('click', 'fill', or 'scroll')
            text: Text for fill operation, or scroll direction for scroll ('up'/'down')
            context: Agent context for log_callback

        Returns:
            Dict with success status
        """
        try:
            logger.info(f"🎯 Executing {operation} on element (backend_node_id={backend_node_id})")

            # Send log to frontend
            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "info",
                        f"🎯 Executing {operation} operation...",
                        {
                            "operation": operation,
                            "backend_node_id": backend_node_id,
                            "text": text[:50] if text and operation == 'fill' else None
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            # Get session_id from current page's CDP session
            session_id = None
            page = await self.browser_session.get_current_page()
            if page:
                cdp_session = await self.browser_session.get_or_create_cdp_session(page._target_id)
                session_id = cdp_session.session_id
                logger.debug(f"   Got session_id: {session_id}")
            else:
                logger.warning("   No current page found, session_id is None")

            # Handle simple scroll operation (may not need backend_node_id)
            if operation == 'scroll':
                return await self._execute_scroll(text)

            # For click/fill, we need backend_node_id
            if not backend_node_id:
                return {'success': False, 'error': 'No backend_node_id provided'}

            # Create Element object for click/fill
            element = Element(
                browser_session=self.browser_session,
                backend_node_id=backend_node_id,
                session_id=session_id
            )

            # Track clipboard content for click operations
            clipboard_content = None

            if operation == 'click':
                # Read clipboard before click to detect if click triggers clipboard write
                clipboard_before = await self._read_clipboard_silent()
                logger.info(f"📋 Clipboard BEFORE click: '{clipboard_before[:100] if clipboard_before else '(empty)'}...'")

                await element.click()
                logger.info(f"✅ Click executed successfully")

                # Read clipboard after click and check if it changed
                # Wait longer for clipboard to be written (some sites have async clipboard operations)
                await asyncio.sleep(1.0)
                clipboard_after = await self._read_clipboard_silent()
                logger.info(f"📋 Clipboard AFTER click: '{clipboard_after[:100] if clipboard_after else '(empty)'}...'")

                if clipboard_after and clipboard_after != clipboard_before:
                    logger.info(f"📋 Clipboard changed after click: {clipboard_after[:50]}...")
                    clipboard_content = clipboard_after
                    # Save to context variables dict if available
                    if self._context:
                        self._context.variables['_last_clipboard_content'] = clipboard_after
                        logger.info(f"   Saved to context variable: _last_clipboard_content")
                else:
                    before_preview = clipboard_before[:30] if clipboard_before else "(empty)"
                    after_preview = clipboard_after[:30] if clipboard_after else "(empty)"
                    logger.warning(f"📋 Clipboard NOT changed. before='{before_preview}', after='{after_preview}'")
            elif operation == 'fill':
                await element.fill(text, clear=True)
                logger.info(f"✅ Fill executed successfully with text: {text[:50]}...")

                # Send success log to frontend
                if context and context.log_callback:
                    try:
                        await context.log_callback(
                            "success",
                            f"✅ Fill operation completed: '{text[:30]}...'",
                            {"operation": "fill", "text_length": len(text)}
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send log callback: {e}")
            else:
                return {'success': False, 'error': f'Unknown operation: {operation}'}

            # Send general success log for click operation
            if operation == 'click' and context and context.log_callback:
                try:
                    log_metadata = {"operation": "click", "backend_node_id": backend_node_id}
                    if clipboard_content:
                        log_metadata["clipboard_content"] = clipboard_content[:100] + "..." if len(clipboard_content) > 100 else clipboard_content
                    await context.log_callback(
                        "success",
                        f"✅ Click operation completed" + (f" (clipboard captured: {len(clipboard_content)} chars)" if clipboard_content else ""),
                        log_metadata
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            # Return success with clipboard content if captured
            result = {'success': True}
            if clipboard_content:
                result['clipboard_content'] = clipboard_content
            return result

        except Exception as e:
            logger.error(f"Failed to execute element operation: {e}")
            import traceback
            traceback.print_exc()

            # Send error log to frontend
            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "error",
                        f"❌ Operation failed: {str(e)[:100]}",
                        {"operation": operation, "error": str(e)}
                    )
                except Exception as log_e:
                    logger.warning(f"Failed to send error log callback: {log_e}")

            return {'success': False, 'error': str(e)}

    async def _read_clipboard_silent(self) -> str:
        """Read clipboard content from interceptor

        Reads from window.__interceptedClipboard which is set by automation_hooks.js
        when any page calls navigator.clipboard.writeText() or execCommand('copy').

        Returns:
            str: Clipboard text content, or empty string if not available
        """
        try:
            page = await self.browser_session.get_current_page()
            if page:
                js_code = "() => window.__interceptedClipboard || ''"
                clipboard_text = await page.evaluate(js_code)
                if clipboard_text:
                    logger.debug(f"Clipboard read via interceptor: {len(clipboard_text)} chars")
                    return clipboard_text
        except Exception as e:
            logger.debug(f"Clipboard read failed: {e}")

        return ""

    async def _execute_scroll(self, direction: str = 'down') -> Dict:
        """Execute scroll operation on the page

        Args:
            direction: Scroll direction ('up', 'down', or pixel amount as string)
                      Positive number = scroll down, negative = scroll up

        Returns:
            Dict with success status
        """
        try:
            # Determine scroll direction and amount
            direction_lower = (direction or 'down').lower().strip()

            if direction_lower in ['up', '上', '向上']:
                scroll_direction = 'up'
                scroll_amount = 500
            elif direction_lower in ['down', '下', '向下']:
                scroll_direction = 'down'
                scroll_amount = 500
            else:
                # Try to parse as integer (pixel amount)
                try:
                    pixel_value = int(direction)
                    if pixel_value < 0:
                        scroll_direction = 'up'
                        scroll_amount = abs(pixel_value)
                    else:
                        scroll_direction = 'down'
                        scroll_amount = pixel_value if pixel_value > 0 else 500
                except ValueError:
                    # Default to scroll down
                    scroll_direction = 'down'
                    scroll_amount = 500

            logger.info(f"📜 Scrolling {scroll_direction} by {scroll_amount} pixels")

            # Use ScrollEvent from browser-use (requires direction and amount)
            event = self.browser_session.event_bus.dispatch(
                ScrollEvent(direction=scroll_direction, amount=scroll_amount)
            )
            await event
            await event.event_result(raise_if_any=False, raise_if_none=False)

            logger.info(f"✅ Scroll executed successfully")
            return {'success': True}

        except Exception as e:
            logger.error(f"Failed to execute scroll: {e}")
            return {'success': False, 'error': str(e)}

    # ==========================================================================
    # Tab Operations: new_tab, switch_tab, close_tab
    # ==========================================================================

    async def _get_open_tabs(self) -> List[Dict]:
        """Get list of open tabs

        Returns:
            List of tab info dicts: [{'tab_id': str, 'url': str, 'title': str}, ...]
        """
        try:
            tabs = await self.browser_session.get_tabs()
            return [
                {
                    'tab_id': t.target_id[-8:] if t.target_id else '',  # Last 8 chars for readability
                    'full_target_id': t.target_id,
                    'url': t.url or '',
                    'title': t.title or ''
                }
                for t in tabs
            ]
        except Exception as e:
            logger.error(f"Failed to get tabs: {e}")
            return []

    async def _execute_new_tab(self, url: str, context: AgentContext = None) -> Dict:
        """Open URL in new tab

        Args:
            url: URL to open in new tab
            context: Agent context for logging

        Returns:
            Dict with success status and tab info
        """
        try:
            logger.info(f"📑 Opening new tab: {url}")

            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "info",
                        f"📑 Opening new tab: {url}",
                        {"url": url, "action": "new_tab"}
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            # Use NavigateToUrlEvent with new_tab=True
            event = self.browser_session.event_bus.dispatch(
                NavigateToUrlEvent(url=url, new_tab=True)
            )
            await event
            result = await event.event_result(raise_if_any=False, raise_if_none=False)

            # Wait for page stability
            await asyncio.sleep(3)

            # Check for failure
            if result and hasattr(result, 'success') and result.success is False:
                logger.error(f"❌ New tab failed: {result.error}")
                return {'success': False, 'error': result.error}

            logger.info(f"✅ New tab opened successfully: {url}")
            return {'success': True, 'url': url}

        except Exception as e:
            logger.error(f"Failed to open new tab: {e}")
            return {'success': False, 'error': str(e)}

    async def _execute_switch_tab(self, tab_index: int, context: AgentContext = None) -> Dict:
        """Switch to tab by index

        Args:
            tab_index: Index of tab to switch to (0 = first tab)
            context: Agent context for logging

        Returns:
            Dict with success status
        """
        try:
            tabs = await self.browser_session.get_tabs()

            if tab_index < 0 or tab_index >= len(tabs):
                error_msg = f"Invalid tab_index {tab_index}, only {len(tabs)} tabs open"
                logger.error(f"❌ {error_msg}")
                return {'success': False, 'error': error_msg}

            target_tab = tabs[tab_index]
            target_id = target_tab.target_id

            logger.info(f"📑 Switching to tab {tab_index}: {target_tab.title or target_tab.url}")

            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "info",
                        f"📑 Switching to tab {tab_index}: {target_tab.title or target_tab.url}",
                        {"tab_index": tab_index, "action": "switch_tab"}
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            # Use SwitchTabEvent
            event = self.browser_session.event_bus.dispatch(
                SwitchTabEvent(target_id=target_id)
            )
            await event
            await event.event_result(raise_if_any=False, raise_if_none=False)

            # Wait for tab to become active
            await asyncio.sleep(1)

            logger.info(f"✅ Switched to tab {tab_index}")
            return {'success': True, 'tab_index': tab_index}

        except Exception as e:
            logger.error(f"Failed to switch tab: {e}")
            return {'success': False, 'error': str(e)}

    async def _execute_close_tab(self, tab_index: int = None, context: AgentContext = None) -> Dict:
        """Close tab by index (None = close current tab)

        Args:
            tab_index: Index of tab to close (None = current tab)
            context: Agent context for logging

        Returns:
            Dict with success status
        """
        try:
            tabs = await self.browser_session.get_tabs()

            if len(tabs) <= 1:
                error_msg = "Cannot close the last tab"
                logger.warning(f"⚠️ {error_msg}")
                return {'success': False, 'error': error_msg}

            if tab_index is not None:
                if tab_index < 0 or tab_index >= len(tabs):
                    error_msg = f"Invalid tab_index {tab_index}, only {len(tabs)} tabs open"
                    logger.error(f"❌ {error_msg}")
                    return {'success': False, 'error': error_msg}
                target_tab = tabs[tab_index]
                target_id = target_tab.target_id
            else:
                # Close current tab - get current page's target_id
                current_page = await self.browser_session.get_current_page()
                if current_page and hasattr(current_page, '_target_id'):
                    target_id = current_page._target_id
                else:
                    # Fallback: close last tab
                    target_tab = tabs[-1]
                    target_id = target_tab.target_id

            logger.info(f"📑 Closing tab: {target_id[-8:]}")

            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "info",
                        f"📑 Closing tab (index={tab_index})",
                        {"tab_index": tab_index, "action": "close_tab"}
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            # Use CloseTabEvent
            event = self.browser_session.event_bus.dispatch(
                CloseTabEvent(target_id=target_id)
            )
            await event
            await event.event_result(raise_if_any=False, raise_if_none=False)

            # Wait for tab to close
            await asyncio.sleep(1)

            logger.info(f"✅ Tab closed")
            return {'success': True}

        except Exception as e:
            logger.error(f"Failed to close tab: {e}")
            return {'success': False, 'error': str(e)}

    async def _cleanup_extra_tabs(self) -> None:
        """Close tabs that were opened during workflow execution

        Uses self._initial_tab_ids to determine which tabs existed before workflow started.
        All tabs not in that set will be closed.
        """
        try:
            tabs = await self._get_open_tabs()
            current_tab_ids = {t['tab_id'] for t in tabs}

            # Find tabs to close (not in initial set)
            tabs_to_close = current_tab_ids - self._initial_tab_ids

            if not tabs_to_close:
                logger.info("📑 No extra tabs to cleanup")
                return

            logger.info(f"📑 Cleaning up {len(tabs_to_close)} extra tabs: {tabs_to_close}")

            for tab in tabs:
                if tab['tab_id'] in tabs_to_close:
                    try:
                        # Close by full target_id
                        event = self.browser_session.event_bus.dispatch(
                            CloseTabEvent(target_id=tab['full_target_id'])
                        )
                        await event
                        await event.event_result(raise_if_any=False, raise_if_none=False)
                        logger.info(f"   Closed tab: {tab['tab_id']}")
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.warning(f"   Failed to close tab {tab['tab_id']}: {e}")

            logger.info(f"✅ Tab cleanup completed")

        except Exception as e:
            logger.warning(f"Tab cleanup failed: {e}")

    async def _scroll_to_element_with_claude(
        self,
        task: str,
        xpath_hints: Dict[str, str],
        text: str,
        context: AgentContext
    ) -> Dict:
        """Scroll to element using unified element-finder flow (same as click/fill)

        Uses the same find_element.py script and element-finder skill as click/fill,
        then extracts xpath from element_info to scroll.

        Flow:
        1. Get DOM with selector_map
        2. Check cached script with cache validation
        3. Execute script with LLM fallback support
        4. Get xpath from element_info
        5. Use CDP to scroll to element

        Args:
            task: Task description
            xpath_hints: XPath hints from user
            text: Optional text hint
            context: Agent context

        Returns:
            Dict with success status
        """
        try:
            # Step 1: Get DOM with selector_map (same as click/fill)
            dom_dict, dom_llm, selector_map = await self._get_current_page_dom()
            if not dom_dict:
                return {'success': False, 'error': 'Failed to get DOM'}

            logger.info(f"Got DOM for scroll_to_element: {len(dom_llm)} chars, {len(selector_map)} interactive elements")

            # Step 2: Setup workspace (same key generation as click/fill)
            script_key = self._generate_script_key(f"scroll_to_{task}", xpath_hints)
            scripts_root = self.config_service.get_path("data.scripts")
            working_dir = scripts_root / script_key
            working_dir.mkdir(parents=True, exist_ok=True)
            script_file = working_dir / "find_element.py"  # Same as click/fill

            logger.info(f"BrowserAgent scroll_to_element workspace: {working_dir}")

            # Step 3: Cache validation (same as click/fill)
            cache_valid = False
            script_content = ""

            if script_file.exists():
                script_content = script_file.read_text(encoding='utf-8')
                cache_valid = self._is_cache_valid(working_dir, task, xpath_hints)
                if cache_valid:
                    logger.info(f"✅ Cache valid: {script_file}")
                    await self._save_dom_data(working_dir, dom_dict)
                else:
                    logger.info(f"🔄 Cache invalidated, regenerating script")
                    await self._prepare_workspace(working_dir, task, 'scroll', xpath_hints, text, dom_dict)
            else:
                await self._prepare_workspace(working_dir, task, 'scroll', xpath_hints, text, dom_dict)

            # Step 4: Execute with LLM fallback (same as click/fill)
            runtime_xpath = list(xpath_hints.values())[0] if xpath_hints else ""

            if cache_valid and script_content:
                # Try cached script with fallback
                find_result = await self._find_element_with_fallback(
                    script_content, dom_dict, runtime_xpath, task, working_dir
                )

                if find_result.get('success'):
                    # Get xpath from element_info
                    element_info = find_result.get('element_info', {})
                    xpath = element_info.get('xpath')

                    # Fallback: find xpath in dom_dict by interactive_index
                    if not xpath:
                        interactive_index = find_result.get('interactive_index')
                        if interactive_index is not None:
                            xpath = self._find_xpath_by_interactive_index(dom_dict, interactive_index)
                            if xpath:
                                logger.info(f"📍 Found xpath from dom_dict: {xpath}")

                    if xpath:
                        scroll_result = await self._execute_scroll_by_xpath(xpath)
                        if scroll_result.get('success'):
                            logger.info(f"✅ Cached script scroll succeeded to: {xpath}")
                            return {
                                'success': True,
                                'xpath': xpath,
                                'cached': True,
                                'element_info': element_info
                            }
                        else:
                            logger.warning(f"Cached xpath scroll failed: {scroll_result.get('error')}")
                    else:
                        logger.warning(f"Cached script found element but no xpath in element_info or dom_dict")
                else:
                    logger.warning(f"Cached script failed: {find_result.get('error')}")

            # Step 5: Generate new script (same flow as click/fill)
            logger.info(f"📝 Generating find_element.py with Claude Agent for scroll...")

            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "info",
                        "📝 Generating element finder script for scroll...",
                        {"script_path": str(script_file)}
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            result = await self._generate_and_execute_for_scroll(
                working_dir=working_dir,
                task=task,
                xpath_hints=xpath_hints,
                text=text,
                selector_map=selector_map,
                max_attempts=3,
                context=context
            )

            return result

        except Exception as e:
            logger.error(f"Failed to scroll to element: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    async def _generate_and_execute_for_scroll(
        self,
        working_dir: Path,
        task: str,
        xpath_hints: Dict[str, str],
        text: str,
        selector_map: Dict,
        max_attempts: int = 3,
        context: AgentContext = None
    ) -> Dict:
        """Generate script and execute scroll (similar to _generate_and_execute_with_retry)

        Args:
            working_dir: Working directory
            task: Task description
            xpath_hints: XPath hints
            text: Optional text hint
            selector_map: Maps interactive_index to backend_node
            max_attempts: Max retry attempts
            context: Agent context

        Returns:
            Dict with success status
        """
        feedback = ""

        for attempt in range(max_attempts):
            logger.info(f"🔄 Scroll attempt {attempt + 1}/{max_attempts} for task: {task}")

            try:
                # 1. Call Claude Agent to generate find_element.py
                claude_result = await self._call_claude_for_find_element(
                    working_dir=working_dir,
                    task=task,
                    operation='scroll',
                    text=text,
                    feedback=feedback,
                    context=context
                )

                if not claude_result.get('success'):
                    feedback = f"Ami Coder failed: {claude_result.get('error')}"
                    logger.warning(f"⚠️ {feedback}")
                    continue

                # 2. Read and execute find_element.py
                script_file = working_dir / "find_element.py"
                if not script_file.exists():
                    feedback = "find_element.py was not created"
                    logger.warning(f"⚠️ {feedback}")
                    continue

                script_content = script_file.read_text(encoding='utf-8')
                dom_data = json.loads((working_dir / "dom_data.json").read_text(encoding='utf-8'))
                dom_dict = dom_data.get("dom", dom_data)

                # Get xpath from task.json
                task_data = json.loads((working_dir / "task.json").read_text(encoding='utf-8'))
                xpath_hints_from_file = task_data.get("xpath_hints", {})
                runtime_xpath = list(xpath_hints_from_file.values())[0] if xpath_hints_from_file else ""

                # Execute with LLM fallback
                find_result = await self._find_element_with_fallback(
                    script_content, dom_dict, runtime_xpath, task, working_dir
                )

                if not find_result.get('success'):
                    feedback = f"find_element.py execution failed: {find_result.get('error')}"
                    logger.warning(f"⚠️ {feedback}")
                    continue

                # 3. Get xpath from element_info
                element_info = find_result.get('element_info', {})
                xpath = element_info.get('xpath')

                # Fallback: find xpath in dom_dict by interactive_index
                if not xpath:
                    interactive_index = find_result.get('interactive_index')
                    if interactive_index is not None:
                        xpath = self._find_xpath_by_interactive_index(dom_dict, interactive_index)
                        if xpath:
                            logger.info(f"📍 Found xpath from dom_dict: {xpath}")

                if not xpath:
                    feedback = f"Found element but could not get xpath from element_info or dom_dict"
                    logger.warning(f"⚠️ {feedback}")
                    await self._refresh_dom_file(working_dir)
                    continue

                logger.info(f"📍 Found element xpath: {xpath}")

                # 4. Execute scroll
                scroll_result = await self._execute_scroll_by_xpath(xpath)

                if scroll_result.get('success'):
                    logger.info(f"✅ Scroll succeeded!")
                    return {
                        'success': True,
                        'xpath': xpath,
                        'cached': False,
                        'element_info': element_info,
                        'attempts': attempt + 1
                    }

                # Scroll failed - refresh DOM and retry
                error_msg = scroll_result.get('error', 'Unknown error')
                logger.warning(f"⚠️ Scroll failed: {error_msg}")

                new_dom, _, new_selector_map = await self._get_current_page_dom()
                selector_map = new_selector_map
                await self._save_dom_data(working_dir, new_dom)

                feedback = f"""
## Previous Attempt Failed
- Found xpath: {xpath}
- Operation: scroll
- Error: {error_msg}

The dom_data.json has been updated. Please analyze and fix find_element.py.
"""

            except Exception as e:
                feedback = f"Exception during attempt: {str(e)}"
                logger.error(f"❌ {feedback}")
                import traceback
                traceback.print_exc()

        return {
            'success': False,
            'error': f'Failed to scroll after {max_attempts} attempts'
        }

    async def _execute_scroll_by_xpath(self, xpath: str) -> Dict:
        """Execute scroll to element by xpath using CDP

        Args:
            xpath: XPath of the target element

        Returns:
            Dict with success status
        """
        try:
            # Get CDP session
            page = await self.browser_session.get_current_page()
            if not page:
                return {'success': False, 'error': 'No current page'}

            cdp_session = await self.browser_session.get_or_create_cdp_session(page._target_id)
            cdp_client = cdp_session.cdp_client
            session_id = cdp_session.session_id

            # Enable DOM
            await cdp_client.send.DOM.enable(session_id=session_id)

            # Perform XPath search
            logger.info(f"📍 Searching for xpath: {xpath}")
            search_result = await cdp_client.send.DOM.performSearch(
                params={'query': xpath},
                session_id=session_id
            )
            search_id = search_result['searchId']
            result_count = search_result['resultCount']

            if result_count == 0:
                await cdp_client.send.DOM.discardSearchResults(
                    params={'searchId': search_id},
                    session_id=session_id
                )
                return {'success': False, 'error': f'XPath not found: {xpath}'}

            # Get the first match
            node_ids = await cdp_client.send.DOM.getSearchResults(
                params={'searchId': search_id, 'fromIndex': 0, 'toIndex': 1},
                session_id=session_id
            )

            if not node_ids['nodeIds']:
                await cdp_client.send.DOM.discardSearchResults(
                    params={'searchId': search_id},
                    session_id=session_id
                )
                return {'success': False, 'error': 'No node IDs returned'}

            node_id = node_ids['nodeIds'][0]

            # Scroll element into view
            await cdp_client.send.DOM.scrollIntoViewIfNeeded(
                params={'nodeId': node_id},
                session_id=session_id
            )

            logger.info(f"✅ Scrolled to element (nodeId={node_id})")

            # Clean up search
            await cdp_client.send.DOM.discardSearchResults(
                params={'searchId': search_id},
                session_id=session_id
            )

            return {'success': True, 'node_id': node_id}

        except Exception as e:
            logger.error(f"Failed to execute scroll by xpath: {e}")
            return {'success': False, 'error': str(e)}

    def _wrap_output(self, input_data: Any, response: Dict) -> Any:
        """Wrap response in AgentOutput if needed

        Args:
            input_data: Original input data
            response: Response dictionary

        Returns:
            AgentOutput or dict
        """
        from ..core.schemas import AgentInput, AgentOutput

        if isinstance(input_data, AgentInput):
            # 统一契约：输出放在 data["result"] 中
            result_data = {
                "url": response.get('current_url'),
                "title": response.get('title'),
                "success": response.get('success', False)
            }

            # Include tab info if present
            if response.get('current_tab_index') is not None:
                result_data['current_tab_index'] = response.get('current_tab_index')
            if response.get('open_tabs_count') is not None:
                result_data['open_tabs_count'] = response.get('open_tabs_count')

            # Collect all clipboard content from steps
            # Returns the last non-empty clipboard content captured
            steps_results = response.get('steps_results', [])
            clipboard_contents = []
            for step in steps_results:
                if step.get('clipboard_content'):
                    clipboard_contents.append(step['clipboard_content'])

            if clipboard_contents:
                # Return the last clipboard content (most recent)
                result_data['clipboard_content'] = clipboard_contents[-1]
                # Also provide all clipboard contents if multiple were captured
                if len(clipboard_contents) > 1:
                    result_data['all_clipboard_contents'] = clipboard_contents

            return AgentOutput(
                success=response.get('success', False),
                data={"result": result_data},
                message=response.get('message', '')
            )
        return response

    def _create_error_response(self, error_msg: str) -> Dict[str, Any]:
        """Create error response dictionary

        Args:
            error_msg: Error message

        Returns:
            Error response dictionary
        """
        return {
            'success': False,
            'message': 'Operation failed',
            'error': error_msg,
            'current_url': '',
            'steps_executed': 0,
            'steps_results': []
        }

    def _convert_legacy_step(self, step: Dict) -> Dict:
        """Convert legacy step format to new format

        Legacy format:
        - action_type: "scroll" | "click" | "input"
        - parameters: {down: true, num_pages: 1} | {selector: "..."} | {text: "..."}

        New format:
        - task: Task description
        - xpath_hints: {} (empty for scroll)
        - text: Direction for scroll, or input text

        Args:
            step: Legacy step dict

        Returns:
            New format step dict
        """
        action_type = step.get('action_type', '').lower()
        parameters = step.get('parameters', {})

        if action_type == 'scroll':
            # Convert scroll: {down: true, num_pages: 1} -> {task: "scroll", text: "down"}
            direction = 'down' if parameters.get('down', True) else 'up'
            num_pages = parameters.get('num_pages', 1)
            # Each page is ~500 pixels
            scroll_amount = num_pages * 500 if direction == 'down' else -num_pages * 500

            return {
                'task': f'Scroll {direction} the page',
                'xpath_hints': {},
                'text': str(scroll_amount)
            }

        elif action_type == 'click':
            selector = parameters.get('selector', '')
            return {
                'task': f'Click on element',
                'xpath_hints': {'selector': selector} if selector else {},
                'text': ''
            }

        elif action_type in ['input', 'fill', 'type']:
            selector = parameters.get('selector', '')
            text = parameters.get('text', '')
            return {
                'task': f'Fill text into element',
                'xpath_hints': {'selector': selector} if selector else {},
                'text': text
            }

        else:
            logger.warning(f"Unknown legacy action_type: {action_type}, passing through")
            return step
