from dataclasses import dataclass, field
from typing import Literal

from app.retrieval.keyword import RankedChunk

RetrievalMode = Literal["vector", "keyword", "hybrid"]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    query: str
    mode: RetrievalMode
    items: list[RankedChunk] = field(default_factory=list)
    degraded_from: RetrievalMode | None = None
    degradation_reason: str | None = None

