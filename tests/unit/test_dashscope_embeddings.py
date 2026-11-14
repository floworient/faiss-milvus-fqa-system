import sys
from types import ModuleType

import dashscope
import pytest

from app.retrieval.embeddings import DashScopeEmbeddingAdapter


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
