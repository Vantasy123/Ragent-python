import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.models import Base
from app.services.crawlers.dom_extractors import DOMExtractors
from app.services.crawlers.cdp_browser_driver import (
    CDPBrowserDriver,
    CrawlerExecutionError,
)
from app.services.job_crawler_service import JobCrawlerService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_detail_extractor_contract():
    """详情 DOM 脚本应包含真实页面语义字段提取逻辑。"""
    script = DOMExtractors.get_detail_extractor_js("boss")
    assert "jd_found" in script
    assert "document.body" not in script
    assert "responsibilities" in script
    assert "required_skills" in script
    assert "benefits" in script


def test_cdp_detail_missing_url():
    """详情 URL 为空时应返回结构化执行错误。"""
    with pytest.raises(CrawlerExecutionError) as exc_info:
        CDPBrowserDriver.crawl_job_detail_via_cdp("boss", "")
    assert exc_info.value.details["reason_code"] == "missing_url"


def test_detail_driver_rejects_body_fallback_or_short_jd(monkeypatch):
    """详情页只出现壳页面或短文本时不得误标记为详情采集成功。"""
    class FakePage:
        url = "https://example.test/job"

        async def goto(self, *_args, **_kwargs):
            return None

        async def evaluate(self, _script):
            return {"jd_text": "登录后查看", "jd_found": False}

        async def close(self):
            return None

    class FakeContext:
        async def new_page(self):
            return FakePage()

    class FakeBrowser:
        contexts = [FakeContext()]

    class FakePlaywright:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        class chromium:
            @staticmethod
            async def connect_over_cdp(_url):
                return FakeBrowser()

    class FakePlaywrightFactory:
        def __call__(self):
            return FakePlaywright()

    import sys
    from types import ModuleType
    fake_async_api = ModuleType("playwright.async_api")
    fake_async_api.async_playwright = FakePlaywrightFactory()
    fake_playwright = ModuleType("playwright")
    fake_playwright.async_api = fake_async_api
    monkeypatch.setitem(sys.modules, "playwright", fake_playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_async_api)
    monkeypatch.setattr(CDPBrowserDriver, "check_cdp_status", lambda _url: {"connected": True})

    with pytest.raises(CrawlerExecutionError) as exc_info:
        CDPBrowserDriver.crawl_job_detail_via_cdp("boss", "https://example.test/job")

    assert exc_info.value.details["reason_code"] == "dom_missing"


    """详情失败应按重试次数执行，并保留列表摘要岗位。"""
    crawler = JobCrawlerService(db_session)
    calls = []

    def fail_detail(platform, source_url, cdp_url):
        calls.append((platform, source_url, cdp_url))
        raise CrawlerExecutionError(
            "页面超时", platform, source_url, {"reason_code": "navigation_timeout"},
        )

    monkeypatch.setattr(CDPBrowserDriver, "crawl_job_detail_via_cdp", fail_detail)
    listing = {
        "title": "后端工程师",
        "company": "真实公司",
        "source_platform": "boss",
        "source_url": "https://www.zhipin.com/job_detail/1.html",
        "jd_text": "列表摘要",
    }
    result = crawler.enrich_job_details([listing], mode="cdp", max_retries=2)

    assert len(calls) == 3
    assert result["stats"] == {
        "attempted": 1, "succeeded": 0, "failed": 1, "skipped": 0,
    }
    assert result["jobs"][0]["title"] == "后端工程师"
    assert result["jobs"][0]["jd_text"] == "列表摘要"
    assert '"reason_code": "navigation_timeout"' in result["jobs"][0]["detail_error"]


def test_enrich_job_details_success_and_skip(monkeypatch, db_session):
    """详情成功应合并真实结果，无 URL 岗位应标记跳过。"""
    crawler = JobCrawlerService(db_session)

    monkeypatch.setattr(
        CDPBrowserDriver,
        "crawl_job_detail_via_cdp",
        lambda platform, source_url, cdp_url: {
            "title": "详情标题",
            "jd_text": "完整 JD",
            "required_skills": ["Python"],
        },
    )
    result = crawler.enrich_job_details(
        [
            {"title": "列表标题", "company": "公司", "source_platform": "boss", "source_url": "https://example.test/job"},
            {"title": "无链接岗位", "company": "公司", "source_platform": "boss"},
        ],
        mode="cdp",
    )

    assert result["stats"] == {
        "attempted": 1, "succeeded": 1, "failed": 0, "skipped": 1,
    }
    assert result["jobs"][0]["jd_text"] == "完整 JD"
    assert result["jobs"][0]["detail_status"] == "success"
    assert result["jobs"][1]["detail_status"] == "skipped"
