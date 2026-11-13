import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import numpy as np
import pytest

from app.agents.contextual_rag import ContextualRAGStrategy
from app.agents.registry import AgentRegistry
from app.core.config import Settings
from app.core.logging import configure_logging
from app.evaluation.runner import EvaluationRunner
from app.ingestion.chunker import AdaptiveChunker, RegexTokenizer
from app.ingestion.parsers import ParserRegistry
from app.ingestion.service import IngestionService, TaskStore
from app.llm.ports import LLMUnavailable
from app.llm.router import TieredLLMRouter
from app.main import ServiceContainer, create_app
from app.memory.store import FileConversationStore
from app.prompts.registry import PromptRegistry
from app.retrieval.repository import IndexRepository
from app.retrieval.service import RetrievalService
from scripts.smoke_test import run_smoke


class FakeEmbedding:
    def embed_texts(self, texts: list[str]) -> np.ndarray:
        return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return np.array([1.0, 0.0], dtype=np.float32)


class FakeLLM:
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = responses

    def complete(self, prompt: str) -> str:
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        yield "流式"
        yield "回答"


def build_app(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "runtime", dashscope_api_key="fake-secret-key"
    )
    versions = iter(f"v{index}" for index in range(1, 20))
    repository = IndexRepository(settings.indexes_dir, lambda: next(versions))
    embedding = FakeEmbedding()
    retrieval = RetrievalService(repository, embedding)
    memory = FileConversationStore(settings.sessions_dir)
    primary = FakeLLM(["非流式回答", LLMUnavailable("primary down")])
    backup = FakeLLM(["备用回答"])
    strategy = ContextualRAGStrategy(
        retrieval,
        PromptRegistry.default(),
        memory,
        TieredLLMRouter(primary, backup),
    )
    ingestion = IngestionService(
        settings,
        ParserRegistry(),
        AdaptiveChunker(settings, RegexTokenizer()),
        embedding,
        repository,
        TaskStore(settings.tasks_dir),
    )
    services = ServiceContainer(
        ingestion=ingestion,
        retrieval=retrieval,
        memory=memory,
        agent_registry=AgentRegistry([strategy]),
        evaluation=EvaluationRunner(retrieval),
    )
    return create_app(settings, services)


@pytest.mark.asyncio
async def test_complete_backend_workflow_and_safe_structured_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    configure_logging("INFO")
    caplog.set_level(logging.INFO)
    app = build_app(tmp_path)
    document = Path("tests/fixtures/knowledge.md").read_bytes()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        summary = await run_smoke(client, document, source_name="knowledge.md")
        fallback = await client.post(
            "/api/v1/chat/completions", json={"question": "再次回答"}
        )

    assert summary["upload_status"] == "succeeded"
    assert summary["retrieval_count"] >= 1
    assert summary["chat_tier"] == 1
    assert summary["sse_events"] == [
        "meta",
        "retrieval",
        "token",
        "token",
        "done",
    ]
    assert summary["evaluation_queries"] == 1
    assert summary["delete_status"] == "succeeded"
    assert summary["remaining_results"] == 0
    assert fallback.status_code == 200
    assert fallback.json()["provider_tier"] == 2

    records = []
    for record in caplog.records:
        try:
            records.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            continue
    assert any(item.get("request_id", "").startswith("req_") for item in records)
    assert any(item.get("task_id", "").startswith("task_") for item in records)
    assert any(item.get("session_id", "").startswith("session_") for item in records)
    assert any(item.get("event") == "llm.fallback" for item in records)
    serialized = json.dumps(records, ensure_ascii=False)
    assert "fake-secret-key" not in serialized
    assert "PRIVATE_FULL_TEXT_MARKER" not in serialized
    assert "仅依据上下文" not in serialized
