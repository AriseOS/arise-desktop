#!/usr/bin/env python
"""Evaluate state embedding text strategies for memory retrieval.

Compares two state text strategies:
1. structured: semantic_v1.retrieval_text (fallback to semantic desc / description)
2. description: natural description field (fallback to semantic desc / title / url)
3. hybrid_dual_channel: weighted fusion of description and structured similarity

Default query set is auto-built from CognitivePhrase entries:
- query: phrase.description (configurable)
- positives: phrase.state_path

You can also provide a custom JSONL dataset with fields:
- query: str (required)
- positive_state_ids: list[str] (required)
- id: str (optional)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LOGGER = logging.getLogger("eval_state_embedding_ab")


@dataclass
class QuerySample:
    sample_id: str
    query: str
    positive_state_ids: List[str]
    source: str


@dataclass
class VariantIndex:
    name: str
    state_ids: List[str]
    state_vectors: List[List[float]]
    available_state_id_set: Set[str]


@dataclass
class RankedState:
    state_id: str
    score: float


@dataclass
class HybridVariantIndex:
    name: str
    state_ids: List[str]
    description_vector_by_state: Dict[str, List[float]]
    structured_vector_by_state: Dict[str, List[float]]
    weight_description: float
    weight_structured: float


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _candidate_ami_settings_paths() -> List[Path]:
    paths: List[Path] = []

    env_path = _safe_text(os.getenv("AMI_SETTINGS_PATH"))
    if env_path:
        paths.append(Path(env_path).expanduser())

    appdata = _safe_text(os.getenv("APPDATA"))
    if appdata:
        paths.append(Path(appdata) / "com.ami.desktop" / ".ami-settings.dat")

    home = Path.home()
    paths.extend(
        [
            home / "AppData" / "Roaming" / "com.ami.desktop" / ".ami-settings.dat",
            home / ".config" / "com.ami.desktop" / ".ami-settings.dat",
            home / ".ami-settings.dat",
        ]
    )

    unique: List[Path] = []
    seen: Set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _load_user_api_key_from_ami_settings(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        LOGGER.debug("Failed to parse Ami settings file %s: %s", path, exc)
        return ""

    return _safe_text(data.get("user_api_key"))


def _resolve_effective_embedding_api_key(explicit_key: str) -> str:
    key = _safe_text(explicit_key)
    if key:
        return key

    for path in _candidate_ami_settings_paths():
        key = _load_user_api_key_from_ami_settings(path)
        if key:
            LOGGER.info("Loaded embedding API key from Ami settings: %s", path)
            return key

    return ""


def _state_text_structured(state: Any) -> str:
    attrs = state.attributes if isinstance(state.attributes, dict) else {}
    semantic = attrs.get("semantic_v1")
    if isinstance(semantic, dict):
        retrieval_text = _safe_text(semantic.get("retrieval_text"))
        if retrieval_text:
            return retrieval_text[:320]
        semantic_desc = _safe_text(semantic.get("description"))
        if semantic_desc:
            return semantic_desc[:240]

    desc = _safe_text(state.description)
    if desc:
        return desc[:240]

    title = _safe_text(state.page_title)
    if title:
        return title[:120]
    return _safe_text(state.page_url)[:240]


def _state_text_description(state: Any) -> str:
    desc = _safe_text(state.description)
    if desc:
        return desc[:240]

    attrs = state.attributes if isinstance(state.attributes, dict) else {}
    semantic = attrs.get("semantic_v1")
    if isinstance(semantic, dict):
        semantic_desc = _safe_text(semantic.get("description"))
        if semantic_desc:
            return semantic_desc[:240]

    title = _safe_text(state.page_title)
    if title:
        return title[:120]
    return _safe_text(state.page_url)[:240]


def _cosine_similarity(vec1: Sequence[float], vec2: Sequence[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return -1.0
    dot = 0.0
    norm1 = 0.0
    norm2 = 0.0
    for a, b in zip(vec1, vec2):
        dot += a * b
        norm1 += a * a
        norm2 += b * b
    if norm1 <= 0.0 or norm2 <= 0.0:
        return -1.0
    return dot / math.sqrt(norm1 * norm2)


def _parse_topk(value: str) -> List[int]:
    result: List[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        k = int(part)
        if k > 0:
            result.append(k)
    unique_sorted = sorted(set(result))
    if not unique_sorted:
        raise ValueError("top_k list is empty")
    return unique_sorted


def _phrase_query_text(phrase: Any, field: str) -> str:
    if field == "description":
        return _safe_text(phrase.description)
    if field == "label":
        return _safe_text(getattr(phrase, "label", "")) or _safe_text(phrase.description)
    if field == "semantic_retrieval_text":
        semantic = phrase.semantic if isinstance(phrase.semantic, dict) else {}
        return _safe_text(semantic.get("retrieval_text")) or _safe_text(phrase.description)
    return _safe_text(phrase.description)


def _init_memory_service(args: argparse.Namespace) -> MemoryService:
    from src.common.memory.memory_service import (
        MemoryService,
        MemoryServiceConfig,
        get_private_memory,
        get_public_memory,
        init_memory_services,
    )

    config = MemoryServiceConfig(
        graph_backend=args.graph_backend,
        graph_url=args.graph_url,
        graph_namespace=args.graph_namespace,
        graph_database=args.graph_database,
        graph_username=args.graph_username,
        graph_password=args.graph_password,
        vector_dimensions=args.embedding_dimension,
        embedding_provider=args.embedding_provider,
        embedding_model=args.embedding_model,
        embedding_api_url=args.embedding_base_url,
        embedding_api_key=args.embedding_api_key,
        embedding_dimension=args.embedding_dimension,
    )

    if args.memory_scope == "database":
        service = MemoryService(config)
        service.initialize()
        return service

    init_memory_services(config)
    if args.memory_scope == "private":
        if not args.user_id:
            raise ValueError("--user-id is required when --memory-scope=private")
        return get_private_memory(args.user_id)
    return get_public_memory()


def _load_states(service: MemoryService, state_limit: Optional[int]) -> List[Any]:
    states = service.workflow_memory.state_manager.list_states(limit=state_limit)
    LOGGER.info("Loaded states: %d", len(states))
    return states


def _load_phrase_samples(
    service: MemoryService,
    query_field: str,
    max_queries: Optional[int],
) -> List[QuerySample]:
    phrases = service.workflow_memory.phrase_manager.list_phrases(limit=max_queries)
    samples: List[QuerySample] = []
    for idx, phrase in enumerate(phrases, 1):
        query = _phrase_query_text(phrase, query_field)
        positives = [sid for sid in phrase.state_path if _safe_text(sid)]
        if not query or not positives:
            continue
        sample_id = _safe_text(getattr(phrase, "id", "")) or f"phrase_{idx}"
        samples.append(
            QuerySample(
                sample_id=sample_id,
                query=query,
                positive_state_ids=positives,
                source="cognitive_phrase",
            )
        )
    LOGGER.info("Built phrase-based samples: %d", len(samples))
    return samples


def _load_custom_samples(path: Path, max_queries: Optional[int]) -> List[QuerySample]:
    samples: List[QuerySample] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            query = _safe_text(data.get("query"))
            positives: List[str] = []
            if isinstance(data.get("positive_state_ids"), list):
                positives = [_safe_text(x) for x in data["positive_state_ids"] if _safe_text(x)]
            elif _safe_text(data.get("positive_state_id")):
                positives = [_safe_text(data.get("positive_state_id"))]

            if not query or not positives:
                continue

            sample_id = _safe_text(data.get("id")) or f"custom_{i}"
            source = _safe_text(data.get("source")) or "custom"
            samples.append(
                QuerySample(
                    sample_id=sample_id,
                    query=query,
                    positive_state_ids=positives,
                    source=source,
                )
            )
            if max_queries and len(samples) >= max_queries:
                break
    LOGGER.info("Loaded custom samples: %d", len(samples))
    return samples


def _build_embedding_service(args: argparse.Namespace) -> EmbeddingService:
    from src.common.memory.services.embedding_service import EmbeddingService

    if not args.embedding_api_key and args.embedding_provider != "local_bge":
        raise ValueError(
            "Embedding API key missing. Set --embedding-api-key or env EMBEDDING_API_KEY/SILICONFLOW_API_KEY."
        )
    service = EmbeddingService(
        api_key=args.embedding_api_key or "local",
        base_url=args.embedding_base_url,
        model=args.embedding_model,
        dimension=args.embedding_dimension,
        provider=args.embedding_provider,
    )
    return service


def _embed_texts(
    embedding_service: EmbeddingService,
    texts: Iterable[str],
    batch_size: int,
) -> Dict[str, List[float]]:
    unique_texts = list(dict.fromkeys(t for t in texts if _safe_text(t)))
    result: Dict[str, List[float]] = {}
    LOGGER.info("Embedding unique texts: %d", len(unique_texts))

    for start in range(0, len(unique_texts), batch_size):
        batch = unique_texts[start : start + batch_size]
        vectors = embedding_service.embed_batch(batch)
        if vectors is None or len(vectors) != len(batch):
            raise RuntimeError("Embedding batch failed or returned unexpected size")
        for text, vec in zip(batch, vectors):
            result[text] = vec
    return result


def _prepare_variant_index(
    name: str,
    states: Sequence[Any],
    state_text_fn,
    text_to_vec: Dict[str, List[float]],
) -> VariantIndex:
    state_ids: List[str] = []
    state_vectors: List[List[float]] = []
    for state in states:
        state_id = _safe_text(getattr(state, "id", ""))
        if not state_id:
            continue
        text = state_text_fn(state)
        vec = text_to_vec.get(text)
        if vec is None:
            continue
        state_ids.append(state_id)
        state_vectors.append(vec)
    return VariantIndex(
        name=name,
        state_ids=state_ids,
        state_vectors=state_vectors,
        available_state_id_set=set(state_ids),
    )


def _normalize_hybrid_weights(
    weight_description: float,
    weight_structured: float,
) -> Tuple[float, float]:
    if weight_description < 0 or weight_structured < 0:
        raise ValueError("Hybrid weights must be >= 0")

    total = weight_description + weight_structured
    if total <= 0:
        raise ValueError("At least one hybrid weight must be > 0")

    return weight_description / total, weight_structured / total


def _variant_to_vector_map(variant: VariantIndex) -> Dict[str, List[float]]:
    return {sid: vec for sid, vec in zip(variant.state_ids, variant.state_vectors)}


def _prepare_hybrid_index(
    variant_structured: VariantIndex,
    variant_description: VariantIndex,
    weight_description: float,
    weight_structured: float,
) -> HybridVariantIndex:
    description_map = _variant_to_vector_map(variant_description)
    structured_map = _variant_to_vector_map(variant_structured)
    state_ids = sorted(set(description_map.keys()) | set(structured_map.keys()))

    return HybridVariantIndex(
        name="hybrid_dual_channel",
        state_ids=state_ids,
        description_vector_by_state=description_map,
        structured_vector_by_state=structured_map,
        weight_description=weight_description,
        weight_structured=weight_structured,
    )


def _hybrid_score_for_state(
    query_vec: Sequence[float],
    state_id: str,
    hybrid_index: HybridVariantIndex,
) -> Optional[float]:
    desc_vec = hybrid_index.description_vector_by_state.get(state_id)
    struct_vec = hybrid_index.structured_vector_by_state.get(state_id)

    desc_score: Optional[float] = None
    struct_score: Optional[float] = None

    if desc_vec is not None:
        desc_score = _cosine_similarity(query_vec, desc_vec)
    if struct_vec is not None:
        struct_score = _cosine_similarity(query_vec, struct_vec)

    if desc_score is not None and struct_score is not None:
        return (
            hybrid_index.weight_description * desc_score
            + hybrid_index.weight_structured * struct_score
        )
    if desc_score is not None:
        return desc_score
    if struct_score is not None:
        return struct_score
    return None


def _evaluate_variant(
    variant: VariantIndex,
    samples: Sequence[QuerySample],
    query_vec_map: Dict[str, List[float]],
    top_ks: Sequence[int],
) -> Dict[str, Any]:
    max_k = max(top_ks)
    total = len(samples)
    used = 0
    skipped_no_query_vec = 0
    skipped_no_positive_in_index = 0
    mrr_sum = 0.0
    hit_counts = {k: 0 for k in top_ks}
    per_query: List[Dict[str, Any]] = []

    for sample in samples:
        q_vec = query_vec_map.get(sample.query)
        if q_vec is None:
            skipped_no_query_vec += 1
            continue

        positives = set(sample.positive_state_ids)
        positives_in_index = positives & variant.available_state_id_set
        if not positives_in_index:
            skipped_no_positive_in_index += 1
            continue

        scored: List[Tuple[str, float]] = []
        for sid, s_vec in zip(variant.state_ids, variant.state_vectors):
            scored.append((sid, _cosine_similarity(q_vec, s_vec)))
        scored.sort(key=lambda x: x[1], reverse=True)

        used += 1
        best_rank = None
        best_score = None
        for rank, (sid, score) in enumerate(scored, 1):
            if sid in positives_in_index:
                best_rank = rank
                best_score = score
                break

        if best_rank is not None:
            mrr_sum += 1.0 / best_rank
            for k in top_ks:
                if best_rank <= k:
                    hit_counts[k] += 1

        top_candidates = [
            {"state_id": sid, "score": round(score, 6)}
            for sid, score in scored[:max_k]
        ]
        per_query.append(
            {
                "sample_id": sample.sample_id,
                "query": sample.query,
                "source": sample.source,
                "positive_state_ids": sample.positive_state_ids,
                "positive_state_ids_in_index": sorted(positives_in_index),
                "best_positive_rank": best_rank,
                "best_positive_score": round(best_score, 6) if best_score is not None else None,
                "top_candidates": top_candidates,
            }
        )

    metrics = {
        "variant": variant.name,
        "total_samples": total,
        "used_samples": used,
        "skipped_no_query_vec": skipped_no_query_vec,
        "skipped_no_positive_in_index": skipped_no_positive_in_index,
        "mrr": (mrr_sum / used) if used else 0.0,
    }
    for k in top_ks:
        metrics[f"hit@{k}"] = (hit_counts[k] / used) if used else 0.0
        metrics[f"hit_count@{k}"] = hit_counts[k]
    return {"metrics": metrics, "per_query": per_query}


def _evaluate_hybrid_variant(
    hybrid_index: HybridVariantIndex,
    samples: Sequence[QuerySample],
    query_vec_map: Dict[str, List[float]],
    top_ks: Sequence[int],
) -> Dict[str, Any]:
    max_k = max(top_ks)
    total = len(samples)
    used = 0
    skipped_no_query_vec = 0
    skipped_no_positive_in_index = 0
    mrr_sum = 0.0
    hit_counts = {k: 0 for k in top_ks}
    per_query: List[Dict[str, Any]] = []

    available_state_id_set = set(hybrid_index.state_ids)

    for sample in samples:
        q_vec = query_vec_map.get(sample.query)
        if q_vec is None:
            skipped_no_query_vec += 1
            continue

        positives = set(sample.positive_state_ids)
        positives_in_index = positives & available_state_id_set
        if not positives_in_index:
            skipped_no_positive_in_index += 1
            continue

        scored: List[Tuple[str, float]] = []
        for sid in hybrid_index.state_ids:
            score = _hybrid_score_for_state(
                query_vec=q_vec,
                state_id=sid,
                hybrid_index=hybrid_index,
            )
            if score is None:
                continue
            scored.append((sid, score))
        scored.sort(key=lambda x: x[1], reverse=True)

        used += 1
        best_rank = None
        best_score = None
        for rank, (sid, score) in enumerate(scored, 1):
            if sid in positives_in_index:
                best_rank = rank
                best_score = score
                break

        if best_rank is not None:
            mrr_sum += 1.0 / best_rank
            for k in top_ks:
                if best_rank <= k:
                    hit_counts[k] += 1

        top_candidates = [
            {"state_id": sid, "score": round(score, 6)}
            for sid, score in scored[:max_k]
        ]
        per_query.append(
            {
                "sample_id": sample.sample_id,
                "query": sample.query,
                "source": sample.source,
                "positive_state_ids": sample.positive_state_ids,
                "positive_state_ids_in_index": sorted(positives_in_index),
                "best_positive_rank": best_rank,
                "best_positive_score": round(best_score, 6)
                if best_score is not None
                else None,
                "top_candidates": top_candidates,
            }
        )

    metrics = {
        "variant": hybrid_index.name,
        "total_samples": total,
        "used_samples": used,
        "skipped_no_query_vec": skipped_no_query_vec,
        "skipped_no_positive_in_index": skipped_no_positive_in_index,
        "mrr": (mrr_sum / used) if used else 0.0,
    }
    for k in top_ks:
        metrics[f"hit@{k}"] = (hit_counts[k] / used) if used else 0.0
        metrics[f"hit_count@{k}"] = hit_counts[k]
    return {"metrics": metrics, "per_query": per_query}


def _rank_states_for_query(
    query_vec: Sequence[float],
    variant: VariantIndex,
    top_k: int,
) -> List[RankedState]:
    scored: List[RankedState] = []
    for sid, s_vec in zip(variant.state_ids, variant.state_vectors):
        scored.append(RankedState(state_id=sid, score=_cosine_similarity(query_vec, s_vec)))
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]


def _rank_states_for_query_hybrid(
    query_vec: Sequence[float],
    hybrid_index: HybridVariantIndex,
    top_k: int,
) -> List[RankedState]:
    scored: List[RankedState] = []
    for sid in hybrid_index.state_ids:
        score = _hybrid_score_for_state(
            query_vec=query_vec,
            state_id=sid,
            hybrid_index=hybrid_index,
        )
        if score is None:
            continue
        scored.append(RankedState(state_id=sid, score=score))
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]


def _state_preview(state: Any) -> Dict[str, str]:
    return {
        "id": _safe_text(getattr(state, "id", "")),
        "title": _safe_text(getattr(state, "page_title", "")),
        "url": _safe_text(getattr(state, "page_url", "")),
        "description": _safe_text(getattr(state, "description", ""))[:160],
    }


def _print_search_result(
    query: str,
    variant_structured: VariantIndex,
    variant_description: VariantIndex,
    variant_hybrid: HybridVariantIndex,
    state_by_id: Dict[str, Any],
    embedding_service: EmbeddingService,
    top_k: int,
) -> None:
    query = _safe_text(query)
    if not query:
        return

    q_vec = embedding_service.encode(query)
    if not q_vec:
        print("Query embedding failed, skipped.")
        return

    print(f"\n=== Query: {query} ===")

    hybrid_label = (
        f"{variant_hybrid.name} "
        f"(description={variant_hybrid.weight_description:.2f}, "
        f"structured={variant_hybrid.weight_structured:.2f})"
    )

    search_variants: List[Tuple[str, List[RankedState]]] = [
        (
            variant_structured.name,
            _rank_states_for_query(q_vec, variant_structured, top_k=top_k),
        ),
        (
            variant_description.name,
            _rank_states_for_query(q_vec, variant_description, top_k=top_k),
        ),
        (
            hybrid_label,
            _rank_states_for_query_hybrid(q_vec, variant_hybrid, top_k=top_k),
        ),
    ]

    for label, ranked in search_variants:
        print(f"\n[{label}] top-{top_k}")
        if not ranked:
            print("(no results)")
            continue
        for idx, item in enumerate(ranked, 1):
            state = state_by_id.get(item.state_id)
            preview = _state_preview(state) if state is not None else {
                "id": item.state_id,
                "title": "",
                "url": "",
                "description": "",
            }
            print(
                f"{idx:02d}. score={item.score:.6f} "
                f"id={preview['id']} "
                f"title={preview['title'] or '-'} "
                f"url={preview['url'] or '-'}"
            )
            if preview["description"]:
                print(f"    desc={preview['description']}")


def _run_search_mode(
    args: argparse.Namespace,
    states: Sequence[Any],
    embedding_service: EmbeddingService,
) -> None:
    top_k = max(1, args.search_top_k)

    structured_texts = [_state_text_structured(s) for s in states]
    description_texts = [_state_text_description(s) for s in states]
    all_texts = list(structured_texts) + list(description_texts)
    text_to_vec = _embed_texts(embedding_service, all_texts, batch_size=args.batch_size)

    variant_structured = _prepare_variant_index(
        name="structured_semantic_v1",
        states=states,
        state_text_fn=_state_text_structured,
        text_to_vec=text_to_vec,
    )
    variant_description = _prepare_variant_index(
        name="description_natural_sentence",
        states=states,
        state_text_fn=_state_text_description,
        text_to_vec=text_to_vec,
    )
    variant_hybrid = _prepare_hybrid_index(
        variant_structured=variant_structured,
        variant_description=variant_description,
        weight_description=args.hybrid_weight_description,
        weight_structured=args.hybrid_weight_structured,
    )
    state_by_id = {
        _safe_text(getattr(state, "id", "")): state for state in states if _safe_text(getattr(state, "id", ""))
    }

    predefined_queries = [_safe_text(q) for q in args.query_text if _safe_text(q)]
    for query in predefined_queries:
        _print_search_result(
            query=query,
            variant_structured=variant_structured,
            variant_description=variant_description,
            variant_hybrid=variant_hybrid,
            state_by_id=state_by_id,
            embedding_service=embedding_service,
            top_k=top_k,
        )

    if not args.interactive and predefined_queries:
        return

    print("\nInteractive mode enabled. Enter a query and press Enter. Use q/quit/exit to stop.")
    while True:
        try:
            query = input("query> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExit.")
            return
        if query.lower() in {"q", "quit", "exit"}:
            print("Exit.")
            return
        if not query:
            continue
        _print_search_result(
            query=query,
            variant_structured=variant_structured,
            variant_description=variant_description,
            variant_hybrid=variant_hybrid,
            state_by_id=state_by_id,
            embedding_service=embedding_service,
            top_k=top_k,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate state embedding text strategy: structured vs description vs hybrid."
    )
    parser.add_argument("--memory-scope", choices=["private", "public", "database"], default="private")
    parser.add_argument("--user-id", default="")

    parser.add_argument("--graph-backend", default="surrealdb")
    parser.add_argument("--graph-url", default=os.getenv("SURREALDB_URL", "ws://127.0.0.1:8000/rpc"))
    parser.add_argument("--graph-namespace", default=os.getenv("SURREALDB_NAMESPACE", "ami"))
    parser.add_argument("--graph-database", default=os.getenv("SURREALDB_DATABASE", "memory"))
    parser.add_argument("--graph-username", default=os.getenv("SURREALDB_USER", "root"))
    parser.add_argument("--graph-password", default=os.getenv("SURREALDB_PASSWORD", "root"))

    parser.add_argument("--embedding-provider", choices=["openai", "local_bge"], default="openai")
    parser.add_argument(
        "--embedding-base-url",
        default=os.getenv("EMBEDDING_BASE_URL", "https://api.ariseos.com/openai/v1"),
    )
    parser.add_argument("--embedding-model", default=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"))
    parser.add_argument("--embedding-dimension", type=int, default=int(os.getenv("EMBEDDING_DIMENSION", "1024")))
    parser.add_argument(
        "--embedding-api-key",
        default=os.getenv("EMBEDDING_API_KEY", os.getenv("SILICONFLOW_API_KEY", "")),
        help=(
            "Embedding API key. If omitted, script auto-loads user_api_key from Ami settings "
            "(e.g. %%APPDATA%%/com.ami.desktop/.ami-settings.dat)."
        ),
    )

    parser.add_argument("--mode", choices=["evaluate", "search"], default="evaluate")

    parser.add_argument("--query-source", choices=["phrases", "custom"], default="phrases")
    parser.add_argument("--query-file", default="")
    parser.add_argument(
        "--phrase-query-field",
        choices=["description", "semantic_retrieval_text", "label"],
        default="description",
    )
    parser.add_argument(
        "--query-text",
        action="append",
        default=[],
        help="Manual query text. Can be passed multiple times. Used by --mode=search.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable interactive query loop in --mode=search.",
    )

    parser.add_argument("--max-queries", type=int, default=0)
    parser.add_argument("--state-limit", type=int, default=0)
    parser.add_argument("--top-ks", default="1,3,5,10")
    parser.add_argument("--search-top-k", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--hybrid-weight-description",
        type=float,
        default=0.7,
        help="Hybrid score weight for description channel.",
    )
    parser.add_argument(
        "--hybrid-weight-structured",
        type=float,
        default=0.3,
        help="Hybrid score weight for structured retrieval_text channel.",
    )

    parser.add_argument("--output-json", default="")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    top_ks = _parse_topk(args.top_ks)
    max_queries = args.max_queries if args.max_queries > 0 else None
    state_limit = args.state_limit if args.state_limit > 0 else None
    (
        args.hybrid_weight_description,
        args.hybrid_weight_structured,
    ) = _normalize_hybrid_weights(
        args.hybrid_weight_description,
        args.hybrid_weight_structured,
    )
    args.embedding_api_key = _resolve_effective_embedding_api_key(args.embedding_api_key)

    service = _init_memory_service(args)
    states = _load_states(service, state_limit=state_limit)
    if not states:
        raise RuntimeError("No states found in memory.")

    embedding_service = _build_embedding_service(args)

    if args.mode == "search":
        _run_search_mode(args=args, states=states, embedding_service=embedding_service)
        return

    if args.query_source == "custom":
        if not args.query_file:
            raise ValueError("--query-file is required when --query-source=custom")
        samples = _load_custom_samples(Path(args.query_file), max_queries=max_queries)
    else:
        samples = _load_phrase_samples(
            service=service,
            query_field=args.phrase_query_field,
            max_queries=max_queries,
        )
    if not samples:
        raise RuntimeError("No query samples available.")

    structured_texts = [_state_text_structured(s) for s in states]
    description_texts = [_state_text_description(s) for s in states]
    query_texts = [s.query for s in samples]
    all_texts = list(structured_texts) + list(description_texts) + list(query_texts)
    text_to_vec = _embed_texts(embedding_service, all_texts, batch_size=args.batch_size)

    variant_structured = _prepare_variant_index(
        name="structured_semantic_v1",
        states=states,
        state_text_fn=_state_text_structured,
        text_to_vec=text_to_vec,
    )
    variant_description = _prepare_variant_index(
        name="description_natural_sentence",
        states=states,
        state_text_fn=_state_text_description,
        text_to_vec=text_to_vec,
    )
    variant_hybrid = _prepare_hybrid_index(
        variant_structured=variant_structured,
        variant_description=variant_description,
        weight_description=args.hybrid_weight_description,
        weight_structured=args.hybrid_weight_structured,
    )
    query_vec_map = {sample.query: text_to_vec.get(sample.query) for sample in samples}

    result_a = _evaluate_variant(variant_structured, samples, query_vec_map, top_ks)
    result_b = _evaluate_variant(variant_description, samples, query_vec_map, top_ks)
    result_h = _evaluate_hybrid_variant(variant_hybrid, samples, query_vec_map, top_ks)

    summary = {
        "config": {
            "memory_scope": args.memory_scope,
            "user_id": args.user_id,
            "graph_backend": args.graph_backend,
            "graph_url": args.graph_url,
            "graph_namespace": args.graph_namespace,
            "graph_database": args.graph_database,
            "query_source": args.query_source,
            "phrase_query_field": args.phrase_query_field,
            "top_ks": top_ks,
            "sample_count": len(samples),
            "state_count": len(states),
            "hybrid_weight_description": args.hybrid_weight_description,
            "hybrid_weight_structured": args.hybrid_weight_structured,
        },
        "variants": {
            result_a["metrics"]["variant"]: result_a["metrics"],
            result_b["metrics"]["variant"]: result_b["metrics"],
            result_h["metrics"]["variant"]: result_h["metrics"],
        },
        "delta": {},
        "delta_hybrid_vs_description": {},
        "delta_hybrid_vs_structured": {},
    }

    for k in ["mrr"] + [f"hit@{x}" for x in top_ks]:
        structured_value = summary["variants"]["structured_semantic_v1"][k]
        description_value = summary["variants"]["description_natural_sentence"][k]
        hybrid_value = summary["variants"][variant_hybrid.name][k]

        summary["delta"][k] = structured_value - description_value
        summary["delta_hybrid_vs_description"][k] = hybrid_value - description_value
        summary["delta_hybrid_vs_structured"][k] = hybrid_value - structured_value

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.output_json:
        output = {
            "summary": summary,
            "per_query": {
                "structured_semantic_v1": result_a["per_query"],
                "description_natural_sentence": result_b["per_query"],
                variant_hybrid.name: result_h["per_query"],
            },
        }
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.info("Wrote detailed report: %s", output_path)


if __name__ == "__main__":
    main()
