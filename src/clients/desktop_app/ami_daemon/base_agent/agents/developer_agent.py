"""
DeveloperAgent - Coding, debugging, and development operations.

This agent handles software development tasks:
1. Writing and modifying code
2. Debugging and fixing issues
3. Git operations (commit, push, branch)
4. Running builds and tests
5. Code review and refactoring

Based on Eigent's developer_agent type.

References:
- Eigent: third-party/eigent/backend/app/service/task.py
"""

import asyncio
import logging
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from ._base import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext, AgentInput, AgentOutput
from ..tools.toolkits import TerminalToolkit, HumanToolkit, FunctionTool
from ..workspace import get_working_directory, get_current_manager
from ..prompts import (
    DEVELOPER_SYSTEM_PROMPT,
    CODE_REVIEW_PROMPT,
    BUG_FIX_PROMPT,
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


class DeveloperAgent(BaseStepAgent):
    """Agent for software development tasks.

    This agent handles:
    - Code writing and modification
    - Bug fixing and debugging
    - Git operations
    - Build and test execution
    - Code review

    Based on Eigent's developer_agent pattern.
    """

    INPUT_SCHEMA = InputSchema(
        description="Agent for coding and development tasks",
        fields={
            "task": FieldSchema(
                type="str",
                required=True,
                description="Development task to perform"
            ),
            "file_paths": FieldSchema(
                type="list",
                required=False,
                description="Relevant file paths",
                items_type="str"
            ),
            "working_directory": FieldSchema(
                type="str",
                required=False,
                description="Working directory for operations"
            ),
            "language": FieldSchema(
                type="str",
                required=False,
                description="Programming language context"
            ),
            "task_type": FieldSchema(
                type="str",
                required=False,
                description="Type of dev task",
                enum=["code", "debug", "review", "git", "build", "test", "refactor"],
                default="code"
            ),
            "max_iterations": FieldSchema(
                type="int",
                required=False,
                description="Maximum LLM iterations",
                default=20
            ),
            "require_confirmation": FieldSchema(
                type="bool",
                required=False,
                description="Require confirmation for critical operations",
                default=True
            ),
        },
        examples=[
            {
                "task": "Fix the TypeError in utils.py",
                "file_paths": ["src/utils.py"],
                "task_type": "debug"
            },
            {
                "task": "Create a function to parse JSON config",
                "language": "python",
                "task_type": "code"
            },
            {
                "task": "Commit changes with message 'Fix auth bug'",
                "task_type": "git"
            }
        ]
    )

    def __init__(self):
        """Initialize DeveloperAgent."""
        metadata = AgentMetadata(
            name="developer_agent",
            description="Handles coding, debugging, and development tasks"
        )
        super().__init__(metadata)

        self._llm_provider: Optional[AnthropicProvider] = None
        self._terminal_toolkit: Optional[TerminalToolkit] = None
        self._human_toolkit: Optional[HumanToolkit] = None
        self._progress_callback: Optional[Callable] = None
        self._task_id: Optional[str] = None
        self._working_dir: str = ""
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

            # Get working directory
            manager = get_current_manager()
            if manager:
                self._working_dir = str(manager.workspace)
            else:
                self._working_dir = get_working_directory()

            # Initialize LLM provider
            self._llm_provider = AnthropicProvider()

            # Initialize Terminal toolkit
            self._terminal_toolkit = TerminalToolkit(
                working_dir=self._working_dir,
                allowed_commands=None,  # Allow all commands with caution
                timeout=120,
            )

            # Initialize Human toolkit for confirmations
            self._human_toolkit = HumanToolkit()

            # Get progress callback
            self._progress_callback = context.log_callback

            self.is_initialized = True
            logger.info(f"DeveloperAgent initialized for task {self._task_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize DeveloperAgent: {e}")
            return False

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """Execute the development task.

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
        task_type = data.get("task_type", "code")
        file_paths = data.get("file_paths", [])
        working_dir = data.get("working_directory", self._working_dir)
        max_iterations = data.get("max_iterations", 20)
        require_confirmation = data.get("require_confirmation", True)
        language = data.get("language", "")

        # Update working directory if specified
        if working_dir and working_dir != self._working_dir:
            self._working_dir = working_dir
            self._terminal_toolkit = TerminalToolkit(
                working_dir=working_dir,
                timeout=120,
            )

        try:
            # Build system prompt
            prompt_context = PromptContext(
                working_directory=self._working_dir,
                custom_context={"language": language} if language else {}
            )
            system_prompt = DEVELOPER_SYSTEM_PROMPT.format(prompt_context)

            # Build initial message with task and context
            initial_message = self._build_initial_message(
                task, task_type, file_paths, language
            )

            # Get tools
            tools = self._get_tools(require_confirmation)

            # Run the agent loop
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
                    "files_modified": result.get("files_modified", []),
                    "commands_executed": result.get("commands_executed", []),
                    "iterations": result.get("iterations", 0),
                }
            )

        except Exception as e:
            logger.error(f"Error in DeveloperAgent: {e}")
            return AgentOutput(
                success=False,
                message=f"Error during development task: {str(e)}",
                data={"error": str(e)}
            )

    def _build_initial_message(
        self,
        task: str,
        task_type: str,
        file_paths: List[str],
        language: str
    ) -> str:
        """Build the initial message for the LLM.

        Args:
            task: Task description
            task_type: Type of development task
            file_paths: Relevant file paths
            language: Programming language

        Returns:
            Initial message string
        """
        parts = [f"**Task:** {task}"]

        if task_type:
            parts.append(f"**Task Type:** {task_type}")

        if language:
            parts.append(f"**Language:** {language}")

        if file_paths:
            files_str = "\n".join(f"- {fp}" for fp in file_paths)
            parts.append(f"**Relevant Files:**\n{files_str}")

        parts.append("\nPlease analyze this task and proceed step by step.")

        return "\n\n".join(parts)

    def _get_tools(self, require_confirmation: bool) -> List[Dict[str, Any]]:
        """Get available tools for the developer agent.

        Args:
            require_confirmation: Whether to require confirmation for dangerous ops

        Returns:
            List of tool definitions
        """
        tools = []

        # Terminal tools
        for tool in self._terminal_toolkit.get_tools():
            tools.append(tool.to_anthropic_format())

        # Human tools (for confirmation)
        for tool in self._human_toolkit.get_tools():
            tools.append(tool.to_anthropic_format())

        # Add file operation tools
        tools.extend(self._get_file_tools())

        return tools

    def _get_file_tools(self) -> List[Dict[str, Any]]:
        """Get file operation tool definitions.

        Returns:
            List of file tool definitions
        """
        return [
            {
                "name": "read_file",
                "description": "Read the contents of a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to read"
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "Starting line number (optional)"
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "Ending line number (optional)"
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "Write content to a file (creates or overwrites)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to write"
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write to the file"
                        }
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "edit_file",
                "description": "Edit a specific section of a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to edit"
                        },
                        "old_text": {
                            "type": "string",
                            "description": "Text to replace"
                        },
                        "new_text": {
                            "type": "string",
                            "description": "Replacement text"
                        }
                    },
                    "required": ["path", "old_text", "new_text"]
                }
            },
            {
                "name": "list_files",
                "description": "List files in a directory",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path"
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern to filter files (optional)"
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "search_code",
                "description": "Search for a pattern in code files",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Search pattern (regex supported)"
                        },
                        "path": {
                            "type": "string",
                            "description": "Directory to search in"
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": "File pattern to search (e.g., '*.py')"
                        }
                    },
                    "required": ["pattern"]
                }
            }
        ]

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
        files_modified = []
        commands_executed = []

        for iteration in range(max_iterations):
            # Emit progress
            if self._progress_callback:
                await self._progress_callback({
                    "type": "developer_agent",
                    "action": "thinking",
                    "iteration": iteration + 1,
                    "max_iterations": max_iterations,
                })

            # Call LLM
            response = await asyncio.to_thread(
                self._llm_provider.generate_with_tools,
                system_prompt=system_prompt,
                messages=self._messages,
                tools=tools,
                max_tokens=16384,
            )

            # Check for end_turn or no tool use
            if response.stop_reason == "end_turn":
                final_text = self._extract_text_response(response)
                return {
                    "success": True,
                    "message": "Task completed",
                    "result": final_text,
                    "files_modified": files_modified,
                    "commands_executed": commands_executed,
                    "iterations": iteration + 1,
                }

            # Process tool calls
            if response.stop_reason == "tool_use":
                tool_results = await self._process_tool_calls(
                    response,
                    files_modified,
                    commands_executed
                )

                # Add assistant message and tool results to history
                self._messages.append({
                    "role": "assistant",
                    "content": response.content
                })
                self._messages.append({
                    "role": "user",
                    "content": tool_results
                })
            else:
                # Unexpected stop reason
                logger.warning(f"Unexpected stop reason: {response.stop_reason}")
                break

        # Max iterations reached
        return {
            "success": False,
            "message": f"Max iterations ({max_iterations}) reached",
            "result": None,
            "files_modified": files_modified,
            "commands_executed": commands_executed,
            "iterations": max_iterations,
        }

    async def _process_tool_calls(
        self,
        response: ToolCallResponse,
        files_modified: List[str],
        commands_executed: List[str]
    ) -> List[Dict[str, Any]]:
        """Process tool calls from LLM response.

        Args:
            response: LLM response with tool calls
            files_modified: List to track modified files
            commands_executed: List to track executed commands

        Returns:
            Tool results for next LLM call
        """
        results = []

        for block in response.content:
            if isinstance(block, ToolUseBlock):
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                # Emit progress
                if self._progress_callback:
                    await self._progress_callback({
                        "type": "developer_agent",
                        "action": "tool_call",
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                    })

                # Execute the tool
                try:
                    result = await self._execute_tool(
                        tool_name,
                        tool_input,
                        files_modified,
                        commands_executed
                    )
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

        return results

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        files_modified: List[str],
        commands_executed: List[str]
    ) -> Any:
        """Execute a single tool.

        Args:
            tool_name: Name of the tool
            tool_input: Tool input parameters
            files_modified: List to track modified files
            commands_executed: List to track commands

        Returns:
            Tool execution result
        """
        # File operations
        if tool_name == "read_file":
            path = Path(self._working_dir) / tool_input["path"]
            if not path.exists():
                return f"Error: File not found: {path}"
            content = path.read_text()
            start = tool_input.get("start_line")
            end = tool_input.get("end_line")
            if start or end:
                lines = content.splitlines()
                start = (start or 1) - 1
                end = end or len(lines)
                content = "\n".join(lines[start:end])
            return content

        elif tool_name == "write_file":
            path = Path(self._working_dir) / tool_input["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(tool_input["content"])
            files_modified.append(str(path))
            return f"Written to {path}"

        elif tool_name == "edit_file":
            path = Path(self._working_dir) / tool_input["path"]
            if not path.exists():
                return f"Error: File not found: {path}"
            content = path.read_text()
            old_text = tool_input["old_text"]
            new_text = tool_input["new_text"]
            if old_text not in content:
                return f"Error: Text not found in file"
            content = content.replace(old_text, new_text, 1)
            path.write_text(content)
            files_modified.append(str(path))
            return f"Edited {path}"

        elif tool_name == "list_files":
            path = Path(self._working_dir) / tool_input["path"]
            pattern = tool_input.get("pattern", "*")
            if not path.exists():
                return f"Error: Directory not found: {path}"
            files = list(path.glob(pattern))
            return "\n".join(str(f.relative_to(path)) for f in files[:100])

        elif tool_name == "search_code":
            # Use grep via terminal
            pattern = tool_input["pattern"]
            search_path = tool_input.get("path", ".")
            file_pattern = tool_input.get("file_pattern", "")

            cmd = f"grep -rn '{pattern}' {search_path}"
            if file_pattern:
                cmd = f"grep -rn --include='{file_pattern}' '{pattern}' {search_path}"

            result = await self._terminal_toolkit.execute_command(cmd)
            commands_executed.append(cmd)
            return result

        # Terminal commands
        elif tool_name == "run_command":
            cmd = tool_input.get("command", "")
            result = await self._terminal_toolkit.execute_command(cmd)
            commands_executed.append(cmd)
            return result

        # Human toolkit
        elif tool_name == "ask_human":
            tools = self._human_toolkit.get_tools()
            ask_tool = next((t for t in tools if t.name == "ask_human"), None)
            if ask_tool:
                return await ask_tool.async_execute(**tool_input)
            return "Human toolkit not available"

        else:
            # Try terminal toolkit
            terminal_tools = {t.name: t for t in self._terminal_toolkit.get_tools()}
            if tool_name in terminal_tools:
                result = await terminal_tools[tool_name].async_execute(**tool_input)
                if "command" in tool_input:
                    commands_executed.append(tool_input["command"])
                return result

            return f"Unknown tool: {tool_name}"

    def _extract_text_response(self, response: ToolCallResponse) -> str:
        """Extract text content from LLM response.

        Args:
            response: LLM response

        Returns:
            Text content string
        """
        texts = []
        for block in response.content:
            if isinstance(block, TextBlock):
                texts.append(block.text)
        return "\n".join(texts)

    async def cleanup(self, context: AgentContext) -> None:
        """Cleanup agent resources.

        Args:
            context: Agent execution context
        """
        logger.debug(f"DeveloperAgent cleanup for task {self._task_id}")
        self._llm_provider = None
        self._terminal_toolkit = None
        self._human_toolkit = None
        self._progress_callback = None
        self._messages = []
