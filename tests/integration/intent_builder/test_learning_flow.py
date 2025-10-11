"""
Integration Test: Learning Flow (User Operations → Intent Memory Graph)

Based on: docs/intent_builder/11_implementation_plan.md Phase 4.1

This test demonstrates the complete learning flow:
1. Load User Operations from JSON
2. Extract Intents using IntentExtractor
3. Build IntentMemoryGraph with intents and edges
4. Save graph to JSON file
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    force=True
)

logger = logging.getLogger(__name__)


class TestLearningFlow:
    """Integration test for Learning Flow"""

    @pytest.fixture
    def test_data_dir(self):
        """Get test data directory"""
        return Path(__file__).parent.parent.parent / "test_data" / "coffee_allegro"

    @pytest.fixture
    def user_operations_json(self, test_data_dir):
        """Load User Operations JSON example"""
        json_path = test_data_dir / "fixtures" / "user_operations.json"
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @pytest.fixture
    def output_dir(self, test_data_dir):
        """Get output directory for test results"""
        output_path = test_data_dir / "output"
        output_path.mkdir(exist_ok=True)
        return output_path

    @pytest.mark.asyncio
    async def test_learning_flow(self, user_operations_json, output_dir, test_data_dir):
        """Demo 1: Complete Learning Flow - User Operations → Intent Graph"""

        logger.info("\n" + "="*70)
        logger.info("Demo 1: Learning Flow - User Operations → Intent Memory Graph")
        logger.info("="*70 + "\n")

        # Try to load cached graph first (fastest)
        cached_graph_path = output_dir / "intent_graph.json"

        if cached_graph_path.exists():
            logger.info("Step 1: Loading cached Intent Graph (skipping intent extraction)...")
            storage = InMemoryIntentStorage()
            storage.load(str(cached_graph_path))
            graph = IntentMemoryGraph(storage)

            stats = graph.get_stats()
            logger.info(f"✓ Loaded graph with {stats['num_intents']} intents, {stats['num_edges']} edges\n")

        else:
            # Step 1: Load or extract intents
            cached_intents_path = test_data_dir / "expected" / "intents.json"

            if cached_intents_path.exists():
                # Use cached intents to save time
                logger.info("Step 1: Loading cached intents (to save LLM API time)...")
                with open(cached_intents_path, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)

                from src.intent_builder.core.intent import Intent
                intents = [Intent.from_dict(intent_dict) for intent_dict in cached_data["intents"]]
                logger.info(f"✓ Loaded {len(intents)} cached intents\n")
            else:
                # Extract intents from User Operations (requires API key)
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    pytest.skip("ANTHROPIC_API_KEY not set and no cached data available")

                logger.info("Step 1: Extracting Intents from User Operations...")
                llm_provider = AnthropicProvider()
                extractor = IntentExtractor(llm_provider=llm_provider)

                intents = await extractor.extract_intents(
                    user_operations_json["operations"],
                    task_description="Collect coffee product prices from Allegro",
                    source_session_id="session_demo_001"
                )

                logger.info(f"✓ Extracted {len(intents)} intents\n")

                # Save to expected for future runs
                cached_data = {"intents": [intent.to_dict() for intent in intents]}
                cached_intents_path.parent.mkdir(parents=True, exist_ok=True)
                with open(cached_intents_path, 'w', encoding='utf-8') as f:
                    json.dump(cached_data, f, ensure_ascii=False, indent=2)
                logger.info(f"✓ Saved intents to expected: {cached_intents_path}\n")

            # Step 2: Create IntentMemoryGraph
            logger.info("Step 2: Building Intent Memory Graph...")
            storage = InMemoryIntentStorage()
            graph = IntentMemoryGraph(storage)

            # Step 3: Add intents to graph
            for intent in intents:
                graph.add_intent(intent)

            logger.info(f"✓ Added {len(intents)} intents to graph")

            # Step 4: Add edges (temporal connections between consecutive intents)
            for i in range(len(intents) - 1):
                from_intent = intents[i]
                to_intent = intents[i + 1]
                graph.add_edge(from_intent.id, to_intent.id)

            logger.info(f"✓ Added {len(intents) - 1} edges (temporal connections)\n")

            # Step 5: Display graph structure
            logger.info("Intent Memory Graph Structure:")
            logger.info("-" * 70)
            all_intents = graph.get_all_intents()
            for i, intent in enumerate(all_intents, 1):
                logger.info(f"Intent {i}: {intent.id}")
                logger.info(f"  Description: {intent.description}")
                logger.info(f"  Operations: {len(intent.operations)} steps")

                # Show successors
                successors = graph.get_successors(intent.id)
                if successors:
                    logger.info(f"  → Next: {successors[0].description}")
                logger.info("")

            # Step 6: Save graph to JSON
            storage.save(str(cached_graph_path))

            logger.info("="*70)
            logger.info(f"✓ Intent Memory Graph saved to: {cached_graph_path}")
            logger.info("="*70 + "\n")

            # Verification
            stats = graph.get_stats()
            logger.info("Graph Statistics:")
            logger.info(f"  Total Intents: {stats['num_intents']}")
            logger.info(f"  Total Edges: {stats['num_edges']}")

            metadata = graph.get_metadata()
            logger.info(f"  Created At: {metadata['created_at']}")
            logger.info(f"  Last Updated: {metadata['last_updated']}")
            logger.info("")

            # Assertions
            assert len(graph.get_all_intents()) == len(intents), "All intents should be in graph"
            assert stats['num_edges'] == len(intents) - 1, "Should have N-1 edges for N intents"

            # Verify we can load the graph back
            loaded_storage = InMemoryIntentStorage()
            loaded_storage.load(str(cached_graph_path))
            loaded_graph = IntentMemoryGraph(loaded_storage)

            assert len(loaded_graph.get_all_intents()) == len(intents), "Loaded graph should have same number of intents"
            assert loaded_graph.get_stats()['num_edges'] == stats['num_edges'], "Loaded graph should have same number of edges"

            logger.info("✅ Learning Flow completed successfully!")
            logger.info("="*70 + "\n")

        # ===== Part 2: Generate MetaFlow =====
        logger.info("\n" + "="*70)
        logger.info("Part 2: MetaFlow Generation - Intent Graph → MetaFlow")
        logger.info("="*70 + "\n")

        # Step 7: Generate MetaFlow from Graph
        logger.info("Step 7: Generating MetaFlow from Intent Graph...")

        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.info("⚠️  ANTHROPIC_API_KEY not set, skipping MetaFlow generation")
            return

        metaflow_generator = MetaFlowGenerator(llm_provider=AnthropicProvider())

        # Rich task description based on user's actual needs
        task_description = """User wants to collect coffee product information from Allegro e-commerce platform.
        Specifically:
        - Navigate to Allegro homepage (https://allegro.pl/)
        - Enter the coffee category through menu navigation
        - Extract all product URLs from the first page of coffee category
        - For each coffee product, visit the detail page and extract:
          * Product title (from H1 element)
          * Product price (from price section, format: XX,XX zł)
          * Sales statistics (number of people who bought recently)
        - Store collected data to database for analysis
        The goal is to monitor popular coffee products and their market performance."""

        user_query = "Collect all coffee product information from the first page, including title, price and sales count"

        logger.info(f"  Task: {task_description}")
        logger.info(f"  Query: {user_query}\n")

        metaflow = await metaflow_generator.generate(
            graph=graph,
            task_description=task_description,
            user_query=user_query
        )

        logger.info(f"✓ MetaFlow generated!")
        logger.info(f"  Version: {metaflow.version}")
        logger.info(f"  Nodes: {len(metaflow.nodes)}\n")

        # Step 8: Display MetaFlow structure
        logger.info("MetaFlow Structure:")
        logger.info("-" * 70)
        for i, node in enumerate(metaflow.nodes, 1):
            node_type = getattr(node, 'type', 'regular')
            if node_type == 'loop':
                logger.info(f"Node {i}: [LOOP] {node.description}")
                logger.info(f"  Source: {node.source}")
                logger.info(f"  Item Var: {node.item_var}")
                logger.info(f"  Children: {len(node.children)}")
            else:
                logger.info(f"Node {i}: {node.intent_name}")
                logger.info(f"  Intent ID: {node.intent_id}")
                logger.info(f"  Description: {node.intent_description}")
                if hasattr(node, 'outputs') and node.outputs:
                    logger.info(f"  Outputs: {node.outputs}")
            logger.info("")

        # Step 9: Save MetaFlow to output
        metaflow_file = output_dir / "metaflow.yaml"
        metaflow.to_yaml_file(str(metaflow_file))

        logger.info("="*70)
        logger.info(f"✓ MetaFlow saved to: {metaflow_file}")
        logger.info("="*70 + "\n")

        # Verify MetaFlow
        assert metaflow.version == "1.0"
        assert len(metaflow.nodes) > 0
        logger.info("✅ MetaFlow Generation completed successfully!")
        logger.info("="*70 + "\n")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--log-cli-level=INFO"])
