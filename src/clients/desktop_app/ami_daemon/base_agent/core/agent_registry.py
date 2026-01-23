"""
Agent Registry Module

Central registry for all specialized agents with dynamic routing.
Based on Eigent's multi-agent architecture with 5 agent types.

References:
- Eigent: third-party/eigent/backend/app/service/task.py
- Eigent: third-party/eigent/backend/app/utils/workforce.py
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Standard agent types (from Eigent).

    These represent the core specialized agents that can handle
    different categories of tasks.
    """
    BROWSER = "browser_agent"
    DEVELOPER = "developer_agent"
    DOCUMENT = "document_agent"
    SOCIAL_MEDIUM = "social_medium_agent"
    QUESTION_CONFIRM = "question_confirm_agent"

    # Additional 2ami-specific agents
    TEXT = "text_agent"
    VARIABLE = "variable_agent"
    SCRAPER = "scraper_agent"
    STORAGE = "storage_agent"
    TAVILY = "tavily_agent"


@dataclass
class AgentInfo:
    """Metadata about a registered agent."""
    agent_type: str
    agent_class: Type  # The actual agent class
    description: str
    capabilities: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    priority: int = 0  # Higher = more preferred when multiple agents match

    # Optional factory function for custom instantiation
    factory: Optional[Callable[..., Any]] = None

    def __post_init__(self):
        """Validate agent info."""
        if not self.agent_type:
            raise ValueError("agent_type is required")
        if not self.agent_class:
            raise ValueError("agent_class is required")


class AgentRegistry:
    """Central registry for all specialized agents.

    Provides:
    - Agent registration and lookup
    - Capability-based agent matching
    - Tag-based filtering
    - Factory pattern for agent instantiation
    """

    def __init__(self):
        """Initialize empty registry."""
        self._agents: Dict[str, AgentInfo] = {}
        self._capability_index: Dict[str, List[str]] = {}  # capability -> [agent_types]
        self._tag_index: Dict[str, List[str]] = {}  # tag -> [agent_types]

    def register(
        self,
        agent_type: str,
        agent_class: Type,
        description: str = "",
        capabilities: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        priority: int = 0,
        factory: Optional[Callable] = None,
        replace: bool = False,
    ) -> None:
        """Register an agent.

        Args:
            agent_type: Unique identifier for this agent type
            agent_class: The agent class to instantiate
            description: Human-readable description
            capabilities: List of capabilities (e.g., ["web_search", "navigation"])
            tags: Tags for filtering (e.g., ["browser", "automation"])
            priority: Priority when multiple agents match (higher = preferred)
            factory: Optional factory function for instantiation
            replace: Whether to replace existing registration

        Raises:
            ValueError: If agent_type already registered and replace=False
        """
        if agent_type in self._agents and not replace:
            raise ValueError(f"Agent type '{agent_type}' is already registered")

        info = AgentInfo(
            agent_type=agent_type,
            agent_class=agent_class,
            description=description,
            capabilities=capabilities or [],
            tags=tags or [],
            priority=priority,
            factory=factory,
        )
        self._agents[agent_type] = info

        # Update indexes
        for cap in info.capabilities:
            if cap not in self._capability_index:
                self._capability_index[cap] = []
            if agent_type not in self._capability_index[cap]:
                self._capability_index[cap].append(agent_type)

        for tag in info.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            if agent_type not in self._tag_index[tag]:
                self._tag_index[tag].append(agent_type)

        logger.debug(f"Registered agent: {agent_type}")

    def unregister(self, agent_type: str) -> bool:
        """Unregister an agent.

        Args:
            agent_type: The agent type to unregister

        Returns:
            True if agent was unregistered, False if not found
        """
        if agent_type not in self._agents:
            return False

        info = self._agents.pop(agent_type)

        # Update indexes
        for cap in info.capabilities:
            if cap in self._capability_index:
                self._capability_index[cap] = [
                    t for t in self._capability_index[cap] if t != agent_type
                ]

        for tag in info.tags:
            if tag in self._tag_index:
                self._tag_index[tag] = [
                    t for t in self._tag_index[tag] if t != agent_type
                ]

        return True

    def get(self, agent_type: str) -> Optional[AgentInfo]:
        """Get agent info by type.

        Args:
            agent_type: The agent type to look up

        Returns:
            AgentInfo if found, None otherwise
        """
        return self._agents.get(agent_type)

    def get_class(self, agent_type: str) -> Optional[Type]:
        """Get agent class by type.

        Args:
            agent_type: The agent type to look up

        Returns:
            Agent class if found, None otherwise
        """
        info = self._agents.get(agent_type)
        return info.agent_class if info else None

    def create(self, agent_type: str, **kwargs) -> Any:
        """Create an agent instance.

        Args:
            agent_type: The agent type to instantiate
            **kwargs: Arguments to pass to constructor/factory

        Returns:
            Agent instance

        Raises:
            KeyError: If agent_type not registered
        """
        info = self._agents.get(agent_type)
        if not info:
            raise KeyError(f"Agent type '{agent_type}' not registered")

        if info.factory:
            return info.factory(**kwargs)
        else:
            return info.agent_class(**kwargs)

    def find_by_capability(self, capability: str) -> List[AgentInfo]:
        """Find agents that have a specific capability.

        Args:
            capability: The capability to search for

        Returns:
            List of AgentInfo, sorted by priority (highest first)
        """
        agent_types = self._capability_index.get(capability, [])
        agents = [self._agents[t] for t in agent_types if t in self._agents]
        return sorted(agents, key=lambda a: a.priority, reverse=True)

    def find_by_tag(self, tag: str) -> List[AgentInfo]:
        """Find agents that have a specific tag.

        Args:
            tag: The tag to search for

        Returns:
            List of AgentInfo, sorted by priority (highest first)
        """
        agent_types = self._tag_index.get(tag, [])
        agents = [self._agents[t] for t in agent_types if t in self._agents]
        return sorted(agents, key=lambda a: a.priority, reverse=True)

    def find_by_capabilities(
        self,
        required: List[str],
        preferred: Optional[List[str]] = None
    ) -> List[AgentInfo]:
        """Find agents that match required capabilities.

        Args:
            required: Capabilities that must all be present
            preferred: Additional preferred capabilities (for scoring)

        Returns:
            List of matching AgentInfo, sorted by match quality
        """
        preferred = preferred or []
        candidates = []

        for agent_type, info in self._agents.items():
            # Check all required capabilities
            if not all(cap in info.capabilities for cap in required):
                continue

            # Score based on preferred capabilities
            score = info.priority
            for cap in preferred:
                if cap in info.capabilities:
                    score += 1

            candidates.append((score, info))

        # Sort by score (highest first)
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [info for _, info in candidates]

    def list_agents(self) -> List[str]:
        """List all registered agent types.

        Returns:
            List of agent type names
        """
        return list(self._agents.keys())

    def list_capabilities(self) -> List[str]:
        """List all known capabilities.

        Returns:
            List of capability names
        """
        return list(self._capability_index.keys())

    def list_tags(self) -> List[str]:
        """List all known tags.

        Returns:
            List of tag names
        """
        return list(self._tag_index.keys())

    def get_all(self) -> Dict[str, AgentInfo]:
        """Get all registered agents.

        Returns:
            Dictionary mapping agent types to AgentInfo
        """
        return dict(self._agents)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize registry for inspection.

        Returns:
            Dictionary representation of registry
        """
        return {
            "agents": {
                t: {
                    "description": info.description,
                    "capabilities": info.capabilities,
                    "tags": info.tags,
                    "priority": info.priority,
                }
                for t, info in self._agents.items()
            },
            "capabilities": dict(self._capability_index),
            "tags": dict(self._tag_index),
        }


# Global default registry instance
_default_registry: Optional[AgentRegistry] = None


def get_registry() -> AgentRegistry:
    """Get the default agent registry.

    Returns:
        The global AgentRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = AgentRegistry()
    return _default_registry


def register_agent(
    agent_type: str,
    agent_class: Type,
    description: str = "",
    capabilities: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    priority: int = 0,
    factory: Optional[Callable] = None,
) -> None:
    """Register an agent in the default registry.

    Convenience function for registering agents.
    """
    get_registry().register(
        agent_type=agent_type,
        agent_class=agent_class,
        description=description,
        capabilities=capabilities,
        tags=tags,
        priority=priority,
        factory=factory,
    )


def get_agent(agent_type: str) -> Optional[Type]:
    """Get an agent class from the default registry.

    Convenience function for looking up agents.
    """
    return get_registry().get_class(agent_type)


def create_agent(agent_type: str, **kwargs) -> Any:
    """Create an agent from the default registry.

    Convenience function for instantiating agents.
    """
    return get_registry().create(agent_type, **kwargs)


_default_agents_registered = False


def register_default_agents() -> None:
    """Register all default agents in the registry.

    This should be called during application startup to
    populate the registry with available agents.

    This function is idempotent - calling it multiple times is safe.
    """
    global _default_agents_registered
    if _default_agents_registered:
        return

    # Import here to avoid circular imports
    from ..agents import (
        EigentStyleBrowserAgent,
        EigentBrowserAgent,
        TextAgent,
        VariableAgent,
        BrowserAgent,
        ScraperAgent,
        StorageAgent,
        TavilyAgent,
        # Specialized agents from Eigent migration
        DeveloperAgent,
        DocumentAgent,
        SocialMediumAgent,
        QuestionConfirmAgent,
    )

    registry = get_registry()

    # Browser agents
    registry.register(
        agent_type=AgentType.BROWSER.value,
        agent_class=EigentStyleBrowserAgent,
        description="Web automation and browser interactions",
        capabilities=["web_navigation", "web_search", "data_extraction", "form_filling"],
        tags=["browser", "web", "automation", "research"],
        priority=10,
    )

    registry.register(
        agent_type="eigent_browser_agent",
        agent_class=EigentBrowserAgent,
        description="ReAct-style browser agent with plan execution",
        capabilities=["web_navigation", "plan_execution", "action_sequencing"],
        tags=["browser", "react", "planning"],
        priority=5,
    )

    registry.register(
        agent_type="basic_browser_agent",
        agent_class=BrowserAgent,
        description="Basic browser interaction agent",
        capabilities=["web_navigation", "basic_interaction"],
        tags=["browser", "basic"],
        priority=1,
    )

    # Text agent
    registry.register(
        agent_type=AgentType.TEXT.value,
        agent_class=TextAgent,
        description="Text generation and processing",
        capabilities=["text_generation", "summarization", "analysis"],
        tags=["text", "nlp", "generation"],
        priority=5,
    )

    # Variable agent
    registry.register(
        agent_type=AgentType.VARIABLE.value,
        agent_class=VariableAgent,
        description="Variable operations and data manipulation",
        capabilities=["variable_management", "data_transformation"],
        tags=["variable", "data", "workflow"],
        priority=5,
    )

    # Scraper agent
    registry.register(
        agent_type=AgentType.SCRAPER.value,
        agent_class=ScraperAgent,
        description="Web scraping and data extraction",
        capabilities=["data_extraction", "web_scraping", "parsing"],
        tags=["scraper", "extraction", "data"],
        priority=5,
    )

    # Storage agent
    registry.register(
        agent_type=AgentType.STORAGE.value,
        agent_class=StorageAgent,
        description="Data storage and retrieval",
        capabilities=["data_storage", "file_operations", "persistence"],
        tags=["storage", "file", "data"],
        priority=5,
    )

    # Tavily agent
    registry.register(
        agent_type=AgentType.TAVILY.value,
        agent_class=TavilyAgent,
        description="Tavily search and research",
        capabilities=["web_search", "research", "information_retrieval"],
        tags=["search", "research", "tavily"],
        priority=3,
    )

    # ==================== Specialized Agents (Eigent Migration) ====================

    # Developer agent
    registry.register(
        agent_type=AgentType.DEVELOPER.value,
        agent_class=DeveloperAgent,
        description="Coding, debugging, git operations, file editing",
        capabilities=["coding", "debugging", "git_operations", "file_editing", "testing"],
        tags=["developer", "code", "programming", "git"],
        priority=10,
    )

    # Document agent
    registry.register(
        agent_type=AgentType.DOCUMENT.value,
        agent_class=DocumentAgent,
        description="Document creation, Google Drive, Notion operations",
        capabilities=["document_creation", "google_drive", "notion", "file_organization"],
        tags=["document", "drive", "notion", "files"],
        priority=8,
    )

    # Social medium agent
    registry.register(
        agent_type=AgentType.SOCIAL_MEDIUM.value,
        agent_class=SocialMediumAgent,
        description="Email (Gmail), calendar, social media communication",
        capabilities=["email", "calendar", "gmail", "scheduling", "communication"],
        tags=["email", "calendar", "social", "communication"],
        priority=8,
    )

    # Question/Confirm agent
    registry.register(
        agent_type=AgentType.QUESTION_CONFIRM.value,
        agent_class=QuestionConfirmAgent,
        description="Human-in-the-loop confirmations and questions",
        capabilities=["human_interaction", "confirmation", "question_answering"],
        tags=["human", "confirmation", "question"],
        priority=5,
    )

    _default_agents_registered = True
    logger.info(f"Registered {len(registry.list_agents())} default agents")


# Agent type constants for convenience
BROWSER_AGENT = AgentType.BROWSER.value
DEVELOPER_AGENT = AgentType.DEVELOPER.value
DOCUMENT_AGENT = AgentType.DOCUMENT.value
SOCIAL_MEDIUM_AGENT = AgentType.SOCIAL_MEDIUM.value
QUESTION_CONFIRM_AGENT = AgentType.QUESTION_CONFIRM.value
