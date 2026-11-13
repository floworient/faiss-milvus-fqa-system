import json
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.memory.models import Citation
from app.memory.store import FileConversationStore


def test_create_and_append_persist_atomic_valid_json(tmp_path: Path) -> None:
    store = FileConversationStore(tmp_path)
    conversation = store.create()
    store.append_user(conversation.session_id, "如何退货")
    store.append_assistant(conversation.session_id, "七天内申请")

    loaded = store.get(conversation.session_id)
    payload = json.loads((tmp_path / f"{conversation.session_id}.json").read_text("utf-8"))

    assert loaded.session_id == conversation.session_id
    assert [item.content for item in loaded.messages] == ["如何退货", "七天内申请"]
    assert payload["session_id"] == conversation.session_id
    assert list(tmp_path.glob("*.tmp")) == []


def test_history_prunes_oldest_complete_turns_by_turn_and_character_budget(
    tmp_path: Path,
) -> None:
    store = FileConversationStore(tmp_path)
    session = store.create().session_id
    store.append_user(session, "oldq")
    store.append_assistant(session, "olda")
    store.append_user(session, "newq")
    store.append_assistant(session, "newa")

    by_turn = store.history_for_prompt(session, max_chars=100, max_turns=1)
    by_chars = store.history_for_prompt(session, max_chars=8, max_turns=10)

    assert [item.content for item in by_turn] == ["newq", "newa"]
    assert [item.content for item in by_chars] == ["newq", "newa"]


def test_failed_assistant_is_excluded_but_preceding_user_is_retained(
    tmp_path: Path,
) -> None:
    store = FileConversationStore(tmp_path)
    session = store.create().session_id
    store.append_user(session, "question")
    store.append_assistant(session, "partial", status="failed")

    history = store.history_for_prompt(session, max_chars=100, max_turns=5)

    assert [item.content for item in history] == ["question"]
    assert store.get(session).messages[-1].content == "partial"


def test_deleted_source_citation_never_persists_excerpt(tmp_path: Path) -> None:
    store = FileConversationStore(tmp_path)
    session = store.create().session_id

    store.append_assistant(
        session,
        "historical answer",
        citations=[Citation("chk_1", "doc_1", "secret.md", "secret text", True)],
    )

    citation = store.get(session).messages[0].citations[0]
    assert citation.deleted is True
    assert citation.excerpt is None


def test_delete_removes_session_file(tmp_path: Path) -> None:
    store = FileConversationStore(tmp_path)
    session = store.create().session_id

    store.delete(session)

    assert not (tmp_path / f"{session}.json").exists()
    with pytest.raises(AppError) as caught:
        store.get(session)
    assert caught.value.code == "session_not_found"


def test_atomic_save_retries_a_transient_windows_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileConversationStore(tmp_path)
    session = store.create().session_id
    original_replace = Path.replace
    attempts = 0

    def flaky_replace(path: Path, target: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError(5, "target is temporarily locked")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    store.append_user(session, "message")

    assert attempts == 2
    assert store.get(session).messages[0].content == "message"
