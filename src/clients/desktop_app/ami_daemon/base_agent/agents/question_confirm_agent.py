"""
QuestionConfirmAgent - Human-in-the-loop confirmations and Q&A.

This agent handles scenarios requiring user interaction:
1. Clarifying ambiguous requests
2. Confirming critical or irreversible actions
3. Gathering additional information
4. Presenting options for user decision

Based on Eigent's question_confirm_agent type.

References:
- Eigent: third-party/eigent/backend/app/service/task.py
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

from ._base import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext, AgentInput, AgentOutput
from ..tools.toolkits import HumanToolkit, FunctionTool
from ..prompts import (
    QUESTION_CONFIRM_SYSTEM_PROMPT,
    QUICK_CONFIRM_PROMPT,
    OPTIONS_PROMPT,
    PromptContext,
)

# Import from common/llm module
from src.common.llm import (
    AnthropicProvider,
    ToolCallResponse,
    ToolUseBlock,
    TextBlock,
)

logger = logging.getLogger(__name__)


class QuestionConfirmAgent(BaseStepAgent):
    """Agent for human-in-the-loop confirmations and Q&A.

    This agent is used when:
    - User input is needed to proceed
    - Critical actions require explicit confirmation
    - Multiple options exist and user preference matters
    - Requirements are ambiguous and need clarification

    Based on Eigent's question_confirm_agent pattern.
    """

    INPUT_SCHEMA = InputSchema(
        description="Agent for human confirmation and Q&A interactions",
        fields={
            "question": FieldSchema(
                type="str",
                required=False,
                description="Question to ask the user"
            ),
            "context": FieldSchema(
                type="str",
                required=False,
                description="Context for the question"
            ),
            "options": FieldSchema(
                type="list",
                required=False,
                description="Options to present to user",
                items_type="str"
            ),
            "confirmation_type": FieldSchema(
                type="str",
                required=False,
                description="Type of confirmation: 'yes_no', 'options', 'open_ended'",
                enum=["yes_no", "options", "open_ended"],
                default="open_ended"
            ),
            "action_description": FieldSchema(
                type="str",
                required=False,
                description="Description of action requiring confirmation"
            ),
            "timeout": FieldSchema(
                type="int",
                required=False,
                description="Timeout in seconds for user response",
                default=300
            ),
            "default_response": FieldSchema(
                type="str",
                required=False,
                description="Default response if timeout occurs"
            ),
        },
        examples=[
            {
                "question": "Which files should I delete?",
                "options": ["Temp files only", "All backup files", "Archive folder"],
                "confirmation_type": "options"
            },
            {
                "action_description": "Push changes to production",
                "confirmation_type": "yes_no"
            }
        ]
    )

    def __init__(self):
        """Initialize QuestionConfirmAgent."""
        metadata = AgentMetadata(
            name="question_confirm_agent",
            description="Handles human-in-the-loop confirmations and Q&A"
        )
        super().__init__(metadata)

        self._llm_provider: Optional[AnthropicProvider] = None
        self._human_toolkit: Optional[HumanToolkit] = None
        self._progress_callback: Optional[Callable] = None
        self._task_id: Optional[str] = None

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize the agent with context.

        Args:
            context: Agent execution context

        Returns:
            True if initialization successful
        """
        try:
            self._task_id = context.workflow_id

            # Initialize LLM provider
            self._llm_provider = AnthropicProvider()

            # Initialize Human toolkit for user interaction
            self._human_toolkit = HumanToolkit()

            # Get progress callback from context
            self._progress_callback = context.log_callback

            self.is_initialized = True
            logger.info(f"QuestionConfirmAgent initialized for task {self._task_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize QuestionConfirmAgent: {e}")
            return False

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """Execute the question/confirmation interaction.

        Args:
            input_data: Input containing question, options, or action to confirm
            context: Agent execution context

        Returns:
            AgentOutput with user's response
        """
        if not self.is_initialized:
            await self.initialize(context)

        # Parse input
        if isinstance(input_data, AgentInput):
            data = input_data.data
        elif isinstance(input_data, dict):
            data = input_data
        else:
            data = {"question": str(input_data)}

        confirmation_type = data.get("confirmation_type", "open_ended")
        question = data.get("question", "")
        options = data.get("options", [])
        action_description = data.get("action_description", "")
        context_info = data.get("context", "")
        timeout = data.get("timeout", 300)
        default_response = data.get("default_response")

        try:
            # Build the question based on type
            if confirmation_type == "yes_no" and action_description:
                formatted_question = self._format_yes_no_confirmation(
                    action_description, context_info
                )
            elif confirmation_type == "options" and options:
                formatted_question = self._format_options_question(
                    question, options, context_info
                )
            else:
                formatted_question = self._format_open_question(
                    question, context_info
                )

            # Emit progress event
            if self._progress_callback:
                await self._progress_callback({
                    "type": "question_confirm",
                    "action": "asking_user",
                    "question": formatted_question,
                    "confirmation_type": confirmation_type,
                    "options": options,
                })

            # Use HumanToolkit to ask the question
            if self._human_toolkit:
                response = await self._ask_human(
                    formatted_question,
                    timeout=timeout,
                    default=default_response
                )
            else:
                # Fallback - return that we need user input
                return AgentOutput(
                    success=False,
                    message="HumanToolkit not available for user interaction",
                    data={
                        "requires_input": True,
                        "question": formatted_question,
                        "confirmation_type": confirmation_type,
                        "options": options,
                    }
                )

            # Parse the response
            parsed_response = self._parse_response(
                response, confirmation_type, options
            )

            return AgentOutput(
                success=True,
                message="User response received",
                data={
                    "user_response": response,
                    "parsed_response": parsed_response,
                    "confirmation_type": confirmation_type,
                    "question_asked": formatted_question,
                }
            )

        except asyncio.TimeoutError:
            logger.warning(f"User response timeout for task {self._task_id}")
            return AgentOutput(
                success=False,
                message="Timeout waiting for user response",
                data={
                    "timeout": True,
                    "default_used": default_response is not None,
                    "response": default_response,
                }
            )

        except Exception as e:
            logger.error(f"Error in QuestionConfirmAgent: {e}")
            return AgentOutput(
                success=False,
                message=f"Error during user interaction: {str(e)}",
                data={"error": str(e)}
            )

    async def _ask_human(
        self,
        question: str,
        timeout: int = 300,
        default: Optional[str] = None
    ) -> str:
        """Ask the user a question via HumanToolkit.

        Args:
            question: The question to ask
            timeout: Timeout in seconds
            default: Default response if timeout

        Returns:
            User's response string
        """
        # Get the ask_human tool from HumanToolkit
        tools = self._human_toolkit.get_tools()
        ask_human_tool = next(
            (t for t in tools if t.name == "ask_human"),
            None
        )

        if ask_human_tool:
            result = await ask_human_tool.async_execute(question=question)
            return result if isinstance(result, str) else str(result)
        else:
            raise RuntimeError("ask_human tool not available")

    def _format_yes_no_confirmation(
        self,
        action: str,
        context: str = ""
    ) -> str:
        """Format a yes/no confirmation question.

        Args:
            action: Description of the action
            context: Additional context

        Returns:
            Formatted confirmation question
        """
        prompt = QUICK_CONFIRM_PROMPT.format(
            PromptContext(),
            action_description=action,
            impact_description=context or "This action may have significant impact."
        )
        return prompt

    def _format_options_question(
        self,
        question: str,
        options: List[str],
        context: str = ""
    ) -> str:
        """Format an options question.

        Args:
            question: The main question
            options: List of options
            context: Additional context

        Returns:
            Formatted options question
        """
        options_text = "\n".join(
            f"{i+1}. {opt}" for i, opt in enumerate(options)
        )

        prompt = OPTIONS_PROMPT.format(
            PromptContext(),
            user_request=question,
            options_list=options_text
        )
        return prompt

    def _format_open_question(
        self,
        question: str,
        context: str = ""
    ) -> str:
        """Format an open-ended question.

        Args:
            question: The question to ask
            context: Additional context

        Returns:
            Formatted question
        """
        if context:
            return f"{question}\n\nContext: {context}"
        return question

    def _parse_response(
        self,
        response: str,
        confirmation_type: str,
        options: List[str]
    ) -> Dict[str, Any]:
        """Parse user response based on confirmation type.

        Args:
            response: Raw user response
            confirmation_type: Type of confirmation
            options: Available options (if applicable)

        Returns:
            Parsed response dictionary
        """
        response_lower = response.lower().strip()

        if confirmation_type == "yes_no":
            is_confirmed = response_lower in ["yes", "y", "confirm", "ok", "proceed", "true"]
            is_denied = response_lower in ["no", "n", "cancel", "abort", "stop", "false"]
            return {
                "confirmed": is_confirmed,
                "denied": is_denied,
                "unclear": not is_confirmed and not is_denied,
                "raw_response": response
            }

        elif confirmation_type == "options":
            # Try to parse option number
            selected_index = None
            try:
                num = int(response_lower)
                if 1 <= num <= len(options):
                    selected_index = num - 1
            except ValueError:
                # Try to match option text
                for i, opt in enumerate(options):
                    if response_lower in opt.lower():
                        selected_index = i
                        break

            return {
                "selected_index": selected_index,
                "selected_option": options[selected_index] if selected_index is not None else None,
                "valid_selection": selected_index is not None,
                "raw_response": response
            }

        else:  # open_ended
            return {
                "response": response,
                "is_empty": len(response.strip()) == 0,
                "word_count": len(response.split()),
            }

    async def cleanup(self, context: AgentContext) -> None:
        """Cleanup agent resources.

        Args:
            context: Agent execution context
        """
        logger.debug(f"QuestionConfirmAgent cleanup for task {self._task_id}")
        self._llm_provider = None
        self._human_toolkit = None
        self._progress_callback = None
