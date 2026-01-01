"""
Semantic Validator

Uses Claude to verify that a generated Workflow can accomplish the user's task.
This is the second layer of validation after rule-based validation.
"""

import os
import yaml
import logging
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from src.common.config_service import ConfigService

logger = logging.getLogger(__name__)


@dataclass
class SemanticIssue:
    """A semantic issue found during validation"""
    severity: str  # "error" or "warning"
    message: str
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "severity": self.severity,
            "message": self.message
        }
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


@dataclass
class SemanticValidationResult:
    """Result of semantic validation"""
    valid: bool
    score: int  # 0-100
    issues: List[SemanticIssue] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "score": self.score,
            "issues": [issue.to_dict() for issue in self.issues],
            "summary": self.summary
        }

    def get_feedback(self) -> str:
        """Get feedback string for the generation agent"""
        if self.valid and not self.issues:
            return "Semantic validation passed. The workflow should accomplish the task."

        parts = []
        if not self.valid:
            parts.append("SEMANTIC VALIDATION FAILED")

        if self.summary:
            parts.append(f"Summary: {self.summary}")

        errors = [i for i in self.issues if i.severity == "error"]
        warnings = [i for i in self.issues if i.severity == "warning"]

        if errors:
            parts.append(f"\nErrors ({len(errors)}):")
            for i, issue in enumerate(errors, 1):
                parts.append(f"  {i}. {issue.message}")
                if issue.suggestion:
                    parts.append(f"     Suggestion: {issue.suggestion}")

        if warnings:
            parts.append(f"\nWarnings ({len(warnings)}):")
            for i, issue in enumerate(warnings, 1):
                parts.append(f"  {i}. {issue.message}")

        return "\n".join(parts)


# Validation prompt template
VALIDATOR_PROMPT = """You are a Workflow validation expert. Your task is to verify that a generated Workflow can accomplish the user's intended task.

## User's Task Description
{task_description}

## User's Intent Sequence
The user performed these actions (in order):
{intent_summary}

## Generated Workflow
```yaml
{workflow_yaml}
```

## Validation Criteria

Please evaluate the workflow on these dimensions:

1. **Completeness**: Does the workflow cover all the steps needed to accomplish the task?
   - Are all user intents represented in the workflow?
   - Are there any missing steps?

2. **Correctness**: Are the steps in the right order with correct configurations?
   - Is browser_agent used for navigation and scraper_agent for extraction?
   - Are data dependencies handled correctly (e.g., extracting URLs before navigating)?

3. **Data Flow**: Are variables properly defined and used?
   - Are extracted data variables available where needed?
   - Is loop data flow correct (extracting list, then iterating)?

4. **Executability**: Can each step actually execute?
   - Are required inputs provided?
   - Are agent types used correctly?

## Output Format

Respond with a JSON object:
```json
{
    "valid": true/false,
    "score": 0-100,
    "summary": "Brief overall assessment",
    "issues": [
        {
            "severity": "error" or "warning",
            "message": "Description of the issue",
            "suggestion": "How to fix it (optional)"
        }
    ]
}
```

If the workflow looks correct and complete, return valid=true with score >= 80.
Only return valid=false if there are critical issues that would prevent task completion.
"""


class SemanticValidator:
    """
    Semantic validator using Claude to check if workflow can accomplish the task.
    """

    def __init__(
        self,
        config_service: Optional["ConfigService"] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        Initialize SemanticValidator.

        Args:
            config_service: ConfigService for reading configuration
            api_key: Anthropic API key
            model: Model to use (default: claude-sonnet-4-5)
            base_url: API proxy URL
        """
        # Get API key
        if api_key:
            self.api_key = api_key
        elif config_service:
            self.api_key = (
                config_service.get("agent.llm.api_key") or
                os.environ.get("ANTHROPIC_API_KEY")
            )
        else:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")

        # Get model
        if model:
            self.model = model
        elif config_service:
            self.model = config_service.get("llm.model") or "claude-sonnet-4-5"
        else:
            self.model = "claude-sonnet-4-5"

        # Get base URL
        if base_url:
            self.base_url = base_url
        elif config_service:
            self.base_url = config_service.get("llm.proxy_url")
        else:
            self.base_url = None

    def _build_intent_summary(self, intent_sequence: List[Dict[str, Any]]) -> str:
        """Build a summary of intents for the prompt"""
        lines = []
        for i, intent in enumerate(intent_sequence, 1):
            desc = intent.get("description", "Unknown intent")
            ops_count = len(intent.get("operations", []))
            lines.append(f"{i}. {desc} ({ops_count} operations)")
        return "\n".join(lines)

    async def validate(
        self,
        task_description: str,
        intent_sequence: List[Dict[str, Any]],
        workflow: Dict[str, Any]
    ) -> SemanticValidationResult:
        """
        Validate workflow semantically.

        Args:
            task_description: User's task description
            intent_sequence: List of Intent dictionaries
            workflow: Generated workflow dictionary

        Returns:
            SemanticValidationResult
        """
        if not self.api_key:
            logger.warning("No API key for semantic validation, skipping")
            return SemanticValidationResult(
                valid=True,
                score=70,
                summary="Semantic validation skipped (no API key)"
            )

        try:
            # Import Anthropic provider
            from src.common.llm import AnthropicProvider

            # Create provider
            provider = AnthropicProvider(
                api_key=self.api_key,
                model_name=self.model,
                base_url=self.base_url
            )

            # Build prompt
            intent_summary = self._build_intent_summary(intent_sequence)
            workflow_yaml = yaml.dump(workflow, allow_unicode=True, default_flow_style=False)

            prompt = VALIDATOR_PROMPT.format(
                task_description=task_description,
                intent_summary=intent_summary,
                workflow_yaml=workflow_yaml
            )

            # Call LLM
            response = await provider.generate_json_response(
                system_prompt="You are a workflow validation expert. Respond only with valid JSON.",
                user_prompt=prompt
            )

            # Parse response
            return self._parse_response(response)

        except Exception as e:
            logger.error(f"Semantic validation error: {e}")
            # On error, return a warning but don't block
            return SemanticValidationResult(
                valid=True,
                score=60,
                summary=f"Semantic validation encountered an error: {str(e)}",
                issues=[SemanticIssue(
                    severity="warning",
                    message=f"Semantic validation failed: {str(e)}"
                )]
            )

    def _parse_response(self, response: Dict[str, Any]) -> SemanticValidationResult:
        """Parse LLM response into SemanticValidationResult"""
        try:
            valid = response.get("valid", True)
            score = response.get("score", 80 if valid else 40)
            summary = response.get("summary", "")

            issues = []
            for issue_data in response.get("issues", []):
                issues.append(SemanticIssue(
                    severity=issue_data.get("severity", "warning"),
                    message=issue_data.get("message", "Unknown issue"),
                    suggestion=issue_data.get("suggestion")
                ))

            return SemanticValidationResult(
                valid=valid,
                score=score,
                summary=summary,
                issues=issues
            )

        except Exception as e:
            logger.error(f"Failed to parse validation response: {e}")
            return SemanticValidationResult(
                valid=True,
                score=60,
                summary="Failed to parse validation response"
            )
