from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.chat import AgentRequest, AgentResponse
from app.memory.models import Conversation


class ChatCompletionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    strategy: str = "contextual_rag"
    retrieval_mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    top_k: int = Field(default=5, ge=1, le=50)
    candidate_k: int = Field(default=20, ge=1, le=200)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value

    def to_domain(self) -> AgentRequest:
        return AgentRequest(**self.model_dump())


class CitationResponse(BaseModel):
    chunk_id: str
    document_id: str
    source_name: str
    excerpt: str | None = None
    deleted: bool = False


class RetrievalTraceResponse(BaseModel):
    mode: Literal["vector", "keyword", "hybrid"]
    degraded_from: Literal["vector", "keyword", "hybrid"] | None = None
    degradation_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    session_id: str
    answer: str
    provider_tier: Literal[1, 2, 3]
    citations: list[CitationResponse]
    retrieval: RetrievalTraceResponse
    metadata: dict[str, object]

    @classmethod
    def from_domain(cls, response: AgentResponse) -> "ChatCompletionResponse":
        return cls.model_validate(response, from_attributes=True)


class MessageResponse(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    status: Literal["complete", "failed"]
    citations: list[CitationResponse]
    metadata: dict[str, object]


class SessionResponse(BaseModel):
    session_id: str
    messages: list[MessageResponse]
    metadata: dict[str, object]

    @classmethod
    def from_domain(cls, conversation: Conversation) -> "SessionResponse":
        return cls.model_validate(conversation, from_attributes=True)


