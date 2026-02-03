"""
Prompt Template Base Module

Provides base classes for prompt templates with variable substitution
and context awareness. Based on Eigent's prompt patterns.

References:
- Eigent: third-party/eigent/backend/app/utils/agent.py
- Anthropic guidelines: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering
"""

import platform
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class PromptContext:
    """Context information for prompt templates.

    Provides environment awareness and dynamic context injection,
    following Eigent's pattern of including operating environment
    in system prompts.
    """
    # Operating environment
    platform: str = field(default_factory=lambda: platform.system())
    architecture: str = field(default_factory=lambda: platform.machine())
    working_directory: str = ""
    current_date: str = ""

    # Task context
    user_id: str = ""
    task_id: str = ""
    agent_id: str = ""

    # Memory and workflow references
    memory_reference: str = ""
    workflow_hints: str = ""
    reference_path: str = ""

    # Browser context
    current_url: str = ""
    page_title: str = ""

    # Custom context for extensibility
    custom_context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize default values."""
        if not self.current_date:
            self.current_date = datetime.now().strftime("%Y-%m-%d")

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for template formatting."""
        base_dict = {
            "platform": self.platform,
            "architecture": self.architecture,
            "working_directory": self.working_directory,
            "current_date": self.current_date,
            "user_id": self.user_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "memory_reference": self.memory_reference,
            "workflow_hints": self.workflow_hints,
            "reference_path": self.reference_path,
            "current_url": self.current_url,
            "page_title": self.page_title,
        }
        # Merge custom context
        base_dict.update(self.custom_context)
        return base_dict

    def with_custom(self, **kwargs) -> "PromptContext":
        """Create a new context with additional custom values."""
        new_custom = {**self.custom_context, **kwargs}
        return PromptContext(
            platform=self.platform,
            architecture=self.architecture,
            working_directory=self.working_directory,
            current_date=self.current_date,
            user_id=self.user_id,
            task_id=self.task_id,
            agent_id=self.agent_id,
            memory_reference=self.memory_reference,
            workflow_hints=self.workflow_hints,
            reference_path=self.reference_path,
            current_url=self.current_url,
            page_title=self.page_title,
            custom_context=new_custom,
        )


class PromptTemplate:
    """Base class for prompt templates with variable substitution.

    Supports:
    - {variable} style substitution
    - Optional sections that can be omitted if empty
    - Nested template composition
    """

    def __init__(self, template: str, name: str = "", description: str = ""):
        """Initialize prompt template.

        Args:
            template: The template string with {variable} placeholders
            name: Optional name for the template
            description: Optional description
        """
        self.template = template
        self.name = name
        self.description = description
        self._cached_variables: Optional[List[str]] = None

    @property
    def variables(self) -> List[str]:
        """Get list of variable names in the template."""
        if self._cached_variables is None:
            # Find all {variable} patterns, excluding {{ escaped braces
            pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
            self._cached_variables = list(set(re.findall(pattern, self.template)))
        return self._cached_variables

    def format(self, context: Optional[PromptContext] = None, **kwargs) -> str:
        """Format the template with context and additional kwargs.

        Args:
            context: PromptContext with environment and task info
            **kwargs: Additional variables to substitute

        Returns:
            Formatted prompt string
        """
        ctx = context or PromptContext()
        format_dict = ctx.to_dict()
        format_dict.update(kwargs)

        # Handle missing variables with empty strings
        for var in self.variables:
            if var not in format_dict:
                format_dict[var] = ""

        return self.template.format(**format_dict)

    def format_safe(self, context: Optional[PromptContext] = None, **kwargs) -> str:
        """Format template, returning original on error.

        Safer version that won't raise on missing variables.
        """
        try:
            return self.format(context, **kwargs)
        except (KeyError, ValueError):
            return self.template

    def with_section(self, section_name: str, content: str) -> "PromptTemplate":
        """Create a new template with a section filled in.

        Useful for composing prompts from reusable sections.

        Args:
            section_name: The variable name to replace
            content: The content to insert

        Returns:
            New PromptTemplate with the section filled
        """
        new_template = self.template.replace(f"{{{section_name}}}", content)
        return PromptTemplate(new_template, name=self.name, description=self.description)

    def append(self, additional: str) -> "PromptTemplate":
        """Create a new template with additional content appended."""
        return PromptTemplate(
            self.template + "\n" + additional,
            name=self.name,
            description=self.description
        )

    def prepend(self, prefix: str) -> "PromptTemplate":
        """Create a new template with prefix content."""
        return PromptTemplate(
            prefix + "\n" + self.template,
            name=self.name,
            description=self.description
        )

    def __str__(self) -> str:
        """Return the raw template string."""
        return self.template

    def __repr__(self) -> str:
        """Return representation with name if available."""
        if self.name:
            return f"PromptTemplate(name='{self.name}')"
        return f"PromptTemplate({len(self.template)} chars)"


class PromptSection:
    """Reusable prompt section that can be conditionally included.

    Useful for building prompts with optional components.
    """

    def __init__(self, title: str, content: str, condition_var: str = ""):
        """Initialize a prompt section.

        Args:
            title: Section title (e.g., "## Memory Reference")
            content: Section content template
            condition_var: If set, section only included when this var is truthy
        """
        self.title = title
        self.content = content
        self.condition_var = condition_var

    def render(self, context: Optional[PromptContext] = None, **kwargs) -> str:
        """Render the section if conditions are met.

        Args:
            context: PromptContext
            **kwargs: Additional variables

        Returns:
            Rendered section or empty string
        """
        ctx = context or PromptContext()
        format_dict = ctx.to_dict()
        format_dict.update(kwargs)

        # Check condition
        if self.condition_var:
            if not format_dict.get(self.condition_var):
                return ""

        # Format content
        try:
            formatted_content = self.content.format(**format_dict)
        except (KeyError, ValueError):
            formatted_content = self.content

        if not formatted_content.strip():
            return ""

        return f"{self.title}\n{formatted_content}\n"


class CompositePrompt:
    """Prompt composed of multiple optional sections.

    Allows building complex prompts from reusable components.
    """

    def __init__(self, base_template: PromptTemplate):
        """Initialize with a base template.

        Args:
            base_template: The base prompt template
        """
        self.base = base_template
        self.sections: List[PromptSection] = []

    def add_section(self, section: PromptSection) -> "CompositePrompt":
        """Add a section to the prompt."""
        self.sections.append(section)
        return self

    def format(self, context: Optional[PromptContext] = None, **kwargs) -> str:
        """Format the complete prompt with all sections.

        Args:
            context: PromptContext
            **kwargs: Additional variables

        Returns:
            Complete formatted prompt
        """
        # Render all sections
        sections_content = ""
        for section in self.sections:
            rendered = section.render(context, **kwargs)
            if rendered:
                sections_content += rendered + "\n"

        # Add sections to kwargs for base template
        kwargs["sections"] = sections_content.strip()

        return self.base.format(context, **kwargs)


# Common prompt sections used across agents
MEMORY_REFERENCE_SECTION = PromptSection(
    title="<memory_reference>",
    content="""## Historical Workflow Reference

A similar workflow was found in memory that successfully completed a related task.

**Reference Path:**
{memory_reference}

Use this as guidance, but adapt to the current page state and task requirements.
</memory_reference>""",
    condition_var="memory_reference"
)

WORKFLOW_HINTS_SECTION = PromptSection(
    title="<workflow_hints>",
    content="""## Workflow Hints

The following hints describe the expected navigation flow:

{workflow_hints}

Follow this flow while adapting to actual page content.
</workflow_hints>""",
    condition_var="workflow_hints"
)

OPERATING_ENVIRONMENT_SECTION = PromptSection(
    title="<operating_environment>",
    content="""- System: {platform} ({architecture})
- Working Directory: {working_directory}
- Current Date: {current_date}""",
    condition_var=""  # Always included
)


# Conversation Memory Section - guides Agent to search history when needed
CONVERSATION_MEMORY_SECTION = PromptSection(
    title="## Conversation Memory",
    content="""You have access to the user's conversation history. Before answering questions about:
- Previous tasks or conversations ("上次", "之前", "last time", "before")
- User preferences or habits ("我喜欢", "我通常", "I prefer")
- Past decisions or outcomes ("之前决定", "上次结果", "we decided")
- Anything the user mentioned "before" or "previously"

**You MUST first search memory:**

1. Call `search_conversations(query)` to find relevant past conversations
2. If results found, call `get_conversation_messages(conversation_id)` for details
3. Then answer based on the retrieved context

If no relevant memory found after search, acknowledge that you checked but found nothing.

**Available memory tools:**
- `search_conversations(query)` - Search past conversations by keyword
- `get_conversation_messages(conversation_id)` - Get messages from a conversation
- `get_recent_conversations()` - List recent conversations

**Example usage:**
- User: "上次在哪个网站找的产品？" → Call search_conversations("产品") first
- User: "继续之前的任务" → Call get_recent_conversations() to find latest task
- User: "我通常喜欢什么格式？" → Call search_conversations("格式 偏好")""",
    condition_var="enable_conversation_memory"  # Only include when memory toolkit is enabled
)
