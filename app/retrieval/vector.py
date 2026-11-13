from typing import Sequence

import faiss
import numpy as np
from numpy.typing import NDArray

from app.domain.documents import Chunk
from app.retrieval.keyword import RankedChunk


class FaissIndex:
    def __init__(self, index: faiss.Index, chunks: Sequence[Chunk]) -> None:
        self.index = index
        self.chunks = list(chunks)

    @classmethod
    def build(
        cls, chunks: Sequence[Chunk], vectors: NDArray[np.float32]
    ) -> "FaissIndex":
        matrix = np.asarray(vectors, dtype=np.float32).copy()
        if matrix.ndim != 2:
            raise ValueError("vectors must be a two-dimensional matrix")
        if len(chunks) != matrix.shape[0]:
            raise ValueError("chunk and vector counts must match")
        if matrix.shape[1] <= 0:
            raise ValueError("vector dimension must be positive")
        faiss.normalize_L2(matrix)
        index = faiss.IndexFlatIP(matrix.shape[1])
        if len(matrix):
            index.add(matrix)
        return cls(index, chunks)

    def search(
        self, vector: NDArray[np.float32], limit: int
    ) -> list[RankedChunk]:
        if not self.chunks or limit <= 0:
            return []
        query = np.asarray(vector, dtype=np.float32).reshape(1, -1).copy()
        if query.shape[1] != self.index.d:
            raise ValueError("query vector dimension does not match index")
        faiss.normalize_L2(query)
        scores, indices = self.index.search(query, min(limit, len(self.chunks)))
        return [
            RankedChunk(
                chunk=self.chunks[index],
                rank=rank,
                score=float(score),
                vector_rank=rank,
            )
            for rank, (score, index) in enumerate(
                zip(scores[0], indices[0], strict=True), start=1
            )
            if index >= 0
        ]

