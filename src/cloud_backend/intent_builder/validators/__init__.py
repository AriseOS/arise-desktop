"""
Workflow validation components

Two-layer validation:
1. RuleValidator: Fast, deterministic code-based validation
2. SemanticValidator: LLM-based validation for task completeness

Unified interface:
- WorkflowValidator: Combines both validation layers
"""

import logging
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

from .yaml_validator import WorkflowYAMLValidator
from .semantic_validator import SemanticValidator, SemanticValidationResult, SemanticIssue

# Import from agents/tools for unified access
from ..agents.tools.validate import (
    RuleValidator,
    ValidationResult,
    validate_workflow_yaml,
    validate_workflow_dict
)

if TYPE_CHECKING:
    from src.common.config_service import ConfigService

logger = logging.getLogger(__name__)


@dataclass
class FullValidationResult:
    """Combined result from both validation layers"""
    valid: bool
    rule_check: ValidationResult
    semantic_check: Optional[SemanticValidationResult] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "valid": self.valid,
            "message": self.message,
            "rule_check": self.rule_check.to_dict() if self.rule_check else None,
        }
        if self.semantic_check:
            result["semantic_check"] = self.semantic_check.to_dict()
        return result

    def get_feedback(self) -> str:
        """Get combined feedback for the generation agent"""
        parts = []

        if not self.valid:
            parts.append("VALIDATION FAILED")

        if self.rule_check and not self.rule_check.valid:
            parts.append("\n## Rule Validation Errors:")
            for error in self.rule_check.errors:
                parts.append(f"  - {error}")

        if self.semantic_check and not self.semantic_check.valid:
            parts.append(f"\n## Semantic Validation:")
            parts.append(self.semantic_check.get_feedback())

        if not parts:
            return "Validation passed."

        return "\n".join(parts)


class WorkflowValidator:
    """
    Unified Workflow Validator combining rule-based and semantic validation.

    Two-layer validation:
    1. Rule validation: Fast, deterministic checks (YAML format, required fields,
       variable references, agent types, foreach structure)
    2. Semantic validation: LLM-based checks (task completeness, data flow correctness,
       step ordering)

    Example:
        validator = WorkflowValidator()
        result = await validator.validate(
            task_description="Extract product info",
            intent_sequence=[...],
            workflow={...}
        )

        if not result.valid:
            print(result.get_feedback())
    """

    def __init__(
        self,
        config_service: Optional["ConfigService"] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        enable_semantic: bool = True
    ):
        """
        Initialize WorkflowValidator.

        Args:
            config_service: ConfigService for reading configuration
            api_key: Anthropic API key for semantic validation
            model: Model to use for semantic validation
            base_url: API proxy URL
            enable_semantic: Whether to enable semantic validation (default: True)
        """
        self.rule_validator = RuleValidator()
        self.enable_semantic = enable_semantic

        if enable_semantic:
            self.semantic_validator = SemanticValidator(
                config_service=config_service,
                api_key=api_key,
                model=model,
                base_url=base_url
            )
        else:
            self.semantic_validator = None

    async def validate(
        self,
        task_description: str,
        intent_sequence: List[Dict[str, Any]],
        workflow: Dict[str, Any],
        skip_semantic: bool = False
    ) -> FullValidationResult:
        """
        Validate workflow using both rule-based and semantic validation.

        Args:
            task_description: User's task description
            intent_sequence: List of Intent dictionaries
            workflow: Generated workflow dictionary
            skip_semantic: Skip semantic validation (useful for quick checks)

        Returns:
            FullValidationResult with combined results
        """
        # Step 1: Rule validation (fast, always run)
        rule_result = self.rule_validator.validate(workflow)

        if not rule_result.valid:
            logger.info(f"Rule validation failed: {len(rule_result.errors)} errors")
            return FullValidationResult(
                valid=False,
                rule_check=rule_result,
                semantic_check=None,
                message="Rule validation failed"
            )

        logger.info("Rule validation passed")

        # Step 2: Semantic validation (if enabled and not skipped)
        if self.enable_semantic and not skip_semantic and self.semantic_validator:
            logger.info("Running semantic validation...")
            semantic_result = await self.semantic_validator.validate(
                task_description=task_description,
                intent_sequence=intent_sequence,
                workflow=workflow
            )

            if not semantic_result.valid:
                logger.info(f"Semantic validation failed: score={semantic_result.score}")
                return FullValidationResult(
                    valid=False,
                    rule_check=rule_result,
                    semantic_check=semantic_result,
                    message="Semantic validation failed"
                )

            logger.info(f"Semantic validation passed: score={semantic_result.score}")
            return FullValidationResult(
                valid=True,
                rule_check=rule_result,
                semantic_check=semantic_result,
                message="Validation complete"
            )

        # Only rule validation
        return FullValidationResult(
            valid=True,
            rule_check=rule_result,
            semantic_check=None,
            message="Rule validation passed (semantic validation skipped)"
        )

    def validate_rules_only(self, workflow: Dict[str, Any]) -> ValidationResult:
        """
        Quick rule-only validation (synchronous).

        Args:
            workflow: Workflow dictionary

        Returns:
            ValidationResult from rule validator
        """
        return self.rule_validator.validate(workflow)


__all__ = [
    # Legacy
    "WorkflowYAMLValidator",

    # Rule validation
    "RuleValidator",
    "ValidationResult",
    "validate_workflow_yaml",
    "validate_workflow_dict",

    # Semantic validation
    "SemanticValidator",
    "SemanticValidationResult",
    "SemanticIssue",

    # Unified validation
    "WorkflowValidator",
    "FullValidationResult",
]
