"""Script Generation Types"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
from pathlib import Path


class ScriptType(Enum):
    """Type of generated script"""
    BROWSER_FIND_ELEMENT = "browser_find_element"
    BROWSER_FIND_XPATH = "browser_find_xpath"
    SCRAPER_EXTRACTION = "scraper_extraction"


@dataclass
class ScriptGenerationResult:
    """Result of script generation"""
    success: bool
    script_type: ScriptType
    script_content: Optional[str] = None
    script_path: Optional[Path] = None
    working_dir: Optional[Path] = None
    error: Optional[str] = None
    turns: int = 0
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "script_type": self.script_type.value,
            "script_content": self.script_content,
            "script_path": str(self.script_path) if self.script_path else None,
            "working_dir": str(self.working_dir) if self.working_dir else None,
            "error": self.error,
            "turns": self.turns,
            "metadata": self.metadata
        }


@dataclass
class BrowserTask:
    """Task description for browser script generation"""
    task: str  # e.g., "Click the login button"
    operation: str  # "click", "fill", "scroll_to_element"
    xpath_hints: Dict[str, str]  # {"target": "//*[@id='login']"}
    text: Optional[str] = None  # For fill operations

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "operation": self.operation,
            "xpath_hints": self.xpath_hints,
            "text": self.text
        }


@dataclass
class ScraperRequirement:
    """Data requirements for scraper script generation"""
    user_description: str  # e.g., "Extract product list"
    output_format: Dict[str, str]  # {"name": "Product name", "price": "Price"}
    xpath_hints: Optional[Dict[str, str]] = None
    sample_data: Optional[list] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_description": self.user_description,
            "output_format": self.output_format,
            "xpath_hints": self.xpath_hints,
            "sample_data": self.sample_data
        }
