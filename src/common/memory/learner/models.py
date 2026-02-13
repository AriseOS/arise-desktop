"""Learner Agent data models.

Defines data structures for the LearnerAgent's input/output:
- ToolUseRecord: Single tool use extracted from agent messages
- SubtaskExecutionData: Execution data for one subtask
- TaskExecutionData: Full task execution data (input to LearnerAgent)
- PhraseCandidate: A single phrase candidate from LLM coverage analysis
- LearningPlan: LLM's coverage analysis and phrase candidates
- LearnResult: Final output of LearnerAgent.learn()
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolUseRecord:
    """A single tool use extracted from agent messages."""

    thinking: str = ""  # Agent's reasoning before tool call
    tool_name: str = ""
    input_summary: str = ""  # Compressed tool input
    success: bool = True
    result_summary: str = ""  # Compressed tool result
    judgment: str = ""  # Agent's assessment after tool result
    current_url: str = ""  # URL at time of tool use

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thinking": self.thinking,
            "tool_name": self.tool_name,
            "input_summary": self.input_summary,
            "success": self.success,
            "result_summary": self.result_summary,
            "judgment": self.judgment,
            "current_url": self.current_url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolUseRecord":
        return cls(
            thinking=data.get("thinking", ""),
            tool_name=data.get("tool_name", ""),
            input_summary=data.get("input_summary", ""),
            success=data.get("success", True),
            result_summary=data.get("result_summary", ""),
            judgment=data.get("judgment", ""),
            current_url=data.get("current_url", ""),
        )


@dataclass
class SubtaskExecutionData:
    """Execution data for one subtask."""

    subtask_id: str = ""
    content: str = ""  # Subtask description
    agent_type: str = ""
    depends_on: List[str] = field(default_factory=list)
    state: str = ""  # "DONE" or "FAILED"
    result_summary: str = ""  # Short summary of subtask result
    tool_records: List[ToolUseRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "content": self.content,
            "agent_type": self.agent_type,
            "depends_on": self.depends_on,
            "state": self.state,
            "result_summary": self.result_summary,
            "tool_records": [r.to_dict() for r in self.tool_records],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubtaskExecutionData":
        return cls(
            subtask_id=data.get("subtask_id", ""),
            content=data.get("content", ""),
            agent_type=data.get("agent_type", ""),
            depends_on=data.get("depends_on", []),
            state=data.get("state", ""),
            result_summary=data.get("result_summary", ""),
            tool_records=[
                ToolUseRecord.from_dict(r)
                for r in data.get("tool_records", [])
            ],
        )


@dataclass
class TaskExecutionData:
    """Full task execution data - input to LearnerAgent."""

    task_id: str = ""
    user_request: str = ""
    subtasks: List[SubtaskExecutionData] = field(default_factory=list)
    completed_count: int = 0
    failed_count: int = 0
    total_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_request": self.user_request,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "total_count": self.total_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskExecutionData":
        return cls(
            task_id=data.get("task_id", ""),
            user_request=data.get("user_request", ""),
            subtasks=[
                SubtaskExecutionData.from_dict(s)
                for s in data.get("subtasks", [])
            ],
            completed_count=data.get("completed_count", 0),
            failed_count=data.get("failed_count", 0),
            total_count=data.get("total_count", 0),
        )


@dataclass
class PhraseCandidate:
    """A single phrase candidate from LLM coverage analysis."""

    should_create: bool = True
    description: str = ""
    label: str = ""
    effective_state_ids: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_create": self.should_create,
            "description": self.description,
            "label": self.label,
            "effective_state_ids": self.effective_state_ids,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhraseCandidate":
        return cls(
            should_create=data.get("should_create", True),
            description=data.get("description", ""),
            label=data.get("label", ""),
            effective_state_ids=data.get("effective_state_ids", []),
            reason=data.get("reason", ""),
        )


@dataclass
class LearningPlan:
    """LLM's coverage analysis and phrase candidates."""

    coverage_judgment: str = ""  # LLM reasoning (debug only)
    phrase_candidates: List[PhraseCandidate] = field(default_factory=list)

    @property
    def should_create_phrase(self) -> bool:
        """Backward compat: true if any candidate should be created."""
        return any(c.should_create for c in self.phrase_candidates)

    @property
    def reason(self) -> str:
        """Backward compat: first candidate's reason or coverage_judgment."""
        if self.phrase_candidates:
            return self.phrase_candidates[0].reason
        return self.coverage_judgment or "No phrase candidates"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "coverage_judgment": self.coverage_judgment,
            "phrase_candidates": [c.to_dict() for c in self.phrase_candidates],
            "should_create_phrase": self.should_create_phrase,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningPlan":
        candidates = [
            PhraseCandidate.from_dict(c)
            for c in data.get("phrase_candidates", [])
        ]
        return cls(
            coverage_judgment=data.get("coverage_judgment", ""),
            phrase_candidates=candidates,
        )


@dataclass
class LearnResult:
    """Final output of LearnerAgent.learn()."""

    phrase_created: bool = False
    phrase_id: Optional[str] = None  # First phrase ID (backward compat)
    phrase_ids: List[str] = field(default_factory=list)  # All created phrase IDs
    learning_plan: LearningPlan = field(default_factory=LearningPlan)
    debug_trace: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phrase_created": self.phrase_created,
            "phrase_id": self.phrase_id,
            "phrase_ids": self.phrase_ids,
            "learning_plan": self.learning_plan.to_dict(),
            "debug_trace": self.debug_trace,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearnResult":
        lp_data = data.get("learning_plan", {})
        debug_trace = data.get("debug_trace", {})
        if not isinstance(debug_trace, dict):
            debug_trace = {}
        return cls(
            phrase_created=data.get("phrase_created", False),
            phrase_id=data.get("phrase_id"),
            phrase_ids=data.get("phrase_ids", []),
            learning_plan=LearningPlan.from_dict(lp_data),
            debug_trace=debug_trace,
        )
