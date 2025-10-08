"""
Test workflow generator with coffee collection example
"""
import asyncio
import logging
from pathlib import Path

from intent_builder.core.metaflow import MetaFlow
from intent_builder.generators.workflow_generator import WorkflowGenerator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_coffee_collection():
    """Test workflow generation from coffee collection MetaFlow"""

    # Load MetaFlow from example file
    example_file = Path(__file__).parent.parent.parent / "docs" / "intent_builder" / "examples" / "coffee_collection_metaflow.yaml"

    logger.info(f"Loading MetaFlow from: {example_file}")
    metaflow = MetaFlow.from_yaml_file(str(example_file))

    logger.info(f"Task: {metaflow.task_description}")
    logger.info(f"Nodes: {len(metaflow.nodes)}")

    # Generate workflow
    generator = WorkflowGenerator()

    logger.info("Starting workflow generation...")
    workflow_yaml = await generator.generate(metaflow)

    logger.info("Generation successful!")
    logger.info("=" * 80)
    logger.info("Generated Workflow:")
    logger.info("=" * 80)
    print(workflow_yaml)
    logger.info("=" * 80)

    # Save to file
    output_file = Path(__file__).parent / "output_coffee_workflow.yaml"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(workflow_yaml)

    logger.info(f"Saved to: {output_file}")


async def test_generator_components():
    """Test individual generator components"""
    from intent_builder.generators.prompt_builder import PromptBuilder
    from intent_builder.generators.llm_service import LLMService
    from intent_builder.validators.yaml_validator import WorkflowYAMLValidator

    # Test PromptBuilder
    logger.info("Testing PromptBuilder...")
    builder = PromptBuilder()
    test_metaflow = """
version: "1.0"
task_description: "Test task"
nodes:
  - id: node_1
    intent_id: "intent_1"
    intent_name: "TestIntent"
    intent_description: "Test intent"
    operations:
      - type: navigate
        url: "https://example.com"
"""
    prompt = builder.build(test_metaflow)
    logger.info(f"Generated prompt length: {len(prompt)} chars")
    assert len(prompt) > 1000
    assert "System Role" in prompt
    assert "BaseAgent Workflow Specification" in prompt
    logger.info("PromptBuilder test passed")

    # Test LLMService initialization
    logger.info("Testing LLMService...")
    llm_service = LLMService(provider="anthropic")
    logger.info(f"LLM service initialized: {llm_service.model}")
    logger.info("LLMService test passed")

    # Test WorkflowYAMLValidator
    logger.info("Testing WorkflowYAMLValidator...")
    validator = WorkflowYAMLValidator()

    # Test invalid YAML
    is_valid, error = validator.validate("invalid: yaml: :")
    assert not is_valid
    logger.info(f"Invalid YAML test passed: {error}")

    # Test valid workflow
    valid_workflow = """
apiVersion: "agentcrafter.io/v1"
kind: "Workflow"
metadata:
  name: "test-workflow"
  version: "1.0.0"
steps:
  - id: "step1"
    name: "Test Step"
    agent_type: "variable"
    agent_instruction: "Test"
"""
    is_valid, error = validator.validate(valid_workflow)
    assert is_valid
    logger.info("Valid workflow test passed")

    logger.info("All component tests passed!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "components":
        asyncio.run(test_generator_components())
    else:
        asyncio.run(test_coffee_collection())
