"""智能求职 Agent 投递看板与求职全流程管理服务：负责看板流水线流转、面试跟进与数据统计。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.core.time_utils import utc_now_naive
from app.domain.models import JobApplication, JobOpportunity, ResumeProfile

logger = logging.getLogger(__name__)

VALID_STAGES = [
    "wishlist",      # 心仪意向
    "applied",       # 已投递/网申
    "screening",     # 简历初筛
    "assessment",    # 笔试测评
    "interview_1",   # 技术一面
    "interview_2",   # 技术二面/总监面
    "hr_interview",  # HR 终面
    "offer",         # 录用 Offer
    "rejected",      # 未通过/挂
    "withdrawn"      # 已放弃/关闭
]


class JobApplicationService:
    def __init__(self, db: Session):
        self.db = db

    def get_applications(
        self,
        user_id: str,
        stage: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = self.db.query(JobApplication).filter(JobApplication.user_id == user_id)
        if stage and stage != "all":
            query = query.filter(JobApplication.stage == stage)

        apps = query.order_by(desc(JobApplication.updated_at)).all()
        results = []
        for a in apps:
            job = self.db.query(JobOpportunity).filter(JobOpportunity.id == a.job_id).first()
            resume = self.db.query(ResumeProfile).filter(ResumeProfile.id == a.resume_id).first() if a.resume_id else None
            results.append({
                "id": a.id,
                "user_id": a.user_id,
                "resume_id": a.resume_id,
                "resume_name": resume.name if resume else "默认简历",
                "job_id": a.job_id,
                "job_title": job.title if job else "未知岗位",
                "company": job.company if job else "未知企业",
                "city": job.city if job else "全国",
                "salary_min": job.salary_min if job else 0,
                "salary_max": job.salary_max if job else 0,
                "stage": a.stage,
                "apply_channel": a.apply_channel,
                "apply_date": a.apply_date.isoformat() if a.apply_date else None,
                "hr_contact": a.hr_contact,
                "next_action_date": a.next_action_date.isoformat() if a.next_action_date else None,
                "notes": a.notes,
                "interview_records": a.interview_records,
                "offer_details": a.offer_details,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None
            })
        return results

    def create_application(
        self,
        user_id: str,
        job_id: str,
        resume_id: Optional[str] = None,
        stage: str = "wishlist",
        apply_channel: str = "牛客网申",
        notes: str = ""
    ) -> JobApplication:
        existing = self.db.query(JobApplication).filter(
            JobApplication.user_id == user_id,
            JobApplication.job_id == job_id
        ).first()

        if existing:
            existing.stage = stage
            existing.notes = notes or existing.notes
            if resume_id:
                existing.resume_id = resume_id
            self.db.commit()
            self.db.refresh(existing)
            return existing

        app = JobApplication(
            user_id=user_id,
            job_id=job_id,
            resume_id=resume_id,
            stage=stage if stage in VALID_STAGES else "wishlist",
            apply_channel=apply_channel,
            apply_date=utc_now_naive() if stage != "wishlist" else None,
            notes=notes
        )
        self.db.add(app)
        self.db.commit()
        self.db.refresh(app)
        return app

    def update_application_stage(
        self,
        application_id: str,
        user_id: str,
        stage: str,
        notes: Optional[str] = None,
        next_action_date: Optional[datetime] = None
    ) -> Optional[JobApplication]:
        app = self.db.query(JobApplication).filter(
            JobApplication.id == application_id,
            JobApplication.user_id == user_id
        ).first()
        if not app:
            return None

        if stage in VALID_STAGES:
            app.stage = stage
            if stage == "applied" and not app.apply_date:
                app.apply_date = utc_now_naive()

        if notes is not None:
            app.notes = notes
        if next_action_date is not None:
            app.next_action_date = next_action_date

        self.db.commit()
        self.db.refresh(app)
        return app

    def add_interview_record(
        self,
        application_id: str,
        user_id: str,
        round_title: str,
        interview_time: str,
        interviewer: str = "",
        questions_and_feedback: str = "",
        result: str = "pending"
    ) -> Optional[JobApplication]:
        app = self.db.query(JobApplication).filter(
            JobApplication.id == application_id,
            JobApplication.user_id == user_id
        ).first()
        if not app:
            return None

        records = list(app.interview_records or [])
        records.append({
            "round_title": round_title,
            "interview_time": interview_time,
            "interviewer": interviewer,
            "questions_and_feedback": questions_and_feedback,
            "result": result,
            "recorded_at": utc_now_naive().isoformat()
        })
        app.interview_records = records
        self.db.commit()
        self.db.refresh(app)
        return app

    def update_offer_details(
        self,
        application_id: str,
        user_id: str,
        offer_details: Dict[str, Any]
    ) -> Optional[JobApplication]:
        app = self.db.query(JobApplication).filter(
            JobApplication.id == application_id,
            JobApplication.user_id == user_id
        ).first()
        if not app:
            return None

        app.offer_details = offer_details
        app.stage = "offer"
        self.db.commit()
        self.db.refresh(app)
        return app

    def delete_application(self, application_id: str, user_id: str) -> bool:
        app = self.db.query(JobApplication).filter(
            JobApplication.id == application_id,
            JobApplication.user_id == user_id
        ).first()
        if not app:
            return False
        self.db.delete(app)
        self.db.commit()
        return True

    def get_dashboard_statistics(self, user_id: str) -> Dict[str, Any]:
        """获取求职全局漏斗数据、各阶段分布与统计指标。"""
        apps = self.db.query(JobApplication).filter(JobApplication.user_id == user_id).all()
        stage_counts = {s: 0 for s in VALID_STAGES}
        for a in apps:
            if a.stage in stage_counts:
                stage_counts[a.stage] += 1

        total = len(apps)
        applied_count = sum(stage_counts[s] for s in VALID_STAGES if s not in ["wishlist"])
        interview_count = stage_counts["interview_1"] + stage_counts["interview_2"] + stage_counts["hr_interview"] + stage_counts["offer"]
        offer_count = stage_counts["offer"]

        funnel = [
            {"stage": "心仪意向", "count": stage_counts["wishlist"], "key": "wishlist"},
            {"stage": "已投递/网申", "count": applied_count, "key": "applied"},
            {"stage": "笔试/初筛", "count": stage_counts["screening"] + stage_counts["assessment"], "key": "screening"},
            {"stage": "进入面试", "count": interview_count, "key": "interview"},
            {"stage": "斩获Offer", "count": offer_count, "key": "offer"},
        ]

        interview_rate = round((interview_count / applied_count * 100), 1) if applied_count > 0 else 0.0
        offer_rate = round((offer_count / applied_count * 100), 1) if applied_count > 0 else 0.0

        return {
            "total_applications": total,
            "applied_count": applied_count,
            "interview_count": interview_count,
            "offer_count": offer_count,
            "interview_rate": interview_rate,
            "offer_rate": offer_rate,
            "stage_counts": stage_counts,
            "funnel": funnel
        }
