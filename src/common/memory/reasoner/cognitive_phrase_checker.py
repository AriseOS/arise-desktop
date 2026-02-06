"""Cognitive Phrase Checker - Checks if cognitive phrases can satisfy target."""

import logging
from typing import List, Optional, Tuple, Any

from src.common.memory.memory.memory import Memory

logger = logging.getLogger(__name__)
from src.common.memory.ontology.cognitive_phrase import CognitivePhrase
from src.common.memory.reasoner.prompts.cognitive_phrase_match_prompt import (
    CognitivePhraseMatchInput,
    CognitivePhraseMatchPrompt,
)


class CognitivePhraseChecker:
    """Checks if cognitive phrases can satisfy target."""

    def __init__(self, memory: Memory, llm_provider: Optional[Any] = None):
        """Initialize checker.

        Args:
            memory: Memory instance.
            llm_provider: LLM provider (AnthropicProvider) for evaluation.
        """
        self.memory = memory
        self.llm_provider = llm_provider
        self.prompt = CognitivePhraseMatchPrompt()

    async def check(self, target: str) -> Tuple[bool, List[CognitivePhrase], str]:
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

        if not self.llm_provider:
            # Fallback to simple text matching
            matches = self._text_match(target, phrases)
            if matches:
                return True, matches, "Text-based match found"
            return False, [], "No text matches found"

        # Use LLM to check if phrases can directly match or be combined
        can_satisfy, matches, reasoning = await self._llm_check(target, phrases)
        return can_satisfy, matches, reasoning

    def _text_match(
        self, target: str, phrases: List[CognitivePhrase], top_k: int = 5
    ) -> List[CognitivePhrase]:
        """Simple text-based matching."""
        target_lower = target.lower()
        scored = []

        for phrase in phrases:
            text = self._build_phrase_match_text(phrase)
            score = sum(1 for word in target_lower.split() if word in text)
            if score > 0:
                scored.append((phrase, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in scored[:top_k]]

    @staticmethod
    def _safe_text(value: Any) -> str:
        """Normalize any value to a stripped string."""
        return str(value or "").strip()

    @classmethod
    def _build_phrase_match_text(cls, phrase: CognitivePhrase) -> str:
        """Build match text with semantic-first preference."""
        semantic = phrase.semantic if isinstance(phrase.semantic, dict) else {}

        keywords_text = ""
        raw_keywords = semantic.get("keywords")
        if isinstance(raw_keywords, list):
            keywords_text = " ".join(
                cls._safe_text(keyword) for keyword in raw_keywords if cls._safe_text(keyword)
            )
        elif isinstance(raw_keywords, str):
            keywords_text = cls._safe_text(raw_keywords)

        parts = [
            cls._safe_text(phrase.label),
            cls._safe_text(semantic.get("retrieval_text")),
            cls._safe_text(semantic.get("intent")),
            keywords_text,
            cls._safe_text(semantic.get("description")),
            cls._safe_text(phrase.description),
        ]

        unique_parts: List[str] = []
        seen = set()
        for part in parts:
            if not part:
                continue
            key = part.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_parts.append(part)

        return " ".join(unique_parts).lower()

    async def _llm_check(
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

            # Call LLM using AnthropicProvider
            response = await self.llm_provider.generate_response(
                system_prompt=system_prompt,
                user_prompt=prompt_text
            )

            # Log raw LLM response for debugging
            logger.info(f"[L1] CognitivePhrase check - target: {target[:100]}...")
            logger.info(f"[L1] LLM response: {response[:500]}...")

            # Parse response
            output = self.prompt.parse_response(response)

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
            logger.error(f"LLM cognitive phrase check failed: {exc}")
            return False, [], f"LLM check error: {str(exc)}"


__all__ = ["CognitivePhraseChecker"]
