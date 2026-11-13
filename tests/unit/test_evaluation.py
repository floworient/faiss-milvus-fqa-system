import io

import pytest

from app.domain.documents import Chunk
from app.domain.retrieval import RetrievalResult
from app.evaluation.models import EvaluationDatasetError, EvaluationSample
from app.evaluation.runner import EvaluationRunner, load_jsonl
from app.retrieval.keyword import RankedChunk


def ranked(chunk_id: str, document_id: str, rank: int) -> RankedChunk:
    return RankedChunk(
        Chunk(chunk_id, document_id, chunk_id, 0, 1, {"source_name": "eval.md"}),
        rank,
        1.0 / rank,
    )


class FixedRetrieval:
    def __init__(self) -> None:
        self.rankings = {
            "q1": [ranked("c1", "d1", 1)],
            "q2": [ranked("other", "dx", 1), ranked("c2", "d2", 2)],
            "q3": [ranked("c3", "d3", 1)],
        }

    def search(self, query: str, mode: str, top_k: int, candidate_k: int):
        return RetrievalResult(query, mode, self.rankings[query][:top_k])


def test_runner_computes_exact_retrieval_metrics_and_per_query_ranks() -> None:
    samples = [
        EvaluationSample("q1", relevant_chunk_ids={"c1"}),
        EvaluationSample("q2", relevant_chunk_ids={"c2"}),
        EvaluationSample("q3", relevant_document_ids={"d3"}),
    ]

    report = EvaluationRunner(FixedRetrieval()).run(samples, "hybrid", top_k=2)

    assert report.query_count == 3
    assert report.hit_at_1 == pytest.approx(2 / 3)
    assert report.recall_at_k == pytest.approx(1.0)
    assert report.mrr == pytest.approx(2.5 / 3)
    assert [item.first_relevant_rank for item in report.queries] == [1, 2, 1]
    assert report.mode == "hybrid"
    assert report.top_k == 2
    assert report.configuration == {
        "mode": "hybrid",
        "top_k": 2,
        "sample_count": 3,
    }
    assert report.answer_accuracy is None


def test_chunk_labels_take_precedence_over_document_labels() -> None:
    sample = EvaluationSample(
        "q3", relevant_chunk_ids={"missing"}, relevant_document_ids={"d3"}
    )

    report = EvaluationRunner(FixedRetrieval()).run([sample], "hybrid", top_k=2)

    assert report.recall_at_k == 0.0
    assert report.queries[0].first_relevant_rank is None


def test_answer_accuracy_uses_only_explicit_human_labels() -> None:
    samples = [
        EvaluationSample("q1", relevant_chunk_ids={"c1"}, human_correct=True),
        EvaluationSample("q2", relevant_chunk_ids={"c2"}, human_correct=False),
        EvaluationSample("q3", relevant_document_ids={"d3"}),
    ]

    report = EvaluationRunner(FixedRetrieval()).run(samples, "vector", top_k=2)

    assert report.answer_accuracy == 0.5


def test_jsonl_loader_accepts_optional_answer_fields() -> None:
    samples = load_jsonl(
        io.StringIO(
            '{"query":"q","relevant_chunk_ids":["c1"],'
            '"reference_answer":"answer","human_correct":true}\n'
        )
    )

    assert samples[0].reference_answer == "answer"
    assert samples[0].human_correct is True
    assert samples[0].relevant_chunk_ids == {"c1"}


@pytest.mark.parametrize(
    ("content", "line_number"),
    [
        ('{"query":"q","relevant_chunk_ids":["c"]}\n\n', 2),
        ('{"query":"q","relevant_chunk_ids":["c"]}\n{broken\n', 2),
        ('{"query":"q"}\n', 1),
    ],
)
def test_jsonl_loader_rejects_blank_malformed_or_unlabelled_rows(
    content: str, line_number: int
) -> None:
    with pytest.raises(EvaluationDatasetError) as caught:
        load_jsonl(io.StringIO(content))

    assert caught.value.line_number == line_number
    assert caught.value.details == {"line_number": line_number}
