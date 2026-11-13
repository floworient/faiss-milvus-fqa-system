from dataclasses import dataclass, field
from typing import Any


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

