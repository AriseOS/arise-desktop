"""
Workflow Generation Service - 集成 Intent Builder

完整流程：
1. 读取 operations.json
2. Intent Extraction (LLM)
3. MetaFlow Generation (LLM)
4. Workflow Generation (LLM)
5. 保存所有中间产物
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional
import yaml

# 添加项目根目录到 Python 路径
# 当前文件: src/cloud-backend/services/workflow_generation_service.py
# 需要到达: agentcrafter/ (项目根目录)
project_root = Path(__file__).parent.parent.parent.parent  # 向上4层
sys.path.insert(0, str(project_root))

from src.intent_builder.extractors.intent_extractor import IntentExtractor
from src.intent_builder.generators.metaflow_generator import MetaFlowGenerator
from src.intent_builder.generators.workflow_generator import WorkflowGenerator
from src.intent_builder.core.intent_memory_graph import IntentMemoryGraph
from src.intent_builder.storage.in_memory_storage import InMemoryIntentStorage
from src.common.llm import AnthropicProvider, OpenAIProvider

logger = logging.getLogger(__name__)

class WorkflowGenerationService:
    """Workflow 生成服务（整合 Intent Builder）"""
    
    def __init__(self, llm_provider_name: str = "anthropic"):
        """
        初始化服务
        
        Args:
            llm_provider_name: LLM 提供商 ("anthropic" 或 "openai")
        """
        # 初始化 LLM Provider
        if llm_provider_name == "anthropic":
            self.llm = AnthropicProvider()
        elif llm_provider_name == "openai":
            self.llm = OpenAIProvider()
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider_name}")
        
        # 初始化三个核心组件
        self.intent_extractor = IntentExtractor(llm_provider=self.llm)
        self.metaflow_generator = MetaFlowGenerator(llm_provider=self.llm)
        self.workflow_generator = WorkflowGenerator(llm_provider=self.llm)
        
        logger.info(f"✅ Workflow Generation Service initialized with {llm_provider_name}")
    
    async def add_intents_to_graph(
        self,
        operations: List[Dict],
        graph_filepath: str,
        task_description: Optional[str] = None
    ) -> int:
        """
        Extract intents from operations and add to existing Intent Memory Graph

        Args:
            operations: User operation list
            graph_filepath: Path to existing intent_graph.json file
            task_description: User's description of what they did (optional, can be empty)

        Returns:
            Number of new intents added
        """
        logger.info(f"🚀 Adding intents from {len(operations)} operations to graph")

        if task_description:
            logger.info(f"📝 User task description: {task_description}")
        else:
            logger.info(f"📝 No task description provided")

        # Intent Extraction (with user's task_description if provided)
        logger.info("1️⃣  Extracting intents...")
        new_intents = await self.intent_extractor.extract_intents(
            operations=operations,
            task_description=task_description or "",  # Empty string if not provided
            source_session_id="cloud-backend"
        )
        logger.info(f"   ✅ Extracted {len(new_intents)} new intents")

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
        user_query: Optional[str] = None
    ) -> str:
        """
        Generate MetaFlow from Intent Graph file (Step 2: Intent Graph + task_description → MetaFlow)

        This will filter relevant intents from the graph based on task_description.

        Args:
            graph_filepath: Path to intent_graph.json file
            task_description: User's task description
            user_query: Optional user query (defaults to task_description)

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

        # 2. Generate MetaFlow (MetaFlowGenerator will filter relevant intents)
        # IMPORTANT: user_query is what user wants to do (for path selection and loop detection)
        # If not provided, fallback to task_description
        effective_user_query = user_query if user_query else task_description

        logger.info("2️⃣  Generating MetaFlow with LLM...")
        logger.info(f"   → Input: {effective_user_query}")
        metaflow = await self.metaflow_generator.generate(
            graph=graph,
            task_description=task_description,
            user_query=effective_user_query
        )
        logger.info(f"   ✅ MetaFlow generated: {len(metaflow.nodes)} nodes")

        # 3. Serialize MetaFlow
        metaflow_yaml = metaflow.to_yaml()

        logger.info(f"✅ MetaFlow generation complete")
        return metaflow_yaml

    async def generate_workflow_from_metaflow(
        self,
        metaflow_yaml: str
    ) -> str:
        """
        Generate Workflow YAML from MetaFlow (Step 3: MetaFlow → Workflow)

        Args:
            metaflow_yaml: MetaFlow YAML string

        Returns:
            workflow_yaml: Workflow YAML string
        """
        logger.info(f"🚀 Generating Workflow from MetaFlow")

        # 1. Parse MetaFlow
        from src.intent_builder.core.metaflow import MetaFlow
        metaflow = MetaFlow.from_yaml(metaflow_yaml)

        logger.info(f"=" * 80)
        logger.info(f"📋 MetaFlow Information:")
        logger.info(f"   Task: {metaflow.task_description}")
        logger.info(f"   Nodes: {len(metaflow.nodes)}")
        logger.info(f"=" * 80)

        # 2. Generate Workflow
        logger.info("4️⃣  Generating Workflow with LLM...")
        workflow_yaml = await self.workflow_generator.generate(metaflow)
        logger.info(f"   ✅ Workflow generated ({len(workflow_yaml)} chars)")

        logger.info(f"✅ Workflow generation complete")
        return workflow_yaml

    async def generate_metaflow_from_recording(
        self,
        operations: List[Dict],
        task_description: str,
        user_query: Optional[str] = None
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

        # 1. Extract intents from operations
        logger.info("1️⃣  Extracting intents from recording...")
        intents = await self.intent_extractor.extract_intents(
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
        metaflow = await self.metaflow_generator.generate(
            graph=graph,
            task_description=task_description,
            user_query=effective_user_query
        )
        logger.info(f"   ✅ MetaFlow generated: {len(metaflow.nodes)} nodes")

        # 4. Serialize MetaFlow
        metaflow_yaml = metaflow.to_yaml()

        logger.info(f"✅ MetaFlow generation from recording complete")
        return metaflow_yaml
