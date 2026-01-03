"""Script Generation Module

This module provides reusable script generation capabilities for browser automation
and data extraction. It's used by both:
- BaseApp agents (BrowserAgent, ScraperAgent) during workflow execution
- Cloud Backend (Intent Builder) for pre-generating scripts during workflow creation

Key components:
- BrowserScriptGenerator: Generates find_element.py for click/fill operations
- ScraperScriptGenerator: Generates extraction_script.py for data extraction
- Templates: Reusable script templates for Claude Agent SDK
"""

from .browser_script_generator import BrowserScriptGenerator
from .scraper_script_generator import ScraperScriptGenerator
from .types import ScriptGenerationResult, ScriptType

__all__ = [
    "BrowserScriptGenerator",
    "ScraperScriptGenerator",
    "ScriptGenerationResult",
    "ScriptType",
]
