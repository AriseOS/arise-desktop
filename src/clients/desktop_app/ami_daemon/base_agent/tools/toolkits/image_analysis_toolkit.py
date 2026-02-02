"""
ImageAnalysisToolkit - Image analysis capabilities for multi-modal agent.

Based on Eigent's ImageAnalysisToolkit implementation which wraps CAMEL's toolkit.
Uses vision models for image understanding and analysis.

References:
- Eigent: third-party/eigent/backend/app/utils/toolkit/image_analysis_toolkit.py
- CAMEL: camel.toolkits.ImageAnalysisToolkit
"""

import logging
from typing import List, Optional

from camel.models import BaseModelBackend
from camel.toolkits import ImageAnalysisToolkit as CAMELImageAnalysisToolkit

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit

logger = logging.getLogger(__name__)


class ImageAnalysisToolkit(BaseToolkit):
    """A toolkit for analyzing images using vision models.

    Wraps CAMEL's ImageAnalysisToolkit to provide:
    - Generate detailed descriptions of image content
    - Answer specific questions about images
    - Process images from both local files and URLs

    Based on Eigent's implementation which wraps CAMEL's ImageAnalysisToolkit.
    """

    agent_name: str = "multi_modal_agent"

    def __init__(
        self,
        model: Optional[BaseModelBackend] = None,
        timeout: Optional[float] = 60.0,
    ) -> None:
        """Initialize the ImageAnalysisToolkit.

        Args:
            model: Model backend for vision analysis.
                If not provided, CAMEL will use its default model.
            timeout: Operation timeout in seconds.
        """
        super().__init__(timeout=timeout)

        # Initialize CAMEL's toolkit with the provided model
        self._camel_toolkit = CAMELImageAnalysisToolkit(
            model=model,
            timeout=timeout,
        )

        logger.info("ImageAnalysisToolkit initialized (wrapping CAMEL)")

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
        logger.info(f"Describing image: {image_path}")
        return self._camel_toolkit.image_to_text(
            image_path=image_path,
            sys_prompt=custom_prompt,
        )

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
        logger.info(f"Asking about image: {question}")
        return self._camel_toolkit.ask_question_about_image(
            image_path=image_path,
            question=question,
            sys_prompt=custom_prompt,
        )

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
        logger.info(f"Extracting text from image: {image_path}")
        return self._camel_toolkit.ask_question_about_image(
            image_path=image_path,
            question=(
                "Please extract and transcribe all text visible in this image. "
                "Include text from signs, labels, documents, screens, or any other source. "
                "Preserve the layout and formatting as much as possible."
            ),
        )

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
        logger.info(f"Identifying objects in image: {image_path}")
        return self._camel_toolkit.ask_question_about_image(
            image_path=image_path,
            question=(
                "Please identify and list all distinct objects visible in this image. "
                "For each object, provide: 1) Name of the object, 2) Brief description, "
                "3) Approximate location in the image (e.g., center, top-left). "
                "Format as a numbered list."
            ),
        )

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns:
            List of FunctionTool objects.
        """
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
