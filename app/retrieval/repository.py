import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

import faiss
import numpy as np
from numpy.typing import NDArray

from app.core.ids import new_id
from app.domain.documents import Chunk
from app.retrieval.keyword import KeywordIndex
from app.retrieval.vector import FaissIndex


@dataclass(slots=True)
class IndexSnapshot:
    version: str | None
    chunks: list[Chunk]
    vector: FaissIndex | None
    keyword: KeywordIndex
    manifest: dict[str, object]

    @property
    def is_empty(self) -> bool:
        return self.version is None or not self.chunks


class IndexRepository:
    schema_version = 1

    def __init__(
        self,
        root: Path,
        version_factory: Callable[[], str] | None = None,
    ) -> None:
        self.root = Path(root)
        self.version_factory = version_factory or (lambda: new_id("idx"))

    def publish(
        self, chunks: Sequence[Chunk], vectors: NDArray[np.float32]
    ) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        version = self.version_factory()
        final_dir = self.root / version
        staging_dir = self.root / f"{version}.staging"
        if final_dir.exists() or staging_dir.exists():
            raise FileExistsError(f"index version already exists: {version}")
        staging_dir.mkdir()
        vector = FaissIndex.build(chunks, vectors)
        keyword = KeywordIndex.build(chunks)
        faiss.write_index(vector.index, str(staging_dir / "faiss.index"))
        self._write_json(staging_dir / "chunks.json", [asdict(item) for item in chunks])
        self._write_json(staging_dir / "keyword.json", keyword.to_dict())
        chunker_versions = sorted(
            {
                str(item.metadata.get("chunker_version"))
                for item in chunks
                if item.metadata.get("chunker_version")
            }
        )
        manifest = {
            "schema_version": self.schema_version,
            "version": version,
            "chunk_count": len(chunks),
            "vector_dimension": vector.index.d,
            "chunker_versions": chunker_versions,
        }
        self._write_json(staging_dir / "manifest.json", manifest)
        staging_dir.rename(final_dir)
        self.activate(version)
        return version

    def activate(self, version: str | None) -> None:
        """Atomically select a prepared version, or restore the empty state."""
        self.root.mkdir(parents=True, exist_ok=True)
        active_file = self.root / "ACTIVE"
        if version is None:
            active_file.unlink(missing_ok=True)
            (self.root / "ACTIVE.tmp").unlink(missing_ok=True)
            return
        if not (self.root / version).is_dir() or version.endswith(".staging"):
            raise ValueError(f"index version is not ready: {version}")
        active_tmp = self.root / "ACTIVE.tmp"
        active_tmp.write_text(version, encoding="utf-8")
        os.replace(active_tmp, active_file)

    def load_active(self) -> IndexSnapshot:
        active_file = self.root / "ACTIVE"
        if not active_file.is_file():
            return IndexSnapshot(None, [], None, KeywordIndex.build([]), {})
        version = active_file.read_text(encoding="utf-8").strip()
        version_dir = self.root / version
        if not version or not version_dir.is_dir() or version.endswith(".staging"):
            return IndexSnapshot(None, [], None, KeywordIndex.build([]), {})
        chunks = [
            Chunk(**item)
            for item in json.loads((version_dir / "chunks.json").read_text("utf-8"))
        ]
        vector = FaissIndex(faiss.read_index(str(version_dir / "faiss.index")), chunks)
        keyword = KeywordIndex.from_dict(
            json.loads((version_dir / "keyword.json").read_text("utf-8"))
        )
        manifest = json.loads((version_dir / "manifest.json").read_text("utf-8"))
        return IndexSnapshot(version, chunks, vector, keyword, manifest)

    def remove_document(
        self, document_id: str, vectors: NDArray[np.float32]
    ) -> str:
        snapshot = self.load_active()
        remaining = [item for item in snapshot.chunks if item.document_id != document_id]
        matrix = np.asarray(vectors, dtype=np.float32)
        if len(remaining) != len(matrix):
            raise ValueError("remaining chunk and vector counts must match")
        return self.publish(remaining, matrix)

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
