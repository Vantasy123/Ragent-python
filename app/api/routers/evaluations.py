"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import EvaluationRun, User
from app.services.common import page, success
from app.services.dependencies import require_admin
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/admin/evaluations", tags=["evaluations"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success(EvaluationService(db).overview())


@router.get("/runs")
def list_runs(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    service = EvaluationService(db)
    rows, total = service.list_runs(pageNo, pageSize)
    return success(page([service.run_to_dict(row) for row in rows], total, pageNo, pageSize))


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    service = EvaluationService(db)
    row = db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="评估记录不存在")
    return success(service.run_to_dict(row, include_details=True))


@router.post("/runs/{trace_id}/evaluate")
def evaluate_trace(trace_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        row = EvaluationService(db).evaluate_trace(trace_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success(EvaluationService(db).run_to_dict(row, include_details=True))


@router.get("/issues")
def list_issues(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    severity: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    service = EvaluationService(db)
    rows, total = service.list_issues(pageNo, pageSize, severity)
    return success(page([service.issue_to_dict(row) for row in rows], total, pageNo, pageSize))
