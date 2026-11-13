import pytest

from app.domain.documents import Chunk
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.keyword import RankedChunk


def chunk(chunk_id: str, document_id: str = "doc_1") -> Chunk:
    return Chunk(chunk_id, document_id, chunk_id, 0, 1, {"source_name": "x.md"})


def ranked(chunk_id: str, rank: int, *, vector: bool) -> RankedChunk:
    return RankedChunk(
        chunk=chunk(chunk_id),
        rank=rank,
        score=1.0 / rank,
        vector_rank=rank if vector else None,
        keyword_rank=None if vector else rank,
    )


def test_rrf_merges_duplicate_chunk_scores_and_ranks() -> None:
    results = reciprocal_rank_fusion(
        [[ranked("a", 1, vector=True)], [ranked("a", 2, vector=False)]], k=60
    )

    assert len(results) == 1
    assert results[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert results[0].rank == 1
    assert results[0].vector_rank == 1
    assert results[0].keyword_rank == 2


def test_rrf_ties_sort_by_chunk_id() -> None:
    results = reciprocal_rank_fusion(
        [[ranked("b", 1, vector=True)], [ranked("a", 1, vector=False)]]
    )

    assert [item.chunk.chunk_id for item in results] == ["a", "b"]


def test_rrf_keeps_different_chunks_from_same_document() -> None:
    first = ranked("a", 1, vector=True)
    second = ranked("b", 2, vector=True)

    results = reciprocal_rank_fusion([[first, second]])

    assert [item.chunk.chunk_id for item in results] == ["a", "b"]
