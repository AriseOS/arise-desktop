"""
ImageGenerationToolkit - Image generation using OpenAI DALL-E and other models.

Uses OpenAI SDK directly (no CAMEL dependency).
"""

import base64
import logging
from pathlib import Path
from typing import List, Literal, Optional, Union

from openai import OpenAI

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit
from ...workspace import get_working_directory

logger = logging.getLogger(__name__)


class ImageGenerationToolkit(BaseToolkit):
    """A toolkit for generating images using AI models.

    Uses OpenAI SDK directly for image generation:
    - DALL-E 2, DALL-E 3, or GPT-Image-1
    - Various image sizes and quality settings
    - Local file saving (b64_json) or URL return
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
        base_url: Optional[str] = None,
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
            timeout: Operation timeout in seconds.
            api_key: OpenAI API key.
            url: Custom API base URL (alias for base_url).
            base_url: Custom API base URL.
            size: Image size to generate.
            quality: Image quality setting.
            response_format: Whether to return URL or base64 data.
            background: Background style (only for gpt-image-1).
            style: Image style (only for dall-e-3).
            working_directory: Directory for saving generated images.
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
                import tempfile
                self._working_directory = str(Path(tempfile.gettempdir()) / "ami_generated_images")
                logger.warning(f"WorkingDirectoryManager not available: {e}. Using temp dir: {self._working_directory}")

        Path(self._working_directory).mkdir(parents=True, exist_ok=True)

        # OpenAI client
        resolved_base_url = base_url or url
        self._client = OpenAI(
            api_key=api_key,
            base_url=resolved_base_url,
            timeout=timeout,
        )

        self._model = model or "dall-e-3"
        self._size = size
        self._quality = quality
        self._response_format = response_format
        self._background = background
        self._style = style

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

        Args:
            prompt: Text description of the image to generate.
            image_name: Name(s) for the saved image file(s).
                Must end with .png.
            n: Number of images to generate.

        Returns:
            Success message with image path/URL, or error message.
        """
        logger.info(f"Generating image: {prompt[:100]}...")

        # Validate image names
        names = [image_name] if isinstance(image_name, str) else image_name
        for name in names:
            if not name.endswith('.png'):
                return f"Error: Image name must end with .png, got: {name}"

        # Build API params
        params = {
            "model": self._model,
            "prompt": prompt,
            "n": n,
        }
        if self._size:
            params["size"] = self._size
        if self._quality:
            params["quality"] = self._quality
        if self._response_format:
            params["response_format"] = self._response_format
        if self._style and self._model == "dall-e-3":
            params["style"] = self._style
        if self._background and self._model == "gpt-image-1":
            params["background"] = self._background

        try:
            response = self._client.images.generate(**params)
        except Exception as e:
            return f"Error generating image: {e}"

        # Process results
        results = []
        for i, image_data in enumerate(response.data):
            name = names[i] if i < len(names) else f"image_{i}.png"

            if self._response_format == "b64_json" and image_data.b64_json:
                # Save base64 to file
                file_path = Path(self._working_directory) / name
                img_bytes = base64.b64decode(image_data.b64_json)
                file_path.write_bytes(img_bytes)
                results.append(f"Image saved to: {file_path}")
            elif image_data.url:
                results.append(f"Image URL: {image_data.url}")
            else:
                results.append(f"Image {i} generated (no URL or b64 data)")

        return "\n".join(results)

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

        Args:
            prompt: Description of the artwork to create.
            style: Art style (e.g., "digital art", "oil painting").
            image_name: Name for the saved image file (must end with .png).

        Returns:
            Success message with image path/URL, or error message.
        """
        if not image_name.endswith('.png'):
            return f"Error: Image name must end with .png, got: {image_name}"

        enhanced_prompt = f"{prompt}, {style} style, high quality, detailed"
        return self.generate_image(prompt=enhanced_prompt, image_name=image_name, n=1)

    @property
    def model(self) -> str:
        """Get the current model name."""
        return self._model

    @property
    def working_directory(self) -> str:
        """Get the working directory for saved images."""
        return self._working_directory

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit."""
        return [
            FunctionTool(self.generate_image),
            FunctionTool(self.create_artwork),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "ImageGeneration"
