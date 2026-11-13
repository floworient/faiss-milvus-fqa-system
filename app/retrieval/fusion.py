from collections.abc import Sequence

from app.retrieval.keyword import RankedChunk


def reciprocal_rank_fusion(
    result_sets: Sequence[Sequence[RankedChunk]], k: int = 60
) -> list[RankedChunk]:
    if k < 0:
        raise ValueError("k must be non-negative")
    merged: dict[str, dict[str, object]] = {}
    for result_set in result_sets:
        for item in result_set:
            chunk_id = item.chunk.chunk_id
            state = merged.setdefault(
                chunk_id,
                {
                    "chunk": item.chunk,
                    "score": 0.0,
                    "vector_rank": None,
                    "keyword_rank": None,
                },
            )
            state["score"] = float(state["score"]) + 1.0 / (k + item.rank)
            if item.vector_rank is not None:
                current = state["vector_rank"]
                state["vector_rank"] = (
                    item.vector_rank if current is None else min(int(current), item.vector_rank)
                )
            if item.keyword_rank is not None:
                current = state["keyword_rank"]
                state["keyword_rank"] = (
                    item.keyword_rank if current is None else min(int(current), item.keyword_rank)
                )
    ordered = sorted(
        merged.values(),
        key=lambda state: (-float(state["score"]), state["chunk"].chunk_id),
    )
    return [
        RankedChunk(
            chunk=state["chunk"],
            rank=rank,
            score=float(state["score"]),
            vector_rank=state["vector_rank"],
            keyword_rank=state["keyword_rank"],
        )
        for rank, state in enumerate(ordered, start=1)
    ]
