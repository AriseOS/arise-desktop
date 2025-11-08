"""Execution task data model"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ExecutionTask:
    """Workflow execution task"""

    task_id: str
    workflow_name: str
    user_id: str
    status: str  # running, completed, failed
    progress: int  # 0-100
    current_step: int
    total_steps: int
    message: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[dict] = None
    error: Optional[str] = None
