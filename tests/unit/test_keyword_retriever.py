from app.domain.documents import Chunk
from app.retrieval.keyword import KeywordIndex


def chunk(chunk_id: str, text: str, source: str = "guide.md") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        text=text,
        position=0,
        token_count=len(text),
        metadata={"source_name": source},
    )


def test_chinese_bigrams_recall_return_policy() -> None:
    index = KeywordIndex.build(
        [chunk("a", "如何办理退货"), chunk("b", "如何修改收货地址")]
    )

    results = index.search("退货", limit=2)

    assert results[0].chunk.chunk_id == "a"
    assert results[0].rank == 1
    assert results[0].score > 0
    assert results[0].chunk.metadata["source_name"] == "guide.md"


def test_english_tokens_are_case_insensitive() -> None:
    index = KeywordIndex.build(
        [chunk("a", "Refund policy for paid orders"), chunk("b", "Shipping guide")]
    )

    assert index.search("REFUND", limit=1)[0].chunk.chunk_id == "a"


def test_empty_query_or_corpus_returns_no_results() -> None:
    assert KeywordIndex.build([]).search("退货", limit=5) == []
    assert KeywordIndex.build([chunk("a", "退货")]).search("  ", limit=5) == []


def test_duplicate_chunk_ids_are_deduplicated_and_ties_are_stable() -> None:
    index = KeywordIndex.build(
        [
            chunk("b", "相同 关键词"),
            chunk("a", "相同 关键词"),
            chunk("a", "不应覆盖"),
        ]
    )

    results = index.search("相同", limit=10)

    assert [item.chunk.chunk_id for item in results] == ["a", "b"]
    assert [item.rank for item in results] == [1, 2]
