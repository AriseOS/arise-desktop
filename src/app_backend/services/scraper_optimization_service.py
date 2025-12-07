"""
Scraper Optimization Service
Provides conversation-based script optimization using Claude Agent
"""
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class ScraperOptimizationService:
    """Service for optimizing scraper scripts through AI conversation"""

    def __init__(self, config_service):
        """Initialize service with config

        Args:
            config_service: Configuration service instance
        """
        self.config_service = config_service

    def _generate_url_hash(self, url: str) -> str:
        """Generate hash for URL

        Args:
            url: The webpage URL

        Returns:
            8-character hash string
        """
        return hashlib.md5(url.encode()).hexdigest()[:8]

    def get_script_workspace(self, user_id: str, workflow_id: str, step_id: str) -> Optional[Path]:
        """Get script workspace path for a specific workflow step

        Args:
            user_id: User ID
            workflow_id: Workflow ID
            step_id: Step ID

        Returns:
            Path to script workspace, or None if not found
        """
        # Build path: data.scripts/users/{user_id}/workflows/{workflow_id}/{step_id}/
        scripts_root = self.config_service.get_path("data.scripts")
        step_dir = scripts_root / f"users/{user_id}/workflows/{workflow_id}/{step_id}"

        if not step_dir.exists():
            logger.warning(f"Step directory not found: {step_dir}")
            return None

        # Find scraper_script_* directory
        script_dirs = list(step_dir.glob("scraper_script_*"))

        if not script_dirs:
            logger.warning(f"No scraper script found in: {step_dir}")
            return None

        # Return the first one (or most recently modified)
        workspace = sorted(script_dirs, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        logger.info(f"Found script workspace: {workspace}")
        return workspace

    def load_workspace_context(self, workspace: Path) -> Dict[str, Any]:
        """Load context from script workspace

        Args:
            workspace: Path to script workspace

        Returns:
            Dictionary with workspace context:
                - script_path: Path to workspace
                - requirement: Data requirements
                - script_content: Current script content
                - has_script: Whether script exists
                - cached_urls: List of URLs with cached DOM snapshots
        """
        requirement_file = workspace / "requirement.json"
        script_file = workspace / "extraction_script.py"
        url_index_file = workspace / "dom_snapshots" / "url_index.json"

        requirement = None
        if requirement_file.exists():
            try:
                requirement = json.loads(requirement_file.read_text(encoding='utf-8'))
            except Exception as e:
                logger.warning(f"Failed to load requirement.json: {e}")

        script_content = None
        has_script = False
        if script_file.exists():
            try:
                script_content = script_file.read_text(encoding='utf-8')
                has_script = True
            except Exception as e:
                logger.warning(f"Failed to load extraction_script.py: {e}")

        # Load cached URLs from url_index.json
        cached_urls = []
        if url_index_file.exists():
            try:
                url_index = json.loads(url_index_file.read_text(encoding='utf-8'))
                # Convert to list of {url, hash, timestamp}
                cached_urls = [
                    {
                        "url": url,
                        "hash": data.get("hash"),
                        "timestamp": data.get("timestamp")
                    }
                    for url, data in url_index.items()
                ]
                logger.info(f"Found {len(cached_urls)} cached DOM URLs")
            except Exception as e:
                logger.warning(f"Failed to load url_index.json: {e}")

        return {
            "script_path": str(workspace),
            "requirement": requirement,
            "script_content": script_content,
            "has_script": has_script,
            "cached_urls": cached_urls
        }

    def check_dom_availability(self, url: str) -> Dict[str, Any]:
        """Check if DOM snapshot exists for a URL

        Args:
            url: The webpage URL

        Returns:
            Dictionary with:
                - available: bool
                - url: original URL
                - url_hash: hash of URL
                - timestamp: when DOM was saved
                - snapshot_path: path to snapshot (if available)
        """
        url_hash = self._generate_url_hash(url)
        dom_snapshots_root = self.config_service.get_path("data.root") / "dom_snapshots"
        snapshot_dir = dom_snapshots_root / url_hash

        if not snapshot_dir.exists():
            return {
                "available": False,
                "url": url,
                "url_hash": url_hash
            }

        dom_file = snapshot_dir / "dom_data.json"
        metadata_file = snapshot_dir / "metadata.json"

        if not dom_file.exists():
            return {
                "available": False,
                "url": url,
                "url_hash": url_hash
            }

        # Load metadata
        metadata = {}
        if metadata_file.exists():
            try:
                metadata = json.loads(metadata_file.read_text(encoding='utf-8'))
            except Exception as e:
                logger.warning(f"Failed to load metadata: {e}")

        return {
            "available": True,
            "url": url,
            "url_hash": url_hash,
            "timestamp": metadata.get("timestamp", "unknown"),
            "snapshot_path": str(snapshot_dir)
        }

    async def chat_with_claude(
        self,
        workspace: Path,
        user_message: str,
        conversation_history: List[Dict] = None,
        user_api_key: str = None
    ) -> Dict[str, Any]:
        """Chat with Claude Agent about script optimization

        This method:
        1. Extracts URL from user message (if mentioned)
        2. Checks if DOM exists for that URL
        3. Calls Claude Agent with appropriate context
        4. Claude can modify the script
        5. Returns Claude's response

        Args:
            workspace: Script workspace path
            user_message: User's message
            conversation_history: Previous conversation (optional)
            user_api_key: User's Anthropic API key

        Returns:
            Dictionary with:
                - response: Claude's response
                - success: Whether task succeeded
                - error: Error message (if failed)
        """
        from src.common.llm import ClaudeAgentProvider

        try:
            # Build conversation history text
            history_text = ""
            if conversation_history:
                for msg in conversation_history[-5:]:  # Last 5 messages
                    role = "User" if msg['role'] == 'user' else "Claude"
                    history_text += f"{role}: {msg['content']}\n\n"

            # Build prompt for Claude Agent
            prompt = f"""# Scraper Script Optimization Assistant

## Working Directory
You are in: `{workspace}`

## Available Files in Workspace
- `extraction_script.py` - Current extraction script (you can modify this)
- `requirement.json` - Data extraction requirements
- `dom_data.json` - DOM used when generating the script originally
- `dom_snapshots/url_index.json` - Index mapping URLs to their DOM snapshots
- `dom_snapshots/{{url_hash}}/dom_data.json` - DOM snapshots for specific URLs

## How to Find DOM for a Specific URL

When user mentions a URL they want to optimize for:

1. **Read the URL index**:
   ```bash
   cat dom_snapshots/url_index.json
   ```
   This file maps URLs to their hash directories.

   Example structure:
   ```json
   {{
     "https://example.com/page1": {{"hash": "2abaa84e", "timestamp": "..."}},
     "https://example.com/page2": {{"hash": "8a88f18c", "timestamp": "..."}}
   }}
   ```

2. **Find the URL's hash**:
   - Look up the user's URL in the JSON you just read
   - Extract the `hash` value for that URL
   - If URL not found, tell user: "I don't have a DOM snapshot for this URL. Please run a scrape on this URL first."

3. **Read the DOM snapshot**:
   ```bash
   cat dom_snapshots/[hash]/dom_data.json
   ```
   Replace `[hash]` with the actual hash value from step 2.

4. **Analyze and fix**:
   - Use the DOM data to analyze why extraction is failing
   - Compare with `requirement.json` to see what fields are needed
   - Modify `extraction_script.py` to fix the issues

**IMPORTANT**: Do NOT try to calculate the URL hash yourself. Always read `url_index.json` first to get the hash.

## Your Task
Help the user optimize their scraper script through conversation.

- Answer questions about the script
- When user mentions a URL, find its DOM using the url_index.json
- Analyze why extraction might be failing by comparing DOM with requirements
- Modify `extraction_script.py` to fix issues
- Explain your changes clearly
- Be conversational and helpful

## Conversation History
{history_text}

## User's Message
{user_message}

## Response Instructions
1. If user mentions a URL:
   - First read `dom_snapshots/url_index.json` to find the hash
   - If found, read `dom_snapshots/{{hash}}/dom_data.json`
   - Use the DOM to help debug/optimize the script
2. If you modify the script, explain what you changed and why
3. Be conversational and encourage the user to test the changes

Please respond to the user now.
"""

            # Use user's API key (passed from request header)
            api_key = user_api_key

            if not api_key:
                logger.error("No API key available for Claude Agent")
                return {
                    "response": "Error: No Anthropic API key available. Please provide your API key.",
                    "success": False,
                    "error": "Missing API key"
                }

            # Read base_url and model from config (same as workflow_executor)
            base_url = self.config_service.get('llm.proxy_url', 'https://api.ariseos.com')
            model = self.config_service.get('llm.model', 'claude-sonnet-4-5-20250929')

            logger.info(f"Using API key for Claude Agent: {api_key[:10]}...")
            logger.info(f"Using base_url: {base_url}")
            logger.info(f"Using model: {model}")

            # Initialize Claude Agent Provider (same pattern as scraper_agent)
            claude_provider = ClaudeAgentProvider(
                config_service=self.config_service,
                api_key=api_key,
                base_url=base_url,
                model=model
            )

            # Get max iterations from config
            max_iterations = self.config_service.get("claude_agent.default_max_iterations", 30)

            logger.info(f"Starting Claude Agent conversation (max_iterations={max_iterations})")
            logger.info(f"User message: {user_message}")

            # Run Claude Agent task
            result = await claude_provider.run_task(
                prompt=prompt,
                working_dir=workspace,
                max_iterations=max_iterations
            )

            if result.success:
                logger.info(f"Claude Agent completed in {result.iterations} iterations")

                # Read the updated script to show what changed
                script_file = workspace / "extraction_script.py"
                updated_script = ""
                if script_file.exists():
                    try:
                        updated_script = script_file.read_text(encoding='utf-8')
                    except Exception as e:
                        logger.warning(f"Failed to read updated script: {e}")

                response_text = f"I've analyzed the URL and updated the extraction script.\n\n"
                response_text += f"Completed in {result.iterations} iterations.\n\n"
                response_text += f"You can now test the updated script by running a scrape."

                return {
                    "response": response_text,
                    "success": True,
                    "iterations": result.iterations
                }
            else:
                logger.warning(f"Claude Agent task failed: {result.error}")
                return {
                    "response": f"I encountered an error: {result.error}\n\nPlease try again or provide more details.",
                    "success": False,
                    "error": result.error
                }

        except Exception as e:
            logger.error(f"Chat with Claude failed: {e}", exc_info=True)
            return {
                "response": f"An error occurred: {str(e)}",
                "success": False,
                "error": str(e)
            }
