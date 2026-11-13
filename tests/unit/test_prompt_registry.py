from pathlib import Path

import pytest

from app.core.errors import AppError
from app.prompts.registry import PromptRegistry


def test_contextual_template_renders_required_variables_and_policy() -> None:
    registry = PromptRegistry.default()

    rendered = registry.render(
        "contextual_rag",
        "v1",
        {"question": "如何退货", "history": "上一轮", "context": "七天内"},
    )

    assert "如何退货" in rendered
    assert "上一轮" in rendered
    assert "七天内" in rendered
    assert "仅依据上下文" in rendered
    assert "不确定" in rendered


def test_user_braces_are_treated_as_literal_text() -> None:
    rendered = PromptRegistry.default().render(
        "contextual_rag",
        "v1",
        {"question": "解释 {unknown}", "history": "", "context": "context"},
    )

    assert "解释 {unknown}" in rendered


def test_render_rejects_missing_required_variable() -> None:
    with pytest.raises(AppError) as caught:
        PromptRegistry.default().render(
            "contextual_rag", "v1", {"question": "q", "history": "h"}
        )

    assert caught.value.code == "prompt_variables_missing"


def test_registry_rejects_template_missing_declared_placeholder(tmp_path: Path) -> None:
    (tmp_path / "broken.txt").write_text(
        "---\nname: broken\nversion: v1\nrequired: question,history,context\n---\n"
        "Question: {question}\nHistory: {history}",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing placeholders"):
        PromptRegistry(tmp_path)


def test_unknown_template_returns_safe_error() -> None:
    with pytest.raises(AppError) as caught:
        PromptRegistry.default().render("missing", "v1", {})

    assert caught.value.code == "prompt_template_not_found"
