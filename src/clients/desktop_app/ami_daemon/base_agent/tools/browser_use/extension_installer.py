"""
Browser-Use Extension Installer

Copies bundled extensions (.crx files) to browser-use cache directory before browser starts.
This avoids downloading from Google servers which are blocked in China.

browser-use will automatically extract .crx files when it starts.
"""

import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Extension IDs that browser-use expects
REQUIRED_EXTENSIONS = [
    "cjpalhdlnbpafiamejdnhcphjbkeiagm",  # uBlock Origin
    "edibdbjcniadpccecjdfdjjppcpchdlm",  # I still don't care about cookies
    "lckanjgmijmafbedllaakclkaicjfmnk",  # ClearURLs
    "gidlfommnbibbmegmgajdbikelkdcmcl",  # Force Background Tab
]

# Default browser-use cache directory
DEFAULT_BROWSERUSE_EXTENSIONS_DIR = Path.home() / ".config" / "browseruse" / "extensions"


def get_bundled_extensions_dir() -> Path:
    """
    Get the path to bundled extensions directory.

    Supports both:
    - Development: deploy/bundled_extensions relative to project root
    - PyInstaller: bundled_extensions in sys._MEIPASS
    """
    # Check if running as PyInstaller bundle
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller extracts data files to sys._MEIPASS
        bundled_path = Path(sys._MEIPASS) / 'bundled_extensions'
        if bundled_path.exists():
            return bundled_path

    # Development mode: try multiple possible locations
    possible_paths = [
        # Relative to this file: extension_installer.py is at
        # src/clients/desktop_app/ami_daemon/base_agent/tools/browser_use/
        # deploy/bundled_extensions is at project root
        Path(__file__).resolve().parents[8] / "deploy" / "bundled_extensions",
        # Alternative calculation
        Path(__file__).parent.parent.parent.parent.parent.parent.parent.parent.parent / "deploy" / "bundled_extensions",
    ]

    for path in possible_paths:
        if path.exists():
            return path.resolve()

    # Fallback: return the first path even if it doesn't exist
    return possible_paths[0].resolve()


def ensure_extensions_installed(
    bundled_dir: Path | None = None,
    cache_dir: Path | None = None,
    force: bool = False
) -> bool:
    """
    Ensure bundled extensions are copied to browser-use cache directory.

    Supports both:
    - .crx files: Will be copied and browser-use will extract them automatically
    - Extracted directories: Will be copied directly

    Args:
        bundled_dir: Path to bundled extensions. Auto-detected if None.
        cache_dir: Path to browser-use cache directory. Uses default if None.
        force: If True, overwrite existing extensions.

    Returns:
        True if at least one extension is available, False otherwise.
    """
    bundled_dir = bundled_dir or get_bundled_extensions_dir()
    cache_dir = cache_dir or DEFAULT_BROWSERUSE_EXTENSIONS_DIR

    if not bundled_dir.exists():
        logger.warning(f"Bundled extensions directory not found: {bundled_dir}")
        logger.warning("Extensions will be downloaded from Google (may fail in China)")
        return False

    # Create cache directory if it doesn't exist
    cache_dir.mkdir(parents=True, exist_ok=True)

    installed_count = 0

    for ext_id in REQUIRED_EXTENSIONS:
        source_crx = bundled_dir / f"{ext_id}.crx"
        source_dir = bundled_dir / ext_id
        target_crx = cache_dir / f"{ext_id}.crx"
        target_dir = cache_dir / ext_id

        # Check if already installed (either as .crx or extracted directory)
        already_installed = (
            (target_crx.exists()) or
            (target_dir.exists() and (target_dir / "manifest.json").exists())
        )
        if already_installed and not force:
            logger.debug(f"Extension already available: {ext_id}")
            installed_count += 1
            continue

        # Try to copy .crx file first (preferred - browser-use will extract it)
        if source_crx.exists():
            try:
                shutil.copy2(source_crx, target_crx)
                logger.info(f"Installed extension (.crx): {ext_id}")
                installed_count += 1
                continue
            except Exception as e:
                logger.error(f"Failed to copy .crx for {ext_id}: {e}")

        # Fallback: copy extracted directory if available
        if source_dir.exists() and (source_dir / "manifest.json").exists():
            try:
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.copytree(source_dir, target_dir)
                logger.info(f"Installed extension (dir): {ext_id}")
                installed_count += 1
                continue
            except Exception as e:
                logger.error(f"Failed to copy directory for {ext_id}: {e}")

        logger.debug(f"Bundled extension not found: {ext_id}")

    if installed_count == len(REQUIRED_EXTENSIONS):
        logger.info(f"All {installed_count} extensions available")
        return True
    elif installed_count > 0:
        logger.info(f"{installed_count}/{len(REQUIRED_EXTENSIONS)} extensions available")
        return True
    else:
        logger.warning("No bundled extensions found")
        return False


def check_extensions_available(cache_dir: Path | None = None) -> dict[str, bool]:
    """
    Check which extensions are available in cache directory.

    Returns:
        Dict mapping extension ID to availability status.
    """
    cache_dir = cache_dir or DEFAULT_BROWSERUSE_EXTENSIONS_DIR

    result = {}
    for ext_id in REQUIRED_EXTENSIONS:
        crx_file = cache_dir / f"{ext_id}.crx"
        ext_dir = cache_dir / ext_id
        result[ext_id] = crx_file.exists() or (ext_dir.exists() and (ext_dir / "manifest.json").exists())

    return result
