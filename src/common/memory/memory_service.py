"""Memory Service - Unified interface for Memory Graph operations.

This module provides a high-level interface for all Memory operations,
used by both Desktop App Daemon and Cloud Backend.

Both backends call this service layer, which handles:
- Graph store initialization (SurrealDB, Neo4j, NetworkX)
- Embedding service configuration
- WorkflowMemory and Reasoner lifecycle
- Query, add, clear operations
"""

import asyncio
import hashlib
import logging
import os
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryServiceConfig:
    """Configuration for Memory Service.

    Attributes:
        graph_backend: Graph store backend ('surrealdb', 'neo4j', 'networkx')
        graph_url: URL for graph store connection
        graph_namespace: Namespace for graph store
        graph_database: Database name for graph store
        graph_username: Username for authentication
        graph_password: Password for authentication
        vector_dimensions: Embedding vector dimensions
        embedding_provider: Embedding service provider
        embedding_model: Embedding model name
        embedding_api_url: Embedding API URL
        embedding_api_key: Embedding API key (or env var name)
        intent_sequence_dedup_threshold: Threshold for deduplication
    """
    # Graph store config
    graph_backend: str = "surrealdb"
    graph_url: str = field(default_factory=lambda: os.getenv(
        "SURREALDB_URL", f"file://{os.path.expanduser('~/.ami/memory.db')}"
    ))
    graph_namespace: str = "ami"
    graph_database: str = "memory"
    graph_username: str = "root"
    graph_password: str = "root"
    vector_dimensions: int = 1024

    # Embedding config
    embedding_provider: str = "openai"
    embedding_model: str = "BAAI/bge-m3"
    embedding_api_url: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_api_key_env: str = "SILICONFLOW_API_KEY"
    embedding_dimension: int = 1024

    # Memory config
    intent_sequence_dedup_threshold: Optional[float] = None


class MemoryService:
    """High-level Memory Service for graph operations.

    Provides unified interface for:
    - Adding recordings to memory
    - Querying memory (task, navigation, action queries)
    - Managing cognitive phrases
    - Memory statistics and cleanup

    Usage:
        # Initialize
        config = MemoryServiceConfig(graph_backend="surrealdb", ...)
        service = MemoryService(config)
        service.initialize()

        # Use
        result = await service.query(query="search products")
        result = await service.add_recording(operations=[...])

        # Cleanup
        service.close()
    """

    def __init__(self, config: MemoryServiceConfig):
        """Initialize Memory Service.

        Args:
            config: Service configuration
        """
        self._config = config
        self._graph_store = None
        self._workflow_memory = None
        self._reasoner = None
        self._llm_provider = None
        self._workflow_processor = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the memory service.

        Sets up:
        1. Graph store (SurrealDB, Neo4j, or NetworkX)
        2. Embedding service
        3. WorkflowMemory
        """
        if self._initialized:
            return

        from src.common.memory.graphstore import create_graph_store
        from src.common.memory.memory.workflow_memory import WorkflowMemory
        from src.common.memory.services import EmbeddingService

        # 1. Create graph store
        backend = self._config.graph_backend
        logger.info(f"Initializing Memory Service with {backend} backend")

        if backend == "surrealdb":
            from src.common.memory.graphstore import SurrealDBConfig
            surreal_config = SurrealDBConfig(
                url=self._config.graph_url,
                namespace=self._config.graph_namespace,
                database=self._config.graph_database,
                username=self._config.graph_username,
                password=self._config.graph_password,
                vector_dimensions=self._config.vector_dimensions,
            )
            self._graph_store = create_graph_store("surrealdb", config=surreal_config)
            logger.info(f"Graph Store: SurrealDB ({surreal_config.mode} mode)")

        elif backend == "neo4j":
            self._graph_store = create_graph_store(
                "neo4j",
                uri=self._config.graph_url,
                user=self._config.graph_username,
                password=self._config.graph_password,
                database=self._config.graph_database,
            )
            logger.info(f"Graph Store: Neo4j ({self._config.graph_url})")

        else:
            self._graph_store = create_graph_store("networkx")
            logger.info("Graph Store: NetworkX (in-memory)")

        # Initialize schema
        self._graph_store.initialize_schema()

        # 2. Create WorkflowMemory
        self._workflow_memory = WorkflowMemory(
            self._graph_store,
            intent_sequence_dedup_threshold=self._config.intent_sequence_dedup_threshold,
        )

        self._initialized = True
        logger.info("Memory Service initialized successfully")

    def _get_reasoner(self, llm_provider: Any = None, embedding_service: Any = None) -> "Reasoner":
        """Get or create Reasoner instance.

        Args:
            llm_provider: LLM provider for reasoning (optional)
            embedding_service: EmbeddingService instance with user API key (optional)

        Returns:
            Reasoner instance
        """
        from src.common.memory.reasoner import Reasoner

        # Update LLM provider if provided
        if llm_provider:
            self._llm_provider = llm_provider

        # Create new Reasoner with current LLM provider and embedding service
        self._reasoner = Reasoner(
            memory=self._workflow_memory,
            llm_provider=self._llm_provider,
            embedding_service=embedding_service,
            max_depth=3,
        )
        return self._reasoner

    def _get_workflow_processor(self, llm_provider: Any = None, embedding_service: Any = None) -> "WorkflowProcessor":
        """Get or create WorkflowProcessor instance.

        Args:
            llm_provider: LLM provider for description generation
            embedding_service: EmbeddingService instance with user API key (optional)

        Returns:
            WorkflowProcessor instance
        """
        from src.common.memory.thinker import WorkflowProcessor

        # Update LLM provider if provided
        if llm_provider:
            self._llm_provider = llm_provider

        self._workflow_processor = WorkflowProcessor(
            llm_provider=self._llm_provider,
            memory=self._workflow_memory,
            embedding_service=embedding_service,
            simple_llm_provider=self._llm_provider,
        )
        return self._workflow_processor

    def set_llm_provider(self, llm_provider: Any) -> None:
        """Set LLM provider for reasoning and description generation.

        Args:
            llm_provider: LLM provider instance
        """
        self._llm_provider = llm_provider

    @property
    def workflow_memory(self) -> "WorkflowMemory":
        """Get the underlying WorkflowMemory instance."""
        if not self._initialized:
            raise RuntimeError("MemoryService not initialized. Call initialize() first.")
        return self._workflow_memory

    @property
    def graph_store(self):
        """Get the underlying graph store."""
        if not self._initialized:
            raise RuntimeError("MemoryService not initialized. Call initialize() first.")
        return self._graph_store

    # ==================== Query Operations ====================

    async def query(
        self,
        query: str,
        top_k: int = 3,
        current_state: Optional[str] = None,
        start_state: Optional[str] = None,
        end_state: Optional[str] = None,
        llm_provider: Any = None,
    ) -> Dict[str, Any]:
        """Query the memory using natural language.

        Supports three query types (auto-detected):
        - Task query: Find complete workflow for a task
        - Navigation query: Find path between two states
        - Action query: Find available actions in current state

        Args:
            query: Natural language query
            top_k: Number of top results to return
            current_state: Current state for action query
            start_state: Start state for navigation query
            end_state: End state for navigation query
            llm_provider: LLM provider for reasoning

        Returns:
            Dict with query results
        """
        if not self._initialized:
            raise RuntimeError("MemoryService not initialized. Call initialize() first.")

        try:
            reasoner = self._get_reasoner(llm_provider)

            result = await reasoner.query(
                target=query,
                current_state=current_state,
                start_state=start_state,
                end_state=end_state,
                top_k=top_k,
            )

            # Build response dict
            response = {
                "success": result.success,
                "query_type": result.query_type,
                "states": [s.to_dict() for s in (result.states or [])],
                "intent_sequences": [s.to_dict() for s in (result.intent_sequences or [])],
                "cognitive_phrase": result.cognitive_phrase.to_dict() if result.cognitive_phrase else None,
                "execution_plan": [s.to_dict() for s in (result.execution_plan or [])] if result.execution_plan else None,
                "subtasks": [s.to_dict() for s in (result.subtasks or [])] if result.subtasks else None,
                "metadata": result.metadata or {},
            }

            # For action queries, put outgoing actions in separate field
            actions_list = [a.to_dict() for a in (result.actions or [])]
            if result.query_type == "action":
                response["outgoing_actions"] = actions_list
                response["actions"] = []
            else:
                response["actions"] = actions_list
                response["outgoing_actions"] = []

            return response

        except Exception as e:
            logger.error(f"Failed to query memory: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e),
            }

    # ==================== Add Recording ====================

    async def add_recording(
        self,
        operations: List[Dict[str, Any]],
        session_id: Optional[str] = None,
        generate_embeddings: bool = True,
        llm_provider: Any = None,
    ) -> Dict[str, Any]:
        """Add a recording to the memory graph.

        Args:
            operations: List of operation events from recording
            session_id: Optional session identifier
            generate_embeddings: Whether to generate embeddings
            llm_provider: LLM provider for description generation

        Returns:
            Dict with processing statistics
        """
        if not self._initialized:
            raise RuntimeError("MemoryService not initialized. Call initialize() first.")

        if not operations:
            return {
                "success": False,
                "error": "No operations provided",
            }

        logger.info(f"[MemoryService] Adding {len(operations)} operations to memory")

        try:
            processor = self._get_workflow_processor(llm_provider)

            result = await processor.process_workflow(
                workflow_data=operations,
                session_id=session_id,
                store_to_memory=True,
            )

            summary = result.get_summary()
            logger.info(f"[MemoryService] Processing complete: {summary}")

            return {
                "success": True,
                "states_added": summary.get("new_states", 0),
                "states_merged": summary.get("reused_states", 0),
                "page_instances_added": summary.get("page_instance_count", 0),
                "intent_sequences_added": summary.get("intent_sequence_count", 0),
                "actions_added": summary.get("action_count", 0),
                "processing_time_ms": summary.get("processing_time_ms", 0),
            }

        except Exception as e:
            logger.error(f"Failed to add recording to memory: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e),
            }

    # ==================== Stats and Clear ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics.

        Returns:
            Dictionary with node count, edge count, etc.
        """
        if not self._initialized:
            return {"initialized": False}

        from src.common.memory.services import EmbeddingService

        stats = self._graph_store.get_statistics()
        stats["initialized"] = True
        stats["embedding_available"] = EmbeddingService.is_available()
        return stats

    def clear(self) -> Dict[str, Any]:
        """Clear all data from the memory.

        Returns:
            Dict with deletion counts
        """
        if not self._initialized:
            raise RuntimeError("MemoryService not initialized. Call initialize() first.")

        try:
            result = self._workflow_memory.clear_all()
            return {
                "success": True,
                **result,
            }
        except Exception as e:
            logger.error(f"Failed to clear memory: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    # ==================== CognitivePhrase Operations ====================

    def list_phrases(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List cognitive phrases from memory.

        Args:
            limit: Maximum number of phrases to return

        Returns:
            List of phrase dictionaries
        """
        if not self._initialized:
            return []

        try:
            phrases = self._workflow_memory.phrase_manager.list_phrases(limit=limit)
            return [
                {
                    "id": p.id,
                    "label": p.label,
                    "description": p.description,
                    "access_count": p.access_count,
                    "last_accessed": p.last_access_time,
                }
                for p in phrases
            ]
        except Exception as e:
            logger.error(f"Failed to list phrases: {e}")
            return []

    def get_phrase(self, phrase_id: str) -> Optional[Dict[str, Any]]:
        """Get a cognitive phrase by ID with related states and intent sequences.

        Args:
            phrase_id: Phrase identifier

        Returns:
            Dictionary with phrase, states, and intent_sequences
        """
        if not self._initialized:
            return None

        try:
            return self._workflow_memory.get_phrase_detail(phrase_id)
        except Exception as e:
            logger.error(f"Failed to get phrase: {e}")
            return None

    def delete_phrase(self, phrase_id: str) -> bool:
        """Delete a cognitive phrase.

        Args:
            phrase_id: Phrase identifier

        Returns:
            True if deleted successfully
        """
        if not self._initialized:
            return False

        try:
            return self._workflow_memory.phrase_manager.delete_phrase(phrase_id)
        except Exception as e:
            logger.error(f"Failed to delete phrase: {e}")
            return False

    # ==================== Lifecycle ====================

    def close(self) -> None:
        """Close the memory service and release resources."""
        if self._graph_store:
            self._graph_store.close()
            self._graph_store = None
        self._workflow_memory = None
        self._reasoner = None
        self._workflow_processor = None
        self._llm_provider = None
        self._initialized = False
        logger.info("Memory Service closed")


# ==================== Multi-Tenant Global Instances ====================
# Per-user private memory (LRU-cached) + shared public memory

MAX_CACHED_PRIVATE_STORES = 100

_private_stores: OrderedDict[str, MemoryService] = OrderedDict()
_private_stores_lock = RLock()
_public_memory_service: Optional[MemoryService] = None
_base_config: Optional[MemoryServiceConfig] = None


def _sanitize_user_id(user_id: str) -> str:
    """Sanitize user_id for use as SurrealDB database name.

    Uses a short hash suffix to prevent collisions from character replacement.
    For example, 'user.1' and 'user-1' produce different database names.

    Args:
        user_id: Raw user ID string.

    Returns:
        Sanitized string safe for SurrealDB database name, collision-free.
    """
    # If user_id is already alphanumeric (common case), skip hashing
    if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", user_id):
        return user_id

    # Replace non-alphanumeric with underscore for readability
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", user_id)
    # Append short hash to prevent collisions (user.1 vs user-1 vs user_1)
    hash_suffix = hashlib.sha256(user_id.encode()).hexdigest()[:8]
    sanitized = f"{sanitized}_{hash_suffix}"
    if sanitized[0].isdigit():
        sanitized = f"u{sanitized}"
    return sanitized


def init_memory_services(base_config: MemoryServiceConfig) -> None:
    """Initialize the memory service infrastructure.

    Sets up:
    - Base config template for creating per-user private instances
    - Public memory service (database: "public")

    Args:
        base_config: Base configuration with shared SurrealDB connection settings.
    """
    global _base_config, _public_memory_service
    _base_config = base_config

    public_config = MemoryServiceConfig(
        graph_backend=base_config.graph_backend,
        graph_url=base_config.graph_url,
        graph_namespace=base_config.graph_namespace,
        graph_database="public",
        graph_username=base_config.graph_username,
        graph_password=base_config.graph_password,
        vector_dimensions=base_config.vector_dimensions,
        embedding_provider=base_config.embedding_provider,
        embedding_model=base_config.embedding_model,
        embedding_api_url=base_config.embedding_api_url,
        embedding_api_key=base_config.embedding_api_key,
        embedding_api_key_env=base_config.embedding_api_key_env,
        embedding_dimension=base_config.embedding_dimension,
        intent_sequence_dedup_threshold=base_config.intent_sequence_dedup_threshold,
    )
    _public_memory_service = MemoryService(public_config)
    _public_memory_service.initialize()
    logger.info("Public Memory Service initialized (database: public)")


def get_private_memory(user_id: str) -> MemoryService:
    """Get or create a private MemoryService for the given user.

    Creates a new SurrealDB database `private_{sanitized_user_id}` on first access.
    Uses LRU cache with eviction for connection management.

    Args:
        user_id: User identifier.

    Returns:
        MemoryService instance for this user's private database.

    Raises:
        RuntimeError: If init_memory_services() has not been called.
    """
    if _base_config is None:
        raise RuntimeError("Memory services not initialized. Call init_memory_services() first.")

    # Fast path: check cache under lock
    with _private_stores_lock:
        if user_id in _private_stores:
            _private_stores.move_to_end(user_id)
            return _private_stores[user_id]

    # Slow path: create service OUTSIDE lock (network I/O in initialize)
    sanitized = _sanitize_user_id(user_id)
    db_name = f"private_{sanitized}"

    config = MemoryServiceConfig(
        graph_backend=_base_config.graph_backend,
        graph_url=_base_config.graph_url,
        graph_namespace=_base_config.graph_namespace,
        graph_database=db_name,
        graph_username=_base_config.graph_username,
        graph_password=_base_config.graph_password,
        vector_dimensions=_base_config.vector_dimensions,
        embedding_provider=_base_config.embedding_provider,
        embedding_model=_base_config.embedding_model,
        embedding_api_url=_base_config.embedding_api_url,
        embedding_api_key=_base_config.embedding_api_key,
        embedding_api_key_env=_base_config.embedding_api_key_env,
        embedding_dimension=_base_config.embedding_dimension,
        intent_sequence_dedup_threshold=_base_config.intent_sequence_dedup_threshold,
    )
    service = MemoryService(config)
    service.initialize()

    # Re-acquire lock to insert into cache
    with _private_stores_lock:
        # Double-check: another thread may have created it while we were initializing
        if user_id in _private_stores:
            service.close()
            _private_stores.move_to_end(user_id)
            return _private_stores[user_id]

        # Evict oldest if at capacity
        if len(_private_stores) >= MAX_CACHED_PRIVATE_STORES:
            _, old_service = _private_stores.popitem(last=False)
            old_service.close()

        _private_stores[user_id] = service
        logger.info(f"Private Memory Service initialized for user '{user_id}' (database: {db_name})")
        return service


def get_public_memory() -> MemoryService:
    """Get the shared public MemoryService.

    Returns:
        Public MemoryService instance.

    Raises:
        RuntimeError: If init_memory_services() has not been called.
    """
    if _public_memory_service is None:
        raise RuntimeError("Memory services not initialized. Call init_memory_services() first.")
    return _public_memory_service


async def share_phrase(user_id: str, phrase_id: str) -> str:
    """Copy a CognitivePhrase and its dependencies to public memory.

    Deep-copies the phrase and all referenced States, Actions,
    IntentSequences, and Domains from user's private database
    to the public database with new IDs.

    Args:
        user_id: User ID (owner of the phrase).
        phrase_id: Phrase ID in user's private memory.

    Returns:
        New phrase ID in public database.

    Raises:
        ValueError: If phrase not found.
    """
    private = get_private_memory(user_id)
    public = get_public_memory()

    private_wm = private.workflow_memory
    public_wm = public.workflow_memory

    # 1. Load phrase
    phrase = private_wm.phrase_manager.get_phrase(phrase_id)
    if not phrase:
        raise ValueError(f"Phrase {phrase_id} not found in private memory for user '{user_id}'")

    # 1b. Idempotency check: if already shared, return existing public phrase ID
    existing_nodes = public_wm.phrase_manager.graph_store.query_nodes(
        label=public_wm.phrase_manager.node_label,
        filters={"source_phrase_id": phrase_id, "contributor_id": user_id},
        limit=1,
    )
    if existing_nodes:
        from src.common.memory.ontology.cognitive_phrase import CognitivePhrase as CP
        existing = CP.from_dict(existing_nodes[0])
        logger.info(f"Phrase '{phrase.label}' already shared by user '{user_id}' (ID: {existing.id})")
        return existing.id

    # 2. Collect all referenced entity IDs from execution_plan
    state_ids = set()
    action_ids = set()
    sequence_ids = set()
    for step in phrase.execution_plan:
        state_ids.add(step.state_id)
        if step.navigation_action_id:
            action_ids.add(step.navigation_action_id)
        sequence_ids.update(step.in_page_sequence_ids)
        if step.navigation_sequence_id:
            sequence_ids.add(step.navigation_sequence_id)

    # Also collect from state_path (backward compat)
    for sid in phrase.state_path:
        state_ids.add(sid)

    # 3. Load all entities from private memory
    states = {}
    for sid in state_ids:
        s = private_wm.state_manager.get_state(sid)
        if s:
            states[sid] = s

    actions = {}
    for aid in action_ids:
        a = private_wm.action_manager.get_action_by_id(aid)
        if a:
            actions[aid] = a

    # Also collect actions between adjacent states in state_path (by graph edge lookup).
    # navigation_action_id in execution_plan may be None if the action was not indexed
    # during phrase creation, but the action edge still exists in the graph.
    for i in range(len(phrase.state_path) - 1):
        src_id = phrase.state_path[i]
        tgt_id = phrase.state_path[i + 1]
        a = private_wm.get_action(src_id, tgt_id)
        if a and a.id not in actions:
            actions[a.id] = a

    sequences = {}
    for seqid in sequence_ids:
        if private_wm.intent_sequence_manager:
            seq = private_wm.intent_sequence_manager.get_sequence(seqid)
            if seq:
                sequences[seqid] = seq

    # Collect domains from states
    domain_ids = set()
    for s in states.values():
        if s.domain:
            domain_ids.add(s.domain)

    domains = {}
    for did in domain_ids:
        d = private_wm.domain_manager.get_domain(did)
        if d:
            domains[did] = d

    # 4. Build id_map incrementally as entities are created/deduped
    id_map = {}

    # 5. Deep-copy entities to public with deduplication

    # Copy domains (keep original domain IDs since they are normalized URLs)
    for did, domain in domains.items():
        new_domain = domain.model_copy(deep=True)
        public_wm.domain_manager.create_domain(new_domain)

    # Copy states with dedup via find_or_create_state()
    for old_id, state in states.items():
        existing_or_new, is_new = public_wm.find_or_create_state(
            url=state.page_url,
            page_title=state.page_title,
            timestamp=state.timestamp,
            description=state.description,
            domain=state.domain,
            path_sig=state.path_sig,
        )
        id_map[old_id] = existing_or_new.id

        # Copy embedding_vector and attributes to new states
        if is_new:
            needs_update = False
            if state.embedding_vector:
                existing_or_new.embedding_vector = state.embedding_vector
                needs_update = True
            if state.attributes:
                existing_or_new.attributes = state.attributes
                needs_update = True
            if needs_update:
                public_wm.state_manager.update_state(existing_or_new)

    # Copy Manage relations (Domain → State) with remapped state IDs
    for old_state_id in states:
        manages = private_wm.manage_manager.list_manages(state_id=old_state_id)
        for manage in manages:
            new_manage = manage.model_copy(deep=True)
            new_manage.state_id = id_map.get(old_state_id, old_state_id)
            # domain_id stays the same (domains keep original IDs)
            public_wm.manage_manager.create_manage(new_manage)

    # Copy intent sequences with dedup via find_duplicate()
    if private_wm.intent_sequence_manager and public_wm.intent_sequence_manager:
        # Pre-build reverse mapping: sequence_id → state_id (O(n) instead of O(n*m))
        seq_to_state = {}
        for step in phrase.execution_plan:
            for sid in step.in_page_sequence_ids:
                seq_to_state[sid] = step.state_id
            if step.navigation_sequence_id:
                seq_to_state[step.navigation_sequence_id] = step.state_id

        for old_id, seq in sequences.items():
            old_state_id = seq_to_state.get(old_id)
            if not old_state_id:
                # Sequence not referenced in execution_plan — copy without dedup
                new_seq = seq.model_copy(deep=True)
                new_seq.id = str(uuid.uuid4())
                public_wm.intent_sequence_manager.create_sequence(new_seq)
                id_map[old_id] = new_seq.id
                continue

            new_state_id = id_map.get(old_state_id, old_state_id)
            dup_id = public_wm.intent_sequence_manager.find_duplicate(seq, new_state_id)
            if dup_id:
                id_map[old_id] = dup_id
            else:
                new_seq = seq.model_copy(deep=True)
                new_seq.id = str(uuid.uuid4())
                public_wm.intent_sequence_manager.create_sequence(new_seq)
                public_wm.intent_sequence_manager.link_to_state(new_state_id, new_seq.id)
                id_map[old_id] = new_seq.id

    # Copy actions with remapped source/target (upsert handles dedup)
    # Also build reverse lookup: (old_source, old_target) → new_action_id
    # for back-filling execution_plan steps that have navigation_action_id=None.
    action_by_edge = {}  # (old_source, old_target) → new_action_id
    for old_id, action in actions.items():
        new_source = id_map.get(action.source, action.source)
        new_target = id_map.get(action.target, action.target)
        # Skip actions where source and target deduped to the same public State
        if new_source == new_target:
            logger.warning(
                f"Skipping action {old_id}: source and target deduped to same state {new_source}"
            )
            continue
        new_action = action.model_copy(deep=True)
        new_action.id = str(uuid.uuid4())
        new_action.source = new_source
        new_action.target = new_target
        if new_action.trigger_sequence_id:
            new_action.trigger_sequence_id = id_map.get(
                new_action.trigger_sequence_id, new_action.trigger_sequence_id
            )
        public_wm.action_manager.create_action(new_action)
        id_map[old_id] = new_action.id
        action_by_edge[(action.source, action.target)] = new_action.id

    # 6. Copy phrase with contributor fields
    new_phrase = phrase.model_copy(deep=True)
    new_phrase.id = str(uuid.uuid4())
    new_phrase.contributor_id = user_id
    new_phrase.contributed_at = int(time.time() * 1000)
    new_phrase.source_phrase_id = phrase_id
    new_phrase.use_count = 0
    new_phrase.upvote_count = 0

    # Remap internal references
    new_phrase.state_path = [id_map.get(sid, sid) for sid in new_phrase.state_path]

    from src.common.memory.ontology.cognitive_phrase import ExecutionStep
    new_plan = []
    for idx, step in enumerate(new_phrase.execution_plan):
        # Remap navigation_action_id; back-fill from action_by_edge if originally None
        nav_action_id = None
        if step.navigation_action_id:
            nav_action_id = id_map.get(step.navigation_action_id, step.navigation_action_id)
        elif idx < len(phrase.state_path) - 1:
            # navigation_action_id was None in original phrase, try to resolve
            # from state_path adjacency
            old_src = phrase.state_path[idx]
            old_tgt = phrase.state_path[idx + 1]
            nav_action_id = action_by_edge.get((old_src, old_tgt))

        new_step = ExecutionStep(
            index=step.index,
            state_id=id_map.get(step.state_id, step.state_id),
            in_page_sequence_ids=[id_map.get(sid, sid) for sid in step.in_page_sequence_ids],
            navigation_action_id=nav_action_id,
            navigation_sequence_id=id_map.get(step.navigation_sequence_id, step.navigation_sequence_id) if step.navigation_sequence_id else None,
        )
        new_plan.append(new_step)
    new_phrase.execution_plan = new_plan

    public_wm.phrase_manager.create_phrase(new_phrase)

    logger.info(f"Shared phrase '{phrase.label}' from user '{user_id}' to public (new ID: {new_phrase.id})")
    return new_phrase.id


# ---------- Backward Compatibility Aliases ----------

# Desktop app uses get_local_memory_service() for the local SurrealDB
# Cloud backend uses get_memory_service() for the shared instance
# Both now delegate to the multi-tenant system.

_local_memory_service: Optional[MemoryService] = None


def get_local_memory_service() -> Optional[MemoryService]:
    """Get the local MemoryService instance (Desktop App).

    Returns:
        MemoryService instance if initialized, None otherwise.
    """
    return _local_memory_service


def set_local_memory_service(service: MemoryService) -> None:
    """Set the local MemoryService instance.

    Args:
        service: MemoryService instance to set as local.
    """
    global _local_memory_service
    _local_memory_service = service


def init_local_memory_service(config: MemoryServiceConfig) -> MemoryService:
    """Initialize and set the local MemoryService instance.

    Args:
        config: Service configuration (should use SurrealDB).

    Returns:
        Initialized MemoryService instance.
    """
    global _local_memory_service
    _local_memory_service = MemoryService(config)
    _local_memory_service.initialize()
    logger.info(f"Local Memory Service initialized: {config.graph_backend}")
    return _local_memory_service


def get_public_memory_service() -> Optional[MemoryService]:
    """Get the public MemoryService instance.

    Returns:
        Public MemoryService instance, or None if not initialized.
    """
    return _public_memory_service


def get_memory_service() -> Optional[MemoryService]:
    """Get the default MemoryService instance (backward compatibility).

    Returns public memory service by default.

    Returns:
        MemoryService instance if initialized, None otherwise.
    """
    return _public_memory_service or _local_memory_service


def set_memory_service(service: MemoryService) -> None:
    """Set the default MemoryService instance (backward compatibility).

    Args:
        service: MemoryService instance to set.
    """
    global _public_memory_service
    _public_memory_service = service


def init_memory_service(config: MemoryServiceConfig) -> MemoryService:
    """Initialize and set the default MemoryService (backward compatibility).

    Args:
        config: Service configuration.

    Returns:
        Initialized MemoryService instance.
    """
    global _public_memory_service
    _public_memory_service = MemoryService(config)
    _public_memory_service.initialize()
    logger.info(f"Memory Service initialized: {config.graph_backend}")
    return _public_memory_service
