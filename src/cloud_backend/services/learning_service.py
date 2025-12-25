"""
Learning Service - Intent extraction and MetaFlow generation
"""
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to Python path so we can import from src
backend_dir = Path(__file__).parent
project_root = str(backend_dir.parent.parent.parent.parent)
sys.path.insert(0, project_root)

from storage_service import storage_service
from src.cloud_backend.intent_builder.extractors.intent_extractor import IntentExtractor
from src.cloud_backend.intent_builder.core.intent_memory_graph import IntentMemoryGraph
from src.cloud_backend.intent_builder.storage.in_memory_storage import InMemoryIntentStorage
from src.cloud_backend.intent_builder.generators.metaflow_generator import MetaFlowGenerator
from src.common.llm import AnthropicProvider

logger = logging.getLogger(__name__)


class LearningService:
    """Handles learning phase operations: intent extraction and metaflow generation"""

    def __init__(self, llm_provider=None):
        """Initialize learning service

        Args:
            llm_provider: LLM provider instance (must be provided with user's API key)
        """
        if llm_provider is None:
            raise ValueError("llm_provider is required - must be created with user's API key and API Proxy URL")
        self.llm_provider = llm_provider
        self.storage = storage_service

    async def extract_intents(self, user_id: int, session_id: str) -> Dict:
        """Extract intents from recorded operations

        Args:
            user_id: User ID
            session_id: Recording session ID

        Returns:
            Dict with keys: success, session_id, intents, intents_count

        Raises:
            ValueError: If operations not found or extraction fails
        """
        logger.info(f"Extracting intents for session {session_id}")

        # 1. Read operations
        operations = self.storage.get_learning_operations(user_id, session_id)
        if not operations:
            raise ValueError(f"Operations not found for session: {session_id}")

        # 2. Get session metadata for task description
        session = self.storage.get_learning_session(user_id, session_id)
        if not session:
            raise ValueError(f"Session metadata not found: {session_id}")

        task_description = session.get("description") or session.get("title", "")

        # 3. Call IntentExtractor
        extractor = IntentExtractor(self.llm_provider)
        intent_objects = await extractor.extract_intents(
            operations=operations,
            task_description=task_description,
            source_session_id=session_id
        )

        # 4. Convert Intent objects to dicts
        intents = [intent.to_dict() for intent in intent_objects]

        # 5. Save intents
        self.storage.save_learning_intents(user_id, session_id, intents)

        logger.info(f"Extracted {len(intents)} intents for session {session_id}")

        return {
            "success": True,
            "session_id": session_id,
            "intents": intents,
            "intents_count": len(intents)
        }

    async def generate_metaflow(self, user_id: int, session_id: str) -> Dict:
        """Generate MetaFlow from extracted intents

        Args:
            user_id: User ID
            session_id: Recording session ID

        Returns:
            Dict with keys: success, session_id, metaflow_yaml, nodes_count

        Raises:
            ValueError: If intents not found or generation fails
        """
        logger.info(f"Generating MetaFlow for session {session_id}")

        # 1. Read intents
        intent_dicts = self.storage.get_learning_intents(user_id, session_id)
        if not intent_dicts:
            raise ValueError(f"Intents not found for session: {session_id}")

        # 2. Get session metadata
        session = self.storage.get_learning_session(user_id, session_id)
        if not session:
            raise ValueError(f"Session metadata not found: {session_id}")

        task_description = session.get("description") or session.get("title", "")

        # 3. Convert dicts to Intent objects
        from src.cloud_backend.intent_builder.core.intent import Intent
        intents = [Intent.from_dict(intent_dict) for intent_dict in intent_dicts]

        # 4. Build IntentMemoryGraph with in-memory storage
        storage_backend = InMemoryIntentStorage()
        graph = IntentMemoryGraph(storage=storage_backend)
        for intent in intents:
            graph.add_intent(intent)

        # Build edges (sequential by default)
        for i in range(len(intents) - 1):
            graph.add_edge(intents[i].id, intents[i + 1].id)

        # 5. Call MetaFlowGenerator
        generator = MetaFlowGenerator(self.llm_provider)
        metaflow = await generator.generate(
            graph=graph,
            task_description=task_description,
            user_query=task_description  # Use task description as user query
        )

        metaflow_yaml = metaflow.to_yaml()

        # 6. Generate visualization JSON
        metaflow_json = metaflow.to_visualization_json()

        # 7. Save MetaFlow
        self.storage.save_learning_metaflow(user_id, session_id, metaflow_yaml)

        logger.info(f"Generated MetaFlow with {len(metaflow.nodes)} nodes for session {session_id}")

        return {
            "success": True,
            "session_id": session_id,
            "metaflow_yaml": metaflow_yaml,
            "metaflow_json": metaflow_json,
            "nodes_count": len(metaflow.nodes)
        }

    def get_session_status(self, user_id: int, session_id: str) -> Optional[Dict]:
        """Get learning session status and metadata

        Args:
            user_id: User ID
            session_id: Recording session ID

        Returns:
            Session metadata dict or None if not found
        """
        return self.storage.get_learning_session(user_id, session_id)

    def list_sessions(self, user_id: int) -> List[Dict]:
        """List all learning sessions for a user

        Args:
            user_id: User ID

        Returns:
            List of session metadata dicts
        """
        return self.storage.list_learning_sessions(user_id)

    def delete_session(self, user_id: int, session_id: str) -> bool:
        """Delete a learning session

        Args:
            user_id: User ID
            session_id: Recording session ID

        Returns:
            True if deleted, False if not found
        """
        return self.storage.delete_learning_session(user_id, session_id)


# Global instance
learning_service = LearningService()
