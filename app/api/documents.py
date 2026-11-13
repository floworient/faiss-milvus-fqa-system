from fastapi import APIRouter, BackgroundTasks, File, Request, UploadFile, status

from app.core.errors import AppError
from app.ingestion.service import IngestionService
from app.schemas.documents import DocumentResponse, TaskResponse

router = APIRouter(prefix="/api/v1", tags=["documents"])


def ingestion_service(request: Request) -> IngestionService:
    service = request.app.state.services.ingestion
    if service is None:
        raise AppError("ingestion_not_configured", "Ingestion is not configured.", 503)
    return service


@router.post(
    "/documents", response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED
)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> TaskResponse:
    content = await file.read()
    task = ingestion_service(request).create_upload(file.filename or "document", content)
    background_tasks.add_task(ingestion_service(request).run, task.task_id)
    return TaskResponse.from_task(task)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, request: Request) -> TaskResponse:
    return TaskResponse.from_task(ingestion_service(request).task_store.get(task_id))


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(request: Request) -> list[DocumentResponse]:
    return [
        DocumentResponse.from_record(record)
        for record in ingestion_service(request).list_documents()
    ]


@router.delete(
    "/documents/{document_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_document(
    document_id: str, request: Request, background_tasks: BackgroundTasks
) -> TaskResponse:
    service = ingestion_service(request)
    task = service.create_delete(document_id)
    background_tasks.add_task(service.run, task.task_id)
    return TaskResponse.from_task(task)
