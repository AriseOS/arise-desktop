"""
Custom Anthropic LLM wrapper that disables prompt caching
for compatibility with custom Anthropic proxy servers that have stricter cache_control limits
"""

import logging
from typing import overload, TypeVar
from pydantic import BaseModel

from browser_use.llm import ChatAnthropic
from browser_use.llm.anthropic.serializer import AnthropicMessageSerializer
from browser_use.llm.views import ChatInvokeCompletion
from browser_use.llm.messages import BaseMessage

logger = logging.getLogger(__name__)
T = TypeVar('T', bound=BaseModel)


class NoCacheChatAnthropic(ChatAnthropic):
    """
    ChatAnthropic wrapper that disables all prompt caching

    This is needed when using custom Anthropic proxy servers (like tun.agenticos.net)
    that have stricter limits on cache_control blocks (max 4 instead of standard limits).

    Browser-use by default adds cache=True to:
    - System messages (SystemPrompt)
    - User state messages (AgentMessagePrompt)
    - Tool schemas (when using structured output)

    This can result in 5+ cache_control blocks, exceeding the proxy limit.

    Solution: Override ainvoke to strip all cache flags before serialization.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.info("Initialized NoCacheChatAnthropic - prompt caching disabled for compatibility with custom proxy")

    def _strip_cache_from_messages(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """
        Create a deep copy of messages with all cache flags set to False

        Args:
            messages: Original messages with cache flags

        Returns:
            New list of messages with cache=False
        """
        stripped_messages = []
        for msg in messages:
            # Deep copy the message and set cache=False
            msg_copy = msg.model_copy(deep=True)
            msg_copy.cache = False
            stripped_messages.append(msg_copy)

        return stripped_messages

    @overload
    async def ainvoke(self, messages: list[BaseMessage], output_format: None = None) -> ChatInvokeCompletion[str]: ...

    @overload
    async def ainvoke(self, messages: list[BaseMessage], output_format: type[T]) -> ChatInvokeCompletion[T]: ...

    async def ainvoke(
        self, messages: list[BaseMessage], output_format: type[T] | None = None
    ) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
        """
        Override ainvoke to strip cache flags before calling parent

        This ensures no cache_control blocks are added to the API request,
        making it compatible with proxy servers that have stricter limits.
        """
        # Strip cache from all messages
        no_cache_messages = self._strip_cache_from_messages(messages)

        # Call parent with stripped messages
        return await super().ainvoke(no_cache_messages, output_format)
