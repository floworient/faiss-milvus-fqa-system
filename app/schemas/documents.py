from dataclasses import asdict
from typing import Literal

from pydantic import BaseModel

from app.domain.documents import DocumentRecord, IngestionTask


class TaskResponse(BaseModel):
    task_id: str
    action: Literal["upload", "delete"]
    document_id: str
    source_name: str
    status: Literal["pending", "running", "succeeded", "failed"]
    code: str | None = None
    message: str | None = None
    retryable: bool = False

    @classmethod
    def from_task(cls, task: IngestionTask) -> "TaskResponse":
        return cls(**asdict(task))


class DocumentResponse(BaseModel):
    document_id: str
    source_name: str
    status: Literal["active", "deleted"]
    chunk_count: int

    @classmethod
    def from_record(cls, record: DocumentRecord) -> "DocumentResponse":
        return cls(**asdict(record))
