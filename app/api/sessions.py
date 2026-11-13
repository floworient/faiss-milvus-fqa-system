from fastapi import APIRouter, Request, Response, status

from app.core.errors import AppError
from app.memory.store import FileConversationStore
from app.schemas.chat import SessionResponse

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def conversation_store(request: Request) -> FileConversationStore:
    store = request.app.state.services.memory
    if store is None:
        raise AppError("memory_not_configured", "Conversation memory is not configured.", 503)
    return store


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, request: Request) -> SessionResponse:
    return SessionResponse.from_domain(conversation_store(request).get(session_id))


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, request: Request) -> Response:
    conversation_store(request).delete(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

