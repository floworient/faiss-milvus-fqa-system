from pathlib import Path

from app.main import create_app


def test_api_document_covers_every_openapi_operation() -> None:
    content = Path("docs/api.md").read_text("utf-8")
    schema = create_app().openapi()

    for path, operations in schema["paths"].items():
        assert f"`{path}`" in content
        for method in operations:
            assert f"`{method.upper()}`" in content


def test_api_document_covers_runtime_contracts() -> None:
    content = Path("docs/api.md").read_text("utf-8")

    for token in (
        "X-Request-ID",
        "202 Accepted",
        "text/event-stream",
        "provider_tier",
        "hit_at_1",
        "recall_at_k",
        "request_id",
    ):
        assert token in content
    for event in ("meta", "retrieval", "token", "fallback", "error", "done"):
        assert f"`{event}`" in content
