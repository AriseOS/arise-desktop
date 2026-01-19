"""State Satisfaction Prompt - LLM prompt for checking if states satisfy target.

This prompt is used to evaluate whether a set of states (and their intents)
can satisfy a given retrieval target.
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from src.cloud_backend.memgraph.services.prompt_base import BasePrompt


class StateSatisfactionInput(BaseModel):
    """Input for state satisfaction checking."""

    target: str = Field(..., description="Target description to satisfy")
    states: List[Dict[str, Any]] = Field(..., description="List of states to evaluate")


class StateSatisfactionOutput(BaseModel):
    """Output from state satisfaction checking."""

    satisfies: bool = Field(..., description="Whether states satisfy the target")
    reasoning: str = Field(..., description="Explanation of the evaluation")
    confidence: float = Field(..., description="Confidence score (0-1)")
    missing_elements: List[str] = Field(
        default_factory=list,
        description="Elements missing from states to fully satisfy target",
    )


class StateSatisfactionPrompt(BasePrompt[StateSatisfactionInput, StateSatisfactionOutput]):
    """Prompt for state satisfaction checking."""

    def __init__(self):
        """Initialize the prompt."""
        super().__init__(prompt_name="state_satisfaction", version="1.0")

    def get_system_prompt(self) -> str:
        """Get system prompt."""
        return """You are an expert at evaluating whether workflow states satisfy user goals.
Your task is to analyze if a set of states (with their intents and actions) can
accomplish a given target."""

    def build_prompt(self, input_data: StateSatisfactionInput) -> str:
        """Build the prompt."""
        # Format states
        states_text = []
        for i, state in enumerate(input_data.states, 1):
            intents_text = ""
            if "atomic_intents" in state:
                intents = state["atomic_intents"]
                if intents:
                    intent_types = [
                        str(intent.get('type', 'N/A'))
                        if isinstance(intent, dict)
                        else str(intent)
                        for intent in intents
                    ]
                    intents_text = f"\n   Intents: {', '.join(intent_types)}"

            states_text.append(
                f"{i}. State: {state.get('label', 'N/A')}\n"
                f"   Type: {state.get('type', 'N/A')}\n"
                f"   URL: {state.get('page_url', 'N/A')}"
                f"{intents_text}"
            )

        prompt = f"""## Task
Evaluate if the given states can satisfy the target.

## Target
{input_data.target}

## States
{chr(10).join(states_text)}

## Instructions
1. Analyze each state's semantic meaning and intents
2. Determine if the states collectively satisfy the target
3. Identify any missing elements needed to fully satisfy the target
4. Consider the workflow context and state transitions
5. Provide detailed reasoning for your evaluation

## Evaluation Criteria
- Do the states cover all aspects of the target?
- Are the intents appropriate for the target?
- Is the workflow semantically coherent?
- Are there any gaps in the workflow?

## Output Format
Return a JSON object with the following structure:
{{
    "satisfies": boolean,
    "reasoning": "detailed explanation of the evaluation",
    "confidence": float between 0 and 1,
    "missing_elements": ["list of missing elements, if any"]
}}

## Examples

### Example 1: Fully Satisfied
Target: "Search for a product"
States: [State with type "SearchProducts"]
Output:
{{
    "satisfies": true,
    "reasoning": "The state directly performs a product search, which fully satisfies the target.",
    "confidence": 0.95,
    "missing_elements": []
}}

### Example 2: Not Satisfied
Target: "Add product to cart and checkout"
States: [State with type "BrowseProduct"]
Output:
{{
    "satisfies": false,
    "reasoning": "The state only browses products but does not add to cart or proceed to checkout.",
    "confidence": 0.85,
    "missing_elements": ["Add to cart action", "Checkout process"]
}}
"""
        return prompt

    def parse_response(self, llm_response: str) -> StateSatisfactionOutput:
        """Parse LLM response."""
        try:
            data = self.parse_json_response(llm_response)
            return StateSatisfactionOutput(**data)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Return default "not satisfied" response on parse error
            return StateSatisfactionOutput(
                satisfies=False,
                reasoning=f"Failed to parse LLM response: {str(exc)}",
                confidence=0.0,
                missing_elements=["Unable to evaluate"],
            )

    def validate_input(self, input_data: StateSatisfactionInput) -> bool:
        """Validate input data."""
        return bool(input_data.target) and isinstance(input_data.states, list)

    def validate_output(self, output_data: StateSatisfactionOutput) -> bool:
        """Validate output data."""
        return (
            isinstance(output_data.satisfies, bool)
            and 0.0 <= output_data.confidence <= 1.0
            and isinstance(output_data.missing_elements, list)
        )


__all__ = [
    "StateSatisfactionInput",
    "StateSatisfactionOutput",
    "StateSatisfactionPrompt",
]
