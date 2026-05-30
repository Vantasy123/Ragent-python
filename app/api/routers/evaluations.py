"""模块导读：本文件位于 app/api/routers/evaluations.py，属于API 路由层。

主要职责：把 HTTP 请求转换成服务层调用，并把结果整理成前端可以直接使用的响应。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.domain.models import EvaluationRun, User
from app.services.common import page, success
from app.services.dependencies import require_admin
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/admin/evaluations", tags=["evaluations"])


class DatasetPayload(BaseModel):
    """评估数据集请求体。"""

    name: str
    description: str = ""
    kbId: str | None = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class CasePayload(BaseModel):
    """评估用例请求体。"""

    question: str
    expectedAnswer: str = ""
    expectedChunkIds: list[str] = Field(default_factory=list)
    expectedKeywords: list[str] = Field(default_factory=list)
    kbId: str | None = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseImportPayload(BaseModel):
    """评估用例批量导入请求体，支持 JSON items 或 CSV 文本。"""

    items: list[dict[str, Any]] = Field(default_factory=list)
    csvText: str = ""


async def process_evaluation_batch_background(batch_id: str, user_id: str | None) -> None:
    """后台执行评估批次，使用独立数据库会话避免复用请求会话。"""

    db = SessionLocal()
    try:
        await EvaluationService(db).process_batch_run(batch_id, user_id)
    finally:
        db.close()


@router.get("/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """overview 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    return success(EvaluationService(db).overview())


@router.get("/datasets")
def list_datasets(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """查询评估数据集列表。"""
    service = EvaluationService(db)
    rows, total = service.list_datasets(pageNo, pageSize)
    return success(page([service.dataset_to_dict(row) for row in rows], total, pageNo, pageSize))


@router.post("/datasets")
def create_dataset(payload: DatasetPayload, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """创建评估数据集。"""
    row = EvaluationService(db).create_dataset(payload.model_dump(), user.id)
    return success(EvaluationService(db).dataset_to_dict(row, include_cases=True))


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """读取评估数据集详情。"""
    service = EvaluationService(db)
    row = service.get_dataset(dataset_id)
    if not row:
        raise HTTPException(status_code=404, detail="评估数据集不存在")
    return success(service.dataset_to_dict(row, include_cases=True))


@router.put("/datasets/{dataset_id}")
def update_dataset(dataset_id: str, payload: DatasetPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """更新评估数据集。"""
    try:
        row = EvaluationService(db).update_dataset(dataset_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success(EvaluationService(db).dataset_to_dict(row, include_cases=True))


@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """删除评估数据集。"""
    deleted = EvaluationService(db).delete_dataset(dataset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="评估数据集不存在")
    return success({"deleted": True})


@router.get("/datasets/{dataset_id}/cases")
def list_cases(
    dataset_id: str,
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """查询评估用例列表。"""
    service = EvaluationService(db)
    rows, total = service.list_cases(dataset_id, pageNo, pageSize)
    return success(page([service.case_to_dict(row) for row in rows], total, pageNo, pageSize))


@router.post("/datasets/{dataset_id}/cases")
def create_case(dataset_id: str, payload: CasePayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """创建评估用例。"""
    try:
        row = EvaluationService(db).create_case(dataset_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success(EvaluationService(db).case_to_dict(row))


@router.post("/datasets/{dataset_id}/cases/import")
def import_cases(dataset_id: str, payload: CaseImportPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """批量导入评估用例，支持 JSON 数组或 CSV 文本。"""
    rows = list(payload.items)
    if payload.csvText.strip():
        rows.extend(csv.DictReader(io.StringIO(payload.csvText)))
    try:
        created = EvaluationService(db).import_cases(dataset_id, rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success({"created": len(created), "items": [EvaluationService.case_to_dict(row) for row in created]})


@router.put("/cases/{case_id}")
def update_case(case_id: str, payload: CasePayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """更新评估用例。"""
    try:
        row = EvaluationService(db).update_case(case_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success(EvaluationService(db).case_to_dict(row))


@router.delete("/cases/{case_id}")
def delete_case(case_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """删除评估用例。"""
    deleted = EvaluationService(db).delete_case(case_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="评估用例不存在")
    return success({"deleted": True})


@router.post("/datasets/{dataset_id}/runs")
def create_batch_run(
    dataset_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """创建并异步执行数据集批量评估。"""
    try:
        row = EvaluationService(db).create_batch_run(dataset_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(process_evaluation_batch_background, row.id, user.id)
    return success(EvaluationService(db).batch_to_dict(row))


@router.get("/batch-runs")
def list_batch_runs(
    datasetId: str | None = None,
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """查询批量评估运行列表。"""
    service = EvaluationService(db)
    rows, total = service.list_batch_runs(datasetId, pageNo, pageSize)
    return success(page([service.batch_to_dict(row) for row in rows], total, pageNo, pageSize))


@router.get("/batch-runs/{batch_id}")
def get_batch_run(batch_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """读取批量评估运行详情。"""
    service = EvaluationService(db)
    row = service.get_batch_run(batch_id)
    if not row:
        raise HTTPException(status_code=404, detail="评估批次不存在")
    return success(service.batch_to_dict(row, include_results=True))


@router.get("/batch-runs/{batch_id}/results")
def list_case_results(
    batch_id: str,
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """查询批次下的单条用例结果。"""
    service = EvaluationService(db)
    rows, total = service.list_case_results(batch_id, pageNo, pageSize)
    return success(page([service.case_result_to_dict(row) for row in rows], total, pageNo, pageSize))


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
