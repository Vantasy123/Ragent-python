"""真实浏览器 CDP 驱动与多平台 DOM 采集器全量测试套件。"""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.models import Base, JobOpportunity
from app.services.crawlers.dom_extractors import DOMExtractors
from app.services.crawlers.cdp_browser_driver import (
    CDPBrowserDriver,
    CrawlerConnectionError,
    CrawlerExecutionError,
)
from app.services.job_crawler_service import JobCrawlerService, SalaryNormalizer, PlatformCityMapper


@pytest.fixture
def db_session():
    """创建测试专用的内存 SQLite 数据库会话。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    yield session
    session.close()


def test_dom_extractors_do_not_fabricate_listing_jd():
    """列表卡片不能把标题、薪资或标签拼接成伪 JD，详情应单独采集。"""
    for script in (
        DOMExtractors.get_extractor_js("boss"),
        DOMExtractors.get_extractor_js("liepin"),
        DOMExtractors.get_extractor_js("51job"),
        DOMExtractors.get_extractor_js("nowcoder"),
    ):
        assert "${company}" not in script or "jd_text: ''" in script or "jd_text: desc" in script


def test_salary_status_is_explicit_in_frontend_contract():
    """该契约由 API 返回，前端可区分面议和未知薪资。"""
    from pathlib import Path
    service_source = Path("frontend/src/services/jobService.ts").read_text(encoding="utf-8")
    assert "salaryStatus" in service_source
    assert "'negotiable'" in service_source
    assert "'unknown'" in service_source


def test_dom_extractors_urls_and_scripts():
    """测试各大平台的搜索 URL 与 JS 提取脚本生成。"""
    for plat in ["boss", "liepin", "51job", "nowcoder"]:
        url = DOMExtractors.get_search_url(plat, "Python大模型", "101010100")
        assert "http" in url
        assert "Python" in url or "%E5%A4%A7%E6%A8%A1%E5%9E%8B" in url or "Python%E5%A4%A7%E6%A8%A1%E5%9E%8B" in url

        js_script = DOMExtractors.get_extractor_js(plat)
        assert len(js_script) > 50
        assert "document.querySelectorAll" in js_script


def test_dom_extractors_pagination_contract():
    """分页 URL 应使用平台对应参数，并拒绝非法页码。"""
    expected_params = {
        "boss": "page=2",
        "liepin": "curPage=2",
        "51job": "page=2",
        "nowcoder": "page=2",
    }
    for platform, expected in expected_params.items():
        url = DOMExtractors.get_search_url(
            platform, "Python", "101010100", page=2,
        )
        assert expected in url

    with pytest.raises(ValueError, match="page"):
        DOMExtractors.get_search_url("boss", "Python", "101010100", page=0)


    """测试薪资智能归一化引擎。"""
    # 1. k 格式
    s_min, s_max, s_unit = SalaryNormalizer.parse("25-45k·16薪")
    assert s_min == 25 and s_max == 45 and s_unit == "k"

    # 2. 万/年格式
    s_min, s_max, s_unit = SalaryNormalizer.parse("36-60万/年")
    assert s_min == 30 and s_max == 50 and s_unit == "k"

    # 3. 元/天格式
    s_min, s_max, s_unit = SalaryNormalizer.parse("300-500元/天")
    assert s_min >= 6 and s_max >= 10 and s_unit == "k"

    # 4. 面议必须显式标记，不能使用固定薪资兜底
    s_min, s_max, s_unit = SalaryNormalizer.parse("面议")
    assert (s_min, s_max, s_unit) == (None, None, "negotiable")


def test_cdp_url_uses_docker_host_gateway(monkeypatch):
    """容器部署应将默认本地 CDP 地址解析为宿主机网关。"""
    monkeypatch.setenv("RAGENT_RUNNING_IN_DOCKER", "true")
    assert CDPBrowserDriver.get_effective_cdp_url("http://127.0.0.1:9223") == "http://host.docker.internal:9223"
    assert CDPBrowserDriver.get_effective_cdp_url("http://localhost:9223") == "http://host.docker.internal:9223"
    assert CDPBrowserDriver.get_effective_cdp_url("http://cdp-proxy:9223") == "http://cdp-proxy:9223"


    """测试本地未启动 Chrome 9223 端口时的诊断报告。"""
    status = CDPBrowserDriver.check_cdp_status("http://127.0.0.1:9999")
    assert status["connected"] is False
    assert "无法连接到 Chrome 调试端口" in status["error"]
    assert "chrome.exe --remote-debugging-port=9223" in status["instruction"]


def test_cdp_status_online_mocked():
    """测试模拟 Chrome 9223 在线时的探测解析。"""
    with patch("httpx.Client.get") as mock_get:
        mock_version_resp = MagicMock(status_code=200)
        mock_version_resp.json.return_value = {
            "Browser": "Chrome/122.0.0.0",
            "Protocol-Version": "1.3",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/xxx"
        }
        mock_list_resp = MagicMock(status_code=200)
        mock_list_resp.json.return_value = [
            {"id": "1", "title": "BOSS直聘 - 招聘求职", "url": "https://www.zhipin.com/web/geek/job", "type": "page"},
            {"id": "2", "title": "猎聘 - 职位列表", "url": "https://www.liepin.com/zhaopin/", "type": "page"}
        ]
        mock_get.side_effect = [mock_version_resp, mock_list_resp]

        status = CDPBrowserDriver.check_cdp_status("http://127.0.0.1:9223")
        assert status["connected"] is True
        assert status["cdp_connected"] is True
        assert status["browser"] == "Chrome/122.0.0.0"
        assert status["tabs_count"] == 2
        assert "boss" in status["logged_in_platforms"]
        assert "liepin" in status["logged_in_platforms"]


def test_cdp_status_degrades_when_tab_list_is_unavailable():
    """CDP 版本接口正常但标签页接口失败时，不得误报可采集。"""
    with patch("httpx.Client.get") as mock_get:
        version_response = MagicMock(status_code=200)
        version_response.json.return_value = {"Browser": "Chrome/122"}
        list_response = MagicMock(status_code=401)
        mock_get.side_effect = [version_response, list_response]

        status = CDPBrowserDriver.check_cdp_status("http://127.0.0.1:9223")

    assert status["connected"] is False
    assert status["cdp_connected"] is True
    assert "非 200" in status["error"]


def test_job_crawler_upsert_real_job(db_session):
    """测试真实抓取结果的去重与增量 Upsert。"""
    crawler = JobCrawlerService(db_session)

    raw_job = {
        "title": "大模型架构专家",
        "company": "字节跳动",
        "city": "北京",
        "salary_str": "40-70K·16薪",
        "education_req": "硕士及以上",
        "experience_req": "3-5年",
        "source_platform": "boss",
        "source_url": "https://www.zhipin.com/job_detail/99999.html",
        "tags": ["Python", "PyTorch", "vLLM", "Agent架构"],
        "company_tags": ["核心业务", "六险一金"],
        "jd_text": "负责字节跳动 AI Agent 与大模型工程系统研发。"
    }

    # 首次插入
    is_new, job = crawler._upsert_job(raw_job)
    assert is_new is True
    assert job is not None
    assert job.salary_min == 40
    assert job.salary_max == 70
    assert job.source_url == "https://www.zhipin.com/job_detail/99999.html"

    # 重复插入触发更新
    raw_job["salary_str"] = "45-75K"
    is_new2, job2 = crawler._upsert_job(raw_job)
    assert is_new2 is False
    assert job2.id == job.id
    assert job2.salary_min == 45
    assert job2.salary_max == 75

    # 验证数据库中仅有 1 条
    assert db_session.query(JobOpportunity).count() == 1


def test_cdp_search_rejects_empty_dom_result(monkeypatch):
    """真实页面无岗位卡片时应返回结构化 DOM 失败，而不是空成功。"""
    async def fake_crawl(*_args, **_kwargs):
        raise CrawlerExecutionError(
            "页面未找到岗位卡片", "boss", "https://www.zhipin.com/web/geek/job",
            {"reason_code": "dom_missing"},
        )

    monkeypatch.setattr(CDPBrowserDriver, "_async_crawl_jobs_via_cdp", fake_crawl)
    with pytest.raises(CrawlerExecutionError) as exc_info:
        CDPBrowserDriver.crawl_jobs_via_cdp(
            "boss", "Python", "北京", "101010100", cdp_url="http://127.0.0.1:9223",
        )
    assert exc_info.value.details["reason_code"] == "dom_missing"


def test_sync_platform_jobs_with_mocked_cdp(db_session):
    """测试端到端 sync_platform_jobs 调度与入库流程。"""
    crawler = JobCrawlerService(db_session)

    mock_crawled_items = [
        {
            "title": "Golang后端架构师",
            "company": "腾讯科技",
            "city": "深圳",
            "salary_str": "35-55K",
            "experience_req": "3-5年",
            "education_req": "本科及以上",
            "source_platform": "liepin",
            "source_url": "https://www.liepin.com/job/88888.shtml",
            "tags": ["Golang", "gRPC", "K8s", "MySQL"],
            "company_tags": ["鹅厂名企"],
            "jd_text": "负责腾讯核心后台服务架构设计与高可用微服务演进。"
        }
    ]

    with patch.object(CDPBrowserDriver, "check_cdp_status", return_value={"connected": True, "tabs_count": 1}), \
         patch.object(CDPBrowserDriver, "crawl_jobs_via_cdp", return_value=mock_crawled_items):

        result = crawler.sync_platform_jobs(
            platform="liepin",
            keyword="Golang",
            city="深圳",
            limit_per_platform=5,
            mode="cdp"
        )

        assert result["stats"]["total_fetched"] == 1
        assert result["stats"]["created"] == 1
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["company"] == "腾讯科技"
        assert result["jobs"][0]["source_platform"] == "liepin"
