import json
import time
from dataclasses import asdict
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Literal, Sequence

from app.core.errors import AppError
from app.core.ids import new_id
from app.memory.models import Citation, Conversation, Message


class FileConversationStore:
    def __init__(
        self, root: Path, deleted_sources_file: Path | None = None
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.deleted_sources_file = (
            Path(deleted_sources_file) if deleted_sources_file is not None else None
        )
        self._locks: dict[str, Lock] = {}
        self._locks_guard = Lock()
        self._document_guard = RLock()

    def create(self, metadata: dict[str, Any] | None = None) -> Conversation:
        conversation = Conversation(new_id("session"), metadata=metadata or {})
        self._save(conversation)
        return conversation

    def get(self, session_id: str) -> Conversation:
        path = self._path(session_id)
        if not path.is_file():
            raise AppError("session_not_found", "Session was not found.", 404)
        payload = json.loads(path.read_text("utf-8"))
        messages = [
            Message(
                role=item["role"],
                content=item["content"],
                status=item.get("status", "complete"),
                citations=[Citation(**citation) for citation in item.get("citations", [])],
                metadata=item.get("metadata", {}),
            )
            for item in payload.get("messages", [])
        ]
        conversation = Conversation(
            session_id=payload["session_id"],
            messages=messages,
            metadata=payload.get("metadata", {}),
        )
        self._redact_deleted(conversation)
        return conversation

    def append_user(self, session_id: str, content: str) -> Message:
        return self._append(session_id, Message("user", content.strip()))

    def append_assistant(
        self,
        session_id: str,
        content: str,
        status: Literal["complete", "failed"] = "complete",
        citations: Sequence[Citation] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        safe_citations = [
            Citation(
                item.chunk_id,
                item.document_id,
                item.source_name,
                item.excerpt,
                item.deleted,
            )
            for item in citations or []
        ]
        return self._append(
            session_id,
            Message(
                "assistant", content, status, safe_citations, metadata or {}
            ),
        )

    def history_for_prompt(
        self, session_id: str, max_chars: int, max_turns: int
    ) -> list[Message]:
        messages = [
            item
            for item in self.get(session_id).messages
            if not (item.role == "assistant" and item.status == "failed")
        ]
        messages = messages[-max_turns * 2 :] if max_turns > 0 else []
        selected: list[Message] = []
        used = 0
        for item in reversed(messages):
            size = len(item.content)
            if selected and used + size > max_chars:
                break
            if not selected and size > max_chars:
                continue
            selected.append(item)
            used += size
        return list(reversed(selected))

    def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        if not path.is_file():
            raise AppError("session_not_found", "Session was not found.", 404)
        path.unlink()

    def redact_document(self, document_id: str) -> None:
        """Remove persisted source excerpts for a deleted document."""
        with self._document_guard:
            for path in self.root.glob("session_*.json"):
                session_id = path.stem
                lock = self._lock_for(session_id)
                with lock:
                    conversation = self.get(session_id)
                    changed = False
                    for message in conversation.messages:
                        for citation in message.citations:
                            if citation.document_id == document_id:
                                citation.deleted = True
                                citation.excerpt = None
                                changed = True
                    if changed:
                        self._save(conversation)

    def document_guard(self) -> Any:
        """Serialize document deletion with citation persistence."""
        return self._document_guard

    def _append(self, session_id: str, message: Message) -> Message:
        lock = self._lock_for(session_id)
        with self._document_guard, lock:
            conversation = self.get(session_id)
            conversation.messages.append(message)
            self._save(conversation)
        return message

    def _save(self, conversation: Conversation) -> None:
        self._redact_deleted(conversation)
        target = self._path(conversation.session_id)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(conversation), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._replace_with_retry(temporary, target)

    @staticmethod
    def _replace_with_retry(source: Path, target: Path) -> None:
        for attempt in range(3):
            try:
                source.replace(target)
                return
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.01 * (attempt + 1))

    def _redact_deleted(self, conversation: Conversation) -> None:
        deleted_ids = self._deleted_document_ids()
        if not deleted_ids:
            return
        for message in conversation.messages:
            for citation in message.citations:
                if citation.document_id in deleted_ids:
                    citation.deleted = True
                    citation.excerpt = None

    def _deleted_document_ids(self) -> set[str]:
        path = self.deleted_sources_file
        if path is None or not path.is_file():
            return set()
        payload = json.loads(path.read_text("utf-8"))
        return {
            str(item["document_id"])
            for item in payload
            if isinstance(item, dict)
            and item.get("deleted") is True
            and item.get("document_id")
        }

    def _lock_for(self, session_id: str) -> Lock:
        with self._locks_guard:
            return self._locks.setdefault(session_id, Lock())

    def _path(self, session_id: str) -> Path:
        if not session_id.startswith("session_") or any(
            separator in session_id for separator in ("/", "\\")
        ):
            raise AppError("session_not_found", "Session was not found.", 404)
        return self.root / f"{session_id}.json"
