"""
SocialMediumAgent - Email, calendar, and communication operations.

This agent handles communication-related tasks:
1. Email operations via Gmail
2. Calendar management
3. Social media interactions (when available)

Based on Eigent's social_medium_agent type.

References:
- Eigent: third-party/eigent/backend/app/service/task.py
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext, AgentInput, AgentOutput
from ..tools.toolkits import HumanToolkit, FunctionTool
from ..prompts import (
    SOCIAL_MEDIUM_SYSTEM_PROMPT,
    EMAIL_COMPOSE_PROMPT,
    CALENDAR_EVENT_PROMPT,
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


class SocialMediumAgent(BaseStepAgent):
    """Agent for email, calendar, and social communication.

    This agent handles:
    - Gmail operations (read, send, search)
    - Calendar management (view, create events)
    - Communication tasks

    Note: Gmail and Calendar operations require MCP toolkits to be configured.
    When MCP toolkits are not available, the agent will provide guidance
    on what actions would be needed.

    Based on Eigent's social_medium_agent pattern.
    """

    INPUT_SCHEMA = InputSchema(
        description="Agent for email, calendar, and communication tasks",
        fields={
            "task": FieldSchema(
                type="str",
                required=True,
                description="Communication task to perform"
            ),
            "task_type": FieldSchema(
                type="str",
                required=False,
                description="Type of communication task",
                enum=["email", "calendar", "general"],
                default="general"
            ),
            # Email-specific fields
            "email_action": FieldSchema(
                type="str",
                required=False,
                description="Email action",
                enum=["read", "send", "search", "draft", "reply"],
            ),
            "recipients": FieldSchema(
                type="list",
                required=False,
                description="Email recipients",
                items_type="str"
            ),
            "subject": FieldSchema(
                type="str",
                required=False,
                description="Email subject"
            ),
            "body": FieldSchema(
                type="str",
                required=False,
                description="Email body content"
            ),
            # Calendar-specific fields
            "calendar_action": FieldSchema(
                type="str",
                required=False,
                description="Calendar action",
                enum=["view", "create", "update", "delete", "find_free_time"],
            ),
            "event_title": FieldSchema(
                type="str",
                required=False,
                description="Calendar event title"
            ),
            "event_time": FieldSchema(
                type="str",
                required=False,
                description="Event time (ISO format or natural language)"
            ),
            "event_duration": FieldSchema(
                type="int",
                required=False,
                description="Event duration in minutes",
                default=60
            ),
            "attendees": FieldSchema(
                type="list",
                required=False,
                description="Event attendees",
                items_type="str"
            ),
            "max_iterations": FieldSchema(
                type="int",
                required=False,
                description="Maximum LLM iterations",
                default=10
            ),
        },
        examples=[
            {
                "task": "Send an email to team about tomorrow's meeting",
                "task_type": "email",
                "email_action": "send",
                "recipients": ["team@example.com"],
                "subject": "Tomorrow's Meeting"
            },
            {
                "task": "Schedule a call with John at 3pm",
                "task_type": "calendar",
                "calendar_action": "create",
                "event_title": "Call with John",
                "event_time": "15:00",
                "event_duration": 30
            }
        ]
    )

    def __init__(self):
        """Initialize SocialMediumAgent."""
        metadata = AgentMetadata(
            name="social_medium_agent",
            description="Handles email, calendar, and communication tasks"
        )
        super().__init__(metadata)

        self._llm_provider: Optional[AnthropicProvider] = None
        self._human_toolkit: Optional[HumanToolkit] = None
        self._gmail_toolkit = None  # Will be GmailMCPToolkit when available
        self._calendar_toolkit = None  # Will be CalendarToolkit when available
        self._progress_callback: Optional[Callable] = None
        self._task_id: Optional[str] = None
        self._messages: List[Dict[str, Any]] = []

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

            # Initialize Human toolkit
            self._human_toolkit = HumanToolkit()

            # Try to initialize Gmail MCP toolkit
            try:
                from ..tools.toolkits import GmailMCPToolkit
                self._gmail_toolkit = GmailMCPToolkit()
                await self._gmail_toolkit.initialize()
                logger.info("Gmail MCP toolkit initialized")
            except (ImportError, ValueError, FileNotFoundError) as e:
                logger.debug(f"Gmail MCP toolkit not available: {e}")

            # Try to initialize Calendar toolkit
            try:
                from ..tools.toolkits import GoogleCalendarToolkit
                self._calendar_toolkit = GoogleCalendarToolkit()
                await self._calendar_toolkit.initialize()
                logger.info("Google Calendar toolkit initialized")
            except (ImportError, ValueError, FileNotFoundError) as e:
                logger.debug(f"Google Calendar toolkit not available: {e}")

            # Get progress callback
            self._progress_callback = context.log_callback

            self.is_initialized = True
            logger.info(f"SocialMediumAgent initialized for task {self._task_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize SocialMediumAgent: {e}")
            return False

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """Execute the communication task.

        Args:
            input_data: Input containing task description
            context: Agent execution context

        Returns:
            AgentOutput with results
        """
        if not self.is_initialized:
            await self.initialize(context)

        # Parse input
        if isinstance(input_data, AgentInput):
            data = input_data.data
        elif isinstance(input_data, dict):
            data = input_data
        else:
            data = {"task": str(input_data)}

        task = data.get("task", "")
        task_type = data.get("task_type", "general")
        max_iterations = data.get("max_iterations", 10)

        try:
            # Check for available toolkits
            available_services = []
            if self._gmail_toolkit:
                available_services.append("Gmail")
            if self._calendar_toolkit:
                available_services.append("Calendar")

            if not available_services:
                # No MCP toolkits available - provide guidance mode
                return await self._guidance_mode(task, data)

            # Build system prompt
            prompt_context = PromptContext()
            system_prompt = SOCIAL_MEDIUM_SYSTEM_PROMPT.format(prompt_context)

            # Add available services info
            system_prompt += f"\n\n**Available Services:** {', '.join(available_services)}"

            # Build initial message
            initial_message = self._build_initial_message(task, task_type, data)

            # Get tools
            tools = self._get_tools()

            # Run agent loop
            result = await self._run_agent_loop(
                system_prompt=system_prompt,
                initial_message=initial_message,
                tools=tools,
                max_iterations=max_iterations,
            )

            return AgentOutput(
                success=result.get("success", False),
                message=result.get("message", ""),
                data={
                    "task": task,
                    "task_type": task_type,
                    "result": result.get("result"),
                    "emails_sent": result.get("emails_sent", 0),
                    "events_created": result.get("events_created", 0),
                    "iterations": result.get("iterations", 0),
                }
            )

        except Exception as e:
            logger.error(f"Error in SocialMediumAgent: {e}")
            return AgentOutput(
                success=False,
                message=f"Error during communication task: {str(e)}",
                data={"error": str(e)}
            )

    async def _guidance_mode(
        self,
        task: str,
        data: Dict[str, Any]
    ) -> AgentOutput:
        """Provide guidance when MCP toolkits are not available.

        Args:
            task: Task description
            data: Full input data

        Returns:
            AgentOutput with guidance
        """
        task_type = data.get("task_type", "general")

        guidance = []
        guidance.append("**Note:** Email and Calendar MCP toolkits are not configured.")
        guidance.append("\nTo enable full functionality, configure the following MCP servers:")
        guidance.append("- Gmail: @gongrzhe/server-gmail-autoauth-mcp")
        guidance.append("- Calendar: Google Calendar API integration")

        if task_type == "email":
            guidance.append("\n**Email Task Guidance:**")
            recipients = data.get("recipients", [])
            subject = data.get("subject", "")
            body = data.get("body", "")

            if recipients:
                guidance.append(f"- Recipients: {', '.join(recipients)}")
            if subject:
                guidance.append(f"- Subject: {subject}")
            if body:
                guidance.append(f"- Body preview: {body[:200]}...")

            guidance.append("\nPlease manually compose and send this email.")

        elif task_type == "calendar":
            guidance.append("\n**Calendar Task Guidance:**")
            event_title = data.get("event_title", "")
            event_time = data.get("event_time", "")
            event_duration = data.get("event_duration", 60)
            attendees = data.get("attendees", [])

            if event_title:
                guidance.append(f"- Event: {event_title}")
            if event_time:
                guidance.append(f"- Time: {event_time}")
            if event_duration:
                guidance.append(f"- Duration: {event_duration} minutes")
            if attendees:
                guidance.append(f"- Attendees: {', '.join(attendees)}")

            guidance.append("\nPlease manually create this calendar event.")

        return AgentOutput(
            success=False,
            message="MCP toolkits not available - manual action required",
            data={
                "requires_manual_action": True,
                "guidance": "\n".join(guidance),
                "task": task,
                "task_type": task_type,
            }
        )

    def _build_initial_message(
        self,
        task: str,
        task_type: str,
        data: Dict[str, Any]
    ) -> str:
        """Build the initial message for the LLM.

        Args:
            task: Task description
            task_type: Type of communication task
            data: Full input data

        Returns:
            Initial message string
        """
        parts = [f"**Task:** {task}", f"**Type:** {task_type}"]

        if task_type == "email":
            if data.get("recipients"):
                parts.append(f"**Recipients:** {', '.join(data['recipients'])}")
            if data.get("subject"):
                parts.append(f"**Subject:** {data['subject']}")
            if data.get("email_action"):
                parts.append(f"**Action:** {data['email_action']}")

        elif task_type == "calendar":
            if data.get("event_title"):
                parts.append(f"**Event:** {data['event_title']}")
            if data.get("event_time"):
                parts.append(f"**Time:** {data['event_time']}")
            if data.get("calendar_action"):
                parts.append(f"**Action:** {data['calendar_action']}")

        parts.append("\nPlease proceed with this communication task.")
        return "\n\n".join(parts)

    def _get_tools(self) -> List[Dict[str, Any]]:
        """Get available tools for the social medium agent.

        Returns:
            List of tool definitions
        """
        tools = []

        # Gmail toolkit tools
        if self._gmail_toolkit:
            for tool in self._gmail_toolkit.get_tools():
                tools.append(tool.to_anthropic_format())

        # Calendar toolkit tools
        if self._calendar_toolkit:
            for tool in self._calendar_toolkit.get_tools():
                tools.append(tool.to_anthropic_format())

        # Human toolkit tools
        for tool in self._human_toolkit.get_tools():
            tools.append(tool.to_anthropic_format())

        # Add placeholder tools if no MCP toolkits available
        if not self._gmail_toolkit:
            tools.append({
                "name": "draft_email",
                "description": "Draft an email (preview only - send manually)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "array", "items": {"type": "string"}},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"]
                }
            })

        if not self._calendar_toolkit:
            tools.append({
                "name": "draft_event",
                "description": "Draft a calendar event (create manually)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start_time": {"type": "string"},
                        "duration_minutes": {"type": "integer"},
                        "attendees": {"type": "array", "items": {"type": "string"}},
                        "description": {"type": "string"},
                    },
                    "required": ["title", "start_time"]
                }
            })

        return tools

    async def _run_agent_loop(
        self,
        system_prompt: str,
        initial_message: str,
        tools: List[Dict[str, Any]],
        max_iterations: int
    ) -> Dict[str, Any]:
        """Run the main agent loop.

        Args:
            system_prompt: System prompt for the LLM
            initial_message: Initial user message
            tools: Available tools
            max_iterations: Maximum iterations

        Returns:
            Result dictionary
        """
        self._messages = [{"role": "user", "content": initial_message}]
        emails_sent = 0
        events_created = 0

        for iteration in range(max_iterations):
            if self._progress_callback:
                await self._progress_callback({
                    "type": "social_medium_agent",
                    "action": "thinking",
                    "iteration": iteration + 1,
                    "max_iterations": max_iterations,
                })

            response = await asyncio.to_thread(
                self._llm_provider.generate_with_tools,
                system_prompt=system_prompt,
                messages=self._messages,
                tools=tools,
                max_tokens=4096,
            )

            if response.stop_reason == "end_turn":
                final_text = self._extract_text_response(response)
                return {
                    "success": True,
                    "message": "Communication task completed",
                    "result": final_text,
                    "emails_sent": emails_sent,
                    "events_created": events_created,
                    "iterations": iteration + 1,
                }

            if response.stop_reason == "tool_use":
                tool_results, sent, created = await self._process_tool_calls(response)
                emails_sent += sent
                events_created += created

                self._messages.append({
                    "role": "assistant",
                    "content": response.content
                })
                self._messages.append({
                    "role": "user",
                    "content": tool_results
                })
            else:
                break

        return {
            "success": False,
            "message": f"Max iterations ({max_iterations}) reached",
            "result": None,
            "emails_sent": emails_sent,
            "events_created": events_created,
            "iterations": max_iterations,
        }

    async def _process_tool_calls(
        self,
        response: ToolCallResponse
    ) -> tuple[List[Dict[str, Any]], int, int]:
        """Process tool calls from LLM response.

        Args:
            response: LLM response with tool calls

        Returns:
            Tuple of (tool_results, emails_sent_count, events_created_count)
        """
        results = []
        emails_sent = 0
        events_created = 0

        for block in response.content:
            if isinstance(block, ToolUseBlock):
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                if self._progress_callback:
                    await self._progress_callback({
                        "type": "social_medium_agent",
                        "action": "tool_call",
                        "tool_name": tool_name,
                    })

                try:
                    result = await self._execute_tool(tool_name, tool_input)

                    # Track sent emails and created events
                    if tool_name in ["send_email", "gmail_send"]:
                        if "success" in str(result).lower() or "sent" in str(result).lower():
                            emails_sent += 1
                    elif tool_name in ["create_event", "calendar_create"]:
                        if "created" in str(result).lower():
                            events_created += 1

                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": str(result)
                    })
                except Exception as e:
                    logger.error(f"Tool {tool_name} failed: {e}")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": f"Error: {str(e)}",
                        "is_error": True
                    })

        return results, emails_sent, events_created

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Any:
        """Execute a single tool.

        Args:
            tool_name: Name of the tool
            tool_input: Tool input parameters

        Returns:
            Tool execution result
        """
        # Gmail tools
        if self._gmail_toolkit:
            gmail_tools = {t.name: t for t in self._gmail_toolkit.get_tools()}
            if tool_name in gmail_tools:
                return await gmail_tools[tool_name].async_execute(**tool_input)

        # Calendar tools
        if self._calendar_toolkit:
            cal_tools = {t.name: t for t in self._calendar_toolkit.get_tools()}
            if tool_name in cal_tools:
                return await cal_tools[tool_name].async_execute(**tool_input)

        # Human tools
        human_tools = {t.name: t for t in self._human_toolkit.get_tools()}
        if tool_name in human_tools:
            return await human_tools[tool_name].async_execute(**tool_input)

        # Draft tools (placeholder when MCP not available)
        if tool_name == "draft_email":
            return (
                f"Email Draft:\n"
                f"To: {', '.join(tool_input.get('to', []))}\n"
                f"Subject: {tool_input.get('subject', '')}\n"
                f"Body:\n{tool_input.get('body', '')}\n\n"
                f"[Please send this email manually]"
            )

        if tool_name == "draft_event":
            return (
                f"Calendar Event Draft:\n"
                f"Title: {tool_input.get('title', '')}\n"
                f"Time: {tool_input.get('start_time', '')}\n"
                f"Duration: {tool_input.get('duration_minutes', 60)} minutes\n"
                f"Attendees: {', '.join(tool_input.get('attendees', []))}\n"
                f"Description: {tool_input.get('description', '')}\n\n"
                f"[Please create this event manually]"
            )

        return f"Unknown tool: {tool_name}"

    def _extract_text_response(self, response: ToolCallResponse) -> str:
        """Extract text content from LLM response."""
        texts = []
        for block in response.content:
            if isinstance(block, TextBlock):
                texts.append(block.text)
        return "\n".join(texts)

    async def cleanup(self, context: AgentContext) -> None:
        """Cleanup agent resources."""
        logger.debug(f"SocialMediumAgent cleanup for task {self._task_id}")
        self._llm_provider = None
        self._human_toolkit = None
        self._gmail_toolkit = None
        self._calendar_toolkit = None
        self._progress_callback = None
        self._messages = []
