from dataclasses import dataclass, field
from typing import Any, Literal

from app.memory.models import Citation


@dataclass(frozen=True, slots=True)
class AgentRequest:
    question: str
    session_id: str | None = None
    strategy: str = "contextual_rag"
    retrieval_mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    top_k: int = 5
    candidate_k: int = 20


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    mode: Literal["vector", "keyword", "hybrid"]
    degraded_from: Literal["vector", "keyword", "hybrid"] | None = None
    degradation_reason: str | None = None


@dataclass(frozen=True, slots=True)
class AgentResponse:
    session_id: str
    answer: str
    citations: list[Citation]
    provider_tier: Literal[1, 2, 3]
    retrieval: RetrievalTrace
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentEvent:
    type: Literal["meta", "retrieval", "token", "fallback", "error", "done"]
    data: dict[str, Any]

