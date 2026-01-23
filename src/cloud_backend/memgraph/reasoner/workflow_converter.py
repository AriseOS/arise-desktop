"""Workflow Converter - Converts states and actions to workflow JSON."""

import uuid
from typing import Any, Dict, List, Optional

from src.cloud_backend.memgraph.ontology.action import Action
from src.cloud_backend.memgraph.ontology.cognitive_phrase import CognitivePhrase
from src.cloud_backend.memgraph.ontology.state import State


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
            # Build intent_sequences from state (new structure)
            intent_sequences_data = []
            if state.intent_sequences:
                for seq in state.intent_sequences:
                    seq_data = seq.to_dict() if hasattr(seq, "to_dict") else seq
                    intent_sequences_data.append(seq_data)

            # Fallback to old intents if intent_sequences is empty (backward compatibility)
            intents_data = []
            if not intent_sequences_data and state.intents:
                intents_data = [
                    intent.to_dict() if hasattr(intent, "to_dict") else intent
                    for intent in state.intents
                ]

            step = {
                "step_id": f"step_{i + 1}",
                "state_id": state.id,
                "page_url": state.page_url,
                "page_title": state.page_title,
                "description": state.description,
                "timestamp": state.timestamp,
                "intent_sequences": intent_sequences_data,  # New: full intent sequences
                "intents": intents_data,  # Backward compatibility
            }

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
