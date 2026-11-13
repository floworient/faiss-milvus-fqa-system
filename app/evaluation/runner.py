import json
from collections.abc import Sequence
from typing import TextIO

from app.domain.retrieval import RetrievalMode
from app.evaluation.models import (
    EvaluationDatasetError,
    EvaluationReport,
    EvaluationSample,
    QueryEvaluation,
)
from app.retrieval.service import RetrievalService


def load_jsonl(stream: TextIO) -> list[EvaluationSample]:
    samples: list[EvaluationSample] = []
    for line_number, line in enumerate(stream, start=1):
        if not line.strip():
            raise EvaluationDatasetError(
                "Evaluation dataset contains a blank row.", line_number
            )
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise EvaluationDatasetError(
                "Evaluation dataset contains malformed JSON.", line_number
            ) from error
        if not isinstance(payload, dict):
            raise EvaluationDatasetError(
                "Evaluation row must be a JSON object.", line_number
            )
        query = payload.get("query")
        chunk_ids = _string_set(payload.get("relevant_chunk_ids"), line_number)
        document_ids = _string_set(
            payload.get("relevant_document_ids"), line_number
        )
        if not isinstance(query, str) or not query.strip():
            raise EvaluationDatasetError(
                "Evaluation row requires a non-empty query.", line_number
            )
        if not chunk_ids and not document_ids:
            raise EvaluationDatasetError(
                "Evaluation row requires chunk or document relevance labels.",
                line_number,
            )
        human_correct = payload.get("human_correct")
        if human_correct is not None and not isinstance(human_correct, bool):
            raise EvaluationDatasetError(
                "human_correct must be a boolean when provided.", line_number
            )
        reference_answer = payload.get("reference_answer")
        if reference_answer is not None and not isinstance(reference_answer, str):
            raise EvaluationDatasetError(
                "reference_answer must be a string when provided.", line_number
            )
        samples.append(
            EvaluationSample(
                query.strip(),
                chunk_ids,
                document_ids,
                reference_answer,
                human_correct,
            )
        )
    if not samples:
        raise EvaluationDatasetError("Evaluation dataset is empty.", 1)
    return samples


def _string_set(value: object, line_number: int) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise EvaluationDatasetError(
            "Relevance labels must be arrays of non-empty strings.", line_number
        )
    return {item.strip() for item in value}


class EvaluationRunner:
    def __init__(self, retrieval: RetrievalService) -> None:
        self.retrieval = retrieval

    def run(
        self,
        samples: Sequence[EvaluationSample],
        mode: RetrievalMode,
        top_k: int,
    ) -> EvaluationReport:
        if not samples:
            raise ValueError("samples must not be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        query_reports: list[QueryEvaluation] = []
        first_ranks: list[int | None] = []
        recalls: list[float] = []
        for sample in samples:
            result = self.retrieval.search(sample.query, mode, top_k, top_k)
            chunks = [item.chunk for item in result.items]
            if sample.relevant_chunk_ids:
                returned = [item.chunk_id for item in chunks]
                relevant = sample.relevant_chunk_ids
            else:
                returned = [item.document_id for item in chunks]
                relevant = sample.relevant_document_ids
            first_rank = next(
                (rank for rank, item_id in enumerate(returned, start=1) if item_id in relevant),
                None,
            )
            matched = len(set(returned) & relevant)
            recall = matched / len(relevant)
            first_ranks.append(first_rank)
            recalls.append(recall)
            query_reports.append(
                QueryEvaluation(
                    sample.query,
                    first_rank,
                    recall,
                    [item.chunk_id for item in chunks],
                    [item.document_id for item in chunks],
                )
            )
        labels = [sample.human_correct for sample in samples if sample.human_correct is not None]
        return EvaluationReport(
            mode=mode,
            top_k=top_k,
            query_count=len(samples),
            hit_at_1=sum(rank == 1 for rank in first_ranks) / len(samples),
            recall_at_k=sum(recalls) / len(samples),
            mrr=sum(0.0 if rank is None else 1.0 / rank for rank in first_ranks)
            / len(samples),
            answer_accuracy=(sum(labels) / len(labels) if labels else None),
            configuration={
                "mode": mode,
                "top_k": top_k,
                "sample_count": len(samples),
            },
            queries=query_reports,
        )
