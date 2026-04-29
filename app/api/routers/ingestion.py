"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.time_utils import to_shanghai_iso
from app.domain.models import User
from app.services.common import page, success
from app.services.dependencies import require_admin
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


class PipelinePayload(BaseModel):
    name: str
    description: str = ""
    nodes: list[dict] = Field(default_factory=list)
    enabled: bool | None = None


class TaskPayload(BaseModel):
    name: str = "手动摄取任务"
    kb_id: str | None = None
    doc_id: str | None = None
    pipeline_id: str | None = None
    payload: dict = Field(default_factory=dict)


def _iso(value):
    return to_shanghai_iso(value)


@router.get("/pipelines")
def list_pipelines(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows, total = IngestionService(db).page_pipelines(pageNo, pageSize)
    items = [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "nodes": row.nodes,
            "enabled": row.enabled,
            "createdAt": _iso(row.created_at),
            "updatedAt": _iso(row.updated_at),
        }
        for row in rows
    ]
    return success(page(items, total, pageNo, pageSize))


@router.get("/pipelines/{pipeline_id}")
def get_pipeline(pipeline_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = IngestionService(db).get_pipeline(pipeline_id)
    if not row:
        raise HTTPException(status_code=404, detail="流水线不存在")
    return success(
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "nodes": row.nodes,
            "enabled": row.enabled,
            "createdAt": _iso(row.created_at),
            "updatedAt": _iso(row.updated_at),
        }
    )


@router.post("/pipelines")
def create_pipeline(payload: PipelinePayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = IngestionService(db).create_pipeline(payload.name, payload.description, payload.nodes)
    return success({"id": row.id})


@router.put("/pipelines/{pipeline_id}")
def update_pipeline(pipeline_id: str, payload: PipelinePayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = IngestionService(db).update_pipeline(pipeline_id, **payload.model_dump(exclude_none=True))
    if not row:
        raise HTTPException(status_code=404, detail="流水线不存在")
    return success({"id": row.id})


@router.delete("/pipelines/{pipeline_id}")
def delete_pipeline(pipeline_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not IngestionService(db).delete_pipeline(pipeline_id):
        raise HTTPException(status_code=404, detail="流水线不存在")
    return success()


@router.get("/tasks")
def list_tasks(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows, total = IngestionService(db).page_tasks(pageNo, pageSize)
    items = [
        {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "kbId": row.kb_id,
            "docId": row.doc_id,
            "pipelineId": row.pipeline_id,
            "errorMessage": row.error_message,
            "payload": row.payload,
            "createdAt": _iso(row.created_at),
            "updatedAt": _iso(row.updated_at),
            "startedAt": _iso(row.started_at),
            "finishedAt": _iso(row.finished_at),
        }
        for row in rows
    ]
    return success(page(items, total, pageNo, pageSize))


@router.post("/tasks")
def create_task(payload: TaskPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = IngestionService(db).create_task(payload.name, payload.kb_id, payload.doc_id, payload.pipeline_id, payload.payload)
    return success({"id": row.id, "status": row.status})


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = IngestionService(db).get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    return success(
        {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "kbId": row.kb_id,
            "docId": row.doc_id,
            "pipelineId": row.pipeline_id,
            "errorMessage": row.error_message,
            "payload": row.payload,
            "createdAt": _iso(row.created_at),
            "updatedAt": _iso(row.updated_at),
            "startedAt": _iso(row.started_at),
            "finishedAt": _iso(row.finished_at),
        }
    )


@router.get("/tasks/{task_id}/nodes")
def get_task_nodes(task_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = IngestionService(db).get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    return success(
        [
            {
                "id": item.id,
                "nodeName": item.node_name,
                "status": item.status,
                "durationMs": item.duration_ms,
                "outputCount": item.output_count,
                "errorMessage": item.error_message,
                "createdAt": _iso(item.created_at),
            }
            for item in row.node_runs
        ]
    )
