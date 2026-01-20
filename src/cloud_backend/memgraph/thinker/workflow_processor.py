"""Workflow Processor - Production-grade LLM-driven workflow processing pipeline.

This module orchestrates the complete workflow processing pipeline using LLM:
1. Extract Domains from workflow data
2. Extract States and Intents
3. Extract Actions (state transitions)
4. Generate Manage edges (Domain-State connections)
5. Store all structures to memory

New Architecture:
    Input → Domain Extraction → State+Intent Extraction → Action Extraction →
    Manage Generation → Memory Storage
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from src.cloud_backend.memgraph.memory.memory import Memory
from src.cloud_backend.memgraph.ontology.action import Action
from src.cloud_backend.memgraph.ontology.cognitive_phrase import CognitivePhrase
from src.cloud_backend.memgraph.ontology.domain import Domain, Manage
from src.cloud_backend.memgraph.ontology.intent import Intent
from src.cloud_backend.memgraph.ontology.state import State
from src.cloud_backend.memgraph.services.embedding_model import EmbeddingModel
from src.cloud_backend.memgraph.services.llm import LLMClient, LLMMessage
from src.cloud_backend.memgraph.thinker.action_extractor import ActionExtractor
from src.cloud_backend.memgraph.thinker.domain_extractor import DomainExtractor
from src.cloud_backend.memgraph.thinker.manage_generator import ManageGenerator
from src.cloud_backend.memgraph.thinker.prompts.workflow_parse_prompt import (
    WorkflowParseInput,
    WorkflowParsePrompt,
)
from src.cloud_backend.memgraph.thinker.state_intent_extractor import StateIntentExtractor


class WorkflowProcessingResult:
    """Result of complete workflow processing.

    Attributes:
        domains: List of extracted Domain objects
        states: List of extracted State objects
        intents: List of extracted Intent objects
        actions: List of extracted Action objects
        manages: List of generated Manage edges
        metadata: Processing metadata with statistics
        timestamp: When processing completed
    """

    def __init__(
        self,
        domains: List[Domain],
        states: List[State],
        intents: List[Intent],
        actions: List[Action],
        manages: List[Manage],
        metadata: Dict[str, Any],
    ):
        """Initialize processing result.

        Args:
            domains: List of Domain objects
            states: List of State objects
            intents: List of Intent objects
            actions: List of Action objects
            manages: List of Manage objects
            metadata: Processing metadata
        """
        self.domains = domains
        self.states = states
        self.intents = intents
        self.actions = actions
        self.manages = manages
        self.metadata = metadata
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "domains": [d.to_dict() for d in self.domains],
            "states": [s.to_dict() for s in self.states],
            "intents": [i.to_dict() for i in self.intents],
            "actions": [a.to_dict() for a in self.actions],
            "manages": [m.to_dict() for m in self.manages],
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get processing summary.

        Returns:
            Summary dictionary with counts
        """
        return {
            "domain_count": len(self.domains),
            "state_count": len(self.states),
            "intent_count": len(self.intents),
            "action_count": len(self.actions),
            "manage_count": len(self.manages),
            "avg_intents_per_state": (
                len(self.intents) / len(self.states) if self.states else 0
            ),
            "avg_states_per_domain": (
                len(self.states) / len(self.domains) if self.domains else 0
            ),
            "processing_time": self.metadata.get("processing_time_ms", 0),
        }


class WorkflowProcessor:
    """Production-grade workflow processor using LLM-driven extraction.

    This processor implements a complete pipeline for transforming raw workflow
    data into structured memory representations:

    Pipeline Stages:
        1. Parse and validate input
        2. Extract Domains using LLM
        3. Extract States and Intents using LLM
        4. Extract Actions using LLM
        5. Generate Manage edges
        6. Store to memory

    All extraction stages use LLM for intelligent analysis and structuring.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        memory: Optional[Memory] = None,
        model_name: str = "gpt-4",
        embedding_model: Optional[EmbeddingModel] = None,
    ):
        """Initialize WorkflowProcessor.

        Args:
            llm_client: LLM client for processing (required)
            memory: Memory instance for storage (optional)
            model_name: Name of LLM model to use
            embedding_model: Embedding model for state vector indexing (optional)
                           If provided, generates embeddings for states based on their intents

        Raises:
            ValueError: If llm_client is None
        """
        if not llm_client:
            raise ValueError("LLM client is required for WorkflowProcessor")

        self.llm_client = llm_client
        self.memory = memory
        self.model_name = model_name
        self.embedding_model = embedding_model

        # Initialize pipeline components
        self.domain_extractor = DomainExtractor(
            llm_client=llm_client, model_name=model_name
        )
        self.state_intent_extractor = StateIntentExtractor(
            llm_client=llm_client, model_name=model_name
        )
        self.action_extractor = ActionExtractor(
            llm_client=llm_client, model_name=model_name
        )
        self.manage_generator = ManageGenerator()
        self.workflow_parse_prompt = WorkflowParsePrompt()

    def process_workflow(
        self,
        workflow_data: Union[List[Dict[str, Any]], str],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        store_to_memory: bool = True,
    ) -> WorkflowProcessingResult:
        """Process complete workflow through LLM-driven pipeline.

        Args:
            workflow_data: Workflow events (list of dicts or JSON string)
            user_id: User ID for attribution
            session_id: Session ID for grouping
            store_to_memory: Whether to store results to memory

        Returns:
            WorkflowProcessingResult with all extracted structures

        Raises:
            ValueError: If input is invalid or processing fails
        """
        start_time = datetime.now()
        print(f"\n{'='*60}")
        print(f"Starting Workflow Processing Pipeline")
        print(f"{'='*60}\n")

        # Stage 0: Parse and validate input
        print("Stage 0: Parsing input data...")
        events = self._parse_input(workflow_data)
        print(f"✓ Parsed {len(events)} events\n")

        # Stage 1: Extract Domains
        print("Stage 1: Extracting domains using LLM...")
        domain_result = self.domain_extractor.extract_domains(
            workflow_data=events, user_id=user_id
        )
        domains = domain_result.domains
        domain_mapping = domain_result.domain_mapping
        print(f"✓ Extracted {len(domains)} domains")
        for domain in domains:
            print(f"  - {domain.domain_name} ({domain.domain_url})")
        print()

        # Stage 2: Extract States and Intents
        print("Stage 2: Extracting states and intents using LLM...")
        state_intent_result = self.state_intent_extractor.extract_states_and_intents(
            workflow_data=events,
            domain_mapping=domain_mapping,
            user_id=user_id,
            session_id=session_id,
        )
        states = state_intent_result.states
        intents = state_intent_result.intents
        print(f"✓ Extracted {len(states)} states and {len(intents)} intents")
        print(f"  - Avg {len(intents)/len(states):.1f} intents per state")
        print()

        # Stage 3: Extract Actions
        print("Stage 3: Extracting actions using LLM...")
        action_result = self.action_extractor.extract_actions(
            states=states, workflow_data=events, user_id=user_id, session_id=session_id
        )
        actions = action_result.actions
        print(f"✓ Extracted {len(actions)} actions (state transitions)")
        print()

        # Stage 4: Generate Manage edges
        print("Stage 4: Generating manage edges...")
        manage_result = self.manage_generator.generate_manages(
            domains=domains, states=states, user_id=user_id
        )
        manages = manage_result.manages
        print(f"✓ Generated {len(manages)} manage edges")
        print()

        # Stage 4.5: Generate embeddings
        if self.embedding_model:
            print("Stage 4.5: Generating embeddings...")
            print("  → Generating intent embeddings...")
            self._generate_intent_embeddings(intents)
            print("  → Generating state embeddings...")
            self._generate_state_embeddings(states)
            print()

        # Stage 5: Store to memory
        if store_to_memory and self.memory:
            print("Stage 5: Storing to memory...")
            self._store_to_memory(domains, states, actions, manages)
            print(f"✓ Stored all structures to memory")
        else:
            print("Stage 5: Skipping memory storage (store_to_memory=False)")
        print()

        # Stage 6: Create cognitive phrase for short-term memory
        cognitive_phrase = None
        if store_to_memory and self.memory and states:
            print("Stage 6: Creating cognitive phrase...")
            cognitive_phrase = self._create_cognitive_phrase_from_workflow(
                states=states,
                actions=actions,
                workflow_data=workflow_data,
                user_id=user_id,
                session_id=session_id,
            )
            if cognitive_phrase:
                success = self.memory.create_phrase(cognitive_phrase)
                if success:
                    print(
                        f"✓ Created cognitive phrase: {cognitive_phrase.description[:80]}..."
                    )
                else:
                    print(f"⚠ Failed to store cognitive phrase")
            else:
                print(f"⚠ Failed to create cognitive phrase")
        print()

        # Calculate processing time
        end_time = datetime.now()
        processing_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # Collect comprehensive metadata
        metadata = {
            "user_id": user_id,
            "session_id": session_id,
            "event_count": len(events),
            "domain_count": len(domains),
            "state_count": len(states),
            "intent_count": len(intents),
            "action_count": len(actions),
            "manage_count": len(manages),
            "stored_to_memory": store_to_memory and self.memory is not None,
            "llm_model": self.model_name,
            "processing_time_ms": processing_time_ms,
            "pipeline_stages": {
                "domain_extraction": domain_result.extraction_metadata,
                "state_intent_extraction": state_intent_result.extraction_metadata,
                "action_extraction": action_result.extraction_metadata,
                "manage_generation": manage_result.generation_metadata,
            },
        }

        result = WorkflowProcessingResult(
            domains=domains,
            states=states,
            intents=intents,
            actions=actions,
            manages=manages,
            metadata=metadata,
        )

        # Print summary
        print(f"{'='*60}")
        print(f"Processing Complete!")
        print(f"{'='*60}")
        summary = result.get_summary()
        for key, value in summary.items():
            print(f"{key}: {value}")
        print(f"{'='*60}\n")

        return result

    def _parse_input(
        self, workflow_data: Union[List[Dict[str, Any]], str]
    ) -> List[Dict[str, Any]]:
        """Parse and optimize workflow input using LLM-driven 3-step process.

        This method implements a comprehensive workflow parsing pipeline:
        1. 解析与抽象 (Parse and Abstract): Analyze and summarize core business intent
        2. 选择器优化 (Selector Optimization): Evaluate and optimize element selectors
        3. JSON生成 (JSON Generation): Generate robust JSON with smart waiting and assertions

        Args:
            workflow_data: Raw workflow data (JSON string or list of dicts)

        Returns:
            List of optimized event dictionaries

        Raises:
            ValueError: If input is invalid
        """
        # Handle string input - this is now expected to be a complete JSON string
        if isinstance(workflow_data, str):
            print("  → Parsing JSON workflow data...")
            try:
                # Try to parse as JSON first
                data = json.loads(workflow_data)
            except json.JSONDecodeError as err:
                raise ValueError(f"Invalid JSON input: {str(err)}") from err

            # If it's already a list, use it directly
            if isinstance(data, list):
                parsed_workflow = data
            # If it's a dict with 'events' key, extract events
            elif isinstance(data, dict) and "events" in data:
                parsed_workflow = data["events"]
            # Otherwise wrap single dict in a list
            elif isinstance(data, dict):
                parsed_workflow = [data]
            else:
                raise ValueError(
                    f"Unexpected data type after JSON parsing: {type(data)}"
                )

            # Now apply LLM-driven 3-step optimization
            print("  → Applying LLM-driven optimization (3-step process)...")
            try:
                # Prepare input for the workflow parse prompt
                workflow_json_str = json.dumps(
                    parsed_workflow, ensure_ascii=False, indent=2
                )
                parse_input = WorkflowParseInput(workflow_data=workflow_json_str)

                # Build the prompt
                system_prompt = self.workflow_parse_prompt.get_system_prompt()
                user_prompt = self.workflow_parse_prompt.build_prompt(parse_input)

                # Call LLM
                messages = [
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ]

                response = self.llm_client.generate(
                    messages, temperature=0.3, max_tokens=4000
                )

                # Parse the LLM response
                parse_output = self.workflow_parse_prompt.parse_response(
                    response.content
                )

                # Log the business intent and selector optimization
                print(f"  → Business Intent: {parse_output.business_intent}")
                if parse_output.selector_optimization:
                    print(
                        f"  → Selector optimizations: {len(parse_output.selector_optimization)} selectors analyzed"
                    )

                # Return the optimized events
                return parse_output.optimized_events

            except Exception as err:
                print(
                    f"  ⚠ Warning: LLM optimization failed ({str(err)}), falling back to basic parsing"
                )
                # Fallback: return the parsed workflow without optimization
                workflow_data = parsed_workflow

        # If workflow_data is already a list (not string), validate it
        if not isinstance(workflow_data, list):
            raise ValueError(f"Expected list of events, got {type(workflow_data)}")

        # Validate not empty
        if not workflow_data:
            raise ValueError("Workflow data is empty")

        # Validate each event is a dict
        for i, event in enumerate(workflow_data):
            if not isinstance(event, dict):
                raise ValueError(f"Event {i} is not a dictionary: {type(event)}")

        return workflow_data

    def _store_to_memory(
        self,
        domains: List[Domain],
        states: List[State],
        actions: List[Action],
        manages: List[Manage],
    ):
        """Store all structures to memory.

        Note: Intents are NOT stored separately - they are embedded in State nodes
        as part of state.intents and state.intent_ids fields.

        Args:
            domains: Domains to store
            states: States to store (containing embedded intents)
            actions: Actions to store
            manages: Manage edges to store
        """
        if not self.memory:
            return

        # Store domains
        for domain in domains:
            try:
                self.memory.create_domain(domain)
            except Exception as err:
                print(f"Warning: Failed to store domain {domain.id}: {str(err)}")

        # Store states (with embedded intents)
        # Each state contains its intents in state.intents field
        for state in states:
            try:
                self.memory.create_state(state)
            except Exception as err:
                print(f"Warning: Failed to store state {state.id}: {str(err)}")

        # Store actions
        for action in actions:
            try:
                self.memory.create_action(action)
            except Exception as err:
                print(f"Warning: Failed to store action: {str(err)}")

        # Store manages
        for manage in manages:
            try:
                self.memory.create_manage(manage)
            except Exception as err:
                print(f"Warning: Failed to store manage edge: {str(err)}")

    def _generate_intent_description(self, intent: Intent) -> str:
        """Generate a natural language description for an intent.

        Combines intent type, element text, and value to create a semantic description
        suitable for embedding and search.

        Args:
            intent: Intent object to describe

        Returns:
            Natural language description of the intent
        """
        parts = []

        # Map intent type to readable action
        type_mapping = {
            "ClickElement": "Click",
            "TypeText": "Type",
            "SelectOption": "Select",
            "Scroll": "Scroll",
            "Hover": "Hover over",
            "Submit": "Submit",
            "Navigate": "Navigate to",
            "Copy": "Copy",
            "Paste": "Paste",
        }

        action = type_mapping.get(intent.type, intent.type)
        parts.append(action)

        # Add element text if available
        if intent.text:
            parts.append(f"'{intent.text}'")

        # Add value if available (for input/select)
        if intent.value:
            if intent.type == "TypeText":
                parts.append(f"with value '{intent.value}'")
            elif intent.type == "SelectOption":
                parts.append(f"option '{intent.value}'")

        # Add element context if no text
        if not intent.text and intent.element_tag:
            parts.append(f"on {intent.element_tag} element")

        # Add page context
        if intent.page_title:
            parts.append(f"on page '{intent.page_title}'")

        return " ".join(parts)

    def _generate_intent_embeddings(self, intents: List[Intent]):
        """Generate embeddings for intents based on their descriptions.

        This method processes intents in batches to generate embeddings efficiently.
        For each intent, it first generates a description, then embeds it.

        Args:
            intents: List of Intent objects
        """
        if not self.embedding_model:
            return

        if not intents:
            print("  Warning: No intents to embed")
            return

        # Generate descriptions for all intents
        for intent in intents:
            if not intent.description:
                intent.description = self._generate_intent_description(intent)

        # Extract descriptions
        descriptions = [intent.description for intent in intents]

        try:
            # Generate embeddings in batch
            print(f"  Generating embeddings for {len(descriptions)} intent descriptions...")
            responses = self.embedding_model.embed_batch(descriptions)

            # Assign embeddings back to intents
            for intent, response in zip(intents, responses):
                intent.embedding_vector = response.to_list()

            print(f"  ✓ Generated {len(responses)} intent embeddings")

        except Exception as err:
            print(f"  Warning: Failed to generate intent embeddings: {str(err)}")

    def _generate_state_embeddings(self, states: List[State]):
        """Generate embeddings for states based on their descriptions.

        This method processes states in batches to generate embeddings efficiently.
        Each state's description is embedded and stored in state.embedding_vector.

        Args:
            states: List of State objects with descriptions
        """
        if not self.embedding_model:
            return

        # Collect states with descriptions
        states_with_descriptions = [s for s in states if s.description]

        if not states_with_descriptions:
            print("Warning: No states have descriptions to embed")
            return

        # Extract descriptions
        descriptions = [state.description for state in states_with_descriptions]

        try:
            # Generate embeddings in batch
            print(
                f"  Generating embeddings for {len(descriptions)} state descriptions..."
            )
            responses = self.embedding_model.embed_batch(descriptions)

            # Assign embeddings back to states
            for state, response in zip(states_with_descriptions, responses):
                state.embedding_vector = response.to_list()

            print(f"  ✓ Generated {len(responses)} state embeddings")

        except Exception as err:
            print(f"  Warning: Failed to generate state embeddings: {str(err)}")

    def _generate_workflow_description(
        self, workflow_data: List[Dict[str, Any]]
    ) -> str:
        """Generate natural language description of the workflow using LLM.

        Args:
            workflow_data: List of workflow events (original input data)

        Returns:
            Natural language description of the workflow
        """
        # Format workflow data for LLM prompt
        workflow_summary = json.dumps(workflow_data, ensure_ascii=False, indent=2)

        prompt = f"""请根据以下用户操作事件序列生成一个简洁的自然语言描述，概括整个工作流的核心过程。

事件序列:
{workflow_summary}

要求:
1. 用一到两句话描述整个工作流的核心目标和关键步骤
2. 突出用户的主要意图和操作路径
3. 使用通俗易懂的语言
4. 只返回描述文本，不要其他格式

示例: "用户浏览商品列表页，搜索咖啡相关商品，查看产品详情并复制了价格信息"

描述:"""

        try:
            messages = [LLMMessage(role="user", content=prompt)]
            response = self.llm_client.generate(
                messages, temperature=0.3, max_tokens=200
            )

            description = response.content.strip()
            # Remove quotes if LLM wrapped the description
            if description.startswith('"') and description.endswith('"'):
                description = description[1:-1]
            if description.startswith("描述:"):
                description = description[3:].strip()

            return description

        except Exception as err:
            print(f"Warning: Failed to generate workflow description: {str(err)}")
            # Fallback: simple description
            return f"用户工作流包含{len(workflow_data)}个操作事件"

    def _create_cognitive_phrase_from_workflow(
        self,
        states: List[State],
        actions: List[Action],
        workflow_data: List[Dict[str, Any]],
        user_id: str,
        session_id: str,
    ) -> Optional[CognitivePhrase]:
        """Create a cognitive phrase from the workflow path.

        Args:
            states: List of State objects
            actions: List of Action objects
            workflow_data: Original workflow events data
            user_id: User ID
            session_id: Session ID

        Returns:
            CognitivePhrase object if created successfully, None otherwise
        """
        if not states:
            return None

        # Sort states by timestamp to build path
        sorted_states = sorted(states, key=lambda s: s.timestamp)

        # Build state path (ordered list of state IDs)
        state_path = [s.id for s in sorted_states]

        # Build action path (ordered list of action types)
        # Create a map from (source, target) to action for quick lookup
        action_map = {(a.source, a.target): a.type for a in actions}

        action_path = []
        for i in range(len(sorted_states) - 1):
            source_id = sorted_states[i].id
            target_id = sorted_states[i + 1].id
            action_type = action_map.get((source_id, target_id), "navigate")
            action_path.append(action_type)

        # Calculate timestamps
        start_timestamp = sorted_states[0].timestamp
        end_timestamp = sorted_states[-1].end_timestamp or sorted_states[-1].timestamp
        duration = end_timestamp - start_timestamp

        # Generate description using LLM based on original workflow_data
        description = self._generate_workflow_description(workflow_data)

        # Create CognitivePhrase
        import time

        current_time = int(time.time() * 1000)

        phrase = CognitivePhrase(
            description=description,
            user_id=user_id,
            session_id=session_id,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            duration=duration,
            state_path=state_path,
            action_path=action_path,
            created_at=current_time,
        )

        # Generate embedding for phrase if embedding_model is available
        if self.embedding_model and description:
            try:
                response = self.embedding_model.embed(description)
                phrase.embedding_vector = response.to_list()
            except Exception as err:
                print(f"Warning: Failed to generate phrase embedding: {str(err)}")

        return phrase


__all__ = [
    "WorkflowProcessor",
    "WorkflowProcessingResult",
]
