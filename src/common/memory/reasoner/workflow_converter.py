"""Workflow Converter - Converts states and actions to workflow JSON."""

import uuid
from typing import Any, Dict, List, Optional

from src.common.memory.ontology.action import Action
from src.common.memory.ontology.cognitive_phrase import CognitivePhrase
from src.common.memory.ontology.intent_sequence import IntentSequence
from src.common.memory.ontology.state import State


class WorkflowConverter:
    """Converts states and actions to workflow JSON."""

    def convert(
        self,
        target: str,
        states: List[State],
        actions: List[Action],
        cognitive_phrases: Optional[List[CognitivePhrase]] = None,
        state_sequences: Optional[Dict[str, List[IntentSequence]]] = None,
    ) -> Dict[str, Any]:
        """Convert to workflow JSON.

        Args:
            target: Target description.
            states: List of states.
            actions: List of actions.
            cognitive_phrases: Optional cognitive phrases used.
            state_sequences: Optional mapping of state_id -> List[IntentSequence].
                If provided, intent_sequences are included in each step.

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
                "page_url": state.page_url,
                "page_title": state.page_title,
                "description": state.description,
                "timestamp": state.timestamp,
            }

            # Add intent_sequences if provided via state_sequences mapping
            if state_sequences and state.id in state_sequences:
                step["intent_sequences"] = [
                    seq.to_dict() if hasattr(seq, "to_dict") else seq
                    for seq in state_sequences[state.id]
                ]

            # Add action if exists
            if i < len(actions):
                action = actions[i]
                step["action"] = {
                    "type": action.type,
                    "source": action.source,
                    "target": action.target,
                    "timestamp": action.timestamp,
                    "attributes": action.attributes,
                }

            workflow["steps"].append(step)

        # Add cognitive phrase info if available
        if cognitive_phrases:
            workflow["metadata"]["cognitive_phrases"] = [
                {"id": p.id, "description": p.description} for p in cognitive_phrases
            ]

        return workflow


__all__ = ["WorkflowConverter"]
