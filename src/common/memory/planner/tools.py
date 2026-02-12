"""Planner Agent tools - Memory access tools for the PlannerAgent.

3 tool functions as bound methods of PlannerTools class:
- recall_phrases: Search complete workflow memories (L1)
- search_states: Search individual page nodes by embedding
- explore_graph: BFS path finding from start state to embedding-matched target

AMITool automatically skips `self` in schema generation.
All tools return JSON strings (AMIAgent expects string results).
All tools search both private and public memory when available.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from src.common.memory.ontology.action import Action
from src.common.memory.ontology.cognitive_phrase import CognitivePhrase
from src.common.memory.ontology.intent_sequence import IntentSequence
from src.common.memory.ontology.state import State

from .models import EnrichedPhrase

logger = logging.getLogger(__name__)


class PlannerTools:
    """Memory access tools for the PlannerAgent.

    Each method is a tool that AMIAgent can call. Methods are bound methods
    so AMITool's schema generation skips `self` automatically.

    Args:
        memory: WorkflowMemory instance (private user memory).
        embedding_service: EmbeddingService for query encoding.
        public_memory: Optional WorkflowMemory instance (public/shared memory).
    """

    def __init__(self, memory, embedding_service, public_memory=None):
        self.memory = memory
        self.public_memory = public_memory
        self.embedding_service = embedding_service

    async def recall_phrases(self, query: str, top_k: int = 5) -> str:
        """Search for related workflow memories by embedding similarity.
        Returns complete CognitivePhrases with States, Actions, and IntentSequences.

        Args:
            query: Search keywords describing the task
            top_k: Number of results to return, default 5
        """
        try:
            vector = self.embedding_service.encode(query)
        except Exception as e:
            logger.error(f"Embedding failed for recall_phrases: {e}")
            return json.dumps({"phrases": [], "error": f"Embedding failed: {e}"})
        if not vector:
            return json.dumps({"phrases": [], "error": "Embedding service unavailable"})

        # Search private memory
        phrases = self.memory.phrase_manager.search_phrases_by_embedding(
            vector, top_k=top_k
        )

        # Search public memory if available
        if self.public_memory:
            try:
                public_phrases = self.public_memory.phrase_manager.search_phrases_by_embedding(
                    vector, top_k=top_k
                )
                phrases.extend(public_phrases)
                # Deduplicate by phrase ID, keep first occurrence
                seen = set()
                unique = []
                for p in phrases:
                    if p.id not in seen:
                        seen.add(p.id)
                        unique.append(p)
                phrases = unique[:top_k]
            except Exception as e:
                logger.warning(f"Public memory search failed: {e}")

        # Enrich each phrase
        enriched_list = []
        for phrase in phrases:
            enriched = self._enrich_phrase(phrase)
            if enriched:
                enriched_list.append(enriched)

        result = {
            "phrases": [ep.to_dict() for ep in enriched_list],
        }
        return json.dumps(result, ensure_ascii=False, default=str)

    def get_phrase_recall_candidates(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Build scored phrase-recall candidates for debugging/reporting.

        This method is side-channel only and does not affect PlannerAgent's
        decision path. It mirrors recall_phrases' private-first + dedup strategy.
        """
        try:
            vector = self.embedding_service.encode(query)
        except Exception as e:
            logger.warning(f"Embedding failed for recall debug candidates: {e}")
            return []
        if not vector:
            return []

        candidates: List[Tuple[CognitivePhrase, float, str]] = []

        try:
            private_ranked = self.memory.phrase_manager.search_phrases_by_embedding_with_scores(
                vector,
                top_k=top_k,
            )
            candidates.extend((phrase, score, "private") for phrase, score in private_ranked)
        except Exception as e:
            logger.warning(f"Private phrase score search failed: {e}")

        if self.public_memory:
            try:
                public_ranked = (
                    self.public_memory.phrase_manager.search_phrases_by_embedding_with_scores(
                        vector,
                        top_k=top_k,
                    )
                )
                candidates.extend((phrase, score, "public") for phrase, score in public_ranked)
            except Exception as e:
                logger.warning(f"Public phrase score search failed: {e}")

        deduped: List[Tuple[CognitivePhrase, float, str]] = []
        seen_ids = set()
        for phrase, score, source in candidates:
            if phrase.id in seen_ids:
                continue
            seen_ids.add(phrase.id)
            deduped.append((phrase, score, source))
            if len(deduped) >= top_k:
                break

        output: List[Dict[str, Any]] = []
        for rank, (phrase, score, source) in enumerate(deduped, start=1):
            page_url, domain = self._get_phrase_primary_url_domain(phrase)
            output.append({
                "rank": rank,
                "phrase_id": phrase.id,
                "label": phrase.label,
                "description": phrase.description,
                "source": source,
                "similarity_score": round(float(score), 4),
                "page_url": page_url,
                "domain": domain,
            })
        return output

    def _enrich_phrase(self, phrase: CognitivePhrase) -> Optional[EnrichedPhrase]:
        """Resolve States, Actions, IntentSequences for a CognitivePhrase."""
        try:
            memory = self._get_memory_for_phrase(phrase)

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

    def _get_memory_for_phrase(self, phrase: CognitivePhrase):
        """Determine which memory (private/public) owns this phrase."""
        # Try private first
        if self.memory.phrase_manager.get_phrase(phrase.id):
            return self.memory
        if self.public_memory and self.public_memory.phrase_manager.get_phrase(phrase.id):
            return self.public_memory
        # Default to private
        return self.memory

    def _get_memory_for_state(self, state_id: str):
        """Determine which memory (private/public) owns this state."""
        if self.memory.state_manager.get_state(state_id):
            return self.memory
        if self.public_memory and self.public_memory.state_manager.get_state(state_id):
            return self.public_memory
        return self.memory

    def _get_phrase_primary_url_domain(self, phrase: CognitivePhrase) -> Tuple[str, str]:
        """Get the first available URL/domain pair for a phrase."""
        memory = self._get_memory_for_phrase(phrase)
        for state_id in phrase.state_path:
            state = memory.state_manager.get_state(state_id)
            if not state:
                continue
            page_url = state.page_url or ""
            domain = state.domain or self._derive_domain(page_url)
            return page_url, domain
        return "", ""

    @staticmethod
    def _derive_domain(page_url: str) -> str:
        if not page_url:
            return ""
        try:
            return urlparse(page_url).netloc
        except Exception:
            return ""

    async def search_states(self, query: str, top_k: int = 10) -> str:
        """Search for related page nodes by embedding similarity.
        Use when CognitivePhrases don't cover part of the task.

        Args:
            query: Search keywords
            top_k: Number of results to return, default 10
        """
        try:
            vector = self.embedding_service.encode(query)
        except Exception as e:
            logger.error(f"Embedding failed for search_states: {e}")
            return json.dumps({"states": [], "error": f"Embedding failed: {e}"})
        if not vector:
            return json.dumps({"states": [], "error": "Embedding service unavailable"})

        # Search private memory
        results = self.memory.state_manager.search_states_by_embedding(
            vector, top_k=top_k
        )

        # Search public memory if available
        if self.public_memory:
            try:
                public_results = self.public_memory.state_manager.search_states_by_embedding(
                    vector, top_k=top_k
                )
                results.extend(public_results)
                # Deduplicate by state ID, keep highest score
                seen = {}
                for state, score in results:
                    if state.id not in seen or score > seen[state.id][1]:
                        seen[state.id] = (state, score)
                results = sorted(seen.values(), key=lambda x: x[1], reverse=True)[:top_k]
            except Exception as e:
                logger.warning(f"Public memory state search failed: {e}")

        states_list = []
        for state, score in results:
            states_list.append({
                "id": state.id,
                "page_url": state.page_url,
                "page_title": state.page_title,
                "description": state.description,
                "domain": state.domain,
                "similarity_score": round(score, 4),
            })

        return json.dumps({"states": states_list}, ensure_ascii=False, default=str)

    async def explore_graph(
        self, query: str, start_state_id: str = "", top_k: int = 5, max_depth: int = 5
    ) -> str:
        """Explore the Memory graph to find a navigation path for an uncovered task part.

        This tool does the following in one call:
        1. Searches for target pages matching the query (embedding similarity)
        2. If start_state_id is provided, tries BFS to find a path from start to each target
        3. Returns the best path found, with page capabilities along the way

        Use this when recall_phrases found a partial match and you need to check
        if the graph has a continuation path for the uncovered part.

        Args:
            query: Description of the uncovered task part to search for
            start_state_id: State ID to start path search from (e.g., last state of a matched phrase). If empty, returns only the matched target states.
            top_k: Number of target candidates to search, default 5
            max_depth: Maximum BFS depth for path finding, default 5
        """
        try:
            vector = self.embedding_service.encode(query)
        except Exception as e:
            logger.error(f"Embedding failed for explore_graph: {e}")
            return json.dumps({"error": f"Embedding failed: {e}", "paths": []})
        if not vector:
            return json.dumps({"error": "Embedding service unavailable", "paths": []})

        # Search target states in both private and public memory
        all_candidates = []
        for mem in self._all_memories():
            results = mem.state_manager.search_states_by_embedding(
                vector, top_k=top_k
            )
            all_candidates.extend([(state, score, mem) for state, score in results])

        # Deduplicate by state ID, keep highest score
        seen = {}
        for state, score, mem in all_candidates:
            if state.id not in seen or score > seen[state.id][1]:
                seen[state.id] = (state, score, mem)
        candidates = sorted(seen.values(), key=lambda x: x[1], reverse=True)[:top_k]

        if not candidates:
            return json.dumps({"paths": [], "message": "No matching states found"})

        # If no start_state_id, just return the target states
        if not start_state_id:
            targets = []
            for state, score, mem in candidates:
                targets.append({
                    "state_id": state.id,
                    "page_url": state.page_url,
                    "description": state.description,
                    "domain": state.domain,
                    "similarity_score": round(score, 4),
                })
            return json.dumps(
                {"paths": [], "targets": targets, "message": "No start_state_id provided, returning target states only"},
                ensure_ascii=False, default=str,
            )

        # Try BFS from start to each candidate target
        paths_found = []
        for target_state, score, mem in candidates:
            if target_state.id == start_state_id:
                continue

            path_result = mem.query_navigation_path(start_state_id, target_state.id)
            if path_result is None:
                # Try the other memory if available
                for other_mem in self._all_memories():
                    if other_mem is not mem:
                        path_result = other_mem.query_navigation_path(
                            start_state_id, target_state.id
                        )
                        if path_result:
                            mem = other_mem
                            break

            if path_result is None:
                continue

            path_states, path_actions = path_result

            # Build path with capabilities for each state
            steps = []
            for i, state in enumerate(path_states):
                step_info = {
                    "state_id": state.id,
                    "page_url": state.page_url,
                    "page_title": state.page_title,
                    "description": state.description,
                    "domain": state.domain,
                }

                # Add capabilities (operations + navigations)
                caps = mem.get_page_capabilities(state.id)
                sequences = caps.get("sequences", [])
                if sequences:
                    step_info["operations"] = []
                    for seq in sequences[:5]:
                        op = {"description": seq.description}
                        intents = []
                        for intent in (seq.intents or [])[:5]:
                            if isinstance(intent, dict):
                                t, txt = intent.get("type", ""), intent.get("text", "")
                            else:
                                t, txt = getattr(intent, "type", ""), getattr(intent, "text", "")
                            if t:
                                intents.append(f"{t}: {txt[:80]}" if txt else t)
                        if intents:
                            op["intents"] = intents
                        step_info["operations"].append(op)

                # Add the action leading to the next state
                if i < len(path_actions):
                    action = path_actions[i]
                    step_info["next_action"] = {
                        "description": action.description,
                        "trigger": action.trigger,
                    }

                steps.append(step_info)

            paths_found.append({
                "target_state_id": target_state.id,
                "target_similarity": round(score, 4),
                "path_length": len(path_states),
                "steps": steps,
            })

        if not paths_found:
            # Return targets even if no path found
            targets = []
            for state, score, mem in candidates[:3]:
                targets.append({
                    "state_id": state.id,
                    "page_url": state.page_url,
                    "description": state.description,
                    "domain": state.domain,
                    "similarity_score": round(score, 4),
                })
            return json.dumps(
                {"paths": [], "targets": targets, "message": "No path found from start state to any target"},
                ensure_ascii=False, default=str,
            )

        return json.dumps(
            {"paths": paths_found},
            ensure_ascii=False, default=str,
        )

    def _all_memories(self):
        """Return list of all available memory instances (private + public)."""
        memories = [self.memory]
        if self.public_memory:
            memories.append(self.public_memory)
        return memories
