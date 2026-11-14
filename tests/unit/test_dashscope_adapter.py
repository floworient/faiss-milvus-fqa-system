import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from app.llm.dashscope import DashScopeLLMAdapter


def test_complete_passes_configured_base_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def successful_call(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))]
            ),
        )

    monkeypatch.setattr("app.llm.dashscope.dashscope.Generation.call", successful_call)

    adapter = DashScopeLLMAdapter(
        "key", "model", base_url="https://gateway.example.com/api/v1"
    )

    assert adapter.complete("prompt") == "answer"
    assert captured["base_address"] == "https://gateway.example.com/api/v1"


@pytest.mark.asyncio
async def test_sync_dashscope_stream_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = threading.Event()
    ticks = 0
    captured: dict[str, object] = {}

    def blocking_call(**kwargs):
        captured.update(kwargs)
        release.wait(timeout=1)
        response = SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="token"))]
            ),
        )
        return iter([response])

    monkeypatch.setattr("app.llm.dashscope.dashscope.Generation.call", blocking_call)

    async def heartbeat() -> None:
        nonlocal ticks
        deadline = asyncio.get_running_loop().time() + 0.05
        while asyncio.get_running_loop().time() < deadline:
            ticks += 1
            await asyncio.sleep(0.005)
        release.set()

    adapter = DashScopeLLMAdapter(
        "key", "model", base_url="https://gateway.example.com/api/v1"
    )
    started = time.perf_counter()
    stream = adapter.stream("prompt")
    stream_task = asyncio.create_task(anext(stream))
    await heartbeat()
    token = await asyncio.wait_for(stream_task, timeout=1)
    await stream.aclose()

    assert token == "token"
    assert captured["base_address"] == "https://gateway.example.com/api/v1"
    assert ticks >= 2
    assert time.perf_counter() - started < 0.5
