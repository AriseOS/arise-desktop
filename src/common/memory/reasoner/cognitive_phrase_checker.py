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
        """Build phrase match text (description-first, semantic as compatibility fallback)."""
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
            cls._safe_text(phrase.description),
            # Backward compatibility for historical records:
            cls._safe_text(semantic.get("description")),
            cls._safe_text(semantic.get("retrieval_text")),
            cls._safe_text(semantic.get("intent")),
            keywords_text,
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

    async def check_merged(
        self,
        target: str,
        private_phrases: List[CognitivePhrase],
        public_phrases: List[CognitivePhrase],
    ) -> Tuple[bool, List[CognitivePhrase], str, str]:
        """Check against merged private + public phrases in a single LLM call.

        Args:
            target: Target description.
            private_phrases: Phrases from user's private memory.
            public_phrases: Phrases from public memory.

        Returns:
            Tuple of (can_satisfy, matching_phrases, reasoning, source).
            source is "private" or "public".
        """
        # Tag and merge phrases
        tagged = []
        for p in private_phrases:
            d = p.to_dict()
            d["_source"] = "private"
            tagged.append(d)
        for p in public_phrases:
            d = p.to_dict()
            d["_source"] = "public"
            tagged.append(d)

        if not tagged:
            return False, [], "No cognitive phrases available", "private"

        if not self.llm_provider:
            all_phrases = private_phrases + public_phrases
            matches = self._text_match(target, all_phrases)
            if matches:
                source = "private" if matches[0] in private_phrases else "public"
                return True, matches, "Text-based match found", source
            return False, [], "No text matches found", "private"

        # Capacity protection: pre-filter if too many phrases
        max_total = 50
        if len(tagged) > max_total:
            half = max_total // 2
            private_scored = self._score_phrases(target, tagged, "private")[:half]
            public_scored = self._score_phrases(target, tagged, "public")[:half]
            tagged = private_scored + public_scored

        try:
            input_data = CognitivePhraseMatchInput(
                target=target,
                cognitive_phrases=tagged,
            )
            prompt_text = self.prompt.build_prompt(input_data)
            system_prompt = self.prompt.get_system_prompt()

            response = await self.llm_provider.generate_response(
                system_prompt=system_prompt,
                user_prompt=prompt_text,
            )

            logger.info(f"[L1] Merged CognitivePhrase check - target: {target[:100]}...")
            logger.info(f"[L1] LLM response: {response[:500]}...")

            output = self.prompt.parse_response(response)

            # Build phrase map from both sources
            phrase_map = {p.id: p for p in private_phrases}
            phrase_map.update({p.id: p for p in public_phrases})

            matching_phrases = []
            if output.can_satisfy and output.matched_phrase_ids:
                matching_phrases = [
                    phrase_map[pid]
                    for pid in output.matched_phrase_ids
                    if pid in phrase_map
                ]

            # Determine source from LLM output or from matched phrase location
            source = output.source
            if source not in ("private", "public") and matching_phrases:
                private_ids = {p.id for p in private_phrases}
                source = "private" if matching_phrases[0].id in private_ids else "public"

            return output.can_satisfy, matching_phrases, output.reasoning, source

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error(f"LLM merged phrase check failed: {exc}")
            return False, [], f"LLM check error: {str(exc)}", "private"

    def _score_phrases(
        self, target: str, tagged_dicts: List[dict], source_filter: str
    ) -> List[dict]:
        """Score and sort tagged phrase dicts by text relevance, filtered by source."""
        target_lower = target.lower()
        filtered = [d for d in tagged_dicts if d.get("_source") == source_filter]
        scored = []
        for d in filtered:
            text = (
                f"{d.get('label', '')} {d.get('description', '')}"
            ).lower()
            score = sum(1 for word in target_lower.split() if word in text)
            scored.append((d, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [d for d, _ in scored]

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
