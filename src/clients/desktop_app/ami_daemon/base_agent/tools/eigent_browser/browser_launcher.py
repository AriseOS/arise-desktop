"""
Browser Launcher - Launch Chrome via subprocess and connect via CDP.

This approach avoids Playwright's browser launching, which leaves automation
fingerprints. Instead, we launch Chrome directly and connect via CDP.

Based on browser-use library's LocalBrowserWatchdog implementation.
"""

import asyncio
import logging
import os
import platform
import shutil
import socket
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import aiohttp

from .config_loader import BrowserConfig
from .extension_manager import get_extension_manager

logger = logging.getLogger(__name__)


class BrowserLauncher:
    """Launch Chrome browser via subprocess and provide CDP URL for connection."""

    def __init__(
        self,
        headless: bool = False,
        user_data_dir: Optional[str] = None,
        enable_stealth: bool = True,
        enable_extensions: bool = True,
    ):
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.enable_stealth = enable_stealth
        self.enable_extensions = enable_extensions

        self._process: Optional[asyncio.subprocess.Process] = None
        self._cdp_port: Optional[int] = None
        self._temp_user_data_dir: Optional[Path] = None

    async def launch(self) -> str:
        """Launch browser and return CDP URL.

        Returns:
            CDP URL (e.g., "http://127.0.0.1:9222")
        """
        # Find Chrome executable
        chrome_path = self._find_chrome_executable()
        if not chrome_path:
            raise RuntimeError("Chrome executable not found")
        logger.info(f"Using Chrome: {chrome_path}")

        # Find free port for CDP
        self._cdp_port = self._find_free_port()
        logger.info(f"CDP port: {self._cdp_port}")

        # Build launch arguments
        args = self._build_launch_args()
        logger.info(f"Launch args count: {len(args)}")
        logger.debug(f"Launch args: {args}")

        # Launch browser subprocess
        logger.info("Launching browser subprocess...")
        logger.info(f"Chrome path: {chrome_path}")
        logger.info(f"Args ({len(args)}): {args[:5]}... (showing first 5)")

        self._process = await asyncio.create_subprocess_exec(
            chrome_path,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info(f"Browser launched with PID: {self._process.pid}")

        # Wait for CDP to be ready
        cdp_url = f"http://127.0.0.1:{self._cdp_port}"
        await self._wait_for_cdp_ready(cdp_url)
        logger.info(f"CDP ready at: {cdp_url}")

        return cdp_url

    async def close(self) -> None:
        """Close the browser process."""
        if self._process:
            try:
                self._process.terminate()
                # Wait for process to terminate
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
                logger.info("Browser process terminated")
            except Exception as e:
                logger.warning(f"Error terminating browser: {e}")
            finally:
                self._process = None

        # Clean up temp user data dir if we created one
        if self._temp_user_data_dir and self._temp_user_data_dir.exists():
            try:
                shutil.rmtree(self._temp_user_data_dir)
                logger.debug(f"Cleaned up temp dir: {self._temp_user_data_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp dir: {e}")
            self._temp_user_data_dir = None

    def _find_chrome_executable(self) -> Optional[str]:
        """Find Chrome executable path."""
        system = platform.system()

        if system == "Darwin":  # macOS
            paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                os.path.expanduser(
                    "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                ),
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
            ]
        elif system == "Windows":
            paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ]
        else:  # Linux
            paths = [
                "/usr/bin/google-chrome-stable",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            ]

        for path in paths:
            if os.path.exists(path):
                return path

        return None

    def _find_free_port(self) -> int:
        """Find a free port for CDP."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    def _build_launch_args(self) -> List[str]:
        """Build Chrome launch arguments."""
        args = []

        # CDP debugging port
        args.append(f"--remote-debugging-port={self._cdp_port}")

        # User data directory (required for CDP connection)
        if self.user_data_dir:
            args.append(f"--user-data-dir={self.user_data_dir}")
        else:
            # Create temp directory
            self._temp_user_data_dir = Path(tempfile.mkdtemp(prefix="chrome-cdp-"))
            args.append(f"--user-data-dir={self._temp_user_data_dir}")

        # Headless mode
        if self.headless:
            args.append("--headless=new")

        # Stealth args
        if self.enable_stealth:
            stealth_args = BrowserConfig.get_launch_args()
            args.extend(stealth_args)

        # Extension args
        if self.enable_extensions and not self.headless:
            # Extensions don't work in headless mode
            try:
                ext_manager = get_extension_manager()
                extension_paths = ext_manager.ensure_extensions_downloaded()
                if extension_paths:
                    ext_args = ext_manager.get_extension_args(extension_paths)
                    args.extend(ext_args)
                    logger.info(f"Extensions loaded: {len(extension_paths)}")
            except Exception as e:
                logger.warning(f"Failed to load extensions: {e}")

        return args

    async def _wait_for_cdp_ready(
        self, cdp_url: str, timeout: float = 30.0
    ) -> None:
        """Wait for CDP to be ready."""
        version_url = f"{cdp_url}/json/version"
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(version_url, timeout=2) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            logger.debug(f"CDP version: {data.get('Browser', 'unknown')}")
                            return
            except Exception:
                pass
            await asyncio.sleep(0.1)

        raise TimeoutError(f"CDP not ready after {timeout}s")

    @property
    def cdp_url(self) -> Optional[str]:
        """Get CDP URL if browser is running."""
        if self._cdp_port:
            return f"http://127.0.0.1:{self._cdp_port}"
        return None

    @property
    def is_running(self) -> bool:
        """Check if browser is running."""
        return self._process is not None and self._process.returncode is None
