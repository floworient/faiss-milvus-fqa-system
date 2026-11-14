import json
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
import threading

import httpx
import numpy as np
import pytest

from app.agents.contextual_rag import ContextualRAGStrategy
from app.agents.registry import AgentRegistry
from app.core.config import Settings
from app.domain.documents import Chunk
from app.llm.ports import LLMUnavailable
from app.llm.router import TieredLLMRouter
from app.main import ServiceContainer, create_app
from app.memory.models import Citation
from app.memory.store import FileConversationStore
from app.prompts.registry import PromptRegistry
from app.retrieval.embeddings import EmbeddingUnavailable
from app.retrieval.repository import IndexRepository
from app.retrieval.service import RetrievalService


class FakeEmbedding:
    def __init__(self, fail_query: bool = False) -> None:
        self.fail_query = fail_query

    def embed_query(self, text: str) -> np.ndarray:
        if self.fail_query:
            raise EmbeddingUnavailable("offline")
        return np.array([1.0, 0.0], dtype=np.float32)

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)


class FakeLLM:
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.stream_items: list[str | Exception] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        self.prompts.append(prompt)
        for item in self.stream_items:
            if isinstance(item, Exception):
                raise item
            yield item


def build_chat_app(
    tmp_path: Path,
    primary: FakeLLM,
    backup: FakeLLM | None = None,
    *,
    fail_embedding: bool = False,
):
    settings = Settings(data_dir=tmp_path / "runtime")
    repository = IndexRepository(settings.indexes_dir, lambda: "v1")
    repository.publish(
        [
            Chunk(
                "chk_return",
                "doc_return",
                "商品签收后七天内可以申请退货。",
                0,
                16,
                {"source_name": "return-policy.md", "chunker_version": "chunker-v1"},
            )
        ],
        np.array([[1.0, 0.0]], dtype=np.float32),
    )
    retrieval = RetrievalService(repository, FakeEmbedding(fail_embedding))
    memory = FileConversationStore(settings.sessions_dir)
    strategy = ContextualRAGStrategy(
        retrieval,
        PromptRegistry.default(),
        memory,
        TieredLLMRouter(primary, backup),
    )
    registry = AgentRegistry([strategy])
    app = create_app(
        settings,
        ServiceContainer(
            retrieval=retrieval,
            memory=memory,
            agent_registry=registry,
        ),
    )
    return app, memory


async def api_request(app: object, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_non_stream_chat_creates_session_and_returns_citations_and_tier(
    tmp_path: Path,
) -> None:
    primary = FakeLLM(["请在签收后七天内提交退货申请。"])
    app, memory = build_chat_app(tmp_path, primary)

    response = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions",
        json={"question": "如何退货？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"].startswith("session_")
    assert body["answer"] == "请在签收后七天内提交退货申请。"
    assert body["provider_tier"] == 1
    assert body["citations"] == [
        {
            "chunk_id": "chk_return",
            "document_id": "doc_return",
            "source_name": "return-policy.md",
            "excerpt": "商品签收后七天内可以申请退货。",
            "deleted": False,
        }
    ]
    assert len(memory.get(body["session_id"]).messages) == 2


@pytest.mark.asyncio
async def test_existing_session_history_is_included_in_next_prompt(tmp_path: Path) -> None:
    primary = FakeLLM(["第一轮回答", "第二轮回答"])
    app, _ = build_chat_app(tmp_path, primary)
    first = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions",
        json={"question": "第一轮问题"},
    )

    second = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions",
        json={"question": "第二轮问题", "session_id": first.json()["session_id"]},
    )

    assert second.status_code == 200
    assert "第一轮问题" in primary.prompts[1]
    assert "第一轮回答" in primary.prompts[1]
    assert "第二轮问题" in primary.prompts[1]


@pytest.mark.asyncio
async def test_hybrid_chat_reports_keyword_fallback_when_embedding_fails(
    tmp_path: Path,
) -> None:
    app, _ = build_chat_app(
        tmp_path, FakeLLM(["关键词检索回答"]), fail_embedding=True
    )

    response = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions",
        json={"question": "退货", "retrieval_mode": "hybrid"},
    )

    assert response.status_code == 200
    assert response.json()["retrieval"] == {
        "mode": "hybrid",
        "degraded_from": "hybrid",
        "degradation_reason": "embedding_unavailable",
    }


@pytest.mark.asyncio
async def test_chat_returns_tier_three_retrieval_summary_when_models_fail(
    tmp_path: Path,
) -> None:
    app, _ = build_chat_app(
        tmp_path,
        FakeLLM([LLMUnavailable("primary")]),
        FakeLLM([LLMUnavailable("backup")]),
    )

    response = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions",
        json={"question": "退货"},
    )

    assert response.status_code == 200
    assert response.json()["provider_tier"] == 3
    assert response.json()["answer"].startswith("模型暂时不可用")


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["missing", "plan_and_execute"])
async def test_unregistered_agent_strategy_is_rejected(
    tmp_path: Path, strategy: str
) -> None:
    app, _ = build_chat_app(tmp_path, FakeLLM(["unused"]))

    response = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions",
        json={"question": "退货", "strategy": strategy},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "agent_strategy_not_found"


def parse_sse(response: httpx.Response) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in response.text.strip().split("\n\n"):
        lines = block.splitlines()
        event_type = next(line[7:] for line in lines if line.startswith("event: "))
        data = json.loads(next(line[6:] for line in lines if line.startswith("data: ")))
        events.append((event_type, data))
    return events


@pytest.mark.asyncio
async def test_sse_emits_meta_retrieval_tokens_and_done_as_json(tmp_path: Path) -> None:
    primary = FakeLLM(["unused"])
    primary.stream_items = ["七天内", "可以退货"]
    app, memory = build_chat_app(tmp_path, primary)

    response = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions/stream",
        json={"question": "如何退货？"},
    )
    events = parse_sse(response)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert [event_type for event_type, _ in events] == [
        "meta",
        "retrieval",
        "token",
        "token",
        "done",
    ]
    session_id = events[0][1]["session_id"]
    assert session_id.startswith("session_")
    assert events[1][1]["citations"][0]["chunk_id"] == "chk_return"
    assert events[2][1] == {"text": "七天内", "tier": 1}
    assert events[-1][1]["status"] == "complete"
    assert memory.get(session_id).messages[-1].content == "七天内可以退货"


@pytest.mark.asyncio
async def test_sse_pretoken_failure_emits_fallback_before_backup_tokens(
    tmp_path: Path,
) -> None:
    primary = FakeLLM(["unused"])
    primary.stream_items = [LLMUnavailable("offline")]
    backup = FakeLLM(["unused"])
    backup.stream_items = ["备用回答"]
    app, _ = build_chat_app(tmp_path, primary, backup)

    response = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions/stream",
        json={"question": "退货"},
    )
    events = parse_sse(response)

    assert [event_type for event_type, _ in events] == [
        "meta",
        "retrieval",
        "fallback",
        "token",
        "done",
    ]
    assert events[2][1]["to_tier"] == 2
    assert events[3][1]["text"] == "备用回答"


@pytest.mark.asyncio
async def test_sse_posttoken_failure_is_audited_but_excluded_from_next_prompt(
    tmp_path: Path,
) -> None:
    primary = FakeLLM(["下一轮完整回答"])
    primary.stream_items = ["残缺内容", LLMUnavailable("offline")]
    backup = FakeLLM(["unused"])
    backup.stream_items = ["不应拼接"]
    app, memory = build_chat_app(tmp_path, primary, backup)

    failed = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions/stream",
        json={"question": "第一轮"},
    )
    failed_events = parse_sse(failed)
    session_id = failed_events[0][1]["session_id"]
    next_response = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions",
        json={"question": "第二轮", "session_id": session_id},
    )

    assert [event_type for event_type, _ in failed_events] == [
        "meta",
        "retrieval",
        "token",
        "error",
        "done",
    ]
    assert failed_events[-1][1]["status"] == "failed"
    assert memory.get(session_id).messages[1].status == "failed"
    assert memory.get(session_id).messages[1].content == "残缺内容"
    assert next_response.status_code == 200
    assert "残缺内容" not in primary.prompts[-1]
    assert backup.stream_items == ["不应拼接"]


@pytest.mark.asyncio
async def test_session_api_returns_safe_message_history(tmp_path: Path) -> None:
    app, _ = build_chat_app(tmp_path, FakeLLM(["七天内申请"]))
    chat = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions",
        json={"question": "如何退货"},
    )

    response = await api_request(
        app, "GET", f"/api/v1/sessions/{chat.json()['session_id']}"
    )

    assert response.status_code == 200
    assert [item["role"] for item in response.json()["messages"]] == [
        "user",
        "assistant",
    ]
    assert response.json()["messages"][1]["citations"][0]["source_name"] == (
        "return-policy.md"
    )


@pytest.mark.asyncio
async def test_session_api_redacts_deleted_source_excerpt(tmp_path: Path) -> None:
    app, memory = build_chat_app(tmp_path, FakeLLM(["unused"]))
    session_id = memory.create().session_id
    memory.append_assistant(
        session_id,
        "历史回答",
        citations=[Citation("chk_old", "doc_old", "deleted.md", "secret", True)],
    )

    response = await api_request(app, "GET", f"/api/v1/sessions/{session_id}")

    citation = response.json()["messages"][0]["citations"][0]
    assert citation["deleted"] is True
    assert citation["excerpt"] is None
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_delete_session_removes_it_and_unknown_session_returns_404(
    tmp_path: Path,
) -> None:
    app, memory = build_chat_app(tmp_path, FakeLLM(["unused"]))
    session_id = memory.create().session_id

    deleted = await api_request(app, "DELETE", f"/api/v1/sessions/{session_id}")
    missing = await api_request(app, "GET", f"/api/v1/sessions/{session_id}")

    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert missing.json()["code"] == "session_not_found"


@pytest.mark.asyncio
async def test_default_app_wires_services_and_degrades_without_api_key(
    tmp_path: Path,
) -> None:
    app = create_app(
        Settings(data_dir=tmp_path / "runtime", dashscope_api_key=None)
    )

    response = await api_request(
        app,
        "POST",
        "/api/v1/chat/completions",
        json={"question": "当前知识库有什么内容？"},
    )

    assert response.status_code == 200
    assert response.json()["provider_tier"] == 3
    assert response.json()["citations"] == []
    assert response.json()["answer"] == "模型暂时不可用，且未检索到可引用的相关资料。"


@pytest.mark.asyncio
async def test_non_stream_chat_does_not_block_event_loop(tmp_path: Path) -> None:
    release = threading.Event()
    ticks = 0

    class BlockingLLM(FakeLLM):
        def complete(self, prompt: str) -> str:
            self.prompts.append(prompt)
            release.wait(timeout=1)
            return "answer"

    app, _ = build_chat_app(tmp_path, BlockingLLM([]))

    async def heartbeat() -> None:
        nonlocal ticks
        deadline = asyncio.get_running_loop().time() + 0.05
        while asyncio.get_running_loop().time() < deadline:
            ticks += 1
            await asyncio.sleep(0.005)
        release.set()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        request_task = asyncio.create_task(
            client.post("/api/v1/chat/completions", json={"question": "退货"})
        )
        await heartbeat()
        response = await asyncio.wait_for(request_task, timeout=1)

    assert response.status_code == 200
    assert ticks >= 2
