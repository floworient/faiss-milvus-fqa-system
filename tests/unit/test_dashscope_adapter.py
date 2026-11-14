import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from app.llm.dashscope import DashScopeLLMAdapter


@pytest.mark.asyncio
async def test_sync_dashscope_stream_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = threading.Event()
    ticks = 0

    def blocking_call(**kwargs):
        del kwargs
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

    adapter = DashScopeLLMAdapter("key", "model")
    started = time.perf_counter()
    stream_task = asyncio.create_task(anext(adapter.stream("prompt")))
    await heartbeat()
    token = await asyncio.wait_for(stream_task, timeout=1)

    assert token == "token"
    assert ticks >= 2
    assert time.perf_counter() - started < 0.5
