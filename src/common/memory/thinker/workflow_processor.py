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

import hashlib
import json
import re
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from urllib.parse import parse_qsl, urlparse

from src.common.memory.memory.memory import Memory
from src.common.memory.memory.workflow_memory import WorkflowMemory
from src.common.memory.ontology.action import Action
from src.common.memory.ontology.cognitive_phrase import CognitivePhrase, ExecutionStep
from src.common.memory.ontology.domain import Domain, Manage, normalize_domain_url
from src.common.memory.ontology.intent import Intent
from src.common.memory.ontology.intent_sequence import IntentSequence
from src.common.memory.ontology.page_instance import PageInstance

logger = logging.getLogger(__name__)

from src.common.memory.ontology.state import State
from src.common.memory.services.embedding_service import EmbeddingService
from src.common.llm import AnthropicProvider, parse_json_with_repair


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

    # Important modifiers should be preserved if the model outputs them.
    _STATE_PROTECTED_MODIFIER_HINTS = (
        "每日",
        "每天",
        "每周",
        "每月",
        "实时",
        "最新",
        "今日",
        "当日",
        "本周",
        "本月",
        "daily",
        "weekly",
        "monthly",
        "realtime",
        "latest",
        "today",
    )

    def __init__(
        self,
        llm_provider: Optional[AnthropicProvider] = None,
        memory: Optional[WorkflowMemory] = None,
        embedding_service: Optional[EmbeddingService] = None,
        simple_llm_provider: Optional[AnthropicProvider] = None,
    ):
        """Initialize WorkflowProcessor.

        Args:
            llm_provider: AnthropicProvider for complex LLM tasks.
                         If None, descriptions will use default values.
            memory: WorkflowMemory instance for storage.
            embedding_service: EmbeddingService with user API key for vector generation.
            simple_llm_provider: Light AnthropicProvider for description generation.
                                If None, uses llm_provider.
        """
        self.llm_provider = llm_provider
        self.memory = memory
        self.embedding_service = embedding_service
        # Use simple provider for descriptions, fall back to main provider
        self.simple_llm_provider = simple_llm_provider or llm_provider

    async def process_workflow(
        self,
        workflow_data: Union[List[Dict[str, Any]], str],
        session_id: Optional[str] = None,
        store_to_memory: bool = True,
        snapshots: Optional[Dict[str, Dict]] = None,
        skip_cognitive_phrase: bool = False,
    ) -> WorkflowProcessingResult:
        """Process complete workflow through URL-based pipeline.

        Args:
            workflow_data: Workflow events (list of dicts or JSON string).
            session_id: Session ID for grouping.
            store_to_memory: Whether to store results to memory.
            snapshots: URL -> snapshot data mapping from recording.
                Each value: {url, snapshot/snapshot_text, captured_at}
            skip_cognitive_phrase: If True, skip CognitivePhrase creation.
                Useful for online learning where per-subtask phrases add noise.

        Returns:
            WorkflowProcessingResult with all extracted structures.

        Raises:
            ValueError: If input is invalid or processing fails.
        """
        start_time = datetime.now()
        logger.info(f"\n{'='*60}")
        logger.info("Starting Workflow Processing Pipeline (URL-based)")
        logger.info(f"{'='*60}\n")

        # Stage 0: Parse and validate input
        logger.info("Stage 0: Parsing input data...")
        events = self._parse_input(workflow_data)
        logger.info(f"  Parsed {len(events)} events\n")

        # Stage 1: Segment events by URL
        logger.info("Stage 1: Segmenting events by URL...")
        segments = self._segment_by_url(events)
        logger.info(f"  Created {len(segments)} URL segments")
        for seg in segments:
            logger.info(f"    - {seg.url} ({len(seg.events)} events)")
        logger.info("")

        # Stage 2: Process segments - find/create States, PageInstances, IntentSequences
        logger.info("Stage 2: Processing segments...")
        states = []
        valid_segments = []  # Track segments that have valid URLs (same order as states)
        state_is_new_flags = []  # Track which states are new
        page_instances = []
        intent_sequences = []
        new_state_count = 0
        reused_state_count = 0
        domain_root_id_map: Dict[str, str] = {}
        # Cache for domain-level root signatures (domain|ROOT)
        domain_root_sig_map: Dict[str, str] = {}
        last_path_sig_by_domain: Dict[str, str] = {}
        last_segment_by_domain: Dict[str, URLSegment] = {}
        last_domain_key: Optional[str] = None

        def _load_domain_root(domain_key: str) -> None:
            if domain_key in domain_root_id_map:
                return
            if not self.memory:
                return
            try:
                existing_domain = self.memory.get_domain(domain_key)
            except Exception as exc:
                print(f"Warning: Failed to load domain {domain_key}: {exc}")
                return
            if existing_domain and isinstance(existing_domain.attributes, dict):
                root_id = existing_domain.attributes.get("root_state_id")
                if root_id:
                    domain_root_id_map[domain_key] = root_id

        def _get_domain_root_sig(domain_key: str) -> str:
            if domain_key not in domain_root_sig_map:
                domain_root_sig_map[domain_key] = self._hash_domain_root_sig(domain_key)
            return domain_root_sig_map[domain_key]

        for segment in segments:
            # Skip segments with empty URL
            if not segment.url:
                logger.info(f"    Warning: Skipping segment with empty URL")
                continue

            domain_key = self._extract_domain_from_url(segment.url)
            if domain_key:
                _load_domain_root(domain_key)

            candidate_path_sig = None
            if domain_key and last_domain_key == domain_key:
                prev_segment = last_segment_by_domain.get(domain_key)
                prev_path_sig = last_path_sig_by_domain.get(domain_key)
                if prev_segment and prev_path_sig:
                    trigger_event = self._find_transition_trigger(prev_segment)
                    action_sig = self._build_action_signature(trigger_event)
                    candidate_path_sig = self._extend_path_sig(prev_path_sig, action_sig)
            if domain_key and not candidate_path_sig:
                root_sig = _get_domain_root_sig(domain_key)
                entry_sig = self._build_entry_signature(segment.url)
                candidate_path_sig = self._extend_path_sig(root_sig, entry_sig)

            # Find or create State
            state, is_new = self._find_or_create_state(
                segment=segment,
                session_id=session_id,
                domain_key=domain_key,
                path_sig=candidate_path_sig,
            )
            states.append(state)
            valid_segments.append(segment)  # Keep track of valid segments
            state_is_new_flags.append(is_new)

            # Assign root for new domains (first-seen state)
            if domain_key and domain_key not in domain_root_id_map:
                domain_root_id_map[domain_key] = state.id

            # Backfill path_sig if missing and we have a stable candidate
            if candidate_path_sig and not state.path_sig:
                state.path_sig = candidate_path_sig
                if self.memory:
                    try:
                        self.memory.state_manager.update_state(state)
                    except Exception as exc:
                        print(f"Warning: Failed to update state path_sig: {exc}")

            if domain_key and state.path_sig:
                last_path_sig_by_domain[domain_key] = state.path_sig
                last_segment_by_domain[domain_key] = segment
                last_domain_key = domain_key
            else:
                last_domain_key = domain_key

            if is_new:
                new_state_count += 1
                logger.info(f"    Created new State: {state.id[:8]}... for {segment.url}")
            else:
                reused_state_count += 1
                logger.info(f"    Reused existing State: {state.id[:8]}... for {segment.url}")

            # Create PageInstance
            instance = self._create_page_instance(
                segment=segment,
                state_id=state.id,
                session_id=session_id,
                snapshots=snapshots,
            )
            page_instances.append(instance)

        # Second pass: Create IntentSequences with navigation markers (v2)
        # We need to know all states first to set navigation_target_state_id
        for idx, (segment, state) in enumerate(zip(valid_segments, states)):
            # Check if this segment leads to navigation (has a next state)
            causes_navigation = False
            navigation_target_state_id = None
            
            if idx < len(states) - 1:
                next_state = states[idx + 1]
                # Check if URL changed (real navigation, not same-state)
                if state.id != next_state.id:
                    # Check if there's a trigger operation in this segment
                    trigger_event = self._find_transition_trigger(segment)
                    if trigger_event:
                        causes_navigation = True
                        navigation_target_state_id = next_state.id
            
            # Create IntentSequence (if has non-navigate events)
            sequence = self._create_intent_sequence(
                segment=segment,
                state_id=state.id,
                session_id=session_id,
                causes_navigation=causes_navigation,
                navigation_target_state_id=navigation_target_state_id,
            )
            if sequence:
                intent_sequences.append(sequence)

        logger.info(f"  New states: {new_state_count}, Reused states: {reused_state_count}")
        logger.info(f"  Page instances: {len(page_instances)}")
        logger.info(f"  Intent sequences: {len(intent_sequences)}\n")

        # Stage 3: Create Actions between consecutive States
        logger.info("Stage 3: Creating Actions...")
        actions = self._create_actions(
            segments=valid_segments,  # Use valid_segments (same order as states)
            states=states,
            intent_sequences=intent_sequences,
            session_id=session_id,
        )
        logger.info(f"  Created {len(actions)} actions\n")

        # Stage 4: Extract Domains and create Manage edges
        logger.info("Stage 4: Extracting Domains and Manage edges...")
        domains, manages = self._extract_domains_and_manages(
            states=states,
            domain_root_id_map=domain_root_id_map,
        )
        logger.info(f"  Created {len(domains)} domains and {len(manages)} manage edges\n")

        # Stage 5: Generate descriptions using LLM
        logger.info("Stage 5: Generating descriptions...")
        # Only generate descriptions for newly created states
        new_states = [s for s, is_new in zip(states, state_is_new_flags) if is_new]
        await self._generate_descriptions(
            states=new_states,
            all_states=states,
            intent_sequences=intent_sequences,
            actions=actions,
        )
        logger.info("")

        # Stage 6: Generate embeddings
        if self.embedding_service:
            logger.info("Stage 6: Generating embeddings...")
            self._generate_embeddings(
                states=states,
                intent_sequences=intent_sequences,
            )
            logger.info("")

        # Stage 7: Store to memory
        if store_to_memory and self.memory:
            logger.info("Stage 7: Storing to memory...")
            self._store_to_memory(
                domains=domains,
                states=states,
                page_instances=page_instances,
                intent_sequences=intent_sequences,
                actions=actions,
                manages=manages,
            )
            logger.info("  Stored all structures to memory")

            # Create cognitive phrase (skip for online learning subtasks)
            if skip_cognitive_phrase:
                logger.info("  Skipping cognitive phrase creation (skip_cognitive_phrase=True)")
            else:
                cognitive_phrase = await self._create_cognitive_phrase(
                    states=states,
                    actions=actions,
                    intent_sequences=intent_sequences,
                    workflow_data=events,
                    session_id=session_id,
                )
                if cognitive_phrase:
                    success = self.memory.create_phrase(cognitive_phrase)
                    if success:
                        logger.info(f"  Created cognitive phrase: {cognitive_phrase.description[:80]}...")
        else:
            logger.info("Stage 7: Skipping memory storage")
        logger.info("")

        # Calculate processing time
        end_time = datetime.now()
        processing_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # Collect metadata
        metadata = {
            "session_id": session_id,
            "event_count": len(events),
            "segment_count": len(segments),
            "new_states": new_state_count,
            "reused_states": reused_state_count,
            "stored_to_memory": store_to_memory and self.memory is not None,
            "llm_model": getattr(self.simple_llm_provider, 'model_name', 'unknown'),
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
        logger.info(f"{'='*60}")
        logger.info("Processing Complete!")
        logger.info(f"{'='*60}")
        summary = result.get_summary()
        for key, value in summary.items():
            logger.info(f"  {key}: {value}")
        logger.info(f"{'='*60}\n")

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

        Handles differences between recording formats:
        - New format (ref-based): {type, ref, text, role, ...}
        - Old format (xpath-based): {type, element: {tagName, xpath, ...}, data: {...}}

        Args:
            event: Raw event dictionary.

        Returns:
            Normalized event dictionary.
        """
        normalized = dict(event)

        # Normalize timestamp to int milliseconds
        ts = event.get("timestamp")
        if isinstance(ts, str):
            normalized["timestamp"] = self._parse_timestamp(ts)
        elif isinstance(ts, datetime):
            # yaml.safe_load auto-converts +00:00 timestamps to datetime objects
            normalized["timestamp"] = int(ts.timestamp() * 1000)
        elif isinstance(ts, (int, float)):
            normalized["timestamp"] = int(ts)
        else:
            normalized["timestamp"] = 0

        # Normalize page_title / title
        if "page_title" not in normalized and "title" in normalized:
            normalized["page_title"] = normalized["title"]
        elif "title" not in normalized and "page_title" in normalized:
            normalized["title"] = normalized["page_title"]

        # New format: ref-based (flat structure)
        # Fields: ref, text, role, value, direction, amount, request_url
        if "ref" in event:
            # Already in new format - just normalize element info
            if "role" in event and "element_tag" not in normalized:
                # Map ARIA role to approximate tag
                role = event.get("role", "")
                role_to_tag = {
                    "button": "button",
                    "link": "a",
                    "textbox": "input",
                    "combobox": "select",
                    "checkbox": "input",
                    "radio": "input",
                    "listitem": "li",
                    "heading": "h1",
                    "img": "img",
                    "generic": "div",
                }
                normalized["element_tag"] = role_to_tag.get(role, "div")
            if "text" in event and event["text"]:
                # text is already at top level
                pass
            if "value" in event:
                # value for type/input events
                normalized["input_value"] = event.get("value", "")

            # scroll event fields
            if "direction" in event:
                normalized["scroll_direction"] = event.get("direction")
            if "amount" in event:
                normalized["scroll_distance"] = event.get("amount")

            # dataload event fields
            if "request_url" in event:
                normalized["data_request_url"] = event.get("request_url")

            return normalized

        # Ref-less scroll events from behavior recorder may still carry
        # direction/amount at top level; normalize them here as fallback.
        if event.get("type", "").lower() == "scroll":
            if "direction" in event and "scroll_direction" not in normalized:
                normalized["scroll_direction"] = event.get("direction")
            if "amount" in event and "scroll_distance" not in normalized:
                normalized["scroll_distance"] = event.get("amount")
            if "distance" in event and "scroll_distance" not in normalized:
                normalized["scroll_distance"] = event.get("distance")

        # Old format: xpath-based (nested element/data objects)
        # Flatten element object
        element = event.get("element", {})
        if element and isinstance(element, dict):
            if "tagName" in element and "element_tag" not in normalized:
                normalized["element_tag"] = element.get("tagName", "").lower()
            if "className" in element and "element_class" not in normalized:
                normalized["element_class"] = element.get("className", "")
            if "textContent" in element and "text" not in normalized:
                normalized["text"] = element.get("textContent", "")[:200]
            if "xpath" in element and "xpath" not in normalized:
                normalized["xpath"] = element.get("xpath", "")
            if "href" in element and "href" not in normalized:
                normalized["href"] = element.get("href", "")

        # Flatten data object
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
        - "2026-01-30T05:57:30.619Z"           (JS UTC — Z suffix)
        - "2026-01-30T05:57:30.619000+00:00"   (Python UTC — get_current_timestamp())
        - "2026-01-30T13:57:30.619000"          (Python local — datetime.now().isoformat())
        - "2026-01-30 13:57:30"                 (Python local — space separator)

        Timezone handling:
        - Z or +00:00 suffix → UTC
        - No timezone info → local time (Python datetime.now())

        Args:
            ts: Timestamp string.

        Returns:
            Timestamp in milliseconds.
        """
        from datetime import datetime, timezone

        try:
            # 1. Handle +00:00 or Z suffix via fromisoformat (Python 3.11+)
            #    Replace Z with +00:00 for fromisoformat compatibility
            if ts.endswith('Z'):
                ts_iso = ts[:-1] + '+00:00'
            else:
                ts_iso = ts

            # Replace space separator with T for fromisoformat
            if 'T' not in ts_iso and ' ' in ts_iso:
                ts_iso = ts_iso.replace(' ', 'T', 1)

            dt = datetime.fromisoformat(ts_iso)
            return int(dt.timestamp() * 1000)

        except (ValueError, AttributeError):
            logger.warning(f"Could not parse timestamp: {ts}")
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
                # Update page_title from user events if navigate event had placeholder
                # User events (click, type, etc.) from behavior_tracker.js have real page title
                if page_title and self._is_placeholder_title(current_segment.page_title):
                    current_segment.page_title = page_title

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

    def _is_placeholder_title(self, title: Optional[str]) -> bool:
        """Check if page_title is a placeholder from CDP navigation events.

        CDP navigation events fire before page title is loaded, so they use
        placeholder values like 'Navigated Page', 'New Tab', etc.

        Args:
            title: Page title to check.

        Returns:
            True if title is a placeholder or empty.
        """
        if not title:
            return True
        placeholder_titles = {
            "navigated page",
            "new tab",
            "closed tab",
            "unknown page",
            "unknown",
            "",
        }
        return title.strip().lower() in placeholder_titles

    def _find_or_create_state(
        self,
        segment: URLSegment,
        session_id: Optional[str] = None,
        domain_key: Optional[str] = None,
        path_sig: Optional[str] = None,
    ) -> tuple[State, bool]:
        """Find existing State by URL or create a new one.

        Uses WorkflowMemory.find_or_create_state for URL index lookup
        and real-time merge.

        Args:
            segment: URLSegment to process.
            session_id: Session ID.
            domain_key: Normalized domain key (optional).
            path_sig: Stable path signature (optional).

        Returns:
            Tuple of (State, is_new).
        """
        # Extract domain from URL
        domain = domain_key or self._extract_domain_from_url(segment.url)

        if self.memory:
            return self.memory.find_or_create_state(
                url=segment.url,
                page_title=segment.page_title,
                timestamp=segment.timestamp,
                domain=domain,
                session_id=session_id,
                path_sig=path_sig,
            )

        # No memory - create State without storage
        state = State(
            page_url=segment.url,
            page_title=segment.page_title,
            timestamp=segment.timestamp,
            domain=domain,
            path_sig=path_sig,
            session_id=session_id,
            instances=[],
        )
        return state, True

    def _create_page_instance(
        self,
        segment: URLSegment,
        state_id: str,
        session_id: Optional[str] = None,
        snapshots: Optional[Dict[str, Dict]] = None,
    ) -> PageInstance:
        """Create PageInstance from segment with optional snapshot.

        Args:
            segment: URLSegment to process.
            state_id: ID of the parent State.
            session_id: Session ID.
            snapshots: URL -> snapshot data mapping.

        Returns:
            PageInstance object with _parent_state_id set for later storage.
        """
        # Match snapshot by URL
        snapshot_text = None
        if snapshots and segment.url in snapshots:
            snapshot_data = snapshots[segment.url]
            snapshot_text = snapshot_data.get("snapshot") or snapshot_data.get("snapshot_text")

        instance = PageInstance(
            url=segment.url,
            page_title=segment.page_title,
            timestamp=segment.timestamp,
            session_id=session_id,
            snapshot_text=snapshot_text,
        )
        # Tag with parent state ID for _store_to_memory
        instance._parent_state_id = state_id

        return instance

    def _create_intent_sequence(
        self,
        segment: URLSegment,
        state_id: str,
        session_id: Optional[str] = None,
        causes_navigation: bool = False,
        navigation_target_state_id: Optional[str] = None,
    ) -> Optional[IntentSequence]:
        """Create IntentSequence from segment events.

        Design decision: Don't create empty IntentSequences.
        Note: This method only creates the object, does NOT store to memory.
        Storage happens in Stage 7 after embedding generation, enabling proper deduplication.

        Args:
            segment: URLSegment to process.
            state_id: ID of the parent State.
            session_id: Session ID.
            causes_navigation: Whether this sequence causes page navigation (v2).
            navigation_target_state_id: Target State ID if causes_navigation (v2).

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
            session_id=session_id,
            # v2 navigation markers
            causes_navigation=causes_navigation,
            navigation_target_state_id=navigation_target_state_id,
        )

        # Store state_id in sequence for later storage (Stage 7)
        # This is a temporary attribute used by _store_intent_sequences
        sequence._parent_state_id = state_id

        return sequence

    def _event_to_intent(self, event: Dict[str, Any]) -> Optional[Intent]:
        """Convert an event dictionary to an Intent object.

        Supports both new format (ref-based) and old format (xpath-based).

        Args:
            event: Event dictionary (normalized).

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
            "enter": "Enter",
            "select_text": "SelectText",
            "dataload": "DataLoad",
        }

        intent_type = type_mapping.get(event_type)
        if not intent_type:
            # Use original type if not in mapping
            intent_type = event.get("type", "Unknown")

        try:
            attributes: Dict[str, Any] = {}
            if event_type == "scroll":
                if event.get("scroll_direction") is not None:
                    attributes["scroll_direction"] = event.get("scroll_direction")
                if event.get("scroll_distance") is not None:
                    attributes["scroll_distance"] = event.get("scroll_distance")
                if event.get("height_change") is not None:
                    attributes["height_change"] = event.get("height_change")

            intent = Intent(
                type=intent_type,
                timestamp=event.get("timestamp", 0),
                # Element identification (ref-based)
                element_ref=event.get("ref", ""),
                element_role=event.get("role", ""),
                # Content
                text=event.get("text", ""),
                value=event.get("value", ""),
                # Page information
                page_url=event.get("url", ""),
                page_title=event.get("title", ""),
                attributes=attributes,
            )
            return intent
        except Exception as e:
            logger.info(f"Warning: Failed to create Intent from event: {e}")
            return None

    def _find_transition_trigger(self, segment: URLSegment) -> Optional[Dict[str, Any]]:
        """Find the operation that triggered page transition.
        
        Strategy: Assume the last click/submit operation in the segment
        caused the navigation to the next state.
        
        Args:
            segment: URL segment to search in.
            
        Returns:
            Trigger event dict if found, None otherwise.
        """
        # Search backwards for trigger operations
        # The last click/submit is the most likely navigation trigger,
        # regardless of element role (link, button, option, generic, etc.)
        for event in reversed(segment.events):
            event_type = str(event.get("type") or "").strip().lower()

            if event_type in ("click", "clickelement"):
                return event

            elif event_type in ("submit", "formsubmit"):
                return event
        
        return None

    def _normalize_action_text(self, text: str) -> str:
        """Normalize action text for stable signatures."""
        if not text:
            return ""
        normalized = text.strip().lower()
        # Remove URLs and emails
        normalized = re.sub(r"https?://\S+", " ", normalized)
        normalized = re.sub(r"\bwww\.\S+", " ", normalized)
        normalized = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", " ", normalized)
        # Remove UUIDs / long hex tokens
        normalized = re.sub(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            " ",
            normalized,
        )
        normalized = re.sub(r"\b[0-9a-f]{8,}\b", " ", normalized)
        # Normalize numbers
        normalized = re.sub(r"\d+", "<n>", normalized)
        # Collapse whitespace
        normalized = " ".join(normalized.split())
        return normalized[:80] if len(normalized) > 80 else normalized

    def _normalize_xpath(self, xpath: str) -> str:
        """Normalize xpath for stable signatures."""
        if not xpath:
            return ""
        normalized = xpath.strip().lower()
        normalized = re.sub(r"\[\d+\]", "[]", normalized)
        normalized = re.sub(r"\s+", "", normalized)
        return normalized[:200] if len(normalized) > 200 else normalized

    def _normalize_href(self, href: str) -> str:
        """Normalize href for stable signatures."""
        if not href:
            return ""
        normalized = href.strip()
        normalized = normalized.split("#")[0].split("?")[0]
        if normalized.startswith("//"):
            normalized = f"https:{normalized}"
        if "://" in normalized:
            try:
                parsed = urlparse(normalized)
                path = parsed.path or ""
            except Exception:
                path = re.sub(r"^[a-z]+://", "", normalized)
                path = "/" + path.split("/", 1)[1] if "/" in path else ""
        else:
            path = normalized
        if not path:
            return ""
        path = path.lower()
        path = re.sub(r"/\d+(?=/|$)", "/<n>", path)
        path = re.sub(r"/[0-9a-f]{8,}(?=/|$)", "/<id>", path)
        path = re.sub(r"/+", "/", path)
        return path[:200] if len(path) > 200 else path

    def _normalize_url_path(self, url: str) -> str:
        """Normalize URL/path for stable entry signatures."""
        return self._normalize_href(url)

    def _build_entry_signature(self, url: str) -> str:
        """Build a stable entry signature from a URL."""
        path = self._normalize_url_path(url) or "/"
        return f"entry|path:{path}"

    def _build_action_signature(self, trigger_event: Optional[Dict[str, Any]]) -> str:
        """Build a stable action signature from a trigger event."""
        if not trigger_event:
            return "auto_navigate"

        event_type = (trigger_event.get("type") or "click").lower()
        role = (trigger_event.get("role") or "").lower()
        xpath = self._normalize_xpath(trigger_event.get("xpath") or "")
        href = self._normalize_href(trigger_event.get("href") or "")
        text = self._normalize_action_text(trigger_event.get("text") or "")
        ref = (trigger_event.get("ref") or "").strip().lower()

        hint = ""
        if xpath:
            hint = f"xpath:{xpath}"
        elif href:
            hint = f"href:{href}"
        elif text:
            hint = f"text:{text}"
        elif ref:
            hint = f"ref:{ref}"

        base = f"{event_type}|{role}" if role else event_type
        if hint:
            return f"{base}|{hint}"
        return base

    def _hash_domain_root_sig(self, domain_key: str) -> str:
        """Hash domain-level root signature."""
        content = f"{domain_key}|ROOT"
        return hashlib.sha1(content.encode("utf-8")).hexdigest()

    def _extend_path_sig(self, prev_sig: str, action_sig: str) -> str:
        """Extend a path signature with a new action signature."""
        content = f"{prev_sig}>{action_sig}"
        return hashlib.sha1(content.encode("utf-8")).hexdigest()
    
    def _create_actions(
        self,
        segments: List[URLSegment],
        states: List[State],
        intent_sequences: Optional[List[IntentSequence]] = None,
        session_id: Optional[str] = None,
    ) -> List[Action]:
        """Create Actions between consecutive States.

        Args:
            segments: List of URL segments.
            states: List of States (same order as segments).
            intent_sequences: List of IntentSequences for trigger lookup (v2).
            session_id: Session ID.

        Returns:
            List of Action objects.
        """
        actions = []

        # Build a map: state_id -> list of IntentSequences for that state
        # We identify the IntentSequence that causes navigation by causes_navigation flag
        state_to_nav_sequences: Dict[str, IntentSequence] = {}
        if intent_sequences:
            for seq in intent_sequences:
                if seq.causes_navigation and seq.navigation_target_state_id:
                    # Use navigation_target_state_id as key for lookup
                    state_to_nav_sequences[seq.navigation_target_state_id] = seq

        for i in range(len(states) - 1):
            source_state = states[i]
            target_state = states[i + 1]
            source_segment = segments[i]
            target_segment = segments[i + 1]

            # Skip if same state (URL)
            if source_state.id == target_state.id:
                continue

            # Find the navigation sequence that triggered this transition (v2)
            trigger_sequence_id = None
            if target_state.id in state_to_nav_sequences:
                trigger_sequence_id = state_to_nav_sequences[target_state.id].id

            # Find the operation that triggered this transition
            trigger_event = self._find_transition_trigger(source_segment)
            
            if trigger_event:
                # Has explicit trigger operation
                action = Action(
                    source=source_state.id,
                    target=target_state.id,
                    type=trigger_event["type"],  # "click" | "submit"
                    timestamp=trigger_event.get("timestamp"),
                    trigger={
                        "ref": trigger_event.get("ref"),
                        "text": trigger_event.get("text"),
                        "role": trigger_event.get("role"),
                    },
                    trigger_sequence_id=trigger_sequence_id,
                    session_id=session_id,
                )
            else:
                # No explicit trigger - automatic navigation/redirect
                action = Action(
                    source=source_state.id,
                    target=target_state.id,
                    type="auto_navigate",
                    timestamp=target_segment.timestamp,
                    trigger=None,
                    trigger_sequence_id=trigger_sequence_id,
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
            host = parsed.netloc or url
        except Exception:
            host = url
        return normalize_domain_url(host, "website")

    def _extract_domains_and_manages(
        self,
        states: List[State],
        domain_root_id_map: Optional[Dict[str, str]] = None,
    ) -> tuple[List[Domain], List[Manage]]:
        """Extract Domains and create Manage edges.

        Args:
            states: List of State objects.
            domain_root_id_map: Optional domain -> root_state_id mapping.

        Returns:
            Tuple of (domains, manages).
        """
        # Collect unique domains from states
        domain_map: Dict[str, Domain] = {}
        manages = []
        domain_root_id_map = domain_root_id_map or {}

        for state in states:
            domain_name = state.domain
            if not domain_name:
                domain_name = self._extract_domain_from_url(state.page_url)

            domain_key = normalize_domain_url(domain_name, "website")
            if not domain_key:
                continue

            if domain_key not in domain_map:
                existing_domain = self.memory.get_domain(domain_key) if self.memory else None
                if existing_domain:
                    domain = existing_domain
                    if not domain.domain_name and domain_name:
                        domain.domain_name = domain_name
                else:
                    domain = Domain(
                        domain_name=domain_name,
                        domain_url=domain_key,
                        domain_type="website",
                    )

                root_id = domain_root_id_map.get(domain_key)
                if root_id:
                    if domain.attributes is None:
                        domain.attributes = {}
                    if "root_state_id" not in domain.attributes:
                        domain.attributes["root_state_id"] = root_id
                domain_map[domain_key] = domain

            # Create Manage edge
            domain = domain_map[domain_key]
            manage = Manage(
                domain_id=domain.id,
                state_id=state.id,
                first_visit=state.timestamp,
                last_visit=state.timestamp,
                visit_count=1,
            )
            manages.append(manage)

        return list(domain_map.values()), manages

    async def _generate_descriptions(
        self,
        states: List[State],
        intent_sequences: List[IntentSequence],
        actions: List[Action],
        all_states: Optional[List[State]] = None,
    ) -> None:
        """Generate descriptions using LLM (async).

        Args:
            states: States that need descriptions.
            all_states: Full states in this workflow for action context lookup.
            intent_sequences: IntentSequences that need descriptions.
            actions: Actions that need descriptions.
        """
        ordered_states = all_states or states
        state_index_map = {s.id: idx for idx, s in enumerate(ordered_states)}
        state_sequences_map: Dict[str, List[IntentSequence]] = {}
        for sequence in intent_sequences:
            state_id = getattr(sequence, "_parent_state_id", None)
            if not state_id:
                continue
            state_sequences_map.setdefault(state_id, []).append(sequence)

        incoming_action_map: Dict[str, Action] = {}
        outgoing_action_map: Dict[str, Action] = {}
        for action in actions:
            if action.target not in incoming_action_map:
                incoming_action_map[action.target] = action
            if action.source not in outgoing_action_map:
                outgoing_action_map[action.source] = action

        # Generate State descriptions
        for state in states:
            if not state.description:
                state_context = self._build_state_generation_context(
                    state=state,
                    ordered_states=ordered_states,
                    state_index_map=state_index_map,
                    state_sequences_map=state_sequences_map,
                    incoming_action_map=incoming_action_map,
                    outgoing_action_map=outgoing_action_map,
                )
                state.description = await self._generate_state_description(
                    state,
                    context=state_context,
                )
                logger.info(f"    Generated State description: {state.description[:50]}...")

        # Generate IntentSequence descriptions
        for sequence in intent_sequences:
            if not sequence.description:
                sequence.description = await self._generate_intent_sequence_description(sequence)
                logger.info(f"    Generated IntentSequence description: {sequence.description[:50]}...")

        # Generate Action descriptions (need state info for context)
        state_map = {s.id: s for s in (all_states or states)}
        memory_state_cache: Dict[str, Optional[State]] = {}
        for action in actions:
            if not action.description:
                source_state = state_map.get(action.source)
                target_state = state_map.get(action.target)
                # Reused states may not be in `states` (new_states only); fallback to memory.
                if self.memory:
                    if not source_state:
                        source_state = memory_state_cache.get(action.source)
                        if source_state is None:
                            source_state = self.memory.get_state(action.source)
                            memory_state_cache[action.source] = source_state
                    if not target_state:
                        target_state = memory_state_cache.get(action.target)
                        if target_state is None:
                            target_state = self.memory.get_state(action.target)
                            memory_state_cache[action.target] = target_state
                action.description = await self._generate_action_description(
                    action, source_state, target_state
                )
                if action.description:
                    logger.info(f"    Generated Action description: {action.description[:50]}...")

    @staticmethod
    def _normalize_keywords(raw_keywords: Any, max_keywords: int = 8) -> List[str]:
        """Normalize semantic keywords to a short, unique list."""
        if not raw_keywords:
            return []

        if isinstance(raw_keywords, str):
            candidates = re.split(r"[,\uFF0C;\uFF1B|/\n\t ]+", raw_keywords)
        elif isinstance(raw_keywords, list):
            candidates = raw_keywords
        else:
            return []

        keywords: List[str] = []
        seen = set()
        for item in candidates:
            word = str(item or "").strip()
            if not word:
                continue
            # Remove obvious dynamic tokens to reduce retrieval noise.
            word = re.sub(r"\b\d{4,}\b", "", word).strip()
            if not word:
                continue
            lowered = word.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            keywords.append(word[:30])
            if len(keywords) >= max_keywords:
                break
        return keywords

    @classmethod
    def _is_protected_state_modifier(cls, keyword: str) -> bool:
        """Check whether keyword is a high-value qualifier (e.g. 每日/每周/最新)."""
        text = str(keyword or "").strip().lower()
        if len(text) < 2:
            return False
        return any(hint in text for hint in cls._STATE_PROTECTED_MODIFIER_HINTS)

    @classmethod
    def _extract_state_modifier_from_description(cls, description: str) -> str:
        """Extract one important qualifier from description text."""
        text = str(description or "").strip()
        if not text:
            return ""

        lowered = text.lower()
        for hint in cls._STATE_PROTECTED_MODIFIER_HINTS:
            token = str(hint or "").strip()
            if not token:
                continue
            token_lower = token.lower()
            if token_lower.isascii() and token_lower.isalpha():
                if re.search(rf"\b{re.escape(token_lower)}\b", lowered):
                    return token
            elif token_lower in lowered:
                return token
        return ""

    def _refine_state_keywords(
        self,
        state: State,
        context: Dict[str, Any],
        label: str,
        raw_keywords: Any,
        max_keywords: int = 4,
    ) -> List[str]:
        """Keep keywords tightly grounded in page evidence (title/url/path/query)."""
        normalized = self._normalize_keywords(raw_keywords, max_keywords=12)
        if not normalized:
            return []

        url_context = context.get("url_context") if isinstance(context, dict) else {}
        if not isinstance(url_context, dict):
            url_context = {}

        label_lower = str(label or "").strip().lower()
        title_lower = str(state.page_title or "").strip().lower()
        path_lower = str(url_context.get("path") or "").strip().lower()
        url_lower = str(state.page_url or "").strip().lower()
        segment_lowers = [
            str(seg or "").strip().lower()
            for seg in (url_context.get("segments") or [])
            if str(seg or "").strip()
        ]
        query_key_lowers = [
            str(key or "").strip().lower()
            for key in (url_context.get("query_keys") or [])
            if str(key or "").strip()
        ]

        scored_terms: List[tuple[int, int, str]] = []
        seen = set()

        for index, keyword in enumerate(normalized):
            kw = str(keyword or "").strip()[:30]
            if not kw:
                continue
            lowered = kw.lower()
            if lowered in seen:
                continue

            # Drop numeric/date fragments such as "2", "5", "2月", "5日".
            if re.fullmatch(r"\d+(?:\.\d+)?", kw):
                continue
            if re.fullmatch(r"\d+[\u5e74\u6708\u65e5\u53f7]?", kw):
                continue
            if len(kw) <= 1 and not kw.isalpha():
                continue

            seen.add(lowered)
            score = 0
            if lowered and lowered in label_lower:
                score += 4
            if lowered and lowered in title_lower:
                score += 4
            if lowered and lowered in path_lower:
                score += 2
            if lowered and lowered in url_lower:
                score += 1
            if lowered and any(lowered in seg for seg in segment_lowers):
                score += 3
            if lowered and any(lowered in key for key in query_key_lowers):
                score += 2

            if score > 0:
                scored_terms.append((score, index, kw))

        if not scored_terms:
            fallback_terms: List[str] = []
            for keyword in normalized:
                kw = str(keyword or "").strip()[:30]
                if not kw:
                    continue
                lowered = kw.lower()
                if re.fullmatch(r"\d+(?:\.\d+)?", kw):
                    continue
                if re.fullmatch(r"\d+[\u5e74\u6708\u65e5\u53f7]?", kw):
                    continue
                if len(kw) <= 1 and not kw.isalpha():
                    continue
                if lowered in label_lower or lowered in title_lower:
                    fallback_terms.append(kw)

            if not fallback_terms:
                for keyword in normalized:
                    kw = str(keyword or "").strip()[:30]
                    if not kw:
                        continue
                    if re.fullmatch(r"\d+(?:\.\d+)?", kw):
                        continue
                    if re.fullmatch(r"\d+[\u5e74\u6708\u65e5\u53f7]?", kw):
                        continue
                    if len(kw) <= 1 and not kw.isalpha():
                        continue
                    fallback_terms.append(kw)

            dedup_fallback: List[str] = []
            seen_fallback = set()
            for item in fallback_terms:
                lowered = item.lower()
                if lowered in seen_fallback:
                    continue
                seen_fallback.add(lowered)
                dedup_fallback.append(item)
                if len(dedup_fallback) >= max_keywords:
                    break
            return dedup_fallback

        scored_terms.sort(key=lambda item: (-item[0], item[1]))
        selected: List[str] = []
        selected_seen = set()
        for _, _, kw in scored_terms:
            lowered = kw.lower()
            if lowered in selected_seen:
                continue
            selected_seen.add(lowered)
            selected.append(kw)
            if len(selected) >= max_keywords:
                break
        return selected

    @staticmethod
    def _build_state_retrieval_text(
        label: str,
        keywords: List[str],
        description: str,
    ) -> str:
        """Build State retrieval text using page label + page-grounded keywords."""
        parts = [str(label or "").strip()] + [str(item or "").strip() for item in keywords]
        retrieval_text = " ".join(part for part in parts if part).strip()
        if len(retrieval_text) < 6 and description:
            retrieval_text = " ".join(
                part for part in [retrieval_text, str(description or "").strip()] if part
            ).strip()
        return retrieval_text[:320]

    def _finalize_state_semantic(
        self,
        state: State,
        context: Dict[str, Any],
        semantic: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply State-specific semantic normalization for stable retrieval."""
        semantic = dict(semantic or {})
        label = str(semantic.get("label") or state.page_title or "页面").strip()[:80]
        intent = str(semantic.get("intent") or "识别页面类型与用途").strip()[:120]
        description = str(
            semantic.get("description") or f"页面: {state.page_title or state.page_url}"
        ).strip()[:240]
        keywords = self._normalize_keywords(semantic.get("keywords"), max_keywords=4)

        # Keep one domain keyword aligned with Domain.domain_url normalization.
        domain_source = str(state.domain or "").strip() or self._extract_domain_from_url(state.page_url)
        domain_keyword = normalize_domain_url(domain_source, "website") if domain_source else ""
        if domain_keyword:
            keyword_set = {str(item or "").lower() for item in keywords}
            if domain_keyword.lower() not in keyword_set:
                if len(keywords) >= 4:
                    keywords = keywords[:3] + [domain_keyword]
                else:
                    keywords.append(domain_keyword)

        semantic["version"] = "semantic_v1"
        semantic["label"] = label
        semantic["intent"] = intent
        semantic["description"] = description
        semantic["keywords"] = keywords
        semantic["retrieval_text"] = self._build_state_retrieval_text(
            label=label,
            keywords=keywords,
            description=description,
        )
        return semantic

    def _parse_semantic_output(
        self,
        raw_response: str,
        default_label: str,
        default_intent: str,
        default_description: str,
    ) -> Dict[str, Any]:
        """Parse LLM output into normalized semantic fields with safe fallbacks."""
        parsed = parse_json_with_repair(raw_response or "")
        if not isinstance(parsed, dict):
            parsed = {}

        # Backward compatibility for previous workflow schema.
        if "label" not in parsed and "name" in parsed:
            parsed["label"] = parsed.get("name")

        label = str(parsed.get("label") or default_label).strip()[:80]
        intent = str(parsed.get("intent") or default_intent).strip()[:120]
        description = str(parsed.get("description") or default_description).strip()[:240]
        keywords = self._normalize_keywords(parsed.get("keywords"))
        retrieval_text = str(parsed.get("retrieval_text") or "").strip()
        if not retrieval_text:
            retrieval_parts = [label, intent] + keywords
            retrieval_text = " ".join(part for part in retrieval_parts if part).strip()

        return {
            "version": "semantic_v1",
            "label": label,
            "intent": intent,
            "keywords": keywords,
            "description": description,
            "retrieval_text": retrieval_text[:320],
        }

    @staticmethod
    def _truncate_text(value: Any, max_len: int = 80) -> str:
        """Truncate text for prompt context display."""
        text = str(value or "").strip()
        if len(text) <= max_len:
            return text
        return f"{text[: max_len - 3]}..."

    @staticmethod
    def _normalize_generated_description(
        raw_text: Any,
        default_text: str,
        max_len: int = 240,
    ) -> str:
        """Normalize plain-text description generated by LLM."""
        text = str(raw_text or "").strip()
        if not text:
            return str(default_text or "").strip()[:max_len]

        # Remove markdown/code wrappers and common field prefixes.
        text = re.sub(r"^```(?:json|text|markdown)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()
        text = re.sub(r"^(description|描述)\s*[:：]\s*", "", text, flags=re.IGNORECASE).strip()

        lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
        if lines:
            text = lines[0]

        text = text.strip("\"'` ").strip()
        if not text:
            text = str(default_text or "").strip()
        return text[:max_len]

    @classmethod
    def _parse_url_context(cls, url: str) -> Dict[str, Any]:
        """Parse URL into stable path/query context."""
        try:
            parsed = urlparse(url or "")
        except Exception:
            parsed = urlparse("")

        path = (parsed.path or "/").strip() or "/"
        raw_segments = [seg for seg in path.split("/") if seg]
        segments = [cls._truncate_text(seg, 30) for seg in raw_segments[:6]]

        query_keys: List[str] = []
        try:
            for key, _ in parse_qsl(parsed.query or "", keep_blank_values=False):
                key_text = cls._truncate_text(key, 40)
                if not key_text or key_text in query_keys:
                    continue
                query_keys.append(key_text)
                if len(query_keys) >= 8:
                    break
        except Exception:
            query_keys = []

        return {
            "path": cls._truncate_text(path, 200),
            "segments": segments,
            "query_keys": query_keys,
        }

    @classmethod
    def _summarize_intent_for_state_prompt(cls, intent: Any) -> str:
        """Summarize one intent as a compact clue for state semantics."""
        if isinstance(intent, dict):
            intent_type = intent.get("type", "")
            text = intent.get("text", "")
            value = intent.get("value", "")
            role = intent.get("element_role") or intent.get("role") or ""
        else:
            intent_type = getattr(intent, "type", "")
            text = getattr(intent, "text", "")
            value = getattr(intent, "value", "")
            role = getattr(intent, "element_role", "") or ""

        intent_type_text = cls._truncate_text(intent_type, 24) or "action"
        main_text = cls._truncate_text(text or value, 64)
        role_text = cls._truncate_text(role, 24)

        parts = [intent_type_text]
        if main_text:
            parts.append(f"text={main_text}")
        if role_text:
            parts.append(f"role={role_text}")
        return ", ".join(parts)

    @classmethod
    def _summarize_state_for_prompt(cls, state: Optional[State]) -> str:
        """Summarize neighboring state for prompt context."""
        if not state:
            return "无"
        url_ctx = cls._parse_url_context(state.page_url)
        title = cls._truncate_text(state.page_title or "", 60) or "无标题"
        return f"{title} (path={url_ctx.get('path', '/')})"

    @classmethod
    def _summarize_navigation_for_prompt(
        cls,
        action: Optional[Action],
        state_lookup: Dict[str, State],
        direction: str,
    ) -> str:
        """Summarize incoming/outgoing navigation clues for prompt context."""
        if not action:
            return "无"

        trigger = action.trigger if isinstance(action.trigger, dict) else {}
        action_type = cls._truncate_text(action.type, 24) or "navigate"
        trigger_text = cls._truncate_text(trigger.get("text"), 64)
        trigger_role = cls._truncate_text(trigger.get("role"), 24)

        if direction == "incoming":
            related_state = state_lookup.get(action.source)
            state_hint = cls._summarize_state_for_prompt(related_state)
            direction_hint = f"from={state_hint}"
        else:
            related_state = state_lookup.get(action.target)
            state_hint = cls._summarize_state_for_prompt(related_state)
            direction_hint = f"to={state_hint}"

        parts = [f"type={action_type}", direction_hint]
        if trigger_text:
            parts.append(f"text={trigger_text}")
        if trigger_role:
            parts.append(f"role={trigger_role}")
        return ", ".join(parts)

    def _build_state_generation_context(
        self,
        state: State,
        ordered_states: List[State],
        state_index_map: Dict[str, int],
        state_sequences_map: Dict[str, List[IntentSequence]],
        incoming_action_map: Dict[str, Action],
        outgoing_action_map: Dict[str, Action],
    ) -> Dict[str, Any]:
        """Build rich but compact context used for State semantic generation."""
        idx = state_index_map.get(state.id)
        prev_state = ordered_states[idx - 1] if idx is not None and idx > 0 else None
        next_state = (
            ordered_states[idx + 1]
            if idx is not None and idx < len(ordered_states) - 1
            else None
        )

        state_lookup = {s.id: s for s in ordered_states}
        incoming_action = incoming_action_map.get(state.id)
        outgoing_action = outgoing_action_map.get(state.id)

        intent_clues: List[str] = []
        for sequence in state_sequences_map.get(state.id, [])[:3]:
            intents = sequence.intents if isinstance(sequence.intents, list) else []
            for intent in intents[:4]:
                clue = self._summarize_intent_for_state_prompt(intent)
                if clue:
                    intent_clues.append(f"- {clue}")
                if len(intent_clues) >= 10:
                    break
            if len(intent_clues) >= 10:
                break

        url_ctx = self._parse_url_context(state.page_url)
        incoming_nav = self._summarize_navigation_for_prompt(
            incoming_action, state_lookup, direction="incoming"
        )
        outgoing_nav = self._summarize_navigation_for_prompt(
            outgoing_action, state_lookup, direction="outgoing"
        )
        prev_hint = self._summarize_state_for_prompt(prev_state)
        next_hint = self._summarize_state_for_prompt(next_state)

        logger.debug(
            "[StateSemanticContext] state=%s path=%s intent_clues=%d incoming=%s outgoing=%s prev=%s next=%s",
            state.id[:8],
            url_ctx.get("path", "/"),
            len(intent_clues),
            incoming_nav,
            outgoing_nav,
            prev_hint,
            next_hint,
        )

        return {
            "url_context": url_ctx,
            "intent_clues": intent_clues,
            "incoming_navigation": incoming_nav,
            "outgoing_navigation": outgoing_nav,
            "prev_state_hint": prev_hint,
            "next_state_hint": next_hint,
        }

    async def _generate_state_description(
        self,
        state: State,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate description for a State using LLM.

        Args:
            state: State to describe.
            context: Optional context clues for better page-type judgment.

        Returns:
            Description string.
        """
        if state.attributes is None:
            state.attributes = {}

        context = context or {}
        url_context = context.get("url_context", {})
        path_hint = str(url_context.get("path") or "无")
        path_segments = url_context.get("segments") or []
        query_keys = url_context.get("query_keys") or []
        path_segments_text = " / ".join(path_segments) if path_segments else "无"
        query_keys_text = ", ".join(query_keys) if query_keys else "无"
        intent_clues = context.get("intent_clues") or []
        intent_clues_text = "\n".join(intent_clues) if intent_clues else "- 无明显页面内操作"
        incoming_nav = str(context.get("incoming_navigation") or "无")
        outgoing_nav = str(context.get("outgoing_navigation") or "无")
        prev_state_hint = str(context.get("prev_state_hint") or "无")
        next_state_hint = str(context.get("next_state_hint") or "无")

        default_label = state.page_title or "页面"
        default_intent = "识别页面类型与用途"
        default_description = f"页面: {state.page_title or state.page_url}"

        # If no LLM provider, return default description
        if not self.simple_llm_provider:
            semantic = self._parse_semantic_output(
                raw_response="",
                default_label=default_label,
                default_intent=default_intent,
                default_description=default_description,
            )
            semantic = self._finalize_state_semantic(
                state=state,
                context=context,
                semantic=semantic,
            )
            state.attributes["semantic_v1"] = semantic
            return semantic["description"]

        prompt = f"""请基于页面上下文整理一份结构化语义 JSON，用于后续检索参考。
你可以综合判断这个页面在任务中的角色和类型（例如列表页、详情页、搜索页、表单页、结果页等），并给出较稳定的页面语义。

URL: {state.page_url}
页面标题: {state.page_title or "无"}
URL 路径线索:
- path: {path_hint}
- path_segments: {path_segments_text}
- query_keys: {query_keys_text}

页面内操作线索:
{intent_clues_text}

导航线索:
- 进入当前页: {incoming_nav}
- 离开当前页: {outgoing_nav}

相邻页面:
- 上一页: {prev_state_hint}
- 下一页: {next_state_hint}

建议结构:
- label: 页面类型短标签（例如"商品详情页"）
- intent: 用户在该页的核心意图（短语）
- keywords: 3-4个关键词，仅保留与页面本身强相关的关键词
- description: 1句话自然语言描述（中文）
- retrieval_text: 用于检索的稳定文本，建议使用 label + keywords（不必包含 intent）

补充建议:
- keywords 优先来自页面本身线索（标题、URL、页面对象），可以尽量减少泛化能力词。
- 不要把日期拆成数字关键词（例如“2”“5”）。
- 内容保持概括和稳定，尽量减少动态 ID、时间戳等噪声。

示例:
{{"label":"产品排行榜页","intent":"查看每日热门产品","keywords":["排行榜","热门产品","产品榜单"],"description":"每日产品排行榜页面，展示热门产品列表。","retrieval_text":"产品排行榜页 排行榜 热门产品 产品榜单"}}

JSON:"""

        try:
            response = await self.simple_llm_provider.generate_response(
                system_prompt="你是一个擅长结构化信息整理的助手，优先输出一个 JSON 对象。",
                user_prompt=prompt
            )
            semantic = self._parse_semantic_output(
                raw_response=response,
                default_label=default_label,
                default_intent=default_intent,
                default_description=default_description,
            )
            semantic = self._finalize_state_semantic(
                state=state,
                context=context,
                semantic=semantic,
            )
            state.attributes["semantic_v1"] = semantic
            return semantic["description"]
        except Exception as e:
            logger.info(f"Warning: Failed to generate state description: {e}")
            semantic = self._parse_semantic_output(
                raw_response="",
                default_label=default_label,
                default_intent=default_intent,
                default_description=default_description,
            )
            semantic = self._finalize_state_semantic(
                state=state,
                context=context,
                semantic=semantic,
            )
            state.attributes["semantic_v1"] = semantic
            return semantic["description"]

    async def _generate_intent_sequence_description(self, sequence: IntentSequence) -> str:
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

        # Keep non-State entities description-first (no semantic_v1 retrieval fields).
        sequence.semantic = {}

        default_description = f"操作序列（{len(sequence.intents)} 个操作）"
        if not self.simple_llm_provider:
            return default_description

        intents_str = "\n".join(f"- {s}" for s in intent_summary[:10])

        prompt = f"""请根据以下操作序列，生成一句简洁稳定的中文描述（用于检索）。

操作序列:
{intents_str}

补充建议:
- 聚焦用户在页面内完成的动作与目标
- 尽量避免动态值（ref 编号、随机 ID、时间戳）
- 只返回描述文本，不需要 JSON 或解释

示例:
用户先搜索再筛选，以快速定位目标商品。"""

        try:
            response = await self.simple_llm_provider.generate_response(
                system_prompt="你是一个擅长概括用户操作的助手。",
                user_prompt=prompt
            )
            return self._normalize_generated_description(
                raw_text=response,
                default_text=default_description,
            )
        except Exception as e:
            logger.info(f"Warning: Failed to generate sequence description: {e}")
            return default_description

    async def _generate_action_description(
        self,
        action: Action,
        source_state: Optional[State] = None,
        target_state: Optional[State] = None,
    ) -> str:
        """Generate description for an Action using LLM.
        
        Uses action.trigger information (from recording) to generate
        accurate natural-language descriptions for better retrieval.

        Args:
            action: Action to describe.
            source_state: Source State of the action.
            target_state: Target State of the action.

        Returns:
            Description string.
        """
        if action.attributes is None:
            action.attributes = {}
        # Keep non-State entities description-first (no semantic_v1 retrieval fields).
        action.attributes.pop("semantic_v1", None)

        if not source_state or not target_state:
            return "页面跳转"

        source_desc = source_state.description or source_state.page_title or "来源页面"
        target_desc = target_state.description or target_state.page_title or "目标页面"
        trigger = action.trigger or {}
        trigger_text = str((trigger.get("text") or "")[:50]).strip()
        trigger_role = str(trigger.get("role") or "").strip()

        # If no LLM provider, use simple template
        if not self.simple_llm_provider:
            fallback_desc = (
                f"点击 '{trigger_text}' 进入 {target_desc}"
                if trigger_text
                else f"自动跳转到 {target_desc}"
            )
            return fallback_desc

        # Use LLM with trigger/context information to generate natural description.
        ref = trigger.get("ref") or ""
        fallback_desc = (
            f"点击 '{trigger_text}' 进入 {target_desc}"
            if trigger_text
            else f"自动跳转到 {target_desc}"
        )
        prompt = f"""请根据以下页面跳转信息，生成一句简洁稳定的中文描述（用于检索）。

来源页面: {source_desc}
来源URL: {source_state.page_url}
目标页面: {target_desc}
目标URL: {target_state.page_url}
用户操作类型: {action.type}
触发元素:
- ref: {ref}
- text: {trigger_text or "无"}
- role: {trigger_role or "无"}

补充建议:
- 描述里可包含“从哪里到哪里、通过什么触发”
- 尽量避免动态值（ref 编号、随机 ID、时间戳）
- 只返回描述文本，不需要 JSON 或解释

示例:
用户通过页面元素触发导航，从来源页面进入目标页面。"""

        try:
            response = await self.simple_llm_provider.generate_response(
                system_prompt="你是一个擅长概括页面跳转行为的助手。",
                user_prompt=prompt
            )
            return self._normalize_generated_description(
                raw_text=response,
                default_text=fallback_desc,
            )
        except Exception as e:
            logger.info(f"Warning: Failed to generate action description: {e}")
            return fallback_desc

    def _merge_state_attributes(self, memory_state: State, local_state: State) -> None:
        """Merge local state attributes into memory state without dropping existing keys."""
        if not local_state.attributes:
            return
        merged = dict(memory_state.attributes or {})
        merged.update(local_state.attributes)
        memory_state.attributes = merged

    @staticmethod
    def _get_state_embedding_text(state: State) -> str:
        """Get stable embedding text for a State (semantic retrieval_text first)."""
        attrs = state.attributes if isinstance(state.attributes, dict) else {}
        semantic = attrs.get("semantic_v1")
        if isinstance(semantic, dict):
            retrieval_text = str(semantic.get("retrieval_text") or "").strip()
            if retrieval_text:
                return retrieval_text[:320]
            semantic_desc = str(semantic.get("description") or "").strip()
            if semantic_desc:
                return semantic_desc[:240]

        desc = str(state.description or "").strip()
        return desc[:240]

    @staticmethod
    def _get_sequence_embedding_text(sequence: IntentSequence) -> str:
        """Get embedding text for IntentSequence (description-first)."""
        desc = str(sequence.description or "").strip()
        return desc[:240]

    @staticmethod
    def _get_phrase_embedding_text(phrase: CognitivePhrase) -> str:
        """Get embedding text for CognitivePhrase (description-first)."""
        desc = str(phrase.description or "").strip()
        if desc:
            return desc[:280]
        label = str(phrase.label or "").strip()
        return label[:120]

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
        if not self.embedding_service:
            return

        # Collect all descriptions (only for items without embedding)
        texts = []
        items = []

        for state in states:
            # Prefer structured retrieval_text for embedding stability.
            text = self._get_state_embedding_text(state)
            if text and not state.embedding_vector:
                texts.append(text)
                items.append(("state", state))

        for sequence in intent_sequences:
            # Use sequence natural description for embedding.
            text = self._get_sequence_embedding_text(sequence)
            if text and not sequence.embedding_vector:
                texts.append(text)
                items.append(("sequence", sequence))

        if not texts:
            logger.info("    No descriptions to embed")
            return

        try:
            logger.info(f"    Generating embeddings for {len(texts)} items...")
            embeddings = self.embedding_service.embed_batch(texts)

            if embeddings is None:
                logger.warning("EmbeddingService returned None for embed_batch")
                return

            for (item_type, item), embedding in zip(items, embeddings):
                item.embedding_vector = embedding

            logger.info(f"    Generated {len(embeddings)} embeddings")
        except Exception as e:
            logger.info(f"Warning: Failed to generate embeddings: {e}")

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
            page_instances: PageInstances to store as independent nodes.
            intent_sequences: IntentSequences to store (with embeddings for dedup).
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
                logger.info(f"Warning: Failed to store domain {domain.id}: {e}")

        # Note: States are already stored via _get_or_create_state.
        # We only need to update descriptions and embeddings for new states
        for state in states:
            # Re-read from memory to get latest version
            memory_state = self.memory.get_state(state.id)
            if memory_state:
                # Update description and embedding from our local state object
                if state.description:
                    memory_state.description = state.description
                self._merge_state_attributes(memory_state, state)
                if state.embedding_vector:
                    memory_state.embedding_vector = state.embedding_vector
                try:
                    self.memory.state_manager.update_state(memory_state)
                except Exception as e:
                    logger.info(f"Warning: Failed to update state {state.id}: {e}")

        # Store PageInstances as independent nodes with HAS_INSTANCE edges
        # ID is deterministic from URL, so upsert naturally deduplicates.
        # Within batch: keep the one with snapshot_text if duplicates exist.
        if self.memory.page_instance_manager:
            pi_stored = 0
            best: Dict[str, tuple] = {}  # url -> (state_id, instance)
            for instance in page_instances:
                state_id = getattr(instance, '_parent_state_id', None)
                if not state_id:
                    continue
                prev = best.get(instance.url)
                if prev is None or (instance.snapshot_text and not prev[1].snapshot_text):
                    best[instance.url] = (state_id, instance)

            for url, (state_id, instance) in best.items():
                try:
                    self.memory.page_instance_manager.create_instance(instance)
                    self.memory.page_instance_manager.link_to_state(state_id, instance.id)
                    self.memory.url_index.add_url(instance.url, state_id)
                    pi_stored += 1
                except Exception as e:
                    logger.info(f"Warning: Failed to store PageInstance {instance.id}: {e}")
            logger.info(f"  PageInstances: {pi_stored} stored")

        # Store IntentSequences with deduplication
        # Now they have embeddings (from Stage 6), so both content hash and
        # embedding similarity dedup will work
        stored_count = 0
        skipped_count = 0
        if self.memory.intent_sequence_manager:
            for sequence in intent_sequences:
                state_id = getattr(sequence, '_parent_state_id', None)
                if not state_id:
                    logger.info(f"Warning: IntentSequence {sequence.id} has no _parent_state_id")
                    continue

                # Check for duplicate (now with embedding)
                existing_id = self.memory.intent_sequence_manager.find_duplicate(
                    sequence, state_id
                )
                if existing_id:
                    skipped_count += 1
                    continue

                # Store new sequence
                try:
                    self.memory.intent_sequence_manager.create_sequence(sequence)
                    self.memory.intent_sequence_manager.link_to_state(state_id, sequence.id)
                    stored_count += 1
                except Exception as e:
                    logger.info(f"Warning: Failed to store IntentSequence {sequence.id}: {e}")

        if stored_count > 0 or skipped_count > 0:
            logger.info(f"  IntentSequences: {stored_count} stored, {skipped_count} skipped (duplicates)")

        # Store actions
        for action in actions:
            try:
                self.memory.create_action(action)
            except Exception as e:
                logger.info(f"Warning: Failed to store action: {e}")

        # Store manages
        for manage in manages:
            try:
                self.memory.create_manage(manage)
            except Exception as e:
                logger.info(f"Warning: Failed to store manage edge: {e}")

    async def _create_cognitive_phrase(
        self,
        states: List[State],
        actions: List[Action],
        intent_sequences: List[IntentSequence],
        workflow_data: List[Dict[str, Any]],
        session_id: Optional[str],
    ) -> Optional[CognitivePhrase]:
        """Create a cognitive phrase from the workflow (async).

        V2: Now builds structured execution_plan with ExecutionSteps.

        Args:
            states: List of State objects.
            actions: List of Action objects.
            intent_sequences: List of IntentSequence objects.
            workflow_data: Original workflow events.
            session_id: Session ID.

        Returns:
            CognitivePhrase if created, None otherwise.
        """
        if not states:
            return None

        # Use states in original workflow order (from segments/navigate events)
        # The states are already ordered correctly by the navigate event sequence
        # Do NOT sort by timestamp as it breaks the workflow path when states are reused
        workflow_states = states

        # Build paths (kept for backward compatibility)
        state_path = [s.id for s in workflow_states]
        action_map = {(a.source, a.target): a for a in actions}  # Changed to store full Action

        action_path = []
        for i in range(len(workflow_states) - 1):
            source_id = workflow_states[i].id
            target_id = workflow_states[i + 1].id
            action = action_map.get((source_id, target_id))
            action_path.append(action.type if action else "navigate")

        # Build execution_plan (v2)
        execution_plan = self._build_execution_plan(
            sorted_states=workflow_states,
            actions=actions,
            intent_sequences=intent_sequences,
        )

        # Calculate timestamps
        start_timestamp = workflow_states[0].timestamp
        end_timestamp = workflow_states[-1].end_timestamp or workflow_states[-1].timestamp
        duration = end_timestamp - start_timestamp

        # Generate label and description (async)
        workflow_info = await self._generate_workflow_description(workflow_data)
        label = workflow_info.get("label")
        description = workflow_info.get("description")
        semantic = workflow_info.get("semantic", {})
        if not isinstance(semantic, dict):
            semantic = {}

        current_time = int(time.time() * 1000)

        # Generate default session_id if not provided
        effective_session_id = session_id or f"session_{current_time}"

        phrase = CognitivePhrase(
            label=label,
            description=description,
            semantic=semantic,
            session_id=effective_session_id,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            duration=duration,
            state_path=state_path,
            action_path=action_path,
            execution_plan=execution_plan,  # v2: structured execution plan
            created_at=current_time,
        )

        # Generate embedding (description-first for cognitive phrase)
        embedding_text = self._get_phrase_embedding_text(phrase)
        if self.embedding_service and embedding_text:
            try:
                embedding = await self.embedding_service.embed_async(embedding_text)
                if embedding:
                    phrase.embedding_vector = embedding
            except Exception as e:
                logger.info(f"Warning: Failed to generate phrase embedding: {e}")

        return phrase

    def _build_execution_plan(
        self,
        sorted_states: List[State],
        actions: List[Action],
        intent_sequences: List[IntentSequence],
    ) -> List[ExecutionStep]:
        """Build structured ExecutionSteps from states, actions and sequences.

        Each ExecutionStep represents what happens at a state:
        - index: step number (1-based)
        - state_id: which state/page
        - in_page_sequence_ids: IntentSequences for in-page operations (not causing navigation)
        - navigation_action_id: which Action leads to the next state (if any)
        - navigation_sequence_id: IntentSequence that triggers navigation (if any)

        Args:
            sorted_states: States in workflow execution order (from navigate events).
                          Note: Parameter name kept for backward compatibility,
                          but these are NOT sorted by timestamp anymore.
            actions: List of Action objects.
            intent_sequences: List of IntentSequence objects.

        Returns:
            List of ExecutionStep objects forming the execution plan.
        """
        execution_plan = []

        # Build action lookup: source_id -> Action
        action_by_source: Dict[str, Action] = {}
        for action in actions:
            action_by_source[action.source] = action

        # Build IntentSequence lookup
        # Separate navigation sequences from in-page sequences
        # state_id -> in_page_sequence_ids (non-navigation)
        # state_id -> navigation_sequence_id (causes navigation)
        state_to_in_page_sequences: Dict[str, List[str]] = {s.id: [] for s in sorted_states}
        state_to_navigation_sequence: Dict[str, str] = {}

        # Build state_id -> sequence mapping from HAS_SEQUENCE relationships
        seq_to_state: Dict[str, str] = {}
        if self.memory and self.memory.intent_sequence_manager:
            for state in sorted_states:
                state_seqs = self.memory.intent_sequence_manager.list_by_state(state.id)
                for s in state_seqs:
                    seq_to_state[s.id] = state.id

        for seq in intent_sequences:
            owner_state_id = seq_to_state.get(seq.id)
            if seq.causes_navigation and seq.navigation_target_state_id:
                # This sequence causes navigation - find its source state
                if owner_state_id:
                    state_to_navigation_sequence[owner_state_id] = seq.id
                else:
                    # Fallback: match via action target
                    for action in actions:
                        if action.target == seq.navigation_target_state_id:
                            state_to_navigation_sequence[action.source] = seq.id
                            break
            else:
                # Non-navigation sequence - use graph relationship
                if owner_state_id and owner_state_id in state_to_in_page_sequences:
                    state_to_in_page_sequences[owner_state_id].append(seq.id)

        # Build ExecutionSteps
        for i, state in enumerate(sorted_states):
            # Get in-page IntentSequences for this state
            in_page_sequence_ids = state_to_in_page_sequences.get(state.id, [])

            # Get navigation sequence (if any)
            navigation_sequence_id = state_to_navigation_sequence.get(state.id)

            # Get navigation action (if this is not the last state)
            navigation_action_id = None
            if i < len(sorted_states) - 1:
                action = action_by_source.get(state.id)
                if action:
                    navigation_action_id = action.id

            step = ExecutionStep(
                index=i + 1,  # 1-based index
                state_id=state.id,
                in_page_sequence_ids=in_page_sequence_ids,
                navigation_action_id=navigation_action_id,
                navigation_sequence_id=navigation_sequence_id,
            )
            execution_plan.append(step)

        return execution_plan

    async def _generate_workflow_description(
        self, workflow_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate label and description for the workflow using LLM.

        Args:
            workflow_data: List of workflow events.

        Returns:
            Dict with 'label', 'description', and optional 'semantic' (kept empty).
        """
        default_label = f"工作流（{len(workflow_data)}步）"
        default_description = f"用户工作流包含{len(workflow_data)}个操作事件。"
        default_result = {
            "label": default_label,
            "description": default_description,
            "semantic": {},
        }

        # If no LLM provider, return default
        if not self.simple_llm_provider:
            return default_result

        workflow_summary = json.dumps(workflow_data[:20], ensure_ascii=False, indent=2)

        prompt = f"""请根据以下用户操作事件序列，输出一个简洁的工作流标题和描述。

事件序列:
{workflow_summary}

建议结构（JSON）:
- label: 工作流短标签（5-15字）
- description: 1-2句话描述关键步骤

示例:
{{"label":"搜索并查看咖啡商品","description":"用户先浏览列表页并搜索关键词，再进入详情页查看关键信息。"}}

JSON:"""

        try:
            response = await self.simple_llm_provider.generate_response(
                system_prompt="你是一个擅长总结工作流的助手，优先输出 JSON 对象。",
                user_prompt=prompt
            )
            parsed = parse_json_with_repair(response or "")
            if not isinstance(parsed, dict):
                parsed = {}
            label = str(parsed.get("label") or default_label).strip()[:80]
            description = self._normalize_generated_description(
                raw_text=parsed.get("description") or parsed.get("summary") or "",
                default_text=default_description,
                max_len=320,
            )
            return {
                "label": label,
                "description": description,
                "semantic": {},
            }
        except Exception as e:
            logger.info(f"Warning: Failed to generate workflow description: {e}")
            return default_result


__all__ = [
    "WorkflowProcessor",
    "WorkflowProcessingResult",
    "URLSegment",
]
