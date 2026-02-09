"""
HumanToolkit - Human-in-the-loop interaction for agents.

Provides tools for agents to request human assistance or send notifications.
Uses TaskState SSE events to communicate with the frontend and awaits
user responses via the human response queue.
"""

import asyncio
import logging
from typing import List, Optional

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit
from ...events.action_types import AskData, NoticeData

logger = logging.getLogger(__name__)


class HumanToolkit(BaseToolkit):
    """A toolkit for human-in-the-loop interactions.

    Allows agents to:
    - Ask questions and wait for human responses (via SSE + queue)
    - Send notifications/messages to humans (via SSE)

    Uses @listen_toolkit for automatic event emission on public methods.
    """

    # Agent name for event tracking
    agent_name: str = "human_agent"

    def __init__(
        self,
        timeout: Optional[float] = 300.0,  # 5 minutes default for human response
    ) -> None:
        """Initialize the HumanToolkit.

        Args:
            timeout: Timeout for waiting for human responses (default 300 seconds).
        """
        super().__init__(timeout=timeout)

        logger.info("HumanToolkit initialized")

    @listen_toolkit(
        inputs=lambda self, question, context=None: f"Asking human: {question[:50]}{'...' if len(question) > 50 else ''}",
        return_msg=lambda r: f"Human responded: {r[:50]}{'...' if len(r) > 50 else ''}" if not r.startswith("[") else r
    )
    async def ask_human_async(
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
        - Persistent network errors or access denied

        Args:
            question: The question to ask the human.
            context: Optional additional context to help the human understand.

        Returns:
            The human's response as a string.
        """
        state = self._task_state
        if state is None:
            raise RuntimeError("HumanToolkit: task_state not set, cannot ask human")

        logger.info(f"Asking human: {question[:100]}{'...' if len(question) > 100 else ''}")

        # Set pending question flag (required by provide_human_response validation)
        state._pending_human_question = question

        # Emit AskData SSE event → frontend shows modal
        await state.put_event(AskData(
            task_id=getattr(state, 'task_id', None),
            question=question,
            context=context,
        ))

        # Await user response from queue (with timeout)
        try:
            response = await asyncio.wait_for(
                state._human_response_queue.get(),
                timeout=self.timeout or 300,
            )
            logger.info(f"Human responded: {str(response)[:100]}...")
            return str(response)
        except asyncio.TimeoutError:
            state._pending_human_question = None
            logger.warning("Timeout waiting for human response")
            return "[Timeout: no human response received]"
        except asyncio.CancelledError:
            state._pending_human_question = None
            raise

    @listen_toolkit(
        inputs=lambda self, title, description: f"Sending message: {title}",
        return_msg=lambda r: r
    )
    async def send_message_async(
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
        state = self._task_state
        if state is None:
            raise RuntimeError("HumanToolkit: task_state not set, cannot send message")

        logger.info(f"Sending message to human: {title}")

        await state.put_event(NoticeData(
            task_id=getattr(state, 'task_id', None),
            title=title,
            message=description,
        ))
        return f"Message sent: {title}"

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Note: Returns async versions of tools since agent execution context
        is async. Tool names are explicitly set to match the system prompt
        expectations (ask_human, send_message) rather than the function
        names (*_async).

        Returns:
            List of FunctionTool objects.
        """
        # Create tools and rename to match expected names
        ask_tool = FunctionTool(self.ask_human_async)
        ask_tool.set_function_name("ask_human")

        send_tool = FunctionTool(self.send_message_async)
        send_tool.set_function_name("send_message")

        return [ask_tool, send_tool]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Human Toolkit"
