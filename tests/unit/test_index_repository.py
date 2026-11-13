import json
from pathlib import Path

import faiss
import numpy as np
import pytest

from app.domain.documents import Chunk
from app.retrieval.repository import IndexRepository
from app.retrieval.vector import FaissIndex


def chunk(chunk_id: str, document_id: str = "doc_1") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        text=f"content {chunk_id}",
        position=0,
        token_count=2,
        metadata={"source_name": "guide.md", "chunker_version": "chunker-v1"},
    )


def test_faiss_index_normalizes_vectors_for_inner_product_search() -> None:
    index = FaissIndex.build(
        [chunk("a"), chunk("b")],
        np.array([[3.0, 0.0], [0.0, 4.0]], dtype=np.float32),
    )

    results = index.search(np.array([2.0, 0.0], dtype=np.float32), limit=2)

    assert results[0].chunk.chunk_id == "a"
    assert results[0].score == pytest.approx(1.0)
    assert results[0].vector_rank == 1


def test_publish_creates_immutable_version_and_switches_active(tmp_path: Path) -> None:
    repository = IndexRepository(tmp_path, version_factory=lambda: "v1")

    version = repository.publish(
        [chunk("a")], np.array([[1.0, 0.0]], dtype=np.float32)
    )
    snapshot = repository.load_active()

    assert version == "v1"
    assert (tmp_path / "v1" / "faiss.index").is_file()
    assert (tmp_path / "v1" / "chunks.json").is_file()
    assert (tmp_path / "v1" / "keyword.json").is_file()
    assert (tmp_path / "ACTIVE").read_text(encoding="utf-8") == "v1"
    assert snapshot.version == "v1"
    assert snapshot.vector.search(np.array([1.0, 0.0], dtype=np.float32), 1)[0].chunk.chunk_id == "a"
    with pytest.raises(FileExistsError):
        repository.publish([chunk("b")], np.array([[0.0, 1.0]], dtype=np.float32))


def test_failed_publication_leaves_previous_snapshot_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    versions = iter(["v1", "v2"])
    repository = IndexRepository(tmp_path, version_factory=lambda: next(versions))
    repository.publish([chunk("a")], np.array([[1.0, 0.0]], dtype=np.float32))

    def fail_write(*args: object, **kwargs: object) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(faiss, "write_index", fail_write)
    with pytest.raises(OSError, match="simulated disk failure"):
        repository.publish([chunk("b")], np.array([[0.0, 1.0]], dtype=np.float32))

    assert repository.load_active().version == "v1"
    assert (tmp_path / "ACTIVE").read_text(encoding="utf-8") == "v1"


def test_missing_active_index_is_empty_and_staging_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "orphan.staging").mkdir(parents=True)

    snapshot = IndexRepository(tmp_path).load_active()

    assert snapshot.is_empty
    assert snapshot.version is None
    assert snapshot.chunks == []


def test_manifest_records_schema_and_chunker_versions(tmp_path: Path) -> None:
    repository = IndexRepository(tmp_path, version_factory=lambda: "v1")

    repository.publish([chunk("a")], np.array([[1.0, 0.0]], dtype=np.float32))
    manifest = json.loads((tmp_path / "v1" / "manifest.json").read_text("utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["chunker_versions"] == ["chunker-v1"]
    assert manifest["chunk_count"] == 1
