"""模块导读：本文件位于 app/api/routers/evaluations.py，属于API 路由层。

主要职责：把 HTTP 请求转换成服务层调用，并把结果整理成前端可以直接使用的响应。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

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
    """overview 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    return success(EvaluationService(db).overview())


@router.get("/runs")
def list_runs(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """list_runs 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    service = EvaluationService(db)
    rows, total = service.list_runs(pageNo, pageSize)
    return success(page([service.run_to_dict(row) for row in rows], total, pageNo, pageSize))


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """get_run 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
    service = EvaluationService(db)
    row = db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="评估记录不存在")
    return success(service.run_to_dict(row, include_details=True))


@router.post("/runs/{trace_id}/evaluate")
def evaluate_trace(trace_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """evaluate_trace 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
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
    """list_issues 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    service = EvaluationService(db)
    rows, total = service.list_issues(pageNo, pageSize, severity)
    return success(page([service.issue_to_dict(row) for row in rows], total, pageNo, pageSize))
