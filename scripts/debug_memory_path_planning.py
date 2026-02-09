#!/usr/bin/env python3
"""Debug script for L2 path planning internals.

This script shows:
1) The recalled subgraph (states/actions) that will be sent to LLM
2) The exact user prompt content for path planning
3) The raw JSON result returned by LLM
4) The resolved path (states + actions) after validation

Usage:
    python scripts/debug_memory_path_planning.py
    python scripts/debug_memory_path_planning.py --task "Collect Product Hunt weekly products"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Ensure imports work for both `src` and cloud backend `main.py`
ROOT = Path(__file__).resolve().parents[1]
CLOUD_BACKEND_DIR = ROOT / "src" / "cloud_backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CLOUD_BACKEND_DIR))

from main import _get_reasoner_for_user, config_service  # type: ignore  # noqa: E402
from src.common.memory.memory_service import (  # noqa: E402
    MemoryServiceConfig,
    init_memory_services,
)
from src.common.memory.ontology.action import Action  # noqa: E402
from src.common.memory.ontology.state import State  # noqa: E402
from src.common.memory.reasoner.prompts.path_planning_prompt import (  # noqa: E402
    PATH_PLANNING_SYSTEM_PROMPT,
    build_path_planning_user_prompt,
)


# -----------------------------------------------------------------------------
# Configuration defaults (can be overridden by CLI args)
# -----------------------------------------------------------------------------
API_KEY = "ami_19f03b13b96dbfa078ef14a60fcb2e60003378e3a4af7c0bdad7aae0dd1c9803"
USER_ID = "Primary"
EXAMPLE_TASK = "收集 Product Hunt 周榜产品信息"

_MEMORY_SERVICES_READY = False


def _mask_key(value: str) -> str:
    value = (value or "").strip()
    if len(value) <= 12:
        return value
    return f"{value[:8]}...{value[-4:]}"


def _state_line(state: State) -> str:
    desc = (state.description or state.page_title or state.page_url or "").strip()
    return f"{state.id[:8]} | {desc} | {state.page_url}"


def _action_line(action: Action) -> str:
    desc = (action.description or action.type or "navigate").strip()
    return f"{action.source[:8]} -> {action.target[:8]} | {desc}"


def _print_title(text: str) -> None:
    print("\n" + "=" * 88)
    print(text)
    print("=" * 88)


def _build_alias_maps(states: List[State]) -> Tuple[Dict[str, str], Dict[str, str]]:
    alias_by_id = {state.id: f"s{idx + 1}" for idx, state in enumerate(states)}
    id_by_alias = {alias: state_id for state_id, alias in alias_by_id.items()}
    return alias_by_id, id_by_alias


def _ensure_memory_services_initialized() -> None:
    global _MEMORY_SERVICES_READY
    if _MEMORY_SERVICES_READY:
        return

    graph_config = config_service.get("graph_store", {})
    memory_config = config_service.get("memory", {})

    base_config = MemoryServiceConfig(
        graph_backend=graph_config.get("backend", "surrealdb"),
        graph_url=graph_config.get("url") or os.getenv("SURREALDB_URL", "ws://localhost:8000/rpc"),
        graph_namespace=graph_config.get("namespace") or os.getenv("SURREALDB_NAMESPACE", "ami"),
        graph_database="public",
        graph_username=graph_config.get("username") or os.getenv("SURREALDB_USER", "root"),
        graph_password=graph_config.get("password") or os.getenv("SURREALDB_PASSWORD", ""),
        vector_dimensions=graph_config.get("vector_dimensions", 1024),
        intent_sequence_dedup_threshold=memory_config.get("intent_sequence_dedup_threshold"),
    )
    init_memory_services(base_config)
    _MEMORY_SERVICES_READY = True


async def debug_l2_path_planning(
    api_key: str,
    user_id: str,
    task: str,
    use_public: bool = False,
    top_k: Optional[int] = None,
    min_score: Optional[float] = None,
    show_full_prompt: bool = False,
) -> None:
    if not api_key.strip():
        raise ValueError("API key is empty. Set API_KEY or pass --api-key.")
    if not use_public and not user_id.strip():
        raise ValueError("user_id is empty. Set USER_ID or pass --user-id.")

    _ensure_memory_services_initialized()

    reasoner = await _get_reasoner_for_user(
        x_ami_api_key=api_key,
        user_id=None if use_public else user_id,
        use_public=use_public,
    )

    if not reasoner.llm_provider or not reasoner.embedding_service:
        raise RuntimeError("Reasoner missing llm_provider or embedding_service")

    effective_top_k = top_k if (top_k and top_k > 0) else reasoner.path_planning_top_k
    effective_min_score = (
        float(min_score) if min_score is not None else reasoner.path_planning_min_score
    )

    _print_title("Config")
    print(f"user_id: {user_id if not use_public else '(public memory)'}")
    print(f"api_key: {_mask_key(api_key)}")
    print(f"task: {task}")
    print(f"candidate_top_k: {effective_top_k}")
    print(f"min_score: {effective_min_score}")
    print(f"max_states: {reasoner.path_planning_max_states}")
    print(f"max_actions: {reasoner.path_planning_max_actions}")

    query_vector = reasoner.embedding_service.encode(task)
    if not query_vector:
        _print_title("Embedding")
        print("No embedding generated for task.")
        return

    raw_candidates = reasoner.memory.state_manager.search_states_by_embedding(
        query_vector=query_vector,
        top_k=max(1, effective_top_k),
    )
    scored_candidates = [(s, sc) for s, sc in raw_candidates if sc >= effective_min_score]

    _print_title("Embedding Candidates")
    if not scored_candidates:
        print("No states above threshold.")
        return
    for idx, (state, score) in enumerate(scored_candidates, 1):
        print(f"{idx:>2}. score={score:.4f} | {_state_line(state)}")

    candidate_states, subgraph_actions, score_by_state_id = reasoner._build_path_planning_subgraph(
        scored_candidates=scored_candidates,
        max_states=reasoner.path_planning_max_states,
        max_actions=reasoner.path_planning_max_actions,
    )

    if not candidate_states:
        _print_title("Subgraph")
        print("No candidate states after subgraph building.")
        return

    alias_by_id, id_by_alias = _build_alias_maps(candidate_states)
    state_map = {state.id: state for state in candidate_states}
    action_by_pair: Dict[tuple[str, str], Action] = {}
    for action in subgraph_actions:
        if action.source and action.target:
            action_by_pair[(action.source, action.target)] = action

    states_text = reasoner._format_path_planning_states_text(
        states=candidate_states,
        alias_by_id=alias_by_id,
    )
    actions_text = reasoner._format_path_planning_actions_text(
        actions=subgraph_actions,
        alias_by_id=alias_by_id,
    )

    _print_title("Subgraph Sent To LLM")
    print("## Task")
    print(task)
    print("\n## States")
    print(states_text)
    print("\n## Actions")
    print(actions_text)

    user_prompt = build_path_planning_user_prompt(
        task=task,
        states_text=states_text,
        actions_text=actions_text,
    )
    if show_full_prompt:
        _print_title("Full Prompt (System + User)")
        print("[System Prompt]")
        print(PATH_PLANNING_SYSTEM_PROMPT)
        print("\n[User Prompt]")
        print(user_prompt)

    planner_result = await reasoner.llm_provider.generate_json_response(
        system_prompt=PATH_PLANNING_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    _print_title("LLM Raw JSON Result")
    print(json.dumps(planner_result, ensure_ascii=False, indent=2))

    planned_state_ids = reasoner._resolve_planned_path_ids(
        planner_result=planner_result,
        id_by_alias=id_by_alias,
        state_map=state_map,
    )
    planned_actions = reasoner._validate_planned_path(
        state_ids=planned_state_ids,
        action_by_pair=action_by_pair,
    ) if planned_state_ids else None

    _print_title("Resolved Path")
    if not planned_state_ids:
        print("No valid path resolved from LLM output.")
        return
    if planned_actions is None:
        print("Path IDs resolved, but edge validation failed.")
        print("Resolved IDs:", planned_state_ids)
        return

    print("State path IDs:", " -> ".join(planned_state_ids))
    print("\nStates:")
    for idx, state_id in enumerate(planned_state_ids, 1):
        state = state_map[state_id]
        score = score_by_state_id.get(state_id, 0.0)
        alias = alias_by_id.get(state_id, state_id)
        print(f"  {idx}. [{alias}] score={score:.4f} | {_state_line(state)}")

    print("\nActions:")
    if not planned_actions:
        print("  (single-state path)")
    else:
        for idx, action in enumerate(planned_actions, 1):
            print(f"  {idx}. {_action_line(action)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Debug L2 path planning subgraph and LLM path output.")
    parser.add_argument("--api-key", default=API_KEY, help="X-Ami-API-Key value")
    parser.add_argument("--user-id", default=USER_ID, help="User id / username")
    parser.add_argument("--task", default=EXAMPLE_TASK, help="Task description")
    parser.add_argument("--use-public", action="store_true", help="Use public memory instead of private")
    parser.add_argument("--top-k", type=int, default=None, help="Override candidate top_k")
    parser.add_argument("--min-score", type=float, default=None, help="Override candidate min_score")
    parser.add_argument("--show-full-prompt", action="store_true", help="Print full system+user prompts")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    await debug_l2_path_planning(
        api_key=args.api_key,
        user_id=args.user_id,
        task=args.task,
        use_public=args.use_public,
        top_k=args.top_k,
        min_score=args.min_score,
        show_full_prompt=args.show_full_prompt,
    )


if __name__ == "__main__":
    asyncio.run(main())
