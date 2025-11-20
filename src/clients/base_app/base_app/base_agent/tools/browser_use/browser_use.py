"""Compatibility wrapper for the Browser-Use tool.

This module re-introduces the historical ``BrowserTool`` entry point that the
rest of the codebase imports (``from ..tools.browser_use import
BrowserTool``). The actual implementation now lives in
``autonomous_browser.py``.  To avoid touching every caller, we simply inherit
from the new ``AutonomousBrowserTool`` class and expose the same constructor
signature, so existing imports continue to work.
"""

from typing import Optional

from .autonomous_browser import AutonomousBrowserTool, BrowserConfig


class BrowserTool(AutonomousBrowserTool):
    """Backwards-compatible Browser tool alias."""

    def __init__(self, config: Optional[BrowserConfig] = None):
        super().__init__(config=config)


__all__ = ["BrowserTool", "BrowserConfig"]
