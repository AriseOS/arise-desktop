"""
MarkItDownToolkit - Document reading and conversion to markdown.

Based on Eigent's MarkItDownToolkit implementation which wraps CAMEL's MarkItDownToolkit.
Provides document reading capabilities for various formats.

References:
- Eigent: third-party/eigent/backend/app/utils/toolkit/markitdown_toolkit.py
- CAMEL: camel.toolkits.MarkItDownToolkit
- MarkItDown: https://github.com/microsoft/markitdown

Supported formats:
- PDF (.pdf)
- Microsoft Office: Word (.doc, .docx), Excel (.xls, .xlsx), PowerPoint (.ppt, .pptx)
- EPUB (.epub)
- HTML (.html, .htm)
- Images (.jpg, .jpeg, .png) for OCR
- Audio (.mp3, .wav) for transcription
- Text-based formats (.csv, .json, .xml, .txt)
- ZIP archives (.zip)
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit

logger = logging.getLogger(__name__)


class MarkItDownToolkit(BaseToolkit):
    """A toolkit for reading and converting documents to markdown.

    Uses Microsoft's MarkItDown library to convert various document
    formats to markdown for easy processing by LLMs.

    Supported formats:
    - PDF documents
    - Microsoft Office (Word, Excel, PowerPoint)
    - EPUB e-books
    - HTML pages
    - Images (with OCR)
    - Audio files (with transcription)
    - Text-based formats (CSV, JSON, XML, TXT)
    - ZIP archives

    Based on Eigent's implementation which wraps CAMEL's MarkItDownToolkit.
    """

    agent_name: str = "document_agent"

    def __init__(
        self,
        timeout: Optional[float] = 120.0,
    ) -> None:
        """Initialize the MarkItDownToolkit.

        Args:
            timeout: Operation timeout in seconds.
        """
        super().__init__(timeout=timeout)

        self._markitdown = None

        logger.info("MarkItDownToolkit initialized")

    def _get_markitdown(self):
        """Get or create MarkItDown instance."""
        if self._markitdown is None:
            try:
                from markitdown import MarkItDown
                self._markitdown = MarkItDown()
            except ImportError:
                raise ImportError(
                    "markitdown package required. Install with: pip install markitdown"
                )
        return self._markitdown

    @listen_toolkit(
        inputs=lambda self, filepath: f"Reading document: {filepath}",
        return_msg=lambda r: f"Converted to {len(r)} chars" if isinstance(r, str) else str(r)[:200]
    )
    def read_file(self, filepath: str) -> str:
        """Read and convert a document to markdown.

        Supports various document formats:
        - PDF (.pdf)
        - Word (.doc, .docx)
        - Excel (.xls, .xlsx)
        - PowerPoint (.ppt, .pptx)
        - EPUB (.epub)
        - HTML (.html, .htm)
        - Images (.jpg, .jpeg, .png)
        - Audio (.mp3, .wav)
        - Text (.txt, .csv, .json, .xml)
        - ZIP archives (.zip)

        Args:
            filepath: Path to the file to read.

        Returns:
            Document content as markdown string, or error message.
        """
        path = Path(filepath)

        if not path.exists():
            return f"Error: File not found: {filepath}"

        logger.info(f"Reading document: {path}")

        try:
            md = self._get_markitdown()
            result = md.convert(str(path))

            if hasattr(result, 'text_content'):
                content = result.text_content
            elif hasattr(result, 'markdown'):
                content = result.markdown
            else:
                content = str(result)

            logger.info(f"Converted {path} to {len(content)} chars of markdown")
            return content

        except ImportError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            error_msg = f"Error reading document: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @listen_toolkit(
        inputs=lambda self, filepaths: f"Reading {len(filepaths)} files",
        return_msg=lambda r: f"Read {len(r)} files" if isinstance(r, dict) else str(r)[:200]
    )
    def read_files(self, filepaths: List[str]) -> Dict[str, str]:
        """Read multiple documents and convert to markdown.

        Args:
            filepaths: List of file paths to read.

        Returns:
            Dictionary mapping filepath to markdown content.
        """
        results = {}

        for filepath in filepaths:
            content = self.read_file(filepath)
            results[filepath] = content

        return results

    @listen_toolkit(
        inputs=lambda self, url: f"Reading URL: {url}",
        return_msg=lambda r: f"Fetched {len(r)} chars" if isinstance(r, str) else str(r)[:200]
    )
    def read_url(self, url: str) -> str:
        """Read and convert a web page to markdown.

        Args:
            url: URL of the web page to read.

        Returns:
            Page content as markdown string, or error message.
        """
        logger.info(f"Reading URL: {url}")

        try:
            md = self._get_markitdown()
            result = md.convert_url(url)

            if hasattr(result, 'text_content'):
                content = result.text_content
            elif hasattr(result, 'markdown'):
                content = result.markdown
            else:
                content = str(result)

            logger.info(f"Converted URL to {len(content)} chars of markdown")
            return content

        except ImportError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            error_msg = f"Error reading URL: {str(e)}"
            logger.error(error_msg)
            return error_msg

    def get_supported_formats(self) -> List[str]:
        """Get list of supported file formats.

        Returns:
            List of supported file extensions.
        """
        return [
            ".pdf",
            ".doc", ".docx",
            ".xls", ".xlsx",
            ".ppt", ".pptx",
            ".epub",
            ".html", ".htm",
            ".jpg", ".jpeg", ".png",
            ".mp3", ".wav",
            ".txt", ".csv", ".json", ".xml",
            ".zip",
        ]

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns:
            List of FunctionTool objects.
        """
        return [
            FunctionTool(self.read_file),
            FunctionTool(self.read_files),
            FunctionTool(self.read_url),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "MarkItDown"
