from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Protocol, Sequence

from app.domain.chat import (
    AgentEvent,
    AgentRequest,
    AgentResponse,
    RetrievalTrace,
)
from app.llm.router import TieredLLMRouter
from app.memory.models import Citation, Message
from app.memory.store import FileConversationStore
from app.prompts.registry import PromptRegistry
from app.retrieval.service import RetrievalService


class QueryRewriter(Protocol):
    def rewrite(self, question: str, history: Sequence[Message]) -> str: ...


class ContextualRAGStrategy:
    name = "contextual_rag"

    def __init__(
        self,
        retrieval: RetrievalService,
        prompts: PromptRegistry,
        memory: FileConversationStore,
        llm: TieredLLMRouter,
        rewriter: QueryRewriter | None = None,
        *,
        max_history_chars: int = 12_000,
        max_history_turns: int = 10,
    ) -> None:
        self.retrieval = retrieval
        self.prompts = prompts
        self.memory = memory
        self.llm = llm
        self.rewriter = rewriter
        self.max_history_chars = max_history_chars
        self.max_history_turns = max_history_turns

    def run(self, request: AgentRequest) -> AgentResponse:
        session_id, history = self._session_and_history(request.session_id)
        question = request.question.strip()
        retrieval_query = self._rewrite(question, history)
        result = self.retrieval.search(
            retrieval_query,
            request.retrieval_mode,
            request.top_k,
            request.candidate_k,
        )
        citations = self._citations(result.items)
        prompt = self.prompts.render(
            "contextual_rag",
            "v1",
            {
                "question": question,
                "history": self._format_history(history),
                "context": self._format_context(citations),
            },
        )
        self.memory.append_user(session_id, question)
        generated = self.llm.complete(prompt, citations)
        self.memory.append_assistant(
            session_id,
            generated.text,
            citations=citations,
            metadata={"provider_tier": generated.tier, **generated.metadata},
        )
        return AgentResponse(
            session_id=session_id,
            answer=generated.text,
            citations=citations,
            provider_tier=generated.tier,
            retrieval=RetrievalTrace(
                result.mode, result.degraded_from, result.degradation_reason
            ),
            metadata=generated.metadata,
        )

    async def stream(self, request: AgentRequest) -> AsyncIterator[AgentEvent]:
        session_id, history = self._session_and_history(request.session_id)
        question = request.question.strip()
        self.memory.append_user(session_id, question)
        yield AgentEvent(
            "meta",
            {
                "session_id": session_id,
                "strategy": self.name,
                "retrieval_mode": request.retrieval_mode,
            },
        )
        retrieval_query = self._rewrite(question, history)
        result = self.retrieval.search(
            retrieval_query,
            request.retrieval_mode,
            request.top_k,
            request.candidate_k,
        )
        citations = self._citations(result.items)
        yield AgentEvent(
            "retrieval",
            {
                "mode": result.mode,
                "degraded_from": result.degraded_from,
                "degradation_reason": result.degradation_reason,
                "citations": [asdict(item) for item in citations],
            },
        )
        prompt = self.prompts.render(
            "contextual_rag",
            "v1",
            {
                "question": question,
                "history": self._format_history(history),
                "context": self._format_context(citations),
            },
        )
        parts: list[str] = []
        final_status = "failed"
        final_tier = 1
        async for event in self.llm.stream(prompt, citations):
            if event.type == "token":
                parts.append(str(event.data.get("text", "")))
            if event.type == "done":
                final_status = str(event.data.get("status", "failed"))
                final_tier = int(event.data.get("tier", final_tier))
                self.memory.append_assistant(
                    session_id,
                    "".join(parts),
                    status="complete" if final_status == "complete" else "failed",
                    citations=citations,
                    metadata={"provider_tier": final_tier},
                )
            yield AgentEvent(event.type, dict(event.data))

    def _session_and_history(
        self, session_id: str | None
    ) -> tuple[str, list[Message]]:
        if session_id is None:
            conversation = self.memory.create()
            return conversation.session_id, []
        self.memory.get(session_id)
        return session_id, self.memory.history_for_prompt(
            session_id, self.max_history_chars, self.max_history_turns
        )

    def _rewrite(self, question: str, history: Sequence[Message]) -> str:
        if self.rewriter is None or not history:
            return question
        try:
            rewritten = self.rewriter.rewrite(question, history).strip()
            return rewritten or question
        except Exception:
            return question

    @staticmethod
    def _citations(items: Sequence[object]) -> list[Citation]:
        return [
            Citation(
                item.chunk.chunk_id,
                item.chunk.document_id,
                str(item.chunk.metadata.get("source_name", "unknown")),
                item.chunk.text,
            )
            for item in items
        ]

    @staticmethod
    def _format_history(history: Sequence[Message]) -> str:
        if not history:
            return "（无）"
        labels = {"user": "用户", "assistant": "助手"}
        return "\n".join(f"{labels[item.role]}：{item.content}" for item in history)

    @staticmethod
    def _format_context(citations: Sequence[Citation]) -> str:
        if not citations:
            return "（未检索到相关资料）"
        return "\n\n".join(
            f"[{index}] {item.source_name}\n{item.excerpt or ''}"
            for index, item in enumerate(citations, start=1)
        )

