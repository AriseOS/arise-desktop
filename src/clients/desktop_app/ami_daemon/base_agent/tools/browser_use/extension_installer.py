"""Browser extension installer for browser-use

This module handles installation of bundled browser extensions to avoid
downloading from external sources (useful in restricted network environments).

Currently no bundled extensions are included, so this is a no-op.
"""

import logging

logger = logging.getLogger(__name__)


def ensure_extensions_installed() -> bool:
    """Ensure browser extensions are installed in browser-use cache.

    This function checks if bundled browser extensions need to be installed
    and installs them if necessary. Currently returns True as no extensions
    are bundled.

    Returns:
        bool: True if extensions are ready (or no extensions needed),
              False if installation failed
    """
    # No bundled extensions currently - just return True
    logger.debug("No bundled browser extensions to install")
    return True
