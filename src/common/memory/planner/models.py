"""Planner Agent data models.

Defines data structures for the PlannerAgent's input/output:
- EnrichedPhrase: enriched Memory data for recall_phrases tool
- PlanStep / MemoryPlan / PlanResult: execution-oriented plan output
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.common.memory.ontology.action import Action
from src.common.memory.ontology.cognitive_phrase import CognitivePhrase
from src.common.memory.ontology.intent_sequence import IntentSequence
from src.common.memory.ontology.state import State


@dataclass
class EnrichedPhrase:
    """CognitivePhrase with fully resolved States, Actions, and IntentSequences.

    Used by PlannerTools.recall_phrases() to return complete workflow data
    so the PlannerAgent can inspect every step without additional queries.
    """

    phrase: CognitivePhrase
    states: List[State]
    actions: List[Action]
    state_sequences: Dict[str, List[IntentSequence]]  # state_id -> sequences

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON output."""
        steps = []
        for step in self.phrase.execution_plan:
            state = next(
                (s for s in self.states if s.id == step.state_id), None
            )
            if not state:
                continue

            # In-page operations for this step
            in_page_ops = []
            sequences = self.state_sequences.get(step.state_id, [])
            for seq in sequences:
                if seq.id in step.in_page_sequence_ids:
                    in_page_ops.append({
                        "id": seq.id,
                        "description": seq.description,
                        "intents": [
                            _intent_to_compact(intent)
                            for intent in (seq.intents or [])
                        ],
                    })

            # Navigation info
            navigation = None
            if step.navigation_action_id:
                action = next(
                    (a for a in self.actions if a.id == step.navigation_action_id),
                    None,
                )
                if action:
                    navigation = {
                        "action_id": action.id,
                        "target_state": action.target,
                        "description": action.description,
                    }
                    if action.trigger:
                        navigation["trigger"] = action.trigger

            # Navigation sequence
            nav_sequence = None
            if step.navigation_sequence_id:
                for seq in sequences:
                    if seq.id == step.navigation_sequence_id:
                        nav_sequence = {
                            "id": seq.id,
                            "description": seq.description,
                            "intents": [
                                _intent_to_compact(intent)
                                for intent in (seq.intents or [])
                            ],
                        }
                        break

            steps.append({
                "index": step.index,
                "state": {
                    "id": state.id,
                    "page_url": state.page_url,
                    "page_title": state.page_title,
                    "description": state.description,
                },
                "in_page_operations": in_page_ops,
                "navigation": navigation,
                "navigation_sequence": nav_sequence,
            })

        return {
            "id": self.phrase.id,
            "label": self.phrase.label,
            "description": self.phrase.description,
            "steps": steps,
        }


def _intent_to_compact(intent) -> Dict[str, Any]:
    """Convert an Intent to a compact dict for serialization."""
    if isinstance(intent, dict):
        return {
            "type": intent.get("type", ""),
            "text": intent.get("text"),
            "ref": intent.get("element_ref") or intent.get("ref"),
            "role": intent.get("element_role") or intent.get("role"),
        }
    return {
        "type": getattr(intent, "type", ""),
        "text": getattr(intent, "text", None),
        "ref": getattr(intent, "element_ref", None) or getattr(intent, "ref", None),
        "role": getattr(intent, "element_role", None) or getattr(intent, "role", None),
    }


@dataclass
class PlanStep:
    """A single step in the execution plan.

    Each step is a concrete action with optional Memory backing.
    """

    index: int  # Sequential step number
    content: str  # Actionable instruction text
    source: str = "none"  # "phrase" | "graph" | "none"
    phrase_id: Optional[str] = None  # CognitivePhrase ID (source=phrase)
    state_ids: List[str] = field(default_factory=list)  # State IDs (source=graph)
    workflow_guide: str = ""  # Detailed guide extracted from tool results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "content": self.content,
            "source": self.source,
            "phrase_id": self.phrase_id,
            "state_ids": self.state_ids,
            "workflow_guide": self.workflow_guide,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanStep":
        # "content" is the new field; "summary" is the old field name
        content = data.get("content", "") or data.get("summary", "")
        return cls(
            index=data.get("index", 0),
            content=content,
            source=data.get("source", "none"),
            phrase_id=data.get("phrase_id"),
            state_ids=data.get("state_ids", []),
            workflow_guide=data.get("workflow_guide", ""),
        )



@dataclass
class MemoryPlan:
    """Parsed <memory_plan> output from PlannerAgent.

    Contains an execution-oriented step plan with optional Memory backing,
    plus observed user preferences.
    """

    steps: List[PlanStep] = field(default_factory=list)
    preferences: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "preferences": self.preferences,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryPlan":
        steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            steps=steps,
            preferences=data.get("preferences", []),
        )


@dataclass
class PlanResult:
    """Complete output of PlannerAgent.plan().

    Contains a MemoryPlan (execution-oriented step plan).
    Serializable for HTTP transport between Cloud Backend and Client.
    """

    memory_plan: MemoryPlan = field(default_factory=MemoryPlan)
    debug_trace: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_plan": self.memory_plan.to_dict(),
            "debug_trace": self.debug_trace,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanResult":
        memory_plan_data = data.get("memory_plan", {})
        debug_trace = data.get("debug_trace", {})
        if not isinstance(debug_trace, dict):
            debug_trace = {}
        return cls(
            memory_plan=MemoryPlan.from_dict(memory_plan_data),
            debug_trace=debug_trace,
        )
