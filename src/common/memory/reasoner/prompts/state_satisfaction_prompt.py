"""State Satisfaction Prompt - LLM prompt for checking if states satisfy target.

This prompt is used to evaluate whether a set of states (and their intents)
can satisfy a given retrieval target.
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from src.common.memory.services.prompt_base import BasePrompt


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
        return """You are an expert at evaluating whether workflow states provide relevant navigation information for a target task.
Your task is to analyze if a set of states (with their pages/URLs and intents) contain relevant pages or paths that would help accomplish the given target."""

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
Evaluate if the given states provide relevant navigation information (pages/URLs) for accomplishing the target.

## Target
{input_data.target}

## States
{chr(10).join(states_text)}

## Instructions
1. Analyze each state's page URL and semantic meaning
2. Determine if the states contain pages or paths relevant to the target
3. Identify any missing navigation information needed
4. Focus on whether these states point to the RIGHT PLACES, not whether they can complete the entire task

## Evaluation Criteria
- Do the states provide relevant pages/URLs for accomplishing the target?
- Are the pages/paths semantically related to the target task?
- Would navigating to these pages help accomplish the target?
- Note: States do NOT need to cover all task steps — they only need to provide useful navigation guidance

## Output Format
Return a JSON object with the following structure:
{{
    "satisfies": boolean,
    "reasoning": "detailed explanation of the evaluation",
    "confidence": float between 0 and 1,
    "missing_elements": ["list of missing navigation info, if any"]
}}

## Examples

### Example 1: Relevant Navigation
Target: "Collect Product Hunt weekly leaderboard product info"
States: [State with URL "https://www.producthunt.com/leaderboard/weekly/2025/1/1"]
Output:
{{
    "satisfies": true,
    "reasoning": "The state points to the PH weekly leaderboard page, which is the relevant page for collecting weekly product info.",
    "confidence": 0.9,
    "missing_elements": []
}}

### Example 2: Not Relevant
Target: "Add product to cart and checkout"
States: [State with URL "https://example.com/about-us"]
Output:
{{
    "satisfies": false,
    "reasoning": "The about-us page is not relevant to adding products to cart or checkout.",
    "confidence": 0.85,
    "missing_elements": ["Product page or cart page URL"]
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
