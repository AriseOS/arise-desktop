"""
FileToolkit - File writing and management for document operations.

Based on Eigent's FileToolkit implementation which wraps CAMEL's FileToolkit.
Provides file writing capabilities with event emission support.

References:
- Eigent: third-party/eigent/backend/app/utils/toolkit/file_write_toolkit.py
- CAMEL: camel.toolkits.FileToolkit
"""

import logging
from pathlib import Path
from typing import List, Optional, Union

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit
from ...workspace import get_working_directory

logger = logging.getLogger(__name__)


class FileToolkit(BaseToolkit):
    """A toolkit for file writing and management operations.

    Provides file creation and writing capabilities:
    - Write content to various file formats (txt, md, html, json, csv, etc.)
    - UTF-8 encoding by default
    - Automatic backup functionality
    - Support for LaTeX rendering in PDF

    Based on Eigent's implementation which wraps CAMEL's FileToolkit.
    """

    agent_name: str = "document_agent"

    def __init__(
        self,
        working_directory: Optional[str] = None,
        timeout: Optional[float] = 60.0,
        default_encoding: str = "utf-8",
        backup_enabled: bool = True,
    ) -> None:
        """Initialize the FileToolkit.

        Args:
            working_directory: Directory for file operations.
                If not provided, uses task workspace from WorkingDirectoryManager.
            timeout: Operation timeout in seconds.
            default_encoding: Default file encoding (default: utf-8).
            backup_enabled: Whether to create backups when modifying files.
        """
        super().__init__(timeout=timeout)

        # Determine working directory - fail if not provided and no workspace manager
        if working_directory:
            self._working_directory = Path(working_directory)
        else:
            self._working_directory = Path(get_working_directory())

        # Ensure directory exists
        self._working_directory.mkdir(parents=True, exist_ok=True)

        self._default_encoding = default_encoding
        self._backup_enabled = backup_enabled

        logger.info(
            f"FileToolkit initialized in {self._working_directory} "
            f"(encoding={default_encoding}, backup={backup_enabled})"
        )

    def _resolve_filepath(self, filename: str) -> Path:
        """Resolve a filename to an absolute path.

        If the filename is absolute, returns it directly.
        Otherwise, joins it with the working directory.

        Args:
            filename: The filename or path.

        Returns:
            Absolute Path object.
        """
        path = Path(filename)
        if path.is_absolute():
            return path
        return self._working_directory / filename

    def _create_backup(self, filepath: Path) -> Optional[Path]:
        """Create a backup of a file if it exists.

        Only keeps the single most recent backup per file. Previous backups
        are deleted before creating a new one.

        Args:
            filepath: Path to the file.

        Returns:
            Path to backup file if created, None otherwise.
        """
        if not self._backup_enabled or not filepath.exists():
            return None

        import shutil

        backup_path = filepath.with_suffix(f".bak{filepath.suffix}")

        try:
            shutil.copy2(filepath, backup_path)
            logger.info(f"Created backup: {backup_path}")
            return backup_path
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
            return None

    @listen_toolkit(
        inputs=lambda self, title, content, filename, **kw: f"Writing to {filename}",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def write_to_file(
        self,
        title: str,
        content: Union[str, List[List[str]]],
        filename: str,
        encoding: Optional[str] = None,
        use_latex: bool = False,
    ) -> str:
        """Write content to a file.

        Supports various file formats including:
        - Text files (.txt, .md, .html, .json, .yaml, .xml)
        - CSV files (.csv) - content can be a list of lists
        - Word documents (.docx)
        - PDF files (.pdf) with optional LaTeX support

        Args:
            title: Title or heading for the content.
            content: The content to write. For CSV, can be a list of lists.
            filename: The filename to write to.
            encoding: File encoding (default: utf-8).
            use_latex: Whether to render LaTeX in PDF files.

        Returns:
            Success message with file path, or error message.
        """
        effective_encoding = encoding or self._default_encoding
        filepath = self._resolve_filepath(filename)

        # Create parent directories if needed
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Create backup if file exists
        self._create_backup(filepath)

        logger.info(f"Writing to file: {filepath}")

        try:
            suffix = filepath.suffix.lower()

            if suffix == ".csv":
                # Handle CSV files
                import csv
                with open(filepath, "w", newline="", encoding=effective_encoding) as f:
                    writer = csv.writer(f)
                    if isinstance(content, list):
                        for row in content:
                            writer.writerow(row)
                    else:
                        # Write content as single column
                        for line in content.split("\n"):
                            writer.writerow([line])

            elif suffix == ".json":
                # Handle JSON files
                import json
                with open(filepath, "w", encoding=effective_encoding) as f:
                    if isinstance(content, str):
                        # Try to parse and pretty-print
                        try:
                            data = json.loads(content)
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        except json.JSONDecodeError:
                            f.write(content)
                    else:
                        json.dump(content, f, indent=2, ensure_ascii=False)

            elif suffix == ".docx":
                # Handle Word documents
                try:
                    from docx import Document

                    doc = Document()

                    # Add title
                    if title:
                        doc.add_heading(title, level=1)

                    # Add content
                    if isinstance(content, str):
                        for paragraph in content.split("\n\n"):
                            if paragraph.strip():
                                doc.add_paragraph(paragraph.strip())
                    elif isinstance(content, list):
                        for row in content:
                            doc.add_paragraph(", ".join(str(cell) for cell in row))

                    doc.save(str(filepath))
                except ImportError:
                    return "Error: python-docx package required for .docx files. Install with: pip install python-docx"

            elif suffix == ".pdf":
                # Handle PDF files
                try:
                    from reportlab.lib.pagesizes import letter
                    from reportlab.pdfgen import canvas
                    from reportlab.lib.units import inch

                    c = canvas.Canvas(str(filepath), pagesize=letter)
                    width, height = letter

                    # Add title
                    if title:
                        c.setFont("Helvetica-Bold", 16)
                        c.drawString(1 * inch, height - 1 * inch, title)

                    # Add content
                    c.setFont("Helvetica", 12)
                    y_position = height - 1.5 * inch

                    if isinstance(content, str):
                        for line in content.split("\n"):
                            if y_position < 1 * inch:
                                c.showPage()
                                y_position = height - 1 * inch
                                c.setFont("Helvetica", 12)
                            if len(line) > 80:
                                logger.warning(f"PDF line truncated from {len(line)} to 80 chars")
                            c.drawString(1 * inch, y_position, line[:80])  # Truncate long lines
                            y_position -= 14

                    c.save()
                except ImportError:
                    return "Error: reportlab package required for .pdf files. Install with: pip install reportlab"

            else:
                # Default: write as text file
                full_content = ""
                if title:
                    # Add title based on file type
                    if suffix == ".md":
                        full_content = f"# {title}\n\n"
                    elif suffix == ".html":
                        full_content = f"<h1>{title}</h1>\n\n"
                    else:
                        full_content = f"{title}\n{'=' * len(title)}\n\n"

                if isinstance(content, str):
                    full_content += content
                elif isinstance(content, list):
                    # Convert list of lists to text
                    for row in content:
                        full_content += "\t".join(str(cell) for cell in row) + "\n"

                with open(filepath, "w", encoding=effective_encoding) as f:
                    f.write(full_content)

            logger.info(f"Successfully wrote to file: {filepath}")
            return f"Content successfully written to file: {filepath}"

        except Exception as e:
            error_msg = f"Error writing to file {filepath}: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @listen_toolkit(
        inputs=lambda self, filepath: f"Reading {filepath}",
        return_msg=lambda r: f"Read {len(r)} chars" if isinstance(r, str) else str(r)
    )
    def read_file(self, filepath: str) -> str:
        """Read content from a file.

        Args:
            filepath: Path to the file to read.

        Returns:
            File content as string, or error message.
        """
        path = self._resolve_filepath(filepath)

        if not path.exists():
            return f"Error: File not found: {path}"

        try:
            with open(path, "r", encoding=self._default_encoding) as f:
                content = f.read()
            logger.info(f"Read {len(content)} chars from {path}")
            return content
        except Exception as e:
            error_msg = f"Error reading file {path}: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @listen_toolkit(
        inputs=lambda self, filepath: f"Checking {filepath}",
        return_msg=lambda r: str(r)
    )
    def file_exists(self, filepath: str) -> bool:
        """Check if a file exists.

        Args:
            filepath: Path to check.

        Returns:
            True if file exists, False otherwise.
        """
        path = self._resolve_filepath(filepath)
        return path.exists()

    @listen_toolkit(
        inputs=lambda self, directory=None: f"Listing files in {directory or 'working directory'}",
        return_msg=lambda r: f"Found {len(r)} files" if isinstance(r, list) else str(r)
    )
    def list_files(self, directory: Optional[str] = None) -> List[str]:
        """List files in a directory.

        Args:
            directory: Directory to list. Defaults to working directory.

        Returns:
            List of filenames.
        """
        dir_path = self._resolve_filepath(directory) if directory else self._working_directory

        if not dir_path.exists():
            logger.warning(f"Directory not found: {dir_path}")
            return []

        try:
            files = [f.name for f in dir_path.iterdir() if f.is_file()]
            return sorted(files)
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []

    @property
    def working_directory(self) -> Path:
        """Get the current working directory."""
        return self._working_directory

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns:
            List of FunctionTool objects.
        """
        return [
            FunctionTool(self.write_to_file),
            FunctionTool(self.read_file),
            FunctionTool(self.file_exists),
            FunctionTool(self.list_files),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "File"
