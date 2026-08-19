"""智能求职 Agent 简历中枢 API 路由。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.dependencies import get_current_user
from app.services.job_resume_service import JobResumeService

router = APIRouter(prefix="/jobs/resumes", tags=["Job Resumes"])


class ParseResumeRequest(BaseModel):
    raw_text: str


class CreateResumeRequest(BaseModel):
    name: str = "我的求职简历"
    raw_text: str
    parsed_data: Optional[Dict[str, Any]] = None
    resume_id: Optional[str] = None
    is_default: bool = False


class StarPolishRequest(BaseModel):
    project_name: str
    tech_stack: List[str] = []
    background: str = ""
    target_jd: str = ""


class CreateVersionRequest(BaseModel):
    version_name: str
    target_job_title: str
    target_jd: str = ""
    custom_data: Optional[Dict[str, Any]] = None


@router.get("")
def list_resumes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobResumeService(db)
    resumes = service.get_resumes_by_user(current_user.id)
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "targetRole": r.target_role,
                "yearsOfExperience": r.years_of_experience,
                "educationLevel": r.education_level,
                "currentCity": r.current_city,
                "targetCity": r.target_city,
                "expectedSalary": r.expected_salary,
                "score": r.score,
                "scoreDetails": r.score_details,
                "isDefault": r.is_default,
                "versionsCount": len(r.versions),
                "updatedAt": r.updated_at.isoformat() if r.updated_at else None,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            }
            for r in resumes
        ]
    }


@router.get("/{resume_id}")
def get_resume_detail(
    resume_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobResumeService(db)
    resume = service.get_resume_by_id(resume_id, user_id=current_user.id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    return {
        "id": resume.id,
        "name": resume.name,
        "targetRole": resume.target_role,
        "yearsOfExperience": resume.years_of_experience,
        "educationLevel": resume.education_level,
        "currentCity": resume.current_city,
        "targetCity": resume.target_city,
        "expectedSalary": resume.expected_salary,
        "rawText": resume.raw_text,
        "parsedData": resume.parsed_data,
        "score": resume.score,
        "scoreDetails": resume.score_details,
        "isDefault": resume.is_default,
        "versions": [
            {
                "id": v.id,
                "versionName": v.version_name,
                "targetJobTitle": v.target_job_title,
                "customContent": v.custom_content,
                "starEnhancedProjects": v.star_enhanced_projects,
                "tailoredJd": v.tailored_jd,
                "score": v.score,
                "updatedAt": v.updated_at.isoformat() if v.updated_at else None
            }
            for v in resume.versions
        ]
    }


@router.post("/parse")
def parse_resume(
    req: ParseResumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobResumeService(db)
    parsed = service.parse_resume_text(req.raw_text)
    score, score_details = service.calculate_resume_score(parsed)
    return {
        "parsedData": parsed,
        "score": score,
        "scoreDetails": score_details
    }


@router.post("")
def create_or_save_resume(
    req: CreateResumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobResumeService(db)
    resume = service.create_or_update_resume(
        user_id=current_user.id,
        name=req.name,
        raw_text=req.raw_text,
        parsed_data=req.parsed_data,
        resume_id=req.resume_id,
        is_default=req.is_default
    )
    return {
        "id": resume.id,
        "name": resume.name,
        "score": resume.score,
        "scoreDetails": resume.score_details,
        "message": "简历保存成功"
    }


@router.post("/{resume_id}/star-polish")
def star_polish_project(
    resume_id: str,
    req: StarPolishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobResumeService(db)
    res = service.optimize_project_star({
        "project_name": req.project_name,
        "tech_stack": req.tech_stack,
        "background": req.background
    }, target_jd=req.target_jd)
    return {"starOptimized": res}


@router.post("/{resume_id}/versions")
def create_version(
    resume_id: str,
    req: CreateVersionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobResumeService(db)
    version = service.create_custom_version(
        resume_id=resume_id,
        version_name=req.version_name,
        target_job_title=req.target_job_title,
        target_jd=req.target_jd,
        custom_data=req.custom_data
    )
    return {
        "id": version.id,
        "versionName": version.version_name,
        "score": version.score,
        "starEnhancedProjects": version.star_enhanced_projects
    }


@router.delete("/{resume_id}")
def delete_resume(
    resume_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobResumeService(db)
    ok = service.delete_resume(resume_id, user_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="简历不存在或无权删除")
    return {"success": True}
