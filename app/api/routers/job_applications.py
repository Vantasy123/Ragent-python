"""智能求职 Agent 投递流程管理与求职看板 API 路由。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.dependencies import get_current_user
from app.services.job_application_service import JobApplicationService

router = APIRouter(prefix="/jobs/applications", tags=["Job Applications"])


class CreateApplicationRequest(BaseModel):
    job_id: str
    resume_id: Optional[str] = None
    stage: str = "wishlist"
    apply_channel: str = "牛客网申"
    notes: str = ""


class UpdateStageRequest(BaseModel):
    stage: str
    notes: Optional[str] = None
    next_action_date: Optional[datetime] = None


class AddInterviewRecordRequest(BaseModel):
    round_title: str
    interview_time: str
    interviewer: str = ""
    questions_and_feedback: str = ""
    result: str = "pending"


class UpdateOfferRequest(BaseModel):
    offer_details: Dict[str, Any]


@router.get("")
def list_applications(
    stage: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobApplicationService(db)
    items = service.get_applications(current_user.id, stage=stage)
    return {"items": items}


@router.post("")
def create_application(
    req: CreateApplicationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobApplicationService(db)
    app = service.create_application(
        user_id=current_user.id,
        job_id=req.job_id,
        resume_id=req.resume_id,
        stage=req.stage,
        apply_channel=req.apply_channel,
        notes=req.notes
    )
    return {"id": app.id, "stage": app.stage, "message": "已成功加入投递看板"}


@router.put("/{app_id}/stage")
def update_stage(
    app_id: str,
    req: UpdateStageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobApplicationService(db)
    app = service.update_application_stage(
        application_id=app_id,
        user_id=current_user.id,
        stage=req.stage,
        notes=req.notes,
        next_action_date=req.next_action_date
    )
    if not app:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    return {"id": app.id, "stage": app.stage, "message": "阶段状态已更新"}


@router.post("/{app_id}/interview")
def add_interview_record(
    app_id: str,
    req: AddInterviewRecordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobApplicationService(db)
    app = service.add_interview_record(
        application_id=app_id,
        user_id=current_user.id,
        round_title=req.round_title,
        interview_time=req.interview_time,
        interviewer=req.interviewer,
        questions_and_feedback=req.questions_and_feedback,
        result=req.result
    )
    if not app:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    return {"id": app.id, "interviewRecords": app.interview_records, "message": "面试记录添加成功"}


@router.put("/{app_id}/offer")
def update_offer(
    app_id: str,
    req: UpdateOfferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobApplicationService(db)
    app = service.update_offer_details(
        application_id=app_id,
        user_id=current_user.id,
        offer_details=req.offer_details
    )
    if not app:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    return {"id": app.id, "offerDetails": app.offer_details, "message": "Offer 详情已保存"}


@router.delete("/{app_id}")
def delete_application(
    app_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobApplicationService(db)
    ok = service.delete_application(app_id, user_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="记录不存在或无权删除")
    return {"success": True}


@router.get("/dashboard/stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobApplicationService(db)
    stats = service.get_dashboard_statistics(current_user.id)
    return stats
