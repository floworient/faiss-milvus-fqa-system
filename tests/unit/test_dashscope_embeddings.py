import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import dashscope
import numpy as np
import pytest

from app.retrieval.embeddings import DashScopeEmbeddingAdapter, EmbeddingUnavailable


def install_embedding_response(
    monkeypatch: pytest.MonkeyPatch,
    items: list[dict[str, Any]],
    *,
    status_code: int = 200,
    code: str = "",
    message: str = "",
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def call(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            status_code=status_code,
            output={"embeddings": items},
            code=code,
            message=message,
        )

    monkeypatch.setattr(dashscope.TextEmbedding, "call", staticmethod(call))
    return captured


def test_embedding_adapter_configures_dashscope_base_url_before_model_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeDashScopeEmbedding:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            captured["base_url_at_creation"] = dashscope.base_http_api_url

    llama_index = ModuleType("llama_index")
    embeddings = ModuleType("llama_index.embeddings")
    integration = ModuleType("llama_index.embeddings.dashscope")
    integration.DashScopeEmbedding = FakeDashScopeEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_index", llama_index)
    monkeypatch.setitem(sys.modules, "llama_index.embeddings", embeddings)
    monkeypatch.setitem(sys.modules, "llama_index.embeddings.dashscope", integration)
    monkeypatch.setattr(
        dashscope, "base_http_api_url", "https://dashscope.aliyuncs.com/api/v1"
    )

    adapter = DashScopeEmbeddingAdapter(
        "key",
        "text-embedding-v3",
        512,
        base_url="https://gateway.example.com/api/v1",
    )

    assert adapter.dimension == 512
    assert captured["base_url_at_creation"] == "https://gateway.example.com/api/v1"


def test_embedding_adapter_accepts_workspace_index_and_restores_input_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_embedding_response(
        monkeypatch,
        [
            {"index": 1, "embedding": [2.0, 20.0], "type": "dense"},
            {"index": 0, "embedding": [1.0, 10.0], "type": "dense"},
        ],
    )
    adapter = DashScopeEmbeddingAdapter(
        "key", "qwen3.7-text-embedding-flash", 1, "https://gateway.example.com/api/v1"
    )

    vectors = adapter.embed_texts(["first", "second"])

    np.testing.assert_array_equal(vectors, np.array([[1.0], [2.0]], dtype=np.float32))


def test_embedding_adapter_keeps_native_text_index_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_embedding_response(
        monkeypatch,
        [{"text_index": 0, "embedding": [1.0, 2.0]}],
    )
    adapter = DashScopeEmbeddingAdapter(
        "key", "text-embedding-v3", 2, "https://dashscope.aliyuncs.com/api/v1"
    )

    vector = adapter.embed_texts(["document"])

    np.testing.assert_array_equal(vector, np.array([[1.0, 2.0]], dtype=np.float32))


def test_embedding_adapter_uses_query_text_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = install_embedding_response(
        monkeypatch,
        [{"index": 0, "embedding": [3.0, 4.0], "type": "dense"}],
    )
    adapter = DashScopeEmbeddingAdapter(
        "key", "qwen3.7-text-embedding-flash", 2, "https://gateway.example.com/api/v1"
    )

    vector = adapter.embed_query("query")

    np.testing.assert_array_equal(vector, np.array([3.0, 4.0], dtype=np.float32))
    assert captured["text_type"] == "query"


@pytest.mark.parametrize(
    "items",
    [
        [{"index": 0, "embedding": [1.0]}, {"index": 0, "embedding": [2.0]}],
        [{"index": -1, "embedding": [1.0]}, {"index": 1, "embedding": [2.0]}],
        [{"index": "0", "embedding": [1.0]}, {"index": 1, "embedding": [2.0]}],
        [{"index": 0, "embedding": [1.0]}, {"index": 2, "embedding": [2.0]}],
        [{"index": 0}, {"index": 1, "embedding": [2.0]}],
        [{"index": 0, "embedding": [1.0]}],
    ],
)
def test_embedding_adapter_rejects_malformed_or_incomplete_batches(
    monkeypatch: pytest.MonkeyPatch,
    items: list[dict[str, Any]],
) -> None:
    install_embedding_response(monkeypatch, items)
    adapter = DashScopeEmbeddingAdapter(
        "key", "model", 1, "https://gateway.example.com/api/v1"
    )

    with pytest.raises(EmbeddingUnavailable):
        adapter.embed_texts(["first", "second"])


def test_embedding_adapter_maps_provider_errors_without_exposing_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_embedding_response(
        monkeypatch,
        [],
        status_code=400,
        code="InvalidParameter",
        message="rejected sensitive document text",
    )
    adapter = DashScopeEmbeddingAdapter(
        "key", "model", 1, "https://gateway.example.com/api/v1"
    )

    with pytest.raises(EmbeddingUnavailable) as captured:
        adapter.embed_texts(["document"])

    assert "InvalidParameter" in str(captured.value)
    assert "sensitive document text" not in str(captured.value)
