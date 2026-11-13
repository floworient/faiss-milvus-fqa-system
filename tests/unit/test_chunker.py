from pathlib import Path

from app.core.config import Settings
from app.domain.documents import ParsedDocument
from app.ingestion.chunker import AdaptiveChunker


class WhitespaceTokenizer:
    def encode(self, text: str) -> list[str]:
        return text.split()

    def decode(self, tokens: list[str]) -> str:
        return " ".join(tokens)


class CharacterTokenizer:
    def encode(self, text: str) -> list[str]:
        return list(text)

    def decode(self, tokens: list[str]) -> str:
        return "".join(tokens)


def settings(tmp_path: Path, minimum: int = 256, maximum: int = 768) -> Settings:
    return Settings(
        data_dir=tmp_path,
        chunk_min_tokens=minimum,
        chunk_max_tokens=maximum,
        chunk_overlap_ratio=0.1,
    )


def document(text: str, metadata: dict | None = None) -> ParsedDocument:
    return ParsedDocument(
        document_id="doc_1",
        source_name="guide.md",
        title="指南",
        text=text,
        metadata=metadata or {},
    )


def test_short_document_yields_one_non_empty_chunk(tmp_path: Path) -> None:
    chunks = AdaptiveChunker(settings(tmp_path), WhitespaceTokenizer()).split(
        document("short useful answer")
    )

    assert [chunk.text for chunk in chunks] == ["short useful answer"]
    assert chunks[0].token_count == 3


def test_chunk_metadata_preserves_markdown_headings(tmp_path: Path) -> None:
    chunks = AdaptiveChunker(settings(tmp_path), WhitespaceTokenizer()).split(
        document("return policy", {"headings": ["售后", "退货"]})
    )

    assert chunks[0].metadata["headings"] == ["售后", "退货"]
    assert chunks[0].metadata["source_name"] == "guide.md"


def test_long_paragraph_uses_bounded_overlapping_windows(tmp_path: Path) -> None:
    text = " ".join(f"token{i}" for i in range(900))
    chunks = AdaptiveChunker(
        settings(tmp_path, minimum=256, maximum=300), WhitespaceTokenizer()
    ).split(document(text))

    assert all(256 <= chunk.token_count <= 300 for chunk in chunks[:-1])
    assert 0 < chunks[-1].token_count <= 300
    first = chunks[0].text.split()
    second = chunks[1].text.split()
    assert first[-30:] == second[:30]


def test_chinese_without_spaces_splits_deterministically(tmp_path: Path) -> None:
    source = "退货政策适用于签收后七天内。" * 80
    chunker = AdaptiveChunker(
        settings(tmp_path, minimum=80, maximum=120), CharacterTokenizer()
    )

    first = chunker.split(document(source))
    second = chunker.split(document(source))

    assert len(first) > 1
    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]
    assert [item.text for item in first] == [item.text for item in second]


def test_empty_sections_never_produce_chunks(tmp_path: Path) -> None:
    chunks = AdaptiveChunker(settings(tmp_path), WhitespaceTokenizer()).split(
        document("\n\n useful section \n\n\n")
    )

    assert len(chunks) == 1
    assert chunks[0].text == "useful section"
