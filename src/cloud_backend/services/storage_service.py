"""
Storage Service - Server local filesystem management (Cloud Backend)

Storage paths:
- Development: ~/ami-server
- Production: /var/lib/ami-server/ (or via STORAGE_PATH env var)

Directory structure:
~/ami-server/
├── users/{user_id}/
│   └── (memory data managed by graph store)
└── database/
    └── ami.db
"""

from pathlib import Path
import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class StorageService:
    """Server local filesystem manager"""

    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize Cloud Backend storage service

        Args:
            base_path: Base path (optional)
                Development: ~/ami-server (default)
                Production: /var/lib/ami-server/ (via STORAGE_PATH env var)
        """
        if base_path:
            self.base_path = Path(base_path).expanduser()
        else:
            default_path = os.getenv("STORAGE_PATH", "~/ami-server")
            self.base_path = Path(default_path).expanduser()

        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Cloud Backend Storage initialized: {self.base_path}")

    def _user_path(self, user_id: str) -> Path:
        """Get user directory"""
        path = self.base_path / "users" / str(user_id)
        path.mkdir(parents=True, exist_ok=True)
        return path
