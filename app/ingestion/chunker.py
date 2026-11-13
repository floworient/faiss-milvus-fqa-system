import hashlib
import re
from typing import Protocol

from app.core.config import Settings
from app.domain.documents import Chunk, ParsedDocument


class TokenizerPort(Protocol):
    def encode(self, text: str) -> list[str]: ...

    def decode(self, tokens: list[str]) -> str: ...


class RegexTokenizer:
    """A deterministic local tokenizer suitable for chunk sizing and tests."""

    _pattern = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+|[^\s]", re.UNICODE)

    def encode(self, text: str) -> list[str]:
        return self._pattern.findall(text)

    def decode(self, tokens: list[str]) -> str:
        output: list[str] = []
        for token in tokens:
            if output and token.isascii() and token.isalnum() and output[-1][-1:].isascii():
                output.append(" ")
            output.append(token)
        return "".join(output)


class AdaptiveChunker:
    version = "chunker-v1"

    def __init__(self, settings: Settings, tokenizer: TokenizerPort) -> None:
        self.settings = settings
        self.tokenizer = tokenizer

    def split(self, document: ParsedDocument) -> list[Chunk]:
        text = document.text.strip()
        if not text:
            return []
        tokens = self.tokenizer.encode(text)
        if not tokens:
            return []
        target = self._target_size(len(tokens))
        overlap = min(int(target * self.settings.chunk_overlap_ratio), target - 1)
        step = max(1, target - overlap)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        chunks: list[Chunk] = []
        position = 0
        for start in range(0, len(tokens), step):
            window = tokens[start : start + target]
            chunk_text = self.tokenizer.decode(window).strip()
            if chunk_text:
                identity = (
                    f"{document.source_name}\0{digest}\0{self.version}\0{position}"
                )
                chunk_id = "chk_" + hashlib.sha256(identity.encode()).hexdigest()[:24]
                metadata = dict(document.metadata)
                metadata.update(
                    {
                        "source_name": document.source_name,
                        "title": document.title,
                        "chunker_version": self.version,
                    }
                )
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        document_id=document.document_id,
                        text=chunk_text,
                        position=position,
                        token_count=len(window),
                        metadata=metadata,
                    )
                )
                position += 1
            if start + target >= len(tokens):
                break
        return chunks

    def _target_size(self, token_count: int) -> int:
        if token_count <= self.settings.chunk_min_tokens:
            return token_count
        if token_count <= self.settings.chunk_max_tokens:
            return token_count
        return self.settings.chunk_max_tokens
