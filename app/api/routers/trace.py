"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.time_utils import to_shanghai_iso
from app.domain.models import TraceRun, User
from app.services.common import page, success
from app.services.dependencies import require_admin
from app.services.evaluation_service import EvaluationService

router = APIRouter(tags=["trace"])


def _normalize_span_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = metadata or {}
    if set(metadata.keys()) == {"metadata"} and isinstance(metadata["metadata"], dict):
        return metadata["metadata"]
    return metadata


def _split_span_metadata(metadata: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = _normalize_span_metadata(metadata)

    # 新结构优先：Trace 写入时已经显式区分 input/output，详情页直接使用。
    if "input" in metadata or "output" in metadata:
        input_data = metadata.get("input") if isinstance(metadata.get("input"), dict) else {}
        output_data = metadata.get("output") if isinstance(metadata.get("output"), dict) else {}
        return input_data, output_data

    input_data: dict[str, Any] = {}
    output_data: dict[str, Any] = {}

    for key in ("query", "question", "original_query", "input", "request", "stage"):
        if key in metadata:
            input_data[key] = metadata[key]

    for key in (
        "rewritten",
        "rewritten_query",
        "chunks",
        "sources",
        "responseLength",
        "chunk_count",
        "channels",
        "intent",
        "elapsed_ms",
    ):
        if key in metadata:
            output_data[key] = metadata[key]

    # 兼容旧数据：旧 span 只有一份 metadata 时，仍按历史规则兜底。
    if not input_data:
        input_data = metadata
    if not output_data:
        output_data = metadata

    return input_data, output_data


@router.get("/rag/traces/runs")
def list_runs(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(TraceRun).order_by(TraceRun.created_at.desc())
    total = query.count()
    rows = query.offset((pageNo - 1) * pageSize).limit(pageSize).all()
    items = [
        {
            "traceId": row.id,
            "sessionId": row.session_id,
            "taskId": row.task_id,
            "status": row.status,
            "totalDurationMs": row.total_duration_ms,
            "createdAt": to_shanghai_iso(row.created_at),
        }
        for row in rows
    ]
    return success(page(items, total, pageNo, pageSize))


@router.get("/rag/traces/runs/{trace_id}")
def get_run(trace_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = db.query(TraceRun).filter(TraceRun.id == trace_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Trace 不存在")
    evaluation_service = EvaluationService(db)
    evaluation = evaluation_service.ensure_evaluated(trace_id)
    return success(
        {
            "traceId": row.id,
            "sessionId": row.session_id,
            "taskId": row.task_id,
            "status": row.status,
            "totalDurationMs": row.total_duration_ms,
            "createdAt": to_shanghai_iso(row.created_at),
            "evaluationSummary": evaluation_service.run_to_dict(evaluation) if evaluation else None,
            "metrics": [evaluation_service.metric_to_dict(metric) for metric in evaluation.metrics] if evaluation else [],
        }
    )


@router.get("/rag/traces/runs/{trace_id}/nodes")
def get_nodes(trace_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = db.query(TraceRun).filter(TraceRun.id == trace_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Trace 不存在")

    nodes = []
    for span in sorted(row.spans, key=lambda item: item.created_at):
        metadata = _normalize_span_metadata(span.metadata_json)
        input_data, output_data = _split_span_metadata(metadata)
        nodes.append(
            {
                "id": span.id,
                "name": span.operation,
                "operation": span.operation,
                "status": span.status,
                "durationMs": span.duration_ms,
                "metadata": metadata.get("context") if isinstance(metadata.get("context"), dict) else metadata,
                "input": input_data,
                "output": output_data,
                "errorMessage": span.error_message,
                "createdAt": to_shanghai_iso(span.created_at),
            }
        )
    return success(nodes)
