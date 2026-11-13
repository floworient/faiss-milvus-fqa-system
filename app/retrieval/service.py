import logging

from app.core.errors import AppError
from app.core.logging import log_event
from app.domain.retrieval import RetrievalMode, RetrievalResult
from app.retrieval.embeddings import EmbeddingPort, EmbeddingUnavailable
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.repository import IndexRepository


class RetrievalService:
    def __init__(
        self, repository: IndexRepository, embedding: EmbeddingPort
    ) -> None:
        self.repository = repository
        self.embedding = embedding

    def search(
        self,
        query: str,
        mode: RetrievalMode,
        top_k: int = 5,
        candidate_k: int = 20,
    ) -> RetrievalResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise AppError("empty_query", "Query must not be empty.", 422)
        snapshot = self.repository.load_active()
        if snapshot.is_empty:
            return self._logged(RetrievalResult(normalized_query, mode))
        keyword_results = []
        if mode in ("keyword", "hybrid"):
            keyword_results = snapshot.keyword.search(normalized_query, candidate_k)
        if mode == "keyword":
            return self._logged(
                RetrievalResult(normalized_query, mode, keyword_results[:top_k])
            )
        try:
            vector = self.embedding.embed_query(normalized_query)
            vector_results = snapshot.vector.search(vector, candidate_k) if snapshot.vector else []
        except EmbeddingUnavailable as error:
            if mode == "hybrid":
                return self._logged(
                    RetrievalResult(
                        normalized_query,
                        mode,
                        keyword_results[:top_k],
                        degraded_from="hybrid",
                        degradation_reason="embedding_unavailable",
                    )
                )
            raise AppError(
                "embedding_unavailable", "Vector retrieval is temporarily unavailable.", 503
            ) from error
        if mode == "vector":
            return self._logged(
                RetrievalResult(normalized_query, mode, vector_results[:top_k])
            )
        fused = reciprocal_rank_fusion([vector_results, keyword_results])
        return self._logged(RetrievalResult(normalized_query, mode, fused[:top_k]))

    @staticmethod
    def _logged(result: RetrievalResult) -> RetrievalResult:
        log_event(
            logging.getLogger("app.retrieval"),
            "retrieval.completed",
            mode=result.mode,
            result_count=len(result.items),
            degraded_from=result.degraded_from,
            degradation_reason=result.degradation_reason,
        )
        return result

