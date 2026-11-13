from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request

from app.api.errors import app_error_handler
from app.core.config import Settings
from app.core.errors import AppError
from app.core.ids import new_id


@dataclass(slots=True)
class ServiceContainer:
    """Typed application service registry populated by later modules."""

    ingestion: Any | None = None
    retrieval: Any | None = None
    memory: Any | None = None
    agent_registry: Any | None = None
    evaluation: Any | None = None


def create_app(
    settings: Settings | None = None,
    services: ServiceContainer | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    resolved_settings.ensure_directories()

    app = FastAPI(
        title="RAG Knowledge QA API",
        version="0.1.0",
        description="Development-preview modular RAG backend.",
    )
    app.state.settings = resolved_settings
    app.state.services = services or ServiceContainer()
    app.add_exception_handler(AppError, app_error_handler)

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next: Any):
        request_id = request.headers.get("x-request-id") or new_id("req")
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

