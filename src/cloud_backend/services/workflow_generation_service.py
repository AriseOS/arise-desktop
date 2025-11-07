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
    
    async def generate_workflow_from_operations(
        self,
        operations: List[Dict],
        task_description: Optional[str] = None,
        user_query: Optional[str] = None
    ) -> Dict[str, str]:
        """
        从 operations 生成 Workflow（完整流程）
        
        Args:
            operations: 用户操作列表
            task_description: 任务描述（可选，从 operations 推断）
            user_query: 用户查询（可选，默认等于 task_description）
            
        Returns:
            {
                "workflow_yaml": "...",
                "metaflow_yaml": "...",
                "intent_graph_json": "...",
                "workflow_name": "..."
            }
        """
        logger.info(f"🚀 Starting workflow generation from {len(operations)} operations")
        
        # 1. 推断 task_description（如果没有提供）
        if not task_description:
            task_description = self._infer_task_description(operations)
            logger.info(f"📝 Inferred task: {task_description}")
        
        # 2. user_query 默认等于 task_description
        if not user_query:
            user_query = task_description
        
        # 3. Intent Extraction
        logger.info("1️⃣  Extracting intents...")
        intents = await self.intent_extractor.extract_intents(
            operations=operations,
            task_description=task_description,
            source_session_id="cloud-backend"
        )
        logger.info(f"   ✅ Extracted {len(intents)} intents")
        
        # 4. Build Intent Memory Graph
        logger.info("2️⃣  Building Intent Memory Graph...")
        storage = InMemoryIntentStorage()
        graph = IntentMemoryGraph(storage=storage)
        for intent in intents:
            graph.add_intent(intent)
        
        # 自动连接（基于依赖关系）
        for i in range(len(intents) - 1):
            graph.add_edge(intents[i].id, intents[i + 1].id)
        
        logger.info(f"   ✅ Graph built: {len(graph.get_all_intents())} nodes, {len(graph.get_edges())} edges")
        
        # 5. MetaFlow Generation
        logger.info("3️⃣  Generating MetaFlow...")
        metaflow = await self.metaflow_generator.generate(
            graph=graph,
            task_description=task_description,
            user_query=user_query
        )
        logger.info(f"   ✅ MetaFlow generated: {len(metaflow.nodes)} nodes")
        
        # 6. Workflow Generation
        logger.info("4️⃣  Generating Workflow...")
        workflow_yaml = await self.workflow_generator.generate(metaflow)
        logger.info(f"   ✅ Workflow generated ({len(workflow_yaml)} chars)")
        
        # 7. 生成 workflow_name
        workflow_name = self._generate_workflow_name(workflow_yaml, task_description)
        
        # 8. Serialize intermediate artifacts
        metaflow_yaml = metaflow.to_yaml()

        # Serialize intent graph manually (IntentMemoryGraph doesn't have to_json)
        import json
        intent_graph_data = {
            "intents": {
                intent.id: intent.to_dict()
                for intent in graph.get_all_intents()
            },
            "edges": graph.get_edges(),
            "metadata": {
                "created_at": graph.get_metadata()["created_at"].isoformat(),
                "last_updated": graph.get_metadata()["last_updated"].isoformat(),
                "version": "2.0"
            },
            "stats": graph.get_stats()
        }
        intent_graph_json = json.dumps(intent_graph_data, ensure_ascii=False, indent=2)

        logger.info(f"✅ Workflow generation complete: {workflow_name}")

        return {
            "workflow_yaml": workflow_yaml,
            "metaflow_yaml": metaflow_yaml,
            "intent_graph_json": intent_graph_json,
            "workflow_name": workflow_name
        }
    
    def _infer_task_description(self, operations: List[Dict]) -> str:
        """
        从 operations 推断任务描述
        
        简单策略：提取第一个 URL 的域名
        """
        for op in operations:
            if op.get("type") == "navigate" and op.get("url"):
                url = op["url"]
                # 提取域名
                import re
                match = re.search(r'https?://([^/]+)', url)
                if match:
                    domain = match.group(1)
                    return f"从 {domain} 抓取数据"
        
        return "网页数据抓取任务"
    
    def _generate_workflow_name(self, workflow_yaml: str, task_description: str) -> str:
        """
        从 workflow YAML 生成名称
        
        策略：
        1. 提取 workflow.yaml 中的 name 字段
        2. 如果没有，基于 task_description 生成
        """
        try:
            workflow_dict = yaml.safe_load(workflow_yaml)
            if "name" in workflow_dict:
                return workflow_dict["name"]
        except:
            pass
        
        # 基于 task_description 生成（简化版）
        # 移除特殊字符，用短横线连接
        import re
        name = re.sub(r'[^\w\s-]', '', task_description)
        name = re.sub(r'[-\s]+', '-', name).strip('-')
        return name[:50]  # 限制长度
