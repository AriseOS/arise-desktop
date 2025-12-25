"""
Workflow Generation Service - 集成 Intent Builder

完整流程：
1. 读取 operations.json
2. Intent Extraction (LLM)
3. MetaFlow Generation (LLM)
4. Workflow Generation (LLM)
5. 保存所有中间产物
"""

import json
import logging
import re
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
import yaml

# 添加项目根目录到 Python 路径
# 当前文件: src/cloud-backend/services/workflow_generation_service.py
# 需要到达: ami/ (项目根目录)
project_root = Path(__file__).parent.parent.parent.parent  # 向上4层
sys.path.insert(0, str(project_root))

from src.cloud_backend.intent_builder.extractors.intent_extractor import IntentExtractor
from src.cloud_backend.intent_builder.generators.metaflow_generator import MetaFlowGenerator
from src.cloud_backend.intent_builder.generators.workflow_generator import WorkflowGenerator
from src.cloud_backend.intent_builder.core.intent_memory_graph import IntentMemoryGraph
from src.cloud_backend.intent_builder.storage.in_memory_storage import InMemoryIntentStorage
from src.common.llm import AnthropicProvider, OpenAIProvider

logger = logging.getLogger(__name__)

class WorkflowGenerationService:
    """Workflow 生成服务（整合 Intent Builder）

    Supports API Proxy mode:
    - When user_api_key is provided, routes all LLM calls through API Proxy
    - API Proxy URL is read from Cloud Backend config
    """

    def __init__(self, llm_provider_name: str = "anthropic", config_service=None):
        """
        初始化服务

        Args:
            llm_provider_name: LLM 提供商 ("anthropic" 或 "openai")
            config_service: CloudConfigService instance for reading config
        """
        self.llm_provider_name = llm_provider_name
        self.config_service = config_service

        # Store config for API Proxy
        if config_service:
            self.use_proxy = config_service.get("llm.use_proxy", False)
            self.proxy_base_url = config_service.get("llm.proxy_url", "http://localhost:8080")
        else:
            self.use_proxy = False
            self.proxy_base_url = "http://localhost:8080"

        # No default LLM provider - always require user_api_key
        self.default_llm = None

        logger.info(f"✅ Workflow Generation Service initialized")
        logger.info(f"   Provider: {llm_provider_name}")
        logger.info(f"   API Proxy: always enabled (user API keys required)")
        logger.info(f"   Proxy URL: {self.proxy_base_url}")

    def _create_llm_provider(self, user_api_key: Optional[str] = None):
        """
        Create LLM provider instance

        Args:
            user_api_key: User's Ami API key (required)

        Returns:
            LLM provider instance configured for API Proxy

        Raises:
            ValueError: If user_api_key is not provided
        """
        # Always require user_api_key
        if not user_api_key:
            raise ValueError("user_api_key is required - all LLM calls must use user's API key through API Proxy")

        logger.info(f"Creating LLM provider for API Proxy (user_api_key: {user_api_key[:10]}...)")

        if self.llm_provider_name == "anthropic":
            return AnthropicProvider(
                api_key=user_api_key,
                base_url=self.proxy_base_url
            )
        elif self.llm_provider_name == "openai":
            return OpenAIProvider(
                api_key=user_api_key,
                base_url=self.proxy_base_url
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider_name}")
    
    async def add_intents_to_graph(
        self,
        operations: List[Dict],
        graph_filepath: str,
        task_description: Optional[str] = None,
        user_api_key: Optional[str] = None
    ) -> int:
        """
        Extract intents from operations and add to existing Intent Memory Graph

        Args:
            operations: User operation list
            graph_filepath: Path to existing intent_graph.json file
            task_description: User's description of what they did (optional, can be empty)
            user_api_key: User's Ami API key (for API Proxy)

        Returns:
            Number of new intents added
        """
        logger.info(f"🚀 Adding intents from {len(operations)} operations to graph")

        if task_description:
            logger.info(f"📝 User task description: {task_description}")
        else:
            logger.info(f"📝 No task description provided")

        # Create LLM provider with user_api_key if provided
        llm = self._create_llm_provider(user_api_key)
        intent_extractor = IntentExtractor(llm_provider=llm)

        # Intent Extraction (with user's task_description if provided)
        logger.info("1️⃣  Extracting intents...")
        try:
            new_intents = await intent_extractor.extract_intents(
                operations=operations,
                task_description=task_description or "",  # Empty string if not provided
                source_session_id="cloud-backend"
            )
            logger.info(f"   ✅ Extracted {len(new_intents)} new intents")
        except Exception as e:
            logger.error(f"❌ Failed to extract intents: {e}", exc_info=True)
            # If intent extraction fails, we can't really proceed with adding to graph
            # But we should not crash the whole background process if possible
            return 0

        # 3. Load existing Intent Graph or create new one
        from pathlib import Path
        storage = InMemoryIntentStorage()

        if Path(graph_filepath).exists():
            logger.info(f"2️⃣  Loading existing graph from {graph_filepath}")
            storage.load(graph_filepath)
            existing_count = len(storage.get_all_intents())
            logger.info(f"   ✅ Loaded {existing_count} existing intents")
        else:
            logger.info(f"2️⃣  Creating new graph (file doesn't exist yet)")
            existing_count = 0

        graph = IntentMemoryGraph(storage=storage)

        # 4. Add new intents to graph
        logger.info("3️⃣  Adding new intents to graph...")
        for intent in new_intents:
            graph.add_intent(intent)

        # Auto-connect new intents based on sequential order
        for i in range(len(new_intents) - 1):
            graph.add_edge(new_intents[i].id, new_intents[i + 1].id)

        # 5. Save updated graph
        logger.info(f"4️⃣  Saving updated graph to {graph_filepath}")
        storage.save(graph_filepath)

        total_intents = len(graph.get_all_intents())
        logger.info(f"   ✅ Graph updated: {total_intents} total intents ({len(new_intents)} new)")

        return len(new_intents)

    async def generate_metaflow_from_graph_file(
        self,
        graph_filepath: str,
        task_description: str,
        user_query: Optional[str] = None,
        user_api_key: Optional[str] = None
    ) -> str:
        """
        Generate MetaFlow from Intent Graph file (Step 2: Intent Graph + task_description → MetaFlow)

        This will filter relevant intents from the graph based on task_description.

        Args:
            graph_filepath: Path to intent_graph.json file
            task_description: User's task description
            user_query: Optional user query (defaults to task_description)
            user_api_key: User's Ami API key (for API Proxy)

        Returns:
            metaflow_yaml: MetaFlow YAML string
        """
        logger.info(f"🚀 Generating MetaFlow from Intent Graph")
        logger.info(f"=" * 80)
        logger.info(f"📝 Task Description (what user did):")
        logger.info(f"   {task_description}")
        if user_query:
            logger.info(f"🎯 User Query (what user wants to do):")
            logger.info(f"   {user_query}")
        else:
            logger.info(f"⚠️  No user_query provided, using task_description as fallback")
        logger.info(f"=" * 80)

        # 1. Load Intent Memory Graph from file
        from pathlib import Path
        if not Path(graph_filepath).exists():
            raise FileNotFoundError(f"Intent Graph file not found: {graph_filepath}")

        storage = InMemoryIntentStorage()
        storage.load(graph_filepath)

        graph = IntentMemoryGraph(storage=storage)
        logger.info(f"   ✅ Graph loaded: {len(graph.get_all_intents())} intents")

        # 2. Create LLM provider with user_api_key if provided
        llm = self._create_llm_provider(user_api_key)
        metaflow_generator = MetaFlowGenerator(llm_provider=llm)

        # 3. Generate MetaFlow (MetaFlowGenerator will filter relevant intents)
        # IMPORTANT: user_query is what user wants to do (for path selection and loop detection)
        # If not provided, fallback to task_description
        effective_user_query = user_query if user_query else task_description

        logger.info("2️⃣  Generating MetaFlow with LLM...")
        logger.info(f"   → Input: {effective_user_query}")
        metaflow = await metaflow_generator.generate(
            graph=graph,
            task_description=task_description,
            user_query=effective_user_query
        )
        logger.info(f"   ✅ MetaFlow generated: {len(metaflow.nodes)} nodes")

        # 4. Serialize MetaFlow
        metaflow_yaml = metaflow.to_yaml()

        logger.info(f"✅ MetaFlow generation complete")
        return metaflow_yaml

    async def generate_workflow_from_metaflow(
        self,
        metaflow_yaml: str,
        user_api_key: Optional[str] = None
    ) -> str:
        """
        Generate Workflow YAML from MetaFlow (Step 3: MetaFlow → Workflow)

        Args:
            metaflow_yaml: MetaFlow YAML string
            user_api_key: User's Ami API key (for API Proxy)

        Returns:
            workflow_yaml: Workflow YAML string
        """
        logger.info(f"🚀 Generating Workflow from MetaFlow")

        # 1. Parse MetaFlow
        from src.cloud_backend.intent_builder.core.metaflow import MetaFlow
        metaflow = MetaFlow.from_yaml(metaflow_yaml)

        logger.info(f"=" * 80)
        logger.info(f"📋 MetaFlow Information:")
        logger.info(f"   Task: {metaflow.task_description}")
        logger.info(f"   Nodes: {len(metaflow.nodes)}")
        logger.info(f"=" * 80)

        # 2. Create LLM provider with user_api_key if provided
        llm = self._create_llm_provider(user_api_key)
        workflow_generator = WorkflowGenerator(llm_provider=llm)

        # 3. Generate Workflow
        logger.info("4️⃣  Generating Workflow with LLM...")
        workflow_yaml = await workflow_generator.generate(metaflow)
        logger.info(f"   ✅ Workflow generated ({len(workflow_yaml)} chars)")

        logger.info(f"✅ Workflow generation complete")
        return workflow_yaml

    async def generate_metaflow_from_recording(
        self,
        operations: List[Dict],
        task_description: str,
        user_query: Optional[str] = None,
        existing_metaflow_yaml: Optional[str] = None,
        user_api_key: Optional[str] = None
    ) -> str:
        """
        Generate MetaFlow directly from recording operations (without using global Intent Graph)

        This method:
        1. Extracts intents from the recording operations
        2. Creates a temporary Intent Graph with only these intents
        3. Generates MetaFlow from this temporary graph

        Use case: User wants to generate workflow from a specific recording,
        using only the context from that recording (not historical Intent Memory).

        Args:
            operations: List of operations from the recording
            task_description: User's description of what they did
            user_query: User's description of what they want to do (for MetaFlow generation)
            existing_metaflow_yaml: Existing MetaFlow YAML (for in-place modification, not used for now)
            user_api_key: User's Ami API key (for API Proxy)

        Returns:
            metaflow_yaml: MetaFlow YAML string
        """
        logger.info(f"🚀 Generating MetaFlow from recording ({len(operations)} operations)")
        logger.info(f"=" * 80)
        logger.info(f"📝 Task Description (what user did):")
        logger.info(f"   {task_description}")
        if user_query:
            logger.info(f"🎯 User Query (what user wants to do):")
            logger.info(f"   {user_query}")
        else:
            logger.info(f"⚠️  No user_query provided, using task_description as fallback")
        logger.info(f"=" * 80)

        # Create LLM provider with user_api_key if provided
        llm = self._create_llm_provider(user_api_key)
        intent_extractor = IntentExtractor(llm_provider=llm)
        metaflow_generator = MetaFlowGenerator(llm_provider=llm)

        # 1. Extract intents from operations
        logger.info("1️⃣  Extracting intents from recording...")
        intents = await intent_extractor.extract_intents(
            operations=operations,
            task_description=task_description,
            source_session_id="recording-based-generation"
        )
        logger.info(f"   ✅ Extracted {len(intents)} intents")

        # 2. Create temporary Intent Graph with only these intents
        logger.info("2️⃣  Creating temporary Intent Graph...")
        storage = InMemoryIntentStorage()
        graph = IntentMemoryGraph(storage=storage)

        for intent in intents:
            graph.add_intent(intent)

        # Auto-connect intents based on sequential order
        for i in range(len(intents) - 1):
            graph.add_edge(intents[i].id, intents[i + 1].id)

        logger.info(f"   ✅ Temporary graph created: {len(intents)} intents")

        # 3. Generate MetaFlow from temporary graph
        # IMPORTANT: Use user_query if provided (what user wants to do), otherwise fallback to task_description
        effective_user_query = user_query if user_query else task_description

        logger.info("3️⃣  Generating MetaFlow from recording-specific intents with LLM...")
        logger.info(f"   → Input: {effective_user_query}")
        metaflow = await metaflow_generator.generate(
            graph=graph,
            task_description=task_description,
            user_query=effective_user_query
        )
        logger.info(f"   ✅ MetaFlow generated: {len(metaflow.nodes)} nodes")

        # 4. Serialize MetaFlow
        metaflow_yaml = metaflow.to_yaml()

        logger.info(f"✅ MetaFlow generation from recording complete")
        return metaflow_yaml

    async def generate_workflow_from_operations(
        self,
        operations: List[Dict],
        task_description: Optional[str] = None,
        user_query: Optional[str] = None,
        user_api_key: Optional[str] = None
    ) -> Dict[str, str]:
        """High-level helper used by tests: operations → MetaFlow → Workflow.

        Args:
            operations: Recorded browser operations
            task_description: Optional user provided description
            user_query: Optional goal description for MetaFlow generation
            user_api_key: Ami API key (for API Proxy routing)

        Returns:
            Dict containing workflow/metaflow YAML、intent graph JSON、workflow name
        """

        if not operations:
            raise ValueError("Operations list cannot be empty")

        effective_task_description = (task_description or "").strip()
        if not effective_task_description:
            effective_task_description = self._infer_task_description(operations)

        # Generate MetaFlow & Workflow via existing pipeline
        metaflow_yaml = await self.generate_metaflow_from_recording(
            operations=operations,
            task_description=effective_task_description,
            user_query=user_query,
            user_api_key=user_api_key
        )

        workflow_yaml = await self.generate_workflow_from_metaflow(
            metaflow_yaml=metaflow_yaml,
            user_api_key=user_api_key
        )

        workflow_name = self._generate_workflow_name(
            effective_task_description,
            operations
        )

        intent_graph_json = self._build_intent_graph_json(
            operations,
            effective_task_description
        )

        return {
            "success": True,
            "workflow_yaml": workflow_yaml,
            "metaflow_yaml": metaflow_yaml,
            "intent_graph_json": intent_graph_json,
            "workflow_name": workflow_name,
            "task_description": effective_task_description
        }

    def _infer_task_description(self, operations: List[Dict]) -> str:
        """Infer a lightweight task description from operations when user input is absent."""

        host = self._extract_host_from_operations(operations)
        if host:
            return f"Auto workflow for {host}"

        first_type = operations[0].get("type") if operations else "task"
        return f"Auto workflow for {first_type or 'task'}"

    def _extract_host_from_operations(self, operations: List[Dict]) -> Optional[str]:
        """Return the first domain found inside the operations list."""

        for op in operations:
            url = op.get("url")
            if not url and isinstance(op.get("data"), dict):
                url = op["data"].get("url")
            if not url:
                continue
            parsed = urlparse(url)
            host = parsed.netloc or parsed.path
            if host:
                return host.lower()
        return None

    def _generate_workflow_name(self, task_description: str, operations: List[Dict]) -> str:
        """Generate a safe, human friendly workflow name (<=100 chars)."""

        base = (task_description or "").strip()
        if not base:
            base = self._extract_host_from_operations(operations) or "workflow"

        slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", base.lower())
        slug = re.sub(r"-+", "-", slug).strip("-")

        if not slug:
            slug = self._extract_host_from_operations(operations) or f"workflow-{uuid.uuid4().hex[:8]}"

        if len(slug) > 100:
            slug = slug[:100].rstrip("-")

        return slug or f"workflow-{uuid.uuid4().hex[:6]}"

    def _build_intent_graph_json(self, operations: List[Dict], task_description: str) -> str:
        """Create a lightweight graph JSON for downstream visualization/tests."""

        nodes = []
        edges = []

        for idx, op in enumerate(operations):
            node_id = f"op_{idx}"
            element = op.get("element") or {}
            nodes.append({
                "id": node_id,
                "type": op.get("type"),
                "url": op.get("url") or (op.get("data") or {}).get("url"),
                "text": element.get("text") or element.get("textContent"),
                "timestamp": op.get("timestamp")
            })

            if idx > 0:
                edges.append({
                    "source": f"op_{idx - 1}",
                    "target": node_id
                })

        graph_payload = {
            "task_description": task_description,
            "operation_count": len(operations),
            "nodes": nodes,
            "edges": edges
        }

        return json.dumps(graph_payload, ensure_ascii=False)
