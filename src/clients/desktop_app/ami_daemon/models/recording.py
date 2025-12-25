"""Recording session data model"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class RecordingSession:
    """Recording session stored in memory during recording"""

    session_id: str
    user_id: str
    created_at: datetime = field(default_factory=datetime.now)
    is_recording: bool = True
    operation_list: List[dict] = field(default_factory=list)
    stopped_at: Optional[datetime] = None

    def stop(self):
        """Stop recording and set timestamp"""
        self.is_recording = False
        self.stopped_at = datetime.now()

    def to_file_format(self) -> dict:
        """Convert to file format for storage"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "total_operations": len(self.operation_list),
            "operations": self.operation_list
        }
