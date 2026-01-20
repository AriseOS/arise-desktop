"""Cognitive Phrase Match Prompt - LLM prompt for checking cognitive phrase matches.

This prompt is used to determine if cognitive phrases can satisfy a target,
either directly or through combination.
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from src.cloud_backend.memgraph.services.prompt_base import BasePrompt


class CognitivePhraseMatchInput(BaseModel):
    """Input for cognitive phrase matching."""

    target: str = Field(..., description="Target description to match")
    cognitive_phrases: List[Dict[str, Any]] = Field(
        ..., description="List of candidate cognitive phrases"
    )


class CognitivePhraseMatchOutput(BaseModel):
    """Output from cognitive phrase matching."""

    can_satisfy: bool = Field(..., description="Whether phrases can satisfy target")
    matched_phrase_ids: List[str] = Field(
        default_factory=list, description="IDs of matching phrases"
    )
    combination_strategy: str = Field(
        default="none",
        description="How to combine phrases: 'direct', 'sequential', 'none'",
    )
    reasoning: str = Field(..., description="Explanation of the match result")
    confidence: float = Field(..., description="Confidence score (0-1)")


class CognitivePhraseMatchPrompt(BasePrompt[CognitivePhraseMatchInput, CognitivePhraseMatchOutput]):
    """Prompt for cognitive phrase matching."""

    def __init__(self):
        """Initialize the prompt."""
        super().__init__(prompt_name="cognitive_phrase_match", version="1.0")

    def get_system_prompt(self) -> str:
        """Get system prompt."""
        return """You are an expert at analyzing cognitive phrases and user goals.
Your task is to determine if available cognitive phrases can satisfy a user's target,
either through direct match or by combining multiple phrases."""

    def build_prompt(self, input_data: CognitivePhraseMatchInput) -> str:
        """Build the prompt."""
        # Format cognitive phrases
        phrases_text = []
        for i, phrase in enumerate(input_data.cognitive_phrases, 1):
            phrases_text.append(
                f"{i}. ID: {phrase.get('id', 'unknown')}\n"
                f"   Label: {phrase.get('label', 'N/A')}\n"
                f"   Description: {phrase.get('description', 'N/A')}\n"
                f"   States: {len(phrase.get('states', []))} states\n"
                f"   Actions: {len(phrase.get('actions', []))} actions"
            )

        prompt = f"""## Task
Analyze if the available cognitive phrases can satisfy the user's target.

## Target
{input_data.target}

## Available Cognitive Phrases
{chr(10).join(phrases_text)}

## Instructions
1. Analyze if any single cognitive phrase directly matches the target
2. Consider if multiple phrases can be combined to satisfy the target
3. Evaluate the semantic similarity and workflow compatibility
4. Provide a clear reasoning for your decision

## Output Format
Return a JSON object with the following structure:
{{
    "can_satisfy": boolean,
    "matched_phrase_ids": [list of phrase IDs that match],
    "combination_strategy": "direct" | "sequential" | "none",
    "reasoning": "detailed explanation",
    "confidence": float between 0 and 1
}}

## Example
{{
    "can_satisfy": true,
    "matched_phrase_ids": ["phrase-123"],
    "combination_strategy": "direct",
    "reasoning": "Phrase 'phrase-123' directly matches the target as it "
                 "contains the exact workflow steps needed.",
    "confidence": 0.92
}}
"""
        return prompt

    def parse_response(self, llm_response: str) -> CognitivePhraseMatchOutput:
        """Parse LLM response."""
        try:
            data = self.parse_json_response(llm_response)
            return CognitivePhraseMatchOutput(**data)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Return default "no match" response on parse error
            return CognitivePhraseMatchOutput(
                can_satisfy=False,
                matched_phrase_ids=[],
                combination_strategy="none",
                reasoning=f"Failed to parse LLM response: {str(exc)}",
                confidence=0.0,
            )

    def validate_input(self, input_data: CognitivePhraseMatchInput) -> bool:
        """Validate input data."""
        return bool(input_data.target) and isinstance(input_data.cognitive_phrases, list)

    def validate_output(self, output_data: CognitivePhraseMatchOutput) -> bool:
        """Validate output data."""
        return (
            isinstance(output_data.can_satisfy, bool)
            and 0.0 <= output_data.confidence <= 1.0
            and output_data.combination_strategy in ["direct", "sequential", "none"]
        )


__all__ = [
    "CognitivePhraseMatchInput",
    "CognitivePhraseMatchOutput",
    "CognitivePhraseMatchPrompt",
]
