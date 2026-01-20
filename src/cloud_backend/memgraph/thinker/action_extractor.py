"""Action Extractor - Extracts state transitions (actions) using LLM.

This module uses LLM to identify Actions (state transitions that cause navigation).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.cloud_backend.memgraph.ontology.action import Action
from src.cloud_backend.memgraph.ontology.state import State
from src.cloud_backend.memgraph.services.llm import LLMClient, LLMMessage, LLMResponse
from src.cloud_backend.memgraph.thinker.prompts.action_extraction_prompt import (
    ActionExtractionInput,
    ActionExtractionPrompt,
)


class ActionExtractionResult:
    """Result of action extraction.

    Attributes:
        actions: List of extracted Action objects
        extraction_metadata: Metadata about extraction
        llm_response: Raw LLM response
        timestamp: When extraction was performed
    """

    def __init__(
        self,
        actions: List[Action],
        extraction_metadata: Dict[str, Any],
        llm_response: str
    ):
        """Initialize extraction result.

        Args:
            actions: List of Action objects
            extraction_metadata: Extraction metadata
            llm_response: Raw LLM response
        """
        self.actions = actions
        self.extraction_metadata = extraction_metadata
        self.llm_response = llm_response
        self.timestamp = datetime.now()


class ActionExtractor:
    """Extractor for identifying actions (state transitions) using LLM.

    Uses LLM to analyze state sequences and identify Actions that represent
    navigation events causing state transitions.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        model_name: str = "gpt-4"
    ):
        """Initialize ActionExtractor.

        Args:
            llm_client: LLM client for extraction (required)
            model_name: Name of LLM model to use

        Raises:
            ValueError: If llm_client is None
        """
        if not llm_client:
            raise ValueError("LLM client is required for ActionExtractor")

        self.llm_client = llm_client
        self.model_name = model_name
        self.prompt = ActionExtractionPrompt()

    def extract_actions(
        self,
        states: List[State],
        workflow_data: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> ActionExtractionResult:
        """Extract actions from state sequence using LLM.

        Args:
            states: List of State objects (ordered by timestamp)
            workflow_data: Optional workflow events for additional context
            user_id: User ID
            session_id: Session ID

        Returns:
            ActionExtractionResult containing extracted actions

        Raises:
            ValueError: If input is invalid
        """
        if not states:
            raise ValueError("States list is empty")

        if len(states) < 2:
            # No transitions possible with less than 2 states
            return ActionExtractionResult(
                actions=[],
                extraction_metadata={
                    "extraction_method": "llm",
                    "action_count": 0,
                    "state_count": len(states),
                    "note": "Less than 2 states, no transitions possible"
                },
                llm_response="no_transitions"
            )

        # Format states for prompt
        states_summary = self._format_states_for_prompt(states)

        # Build prompt using prompt object
        prompt_input = ActionExtractionInput(states_summary=states_summary)

        # Validate input
        if not self.prompt.validate_input(prompt_input):
            raise ValueError("Invalid prompt input: no states summary provided")

        user_prompt = self.prompt.build_prompt(prompt_input)
        system_prompt = self.prompt.get_system_prompt()

        # Call LLM
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt)
        ]

        response: LLMResponse = self.llm_client.generate(
            messages,
            temperature=0.1,
            max_tokens=4000
        )

        # Parse response using prompt object
        parsed_output = self.prompt.parse_response(response.content)

        # Validate output (actions can be empty, so always valid)
        if not self.prompt.validate_output(parsed_output):
            raise ValueError("LLM returned invalid output")

        # Create Action objects from parsed output
        actions = []
        state_id_map = {i: state.id for i, state in enumerate(states)}

        for action_data in parsed_output.actions:
            source_idx = action_data.source_index
            target_idx = action_data.target_index

            # Validate indices
            if source_idx not in state_id_map or target_idx not in state_id_map:
                print(f"Warning: Invalid state index {source_idx} or {target_idx}")
                continue

            if source_idx == target_idx:
                print(f"Warning: Source and target are the same ({source_idx})")
                continue

            # Create Action
            try:
                action = Action(
                    source=state_id_map[source_idx],
                    target=state_id_map[target_idx],
                    type=action_data.type,
                    timestamp=action_data.timestamp,
                    trigger_intent_id=action_data.trigger_intent_id,
                    user_id=user_id,
                    session_id=session_id,
                    attributes=action_data.attributes
                )
                actions.append(action)

            except Exception as action_err:
                print(f"Warning: Failed to create action: {str(action_err)}")
                continue

        # Build metadata
        metadata = {
            "extraction_method": "llm",
            "llm_model": self.model_name,
            "action_count": len(actions),
            "state_count": len(states),
            "possible_transitions": len(states) * (len(states) - 1),
            "actual_transitions": len(actions)
        }

        return ActionExtractionResult(
            actions=actions,
            extraction_metadata=metadata,
            llm_response=response.content
        )

    def _format_states_for_prompt(self, states: List[State]) -> str:
        """Format states for LLM prompt.

        Args:
            states: List of State objects

        Returns:
            Formatted states string
        """
        lines = []
        for i, state in enumerate(states):
            intent_count = len(state.intents) if state.intents else 0
            duration = state.duration if state.duration else "unknown"

            state_desc = (
                f"{i}. {state.page_url}\n"
                f"   - Title: {state.page_title or 'N/A'}\n"
                f"   - Timestamp: {state.timestamp}\n"
                f"   - Duration: {duration}ms\n"
                f"   - Intents: {intent_count} operations"
            )
            lines.append(state_desc)

        return '\n'.join(lines)


__all__ = [
    "ActionExtractor",
    "ActionExtractionResult",
]
