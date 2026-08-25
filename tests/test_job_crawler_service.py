"""多平台岗位采集与数据同步中枢测试。"""

from __future__ import annotations

import pytest
from datetime import timedelta
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.models import Base, JobOpportunity
from app.services.job_crawler_service import PlatformCityMapper, SalaryNormalizer, JobCrawlerService
from app.core.time_utils import utc_now_naive


@pytest.fixture
def db_session():
    """提供测试用 SQLite 内存数据库。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_platform_city_mapper():
    """测试城市编码映射解析。"""
    assert PlatformCityMapper.get_code("boss", "北京") == "101010100"
    assert PlatformCityMapper.get_code("liepin", "上海") == "020"
    assert PlatformCityMapper.get_code("51job", "深圳") == "040000"
    assert PlatformCityMapper.get_code("nowcoder", "杭州") == "5"
    assert PlatformCityMapper.get_code("boss", "全国") == "100010000"


def test_salary_normalizer():
    """测试薪资语法智能解析与归一化。"""
    # 1. 标准 K 格式
    assert SalaryNormalizer.parse("25-45K·16薪") == (25, 45, "k")
    assert SalaryNormalizer.parse("15-28k") == (15, 28, "k")

    # 2. 万/年格式 (30-50万/年折算为月薪)
    s_min, s_max, unit = SalaryNormalizer.parse("30-60万/年")
    assert unit == "k"
    assert s_min == 25  # 30 * 10 / 12 = 25k
    assert s_max == 50  # 60 * 10 / 12 = 50k

    # 3. 日薪格式 (200-400元/天按 21.75 天折算)
    d_min, d_max, d_unit = SalaryNormalizer.parse("200-400元/天")
    assert d_unit == "k"
    assert d_min == 4
    assert d_max == 8

    # 4. 面议与缺省状态必须显式区分，不能伪造成固定薪资
    assert SalaryNormalizer.parse("面议") == (None, None, "negotiable")
    assert SalaryNormalizer.parse("") == (None, None, "unknown")


def test_job_identity_upsert_tracks_external_id_url_hash_and_last_seen(db_session):
    """外部职位 ID、规范化 URL 和 JD hash 应支持稳定增量更新。"""
    crawler = JobCrawlerService(db_session)

    first = {
        "title": "后端工程师",
        "company": "测试公司",
        "city": "北京",
        "salary_str": "面议",
        "jd_text": "负责服务端开发",
        "source_platform": "boss",
        "source_url": "HTTPS://WWW.ZHIPIN.COM/job_detail/abc/?utm_source=test&spm=foo&x=1",
        "external_job_id": "boss-abc",
    }
    is_new, job = crawler._upsert_job(first)
    assert is_new is True
    assert job is not None
    assert job.external_job_id == "boss-abc"
    assert job.source_url_canonical == "https://www.zhipin.com/job_detail/abc?x=1"
    first_seen = job.last_seen_at
    first_hash = job.jd_hash
    assert job.salary_status == "negotiable"

    second = {
        **first,
        "title": "后端工程师（更新）",
        "jd_text": "负责服务端开发和性能优化",
        "source_url": "https://www.zhipin.com/job_detail/abc?x=1&utm_campaign=ignored",
        "salary_str": "25-40K",
    }
    is_new, updated = crawler._upsert_job(second)
    assert is_new is False
    assert updated is not None
    assert updated.id == job.id
    assert updated.title == "后端工程师（更新）"
    assert updated.jd_hash != first_hash
    assert updated.last_seen_at is not None
    assert updated.last_seen_at >= first_seen
    assert updated.salary_status == "known"


def test_job_external_id_is_scoped_by_platform(db_session):
    """不同平台可以使用相同外部职位 ID。"""
    crawler = JobCrawlerService(db_session)
    common = {
        "title": "同名岗位",
        "company": "同一公司",
        "city": "上海",
        "salary_str": "20-30K",
        "jd_text": "岗位职责",
        "external_job_id": "same-id",
    }
    created = []
    for platform in ("boss", "liepin"):
        is_new, job = crawler._upsert_job({**common, "source_platform": platform})
        assert is_new is True
        created.append(job)
    assert created[0].id != created[1].id
    assert db_session.query(JobOpportunity).count() == 2
def test_stale_jobs_are_closed_only_after_successful_nonempty_platform_sync(db_session, monkeypatch):
    """成功采集时关闭长期未见岗位，采集失败时保持 active。"""
    crawler = JobCrawlerService(db_session)
    stale = JobOpportunity(
        title="旧岗位",
        company="旧公司",
        city="北京",
        source_platform="boss",
        job_type="social",
        status="active",
        last_seen_at=utc_now_naive() - timedelta(days=31),
    )
    db_session.add(stale)
    db_session.commit()

    monkeypatch.setattr(
        crawler,
        "_fetch_jobs_from_platform",
        lambda *args, **kwargs: [{
            "title": "新岗位",
            "company": "新公司",
            "city": "北京",
            "source_platform": "boss",
            "source_url": "https://example.com/jobs/new",
            "salary_str": "20-30K",
        }],
    )
    monkeypatch.setattr(crawler, "check_driver_status", lambda _url: {"connected": False})
    result = crawler.sync_platform_jobs(platform="boss", city="北京", limit_per_platform=1)
    assert result["stats"]["closed"] == 1
    assert db_session.get(JobOpportunity, stale.id).status == "closed"

    failed = JobOpportunity(
        title="故障期间岗位",
        company="公司",
        city="北京",
        source_platform="boss",
        job_type="social",
        status="active",
        last_seen_at=utc_now_naive() - timedelta(days=31),
    )
    db_session.add(failed)
    db_session.commit()
    monkeypatch.setattr(crawler, "_fetch_jobs_from_platform", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("平台不可用")))
    result = crawler.sync_platform_jobs(platform="boss", city="北京", limit_per_platform=1)
    assert result["stats"]["status"] == "failed"
    assert db_session.get(JobOpportunity, failed.id).status == "active"



def test_sync_rolls_back_job_batch_when_upsert_fails(db_session, monkeypatch):
    """批次内岗位入库失败时，不应留下半批数据或下架变更。"""
    crawler = JobCrawlerService(db_session)
    stale = JobOpportunity(
        title="待保留岗位",
        company="测试公司",
        city="北京",
        source_platform="boss",
        job_type="social",
        status="active",
        last_seen_at=utc_now_naive() - timedelta(days=31),
    )
    db_session.add(stale)
    db_session.commit()

    raw_jobs = [
        {
            "title": "岗位一",
            "company": "公司一",
            "city": "北京",
            "source_platform": "boss",
            "source_url": "https://example.com/jobs/one",
            "salary_str": "20-30K",
        },
        {
            "title": "岗位二",
            "company": "公司二",
            "city": "北京",
            "source_platform": "boss",
            "source_url": "https://example.com/jobs/two",
            "salary_str": "20-30K",
        },
    ]
    monkeypatch.setattr(crawler, "check_driver_status", lambda _url: {"connected": False})
    monkeypatch.setattr(crawler, "_fetch_jobs_from_platform", lambda *args, **kwargs: raw_jobs)

    original_upsert = crawler._upsert_job
    calls = 0

    def failing_upsert(raw, persist=True):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("批次写入失败")
        return original_upsert(raw, persist=persist)

    monkeypatch.setattr(crawler, "_upsert_job", failing_upsert)
    with pytest.raises(RuntimeError, match="批次写入失败"):
        crawler.sync_platform_jobs(platform="boss", city="北京", limit_per_platform=2)

    assert db_session.query(JobOpportunity).filter(
        JobOpportunity.source_platform == "boss",
        JobOpportunity.title.in_(["岗位一", "岗位二"]),
    ).count() == 0
    assert db_session.get(JobOpportunity, stale.id).status == "active"


def test_job_crawler_service_sync(db_session, monkeypatch):
    """测试多招聘平台岗位采集、防重与 Upsert 入库。"""
    crawler = JobCrawlerService(db_session)

    # Mock parse_jd_text to fast-track test without waiting on remote LLM calls
    monkeypatch.setattr(
        crawler.matching_service,
        "parse_jd_text",
        MagicMock(return_value={
            "required_skills": ["Java", "Spring Boot", "MySQL"],
            "preferred_skills": ["Redis", "Kafka", "微服务"],
            "responsibilities": ["核心业务开发", "系统性能调优"],
            "benefits": ["五险一金", "弹性打卡"]
        })
    )

    # 1. 平台列表
    platforms = crawler.get_supported_platforms()
    assert len(platforms) == 4
    assert any(p["id"] == "boss" for p in platforms)
    assert any(p["id"] == "liepin" for p in platforms)

    # 外部招聘平台不属于离线测试边界；用真实采集器契约数据验证同步、去重和 Upsert。
    fixture_jobs = [
        {
            "title": f"Java 后端工程师 {index}",
            "company": f"测试公司 {index}",
            "city": "北京",
            "salary_str": "25-45K",
            "jd_text": "负责 Java、Spring Boot、MySQL 核心业务开发",
            "source_platform": "boss",
            "source_url": f"https://www.zhipin.com/job_detail/test-{index}",
            "required_skills": ["Java", "Spring Boot", "MySQL"],
        }
        for index in range(3)
    ]
    all_fixture_jobs = {
        platform: [
            {
                **item,
                "source_platform": platform,
                "source_url": item["source_url"].replace("test-", f"{platform}-"),
            }
            for item in (fixture_jobs if platform == "boss" else fixture_jobs[:2])
        ]
        for platform in ("boss", "liepin", "51job", "nowcoder")
    }

    def fetch_fixture(platform, keyword, city, job_type, limit=10, mode="auto", cdp_url=None):
        return all_fixture_jobs.get(platform, fixture_jobs)[:limit]

    monkeypatch.setattr(crawler, "_fetch_jobs_from_platform", fetch_fixture)

    # 1. 平台列表
    platforms = crawler.get_supported_platforms()
    assert len(platforms) == 4
    assert any(p["id"] == "boss" for p in platforms)
    assert any(p["id"] == "liepin" for p in platforms)

    # 2. 针对单个平台同步
    res_boss = crawler.sync_platform_jobs(
        platform="boss",
        keyword="Java后端",
        city="北京",
        limit_per_platform=3
    )

    assert res_boss["stats"]["total_fetched"] == 3
    assert res_boss["stats"]["created"] == 3
    assert res_boss["stats"]["updated"] == 0

    # 检查数据库内是否已存在该岗位
    db_jobs = db_session.query(JobOpportunity).filter(JobOpportunity.source_platform == "boss").all()
    assert len(db_jobs) == 3
    assert all(j.city == "北京" for j in db_jobs)

    # 3. 重复同步相同平台应触发 Upsert 更新而非重复插入
    res_boss_repeat = crawler.sync_platform_jobs(
        platform="boss",
        keyword="Java后端",
        city="北京",
        limit_per_platform=3
    )
    # 因为防重键相同，created 应为 0，updated 为 3
    assert res_boss_repeat["stats"]["created"] == 0
    assert res_boss_repeat["stats"]["updated"] == 3
    assert db_session.query(JobOpportunity).filter(JobOpportunity.source_platform == "boss").count() == 3

    # 4. 全部平台多源聚合采集
    res_all = crawler.sync_platform_jobs(
        platform="all",
        keyword="Python大模型",
        city="上海",
        limit_per_platform=2
    )
    assert res_all["stats"]["total_fetched"] == 8
    assert res_all["stats"]["created"] > 0


def test_sync_collects_multiple_pages_and_closes_stale_only_when_complete(db_session, monkeypatch):
    """多页同步应按 next_page 继续，并在完整结束后才关闭 stale 岗位。"""
    crawler = JobCrawlerService(db_session)
    stale = JobOpportunity(
        title="分页旧岗位",
        company="旧公司",
        city="北京",
        source_platform="boss",
        job_type="social",
        status="active",
        last_seen_at=utc_now_naive() - timedelta(days=31),
    )
    db_session.add(stale)
    db_session.commit()

    requested_pages = []

    def fetch_page(platform, keyword, city, job_type, limit=10, mode="auto", cdp_url=None, page=1):
        requested_pages.append(page)
        if page == 1:
            return {
                "items": [{
                    "title": "第一页岗位",
                    "company": "公司一",
                    "city": "北京",
                    "source_platform": "boss",
                    "source_url": "https://example.com/jobs/page-1",
                    "salary_str": "20-30K",
                }],
                "page": 1,
                "has_more": True,
                "next_page": 2,
            }
        return {
            "items": [{
                "title": "第二页岗位",
                "company": "公司二",
                "city": "北京",
                "source_platform": "boss",
                "source_url": "https://example.com/jobs/page-2",
                "salary_str": "25-35K",
            }],
            "page": 2,
            "has_more": False,
            "next_page": None,
        }

    monkeypatch.setattr(crawler, "_fetch_jobs_from_platform", fetch_page)
    monkeypatch.setattr(crawler, "check_driver_status", lambda _url: {"connected": False})

    result = crawler.sync_platform_jobs(
        platform="boss", city="北京", limit_per_platform=2, max_pages=2,
    )

    assert requested_pages == [1, 2]
    assert result["stats"]["total_fetched"] == 2
    assert result["stats"]["has_more"] is False
    assert result["stats"]["next_page"] is None
    assert result["stats"]["closed"] == 1
    assert db_session.get(JobOpportunity, stale.id).status == "closed"


def test_live_search_keeps_all_requested_pages_and_reports_total(db_session, monkeypatch):
    """实时直搜多页时应返回所有已采集岗位，而不是只保留第一页容量。"""
    crawler = JobCrawlerService(db_session)
    requested_pages = []

    def fetch_page(platform, keyword, city, job_type, limit=10, mode="auto", cdp_url=None, page=1):
        requested_pages.append(page)
        return {
            "items": [{
                "title": f"实时岗位 {page}",
                "company": "实时公司",
                "city": "北京",
                "source_platform": platform,
                "source_url": f"https://example.com/live/{page}",
            }],
            "page": page,
            "has_more": page < 3,
            "next_page": page + 1 if page < 3 else None,
        }

    monkeypatch.setattr(crawler, "_fetch_jobs_from_platform", fetch_page)
    result = crawler.live_search_platform_jobs(
        platform="boss", keyword="Java", city="北京", limit_per_platform=1, max_pages=3,
    )

    assert requested_pages == [1, 2, 3]
    assert result["status"] == "success"
    assert result["total"] == 3
    assert len(result["jobs"]) == 3
    assert result["has_more"] is False
    assert result["next_page"] is None
    assert result["persisted"] is False


    """达到 max_pages 但仍有下一页时，不得执行 stale 下架。"""
    crawler = JobCrawlerService(db_session)
    stale = JobOpportunity(
        title="未完成分页旧岗位",
        company="旧公司",
        city="北京",
        source_platform="boss",
        job_type="social",
        status="active",
        last_seen_at=utc_now_naive() - timedelta(days=31),
    )
    db_session.add(stale)
    db_session.commit()

    monkeypatch.setattr(
        crawler,
        "_fetch_jobs_from_platform",
        lambda *args, **kwargs: {
            "items": [{
                "title": "第一页岗位",
                "company": "公司一",
                "city": "北京",
                "source_platform": "boss",
                "source_url": "https://example.com/jobs/page-1",
                "salary_str": "20-30K",
            }],
            "page": kwargs.get("page", 1),
            "has_more": True,
            "next_page": kwargs.get("page", 1) + 1,
        },
    )
    monkeypatch.setattr(crawler, "check_driver_status", lambda _url: {"connected": False})

    result = crawler.sync_platform_jobs(
        platform="boss", city="北京", limit_per_platform=1, max_pages=1,
    )

    assert result["stats"]["has_more"] is True
    assert result["stats"]["next_page"] == 2
    assert result["stats"]["closed"] == 0
    assert db_session.get(JobOpportunity, stale.id).status == "active"
