from collections.abc import AsyncIterator

import pytest

from app.llm.ports import (
    LLMInvalidRequest,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)
from app.llm.router import TieredLLMRouter
from app.memory.models import Citation


class FakeLLM:
    def __init__(self, complete_result: str | Exception) -> None:
        self.complete_result = complete_result
        self.complete_calls = 0
        self.stream_calls = 0
        self.stream_items: list[str | Exception] = []

    def complete(self, prompt: str) -> str:
        self.complete_calls += 1
        if isinstance(self.complete_result, Exception):
            raise self.complete_result
        return self.complete_result

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        self.stream_calls += 1
        for item in self.stream_items:
            if isinstance(item, Exception):
                raise item
            yield item


def citations() -> list[Citation]:
    return [Citation("chk_1", "doc_1", "guide.md", "七天内可以退货")]


def test_primary_success_uses_tier_one_without_backup() -> None:
    primary = FakeLLM("primary answer")
    backup = FakeLLM("backup answer")

    result = TieredLLMRouter(primary, backup).complete("prompt", citations())

    assert result.text == "primary answer"
    assert result.tier == 1
    assert result.citations == citations()
    assert backup.complete_calls == 0


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (LLMTimeout("timeout"), "timeout"),
        (LLMRateLimited("rate"), "rate_limited"),
        (LLMUnavailable("offline"), "unavailable"),
    ],
)
def test_retryable_primary_failure_switches_once_to_backup(
    error: Exception, reason: str
) -> None:
    primary = FakeLLM(error)
    backup = FakeLLM("backup answer")

    result = TieredLLMRouter(primary, backup).complete("secret prompt", citations())

    assert result.text == "backup answer"
    assert result.tier == 2
    assert result.metadata == {"fallback_reason": reason}
    assert primary.complete_calls == 1
    assert backup.complete_calls == 1
    assert "secret prompt" not in repr(result.metadata)


def test_invalid_request_does_not_retry_or_fallback() -> None:
    primary = FakeLLM(LLMInvalidRequest("bad request"))
    backup = FakeLLM("backup answer")

    with pytest.raises(LLMInvalidRequest):
        TieredLLMRouter(primary, backup).complete("prompt", citations())

    assert backup.complete_calls == 0


def test_backup_invalid_request_does_not_fall_back_to_summary() -> None:
    primary = FakeLLM(LLMUnavailable("primary down"))
    backup = FakeLLM(LLMInvalidRequest("bad backup request"))

    with pytest.raises(LLMInvalidRequest):
        TieredLLMRouter(primary, backup).complete("prompt", citations())


def test_both_models_failing_returns_deterministic_tier_three_summary() -> None:
    primary = FakeLLM(LLMUnavailable("primary down"))
    backup = FakeLLM(LLMTimeout("backup down"))

    result = TieredLLMRouter(primary, backup).complete(
        "prompt with API_KEY=super-secret", citations()
    )

    assert result.tier == 3
    assert result.text == "模型暂时不可用。检索到的相关资料：\n[1] guide.md：七天内可以退货"
    assert result.metadata == {"fallback_reason": "all_models_unavailable"}
    assert "super-secret" not in repr(result)


async def collect_stream(router: TieredLLMRouter):
    return [event async for event in router.stream("prompt", citations())]


@pytest.mark.asyncio
async def test_stream_failure_before_token_falls_back_to_backup() -> None:
    primary = FakeLLM("unused")
    primary.stream_items = [LLMTimeout("timeout")]
    backup = FakeLLM("unused")
    backup.stream_items = ["back", "up"]

    events = await collect_stream(TieredLLMRouter(primary, backup))

    assert [event.type for event in events] == ["fallback", "token", "token", "done"]
    assert events[0].data == {"from_tier": 1, "to_tier": 2, "reason": "timeout"}
    assert "".join(event.data["text"] for event in events if event.type == "token") == "backup"
    assert events[-1].data == {"status": "complete", "tier": 2}


@pytest.mark.asyncio
async def test_stream_failure_after_token_does_not_mix_backup_output() -> None:
    primary = FakeLLM("unused")
    primary.stream_items = ["partial", LLMUnavailable("offline")]
    backup = FakeLLM("unused")
    backup.stream_items = ["must-not-appear"]

    events = await collect_stream(TieredLLMRouter(primary, backup))

    assert [event.type for event in events] == ["token", "error", "done"]
    assert events[0].data["text"] == "partial"
    assert events[1].data["code"] == "unavailable"
    assert events[-1].data == {"status": "failed", "tier": 1}
    assert backup.stream_calls == 0


@pytest.mark.asyncio
async def test_stream_uses_tier_three_summary_when_both_models_fail() -> None:
    primary = FakeLLM("unused")
    primary.stream_items = [LLMUnavailable("offline")]
    backup = FakeLLM("unused")
    backup.stream_items = [LLMRateLimited("busy")]

    events = await collect_stream(TieredLLMRouter(primary, backup))

    assert [event.type for event in events] == [
        "fallback",
        "fallback",
        "token",
        "done",
    ]
    assert events[2].data["text"].startswith("模型暂时不可用")
    assert events[-1].data == {"status": "complete", "tier": 3}
