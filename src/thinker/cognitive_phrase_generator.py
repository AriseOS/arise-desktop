"""Cognitive Phrase Generator - Generates CognitivePhrases from States and Actions.

This module uses LLM to synthesize high-level cognitive phrases from semantic
states and actions, representing complete user tasks or goals.
"""

from typing import Any, Dict, List, Optional

from src.ontology.action import Action
from src.ontology.cognitive_phrase import CognitivePhrase
from src.ontology.state import State
from src.services.llm import LLMClient, LLMMessage, LLMResponse
from src.thinker.prompts.cognitive_phrase_prompt import CognitivePhrasePrompt


class CognitivePhraseGenerationResult:
    """Result of cognitive phrase generation."""

    def __init__(
        self,
        phrases: List[CognitivePhrase],
        metadata: Dict[str, Any],
        llm_response: str
    ):
        """Initialize generation result.

        Args:
            phrases: List of generated CognitivePhrase objects
            metadata: Generation metadata
            llm_response: Raw LLM response
        """
        self.phrases = phrases
        self.metadata = metadata
        self.llm_response = llm_response


class CognitivePhraseGenerator:
    """Generator for creating CognitivePhrases from States and Actions.

    Uses LLM to synthesize high-level cognitive phrases representing
    complete user tasks or goals.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None
    ):
        """Initialize CognitivePhraseGenerator.

        Args:
            llm_client: LLM client for generation (optional)
        """
        self.llm_client = llm_client
        self.prompt = CognitivePhrasePrompt()

    def generate_phrases(
        self,
        states: List[State],
        actions: List[Action],
        use_llm: bool = True
    ) -> CognitivePhraseGenerationResult:
        """Generate cognitive phrases from states and actions.

        Args:
            states: List of State objects
            actions: List of Action objects
            use_llm: Whether to use LLM for generation (default: True)

        Returns:
            CognitivePhraseGenerationResult

        Raises:
            ValueError: If input is invalid
        """
        input_data = {"states": states, "actions": actions}

        if not self.prompt.validate_input(input_data):
            raise ValueError("Invalid input: states list is empty")

        if use_llm and self.llm_client:
            return self._generate_with_llm(states, actions)

        return self._generate_rule_based(states, actions)

    def _generate_with_llm(
        self,
        states: List[State],
        actions: List[Action]
    ) -> CognitivePhraseGenerationResult:
        """Generate phrases using LLM.

        Args:
            states: List of State objects
            actions: List of Action objects

        Returns:
            CognitivePhraseGenerationResult
        """
        try:
            # Build prompt
            input_data = {"states": states, "actions": actions}
            user_prompt = self.prompt.build_prompt(input_data)
            system_prompt = self.prompt.get_system_prompt()

            # Call LLM
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt)
            ]
            response: LLMResponse = self.llm_client.generate(
                messages,
                temperature=0.1,
                max_tokens=6000
            )

            # Parse response
            phrases = self.prompt.parse_response(response.content)

            # Parse metadata
            data = self.prompt.parse_json_response(response.content)
            metadata = data.get("metadata", {})

            # Populate state and action references
            for phrase in phrases:
                # Add state references
                state_map = {state.id: state for state in states}
                phrase.states = [
                    state_map[sid] for sid in phrase.state_ids
                    if sid in state_map
                ]

                # Add action references (actions connecting phrase states)
                phrase_state_ids = set(phrase.state_ids)
                phrase.actions = [
                    action for action in actions
                    if action.source in phrase_state_ids and action.target in phrase_state_ids
                ]

            return CognitivePhraseGenerationResult(
                phrases=phrases,
                metadata=metadata,
                llm_response=response.content
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Intentionally catch all exceptions for fallback to rule-based method
            print(f"LLM phrase generation failed, falling back to rule-based: {str(e)}")
            return self._generate_rule_based(states, actions)

    def _generate_rule_based(
        self,
        states: List[State],
        actions: List[Action]
    ) -> CognitivePhraseGenerationResult:
        """Generate phrases using rule-based approach.

        Creates a single cognitive phrase encompassing all states.

        Args:
            states: List of State objects
            actions: List of Action objects

        Returns:
            CognitivePhraseGenerationResult
        """
        if not states:
            return CognitivePhraseGenerationResult(
                phrases=[],
                metadata={"error": "No states provided"},
                llm_response=""
            )

        # Sort states by timestamp
        sorted_states = sorted(states, key=lambda x: x.timestamp)

        # Create a single phrase
        start_timestamp = sorted_states[0].timestamp
        end_timestamp = sorted_states[-1].end_timestamp or sorted_states[-1].timestamp

        phrase = CognitivePhrase(
            label="User Workflow Session",
            description="Complete user workflow session (rule-based generation)",
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            duration=end_timestamp - start_timestamp,
            user_id=sorted_states[0].user_id,
            session_id=sorted_states[0].session_id,
            state_ids=[state.id for state in sorted_states],
            states=sorted_states,
            actions=actions,
            attributes={"rule_based": True},
            llm_generated=False
        )

        metadata = {
            "total_phrases": 1,
            "generation_method": "rule_based",
            "confidence_score": 0.6,
            "notes": "Simple rule-based phrase generation"
        }

        return CognitivePhraseGenerationResult(
            phrases=[phrase],
            metadata=metadata,
            llm_response="rule_based"
        )


__all__ = [
    "CognitivePhraseGenerator",
    "CognitivePhraseGenerationResult",
]