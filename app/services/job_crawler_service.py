"""多平台（BOSS直聘 / 猎聘 / 51job / 牛客网）真实岗位采集与数据同步中枢。

基于 Chrome CDP (Chrome DevTools Protocol) 与 Playwright 真实浏览器驱动架构：
1. 真实浏览器 CDP 驱动：复用用户本地已登录的 Chrome（默认端口 9223），直接从真实渲染的 DOM 提取卡片；
2. 城市代码与薪资语法结构化归一化；
3. 纯真实数据链路：拒绝任何模拟假数据，未连接或无数据时提供明确的环境诊断指导；
4. 基于大模型语义提取与智能特征规则的结构化清洗与 Upsert 入库。
"""

from __future__ import annotations

import json
import hashlib
import logging
import random
import re
import time
import uuid
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.domain.models import JobOpportunity
from app.services.crawlers.cdp_browser_driver import (
    CDPBrowserDriver,
    CrawlerConnectionError,
    CrawlerExecutionError,
)
from app.services.job_matching_service import JobMatchingService
from app.core.time_utils import utc_now_naive

logger = logging.getLogger(__name__)


class PlatformCityMapper:
    """各主流招聘平台的城市名称与代码映射转换器。"""

    CITY_CODES: Dict[str, Dict[str, str]] = {
        "boss": {
            "全国": "100010000",
            "北京": "101010100",
            "上海": "101020100",
            "广州": "101280100",
            "深圳": "101280600",
            "杭州": "101210100",
            "成都": "101270100",
            "武汉": "101200100",
            "南京": "101190100",
            "西安": "101110100",
            "苏州": "101190400",
        },
        "liepin": {
            "全国": "000",
            "北京": "010",
            "上海": "020",
            "广州": "050020",
            "深圳": "050090",
            "杭州": "070020",
            "成都": "280020",
            "武汉": "170020",
            "南京": "060020",
            "西安": "270020",
            "苏州": "060080",
        },
        "51job": {
            "全国": "000000",
            "北京": "010000",
            "上海": "020000",
            "广州": "030200",
            "深圳": "040000",
            "杭州": "080200",
            "成都": "090200",
            "武汉": "180200",
            "南京": "070200",
            "西安": "200200",
            "苏州": "070300",
        },
        "nowcoder": {
            "全国": "0",
            "北京": "1",
            "上海": "2",
            "广州": "3",
            "深圳": "4",
            "杭州": "5",
            "成都": "6",
            "武汉": "7",
            "南京": "8",
            "西安": "9",
            "苏州": "10",
        }
    }

    @classmethod
    def get_code(cls, platform: str, city_name: str) -> str:
        """获取目标平台的城市编码，默认返回全国或目标城市。"""
        p_dict = cls.CITY_CODES.get(platform, {})
        for name, code in p_dict.items():
            if name in city_name or city_name in name:
                return code
        return p_dict.get("全国", "0")


class SalaryNormalizer:
    """薪资描述智能解析与归一化（将月薪、年薪、日薪统一规范为千元/月）。"""

    @classmethod
    def parse(cls, salary_str: str) -> Tuple[Optional[int], Optional[int], str]:
        """解析薪资文本，返回 (salary_min, salary_max, salary_unit)。"""
        if not salary_str or not salary_str.strip():
            return None, None, "unknown"
        if "面议" in salary_str:
            return None, None, "negotiable"

        text = salary_str.strip().lower()

        # 1. 匹配标准 K/k 格式：25-45k 或 25-45k·16薪
        k_match = re.search(r"(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*k", text)
        if k_match:
            s_min = int(float(k_match.group(1)))
            s_max = int(float(k_match.group(2)))
            return s_min, s_max, "k"

        # 2. 匹配万/年格式：30-50万/年
        wan_year_match = re.search(r"(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*万", text)
        if wan_year_match and ("年" in text or "year" in text):
            y_min = float(wan_year_match.group(1))
            y_max = float(wan_year_match.group(2))
            s_min = max(1, int(y_min * 10 / 12))
            s_max = max(s_min, int(y_max * 10 / 12))
            return s_min, s_max, "k"

        # 3. 匹配元/天格式：200-400元/天
        day_match = re.search(r"(\d+)\s*[-~至到]\s*(\d+)\s*(?:元|块)?\s*/\s*天", text)
        if day_match:
            d_min = int(day_match.group(1))
            d_max = int(day_match.group(2))
            s_min = max(1, int(d_min * 21.75 / 1000))
            s_max = max(s_min, int(d_max * 21.75 / 1000))
            return s_min, s_max, "k"

        # 4. 纯数字区间兜底：20-35
        num_match = re.search(r"(\d+)\s*[-~至到]\s*(\d+)", text)
        if num_match:
            s_min = int(num_match.group(1))
            s_max = int(num_match.group(2))
            if s_min < 100 and s_max < 100:
                return s_min, s_max, "k"

        return None, None, "unknown"


class JobCrawlerService:
    """多平台真实岗位采集与数据同步中枢。"""

    SUPPORTED_PLATFORMS = [
        {"id": "boss", "name": "BOSS直聘", "mode": "Chrome CDP-DOM 真实驱动", "icon": "💼", "status": "active"},
        {"id": "liepin", "name": "猎聘网", "mode": "Chrome CDP-DOM 真实驱动", "icon": "🎯", "status": "active"},
        {"id": "51job", "name": "前程无忧", "mode": "Chrome CDP-DOM 真实驱动", "icon": "🏢", "status": "active"},
        {"id": "nowcoder", "name": "牛客校招", "mode": "Chrome CDP-DOM 真实驱动", "icon": "🎓", "status": "active"},
    ]

    _last_query_timestamp: float = 0.0
    _cooldown_seconds: float = 0.5

    def __init__(self, db: Session):
        self.db = db
        self.matching_service = JobMatchingService(db)

    def get_supported_platforms(self) -> List[Dict[str, Any]]:
        """获取系统支持的招聘平台列表。"""
        return self.SUPPORTED_PLATFORMS

    def check_driver_status(self, cdp_url: str = CDPBrowserDriver.DEFAULT_CDP_URL) -> Dict[str, Any]:
        """检查底层真实浏览器 CDP 驱动连接状态。"""
        return CDPBrowserDriver.check_cdp_status(cdp_url)

    def sync_platform_jobs(
        self,
        platform: str = "all",
        keyword: str = "后端开发",
        city: str = "全国",
        job_type: str = "social",
        limit_per_platform: int = 10,
        mode: str = "auto",
        cdp_url: str = CDPBrowserDriver.DEFAULT_CDP_URL,
        page: int = 1,
        max_pages: int = 1,
        enrich_details: bool = False,
    ) -> Dict[str, Any]:
        """执行多招聘平台的真实岗位采集与数据管道同步。"""
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        if max_pages < 1 or max_pages > 20:
            raise ValueError("max_pages 必须在 1 到 20 之间")
        self._wait_cooldown()

        supported_ids = {p["id"] for p in self.SUPPORTED_PLATFORMS}
        if platform not in supported_ids and platform not in {"all", "全部"}:
            raise ValueError(f"不支持的招聘平台: {platform}")
        if mode not in {"auto", "cdp", "playwright"}:
            raise ValueError(f"不支持的采集模式: {mode}")

        target_platforms = (
            [p["id"] for p in self.SUPPORTED_PLATFORMS]
            if platform in {"all", "全部"}
            else [platform]
        )

        all_raw_jobs: List[Dict[str, Any]] = []
        platform_errors: Dict[str, Any] = {}
        sync_run_id = str(uuid.uuid4())
        query_fingerprint = self._query_fingerprint(
            keyword=keyword,
            city=city,
            job_type=job_type,
            platform=platform,
        )
        sync_stats = {
            "status": "success",
            "total_fetched": 0,
            "created": 0,
            "updated": 0,
            "closed": 0,
            "platforms": target_platforms,
            "platform_errors": platform_errors,
            "driver_mode": mode,
            "page": page,
            "has_more": False,
            "next_page": None,
            "sync_run_id": sync_run_id,
            "query_fingerprint": query_fingerprint,
            "detail_attempted": 0,
            "detail_succeeded": 0,
            "detail_failed": 0,
            "detail_skipped": 0,
        }

        cdp_status = self.check_driver_status(cdp_url)
        sync_stats["cdp_status"] = cdp_status

        for plat in target_platforms:
            platform_items: List[Dict[str, Any]] = []
            platform_query_fingerprint = self._query_fingerprint(
                keyword=keyword,
                city=city,
                job_type=job_type,
                platform=plat,
            )
            platform_complete = True
            current_page = page
            try:
                for _ in range(max_pages):
                    fetch_kwargs = {
                        "limit": limit_per_platform,
                        "mode": mode,
                        "cdp_url": cdp_url,
                    }
                    if current_page != 1:
                        fetch_kwargs["page"] = current_page
                    raw_result = self._fetch_jobs_from_platform(
                        plat, keyword, city, job_type, **fetch_kwargs
                    )
                    raw_items, page_has_more, page_next = self._normalize_page_result(
                        raw_result, page=current_page, limit=limit_per_platform,
                    )
                    platform_items.extend(raw_items)
                    all_raw_jobs.extend(raw_items)
                    if not page_has_more:
                        break
                    next_page = page_next or (current_page + 1)
                    if next_page <= current_page:
                        platform_complete = False
                        break
                    current_page = next_page
                else:
                    platform_complete = False

                sync_stats["has_more"] = sync_stats["has_more"] or not platform_complete
                if not platform_complete:
                    sync_stats["next_page"] = current_page
                if platform_complete:
                    sync_stats["closed"] += self._close_stale_jobs_for_platform(
                        platform=plat,
                        city=city,
                        job_type=job_type,
                        seen_jobs=platform_items,
                        query_fingerprint=platform_query_fingerprint,
                        sync_run_id=sync_run_id,
                        persist=False,
                    )
            except Exception as e:
                logger.warning(f"采集平台 {plat} 真实数据异常: {e}")
                details = getattr(e, "details", {}) or {}
                platform_errors[plat] = {
                    "reason_code": details.get("reason_code", "crawl_failed"),
                    "message": str(e),
                }

        sync_stats["total_fetched"] = len(all_raw_jobs)

        if enrich_details and all_raw_jobs:
            detail_result = self.enrich_job_details(
                all_raw_jobs,
                mode=mode,
                cdp_url=cdp_url,
            )
            all_raw_jobs = detail_result["jobs"]
            for key in ("attempted", "succeeded", "failed", "skipped"):
                sync_stats[f"detail_{key}"] = detail_result["stats"][key]

        created_count = 0
        updated_count = 0
        saved_jobs: List[Dict[str, Any]] = []

        try:
            for raw in all_raw_jobs:
                is_new, job_obj = self._upsert_job(
                    {**raw, "_sync_query_fingerprint": self._query_fingerprint(
                        keyword=keyword,
                        city=city,
                        job_type=job_type,
                        platform=str(raw.get("source_platform") or platform),
                    ), "_sync_run_id": sync_run_id},
                    persist=False,
                )
                if is_new:
                    created_count += 1
                else:
                    updated_count += 1
                if job_obj:
                    saved_jobs.append({
                        "id": job_obj.id,
                        "title": job_obj.title,
                        "company": job_obj.company,
                        "city": job_obj.city,
                        "salary": (
                            "面议" if job_obj.salary_status == "negotiable"
                            else "薪资未知" if job_obj.salary_status == "unknown"
                            else f"{job_obj.salary_min}k-{job_obj.salary_max}k"
                        ),
                        "salary_status": job_obj.salary_status,
                        "source_platform": job_obj.source_platform,
                        "source_url": job_obj.source_url,
                        "detail_status": job_obj.detail_status,
                        "detail_error": job_obj.detail_error,
                        "detail_attempted_at": (
                            job_obj.detail_attempted_at.isoformat()
                            if job_obj.detail_attempted_at else None
                        ),
                        "is_new": is_new
                    })
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        sync_stats["created"] = created_count
        sync_stats["updated"] = updated_count
        if platform_errors and all_raw_jobs:
            sync_stats["status"] = "partial_success"
        elif platform_errors:
            sync_stats["status"] = "failed"
        elif not all_raw_jobs:
            sync_stats["status"] = "empty"

        return {
            "stats": sync_stats,
            "jobs": saved_jobs
        }

    def live_search_platform_jobs(
        self,
        platform: str = "all",
        keyword: str = "后端开发",
        city: str = "全国",
        job_type: str = "social",
        limit_per_platform: int = 10,
        mode: str = "auto",
        cdp_url: str = CDPBrowserDriver.DEFAULT_CDP_URL,
        page: int = 1,
        max_pages: int = 1,
    ) -> Dict[str, Any]:
        """直接从招聘平台检索岗位并返回结果，不写入本地岗位库。"""
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        if max_pages < 1 or max_pages > 20:
            raise ValueError("max_pages 必须在 1 到 20 之间")
        supported_ids = {p["id"] for p in self.SUPPORTED_PLATFORMS}
        if platform not in supported_ids and platform not in {"all", "全部"}:
            raise ValueError(f"不支持的招聘平台: {platform}")
        if mode not in {"auto", "cdp", "playwright"}:
            raise ValueError(f"不支持的采集模式: {mode}")

        target_platforms = (
            [p["id"] for p in self.SUPPORTED_PLATFORMS]
            if platform in {"all", "全部"}
            else [platform]
        )
        jobs: List[Dict[str, Any]] = []
        errors: Dict[str, str] = {}
        has_more = False
        next_page: Optional[int] = None
        self._wait_cooldown()
        for target in target_platforms:
            platform_items: List[Dict[str, Any]] = []
            current_page = page
            try:
                for _ in range(max_pages):
                    fetch_kwargs = {
                        "limit": limit_per_platform,
                        "mode": mode,
                        "cdp_url": cdp_url,
                    }
                    if current_page != 1:
                        fetch_kwargs["page"] = current_page
                    raw_result = self._fetch_jobs_from_platform(
                        target, keyword, city, job_type, **fetch_kwargs,
                    )
                    page_items, page_has_more, page_next = self._normalize_page_result(
                        raw_result, page=current_page, limit=limit_per_platform,
                    )
                    platform_items.extend(page_items)
                    jobs.extend(page_items)
                    if not page_has_more:
                        break
                    next_page = page_next or (current_page + 1)
                    if next_page <= current_page:
                        break
                    current_page = next_page
                else:
                    has_more = True
                    next_page = current_page
            except Exception as exc:
                logger.warning("实时搜索平台 %s 失败: %s", target, exc)
                details = getattr(exc, "details", {}) or {}
                errors[target] = {
                    "reason_code": details.get("reason_code", "crawl_failed"),
                    "message": str(exc),
                }

        return {
            "status": "success" if jobs and not errors else ("partial_success" if jobs else ("failed" if errors else "empty")),
            "keyword": keyword,
            "city": city,
            "platform": platform,
            "jobs": jobs,
            "total": len(jobs),
            "page": page,
            "has_more": has_more,
            "next_page": next_page if has_more else None,
            "platform_errors": errors,
            "persisted": False,
        }

    def _wait_cooldown(self) -> None:
        """执行查询间安全冷却与抖动延迟。"""
        now = time.time()
        elapsed = now - JobCrawlerService._last_query_timestamp
        if elapsed < JobCrawlerService._cooldown_seconds:
            wait_time = (JobCrawlerService._cooldown_seconds - elapsed) + random.uniform(0.05, 0.15)
            time.sleep(wait_time)
        JobCrawlerService._last_query_timestamp = time.time()

    @staticmethod
    def _normalize_page_result(
        result: Any,
        page: int,
        limit: int,
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[int]]:
        """兼容旧版 list 采集器，并读取新版分页 metadata。"""
        if isinstance(result, dict):
            items = result.get("items", result.get("jobs", []))
            if not isinstance(items, list):
                items = []
            has_more = bool(result.get("has_more", result.get("hasMore", False)))
            next_page = result.get("next_page", result.get("nextPage"))
            if next_page is not None:
                try:
                    next_page = int(next_page)
                except (TypeError, ValueError):
                    next_page = None
            return items, has_more, next_page
        if isinstance(result, list):
            # 旧驱动只返回岗位列表，不能据此断言还有下一页；保守地不关闭 stale 岗位。
            return result, False, None
        return [], False, None

    def _close_stale_jobs_for_platform(
        self,
        platform: str,
        city: str,
        job_type: str,
        seen_jobs: List[Dict[str, Any]],
        stale_after_days: int = 30,
        sync_run_id: str = "",
        query_fingerprint: str = "",
        persist: bool = True,
    ) -> int:
        """仅在平台成功返回数据时关闭长期未见岗位，避免短暂故障误下架。"""
        if not seen_jobs:
            return 0

        seen_external_ids = {
            str(item.get("external_job_id") or item.get("job_id")).strip()
            for item in seen_jobs
            if item.get("external_job_id") or item.get("job_id")
        }
        seen_urls = {
            self._canonical_url((item.get("source_url") or "").strip())
            for item in seen_jobs
            if item.get("source_url")
        }
        cutoff = utc_now_naive() - timedelta(days=stale_after_days)
        query = self.db.query(JobOpportunity).filter(
            JobOpportunity.source_platform == platform,
            JobOpportunity.city == city,
            JobOpportunity.job_type == job_type,
            JobOpportunity.status == "active",
            JobOpportunity.last_seen_at.isnot(None),
            JobOpportunity.last_seen_at < cutoff,
            or_(
                JobOpportunity.sync_query_fingerprint == query_fingerprint,
                JobOpportunity.sync_query_fingerprint == "",
            ),
        )
        closed = 0
        for job in query.all():
            if job.external_job_id and job.external_job_id in seen_external_ids:
                continue
            if job.source_url_canonical and job.source_url_canonical in seen_urls:
                continue
            job.status = "closed"
            closed += 1
        if closed and persist:
            self.db.commit()
        return closed

    def enrich_job_details(
        self,
        jobs: List[Dict[str, Any]],
        mode: str = "auto",
        cdp_url: str = CDPBrowserDriver.DEFAULT_CDP_URL,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """对列表岗位执行真实详情页二阶段采集；详情失败不丢失列表岗位。"""
        stats = {"attempted": 0, "succeeded": 0, "failed": 0, "skipped": 0}
        enriched = []
        for raw in jobs:
            url = (raw.get("source_url") or "").strip()
            if not url:
                raw.update({"detail_status": "skipped", "detail_error": "missing_url"})
                stats["skipped"] += 1
                enriched.append(raw)
                continue
            stats["attempted"] += 1
            last_error = ""
            for attempt in range(max(1, max_retries + 1)):
                try:
                    if mode not in {"auto", "cdp"}:
                        raise CrawlerExecutionError("详情采集必须复用真实 CDP 页面", str(raw.get("source_platform") or ""), url, {"reason_code": "unsupported_mode"})
                    detail = CDPBrowserDriver.crawl_job_detail_via_cdp(
                        str(raw.get("source_platform") or "boss"), url, cdp_url,
                    )
                    raw.update({k: v for k, v in detail.items() if v})
                    raw["detail_status"] = "success"
                    raw["detail_error"] = ""
                    stats["succeeded"] += 1
                    break
                except Exception as exc:
                    details = getattr(exc, "details", {}) or {}
                    last_error = json.dumps({"reason_code": details.get("reason_code", "unknown"), "message": str(exc)}, ensure_ascii=False)
                    if attempt < max_retries:
                        # 详情页失败通常是瞬时导航/CDP问题，采用指数退避并加入轻微抖动。
                        delay = min(2.0, 0.2 * (2 ** attempt)) + random.uniform(0.0, 0.05)
                        time.sleep(delay)
            else:
                raw.update({"detail_status": "failed", "detail_error": last_error})
                stats["failed"] += 1
            enriched.append(raw)
        return {"jobs": enriched, "stats": stats}

    def _fetch_jobs_from_platform(
        self,
        platform: str,
        keyword: str,
        city: str,
        job_type: str,
        limit: int = 10,
        mode: str = "auto",
        cdp_url: str = CDPBrowserDriver.DEFAULT_CDP_URL,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """按平台调用真实浏览器（CDP 或 Playwright）采集岗位。"""
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        city_code = PlatformCityMapper.get_code(platform, city)

        # 优先使用 CDP 连接本地已打开并登录的 Chrome 浏览器
        if mode in {"auto", "cdp"}:
            status = CDPBrowserDriver.check_cdp_status(cdp_url)
            if status.get("connected"):
                try:
                    return CDPBrowserDriver.crawl_jobs_via_cdp(
                        platform=platform,
                        keyword=keyword,
                        city=city,
                        city_code=city_code,
                        job_type=job_type,
                        limit=limit,
                        cdp_url=cdp_url,
                        page=page,
                    )
                except Exception as e:
                    logger.warning(f"CDP 抓取平台 {platform} 失败: {e}")
                    if mode == "cdp":
                        raise e

        # 备选使用 Playwright 独立浏览器
        if mode in {"auto", "playwright"}:
            try:
                return CDPBrowserDriver.crawl_jobs_via_playwright(
                    platform=platform,
                    keyword=keyword,
                    city=city,
                    city_code=city_code,
                    job_type=job_type,
                    limit=limit,
                    page=page,
                )
            except Exception as e:
                logger.error(f"Playwright 抓取平台 {platform} 失败: {e}")
                raise CrawlerConnectionError(
                    message=f"真实浏览器抓取失败：未检测到已连接的 Chrome 9223 端口，Playwright 抓取亦异常 ({e})",
                    instruction=CDPBrowserDriver.get_launch_command()
                )

        raise CrawlerConnectionError(
            message=f"未找到可用的真实浏览器驱动，请启动本地 Chrome 远程调试端口 9223",
            instruction=CDPBrowserDriver.get_launch_command()
        )

    @staticmethod
    def _query_fingerprint(
        keyword: str,
        city: str,
        job_type: str,
        platform: str,
    ) -> str:
        """为 stale 生命周期绑定稳定的查询范围，避免不同搜索条件互相下架。"""
        payload = json.dumps(
            {
                "keyword": (keyword or "").strip().casefold(),
                "city": (city or "").strip(),
                "job_type": (job_type or "").strip().casefold(),
                "platform": (platform or "").strip().casefold(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_url(url: str) -> str:
        if not url:
            return ""
        parts = urlsplit(url.strip())
        query = [(key, value) for key, value in parse_qsl(parts.query) if key.lower() not in {"utm_source", "utm_medium", "utm_campaign", "spm"}]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(sorted(query)), ""))

    @staticmethod
    def _jd_hash(jd_text: str) -> str:
        return hashlib.sha256((jd_text or "").strip().encode("utf-8")).hexdigest()

    def _upsert_job(
        self,
        raw: Dict[str, Any],
        persist: bool = True,
    ) -> Tuple[bool, Optional[JobOpportunity]]:
        """基于外部职位标识、规范化 URL 或业务字段执行增量 Upsert。"""
        company = (raw.get("company") or "").strip()
        title = (raw.get("title") or "").strip()
        city = (raw.get("city") or "全国").strip()
        platform = (raw.get("source_platform") or "boss").strip()
        salary_str = (raw.get("salary_str") or "").strip()
        jd_text = (raw.get("jd_text") or "").strip()
        source_url = (raw.get("source_url") or "").strip()
        external_job_id = (raw.get("external_job_id") or raw.get("job_id") or "").strip() or None
        canonical_url = self._canonical_url(source_url)
        jd_hash = self._jd_hash(jd_text)
        sync_query_fingerprint = str(raw.get("_sync_query_fingerprint") or "")
        sync_run_id = str(raw.get("_sync_run_id") or "")
        detail_status = str(raw.get("detail_status") or ("success" if jd_text else "pending"))
        detail_error = str(raw.get("detail_error") or "")

        if not company or not title:
            return False, None

        s_min, s_max, s_unit = SalaryNormalizer.parse(salary_str)
        salary_status = "known" if s_unit == "k" and s_min is not None and s_max is not None else s_unit

        # 检查是否已存在：优先使用平台内外部 ID；若 ID 变化，再回退到规范化 URL。
        existing = None
        if external_job_id:
            existing = (
                self.db.query(JobOpportunity)
                .filter(
                    JobOpportunity.source_platform == platform,
                    JobOpportunity.external_job_id == external_job_id,
                )
                .first()
            )
        if existing is None and canonical_url:
            existing = (
                self.db.query(JobOpportunity)
                .filter(
                    JobOpportunity.source_platform == platform,
                    JobOpportunity.source_url_canonical == canonical_url,
                )
                .first()
            )
        if existing is None and not external_job_id and not canonical_url:
            existing = (
                self.db.query(JobOpportunity)
                .filter(
                    JobOpportunity.source_platform == platform,
                    JobOpportunity.company == company,
                    JobOpportunity.title == title,
                    JobOpportunity.city == city,
                )
                .first()
            )

        if existing:
            existing.title = title
            existing.company = company
            existing.city = city
            existing.salary_min = s_min
            existing.salary_max = s_max
            existing.salary_unit = s_unit
            existing.salary_status = salary_status
            if jd_text:
                existing.jd_text = jd_text
            if source_url:
                existing.source_url = source_url
            existing.external_job_id = external_job_id or existing.external_job_id
            existing.source_url_canonical = canonical_url or existing.source_url_canonical
            existing.jd_hash = jd_hash
            existing.sync_query_fingerprint = sync_query_fingerprint or existing.sync_query_fingerprint
            existing.last_sync_run_id = sync_run_id or existing.last_sync_run_id
            existing.last_seen_at = utc_now_naive()
            existing.detail_status = detail_status
            existing.detail_error = detail_error
            existing.detail_attempted_at = utc_now_naive() if detail_status in {"success", "failed"} else existing.detail_attempted_at
            existing.status = "active"
            if persist:
                self.db.commit()
                self.db.refresh(existing)
            else:
                self.db.flush()
            return False, existing

        # 提取技能与职责
        req_skills = raw.get("required_skills") or raw.get("tags") or []
        pref_skills = raw.get("preferred_skills") or []
        resp = raw.get("responsibilities") or []
        bene = raw.get("benefits") or raw.get("company_tags") or []

        if not req_skills and jd_text:
            parsed = self.matching_service.parse_jd_text(jd_text, title=title)
            req_skills = parsed.get("required_skills", [])
            pref_skills = parsed.get("preferred_skills", [])
            resp = parsed.get("responsibilities", [])
            bene = parsed.get("benefits", [])

        new_job = JobOpportunity(
            title=title,
            company=company,
            city=city,
            salary_min=s_min,
            salary_max=s_max,
            salary_unit=s_unit,
            salary_status=salary_status,
            education_req=raw.get("education_req", "学历不限"),
            experience_req=raw.get("experience_req", "经验不限"),
            job_type=raw.get("job_type", "social"),
            source_platform=platform,
            source_url=source_url,
            external_job_id=external_job_id,
            source_url_canonical=canonical_url,
            jd_hash=jd_hash,
            sync_query_fingerprint=sync_query_fingerprint,
            last_sync_run_id=sync_run_id,
            last_seen_at=utc_now_naive(),
            company_tags=raw.get("company_tags", ["真实招聘"]),
            jd_text=jd_text,
            required_skills=req_skills,
            preferred_skills=pref_skills,
            responsibilities=resp,
            benefits=bene,
            detail_status=detail_status,
            detail_error=detail_error,
            detail_attempted_at=utc_now_naive() if detail_status in {"success", "failed"} else None,
            status="active"
        )

        self.db.add(new_job)
        if persist:
            self.db.commit()
            self.db.refresh(new_job)
        else:
            self.db.flush()
        return True, new_job
