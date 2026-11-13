from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class Citation:
    chunk_id: str
    document_id: str
    source_name: str
    excerpt: str | None = None
    deleted: bool = False

    def __post_init__(self) -> None:
        if self.deleted:
            self.excerpt = None


@dataclass(slots=True)
class Message:
    role: Literal["user", "assistant"]
    content: str
    status: Literal["complete", "failed"] = "complete"
    citations: list[Citation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Conversation:
    session_id: str
    messages: list[Message] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

