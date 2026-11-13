import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from app.domain.documents import Chunk


@dataclass(frozen=True, slots=True)
class RankedChunk:
    chunk: Chunk
    rank: int
    score: float
    vector_rank: int | None = None
    keyword_rank: int | None = None


class KeywordIndex:
    """A compact BM25 index with Latin tokens and Chinese bigrams."""

    def __init__(self, chunks: list[Chunk], terms: list[list[str]]) -> None:
        self.chunks = chunks
        self.terms = terms
        self.document_frequency: Counter[str] = Counter()
        for unique_terms in map(set, terms):
            self.document_frequency.update(unique_terms)
        self.average_length = (
            sum(map(len, terms)) / len(terms) if terms else 0.0
        )

    @classmethod
    def build(cls, chunks: Sequence[Chunk]) -> "KeywordIndex":
        unique: dict[str, Chunk] = {}
        for item in chunks:
            unique.setdefault(item.chunk_id, item)
        ordered = [unique[key] for key in sorted(unique)]
        return cls(ordered, [cls.tokenize(item.text) for item in ordered])

    def search(self, query: str, limit: int) -> list[RankedChunk]:
        query_terms = self.tokenize(query)
        if not query_terms or not self.chunks or limit <= 0:
            return []
        scored: list[tuple[float, Chunk]] = []
        corpus_size = len(self.chunks)
        for item, document_terms in zip(self.chunks, self.terms, strict=True):
            frequencies = Counter(document_terms)
            score = 0.0
            for term in query_terms:
                frequency = frequencies[term]
                if frequency == 0:
                    continue
                frequency_docs = self.document_frequency[term]
                inverse_frequency = math.log(
                    1 + (corpus_size - frequency_docs + 0.5) / (frequency_docs + 0.5)
                )
                length_ratio = (
                    len(document_terms) / self.average_length
                    if self.average_length
                    else 0.0
                )
                denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * length_ratio)
                score += inverse_frequency * (frequency * 2.5 / denominator)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1].chunk_id))
        return [
            RankedChunk(
                chunk=item,
                rank=rank,
                score=score,
                keyword_rank=rank,
            )
            for rank, (score, item) in enumerate(scored[:limit], start=1)
        ]

    def to_dict(self) -> dict[str, Any]:
        return {"chunks": [asdict(item) for item in self.chunks]}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KeywordIndex":
        return cls.build([Chunk(**item) for item in payload.get("chunks", [])])

    @staticmethod
    def tokenize(text: str) -> list[str]:
        lowered = text.lower()
        terms = re.findall(r"[a-z0-9_]+", lowered)
        for sequence in re.findall(r"[\u4e00-\u9fff]+", lowered):
            if len(sequence) == 1:
                terms.append(sequence)
            else:
                terms.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
        return terms
