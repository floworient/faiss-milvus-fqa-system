from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    document_id: str
    source_name: str
    title: str | None
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    document_id: str
    text: str
    position: int
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IngestionTask:
    task_id: str
    action: Literal["upload", "delete"]
    document_id: str
    source_name: str
    status: Literal["pending", "running", "succeeded", "failed"] = "pending"
    code: str | None = None
    message: str | None = None
    retryable: bool = False


@dataclass(slots=True)
class DocumentRecord:
    document_id: str
    source_name: str
    status: Literal["active", "deleted"] = "active"
    chunk_count: int = 0

