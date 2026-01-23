"""API Routers"""

from .quick_task import router as quick_task_router
from .integrations import router as integrations_router
from .settings import router as settings_router

__all__ = [
    "quick_task_router",
    "integrations_router",
    "settings_router",
]
