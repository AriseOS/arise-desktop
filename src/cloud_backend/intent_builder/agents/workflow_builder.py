"""
WorkflowBuilder Agent

Uses Claude Agent SDK to generate Workflow YAML from Intent sequences.
Replaces the old MetaFlowGenerator + WorkflowGenerator combination.

Design principles:
- Simple system prompt with core rules only
- Claude reads detailed specs via tools when needed
- Validation integrated into generation loop
- Support multi-turn dialogue for workflow understanding and editing

Multi-turn conversation pattern:
- Use single ClaudeSDKClient instance for entire session
- Call query() multiple times within same async context
- Session state maintained automatically by SDK
"""

import os
import re
import yaml
import logging
import tempfile
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncIterator, Callable, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

from .tools.validate import validate_workflow_dict

# Skills management
from src.cloud_backend.services.skills import SkillManager

if TYPE_CHECKING:
    from src.common.config_service import ConfigService
    from src.cloud_backend.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class SessionState(Enum):
    """State of a workflow builder session"""
    IDLE = "idle"
    GENERATING = "generating"
    READY = "ready"  # Workflow generated, ready for dialogue
    CLOSED = "closed"


# System prompt - focus on understanding, not rules
SYSTEM_PROMPT = """You are helping users automate their browser workflows.

## What You're Doing

Users record their browser actions (clicks, navigation, data extraction). Your job is to generate a Workflow YAML that can **replay and automate** what they did.

Think of it this way:
- The user showed you exactly how they do a task manually
- You're creating an automation script that does the same thing
- The workflow will run on a fresh browser - it needs to follow the same path the user took

## Key Insight

The Intent sequence you receive is a recording of real user actions. Each operation happened for a reason:
- Every click led somewhere
- Every navigation was necessary to reach the next page
- Every xpath shows exactly which element the user interacted with

When the workflow runs, it starts from scratch. If the user clicked through 3 pages to reach a product list, your workflow needs those same 3 navigation steps - you can't just jump to the final URL because the page state won't be the same.

## Available Skills

| Skill | Purpose |
|-------|---------|
| workflow-generation | Workflow structure and generation process |
| agent-specs | Agent capabilities (browser_agent, scraper_agent, etc.) |
| workflow-optimizations | Optimization patterns (click-to-navigate, scroll, etc.) |
| workflow-validation | Validate your YAML before output |

**CRITICAL**: Only use agents defined in `agent-specs` skill. Do NOT invent agents like `llm_agent`, `ai_agent`, etc.

## Output

**IMPORTANT**: You must write the final workflow to `workflow.yaml` file using the Write tool. Do NOT just output it in a code block - the file is required for the system to read your workflow.

After writing the file, provide a high-level explanation of the workflow and summarize what changed.
"""


# System prompt for modification mode
MODIFICATION_SYSTEM_PROMPT = """You are helping users modify their existing workflow.

## How Workflow Works

A workflow has two layers:

1. **workflow.yaml** - The framework that defines:
   - What steps to execute and in what order
   - Which agent handles each step
   - Step parameters like URLs, selectors, output variables

### Available Agents

| Agent | Use Case | Required Inputs |
|-------|----------|-----------------|
| `browser_agent` | Navigate, click, fill forms | `target_url` or `interaction_steps` |
| `scraper_agent` | Extract data from page | `data_requirements` |
| `text_agent` | LLM text generation/transform | `instruction` |
| `variable` | Data operations (set/filter/slice) | `operation`, `data` |
| `storage_agent` | Store/query/export data | `operation`, `collection` |
| `tavily_agent` | Web search | `operation`, `query` |

**Example - text_agent for summarization**:
```yaml
- id: generate-summary
  agent: text_agent
  inputs:
    instruction: "Summarize this content in Chinese"
    data: "{{extracted_content}}"
  outputs:
    result: summary
```

2. **extraction_script.py** - The actual code that runs for scraper steps:
   - Located directly in `{step_id}/` directories
   - Parses DOM data and extracts specific fields
   - Uses XPath selectors to find elements

## Problem Type Detection

**IMPORTANT**: First determine what type of problem the user is reporting:

| User Keywords | Problem Type | Action |
|---------------|--------------|--------|
| "抓不到", "空", "没有数据", "empty", "no data" | **Scraper Fix** | Read `scraper-fix` skill and follow its workflow |
| "字段缺失", "missing field", "少了", "没抓到xxx" | **Scraper Fix** | Read `scraper-fix` skill and follow its workflow |
| "数据错误", "wrong data", "抓错了" | **Scraper Fix** | Read `scraper-fix` skill and follow its workflow |
| "添加步骤", "删除步骤", "修改顺序" | Workflow Modification | Edit `workflow.yaml` |
| "修改URL", "改参数" | Workflow Modification | Edit `workflow.yaml` |

## For Scraper/Extraction Issues

When user reports data extraction problems:

1. **Read the scraper-fix skill FIRST**:
   ```bash
   cat .claude/skills/scraper-fix/SKILL.md
   ```

2. **Follow the workflow in the skill** to diagnose and fix the issue.

3. **Run and verify** the script outputs correct data before finishing.

## For Workflow Structure Modifications

1. Read the user's request carefully
2. Make the requested changes to `workflow.yaml`
3. Use workflow-validation skill to check your changes
4. Explain the workflow at a high level (what it does and key steps)
5. Briefly summarize what you changed

## Important Rules

- **For scraper issues**: Always read `scraper-fix` skill first
- Keep the user response focused on behavior and changes, not the full YAML content
- Preserve parts the user didn't ask to change
- Every step must have: `id`, `agent`, and `inputs`
- **Only use agents from the table above. Do NOT invent agents like `llm_agent`, `ai_agent`, etc.**
- For scripts, only modify files in the script directory
"""


@dataclass
class GenerationResult:
    """Result of workflow generation"""
    success: bool
    workflow: Optional[Dict[str, Any]] = None
    workflow_yaml: Optional[str] = None
    error: Optional[str] = None
    iterations: int = 0
    session_id: Optional[str] = None  # For continuing dialogue
    script_generation: Optional[Dict[str, Any]] = None  # Script generation results


@dataclass
class StreamEvent:
    """Streaming event from generation process"""
    type: str  # "progress", "text", "tool_use", "workflow_updated", "complete", "error"
    message: str
    data: Optional[Dict[str, Any]] = None
    workflow_yaml: Optional[str] = None  # Updated workflow YAML (for workflow_updated/complete)


@dataclass
class DialogueMessage:
    """A message in the workflow dialogue"""
    role: str  # "user" or "assistant"
    content: str
    workflow_yaml: Optional[str] = None  # If assistant modified the workflow
    timestamp: Optional[float] = None


class WorkflowBuilder:
    """
    Generate Workflow YAML from Intent sequences using Claude Agent SDK.

    This replaces the old MetaFlowGenerator + WorkflowGenerator combination
    with a single Claude Agent that has access to tools for reading specs
    and validating workflows.
    """

    def __init__(
        self,
        config_service: Optional["ConfigService"] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_iterations: int = 100
    ):
        """
        Initialize WorkflowBuilder.

        Args:
            config_service: ConfigService for reading configuration
            api_key: Anthropic API key (overrides config/env)
            model: Model to use (default: claude-sonnet-4-5)
            base_url: API proxy URL
            max_iterations: Max turns for Claude Agent
        """
        # Get API key
        if api_key:
            self.api_key = api_key
        elif config_service:
            self.api_key = (
                config_service.get("claude_agent.api_key") or
                config_service.get("agent.llm.api_key") or
                os.environ.get("ANTHROPIC_API_KEY")
            )
        else:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError("Anthropic API key not found")

        # Get model
        if model:
            self.model = model
        elif config_service:
            self.model = config_service.get("claude_agent.model") or "claude-sonnet-4-5"
        else:
            self.model = "claude-sonnet-4-5"

        # Get base URL
        if base_url:
            self.base_url = base_url
        elif config_service:
            self.base_url = config_service.get("llm.proxy_url")
        else:
            self.base_url = None

        self.max_iterations = max_iterations

        logger.info(f"WorkflowBuilder initialized:")
        logger.info(f"  Model: {self.model}")
        logger.info(f"  Base URL: {self.base_url or '(default)'}")
        logger.info(f"  Max iterations: {self.max_iterations}")

    def _build_system_prompt(self) -> str:
        """Build system prompt (Skills provide detailed guidance)"""
        return SYSTEM_PROMPT

    def _build_user_prompt(
        self,
        task_description: str,
        intent_sequence: List[Dict[str, Any]],
        user_query: Optional[str] = None
    ) -> str:
        """Build user prompt with task, intents, and complete operations"""
        # Build intent data with full operations for Claude to understand user behavior
        enriched_intents = []
        for intent in intent_sequence:
            enriched = {
                "description": intent.get("description", ""),
                "intent_type": intent.get("intent_type", "unknown"),
            }

            # Include ALL operation details - let Claude decide what's important
            operations = intent.get("operations", [])
            if operations:
                op_details = []
                for op in operations:
                    op_type = op.get("type", "unknown")
                    url = op.get("url", "")
                    element = op.get("element", {})

                    detail = {"type": op_type}
                    if url:
                        detail["url"] = url
                    if element.get("textContent"):
                        # Truncate very long text but keep enough context
                        detail["text"] = element["textContent"][:200]
                    if element.get("href"):
                        detail["href"] = element["href"]
                    if element.get("xpath"):
                        detail["xpath"] = element["xpath"]
                    if element.get("tagName"):
                        detail["tagName"] = element["tagName"]
                    if element.get("id"):
                        detail["id"] = element["id"]
                    if element.get("className"):
                        detail["className"] = element["className"]

                    op_details.append(detail)

                enriched["operations"] = op_details
                enriched["operations_count"] = len(operations)

            enriched_intents.append(enriched)

        intents_yaml = yaml.dump(enriched_intents, allow_unicode=True, default_flow_style=False)

        # Build user query section if available
        user_query_section = ""
        if user_query:
            user_query_section = f"""
## User Query (IMPORTANT - User's Goal)
{user_query}

**Pay attention to:**
- If the user mentions "repeat", "loop", "all items", "top N", "each" → Use `foreach` to iterate
- If the user mentions a specific count (e.g., "10 products") → Use this as the iteration limit
- The user query describes the ACTUAL goal, not just what was recorded
"""

        return f"""Please generate a Workflow for the following task:

## Task Description
{task_description}
{user_query_section}
## User's Recorded Actions (Intent Operations)

Each operation contains details you need for optimization decisions (especially `href` for click-to-navigate):

```yaml
{intents_yaml}
```

## Your Task Checklist

Use TodoWrite to track these steps:

1. [ ] Read `workflow-generation` skill - understand workflow structure
2. [ ] Read `agent-specs` skill - understand agent input formats (especially browser_agent's interaction_steps)
3. [ ] Read `workflow-optimizations` skill - understand optimization patterns
4. [ ] Analyze each intent operation for optimization opportunities:
   - Click with `href` → Can optimize to `target_url`
   - Click without `href` → Must use `interaction_steps`
   - Consecutive scrolls → Combine or remove
5. [ ] Generate the optimized workflow YAML
6. [ ] Validate with `workflow-validation` skill
7. [ ] **Write the workflow to `workflow.yaml` file** (REQUIRED - use Write tool)
8. [ ] Output final YAML in code block and list optimizations applied

## Key Reminders

- `xpath_hints` must be **dict format**: `xpath_hints: {{key: "//xpath"}}` (NOT a list!)
- All click/fill/scroll MUST use `interaction_steps` (unless optimized to `target_url`)
- Document which operations were optimized and why
"""

    def _prepare_working_directory(self) -> Path:
        """Create a temporary working directory with Skills accessible"""
        work_dir = Path(tempfile.mkdtemp(prefix="workflow_builder_"))
        SkillManager.prepare_workflow_skills(work_dir)
        return work_dir

    def _extract_yaml_from_response(self, response: str) -> Optional[str]:
        """Extract YAML from Claude's response (fallback method)"""
        # Look for ```yaml blocks
        yaml_match = re.search(r'```yaml\s*\n(.*?)\n```', response, re.DOTALL)
        if yaml_match:
            return yaml_match.group(1).strip()

        # Look for generic ``` blocks
        code_match = re.search(r'```\s*\n(.*?)\n```', response, re.DOTALL)
        if code_match:
            content = code_match.group(1).strip()
            # Check if it looks like YAML
            if content.startswith("apiVersion:") or content.startswith("kind:"):
                return content

        return None

    def _find_workflow_file(self, work_dir: Path) -> Optional[Path]:
        """
        Find the workflow YAML file generated by Claude Agent.

        Claude Agent typically writes to workflow.yaml, but we also check
        for other common names.
        """
        # Common workflow file names (in order of priority)
        candidate_names = [
            "workflow.yaml",
            "workflow.yml",
            "generated_workflow.yaml",
            "output.yaml",
        ]

        for name in candidate_names:
            file_path = work_dir / name
            if file_path.exists():
                logger.info(f"Found workflow file: {file_path}")
                return file_path

        # Also search for any .yaml/.yml file in the directory
        yaml_files = list(work_dir.glob("*.yaml")) + list(work_dir.glob("*.yml"))
        if yaml_files:
            # Sort by modification time, newest first
            yaml_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            logger.info(f"Found workflow file by glob: {yaml_files[0]}")
            return yaml_files[0]

        return None

    def _read_workflow_from_file(self, work_dir: Path) -> Optional[str]:
        """
        Read workflow YAML content from file generated by Claude Agent.

        This is the preferred method as it reads exactly what Claude Agent wrote,
        avoiding any formatting issues from response text extraction.
        """
        file_path = self._find_workflow_file(work_dir)
        if file_path:
            try:
                content = file_path.read_text(encoding="utf-8")
                logger.info(f"Read workflow from file: {file_path} ({len(content)} chars)")
                return content
            except Exception as e:
                logger.error(f"Failed to read workflow file {file_path}: {e}")
        return None

    async def build(
        self,
        task_description: str,
        intent_sequence: List[Dict[str, Any]],
        user_query: Optional[str] = None
    ) -> GenerationResult:
        """
        Generate Workflow from Intent sequence.

        Args:
            task_description: User's task description
            intent_sequence: List of Intent dictionaries
            user_query: User's goal/intent (e.g., "repeat for 10 items")

        Returns:
            GenerationResult with workflow or error
        """
        logger.info(f"Starting workflow generation for task: {task_description}")
        if user_query:
            logger.info(f"User query: {user_query}")
        logger.info(f"Intent count: {len(intent_sequence)}")

        try:
            from claude_agent_sdk import (
                ClaudeSDKClient,
                ClaudeAgentOptions,
                ResultMessage,
                AssistantMessage,
                TextBlock,
            )
        except ImportError:
            return GenerationResult(
                success=False,
                error="Ami Coder SDK not installed. Please install with: pip install claude-agent-sdk"
            )

        # Prepare working directory
        work_dir = self._prepare_working_directory()
        logger.info(f"Working directory: {work_dir}")

        try:
            # Build prompts
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(task_description, intent_sequence, user_query)

            # Configure environment
            env_vars = dict(os.environ)
            env_vars["ANTHROPIC_API_KEY"] = self.api_key
            if self.base_url:
                env_vars["ANTHROPIC_BASE_URL"] = self.base_url

            # Configure agent options with Skills enabled
            options = ClaudeAgentOptions(
                model=self.model,
                cwd=str(work_dir),
                max_turns=self.max_iterations,
                allowed_tools=["Skill", "Read", "Write", "Bash", "Glob"],
                setting_sources=["project"],  # Load Skills from .claude/skills/
                permission_mode="bypassPermissions",
                system_prompt=system_prompt,
                env=env_vars,
                max_buffer_size=1024 * 1024
            )

            # Run agent
            final_response = ""
            turn_count = 0

            logger.info("🤖 Starting Claude Agent SDK workflow generation...")

            async with asyncio.timeout(self.max_iterations * 60):
                async with ClaudeSDKClient(options=options) as client:
                    await client.query(user_prompt)
                    logger.info("📤 Sent user prompt to Claude Agent")

                    async for message in client.receive_response():
                        if isinstance(message, AssistantMessage):
                            turn_count += 1
                            logger.info(f"📨 Turn {turn_count}: Received AssistantMessage")
                            if hasattr(message, 'content'):
                                for block in message.content:
                                    if isinstance(block, TextBlock):
                                        # Log first 200 chars of text
                                        preview = block.text[:200] + "..." if len(block.text) > 200 else block.text
                                        logger.info(f"   📝 TextBlock: {preview}")
                                        final_response += block.text + "\n"
                                    elif hasattr(block, 'name'):
                                        # ToolUseBlock - log with input parameters
                                        tool_input = getattr(block, 'input', {})
                                        if block.name == "Bash":
                                            cmd = tool_input.get('command', '')[:200]
                                            logger.info(f"   🔧 ToolUse: Bash - {cmd}")
                                        elif block.name == "Write":
                                            file_path = tool_input.get('file_path', '')
                                            content_len = len(tool_input.get('content', ''))
                                            logger.info(f"   🔧 ToolUse: Write - {file_path} ({content_len} chars)")
                                        elif block.name == "Read":
                                            file_path = tool_input.get('file_path', '')
                                            logger.info(f"   🔧 ToolUse: Read - {file_path}")
                                        elif block.name == "Edit":
                                            file_path = tool_input.get('file_path', '')
                                            logger.info(f"   🔧 ToolUse: Edit - {file_path}")
                                        else:
                                            logger.info(f"   🔧 ToolUse: {block.name}")

                        if isinstance(message, ResultMessage):
                            logger.info(f"✅ ResultMessage: is_error={message.is_error}, num_turns={message.num_turns}")
                            if message.is_error:
                                logger.error(f"❌ Agent error: {message.result}")
                                return GenerationResult(
                                    success=False,
                                    error=message.result,
                                    iterations=message.num_turns
                                )

            # Priority 1: Read workflow from file generated by Claude Agent
            yaml_content = self._read_workflow_from_file(work_dir)

            # Priority 2: Fall back to extracting from response text
            if not yaml_content:
                logger.warning("No workflow file found, falling back to response extraction")
                yaml_content = self._extract_yaml_from_response(final_response)

            if not yaml_content:
                # Log the response for debugging
                logger.error(f"❌ Failed to get YAML. No file found and response extraction failed.")
                logger.error(f"❌ Response length: {len(final_response)}")
                logger.error(f"❌ Response preview (first 500 chars): {final_response[:500]}")
                logger.error(f"❌ Response preview (last 500 chars): {final_response[-500:] if len(final_response) > 500 else 'N/A'}")
                # List files in work_dir for debugging
                try:
                    files = list(work_dir.iterdir())
                    logger.error(f"❌ Files in work_dir: {[f.name for f in files]}")
                except Exception:
                    pass
                return GenerationResult(
                    success=False,
                    error="Failed to extract YAML: no workflow file found and response parsing failed",
                    iterations=turn_count
                )

            # Parse and validate
            try:
                workflow = yaml.safe_load(yaml_content)
            except yaml.YAMLError as e:
                logger.error(f"❌ YAML parse error: {e}")
                logger.error(f"❌ YAML content preview: {yaml_content[:500]}")
                return GenerationResult(
                    success=False,
                    error=f"YAML parse error: {e}",
                    iterations=turn_count
                )

            validation = validate_workflow_dict(workflow)
            if not validation.valid:
                return GenerationResult(
                    success=False,
                    workflow=workflow,
                    workflow_yaml=yaml_content,
                    error=f"Validation failed: {'; '.join(validation.errors)}",
                    iterations=turn_count
                )

            return GenerationResult(
                success=True,
                workflow=workflow,
                workflow_yaml=yaml_content,
                iterations=turn_count
            )

        finally:
            # Cleanup working directory
            import shutil
            try:
                shutil.rmtree(work_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup working directory: {e}")

    async def build_stream(
        self,
        task_description: str,
        intent_sequence: List[Dict[str, Any]]
    ) -> AsyncIterator[StreamEvent]:
        """
        Generate Workflow with streaming progress updates.

        This is useful for frontend display of generation progress.

        Args:
            task_description: User's task description
            intent_sequence: List of Intent dictionaries

        Yields:
            StreamEvent objects with progress updates
        """
        yield StreamEvent(
            type="progress",
            message="Initializing workflow generation...",
            data={"progress": 5}
        )

        try:
            from claude_agent_sdk import (
                ClaudeSDKClient,
                ClaudeAgentOptions,
                ResultMessage,
                AssistantMessage,
                TextBlock,
                ToolUseBlock,
            )
        except ImportError:
            yield StreamEvent(
                type="error",
                message="Ami Coder SDK not installed"
            )
            return

        work_dir = self._prepare_working_directory()

        try:
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(task_description, intent_sequence)

            env_vars = dict(os.environ)
            env_vars["ANTHROPIC_API_KEY"] = self.api_key
            if self.base_url:
                env_vars["ANTHROPIC_BASE_URL"] = self.base_url

            options = ClaudeAgentOptions(
                model=self.model,
                cwd=str(work_dir),
                max_turns=self.max_iterations,
                allowed_tools=["Skill", "Read", "Write", "Bash", "Glob"],
                setting_sources=["project"],  # Load Skills from .claude/skills/
                permission_mode="bypassPermissions",
                system_prompt=system_prompt,
                env=env_vars,
                max_buffer_size=1024 * 1024
            )

            yield StreamEvent(
                type="progress",
                message="Analyzing intent sequence...",
                data={"progress": 15}
            )

            final_response = ""
            turn_count = 0

            async with asyncio.timeout(self.max_iterations * 60):
                async with ClaudeSDKClient(options=options) as client:
                    await client.query(user_prompt)

                    async for message in client.receive_response():
                        if isinstance(message, AssistantMessage):
                            turn_count += 1
                            progress = min(20 + turn_count * 10, 80)

                            if hasattr(message, 'content'):
                                for block in message.content:
                                    if isinstance(block, TextBlock):
                                        final_response += block.text + "\n"
                                        # Yield text updates
                                        yield StreamEvent(
                                            type="text",
                                            message=block.text[:200] + "..." if len(block.text) > 200 else block.text,
                                            data={"progress": progress}
                                        )

                                    elif isinstance(block, ToolUseBlock):
                                        # Log tool details
                                        tool_input = getattr(block, 'input', {})
                                        if block.name == "Bash":
                                            cmd = tool_input.get('command', '')[:200]
                                            logger.info(f"   🔧 ToolUse: Bash - {cmd}")
                                        elif block.name == "Write":
                                            file_path = tool_input.get('file_path', '')
                                            content_len = len(tool_input.get('content', ''))
                                            logger.info(f"   🔧 ToolUse: Write - {file_path} ({content_len} chars)")
                                        elif block.name == "Read":
                                            file_path = tool_input.get('file_path', '')
                                            logger.info(f"   🔧 ToolUse: Read - {file_path}")
                                        elif block.name == "Edit":
                                            file_path = tool_input.get('file_path', '')
                                            logger.info(f"   🔧 ToolUse: Edit - {file_path}")
                                        else:
                                            logger.info(f"   🔧 ToolUse: {block.name}")
                                        yield StreamEvent(
                                            type="tool_use",
                                            message=f"Using tool: {block.name}",
                                            data={
                                                "tool": block.name,
                                                "progress": progress
                                            }
                                        )

                        if isinstance(message, ResultMessage):
                            if message.is_error:
                                yield StreamEvent(
                                    type="error",
                                    message=message.result or "Generation failed"
                                )
                                return

            yield StreamEvent(
                type="progress",
                message="Validating workflow...",
                data={"progress": 90}
            )

            # Priority 1: Read workflow from file generated by Claude Agent
            yaml_content = self._read_workflow_from_file(work_dir)

            # Priority 2: Fall back to extracting from response text
            if not yaml_content:
                logger.warning("No workflow file found, falling back to response extraction")
                yaml_content = self._extract_yaml_from_response(final_response)

            if not yaml_content:
                # Log the response for debugging
                logger.error(f"❌ Failed to get YAML. No file found and response extraction failed.")
                logger.error(f"❌ Response length: {len(final_response)}")
                logger.error(f"❌ Response preview (first 500 chars): {final_response[:500]}")
                # List files in work_dir for debugging
                try:
                    files = list(work_dir.iterdir())
                    logger.error(f"❌ Files in work_dir: {[f.name for f in files]}")
                except Exception:
                    pass
                yield StreamEvent(
                    type="error",
                    message="Failed to extract YAML: no workflow file found and response parsing failed"
                )
                return

            try:
                workflow = yaml.safe_load(yaml_content)
            except yaml.YAMLError as e:
                logger.error(f"❌ YAML parse error: {e}")
                logger.error(f"❌ YAML content preview: {yaml_content[:500]}")
                yield StreamEvent(
                    type="error",
                    message=f"YAML parse error: {e}"
                )
                return

            validation = validate_workflow_dict(workflow)
            if not validation.valid:
                yield StreamEvent(
                    type="error",
                    message=f"Validation failed: {'; '.join(validation.errors)}"
                )
                return

            yield StreamEvent(
                type="complete",
                message="Workflow generated successfully",
                data={
                    "progress": 100,
                    "workflow": workflow,
                    "workflow_yaml": yaml_content,
                    "iterations": turn_count
                }
            )

        finally:
            import shutil
            try:
                shutil.rmtree(work_dir)
            except Exception:
                pass


class WorkflowBuilderSession:
    """
    Interactive session for workflow generation and dialogue.

    Supports multi-turn conversation where users can:
    1. Generate initial workflow from intents
    2. Ask questions about the workflow
    3. Request modifications via natural language
    4. Get explanations of specific steps

    The session maintains a single ClaudeSDKClient instance for the entire
    conversation, enabling proper context preservation.

    Example:
        async with WorkflowBuilderSession(api_key="...") as session:
            # Initial generation
            result = await session.generate(task_description, intents)

            # Follow-up dialogue
            response = await session.chat("Why did you use browser_agent here?")
            response = await session.chat("Change step 3 to use scraper_agent")

            # Get current workflow
            workflow = session.get_current_workflow()
    """

    def __init__(
        self,
        config_service: Optional["ConfigService"] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_iterations: int = 100,
        session_id: Optional[str] = None
    ):
        """
        Initialize WorkflowBuilderSession.

        Args:
            config_service: ConfigService for reading configuration
            api_key: Anthropic API key
            model: Model to use (default: claude-sonnet-4-5)
            base_url: API proxy URL
            max_iterations: Max turns per request
            session_id: Optional session ID (auto-generated if not provided)
        """
        # Get API key
        if api_key:
            self.api_key = api_key
        elif config_service:
            self.api_key = (
                config_service.get("claude_agent.api_key") or
                config_service.get("agent.llm.api_key") or
                os.environ.get("ANTHROPIC_API_KEY")
            )
        else:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError("Anthropic API key not found")

        # Get model
        if model:
            self.model = model
        elif config_service:
            self.model = config_service.get("claude_agent.model") or "claude-sonnet-4-5"
        else:
            self.model = "claude-sonnet-4-5"

        # Get base URL
        if base_url:
            self.base_url = base_url
        elif config_service:
            self.base_url = config_service.get("llm.proxy_url")
        else:
            self.base_url = None

        self.max_iterations = max_iterations
        self.session_id = session_id or f"workflow_session_{id(self)}"

        # Session state
        self.state = SessionState.IDLE
        self._client = None
        self._work_dir: Optional[Path] = None
        self._current_workflow: Optional[Dict[str, Any]] = None
        self._current_workflow_yaml: Optional[str] = None
        self._dialogue_history: List[DialogueMessage] = []
        self._task_description: Optional[str] = None
        self._intent_sequence: Optional[List[Dict[str, Any]]] = None

        logger.info(f"WorkflowBuilderSession initialized: {self.session_id}")

    def _build_system_prompt(self) -> str:
        """Build system prompt (Skills provide detailed guidance)"""
        # Extended prompt for dialogue mode
        dialogue_additions = """

## Dialogue Mode

You are in an interactive dialogue session. After generating the initial workflow:
1. Answer user questions about the workflow
2. Explain specific steps or decisions
3. Modify the workflow based on user requests
4. Use validate-workflow Skill after modifications

When modifying the workflow:
- Output the complete updated YAML in a ```yaml code block
- Explain what changes were made
- Validate the changes using the validate-workflow Skill
"""
        return SYSTEM_PROMPT + dialogue_additions

    def _build_initial_prompt(
        self,
        task_description: str,
        intent_sequence: List[Dict[str, Any]],
        user_query: Optional[str] = None
    ) -> str:
        """Build initial prompt for workflow generation"""
        # Build intent data with full operations for Claude to understand user behavior
        enriched_intents = []
        for intent in intent_sequence:
            enriched = {
                "description": intent.get("description", ""),
                "intent_type": intent.get("intent_type", "unknown"),
            }

            # Include ALL operation details - let Claude decide what's important
            operations = intent.get("operations", [])
            if operations:
                op_details = []
                for op in operations:
                    op_type = op.get("type", "unknown")
                    url = op.get("url", "")
                    element = op.get("element", {})

                    detail = {"type": op_type}
                    if url:
                        detail["url"] = url
                    if element.get("textContent"):
                        # Truncate very long text but keep enough context
                        detail["text"] = element["textContent"][:200]
                    if element.get("href"):
                        detail["href"] = element["href"]
                    if element.get("xpath"):
                        detail["xpath"] = element["xpath"]
                    if element.get("tagName"):
                        detail["tagName"] = element["tagName"]
                    if element.get("id"):
                        detail["id"] = element["id"]
                    if element.get("className"):
                        detail["className"] = element["className"]

                    op_details.append(detail)

                enriched["operations"] = op_details
                enriched["operations_count"] = len(operations)

            enriched_intents.append(enriched)

        intents_yaml = yaml.dump(enriched_intents, allow_unicode=True, default_flow_style=False)

        # Build user query section if available
        user_query_section = ""
        if user_query:
            user_query_section = f"""
## User Query (IMPORTANT - User's Goal)
{user_query}

**Pay attention to:**
- If the user mentions "repeat", "loop", "all items", "top N", "each" → Use `foreach` to iterate
- If the user mentions a specific count (e.g., "10 products") → Use this as the iteration limit
- The user query describes the ACTUAL goal, not just what was recorded
"""

        return f"""Please generate a Workflow for the following task:

## Task Description
{task_description}
{user_query_section}
## User's Recorded Actions (Intent Operations)

Each operation contains details you need for optimization decisions (especially `href` for click-to-navigate):

```yaml
{intents_yaml}
```

## Your Task Checklist

Use TodoWrite to track these steps:

1. [ ] Read `workflow-generation` skill - understand workflow structure
2. [ ] Read `agent-specs` skill - understand agent input formats (especially browser_agent's interaction_steps)
3. [ ] Read `workflow-optimizations` skill - understand optimization patterns
4. [ ] Analyze each intent operation for optimization opportunities:
   - Click with `href` → Can optimize to `target_url`
   - Click without `href` → Must use `interaction_steps`
   - Consecutive scrolls → Combine or remove
5. [ ] Generate the optimized workflow YAML
6. [ ] Validate with `workflow-validation` skill
7. [ ] **Write the workflow to `workflow.yaml` file** (REQUIRED - use Write tool)
8. [ ] Output final YAML in code block and list optimizations applied

## Key Reminders

- `xpath_hints` must be **dict format**: `xpath_hints: {{key: "//xpath"}}` (NOT a list!)
- All click/fill/scroll MUST use `interaction_steps` (unless optimized to `target_url`)
- Document which operations were optimized and why
"""

    def _prepare_working_directory(self) -> Path:
        """Create a temporary working directory with Skills accessible"""
        work_dir = Path(tempfile.mkdtemp(prefix="workflow_builder_session_"))
        SkillManager.prepare_workflow_skills(work_dir)
        logger.info(f"[Session] Prepared workflow skills in {work_dir}")
        return work_dir

    def _extract_yaml_from_response(self, response: str) -> Optional[str]:
        """Extract YAML from Claude's response (fallback method)"""
        yaml_match = re.search(r'```yaml\s*\n(.*?)\n```', response, re.DOTALL)
        if yaml_match:
            return yaml_match.group(1).strip()

        code_match = re.search(r'```\s*\n(.*?)\n```', response, re.DOTALL)
        if code_match:
            content = code_match.group(1).strip()
            if content.startswith("apiVersion:") or content.startswith("kind:"):
                return content

        return None

    def _find_workflow_file(self) -> Optional[Path]:
        """
        Find the workflow YAML file generated by Claude Agent in session work_dir.
        """
        if not self._work_dir:
            return None

        # Common workflow file names (in order of priority)
        candidate_names = [
            "workflow.yaml",
            "workflow.yml",
            "generated_workflow.yaml",
            "output.yaml",
        ]

        for name in candidate_names:
            file_path = self._work_dir / name
            if file_path.exists():
                logger.info(f"[Session] Found workflow file: {file_path}")
                return file_path

        # Also search for any .yaml/.yml file in the directory
        yaml_files = list(self._work_dir.glob("*.yaml")) + list(self._work_dir.glob("*.yml"))
        if yaml_files:
            # Sort by modification time, newest first
            yaml_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            logger.info(f"[Session] Found workflow file by glob: {yaml_files[0]}")
            return yaml_files[0]

        return None

    def _read_workflow_from_file(self) -> Optional[str]:
        """
        Read workflow YAML content from file generated by Claude Agent.

        This is the preferred method as it reads exactly what Claude Agent wrote.
        """
        file_path = self._find_workflow_file()
        if file_path:
            try:
                content = file_path.read_text(encoding="utf-8")
                logger.info(f"[Session] Read workflow from file: {file_path} ({len(content)} chars)")
                return content
            except Exception as e:
                logger.error(f"[Session] Failed to read workflow file {file_path}: {e}")
        return None

    async def __aenter__(self) -> "WorkflowBuilderSession":
        """Enter async context - prepare session"""
        try:
            from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
        except ImportError:
            raise ImportError(
                "Ami Coder SDK not installed. Please install with: pip install claude-agent-sdk"
            )

        self._work_dir = self._prepare_working_directory()

        # Configure environment
        env_vars = dict(os.environ)
        env_vars["ANTHROPIC_API_KEY"] = self.api_key
        if self.base_url:
            env_vars["ANTHROPIC_BASE_URL"] = self.base_url

        # Configure agent options with Skills enabled
        options = ClaudeAgentOptions(
            model=self.model,
            cwd=str(self._work_dir),
            max_turns=self.max_iterations,
            allowed_tools=["Skill", "Read", "Write", "Bash", "Glob"],
            setting_sources=["project"],  # Load Skills from .claude/skills/
            permission_mode="bypassPermissions",
            system_prompt=self._build_system_prompt(),
            env=env_vars,
            max_buffer_size=1024 * 1024
        )

        # Create and connect client
        self._client = ClaudeSDKClient(options=options)
        await self._client.connect()

        self.state = SessionState.IDLE
        logger.info(f"Session {self.session_id} connected")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit async context - cleanup"""
        await self.close()
        return False

    async def close(self):
        """Close the session and cleanup resources"""
        if self._client:
            await self._client.disconnect()
            self._client = None

        if self._work_dir:
            import shutil
            try:
                shutil.rmtree(self._work_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup working directory: {e}")
            self._work_dir = None

        self.state = SessionState.CLOSED
        logger.info(f"Session {self.session_id} closed")

    async def generate(
        self,
        task_description: str,
        intent_sequence: List[Dict[str, Any]],
        on_progress: Optional[Callable[[StreamEvent], None]] = None,
        user_query: Optional[str] = None,
        dom_snapshots: Optional[Dict[str, Dict]] = None,
        workflow_dir: Optional[Path] = None
    ) -> GenerationResult:
        """
        Generate initial workflow from intents.

        Args:
            task_description: User's task description
            intent_sequence: List of Intent dictionaries
            on_progress: Optional callback for progress events
            user_query: User's goal/intent (e.g., "repeat for 10 items")
            dom_snapshots: Optional DOM snapshots for script generation
            workflow_dir: Optional directory to save scripts

        Returns:
            GenerationResult with workflow or error
        """
        if self.state == SessionState.CLOSED:
            return GenerationResult(success=False, error="Session is closed")

        if not self._client:
            return GenerationResult(success=False, error="Session not connected")

        self.state = SessionState.GENERATING
        self._task_description = task_description
        self._intent_sequence = intent_sequence
        self._user_query = user_query
        self._dom_snapshots = dom_snapshots
        self._workflow_dir = workflow_dir

        # Log inputs for debugging
        logger.info(f"🤖 [Session.generate] Starting workflow generation")
        logger.info(f"  📋 Task description: {task_description[:100]}...")
        logger.info(f"  🎯 User query: {user_query or '(not provided)'}")
        logger.info(f"  📊 Intent count: {len(intent_sequence)}")
        logger.info(f"  📁 Work dir: {self._work_dir}")
        logger.info(f"  📸 DOM snapshots: {len(dom_snapshots) if dom_snapshots else 0} URLs")
        logger.info(f"  📂 Workflow dir: {workflow_dir or '(not provided)'}")

        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ResultMessage,
                TextBlock,
                ToolUseBlock,
            )
        except ImportError:
            return GenerationResult(
                success=False,
                error="Ami Coder SDK not installed"
            )

        try:
            # Build and send initial prompt
            prompt = self._build_initial_prompt(task_description, intent_sequence, user_query)
            logger.info("🤖 [Session] Starting Claude Agent SDK workflow generation...")
            await self._client.query(prompt, session_id=self.session_id)
            logger.info("📤 [Session] Sent user prompt to Claude Agent")

            # Collect response
            final_response = ""
            turn_count = 0

            if on_progress:
                on_progress(StreamEvent(
                    type="progress",
                    message="Generating workflow...",
                    data={"progress": 10}
                ))

            async for message in self._client.receive_response():
                if isinstance(message, AssistantMessage):
                    turn_count += 1
                    logger.info(f"📨 [Session] Turn {turn_count}: Received AssistantMessage")
                    if hasattr(message, 'content'):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                # Log first 200 chars
                                preview = block.text[:200] + "..." if len(block.text) > 200 else block.text
                                logger.info(f"   📝 [Session] TextBlock: {preview}")
                                final_response += block.text + "\n"
                                if on_progress:
                                    progress = min(20 + turn_count * 10, 80)
                                    on_progress(StreamEvent(
                                        type="text",
                                        message=block.text[:200] + "..." if len(block.text) > 200 else block.text,
                                        data={"progress": progress}
                                    ))
                            elif isinstance(block, ToolUseBlock):
                                # Log tool name and input parameters for debugging
                                tool_input = getattr(block, 'input', {})
                                if block.name == "Bash":
                                    cmd = tool_input.get('command', '')[:200]
                                    logger.info(f"   🔧 [Session] ToolUse: Bash - {cmd}")
                                elif block.name == "Write":
                                    file_path = tool_input.get('file_path', '')
                                    content_len = len(tool_input.get('content', ''))
                                    logger.info(f"   🔧 [Session] ToolUse: Write - {file_path} ({content_len} chars)")
                                elif block.name == "Read":
                                    file_path = tool_input.get('file_path', '')
                                    logger.info(f"   🔧 [Session] ToolUse: Read - {file_path}")
                                elif block.name == "Edit":
                                    file_path = tool_input.get('file_path', '')
                                    logger.info(f"   🔧 [Session] ToolUse: Edit - {file_path}")
                                else:
                                    logger.info(f"   🔧 [Session] ToolUse: {block.name}")
                                if on_progress:
                                    on_progress(StreamEvent(
                                        type="tool_use",
                                        message=f"Using tool: {block.name}",
                                        data={"tool": block.name}
                                    ))

                if isinstance(message, ResultMessage):
                    logger.info(f"✅ [Session] ResultMessage: is_error={message.is_error}, num_turns={message.num_turns}")
                    if message.is_error:
                        logger.error(f"❌ [Session] Agent error: {message.result}")
                        self.state = SessionState.IDLE
                        return GenerationResult(
                            success=False,
                            error=message.result,
                            iterations=message.num_turns
                        )

            # Priority 1: Read workflow from file generated by Claude Agent
            yaml_content = self._read_workflow_from_file()

            # Priority 2: Fall back to extracting from response text
            if not yaml_content:
                logger.warning("[Session] No workflow file found, falling back to response extraction")
                yaml_content = self._extract_yaml_from_response(final_response)

            if not yaml_content:
                # Log for debugging
                logger.error(f"[Session] Failed to get YAML. No file found and response extraction failed.")
                logger.error(f"[Session] Response length: {len(final_response)}")
                logger.error(f"[Session] Response preview (first 500 chars): {final_response[:500]}")
                # List files in work_dir for debugging
                if self._work_dir:
                    try:
                        files = list(self._work_dir.iterdir())
                        logger.error(f"[Session] Files in work_dir: {[f.name for f in files]}")
                    except Exception:
                        pass
                self.state = SessionState.IDLE
                return GenerationResult(
                    success=False,
                    error="Failed to extract YAML: no workflow file found and response parsing failed",
                    iterations=turn_count
                )

            # Parse and validate
            try:
                workflow = yaml.safe_load(yaml_content)
            except yaml.YAMLError as e:
                logger.error(f"[Session] YAML parse error: {e}")
                logger.error(f"[Session] YAML content preview: {yaml_content[:500]}")
                self.state = SessionState.IDLE
                return GenerationResult(
                    success=False,
                    error=f"YAML parse error: {e}",
                    iterations=turn_count
                )

            validation = validate_workflow_dict(workflow)
            if not validation.valid:
                self.state = SessionState.IDLE
                return GenerationResult(
                    success=False,
                    workflow=workflow,
                    workflow_yaml=yaml_content,
                    error=f"Validation failed: {'; '.join(validation.errors)}",
                    iterations=turn_count
                )

            # Success - store workflow and transition to READY state
            self._current_workflow = workflow
            self._current_workflow_yaml = yaml_content
            self._dialogue_history.append(DialogueMessage(
                role="assistant",
                content=final_response,
                workflow_yaml=yaml_content
            ))

            self.state = SessionState.READY

            # Log output for debugging
            logger.info(f"✅ [Session.generate] Workflow generation successful")
            logger.info(f"  📄 Workflow name: {workflow.get('metadata', {}).get('name', 'unknown')}")
            logger.info(f"  📊 Steps count: {len(workflow.get('steps', []))}")
            logger.info(f"  📝 YAML size: {len(yaml_content)} chars")
            logger.info(f"  🔄 Iterations: {turn_count}")

            # Note: Script generation is now handled in main.py after workflow is saved
            # The dom_snapshots and workflow_dir parameters are kept for future use
            # or for cases where script generation needs to happen during generation
            script_generation_result = None

            if on_progress:
                on_progress(StreamEvent(
                    type="complete",
                    message="Workflow generated successfully",
                    data={"progress": 100}
                ))

            return GenerationResult(
                success=True,
                workflow=workflow,
                workflow_yaml=yaml_content,
                iterations=turn_count,
                session_id=self.session_id,
                script_generation=script_generation_result
            )

        except Exception as e:
            logger.error(f"Generation error: {e}")
            self.state = SessionState.IDLE
            return GenerationResult(
                success=False,
                error=str(e)
            )

    async def chat(
        self,
        user_message: str,
        on_progress: Optional[Callable[[StreamEvent], None]] = None
    ) -> DialogueMessage:
        """
        Send a follow-up message in the dialogue.

        The user can:
        - Ask questions about the workflow
        - Request modifications
        - Get explanations of specific steps

        Args:
            user_message: User's message
            on_progress: Optional callback for progress events

        Returns:
            DialogueMessage with assistant's response
        """
        if self.state != SessionState.READY:
            return DialogueMessage(
                role="assistant",
                content=f"Cannot chat in state {self.state.value}. Generate a workflow first."
            )

        if not self._client:
            return DialogueMessage(
                role="assistant",
                content="Session not connected"
            )

        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ResultMessage,
                TextBlock,
            )
        except ImportError:
            return DialogueMessage(
                role="assistant",
                content="Ami Coder SDK not installed"
            )

        # Record user message
        import time
        self._dialogue_history.append(DialogueMessage(
            role="user",
            content=user_message,
            timestamp=time.time()
        ))

        try:
            # Send follow-up message (same session maintains context)
            await self._client.query(user_message, session_id=self.session_id)

            # Collect response
            response_text = ""

            async for message in self._client.receive_response():
                if isinstance(message, AssistantMessage):
                    if hasattr(message, 'content'):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                response_text += block.text + "\n"
                                if on_progress:
                                    on_progress(StreamEvent(
                                        type="text",
                                        message=block.text[:200] + "..." if len(block.text) > 200 else block.text
                                    ))

                if isinstance(message, ResultMessage):
                    break

            # Check if Claude Agent wrote an updated workflow file
            # Priority 1: Read from file
            new_yaml = self._read_workflow_from_file()
            # Priority 2: Fall back to response text extraction
            if not new_yaml:
                new_yaml = self._extract_yaml_from_response(response_text)

            if new_yaml:
                try:
                    new_workflow = yaml.safe_load(new_yaml)
                    validation = validate_workflow_dict(new_workflow)
                    if validation.valid:
                        self._current_workflow = new_workflow
                        self._current_workflow_yaml = new_yaml
                        logger.info("Workflow updated via dialogue")
                except yaml.YAMLError as e:
                    logger.warning(f"Failed to parse updated workflow YAML: {e}")
                    pass  # Keep existing workflow if new YAML is invalid

            response = DialogueMessage(
                role="assistant",
                content=response_text.strip(),
                workflow_yaml=new_yaml,
                timestamp=time.time()
            )

            self._dialogue_history.append(response)
            return response

        except Exception as e:
            logger.error(f"Chat error: {e}")
            return DialogueMessage(
                role="assistant",
                content=f"Error: {str(e)}"
            )

    def get_current_workflow(self) -> Optional[Dict[str, Any]]:
        """Get the current workflow dictionary"""
        return self._current_workflow

    def get_current_workflow_yaml(self) -> Optional[str]:
        """Get the current workflow as YAML string"""
        return self._current_workflow_yaml

    def get_dialogue_history(self) -> List[DialogueMessage]:
        """Get the full dialogue history"""
        return self._dialogue_history.copy()

    def get_state(self) -> SessionState:
        """Get current session state"""
        return self.state

    def set_existing_workflow(self, workflow_yaml: str) -> bool:
        """
        Set an existing workflow for dialogue.

        This is used when creating a session for an existing Workflow
        (not freshly generated). The session transitions to READY state
        so that chat() can be called immediately.

        Args:
            workflow_yaml: YAML string of the existing workflow

        Returns:
            True if workflow was set successfully, False otherwise
        """
        try:
            workflow = yaml.safe_load(workflow_yaml)

            # Validate the workflow
            validation = validate_workflow_dict(workflow)
            if not validation.valid:
                logger.warning(f"Existing workflow has validation issues: {validation.errors}")
                # Still allow setting it - user may want to fix via dialogue

            # Set workflow data
            self._current_workflow = workflow
            self._current_workflow_yaml = workflow_yaml

            # Extract task description from metadata if available
            self._task_description = workflow.get("metadata", {}).get("name", "Existing workflow")

            # Add context message to help Claude understand
            context_message = f"""I'm working with an existing Workflow. Here is the current Workflow YAML:

```yaml
{workflow_yaml}
```

The user may ask questions about this workflow or request modifications.
When making modifications:
1. Output the complete updated YAML in a ```yaml code block
2. Explain what changes were made
3. Validate the changes

I'm ready to help with questions or modifications to this workflow."""

            # Send context to Claude (if client is connected)
            if self._client:
                # Queue the context message for the conversation
                import time
                self._dialogue_history.append(DialogueMessage(
                    role="assistant",
                    content=context_message,
                    workflow_yaml=workflow_yaml,
                    timestamp=time.time()
                ))

            # Transition to READY state
            self.state = SessionState.READY
            logger.info(f"Session {self.session_id} set with existing workflow, now READY for dialogue")

            return True

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse existing workflow YAML: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to set existing workflow: {e}")
            return False


class WorkflowModificationSession:
    """
    Session for modifying existing workflows via dialogue.

    Unlike WorkflowBuilderSession which generates from intents,
    this session takes an existing workflow and modifies it based on user requests.

    Can modify both:
    - workflow.yaml (workflow structure)
    - extraction_script.py (scraper scripts in step directories)

    Supports SSE streaming for real-time progress updates.

    Session workflow:
    1. Copy entire workflow directory to session directory
    2. User interacts with Claude to modify files
    3. After each chat, sync modified files back to original workflow
    4. On close, cleanup session directory

    Example:
        session = WorkflowModificationSession(
            workflow_yaml="...",
            user_id="user1",
            workflow_id="wf_123",
            storage_service=storage_service,
            api_key="..."
        )
        await session._connect()
        async for event in session.chat_stream("把第3步改成抓取更多字段"):
            print(event)
        await session._disconnect()
        session.cleanup()
    """

    def __init__(
        self,
        workflow_yaml: str,
        user_id: str,
        workflow_id: str,
        storage_service: "StorageService",
        config_service: Optional["ConfigService"] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_iterations: int = 100,
        session_id: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None
    ):
        """
        Initialize WorkflowModificationSession.

        Args:
            workflow_yaml: The existing workflow YAML to modify
            user_id: User ID for session storage
            workflow_id: Workflow ID to copy and modify
            storage_service: StorageService for session directory management
            config_service: ConfigService for reading configuration
            api_key: Anthropic API key
            model: Model to use (default: claude-sonnet-4-5)
            base_url: API proxy URL
            max_iterations: Max turns per request
            session_id: Optional session ID (auto-generated if not provided)
            chat_history: Optional chat history to restore context
                Format: [{"role": "user"|"assistant", "content": "..."}, ...]
        """
        self.workflow_yaml = workflow_yaml
        self.user_id = user_id
        self.workflow_id = workflow_id
        self.storage_service = storage_service
        self.chat_history = chat_history or []

        # Parse and validate the workflow
        try:
            self.workflow = yaml.safe_load(workflow_yaml)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid workflow YAML: {e}")

        # Get API key
        if api_key:
            self.api_key = api_key
        elif config_service:
            self.api_key = (
                config_service.get("claude_agent.api_key") or
                config_service.get("agent.llm.api_key") or
                os.environ.get("ANTHROPIC_API_KEY")
            )
        else:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError("Anthropic API key not found")

        # Get model
        if model:
            self.model = model
        elif config_service:
            self.model = config_service.get("claude_agent.model") or "claude-sonnet-4-5"
        else:
            self.model = "claude-sonnet-4-5"

        # Get base URL
        if base_url:
            self.base_url = base_url
        elif config_service:
            self.base_url = config_service.get("llm.proxy_url")
        else:
            self.base_url = None

        self.max_iterations = max_iterations
        self.session_id = session_id or f"mod_session_{id(self)}"

        # Session state
        self.state = SessionState.READY  # Start in READY since we have a workflow
        self._client = None
        self._work_dir: Optional[Path] = None
        self._initialized = False

        logger.info(f"WorkflowModificationSession initialized: {self.session_id}")
        logger.info(f"  User: {user_id}, Workflow: {workflow_id}")
        if self.chat_history:
            logger.info(f"  Chat history: {len(self.chat_history)} messages to restore")

    async def __aenter__(self):
        """Async context manager entry - connect to Claude Agent"""
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - disconnect from Claude Agent"""
        await self._disconnect()

    async def _connect(self):
        """Connect to Claude Agent with modification system prompt.

        Prepares session directory by copying workflow, then connects to Claude.
        The workflow.yaml is already in the session directory (copied by _prepare_working_directory).
        If chat_history is provided, injects it as context after connection.
        """
        logger.info(f"🔌 [_connect] Starting connection for session {self.session_id}")

        if self._initialized:
            logger.info(f"⏭️ [_connect] Already initialized, skipping")
            return

        try:
            from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
            logger.info(f"✅ [_connect] Claude Agent SDK imported successfully")
        except ImportError:
            logger.error(f"❌ [_connect] Claude Agent SDK not installed")
            raise RuntimeError("Ami Coder SDK not installed")

        # Prepare working directory - copies entire workflow to session directory
        self._work_dir = self._prepare_working_directory()
        logger.info(f"📁 [_connect] Work directory: {self._work_dir}")

        # workflow.yaml is already in the session directory (copied from original workflow)
        workflow_file = self._work_dir / "workflow.yaml"
        if workflow_file.exists():
            logger.info(f"📝 [_connect] Workflow file exists: {workflow_file}")
        else:
            logger.warning(f"⚠️ [_connect] Workflow file not found: {workflow_file}")

        # Build system prompt (include chat history context if available)
        system_prompt = self._build_system_prompt()
        logger.info(f"📋 [_connect] Built system prompt ({len(system_prompt)} chars)")

        # Configure Claude Agent
        logger.info(f"⚙️ [_connect] Configuring ClaudeAgentOptions...")
        logger.info(f"   Model: {self.model}")
        logger.info(f"   Max turns: {self.max_iterations}")
        logger.info(f"   Base URL: {self.base_url or '(default)'}")

        options = ClaudeAgentOptions(
            max_turns=self.max_iterations,
            permission_mode="bypassPermissions",
            cwd=str(self._work_dir),
            system_prompt=system_prompt,
            model=self.model,
        )

        # Set up API configuration
        if self.base_url:
            os.environ["ANTHROPIC_BASE_URL"] = self.base_url
        os.environ["ANTHROPIC_API_KEY"] = self.api_key

        # Create and connect client
        logger.info(f"🤖 [_connect] Creating ClaudeSDKClient...")
        self._client = ClaudeSDKClient(options=options)

        logger.info(f"🔗 [_connect] Calling client.connect()...")
        await self._client.connect()

        self._initialized = True
        logger.info(f"✅ [_connect] WorkflowModificationSession {self.session_id} connected successfully")

    async def _disconnect(self):
        """Disconnect from Claude Agent.

        Note: This only disconnects the Claude connection.
        Call cleanup() separately to remove the session directory.
        Sync happens in main.py after each chat, not here.
        """
        if self._client:
            await self._client.disconnect()
            self._client = None

        self._initialized = False
        self.state = SessionState.CLOSED
        logger.info(f"WorkflowModificationSession {self.session_id} disconnected")

    def cleanup(self):
        """Cleanup session directory.

        Should be called after _disconnect() when the session is no longer needed.
        """
        if self.storage_service and self.user_id and self.session_id:
            self.storage_service.cleanup_modification_session(
                user_id=self.user_id,
                session_id=self.session_id
            )
            logger.info(f"WorkflowModificationSession {self.session_id} cleaned up")

    def _prepare_working_directory(self) -> Path:
        """Prepare working directory by copying workflow to session directory.

        Uses storage_service to:
        1. Create session directory at ami-server/sessions/{user_id}/{session_id}/
        2. Copy entire workflow directory (including step subdirectories with scripts)
        3. Add modification skills for both workflow and script editing
        """
        # Copy workflow to session directory
        work_dir = self.storage_service.copy_workflow_to_session(
            user_id=self.user_id,
            workflow_id=self.workflow_id,
            session_id=self.session_id
        )

        # Add modification skills (includes workflow and dom-extraction skills)
        SkillManager.prepare_modification_skills(work_dir)

        logger.info(f"Prepared session directory: {work_dir}")
        return work_dir

    def _build_system_prompt(self) -> str:
        """Build system prompt for modification mode.

        The workflow.yaml is available in the working directory,
        so Claude can read it with the Read tool.
        If chat_history is provided, include it as context in the system prompt.

        Also generates pre-computed scraper context to avoid exploration overhead.
        """
        # Lazy import to avoid circular dependency
        from src.cloud_backend.intent_builder.services.scraper_context_service import (
            generate_scraper_context_markdown
        )

        base_prompt = MODIFICATION_SYSTEM_PROMPT

        # Generate scraper context (directory structure, requirements, script status)
        scraper_context = ""
        if self._work_dir and self._work_dir.exists():
            try:
                scraper_context = generate_scraper_context_markdown(
                    session_dir=self._work_dir,
                    workflow_yaml=self.workflow_yaml,
                    pre_run_scripts=True,  # Pre-run scripts to show current output
                    dom_snapshots=None  # Will use existing dom_data.json if available
                )
                logger.info(f"📊 [_build_system_prompt] Generated scraper context ({len(scraper_context)} chars)")
            except Exception as e:
                logger.warning(f"⚠️ [_build_system_prompt] Failed to generate scraper context: {e}")
                scraper_context = ""

        # Append scraper context if available
        if scraper_context:
            base_prompt += f"\n\n{scraper_context}"
        else:
            # Fallback to basic working directory info
            base_prompt += """

## Your Working Directory

The workflow and all its resources are in your current working directory.
- Read `workflow.yaml` to see the current workflow
- Browse step directories to find scraper scripts

The user will ask you to modify the workflow or fix extraction issues.
"""

        # If chat history is provided, append it as context
        if self.chat_history and len(self.chat_history) > 0:
            history_lines = [
                "",
                "## Previous Conversation Context",
                "",
                "This session was restored from a previous conversation. Here is the context:",
                ""
            ]

            for msg in self.chat_history:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                # Truncate very long messages to save context
                if len(content) > 500:
                    content = content[:500] + "... [truncated]"
                history_lines.append(f"**{role.upper()}**: {content}")
                history_lines.append("")

            history_lines.append("Continue helping the user based on this context.")
            base_prompt += "\n".join(history_lines)
            logger.info(f"📜 [_build_system_prompt] Added {len(self.chat_history)} messages to system prompt as context")

        return base_prompt

    async def chat_stream(
        self,
        user_message: str
    ) -> AsyncIterator[StreamEvent]:
        """
        Send a message and stream the response.

        Yields StreamEvent objects with:
        - type: "text" | "tool_use" | "workflow_updated" | "complete" | "error"
        - content/message: The content
        - workflow_yaml: Updated YAML (only for workflow_updated and complete)

        Args:
            user_message: User's modification request

        Yields:
            StreamEvent objects
        """
        logger.info(f"🔄 [chat_stream] Starting chat_stream for session {self.session_id}")
        logger.info(f"📝 [chat_stream] User message: {user_message[:100]}...")

        if not self._client:
            logger.error(f"❌ [chat_stream] Session not connected")
            yield StreamEvent(type="error", message="Session not connected")
            return

        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ResultMessage,
                UserMessage,
                TextBlock,
                ToolUseBlock,
                ToolResultBlock,
            )
        except ImportError:
            logger.error(f"❌ [chat_stream] Claude Agent SDK not installed")
            yield StreamEvent(type="error", message="Ami Coder SDK not installed")
            return

        try:
            # Send message to Claude
            logger.info(f"📤 [chat_stream] Sending query to Claude Agent...")
            await self._client.query(user_message, session_id=self.session_id)
            logger.info(f"✅ [chat_stream] Query sent successfully, waiting for response...")

            response_text = ""
            new_yaml = None
            message_count = 0

            # Stream response
            logger.info(f"🔄 [chat_stream] Starting to receive response stream...")
            async for message in self._client.receive_response():
                message_count += 1
                logger.info(f"📨 [chat_stream] Received message #{message_count}: {type(message).__name__}")

                if isinstance(message, AssistantMessage):
                    logger.info(f"📨 [chat_stream] AssistantMessage received")
                    if hasattr(message, 'content'):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                preview = block.text[:100] + "..." if len(block.text) > 100 else block.text
                                logger.info(f"   📝 [chat_stream] TextBlock: {preview}")
                                response_text += block.text + "\n"
                                yield StreamEvent(
                                    type="text",
                                    message=block.text
                                )
                            elif isinstance(block, ToolUseBlock):
                                # Log tool name and input parameters for debugging
                                tool_input = getattr(block, 'input', {})
                                if block.name == "Bash":
                                    cmd = tool_input.get('command', '')[:200]
                                    logger.info(f"   🔧 [chat_stream] ToolUseBlock: Bash - {cmd}")
                                elif block.name == "Write":
                                    file_path = tool_input.get('file_path', '')
                                    content_len = len(tool_input.get('content', ''))
                                    logger.info(f"   🔧 [chat_stream] ToolUseBlock: Write - {file_path} ({content_len} chars)")
                                elif block.name == "Read":
                                    file_path = tool_input.get('file_path', '')
                                    logger.info(f"   🔧 [chat_stream] ToolUseBlock: Read - {file_path}")
                                elif block.name == "Edit":
                                    file_path = tool_input.get('file_path', '')
                                    logger.info(f"   🔧 [chat_stream] ToolUseBlock: Edit - {file_path}")
                                else:
                                    logger.info(f"   🔧 [chat_stream] ToolUseBlock: {block.name}")
                                yield StreamEvent(
                                    type="tool_use",
                                    message=f"Using tool: {block.name}"
                                )

                if isinstance(message, UserMessage):
                    # Log tool results (UserMessage contains tool execution results)
                    if hasattr(message, 'content'):
                        for block in message.content:
                            if isinstance(block, ToolResultBlock):
                                tool_id = getattr(block, 'tool_use_id', '')[:8]
                                content = getattr(block, 'content', '')
                                # Truncate long output
                                if len(content) > 500:
                                    preview = content[:500] + f"... ({len(content)} chars total)"
                                else:
                                    preview = content
                                logger.info(f"   📋 [chat_stream] ToolResult [{tool_id}]: {preview}")

                if isinstance(message, ResultMessage):
                    logger.info(f"✅ [chat_stream] ResultMessage received, is_error={message.is_error}")
                    break

            logger.info(f"✅ [chat_stream] Response stream complete, total messages: {message_count}")

            # Check if Claude wrote to workflow.yaml file
            # Only detect actual file changes, don't extract from response text
            # (response text may contain yaml blocks that aren't workflow definitions)
            workflow_file = self._work_dir / "workflow.yaml"
            if workflow_file.exists():
                file_yaml = workflow_file.read_text()
                if file_yaml != self.workflow_yaml:
                    new_yaml = file_yaml
                    logger.info(f"📝 [chat_stream] Detected workflow.yaml change")

            # Validate and update if workflow.yaml was modified
            workflow_updated = False
            if new_yaml:
                try:
                    new_workflow = yaml.safe_load(new_yaml)
                    validation = validate_workflow_dict(new_workflow)
                    if validation.valid:
                        self.workflow = new_workflow
                        self.workflow_yaml = new_yaml
                        workflow_updated = True
                        yield StreamEvent(
                            type="workflow_updated",
                            message="Workflow updated",
                            workflow_yaml=new_yaml
                        )
                    else:
                        yield StreamEvent(
                            type="error",
                            message=f"Validation errors: {validation.errors}"
                        )
                except yaml.YAMLError as e:
                    yield StreamEvent(
                        type="error",
                        message=f"Invalid YAML: {e}"
                    )

            # Send complete event
            yield StreamEvent(
                type="complete",
                message=response_text.strip(),
                workflow_yaml=self.workflow_yaml if workflow_updated else None
            )

        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield StreamEvent(type="error", message=str(e))

    def get_current_workflow(self) -> Dict[str, Any]:
        """Get the current workflow dictionary"""
        return self.workflow

    def get_current_workflow_yaml(self) -> str:
        """Get the current workflow as YAML string"""
        return self.workflow_yaml
