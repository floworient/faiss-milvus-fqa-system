from dataclasses import dataclass, field
from typing import Literal

from app.core.errors import AppError


class EvaluationDatasetError(AppError):
    def __init__(self, message: str, line_number: int) -> None:
        super().__init__(
            "invalid_evaluation_dataset",
            message,
            422,
            {"line_number": line_number},
        )
        self.line_number = line_number


@dataclass(frozen=True, slots=True)
class EvaluationSample:
    query: str
    relevant_chunk_ids: set[str] = field(default_factory=set)
    relevant_document_ids: set[str] = field(default_factory=set)
    reference_answer: str | None = None
    human_correct: bool | None = None


@dataclass(frozen=True, slots=True)
class QueryEvaluation:
    query: str
    first_relevant_rank: int | None
    recall_at_k: float
    returned_chunk_ids: list[str]
    returned_document_ids: list[str]


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    mode: Literal["vector", "keyword", "hybrid"]
    top_k: int
    query_count: int
    hit_at_1: float
    recall_at_k: float
    mrr: float
    answer_accuracy: float | None
    configuration: dict[str, object]
    queries: list[QueryEvaluation]

