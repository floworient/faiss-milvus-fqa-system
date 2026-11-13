import io
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.core.errors import AppError
from app.evaluation.models import EvaluationDatasetError
from app.evaluation.runner import EvaluationRunner, load_jsonl
from app.schemas.evaluation import EvaluationReportResponse

router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])


def evaluation_runner(request: Request) -> EvaluationRunner:
    runner = request.app.state.services.evaluation
    if runner is None:
        raise AppError(
            "evaluation_not_configured", "Evaluation service is not configured.", 503
        )
    return runner


@router.post("/retrieval", response_model=EvaluationReportResponse)
async def evaluate_retrieval(
    request: Request,
    file: Annotated[UploadFile, File()],
    mode: Annotated[Literal["vector", "keyword", "hybrid"], Form()] = "hybrid",
    top_k: Annotated[int, Form(ge=1, le=50)] = 5,
    dataset_name: Annotated[str | None, Form()] = None,
) -> EvaluationReportResponse:
    del dataset_name
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EvaluationDatasetError(
            "Evaluation dataset must be valid UTF-8.", 1
        ) from error
    samples = load_jsonl(io.StringIO(text))
    report = evaluation_runner(request).run(samples, mode, top_k)
    return EvaluationReportResponse.from_domain(report)

