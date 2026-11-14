"""Generate the versioned Apifox/Postman import bundle from the FastAPI app."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings


COLLECTION_SCHEMA = (
    "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
)
BASE_URL = "{{base_url}}"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _event(listen: str, lines: list[str]) -> dict[str, object]:
    return {
        "listen": listen,
        "script": {"type": "text/javascript", "exec": lines},
    }


def _headers(*extra: tuple[str, str]) -> list[dict[str, str]]:
    values = [("X-Request-ID", "{{request_id}}"), *extra]
    return [{"key": key, "value": value, "type": "text"} for key, value in values]


def _url(path: str) -> dict[str, object]:
    return {
        "raw": f"{BASE_URL}{path}",
        "host": [BASE_URL],
        "path": [segment for segment in path.split("/") if segment],
    }


def _json_body(payload: object) -> dict[str, object]:
    return {
        "mode": "raw",
        "raw": json.dumps(payload, ensure_ascii=False, indent=2),
        "options": {"raw": {"language": "json"}},
    }


def _status_tests(status_code: int, *extra: str) -> list[str]:
    return [
        f"pm.test('HTTP {status_code}', function () {{",
        f"  pm.response.to.have.status({status_code});",
        "});",
        "pm.test('返回 X-Request-ID', function () {",
        "  pm.expect(pm.response.headers.get('X-Request-ID')).to.be.a('string');",
        "});",
        *extra,
    ]


def _request_item(
    name: str,
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
    headers: list[dict[str, str]] | None = None,
    tests: list[str] | None = None,
    description: str = "",
) -> dict[str, object]:
    request: dict[str, object] = {
        "method": method,
        "header": headers if headers is not None else _headers(),
        "url": _url(path),
        "description": description,
    }
    if body is not None:
        request["body"] = body
    item: dict[str, object] = {"name": name, "request": request}
    if tests:
        item["event"] = [_event("test", tests)]
    return item


def _collection() -> dict[str, object]:
    json_headers = _headers(("Content-Type", "application/json"))
    health = _request_item(
        "健康检查",
        "GET",
        "/health",
        tests=_status_tests(
            200,
            "const body = pm.response.json();",
            "pm.test('服务状态正常', function () { pm.expect(body.status).to.eql('ok'); });",
        ),
    )
    upload = _request_item(
        "上传知识文档",
        "POST",
        "/api/v1/documents",
        body={
            "mode": "formdata",
            "formdata": [
                {
                    "key": "file",
                    "type": "file",
                    "src": "fixtures/knowledge.md",
                    "description": "导入后如客户端未解析相对路径，请重新选择同目录文件。",
                }
            ],
        },
        tests=_status_tests(
            202,
            "const body = pm.response.json();",
            "pm.test('返回上传任务', function () {",
            "  pm.expect(body.action).to.eql('upload');",
            "  pm.expect(body.task_id).to.match(/^task_[0-9a-f]{32}$/);",
            "  pm.expect(body.document_id).to.match(/^doc_[0-9a-f]{32}$/);",
            "});",
            "if (pm.response.code === 202 && body.task_id && body.document_id) {",
            "  pm.environment.set('upload_task_id', body.task_id);",
            "  pm.environment.set('task_id', body.task_id);",
            "  pm.environment.set('document_id', body.document_id);",
            "}",
        ),
    )
    upload_task = _request_item(
        "查询上传任务（成功前可重复执行）",
        "GET",
        "/api/v1/tasks/{{upload_task_id}}",
        tests=_status_tests(
            200,
            "const body = pm.response.json();",
            "pm.test('上传任务状态合法', function () {",
            "  pm.expect(['pending', 'running', 'succeeded', 'failed']).to.include(body.status);",
            "});",
            "pm.test('上传任务未失败', function () {",
            "  pm.expect(body.status).not.eql('failed');",
            "});",
            "if (body.status === 'failed') {",
            "  pm.environment.unset('document_id');",
            "  console.error('上传任务失败', body.code, body.message);",
            "}",
            "if (body.status === 'succeeded') {",
            "  pm.environment.set('document_id', body.document_id);",
            "}",
        ),
    )
    list_documents = _request_item(
        "查询文档列表",
        "GET",
        "/api/v1/documents",
        tests=_status_tests(
            200,
            "const body = pm.response.json();",
            "pm.test('文档列表为数组', function () { pm.expect(body).to.be.an('array'); });",
        ),
    )
    delete_document = _request_item(
        "删除知识文档",
        "DELETE",
        "/api/v1/documents/{{document_id}}",
        tests=_status_tests(
            202,
            "const body = pm.response.json();",
            "pm.test('返回删除任务', function () { pm.expect(body.action).to.eql('delete'); });",
            "if (pm.response.code === 202 && body.task_id) {",
            "  pm.environment.set('delete_task_id', body.task_id);",
            "  pm.environment.set('task_id', body.task_id);",
            "}",
        ),
    )
    delete_task = _request_item(
        "查询删除任务（成功前可重复执行）",
        "GET",
        "/api/v1/tasks/{{delete_task_id}}",
        tests=_status_tests(
            200,
            "const body = pm.response.json();",
            "pm.test('删除任务状态合法', function () {",
            "  pm.expect(['pending', 'running', 'succeeded', 'failed']).to.include(body.status);",
            "});",
            "pm.test('删除任务未失败', function () {",
            "  pm.expect(body.status).not.eql('failed');",
            "});",
            "if (body.status === 'failed') {",
            "  console.error('删除任务失败', body.code, body.message);",
            "}",
        ),
    )

    def retrieval(name: str, mode: str) -> dict[str, object]:
        return _request_item(
            name,
            "POST",
            "/api/v1/retrieval/search",
            headers=json_headers,
            body=_json_body(
                {"query": "{{query}}", "mode": mode, "top_k": 5, "candidate_k": 20}
            ),
            tests=_status_tests(
                200,
                "const body = pm.response.json();",
                f"pm.test('检索模式为 {mode}', function () {{ pm.expect(body.mode).to.eql('{mode}'); }});",
                "pm.test('检索结果为数组', function () { pm.expect(body.results).to.be.an('array'); });",
            ),
        )

    chat_body = {
        "question": "{{query}}",
        "strategy": "contextual_rag",
        "retrieval_mode": "hybrid",
        "top_k": 5,
        "candidate_k": 20,
    }
    chat = _request_item(
        "非流式知识问答",
        "POST",
        "/api/v1/chat/completions",
        headers=json_headers,
        body=_json_body(chat_body),
        tests=_status_tests(
            200,
            "const body = pm.response.json();",
            "pm.test('回答结构正确', function () {",
            "  pm.expect(body.answer).to.be.a('string');",
            "  pm.expect([1, 2, 3]).to.include(body.provider_tier);",
            "  pm.expect(body.citations).to.be.an('array');",
            "});",
            "if (pm.response.code === 200 && body.session_id) {",
            "  pm.environment.set('session_id', body.session_id);",
            "}",
        ),
    )
    stream = _request_item(
        "SSE 流式知识问答",
        "POST",
        "/api/v1/chat/completions/stream",
        headers=_headers(
            ("Content-Type", "application/json"), ("Accept", "text/event-stream")
        ),
        body=_json_body(chat_body),
        tests=_status_tests(
            200,
            "pm.test('响应为 text/event-stream', function () {",
            "  pm.expect(pm.response.headers.get('Content-Type')).to.include('text/event-stream');",
            "});",
        ),
        description=(
            "请在 Apifox SSE 调试界面检查事件顺序：meta → retrieval → token → done/error。"
        ),
    )
    get_session = _request_item(
        "查询会话历史",
        "GET",
        "/api/v1/sessions/{{session_id}}",
        tests=_status_tests(
            200,
            "const body = pm.response.json();",
            "pm.test('会话 ID 匹配', function () {",
            "  pm.expect(body.session_id).to.eql(pm.environment.get('session_id'));",
            "});",
        ),
    )
    delete_session = _request_item(
        "删除会话",
        "DELETE",
        "/api/v1/sessions/{{session_id}}",
        tests=[
            "pm.test('HTTP 204', function () { pm.response.to.have.status(204); });",
            "if (pm.response.code === 204) { pm.environment.unset('session_id'); }",
        ],
    )
    evaluation = _request_item(
        "运行检索评测",
        "POST",
        "/api/v1/evaluations/retrieval",
        body={
            "mode": "formdata",
            "formdata": [
                {
                    "key": "file",
                    "type": "file",
                    "src": "fixtures/evaluation.runtime.jsonl",
                    "description": "先运行 prepare_evaluation.py 写入当前 document_id。",
                },
                {"key": "mode", "value": "hybrid", "type": "text"},
                {"key": "top_k", "value": "5", "type": "text"},
                {
                    "key": "dataset_name",
                    "value": "apifox-smoke",
                    "type": "text",
                },
            ],
        },
        tests=_status_tests(
            200,
            "const body = pm.response.json();",
            "pm.test('评测报告结构正确', function () {",
            "  pm.expect(body.query_count).to.be.a('number');",
            "  pm.expect(body.queries).to.be.an('array');",
            "});",
        ),
    )
    invalid_retrieval = _request_item(
        "非法检索参数（预期 422）",
        "POST",
        "/api/v1/retrieval/search",
        headers=json_headers,
        body=_json_body(
            {"query": "{{query}}", "mode": "hybrid", "top_k": 0, "candidate_k": 20}
        ),
        tests=[
            "pm.test('HTTP 422', function () { pm.response.to.have.status(422); });",
            "const body = pm.response.json();",
            "pm.test('包含参数校验详情', function () { pm.expect(body.detail).to.be.an('array'); });",
        ],
    )
    missing_task = _request_item(
        "不存在的任务（预期 404）",
        "GET",
        "/api/v1/tasks/{{missing_task_id}}",
        tests=[
            "pm.test('HTTP 404', function () { pm.response.to.have.status(404); });",
            "const body = pm.response.json();",
            "pm.test('错误码正确', function () { pm.expect(body.code).to.eql('task_not_found'); });",
        ],
    )
    missing_session = _request_item(
        "不存在的会话（预期 404）",
        "GET",
        "/api/v1/sessions/{{missing_session_id}}",
        tests=[
            "pm.test('HTTP 404', function () { pm.response.to.have.status(404); });",
            "const body = pm.response.json();",
            "pm.test('错误码正确', function () { pm.expect(body.code).to.eql('session_not_found'); });",
        ],
    )

    return {
        "info": {
            "name": "RAG Knowledge QA API",
            "description": (
                "面向 Apifox 的完整调试集合。先导入 local 环境并按 README 执行。"
            ),
            "schema": COLLECTION_SCHEMA,
        },
        "event": [
            _event(
                "prerequest",
                [
                    "const suffix = Date.now() + '_' + Math.random().toString(16).slice(2);",
                    "pm.environment.set('request_id', 'req_apifox_' + suffix);",
                ],
            )
        ],
        "variable": [{"key": "base_url", "value": "http://127.0.0.1:8000"}],
        "item": [
            {"name": "00 系统", "item": [health]},
            {
                "name": "01 文档与任务",
                "item": [
                    upload,
                    upload_task,
                    list_documents,
                    delete_document,
                    delete_task,
                ],
            },
            {
                "name": "02 检索",
                "item": [
                    retrieval("关键词检索", "keyword"),
                    retrieval("向量检索", "vector"),
                    retrieval("混合检索", "hybrid"),
                ],
            },
            {"name": "03 问答", "item": [chat, stream]},
            {"name": "04 会话", "item": [get_session, delete_session]},
            {"name": "05 评测", "item": [evaluation]},
            {
                "name": "06 异常用例",
                "item": [invalid_retrieval, missing_task, missing_session],
            },
        ],
    }


def _environment() -> dict[str, object]:
    values = {
        "base_url": "http://127.0.0.1:8000",
        "query": "退货政策是什么？",
        "request_id": "",
        "task_id": "",
        "upload_task_id": "",
        "delete_task_id": "",
        "document_id": "",
        "session_id": "",
        "missing_task_id": "task_00000000000000000000000000000000",
        "missing_session_id": "session_00000000000000000000000000000000",
    }
    return {
        "id": "rag-knowledge-qa-local",
        "name": "RAG Knowledge QA - Local",
        "values": [
            {"key": key, "value": value, "enabled": True, "type": "default"}
            for key, value in values.items()
        ],
        "_postman_variable_scope": "environment",
        "_postman_exported_using": "RAG Knowledge QA bundle generator",
    }


README = """# Apifox 导入与调试

本目录是 `RAG Knowledge QA API 0.1.0` 的完整 Apifox 导入包。

## 导入顺序

1. 启动后端，确认 `http://127.0.0.1:8000/health` 返回 `ok`。
2. 在 Apifox 中导入 `openapi.json`，用于创建接口和数据模型。
3. 导入 `rag-knowledge-qa.postman_collection.json`，用于导入示例、脚本和断言。若导入到同一项目时出现重复接口，请选择合并或覆盖，不要保留两份。
4. 导入 `local.postman_environment.json` 并切换到 `RAG Knowledge QA - Local` 环境。
5. 文件字段若没有自动解析相对路径，请手动选择 `fixtures/knowledge.md`；评测文件按下文生成。

## 推荐端到端顺序

1. `00 系统 / 健康检查`
2. `01 文档与任务 / 上传知识文档`
3. 重复执行“查询上传任务”，直到 `status` 为 `succeeded`；若为 `failed`，断言会失败并显示 `code/message`，停止后续流程
4. 执行文档列表、关键词/向量/混合检索
5. 执行非流式问答；脚本会保存 `session_id`
6. 查询会话历史
7. 在 Apifox SSE 调试器中执行流式问答
8. 从 Apifox 环境复制 `document_id`，生成带真实标签的评测文件：

   ```powershell
   python -X utf8 docs/apifox/prepare_evaluation.py --document-id doc_实际值
   ```

9. 在评测请求中选择 `fixtures/evaluation.runtime.jsonl` 后运行检索评测；正确检索该文档时 Hit@1、Recall@K 和 MRR 应大于 0
10. 删除会话、删除文档，并轮询删除任务直到成功；若删除任务为 `failed`，保留 `document_id` 并检查错误信息

上传和删除是异步任务。集合不会自动无限轮询，避免接口失败时卡死运行器。轮询脚本接受 `pending/running/succeeded`，但会把终态 `failed` 标记为断言失败。

## SSE 验收

流式接口请求头包含 `Accept: text/event-stream`。预期事件顺序为：

```text
meta → retrieval → token（一个或多个）→ done
```

异常时最后一个事件可能是 `error`。Collection 只断言 HTTP 状态和 Content-Type；事件内容请在 Apifox SSE 调试界面查看。

## 环境变量

`request_id` 由 Collection 前置脚本自动刷新。上传、删除和问答成功后，后置脚本会写入 `upload_task_id`、`delete_task_id`、`document_id` 和 `session_id`。环境中不保存 DashScope Key；模型密钥只配置在后端 `.env`。

## 重新生成

后端路由或 Schema 变化后，在仓库根目录执行：

```powershell
python -X utf8 scripts/generate_apifox_bundle.py
python -X utf8 -m pytest tests/unit/test_apifox_bundle.py -q
```

OpenAPI 的权威来源仍是 FastAPI `create_app()`；不要手工修改生成的 JSON。
"""


PREPARE_EVALUATION = '''"""Materialize an evaluation JSONL file with the uploaded document ID."""

import argparse
import json
import re
from pathlib import Path


DOCUMENT_ID_PATTERN = re.compile(r"doc_[0-9a-f]{32}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "fixtures" / "evaluation.runtime.jsonl",
    )
    arguments = parser.parse_args()
    if DOCUMENT_ID_PATTERN.fullmatch(arguments.document_id) is None:
        parser.error("--document-id must match doc_<32 lowercase hex characters>")

    template = Path(__file__).parent / "fixtures" / "evaluation.template.jsonl"
    rows = []
    for line in template.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row["relevant_document_ids"] = [arguments.document_id]
        rows.append(json.dumps(row, ensure_ascii=False))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text("\\n".join(rows) + "\\n", encoding="utf-8")
    print(f"Generated evaluation fixture at {arguments.output.resolve()}")


if __name__ == "__main__":
    main()
'''


def _openapi() -> dict[str, Any]:
    from app.main import ServiceContainer, create_app

    with tempfile.TemporaryDirectory(prefix="rag-apifox-openapi-") as directory:
        settings = Settings(
            _env_file=None,
            dashscope_api_key=None,
            data_dir=Path(directory) / "runtime",
        )
        app = create_app(settings, ServiceContainer())
        schema = app.openapi()
    schema["servers"] = [
        {"url": "http://127.0.0.1:8000", "description": "本地开发环境"}
    ]
    return schema


def generate_bundle(output_dir: Path) -> None:
    output_dir = Path(output_dir)
    fixtures = output_dir / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)

    _write_json(output_dir / "openapi.json", _openapi())
    _write_json(
        output_dir / "rag-knowledge-qa.postman_collection.json", _collection()
    )
    _write_json(output_dir / "local.postman_environment.json", _environment())
    (fixtures / "knowledge.md").write_text(
        "# 售后知识库\n\n## 退货政策\n\n商品签收后七天内可以申请退货。\n",
        encoding="utf-8",
        newline="\n",
    )
    (fixtures / "evaluation.template.jsonl").write_text(
        json.dumps(
            {
                "query": "退货政策是什么？",
                "relevant_document_ids": ["__DOCUMENT_ID_FROM_UPLOAD__"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output_dir / "prepare_evaluation.py").write_text(
        PREPARE_EVALUATION, encoding="utf-8", newline="\n"
    )
    (output_dir / "README.md").write_text(
        README, encoding="utf-8", newline="\n"
    )


def bundle_matches_generated(output_dir: Path) -> bool:
    output_dir = Path(output_dir)
    with tempfile.TemporaryDirectory(prefix="rag-apifox-verify-") as directory:
        expected_root = Path(directory) / "bundle"
        generate_bundle(expected_root)
        for expected in expected_root.rglob("*"):
            if not expected.is_file():
                continue
            candidate = output_dir / expected.relative_to(expected_root)
            if not candidate.is_file() or candidate.read_bytes() != expected.read_bytes():
                return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/apifox"),
        help="Bundle output directory (default: docs/apifox)",
    )
    arguments = parser.parse_args()
    generate_bundle(arguments.output)
    print(f"Generated Apifox bundle at {arguments.output.resolve()}")


if __name__ == "__main__":
    main()
