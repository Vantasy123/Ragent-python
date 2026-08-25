"""智能求职 Agent 招聘岗位机会库 API 路由。"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.dependencies import get_current_user
from app.services.job_matching_service import JobMatchingService
from app.services.job_crawler_service import JobCrawlerService
from app.services.crawlers.cdp_browser_driver import CDPBrowserDriver

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
    platform: Literal["all", "boss", "liepin", "51job", "nowcoder"] = "all"
    keyword: str = "后端开发"
    city: str = "全国"
    job_type: str = "social"
    limit_per_platform: int = Field(10, ge=1, le=50)
    page: int = Field(1, ge=1)
    max_pages: int = Field(1, ge=1, le=20)
    enrich_details: bool = False
    mode: Literal["auto", "cdp", "playwright"] = "auto"
    cdp_url: str = CDPBrowserDriver.DEFAULT_CDP_URL


@router.get("/crawlers/cdp-status")
def get_cdp_status(
    cdp_url: str = Query(CDPBrowserDriver.DEFAULT_CDP_URL),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """检测本地 Chrome 远程调试端口（9223）连接状态与活动标签页。"""
    crawler = JobCrawlerService(db)
    status = crawler.check_driver_status(cdp_url)
    return {
        "code": 200,
        "data": status
    }


@router.get("/platforms")
def get_supported_platforms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    crawler = JobCrawlerService(db)
    return {"platforms": crawler.get_supported_platforms()}


@router.post("/live-search")
def live_search_jobs(
    req: SyncJobsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """直接检索招聘平台并返回真实岗位，不写入本地岗位库。"""
    crawler = JobCrawlerService(db)
    try:
        result = crawler.live_search_platform_jobs(
            platform=req.platform,
            keyword=req.keyword,
            city=req.city,
            job_type=req.job_type,
            limit_per_platform=req.limit_per_platform,
            mode=req.mode,
            cdp_url=req.cdp_url,
            page=req.page,
            max_pages=req.max_pages,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"code": 200, "message": "已完成实时平台搜索", "data": result}


@router.post("/sync")
def sync_jobs(
    req: SyncJobsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    crawler = JobCrawlerService(db)
    try:
        result = crawler.sync_platform_jobs(
            platform=req.platform,
            keyword=req.keyword,
            city=req.city,
            job_type=req.job_type,
            limit_per_platform=req.limit_per_platform,
            mode=req.mode,
            cdp_url=req.cdp_url,
            page=req.page,
            max_pages=req.max_pages,
            enrich_details=req.enrich_details,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    created = result['stats'].get('created', 0)
    updated = result['stats'].get('updated', 0)
    total_fetched = result['stats'].get('total_fetched', 0)

    if total_fetched > 0:
        msg = f"成功从真实招聘平台同步 {total_fetched} 个岗位（新增 {created} 条，更新 {updated} 条）"
    else:
        errors = result['stats'].get('platform_errors', {})
        if errors:
            first_error = next(iter(errors.values()))
            error_text = first_error if isinstance(first_error, str) else first_error.get('message', str(first_error))
            reason_code = first_error.get('reason_code') if isinstance(first_error, dict) else None
            prefix = {
                'auth_required': '平台登录态不可用',
                'anti_bot': '平台触发验证码或风控',
                'dom_missing': '平台页面结构未识别',
                'cdp_unavailable': 'Chrome CDP 不可用',
            }.get(reason_code, '真实采集未完成')
            msg = f"{prefix}：{error_text}"
        else:
            msg = "未抓取到符合条件的真实岗位"

    return {
        "code": 200,
        "message": msg,
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
        "offset": offset,
        "limit": limit,
        "hasMore": offset + len(jobs) < total,
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
                "salaryStatus": j.salary_status,
                "educationReq": j.education_req,
                "experienceReq": j.experience_req,
                "jobType": j.job_type,
                "sourcePlatform": j.source_platform,
                "sourceUrl": j.source_url,
                "externalJobId": j.external_job_id,
                "sourceUrlCanonical": j.source_url_canonical,
                "lastSeenAt": j.last_seen_at.isoformat() if j.last_seen_at else None,
                "detailStatus": j.detail_status,
                "detailError": j.detail_error,
                "detailAttemptedAt": j.detail_attempted_at.isoformat() if j.detail_attempted_at else None,
                "jdText": j.jd_text,
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
        "salaryStatus": job.salary_status,
        "educationReq": job.education_req,
        "experienceReq": job.experience_req,
        "jobType": job.job_type,
        "sourcePlatform": job.source_platform,
        "sourceUrl": job.source_url,
        "externalJobId": job.external_job_id,
        "sourceUrlCanonical": job.source_url_canonical,
        "lastSeenAt": job.last_seen_at.isoformat() if job.last_seen_at else None,
        "detailStatus": job.detail_status,
        "detailError": job.detail_error,
        "detailAttemptedAt": job.detail_attempted_at.isoformat() if job.detail_attempted_at else None,
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
