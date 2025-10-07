"""
Workflow Generator - Convert MetaFlow to BaseAgent Workflow

Main generator that orchestrates the conversion process:
1. Build prompt from MetaFlow
2. Call LLM to generate workflow YAML
3. Validate and retry if needed
"""
import logging
from typing import Optional
import yaml

from ..core.metaflow import MetaFlow
from .prompt_builder import PromptBuilder
from .llm_service import LLMService
from ..validators.yaml_validator import WorkflowYAMLValidator

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Raised when workflow generation fails"""
    pass


class WorkflowGenerator:
    """Generate BaseAgent Workflow from MetaFlow"""

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        validator: Optional[WorkflowYAMLValidator] = None,
        max_retries: int = 3
    ):
        """
        Initialize WorkflowGenerator

        Args:
            llm_service: LLM service for generating workflow
            prompt_builder: Prompt builder for constructing prompts
            validator: YAML validator for validating generated workflow
            max_retries: Maximum number of retries on failure
        """
        self.llm_service = llm_service or LLMService()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.validator = validator or WorkflowYAMLValidator()
        self.max_retries = max_retries

    async def generate(self, metaflow: MetaFlow) -> str:
        """
        Generate Workflow YAML from MetaFlow

        Args:
            metaflow: MetaFlow object

        Returns:
            workflow_yaml: Valid workflow YAML string

        Raises:
            GenerationError: If generation fails after max retries
        """
        logger.info(f"Starting workflow generation for task: {metaflow.task_description}")

        # Convert MetaFlow to YAML string
        metaflow_yaml = metaflow.to_yaml()

        # Build initial prompt
        prompt = self.prompt_builder.build(metaflow_yaml)

        # Generation loop with retry
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Generation attempt {attempt + 1}/{self.max_retries}")

                # Call LLM to generate workflow
                workflow_yaml = await self.llm_service.generate(prompt)

                # Validate generated YAML
                is_valid, error_message = self.validator.validate(workflow_yaml)

                if is_valid:
                    logger.info("Workflow generation successful")
                    return workflow_yaml
                else:
                    logger.warning(f"Validation failed: {error_message}")

                    # Add error feedback to prompt for retry
                    if attempt < self.max_retries - 1:
                        prompt = self._add_error_feedback(prompt, error_message)

            except Exception as e:
                logger.error(f"Generation attempt {attempt + 1} failed: {str(e)}")

                if attempt == self.max_retries - 1:
                    raise GenerationError(
                        f"Failed to generate workflow after {self.max_retries} attempts: {str(e)}"
                    )

                # Add error feedback for retry
                prompt = self._add_error_feedback(prompt, str(e))

        raise GenerationError(f"Failed to generate valid workflow after {self.max_retries} attempts")

    def generate_sync(self, metaflow: MetaFlow) -> str:
        """
        Synchronous version of generate()

        Args:
            metaflow: MetaFlow object

        Returns:
            workflow_yaml: Valid workflow YAML string
        """
        import asyncio
        return asyncio.run(self.generate(metaflow))

    def _add_error_feedback(self, prompt: str, error: str) -> str:
        """
        Add error feedback to prompt for retry

        Args:
            prompt: Original prompt
            error: Error message

        Returns:
            Updated prompt with error feedback
        """
        feedback = f"""

---

**Previous Generation Failed**

Error: {error}

Please fix the issues and regenerate the workflow YAML. Make sure to:
1. Follow the workflow specification exactly
2. Ensure all required fields are present
3. Use correct YAML syntax
4. Validate variable references

Regenerate the workflow:
"""
        return prompt + feedback


# Convenience function
async def generate_workflow_from_metaflow(metaflow: MetaFlow) -> str:
    """
    Convenience function to generate workflow from MetaFlow

    Args:
        metaflow: MetaFlow object

    Returns:
        workflow_yaml: Valid workflow YAML string
    """
    generator = WorkflowGenerator()
    return await generator.generate(metaflow)


async def generate_workflow_from_yaml_file(yaml_file: str) -> str:
    """
    Convenience function to generate workflow from MetaFlow YAML file

    Args:
        yaml_file: Path to MetaFlow YAML file

    Returns:
        workflow_yaml: Valid workflow YAML string
    """
    metaflow = MetaFlow.from_yaml_file(yaml_file)
    generator = WorkflowGenerator()
    return await generator.generate(metaflow)
