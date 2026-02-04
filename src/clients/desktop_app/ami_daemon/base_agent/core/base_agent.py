"""
BaseAgent Framework
Base class for all custom Agents, providing standardized interfaces and capabilities
"""
import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

from .schemas import (
    AgentConfig, AgentResult, AgentState, AgentStatus
)
from ..tools.base_tool import BaseTool, ToolResult, ToolStatus
from ..memory.memory_manager import MemoryManager

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Universal Agent base framework.
    All custom Agents inherit from this class for standardized interfaces.

    Core design principles:
    1. Standardized interfaces - Clear extension specs for AI tools
    2. Tool integration - Seamless integration with various external tools
    3. State management - Complete execution state and memory management
    4. Extensibility - Support for hooks and plugin mechanisms
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        config_service: Optional[Any] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        browser_manager: Optional[Any] = None,
        browser_session_id: Optional[str] = None,
        cloud_client: Optional[Any] = None
    ):
        """Initialize BaseAgent

        Args:
            config: Agent configuration
            config_service: Configuration service instance
            provider_config: LLM provider configuration
            user_id: User ID for Memory isolation
            browser_manager: BrowserManager instance for unified browser session management
            browser_session_id: Browser session ID
            cloud_client: CloudClient instance for cloud communication
        """
        # Basic configuration
        self.config = config or AgentConfig(name="BaseAgent")
        self.config_service = config_service
        self.id = str(uuid.uuid4())

        # Browser management
        self.browser_manager = browser_manager
        self.browser_session_id = browser_session_id

        # Cloud client for script generation
        self.cloud_client = cloud_client

        # Core components
        self.tools: Dict[str, BaseTool] = {}
        self.hooks: Dict[str, List[Callable]] = {}

        # Provider initialization
        self.provider = None
        self.provider_config = provider_config or {}
        self._initialize_provider()

        # Determine Memory user_id
        if user_id:
            memory_user_id = user_id
            self.user_id = user_id
            logger.info(f"BaseAgent instance {self.id[:8]} started, serving user: {user_id}")
        else:
            memory_user_id = f"agent_{self.id}"
            self.user_id = memory_user_id
            logger.warning(
                f"BaseAgent user_id not specified, using instance-isolated memory namespace: {memory_user_id[:20]}..."
            )

        # Memory system
        self.memory_manager = MemoryManager(
            user_id=memory_user_id,
            config_service=config_service
        )
        logger.info(f"Memory system enabled, user_id: {memory_user_id}")

        # State management
        self.state = AgentState(
            agent_id=self.id,
            status=AgentStatus.CREATED
        )

        # Execution statistics
        self._execution_history: List[Dict[str, Any]] = []

        # Setup logging
        self._setup_logging()

        logger.info(f"BaseAgent {self.config.name} ({self.id}) initialized")

    # ==================== Standardized Interfaces ====================

    async def execute(self, input_data: Any, **kwargs) -> AgentResult:
        """
        Main execution entry - subclasses must implement

        Args:
            input_data: Input data
            **kwargs: Additional parameters

        Returns:
            AgentResult: Execution result
        """
        raise NotImplementedError("Subclasses must implement execute method")

    async def initialize(self) -> bool:
        """
        Initialize Agent

        Returns:
            bool: Whether initialization was successful
        """
        try:
            self.state.status = AgentStatus.INITIALIZING
            await self._trigger_hook('before_initialize')

            # Initialize Provider
            if self.provider:
                provider_success = await self.initialize_provider_async()
                if not provider_success:
                    logger.error("Provider initialization failed")
                    self.state.status = AgentStatus.FAILED
                    return False
            else:
                logger.error("Provider not set")
                self.state.status = AgentStatus.FAILED
                return False

            # Initialize all tools
            for tool_name, tool in self.tools.items():
                success = await tool.initialize()
                if not success:
                    logger.error(f"Tool {tool_name} initialization failed")
                    return False

            self.state.status = AgentStatus.READY
            self.state.started_at = datetime.now()

            await self._trigger_hook('after_initialize')
            logger.info(f"Agent {self.config.name} initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Agent initialization failed: {e}")
            self.state.status = AgentStatus.FAILED
            return False

    async def cleanup(self) -> bool:
        """
        Cleanup resources

        Returns:
            bool: Whether cleanup was successful
        """
        try:
            await self._trigger_hook('before_cleanup')

            # Cleanup all tools
            for tool_name, tool in self.tools.items():
                await tool.cleanup()

            self.state.status = AgentStatus.STOPPED
            self.state.completed_at = datetime.now()

            await self._trigger_hook('after_cleanup')
            logger.info(f"Agent {self.config.name} cleanup completed")
            return True

        except Exception as e:
            logger.error(f"Agent cleanup failed: {e}")
            return False

    # ==================== Private Methods ====================

    def _setup_logging(self) -> None:
        """Setup logging"""
        if self.config.enable_logging:
            logging.basicConfig(
                level=getattr(logging, self.config.log_level),
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

    async def _trigger_hook(self, event: str, **kwargs) -> None:
        """Trigger hook"""
        if event in self.hooks:
            for callback in self.hooks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(**kwargs)
                    else:
                        callback(**kwargs)
                except Exception as e:
                    logger.error(f"Hook execution failed {event}: {e}")

    # ==================== Utility Methods ====================

    def get_status(self) -> AgentStatus:
        """Get current status"""
        return self.state.status

    def get_execution_history(self) -> List[Dict[str, Any]]:
        """Get execution history"""
        return self._execution_history.copy()

    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get tool info"""
        if tool_name in self.tools:
            tool = self.tools[tool_name]
            return {
                'name': tool_name,
                'metadata': tool.metadata.dict(),
                'actions': tool.get_available_actions(),
                'status': tool.status.value
            }
        return None

    async def health_check(self) -> Dict[str, Any]:
        """Health check"""
        health_info = {
            'agent_id': self.id,
            'status': self.state.status.value,
            'uptime': (datetime.now() - self.state.created_at).total_seconds(),
            'tools': {},
            'execution_count': self.state.execution_count
        }

        for tool_name, tool in self.tools.items():
            health_info['tools'][tool_name] = await tool.health_check()

        if self.provider:
            health_info['provider'] = {
                'type': type(self.provider).__name__,
                'initialized': getattr(self.provider, 'is_initialized', False),
                'model': getattr(self.provider, 'model_name', 'unknown')
            }

        return health_info

    # ==================== Provider Management ====================

    def _initialize_provider(self) -> None:
        """Initialize Provider - auto-load from config_service"""
        try:
            if not self.provider_config and self.config_service:
                import os
                logger.info("No provider_config provided, loading from config_service")

                provider_type = self.config_service.get('llm.provider')
                if not provider_type:
                    raise ValueError("llm.provider not configured")
                model_name = self.config_service.get('llm.model')
                if not model_name:
                    raise ValueError("llm.model not configured")

                if provider_type == 'anthropic':
                    api_key = os.environ.get('ANTHROPIC_API_KEY')
                else:
                    api_key = os.environ.get('OPENAI_API_KEY')

                use_proxy = self.config_service.get('llm.use_proxy', False)
                base_url = None
                if use_proxy:
                    base_url = self.config_service.get('llm.proxy_url')
                    if not base_url:
                        raise ValueError("llm.proxy_url not configured but llm.use_proxy is true")
                    logger.info(f"API Proxy enabled: {base_url}")

                self.provider_config = {
                    'type': provider_type,
                    'api_key': api_key,
                    'model_name': model_name,
                    'base_url': base_url
                }

            provider_type = self.provider_config.get('type', 'openai')
            api_key = self.provider_config.get('api_key')
            model_name = self.provider_config.get('model_name')
            base_url = self.provider_config.get('base_url')

            if provider_type == 'openai':
                from src.common.llm import OpenAIProvider
                self.provider = OpenAIProvider(api_key=api_key, model_name=model_name, base_url=base_url)
            elif provider_type == 'anthropic':
                from src.common.llm import AnthropicProvider
                self.provider = AnthropicProvider(api_key=api_key, model_name=model_name, base_url=base_url)
            else:
                logger.warning(f"Unknown provider type: {provider_type}")
                return

            logger.info(f"Provider initialized: {provider_type}, model: {model_name}")

        except Exception as e:
            logger.error(f"Provider initialization failed: {e}")
            self.provider = None

    async def initialize_provider_async(self) -> bool:
        """Async initialize Provider"""
        if not self.provider:
            logger.warning("Provider not set")
            return False

        try:
            await self.provider._initialize_client()
            logger.info("Provider async initialization completed")
            return True
        except Exception as e:
            logger.error(f"Provider async initialization failed: {e}")
            return False

    def get_provider_info(self) -> Dict[str, Any]:
        """Get Provider info"""
        if not self.provider:
            return {"status": "not_initialized"}

        return {
            "type": type(self.provider).__name__,
            "model": getattr(self.provider, 'model_name', 'unknown'),
            "initialized": getattr(self.provider, 'is_initialized', False),
            "api_key_set": bool(getattr(self.provider, 'api_key', None))
        }

    # ==================== Tool Call Interface ====================

    async def use_tool(
        self,
        tool_name: str,
        action: str,
        params: Dict[str, Any],
        **kwargs
    ) -> ToolResult:
        """
        Standardized tool call interface

        Args:
            tool_name: Tool name
            action: Action name
            params: Action parameters
            **kwargs: Additional parameters

        Returns:
            ToolResult: Tool execution result
        """
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not registered")

        tool = self.tools[tool_name]

        try:
            await self._trigger_hook('before_tool_call', tool_name=tool_name, action=action)

            call_info = {
                'tool': tool_name,
                'action': action,
                'params': params,
                'timestamp': datetime.now()
            }
            self._execution_history.append(call_info)

            result = await tool.execute_with_retry(action, params, **kwargs)

            call_info['result'] = {
                'success': result.success,
                'execution_time': result.execution_time
            }

            await self._trigger_hook('after_tool_call', tool_name=tool_name, result=result)

            logger.debug(f"Tool call completed: {tool_name}.{action} -> {result.success}")
            return result

        except Exception as e:
            logger.error(f"Tool call failed: {tool_name}.{action}, error: {e}")
            return ToolResult(
                success=False,
                message=f"Tool call failed: {str(e)}",
                status=ToolStatus.ERROR
            )

    def register_tool(self, name: str, tool: BaseTool) -> None:
        """
        Register tool

        Args:
            name: Tool name
            tool: Tool instance
        """
        if not isinstance(tool, BaseTool):
            raise ValueError("Tool must inherit from BaseTool")

        self.tools[name] = tool
        logger.info(f"Tool '{name}' registered: {tool.metadata.description}")

    def unregister_tool(self, name: str) -> bool:
        """
        Unregister tool

        Args:
            name: Tool name

        Returns:
            bool: Whether unregistration was successful
        """
        if name in self.tools:
            del self.tools[name]
            logger.info(f"Tool '{name}' unregistered")
            return True
        return False

    def get_registered_tools(self) -> List[str]:
        """
        Get list of registered tools

        Returns:
            List[str]: Tool name list
        """
        return list(self.tools.keys())
