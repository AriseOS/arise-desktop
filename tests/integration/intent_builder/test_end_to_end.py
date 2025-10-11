"""
End-to-End Integration Test: User Operations → Workflow

Complete pipeline test:
1. Learning Phase: User Operations → Intent Graph
2. Generation Phase: Intent Graph + Query → MetaFlow → Workflow
"""
import json
import logging
import os
from pathlib import Path

import pytest

from src.intent_builder.extractors.intent_extractor import IntentExtractor
from src.intent_builder.core.intent_memory_graph import IntentMemoryGraph
from src.intent_builder.storage.in_memory_storage import InMemoryIntentStorage
from src.intent_builder.generators.metaflow_generator import MetaFlowGenerator
from src.intent_builder.generators.workflow_generator import WorkflowGenerator
from src.common.llm import AnthropicProvider

logging.basicConfig(level=logging.INFO, format='%(message)s', force=True)
logger = logging.getLogger(__name__)


class TestEndToEnd:
    """End-to-End Integration Test"""

    @pytest.fixture
    def test_data_dir(self):
        """Get test data directory"""
        return Path(__file__).parent.parent.parent / "test_data" / "coffee_allegro"

    @pytest.fixture
    def user_operations_json(self, test_data_dir):
        """Load User Operations JSON"""
        json_path = test_data_dir / "fixtures" / "user_operations.json"
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @pytest.fixture
    def output_dir(self, test_data_dir):
        """Get output directory"""
        output_path = test_data_dir / "output"
        output_path.mkdir(exist_ok=True)
        return output_path

    @pytest.mark.asyncio
    async def test_end_to_end_pipeline(self, user_operations_json, output_dir, test_data_dir):
        """Complete pipeline: User Operations → Intent Graph → MetaFlow → Workflow"""

        logger.info("\n" + "="*80)
        logger.info("End-to-End Test: User Operations → Intent Graph → MetaFlow → Workflow")
        logger.info("="*80 + "\n")

        # ===== Phase 1: Learning (User Operations → Intent Graph) =====
        logger.info("Phase 1: Learning - User Operations → Intent Graph")
        logger.info("-"*80)

        cached_graph_path = output_dir / "intent_graph.json"

        if cached_graph_path.exists():
            logger.info("Loading cached Intent Graph...")
            storage = InMemoryIntentStorage()
            storage.load(str(cached_graph_path))
            graph = IntentMemoryGraph(storage)
            stats = graph.get_stats()
            logger.info(f"✓ Loaded {stats['num_intents']} intents, {stats['num_edges']} edges\n")
        else:
            # Extract intents
            cached_intents_path = test_data_dir / "expected" / "intents.json"

            if cached_intents_path.exists():
                logger.info("Loading cached intents...")
                with open(cached_intents_path, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                from src.intent_builder.core.intent import Intent
                intents = [Intent.from_dict(d) for d in cached_data["intents"]]
                logger.info(f"✓ Loaded {len(intents)} intents\n")
            else:
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    pytest.skip("ANTHROPIC_API_KEY not set and no cached data")

                logger.info("Extracting intents from User Operations...")
                llm_provider = AnthropicProvider()
                extractor = IntentExtractor(llm_provider=llm_provider)
                intents = await extractor.extract_intents(
                    user_operations_json["operations"],
                    task_description="Collect coffee product prices from Allegro",
                    source_session_id="session_demo_001"
                )
                logger.info(f"✓ Extracted {len(intents)} intents\n")

            # Build graph
            logger.info("Building Intent Memory Graph...")
            storage = InMemoryIntentStorage()
            graph = IntentMemoryGraph(storage)

            for intent in intents:
                graph.add_intent(intent)

            for i in range(len(intents) - 1):
                graph.add_edge(intents[i].id, intents[i + 1].id)

            logger.info(f"✓ Built graph with {len(intents)} intents\n")

            storage.save(str(cached_graph_path))
            logger.info(f"✓ Saved graph to {cached_graph_path}\n")

        # ===== Phase 2: Generation (Intent Graph → MetaFlow → Workflow) =====
        logger.info("Phase 2: Generation - Intent Graph → MetaFlow → Workflow")
        logger.info("-"*80)

        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.info("⚠️  ANTHROPIC_API_KEY not set, skipping generation phase")
            return

        # Step 1: Generate MetaFlow
        logger.info("Step 1: Generating MetaFlow from Intent Graph...")

        task_description = """User wants to collect coffee product information from Allegro.
        Navigate to homepage, enter coffee category, extract product list, 
        then for each product extract title, price and sales count."""

        user_query = "Collect all coffee products from first page with title, price and sales"

        metaflow_generator = MetaFlowGenerator(llm_provider=AnthropicProvider())
        metaflow = await metaflow_generator.generate(
            graph=graph,
            task_description=task_description,
            user_query=user_query
        )

        logger.info(f"✓ Generated MetaFlow with {len(metaflow.nodes)} nodes\n")

        metaflow_file = output_dir / "metaflow.yaml"
        metaflow.to_yaml_file(str(metaflow_file))
        logger.info(f"✓ Saved MetaFlow to {metaflow_file}\n")

        # Step 2: Generate Workflow
        logger.info("Step 2: Generating Workflow from MetaFlow...")

        workflow_generator = WorkflowGenerator(llm_provider=AnthropicProvider())
        workflow_yaml = await workflow_generator.generate(metaflow)

        logger.info(f"✓ Generated Workflow YAML ({len(workflow_yaml)} chars)\n")

        workflow_file = output_dir / "workflow.yaml"
        with open(workflow_file, 'w', encoding='utf-8') as f:
            f.write(workflow_yaml)

        logger.info(f"✓ Saved Workflow to {workflow_file}\n")

        # ===== Verification =====
        logger.info("="*80)
        logger.info("✅ End-to-End Pipeline Completed Successfully!")
        logger.info("="*80)
        logger.info(f"Outputs:")
        logger.info(f"  - Intent Graph: {cached_graph_path}")
        logger.info(f"  - MetaFlow:     {metaflow_file}")
        logger.info(f"  - Workflow:     {workflow_file}")
        logger.info("="*80 + "\n")

        # Assertions
        assert workflow_yaml is not None
        assert len(workflow_yaml) > 0
        assert "workflow:" in workflow_yaml or "name:" in workflow_yaml


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
