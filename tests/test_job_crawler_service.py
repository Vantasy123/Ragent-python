"""多平台岗位采集与数据同步中枢测试。"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.models import Base, JobOpportunity
from app.services.job_crawler_service import PlatformCityMapper, SalaryNormalizer, JobCrawlerService


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

    # 4. 面议与缺省兜底
    assert SalaryNormalizer.parse("面议") == (15, 30, "k")
    assert SalaryNormalizer.parse("") == (15, 30, "k")


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
