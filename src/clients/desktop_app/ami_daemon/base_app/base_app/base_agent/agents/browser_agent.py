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

from .base_agent import BaseStepAgent, AgentMetadata
from ..core.schemas import AgentContext

try:
    from browser_use import Tools
    from browser_use.browser.session import BrowserSession
    from browser_use.browser.events import NavigateToUrlEvent, ScrollEvent
    from browser_use.agent.views import ActionResult
    from browser_use.actor.element import Element
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    Tools = None
    BrowserSession = None
    NavigateToUrlEvent = None
    ScrollEvent = None
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

    # ==========================================================================
    # Preset Template: test_operation.py - Validates find_element.py
    # ==========================================================================
    PRESET_TEST_OPERATION = '''#!/usr/bin/env python3
"""Test script - Validates that find_element.py correctly finds the target element.

This script:
1. Loads DOM data from dom_data.json
2. Calls find_target_element() from find_element.py
3. Validates the returned interactive_index exists in selector_map
4. Reports success or failure with details

Usage: python test_operation.py
Exit code: 0 = success, 1 = failure
"""
import json
import sys

def test():
    """Test find_element.py and validate result"""
    # Load DOM
    try:
        with open("dom_data.json", "r", encoding="utf-8") as f:
            dom_dict = json.load(f)
    except Exception as e:
        print(f"FAILED: Cannot load dom_data.json: {e}")
        return False

    # Load task info
    try:
        with open("task.json", "r", encoding="utf-8") as f:
            task_info = json.load(f)
    except Exception as e:
        print(f"FAILED: Cannot load task.json: {e}")
        return False

    # Import and run find_element
    try:
        from find_element import find_target_element
    except ImportError as e:
        print(f"FAILED: Cannot import find_element.py: {e}")
        return False
    except SyntaxError as e:
        print(f"FAILED: Syntax error in find_element.py: {e}")
        return False

    # Execute find_target_element
    try:
        result = find_target_element(dom_dict)
    except Exception as e:
        print(f"FAILED: find_target_element() raised exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Validate result structure
    if not isinstance(result, dict):
        print(f"FAILED: find_target_element() must return dict, got {type(result)}")
        return False

    if not result.get("success"):
        error = result.get("error", "Unknown error")
        print(f"FAILED: find_target_element() returned failure: {error}")
        return False

    # Validate interactive_index
    interactive_index = result.get("interactive_index")
    if interactive_index is None:
        print("FAILED: Result missing 'interactive_index'")
        return False

    if not isinstance(interactive_index, int):
        print(f"FAILED: interactive_index must be int, got {type(interactive_index)}")
        return False

    # Validate element_info
    element_info = result.get("element_info", {})
    if not element_info:
        print("WARNING: Result missing 'element_info', but interactive_index is valid")

    # Success!
    print(f"SUCCESS: Found element")
    print(f"  interactive_index: {interactive_index}")
    print(f"  tag: {element_info.get('tag', 'N/A')}")
    print(f"  text: {element_info.get('text', 'N/A')[:50] if element_info.get('text') else 'N/A'}")
    print(f"  class: {element_info.get('class', 'N/A')[:50] if element_info.get('class') else 'N/A'}")
    return True

if __name__ == "__main__":
    success = test()
    sys.exit(0 if success else 1)
'''

    # ==========================================================================
    # Preset Template: find_element_template.py - Template for Claude Agent
    # ==========================================================================
    PRESET_FIND_ELEMENT_TEMPLATE = '''#!/usr/bin/env python3
"""Find target element in DOM - Generated by Claude Agent

This script finds the target element based on task description and xpath hints.
It searches dom_data.json and returns the interactive_index of the target element.

IMPORTANT:
- Only elements with 'interactive_index' can be clicked or filled
- For input fields, prefer div with 'EditorClass' over hidden inputs
- Handle both Chinese and English text (e.g., "新邮件" = "New mail")
"""
import json
from typing import Dict, Optional, List

def find_target_element(dom_dict: dict) -> dict:
    """Find target element and return its interactive_index

    Args:
        dom_dict: DOM dictionary loaded from dom_data.json

    Returns:
        dict with:
        - success: bool
        - interactive_index: int (element index for click/fill operations)
        - element_info: dict with tag, text, xpath, class (for debugging)
        - error: str (if success is False)
    """

    def search_recursive(node: dict, condition_fn) -> Optional[dict]:
        """Recursively search DOM tree with a condition function"""
        if condition_fn(node):
            return node
        for child in node.get('children', []):
            result = search_recursive(child, condition_fn)
            if result:
                return result
        return None

    def search_by_text(node: dict, keywords: List[str], require_interactive: bool = True) -> Optional[dict]:
        """Search for element containing any of the keywords in text"""
        def condition(n):
            text = (n.get('text', '') or '').lower()
            has_index = n.get('interactive_index') is not None
            for kw in keywords:
                if kw.lower() in text:
                    if not require_interactive or has_index:
                        return True
            return False
        return search_recursive(node, condition)

    def search_by_class(node: dict, class_keywords: List[str]) -> Optional[dict]:
        """Search for element with class containing any keyword"""
        def condition(n):
            cls = (n.get('class', '') or '').lower()
            has_index = n.get('interactive_index') is not None
            for kw in class_keywords:
                if kw.lower() in cls and has_index:
                    return True
            return False
        return search_recursive(node, condition)

    def search_by_placeholder(node: dict, keywords: List[str]) -> Optional[dict]:
        """Search input by placeholder text"""
        def condition(n):
            placeholder = (n.get('placeholder', '') or '').lower()
            has_index = n.get('interactive_index') is not None
            for kw in keywords:
                if kw.lower() in placeholder and has_index:
                    return True
            return False
        return search_recursive(node, condition)

    def search_by_aria_label(node: dict, keywords: List[str]) -> Optional[dict]:
        """Search by aria-label attribute"""
        def condition(n):
            aria = (n.get('aria-label', '') or '').lower()
            has_index = n.get('interactive_index') is not None
            for kw in keywords:
                if kw.lower() in aria and has_index:
                    return True
            return False
        return search_recursive(node, condition)

    # TODO: Implement your search logic here based on task.json
    # Example searches (uncomment and modify as needed):
    #
    # element = search_by_text(dom_dict, ["New mail", "新邮件"])
    # element = search_by_class(dom_dict, ["EditorClass"])
    # element = search_by_placeholder(dom_dict, ["Subject", "主题"])
    # element = search_by_aria_label(dom_dict, ["New message"])

    element = None  # Replace with actual search

    # Return result
    if not element:
        return {"success": False, "error": "Target element not found in DOM"}

    if element.get('interactive_index') is None:
        return {"success": False, "error": "Found element but it has no interactive_index (not clickable)"}

    return {
        "success": True,
        "interactive_index": element.get("interactive_index"),
        "element_info": {
            "tag": element.get("tag"),
            "text": (element.get("text") or "")[:100],
            "xpath": element.get("xpath"),
            "class": element.get("class")
        }
    }

if __name__ == "__main__":
    # Test locally
    with open("dom_data.json", "r", encoding="utf-8") as f:
        dom = json.load(f)
    result = find_target_element(dom)
    print(json.dumps(result, indent=2, ensure_ascii=False))
'''

    # ==========================================================================
    # Claude Agent Prompt - Generates find_element.py
    # ==========================================================================
    CLAUDE_AGENT_PROMPT = """# Browser Element Finder Task

## Your Working Directory
You are working in: `{working_dir}`

## Available Files
- `task.json` - Task description with xpath hints
- `dom_data.json` - Current page DOM structure (nested JSON)
- `find_element_template.py` - Template with helper functions (copy and modify)
- `test_operation.py` - Test script to validate your find_element.py

## Your Task
Create `find_element.py` that finds the target element described in task.json.

## Instructions

### Step 1: Read task.json
```bash
cat task.json
```
Understand what element to find and the xpath hints provided.

### Step 2: Explore DOM
Search dom_data.json to find the target element:
```bash
# Search by text
grep -i "new mail" dom_data.json | head -20

# Search by class
grep -i "editorclass" dom_data.json | head -20

# Search by aria-label
grep -i "aria-label" dom_data.json | head -20
```

### Step 3: Create find_element.py
Copy the template and implement the search logic:
```bash
cp find_element_template.py find_element.py
```
Then edit find_element.py to implement the actual search.

### Step 4: Test
Run the test script to verify your implementation:
```bash
python test_operation.py
```
If it fails, read the error and fix find_element.py.

## DOM Element Structure
Each element in dom_data.json contains:
- `tag`: HTML tag (button, input, div, etc.)
- `text`: Text content
- `xpath`: XPath location
- `interactive_index`: **REQUIRED** - Index for click/fill operations
- `class`, `id`, `placeholder`, `aria-label`: HTML attributes
- `children`: Child elements

## CRITICAL Rules
1. Only elements with `interactive_index` can be clicked or filled
2. For input fields: prefer `div` with `EditorClass` over hidden `input`
3. Handle multi-language: "新邮件" = "New mail", "添加主题" = "Add subject"
4. Return `interactive_index` as an integer

## Success Criteria
`python test_operation.py` must print "SUCCESS" and exit with code 0.
"""

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

        Path structure: users/{user_id}/workflows/{workflow_id}/{step_id}/browser_script_{hash}

        Args:
            task: Task description
            xpath_hints: XPath hints for element location

        Returns:
            Relative path for script storage
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

        # Generate hash-based key using task and xpath_hints
        content = f"browser_{task}_{json.dumps(xpath_hints, sort_keys=True)}"
        hash_suffix = hashlib.md5(content.encode()).hexdigest()[:8]
        script_key = f"browser_script_{hash_suffix}"

        # Build relative path (will be prefixed with data.scripts by config_service)
        script_path = f"users/{user_id}/workflows/{workflow_id}/{step_id}/{script_key}"
        logger.debug(f"Generated script path: {script_path}")
        return script_path

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

                logger.info(f"📍 Step {idx + 1}/{len(interaction_steps)}: {task}")

                # Execute the intelligent interaction
                step_result = await self._execute_intelligent_interaction(
                    task=task,
                    xpath_hints=xpath_hints,
                    text=text,
                    context=context,
                    max_retries=2
                )

                steps_results.append({
                    'task': task,
                    'success': step_result['success'],
                    'verification': step_result.get('verification', ''),
                    'error': step_result.get('error', '')
                })

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
                'steps_results': steps_results
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
                return {
                    'success': True,
                    'element_info': result.get('element_info', {}),
                    'interactive_index': result.get('interactive_index'),
                    'cached': result.get('cached', False),
                    'attempts': result.get('attempts', 1)
                }
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
        from src.common.llm import ClaudeAgentProvider

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
                raise RuntimeError("ConfigService not available - required for Claude Agent SDK")

            script_key = self._generate_script_key(task, xpath_hints)
            scripts_root = self.config_service.get_path("data.scripts")
            working_dir = scripts_root / script_key
            working_dir.mkdir(parents=True, exist_ok=True)

            script_file = working_dir / "find_element.py"

            logger.info(f"BrowserAgent script workspace: {working_dir}")

            # 2. Prepare workspace with preset templates and input files
            await self._prepare_workspace(working_dir, task, operation, xpath_hints, text, dom_dict)

            # 3. Check if cached script exists and try to use it first
            if script_file.exists():
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

                # Update DOM for current page
                (working_dir / "dom_data.json").write_text(
                    json.dumps(dom_dict, indent=2, ensure_ascii=False),
                    encoding='utf-8'
                )

                # Try executing cached script
                find_result = self._execute_find_element_script(script_content, dom_dict)

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
                                return {
                                    'success': True,
                                    'interactive_index': interactive_index,
                                    'backend_node_id': backend_node_id,
                                    'element_info': find_result.get('element_info', {}),
                                    'cached': True
                                }
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
                            "⚠️ Cached script didn't work, regenerating with Claude Agent...",
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
        # 1. Save preset templates
        test_file = working_dir / "test_operation.py"
        test_file.write_text(self.PRESET_TEST_OPERATION, encoding='utf-8')

        template_file = working_dir / "find_element_template.py"
        template_file.write_text(self.PRESET_FIND_ELEMENT_TEMPLATE, encoding='utf-8')

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

        # 3. Save dom_data.json
        dom_file = working_dir / "dom_data.json"
        dom_file.write_text(
            json.dumps(dom_dict, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

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
        from src.common.llm import ClaudeAgentProvider

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
                    feedback = f"Claude Agent failed: {claude_result.get('error')}"
                    logger.warning(f"⚠️ {feedback}")
                    continue

                # 2. Read and execute find_element.py
                script_file = working_dir / "find_element.py"
                if not script_file.exists():
                    feedback = "find_element.py was not created"
                    logger.warning(f"⚠️ {feedback}")
                    continue

                script_content = script_file.read_text(encoding='utf-8')
                dom_dict = json.loads((working_dir / "dom_data.json").read_text(encoding='utf-8'))

                find_result = self._execute_find_element_script(script_content, dom_dict)

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
                    return {
                        'success': True,
                        'interactive_index': interactive_index,
                        'backend_node_id': backend_node_id,
                        'element_info': find_result.get('element_info', {}),
                        'attempts': attempt + 1
                    }

                # 5. Operation failed - refresh DOM and prepare feedback
                error_msg = op_result.get('error', 'Unknown error')
                logger.warning(f"⚠️ Operation failed: {error_msg}")

                # Refresh DOM file for next attempt
                new_dom, _, new_selector_map = await self._get_current_page_dom()
                selector_map = new_selector_map  # Update selector_map for next attempt

                (working_dir / "dom_data.json").write_text(
                    json.dumps(new_dom, indent=2, ensure_ascii=False),
                    encoding='utf-8'
                )

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
        """Call Claude Agent SDK to generate/fix find_element.py for click/fill operations

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
        from src.common.llm import ClaudeAgentProvider

        try:
            # Build prompt
            prompt = self.CLAUDE_AGENT_PROMPT.format(working_dir=working_dir)

            # Add task-specific context
            prompt += f"""

## Current Task Details
- **Task:** {task}
- **Operation:** {operation}
- **Text (for fill):** {text if text else "N/A"}
"""

            # Add feedback if this is a retry
            if feedback:
                prompt += f"""

## IMPORTANT: Previous Attempt Failed
{feedback}

Please fix find_element.py based on the error above.
"""

            prompt += """
Start by reading task.json and dom_data.json to understand the requirements and DOM structure.
"""

            # Initialize Claude Agent Provider
            api_key = None
            base_url = None
            if self.provider and hasattr(self.provider, 'api_key'):
                api_key = self.provider.api_key
                base_url = getattr(self.provider, 'base_url', None)

            claude_provider = ClaudeAgentProvider(
                config_service=self.config_service,
                api_key=api_key,
                base_url=base_url
            )

            # Run Claude Agent SDK with streaming
            logger.info(f"Starting Claude Agent for find_element.py...")

            # Progress update ID for dynamic log updates (like ScraperAgent)
            progress_update_id = f"browser_script_generation_{id(self)}_{task[:20]}"

            # Send initial log to frontend
            if context and context.log_callback:
                try:
                    await context.log_callback(
                        "info",
                        f"📝 Generating element finder script for: {task}",
                        {
                            "update_id": progress_update_id,
                            "task": task,
                            "operation": operation
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            task_completed = False
            task_error = None
            final_turn = 0

            async for event in claude_provider.run_task_stream(
                prompt=prompt,
                working_dir=working_dir
            ):
                if event.turn:
                    final_turn = event.turn

                # Forward streaming events to frontend (like ScraperAgent)
                if context and context.log_callback:
                    try:
                        if event.type == "text":
                            await context.log_callback(
                                "info",
                                f"🔍 Finding element (turn {event.turn})\n{event.content[:150]}...",
                                {
                                    "update_id": progress_update_id,
                                    "turn": event.turn,
                                    "message": event.content[:150]
                                }
                            )
                        elif event.type == "tool_use":
                            tool_desc = f"Using {event.tool_name} tool"
                            await context.log_callback(
                                "info",
                                f"🔍 Finding element (turn {event.turn})\n{tool_desc}",
                                {
                                    "update_id": progress_update_id,
                                    "turn": event.turn,
                                    "message": tool_desc,
                                    "tool_name": event.tool_name
                                }
                            )
                        elif event.type == "complete":
                            task_completed = True
                            logger.info(f"Claude Agent completed in {final_turn} turns")
                        elif event.type == "error":
                            task_error = event.content
                            logger.error(f"Claude Agent error: {event.content}")
                    except Exception as e:
                        logger.warning(f"Failed to forward streaming event: {e}")

                if event.type == "text":
                    logger.debug(f"Claude (turn {event.turn}): {event.content[:80]}...")
                elif event.type == "tool_use":
                    logger.debug(f"Claude using: {event.tool_name}")
                elif event.type == "complete":
                    task_completed = True
                elif event.type == "error":
                    task_error = event.content

            # Send completion log with script content
            if context and context.log_callback:
                try:
                    script_file = working_dir / "find_element.py"
                    if script_file.exists():
                        script_content = script_file.read_text(encoding='utf-8')
                        # Update the dynamic progress log to show completion
                        await context.log_callback(
                            "success",
                            f"✅ Element finder script generated ({final_turn} turns)",
                            {
                                "update_id": progress_update_id,
                                "turn": final_turn,
                                "completed": True
                            }
                        )
                        # Send script content as code
                        await context.log_callback(
                            "success",
                            f"📜 Generated find_element.py ({len(script_content)} chars)",
                            {
                                "script_content": script_content,
                                "content_type": "code",
                                "language": "python",
                                "cache_path": str(script_file)
                            }
                        )
                except Exception as e:
                    logger.warning(f"Failed to send completion log: {e}")

            if task_error:
                return {'success': False, 'error': task_error}

            if not task_completed:
                return {'success': False, 'error': f'Claude Agent did not complete ({final_turn} turns)'}

            return {'success': True}

        except Exception as e:
            logger.error(f"Claude Agent call failed: {e}")
            return {'success': False, 'error': str(e)}

    async def _refresh_dom_file(self, working_dir: Path) -> Dict:
        """Refresh dom_data.json with current page DOM

        Args:
            working_dir: Working directory

        Returns:
            New selector_map
        """
        new_dom, _, new_selector_map = await self._get_current_page_dom()
        (working_dir / "dom_data.json").write_text(
            json.dumps(new_dom, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        logger.info(f"📄 Refreshed dom_data.json")
        return new_selector_map

    def _execute_find_element_script(self, code: str, dom_dict: Dict) -> Dict:
        """Execute find_element.py to get target element info

        Args:
            code: Generated Python code
            dom_dict: DOM dictionary

        Returns:
            Dict with success, interactive_index, element_info
        """
        try:
            # Create execution environment
            exec_env = {
                'dom_dict': dom_dict,
                'json': json,
            }

            # Execute the code
            exec(code, exec_env, exec_env)

            # Call the function
            find_target_element = exec_env.get('find_target_element')
            if not find_target_element:
                return {'success': False, 'error': 'Script missing find_target_element function'}

            result = find_target_element(dom_dict)
            return result

        except Exception as e:
            logger.error(f"Failed to execute find_element.py: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': f'Script execution failed: {str(e)}'}

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
                    # Save to context if available
                    if self._context:
                        self._context.set_variable('_last_clipboard_content', clipboard_after)
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
                    await context.log_callback(
                        "success",
                        f"✅ Click operation completed",
                        {"operation": "click", "backend_node_id": backend_node_id}
                    )
                except Exception as e:
                    logger.warning(f"Failed to send log callback: {e}")

            return {'success': True}

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
    # Preset Template: find_xpath_element.py - For scroll_to_element operation
    # ==========================================================================
    PRESET_FIND_XPATH_TEMPLATE = '''#!/usr/bin/env python3
"""Find element xpath in DOM - Template for scroll_to_element operation

This script searches the DOM structure to find the xpath of a target element.
Unlike find_element.py which returns interactive_index, this returns xpath
because scroll targets may not be interactive elements.

Usage:
    from find_xpath_element import find_target_xpath
    xpath = find_target_xpath(dom_dict)
"""
import json


def find_by_text(node: dict, text: str, partial: bool = True) -> dict:
    """Find element containing specific text"""
    node_text = (node.get('text', '') or '').lower()
    search_text = text.lower()

    if partial:
        if search_text in node_text:
            return node
    else:
        if search_text == node_text:
            return node

    for child in node.get('children', []):
        result = find_by_text(child, text, partial)
        if result:
            return result
    return None


def find_by_tag(node: dict, tag: str) -> dict:
    """Find first element with specific tag"""
    if node.get('tag', '').lower() == tag.lower():
        return node

    for child in node.get('children', []):
        result = find_by_tag(child, tag)
        if result:
            return result
    return None


def find_by_id(node: dict, element_id: str) -> dict:
    """Find element by id attribute"""
    attrs = node.get('attributes', {})
    if attrs.get('id') == element_id:
        return node

    for child in node.get('children', []):
        result = find_by_id(child, element_id)
        if result:
            return result
    return None


def find_by_class(node: dict, class_name: str) -> dict:
    """Find element containing specific class"""
    attrs = node.get('attributes', {})
    classes = attrs.get('class', '')
    if class_name in classes:
        return node

    for child in node.get('children', []):
        result = find_by_class(child, class_name)
        if result:
            return result
    return None


def find_target_xpath(dom_dict: dict) -> str:
    """Find the xpath of the target element

    TODO: Implement your search logic here using the helper functions above.

    Args:
        dom_dict: DOM dictionary with xpath field for each element

    Returns:
        str: xpath of the target element, or empty string if not found
    """
    # Example: Find footer element
    # result = find_by_tag(dom_dict, 'footer')
    # if result and result.get('xpath'):
    #     return result['xpath']

    # Example: Find element by text
    # result = find_by_text(dom_dict, 'References')
    # if result and result.get('xpath'):
    #     return result['xpath']

    raise NotImplementedError("TODO: Implement find_target_xpath()")


if __name__ == "__main__":
    # Test the script
    with open("dom_data.json", "r", encoding="utf-8") as f:
        dom_dict = json.load(f)

    xpath = find_target_xpath(dom_dict)
    if xpath:
        print(f"SUCCESS: Found xpath: {xpath}")
    else:
        print("FAILED: Could not find target element")
'''

    async def _scroll_to_element_with_claude(
        self,
        task: str,
        xpath_hints: Dict[str, str],
        text: str,
        context: AgentContext
    ) -> Dict:
        """Scroll to element using Claude Agent to generate reusable script

        Similar to click/fill flow, but generates find_xpath_element.py
        that returns xpath instead of interactive_index.

        Flow:
        1. Get DOM with xpath information
        2. Check cached script, if exists -> execute directly
        3. If no cache -> Claude Agent generates find_xpath_element.py
        4. Execute script to get xpath
        5. Use CDP to scroll to element
        6. Cache script for reuse

        Args:
            task: Task description
            xpath_hints: XPath hints from user
            text: Optional text hint
            context: Agent context

        Returns:
            Dict with success status
        """
        from src.common.llm import ClaudeAgentProvider

        try:
            # Step 1: Get DOM with xpath
            dom_dict, dom_llm, _ = await self._get_current_page_dom()
            if not dom_dict:
                return {'success': False, 'error': 'Failed to get DOM'}

            logger.info(f"Got DOM for scroll_to_element: {len(dom_llm)} chars")

            # Step 2: Setup workspace
            script_key = self._generate_script_key(f"scroll_to_{task}", xpath_hints)
            scripts_root = self.config_service.get_path("data.scripts")
            working_dir = scripts_root / script_key
            working_dir.mkdir(parents=True, exist_ok=True)
            script_file = working_dir / "find_xpath_element.py"

            logger.info(f"BrowserAgent scroll_to_element workspace: {working_dir}")

            # Save DOM data
            (working_dir / "dom_data.json").write_text(
                json.dumps(dom_dict, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            # Step 3: Check cached script
            if script_file.exists():
                logger.info(f"Found cached script: {script_file}")
                script_content = script_file.read_text(encoding='utf-8')

                # Execute cached script
                xpath_result = self._execute_find_xpath_script(script_content, dom_dict)

                if xpath_result.get('success'):
                    xpath = xpath_result.get('xpath')
                    logger.info(f"Cached script found xpath: {xpath}")

                    # Execute scroll
                    scroll_result = await self._execute_scroll_by_xpath(xpath)
                    if scroll_result.get('success'):
                        return {
                            'success': True,
                            'xpath': xpath,
                            'cached': True,
                            'element_info': {'xpath': xpath}
                        }
                    else:
                        logger.warning(f"Cached xpath scroll failed: {scroll_result.get('error')}")
                else:
                    logger.warning(f"Cached script failed: {xpath_result.get('error')}")

            # Step 4: Prepare workspace for Claude Agent
            # Save task info
            task_info = {
                'task': task,
                'xpath_hints': xpath_hints,
                'text': text
            }
            (working_dir / "task.json").write_text(
                json.dumps(task_info, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            # Save template
            (working_dir / "find_xpath_template.py").write_text(
                self.PRESET_FIND_XPATH_TEMPLATE,
                encoding='utf-8'
            )

            # Step 5: Build prompt for Claude Agent
            xpath_hints_text = ""
            if xpath_hints:
                hints_list = "\n".join([f"- {name}: {xpath}" for name, xpath in xpath_hints.items()])
                xpath_hints_text = f"\nXPath hints (reference only):\n{hints_list}"

            prompt = f"""# Generate find_xpath_element.py Script

## Task
{task}
{xpath_hints_text}

## Working Directory
{working_dir}

## Available Files
- dom_data.json: DOM structure with xpath for each element
- find_xpath_template.py: Template with helper functions
- task.json: Task description

## Instructions
1. Read dom_data.json to understand the page structure
2. Read find_xpath_template.py for helper functions
3. Create find_xpath_element.py that implements find_target_xpath()
4. The function should return the xpath string of the target element
5. Test your script by running: python find_xpath_element.py

## Important
- The DOM includes 'xpath' field for each element - use it directly
- Search for elements matching the task description
- Return the xpath string, NOT interactive_index
- Use helper functions: find_by_text, find_by_tag, find_by_id, find_by_class

## Output
Create find_xpath_element.py that prints:
SUCCESS: Found xpath: /html/body/...
"""

            # Step 6: Call Claude Agent using run_task_stream
            logger.info(f"Calling Claude Agent to generate find_xpath_element.py...")

            # Get API credentials from provider if available
            api_key = None
            base_url = None
            if self.provider and hasattr(self.provider, 'api_key'):
                api_key = self.provider.api_key
                base_url = getattr(self.provider, 'base_url', None)

            claude_provider = ClaudeAgentProvider(
                config_service=self.config_service,
                api_key=api_key,
                base_url=base_url
            )

            task_completed = False
            task_error = None
            final_turn = 0

            async for event in claude_provider.run_task_stream(
                prompt=prompt,
                working_dir=working_dir
            ):
                if event.turn:
                    final_turn = event.turn

                if event.type == "text":
                    logger.debug(f"Claude (turn {event.turn}): {event.content[:80]}...")
                elif event.type == "tool_use":
                    logger.debug(f"Claude using: {event.tool_name}")
                elif event.type == "complete":
                    task_completed = True
                    logger.info(f"Claude Agent completed in {final_turn} turns")
                elif event.type == "error":
                    task_error = event.content
                    logger.error(f"Claude Agent error: {event.content}")

            if task_error:
                return {'success': False, 'error': task_error}

            if not task_completed:
                return {'success': False, 'error': f'Claude Agent did not complete ({final_turn} turns)'}

            # Step 7: Execute generated script
            if not script_file.exists():
                return {'success': False, 'error': 'Claude Agent did not generate find_xpath_element.py'}

            script_content = script_file.read_text(encoding='utf-8')

            # Update DOM (may have changed)
            dom_dict, _, _ = await self._get_current_page_dom()
            (working_dir / "dom_data.json").write_text(
                json.dumps(dom_dict, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            xpath_result = self._execute_find_xpath_script(script_content, dom_dict)

            if not xpath_result.get('success'):
                return {'success': False, 'error': f"Script failed: {xpath_result.get('error')}"}

            xpath = xpath_result.get('xpath')
            logger.info(f"Script found xpath: {xpath}")

            # Step 8: Execute scroll
            scroll_result = await self._execute_scroll_by_xpath(xpath)

            if scroll_result.get('success'):
                return {
                    'success': True,
                    'xpath': xpath,
                    'cached': False,
                    'element_info': {'xpath': xpath}
                }
            else:
                return {
                    'success': False,
                    'error': f"Failed to scroll to xpath '{xpath}': {scroll_result.get('error')}"
                }

        except Exception as e:
            logger.error(f"Failed to scroll to element: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def _execute_find_xpath_script(self, script_content: str, dom_dict: Dict) -> Dict:
        """Execute find_xpath_element.py script to get xpath

        Args:
            script_content: Python script content
            dom_dict: DOM dictionary

        Returns:
            Dict with success status and xpath
        """
        try:
            # Create execution namespace
            namespace = {'dom_dict': dom_dict}

            # Execute script to define functions
            exec(script_content, namespace)

            # Call find_target_xpath
            if 'find_target_xpath' not in namespace:
                return {'success': False, 'error': 'Script does not define find_target_xpath()'}

            xpath = namespace['find_target_xpath'](dom_dict)

            if xpath:
                return {'success': True, 'xpath': xpath}
            else:
                return {'success': False, 'error': 'find_target_xpath() returned empty'}

        except Exception as e:
            logger.error(f"Script execution error: {e}")
            return {'success': False, 'error': str(e)}

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
            return AgentOutput(
                success=response.get('success', False),
                data=response,
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
