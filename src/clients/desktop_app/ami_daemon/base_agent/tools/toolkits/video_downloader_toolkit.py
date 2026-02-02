"""
VideoDownloaderToolkit - Video download capabilities for multi-modal agent.

Based on Eigent's VideoDownloaderToolkit implementation which wraps CAMEL's toolkit.
Uses yt-dlp for video downloading from various platforms.

References:
- Eigent: third-party/eigent/backend/app/utils/toolkit/video_download_toolkit.py
- CAMEL: camel.toolkits.VideoDownloaderToolkit
- yt-dlp: https://github.com/yt-dlp/yt-dlp
"""

import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit
from ...workspace import get_working_directory

logger = logging.getLogger(__name__)


class VideoDownloaderToolkit(BaseToolkit):
    """A toolkit for downloading videos from various platforms.

    Uses yt-dlp to download videos from:
    - YouTube
    - Vimeo
    - Twitter/X
    - TikTok
    - Instagram
    - And many more platforms

    Based on Eigent's implementation which wraps CAMEL's VideoDownloaderToolkit.
    """

    agent_name: str = "multi_modal_agent"

    def __init__(
        self,
        working_directory: Optional[str] = None,
        cookies_path: Optional[str] = None,
        timeout: Optional[float] = 300.0,
    ) -> None:
        """Initialize the VideoDownloaderToolkit.

        Args:
            working_directory: Directory for saving videos.
                If not provided, uses task workspace from WorkingDirectoryManager.
            cookies_path: Optional path to cookies file for authenticated downloads.
            timeout: Download timeout in seconds.
        """
        super().__init__(timeout=timeout)

        # Determine working directory - fail if not provided and no workspace manager
        if working_directory:
            self._working_directory = Path(working_directory)
        else:
            self._working_directory = Path(get_working_directory())

        # Ensure directory exists
        self._working_directory.mkdir(parents=True, exist_ok=True)

        self._cookies_path = cookies_path

        logger.info(f"VideoDownloaderToolkit initialized in {self._working_directory}")

    def _check_yt_dlp(self) -> bool:
        """Check if yt-dlp is available."""
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @listen_toolkit(
        inputs=lambda self, url, **kw: f"Downloading video from: {url[:50]}...",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def download_video(
        self,
        url: str,
        filename: Optional[str] = None,
        video_format: Optional[str] = None,
        quality: str = "best",
    ) -> str:
        """Download a video from a URL.

        Supports various platforms including YouTube, Vimeo, Twitter, TikTok, etc.

        Args:
            url: URL of the video to download.
            filename: Optional output filename (without extension).
                If not provided, uses video title.
            video_format: Optional format (mp4, webm, etc.). Defaults to mp4.
            quality: Quality setting ('best', 'worst', '720p', '1080p', etc.).

        Returns:
            Success message with file path, or error message.
        """
        if not self._check_yt_dlp():
            return "Error: yt-dlp not installed. Install with: pip install yt-dlp"

        logger.info(f"Downloading video from: {url}")

        try:
            # Build yt-dlp command
            cmd = ["yt-dlp"]

            # Output template
            if filename:
                output_template = str(self._working_directory / f"{filename}.%(ext)s")
            else:
                output_template = str(self._working_directory / "%(title)s.%(ext)s")

            cmd.extend(["-o", output_template])

            # Format selection
            if video_format:
                if video_format.lower() == "mp4":
                    cmd.extend(["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"])
                elif video_format.lower() == "mp3":
                    cmd.extend(["-x", "--audio-format", "mp3"])
                else:
                    cmd.extend(["-f", f"bestvideo[ext={video_format}]+bestaudio/best[ext={video_format}]/best"])
            else:
                # Default to mp4
                cmd.extend(["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"])

            # Quality selection
            if quality != "best":
                if quality == "worst":
                    cmd.extend(["--format-sort", "res"])
                elif quality in ["720p", "1080p", "480p", "360p"]:
                    height = quality[:-1]
                    cmd.extend(["-f", f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"])

            # Cookies
            if self._cookies_path and Path(self._cookies_path).exists():
                cmd.extend(["--cookies", self._cookies_path])

            # Additional options
            cmd.extend([
                "--no-playlist",  # Don't download playlist
                "--restrict-filenames",  # Safe filenames
                "--print", "after_move:filepath",  # Print final path
            ])

            # Add URL
            cmd.append(url)

            # Execute
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self._working_directory)
            )

            if result.returncode == 0:
                # Get output file path from stdout
                output_lines = result.stdout.strip().split('\n')
                filepath = output_lines[-1] if output_lines else "unknown"

                logger.info(f"Video downloaded successfully: {filepath}")
                return f"Video downloaded successfully: {filepath}"
            else:
                error_msg = result.stderr or result.stdout or "Unknown error"
                logger.error(f"Download failed: {error_msg}")
                return f"Error downloading video: {error_msg[:500]}"

        except subprocess.TimeoutExpired:
            return f"Error: Download timed out after {self.timeout} seconds"
        except Exception as e:
            error_msg = f"Error downloading video: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @listen_toolkit(
        inputs=lambda self, url: f"Getting info for: {url[:50]}...",
        return_msg=lambda r: str(r)[:200]
    )
    def get_video_info(self, url: str) -> Dict[str, Any]:
        """Get information about a video without downloading.

        Args:
            url: URL of the video.

        Returns:
            Dictionary with video metadata, or error message.
        """
        if not self._check_yt_dlp():
            return {"error": "yt-dlp not installed"}

        logger.info(f"Getting video info for: {url}")

        try:
            import json

            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-playlist",
                url
            ]

            if self._cookies_path and Path(self._cookies_path).exists():
                cmd.extend(["--cookies", self._cookies_path])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                info = json.loads(result.stdout)
                return {
                    "title": info.get("title"),
                    "description": info.get("description", "")[:500],
                    "duration": info.get("duration"),
                    "duration_string": info.get("duration_string"),
                    "uploader": info.get("uploader"),
                    "upload_date": info.get("upload_date"),
                    "view_count": info.get("view_count"),
                    "like_count": info.get("like_count"),
                    "thumbnail": info.get("thumbnail"),
                    "formats_available": len(info.get("formats", [])),
                    "webpage_url": info.get("webpage_url"),
                }
            else:
                return {"error": result.stderr or "Failed to get video info"}

        except subprocess.TimeoutExpired:
            return {"error": "Timeout getting video info"}
        except json.JSONDecodeError:
            return {"error": "Failed to parse video info"}
        except Exception as e:
            return {"error": str(e)}

    @listen_toolkit(
        inputs=lambda self, url, **kw: f"Extracting audio from: {url[:50]}...",
        return_msg=lambda r: r[:200] if isinstance(r, str) else str(r)
    )
    def download_audio(
        self,
        url: str,
        filename: Optional[str] = None,
        audio_format: str = "mp3",
    ) -> str:
        """Download only the audio from a video.

        Args:
            url: URL of the video.
            filename: Optional output filename (without extension).
            audio_format: Audio format (mp3, m4a, wav, etc.).

        Returns:
            Success message with file path, or error message.
        """
        if not self._check_yt_dlp():
            return "Error: yt-dlp not installed. Install with: pip install yt-dlp"

        logger.info(f"Downloading audio from: {url}")

        try:
            cmd = ["yt-dlp"]

            # Output template
            if filename:
                output_template = str(self._working_directory / f"{filename}.%(ext)s")
            else:
                output_template = str(self._working_directory / "%(title)s.%(ext)s")

            cmd.extend(["-o", output_template])

            # Extract audio
            cmd.extend([
                "-x",
                "--audio-format", audio_format,
                "--audio-quality", "0",  # Best quality
            ])

            # Cookies
            if self._cookies_path and Path(self._cookies_path).exists():
                cmd.extend(["--cookies", self._cookies_path])

            cmd.extend([
                "--no-playlist",
                "--restrict-filenames",
                "--print", "after_move:filepath",
                url
            ])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self._working_directory)
            )

            if result.returncode == 0:
                output_lines = result.stdout.strip().split('\n')
                filepath = output_lines[-1] if output_lines else "unknown"

                logger.info(f"Audio downloaded successfully: {filepath}")
                return f"Audio downloaded successfully: {filepath}"
            else:
                error_msg = result.stderr or result.stdout or "Unknown error"
                return f"Error downloading audio: {error_msg[:500]}"

        except subprocess.TimeoutExpired:
            return f"Error: Download timed out after {self.timeout} seconds"
        except Exception as e:
            return f"Error downloading audio: {str(e)}"

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
            FunctionTool(self.download_video),
            FunctionTool(self.get_video_info),
            FunctionTool(self.download_audio),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "VideoDownloader"
