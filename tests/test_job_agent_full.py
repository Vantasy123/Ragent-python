"""智能求职 Agent 全链路单元测试与 API 测试。"""

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.core.database import Base
from app.domain.models import (
    User,
    ResumeProfile,
    JobOpportunity,
    JobApplication,
    MockInterviewSession,
    ApplicationFormMapping
)
from app.services.job_resume_service import JobResumeService
from app.services.job_matching_service import JobMatchingService, ensure_default_job_samples
from app.services.job_application_service import JobApplicationService
from app.services.mock_interview_service import MockInterviewService
from app.services.job_auto_fill_service import JobAutoFillService
from app.agents.tool_registry import UnifiedToolRegistry, ToolCallRequest
from app.main import app
from app.services.security import create_token


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    user = User(
        id="test_user_job_1",
        username="jobseeker",
        nickname="张三",
        password_hash="fakehash",
        role="user",
        is_active=True
    )
    admin = User(
        id="admin_user_job_1",
        username="admin",
        nickname="管理员",
        password_hash="fakehash",
        role="admin",
        is_active=True
    )
    session.add(user)
    session.add(admin)
    session.commit()

    yield session
    session.close()


def test_resume_service(db_session):
    service = JobResumeService(db_session)
    raw_resume = """
    张三 | 13800138000 | zhangsan@example.com | 期望职位：后端开发工程师
    北京航空航天大学 计算机科学与技术 本科 (2020 - 2024)
    项目经历：
    高并发分布式电商秒杀系统
    - 使用 Go 和 Redis 构建分布式预扣库存模块，承载 50000 QPS 峰值。
    - 采用 Kafka 进行异步落库削峰，系统 P99 延迟降低 60%。
    技能：Go, Python, Java, MySQL, Redis, Kafka, Docker
    """
    parsed = service.parse_resume_text(raw_resume)
    assert "basic_info" in parsed
    assert "skills" in parsed

    score, details = service.calculate_resume_score(parsed)
    assert 0 <= score <= 100
    assert "completeness" in details

    profile = service.create_or_update_resume(
        user_id="test_user_job_1",
        name="张三的主简历",
        raw_text=raw_resume,
        parsed_data=parsed,
        is_default=True
    )
    assert profile.id is not None
    assert profile.score >= 60

    star_opt = service.optimize_project_star({
        "project_name": "电商秒杀系统",
        "tech_stack": ["Go", "Redis"],
        "background": "高并发库存扣减瓶颈"
    })
    assert "action" in star_opt or "star_summary" in star_opt

    version = service.create_custom_version(
        resume_id=profile.id,
        version_name="大厂后端定向版",
        target_job_title="高级Go后端工程师"
    )
    assert version.id is not None
    assert len(profile.versions) == 2


def test_job_matching_service(db_session):
    ensure_default_job_samples(db_session)
    service = JobMatchingService(db_session)

    jobs, total = service.get_job_postings()
    assert total >= 4
    job = jobs[0]

    resume_service = JobResumeService(db_session)
    profile = resume_service.create_or_update_resume(
        user_id="test_user_job_1",
        name="测试简历",
        raw_text="熟练掌握 Go, MySQL, Redis, 高并发开发"
    )

    analysis = service.analyze_job_match(
        user_id="test_user_job_1",
        resume_id=profile.id,
        job_id=job.id
    )
    assert analysis.overall_score > 0
    assert len(analysis.matched_skills) > 0 or len(analysis.missing_skills) > 0

    greeting = service.generate_greeting(
        user_id="test_user_job_1",
        resume_id=profile.id,
        job_id=job.id
    )
    assert len(greeting) > 10


def test_job_application_kanban(db_session):
    ensure_default_job_samples(db_session)
    job_service = JobMatchingService(db_session)
    jobs, _ = job_service.get_job_postings()
    job = jobs[0]

    app_service = JobApplicationService(db_session)
    app = app_service.create_application(
        user_id="test_user_job_1",
        job_id=job.id,
        stage="wishlist",
        apply_channel="牛客网申"
    )
    assert app.id is not None

    app_service.update_application_stage(
        application_id=app.id,
        user_id="test_user_job_1",
        stage="interview_1",
        notes="已约技术一面"
    )

    app_service.add_interview_record(
        application_id=app.id,
        user_id="test_user_job_1",
        round_title="技术一面",
        interview_time="2026-08-25 14:00",
        interviewer="字节后端架构师",
        questions_and_feedback="表现优秀，深入考察了 Redis 与分布式锁"
    )

    stats = app_service.get_dashboard_statistics("test_user_job_1")
    assert stats["total_applications"] >= 1
    assert stats["interview_count"] >= 1


def test_mock_interview_service(db_session):
    service = MockInterviewService(db_session)
    session = service.create_interview_session(
        user_id="test_user_job_1",
        target_role="Go 后端开发",
        role_type="tech_expert",
        difficulty="intermediate"
    )
    assert session.id is not None
    assert len(session.records) >= 1

    first_record = session.records[0]
    evaluated = service.evaluate_answer(
        record_id=first_record.id,
        user_answer="InnoDB 底层使用 B+ 树索引，非叶子节点存储主键值，叶子节点双向链表相连存储整行记录。回表通过二级索引查找主键再去聚簇索引拿数据。"
    )
    assert evaluated.score > 0
    assert len(evaluated.feedback) > 0

    finished = service.finish_session_and_generate_report(session.id)
    assert finished.status == "completed"
    assert "technical_depth" in finished.detailed_dimensions


def test_autofill_and_bridge(db_session):
    resume_service = JobResumeService(db_session)
    profile = resume_service.create_or_update_resume(
        user_id="test_user_job_1",
        name="网申测试简历",
        raw_text="张三 13800000000 zhangsan@test.com 本科 软件工程"
    )
    autofill_service = JobAutoFillService(db_session)
    payload = autofill_service.generate_form_fill_payload(
        resume_id=profile.id,
        platform_name="nowcoder"
    )
    assert payload["platform"] == "nowcoder"
    assert "form_fields" in payload
    assert payload["form_fields"]["name"] != ""


def test_job_agent_tools():
    import asyncio

    async def _runner():
        registry = UnifiedToolRegistry(include_ops=False)
        tools = registry.list_tools(audience="user")
        tool_names = [t["name"] for t in tools]
        assert "job_parse_resume" in tool_names
        assert "job_search_postings" in tool_names
        assert "job_generate_interview_questions" in tool_names
        assert "job_generate_greeting" in tool_names

        res = await registry.call(
            ToolCallRequest(
                name="job_search_postings",
                args={"keyword": "后端", "limit": 5}
            ),
            actor_role="user"
        )
        assert res.success is True

    asyncio.run(_runner())
