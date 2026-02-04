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
        self._reused_existing: bool = False  # Track if we reused an existing Chrome instance
        self._reused_pid: Optional[int] = None  # PID of reused Chrome instance

    async def launch(self) -> str:
        """Launch browser and return CDP URL.

        If an existing Chrome instance is found using the same profile with CDP enabled,
        it will be reused instead of launching a new one.

        Returns:
            CDP URL (e.g., "http://127.0.0.1:9222")
        """
        # Check for existing Chrome processes using the same user data dir
        if self.user_data_dir:
            existing_cdp_url = await self._check_and_cleanup_existing_chrome()
            if existing_cdp_url:
                logger.info(f"Reusing existing Chrome instance at {existing_cdp_url}")
                # Extract port from URL for our tracking
                import re
                port_match = re.search(r':(\d+)$', existing_cdp_url)
                if port_match:
                    self._cdp_port = int(port_match.group(1))
                self._reused_existing = True
                return existing_cdp_url

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

        # Prepare environment - on macOS, set LSBackgroundOnly to prevent stealing focus
        env = os.environ.copy()
        if platform.system() == "Darwin":
            # LSBackgroundOnly=1 tells macOS to treat this as a background app
            # that should not steal focus when launched
            env["LSBackgroundOnly"] = "1"

        self._process = await asyncio.create_subprocess_exec(
            chrome_path,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        logger.info(f"Browser launched with PID: {self._process.pid}")

        # Wait for CDP to be ready
        cdp_url = f"http://127.0.0.1:{self._cdp_port}"
        await self._wait_for_cdp_ready(cdp_url)
        logger.info(f"CDP ready at: {cdp_url}")

        return cdp_url

    async def close(self) -> None:
        """Close the browser process.

        If we reused an existing Chrome instance, we don't terminate it.
        """
        if self._reused_existing:
            logger.info("Skipping browser termination (reused existing instance)")
            self._process = None
            return

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

    async def _check_and_cleanup_existing_chrome(self) -> Optional[str]:
        """Check for existing Chrome processes using the same user data dir.

        If an existing Chrome instance is found with a CDP port, return that CDP URL
        so we can reuse it. Otherwise, clean up and return None to launch a new instance.

        Returns:
            CDP URL if existing instance can be reused, None otherwise.
        """
        import subprocess
        import signal
        import re

        if not self.user_data_dir:
            return None

        try:
            system = platform.system()
            if system not in ("Darwin", "Linux"):
                return None

            # Find Chrome processes with this user-data-dir
            result = subprocess.run(
                ["pgrep", "-f", f"--user-data-dir={self.user_data_dir}"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if not result.stdout.strip():
                logger.debug("No existing Chrome process found for this profile")
                return None

            pids = result.stdout.strip().split('\n')
            logger.info(f"Found {len(pids)} Chrome process(es) using this profile")

            # Try to find the main Chrome process with remote-debugging-port
            for pid in pids:
                try:
                    pid_int = int(pid.strip())
                    # Get the command line of this process
                    cmd_result = subprocess.run(
                        ["ps", "-p", str(pid_int), "-o", "args="],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    cmdline = cmd_result.stdout.strip()

                    # Check if it has remote-debugging-port
                    port_match = re.search(r'--remote-debugging-port=(\d+)', cmdline)
                    if port_match:
                        existing_port = int(port_match.group(1))
                        cdp_url = f"http://127.0.0.1:{existing_port}"

                        # Verify the CDP is responding
                        try:
                            # Use trust_env=False to bypass system proxy for localhost
                            async with aiohttp.ClientSession(trust_env=False) as session:
                                async with session.get(f"{cdp_url}/json/version", timeout=2) as resp:
                                    if resp.status == 200:
                                        data = await resp.json()
                                        logger.info(f"Found existing Chrome instance at {cdp_url} (PID {pid_int}): {data.get('Browser', 'unknown')}")
                                        # Save the PID for later use
                                        self._reused_pid = pid_int
                                        return cdp_url
                        except Exception as e:
                            logger.debug(f"Existing Chrome CDP not responding: {e}")

                except (ValueError, subprocess.TimeoutExpired) as e:
                    continue

            # No reusable instance found - kill existing processes
            logger.info("No reusable Chrome instance found, cleaning up existing processes...")

            for pid in pids:
                try:
                    pid_int = int(pid.strip())
                    logger.info(f"Killing Chrome process {pid_int}")
                    os.kill(pid_int, signal.SIGTERM)
                except (ValueError, OSError) as e:
                    logger.warning(f"Failed to kill process {pid}: {e}")

            # Wait for processes to terminate
            await asyncio.sleep(1.0)

            # Force kill if still running
            result = subprocess.run(
                ["pgrep", "-f", f"--user-data-dir={self.user_data_dir}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        pid_int = int(pid.strip())
                        logger.warning(f"Force killing Chrome process {pid_int}")
                        os.kill(pid_int, signal.SIGKILL)
                    except (ValueError, OSError):
                        pass
                await asyncio.sleep(0.5)

            # Clean up SingletonLock if it exists
            singleton_lock = Path(self.user_data_dir) / "SingletonLock"
            if singleton_lock.exists():
                try:
                    singleton_lock.unlink()
                    logger.info("Removed stale SingletonLock file")
                except OSError as e:
                    logger.warning(f"Could not remove SingletonLock: {e}")

            return None

        except subprocess.TimeoutExpired:
            logger.warning("Timeout while checking for existing Chrome processes")
            return None
        except FileNotFoundError:
            logger.debug("pgrep not available")
            return None
        except Exception as e:
            logger.warning(f"Error checking for existing Chrome: {e}")
            return None

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
        attempt = 0

        logger.info(f"Waiting for CDP to be ready at {version_url} (timeout={timeout}s)")

        while asyncio.get_event_loop().time() - start_time < timeout:
            attempt += 1
            try:
                # Check if process is still running
                if self._process and self._process.returncode is not None:
                    logger.error(f"Browser process exited with code {self._process.returncode}")
                    # Try to get stderr
                    if self._process.stderr:
                        try:
                            stderr = await asyncio.wait_for(
                                self._process.stderr.read(4096),
                                timeout=1.0
                            )
                            if stderr:
                                logger.error(f"Browser stderr: {stderr.decode('utf-8', errors='ignore')[:500]}")
                        except Exception:
                            pass
                    raise RuntimeError(f"Browser process exited unexpectedly with code {self._process.returncode}")

                # Use trust_env=False to bypass system proxy for localhost
                async with aiohttp.ClientSession(trust_env=False) as session:
                    async with session.get(version_url, timeout=2) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            browser_version = data.get('Browser', 'unknown')
                            logger.info(f"CDP ready after {attempt} attempts. Browser: {browser_version}")
                            return
                        else:
                            if attempt % 10 == 0:  # Log every 10 attempts
                                logger.debug(f"CDP attempt {attempt}: status={resp.status}")
            except aiohttp.ClientConnectorError as e:
                if attempt % 10 == 0:
                    logger.debug(f"CDP attempt {attempt}: connection refused (browser may still be starting)")
            except asyncio.TimeoutError:
                if attempt % 10 == 0:
                    logger.debug(f"CDP attempt {attempt}: timeout")
            except RuntimeError:
                raise  # Re-raise browser exit error
            except Exception as e:
                if attempt % 10 == 0:
                    logger.debug(f"CDP attempt {attempt}: {type(e).__name__}: {e}")
            await asyncio.sleep(0.1)

        # Timeout - collect diagnostic info
        elapsed = asyncio.get_event_loop().time() - start_time
        logger.error(f"CDP not ready after {elapsed:.1f}s ({attempt} attempts)")

        # Check process state
        if self._process:
            if self._process.returncode is not None:
                logger.error(f"Browser process has exited with code: {self._process.returncode}")
            else:
                logger.error(f"Browser process still running (PID: {self._process.pid})")

        raise TimeoutError(f"CDP not ready after {timeout}s ({attempt} attempts)")

    @property
    def cdp_url(self) -> Optional[str]:
        """Get CDP URL if browser is running."""
        if self._cdp_port:
            return f"http://127.0.0.1:{self._cdp_port}"
        return None

    @property
    def browser_pid(self) -> Optional[int]:
        """Get browser PID (either launched or reused)."""
        if self._process is not None:
            return self._process.pid
        if self._reused_existing and self._reused_pid is not None:
            return self._reused_pid
        return None

    @property
    def is_running(self) -> bool:
        """Check if browser is running."""
        return self._process is not None and self._process.returncode is None
