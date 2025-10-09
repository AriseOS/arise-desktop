"""Workflow Processor - Main orchestrator for workflow processing pipeline.

This module orchestrates the complete workflow processing pipeline:
1. Parse workflow input (JSON/text) into Intents
2. Build Intent DAG using LogicalForm
3. Generate States and Actions
4. Synthesize CognitivePhrases
5. Store results to memory
"""

import json
import uuid
from typing import Any, Dict, List, Optional, Union

from src.memory.memory import Memory
from src.ontology.action import Action
from src.ontology.cognitive_phrase import CognitivePhrase
from src.ontology.intent import Intent
from src.ontology.state import State
from src.thinker.json_processor import BrowserContext, BrowserEvent, JSONInputBatch, JsonProcessor
from src.services.llm import LLMClient
from src.thinker.cognitive_phrase_generator import CognitivePhraseGenerator
from src.thinker.intent_dag_builder import IntentDAG, IntentDAGBuilder
from src.thinker.state_generator import StateGenerator


class WorkflowProcessingResult:
    """Result of workflow processing pipeline.

    Attributes:
        intents: List of extracted Intent objects
        intent_dag: Intent DAG structure
        states: List of generated State objects
        actions: List of generated Action objects
        phrases: List of generated CognitivePhrase objects
        metadata: Processing metadata
    """

    def __init__(
        self,
        intents: List[Intent],
        intent_dag: IntentDAG,
        states: List[State],
        actions: List[Action],
        phrases: List[CognitivePhrase],
        metadata: Dict[str, Any]
    ):
        """Initialize processing result.

        Args:
            intents: List of Intent objects
            intent_dag: Intent DAG
            states: List of State objects
            actions: List of Action objects
            phrases: List of CognitivePhrase objects
            metadata: Processing metadata
        """
        self.intents = intents
        self.intent_dag = intent_dag
        self.states = states
        self.actions = actions
        self.phrases = phrases
        self.metadata = metadata

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "intents": [intent.to_dict() for intent in self.intents],
            "intent_dag": self.intent_dag.to_dict(),
            "states": [state.to_dict() for state in self.states],
            "actions": [action.to_dict() for action in self.actions],
            "phrases": [phrase.to_dict() for phrase in self.phrases],
            "metadata": self.metadata
        }


class WorkflowProcessor:
    """Main orchestrator for workflow processing pipeline.

    Coordinates the complete transformation from raw workflow input to
    stored cognitive structures.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        memory: Optional[Memory] = None
    ):
        """Initialize WorkflowProcessor.

        Args:
            llm_client: LLM client for processing (optional)
            memory: Memory instance for storage (optional)
        """
        self.llm_client = llm_client
        self.memory = memory

        # Initialize pipeline components
        self.json_processor = JsonProcessor()
        self.dag_builder = IntentDAGBuilder(
            llm_client=llm_client,
            model_name=llm_client.model_name if llm_client else "gpt-4"
        )
        self.state_generator = StateGenerator(
            llm_client=llm_client,
            model_name=llm_client.model_name if llm_client else "gpt-4"
        )
        self.phrase_generator = CognitivePhraseGenerator(llm_client=llm_client)

    def process_workflow(
        self,
        workflow_input: Union[str, Dict[str, Any], List[Dict[str, Any]]],
        input_type: str = "json",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        store_to_memory: bool = True
    ) -> WorkflowProcessingResult:
        """Process workflow through complete pipeline.

        Args:
            workflow_input: Workflow input (JSON string, dict, or list of events)
            input_type: Input type ("json" or "text")
            user_id: User ID (optional)
            session_id: Session ID (optional)
            store_to_memory: Whether to store results to memory (default: True)

        Returns:
            WorkflowProcessingResult containing all generated structures

        Raises:
            ValueError: If input is invalid
        """
        # Step 1: Parse workflow input to JSONInputBatch
        batch = self._parse_workflow_input(
            workflow_input,
            input_type,
            user_id,
            session_id
        )

        # Step 2: Extract Intents using LogicalForm analysis
        intent_result = self.dag_builder.analyze_events_to_intents(
            batch,
            use_llm=self.llm_client is not None
        )
        intents = intent_result.atomic_intents

        if not intents:
            raise ValueError("No intents extracted from workflow")

        # Step 3: Build Intent DAG
        intent_dag = self.dag_builder.build_dag(
            intents,
            use_llm=self.llm_client is not None
        )

        # Step 4: Generate States and Actions
        state_result = self.state_generator.generate_semantic_states(
            intents,
            context={"dag": intent_dag.to_dict()}
        )
        states = state_result.semantic_states
        actions = state_result.transition_edges

        # Step 5: Generate CognitivePhrases
        phrase_result = self.phrase_generator.generate_phrases(
            states,
            actions,
            use_llm=self.llm_client is not None
        )
        phrases = phrase_result.phrases

        # Step 6: Store to memory if requested
        if store_to_memory and self.memory:
            self._store_to_memory(states, actions, phrases)

        # Collect metadata
        metadata = {
            "input_type": input_type,
            "user_id": user_id,
            "session_id": session_id,
            "intent_count": len(intents),
            "dag_edges": len(intent_dag.edges),
            "state_count": len(states),
            "action_count": len(actions),
            "phrase_count": len(phrases),
            "stored_to_memory": store_to_memory and self.memory is not None,
            "pipeline_stages": {
                "intent_extraction": intent_result.analysis_metadata,
                "dag_construction": intent_dag.metadata,
                "state_generation": state_result.generation_metadata,
                "phrase_generation": phrase_result.metadata
            }
        }

        return WorkflowProcessingResult(
            intents=intents,
            intent_dag=intent_dag,
            states=states,
            actions=actions,
            phrases=phrases,
            metadata=metadata
        )

    def _parse_workflow_input(
        self,
        workflow_input: Union[str, Dict[str, Any], List[Dict[str, Any]]],
        input_type: str,
        user_id: Optional[str],
        session_id: Optional[str]
    ) -> JSONInputBatch:
        """Parse workflow input to JSONInputBatch.

        Args:
            workflow_input: Raw workflow input
            input_type: Input type ("json" or "text")
            user_id: User ID
            session_id: Session ID

        Returns:
            JSONInputBatch object

        Raises:
            ValueError: If input cannot be parsed
        """
        # Parse JSON input
        if input_type == "json":
            if isinstance(workflow_input, str):
                try:
                    data = json.loads(workflow_input)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON input: {e}") from e
            else:
                data = workflow_input

            # Handle different JSON formats
            if isinstance(data, list):
                # List of events
                events = [self._dict_to_event(event_dict) for event_dict in data]
            elif isinstance(data, dict):
                if "events" in data:
                    # Batch format with events key
                    events = [self._dict_to_event(e) for e in data["events"]]
                else:
                    # Single event
                    events = [self._dict_to_event(data)]
            else:
                raise ValueError("Invalid JSON structure")

            # Create batch
            batch_id = f"batch_{uuid.uuid4().hex[:8]}"
            context = BrowserContext(
                user_id=user_id or "unknown",
                session_id=session_id or "unknown"
            )
            batch = JSONInputBatch(
                batch_id=batch_id,
                events=events,
                context=context
            )

            return batch

        if input_type == "text":
            # For text input, we'll create a simple navigation event
            # This is a simplified implementation
            event = BrowserEvent(
                event_type="navigation",
                timestamp=0,
                page_url=workflow_input if isinstance(workflow_input, str) else "unknown",
                page_title="Text Input",
                attributes={"raw_text": str(workflow_input)}
            )

            batch_id = f"batch_{uuid.uuid4().hex[:8]}"
            context = BrowserContext(
                user_id=user_id or "unknown",
                session_id=session_id or "unknown"
            )
            batch = JSONInputBatch(
                batch_id=batch_id,
                events=[event],
                context=context
            )

            return batch

        raise ValueError(f"Unsupported input type: {input_type}")

    def _dict_to_event(self, event_dict: Dict[str, Any]) -> BrowserEvent:
        """Convert dictionary to BrowserEvent.

        Args:
            event_dict: Event dictionary

        Returns:
            BrowserEvent object
        """
        return BrowserEvent(
            event_type=event_dict.get("event_type", "unknown"),
            timestamp=event_dict.get("timestamp", 0),
            page_url=event_dict.get("page_url", ""),
            page_title=event_dict.get("page_title"),
            element_id=event_dict.get("element_id"),
            element_tag=event_dict.get("element_tag"),
            element_class=event_dict.get("element_class"),
            xpath=event_dict.get("xpath"),
            css_selector=event_dict.get("css_selector"),
            text=event_dict.get("text"),
            value=event_dict.get("value"),
            coordinates=event_dict.get("coordinates"),
            attributes=event_dict.get("attributes", {})
        )

    def _store_to_memory(
        self,
        states: List[State],
        actions: List[Action],
        phrases: List[CognitivePhrase]
    ) -> None:
        """Store processing results to memory.

        Args:
            states: List of State objects
            actions: List of Action objects
            phrases: List of CognitivePhrase objects
        """
        if not self.memory:
            return

        # Store states
        for state in states:
            self.memory.create_state(state)

        # Store actions
        for action in actions:
            self.memory.create_action(action)

        # Store cognitive phrases
        for phrase in phrases:
            self.memory.create_phrase(phrase)

    def process_workflow_file(
        self,
        file_path: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        store_to_memory: bool = True
    ) -> WorkflowProcessingResult:
        """Process workflow from a file.

        Args:
            file_path: Path to workflow file (JSON or text)
            user_id: User ID (optional)
            session_id: Session ID (optional)
            store_to_memory: Whether to store results to memory

        Returns:
            WorkflowProcessingResult

        Raises:
            IOError: If file cannot be read
            ValueError: If file content is invalid
        """
        # Read file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Detect input type
        input_type = "json" if file_path.endswith('.json') else "text"

        # Process
        return self.process_workflow(
            workflow_input=content,
            input_type=input_type,
            user_id=user_id,
            session_id=session_id,
            store_to_memory=store_to_memory
        )


__all__ = [
    "WorkflowProcessor",
    "WorkflowProcessingResult",
]