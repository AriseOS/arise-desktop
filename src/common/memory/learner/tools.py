"""Learner Agent tools - Memory query tools for the LearnerAgent.

4 tool functions as bound methods of LearnerTools class:
- recall_phrases: Search existing phrases with enriched details (recall-first)
- find_states_by_urls: Look up States by URLs (O(1) via url_index)
- get_state_sequences: Get IntentSequences for a State
- verify_action: Check if an Action exists between two States

AMITool automatically skips `self` in schema generation.
All tools return JSON strings (AMIAgent expects string results).
All tools search PRIVATE memory only (learner writes to private).
"""

import json
import logging
from typing import List, Optional

from src.common.memory.planner.models import EnrichedPhrase

logger = logging.getLogger(__name__)


class LearnerTools:
    """Memory query tools for the LearnerAgent.

    Each method is a tool that AMIAgent can call. Methods are bound methods
    so AMITool's schema generation skips `self` automatically.

    Args:
        memory: WorkflowMemory instance (private user memory).
        embedding_service: EmbeddingService for query encoding.
    """

    def __init__(self, memory, embedding_service):
        self.memory = memory
        self.embedding_service = embedding_service

    async def recall_phrases(self, query: str, top_k: int = 5) -> str:
        """Search for existing CognitivePhrases by embedding similarity.
        Returns enriched data: each phrase with full state_path (URLs, page titles),
        execution_plan (operations), actions, and similarity_score.

        Use this as the FIRST step to check what already exists before analyzing
        the execution trace. The similarity_score is for reference — do NOT use
        a hard threshold; instead read the phrase details and judge coverage yourself.

        Args:
            query: Search query combining user_request and subtask summaries
            top_k: Number of results to return, default 5
        """
        try:
            vector = self.embedding_service.encode(query)
        except Exception as e:
            logger.error(f"Embedding failed for recall_phrases: {e}")
            return json.dumps({"phrases": [], "error": f"Embedding failed: {e}"})

        if not vector:
            return json.dumps({"phrases": [], "error": "Embedding service unavailable"})

        try:
            ranked = self.memory.phrase_manager.search_phrases_by_embedding_with_scores(
                vector, top_k=top_k
            )
        except Exception as e:
            logger.warning(f"Error searching phrases: {e}")
            return json.dumps({"phrases": [], "error": str(e)})

        enriched_list = []
        for phrase, score in ranked:
            enriched = self._enrich_phrase(phrase)
            if enriched:
                d = enriched.to_dict()
                d["similarity_score"] = round(float(score), 4)
                enriched_list.append(d)

        return json.dumps(
            {"phrases": enriched_list},
            ensure_ascii=False,
            default=str,
        )

    def _enrich_phrase(self, phrase) -> Optional[EnrichedPhrase]:
        """Resolve States, Actions, IntentSequences for a CognitivePhrase.

        Reuses EnrichedPhrase model from planner.models for consistent
        serialization format.
        """
        try:
            memory = self.memory

            # Resolve States from state_path
            states = []
            for state_id in phrase.state_path:
                state = memory.state_manager.get_state(state_id)
                if state:
                    states.append(state)

            # Resolve IntentSequences per state via execution_plan
            state_sequences = {}
            for step in phrase.execution_plan:
                seqs = []
                if memory.intent_sequence_manager:
                    for seq_id in step.in_page_sequence_ids:
                        seq = memory.intent_sequence_manager.get_sequence(seq_id)
                        if seq:
                            seqs.append(seq)
                    if step.navigation_sequence_id:
                        nav_seq = memory.intent_sequence_manager.get_sequence(
                            step.navigation_sequence_id
                        )
                        if nav_seq:
                            seqs.append(nav_seq)
                state_sequences[step.state_id] = seqs

            # Resolve Actions between consecutive states
            actions = []
            for step in phrase.execution_plan:
                if step.navigation_action_id:
                    action = memory.action_manager.get_action_by_id(
                        step.navigation_action_id
                    )
                    if action:
                        actions.append(action)
                        continue
                # Fallback: lookup by state pair
                step_idx = step.index - 1  # 0-based
                if step_idx < len(phrase.state_path) - 1:
                    action = memory.get_action(
                        phrase.state_path[step_idx],
                        phrase.state_path[step_idx + 1],
                    )
                    if action:
                        actions.append(action)

            return EnrichedPhrase(
                phrase=phrase,
                states=states,
                actions=actions,
                state_sequences=state_sequences,
            )
        except Exception as e:
            logger.warning(f"Failed to enrich phrase {phrase.id}: {e}")
            return None

    async def find_states_by_urls(self, urls: List[str]) -> str:
        """Look up Memory States by their URLs. Returns State info for each URL found.

        Use this to check which URLs from the execution trace exist as States in Memory.

        Args:
            urls: List of URLs to look up
        """
        results = []
        for url in urls:
            try:
                state = self.memory.find_state_by_url(url)
                if state:
                    results.append({
                        "url": url,
                        "found": True,
                        "state_id": state.id,
                        "page_title": state.page_title,
                        "description": state.description,
                        "domain": state.domain,
                    })
                else:
                    results.append({
                        "url": url,
                        "found": False,
                    })
            except Exception as e:
                logger.warning(f"Error looking up URL {url}: {e}")
                results.append({
                    "url": url,
                    "found": False,
                    "error": str(e),
                })

        return json.dumps(
            {"states": results},
            ensure_ascii=False,
            default=str,
        )

    async def get_state_sequences(self, state_id: str) -> str:
        """Get IntentSequences associated with a State.

        Returns the list of operations (IntentSequences) that can be performed on this page.

        Args:
            state_id: State ID to query
        """
        try:
            if not self.memory.intent_sequence_manager:
                return json.dumps({"sequences": [], "error": "No intent_sequence_manager"})

            sequences = self.memory.intent_sequence_manager.list_by_state(state_id)
            seq_list = []
            for seq in sequences:
                seq_list.append({
                    "id": seq.id,
                    "description": seq.description,
                    "causes_navigation": getattr(seq, "causes_navigation", False),
                    "navigation_target_state_id": getattr(seq, "navigation_target_state_id", None),
                })

            return json.dumps(
                {"state_id": state_id, "sequences": seq_list},
                ensure_ascii=False,
                default=str,
            )
        except Exception as e:
            logger.warning(f"Error getting sequences for state {state_id}: {e}")
            return json.dumps({"sequences": [], "error": str(e)})

    async def verify_action(self, source_state_id: str, target_state_id: str) -> str:
        """Verify that an Action (navigation edge) exists between two States.

        Use this to confirm that the effective path has valid connections in Memory.

        Args:
            source_state_id: Source State ID
            target_state_id: Target State ID
        """
        try:
            action = self.memory.get_action(source_state_id, target_state_id)
            if action:
                return json.dumps({
                    "connected": True,
                    "action_id": action.id,
                    "description": action.description,
                    "type": action.type,
                    "trigger": action.trigger,
                })
            return json.dumps({
                "connected": False,
                "source_state_id": source_state_id,
                "target_state_id": target_state_id,
            })
        except Exception as e:
            logger.warning(
                f"Error verifying action {source_state_id} -> {target_state_id}: {e}"
            )
            return json.dumps({"connected": False, "error": str(e)})
