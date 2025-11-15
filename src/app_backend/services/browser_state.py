"""Browser state definitions"""
from enum import Enum


class BrowserState(Enum):
    """Browser lifecycle states"""

    NOT_STARTED = "not_started"  # Browser has not been started yet
    STARTING = "starting"         # Browser is starting up (2-3 seconds)
    RUNNING = "running"           # Browser is running normally
    STOPPING = "stopping"         # Browser is shutting down
    STOPPED = "stopped"           # Browser has stopped
    ERROR = "error"               # Browser encountered an error

    def __str__(self):
        return self.value
