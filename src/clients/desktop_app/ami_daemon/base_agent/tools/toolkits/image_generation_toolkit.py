"""
ImageGenerationToolkit - Image generation using OpenAI DALL-E and other models.

Based on Eigent's OpenAIImageToolkit implementation which wraps CAMEL's toolkit.
Uses OpenAI or Grok models for image generation from text prompts.

References:
- Eigent: third-party/eigent/backend/app/utils/toolkit/openai_image_toolkit.py
- CAMEL: camel.toolkits.OpenAIImageToolkit (ImageGenToolkit)
"""

import logging
from pathlib import Path
from typing import List, Literal, Optional, Union

from camel.toolkits import OpenAIImageToolkit as CAMELImageGenToolkit

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit
from ...workspace import get_working_directory

logger = logging.getLogger(__name__)


class ImageGenerationToolkit(BaseToolkit):
    """A toolkit for generating images using AI models.

    Wraps CAMEL's ImageGenToolkit to provide:
    - Image generation from text prompts using DALL-E 2, DALL-E 3, or GPT-Image-1
    - Support for various image sizes and quality settings
    - Local file saving or URL return

    Based on Eigent's implementation which wraps CAMEL's OpenAIImageToolkit.
    """

    agent_name: str = "multi_modal_agent"

    def __init__(
        self,
        model: Optional[
            Literal[
                "gpt-image-1",
                "dall-e-3",
                "dall-e-2",
            ]
        ] = "dall-e-3",
        timeout: Optional[float] = 180.0,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        size: Optional[
            Literal[
                "256x256",
                "512x512",
                "1024x1024",
                "1536x1024",
                "1024x1536",
                "1792x1024",
                "1024x1792",
                "auto",
            ]
        ] = "1024x1024",
        quality: Optional[
            Literal["auto", "low", "medium", "high", "standard", "hd"]
        ] = "standard",
        response_format: Optional[Literal["url", "b64_json"]] = "b64_json",
        background: Optional[Literal["transparent", "opaque", "auto"]] = "auto",
        style: Optional[Literal["vivid", "natural"]] = None,
        working_directory: Optional[str] = None,
    ) -> None:
        """Initialize the ImageGenerationToolkit.

        Args:
            model: The model to use for image generation.
                Options: "gpt-image-1", "dall-e-3", "dall-e-2".
            timeout: Operation timeout in seconds.
            api_key: OpenAI API key. If not provided, uses OPENAI_API_KEY env var.
            url: Custom API base URL.
            size: Image size to generate.
            quality: Image quality setting (model-dependent).
            response_format: Whether to return URL or base64 data.
            background: Background style (only for gpt-image-1).
            style: Image style (only for dall-e-3).
            working_directory: Directory for saving generated images.
                If not provided, uses task workspace from WorkingDirectoryManager.
        """
        super().__init__(timeout=timeout)

        # Determine working directory
        if working_directory:
            self._working_directory = working_directory
        else:
            try:
                self._working_directory = str(
                    Path(get_working_directory()) / "generated_images"
                )
            except RuntimeError as e:
                # WorkingDirectoryManager not initialized, use temp directory
                import tempfile
                self._working_directory = str(Path(tempfile.gettempdir()) / "ami_generated_images")
                logger.warning(f"WorkingDirectoryManager not available: {e}. Using temp dir: {self._working_directory}")

        # Ensure directory exists
        Path(self._working_directory).mkdir(parents=True, exist_ok=True)

        # Initialize CAMEL's toolkit
        self._camel_toolkit = CAMELImageGenToolkit(
            model=model,
            timeout=timeout,
            api_key=api_key,
            url=url,
            size=size,
            quality=quality,
            response_format=response_format,
            background=background,
            style=style,
            working_directory=self._working_directory,
        )

        self._model = model
        logger.info(
            f"ImageGenerationToolkit initialized (model={model}, "
            f"working_directory={self._working_directory})"
        )

    @listen_toolkit(
        inputs=lambda self, prompt, **kw: f"Generating image: {prompt[:50]}...",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def generate_image(
        self,
        prompt: str,
        image_name: Union[str, List[str]] = "image.png",
        n: int = 1,
    ) -> str:
        """Generate an image from a text prompt.

        The generated image will be saved locally (for b64_json response format)
        or an image URL will be returned (for url response format).

        Args:
            prompt: Text description of the image to generate.
            image_name: Name(s) for the saved image file(s).
                Must end with .png. If generating multiple images, provide
                a list of names matching the n parameter.
            n: Number of images to generate.

        Returns:
            Success message with image path/URL, or error message.
        """
        logger.info(f"Generating image: {prompt[:100]}...")

        # Validate image_name ends with .png
        if isinstance(image_name, str):
            if not image_name.endswith('.png'):
                return f"Error: Image name must end with .png, got: {image_name}"
        elif isinstance(image_name, list):
            for name in image_name:
                if not name.endswith('.png'):
                    return f"Error: All image names must end with .png, got: {name}"

        return self._camel_toolkit.generate_image(
            prompt=prompt,
            image_name=image_name,
            n=n,
        )

    @listen_toolkit(
        inputs=lambda self, prompt, **kw: f"Creating artwork: {prompt[:50]}...",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def create_artwork(
        self,
        prompt: str,
        style: str = "digital art",
        image_name: str = "artwork.png",
    ) -> str:
        """Create an artistic image with style guidance.

        A convenience wrapper that enhances the prompt with style directions.

        Args:
            prompt: Description of the artwork to create.
            style: Art style (e.g., "digital art", "oil painting",
                "watercolor", "photorealistic", "cartoon").
            image_name: Name for the saved image file (must end with .png).

        Returns:
            Success message with image path/URL, or error message.
        """
        logger.info(f"Creating artwork: {prompt[:100]}...")

        if not image_name.endswith('.png'):
            return f"Error: Image name must end with .png, got: {image_name}"

        enhanced_prompt = f"{prompt}, {style} style, high quality, detailed"

        return self._camel_toolkit.generate_image(
            prompt=enhanced_prompt,
            image_name=image_name,
            n=1,
        )

    @property
    def model(self) -> str:
        """Get the current model name."""
        return self._model

    @property
    def working_directory(self) -> str:
        """Get the working directory for saved images."""
        return self._working_directory

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns:
            List of FunctionTool objects.
        """
        return [
            FunctionTool(self.generate_image),
            FunctionTool(self.create_artwork),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "ImageGeneration"
