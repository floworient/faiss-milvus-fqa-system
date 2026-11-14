import re
from pathlib import Path


README = Path("README.md")


def test_readme_declares_preview_scope_and_security_boundary() -> None:
    content = README.read_text("utf-8")
    assert "开发预览版" in content
    assert "已实现" in content
    assert "规划中" in content
    assert "不要直接暴露到公网" in content
    assert "无需 API Key" in content
    assert "DashScope" in content
    assert "目标指标（尚未复现）" in content
    assert not re.search(r"(?:实测|已验证).{0,20}73%\s*(?:→|提升至)\s*85%\+", content)


def test_readme_links_assets_and_documents_that_exist() -> None:
    content = README.read_text("utf-8")
    required_links = (
        "docs/image/rag-qa-logo.svg",
        "docs/image/rag-qa-architecture.svg",
        "docs/architecture.md",
        "INSTALL_TROUBLESHOOTING.md",
    )
    for target in required_links:
        assert target in content
        assert Path(target).is_file()


def test_readme_documents_verified_public_commands() -> None:
    content = README.read_text("utf-8")
    for command in (
        "uvicorn app.main:create_app --factory",
        "python scripts/smoke_test.py --base-url http://127.0.0.1:8000",
        "python -m pytest -q",
        "python -m app.evaluation.cli",
    ):
        assert command in content
    for route in (
        "/docs",
        "/api/v1/documents",
        "/api/v1/retrieval/search",
        "/api/v1/chat/completions/stream",
        "/api/v1/evaluations/retrieval",
    ):
        assert route in content
    for event in ("meta", "retrieval", "token", "fallback", "error", "done"):
        assert f"`{event}`" in content


def test_troubleshooting_guide_explains_legacy_transition() -> None:
    content = Path("INSTALL_TROUBLESHOOTING.md").read_text("utf-8")
    assert "旧版入口与索引迁移" in content
    assert "ask.py" in content
    assert "train.py" in content
    assert "uvicorn app.main:create_app --factory" in content
    assert "不兼容" in content
