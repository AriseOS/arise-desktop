"""Browser session management for Electron-embedded browser.

Browser lifecycle is managed by Electron (WebView pool + CDP).
This module provides session access and status reporting.
"""
import logging
from typing import Optional, Callable, Dict, Any

from src.clients.desktop_app.ami_daemon.services.browser_state import BrowserState
from src.clients.desktop_app.ami_daemon.services.browser_window_manager import BrowserWindowManager

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manage browser session access and status.

    Browser is always available via Electron's embedded Chromium CDP.
    No start/stop, no health check, no PID tracking needed.
    """

    def __init__(self, config_service=None):
        self.config_service = config_service
        self.state = BrowserState.RUNNING  # Always running via Electron
        self.window_manager = BrowserWindowManager(config_service=config_service)
        self._status_callbacks: list[Callable] = []

    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "is_running": True,
            "browser_type": "electron-embedded",
        }

    def is_ready(self) -> bool:
        return True

    def subscribe_status_change(self, callback: Callable[[str], None]):
        self._status_callbacks.append(callback)

    async def cleanup(self):
        logger.info("Browser manager cleanup (no-op for Electron-embedded browser)")
