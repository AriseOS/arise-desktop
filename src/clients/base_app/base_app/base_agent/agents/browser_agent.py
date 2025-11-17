"""BrowserAgent - Browser navigation and interaction agent

This agent handles pure browser navigation and interactions without data extraction.
Uses browser-use library for browser automation.

Responsibilities:
- Navigate to specified URLs
- Execute scroll operations (optional)
- Share browser session with other agents

NOT responsible for:
- Data extraction (use ScraperAgent instead)
- Complex interactions like click, input (future enhancement)
"""
import asyncio
import logging
from typing import Any, Dict, Optional, Union, List

from .base_agent import BaseStepAgent, AgentMetadata
from ..core.schemas import AgentContext

try:
    from browser_use import Tools
    from browser_use.browser.session import BrowserSession
    from browser_use.browser.events import NavigateToUrlEvent, ScrollEvent
    from browser_use.agent.views import ActionResult
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    Tools = None
    BrowserSession = None
    NavigateToUrlEvent = None
    ScrollEvent = None
    ActionResult = None

logger = logging.getLogger(__name__)


class BrowserAgent(BaseStepAgent):
    """Browser navigation and interaction agent

    A lightweight agent focused on browser navigation and basic interactions.
    This is essentially a subset of ScraperAgent, reusing the same browser-use
    infrastructure but without data extraction capabilities.

    Key Features:
    - Navigate to URLs
    - Execute scroll operations
    - Share browser session across workflow steps

    Example:
        >>> agent = BrowserAgent()
        >>> await agent.initialize(context)
        >>> result = await agent.execute({
        ...     'target_url': 'https://example.com',
        ...     'interaction_steps': [
        ...         {'action_type': 'scroll', 'parameters': {'down': True, 'num_pages': 2}}
        ...     ]
        ... }, context)
    """

    def __init__(self,
                 config_service=None,
                 metadata: Optional[AgentMetadata] = None):
        """Initialize BrowserAgent

        Args:
            config_service: Configuration service (optional)
            metadata: Agent metadata (optional)
        """

        if metadata is None:
            metadata = AgentMetadata(
                name="browser_agent",
                description="Browser navigation and interaction agent for page navigation and scrolling"
            )
        super().__init__(metadata)

        # Save config service
        self.config_service = config_service

        # browser-use components (will be set in initialize)
        self.browser_session = None
        self.controller = None

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
            # Get browser session from context (shared across workflow)
            session_info = await context.get_browser_session()

            # Set browser-use components
            self.browser_session = session_info.session
            self.controller = session_info.controller

            # Mark as initialized
            self.is_initialized = True

            logger.info(f"BrowserAgent initialized successfully using workflow {context.workflow_id} shared session")
            return True

        except Exception as e:
            logger.error(f"BrowserAgent initialization failed: {e}")
            return False

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data

        Optional fields:
        - target_url: str (if provided, will navigate to this URL first)
        - interaction_steps: List[Dict] (operations to perform, e.g., scroll)
        - timeout: int

        Note: At least one of target_url or interaction_steps must be provided.

        Args:
            input_data: Input data (AgentInput or dict)

        Returns:
            bool: True if valid, False otherwise
        """
        # Handle AgentInput wrapper
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

            for step in steps:
                if 'action_type' not in step:
                    logger.error("Validation failed: step missing 'action_type'")
                    return False

                # Currently only support 'scroll'
                if step['action_type'] not in ['scroll']:
                    logger.error(f"Validation failed: unsupported action_type '{step['action_type']}'")
                    return False

        return True

    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """Execute navigation and interactions

        Flow:
        1. Check initialization
        2. Extract input data
        3. Navigate to target_url
        4. Execute interaction_steps (if any)
        5. Return result

        Args:
            input_data: Input data (AgentInput or dict)
            context: Execution context

        Returns:
            AgentOutput with navigation result
        """
        if not self.is_initialized:
            raise RuntimeError("BrowserAgent not initialized")

        # Handle AgentInput wrapper
        from ..core.schemas import AgentInput, AgentOutput

        if isinstance(input_data, AgentInput):
            actual_data = input_data.data
        else:
            actual_data = input_data

        # Extract parameters
        target_url = actual_data.get('target_url')
        interaction_steps = actual_data.get('interaction_steps', [])
        timeout = actual_data.get('timeout', 30)

        logger.info(f"🌐 BrowserAgent executing: target_url={target_url}, "
                   f"interaction_steps={len(interaction_steps)}")

        try:
            # Navigate to target URL and/or execute interactions
            if target_url:
                result = await self._navigate_to_pages(target_url, interaction_steps)
            elif interaction_steps:
                # Only execute interactions on current page (no navigation)
                result = await self._execute_interactions_only(interaction_steps)
            else:
                raise ValueError("Must provide either target_url or interaction_steps")

            # Check navigation result
            if result.success is False:
                logger.error(f"❌ Navigation failed: {result.error}")
                return self._create_error_response(
                    f"Navigation failed: {result.error}"
                )

            # Get current URL from browser session
            try:
                current_url = self.browser_session.context.pages[0].url if self.browser_session else (target_url or "")
            except:
                current_url = target_url or ""

            # Success response
            if target_url:
                message = f"Successfully navigated to {target_url}"
                if interaction_steps:
                    message += f" and executed {len(interaction_steps)} interaction step(s)"
            else:
                message = f"Successfully executed {len(interaction_steps)} interaction step(s) on current page"

            logger.info(f"✅ {message}")

            response = self._create_response(
                success=True,
                message=message,
                current_url=current_url,
                steps_executed=len(interaction_steps)
            )

            # Wrap in AgentOutput if needed
            if isinstance(input_data, AgentInput):
                return AgentOutput(
                    success=True,
                    data=response,
                    message=response['message']
                )
            else:
                return response

        except Exception as e:
            logger.error(f"❌ BrowserAgent execution failed: {e}")
            import traceback
            traceback.print_exc()

            error_response = self._create_error_response(str(e))

            if isinstance(input_data, AgentInput):
                return AgentOutput(
                    success=False,
                    data=error_response,
                    message=f"Execution failed: {e}"
                )
            else:
                return error_response

    async def _execute_interactions_only(self, interaction_steps: List[Dict]) -> ActionResult:
        """Execute interaction steps on current page without navigation

        Args:
            interaction_steps: Interaction steps to execute

        Returns:
            ActionResult with execution result
        """
        try:
            if not interaction_steps:
                return ActionResult(extracted_content="No interactions to execute")

            logger.info(f"🎯 Executing {len(interaction_steps)} interaction steps on current page...")

            for idx, step in enumerate(interaction_steps):
                action_type = step.get('action_type', 'unknown')
                logger.info(f"   Step {idx + 1}/{len(interaction_steps)}: {action_type}")

                interaction_result = await self._execute_interaction_step(step)

                # Check if interaction failed
                if interaction_result.success is False:
                    logger.error(f"❌ Interaction step {idx + 1} failed: {interaction_result.error}")
                    return interaction_result

                # Small delay between interactions
                await asyncio.sleep(0.5)

            logger.info(f"✅ All interaction steps completed successfully")

            # Wait for content stability after interactions
            await asyncio.sleep(3)

            return ActionResult(extracted_content=f"Executed {len(interaction_steps)} interaction steps")

        except Exception as e:
            logger.error(f"❌ Interaction execution failed: {e}")
            return ActionResult(success=False, error=str(e))

    async def _navigate_to_pages(self,
                                path: Union[str, List[str]],
                                interaction_steps: List[Dict]) -> ActionResult:
        """Execute sequential page navigation in the same tab

        This method is copied from ScraperAgent with minor modifications.
        It handles navigation to one or more URLs and executes optional
        interaction steps after navigation.

        Args:
            path: Target URL or list of URLs
            interaction_steps: Interaction steps to execute after navigation

        Returns:
            ActionResult with navigation result
        """
        try:
            # Convert single path to list for unified processing
            urls = path if isinstance(path, list) else [path]
            last_result = None

            # Navigate through all URLs in the same tab
            for i, url in enumerate(urls):
                logger.info(f"🔗 Navigating to: {url}")

                # Use event system directly (v0.9+ recommended approach)
                event = self.browser_session.event_bus.dispatch(
                    NavigateToUrlEvent(url=url, new_tab=False)
                )
                await event
                result = await event.event_result(raise_if_any=False, raise_if_none=False)
                await asyncio.sleep(5)  # Wait for page stability

                # Check for failure
                if result and hasattr(result, 'success') and result.success is False:
                    logger.error(f"❌ Navigation failed for URL: {url}, error: {result.error}")
                    return result

                last_result = result

            # Execute interaction steps after navigation (if provided)
            if interaction_steps:
                logger.info(f"🎯 Executing {len(interaction_steps)} interaction steps...")
                for idx, step in enumerate(interaction_steps):
                    action_type = step.get('action_type', 'unknown')
                    logger.info(f"   Step {idx + 1}/{len(interaction_steps)}: {action_type}")

                    interaction_result = await self._execute_interaction_step(step)

                    # Check if interaction failed
                    if interaction_result.success is False:
                        logger.error(f"❌ Interaction step {idx + 1} failed: {interaction_result.error}")
                        return interaction_result

                    # Small delay between interactions
                    await asyncio.sleep(0.5)

                logger.info(f"✅ All interaction steps completed successfully")

                # Wait for content stability after interactions
                await asyncio.sleep(3)

            # Return the last result
            return last_result if last_result else ActionResult(extracted_content="No navigation performed")

        except Exception as e:
            logger.error(f"❌ Navigation failed: {e}")
            return ActionResult(success=False, error=str(e))

    async def _execute_interaction_step(self, step_config: Dict) -> ActionResult:
        """Execute single interaction step (currently only supports scroll)

        This method is copied from ScraperAgent, only scroll is supported in MVP.
        Future versions may add support for click, input, etc.

        Args:
            step_config: Step configuration with action_type and parameters

        Returns:
            ActionResult with execution result
        """
        try:
            action_type = step_config['action_type']
            parameters = step_config.get('parameters', {})

            if action_type == 'scroll':
                # Use event system directly (v0.9+ recommended approach)
                scroll_down = parameters.get('down', True)
                amount = int(parameters.get('num_pages', 1.0) * 500)  # Convert pages to pixels (approx 500px per page)
                direction = "down" if scroll_down else "up"

                logger.debug(f"Scrolling: direction={direction}, amount={amount}px")

                event = self.browser_session.event_bus.dispatch(
                    ScrollEvent(direction=direction, amount=amount)
                )
                await event
                result = await event.event_result(raise_if_any=False, raise_if_none=False)

                # Wait for page stability after scroll
                await asyncio.sleep(1)

                # Create ActionResult-like response for consistency
                return ActionResult(extracted_content=f"Scrolled {direction} {amount}px")
            else:
                logger.warning(f"Unsupported action type: {action_type}. Currently only 'scroll' is supported.")
                return ActionResult(success=False, error=f"Unsupported action type: {action_type}")

        except Exception as e:
            logger.error(f"Interaction step failed: {e}")
            return ActionResult(success=False, error=str(e))

    def _create_response(self, success: bool, message: str = "", **kwargs) -> Dict[str, Any]:
        """Create response dictionary

        Args:
            success: Whether the operation was successful
            message: Response message
            **kwargs: Additional response fields

        Returns:
            Response dictionary
        """
        response = {
            'success': success,
            'message': message
        }
        response.update(kwargs)
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
            'message': 'Navigation failed',
            'error': error_msg,
            'current_url': '',
            'steps_executed': 0
        }
