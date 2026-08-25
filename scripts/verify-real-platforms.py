"""通过用户已登录 Chrome CDP 执行四个平台真实搜索与详情验收。

本脚本不登录、不保存密码、不生成岗位；所有结果均来自当前 Chrome 页面 DOM。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.crawlers.cdp_browser_driver import CDPBrowserDriver, CrawlerExecutionError
from app.services.crawlers.dom_extractors import DOMExtractors
from app.services.job_crawler_service import PlatformCityMapper

PLATFORMS = ("boss", "liepin", "51job", "nowcoder")
DOM_BLOCK_MARKERS = ("滑块验证码", "人机验证", "安全验证", "security.min.js", "acw_tc")
AUTH_MARKERS = ("请先登录", "立即登录", "登录后查看", "login required")
LOGIN_EVIDENCE_MARKERS = ("退出登录", "退出", "个人中心", "我的简历", "账号设置", "logout")


def _reason(page_text: str) -> str | None:
    lowered = page_text.lower()
    if "security.min.js" in lowered or "acw_tc" in lowered or "滑块验证码" in page_text or "安全验证" in page_text:
        return "anti_bot"
    if any(marker.lower() in lowered for marker in AUTH_MARKERS):
        return "auth_required"
    return None


async def _extract_search_jobs(page: Any, platform: str) -> list[dict[str, Any]]:
    """按当前真实页面 DOM 提取岗位；脚本只读页面，不注入数据。"""
    raw_jobs = await page.evaluate(DOMExtractors.get_extractor_js(platform))
    if not isinstance(raw_jobs, list):
        return []
    return [item for item in raw_jobs if item.get("title") and item.get("company")]


async def _find_detail_url(page: Any, platform: str) -> str:
    if platform == "51job":
        links = await page.locator('a[href*="jobs.51job.com"]').evaluate_all(
            "els => els.map(a => a.href).filter(href => /jobs\\.51job\\.com\\/[^/]+\\/[0-9]+[.]html/.test(href))"
        )
        return links[0] if links else ""
    return ""


async def verify_platform(platform: str, keyword: str, city: str, cdp_url: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "platform": platform,
        "cdp_connected": False,
        "login_verified": False,
        "anti_bot_clear": False,
        "search_verified": False,
        "detail_verified": False,
        "status": "failed",
        "reason_code": None,
        "jobs_found": 0,
    }
    status = CDPBrowserDriver.check_cdp_status(cdp_url)
    if not status.get("connected"):
        result.update({"reason_code": "cdp_unavailable", "message": status.get("error", "CDP unavailable")})
        return result
    result["cdp_connected"] = True

    from playwright.async_api import async_playwright

    target_url = DOMExtractors.get_search_url(
        platform,
        keyword,
        PlatformCityMapper.get_code(platform, city),
        "social",
        page=1,
    )
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        platform_domains = {
            "boss": "zhipin.com",
            "liepin": "liepin.com",
            "51job": "51job.com",
            "nowcoder": "nowcoder.com",
        }
        existing_page = next(
            (candidate for candidate in context.pages if platform_domains[platform] in candidate.url),
            None,
        )
        page = existing_page or await context.new_page()
        owns_page = existing_page is None
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)
            if page.url == "about:blank" or not await page.title():
                result.update({"reason_code": "navigation_blocked", "message": "平台导航返回空白页面，可能被网络、浏览器策略或平台风控拦截"})
                return result
            page_text = await page.locator("body").inner_text()
            blocked = _reason(page_text)
            if blocked:
                result.update({"reason_code": blocked, "message": "真实页面需要登录或安全验证"})
                return result
            if not any(marker.lower() in page_text.lower() for marker in LOGIN_EVIDENCE_MARKERS):
                result.update({"reason_code": "auth_unverified", "message": "页面未出现可确认登录态的证据"})
                return result
            result["login_verified"] = True
            result["anti_bot_clear"] = True

            raw_jobs = await page.evaluate(DOMExtractors.get_extractor_js(platform))
            if not isinstance(raw_jobs, list) or not raw_jobs:
                result.update({"reason_code": "dom_missing", "message": "未从真实页面 DOM 提取到岗位卡片"})
                return result
            jobs = [item for item in raw_jobs if item.get("title") and item.get("company")]
            if not jobs:
                result.update({"reason_code": "dom_missing", "message": "岗位卡片缺少 title/company"})
                return result
            result["jobs_found"] = len(jobs)
            result["search_verified"] = True
            result["sample_job"] = {key: jobs[0].get(key, "") for key in ("title", "company", "source_url")}

            detail_url = jobs[0].get("source_url") or await _find_detail_url(page, platform)
            if platform == "51job":
                detail_jobs = [
                    item for item in jobs
                    if re.search(r"jobs\\.51job\\.com/[^/]+/[0-9]+[.]html", str(item.get("source_url") or ""))
                ]
                if detail_jobs:
                    jobs = detail_jobs
                    result["sample_job"] = {key: jobs[0].get(key, "") for key in ("title", "company", "source_url")}
                    detail_url = jobs[0].get("source_url")
                else:
                    detail_url = await _find_detail_url(page, platform)
            if not detail_url:
                result.update({"reason_code": "missing_url", "message": "首个真实岗位没有详情 URL"})
                return result
            result["login_verified"] = True
            detail_page = await context.new_page()
            try:
                detail_error = None
                for attempt in range(3):
                    try:
                        await detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                        detail_error = None
                        break
                    except Exception as exc:
                        detail_error = exc
                        if attempt < 2:
                            await detail_page.wait_for_timeout(1000 * (attempt + 1))
                if detail_error is not None:
                    result.update({"reason_code": "navigation_timeout", "message": str(detail_error)})
                    return result
                await detail_page.wait_for_timeout(1500)
                detail_text = await detail_page.locator("body").inner_text()
                blocked = _reason(detail_text)
                if blocked:
                    result.update({"reason_code": blocked, "message": "详情页需要登录或安全验证"})
                    return result
                if not any(marker.lower() in detail_text.lower() for marker in LOGIN_EVIDENCE_MARKERS):
                    result.update({"reason_code": "auth_unverified", "message": "详情页未出现可确认登录态的证据"})
                    return result
                detail = await detail_page.evaluate(DOMExtractors.get_detail_extractor_js(platform))
                jd = str(detail.get("jd_text") or "") if isinstance(detail, dict) else ""
                if not isinstance(detail, dict) or not detail.get("jd_found") or len(jd) < 40:
                    result.update({"reason_code": "dom_missing", "message": "详情页没有足够长度的 JD 容器文本"})
                    return result
                result["detail_verified"] = True
                result["detail_chars"] = len(jd)
                result["status"] = "verified"
                result["login_verified"] = True
                return result
            finally:
                await detail_page.close()
        except Exception as exc:
            details = getattr(exc, "details", {}) or {}
            result.update({"reason_code": details.get("reason_code", "browser_error"), "message": str(exc)})
            return result
        finally:
            if owns_page:
                await page.close()
            # 不关闭用户的 Chrome；CDP 会话属于用户，脚本只关闭自己创建的标签页。


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp-url", default=CDPBrowserDriver.DEFAULT_CDP_URL)
    parser.add_argument("--keyword", default="Python")
    parser.add_argument("--city", default="北京")
    args = parser.parse_args()
    results = [await verify_platform(platform, args.keyword, args.city, args.cdp_url) for platform in PLATFORMS]
    print(json.dumps({"keyword": args.keyword, "city": args.city, "results": results}, ensure_ascii=False, indent=2))
    return 0 if all(item["status"] == "verified" for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
