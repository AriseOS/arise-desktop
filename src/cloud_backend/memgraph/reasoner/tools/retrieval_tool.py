"""Retrieval Tool - Tool for retrieving states and actions from memory.

This tool implements the retrieval functionality:
1. Use embedding to find candidate states
2. Use LLM to check if states satisfy the target
3. Explore neighbor states up to max_depth
"""

from typing import Any, Dict, List, Optional

from src.cloud_backend.memgraph.memory.memory import Memory
from src.cloud_backend.memgraph.ontology.state import State
from src.cloud_backend.memgraph.reasoner.prompts.state_satisfaction_prompt import (
    StateSatisfactionInput,
    StateSatisfactionPrompt,
)
from src.cloud_backend.memgraph.reasoner.tools.task_tool import TaskTool, ToolResult


class RetrievalTool(TaskTool):
    """Tool for retrieving states and actions from memory."""

    def __init__(
        self,
        memory: Memory,
        llm_provider: Optional[Any] = None,
        embedding_service=None,
        max_depth: int = 3,
    ):
        """Initialize RetrievalTool.

        Args:
            memory: Memory instance.
            llm_provider: LLM provider (AnthropicProvider) for evaluation.
            embedding_service: Embedding service for vector search.
            max_depth: Maximum neighbor exploration depth.
        """
        super().__init__(
            name="retrieval",
            description="Retrieve states and actions from memory based on target",
        )
        self.memory = memory
        self.llm_provider = llm_provider
        self.embedding_service = embedding_service
        self.max_depth = max_depth
        self.satisfaction_prompt = StateSatisfactionPrompt()

    async def execute(
        self, target: str, parameters: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Execute retrieval for the target.

        Process:
        a. Use embedding to find states
        b. Use LLM to check if state satisfies target
        c. If not, explore neighbors up to max_depth
        d. Use LLM to evaluate satisfaction at each step

        Args:
            target: Target description.
            parameters: Optional parameters (top_k, max_depth override).

        Returns:
            ToolResult with states, actions, and reasoning.
        """
        # Get parameters
        params = parameters or {}
        top_k = params.get("top_k", 10)
        max_depth = params.get("max_depth", self.max_depth)

        # Step a: Find initial states using embedding
        initial_states = self._find_states_by_embedding(target, top_k)

        if not initial_states:
            return ToolResult(False, states=[], actions=[], reasoning="No states found in memory",
                metadata={"method": "embedding_search", "top_k": top_k},
            )

        # Step b: Check if initial state satisfies target
        for state in initial_states:
            if await self._check_satisfaction(target, [state]):
                return ToolResult(
                    True,
                    states=[state],
                    actions=[],
                    reasoning=f"State {state.id} directly satisfies target",
                    metadata={"method": "direct_match"},
                )

        # Step c: Explore neighbors
        best_state = initial_states[0]
        result = await self._explore_neighbors(target, best_state, max_depth)
        return result

    def _find_states_by_embedding(self, target: str, top_k: int = 10) -> List[State]:
        """Find states using embedding similarity."""
        if self.embedding_service:
            try:
                query_embedding = self.embedding_service.encode(target)
                return self.memory.state_manager.search_states_by_embedding(
                    query_embedding, top_k=top_k
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print(f"Embedding search failed: {exc}")

        # Fallback to listing states
        return self.memory.state_manager.list_states(limit=top_k)

    async def _check_satisfaction(self, target: str, states: List[State]) -> bool:
        """Check if states satisfy target using LLM."""
        if not self.llm_provider:
            # Rule-based fallback
            return len(states) > 0

        try:
            # Prepare input
            input_data = StateSatisfactionInput(
                target=target, states=[state.to_dict() for state in states]
            )

            # Build prompt
            prompt_text = self.satisfaction_prompt.build_prompt(input_data)
            system_prompt = self.satisfaction_prompt.get_system_prompt()

            # Call LLM using AnthropicProvider
            response = await self.llm_provider.generate_response(
                system_prompt=system_prompt,
                user_prompt=prompt_text
            )

            # Parse response
            output = self.satisfaction_prompt.parse_response(response)

            return output.satisfies

        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"LLM satisfaction check failed: {exc}")
            return False

    async def _explore_neighbors(
        self, target: str, initial_state: State, max_depth: int
    ) -> ToolResult:
        """Explore neighbors up to max_depth."""
        visited = set()
        queue = [(initial_state, 0, [], [])]  # (state, depth, path_states, path_actions)
        best_result = None

        while queue:
            current_state, depth, path_states, path_actions = queue.pop(0)

            if current_state.id in visited:
                continue
            visited.add(current_state.id)

            # Build current path
            current_path_states = path_states + [current_state]
            current_path_actions = path_actions

            # Check if current path satisfies target
            if await self._check_satisfaction(target, current_path_states):
                return ToolResult(True,
                    states=current_path_states,
                    actions=current_path_actions,
                    reasoning=f"Found satisfying path at depth {depth}",
                    metadata={"method": "neighbor_exploration", "depth": depth},
                )

            # Update best result if better
            if not best_result or len(current_path_states) > len(
                best_result.states
            ):
                best_result = ToolResult(False,
                    states=current_path_states,
                    actions=current_path_actions,
                    reasoning=f"Best path at depth {depth}",
                    metadata={"method": "neighbor_exploration", "depth": depth},
                )

            # Check depth limit
            if depth >= max_depth:
                continue

            # Get neighbors
            actions = self.memory.action_manager.list_actions(
                source_id=current_state.id
            )
            for action in actions:
                neighbor = self.memory.state_manager.get_state(action.target)
                if neighbor and neighbor.id not in visited:
                    queue.append(
                        (
                            neighbor,
                            depth + 1,
                            current_path_states,
                            current_path_actions + [action],
                        )
                    )

        # Return best result found (not satisfied but closest)
        return best_result or ToolResult(False,
            states=[initial_state],
            actions=[],
            reasoning="Max depth reached without satisfaction",
            metadata={"method": "neighbor_exploration", "max_depth": max_depth},
        )

    def get_optional_parameters(self) -> Dict[str, Any]:
        """Get optional parameters."""
        return {
            "top_k": 10,
            "max_depth": self.max_depth,
        }


__all__ = ["RetrievalTool"]
