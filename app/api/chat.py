import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agents.registry import AgentRegistry
from app.core.errors import AppError
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


def agent_registry(request: Request) -> AgentRegistry:
    registry = request.app.state.services.agent_registry
    if registry is None:
        raise AppError("agent_not_configured", "Agent service is not configured.", 503)
    return registry


@router.post("/completions", response_model=ChatCompletionResponse)
async def complete(
    payload: ChatCompletionRequest, request: Request
) -> ChatCompletionResponse:
    response = agent_registry(request).get(payload.strategy).run(payload.to_domain())
    return ChatCompletionResponse.from_domain(response)


@router.post("/completions/stream")
async def stream(payload: ChatCompletionRequest, request: Request) -> StreamingResponse:
    strategy = agent_registry(request).get(payload.strategy)

    async def event_source():
        async for event in strategy.stream(payload.to_domain()):
            data = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
            yield f"event: {event.type}\ndata: {data}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

