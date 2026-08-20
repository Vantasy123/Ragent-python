"""Ragent MCP (Model Context Protocol) 服务端单元测试。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.models import Base, ResumeProfile, JobOpportunity
from app.mcp_server import RagentMcpServer, MCP_TOOLS_DEFINITIONS


@pytest.fixture
def mock_db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    init_session = TestingSessionLocal()
    resume = ResumeProfile(
        user_id="test_user_001",
        name="测试求职者",
        target_role="Python大模型工程师",
        score=92,
        is_default=True,
        parsed_data={
            "basic_info": {"name": "张三", "phone": "13800138000", "email": "zhangsan@example.com"},
            "educations": [{"school": "清华大学", "major": "计算机", "degree": "硕士"}],
            "work_experiences": [],
            "project_experiences": [{"project_name": "AI Agent 系统", "role": "负责人", "star_highlights": "QPS提升5倍"}]
        }
    )
    init_session.add(resume)
    init_session.commit()
    init_session.close()

    monkeypatch.setattr("app.mcp_server.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def test_mcp_tools_definitions():
    """测试 MCP 工具列表定义完整性（包含 2 个渐进式发现工具与 4 个专有执行工具）。"""
    assert len(MCP_TOOLS_DEFINITIONS) == 6
    tool_names = [t["name"] for t in MCP_TOOLS_DEFINITIONS]
    assert "ragent_discover_capabilities" in tool_names
    assert "ragent_inspect_capability" in tool_names
    assert "ragent_sync_and_search_jobs" in tool_names
    assert "ragent_query_interview_rag" in tool_names
    assert "ragent_manage_resume_profile" in tool_names
    assert "ragent_export_autofill_payload" in tool_names


def test_mcp_handle_tool_call_resume_profile(mock_db_session):
    """测试 MCP 获取求职者简历档案。"""
    server = RagentMcpServer()
    res = server.handle_tool_call(
        "ragent_manage_resume_profile",
        {"action": "get_active"}
    )
    assert res["status"] == "success"
    assert res["active_resume"]["name"] == "测试求职者"
    assert res["active_resume"]["score"] == 92


def test_mcp_handle_tool_call_autofill_payload(mock_db_session):
    """测试 MCP 生成网申自动填表 Payload。"""
    server = RagentMcpServer()
    res = server.handle_tool_call(
        "ragent_export_autofill_payload",
        {"platform_name": "nowcoder", "add_to_kanban": False}
    )
    assert res["status"] == "success"
    assert res["platform"] == "nowcoder"
    assert res["autofill_payload"]["form_fields"]["name"] == "张三"
    assert res["autofill_payload"]["form_fields"]["phone"] == "13800138000"


def test_mcp_handle_tool_call_sync_jobs(mock_db_session):
    """测试 MCP 实时多招聘平台岗位同步。"""
    server = RagentMcpServer()
    res = server.handle_tool_call(
        "ragent_sync_and_search_jobs",
        {"action": "sync", "platform": "boss", "keyword": "Java", "limit": 2}
    )
    assert res["status"] == "success"
    assert res["stats"]["total_fetched"] == 2
    assert len(res["jobs"]) == 2
