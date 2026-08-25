"""Chrome CDP (Chrome DevTools Protocol) 真实浏览器远程调试与 Playwright 驱动模块。

核心设计：
1. 直连用户本地启动了 --remote-debugging-port=9223 的 Chrome 浏览器，复用真实登录态与 Cookie；
2. 自动化打开各平台岗位搜索页，等待渲染并注入 DOM 抽取脚本；
3. 支持 Playwright 无头模式作为备用驱动；
4. 绝不生成任何模拟/假数据，连接失败或无数据时明确抛出结构化错误与指引。
"""

from __future__ import annotations

import asyncio
import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional
import httpx

from app.services.crawlers.dom_extractors import DOMExtractors

logger = logging.getLogger(__name__)


class CrawlerConnectionError(Exception):
    """当无法连接到 Chrome CDP 调试端口且无可用真实驱动时抛出。"""
    def __init__(self, message: str, instruction: str = "", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.instruction = instruction
        self.details = details or {}


class CrawlerExecutionError(Exception):
    """真实页面抓取执行失败（如被滑块验证码阻塞或页面超时）时抛出。"""
    def __init__(self, message: str, platform: str, url: str = "", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.platform = platform
        self.url = url
        self.details = details or {}


class CDPBrowserDriver:
    """CDP 真实浏览器驱动与页面自动化控制器。"""

    DEFAULT_CDP_URL = os.getenv("RAGENT_CDP_URL", "http://127.0.0.1:9223")

    @classmethod
    def get_effective_cdp_url(cls, cdp_url: str | None = None) -> str:
        """解析 CDP 地址；容器内可通过 host.docker.internal 访问宿主 Chrome。"""
        url = (cdp_url or cls.DEFAULT_CDP_URL).strip()
        if os.getenv("RAGENT_RUNNING_IN_DOCKER", "").lower() in {"1", "true", "yes"}:
            if url.startswith("http://127.0.0.1") or url.startswith("http://localhost"):
                return url.replace("127.0.0.1", "host.docker.internal").replace("localhost", "host.docker.internal", 1)
        return url

    @classmethod
    def check_cdp_status(cls, cdp_url: str = DEFAULT_CDP_URL) -> Dict[str, Any]:
        """探测本地 Chrome CDP 远程调试端口是否可用以及已打开的标签页。"""
        effective_cdp_url = cls.get_effective_cdp_url(cdp_url)
        url = effective_cdp_url.rstrip("/")
        try:
            with httpx.Client(timeout=1.2) as client:
                resp = client.get(f"{url}/json/version")
                if resp.status_code != 200:
                    return {
                        "connected": False,
                        "cdp_connected": False,
                        "platform_session_state": {},
                        "error": f"CDP 端口响应非 200: {resp.status_code}",
                        "instruction": cls.get_launch_command()
                    }
                version_info = resp.json()

                list_resp = client.get(f"{url}/json/list")
                if list_resp.status_code != 200:
                    return {
                        "connected": False,
                        "cdp_connected": True,
                        "error": f"CDP 标签页接口响应非 200: {list_resp.status_code}",
                        "instruction": cls.get_launch_command(),
                        "cdp_url": effective_cdp_url,
                    }
                tabs = list_resp.json()
                if not isinstance(tabs, list):
                    return {
                        "connected": False,
                        "cdp_connected": True,
                        "error": "CDP 标签页接口返回格式异常",
                        "instruction": cls.get_launch_command(),
                        "cdp_url": effective_cdp_url,
                    }

                tab_summaries = []
                logged_in_platforms = []
                for t in tabs:
                    tab_url = t.get("url", "")
                    tab_title = t.get("title", "")
                    platform_id = cls._identify_platform_by_url(tab_url)
                    if platform_id:
                        logged_in_platforms.append(platform_id)
                    tab_summaries.append({
                        "id": t.get("id"),
                        "title": tab_title,
                        "url": tab_url,
                        "type": t.get("type"),
                        "platform": platform_id
                    })

                platform_session_state = {}
                for platform_id in set(logged_in_platforms):
                    platform_session_state[platform_id] = "unknown"

                return {
                    "connected": True,
                    "cdp_connected": True,
                    "browser": version_info.get("Browser", "Chrome"),
                    "protocol_version": version_info.get("Protocol-Version"),
                    "webSocketDebuggerUrl": version_info.get("webSocketDebuggerUrl"),
                    "tabs_count": len(tabs),
                    "logged_in_platforms": list(set(logged_in_platforms)),
                    "platform_session_state": platform_session_state,
                    "tabs": tab_summaries[:10],
                    "cdp_url": effective_cdp_url
                }
        except Exception as e:
            return {
                "connected": False,
                "cdp_connected": False,
                "platform_session_state": {},
                "error": f"无法连接到 Chrome 调试端口 ({cdp_url}): {e}",
                "instruction": cls.get_launch_command(),
                "cdp_url": cdp_url
            }

    @classmethod
    def get_launch_command(cls) -> str:
        """返回在本地启动 Chrome CDP 调试端口的推荐命令行（支持 Windows 完整路径）。"""
        return 'chrome.exe --remote-debugging-port=9223 --user-data-dir="C:\\ragent-chrome"'

    @classmethod
    def _identify_platform_by_url(cls, url: str) -> Optional[str]:
        """识别 URL 所属招聘平台。"""
        if "zhipin.com" in url:
            return "boss"
        elif "liepin.com" in url:
            return "liepin"
        elif "51job.com" in url:
            return "51job"
        elif "nowcoder.com" in url:
            return "nowcoder"
        return None

    @classmethod
    def crawl_job_detail_via_cdp(
        cls,
        platform: str,
        source_url: str,
        cdp_url: str = DEFAULT_CDP_URL,
        timeout_seconds: float = 20.0,
    ) -> Dict[str, Any]:
        """复用本地已登录 Chrome，访问真实详情页并提取 DOM。"""
        if not source_url:
            raise CrawlerExecutionError("详情页 URL 为空", platform, details={"reason_code": "missing_url"})
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        effective_cdp_url = cls.get_effective_cdp_url(cdp_url)
        coro = cls._async_crawl_job_detail_via_cdp(platform, source_url, effective_cdp_url, timeout_seconds)
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(asyncio.run, coro).result(timeout=timeout_seconds + 5)
        return loop.run_until_complete(coro)

    @classmethod
    async def _async_crawl_job_detail_via_cdp(
        cls, platform: str, source_url: str, cdp_url: str, timeout_seconds: float,
    ) -> Dict[str, Any]:
        from playwright.async_api import async_playwright
        status = cls.check_cdp_status(cdp_url)
        if not status.get("connected"):
            raise CrawlerConnectionError("无法连接到 Chrome CDP 调试端口", cls.get_launch_command(), {"reason_code": "cdp_unavailable"})
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            browser_page = await context.new_page()
            try:
                await browser_page.goto(source_url, timeout=int(timeout_seconds * 1000), wait_until="domcontentloaded")
                if browser_page.url in {"", "about:blank"}:
                    raise CrawlerExecutionError(
                        "详情页导航后为空白页面",
                        platform,
                        source_url,
                        {"reason_code": "navigation_blocked"},
                    )
                extractor = DOMExtractors.get_detail_extractor_js(platform)
                result = await browser_page.evaluate(extractor)
                if not isinstance(result, dict) or not result.get("jd_found") or len(str(result.get("jd_text") or "")) < 40:
                    raise CrawlerExecutionError(
                        "详情页缺少可识别的 JD DOM",
                        platform,
                        source_url,
                        {"reason_code": "dom_missing"},
                    )
                return result
            except CrawlerExecutionError:
                raise
            except Exception as exc:
                reason = "navigation_timeout" if "timeout" in str(exc).lower() else "parse_error"
                raise CrawlerExecutionError(str(exc), platform, source_url, {"reason_code": reason})
            finally:
                await browser_page.close()

    @classmethod
    def crawl_jobs_via_cdp(
        cls,
        platform: str,
        keyword: str,
        city: str,
        city_code: str,
        job_type: str = "social",
        limit: int = 10,
        cdp_url: str = DEFAULT_CDP_URL,
        timeout_seconds: float = 20.0,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """通过同步封装调用异步 CDP 采集。"""
        if limit < 1 or limit > 50:
            raise ValueError("limit 必须在 1 到 50 之间")
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        effective_cdp_url = cls.get_effective_cdp_url(cdp_url)
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    cls._async_crawl_jobs_via_cdp(
                        platform, keyword, city, city_code, job_type, limit,
                        effective_cdp_url, timeout_seconds, page,
                    )
                )
                return future.result(timeout=timeout_seconds + 5)
        return loop.run_until_complete(
            cls._async_crawl_jobs_via_cdp(
                platform, keyword, city, city_code, job_type, limit,
                effective_cdp_url, timeout_seconds, page,
            )
        )

    @classmethod
    async def _async_crawl_jobs_via_cdp(
        cls,
        platform: str,
        keyword: str,
        city: str,
        city_code: str,
        job_type: str = "social",
        limit: int = 10,
        cdp_url: str = DEFAULT_CDP_URL,
        timeout_seconds: float = 20.0,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """异步执行 CDP 真实页面导航与 DOM 提取。"""
        from playwright.async_api import async_playwright

        target_url = DOMExtractors.get_search_url(platform, keyword, city_code, job_type, page=page)
        extractor_js = DOMExtractors.get_extractor_js(platform)

        status = cls.check_cdp_status(cdp_url)
        if not status.get("connected"):
            raise CrawlerConnectionError(
                message=f"无法连接到 Chrome CDP 调试端口 ({cdp_url})，请先启动本地 Chrome 浏览器。",
                instruction=cls.get_launch_command(),
                details={"status": status}
            )

        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(cdp_url)
            except Exception as conn_err:
                raise CrawlerConnectionError(
                    message=f"Playwright 连接 Chrome CDP ({cdp_url}) 失败: {conn_err}",
                    instruction=cls.get_launch_command(),
                    details={"error": str(conn_err)}
                )

            # 优先复用已打开的目标平台标签页，避免关闭用户原有登录页。
            contexts = browser.contexts
            context = contexts[0] if contexts else await browser.new_context()
            platform_domains = {
                "boss": "zhipin.com",
                "liepin": "liepin.com",
                "51job": "51job.com",
                "nowcoder": "nowcoder.com",
            }
            domain = platform_domains.get(platform, "")
            browser_page = next(
                (candidate for candidate in context.pages if domain and domain in candidate.url),
                None,
            )
            owns_page = browser_page is None
            if browser_page is None:
                browser_page = await context.new_page()

            try:
                logger.info(f"CDP 打开目标岗位页面: {target_url}")
                await browser_page.goto(target_url, timeout=int(timeout_seconds * 1000), wait_until="domcontentloaded")
                if browser_page.url in {"", "about:blank"}:
                    raise CrawlerExecutionError(
                        f"{platform} 平台导航后页面为空白",
                        platform,
                        target_url,
                        {"reason_code": "navigation_blocked"},
                    )

                # 动态站点需要等待执行上下文重建和职位卡片渲染；
                # 轮询比固定 sleep 更适合冷启动和慢网络场景。
                selectors = {
                    "boss": ".job-card-wrapper, .job-card-box, li.job-card-box",
                    "liepin": ".job-card-pc-container, .job-card-wrapper",
                    "51job": ".joblist-item, .j_joblist .e, .job-item",
                    "nowcoder": ".job-item, .rec-job-item, .feed-item",
                }
                selector = selectors.get(platform, "")
                deadline = asyncio.get_running_loop().time() + min(timeout_seconds, 20.0)
                card_count = 0
                while selector and asyncio.get_running_loop().time() < deadline:
                    try:
                        card_count = await browser_page.locator(selector).count()
                    except Exception:
                        card_count = 0
                    if card_count:
                        break
                    await asyncio.sleep(0.8)

                # 轻微滚动触发懒加载，再给已渲染卡片一次机会。
                await browser_page.evaluate("window.scrollBy(0, 800);")
                if not card_count:
                    await asyncio.sleep(0.8)

                page_content = await browser_page.content()
                blocked_reason = None
                lowered_content = page_content.lower()
                if "验证码" in page_content or "security.min.js" in lowered_content or "acw_tc" in lowered_content:
                    blocked_reason = "anti_bot"
                elif any(marker in lowered_content for marker in ("请先登录", "立即登录", "登录后查看", "login required")):
                    blocked_reason = "auth_required"
                if blocked_reason:
                    raise CrawlerExecutionError(
                        f"{platform} 页面需要完成登录或安全验证",
                        platform,
                        target_url,
                        {"reason_code": blocked_reason},
                    )

                # 执行专属真实 DOM 抽取脚本
                raw_extracted = await browser_page.evaluate(extractor_js)
                if not isinstance(raw_extracted, list):
                    raise CrawlerExecutionError(
                        f"{platform} 页面 DOM 返回格式异常",
                        platform,
                        target_url,
                        {"reason_code": "dom_missing"},
                    )
                if not raw_extracted:
                    raise CrawlerExecutionError(
                        f"{platform} 页面未找到岗位卡片，可能页面结构已变化或尚未完成渲染",
                        platform,
                        target_url,
                        {"reason_code": "dom_missing"},
                    )

                logger.info(f"{platform} 真实 DOM 提取成功，捕获到 {len(raw_extracted)} 条真实岗位")

                # 补全元数据
                normalized_jobs = []
                for item in raw_extracted[:limit]:
                    if not item.get("title") or not item.get("company"):
                        continue
                    item["source_platform"] = platform
                    item["city"] = item.get("city") or city
                    item["job_type"] = job_type
                    normalized_jobs.append(item)

                has_more = await cls._detect_has_more(browser_page, platform)
                return {
                    "items": normalized_jobs,
                    "page": page,
                    "has_more": has_more,
                    "next_page": page + 1 if has_more else None,
                }

            except CrawlerExecutionError:
                raise
            except Exception as run_err:
                logger.error(f"CDP 抓取页面 {target_url} 异常: {run_err}")
                raise CrawlerExecutionError(
                    message=f"采集平台 {platform} 真实页面发生异常: {run_err}",
                    platform=platform,
                    url=target_url,
                    details={"error": str(run_err)}
                )
            finally:
                if owns_page:
                    try:
                        await browser_page.close()
                    except Exception:
                        pass

    @classmethod
    def crawl_jobs_via_playwright(
        cls,
        platform: str,
        keyword: str,
        city: str,
        city_code: str,
        job_type: str = "social",
        limit: int = 10,
        headless: bool = True,
        timeout_seconds: float = 20.0,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """通过同步封装调用异步独立 Playwright 采集。"""
        if limit < 1 or limit > 50:
            raise ValueError("limit 必须在 1 到 50 之间")
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    cls._async_crawl_jobs_via_playwright(
                        platform, keyword, city, city_code, job_type, limit,
                        headless, timeout_seconds, page,
                    )
                )
                return future.result(timeout=timeout_seconds + 5)
        else:
            return loop.run_until_complete(
                cls._async_crawl_jobs_via_playwright(
                    platform, keyword, city, city_code, job_type, limit,
                    headless, timeout_seconds, page,
                )
            )

    @classmethod
    async def _detect_has_more(cls, browser_page: Any, platform: str) -> bool:
        """从真实分页控件 DOM 判断是否存在下一页。"""
        selectors = {
            "boss": ".ui-pagination-next, .pagination-next, a.next",
            "liepin": ".ant-pagination-next, .pagination-next, a.next",
            "51job": ".p_in li:last-child, .pagination-next, a.next",
            "nowcoder": ".pagination-next, .next-page, button[aria-label*='下一页']",
        }
        selector = selectors.get(platform)
        if not selector:
            return False
        try:
            return bool(await browser_page.locator(selector).evaluate(
                "el => !el.classList.contains('disabled') && !el.hasAttribute('disabled')"
            ))
        except Exception:
            return False

    @classmethod
    async def _async_crawl_jobs_via_playwright(
        cls,
        platform: str,
        keyword: str,
        city: str,
        city_code: str,
        job_type: str = "social",
        limit: int = 10,
        headless: bool = True,
        timeout_seconds: float = 20.0,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """异步独立 Playwright 抓取。"""
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        from playwright.async_api import async_playwright

        target_url = DOMExtractors.get_search_url(
            platform, keyword, city_code, job_type, page=page,
        )
        extractor_js = DOMExtractors.get_extractor_js(platform)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ]
            )
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            browser_page = await context.new_page()

            try:
                logger.info(f"Playwright 独立浏览器打开目标页面: {target_url}")
                await browser_page.goto(target_url, timeout=int(timeout_seconds * 1000), wait_until="domcontentloaded")
                await asyncio.sleep(2.5)
                await browser_page.evaluate("window.scrollBy(0, 800);")
                await asyncio.sleep(1.0)

                page_content = (await browser_page.content()).lower()
                blocked_reason = None
                if "验证码" in page_content or "security.min.js" in page_content or "acw_tc" in page_content:
                    blocked_reason = "anti_bot"
                elif any(marker in page_content for marker in ("请先登录", "立即登录", "登录后查看", "login required")):
                    blocked_reason = "auth_required"
                if blocked_reason:
                    raise CrawlerExecutionError(
                        f"{platform} 页面需要完成登录或安全验证",
                        platform,
                        target_url,
                        {"reason_code": blocked_reason},
                    )

                raw_extracted = await browser_page.evaluate(extractor_js)
                if not isinstance(raw_extracted, list) or not raw_extracted:
                    raise CrawlerExecutionError(
                        f"{platform} 页面未找到岗位卡片，可能页面结构已变化或尚未完成渲染",
                        platform,
                        target_url,
                        {"reason_code": "dom_missing"},
                    )

                normalized_jobs = []
                for item in raw_extracted[:limit]:
                    if not item.get("title") or not item.get("company"):
                        continue
                    item["source_platform"] = platform
                    item["city"] = item.get("city") or city
                    item["job_type"] = job_type
                    normalized_jobs.append(item)

                has_more = await cls._detect_has_more(browser_page, platform)
                return {
                    "items": normalized_jobs,
                    "page": page,
                    "has_more": has_more,
                    "next_page": page + 1 if has_more else None,
                }
            except CrawlerExecutionError:
                raise
            except Exception as e:
                raise CrawlerExecutionError(
                    message=f"Playwright 抓取平台 {platform} 失败: {e}",
                    platform=platform,
                    url=target_url,
                    details={"error": str(e)}
                )
            finally:
                await browser.close()
