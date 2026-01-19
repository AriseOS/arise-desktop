"""Cognitive Phrase Checker - Checks if cognitive phrases can satisfy target."""

from typing import List, Optional, Tuple

from src.cloud_backend.memgraph.memory.memory import Memory
from src.cloud_backend.memgraph.ontology.cognitive_phrase import CognitivePhrase
from src.cloud_backend.memgraph.reasoner.prompts.cognitive_phrase_match_prompt import (
    CognitivePhraseMatchInput,
    CognitivePhraseMatchPrompt,
)
from src.cloud_backend.memgraph.services.llm import LLMClient, LLMMessage


class CognitivePhraseChecker:
    """Checks if cognitive phrases can satisfy target."""

    def __init__(self, memory: Memory, llm_client: Optional[LLMClient] = None):
        """Initialize checker.

        Args:
            memory: Memory instance.
            llm_client: LLM client for evaluation.
        """
        self.memory = memory
        self.llm_client = llm_client
        self.prompt = CognitivePhraseMatchPrompt()

    def check(self, target: str) -> Tuple[bool, List[CognitivePhrase], str]:
        """Check if cognitive phrases can satisfy target.

        Args:
            target: Target description.

        Returns:
            Tuple of (can_satisfy, matching_phrases, reasoning).
        """
        # Get all cognitive phrases
        phrases = self.memory.phrase_manager.list_phrases()

        if not phrases:
            return False, [], "No cognitive phrases available"

        if not self.llm_client:
            # Fallback to simple text matching
            matches = self._text_match(target, phrases)
            if matches:
                return True, matches, "Text-based match found"
            return False, [], "No text matches found"

        # Use LLM to check if phrases can directly match or be combined
        can_satisfy, matches, reasoning = self._llm_check(target, phrases)
        return can_satisfy, matches, reasoning

    def _text_match(
        self, target: str, phrases: List[CognitivePhrase], top_k: int = 5
    ) -> List[CognitivePhrase]:
        """Simple text-based matching."""
        target_lower = target.lower()
        scored = []

        for phrase in phrases:
            text = f"{phrase.label} {phrase.description or ''}".lower()
            score = sum(1 for word in target_lower.split() if word in text)
            if score > 0:
                scored.append((phrase, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in scored[:top_k]]

    def _llm_check(
        self, target: str, phrases: List[CognitivePhrase]
    ) -> Tuple[bool, List[CognitivePhrase], str]:
        """Use LLM to check if phrases can satisfy target."""
        try:
            # Prepare input
            input_data = CognitivePhraseMatchInput(
                target=target,
                cognitive_phrases=[phrase.to_dict() for phrase in phrases],
            )

            # Build prompt
            prompt_text = self.prompt.build_prompt(input_data)
            system_prompt = self.prompt.get_system_prompt()

            # Call LLM
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=prompt_text),
            ]

            response = self.llm_client.generate(messages=messages, temperature=0.1)

            # Print raw LLM response for debugging
            print("\n" + "=" * 80)
            print("COGNITIVE PHRASE CHECKER - RAW LLM RESPONSE:")
            print("=" * 80)
            print(response.content)
            print("=" * 80 + "\n")

            # Parse response
            output = self.prompt.parse_response(response.content)

            # Find matching phrases
            matching_phrases = []
            if output.can_satisfy and output.matched_phrase_ids:
                phrase_map = {p.id: p for p in phrases}
                matching_phrases = [
                    phrase_map[pid]
                    for pid in output.matched_phrase_ids
                    if pid in phrase_map
                ]

            return output.can_satisfy, matching_phrases, output.reasoning

        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"LLM cognitive phrase check failed: {exc}")
            return False, [], f"LLM check error: {str(exc)}"


__all__ = ["CognitivePhraseChecker"]
