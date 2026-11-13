from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import AppError


async def app_error_handler(request: Request, error: AppError) -> JSONResponse:
    payload: dict[str, Any] = {
        "code": error.code,
        "message": error.message,
        "request_id": getattr(request.state, "request_id", None),
    }
    if error.details is not None:
        payload["details"] = error.details
    return JSONResponse(status_code=error.status_code, content=payload)

