import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Request

from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.errors import app_error_handler
from app.api.evaluations import router as evaluations_router
from app.api.retrieval import router as retrieval_router
from app.api.sessions import router as sessions_router
from app.agents.contextual_rag import ContextualRAGStrategy
from app.agents.registry import AgentRegistry
from app.core.config import Settings
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.logging import configure_logging, log_event
from app.ingestion.chunker import AdaptiveChunker, RegexTokenizer
from app.ingestion.parsers import ParserRegistry
from app.ingestion.service import IngestionService, TaskStore
from app.evaluation.runner import EvaluationRunner
from app.llm.dashscope import DashScopeLLMAdapter
from app.llm.ports import UnavailableLLM
from app.llm.router import TieredLLMRouter
from app.memory.store import FileConversationStore
from app.prompts.registry import PromptRegistry
from app.retrieval.embeddings import DashScopeEmbeddingAdapter, UnavailableEmbedding
from app.retrieval.repository import IndexRepository
from app.retrieval.service import RetrievalService


@dataclass(slots=True)
class ServiceContainer:
    """Typed application service registry populated by later modules."""

    ingestion: Any | None = None
    retrieval: Any | None = None
    memory: Any | None = None
    agent_registry: Any | None = None
    evaluation: Any | None = None


def build_service_container(settings: Settings) -> ServiceContainer:
    if settings.dashscope_api_key:
        embedding = DashScopeEmbeddingAdapter(
            settings.dashscope_api_key,
            settings.embedding_model,
            settings.embedding_dimension,
            settings.dashscope_base_url,
        )
        primary_llm = DashScopeLLMAdapter(
            settings.dashscope_api_key,
            settings.primary_llm_model,
            settings.dashscope_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        backup_llm = DashScopeLLMAdapter(
            settings.dashscope_api_key,
            settings.backup_llm_model,
            settings.dashscope_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    else:
        embedding = UnavailableEmbedding()
        primary_llm = UnavailableLLM()
        backup_llm = None
    repository = IndexRepository(settings.indexes_dir)
    retrieval = RetrievalService(repository, embedding)
    memory = FileConversationStore(
        settings.sessions_dir, settings.data_dir / "deleted_sources.json"
    )
    ingestion = IngestionService(
        settings,
        ParserRegistry(),
        AdaptiveChunker(settings, RegexTokenizer()),
        embedding,
        repository,
        TaskStore(settings.tasks_dir),
        memory,
    )
    strategy = ContextualRAGStrategy(
        retrieval,
        PromptRegistry.default(),
        memory,
        TieredLLMRouter(primary_llm, backup_llm),
    )
    return ServiceContainer(
        ingestion=ingestion,
        retrieval=retrieval,
        memory=memory,
        agent_registry=AgentRegistry([strategy]),
        evaluation=EvaluationRunner(retrieval),
    )


def create_app(
    settings: Settings | None = None,
    services: ServiceContainer | None = None,
) -> FastAPI:
    configure_logging()
    resolved_settings = settings or Settings()
    resolved_settings.ensure_directories()

    app = FastAPI(
        title="RAG Knowledge QA API",
        version="0.1.0",
        description="Development-preview modular RAG backend.",
    )
    app.state.settings = resolved_settings
    app.state.services = services if services is not None else build_service_container(resolved_settings)
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(chat_router)
    app.include_router(documents_router)
    app.include_router(evaluations_router)
    app.include_router(retrieval_router)
    app.include_router(sessions_router)

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next: Any):
        request_id = request.headers.get("x-request-id") or new_id("req")
        request.state.request_id = request_id
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        finally:
            log_event(
                logging.getLogger("app.request"),
                "request.completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

