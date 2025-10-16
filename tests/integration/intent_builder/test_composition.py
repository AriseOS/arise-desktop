"""
Workflow Composition Test: Natural Language → Workflow

Tests Intent reuse and combination capabilities by generating new workflows
from natural language descriptions using previously stored Intents.

Usage:
    # Test cross-market product selection workflow (default)
    python test_composition.py

    # Test different composition scenarios
    SCENARIO=cross_platform_comparison python test_composition.py
    SCENARIO=price_analysis python test_composition.py
"""
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.intent_builder.core.intent_memory_graph import IntentMemoryGraph
from src.intent_builder.storage.in_memory_storage import InMemoryIntentStorage
from src.intent_builder.generators.metaflow_generator import MetaFlowGenerator
from src.intent_builder.generators.workflow_generator import WorkflowGenerator
from src.common.llm import AnthropicProvider

logging.basicConfig(level=logging.INFO, format='%(message)s', force=True)
logger = logging.getLogger(__name__)

# ===== Configuration: Change this to test different composition scenarios =====
SCENARIO = os.environ.get("SCENARIO", "cross_market_product_selection")
# ===================================================================

# Test scenarios configuration
SCENARIOS = {
    "cross_market_product_selection": {
        "description": "Cross-market product selection insights for e-commerce sourcing decisions",
        "task_description": (
            "Analyze coffee product opportunities by comparing Poland (Allegro) "
            "and US (Amazon) markets to identify profitable sourcing opportunities"
        ),
        "user_query": (
            "I want to identify which coffee products are worth sourcing for my e-commerce business. "
            "Compare the Poland market (Allegro) and US market (Amazon), and analyze: "
            "1) Which products are validated in both markets (safe picks for sourcing) "
            "2) Which products are hot in the US but have low competition in Poland (market opportunities) "
            "3) What are the consumer preference differences between these two markets "
            "Give me actionable sourcing recommendations with specific products and reasoning."
        ),
        "required_intents": ["allegro", "amazon"],
        "expected_new_intents": ["market_analysis", "sourcing_recommendation"]
    },
    "cross_platform_comparison": {
        "description": "Generate comparison report between Allegro and Amazon coffee products",
        "task_description": "Create a cross-platform coffee product comparison report by combining data from Allegro and Amazon",
        "user_query": "Generate a comparison report showing coffee products from both Allegro and Amazon with price and ratings comparison",
        "required_intents": ["allegro", "amazon"],
        "expected_new_intents": ["data_comparison", "report_generation"]
    },
    "price_analysis": {
        "description": "Analyze price trends across multiple coffee products",
        "task_description": "Analyze coffee product prices across different platforms and identify best value options",
        "user_query": "Find the best value coffee products by comparing prices and features across Allegro and Amazon",
        "required_intents": ["allegro", "amazon"],
        "expected_new_intents": ["price_analysis", "value_ranking"]
    }
}


class TestWorkflowComposition:
    """Test Workflow Composition: Natural Language → Combined Workflow"""

    def __init__(self):
        self.test_data_dir = Path(__file__).parent.parent.parent / "test_data"
        self.scenario_config = SCENARIOS[SCENARIO]
        self.output_dir = self.test_data_dir / "composition" / SCENARIO
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_intent_graph(self, platform_name):
        """Load stored Intent Graph from previous learning phases"""
        graph_path = self.test_data_dir / f"coffee_{platform_name}" / "output" / "intent_graph.json"

        if not graph_path.exists():
            raise FileNotFoundError(f"Intent Graph not found for {platform_name}: {graph_path}")

        logger.info(f"Loading Intent Graph for {platform_name}...")
        storage = InMemoryIntentStorage()
        storage.load(str(graph_path))
        graph = IntentMemoryGraph(storage)
        stats = graph.get_stats()
        logger.info(f"✓ Loaded {stats['num_intents']} intents, {stats['num_edges']} edges from {platform_name}")

        return graph

    def combine_intent_graphs(self, graphs):
        """Combine multiple Intent Graphs into one unified graph"""
        logger.info("Combining Intent Graphs from multiple sources...")

        # Create a new unified storage and graph
        unified_storage = InMemoryIntentStorage()
        unified_graph = IntentMemoryGraph(unified_storage)

        # Track intent IDs to avoid conflicts
        all_intents = []
        intent_id_mapping = {}

        for source_name, graph in graphs.items():
            intents = graph.get_all_intents()
            logger.info(f"Adding {len(intents)} intents from {source_name}")

            for intent in intents:
                # Create new ID to avoid conflicts
                old_id = intent.id
                new_id = f"{source_name}_{old_id}"

                # Store mapping for potential reference updates
                intent_id_mapping[f"{source_name}:{old_id}"] = new_id

                # Update intent ID and add to unified graph
                intent.id = new_id
                intent.description = f"[{source_name}] {intent.description}"
                all_intents.append(intent)

        # Add all intents to unified graph
        for intent in all_intents:
            unified_graph.add_intent(intent)

        # Create edges within each platform (preserve internal connections)
        for source_name, graph in graphs.items():
            intents = graph.get_all_intents()
            for i in range(len(intents) - 1):
                source_id = f"{source_name}_{intents[i].id}"
                target_id = f"{source_name}_{intents[i + 1].id}"
                unified_graph.add_edge(source_id, target_id)

        stats = unified_graph.get_stats()
        logger.info(f"✓ Created unified graph with {stats['num_intents']} intents, {stats['num_edges']} edges")

        return unified_graph

    async def generate_composed_workflow(self, unified_graph):
        """Generate a new workflow from combined Intents using natural language"""
        task_description = self.scenario_config["task_description"]
        user_query = self.scenario_config["user_query"]

        logger.info("\n" + "="*80)
        logger.info(f"Workflow Composition Test: {SCENARIO}")
        logger.info(f"Description: {self.scenario_config['description']}")
        logger.info("="*80 + "\n")

        logger.info("Phase 1: Generating MetaFlow from combined Intents")
        logger.info("-"*80)
        logger.info(f"Task Description: {task_description}")
        logger.info(f"User Query: {user_query}\n")

        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.error("⚠️ ANTHROPIC_API_KEY not set, cannot generate workflow")
            return None, None

        # Generate MetaFlow
        metaflow_generator = MetaFlowGenerator(llm_provider=AnthropicProvider())
        metaflow = await metaflow_generator.generate(
            graph=unified_graph,
            task_description=task_description,
            user_query=user_query
        )

        logger.info(f"✓ Generated MetaFlow with {len(metaflow.nodes)} nodes\n")

        # Save MetaFlow
        metaflow_file = self.output_dir / "metaflow.yaml"
        metaflow.to_yaml_file(str(metaflow_file))
        logger.info(f"✓ Saved MetaFlow to {metaflow_file}\n")

        # Generate Workflow
        logger.info("Phase 2: Generating Workflow from MetaFlow")
        logger.info("-"*80)

        workflow_generator = WorkflowGenerator(llm_provider=AnthropicProvider())
        workflow_yaml = await workflow_generator.generate(metaflow)

        logger.info(f"✓ Generated Workflow YAML ({len(workflow_yaml)} chars)\n")

        # Save Workflow
        workflow_file = self.output_dir / "workflow.yaml"
        with open(workflow_file, 'w', encoding='utf-8') as f:
            f.write(workflow_yaml)

        logger.info(f"✓ Saved Workflow to {workflow_file}\n")

        return metaflow, workflow_yaml

    def analyze_composition_results(self, unified_graph, metaflow, workflow_yaml):
        """Analyze the composition results and report findings"""
        logger.info("Phase 3: Composition Analysis")
        logger.info("-"*80)

        # Get unified graph stats
        graph_stats = unified_graph.get_stats()
        logger.info(f"Unified Intent Graph:")
        logger.info(f"  - Total Intents: {graph_stats['num_intents']}")
        logger.info(f"  - Total Edges: {graph_stats['num_edges']}")

        # Analyze MetaFlow nodes
        if metaflow:
            logger.info(f"Generated MetaFlow:")
            logger.info(f"  - Total Nodes: {len(metaflow.nodes)}")

            # Categorize nodes by type (if available)
            node_types = {}
            for node in metaflow.nodes:
                node_type = getattr(node, 'type', 'unknown')
                node_types[node_type] = node_types.get(node_type, 0) + 1

            for node_type, count in node_types.items():
                logger.info(f"  - {node_type} nodes: {count}")

        # Check workflow content
        if workflow_yaml:
            workflow_lines = workflow_yaml.split('\n')
            non_empty_lines = [line for line in workflow_lines if line.strip()]
            logger.info(f"Generated Workflow:")
            logger.info(f"  - Total lines: {len(workflow_lines)}")
            logger.info(f"  - Non-empty lines: {len(non_empty_lines)}")

            # Look for key workflow elements
            key_elements = ['steps:', 'name:', 'description:', 'tools:']
            for element in key_elements:
                if element in workflow_yaml:
                    logger.info(f"  - Contains {element}: ✓")

        # Save analysis results
        analysis = {
            "scenario": SCENARIO,
            "description": self.scenario_config["description"],
            "unified_graph_stats": graph_stats,
            "metaflow_nodes": len(metaflow.nodes) if metaflow else 0,
            "workflow_lines": len(workflow_yaml.split('\n')) if workflow_yaml else 0
        }

        analysis_file = self.output_dir / "analysis.json"
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2)

        logger.info(f"\n✓ Analysis saved to {analysis_file}")

    async def run_composition_test(self):
        """Run the complete workflow composition test"""
        try:
            # Load required Intent Graphs
            required_platforms = self.scenario_config["required_intents"]
            graphs = {}

            for platform in required_platforms:
                graphs[platform] = self.load_intent_graph(platform)

            # Combine Intent Graphs
            unified_graph = self.combine_intent_graphs(graphs)

            # Generate composed workflow
            metaflow, workflow_yaml = await self.generate_composed_workflow(unified_graph)

            # Analyze results
            self.analyze_composition_results(unified_graph, metaflow, workflow_yaml)

            logger.info("\n" + "="*80)
            logger.info("✅ Workflow Composition Test Completed Successfully!")
            logger.info("="*80)
            logger.info(f"Outputs:")
            logger.info(f"  - MetaFlow:     {self.output_dir / 'metaflow.yaml'}")
            logger.info(f"  - Workflow:     {self.output_dir / 'workflow.yaml'}")
            logger.info(f"  - Analysis:     {self.output_dir / 'analysis.json'}")
            logger.info("="*80 + "\n")

            return True

        except Exception as e:
            logger.error(f"❌ Workflow Composition Test Failed: {e}")
            return False


async def main():
    """Main execution function"""
    if SCENARIO not in SCENARIOS:
        logger.error(f"Unknown scenario: {SCENARIO}")
        logger.info(f"Available scenarios: {list(SCENARIOS.keys())}")
        return

    logger.info("Workflow Composition Test")
    logger.info(f"Scenario: {SCENARIO}")
    logger.info(f"Description: {SCENARIOS[SCENARIO]['description']}")

    test = TestWorkflowComposition()
    success = await test.run_composition_test()

    if success:
        logger.info("🎉 Composition test completed successfully!")
    else:
        logger.error("💥 Composition test failed!")


if __name__ == "__main__":
    import asyncio

    # Run the test
    asyncio.run(main())