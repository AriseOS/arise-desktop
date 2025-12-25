"""
Conversation Skill Handler

Handles user feedback through Claude Agent SDK with skill system.
Claude autonomously decides which skills to use based on skill descriptions.
"""

import os
import logging
import re
from pathlib import Path
from typing import Dict, AsyncGenerator, Optional, List
import yaml

from src.common.llm.claude_agent_provider import ClaudeAgentProvider

logger = logging.getLogger(__name__)


class ConversationSkillHandler:
    """
    Handler for conversation-based workflow feedback using Claude Skills

    This handler:
    1. Loads skill descriptions from .md files
    2. Passes user feedback + workflow context + skills to Claude
    3. Lets Claude autonomously decide whether to use skills or just respond
    4. Streams Claude's work in real-time
    """

    def __init__(self, config_service=None):
        """
        Initialize Conversation Skill Handler

        Args:
            config_service: Optional config service for LLM configuration
        """
        self.config_service = config_service
        # Skills are now loaded by Claude Agent SDK from .claude/skills/
        # No need to manually scan and load them

    def _parse_skill_frontmatter(self, skill_md_path: Path) -> Optional[Dict]:
        """
        Parse YAML frontmatter from SKILL.md file

        Args:
            skill_md_path: Path to SKILL.md file

        Returns:
            Dict with 'name', 'description', and 'skill_dir' keys, or None if parsing fails
        """
        try:
            with open(skill_md_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Match YAML frontmatter pattern: ---\n...\n---
            match = re.match(r'^---\s*\n(.*?\n)---\s*\n', content, re.DOTALL)
            if not match:
                logger.error(f"No YAML frontmatter found in {skill_md_path}")
                return None

            frontmatter_yaml = match.group(1)
            frontmatter = yaml.safe_load(frontmatter_yaml)

            if not isinstance(frontmatter, dict):
                logger.error(f"Invalid frontmatter format in {skill_md_path}")
                return None

            # Validate required fields
            if 'name' not in frontmatter or 'description' not in frontmatter:
                logger.error(f"Missing required fields (name, description) in {skill_md_path}")
                return None

            return {
                'name': frontmatter['name'],
                'description': frontmatter['description'],
                'skill_dir': skill_md_path.parent
            }

        except Exception as e:
            logger.error(f"Failed to parse frontmatter from {skill_md_path}: {e}")
            return None

    def _load_skills(self) -> List[Dict]:
        """
        Load skills from skill directories

        Scans the skills directory for subdirectories containing SKILL.md files.
        Parses the YAML frontmatter to extract name and description.

        Returns:
            List of skill metadata dictionaries with keys: name, description, skill_dir
        """
        skills = []

        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return skills

        # Scan for skill directories (directories containing SKILL.md)
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            # Skip special directories
            if skill_dir.name.startswith('.') or skill_dir.name in ['__pycache__', 'definitions', 'tools', 'skill_tools']:
                continue

            skill_md_path = skill_dir / "SKILL.md"
            if not skill_md_path.exists():
                logger.warning(f"No SKILL.md found in {skill_dir}, skipping")
                continue

            # Parse frontmatter
            skill_metadata = self._parse_skill_frontmatter(skill_md_path)
            if skill_metadata:
                skills.append(skill_metadata)
                logger.info(f"Loaded skill: {skill_metadata['name']} from {skill_dir}")

        return skills

    def _build_conversation_prompt(
        self,
        user_message: str,
        workflow_context: Dict
    ) -> str:
        """
        Build prompt for Claude with user feedback and workflow context

        Skills are automatically discovered by Claude Agent SDK from .claude/skills/
        No need to manually list skills in the prompt.

        Args:
            user_message: User's feedback message
            workflow_context: Workflow execution context

        Returns:
            Formatted prompt for Claude Agent
        """
        # Extract workflow information
        workflow_result = workflow_context.get('workflow_result', {})
        workflow_yaml = workflow_result.get('workflow_yaml', '')
        workflow_name = workflow_result.get('workflow_name', 'Unknown Workflow')
        steps = workflow_result.get('steps', [])

        # Build simplified prompt - let Claude autonomously discover and use skills
        prompt = f"""# Workflow Feedback Assistant

You are an intelligent assistant helping users debug and optimize their workflows.

## Your Working Directory

You have access to these files:
- `workflow.yaml` - Full workflow configuration
- `workflow_context.json` - Workflow metadata (user_id, workflow_id, steps)

## User's Feedback

{user_message}

## Current Workflow

**Name**: {workflow_name}
**Steps**: {len(steps)} steps

### Quick Overview
```yaml
{workflow_yaml[:1000]}{'...' if len(workflow_yaml) > 1000 else ''}
```

**Read `workflow.yaml` for complete details**

### Steps Summary
"""

        # Add steps summary
        for i, step in enumerate(steps[:10]):
            step_name = step.get('name', 'Unknown')
            step_type = step.get('type', 'unknown')
            step_id = step.get('id', 'unknown')
            prompt += f"\n{i+1}. **{step_name}** (type: `{step_type}`, id: `{step_id}`)"

        if len(steps) > 10:
            prompt += f"\n... and {len(steps) - 10} more steps"

        # Simple task description - let Claude autonomously use skills
        prompt += f"""

---

## YOUR TASK

User's feedback: "{user_message}"

Please analyze the feedback and help resolve the workflow issue. You have access to specialized skills that can help with specific problems - use them if appropriate.

BEGIN NOW.
"""

        return prompt

    async def handle_feedback(
        self,
        user_message: str,
        workflow_context: Dict,
        api_key: Optional[str] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Handle user feedback using Claude Agent SDK with skills

        Args:
            user_message: User's feedback message
            workflow_context: Workflow execution context
            api_key: Optional user API key

        Yields:
            {
                'type': 'thinking' | 'analyzing' | 'tool_use' | 'result' | 'error',
                'content': str,
                'update_id': str,  # For dynamic UI updates
                'turn': int
            }
        """
        import shutil
        import tempfile

        temp_workspace = None

        try:
            # Create update_id for all progress messages
            progress_update_id = f"conversation_{id(self)}"

            # Step 1: Prepare working directory with tools and workflow context
            yield {
                'type': 'thinking',
                'content': 'Preparing workspace...',
                'update_id': progress_update_id
            }

            # Create temporary workspace
            temp_workspace = Path(tempfile.mkdtemp(prefix="conversation_skill_"))

            # Save workflow YAML to file for Claude to read
            workflow_result = workflow_context.get('workflow_result', {})
            workflow_yaml = workflow_result.get('workflow_yaml', '')
            if workflow_yaml:
                workflow_file = temp_workspace / "workflow.yaml"
                workflow_file.write_text(workflow_yaml, encoding='utf-8')
                logger.info(f"Saved workflow YAML to {workflow_file}")

            # Save workflow context as JSON for reference
            context_file = temp_workspace / "workflow_context.json"
            import json
            context_data = {
                'user_id': workflow_context.get('user_id'),
                'workflow_id': workflow_context.get('workflow_id'),
                'workflow_name': workflow_result.get('workflow_name'),
                'steps': workflow_result.get('steps', [])
            }
            # Include API key if available (for skill tools to use)
            if api_key:
                context_data['api_key'] = api_key
            context_file.write_text(json.dumps(context_data, indent=2, ensure_ascii=False), encoding='utf-8')

            # Copy skills to .claude/skills/ structure for SDK auto-discovery
            claude_skills_dir = temp_workspace / ".claude" / "skills"
            claude_skills_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Created SDK skills directory: {claude_skills_dir}")

            # Copy skills from src/app_backend/services/skills/ to .claude/skills/
            source_skills_dir = Path(__file__).parent / "skills"
            skill_count = 0
            if source_skills_dir.exists():
                for skill_dir in source_skills_dir.iterdir():
                    if skill_dir.is_dir() and not skill_dir.name.startswith('.'):
                        # Skip __pycache__ and other special directories
                        if skill_dir.name in ['__pycache__']:
                            continue

                        dest_skill_dir = claude_skills_dir / skill_dir.name
                        shutil.copytree(skill_dir, dest_skill_dir)
                        skill_count += 1
                        logger.info(f"✅ Copied skill '{skill_dir.name}' to {dest_skill_dir}")

                        # Log SKILL.md existence
                        skill_md = dest_skill_dir / "SKILL.md"
                        if skill_md.exists():
                            logger.info(f"   ✓ SKILL.md found: {skill_md}")
                        else:
                            logger.warning(f"   ⚠️  SKILL.md missing in {skill_dir.name}")

                logger.info(f"🎯 Total skills copied: {skill_count}")
            else:
                logger.warning(f"⚠️  Skills directory not found: {source_skills_dir}")

            # Step 2: Build prompt
            yield {
                'type': 'thinking',
                'content': 'Understanding your feedback...',
                'update_id': progress_update_id
            }

            prompt = self._build_conversation_prompt(user_message, workflow_context)

            # Step 3: Initialize Claude Agent Provider
            claude_agent = ClaudeAgentProvider(
                api_key=api_key,
                config_service=self.config_service
            )

            # Step 4: Execute with Claude Agent (streaming)
            max_iterations = 50  # Increased for skill execution with final summary generation
            task_completed = False
            task_error = None
            final_turn = 0
            last_text_content = None  # Track the last text message
            last_text_turn = 0
            skill_usage_detected = False  # Track if Skill tool was used

            logger.info("=" * 80)
            logger.info("🚀 Starting Claude Agent SDK with Skills Enabled")
            logger.info(f"   Working Directory: {temp_workspace}")
            logger.info(f"   Skills Directory: {temp_workspace}/.claude/skills/")
            logger.info(f"   Max Iterations: {max_iterations}")
            logger.info(f"   Tools: Read, Bash, Edit, Skill")
            logger.info(f"   User Message: {user_message}")
            logger.info("=" * 80)

            try:
                # Stream Claude Agent execution with skills enabled
                async for event in claude_agent.run_task_stream(
                    prompt=prompt,
                    working_dir=temp_workspace,  # Use temp workspace with .claude/skills/
                    max_iterations=max_iterations,
                    tools=["Read", "Bash", "Edit"],  # Base tools
                    enable_skills=True  # Enable SDK skills auto-discovery
                ):
                    # Forward streaming events to frontend
                    if event.type == "text":
                        # Store the last text message
                        last_text_content = event.content
                        last_text_turn = event.turn

                        # Send as progress message with update_id (will be replaced by next message)
                        yield {
                            'type': 'analyzing',
                            'content': f'💭 {event.content}',
                            'update_id': progress_update_id,
                            'turn': event.turn
                        }
                    elif event.type == "tool_use":
                        # Build tool description with parameters
                        tool_desc = f"🔧 Using {event.tool_name}"

                        # Add specific parameter info for key tools
                        if event.tool_name == "Bash" and event.tool_input and 'command' in event.tool_input:
                            cmd = event.tool_input['command']
                            # Truncate very long commands
                            if len(cmd) > 200:
                                cmd_preview = cmd[:200] + "..."
                            else:
                                cmd_preview = cmd
                            tool_desc = f"🔧 Bash: {cmd_preview}"
                        elif event.tool_name == "Read" and event.tool_input and 'file_path' in event.tool_input:
                            tool_desc = f"🔧 Read: {event.tool_input['file_path']}"
                        elif event.tool_name == "Edit" and event.tool_input and 'file_path' in event.tool_input:
                            tool_desc = f"🔧 Edit: {event.tool_input['file_path']}"
                        elif event.tool_name == "Skill":
                            # Track Skill tool usage
                            skill_usage_detected = True
                            skill_name = event.tool_input.get('skill_name', 'unknown') if event.tool_input else 'unknown'
                            logger.info("=" * 80)
                            logger.info(f"🎯 SKILL TOOL DETECTED!")
                            logger.info(f"   Skill Name: {skill_name}")
                            logger.info(f"   Turn: {event.turn}")
                            logger.info(f"   Input: {event.tool_input}")
                            logger.info("=" * 80)
                            tool_desc = f"🎯 Skill: {skill_name}"

                        yield {
                            'type': 'analyzing',
                            'content': f'{tool_desc} (turn {event.turn})',
                            'update_id': progress_update_id,
                            'turn': event.turn,
                            'tool_name': event.tool_name
                        }
                    elif event.type == "thinking":
                        yield {
                            'type': 'analyzing',
                            'content': f'💭 {event.content}',
                            'update_id': progress_update_id,
                            'turn': event.turn or 0
                        }
                    elif event.type == "complete":
                        task_completed = True
                        final_turn = event.turn or 0
                        logger.info(f"✅ Conversation completed: {event.content}")
                    elif event.type == "error":
                        task_error = event.content
                        final_turn = event.turn or 0
                        logger.error(f"❌ Conversation error: {event.content}")

                    # Track final turn
                    if event.turn:
                        final_turn = event.turn

            except Exception as e:
                task_error = str(e)
                logger.error(f"Error during Claude Agent streaming: {e}", exc_info=True)

            # Step 4: Report result
            logger.info("=" * 80)
            logger.info("📊 Execution Summary")
            logger.info(f"   Task Completed: {task_completed}")
            logger.info(f"   Task Error: {task_error}")
            logger.info(f"   Total Turns: {final_turn}")
            logger.info(f"   Skill Tool Used: {skill_usage_detected}")
            if skill_usage_detected:
                logger.info("   ✅ Claude autonomously used SDK Skills!")
            else:
                logger.info("   ⚠️  No Skill tool usage detected (Claude may have solved it directly)")
            logger.info("=" * 80)

            if task_error:
                yield {
                    'type': 'error',
                    'content': f'Failed to process feedback: {task_error}\n\nPlease try rephrasing your feedback or provide more details.'
                }
            elif task_completed:
                # Send the last text message as final result
                if last_text_content:
                    yield {
                        'type': 'result',
                        'content': last_text_content,
                        'turn': last_text_turn
                    }
                else:
                    # No text content, send simple completion message
                    yield {
                        'type': 'result',
                        'content': f'✓ Response completed (processed in {final_turn} turns).'
                    }
            else:
                yield {
                    'type': 'error',
                    'content': f'Response did not complete properly.\n\nPlease try again with more specific feedback.'
                }

        except Exception as e:
            logger.error(f"Error in conversation skill handler: {e}", exc_info=True)
            yield {
                'type': 'error',
                'content': f'Unexpected error: {str(e)}'
            }
        finally:
            # Clean up temporary workspace
            if temp_workspace and temp_workspace.exists():
                try:
                    import shutil
                    shutil.rmtree(temp_workspace)
                    logger.info(f"Cleaned up temporary workspace: {temp_workspace}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up workspace: {cleanup_error}")
