"""Execution task data model"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class ExecutionTask:
    """Workflow execution task"""

    task_id: str
    workflow_id: str  # System identifier like "workflow_75a80ae0a48f"
    workflow_name: str  # Human-readable name like "watcha-extract-all-products"
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
    steps: List[Dict[str, Any]] = field(default_factory=list)  # List of step info for timeline
