import json
import logging
from dataclasses import asdict
from pathlib import Path, PurePath
from threading import Lock
from typing import Sequence

import numpy as np

from app.core.config import Settings
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.logging import log_event
from app.domain.documents import DocumentRecord, IngestionTask
from app.ingestion.chunker import AdaptiveChunker
from app.ingestion.parsers import ParserRegistry
from app.retrieval.embeddings import EmbeddingPort
from app.retrieval.repository import IndexRepository


class TaskStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def save(self, task: IngestionTask) -> None:
        target = self.root / f"{task.task_id}.json"
        temporary = self.root / f"{task.task_id}.tmp"
        with self._lock:
            temporary.write_text(
                json.dumps(asdict(task), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(target)

    def get(self, task_id: str) -> IngestionTask:
        target = self.root / f"{task_id}.json"
        if not target.is_file():
            raise AppError("task_not_found", "Task was not found.", 404)
        return IngestionTask(**json.loads(target.read_text("utf-8")))

    def recover_interrupted(self) -> None:
        for path in self.root.glob("task_*.json"):
            task = IngestionTask(**json.loads(path.read_text("utf-8")))
            if task.status in ("pending", "running"):
                task.status = "failed"
                task.code = "interrupted_by_restart"
                task.message = "Task was interrupted by process restart."
                task.retryable = True
                self.save(task)


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        parser_registry: ParserRegistry,
        chunker: AdaptiveChunker,
        embedding: EmbeddingPort,
        repository: IndexRepository,
        task_store: TaskStore,
    ) -> None:
        self.settings = settings
        self.settings.ensure_directories()
        self.parser_registry = parser_registry
        self.chunker = chunker
        self.embedding = embedding
        self.repository = repository
        self.task_store = task_store
        self.documents_file = settings.data_dir / "documents.json"
        self.deleted_sources_file = settings.data_dir / "deleted_sources.json"
        self._lock = Lock()
        self.task_store.recover_interrupted()

    def create_upload(self, filename: str, content: bytes) -> IngestionTask:
        if len(content) > self.settings.upload_max_bytes:
            raise AppError("upload_too_large", "Uploaded document is too large.", 413)
        self.parser_registry.validate(filename, content)
        document_id = new_id("doc")
        task = IngestionTask(
            task_id=new_id("task"),
            action="upload",
            document_id=document_id,
            source_name=self._source_name(filename),
        )
        self.task_store.save(task)
        (self.settings.uploads_dir / f"{document_id}.source").write_bytes(content)
        return task

    def run(self, task_id: str) -> None:
        task = self.task_store.get(task_id)
        task.status = "running"
        self.task_store.save(task)
        log_event(
            logging.getLogger("app.ingestion"),
            "ingestion.started",
            task_id=task.task_id,
            document_id=task.document_id,
            action=task.action,
        )
        try:
            if task.action == "upload":
                self._run_upload(task)
            else:
                self._run_delete(task)
            task.status = "succeeded"
            task.code = None
            task.message = None
            log_event(
                logging.getLogger("app.ingestion"),
                "ingestion.completed",
                task_id=task.task_id,
                document_id=task.document_id,
                action=task.action,
                status=task.status,
            )
        except Exception as error:
            task.status = "failed"
            task.code = getattr(error, "code", "ingestion_failed")
            task.message = "Document indexing failed."
            task.retryable = True
            log_event(
                logging.getLogger("app.ingestion"),
                "ingestion.failed",
                task_id=task.task_id,
                document_id=task.document_id,
                action=task.action,
                code=task.code,
                retryable=task.retryable,
            )
        self.task_store.save(task)

    def list_documents(self) -> list[DocumentRecord]:
        if not self.documents_file.is_file():
            return []
        return [
            DocumentRecord(**item)
            for item in json.loads(self.documents_file.read_text("utf-8"))
        ]

    def list_deleted_sources(self) -> list[dict[str, object]]:
        if not self.deleted_sources_file.is_file():
            return []
        return json.loads(self.deleted_sources_file.read_text("utf-8"))

    def _run_upload(self, task: IngestionTask) -> None:
        source = self.settings.uploads_dir / f"{task.document_id}.source"
        documents = self.parser_registry.parse(
            task.document_id, task.source_name, source.read_bytes()
        )
        new_chunks = [chunk for document in documents for chunk in self.chunker.split(document)]
        with self._lock:
            snapshot = self.repository.load_active()
            chunks = [
                item for item in snapshot.chunks if item.document_id != task.document_id
            ] + new_chunks
            vectors = self.embedding.embed_texts([item.text for item in chunks])
            self.repository.publish(chunks, vectors)
            records = [
                item for item in self.list_documents() if item.document_id != task.document_id
            ]
            records.append(
                DocumentRecord(
                    task.document_id, task.source_name, "active", len(new_chunks)
                )
            )
            self._save_documents(records)

    def create_delete(self, document_id: str) -> IngestionTask:
        records = self.list_documents()
        record = next(
            (item for item in records if item.document_id == document_id), None
        )
        if record is None:
            raise AppError("document_not_found", "Document was not found.", 404)
        task = IngestionTask(
            task_id=new_id("task"),
            action="delete",
            document_id=document_id,
            source_name=record.source_name,
        )
        self.task_store.save(task)
        return task

    def _run_delete(self, task: IngestionTask) -> None:
        with self._lock:
            snapshot = self.repository.load_active()
            remaining = [
                item for item in snapshot.chunks if item.document_id != task.document_id
            ]
            if remaining:
                vectors = self.embedding.embed_texts([item.text for item in remaining])
            else:
                dimension = int(snapshot.manifest.get("vector_dimension", 1))
                vectors = np.empty((0, dimension), dtype=np.float32)
            source = self.settings.uploads_dir / f"{task.document_id}.source"
            staged_source = source.with_suffix(".deleting")
            if source.exists():
                source.replace(staged_source)
            try:
                self.repository.publish(remaining, vectors)
                records = [
                    item
                    for item in self.list_documents()
                    if item.document_id != task.document_id
                ]
                self._save_documents(records)
                tombstones = [
                    item
                    for item in self.list_deleted_sources()
                    if item.get("document_id") != task.document_id
                ]
                tombstones.append(
                    {
                        "document_id": task.document_id,
                        "source_name": task.source_name,
                        "deleted": True,
                    }
                )
                self._write_json_atomic(self.deleted_sources_file, tombstones)
                if staged_source.exists():
                    staged_source.unlink()
            except Exception:
                if staged_source.exists() and not source.exists():
                    staged_source.replace(source)
                raise

    def _save_documents(self, records: Sequence[DocumentRecord]) -> None:
        self._write_json_atomic(self.documents_file, [asdict(item) for item in records])

    @staticmethod
    def _write_json_atomic(path: Path, payload: object) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)

    @staticmethod
    def _source_name(filename: str) -> str:
        return PurePath(filename.replace("\\", "/")).name or "document"
