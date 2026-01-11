"""
Resource type definitions for workflow resource management
"""

from enum import Enum
from typing import List


class ResourceType(Enum):
    """Resource types supported by the system"""
    SCRAPER_SCRIPT = "scraper_scripts"
    CODE_AGENT_SCRIPT = "code_agent_scripts"
    CUSTOM_PROMPT = "custom_prompts"


class ResourceConfig:
    """Configuration for each resource type - defines which files to sync"""

    SYNC_FILES = {
        ResourceType.SCRAPER_SCRIPT: [
            "extraction_script.py",
            "requirement.json",
            "test_extraction.py",
            "dom_tools.py"
        ],
        ResourceType.CODE_AGENT_SCRIPT: [
            "generated_code.py",
            "config.json"
        ],
        ResourceType.CUSTOM_PROMPT: [
            "prompt.txt",
            "metadata.json"
        ]
    }

    @classmethod
    def get_sync_files(cls, resource_type: ResourceType) -> List[str]:
        """Get list of files to sync for a resource type"""
        return cls.SYNC_FILES.get(resource_type, [])
