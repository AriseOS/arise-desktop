"""
ImageAnalysisToolkit - Image analysis using vision-capable LLM providers.

Uses AnthropicProvider directly for image understanding (no CAMEL dependency).
"""

import base64
import logging
from pathlib import Path
from typing import List, Optional

from src.common.llm import AnthropicProvider

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit

logger = logging.getLogger(__name__)

# Supported image media types
_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _load_image_content(image_path: str) -> List[dict]:
    """Load image and return Anthropic-format content blocks.

    Args:
        image_path: Local file path or URL.

    Returns:
        List of content blocks for Anthropic messages API.
    """
    if image_path.startswith("http://") or image_path.startswith("https://"):
        # URL-based image
        return [{"type": "image", "source": {"type": "url", "url": image_path}}]

    # Local file - read and encode as base64
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    suffix = path.suffix.lower()
    media_type = _IMAGE_MEDIA_TYPES.get(suffix, "image/png")

    image_data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return [{
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": image_data,
        },
    }]


class ImageAnalysisToolkit(BaseToolkit):
    """A toolkit for analyzing images using vision-capable LLM.

    Uses AnthropicProvider directly for vision analysis:
    - Generate detailed descriptions of image content
    - Answer specific questions about images
    - Process images from both local files and URLs
    """

    agent_name: str = "multi_modal_agent"

    def __init__(
        self,
        provider: Optional[AnthropicProvider] = None,
        timeout: Optional[float] = 60.0,
        # Backward compatible: accept model kwarg (ignored, use provider)
        model=None,
    ) -> None:
        """Initialize the ImageAnalysisToolkit.

        Args:
            provider: AnthropicProvider instance for vision analysis.
            timeout: Operation timeout in seconds.
            model: Ignored (backward compatibility with CAMEL interface).
        """
        super().__init__(timeout=timeout)
        self._provider = provider
        logger.info("ImageAnalysisToolkit initialized")

    async def _ask_vision(self, image_path: str, question: str, system_prompt: Optional[str] = None) -> str:
        """Ask a question about an image using vision model.

        Args:
            image_path: Path to image or URL.
            question: Question to ask about the image.
            system_prompt: Optional system prompt.

        Returns:
            LLM response text.
        """
        if not self._provider:
            return "Error: No vision provider configured"

        image_blocks = _load_image_content(image_path)
        content = image_blocks + [{"type": "text", "text": question}]

        messages = [{"role": "user", "content": content}]
        response = await self._provider.generate_with_tools(
            system_prompt=system_prompt or "You are an expert image analyst.",
            messages=messages,
            tools=[],
            max_tokens=4096,
        )
        return response.get_text()

    @listen_toolkit(
        inputs=lambda self, image_path, **kw: f"Analyzing image: {image_path}",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def describe_image(
        self,
        image_path: str,
        custom_prompt: Optional[str] = None,
    ) -> str:
        """Generate a detailed description of an image.

        Args:
            image_path: Path to the image file or URL.
            custom_prompt: Optional custom system prompt for analysis.

        Returns:
            Text description of the image content.
        """
        import asyncio
        logger.info(f"Describing image: {image_path}")
        return asyncio.run(self._ask_vision(
            image_path,
            "Please provide a detailed description of this image.",
            system_prompt=custom_prompt,
        ))

    @listen_toolkit(
        inputs=lambda self, image_path, question: f"Asking about image: {question[:50]}...",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def ask_about_image(
        self,
        image_path: str,
        question: str,
        custom_prompt: Optional[str] = None,
    ) -> str:
        """Ask a specific question about an image.

        Args:
            image_path: Path to the image file or URL.
            question: The question to ask about the image.
            custom_prompt: Optional custom system prompt for analysis.

        Returns:
            Answer to the question about the image.
        """
        import asyncio
        logger.info(f"Asking about image: {question}")
        return asyncio.run(self._ask_vision(image_path, question, system_prompt=custom_prompt))

    @listen_toolkit(
        inputs=lambda self, image_path: f"Extracting text from: {image_path}",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def extract_text(self, image_path: str) -> str:
        """Extract text (OCR) from an image.

        Args:
            image_path: Path to the image file or URL.

        Returns:
            Extracted text from the image.
        """
        import asyncio
        logger.info(f"Extracting text from image: {image_path}")
        return asyncio.run(self._ask_vision(
            image_path,
            "Please extract and transcribe all text visible in this image. "
            "Include text from signs, labels, documents, screens, or any other source. "
            "Preserve the layout and formatting as much as possible.",
        ))

    @listen_toolkit(
        inputs=lambda self, image_path: f"Identifying objects in: {image_path}",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def identify_objects(self, image_path: str) -> str:
        """Identify and list objects in an image.

        Args:
            image_path: Path to the image file or URL.

        Returns:
            List of identified objects with descriptions.
        """
        import asyncio
        logger.info(f"Identifying objects in image: {image_path}")
        return asyncio.run(self._ask_vision(
            image_path,
            "Please identify and list all distinct objects visible in this image. "
            "For each object, provide: 1) Name of the object, 2) Brief description, "
            "3) Approximate location in the image (e.g., center, top-left). "
            "Format as a numbered list.",
        ))

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit."""
        return [
            FunctionTool(self.describe_image),
            FunctionTool(self.ask_about_image),
            FunctionTool(self.extract_text),
            FunctionTool(self.identify_objects),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "ImageAnalysis"
