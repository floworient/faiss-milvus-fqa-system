import json
import re
from pathlib import PurePath
from typing import Any

from app.core.errors import AppError
from app.domain.documents import ParsedDocument


class DocumentValidationError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=422)


class ParserRegistry:
    """Validate and normalize supported document formats."""

    supported_suffixes = {".txt", ".md", ".json"}

    def validate(self, filename: str, content: bytes) -> str:
        source_name = self._source_name(filename)
        suffix = PurePath(source_name).suffix.lower()
        if suffix not in self.supported_suffixes:
            raise DocumentValidationError(
                "unsupported_document_type", "Only TXT, Markdown, and JSON are supported."
            )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise DocumentValidationError(
                "invalid_text_encoding", "Document must be valid UTF-8."
            ) from error
        if not text.strip():
            raise DocumentValidationError("empty_document", "Document must not be empty.")
        if suffix == ".json":
            self._json_entries(text)
        return suffix

    def parse(
        self, document_id: str, filename: str, content: bytes
    ) -> list[ParsedDocument]:
        suffix = self.validate(filename, content)
        source_name = self._source_name(filename)
        text = content.decode("utf-8").strip()
        if suffix == ".json":
            entries = self._json_entries(text)
            return [
                ParsedDocument(
                    document_id=document_id,
                    source_name=source_name,
                    title=entry.get("title"),
                    text=entry["text"],
                    metadata={"format": "json", "json_index": index},
                )
                for index, entry in enumerate(entries)
            ]
        if suffix == ".md":
            headings = [
                match.group(2).strip()
                for match in re.finditer(r"^(#{1,6})\s+(.+?)\s*$", text, re.MULTILINE)
            ]
            h1 = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
            return [
                ParsedDocument(
                    document_id=document_id,
                    source_name=source_name,
                    title=h1.group(1).strip() if h1 else None,
                    text=text,
                    metadata={"format": "markdown", "headings": headings},
                )
            ]
        return [
            ParsedDocument(
                document_id=document_id,
                source_name=source_name,
                title=None,
                text=text,
                metadata={"format": "text"},
            )
        ]

    @staticmethod
    def _source_name(filename: str) -> str:
        normalized = filename.replace("\\", "/")
        source_name = PurePath(normalized).name
        return source_name or "document"

    @staticmethod
    def _json_entries(text: str) -> list[dict[str, str]]:
        try:
            payload: Any = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise DocumentValidationError(
                "invalid_json_document", "JSON document is malformed or unsupported."
            ) from error
        items = payload if isinstance(payload, list) else [payload]
        if not items:
            raise DocumentValidationError(
                "invalid_json_document", "JSON document is malformed or unsupported."
            )
        entries: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                entries = []
                break
            if isinstance(item.get("question"), str) and isinstance(
                item.get("answer"), str
            ):
                question = item["question"].strip()
                answer = item["answer"].strip()
                value = f"问题：{question}\n答案：{answer}"
            else:
                raw = item.get("text", item.get("content"))
                value = raw.strip() if isinstance(raw, str) else ""
            if not value:
                entries = []
                break
            entry = {"text": value}
            if isinstance(item.get("title"), str) and item["title"].strip():
                entry["title"] = item["title"].strip()
            entries.append(entry)
        if not entries:
            raise DocumentValidationError(
                "invalid_json_document", "JSON document is malformed or unsupported."
            )
        return entries
