from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.common import page, success
from services.dependencies import require_admin
from services.ingestion_service import IngestionService

router = APIRouter(tags=["ingestion"])


class PipelinePayload(BaseModel):
    name: str
    description: str = ""
    nodes: list = []
    enabled: bool | None = None


class TaskPayload(BaseModel):
    name: str
    kb_id: str | None = None
    doc_id: str | None = None
    pipeline_id: str | None = None
    payload: dict = {}


@router.post("/ingestion/pipelines")
def create_pipeline(payload: PipelinePayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = IngestionService(db).create_pipeline(payload.name, payload.description, payload.nodes)
    return success({"id": row.id})


@router.put("/ingestion/pipelines/{pipeline_id}")
def update_pipeline(pipeline_id: str, payload: PipelinePayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = IngestionService(db).update_pipeline(pipeline_id, **payload.model_dump(exclude_none=True))
    if not row:
        raise HTTPException(status_code=404, detail="流水线不存在")
    return success({"id": row.id})


@router.get("/ingestion/pipelines/{pipeline_id}")
def get_pipeline(pipeline_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = IngestionService(db).get_pipeline(pipeline_id)
    if not row:
        raise HTTPException(status_code=404, detail="流水线不存在")
    return success({"id": row.id, "name": row.name, "description": row.description, "nodes": row.nodes, "enabled": row.enabled})


@router.get("/ingestion/pipelines")
def list_pipelines(pageNo: int = 1, pageSize: int = 10, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows, total = IngestionService(db).page_pipelines(pageNo, pageSize)
    items = [{"id": row.id, "name": row.name, "description": row.description, "enabled": row.enabled, "createdAt": row.created_at.isoformat()} for row in rows]
    return success(page(items, total, pageNo, pageSize))


@router.delete("/ingestion/pipelines/{pipeline_id}")
def delete_pipeline(pipeline_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not IngestionService(db).delete_pipeline(pipeline_id):
        raise HTTPException(status_code=404, detail="流水线不存在")
    return success()


@router.post("/ingestion/tasks")
def create_task(payload: TaskPayload, background_tasks: BackgroundTasks, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    service = IngestionService(db)
    row = service.create_task(payload.name, payload.kb_id, payload.doc_id, payload.pipeline_id, payload.payload)
    background_tasks.add_task(service.process_task, row.id)
    return success({"id": row.id, "status": row.status})


@router.get("/ingestion/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = IngestionService(db).get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    return success(
        {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "errorMessage": row.error_message,
            "startedAt": row.started_at.isoformat() if row.started_at else None,
            "finishedAt": row.finished_at.isoformat() if row.finished_at else None,
        }
    )


@router.get("/ingestion/tasks/{task_id}/nodes")
def get_task_nodes(task_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = IngestionService(db).get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    return success(
        [
            {
                "id": node.id,
                "nodeName": node.node_name,
                "status": node.status,
                "durationMs": node.duration_ms,
                "outputCount": node.output_count,
                "errorMessage": node.error_message,
            }
            for node in row.node_runs
        ]
    )


@router.get("/ingestion/tasks")
def list_tasks(pageNo: int = 1, pageSize: int = 10, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows, total = IngestionService(db).page_tasks(pageNo, pageSize)
    items = [{"id": row.id, "name": row.name, "status": row.status, "createdAt": row.created_at.isoformat(), "finishedAt": row.finished_at.isoformat() if row.finished_at else None} for row in rows]
    return success(page(items, total, pageNo, pageSize))
