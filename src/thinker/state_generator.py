"""State Generator - Generates semantic states from intents.

This module transforms atomic intents into semantic states and transition edges,
representing higher-level user behaviors and state transitions.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.ontology.action import TransitionEdge
from src.ontology.intent import AtomicIntent
from src.ontology.state import SemanticState, SemanticStateType
from src.services.llm import LLMClient, LLMMessage, LLMResponse
from src.thinker.prompts.state_generation_prompt import StateGenerationPrompt


class StateGenerationResult:
    """Result of semantic state generation.

    Attributes:
        semantic_states: List of generated SemanticState objects
        transition_edges: List of TransitionEdge objects
        generation_metadata: Metadata about the generation process
        llm_response: Raw LLM response (if LLM was used)
        timestamp: Time when generation was performed
    """

    def __init__(
        self,
        semantic_states: List[SemanticState],
        transition_edges: List[TransitionEdge],
        generation_metadata: Dict[str, Any],
        llm_response: str
    ):
        """Initialize state generation result.

        Args:
            semantic_states: List of semantic states
            transition_edges: List of transition edges
            generation_metadata: Generation metadata
            llm_response: Raw LLM response
        """
        self.semantic_states = semantic_states
        self.transition_edges = transition_edges
        self.generation_metadata = generation_metadata
        self.llm_response = llm_response
        self.timestamp = datetime.now()

    def get_state_count(self) -> int:
        """Get number of states generated.

        Returns:
            Number of states
        """
        return len(self.semantic_states)

    def get_edge_count(self) -> int:
        """Get number of edges generated.

        Returns:
            Number of edges
        """
        return len(self.transition_edges)


class StateGenerator:
    """Generator for creating semantic states from atomic intents.

    Uses LLM and semantic analysis to aggregate atomic intents into higher-level
    semantic states with transition edges, representing complete user behaviors.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        model_name: str = "gpt-4"
    ):
        """Initialize StateGenerator.

        Args:
            llm_client: LLM client for generation (optional)
            model_name: Name of LLM model to use (default: gpt-4)
        """
        self.llm_client = llm_client
        self.model_name = model_name
        self.prompt = StateGenerationPrompt()
        self.generation_cache: Dict[str, StateGenerationResult] = {}

    def generate_semantic_states(
        self,
        atomic_intents: List[AtomicIntent],
        context: Optional[Dict[str, Any]] = None
    ) -> StateGenerationResult:
        """Generate semantic states and transition edges from atomic intents.

        Args:
            atomic_intents: List of atomic intents to analyze
            context: Optional context information (e.g., DAG structure)

        Returns:
            StateGenerationResult containing states and edges

        Raises:
            ValueError: If input is invalid
        """
        # Validate input
        input_data = {"atomic_intents": atomic_intents, "context": context}
        if not self.prompt.validate_input(input_data):
            raise ValueError("Invalid input: atomic intents list is empty")

        # Use LLM or fallback to rule-based
        if self.llm_client:
            return self._generate_with_llm(atomic_intents, context)

        return self._generate_rule_based(atomic_intents, context)

    def _generate_with_llm(
        self,
        atomic_intents: List[AtomicIntent],
        context: Optional[Dict[str, Any]]
    ) -> StateGenerationResult:
        """Generate states using LLM analysis.

        Args:
            atomic_intents: List of atomic intents
            context: Optional context information

        Returns:
            StateGenerationResult
        """
        try:
            # Build prompt
            input_data = {"atomic_intents": atomic_intents, "context": context}
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
            states_data, edges_data, metadata = self.prompt.parse_response(
                response.content
            )

            # Build intent mapping
            intent_map = {intent.id: intent for intent in atomic_intents}

            # Create SemanticState objects
            semantic_states = []
            state_id_map = {}  # Temporary ID to real ID mapping

            for i, state_data in enumerate(states_data):
                try:
                    state = self.prompt.create_semantic_state(state_data, intent_map)
                    semantic_states.append(state)
                    # Record mapping for edge construction
                    temp_id = f"state_{i}"
                    state_id_map[temp_id] = state.id
                except ValueError as err:
                    print(f"Failed to create semantic state: {str(err)}")
                    continue

            # Create TransitionEdge objects
            transition_edges = []
            for edge_data in edges_data:
                try:
                    edge = self.prompt.create_transition_edge(edge_data, state_id_map)
                    transition_edges.append(edge)
                except ValueError as err:
                    print(f"Failed to create transition edge: {str(err)}")
                    continue

            # Create result
            result = StateGenerationResult(
                semantic_states=semantic_states,
                transition_edges=transition_edges,
                generation_metadata=metadata,
                llm_response=response.content
            )

            # Cache result
            cache_key = f"gen_{datetime.now().timestamp()}"
            self.generation_cache[cache_key] = result

            return result

        except Exception as err:  # pylint: disable=broad-exception-caught
            # Intentionally catch all exceptions for fallback
            error_msg = f"LLM state generation failed: {str(err)}"
            print(f"{error_msg}, falling back to rule-based")
            return self._generate_rule_based(atomic_intents, context)

    def _generate_rule_based(
        self,
        atomic_intents: List[AtomicIntent],
        context: Optional[Dict[str, Any]]  # pylint: disable=unused-argument
    ) -> StateGenerationResult:
        """Generate states using rule-based approach.

        Groups intents by page URL and creates states accordingly.

        Args:
            atomic_intents: List of atomic intents
            context: Optional context information

        Returns:
            StateGenerationResult
        """
        # Simple strategy: group by page URL
        page_groups: Dict[str, List[AtomicIntent]] = {}

        for intent in atomic_intents:
            page_url = intent.page_url
            if page_url not in page_groups:
                page_groups[page_url] = []
            page_groups[page_url].append(intent)

        # Create a semantic state for each page group
        semantic_states = []
        for page_url, intents in page_groups.items():
            if not intents:
                continue

            # Sort by timestamp
            intents.sort(key=lambda x: x.timestamp)

            # Infer state type (based on intent types)
            state_type = SemanticStateType.UNKNOWN

            # Create state
            first_intent = intents[0]
            last_intent = intents[-1] if len(intents) > 1 else first_intent
            duration = (last_intent.timestamp - first_intent.timestamp
                       if len(intents) > 1 else None)

            state = SemanticState(
                label=f"Activity on {page_url}",
                type=state_type,
                timestamp=first_intent.timestamp,
                end_timestamp=last_intent.timestamp if len(intents) > 1 else None,
                duration=duration,
                page_url=page_url,
                page_title=first_intent.page_title,
                user_id=first_intent.user_id,
                session_id=first_intent.session_id,
                atomic_intents=intents,
                attributes={"rule_based": True}
            )

            semantic_states.append(state)

        # Sort by timestamp
        semantic_states.sort(key=lambda x: x.timestamp)

        # Create transition edges
        transition_edges = []
        for i in range(len(semantic_states) - 1):
            edge = TransitionEdge(
                source=semantic_states[i].id,
                target=semantic_states[i + 1].id,
                timestamp=semantic_states[i + 1].timestamp,
                type="user_action",
                user_id=semantic_states[i].user_id,
                session_id=semantic_states[i].session_id,
                attributes={"rule_based": True}
            )
            transition_edges.append(edge)

        metadata = {
            "total_states": len(semantic_states),
            "total_edges": len(transition_edges),
            "generation_method": "rule_based",
            "confidence_score": 0.6,
            "notes": "Rule-based state generation (LLM fallback)"
        }

        return StateGenerationResult(
            semantic_states=semantic_states,
            transition_edges=transition_edges,
            generation_metadata=metadata,
            llm_response="rule_based_fallback"
        )

    def get_generation_statistics(self) -> Dict[str, Any]:
        """Get statistics about cached state generations.

        Returns:
            Dictionary with generation statistics
        """
        total_generations = len(self.generation_cache)
        total_states = sum(
            result.get_state_count()
            for result in self.generation_cache.values()
        )
        total_edges = sum(
            result.get_edge_count()
            for result in self.generation_cache.values()
        )

        return {
            "total_generations": total_generations,
            "total_states": total_states,
            "total_edges": total_edges,
            "generations": [
                {
                    "key": key,
                    "state_count": result.get_state_count(),
                    "edge_count": result.get_edge_count(),
                    "timestamp": result.timestamp.isoformat()
                }
                for key, result in self.generation_cache.items()
            ]
        }


__all__ = [
    "StateGenerator",
    "StateGenerationResult",
]
