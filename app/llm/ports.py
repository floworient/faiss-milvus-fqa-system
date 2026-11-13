from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.memory.models import Citation


class LLMError(RuntimeError):
    reason_code = "unavailable"


class LLMTimeout(LLMError):
    reason_code = "timeout"


class LLMRateLimited(LLMError):
    reason_code = "rate_limited"


class LLMUnavailable(LLMError):
    reason_code = "unavailable"


class LLMInvalidRequest(LLMError):
    reason_code = "invalid_request"


class LLMPort(Protocol):
    def complete(self, prompt: str) -> str: ...

    def stream(self, prompt: str) -> AsyncIterator[str]: ...


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    tier: Literal[1, 2, 3]
    citations: list[Citation]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LLMEvent:
    type: Literal["token", "fallback", "error", "done"]
    data: dict[str, Any]

