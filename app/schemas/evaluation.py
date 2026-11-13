from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.evaluation.models import EvaluationReport


class QueryEvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    query: str
    first_relevant_rank: int | None
    recall_at_k: float
    returned_chunk_ids: list[str]
    returned_document_ids: list[str]


class EvaluationReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mode: Literal["vector", "keyword", "hybrid"]
    top_k: int
    query_count: int
    hit_at_1: float
    recall_at_k: float
    mrr: float
    answer_accuracy: float | None
    configuration: dict[str, object]
    queries: list[QueryEvaluationResponse]

    @classmethod
    def from_domain(cls, report: EvaluationReport) -> "EvaluationReportResponse":
        return cls.model_validate(report)

