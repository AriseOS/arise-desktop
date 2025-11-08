"""Browser session management"""
import logging

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manage global browser session for workflow execution"""

    def __init__(self, headless: bool = False, config_service=None):
        """Initialize browser manager

        Args:
            headless: Run browser in headless mode
            config_service: Configuration service for user data directory
        """
        self.headless = headless
        self.config_service = config_service
        self.session_manager = None
        self.global_session = None

    async def init_global_session(self):
        """Initialize global browser session"""
        from src.clients.base_app.base_app.base_agent.tools.browser_session_manager import (
            BrowserSessionManager
        )

        self.session_manager = await BrowserSessionManager.get_instance()
        self.global_session = await self.session_manager.get_or_create_session(
            session_id="global",
            config_service=self.config_service,  # Pass config service
            headless=self.headless,
            keep_alive=True
        )
        logger.info("Global browser session initialized")

    def is_ready(self) -> bool:
        """Check if browser is ready"""
        return self.global_session is not None

    async def cleanup(self):
        """Cleanup browser resources"""
        if self.session_manager:
            await self.session_manager.close_all_sessions()
            logger.info("Browser sessions cleaned up")
