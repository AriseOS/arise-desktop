"""Browser window management for macOS"""
import logging
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WindowLayout:
    """Window layout configuration"""
    app_x: int
    app_y: int
    app_width: int
    app_height: int
    browser_x: int
    browser_y: int
    browser_width: int
    browser_height: int


class BrowserWindowManager:
    """Manage browser window positioning and layout on macOS"""

    def __init__(self, config_service=None):
        """Initialize window manager

        Args:
            config_service: Configuration service for preferences storage
        """
        self.config_service = config_service
        self.preferences_file = self._get_preferences_path()
        self.current_layout: Optional[WindowLayout] = None

    def _get_preferences_path(self) -> Path:
        """Get path to window preferences file

        Returns:
            Path to preferences JSON file
        """
        if self.config_service:
            base_path = self.config_service.get_storage_path()
        else:
            base_path = Path.home() / ".ami"

        preferences_dir = base_path / "preferences"
        preferences_dir.mkdir(parents=True, exist_ok=True)
        return preferences_dir / "window_layout.json"

    def get_screen_size(self) -> Tuple[int, int]:
        """Get screen resolution using macOS system_profiler

        Returns:
            Tuple of (width, height) in pixels
        """
        try:
            # Use AppleScript to get screen size
            script = """
            tell application "Finder"
                get bounds of window of desktop
            end tell
            """
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                # Parse output: "0, 0, width, height"
                bounds = result.stdout.strip().split(", ")
                if len(bounds) == 4:
                    width = int(bounds[2])
                    height = int(bounds[3])
                    logger.info(f"Detected screen size: {width}x{height}")
                    return width, height

            # Fallback: use default retina display resolution
            logger.warning("Failed to detect screen size, using default 1920x1080")
            return 1920, 1080

        except Exception as e:
            logger.error(f"Error getting screen size: {e}")
            return 1920, 1080

    def calculate_default_layout(self) -> WindowLayout:
        """Calculate default window layout (35% app, 65% browser)

        Returns:
            WindowLayout with calculated positions and sizes
        """
        screen_width, screen_height = self.get_screen_size()

        # Calculate dimensions (35% app, 65% browser)
        app_width = int(screen_width * 0.35)
        browser_width = screen_width - app_width

        # Use full screen height for both windows
        window_height = screen_height

        # Position app on left, browser on right
        layout = WindowLayout(
            app_x=0,
            app_y=0,
            app_width=app_width,
            app_height=window_height,
            browser_x=app_width,
            browser_y=0,
            browser_width=browser_width,
            browser_height=window_height
        )

        logger.info(f"Calculated default layout: app={app_width}x{window_height} @ (0,0), "
                   f"browser={browser_width}x{window_height} @ ({app_width},0)")

        return layout

    def save_layout_preferences(self, layout: WindowLayout):
        """Save window layout preferences to file

        Args:
            layout: WindowLayout to save
        """
        try:
            preferences = {
                "app": {
                    "x": layout.app_x,
                    "y": layout.app_y,
                    "width": layout.app_width,
                    "height": layout.app_height
                },
                "browser": {
                    "x": layout.browser_x,
                    "y": layout.browser_y,
                    "width": layout.browser_width,
                    "height": layout.browser_height
                }
            }

            with open(self.preferences_file, 'w') as f:
                json.dump(preferences, f, indent=2)

            logger.info(f"Saved window layout preferences to {self.preferences_file}")

        except Exception as e:
            logger.error(f"Failed to save layout preferences: {e}")

    def load_layout_preferences(self) -> Optional[WindowLayout]:
        """Load window layout preferences from file

        Returns:
            WindowLayout if preferences exist, None otherwise
        """
        try:
            if not self.preferences_file.exists():
                logger.debug("No saved window layout preferences found")
                return None

            with open(self.preferences_file, 'r') as f:
                preferences = json.load(f)

            layout = WindowLayout(
                app_x=preferences["app"]["x"],
                app_y=preferences["app"]["y"],
                app_width=preferences["app"]["width"],
                app_height=preferences["app"]["height"],
                browser_x=preferences["browser"]["x"],
                browser_y=preferences["browser"]["y"],
                browser_width=preferences["browser"]["width"],
                browser_height=preferences["browser"]["height"]
            )

            logger.info(f"Loaded window layout preferences from {self.preferences_file}")
            return layout

        except Exception as e:
            logger.error(f"Failed to load layout preferences: {e}")
            return None

    def get_or_create_layout(self) -> WindowLayout:
        """Get saved layout or create default layout

        Returns:
            WindowLayout (from preferences or default)
        """
        # Try to load saved preferences
        layout = self.load_layout_preferences()

        if layout is None:
            # No saved preferences, use default layout
            layout = self.calculate_default_layout()
            # Save default layout for future use
            self.save_layout_preferences(layout)

        self.current_layout = layout
        return layout

    def position_browser_window(self, browser_pid: int) -> bool:
        """Position browser window using macOS AppleScript

        Args:
            browser_pid: Browser process PID

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.current_layout:
                self.current_layout = self.get_or_create_layout()

            layout = self.current_layout

            # AppleScript to position Chrome/Chromium window
            # Note: Chrome identifies windows by index, we target the most recent window
            script = f"""
            tell application "System Events"
                tell process "Chromium"
                    set frontmost to true
                    tell window 1
                        set position to {{{layout.browser_x}, {layout.browser_y}}}
                        set size to {{{layout.browser_width}, {layout.browser_height}}}
                    end tell
                end tell
            end tell
            """

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                logger.info(f"✅ Browser window positioned at ({layout.browser_x}, {layout.browser_y}) "
                          f"with size {layout.browser_width}x{layout.browser_height}")
                return True
            else:
                logger.error(f"Failed to position browser window: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Timeout positioning browser window")
            return False
        except Exception as e:
            logger.error(f"Error positioning browser window: {e}")
            return False

    def position_app_window(self, app_name: str = "Ami") -> bool:
        """Position Tauri app window using macOS AppleScript

        Args:
            app_name: Name of the Tauri application

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.current_layout:
                self.current_layout = self.get_or_create_layout()

            layout = self.current_layout

            # AppleScript to position Tauri app window
            script = f"""
            tell application "System Events"
                tell process "{app_name}"
                    set frontmost to true
                    tell window 1
                        set position to {{{layout.app_x}, {layout.app_y}}}
                        set size to {{{layout.app_width}, {layout.app_height}}}
                    end tell
                end tell
            end tell
            """

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                logger.info(f"✅ App window positioned at ({layout.app_x}, {layout.app_y}) "
                          f"with size {layout.app_width}x{layout.app_height}")
                return True
            else:
                logger.error(f"Failed to position app window: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Timeout positioning app window")
            return False
        except Exception as e:
            logger.error(f"Error positioning app window: {e}")
            return False

    def arrange_windows(self, browser_pid: int, app_name: str = "Ami") -> Dict[str, bool]:
        """Arrange both app and browser windows side by side

        Args:
            browser_pid: Browser process PID
            app_name: Name of the Tauri application

        Returns:
            Dict with success status for each window
        """
        logger.info("Arranging windows for side-by-side layout...")

        # Ensure we have layout
        if not self.current_layout:
            self.get_or_create_layout()

        # Position both windows
        app_success = self.position_app_window(app_name)
        browser_success = self.position_browser_window(browser_pid)

        result = {
            "app_positioned": app_success,
            "browser_positioned": browser_success,
            "success": app_success and browser_success
        }

        if result["success"]:
            logger.info("✅ Windows arranged successfully")
        else:
            logger.warning(f"⚠️ Window arrangement incomplete: app={app_success}, browser={browser_success}")

        return result

    def update_layout(self, app_width_percent: float) -> WindowLayout:
        """Update layout with new app width percentage

        Args:
            app_width_percent: Percentage of screen width for app (0.0 to 1.0)

        Returns:
            Updated WindowLayout
        """
        screen_width, screen_height = self.get_screen_size()

        # Calculate new dimensions
        app_width = int(screen_width * app_width_percent)
        browser_width = screen_width - app_width

        # Create new layout
        layout = WindowLayout(
            app_x=0,
            app_y=0,
            app_width=app_width,
            app_height=screen_height,
            browser_x=app_width,
            browser_y=0,
            browser_width=browser_width,
            browser_height=screen_height
        )

        # Save and set as current
        self.save_layout_preferences(layout)
        self.current_layout = layout

        logger.info(f"Updated layout: {app_width_percent*100:.0f}% app, {(1-app_width_percent)*100:.0f}% browser")

        return layout

    def get_layout_info(self) -> Dict[str, Any]:
        """Get current layout information

        Returns:
            Dict with layout details
        """
        if not self.current_layout:
            self.current_layout = self.get_or_create_layout()

        layout = self.current_layout
        screen_width, screen_height = self.get_screen_size()

        return {
            "screen": {
                "width": screen_width,
                "height": screen_height
            },
            "app": {
                "x": layout.app_x,
                "y": layout.app_y,
                "width": layout.app_width,
                "height": layout.app_height,
                "percent": round(layout.app_width / screen_width * 100, 1)
            },
            "browser": {
                "x": layout.browser_x,
                "y": layout.browser_y,
                "width": layout.browser_width,
                "height": layout.browser_height,
                "percent": round(layout.browser_width / screen_width * 100, 1)
            }
        }
