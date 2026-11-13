from pathlib import Path

import httpx
import numpy as np
import pytest

from app.core.config import Settings
from app.domain.documents import Chunk
from app.main import ServiceContainer, create_app
from app.retrieval.embeddings import EmbeddingUnavailable
from app.retrieval.repository import IndexRepository
from app.retrieval.service import RetrievalService


class FakeEmbedding:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.query_calls = 0

    def embed_query(self, text: str) -> np.ndarray:
        self.query_calls += 1
        if self.fail:
            raise EmbeddingUnavailable("offline")
        return np.array([1.0, 0.0], dtype=np.float32)

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)


def build_service(tmp_path: Path, embedding: FakeEmbedding) -> RetrievalService:
    repository = IndexRepository(tmp_path / "indexes", version_factory=lambda: "v1")
    chunks = [
        Chunk(
            "chk_return",
            "doc_1",
            "如何办理退货",
            2,
            6,
            {"source_name": "guide.md", "chunker_version": "chunker-v1"},
        ),
        Chunk(
            "chk_ship",
            "doc_2",
            "shipping policy",
            0,
            2,
            {"source_name": "shipping.md", "chunker_version": "chunker-v1"},
        ),
    ]
    repository.publish(chunks, np.array([[1.0, 0.0], [0.0, 1.0]], np.float32))
    return RetrievalService(repository, embedding)


async def post_search(app: object, payload: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/v1/retrieval/search", json=payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["vector", "keyword", "hybrid"])
async def test_search_supports_all_retrieval_modes(tmp_path: Path, mode: str) -> None:
    embedding = FakeEmbedding()
    app = create_app(
        Settings(data_dir=tmp_path / "runtime"),
        ServiceContainer(retrieval=build_service(tmp_path, embedding)),
    )

    response = await post_search(
        app, {"query": "退货", "mode": mode, "top_k": 2, "candidate_k": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == mode
    assert body["results"][0]["chunk_id"] == "chk_return"
    assert body["results"][0]["source"] == "guide.md"
    assert body["results"][0]["position"] == 2
    assert "score" in body["results"][0]
    assert "vector_rank" in body["results"][0]
    assert "keyword_rank" in body["results"][0]
    assert embedding.query_calls == (0 if mode == "keyword" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"query": "退货", "mode": "unknown", "top_k": 2},
        {"query": "退货", "mode": "hybrid", "top_k": 0},
    ],
)
async def test_search_rejects_invalid_mode_or_top_k(
    tmp_path: Path, payload: dict
) -> None:
    app = create_app(Settings(data_dir=tmp_path / "runtime"), ServiceContainer())

    response = await post_search(app, payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_index_returns_empty_result(tmp_path: Path) -> None:
    service = RetrievalService(IndexRepository(tmp_path / "indexes"), FakeEmbedding())
    app = create_app(
        Settings(data_dir=tmp_path / "runtime"), ServiceContainer(retrieval=service)
    )

    response = await post_search(app, {"query": "退货", "mode": "hybrid"})

    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.asyncio
async def test_hybrid_degrades_to_keyword_when_embedding_is_unavailable(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path, FakeEmbedding(fail=True))
    app = create_app(
        Settings(data_dir=tmp_path / "runtime"), ServiceContainer(retrieval=service)
    )

    response = await post_search(app, {"query": "退货", "mode": "hybrid"})

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["chunk_id"] == "chk_return"
    assert body["degraded_from"] == "hybrid"
    assert body["degradation_reason"] == "embedding_unavailable"
