from pathlib import Path

import httpx
import numpy as np
import pytest

from app.core.config import Settings
from app.ingestion.chunker import AdaptiveChunker, RegexTokenizer
from app.ingestion.parsers import ParserRegistry
from app.ingestion.service import IngestionService, TaskStore
from app.main import ServiceContainer, create_app
from app.retrieval.embeddings import EmbeddingUnavailable
from app.retrieval.repository import IndexRepository


class FakeEmbedding:
    def __init__(self) -> None:
        self.fail = False

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if self.fail:
            raise EmbeddingUnavailable("offline")
        return np.array([[1.0, float(index)] for index, _ in enumerate(texts)], np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return np.array([1.0, 0.0], np.float32)


def build_app(tmp_path: Path, upload_max_bytes: int = 1024 * 1024):
    settings = Settings(
        data_dir=tmp_path / "runtime", upload_max_bytes=upload_max_bytes
    )
    versions = iter(f"v{index}" for index in range(1, 20))
    repository = IndexRepository(settings.indexes_dir, lambda: next(versions))
    embedding = FakeEmbedding()
    service = IngestionService(
        settings,
        ParserRegistry(),
        AdaptiveChunker(settings, RegexTokenizer()),
        embedding,
        repository,
        TaskStore(settings.tasks_dir),
    )
    app = create_app(settings, ServiceContainer(ingestion=service))
    return app, service, repository, embedding


async def request(app: object, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_upload_persists_task_source_and_publishes_indexes(tmp_path: Path) -> None:
    app, service, repository, _ = build_app(tmp_path)

    response = await request(
        app,
        "POST",
        "/api/v1/documents",
        files={"file": ("guide.md", "# 退货\n\n七天内可以退货。", "text/markdown")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["task_id"].startswith("task_")
    assert payload["document_id"].startswith("doc_")
    task_response = await request(app, "GET", f"/api/v1/tasks/{payload['task_id']}")
    assert task_response.json()["status"] == "succeeded"
    assert (service.settings.uploads_dir / f"{payload['document_id']}.source").is_file()
    assert (service.settings.tasks_dir / f"{payload['task_id']}.json").is_file()
    snapshot = repository.load_active()
    assert not snapshot.is_empty
    assert snapshot.keyword.search("退货", 1)[0].chunk.document_id == payload["document_id"]
    assert snapshot.manifest["chunk_count"] >= 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content", "expected_code"),
    [
        ("bad.json", b"{broken", "invalid_json_document"),
        ("empty.txt", b"  ", "empty_document"),
        ("fake.pdf", b"plain text", "unsupported_document_type"),
    ],
)
async def test_invalid_upload_is_rejected_before_source_is_written(
    tmp_path: Path, filename: str, content: bytes, expected_code: str
) -> None:
    app, service, _, _ = build_app(tmp_path)

    response = await request(
        app, "POST", "/api/v1/documents", files={"file": (filename, content)}
    )

    assert response.status_code == 422
    assert response.json()["code"] == expected_code
    assert list(service.settings.uploads_dir.glob("*.source")) == []


@pytest.mark.asyncio
async def test_oversized_upload_is_rejected_before_source_is_written(
    tmp_path: Path,
) -> None:
    app, service, _, _ = build_app(tmp_path, upload_max_bytes=5)

    response = await request(
        app, "POST", "/api/v1/documents", files={"file": ("big.txt", b"123456")}
    )

    assert response.status_code == 413
    assert list(service.settings.uploads_dir.glob("*.source")) == []


@pytest.mark.asyncio
async def test_traversal_filename_is_normalized_to_server_generated_path(
    tmp_path: Path,
) -> None:
    app, service, _, _ = build_app(tmp_path)

    response = await request(
        app, "POST", "/api/v1/documents", files={"file": ("../guide.txt", b"refund")}
    )

    assert response.status_code == 202
    document_id = response.json()["document_id"]
    assert (service.settings.uploads_dir / f"{document_id}.source").is_file()
    assert not (tmp_path / "guide.txt").exists()


def test_embedding_failure_keeps_previous_active_index(tmp_path: Path) -> None:
    _, service, repository, embedding = build_app(tmp_path)
    first = service.create_upload("first.txt", b"working content")
    service.run(first.task_id)
    active_version = repository.load_active().version
    embedding.fail = True

    second = service.create_upload("second.txt", b"new content")
    service.run(second.task_id)

    assert service.task_store.get(second.task_id).status == "failed"
    assert repository.load_active().version == active_version


def test_pending_task_is_marked_retryable_failed_after_restart(tmp_path: Path) -> None:
    _, service, _, _ = build_app(tmp_path)
    task = service.create_upload("guide.txt", b"content")

    TaskStore(service.settings.tasks_dir).recover_interrupted()

    recovered = service.task_store.get(task.task_id)
    assert recovered.status == "failed"
    assert recovered.code == "interrupted_by_restart"
    assert recovered.retryable is True


@pytest.mark.asyncio
async def test_delete_removes_source_and_active_chunks_but_keeps_safe_tombstone(
    tmp_path: Path,
) -> None:
    app, service, repository, _ = build_app(tmp_path)
    upload = await request(
        app, "POST", "/api/v1/documents", files={"file": ("guide.txt", b"refund")}
    )
    document_id = upload.json()["document_id"]

    response = await request(app, "DELETE", f"/api/v1/documents/{document_id}")

    assert response.status_code == 202
    task = service.task_store.get(response.json()["task_id"])
    assert task.status == "succeeded"
    assert not (service.settings.uploads_dir / f"{document_id}.source").exists()
    assert all(item.document_id != document_id for item in repository.load_active().chunks)
    listed = await request(app, "GET", "/api/v1/documents")
    assert listed.json() == []
    tombstone = service.list_deleted_sources()[0]
    assert tombstone == {
        "document_id": document_id,
        "source_name": "guide.txt",
        "deleted": True,
    }
    assert "text" not in tombstone


@pytest.mark.asyncio
async def test_failed_delete_preserves_active_index_and_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, service, repository, _ = build_app(tmp_path)
    upload = await request(
        app, "POST", "/api/v1/documents", files={"file": ("guide.txt", b"refund")}
    )
    document_id = upload.json()["document_id"]
    active_version = repository.load_active().version

    def fail_publish(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(repository, "publish", fail_publish)
    response = await request(app, "DELETE", f"/api/v1/documents/{document_id}")

    assert service.task_store.get(response.json()["task_id"]).status == "failed"
    assert repository.load_active().version == active_version
    assert (service.settings.uploads_dir / f"{document_id}.source").is_file()
    assert [item.document_id for item in service.list_documents()] == [document_id]
