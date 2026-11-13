from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.retrieval import RetrievalResult


class RetrievalSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    top_k: int = Field(default=5, ge=1, le=50)
    candidate_k: int = Field(default=20, ge=1, le=200)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class RetrievalItemResponse(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    source: str | None
    position: int
    score: float
    rank: int
    vector_rank: int | None
    keyword_rank: int | None


class RetrievalSearchResponse(BaseModel):
    query: str
    mode: Literal["vector", "keyword", "hybrid"]
    results: list[RetrievalItemResponse]
    degraded_from: Literal["vector", "keyword", "hybrid"] | None = None
    degradation_reason: str | None = None

    @classmethod
    def from_result(cls, result: RetrievalResult) -> "RetrievalSearchResponse":
        return cls(
            query=result.query,
            mode=result.mode,
            results=[
                RetrievalItemResponse(
                    chunk_id=item.chunk.chunk_id,
                    document_id=item.chunk.document_id,
                    text=item.chunk.text,
                    source=item.chunk.metadata.get("source_name"),
                    position=item.chunk.position,
                    score=item.score,
                    rank=item.rank,
                    vector_rank=item.vector_rank,
                    keyword_rank=item.keyword_rank,
                )
                for item in result.items
            ],
            degraded_from=result.degraded_from,
            degradation_reason=result.degradation_reason,
        )

