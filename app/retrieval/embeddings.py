from typing import Protocol, Sequence

import numpy as np
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


class DashScopeEmbeddingAdapter:
    """LlamaIndex DashScope embedding adapter without global Settings mutation."""

    def __init__(self, api_key: str, model: str, dimension: int) -> None:
        from llama_index.embeddings.dashscope import DashScopeEmbedding

        self._model = DashScopeEmbedding(
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

