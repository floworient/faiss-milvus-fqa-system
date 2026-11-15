from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from app.llm.openai_compatible import OpenAICompatibleLLMAdapter
from app.llm.ports import (
    LLMInvalidRequest,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)


def install_sync_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    client_type = httpx.Client
    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs: object) -> httpx.Client:
        return client_type(transport=transport, **kwargs)

    monkeypatch.setattr("app.llm.openai_compatible.httpx.Client", client_factory)


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk


def install_async_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    client_type = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        return client_type(transport=transport, **kwargs)

    monkeypatch.setattr("app.llm.openai_compatible.httpx.AsyncClient", client_factory)


def test_complete_calls_openai_compatible_chat_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://gateway.example.com/compatible-mode/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer key"
        assert request.read()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "answer"}}]},
        )

    install_sync_transport(monkeypatch, handler)
    adapter = OpenAICompatibleLLMAdapter(
        "key", "qwen3.8-flash", "https://gateway.example.com/compatible-mode/v1"
    )

    assert adapter.complete("prompt") == "answer"


@pytest.mark.asyncio
async def test_stream_parses_fragmented_sse_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [
        b'data: {"choices":[{"delta":{"cont',
        b'ent":"hello"}}]}\n\ndata: {"choices":[{"delta":{"content":" world"}}]}\n',
        b'\ndata: [DONE]\n\n',
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/compatible-mode/v1/chat/completions")
        return httpx.Response(200, stream=ChunkStream(chunks))

    install_async_transport(monkeypatch, handler)
    adapter = OpenAICompatibleLLMAdapter(
        "key", "qwen3.8-flash", "https://gateway.example.com/compatible-mode/v1"
    )

    assert [token async for token in adapter.stream("prompt")] == ["hello", " world"]


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (400, LLMInvalidRequest),
        (422, LLMInvalidRequest),
        (429, LLMRateLimited),
        (500, LLMUnavailable),
    ],
)
def test_complete_maps_http_errors(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    error_type: type[Exception],
) -> None:
    install_sync_transport(
        monkeypatch,
        lambda request: httpx.Response(status_code, json={"error": {"code": "upstream"}}),
    )
    adapter = OpenAICompatibleLLMAdapter(
        "key", "model", "https://gateway.example.com/compatible-mode/v1"
    )

    with pytest.raises(error_type):
        adapter.complete("prompt")


def test_complete_maps_http_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    install_sync_transport(monkeypatch, handler)
    adapter = OpenAICompatibleLLMAdapter(
        "key", "model", "https://gateway.example.com/compatible-mode/v1"
    )

    with pytest.raises(LLMTimeout):
        adapter.complete("prompt")


def test_complete_rejects_malformed_success(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sync_transport(monkeypatch, lambda request: httpx.Response(200, json={}))
    adapter = OpenAICompatibleLLMAdapter(
        "key", "model", "https://gateway.example.com/compatible-mode/v1"
    )

    with pytest.raises(LLMUnavailable):
        adapter.complete("prompt")
