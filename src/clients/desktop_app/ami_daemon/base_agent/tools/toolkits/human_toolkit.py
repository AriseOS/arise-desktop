"""
HumanToolkit - Human-in-the-loop interaction for agents.

Ported from CAMEL-AI/Eigent project.
Provides tools for agents to request human assistance or send notifications.
"""

import asyncio
import logging
from typing import Callable, List, Optional, Awaitable, Union

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit
from ...events.toolkit_listen import _run_async_safely

logger = logging.getLogger(__name__)


# Type for callback functions
HumanCallback = Callable[[str, Optional[str]], Union[str, Awaitable[str]]]
MessageCallback = Callable[[str, str], Union[None, Awaitable[None]]]


class HumanToolkit(BaseToolkit):
    """A toolkit for human-in-the-loop interactions.

    Allows agents to:
    - Ask questions and wait for human responses
    - Send notifications/messages to humans

    Uses @listen_toolkit for automatic event emission on public methods.
    """

    # Agent name for event tracking
    agent_name: str = "human_agent"

    def __init__(
        self,
        ask_callback: Optional[HumanCallback] = None,
        message_callback: Optional[MessageCallback] = None,
        timeout: Optional[float] = 300.0,  # 5 minutes default for human response
    ) -> None:
        """Initialize the HumanToolkit.

        Args:
            ask_callback: Callback function for asking questions.
                Signature: (question: str, context: Optional[str]) -> str
                Should present the question to the user and return their response.
                If async, should be an async function.
            message_callback: Callback function for sending messages.
                Signature: (title: str, description: str) -> None
                Should display the message to the user.
            timeout: Timeout for waiting for human responses (default 300 seconds).
        """
        super().__init__(timeout=timeout)

        self._ask_callback = ask_callback
        self._message_callback = message_callback

        # For synchronous usage without callbacks
        self._pending_question: Optional[str] = None
        self._response_event = asyncio.Event()
        self._response_value: Optional[str] = None

        logger.info(
            f"HumanToolkit initialized "
            f"(has_ask_callback={ask_callback is not None}, "
            f"has_message_callback={message_callback is not None})"
        )

    @listen_toolkit(
        inputs=lambda self, question, context=None: f"Asking human: {question[:50]}{'...' if len(question) > 50 else ''}",
        return_msg=lambda r: f"Human responded: {r[:50]}{'...' if len(r) > 50 else ''}" if not r.startswith("[") else r
    )
    def ask_human(
        self,
        question: str,
        context: Optional[str] = None,
    ) -> str:
        """Ask a question and wait for human response.

        Use this when you need human assistance, such as:
        - Login/authentication required
        - CAPTCHA or verification needed
        - Clarification on ambiguous task
        - Decision that requires human judgment

        Args:
            question: The question to ask the human.
            context: Optional additional context to help the human understand.

        Returns:
            The human's response as a string.
        """
        full_question = question
        if context:
            full_question = f"{question}\n\nContext: {context}"

        logger.info(f"Asking human: {question[:100]}{'...' if len(question) > 100 else ''}")

        if self._ask_callback:
            try:
                result = self._ask_callback(question, context)
                # Handle async callback
                if asyncio.iscoroutine(result):
                    # If we're in an async context, this won't work
                    # The caller should use ask_human_async instead
                    try:
                        loop = asyncio.get_running_loop()
                        # We're in an async context, can't run sync
                        logger.warning("Async callback in sync context, returning placeholder")
                        return "[Awaiting human response - please use async version]"
                    except RuntimeError:
                        # No running loop, we can run it
                        result = asyncio.run(result)
                logger.info(f"Human responded: {str(result)[:100]}...")
                return str(result)
            except Exception as e:
                logger.error(f"Error calling ask_callback: {e}")
                return f"[Error getting human response: {e}]"
        else:
            # No callback configured, return a placeholder
            logger.warning("No ask_callback configured, returning placeholder")
            return f"[Human response needed for: {question}]"

    @listen_toolkit(
        inputs=lambda self, question, context=None: f"Asking human: {question[:50]}{'...' if len(question) > 50 else ''}",
        return_msg=lambda r: f"Human responded: {r[:50]}{'...' if len(r) > 50 else ''}" if not r.startswith("[") else r
    )
    async def ask_human_async(
        self,
        question: str,
        context: Optional[str] = None,
    ) -> str:
        """Ask a question and wait for human response (async version).

        Args:
            question: The question to ask the human.
            context: Optional additional context.

        Returns:
            The human's response as a string.
        """
        logger.info(f"Asking human (async): {question[:100]}{'...' if len(question) > 100 else ''}")

        if self._ask_callback:
            try:
                result = self._ask_callback(question, context)
                if asyncio.iscoroutine(result):
                    result = await result
                logger.info(f"Human responded: {str(result)[:100]}...")
                return str(result)
            except Exception as e:
                logger.error(f"Error calling ask_callback: {e}")
                return f"[Error getting human response: {e}]"
        else:
            logger.warning("No ask_callback configured, returning placeholder")
            return f"[Human response needed for: {question}]"

    @listen_toolkit(
        inputs=lambda self, title, description: f"Sending message: {title}",
        return_msg=lambda r: r
    )
    def send_message(
        self,
        title: str,
        description: str,
    ) -> str:
        """Send a one-way notification to the human.

        Use this to inform the human about:
        - Progress updates
        - Important findings
        - Warnings or issues

        This does NOT wait for a response.

        Args:
            title: Short title/summary of the message.
            description: Detailed message content.

        Returns:
            Confirmation that the message was sent.
        """
        logger.info(f"Sending message to human: {title}")

        if self._message_callback:
            try:
                result = self._message_callback(title, description)
                if asyncio.iscoroutine(result):
                    # Use _run_async_safely for proper handling in both contexts
                    _run_async_safely(result, toolkit=self)
                return f"Message sent: {title}"
            except Exception as e:
                logger.error(f"Error calling message_callback: {e}")
                return f"Message delivery failed: {e}"
        else:
            # Log the message even without callback
            logger.info(f"[Message to Human] {title}: {description}")
            return f"Message logged: {title}"

    @listen_toolkit(
        inputs=lambda self, title, description: f"Sending message: {title}",
        return_msg=lambda r: r
    )
    async def send_message_async(
        self,
        title: str,
        description: str,
    ) -> str:
        """Send a one-way notification to the human (async version).

        Args:
            title: Short title/summary.
            description: Detailed message content.

        Returns:
            Confirmation that the message was sent.
        """
        logger.info(f"Sending message to human (async): {title}")

        if self._message_callback:
            try:
                result = self._message_callback(title, description)
                if asyncio.iscoroutine(result):
                    await result
                return f"Message sent: {title}"
            except Exception as e:
                logger.error(f"Error calling message_callback: {e}")
                return f"Message delivery failed: {e}"
        else:
            logger.info(f"[Message to Human] {title}: {description}")
            return f"Message logged: {title}"

    def set_ask_callback(self, callback: HumanCallback) -> None:
        """Set or update the ask callback.

        Args:
            callback: The callback function for asking questions.
        """
        self._ask_callback = callback
        logger.info("Ask callback updated")

    def set_message_callback(self, callback: MessageCallback) -> None:
        """Set or update the message callback.

        Args:
            callback: The callback function for sending messages.
        """
        self._message_callback = callback
        logger.info("Message callback updated")

    # Methods for external response injection (when not using callbacks)

    def provide_response(self, response: str) -> None:
        """Provide a response to a pending question.

        Used when callbacks are not available and responses are provided externally.

        Args:
            response: The human's response.
        """
        self._response_value = response
        self._response_event.set()
        logger.info(f"Response provided: {response[:50]}...")

    def get_pending_question(self) -> Optional[str]:
        """Get the current pending question, if any.

        Returns:
            The pending question or None.
        """
        return self._pending_question

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Note: Returns async versions of tools since agent execution context
        is async. The async versions properly await async callbacks.
        Tool names are explicitly set to match the system prompt expectations
        (ask_human, send_message) rather than the function names (*_async).

        Returns:
            List of FunctionTool objects.
        """
        return [
            FunctionTool(self.ask_human_async, name="ask_human"),
            FunctionTool(self.send_message_async, name="send_message"),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Human Toolkit"
