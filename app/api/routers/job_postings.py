"""智能求职 Agent 招聘岗位机会库 API 路由。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.dependencies import get_current_user
from app.services.job_matching_service import JobMatchingService
from app.services.job_crawler_service import JobCrawlerService

router = APIRouter(prefix="/jobs/postings", tags=["Job Postings"])


class CreateJobPostingRequest(BaseModel):
    title: str
    company: str
    jd_text: str
    city: str = "北京"
    salary_min: int = 15
    salary_max: int = 30
    education_req: str = "本科及以上"
    experience_req: str = "1-3年"
    job_type: str = "social"
    source_platform: str = "nowcoder"
    source_url: str = ""
    company_tags: List[str] = []


class ParseJdRequest(BaseModel):
    jd_text: str
    title: str = ""


class SyncJobsRequest(BaseModel):
    platform: str = "all"  # 'boss', 'liepin', '51job', 'nowcoder', 'all'
    keyword: str = "后端开发"
    city: str = "全国"
    job_type: str = "social"
    limit_per_platform: int = 10


@router.get("/platforms")
def get_supported_platforms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    crawler = JobCrawlerService(db)
    return {"platforms": crawler.get_supported_platforms()}


@router.post("/sync")
def sync_jobs(
    req: SyncJobsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    crawler = JobCrawlerService(db)
    result = crawler.sync_platform_jobs(
        platform=req.platform,
        keyword=req.keyword,
        city=req.city,
        job_type=req.job_type,
        limit_per_platform=req.limit_per_platform
    )
    return {
        "code": 200,
        "message": f"成功从招聘平台同步岗位（新增 {result['stats']['created']} 条，更新 {result['stats']['updated']} 条）",
        "data": result
    }


@router.get("")
def list_jobs(
    keyword: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    source_platform: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobMatchingService(db)
    jobs, total = service.get_job_postings(
        keyword=keyword,
        city=city,
        job_type=job_type,
        source_platform=source_platform,
        limit=limit,
        offset=offset
    )
    return {
        "total": total,
        "items": [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "companyLogo": j.company_logo,
                "city": j.city,
                "salaryMin": j.salary_min,
                "salaryMax": j.salary_max,
                "salaryUnit": j.salary_unit,
                "educationReq": j.education_req,
                "experienceReq": j.experience_req,
                "jobType": j.job_type,
                "sourcePlatform": j.source_platform,
                "sourceUrl": j.source_url,
                "companyTags": j.company_tags,
                "requiredSkills": j.required_skills,
                "preferredSkills": j.preferred_skills,
                "responsibilities": j.responsibilities,
                "benefits": j.benefits,
                "createdAt": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ]
    }


@router.get("/{job_id}")
def get_job_detail(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobMatchingService(db)
    job = service.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "companyLogo": job.company_logo,
        "city": job.city,
        "salaryMin": job.salary_min,
        "salaryMax": job.salary_max,
        "salaryUnit": job.salary_unit,
        "educationReq": job.education_req,
        "experienceReq": job.experience_req,
        "jobType": job.job_type,
        "sourcePlatform": job.source_platform,
        "sourceUrl": job.source_url,
        "companyTags": job.company_tags,
        "jdText": job.jd_text,
        "requiredSkills": job.required_skills,
        "preferredSkills": job.preferred_skills,
        "responsibilities": job.responsibilities,
        "benefits": job.benefits,
        "createdAt": job.created_at.isoformat() if job.created_at else None,
    }


@router.post("/parse-jd")
def parse_jd(
    req: ParseJdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobMatchingService(db)
    parsed = service.parse_jd_text(req.jd_text, title=req.title)
    return {"parsedJd": parsed}


@router.post("")
def create_job(
    req: CreateJobPostingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobMatchingService(db)
    job = service.create_or_import_job(
        title=req.title,
        company=req.company,
        jd_text=req.jd_text,
        city=req.city,
        salary_min=req.salary_min,
        salary_max=req.salary_max,
        education_req=req.education_req,
        experience_req=req.experience_req,
        job_type=req.job_type,
        source_platform=req.source_platform,
        source_url=req.source_url,
        company_tags=req.company_tags
    )
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "message": "岗位录入成功"
    }
