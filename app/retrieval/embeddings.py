import math
import re
from http import HTTPStatus
from typing import Any, Protocol, Sequence

import dashscope
import numpy as np
import requests
from numpy.typing import NDArray


class EmbeddingUnavailable(RuntimeError):
    """The configured embedding provider cannot serve the request."""


class EmbeddingPort(Protocol):
    def embed_texts(self, texts: Sequence[str]) -> NDArray[np.float32]: ...

    def embed_query(self, text: str) -> NDArray[np.float32]: ...


class UnavailableEmbedding:
    """Explicit no-key adapter that keeps keyword-only retrieval available."""

    def embed_texts(self, texts: Sequence[str]) -> NDArray[np.float32]:
        raise EmbeddingUnavailable("Embedding provider is not configured")

    def embed_query(self, text: str) -> NDArray[np.float32]:
        raise EmbeddingUnavailable("Embedding provider is not configured")


def _safe_provider_code(response: object) -> str:
    code = getattr(response, "code", None)
    if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code):
        return code
    return "unknown"


def _request_compatible_embeddings(
    model: str,
    texts: Sequence[str],
    api_key: str | None,
    *,
    text_type: str,
) -> list[list[float]]:
    try:
        response = dashscope.TextEmbedding.call(
            model=model,
            input=list(texts),
            api_key=api_key,
            text_type=text_type,
        )
    except requests.exceptions.RequestException:
        raise EmbeddingUnavailable("Embedding provider request failed") from None
    status_code = getattr(response, "status_code", None)
    if status_code != HTTPStatus.OK:
        raise EmbeddingUnavailable(
            "Embedding provider rejected request "
            f"(status={status_code}, code={_safe_provider_code(response)})"
        )

    output = getattr(response, "output", None)
    if not isinstance(output, dict):
        raise EmbeddingUnavailable("Embedding provider returned malformed output")
    items = output.get("embeddings")
    if not isinstance(items, list):
        raise EmbeddingUnavailable("Embedding provider returned malformed embeddings")

    ordered: list[list[float] | None] = [None] * len(texts)
    vector_size: int | None = None
    for item in items:
        if not isinstance(item, dict):
            raise EmbeddingUnavailable("Embedding provider returned malformed item")
        index = item["text_index"] if "text_index" in item else item.get("index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or index >= len(ordered)
            or ordered[index] is not None
        ):
            raise EmbeddingUnavailable("Embedding provider returned invalid index")
        embedding = item.get("embedding")
        if (
            not isinstance(embedding, list)
            or not embedding
            or any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                for value in embedding
            )
        ):
            raise EmbeddingUnavailable("Embedding provider returned invalid vector")
        try:
            vector = [float(value) for value in embedding]
        except (OverflowError, TypeError, ValueError):
            raise EmbeddingUnavailable(
                "Embedding provider returned invalid vector"
            ) from None
        float32_max = float(np.finfo(np.float32).max)
        if any(
            not math.isfinite(value) or abs(value) > float32_max for value in vector
        ):
            raise EmbeddingUnavailable("Embedding provider returned invalid vector")
        if vector_size is None:
            vector_size = len(vector)
        elif len(vector) != vector_size:
            raise EmbeddingUnavailable("Embedding provider returned inconsistent vectors")
        ordered[index] = vector

    if any(vector is None for vector in ordered):
        raise EmbeddingUnavailable("Embedding provider returned an incomplete batch")
    return [vector for vector in ordered if vector is not None]


class DashScopeEmbeddingAdapter:
    """LlamaIndex DashScope embedding adapter without global Settings mutation."""

    def __init__(
        self, api_key: str, model: str, dimension: int, base_url: str
    ) -> None:
        dashscope.base_http_api_url = base_url

        from llama_index.embeddings.dashscope import DashScopeEmbedding

        class CompatibleDashScopeEmbedding(DashScopeEmbedding):
            def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
                return _request_compatible_embeddings(
                    self.model_name,
                    texts,
                    self._api_key,
                    text_type=self._text_type,
                )

            def _get_text_embedding(self, text: str) -> list[float]:
                return self._get_text_embeddings([text])[0]

            def _get_query_embedding(self, query: str) -> list[float]:
                return _request_compatible_embeddings(
                    self.model_name,
                    [query],
                    self._api_key,
                    text_type="query",
                )[0]

        self._model = CompatibleDashScopeEmbedding(
            api_key=api_key,
            model_name=model,
            embed_batch_size=10,
        )
        self.dimension = dimension

    def embed_texts(self, texts: Sequence[str]) -> NDArray[np.float32]:
        vectors = self._model.get_text_embedding_batch(list(texts))
        return np.asarray(vectors, dtype=np.float32)[:, : self.dimension]

    def embed_query(self, text: str) -> NDArray[np.float32]:
        vector = self._model.get_query_embedding(text)
        return np.asarray(vector, dtype=np.float32)[: self.dimension]

