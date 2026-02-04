"""Memory Service - Unified interface for Memory Graph operations.

This module provides a high-level interface for all Memory operations,
used by both Desktop App Daemon and Cloud Backend.

Both backends call this service layer, which handles:
- Graph store initialization (SurrealDB, Neo4j, NetworkX)
- Embedding service configuration
- WorkflowMemory and Reasoner lifecycle
- Query, add, clear operations
"""

import logging
import os
from dataclasses import dataclass, field
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

        # 2. Configure embedding service
        self._configure_embedding()

        # 3. Create WorkflowMemory
        self._workflow_memory = WorkflowMemory(
            self._graph_store,
            intent_sequence_dedup_threshold=self._config.intent_sequence_dedup_threshold,
        )

        self._initialized = True
        logger.info("Memory Service initialized successfully")

    def _configure_embedding(self) -> None:
        """Configure the embedding service."""
        from src.common.memory.services import EmbeddingService

        # Get API key from config or environment
        api_key = self._config.embedding_api_key
        if not api_key and self._config.embedding_api_key_env:
            api_key = os.getenv(self._config.embedding_api_key_env)

        if not api_key:
            logger.warning(
                f"Embedding API key not found. "
                f"Set {self._config.embedding_api_key_env} or provide embedding_api_key. "
                "Semantic search will be disabled."
            )
            return

        EmbeddingService.configure(
            provider=self._config.embedding_provider,
            model=self._config.embedding_model,
            dimension=self._config.embedding_dimension,
            api_url=self._config.embedding_api_url,
            api_key=api_key,
        )
        logger.info(
            f"Embedding Service: {self._config.embedding_provider} / "
            f"{self._config.embedding_model}"
        )

    def _get_reasoner(self, llm_provider: Any = None) -> "Reasoner":
        """Get or create Reasoner instance.

        Args:
            llm_provider: LLM provider for reasoning (optional)

        Returns:
            Reasoner instance
        """
        from src.common.memory.reasoner import Reasoner
        from src.common.memory.services import EmbeddingService

        # Update LLM provider if provided
        if llm_provider:
            self._llm_provider = llm_provider

        # Create new Reasoner with current LLM provider
        self._reasoner = Reasoner(
            memory=self._workflow_memory,
            llm_provider=self._llm_provider,
            embedding_service=EmbeddingService if EmbeddingService.is_available() else None,
            max_depth=3,
        )
        return self._reasoner

    def _get_workflow_processor(self, llm_provider: Any = None) -> "WorkflowProcessor":
        """Get or create WorkflowProcessor instance.

        Args:
            llm_provider: LLM provider for description generation

        Returns:
            WorkflowProcessor instance
        """
        from src.common.memory.thinker import WorkflowProcessor
        from src.common.memory.services import EmbeddingService

        # Update LLM provider if provided
        if llm_provider:
            self._llm_provider = llm_provider

        # Get embedding model
        embedding_model = None
        if EmbeddingService.is_available():
            embedding_model = EmbeddingService.get_model()

        self._workflow_processor = WorkflowProcessor(
            llm_provider=self._llm_provider,
            memory=self._workflow_memory,
            embedding_model=embedding_model,
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
        user_id: Optional[str] = None,
        generate_embeddings: bool = True,
        llm_provider: Any = None,
    ) -> Dict[str, Any]:
        """Add a recording to the memory graph.

        Args:
            operations: List of operation events from recording
            session_id: Optional session identifier
            user_id: Optional user identifier
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
                user_id=user_id,
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


# ==================== Global Instances ====================
# Two separate instances: local (SurrealDB) and public (Cloud Backend)

_local_memory_service: Optional[MemoryService] = None
_public_memory_service: Optional[MemoryService] = None


# ---------- Local Memory Service (SurrealDB embedded) ----------

def get_local_memory_service() -> Optional[MemoryService]:
    """Get the local MemoryService instance (SurrealDB embedded).

    Returns:
        MemoryService instance if initialized, None otherwise
    """
    return _local_memory_service


def set_local_memory_service(service: MemoryService) -> None:
    """Set the local MemoryService instance.

    Args:
        service: MemoryService instance to set as local
    """
    global _local_memory_service
    _local_memory_service = service


def init_local_memory_service(config: MemoryServiceConfig) -> MemoryService:
    """Initialize and set the local MemoryService instance.

    Args:
        config: Service configuration (should use SurrealDB)

    Returns:
        Initialized MemoryService instance
    """
    global _local_memory_service
    _local_memory_service = MemoryService(config)
    _local_memory_service.initialize()
    logger.info(f"Local Memory Service initialized: {config.graph_backend}")
    return _local_memory_service


# ---------- Public Memory Service (Cloud Backend) ----------

def get_public_memory_service() -> Optional[MemoryService]:
    """Get the public MemoryService instance (Cloud Backend).

    Returns:
        MemoryService instance if initialized, None otherwise
    """
    return _public_memory_service


def set_public_memory_service(service: MemoryService) -> None:
    """Set the public MemoryService instance.

    Args:
        service: MemoryService instance to set as public
    """
    global _public_memory_service
    _public_memory_service = service


def init_public_memory_service(config: MemoryServiceConfig) -> MemoryService:
    """Initialize and set the public MemoryService instance.

    Args:
        config: Service configuration (should use Neo4j or remote SurrealDB)

    Returns:
        Initialized MemoryService instance
    """
    global _public_memory_service
    _public_memory_service = MemoryService(config)
    _public_memory_service.initialize()
    logger.info(f"Public Memory Service initialized: {config.graph_backend}")
    return _public_memory_service


# ---------- Backward Compatibility ----------
# get_memory_service() returns public by default (current behavior)

def get_memory_service() -> Optional[MemoryService]:
    """Get the default MemoryService instance.

    Returns public memory service by default. For explicit access,
    use get_local_memory_service() or get_public_memory_service().

    Returns:
        MemoryService instance if initialized, None otherwise
    """
    return _public_memory_service or _local_memory_service


def set_memory_service(service: MemoryService) -> None:
    """Set the default MemoryService instance.

    Sets as public memory service for backward compatibility.

    Args:
        service: MemoryService instance to set
    """
    set_public_memory_service(service)


def init_memory_service(config: MemoryServiceConfig) -> MemoryService:
    """Initialize and set the default MemoryService instance.

    Initializes as public memory service for backward compatibility.

    Args:
        config: Service configuration

    Returns:
        Initialized MemoryService instance
    """
    return init_public_memory_service(config)
