"""Workflow Processor - URL-based event segmentation and State management.

This module implements the new processing pipeline from memory-graph-ontology-design.md:
1. Parse and validate input
2. Segment events by URL (split by navigate events)
3. For each segment:
   - Find or create State using URL index (real-time merge)
   - Add PageInstance
   - Create IntentSequence (if non-empty)
4. Create Actions between adjacent segments
5. Extract Domains and create Manage edges
6. Generate embeddings batch
7. Store all structures to memory
"""

import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from src.cloud_backend.memgraph.memory.memory import Memory
from src.cloud_backend.memgraph.memory.workflow_memory import WorkflowMemory
from src.cloud_backend.memgraph.ontology.action import Action
from src.cloud_backend.memgraph.ontology.cognitive_phrase import CognitivePhrase
from src.cloud_backend.memgraph.ontology.domain import Domain, Manage
from src.cloud_backend.memgraph.ontology.intent import Intent
from src.cloud_backend.memgraph.ontology.intent_sequence import IntentSequence
from src.cloud_backend.memgraph.ontology.page_instance import PageInstance
from src.cloud_backend.memgraph.ontology.state import State
from src.cloud_backend.memgraph.services.embedding_model import EmbeddingModel
from src.cloud_backend.memgraph.services.llm import LLMClient, LLMMessage


class URLSegment:
    """Represents a segment of events that occurred on the same URL.

    Attributes:
        url: The URL where these events occurred.
        page_title: Title of the page.
        timestamp: When user entered this URL.
        end_timestamp: When user left this URL.
        events: List of events that occurred on this URL.
    """

    def __init__(
        self,
        url: str,
        page_title: Optional[str] = None,
        timestamp: int = 0,
        end_timestamp: Optional[int] = None,
        events: Optional[List[Dict[str, Any]]] = None,
    ):
        self.url = url
        self.page_title = page_title
        self.timestamp = timestamp
        self.end_timestamp = end_timestamp
        self.events = events or []

    def add_event(self, event: Dict[str, Any]) -> None:
        """Add an event to this segment."""
        self.events.append(event)
        # Update end_timestamp
        event_ts = event.get("timestamp", 0)
        if event_ts and (self.end_timestamp is None or event_ts > self.end_timestamp):
            self.end_timestamp = event_ts

    def get_duration(self) -> int:
        """Get duration in milliseconds."""
        if self.end_timestamp and self.timestamp:
            return self.end_timestamp - self.timestamp
        return 0


class WorkflowProcessingResult:
    """Result of complete workflow processing.

    Attributes:
        domains: List of extracted Domain objects.
        states: List of State objects (may include existing reused states).
        page_instances: List of PageInstance objects created.
        intent_sequences: List of IntentSequence objects created.
        actions: List of Action objects created.
        manages: List of Manage edges created.
        metadata: Processing metadata with statistics.
        timestamp: When processing completed.
    """

    def __init__(
        self,
        domains: List[Domain],
        states: List[State],
        page_instances: List[PageInstance],
        intent_sequences: List[IntentSequence],
        actions: List[Action],
        manages: List[Manage],
        metadata: Dict[str, Any],
    ):
        self.domains = domains
        self.states = states
        self.page_instances = page_instances
        self.intent_sequences = intent_sequences
        self.actions = actions
        self.manages = manages
        self.metadata = metadata
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "domains": [d.to_dict() for d in self.domains],
            "states": [s.to_dict() for s in self.states],
            "page_instances": [p.to_dict() for p in self.page_instances],
            "intent_sequences": [s.to_dict() for s in self.intent_sequences],
            "actions": [a.to_dict() for a in self.actions],
            "manages": [m.to_dict() for m in self.manages],
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get processing summary."""
        return {
            "domain_count": len(self.domains),
            "state_count": len(self.states),
            "page_instance_count": len(self.page_instances),
            "intent_sequence_count": len(self.intent_sequences),
            "action_count": len(self.actions),
            "manage_count": len(self.manages),
            "new_states": self.metadata.get("new_states", 0),
            "reused_states": self.metadata.get("reused_states", 0),
            "processing_time_ms": self.metadata.get("processing_time_ms", 0),
        }


class WorkflowProcessor:
    """URL-based workflow processor with State deduplication.

    This processor implements the new pipeline from memory-graph-ontology-design.md:
    - Segment events by URL (navigate events create new segments)
    - Use URL index for O(1) State lookup and real-time merge
    - Create PageInstance for each URL visit
    - Create IntentSequence from non-navigate events
    - Create Actions between consecutive States
    """

    def __init__(
        self,
        llm_client: LLMClient,
        memory: Optional[WorkflowMemory] = None,
        model_name: str = "gpt-4",
        embedding_model: Optional[EmbeddingModel] = None,
    ):
        """Initialize WorkflowProcessor.

        Args:
            llm_client: LLM client for description generation.
            memory: WorkflowMemory instance for storage.
            model_name: Name of LLM model to use.
            embedding_model: Embedding model for vector generation.

        Raises:
            ValueError: If llm_client is None.
        """
        if not llm_client:
            raise ValueError("LLM client is required for WorkflowProcessor")

        self.llm_client = llm_client
        self.memory = memory
        self.model_name = model_name
        self.embedding_model = embedding_model

    def process_workflow(
        self,
        workflow_data: Union[List[Dict[str, Any]], str],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        store_to_memory: bool = True,
    ) -> WorkflowProcessingResult:
        """Process complete workflow through URL-based pipeline.

        Args:
            workflow_data: Workflow events (list of dicts or JSON string).
            user_id: User ID for attribution.
            session_id: Session ID for grouping.
            store_to_memory: Whether to store results to memory.

        Returns:
            WorkflowProcessingResult with all extracted structures.

        Raises:
            ValueError: If input is invalid or processing fails.
        """
        start_time = datetime.now()
        print(f"\n{'='*60}")
        print("Starting Workflow Processing Pipeline (URL-based)")
        print(f"{'='*60}\n")

        # Stage 0: Parse and validate input
        print("Stage 0: Parsing input data...")
        events = self._parse_input(workflow_data)
        print(f"  Parsed {len(events)} events\n")

        # Stage 1: Segment events by URL
        print("Stage 1: Segmenting events by URL...")
        segments = self._segment_by_url(events)
        print(f"  Created {len(segments)} URL segments")
        for seg in segments:
            print(f"    - {seg.url} ({len(seg.events)} events)")
        print()

        # Stage 2: Process segments - find/create States, PageInstances, IntentSequences
        print("Stage 2: Processing segments...")
        states = []
        state_is_new_flags = []  # Track which states are new
        page_instances = []
        intent_sequences = []
        new_state_count = 0
        reused_state_count = 0

        for segment in segments:
            # Skip segments with empty URL
            if not segment.url:
                print(f"    Warning: Skipping segment with empty URL")
                continue

            # Find or create State
            state, is_new = self._find_or_create_state(
                segment=segment,
                user_id=user_id,
                session_id=session_id,
            )
            states.append(state)
            state_is_new_flags.append(is_new)

            if is_new:
                new_state_count += 1
                print(f"    Created new State: {state.id[:8]}... for {segment.url}")
            else:
                reused_state_count += 1
                print(f"    Reused existing State: {state.id[:8]}... for {segment.url}")

            # Create PageInstance
            instance = self._create_page_instance(
                segment=segment,
                state_id=state.id,
                user_id=user_id,
                session_id=session_id,
            )
            page_instances.append(instance)

            # Create IntentSequence (if has non-navigate events)
            sequence = self._create_intent_sequence(
                segment=segment,
                state_id=state.id,
                user_id=user_id,
                session_id=session_id,
            )
            if sequence:
                intent_sequences.append(sequence)

        print(f"  New states: {new_state_count}, Reused states: {reused_state_count}")
        print(f"  Page instances: {len(page_instances)}")
        print(f"  Intent sequences: {len(intent_sequences)}\n")

        # Stage 3: Create Actions between consecutive States
        print("Stage 3: Creating Actions...")
        actions = self._create_actions(
            segments=segments,
            states=states,
            user_id=user_id,
            session_id=session_id,
        )
        print(f"  Created {len(actions)} actions\n")

        # Stage 4: Extract Domains and create Manage edges
        print("Stage 4: Extracting Domains and Manage edges...")
        domains, manages = self._extract_domains_and_manages(
            states=states,
            user_id=user_id,
        )
        print(f"  Created {len(domains)} domains and {len(manages)} manage edges\n")

        # Stage 5: Generate descriptions using LLM
        print("Stage 5: Generating descriptions...")
        # Only generate descriptions for newly created states
        new_states = [s for s, is_new in zip(states, state_is_new_flags) if is_new]
        self._generate_descriptions(
            states=new_states,
            intent_sequences=intent_sequences,
            actions=actions,
        )
        print()

        # Stage 6: Generate embeddings
        if self.embedding_model:
            print("Stage 6: Generating embeddings...")
            self._generate_embeddings(
                states=states,
                intent_sequences=intent_sequences,
            )
            print()

        # Stage 7: Store to memory
        if store_to_memory and self.memory:
            print("Stage 7: Storing to memory...")
            self._store_to_memory(
                domains=domains,
                states=states,
                page_instances=page_instances,
                intent_sequences=intent_sequences,
                actions=actions,
                manages=manages,
            )
            print("  Stored all structures to memory")

            # Create cognitive phrase
            cognitive_phrase = self._create_cognitive_phrase(
                states=states,
                actions=actions,
                workflow_data=events,
                user_id=user_id,
                session_id=session_id,
            )
            if cognitive_phrase:
                success = self.memory.create_phrase(cognitive_phrase)
                if success:
                    print(f"  Created cognitive phrase: {cognitive_phrase.description[:80]}...")
        else:
            print("Stage 7: Skipping memory storage")
        print()

        # Calculate processing time
        end_time = datetime.now()
        processing_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # Collect metadata
        metadata = {
            "user_id": user_id,
            "session_id": session_id,
            "event_count": len(events),
            "segment_count": len(segments),
            "new_states": new_state_count,
            "reused_states": reused_state_count,
            "stored_to_memory": store_to_memory and self.memory is not None,
            "llm_model": self.model_name,
            "processing_time_ms": processing_time_ms,
        }

        result = WorkflowProcessingResult(
            domains=domains,
            states=states,
            page_instances=page_instances,
            intent_sequences=intent_sequences,
            actions=actions,
            manages=manages,
            metadata=metadata,
        )

        # Print summary
        print(f"{'='*60}")
        print("Processing Complete!")
        print(f"{'='*60}")
        summary = result.get_summary()
        for key, value in summary.items():
            print(f"  {key}: {value}")
        print(f"{'='*60}\n")

        return result

    def _parse_input(
        self, workflow_data: Union[List[Dict[str, Any]], str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Parse and validate workflow input.

        Supports multiple input formats:
        1. List of events directly
        2. JSON string of list or dict
        3. Recording format: {"operations": [...], "session_id": "..."}
        4. Events format: {"events": [...]}

        Args:
            workflow_data: Raw workflow data.

        Returns:
            List of normalized event dictionaries.

        Raises:
            ValueError: If input is invalid.
        """
        # Parse JSON string
        if isinstance(workflow_data, str):
            try:
                data = json.loads(workflow_data)
            except json.JSONDecodeError as err:
                raise ValueError(f"Invalid JSON input: {str(err)}") from err
        else:
            data = workflow_data

        # Extract events from various formats
        if isinstance(data, list):
            events = data
        elif isinstance(data, dict):
            # Recording format: {"operations": [...]}
            if "operations" in data:
                events = data["operations"]
            # Events format: {"events": [...]}
            elif "events" in data:
                events = data["events"]
            else:
                events = [data]
        else:
            raise ValueError(f"Unexpected data type: {type(data)}")

        if not isinstance(events, list):
            raise ValueError(f"Expected list of events, got {type(events)}")

        if not events:
            raise ValueError("Workflow data is empty")

        # Normalize events
        normalized = []
        for i, event in enumerate(events):
            if not isinstance(event, dict):
                raise ValueError(f"Event {i} is not a dictionary: {type(event)}")
            normalized.append(self._normalize_event(event))

        return normalized

    def _normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize event to standard format.

        Handles differences between recording format and simple format:
        - timestamp: string -> milliseconds int
        - element: nested object -> flattened fields
        - page_title vs title

        Args:
            event: Raw event dictionary.

        Returns:
            Normalized event dictionary.
        """
        normalized = dict(event)

        # Normalize timestamp
        ts = event.get("timestamp")
        if isinstance(ts, str):
            normalized["timestamp"] = self._parse_timestamp(ts)
        elif ts is None:
            normalized["timestamp"] = 0

        # Normalize page_title / title
        if "page_title" not in normalized and "title" in normalized:
            normalized["page_title"] = normalized["title"]
        elif "title" not in normalized and "page_title" in normalized:
            normalized["title"] = normalized["page_title"]

        # Flatten element object (recording format)
        element = event.get("element", {})
        if element and isinstance(element, dict):
            if "tagName" in element and "element_tag" not in normalized:
                normalized["element_tag"] = element.get("tagName", "").lower()
            if "className" in element and "element_class" not in normalized:
                normalized["element_class"] = element.get("className", "")
            if "textContent" in element and "text" not in normalized:
                normalized["text"] = element.get("textContent", "")[:200]  # Truncate long text
            if "xpath" in element and "xpath" not in normalized:
                normalized["xpath"] = element.get("xpath", "")
            if "href" in element and "href" not in normalized:
                normalized["href"] = element.get("href", "")

        # Flatten data object (recording format)
        data = event.get("data", {})
        if data and isinstance(data, dict):
            if "selectedText" in data and "text" not in normalized:
                normalized["text"] = data.get("selectedText", "")[:200]
            if "direction" in data:
                normalized["scroll_direction"] = data.get("direction")
            if "distance" in data:
                normalized["scroll_distance"] = data.get("distance")

        return normalized

    def _parse_timestamp(self, ts: str) -> int:
        """Parse timestamp string to milliseconds.

        Supports formats:
        - "2026-01-20 13:31:56" (local time)
        - "2026-01-20T13:31:56" (ISO format)
        - "2026-01-20 05:31:56" (UTC time)

        Args:
            ts: Timestamp string.

        Returns:
            Timestamp in milliseconds.
        """
        from datetime import datetime

        try:
            # Try common formats
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S.%f",
            ]:
                try:
                    dt = datetime.strptime(ts, fmt)
                    return int(dt.timestamp() * 1000)
                except ValueError:
                    continue

            # Fallback: return 0
            print(f"Warning: Could not parse timestamp: {ts}")
            return 0
        except Exception:
            return 0

    def _segment_by_url(
        self, events: List[Dict[str, Any]]
    ) -> List[URLSegment]:
        """Segment events by URL based on navigate events.

        Navigate events create new segments. All events between two
        navigate events belong to the same segment.

        Args:
            events: List of workflow events.

        Returns:
            List of URLSegment objects.
        """
        segments = []
        current_segment = None

        for event in events:
            event_type = event.get("type", "").lower()
            url = event.get("url") or event.get("page_url", "")
            page_title = event.get("page_title") or event.get("title", "")
            timestamp = event.get("timestamp", 0)

            # Navigate event starts a new segment
            if event_type in ("navigate", "navigation", "pageload", "page_load"):
                # Close current segment
                if current_segment:
                    segments.append(current_segment)

                # Start new segment
                current_segment = URLSegment(
                    url=url,
                    page_title=page_title,
                    timestamp=timestamp,
                )

            # Non-navigate event goes into current segment
            elif current_segment:
                current_segment.add_event(event)

            # First event is not navigate - create segment from it
            else:
                current_segment = URLSegment(
                    url=url,
                    page_title=page_title,
                    timestamp=timestamp,
                )
                # Add this event if it's not just a URL event
                if event_type and event_type not in ("url", "page"):
                    current_segment.add_event(event)

        # Close last segment
        if current_segment:
            segments.append(current_segment)

        return segments

    def _find_or_create_state(
        self,
        segment: URLSegment,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> tuple[State, bool]:
        """Find existing State by URL or create a new one.

        Uses WorkflowMemory.find_or_create_state for URL index lookup
        and real-time merge.

        Args:
            segment: URLSegment to process.
            user_id: User ID.
            session_id: Session ID.

        Returns:
            Tuple of (State, is_new).
        """
        # Extract domain from URL
        domain = self._extract_domain_from_url(segment.url)

        if self.memory:
            return self.memory.find_or_create_state(
                url=segment.url,
                page_title=segment.page_title,
                timestamp=segment.timestamp,
                domain=domain,
                user_id=user_id,
                session_id=session_id,
            )

        # No memory - create State without storage
        state = State(
            page_url=segment.url,
            page_title=segment.page_title,
            timestamp=segment.timestamp,
            domain=domain,
            user_id=user_id,
            session_id=session_id,
            instances=[],
            intent_sequences=[],
        )
        return state, True

    def _create_page_instance(
        self,
        segment: URLSegment,
        state_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> PageInstance:
        """Create PageInstance from segment.

        Args:
            segment: URLSegment to process.
            state_id: ID of the parent State.
            user_id: User ID.
            session_id: Session ID.

        Returns:
            PageInstance object.
        """
        instance = PageInstance(
            url=segment.url,
            page_title=segment.page_title,
            timestamp=segment.timestamp,
            user_id=user_id,
            session_id=session_id,
        )

        # Add to State in memory
        if self.memory:
            self.memory.add_page_instance(state_id, instance)

        return instance

    def _create_intent_sequence(
        self,
        segment: URLSegment,
        state_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[IntentSequence]:
        """Create IntentSequence from segment events.

        Design decision: Don't create empty IntentSequences.

        Args:
            segment: URLSegment to process.
            state_id: ID of the parent State.
            user_id: User ID.
            session_id: Session ID.

        Returns:
            IntentSequence object if has events, None otherwise.
        """
        # Filter out non-action events
        action_events = [
            e for e in segment.events
            if e.get("type", "").lower() not in ("navigate", "navigation", "pageload", "page_load", "url", "page")
        ]

        # Don't create empty IntentSequence
        if not action_events:
            return None

        # Convert events to Intents
        intents = []
        for event in action_events:
            intent = self._event_to_intent(event)
            if intent:
                intents.append(intent)

        if not intents:
            return None

        sequence = IntentSequence(
            timestamp=segment.timestamp,
            intents=intents,
            user_id=user_id,
            session_id=session_id,
        )

        # Add to State in memory
        if self.memory:
            self.memory.add_intent_sequence(state_id, sequence)

        return sequence

    def _event_to_intent(self, event: Dict[str, Any]) -> Optional[Intent]:
        """Convert an event dictionary to an Intent object.

        Args:
            event: Event dictionary.

        Returns:
            Intent object if valid, None otherwise.
        """
        event_type = event.get("type", "").lower()

        # Map event types to Intent types
        type_mapping = {
            "click": "ClickElement",
            "clickelement": "ClickElement",
            "type": "TypeText",
            "typetext": "TypeText",
            "input": "TypeText",
            "select": "SelectOption",
            "selectoption": "SelectOption",
            "scroll": "Scroll",
            "hover": "Hover",
            "submit": "Submit",
            "copy": "Copy",
            "paste": "Paste",
        }

        intent_type = type_mapping.get(event_type)
        if not intent_type:
            # Use original type if not in mapping
            intent_type = event.get("type", "Unknown")

        try:
            intent = Intent(
                type=intent_type,
                timestamp=event.get("timestamp", 0),
                element_tag=event.get("element_tag") or event.get("tag", ""),
                element_id=event.get("element_id") or event.get("id", ""),
                element_class=event.get("element_class") or event.get("class", ""),
                text=event.get("text") or event.get("element_text", ""),
                value=event.get("value") or event.get("input_value", ""),
                selector=event.get("selector", ""),
                page_url=event.get("page_url") or event.get("url", ""),
                page_title=event.get("page_title") or event.get("title", ""),
            )
            return intent
        except Exception as e:
            print(f"Warning: Failed to create Intent from event: {e}")
            return None

    def _create_actions(
        self,
        segments: List[URLSegment],
        states: List[State],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Action]:
        """Create Actions between consecutive States.

        Args:
            segments: List of URL segments.
            states: List of States (same order as segments).
            user_id: User ID.
            session_id: Session ID.

        Returns:
            List of Action objects.
        """
        actions = []

        for i in range(len(states) - 1):
            source_state = states[i]
            target_state = states[i + 1]
            source_segment = segments[i]
            target_segment = segments[i + 1]

            # Skip if same state (URL)
            if source_state.id == target_state.id:
                continue

            action = Action(
                source=source_state.id,
                target=target_state.id,
                type="navigate",
                timestamp=target_segment.timestamp,
                user_id=user_id,
                session_id=session_id,
            )
            actions.append(action)

        return actions

    def _extract_domain_from_url(self, url: str) -> str:
        """Extract domain from URL.

        Args:
            url: URL to extract domain from.

        Returns:
            Domain string.
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc or url
        except Exception:
            return url

    def _extract_domains_and_manages(
        self,
        states: List[State],
        user_id: Optional[str] = None,
    ) -> tuple[List[Domain], List[Manage]]:
        """Extract Domains and create Manage edges.

        Args:
            states: List of State objects.
            user_id: User ID.

        Returns:
            Tuple of (domains, manages).
        """
        # Collect unique domains from states
        domain_map: Dict[str, Domain] = {}
        manages = []

        for state in states:
            domain_name = state.domain
            if not domain_name:
                domain_name = self._extract_domain_from_url(state.page_url)

            if domain_name not in domain_map:
                domain = Domain(
                    domain_name=domain_name,
                    domain_url=f"https://{domain_name}" if not domain_name.startswith("http") else domain_name,
                    domain_type="website",
                    user_id=user_id,
                )
                domain_map[domain_name] = domain

            # Create Manage edge
            domain = domain_map[domain_name]
            manage = Manage(
                domain_id=domain.id,
                state_id=state.id,
                user_id=user_id,
                first_visit=state.timestamp,
                last_visit=state.timestamp,
                visit_count=1,
            )
            manages.append(manage)

        return list(domain_map.values()), manages

    def _generate_descriptions(
        self,
        states: List[State],
        intent_sequences: List[IntentSequence],
        actions: List[Action],
    ) -> None:
        """Generate descriptions using LLM.

        Args:
            states: States that need descriptions.
            intent_sequences: IntentSequences that need descriptions.
            actions: Actions that need descriptions.
        """
        # Generate State descriptions
        for state in states:
            if not state.description:
                state.description = self._generate_state_description(state)
                print(f"    Generated State description: {state.description[:50]}...")

        # Generate IntentSequence descriptions
        for sequence in intent_sequences:
            if not sequence.description:
                sequence.description = self._generate_intent_sequence_description(sequence)
                print(f"    Generated IntentSequence description: {sequence.description[:50]}...")

        # Generate Action descriptions
        for action in actions:
            if not action.description:
                action.description = self._generate_action_description(action)

    def _generate_state_description(self, state: State) -> str:
        """Generate description for a State using LLM.

        Args:
            state: State to describe.

        Returns:
            Description string.
        """
        prompt = f"""请用简洁的中文描述这个页面的类型和用途。

URL: {state.page_url}
页面标题: {state.page_title or "无"}

要求:
1. 用一句话描述页面类型（如"商品详情页"、"搜索结果页"等）
2. 不要包含具体的URL或ID
3. 只返回描述文本

示例: "淘宝商品详情页，展示商品信息和购买选项"

描述:"""

        try:
            messages = [LLMMessage(role="user", content=prompt)]
            response = self.llm_client.generate(
                messages, temperature=0.3, max_tokens=100
            )
            return response.content.strip()
        except Exception as e:
            print(f"Warning: Failed to generate state description: {e}")
            return f"页面: {state.page_title or state.page_url}"

    def _generate_intent_sequence_description(self, sequence: IntentSequence) -> str:
        """Generate description for an IntentSequence using LLM.

        Args:
            sequence: IntentSequence to describe.

        Returns:
            Description string.
        """
        # Build intent summary
        intent_summary = []
        for intent in sequence.intents:
            if isinstance(intent, dict):
                intent_type = intent.get("type", "")
                text = intent.get("text", "")
                value = intent.get("value", "")
            else:
                intent_type = intent.type
                text = intent.text or ""
                value = intent.value or ""

            if text:
                intent_summary.append(f"{intent_type}: {text}")
            elif value:
                intent_summary.append(f"{intent_type}: {value}")
            else:
                intent_summary.append(intent_type)

        intents_str = "\n".join(f"- {s}" for s in intent_summary[:10])

        prompt = f"""请用简洁的中文描述这组操作的目的。

操作序列:
{intents_str}

要求:
1. 用一句话描述这组操作的核心目的
2. 不要列举具体操作
3. 只返回描述文本

示例: "搜索并筛选咖啡商品"

描述:"""

        try:
            messages = [LLMMessage(role="user", content=prompt)]
            response = self.llm_client.generate(
                messages, temperature=0.3, max_tokens=100
            )
            return response.content.strip()
        except Exception as e:
            print(f"Warning: Failed to generate sequence description: {e}")
            return f"操作序列 ({len(sequence.intents)} 个操作)"

    def _generate_action_description(self, action: Action) -> str:
        """Generate description for an Action.

        Args:
            action: Action to describe.

        Returns:
            Description string.
        """
        return f"从页面导航到下一页面"

    def _generate_embeddings(
        self,
        states: List[State],
        intent_sequences: List[IntentSequence],
    ) -> None:
        """Generate embeddings for States and IntentSequences.

        Args:
            states: States to embed.
            intent_sequences: IntentSequences to embed.
        """
        if not self.embedding_model:
            return

        # Collect all descriptions
        texts = []
        items = []

        for state in states:
            if state.description:
                texts.append(state.description)
                items.append(("state", state))

        for sequence in intent_sequences:
            if sequence.description:
                texts.append(sequence.description)
                items.append(("sequence", sequence))

        if not texts:
            print("    No descriptions to embed")
            return

        try:
            print(f"    Generating embeddings for {len(texts)} items...")
            responses = self.embedding_model.embed_batch(texts)

            for (item_type, item), response in zip(items, responses):
                if item_type == "state":
                    item.embedding_vector = response.to_list()
                else:
                    item.embedding_vector = response.to_list()

            print(f"    Generated {len(responses)} embeddings")
        except Exception as e:
            print(f"Warning: Failed to generate embeddings: {e}")

    def _store_to_memory(
        self,
        domains: List[Domain],
        states: List[State],
        page_instances: List[PageInstance],
        intent_sequences: List[IntentSequence],
        actions: List[Action],
        manages: List[Manage],
    ) -> None:
        """Store all structures to memory.

        Args:
            domains: Domains to store.
            states: States to store.
            page_instances: PageInstances (already added to states).
            intent_sequences: IntentSequences (already added to states).
            actions: Actions to store.
            manages: Manages to store.
        """
        if not self.memory:
            return

        # Store domains
        for domain in domains:
            try:
                self.memory.create_domain(domain)
            except Exception as e:
                print(f"Warning: Failed to store domain {domain.id}: {e}")

        # Note: States are already updated by add_page_instance and add_intent_sequence
        # We only need to update descriptions and embeddings for new states
        for state in states:
            # Re-read from memory to get the version with instances/sequences
            memory_state = self.memory.get_state(state.id)
            if memory_state:
                # Update description and embedding from our local state object
                if state.description:
                    memory_state.description = state.description
                if state.embedding_vector:
                    memory_state.embedding_vector = state.embedding_vector
                try:
                    self.memory.state_manager.update_state(memory_state)
                except Exception as e:
                    print(f"Warning: Failed to update state {state.id}: {e}")

        # Store actions
        for action in actions:
            try:
                self.memory.create_action(action)
            except Exception as e:
                print(f"Warning: Failed to store action: {e}")

        # Store manages
        for manage in manages:
            try:
                self.memory.create_manage(manage)
            except Exception as e:
                print(f"Warning: Failed to store manage edge: {e}")

    def _create_cognitive_phrase(
        self,
        states: List[State],
        actions: List[Action],
        workflow_data: List[Dict[str, Any]],
        user_id: Optional[str],
        session_id: Optional[str],
    ) -> Optional[CognitivePhrase]:
        """Create a cognitive phrase from the workflow.

        Args:
            states: List of State objects.
            actions: List of Action objects.
            workflow_data: Original workflow events.
            user_id: User ID.
            session_id: Session ID.

        Returns:
            CognitivePhrase if created, None otherwise.
        """
        if not states:
            return None

        # Sort states by timestamp
        sorted_states = sorted(states, key=lambda s: s.timestamp)

        # Build paths
        state_path = [s.id for s in sorted_states]
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

        # Generate description
        description = self._generate_workflow_description(workflow_data)

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

        # Generate embedding
        if self.embedding_model and description:
            try:
                response = self.embedding_model.embed(description)
                phrase.embedding_vector = response.to_list()
            except Exception as e:
                print(f"Warning: Failed to generate phrase embedding: {e}")

        return phrase

    def _generate_workflow_description(
        self, workflow_data: List[Dict[str, Any]]
    ) -> str:
        """Generate description for the workflow using LLM.

        Args:
            workflow_data: List of workflow events.

        Returns:
            Description string.
        """
        workflow_summary = json.dumps(workflow_data[:20], ensure_ascii=False, indent=2)

        prompt = f"""请根据以下用户操作事件序列生成一个简洁的自然语言描述。

事件序列:
{workflow_summary}

要求:
1. 用一到两句话描述整个工作流的核心目标和关键步骤
2. 突出用户的主要意图和操作路径
3. 使用通俗易懂的语言
4. 只返回描述文本

示例: "用户浏览商品列表页，搜索咖啡相关商品，查看产品详情并复制了价格信息"

描述:"""

        try:
            messages = [LLMMessage(role="user", content=prompt)]
            response = self.llm_client.generate(
                messages, temperature=0.3, max_tokens=200
            )
            return response.content.strip()
        except Exception as e:
            print(f"Warning: Failed to generate workflow description: {e}")
            return f"用户工作流包含{len(workflow_data)}个操作事件"


__all__ = [
    "WorkflowProcessor",
    "WorkflowProcessingResult",
    "URLSegment",
]
