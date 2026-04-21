from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import TraceRun, User
from services.common import success
from services.dependencies import require_admin

router = APIRouter(tags=["trace"])


def _normalize_span_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = metadata or {}
    if set(metadata.keys()) == {"metadata"} and isinstance(metadata["metadata"], dict):
        return metadata["metadata"]
    return metadata


def _split_span_metadata(metadata: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = _normalize_span_metadata(metadata)
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

    if not input_data:
        input_data = metadata
    if not output_data:
        output_data = metadata

    return input_data, output_data


@router.get("/rag/traces/runs")
def list_runs(limit: int = 50, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(TraceRun).order_by(TraceRun.created_at.desc()).limit(limit).all()
    return success(
        [
            {
                "traceId": row.id,
                "sessionId": row.session_id,
                "taskId": row.task_id,
                "status": row.status,
                "totalDurationMs": row.total_duration_ms,
                "createdAt": row.created_at.isoformat(),
            }
            for row in rows
        ]
    )


@router.get("/rag/traces/runs/{trace_id}")
def get_run(trace_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = db.query(TraceRun).filter(TraceRun.id == trace_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Trace not found")
    return success(
        {
            "traceId": row.id,
            "sessionId": row.session_id,
            "taskId": row.task_id,
            "status": row.status,
            "totalDurationMs": row.total_duration_ms,
            "createdAt": row.created_at.isoformat(),
        }
    )


@router.get("/rag/traces/runs/{trace_id}/nodes")
def get_nodes(trace_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = db.query(TraceRun).filter(TraceRun.id == trace_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Trace not found")

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
                "metadata": metadata,
                "input": input_data,
                "output": output_data,
                "errorMessage": span.error_message,
                "createdAt": span.created_at.isoformat(),
            }
        )
    return success(nodes)
