"""
WorkflowWorkspace - Execution record for workflow error recovery.

Each workflow has one workspace that records:
- All step execution results
- Error details for failed steps
- Context for recovery agent to understand what happened
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)


@dataclass
class StepRecord:
    """Record for a single step execution."""

    step_id: str
    step_name: str
    agent_type: str

    # Task info
    task_description: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    expected_outputs: List[str] = field(default_factory=list)

    # Execution result
    status: Literal["pending", "running", "success", "failed", "recovered"] = "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # Page context
    page_url: Optional[str] = None
    page_title: Optional[str] = None

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "step_id": self.step_id,
            "step_name": self.step_name,
            "agent_type": self.agent_type,
            "task_description": self.task_description,
            "inputs": self.inputs,
            "expected_outputs": self.expected_outputs,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "page_url": self.page_url,
            "page_title": self.page_title,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def to_markdown(self) -> str:
        """Convert to markdown format for LLM context."""
        lines = []
        lines.append(f"## Step: {self.step_name} ({self.agent_type})")
        lines.append(f"**ID:** {self.step_id}")

        # Status with emoji
        status_emoji = {
            "pending": "⏳",
            "running": "🔄",
            "success": "✅",
            "failed": "❌",
            "recovered": "🔧",
        }
        lines.append(f"**Status:** {status_emoji.get(self.status, '?')} {self.status.upper()}")

        if self.task_description:
            lines.append(f"**Task:** {self.task_description}")

        if self.page_url:
            lines.append(f"**URL:** {self.page_url}")

        if self.page_title:
            lines.append(f"**Page Title:** {self.page_title}")

        if self.result:
            lines.append("\n**Result:**")
            lines.append("```json")
            lines.append(json.dumps(self.result, indent=2, ensure_ascii=False))
            lines.append("```")

        if self.error:
            lines.append("\n**Error:**")
            lines.append(f"```\n{self.error}\n```")

        if self.expected_outputs:
            lines.append("\n**Expected Outputs:**")
            for output in self.expected_outputs:
                lines.append(f"- {output}")

        lines.append("")  # Empty line between steps
        return "\n".join(lines)


class WorkflowWorkspace:
    """
    Workspace for workflow execution.

    Records all step executions and provides context for error recovery.
    """

    def __init__(
        self,
        workflow_id: str,
        workflow_name: str,
        user_id: str,
        base_path: Optional[Path] = None,
    ):
        self.workflow_id = workflow_id
        self.workflow_name = workflow_name
        self.user_id = user_id
        self.started_at = datetime.now()

        # Step records
        self.step_records: List[StepRecord] = []
        self._current_step: Optional[StepRecord] = None

        # Status
        self.status: Literal["running", "completed", "failed", "recovering"] = "running"

        # Storage path
        if base_path:
            self.workspace_path = base_path / "workspace"
        else:
            self.workspace_path = (
                Path.home() / ".ami" / "users" / user_id / "workflows" / workflow_id / "workspace"
            )
        self.workspace_path.mkdir(parents=True, exist_ok=True)

    def start_step(
        self,
        step_id: str,
        step_name: str,
        agent_type: str,
        task_description: str = "",
        inputs: Optional[Dict[str, Any]] = None,
        expected_outputs: Optional[List[str]] = None,
    ) -> StepRecord:
        """Start recording a new step."""
        record = StepRecord(
            step_id=step_id,
            step_name=step_name,
            agent_type=agent_type,
            task_description=task_description,
            inputs=inputs or {},
            expected_outputs=expected_outputs or [],
            status="running",
            started_at=datetime.now(),
        )
        self.step_records.append(record)
        self._current_step = record
        logger.info(f"[Workspace] Started step: {step_name} ({step_id})")
        return record

    def update_step_context(
        self,
        page_url: Optional[str] = None,
        page_title: Optional[str] = None,
    ):
        """Update current step with page context."""
        if self._current_step:
            if page_url:
                self._current_step.page_url = page_url
            if page_title:
                self._current_step.page_title = page_title

    def complete_step(
        self,
        result: Dict[str, Any],
        message: Optional[str] = None,
    ):
        """Mark current step as completed successfully."""
        if self._current_step:
            self._current_step.status = "success"
            self._current_step.result = result
            self._current_step.completed_at = datetime.now()
            logger.info(f"[Workspace] Completed step: {self._current_step.step_name}")
            self._current_step = None

    def fail_step(
        self,
        error: str,
        page_url: Optional[str] = None,
        page_title: Optional[str] = None,
    ):
        """Mark current step as failed."""
        if self._current_step:
            self._current_step.status = "failed"
            self._current_step.error = error
            self._current_step.completed_at = datetime.now()
            if page_url:
                self._current_step.page_url = page_url
            if page_title:
                self._current_step.page_title = page_title
            logger.warning(f"[Workspace] Failed step: {self._current_step.step_name} - {error}")
            # Don't clear _current_step, recovery might need it

    def recover_step(
        self,
        result: Dict[str, Any],
    ):
        """Mark current step as recovered."""
        if self._current_step:
            self._current_step.status = "recovered"
            self._current_step.result = result
            self._current_step.completed_at = datetime.now()
            logger.info(f"[Workspace] Recovered step: {self._current_step.step_name}")
            self._current_step = None

    def get_failed_step(self) -> Optional[StepRecord]:
        """Get the most recent failed step."""
        for record in reversed(self.step_records):
            if record.status == "failed":
                return record
        return None

    def get_current_step(self) -> Optional[StepRecord]:
        """Get the current running step."""
        return self._current_step

    def to_markdown(self, include_successful_results: bool = True) -> str:
        """
        Convert workspace to markdown format for LLM context.

        Args:
            include_successful_results: If True, include full results for successful steps.
                                       If False, only show summary for successful steps.
        """
        lines = []
        lines.append(f"# Workflow: {self.workflow_name}")
        lines.append(f"**ID:** {self.workflow_id}")
        lines.append(f"**Started:** {self.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Status:** {self.status}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for i, record in enumerate(self.step_records, 1):
            if not include_successful_results and record.status == "success":
                # Abbreviated format for successful steps
                lines.append(f"## Step {i}: {record.step_name}")
                lines.append(f"**Status:** ✅ SUCCESS")
                if record.page_url:
                    lines.append(f"**URL:** {record.page_url}")
                lines.append("")
            else:
                # Full format
                lines.append(f"## Step {i}: {record.step_name}")
                lines.append(record.to_markdown()[len(f"## Step: {record.step_name}"):].strip())
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert workspace to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "user_id": self.user_id,
            "started_at": self.started_at.isoformat(),
            "status": self.status,
            "step_records": [r.to_dict() for r in self.step_records],
        }

    async def save(self):
        """Save workspace to disk."""
        try:
            # Save JSON format
            json_path = self.workspace_path / "workspace.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

            # Save Markdown format
            md_path = self.workspace_path / "workspace.md"
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(self.to_markdown())

            logger.info(f"[Workspace] Saved to {self.workspace_path}")

        except Exception as e:
            logger.error(f"[Workspace] Failed to save: {e}")

    @classmethod
    def load(cls, workflow_id: str, user_id: str) -> Optional["WorkflowWorkspace"]:
        """Load workspace from disk."""
        try:
            workspace_path = (
                Path.home() / ".ami" / "users" / user_id / "workflows" / workflow_id / "workspace"
            )
            json_path = workspace_path / "workspace.json"

            if not json_path.exists():
                return None

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            workspace = cls(
                workflow_id=data["workflow_id"],
                workflow_name=data["workflow_name"],
                user_id=data["user_id"],
            )
            workspace.started_at = datetime.fromisoformat(data["started_at"])
            workspace.status = data["status"]

            for record_data in data["step_records"]:
                record = StepRecord(
                    step_id=record_data["step_id"],
                    step_name=record_data["step_name"],
                    agent_type=record_data["agent_type"],
                    task_description=record_data.get("task_description", ""),
                    inputs=record_data.get("inputs", {}),
                    expected_outputs=record_data.get("expected_outputs", []),
                    status=record_data["status"],
                    result=record_data.get("result"),
                    error=record_data.get("error"),
                    page_url=record_data.get("page_url"),
                    page_title=record_data.get("page_title"),
                )
                if record_data.get("started_at"):
                    record.started_at = datetime.fromisoformat(record_data["started_at"])
                if record_data.get("completed_at"):
                    record.completed_at = datetime.fromisoformat(record_data["completed_at"])
                workspace.step_records.append(record)

            return workspace

        except Exception as e:
            logger.error(f"[Workspace] Failed to load: {e}")
            return None

    def get_context_for_recovery(self) -> str:
        """
        Get formatted context for recovery agent.

        Returns a markdown string optimized for the recovery agent to understand
        what happened and what needs to be fixed.
        """
        failed_step = self.get_failed_step()
        if not failed_step:
            return "No failed step found."

        lines = []
        lines.append("# Error Recovery Context")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append(f"Workflow '{self.workflow_name}' failed at step '{failed_step.step_name}'.")
        lines.append("")

        # Failed step details
        lines.append("## Failed Step Details")
        lines.append(f"- **Step ID:** {failed_step.step_id}")
        lines.append(f"- **Step Name:** {failed_step.step_name}")
        lines.append(f"- **Agent Type:** {failed_step.agent_type}")
        lines.append(f"- **Task:** {failed_step.task_description}")
        if failed_step.page_url:
            lines.append(f"- **Current URL:** {failed_step.page_url}")
        lines.append("")

        lines.append("### Error")
        lines.append(f"```\n{failed_step.error}\n```")
        lines.append("")

        if failed_step.expected_outputs:
            lines.append("### Expected Outputs")
            for output in failed_step.expected_outputs:
                lines.append(f"- {output}")
            lines.append("")

        # Previous steps context
        lines.append("## Previous Steps")
        successful_steps = [r for r in self.step_records if r.status == "success"]
        if successful_steps:
            for i, step in enumerate(successful_steps, 1):
                lines.append(f"\n### Step {i}: {step.step_name}")
                lines.append(f"- **Status:** ✅ Success")
                if step.page_url:
                    lines.append(f"- **URL:** {step.page_url}")
                if step.result:
                    # Truncate large results
                    result_str = json.dumps(step.result, ensure_ascii=False)
                    if len(result_str) > 500:
                        result_str = result_str[:500] + "... (truncated)"
                    lines.append(f"- **Result:** `{result_str}`")
        else:
            lines.append("No previous successful steps.")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Instructions for Recovery")
        lines.append("")
        lines.append("Please analyze the error and attempt to fix it. You can:")
        lines.append("1. Check the current page state with `browser_get_page_snapshot`")
        lines.append("2. Navigate or interact with the page as needed")
        lines.append("3. Try alternative approaches to achieve the step's goal")
        lines.append("4. Return the expected output data when successful")

        return "\n".join(lines)
