import json
import os
from pathlib import Path
import subprocess
import sys

from scripts.generate_apifox_bundle import generate_bundle


EXPECTED_OPERATIONS = {
    ("GET", "/health"),
    ("POST", "/api/v1/documents"),
    ("GET", "/api/v1/documents"),
    ("GET", "/api/v1/tasks/{task_id}"),
    ("DELETE", "/api/v1/documents/{document_id}"),
    ("POST", "/api/v1/retrieval/search"),
    ("POST", "/api/v1/chat/completions"),
    ("POST", "/api/v1/chat/completions/stream"),
    ("GET", "/api/v1/sessions/{session_id}"),
    ("DELETE", "/api/v1/sessions/{session_id}"),
    ("POST", "/api/v1/evaluations/retrieval"),
}


def _load(path: Path) -> object:
    return json.loads(path.read_text("utf-8"))


def _requests(items: list[dict[str, object]]) -> list[dict[str, object]]:
    flattened: list[dict[str, object]] = []
    for item in items:
        nested = item.get("item")
        if isinstance(nested, list):
            flattened.extend(_requests(nested))
        elif "request" in item:
            flattened.append(item)
    return flattened


def _collection_operations(collection: dict[str, object]) -> set[tuple[str, str]]:
    operations: set[tuple[str, str]] = set()
    for item in _requests(collection["item"]):  # type: ignore[arg-type]
        request = item["request"]
        method = request["method"]
        raw = request["url"]["raw"]
        path = raw.removeprefix("{{base_url}}")
        path = path.replace("{{task_id}}", "{task_id}")
        path = path.replace("{{upload_task_id}}", "{task_id}")
        path = path.replace("{{delete_task_id}}", "{task_id}")
        path = path.replace("{{document_id}}", "{document_id}")
        path = path.replace("{{session_id}}", "{session_id}")
        operations.add((method, path))
    return operations


def test_generate_bundle_covers_api_and_variable_flow(tmp_path: Path) -> None:
    generate_bundle(tmp_path)

    openapi = _load(tmp_path / "openapi.json")
    collection = _load(tmp_path / "rag-knowledge-qa.postman_collection.json")
    environment = _load(tmp_path / "local.postman_environment.json")

    openapi_operations = {
        (method.upper(), path)
        for path, path_item in openapi["paths"].items()
        for method in path_item
        if method.lower() in {"get", "post", "delete", "put", "patch"}
    }
    assert openapi_operations == EXPECTED_OPERATIONS
    assert _collection_operations(collection) >= EXPECTED_OPERATIONS
    assert collection["info"]["schema"].endswith(
        "/collection/v2.1.0/collection.json"
    )

    values = {item["key"]: item["value"] for item in environment["values"]}
    assert values["base_url"] == "http://127.0.0.1:8000"
    assert values["query"] == "退货政策是什么？"
    assert values["upload_task_id"] == ""
    assert values["delete_task_id"] == ""
    assert values["document_id"] == ""
    assert values["session_id"] == ""

    collection_text = json.dumps(collection, ensure_ascii=False)
    assert "pm.test" in collection_text
    assert "pm.environment.set('upload_task_id'" in collection_text
    assert "pm.environment.set('delete_task_id'" in collection_text
    assert "pm.environment.set('document_id'" in collection_text
    assert "pm.environment.set('session_id'" in collection_text
    assert "X-Request-ID" in collection_text


def test_generate_bundle_keeps_files_portable_and_sse_non_json(
    tmp_path: Path,
) -> None:
    generate_bundle(tmp_path)
    collection = _load(tmp_path / "rag-knowledge-qa.postman_collection.json")
    requests = _requests(collection["item"])  # type: ignore[arg-type]

    file_sources: list[str] = []
    sse_scripts: list[str] = []
    for item in requests:
        request = item["request"]
        body = request.get("body", {})
        for field in body.get("formdata", []):
            if field.get("type") == "file":
                file_sources.append(field["src"])
        if request["url"]["raw"].endswith("/completions/stream"):
            sse_scripts = [
                line
                for event in item.get("event", [])
                for script in [event.get("script", {})]
                for line in script.get("exec", [])
            ]

    assert file_sources == ["fixtures/knowledge.md", "fixtures/evaluation.jsonl"]
    assert all(not Path(source).is_absolute() for source in file_sources)
    assert (tmp_path / "fixtures" / "knowledge.md").is_file()
    assert (tmp_path / "fixtures" / "evaluation.jsonl").is_file()
    assert "pm.response.json()" not in "\n".join(sse_scripts)
    assert "text/event-stream" in "\n".join(sse_scripts)


def test_generate_bundle_is_deterministic_and_contains_no_secrets(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_bundle(first)
    generate_bundle(second)

    relative_files = {
        path.relative_to(first)
        for path in first.rglob("*")
        if path.is_file()
    }
    assert relative_files == {
        path.relative_to(second)
        for path in second.rglob("*")
        if path.is_file()
    }
    for relative_path in relative_files:
        first_text = (first / relative_path).read_text("utf-8")
        assert first_text == (second / relative_path).read_text("utf-8")
        assert "sk-" not in first_text
        assert "DASHSCOPE_API_KEY" not in first_text


def test_generator_cli_runs_directly_from_repository_root(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    output_dir = tmp_path / "cli-output"
    environment = os.environ.copy()
    environment["RAG_DASHSCOPE_API_KEY"] = ""

    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "scripts/generate_apifox_bundle.py",
            "--output",
            str(output_dir),
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "openapi.json").is_file()
