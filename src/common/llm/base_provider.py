"""
Base LLM Provider abstract class
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import json
import logging
import re
from dataclasses import dataclass

try:
    from json_repair import repair_json
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False

logger = logging.getLogger(__name__)


# =============================================================================
# Public JSON Parsing Utilities
# =============================================================================

def extract_json_from_markdown(text: str) -> str:
    """
    Extract JSON content from markdown code blocks.

    Args:
        text: Raw text that may contain ```json...``` blocks

    Returns:
        Extracted JSON content or original text
    """
    text = text.strip()

    # Check for ```json code block
    if "```json" in text:
        match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
        if match:
            return match.group(1).strip()

    # Check for generic ``` code block
    if "```" in text:
        match = re.search(r'```\s*([\s\S]*?)\s*```', text)
        if match:
            return match.group(1).strip()

    # Try to find JSON object in text
    if not text.startswith('{') and not text.startswith('['):
        match = re.search(r'[\{\[][\s\S]*[\}\]]', text)
        if match:
            return match.group(0)

    return text


def parse_json_with_repair(raw_response: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM output with automatic repair.

    Strategy:
    1. Extract JSON from markdown code blocks if present
    2. Try direct JSON parsing
    3. Try json-repair library if available
    4. Fallback to raw text wrapped in {"answer": ...}

    Args:
        raw_response: Raw text response from LLM

    Returns:
        Parsed JSON dict
    """
    logger.debug(f"Parsing JSON from LLM response (first 200 chars): {raw_response[:200]}")

    try:
        # Step 1: Extract JSON content from markdown code blocks
        json_content = extract_json_from_markdown(raw_response)

        # Step 2: Try direct parsing
        try:
            parsed_data = json.loads(json_content)
            if isinstance(parsed_data, dict):
                logger.info("JSON parsed successfully")
                return parsed_data
            else:
                return {"answer": parsed_data}
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing failed: {str(e)}")

            # Step 3: Try json-repair library
            if HAS_JSON_REPAIR:
                try:
                    logger.info("Attempting JSON repair...")
                    repaired = repair_json(json_content)
                    parsed_data = json.loads(repaired)
                    if isinstance(parsed_data, dict):
                        logger.info("JSON repaired successfully")
                        return parsed_data
                    else:
                        return {"answer": parsed_data}
                except Exception as repair_error:
                    logger.warning(f"json-repair failed: {str(repair_error)}")
            else:
                logger.warning("json-repair library not installed, skipping repair")

            # Step 4: Fallback to raw text
            logger.warning("All JSON parsing attempts failed, returning raw text")
            return {"answer": raw_response.strip()}

    except Exception as e:
        logger.error(f"Unexpected error during JSON parsing: {str(e)}")
        return {"answer": raw_response.strip()}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ToolUseBlock:
    """Represents a tool use request from the LLM."""
    id: str
    name: str
    input: Dict[str, Any]
    type: str = "tool_use"


@dataclass
class TextBlock:
    """Represents a text block from the LLM."""
    text: str
    type: str = "text"


@dataclass
class ToolResultBlock:
    """Represents a tool result to send back to the LLM."""
    tool_use_id: str
    content: str
    type: str = "tool_result"


@dataclass
class ToolCallResponse:
    """Response from generate_with_tools() containing content blocks and stop reason."""
    content: List[Any]  # List of TextBlock or ToolUseBlock
    stop_reason: str  # "end_turn", "tool_use", "max_tokens", etc.

    def get_tool_uses(self) -> List[ToolUseBlock]:
        """Extract all tool use blocks from content."""
        return [block for block in self.content if isinstance(block, ToolUseBlock)]

    def get_text(self) -> str:
        """Extract all text content concatenated."""
        texts = [block.text for block in self.content if isinstance(block, TextBlock)]
        return "\n".join(texts) if texts else ""

    def has_tool_use(self) -> bool:
        """Check if response contains tool use requests."""
        return self.stop_reason == "tool_use" or any(
            isinstance(block, ToolUseBlock) for block in self.content
        )


class BaseProvider(ABC):
    """
    Abstract base class for LLM providers
    """
    
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize the provider
        
        Args:
            api_key: API key for the service
            model_name: Default model name to use
        """
        self.api_key = api_key
        self.model_name = model_name
        self._client = None
    
    @abstractmethod
    async def _initialize_client(self) -> None:
        """
        Initialize the specific SDK client
        Should be implemented by each provider
        """
        pass
    
    @abstractmethod
    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> str:
        """
        Generate a response using the LLM
        
        Args:
            system_prompt: System instruction for the LLM
            user_prompt: User's input prompt
            
        Returns:
            Generated response text
        """
        pass
    
    def get_model_name(self) -> Optional[str]:
        """Get the current model name"""
        return self.model_name

    def set_model_name(self, model_name: str) -> None:
        """Set the model name"""
        self.model_name = model_name

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_tokens: int = 4096,
    ) -> ToolCallResponse:
        """
        Generate a response with tool calling support.

        This method supports multi-turn tool calling conversations.
        Override this method in subclasses to provide tool calling support.

        Args:
            system_prompt: System instruction for the LLM
            messages: Conversation messages in provider-specific format
            tools: List of tool definitions in provider-specific format
            max_tokens: Maximum tokens in response

        Returns:
            ToolCallResponse containing content blocks and stop reason

        Raises:
            NotImplementedError: If the provider doesn't support tool calling
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support tool calling. "
            "Override generate_with_tools() to add support."
        )

    async def generate_json_response(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a JSON response using the LLM with automatic repair

        This method implements a 3-step strategy:
        1. Strong JSON constraints in prompts
        2. Automatic JSON repair using json-repair library
        3. Graceful fallback to raw text

        Args:
            system_prompt: System instruction for the LLM
            user_prompt: User's input prompt (should include JSON format requirements)
            json_schema: Optional JSON schema for validation (not yet implemented)

        Returns:
            Parsed JSON dict or {"answer": raw_response} on failure
        """
        # Add strong JSON constraints to system prompt
        enhanced_system_prompt = f"""{system_prompt}

IMPORTANT JSON FORMAT REQUIREMENTS:
- You MUST return ONLY valid JSON
- Use English double quotes " NOT Chinese quotes " "
- Avoid line breaks in string values, use spaces instead
- Escape quotes in string values as \\"
- Do NOT include comments or extra text outside JSON
- Return pure JSON object only"""

        # Get raw response from LLM
        try:
            raw_response = await self.generate_response(enhanced_system_prompt, user_prompt)
        except Exception as e:
            logger.error(f"❌ LLM generate_response failed: {e}")
            logger.error(f"   Error type: {type(e).__name__}")
            raise

        # Log raw response for debugging
        logger.info("=" * 80)
        logger.info("🔍 LLM Raw Response:")
        logger.info(f"   Type: {type(raw_response)}")
        logger.info(f"   Length: {len(raw_response) if raw_response else 0}")
        logger.info(f"   Content preview (first 500 chars): {raw_response[:500] if raw_response else '<EMPTY>'}")
        logger.info("=" * 80)

        # Parse JSON with automatic repair
        result = parse_json_with_repair(raw_response)

        # Log parsed result for comparison
        logger.info("=" * 80)
        logger.info("Parsed JSON Result:")
        logger.info(json.dumps(result, ensure_ascii=False, indent=2))
        logger.info("=" * 80)

        return result