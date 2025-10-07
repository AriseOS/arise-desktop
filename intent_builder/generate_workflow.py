#!/usr/bin/env python
"""
Simple script to generate workflow from MetaFlow YAML file

Usage:
    PYTHONPATH=. python intent_builder/generate_workflow.py <metaflow_yaml_file> [output_file]

Example:
    PYTHONPATH=. python intent_builder/generate_workflow.py \
        docs/intent_builder/examples/coffee_collection_metaflow.yaml \
        output_workflow.yaml
"""
import asyncio
import logging
import sys
from pathlib import Path

from intent_builder.core.metaflow import MetaFlow
from intent_builder.generators.workflow_generator import WorkflowGenerator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python generate_workflow.py <metaflow_yaml_file> [output_file]")
        print("\nExample:")
        print("  PYTHONPATH=. python intent_builder/generate_workflow.py \\")
        print("      docs/intent_builder/examples/coffee_collection_metaflow.yaml \\")
        print("      output_workflow.yaml")
        sys.exit(1)

    # Get input file
    metaflow_file = Path(sys.argv[1])
    if not metaflow_file.exists():
        logger.error(f"MetaFlow file not found: {metaflow_file}")
        sys.exit(1)

    # Get output file (optional)
    if len(sys.argv) >= 3:
        output_file = Path(sys.argv[2])
    else:
        output_file = Path("output_workflow.yaml")

    logger.info(f"Loading MetaFlow from: {metaflow_file}")
    metaflow = MetaFlow.from_yaml_file(str(metaflow_file))

    logger.info(f"Task: {metaflow.task_description}")
    logger.info(f"Nodes: {len(metaflow.nodes)}")

    # Generate workflow
    generator = WorkflowGenerator()

    logger.info("Starting workflow generation...")
    try:
        workflow_yaml = await generator.generate(metaflow)

        logger.info("Generation successful!")
        logger.info("=" * 80)
        logger.info("Generated Workflow:")
        logger.info("=" * 80)
        print(workflow_yaml)
        logger.info("=" * 80)

        # Save to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(workflow_yaml)

        logger.info(f"Saved to: {output_file}")

    except Exception as e:
        logger.error(f"Generation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
