"""
DocumentAgent - Document creation, management, and cloud services.

This agent handles document-related tasks:
1. Creating and editing local documents
2. Google Drive operations
3. Notion page and database management
4. Document format conversion
5. Research documentation

Based on Eigent's document_agent type.

References:
- Eigent: third-party/eigent/backend/app/service/task.py
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from .base_agent import BaseStepAgent, AgentMetadata, InputSchema, FieldSchema
from ..core.schemas import AgentContext, AgentInput, AgentOutput
from ..tools.toolkits import NoteTakingToolkit, HumanToolkit, FunctionTool
from ..workspace import get_working_directory, get_current_manager
from ..prompts import (
    DOCUMENT_AGENT_SYSTEM_PROMPT,
    NOTE_TAKING_PROMPT,
    DOCUMENT_SUMMARY_PROMPT,
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


class DocumentAgent(BaseStepAgent):
    """Agent for document creation and management.

    This agent handles:
    - Creating local markdown/text documents
    - Research note-taking with citations
    - Google Drive file operations (when MCP toolkit available)
    - Notion page/database operations (when MCP toolkit available)
    - Document summarization and extraction

    Based on Eigent's document_agent pattern.
    """

    INPUT_SCHEMA = InputSchema(
        description="Agent for document creation and cloud service management",
        fields={
            "task": FieldSchema(
                type="str",
                required=True,
                description="Document task to perform"
            ),
            "document_type": FieldSchema(
                type="str",
                required=False,
                description="Type of document operation",
                enum=["create", "edit", "read", "organize", "convert", "summarize"],
                default="create"
            ),
            "content": FieldSchema(
                type="str",
                required=False,
                description="Content for the document"
            ),
            "file_path": FieldSchema(
                type="str",
                required=False,
                description="Path to the document file"
            ),
            "format": FieldSchema(
                type="str",
                required=False,
                description="Document format",
                enum=["markdown", "text", "json", "yaml", "html"],
                default="markdown"
            ),
            "title": FieldSchema(
                type="str",
                required=False,
                description="Document title"
            ),
            "metadata": FieldSchema(
                type="dict",
                required=False,
                description="Additional metadata for the document"
            ),
            "notes_directory": FieldSchema(
                type="str",
                required=False,
                description="Directory for notes storage"
            ),
            "max_iterations": FieldSchema(
                type="int",
                required=False,
                description="Maximum LLM iterations",
                default=15
            ),
        },
        examples=[
            {
                "task": "Create research notes about AI agents",
                "document_type": "create",
                "format": "markdown",
                "title": "AI Agent Research"
            },
            {
                "task": "Summarize the meeting notes",
                "document_type": "summarize",
                "file_path": "notes/meeting-2025-01-22.md"
            }
        ]
    )

    def __init__(self):
        """Initialize DocumentAgent."""
        metadata = AgentMetadata(
            name="document_agent",
            description="Handles document creation and cloud service management"
        )
        super().__init__(metadata)

        self._llm_provider: Optional[AnthropicProvider] = None
        self._note_taking_toolkit: Optional[NoteTakingToolkit] = None
        self._human_toolkit: Optional[HumanToolkit] = None
        self._gdrive_toolkit = None  # GoogleDriveMCPToolkit when available
        self._notion_toolkit = None  # NotionMCPToolkit when available
        self._progress_callback: Optional[Callable] = None
        self._task_id: Optional[str] = None
        self._notes_dir: str = ""
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

            # Get notes directory
            manager = get_current_manager()
            if manager:
                self._notes_dir = str(manager.notes_dir)
            else:
                self._notes_dir = str(Path.home() / ".ami" / "notes")

            # Ensure notes directory exists
            Path(self._notes_dir).mkdir(parents=True, exist_ok=True)

            # Initialize LLM provider
            self._llm_provider = AnthropicProvider()

            # Initialize NoteTaking toolkit
            self._note_taking_toolkit = NoteTakingToolkit(
                notes_dir=self._notes_dir
            )

            # Initialize Human toolkit
            self._human_toolkit = HumanToolkit()

            # Try to initialize Google Drive MCP toolkit
            try:
                from ..tools.toolkits import GoogleDriveMCPToolkit
                self._gdrive_toolkit = GoogleDriveMCPToolkit()
                await self._gdrive_toolkit.initialize()
                logger.info("Google Drive MCP toolkit initialized")
            except (ImportError, ValueError, FileNotFoundError) as e:
                self._gdrive_toolkit = None
                logger.debug(f"Google Drive MCP toolkit not available: {e}")

            # Try to initialize Notion MCP toolkit
            try:
                from ..tools.toolkits import NotionMCPToolkit
                self._notion_toolkit = NotionMCPToolkit()
                await self._notion_toolkit.initialize()
                logger.info("Notion MCP toolkit initialized")
            except (ImportError, ValueError, FileNotFoundError, ConnectionError) as e:
                self._notion_toolkit = None
                logger.debug(f"Notion MCP toolkit not available: {e}")

            # Get progress callback
            self._progress_callback = context.log_callback

            self.is_initialized = True
            logger.info(f"DocumentAgent initialized for task {self._task_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize DocumentAgent: {e}")
            return False

    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """Execute the document task.

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
        document_type = data.get("document_type", "create")
        content = data.get("content", "")
        file_path = data.get("file_path", "")
        doc_format = data.get("format", "markdown")
        title = data.get("title", "")
        metadata = data.get("metadata", {})
        notes_dir = data.get("notes_directory", self._notes_dir)
        max_iterations = data.get("max_iterations", 15)

        # Update notes directory if specified
        if notes_dir and notes_dir != self._notes_dir:
            self._notes_dir = notes_dir
            Path(self._notes_dir).mkdir(parents=True, exist_ok=True)
            self._note_taking_toolkit = NoteTakingToolkit(notes_dir=notes_dir)

        try:
            # Handle simple direct operations
            if document_type == "create" and content:
                result = await self._create_document(
                    content, file_path, doc_format, title, metadata
                )
                return AgentOutput(
                    success=result["success"],
                    message=result["message"],
                    data=result
                )

            elif document_type == "read" and file_path:
                result = await self._read_document(file_path)
                return AgentOutput(
                    success=result["success"],
                    message=result["message"],
                    data=result
                )

            # Complex operations - use LLM loop
            prompt_context = PromptContext(
                working_directory=self._notes_dir,
            )
            system_prompt = DOCUMENT_AGENT_SYSTEM_PROMPT.format(prompt_context)

            initial_message = self._build_initial_message(
                task, document_type, file_path, doc_format, title
            )

            tools = self._get_tools()

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
                    "document_type": document_type,
                    "result": result.get("result"),
                    "documents_created": result.get("documents_created", []),
                    "documents_modified": result.get("documents_modified", []),
                    "iterations": result.get("iterations", 0),
                }
            )

        except Exception as e:
            logger.error(f"Error in DocumentAgent: {e}")
            return AgentOutput(
                success=False,
                message=f"Error during document task: {str(e)}",
                data={"error": str(e)}
            )

    async def _create_document(
        self,
        content: str,
        file_path: str,
        doc_format: str,
        title: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new document directly.

        Args:
            content: Document content
            file_path: Optional file path
            doc_format: Document format
            title: Document title
            metadata: Additional metadata

        Returns:
            Result dictionary
        """
        try:
            # Generate file path if not provided
            if not file_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
                safe_title = safe_title.replace(" ", "_")[:50] or "document"
                file_path = f"{safe_title}_{timestamp}.{self._get_extension(doc_format)}"

            # Ensure full path
            if not Path(file_path).is_absolute():
                file_path = str(Path(self._notes_dir) / file_path)

            # Add metadata header for markdown
            if doc_format == "markdown" and (title or metadata):
                header_parts = ["---"]
                if title:
                    header_parts.append(f"title: {title}")
                header_parts.append(f"date: {datetime.now().isoformat()}")
                for key, value in metadata.items():
                    header_parts.append(f"{key}: {value}")
                header_parts.append("---\n")
                content = "\n".join(header_parts) + content

            # Write file
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            Path(file_path).write_text(content)

            return {
                "success": True,
                "message": f"Document created: {file_path}",
                "file_path": file_path,
                "format": doc_format,
                "title": title,
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to create document: {str(e)}",
                "error": str(e)
            }

    async def _read_document(self, file_path: str) -> Dict[str, Any]:
        """Read a document.

        Args:
            file_path: Path to the document

        Returns:
            Result dictionary with content
        """
        try:
            if not Path(file_path).is_absolute():
                file_path = str(Path(self._notes_dir) / file_path)

            if not Path(file_path).exists():
                return {
                    "success": False,
                    "message": f"File not found: {file_path}",
                }

            content = Path(file_path).read_text()

            return {
                "success": True,
                "message": f"Document read: {file_path}",
                "file_path": file_path,
                "content": content,
                "size": len(content),
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to read document: {str(e)}",
                "error": str(e)
            }

    def _get_extension(self, doc_format: str) -> str:
        """Get file extension for document format.

        Args:
            doc_format: Document format

        Returns:
            File extension
        """
        extensions = {
            "markdown": "md",
            "text": "txt",
            "json": "json",
            "yaml": "yaml",
            "html": "html",
        }
        return extensions.get(doc_format, "txt")

    def _build_initial_message(
        self,
        task: str,
        document_type: str,
        file_path: str,
        doc_format: str,
        title: str
    ) -> str:
        """Build the initial message for the LLM.

        Args:
            task: Task description
            document_type: Type of document operation
            file_path: Relevant file path
            doc_format: Document format
            title: Document title

        Returns:
            Initial message string
        """
        parts = [f"**Task:** {task}"]

        if document_type:
            parts.append(f"**Operation:** {document_type}")

        if file_path:
            parts.append(f"**File:** {file_path}")

        if doc_format:
            parts.append(f"**Format:** {doc_format}")

        if title:
            parts.append(f"**Title:** {title}")

        parts.append(f"\n**Notes Directory:** {self._notes_dir}")
        parts.append("\nPlease proceed with this document task.")

        return "\n\n".join(parts)

    def _get_tools(self) -> List[Dict[str, Any]]:
        """Get available tools for the document agent.

        Returns:
            List of tool definitions
        """
        tools = []

        # NoteTaking tools
        for tool in self._note_taking_toolkit.get_tools():
            tools.append(tool.to_anthropic_format())

        # Human tools
        for tool in self._human_toolkit.get_tools():
            tools.append(tool.to_anthropic_format())

        # Google Drive MCP tools (if available)
        if self._gdrive_toolkit:
            for tool in self._gdrive_toolkit.get_function_tools():
                tools.append(tool.to_anthropic_format())

        # Notion MCP tools (if available)
        if self._notion_toolkit:
            for tool in self._notion_toolkit.get_function_tools():
                tools.append(tool.to_anthropic_format())

        # Add document-specific tools
        tools.extend([
            {
                "name": "create_document",
                "description": "Create a new document with content",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Document title"
                        },
                        "content": {
                            "type": "string",
                            "description": "Document content"
                        },
                        "format": {
                            "type": "string",
                            "description": "Document format (markdown, text, json)",
                            "enum": ["markdown", "text", "json", "yaml", "html"]
                        },
                        "file_name": {
                            "type": "string",
                            "description": "Optional file name"
                        }
                    },
                    "required": ["content"]
                }
            },
            {
                "name": "read_document",
                "description": "Read the contents of a document",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the document"
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "list_documents",
                "description": "List documents in the notes directory",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern to filter (e.g., '*.md')"
                        }
                    }
                }
            },
            {
                "name": "append_to_document",
                "description": "Append content to an existing document",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the document"
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to append"
                        }
                    },
                    "required": ["path", "content"]
                }
            }
        ])

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
        documents_created = []
        documents_modified = []

        for iteration in range(max_iterations):
            # Emit progress
            if self._progress_callback:
                await self._progress_callback({
                    "type": "document_agent",
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
                max_tokens=4096,
            )

            # Check for completion
            if response.stop_reason == "end_turn":
                final_text = self._extract_text_response(response)
                return {
                    "success": True,
                    "message": "Document task completed",
                    "result": final_text,
                    "documents_created": documents_created,
                    "documents_modified": documents_modified,
                    "iterations": iteration + 1,
                }

            # Process tool calls
            if response.stop_reason == "tool_use":
                tool_results = await self._process_tool_calls(
                    response,
                    documents_created,
                    documents_modified
                )

                self._messages.append({
                    "role": "assistant",
                    "content": response.content
                })
                self._messages.append({
                    "role": "user",
                    "content": tool_results
                })
            else:
                logger.warning(f"Unexpected stop reason: {response.stop_reason}")
                break

        return {
            "success": False,
            "message": f"Max iterations ({max_iterations}) reached",
            "result": None,
            "documents_created": documents_created,
            "documents_modified": documents_modified,
            "iterations": max_iterations,
        }

    async def _process_tool_calls(
        self,
        response: ToolCallResponse,
        documents_created: List[str],
        documents_modified: List[str]
    ) -> List[Dict[str, Any]]:
        """Process tool calls from LLM response.

        Args:
            response: LLM response with tool calls
            documents_created: List to track created documents
            documents_modified: List to track modified documents

        Returns:
            Tool results for next LLM call
        """
        results = []

        for block in response.content:
            if isinstance(block, ToolUseBlock):
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                if self._progress_callback:
                    await self._progress_callback({
                        "type": "document_agent",
                        "action": "tool_call",
                        "tool_name": tool_name,
                    })

                try:
                    result = await self._execute_tool(
                        tool_name,
                        tool_input,
                        documents_created,
                        documents_modified
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
        documents_created: List[str],
        documents_modified: List[str]
    ) -> Any:
        """Execute a single tool.

        Args:
            tool_name: Name of the tool
            tool_input: Tool input parameters
            documents_created: List to track created documents
            documents_modified: List to track modified documents

        Returns:
            Tool execution result
        """
        # Document operations
        if tool_name == "create_document":
            result = await self._create_document(
                content=tool_input.get("content", ""),
                file_path=tool_input.get("file_name", ""),
                doc_format=tool_input.get("format", "markdown"),
                title=tool_input.get("title", ""),
                metadata={}
            )
            if result["success"]:
                documents_created.append(result["file_path"])
            return result["message"]

        elif tool_name == "read_document":
            result = await self._read_document(tool_input["path"])
            if result["success"]:
                return result["content"]
            return result["message"]

        elif tool_name == "list_documents":
            pattern = tool_input.get("pattern", "*")
            path = Path(self._notes_dir)
            files = list(path.glob(pattern))
            return "\n".join(str(f.relative_to(path)) for f in files[:100])

        elif tool_name == "append_to_document":
            file_path = tool_input["path"]
            if not Path(file_path).is_absolute():
                file_path = str(Path(self._notes_dir) / file_path)

            if Path(file_path).exists():
                with open(file_path, "a") as f:
                    f.write("\n" + tool_input["content"])
                documents_modified.append(file_path)
                return f"Appended to {file_path}"
            return f"File not found: {file_path}"

        # NoteTaking toolkit
        note_tools = {t.name: t for t in self._note_taking_toolkit.get_tools()}
        if tool_name in note_tools:
            result = await note_tools[tool_name].async_execute(**tool_input)
            return result

        # Human toolkit
        human_tools = {t.name: t for t in self._human_toolkit.get_tools()}
        if tool_name in human_tools:
            return await human_tools[tool_name].async_execute(**tool_input)

        # Google Drive MCP toolkit
        if self._gdrive_toolkit:
            gdrive_tools = {t.name: t for t in self._gdrive_toolkit.get_function_tools()}
            if tool_name in gdrive_tools:
                result = await gdrive_tools[tool_name].async_execute(**tool_input)
                return result

        # Notion MCP toolkit
        if self._notion_toolkit:
            notion_tools = {t.name: t for t in self._notion_toolkit.get_function_tools()}
            if tool_name in notion_tools:
                result = await notion_tools[tool_name].async_execute(**tool_input)
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
        logger.debug(f"DocumentAgent cleanup for task {self._task_id}")
        self._llm_provider = None
        self._note_taking_toolkit = None
        self._human_toolkit = None
        self._progress_callback = None
        self._messages = []
