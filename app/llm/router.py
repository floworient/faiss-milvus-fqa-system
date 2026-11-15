import logging
from collections.abc import AsyncIterator, Sequence

from app.core.logging import log_event
from app.llm.ports import (
    GenerationResult,
    LLMError,
    LLMEvent,
    LLMInvalidRequest,
    LLMPort,
)
from app.memory.models import Citation


class TieredLLMRouter:
    def __init__(self, primary: LLMPort, backup: LLMPort | None = None) -> None:
        self.primary = primary
        self.backup = backup

    def complete(
        self, prompt: str, citations: Sequence[Citation]
    ) -> GenerationResult:
        safe_citations = list(citations)
        try:
            return GenerationResult(
                self.primary.complete(prompt), 1, safe_citations, {}
            )
        except LLMInvalidRequest:
            raise
        except LLMError as primary_error:
            if self.backup is not None:
                self._log_fallback(1, 2, primary_error.reason_code)
                try:
                    return GenerationResult(
                        self.backup.complete(prompt),
                        2,
                        safe_citations,
                        {"fallback_reason": primary_error.reason_code},
                    )
                except LLMInvalidRequest:
                    raise
                except LLMError as backup_error:
                    self._log_fallback(2, 3, backup_error.reason_code)
            else:
                self._log_fallback(1, 3, primary_error.reason_code)
            return GenerationResult(
                self._retrieval_summary(safe_citations),
                3,
                safe_citations,
                {"fallback_reason": "all_models_unavailable"},
            )

    async def stream(
        self, prompt: str, citations: Sequence[Citation]
    ) -> AsyncIterator[LLMEvent]:
        emitted = False
        try:
            async for token in self.primary.stream(prompt):
                emitted = True
                yield LLMEvent("token", {"text": token, "tier": 1})
        except LLMError as error:
            if emitted or isinstance(error, LLMInvalidRequest):
                yield LLMEvent("error", {"code": error.reason_code, "tier": 1})
                yield LLMEvent("done", {"status": "failed", "tier": 1})
                return
            next_tier = 2 if self.backup is not None else 3
            self._log_fallback(1, next_tier, error.reason_code)
            yield LLMEvent(
                "fallback",
                {"from_tier": 1, "to_tier": next_tier, "reason": error.reason_code},
            )
            if self.backup is not None:
                backup_emitted = False
                try:
                    async for token in self.backup.stream(prompt):
                        backup_emitted = True
                        yield LLMEvent("token", {"text": token, "tier": 2})
                except LLMError as backup_error:
                    if backup_emitted or isinstance(backup_error, LLMInvalidRequest):
                        yield LLMEvent(
                            "error", {"code": backup_error.reason_code, "tier": 2}
                        )
                        yield LLMEvent("done", {"status": "failed", "tier": 2})
                        return
                    yield LLMEvent(
                        "fallback",
                        {
                            "from_tier": 2,
                            "to_tier": 3,
                            "reason": backup_error.reason_code,
                        },
                    )
                    self._log_fallback(2, 3, backup_error.reason_code)
                    summary = self._retrieval_summary(citations)
                    yield LLMEvent("token", {"text": summary, "tier": 3})
                    yield LLMEvent("done", {"status": "complete", "tier": 3})
                    return
                yield LLMEvent("done", {"status": "complete", "tier": 2})
                return
            summary = self._retrieval_summary(citations)
            yield LLMEvent("token", {"text": summary, "tier": 3})
            yield LLMEvent("done", {"status": "complete", "tier": 3})
            return
        yield LLMEvent("done", {"status": "complete", "tier": 1})

    @staticmethod
    def _log_fallback(from_tier: int, to_tier: int, reason: str) -> None:
        log_event(
            logging.getLogger("app.llm"),
            "llm.fallback",
            from_tier=from_tier,
            to_tier=to_tier,
            reason=reason,
        )

    @staticmethod
    def _retrieval_summary(citations: Sequence[Citation]) -> str:
        if not citations:
            return "模型暂时不可用，且未检索到可引用的相关资料。"
        lines = ["模型暂时不可用。检索到的相关资料："]
        for index, citation in enumerate(citations, start=1):
            excerpt = citation.excerpt or "（来源内容已删除）"
            lines.append(f"[{index}] {citation.source_name}：{excerpt}")
        return "\n".join(lines)

