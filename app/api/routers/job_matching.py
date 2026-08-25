"""智能求职 Agent 人岗精准匹配与话术生成 API 路由。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.dependencies import get_current_user
from app.services.job_matching_service import JobMatchingService

router = APIRouter(prefix="/jobs/matching", tags=["Job Matching"])


class AnalyzeMatchRequest(BaseModel):
    resume_id: str
    job_id: str


class GenerateGreetingRequest(BaseModel):
    resume_id: str
    job_id: str


@router.post("/analyze")
def analyze_match(
    req: AnalyzeMatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobMatchingService(db)
    try:
        analysis = service.analyze_job_match(
            user_id=current_user.id,
            resume_id=req.resume_id,
            job_id=req.job_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "id": analysis.id,
        "resumeId": analysis.resume_id,
        "jobId": analysis.job_id,
        "overallScore": analysis.overall_score,
        "skillMatchScore": analysis.skill_match_score,
        "experienceMatchScore": analysis.experience_match_score,
        "educationMatchScore": analysis.education_match_score,
        "matchLevel": analysis.match_level,
        "matchedSkills": analysis.matched_skills,
        "missingSkills": analysis.missing_skills,
        "strongPoints": analysis.strong_points,
        "weakPoints": analysis.weak_points,
        "starProjectSuggestions": analysis.star_project_suggestions,
        "customizedGreeting": analysis.customized_greeting,
        "customizedCoverLetter": analysis.customized_cover_letter,
        "updatedAt": analysis.updated_at.isoformat() if analysis.updated_at else None
    }


@router.post("/greeting")
def generate_greeting(
    req: GenerateGreetingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobMatchingService(db)
    greeting = service.generate_greeting(
        user_id=current_user.id,
        resume_id=req.resume_id,
        job_id=req.job_id
    )
    return {"greeting": greeting}
