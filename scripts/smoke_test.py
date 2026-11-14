import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx


async def _wait_for_task(
    client: httpx.AsyncClient, task_id: str, *, attempts: int = 50
) -> dict[str, Any]:
    for _ in range(attempts):
        response = await client.get(f"/api/v1/tasks/{task_id}")
        response.raise_for_status()
        task = response.json()
        if task["status"] in {"succeeded", "failed"}:
            if task["status"] == "failed":
                raise RuntimeError(f"Task failed with code {task.get('code')}")
            return task
        await asyncio.sleep(0.05)
    raise TimeoutError(f"Task {task_id} did not finish")


def _sse_events(body: str) -> list[str]:
    return [
        line.removeprefix("event: ")
        for line in body.splitlines()
        if line.startswith("event: ")
    ]


async def run_smoke(
    client: httpx.AsyncClient, document: bytes, *, source_name: str = "knowledge.md"
) -> dict[str, Any]:
    upload = await client.post(
        "/api/v1/documents",
        files={"file": (source_name, document, "text/markdown")},
    )
    upload.raise_for_status()
    upload_task = await _wait_for_task(client, upload.json()["task_id"])

    retrieval = await client.post(
        "/api/v1/retrieval/search",
        json={"query": "退货政策", "mode": "hybrid", "top_k": 5},
    )
    retrieval.raise_for_status()
    results = retrieval.json()["results"]
    if not results:
        raise AssertionError("Uploaded document was not retrieved")

    chat = await client.post(
        "/api/v1/chat/completions", json={"question": "如何申请退货？"}
    )
    chat.raise_for_status()

    stream = await client.post(
        "/api/v1/chat/completions/stream", json={"question": "请流式回答退货政策"}
    )
    stream.raise_for_status()

    dataset = json.dumps(
        {
            "query": "退货政策",
            "relevant_chunk_ids": [results[0]["chunk_id"]],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    evaluation = await client.post(
        "/api/v1/evaluations/retrieval",
        data={"mode": "hybrid", "top_k": "5"},
        files={"file": ("evaluation.jsonl", dataset, "application/jsonl")},
    )
    evaluation.raise_for_status()

    deletion = await client.delete(
        f"/api/v1/documents/{upload_task['document_id']}"
    )
    deletion.raise_for_status()
    delete_task = await _wait_for_task(client, deletion.json()["task_id"])

    remaining = await client.post(
        "/api/v1/retrieval/search",
        json={"query": "退货政策", "mode": "hybrid", "top_k": 5},
    )
    remaining.raise_for_status()

    return {
        "upload_status": upload_task["status"],
        "retrieval_count": len(results),
        "chat_tier": chat.json()["provider_tier"],
        "session_id": chat.json()["session_id"],
        "sse_events": _sse_events(stream.text),
        "evaluation_queries": evaluation.json()["query_count"],
        "delete_status": delete_task["status"],
        "remaining_results": len(remaining.json()["results"]),
    }


async def _main(base_url: str, document_path: Path) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        summary = await run_smoke(
            client, document_path.read_bytes(), source_name=document_path.name
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def entrypoint() -> None:
    parser = argparse.ArgumentParser(description="Exercise the complete public RAG API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--document", type=Path, default=Path("tests/fixtures/knowledge.md")
    )
    args = parser.parse_args()
    asyncio.run(_main(args.base_url, args.document))


if __name__ == "__main__":
    entrypoint()
