from fastapi import APIRouter, Request

from app.core.errors import AppError
from app.retrieval.service import RetrievalService
from app.schemas.retrieval import RetrievalSearchRequest, RetrievalSearchResponse

router = APIRouter(prefix="/api/v1/retrieval", tags=["retrieval"])


def retrieval_service(request: Request) -> RetrievalService:
    service = request.app.state.services.retrieval
    if service is None:
        raise AppError(
            "retrieval_not_configured", "Retrieval service is not configured.", 503
        )
    return service


@router.post("/search", response_model=RetrievalSearchResponse)
async def search(
    payload: RetrievalSearchRequest, request: Request
) -> RetrievalSearchResponse:
    result = retrieval_service(request).search(
        payload.query, payload.mode, payload.top_k, payload.candidate_k
    )
    return RetrievalSearchResponse.from_result(result)

