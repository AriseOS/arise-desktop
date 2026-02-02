"""State and Intent Extractor - Extracts states and intents from workflow data using LLM.

This module uses LLM to identify States (pages/screens) and Intents (operations within states).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.cloud_backend.memgraph.ontology.domain import Domain
from src.cloud_backend.memgraph.ontology.intent import Intent
from src.cloud_backend.memgraph.ontology.state import State
from src.cloud_backend.memgraph.services.llm import LLMClient, LLMMessage, LLMResponse
from src.cloud_backend.memgraph.thinker.prompts.state_intent_extraction_prompt import (
    StateIntentExtractionInput,
    StateIntentExtractionPrompt,
)

logger = logging.getLogger(__name__)


class StateIntentExtractionResult:
    """Result of state and intent extraction.

    Attributes:
        states: List of extracted State objects
        intents: List of extracted Intent objects
        state_intent_mapping: Mapping from state ID to its intents
        extraction_metadata: Metadata about extraction
        llm_response: Raw LLM response
        timestamp: When extraction was performed
    """

    def __init__(
        self,
        states: List[State],
        intents: List[Intent],
        state_intent_mapping: Dict[str, List[Intent]],
        extraction_metadata: Dict[str, Any],
        llm_response: str
    ):
        """Initialize extraction result.

        Args:
            states: List of State objects
            intents: List of Intent objects
            state_intent_mapping: State ID to intents mapping
            extraction_metadata: Extraction metadata
            llm_response: Raw LLM response
        """
        self.states = states
        self.intents = intents
        self.state_intent_mapping = state_intent_mapping
        self.extraction_metadata = extraction_metadata
        self.llm_response = llm_response
        self.timestamp = datetime.now()


class StateIntentExtractor:
    """Extractor for identifying states and intents from workflow data using LLM.

    Uses LLM to analyze workflow events and extract:
    - States: Pages/screens where user is located
    - Intents: Operations performed within each state (do not cause state transitions)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        model_name: str = "gpt-4"
    ):
        """Initialize StateIntentExtractor.

        Args:
            llm_client: LLM client for extraction (required)
            model_name: Name of LLM model to use

        Raises:
            ValueError: If llm_client is None
        """
        if not llm_client:
            raise ValueError("LLM client is required for StateIntentExtractor")

        self.llm_client = llm_client
        self.model_name = model_name
        self.prompt = StateIntentExtractionPrompt()

    def extract_states_and_intents(
        self,
        workflow_data: List[Dict[str, Any]],
        domain_mapping: Optional[Dict[str, Domain]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> StateIntentExtractionResult:
        """Extract states and intents from workflow data using LLM.

        Args:
            workflow_data: List of workflow event dictionaries
            domain_mapping: Optional URL to Domain mapping
            user_id: User ID
            session_id: Session ID

        Returns:
            StateIntentExtractionResult containing states and intents

        Raises:
            ValueError: If input is invalid
        """
        if not workflow_data:
            raise ValueError("Workflow data is empty")

        # Format ALL events for prompt (no sampling!)
        events_summary = self._format_events_for_prompt(workflow_data)

        # Build prompt using prompt object
        prompt_input = StateIntentExtractionInput(events_summary=events_summary)

        # Validate input
        if not self.prompt.validate_input(prompt_input):
            raise ValueError("Invalid prompt input: no events summary provided")

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
            max_tokens=8000
        )

        # Parse response using prompt object
        parsed_output = self.prompt.parse_response(response.content)

        # Validate output
        if not self.prompt.validate_output(parsed_output):
            raise ValueError("LLM returned invalid output: no states extracted")

        # Create State objects from parsed output
        states = []
        state_id_map = {}  # Temp index -> real state ID

        for idx, state_data in enumerate(parsed_output.states):
            try:
                state = State(
                    page_url=state_data.page_url,
                    page_title=state_data.page_title,
                    timestamp=state_data.timestamp,
                    end_timestamp=state_data.end_timestamp,
                    duration=state_data.duration,
                    description=state_data.description,
                    user_id=user_id,
                    session_id=session_id,
                    attributes=state_data.attributes
                )
                states.append(state)
                state_id_map[idx] = state.id
            except Exception as state_err:
                logger.warning(f" Failed to create state from data: {str(state_err)}")
                continue

        if not states:
            raise ValueError("No valid states could be created from LLM output")

        # Create Intent objects and associate with states
        intents = []
        state_intent_mapping = {state.id: [] for state in states}

        for intent_data in parsed_output.intents:
            state_idx = intent_data.state_index

            if state_idx not in state_id_map:
                logger.warning(f" Invalid state_index {state_idx}, skipping intent")
                continue

            state_id = state_id_map[state_idx]
            state = states[state_idx]

            try:
                # Store legacy xpath-based fields in attributes
                attrs = intent_data.attributes.copy() if intent_data.attributes else {}
                if getattr(intent_data, 'element_id', None):
                    attrs["element_id"] = intent_data.element_id
                if getattr(intent_data, 'element_tag', None):
                    attrs["element_tag"] = intent_data.element_tag
                if getattr(intent_data, 'element_class', None):
                    attrs["element_class"] = intent_data.element_class
                if getattr(intent_data, 'xpath', None):
                    attrs["xpath"] = intent_data.xpath
                if getattr(intent_data, 'css_selector', None):
                    attrs["css_selector"] = intent_data.css_selector
                if getattr(intent_data, 'coordinates', None):
                    attrs["coordinates"] = intent_data.coordinates

                intent = Intent(
                    state_id=state_id,
                    type=intent_data.type,
                    timestamp=intent_data.timestamp,
                    page_url=state.page_url,
                    page_title=state.page_title,
                    element_ref=getattr(intent_data, 'element_ref', None),
                    element_role=getattr(intent_data, 'element_role', None),
                    text=intent_data.text,
                    value=intent_data.value,
                    user_id=user_id,
                    session_id=session_id,
                    attributes=attrs
                )

                intents.append(intent)
                state_intent_mapping[state_id].append(intent)

            except Exception as intent_err:
                logger.warning(f" Failed to create intent from data: {str(intent_err)}")
                continue

        # Build metadata
        metadata = {
            "extraction_method": "llm",
            "llm_model": self.model_name,
            "state_count": len(states),
            "intent_count": len(intents),
            "total_events": len(workflow_data),
            "avg_intents_per_state": len(intents) / len(states) if states else 0
        }

        return StateIntentExtractionResult(
            states=states,
            intents=intents,
            state_intent_mapping=state_intent_mapping,
            extraction_metadata=metadata,
            llm_response=response.content
        )

    def _format_events_for_prompt(self, workflow_data: List[Dict[str, Any]]) -> str:
        """Format workflow events for LLM prompt with complete element information.

        Supports both new ref-based format and legacy xpath-based format.

        Args:
            workflow_data: List of ALL workflow events

        Returns:
            Formatted events string with complete element details for operation replay
        """
        lines = []
        # Process ALL events (no sampling!)
        for i, event in enumerate(workflow_data):
            url = event.get('page_url') or event.get('url', 'unknown')
            event_type = event.get('type', 'unknown')
            timestamp = event.get('timestamp', 0)
            page_title = event.get('page_title', '')

            # New ref-based format (flat structure)
            element_ref = event.get('ref', '')
            element_role = event.get('role', '')
            text = event.get('text', '')
            value = event.get('value', '')

            # Legacy xpath-based format (nested 'element' dict)
            element_dict = event.get('element', {})
            if element_dict:
                element_tag = element_dict.get('tagName', event.get('element_tag', ''))
                element_id = element_dict.get('id', event.get('element_id', ''))
                element_class = element_dict.get('className', event.get('element_class', ''))
                xpath = element_dict.get('xpath', event.get('xpath', ''))
                text = text or element_dict.get('textContent', '')
                css_selector = event.get('css_selector', '')
            else:
                element_tag = event.get('element_tag', '')
                element_id = event.get('element_id', '')
                element_class = event.get('element_class', '')
                xpath = event.get('xpath', '')
                css_selector = event.get('css_selector', '')

            # Extract coordinates from data dict (legacy format)
            data_dict = event.get('data', {})
            client_x = data_dict.get('clientX', event.get('clientX', ''))
            client_y = data_dict.get('clientY', event.get('clientY', ''))
            value = value or data_dict.get('value', '')

            # Format event with all available information
            event_desc = f"{i}. [{event_type}] URL: {url}"
            if page_title:
                event_desc += f" | Title: {page_title}"
            event_desc += f" | Timestamp: {timestamp}"

            # Add element information - prefer new format, fallback to legacy
            has_new_format = element_ref or element_role
            has_legacy_format = element_tag or element_id or element_class or xpath

            if has_new_format:
                # New ref-based format
                event_desc += "\n   Element:"
                if element_ref:
                    event_desc += f" Ref={element_ref}"
                if element_role:
                    event_desc += f" | Role={element_role}"
                if text:
                    event_desc += f" | Text=\"{text}\""
                if value:
                    event_desc += f" | Value=\"{value}\""
            elif has_legacy_format:
                # Legacy xpath-based format
                event_desc += "\n   Element:"
                if element_tag:
                    event_desc += f" Tag={element_tag}"
                if element_id:
                    event_desc += f" | ID={element_id}"
                if element_class:
                    event_desc += f" | Class={element_class}"
                if xpath:
                    event_desc += f" | XPath={xpath}"
                if css_selector:
                    event_desc += f" | CSS={css_selector}"
                if text:
                    event_desc += f" | Text=\"{text}\""
                if value:
                    event_desc += f" | Value=\"{value}\""
                if client_x and client_y:
                    event_desc += f" | Coords=({client_x}, {client_y})"

            lines.append(event_desc)

        return '\n'.join(lines)


__all__ = [
    "StateIntentExtractor",
    "StateIntentExtractionResult",
]
