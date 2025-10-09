"""Workflow Converter - Converts states and actions to workflow JSON."""

import uuid
from typing import Any, Dict, List, Optional

from src.ontology.action import Action
from src.ontology.cognitive_phrase import CognitivePhrase
from src.ontology.state import State


class WorkflowConverter:
    """Converts states and actions to workflow JSON."""

    def convert(
        self,
        target: str,
        states: List[State],
        actions: List[Action],
        cognitive_phrases: Optional[List[CognitivePhrase]] = None,
    ) -> Dict[str, Any]:
        """Convert to workflow JSON.

        Args:
            target: Target description.
            states: List of states.
            actions: List of actions.
            cognitive_phrases: Optional cognitive phrases used.

        Returns:
            Workflow JSON dictionary.
        """
        workflow = {
            "workflow_id": str(uuid.uuid4()),
            "target": target,
            "steps": [],
            "metadata": {
                "num_states": len(states),
                "num_actions": len(actions),
            },
        }

        # Build steps from states and actions
        for i, state in enumerate(states):
            step = {
                "step_id": f"step_{i + 1}",
                "state_id": state.id,
                "state_label": state.label,
                "state_type": state.type.value,
                "page_url": state.page_url,
                "intents": [
                    intent.to_dict() if hasattr(intent, "to_dict") else intent
                    for intent in state.atomic_intents
                ],
            }

            # Add action if exists
            if i < len(actions):
                action = actions[i]
                step["action"] = {
                    "type": action.type,
                    "source": action.source,
                    "target": action.target,
                    "attributes": action.attributes,
                }

            workflow["steps"].append(step)

        # Add cognitive phrase info if available
        if cognitive_phrases:
            workflow["metadata"]["cognitive_phrases"] = [
                {"id": p.id, "label": p.label} for p in cognitive_phrases
            ]

        return workflow


__all__ = ["WorkflowConverter"]
